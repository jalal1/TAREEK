# SPDX-License-Identifier: GPL-3.0-or-later
"""Where to put a secondary stop: at a survey distance, not at the nearest POI.

A chain such as Home-Shopping-Dining-Home gets its main destination from the
gravity OD matrix. Every other stop used to go to the nearest POI of its type
(work generator) or to a random POI within 1-3 km (non-work generator). The
plans then had stop-to-stop legs with a median of 1.3-1.5 km, against 3.9 km
(non-work days) and 6.4 km (work days) in NHTS for large metros. The short
legs take car-km out of the midday, which is one reason the count ratios run
low at midday and high in the morning (P1).

This model draws the stop-to-stop beeline distance from the survey's own
stop-to-stop trips (origin and destination both not Home), per destination
activity, weighted. The caller then takes a POI of the right type in a ring
around that distance (see POISpatialIndex.find_in_ring).

Config (opt-in):
    poi_assignment.stop_distance_source: "nearest" (default, old behaviour)
                                       | "survey"
    poi_assignment.survey_circuity: reported / beeline distance, default 1.25
    poi_assignment.stop_distance_max_km: longest leg kept, default 50
"""

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

from data_sources.base_survey_trip import BaseSurveyTrip as B

logger = logging.getLogger(__name__)

MIN_SAMPLES = 30


class StopDistanceModel:
    """Empirical, weighted stop-to-stop beeline distances (km) per activity."""

    def __init__(self, survey_df: pd.DataFrame, config: Dict):
        pa = config.get('poi_assignment', {})
        circuity = float(pa.get('survey_circuity', 1.25))
        max_km = float(pa.get('stop_distance_max_km', 50.0))

        df = survey_df
        need = {B.ORIGIN_PURPOSE, B.DESTINATION_PURPOSE, B.DISTANCE}
        if df is None or not need.issubset(df.columns):
            raise ValueError(f"StopDistanceModel needs survey columns {sorted(need)}")
        km = pd.to_numeric(df[B.DISTANCE], errors='coerce') * 1.609344 / circuity
        if B.TRIP_WEIGHT in df.columns:
            w = pd.to_numeric(df[B.TRIP_WEIGHT], errors='coerce').fillna(1.0)
        else:
            w = pd.Series(1.0, index=df.index)
        keep = ((df[B.ORIGIN_PURPOSE] != B.ACT_HOME) & (df[B.DESTINATION_PURPOSE] != B.ACT_HOME)
                & km.notna() & (km > 0) & (km <= max_km) & (w > 0))
        sub = pd.DataFrame({'act': df.loc[keep, B.DESTINATION_PURPOSE],
                            'km': km[keep], 'w': w[keep]})

        self._pools: Dict[str, tuple] = {}
        for act, g in sub.groupby('act'):
            if len(g) >= MIN_SAMPLES:
                self._pools[act] = (g['km'].to_numpy(), (g['w'] / g['w'].sum()).to_numpy())
        if len(sub) < MIN_SAMPLES:
            raise ValueError(f"Only {len(sub)} stop-to-stop survey trips; cannot build the model")
        self._all = (sub['km'].to_numpy(), (sub['w'] / sub['w'].sum()).to_numpy())

    def sample_km(self, activity: str, rng: Optional[np.random.Generator] = None) -> float:
        km, p = self._pools.get(activity, self._all)
        if rng is None:
            return float(km[np.random.choice(len(km), p=p)])
        return float(km[rng.choice(len(km), p=p)])

    def median_km(self, activity: str) -> float:
        km, p = self._pools.get(activity, self._all)
        order = np.argsort(km)
        return float(km[order][np.searchsorted(np.cumsum(p[order]), 0.5)])


def build_stop_distance_model(survey_df, config) -> Optional[StopDistanceModel]:
    """The model when poi_assignment.stop_distance_source == 'survey', else None."""
    source = config.get('poi_assignment', {}).get('stop_distance_source', 'nearest')
    if source == 'nearest':
        return None
    if source != 'survey':
        raise ValueError(f"poi_assignment.stop_distance_source must be 'nearest' or "
                         f"'survey', got {source!r}")
    return StopDistanceModel(survey_df, config)


def place_stop(index, lat: float, lon: float, activity: str,
               model: StopDistanceModel) -> Optional[Dict]:
    """A POI of `activity` at a survey-drawn distance from (lat, lon), or None.

    The ring around the target distance widens from +-25% to +-50% to
    [0, 2x target]. Inside the ring a POI is taken at random (uniform), so
    dense areas do not pull every stop to the same POI. None means no POI of
    this type within twice the target distance; the caller then uses its old
    nearest-POI search.
    """
    target_m = model.sample_km(activity) * 1000.0
    for tol in (0.25, 0.5, 1.0):
        hits = index.find_in_ring(lat, lon, activity,
                                  target_m * (1 - tol), target_m * (1 + tol))
        if hits:
            return hits[np.random.randint(len(hits))]
    return None

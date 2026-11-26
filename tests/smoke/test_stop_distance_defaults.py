# SPDX-License-Identifier: GPL-3.0-or-later
"""Survey stop distances and non-work beta "auto" are the defaults (todo item 2).

Secondary stops used to go to the nearest POI, and non-work legs had about
half the survey length. Now a stop goes to a POI at a survey stop -> stop
distance, and the non-work gravity beta is fitted to the survey's Home -> P
distances, unless the config says otherwise.
"""

import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data_sources.base_survey_trip import BaseSurveyTrip as B
from models import od_matrix_nonwork
from models.od_matrix_nonwork import calibrate_beta_to_survey
from models.stop_distance import StopDistanceModel, build_stop_distance_model

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.smoke


def _survey(n=200, seed=0):
    """Stop -> stop Dining trips (2 miles each) and Home -> Shopping trips."""
    rng = np.random.default_rng(seed)
    stop = pd.DataFrame({
        B.ORIGIN_PURPOSE: B.ACT_SHOPPING, B.DESTINATION_PURPOSE: B.ACT_DINING,
        B.DISTANCE: 2.0, B.TRIP_WEIGHT: 1.0}, index=range(n))
    home = pd.DataFrame({
        B.ORIGIN_PURPOSE: B.ACT_HOME, B.DESTINATION_PURPOSE: B.ACT_SHOPPING,
        B.DISTANCE: rng.lognormal(np.log(3.0), 0.6, n), B.TRIP_WEIGHT: 1.0},
        index=range(n, 2 * n))
    return pd.concat([stop, home])


def test_survey_is_the_default():
    model = build_stop_distance_model(_survey(), {})
    assert isinstance(model, StopDistanceModel)
    # 2 miles reported / circuity 1.25 = 2.575 km beeline
    assert model.median_km(B.ACT_DINING) == pytest.approx(2.0 * 1.609344 / 1.25)


def test_nearest_restores_old_search():
    assert build_stop_distance_model(
        _survey(), {'poi_assignment': {'stop_distance_source': 'nearest'}}) is None


def test_default_falls_back_when_survey_cannot_build_model():
    bad = pd.DataFrame({B.ORIGIN_PURPOSE: ['Home'], B.DESTINATION_PURPOSE: ['Shopping']})
    assert build_stop_distance_model(bad, {}) is None
    assert build_stop_distance_model(None, {}) is None


def test_explicit_survey_still_raises():
    bad = pd.DataFrame({B.ORIGIN_PURPOSE: ['Home'], B.DESTINATION_PURPOSE: ['Shopping']})
    with pytest.raises(ValueError):
        build_stop_distance_model(bad, {'poi_assignment': {'stop_distance_source': 'survey'}})


def test_unknown_source_raises():
    with pytest.raises(ValueError):
        build_stop_distance_model(_survey(), {'poi_assignment': {'stop_distance_source': 'x'}})


def test_nonwork_beta_default_is_auto():
    src = inspect.getsource(od_matrix_nonwork.create_nonwork_od_matrix)
    assert "get('beta', 'auto')" in src


def _gravity_inputs():
    dist = np.tile(np.linspace(0.5, 40.0, 80), (5, 1))
    return dist, np.ones(5), np.ones(80)


def test_beta_auto_fits_survey_and_falls_back():
    dist, Oi, Aj = _gravity_inputs()
    beta = calibrate_beta_to_survey(dist, Oi, Aj, _survey(), B.ACT_SHOPPING, {})
    assert 0.05 < beta < 5.0
    # Longer survey trips give a smaller beta.
    longer = _survey()
    longer.loc[longer[B.ORIGIN_PURPOSE] == B.ACT_HOME, B.DISTANCE] *= 3
    assert calibrate_beta_to_survey(dist, Oi, Aj, longer, B.ACT_SHOPPING, {}) < beta
    # Too few Home -> P trips: fallback beta.
    assert calibrate_beta_to_survey(dist, Oi, Aj, _survey(), 'Social', {}) == 2.0


@pytest.mark.parametrize('cfg', ['config/config_local.json',
                                 'config/USA/Birmingham_AL/config.json',
                                 'config/USA/TwinCities/config_twincities.json'])
def test_repo_configs_use_auto(cfg):
    c = json.loads((REPO / cfg).read_text())
    for name, p in c['nonwork_purposes'].items():
        if isinstance(p, dict) and 'od_matrix' in p:
            assert p['od_matrix'].get('beta', 'auto') == 'auto', (cfg, name)
    assert c.get('poi_assignment', {}).get('stop_distance_source', 'survey') == 'survey'

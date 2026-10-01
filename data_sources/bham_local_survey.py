import re
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from utils.logger import setup_logger
from data_sources.base_survey_trip import BaseSurveyTrip
from models.mode_types import (
    MODE_CAR, MODE_BUS, MODE_WALK, MODE_BIKE, MODE_RIDESHARE
)

logger = setup_logger(__name__)


class BirminghamLocalSurveyTrip(BaseSurveyTrip):
    """Birmingham, AL local travel survey (one CSV, one row per person).

    File: data/surveys/birmingham_al_local/birmingham_al_local_survey.csv.
    See data/surveys/birmingham_al_local/README.md for what the file holds.

    Layout ("wide"): a row is one person-day. ``x0, y0`` and ``Loc_Type`` are
    where the day starts; trip slot k (1st .. 13th) holds the destination
    ``xk, yk``, ``<k>_Trip_Start_Time``, ``<k>_Trip_End_Time``,
    ``<k>_activity`` (destination purpose) and ``<k>_Mode``. ``x14, y14`` is
    the home location. Coordinates are UTM zone 16N metres.

    What this survey CANNOT do (see survey_manager.ROLES):
      * person_days -- every respondent reported at least one trip (no
        no-travel days) and nobody is under 18 (no student segment), so
        load_person_days() returns None. Pair it with a survey that has a
        person file, e.g. NHTS with ``"roles": {"person_days": 1}``.
      * od -- origin_loc / destination_loc are left empty: 1,129 trips are
        too few for a block-group OD matrix.
    There are no weights (trip_weight = 1), no household ids and no travel
    date. All days are treated as weekdays (stated by the data owner) and
    put on one reference Wednesday, so the weekday filter keeps them all.

    Cleaning drops whole persons, not single trips, so every kept day is an
    unbroken chain. A person is dropped when a trip time cannot be read or
    goes backwards (other than a crossing of midnight), a mode is not a mode,
    a trip end has no coordinates, or a trip end lies outside the region
    counties (config region.counties).
    """

    # Reference date for the synthetic datetimes: a Wednesday in October
    # (a "regular" month, see SurveyManager.REGULAR_MONTHS).
    REFERENCE_DATE = pd.Timestamp('2024-10-16')
    UTM_CRS = 'EPSG:32616'
    METERS_PER_MILE = 1609.344
    MAX_SLOTS = 13
    SLOT_PREFIX = ['1st', '2nd', '3rd'] + [f'{i}th' for i in range(4, 14)]

    # A later time this much earlier than the previous one, with the previous
    # time in the evening and the later one before dawn, is read as a
    # crossing of midnight. Any other backwards step is an error.
    MIDNIGHT_EVENING_FROM_H = 18
    MIDNIGHT_MORNING_TO_H = 6
    # Small overlaps (a start a few minutes before the previous arrival) are
    # rounding in the answers; they are clamped, not rejected.
    OVERLAP_TOLERANCE_S = 15 * 60

    # ── Raw purpose label -> canonical activity ─────────────────────────
    # Judgment calls (no exact category in Tareek):
    #   Nightlife/ Bar      -> Social   (the only leisure label in the survey)
    #   Services (bank...)  -> Other    (NHTS puts errands in Shopping; the
    #                                    survey separates them, so keep apart)
    #   Pick-up / Drop-off  -> Shopping (as TBI Escort and NHTS "Transport
    #                                    someone" in this code base)
    PURPOSE_MAP = {
        'Home': BaseSurveyTrip.ACT_HOME,
        'Work': BaseSurveyTrip.ACT_WORK,
        'School': BaseSurveyTrip.ACT_SCHOOL,
        'Shopping- Grocery': BaseSurveyTrip.ACT_SHOPPING,
        'Shopping- Retail': BaseSurveyTrip.ACT_SHOPPING,
        'Eat/ Get take-out': BaseSurveyTrip.ACT_DINING,
        'Nightlife/ Bar': BaseSurveyTrip.ACT_SOCIAL,
        'Services (e.g. Bank, post office)': BaseSurveyTrip.ACT_OTHER,
        'Pick-up passenger': BaseSurveyTrip.ACT_SHOPPING,
        'Drop-off passenger': BaseSurveyTrip.ACT_SHOPPING,
    }

    # ── Raw mode label -> canonical mode (keys lower-case) ──────────────
    # Judgment calls:
    #   Carpool/Vanpool -> Car       (driver or passenger is not asked)
    #   Car rental      -> Car
    #   Taxi            -> Rideshare (as NHTS taxi/limo in this code base)
    #   Transit         -> Bus       (Birmingham has no rail transit)
    MODE_MAP = {
        'car': MODE_CAR,
        'car rental': MODE_CAR,
        'carpool/vanpool': MODE_CAR,
        'uber/lyft': MODE_RIDESHARE,
        'taxi': MODE_RIDESHARE,
        'transit': MODE_BUS,
        'walk': MODE_WALK,
        'bike': MODE_BIKE,
    }

    _TIME_RE = re.compile(r'^(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?\s*(AM|PM)?$', re.I)

    def __init__(self, config: Dict):
        super().__init__(config)
        self.metadata = {
            'source_type': 'bham_local',
        }
        self.drop_counts: Dict[str, int] = {}

    def load_person_days(self) -> Optional[pd.DataFrame]:
        """None: the survey has no no-travel days and no persons under 18.

        A person-day table built from it would say that every person travels
        every day and would have no student segment, so it cannot do the
        person_days job.
        """
        logger.info("bham_local: no person-days (no zero-trip days, no persons under 18); "
                    "person-days must come from another survey")
        return None

    # ── Parsing helpers ─────────────────────────────────────────────────

    @classmethod
    def parse_time(cls, value: str) -> Optional[int]:
        """Seconds after midnight, or None when the cell cannot be read.

        Accepts 'H:MM:SS', 'H:M:SS' ('12:9:00'), an Excel day fraction
        ('0.629166667' = 15:06), and an AM/PM suffix. '16:00:00 AM' (a
        24-hour time with a stray AM) is read as 16:00.
        """
        s = str(value).strip()
        if not s:
            return None
        try:
            f = float(s)
            if 0 <= f < 1:
                return int(round(f * 86400))
            return None
        except ValueError:
            pass
        m = cls._TIME_RE.match(s)
        if not m:
            return None
        h, mi, se = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        ampm = (m.group(4) or '').upper()
        if ampm == 'PM' and h < 12:
            h += 12
        elif ampm == 'AM' and h == 12:
            h = 0
        if mi > 59 or se > 59 or h > 24:
            return None
        return h * 3600 + mi * 60 + se

    @classmethod
    def _unwrap_times(cls, times: List[int]) -> Optional[List[int]]:
        """Make a day's times non-decreasing; add 24 h at a midnight crossing.

        Returns None when a time steps backwards in any other way.
        """
        out, offset, last = [], 0, None
        for t in times:
            v = t + offset
            if last is not None and v < last:
                if (last % 86400 >= cls.MIDNIGHT_EVENING_FROM_H * 3600
                        and t < cls.MIDNIGHT_MORNING_TO_H * 3600 and offset == 0):
                    offset = 86400
                    v = t + offset
                elif last - v <= cls.OVERLAP_TOLERANCE_S:
                    v = last
                else:
                    return None
            out.append(v)
            last = v
        return out

    def _region_shape(self):
        """Union of the region counties in UTM 16N, or None when unavailable."""
        try:
            import geopandas as gpd
            shp = Path(self.config['data']['data_dir']) / 'counties' / 'cb_2022_us_county_500k.shp'
            counties = {str(c)[:5] for c in self.config['region']['counties']}
            gdf = gpd.read_file(shp)
            gdf = gdf[gdf['GEOID'].isin(counties)].to_crs(self.UTM_CRS)
            if gdf.empty:
                return None
            return gdf.geometry.union_all() if hasattr(gdf.geometry, 'union_all') \
                else gdf.geometry.unary_union
        except Exception as e:
            logger.warning(f"bham_local: region counties not available ({e}); no region filter")
            return None

    # ── ETL ─────────────────────────────────────────────────────────────

    def extract_data(self, year: str, file_path: Optional[str] = None) -> pd.DataFrame:
        """Read the wide CSV and turn it into one row per trip (long format)."""
        # _survey_entry() looks the entry up by year, so set it first.
        self.metadata['source_year'] = year
        if file_path is None:
            file_path = self._resolve_data_path(self._survey_entry().get('file'))
        elif not Path(file_path).is_absolute():
            file_path = str(Path(self.config['data']['data_dir']) / file_path)
        if not file_path or not Path(file_path).exists():
            raise FileNotFoundError(f"bham_local survey file not found: {file_path}")
        self.metadata['source_year'] = year
        logger.info(f"Reading Birmingham local survey from {file_path}")

        raw = pd.read_csv(file_path, dtype=str, keep_default_na=False, encoding='utf-8-sig')
        rows = []
        for _, r in raw.iterrows():
            pid = f"bham_{str(r['id']).strip()}"
            prev = (r.get('x0', ''), r.get('y0', ''), str(r.get('Loc_Type', '')).strip())
            for k, pre in enumerate(self.SLOT_PREFIX, start=1):
                start = r.get(f'{pre}_Trip_Start_Time', '')
                act = str(r.get(f'{pre}_activity', '')).strip()
                mode = str(r.get(f'{pre}_Mode', '')).strip()
                if not (str(start).strip() or act or mode):
                    continue
                dest = (r.get(f'x{k}', ''), r.get(f'y{k}', ''), act)
                rows.append({
                    'person_id': pid, 'slot': k,
                    'start_raw': start, 'end_raw': r.get(f'{pre}_Trip_End_Time', ''),
                    'o_x': prev[0], 'o_y': prev[1], 'o_purpose_raw': prev[2],
                    'd_x': dest[0], 'd_y': dest[1], 'd_purpose_raw': act,
                    'mode_raw': mode,
                    'home_x': r.get('x14', ''), 'home_y': r.get('y14', ''),
                })
                prev = dest
        df = pd.DataFrame(rows)
        logger.info(f"bham_local: {len(raw):,} persons, {len(df):,} trips read")
        self.data = df
        return df

    def _drop_persons(self, df: pd.DataFrame, bad: pd.Series, reason: str) -> pd.DataFrame:
        bad_ids = set(df.loc[bad, 'person_id'])
        self.drop_counts[reason] = len(bad_ids)
        if bad_ids:
            logger.info(f"bham_local: dropped {len(bad_ids)} persons ({reason})")
        return df[~df['person_id'].isin(bad_ids)]

    def clean_data(self, **kwargs) -> None:
        """Parse times and coordinates, map labels, drop unusable persons."""
        if self.data is None:
            raise ValueError("No data loaded. Call extract_data first.")
        df = self.data.copy()
        n_persons0, n_trips0 = df['person_id'].nunique(), len(df)

        # ── Coordinates ────────────────────────────────────────────────
        for c in ('o_x', 'o_y', 'd_x', 'd_y', 'home_x', 'home_y'):
            df[c] = pd.to_numeric(df[c].astype(str).str.strip(), errors='coerce')
        df = self._drop_persons(df, df[['o_x', 'o_y', 'd_x', 'd_y']].isna().any(axis=1),
                                'a trip end has no coordinates')

        # ── Times ──────────────────────────────────────────────────────
        df['start_s'] = df['start_raw'].map(self.parse_time)
        df['end_s'] = df['end_raw'].map(self.parse_time)
        df = self._drop_persons(df, df['start_s'].isna() | df['end_s'].isna(),
                                'a trip time cannot be read')
        df = df.sort_values(['person_id', 'slot'])
        bad_ids = []
        for pid, g in df.groupby('person_id', sort=False):
            seq = []
            for s, e in zip(g['start_s'], g['end_s']):
                seq += [int(s), int(e)]
            un = self._unwrap_times(seq)
            if un is None:
                bad_ids.append(pid)
                continue
            df.loc[g.index, 'start_s'] = un[0::2]
            df.loc[g.index, 'end_s'] = un[1::2]
        df = self._drop_persons(df, df['person_id'].isin(bad_ids),
                                'trip times go backwards (not a midnight crossing)')

        # ── Modes and purposes ─────────────────────────────────────────
        df['mode_key'] = df['mode_raw'].str.strip().str.lower()
        df = self._drop_persons(df, ~df['mode_key'].isin(self.MODE_MAP),
                                'a mode cell is not a mode')
        # The day-start type is wrong for some persons who start at their
        # home coordinates (e.g. "Nightlife/ Bar" at 05:00, then "Home" at
        # the same point): the start is set to Home when the first origin is
        # within 1 m of the home location x14/y14.
        first = ~df['person_id'].duplicated()
        at_home = (np.hypot(df['o_x'] - df['home_x'], df['o_y'] - df['home_y']) < 1.0)
        fix = first & at_home & (df['o_purpose_raw'] != 'Home')
        self.drop_counts['day start set to Home (start at home coordinates)'] = int(fix.sum())
        df.loc[fix, 'o_purpose_raw'] = 'Home'
        for raw_col in ('o_purpose_raw', 'd_purpose_raw'):
            unknown = set(df[raw_col]) - set(self.PURPOSE_MAP)
            if unknown:
                logger.warning(f"bham_local: unmapped purposes {unknown} -> '{self.ACT_OTHER}'")

        # ── Region filter (whole persons) ──────────────────────────────
        region = self._region_shape()
        if region is not None:
            from shapely import contains_xy
            inside = (contains_xy(region, df['o_x'].to_numpy(), df['o_y'].to_numpy())
                      & contains_xy(region, df['d_x'].to_numpy(), df['d_y'].to_numpy()))
            df = self._drop_persons(df, pd.Series(~inside, index=df.index),
                                    'a trip end is outside the region counties')

        # ── Canonical columns ──────────────────────────────────────────
        base = self.REFERENCE_DATE
        out = pd.DataFrame({
            self.PERSON_ID: df['person_id'],
            self.MODE_TYPE: df['mode_key'].map(self.MODE_MAP),
            self.ORIGIN_LOC: None,
            self.DESTINATION_LOC: None,
            self.ORIGIN_PURPOSE: df['o_purpose_raw'].map(self.PURPOSE_MAP).fillna(self.ACT_OTHER),
            self.DESTINATION_PURPOSE: df['d_purpose_raw'].map(self.PURPOSE_MAP).fillna(self.ACT_OTHER),
            self.DEPART_TIME: base + pd.to_timedelta(df['start_s'].astype(int), unit='s'),
            self.ARRIVE_TIME: base + pd.to_timedelta(df['end_s'].astype(int), unit='s'),
            self.DURATION: (df['end_s'] - df['start_s']).astype(float),
            # Straight-line distance; the survey has no network distance.
            self.DISTANCE: np.hypot(df['d_x'] - df['o_x'], df['d_y'] - df['o_y']) / self.METERS_PER_MILE,
            self.TRIP_WEIGHT: 1.0,
        })
        out[self.SOURCE_TYPE] = self.metadata['source_type']
        out[self.SOURCE_YEAR] = self.metadata.get('source_year', '')

        self.data = out.reset_index(drop=True)
        logger.info(f"bham_local: kept {out[self.PERSON_ID].nunique():,}/{n_persons0:,} persons, "
                    f"{len(out):,}/{n_trips0:,} trips; {self.drop_counts}")
        self.validate_schema()
        self.detect_geo_level()

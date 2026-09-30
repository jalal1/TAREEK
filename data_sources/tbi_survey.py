import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from pathlib import Path
from utils.logger import setup_logger
from data_sources.base_survey_trip import BaseSurveyTrip
from models.mode_types import (
    MODE_CAR, MODE_BUS, MODE_RAIL, MODE_WALK, MODE_BIKE,
    MODE_SCHOOL_BUS, MODE_RIDESHARE, MODE_OTHER
)

logger = setup_logger(__name__)


class TBISurveyTrip(BaseSurveyTrip):
    """TBI (Travel Behavior Inventory) survey trip data source.

    Reads TBI CSV files, cleans with TBI-specific rules, and maps
    raw column names to the canonical schema defined in BaseSurveyTrip.

    Two trip tables exist. The Trip file holds unlinked legs: a transfer
    (walk -> bus -> walk) is split into legs whose middle purpose is
    "Change mode". Cleaning must drop those legs, which leaves a hole in the
    day. The LinkedTrip file joins the legs into one trip per activity. Set
    ``linked_trip_file`` on the survey entry to use it; ``file`` (the Trip
    file) is still read for the 2020 block groups, which the LinkedTrip file
    does not carry.
    """

    # ── Raw CSV columns needed from the TBI file ───────────────────────
    RAW_COLUMNS = [
        'person_id', 'day_id', 'linked_trip_id', 'mode_type',
        'o_bg_2020', 'd_bg_2020',
        'o_purpose_category', 'd_purpose_category',
        'o_purpose_category_broad', 'd_purpose_category_broad',
        'depart_time', 'arrive_time',
        'duration_seconds', 'distance_miles',
        'trip_o_county', 'trip_d_county',
        'trip_weight',
    ]

    # ── Raw columns from the LinkedTrip file (no block groups; those come
    #    from its legs in the Trip file) ──
    LINKED_RAW_COLUMNS = [
        'linked_trip_id', 'person_id', 'day_id', 'mode_type',
        'o_purpose_category', 'd_purpose_category',
        'o_purpose_category_broad', 'd_purpose_category_broad',
        'depart_time', 'arrive_time',
        'duration_seconds', 'distance_miles',
        'trip_o_county', 'trip_d_county',
        'linked_trip_weight',
    ]

    # ── Where the day began (Day file ``begin_day``) -> origin purpose ──
    # TBI leaves the origin of the first trip of a day "Missing" on about a
    # third of the weighted days (2,812 of 2,815 Missing origins are first
    # trips). The Day file says where the person began the day: on 94% of
    # those days it is Home. Other places (a friend's home, a hotel) have no
    # canonical activity, so those trips stay Missing and are dropped.
    BEGIN_DAY_TO_PURPOSE = {
        'Home': ('Home', 'Went home'),     # (o_purpose_category, ..._broad)
        'Work': ('Work', 'Work'),
    }

    # ── Mapping from raw TBI column names to canonical names ───────────
    COLUMN_MAP = {
        'o_bg_2020': BaseSurveyTrip.ORIGIN_LOC,
        'd_bg_2020': BaseSurveyTrip.DESTINATION_LOC,
        'o_purpose_category_broad': BaseSurveyTrip.ORIGIN_PURPOSE,
        'd_purpose_category_broad': BaseSurveyTrip.DESTINATION_PURPOSE,
    }

    # ── TBI-only columns used during cleaning then dropped ─────────────
    _CLEANING_ONLY_COLUMNS = [
        'day_id', 'linked_trip_id',
        'o_purpose_category', 'd_purpose_category',
        'trip_o_county', 'trip_d_county',
    ]

    # ── Mapping from raw TBI purpose labels to canonical activity types ──
    # Multiple raw labels can map to the same canonical type.
    PURPOSE_MAP = {
        'Went home': BaseSurveyTrip.ACT_HOME,
        'Work': BaseSurveyTrip.ACT_WORK,
        'School': BaseSurveyTrip.ACT_SCHOOL,
        'Shopping/Errands': BaseSurveyTrip.ACT_SHOPPING,
        'Escort': BaseSurveyTrip.ACT_SHOPPING,
        'Social/Recreation': BaseSurveyTrip.ACT_SOCIAL,
        'Dining': BaseSurveyTrip.ACT_DINING,
        'Other': BaseSurveyTrip.ACT_OTHER,
    }

    # ── Mapping from raw TBI mode labels to canonical transport modes ────
    MODE_MAP = {
        'Household Vehicle': MODE_CAR,
        'Other Vehicle': MODE_CAR,
        'Walk': MODE_WALK,
        'Public Bus': MODE_BUS,
        'Other Bus': MODE_BUS,
        'Rail': MODE_RAIL,
        'Micromobility': MODE_BIKE,
        'School Bus': MODE_SCHOOL_BUS,
        'Smartphone ridehailing service': MODE_RIDESHARE,
        'Other': MODE_OTHER,
        'For-Hire Vehicle': MODE_OTHER,
    }

    # ── Person-day files (Day + Person tables) ──────────────────────────
    DAY_RAW_COLUMNS = ['person_id', 'travel_date', 'travel_dow', 'num_trips', 'day_weight']
    PERSON_RAW_COLUMNS = ['person_id', 'age', 'employment']
    WORKER_LABELS = {'Employed full-time', 'Employed part-time', 'Self-employed'}
    CHILD_AGE_LABELS = {'Under 5'}
    STUDENT_AGE_LABELS = {'5 to 15', '16 to 17'}
    DOW_TO_WEEKDAY = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3,
                      'Friday': 4, 'Saturday': 5, 'Sunday': 6}

    def __init__(self, config: Dict):
        super().__init__(config)
        self.metadata = {
            'source_type': 'tbi',
        }

    def load_person_days(self) -> Optional[pd.DataFrame]:
        """Person-days from the TBI Day and Person files.

        Config keys on the survey entry: ``day_file`` (…2023Day.csv) and
        ``person_file`` (…2023Person.csv). TBI observes several days per
        person, so each row carries its calendar ``date``. Days with a zero
        ``day_weight`` are not part of the weighted sample and are dropped.
        """
        entry = self._survey_entry()
        day_path = self._resolve_data_path(entry.get('day_file'))
        person_path = self._resolve_data_path(entry.get('person_file'))
        if day_path is None or person_path is None:
            logger.warning("TBI: 'day_file' and 'person_file' are both needed in the "
                           "survey config entry — no person-days")
            return None
        for path in (day_path, person_path):
            if not Path(path).exists():
                raise FileNotFoundError(f"TBI person-day file not found: {path}")

        day = pd.read_csv(day_path, usecols=self.DAY_RAW_COLUMNS,
                          dtype={'person_id': str}, encoding='iso-8859-1')
        per = pd.read_csv(person_path, usecols=self.PERSON_RAW_COLUMNS,
                          dtype={'person_id': str}, encoding='iso-8859-1')
        d = day.merge(per, on='person_id', how='left')

        segment = np.select(
            [d['employment'].isin(self.WORKER_LABELS),
             d['age'].isin(self.CHILD_AGE_LABELS),
             d['age'].isin(self.STUDENT_AGE_LABELS),
             d['age'].notna() & ~d['age'].isin(['Missing'])],
            [self.SEG_WORKER, self.SEG_CHILD, self.SEG_STUDENT, self.SEG_NONWORKER_ADULT],
            default='unknown')
        date = pd.to_datetime(d['travel_date'], errors='coerce')
        out = pd.DataFrame({
            self.PD_PERSON_ID: d['person_id'],
            self.PD_DATE: date.dt.strftime('%Y-%m-%d'),
            self.PD_WEIGHT: pd.to_numeric(d['day_weight'], errors='coerce').fillna(0.0),
            self.PD_SEGMENT: segment,
            self.PD_MONTH: date.dt.month,
            self.PD_WEEKDAY: d['travel_dow'].map(self.DOW_TO_WEEKDAY),
            self.PD_N_TRIPS: pd.to_numeric(d['num_trips'], errors='coerce').fillna(0).clip(lower=0),
        })
        out = out[(out[self.PD_WEIGHT] > 0) & (out[self.PD_SEGMENT] != 'unknown')
                  & out[self.PD_DATE].notna()]
        logger.info(f"TBI person-days: {len(out):,} from {day_path}")
        return out.reset_index(drop=True)

    # ── Reported commute frequency (Person file) ─────────────────────────
    # commute_freq is asked of workers with a work place outside the home;
    # a worker who works only from home commutes 0 days, and one whose job
    # is travel (driver, sales) reports work_freq instead. Days per week;
    # a week has at most 5 weekdays, so 6-7 counts as 5.
    COMMUTE_FREQ_DAYS = {
        '6-7 days a week': 5.0, '5 days a week': 5.0, '9 days every 2 weeks': 4.5,
        '4 days a week': 4.0, '3 days a week': 3.0, '2 days a week': 2.0,
        '1 day a week': 1.0, '1-3 days a month': 2.0 / 4.33,
        'Less than monthly': 0.5 / 4.33, 'Never': 0.0,
    }
    JOB_TYPE_COMMUTES = {
        'Go to one work location ONLY (outside of home)',
        'Telework some days and travel to a work location some days',
        'Work location regularly varies (different offices/jobsites)',
    }
    JOB_TYPE_HOME_ONLY = 'Work ONLY from home or remotely (telework, self-employed)'
    JOB_TYPE_TRAVEL = 'Drive/bike/travel for work (driver, sales, deliveries)'

    def reported_commute_rate(self) -> Optional[Dict[str, float]]:
        """Share of weekdays a worker says they travel to work (Person file).

        This is an independent check of the diary P(commute): the diary
        counts the days with a trip to Work. The two differ for known
        reasons: the reported value is a typical week (no leave, no sick
        days), and the diary's Work also holds work-related business trips.
        Weighted by person_weight. Returns None without a person file.
        """
        person_path = self._resolve_data_path(self._survey_entry().get('person_file'))
        if person_path is None or not Path(person_path).exists():
            return None
        p = pd.read_csv(person_path, encoding='iso-8859-1',
                        usecols=['person_id', 'employment', 'job_type', 'commute_freq',
                                 'work_freq', 'person_weight'])
        p = p[p['employment'].isin(self.WORKER_LABELS)
              & (pd.to_numeric(p['person_weight'], errors='coerce') > 0)]
        days = np.select(
            [p['job_type'].isin(self.JOB_TYPE_COMMUTES),
             p['job_type'].eq(self.JOB_TYPE_HOME_ONLY),
             p['job_type'].eq(self.JOB_TYPE_TRAVEL)],
            [p['commute_freq'].map(self.COMMUTE_FREQ_DAYS),
             0.0,
             p['work_freq'].map(self.COMMUTE_FREQ_DAYS)],
            default=np.nan)
        known = ~np.isnan(days)
        w = pd.to_numeric(p['person_weight'], errors='coerce').to_numpy()[known]
        if w.sum() <= 0:
            return None
        rate = float((w * days[known] / 5.0).sum() / w.sum())
        logger.info(f"TBI reported commute: {rate:.1%} of weekdays "
                    f"({int(known.sum()):,} of {len(p):,} workers answered)")
        return {'rate': rate, 'workers': int(known.sum())}

    def _get_allowed_county_fips(self) -> set:
        """5-digit state+county GEOIDs from config region.counties.

        The state is part of the key: the Twin Cities region holds Wisconsin
        counties 55093 and 55109, and matching on the 3-digit county code
        alone also let in Minnesota's 27093 (Meeker) and 27109 (Olmsted).
        """
        return {str(geoid)[:5] for geoid in self.config['region']['counties']}

    def _read_linked_trips(self, linked_path: str, trip_path: str) -> pd.DataFrame:
        """LinkedTrip rows with the Trip file's block groups.

        A linked trip starts where its first leg starts and ends where its
        last leg ends, so o_bg_2020 comes from the first leg and d_bg_2020
        from the last.
        """
        legs = pd.read_csv(trip_path, encoding='iso-8859-1', low_memory=False,
                           usecols=['linked_trip_id', 'leg_num', 'o_bg_2020', 'd_bg_2020'],
                           dtype={'linked_trip_id': str, 'o_bg_2020': str, 'd_bg_2020': str})
        legs = legs.sort_values(['linked_trip_id', 'leg_num'])
        # drop_duplicates, not groupby().first(): first() would skip a leg
        # with no block group and take the next leg's origin instead.
        first_leg = legs.drop_duplicates('linked_trip_id', keep='first').set_index('linked_trip_id')
        last_leg = legs.drop_duplicates('linked_trip_id', keep='last').set_index('linked_trip_id')
        per_link = pd.DataFrame({
            'o_bg_2020': first_leg['o_bg_2020'],
            'd_bg_2020': last_leg['d_bg_2020'],
        })
        linked = pd.read_csv(linked_path, encoding='iso-8859-1', low_memory=False,
                             usecols=self.LINKED_RAW_COLUMNS,
                             dtype={'linked_trip_id': str, 'person_id': str, 'day_id': str})
        linked = linked.rename(columns={'linked_trip_weight': 'trip_weight'})
        n_orphan = int((~linked['linked_trip_id'].isin(per_link.index)).sum())
        if n_orphan:
            logger.warning(f"TBI: {n_orphan:,} linked trips have no leg in the Trip file")
        df = linked.merge(per_link, left_on='linked_trip_id', right_index=True, how='left')
        logger.info(f"TBI: {len(df):,} linked trips from {len(legs):,} legs")
        return df

    def _fill_missing_origins(self, df: pd.DataFrame) -> pd.DataFrame:
        """Give a "Missing" origin purpose the place the person was before.

        The first trip of a day gets the Day file's ``begin_day`` (see
        BEGIN_DAY_TO_PURPOSE); a later trip gets the previous trip's
        destination. Must run before any trip is removed, so that the
        previous trip is really the previous one.
        """
        miss = df['o_purpose_category'].eq('Missing') | df['o_purpose_category_broad'].eq('Missing')
        if not miss.any():
            return df
        df = df.sort_values(['day_id', 'depart_time']).copy()
        miss = miss.reindex(df.index)
        first = ~df['day_id'].duplicated()

        begin = pd.Series(np.nan, index=df.index, dtype=object)
        day_path = self._resolve_data_path(self._survey_entry().get('day_file'))
        if day_path and Path(day_path).exists():
            day = pd.read_csv(day_path, usecols=['day_id', 'begin_day'],
                              dtype={'day_id': str}, encoding='iso-8859-1')
            begin = df['day_id'].astype(str).map(day.set_index('day_id')['begin_day'])

        prev_n = df.groupby('day_id')['d_purpose_category'].shift(1)
        prev_b = df.groupby('day_id')['d_purpose_category_broad'].shift(1)
        n_first = n_later = 0
        for label, (narrow, broad) in self.BEGIN_DAY_TO_PURPOSE.items():
            sel = miss & first & begin.eq(label)
            df.loc[sel, 'o_purpose_category'] = narrow
            df.loc[sel, 'o_purpose_category_broad'] = broad
            n_first += int(sel.sum())
        later = miss & ~first & prev_n.notna()
        df.loc[later, 'o_purpose_category'] = prev_n[later]
        df.loc[later, 'o_purpose_category_broad'] = prev_b[later]
        n_later = int(later.sum())
        logger.info(f"TBI: filled {n_first + n_later:,} of {int(miss.sum()):,} Missing origin "
                    f"purposes ({n_first:,} from the Day file begin_day, "
                    f"{n_later:,} from the previous trip)")
        return df

    def extract_data(self, year: str, file_path: Optional[str] = None) -> pd.DataFrame:
        """Read TBI CSV for the given year and apply geographic filtering.

        Args:
            year: Survey year (e.g. '2023').  Stored in metadata.
            file_path: Absolute or relative path to the CSV file.
                       When called via SurveyManager, this is resolved from
                       the ``data.surveys[].file`` config entry.  When called
                       directly (e.g. from a notebook), falls back to
                       ``config['data']['surveys']`` lookup.
        """
        try:
            data_dir = self.config['data']['data_dir']
            if file_path is None:
                # Fallback: look up from config surveys list
                for entry in self.config['data'].get('surveys', []):
                    if entry.get('type') == 'tbi' and entry.get('year') == year:
                        file_path = str(Path(data_dir) / entry['file'])
                        break
                if file_path is None:
                    raise KeyError(f"No TBI survey entry for year {year} in config['data']['surveys']")
            else:
                # Resolve relative paths against data_dir
                if not Path(file_path).is_absolute():
                    file_path = str(Path(data_dir) / file_path)
            # _survey_entry() looks the entry up by year, so set it first.
            self.metadata['source_year'] = year
            linked_path = self._resolve_data_path(self._survey_entry().get('linked_trip_file'))
            if linked_path:
                logger.info(f"Reading {year} TBI linked trips from {linked_path} "
                            f"(block groups from {file_path})")
                df = self._read_linked_trips(linked_path, file_path)
            else:
                logger.info(f"Reading {year} TBI survey data from {file_path}")
                df = pd.read_csv(
                    file_path,
                    usecols=self.RAW_COLUMNS,
                    encoding='iso-8859-1',
                    low_memory=False,
                    dtype={'person_id': str, 'day_id': str, 'linked_trip_id': str,
                           'o_bg_2020': str, 'd_bg_2020': str},
                )

            # Before any trip is removed: the fill reads the previous trip.
            df = self._fill_missing_origins(df)

            # Filter trips by block groups using county FIPS from config
            try:
                allowed_fips = self._get_allowed_county_fips()
                logger.info(f"Allowed county GEOIDs: {sorted(allowed_fips)}")

                # Block group format: state_fips(2) + county_fips(3) + tract + block_group
                df['o_fips'] = df['o_bg_2020'].astype(str).str[:5]
                df['d_fips'] = df['d_bg_2020'].astype(str).str[:5]

                before_filter = len(df)
                df = df[
                    df['o_fips'].isin(allowed_fips) &
                    df['d_fips'].isin(allowed_fips)
                ].copy()
                after_filter = len(df)
                logger.info(f"Filtered by region FIPS codes: {before_filter} -> {after_filter} records")

                df.drop(columns=['o_fips', 'd_fips'], inplace=True)

            except KeyError as e:
                logger.warning(
                    f"Block group columns 'o_bg_2020' or 'd_bg_2020' not found; "
                    f"skipping FIPS filter: {e}"
                )

            # Convert time columns to datetime
            for col in ['depart_time', 'arrive_time']:
                logger.info(f"Converting {col} to datetime...")
                df[col] = pd.to_datetime(df[col], errors='coerce')

            self.data = df
            self.metadata['source_year'] = year
            logger.info(f"Successfully extracted {len(df)} records")
            return df

        except KeyError:
            logger.error(f"Year {year} not found in config")
            raise
        except Exception as e:
            logger.error(f"Error extracting data: {e}")
            raise

    def clean_data(self, timezone: str = 'America/Chicago',
                   duration_std_multiplier: float = 3.0,
                   distance_std_multiplier: float = 3.0) -> None:
        """Clean TBI data with TBI-specific filters, rename to canonical columns."""
        if self.data is None:
            raise ValueError("No data loaded. Call extract_data first.")

        try:
            df = self.data.copy()
            initial_count = len(df)
            logger.info(f"Starting TBI data cleaning. Initial records: {initial_count}")

            # ── TBI-specific basic filters ──────────────────────────────
            # No trip_survey_complete filter: TBI weights trips whose trip
            # survey is incomplete, and the purpose and mode checks below
            # already reject trips that lack them. The filter removed walk
            # access legs of transit trips most, so it cut bus + rail from
            # 2.2% to 0.8% of the linked trips on weighted days.
            df = df[
                (df['mode_type'].notna()) &
                (df['mode_type'] != 'Long distance passenger mode') &
                (df['mode_type'] != 'Missing') &
                (df['duration_seconds'].notna()) &
                (df['duration_seconds'] > 0) &
                (df['distance_miles'].notna()) &
                (df['distance_miles'] >= 0) &
                (df['depart_time'].notna()) &
                (df['arrive_time'].notna()) &
                (df['arrive_time'] >= df['depart_time']) &
                (df['o_bg_2020'].notna()) &
                (df['d_bg_2020'].notna()) &
                (df['o_bg_2020'] != 'Missing') &
                (df['d_bg_2020'] != 'Missing') &
                (df['o_purpose_category'] != 'Missing') &
                (df['d_purpose_category'] != 'Missing') &
                (df['trip_o_county'] != 'Missing') &
                (df['trip_d_county'] != 'Missing') &
                (df['trip_o_county'].notna()) &
                (df['trip_d_county'].notna()) &
                (df['o_purpose_category_broad'] != 'Missing') &
                (df['d_purpose_category_broad'] != 'Missing') &
                (df['d_purpose_category_broad'].notna()) &
                (df['o_purpose_category_broad'].notna()) &
                (~df['d_purpose_category_broad'].isin(['Change mode', 'Not imputable'])) &
                (~df['o_purpose_category_broad'].isin(['Change mode', 'Not imputable']))
            ]

            after_basic = len(df)
            logger.info(f"After basic filters: {after_basic} records ({initial_count - after_basic} removed)")

            # ── Statistical outlier filtering: duration ──────────────────
            dur_mean = df['duration_seconds'].mean()
            dur_std = df['duration_seconds'].std()
            dur_threshold = dur_mean + duration_std_multiplier * dur_std

            logger.info(f"Duration stats: mean={dur_mean/60:.2f} min, std={dur_std/60:.2f} min")
            logger.info(f"Duration threshold (mean + {duration_std_multiplier}*std): {dur_threshold/60:.2f} min")

            before = len(df)
            df = df[df['duration_seconds'] <= dur_threshold]
            logger.info(f"After duration filter: {len(df)} records ({before - len(df)} removed)")

            # ── Statistical outlier filtering: distance ──────────────────
            dist_mean = df['distance_miles'].mean()
            dist_std = df['distance_miles'].std()
            dist_threshold = dist_mean + distance_std_multiplier * dist_std

            logger.info(f"Distance stats: mean={dist_mean:.2f} mi, std={dist_std:.2f} mi")
            logger.info(f"Distance threshold (mean + {distance_std_multiplier}*std): {dist_threshold:.2f} mi")

            before = len(df)
            df = df[df['distance_miles'] <= dist_threshold]
            logger.info(f"After distance filter: {len(df)} records ({before - len(df)} removed)")

            # ── Timezone conversion ──────────────────────────────────────
            # TBI publishes times as UTC ("...Z"), so they must be converted to
            # the region's local time before any hour-of-day analysis — an
            # unconverted US Central trip appears 5-6 hours late, which turns
            # the afternoon peak into a late-evening one and puts real evening
            # travel after midnight.
            #
            # The tz offset is then dropped so the stored value is local wall
            # clock. Without this the database normalises a tz-aware timestamp
            # back to UTC on write, silently undoing the conversion above.
            for col in ['arrive_time', 'depart_time']:
                df[col] = df[col].dt.tz_convert(timezone).dt.tz_localize(None)

            # ── Clean block group IDs ────────────────────────────────────
            for col in ['o_bg_2020', 'd_bg_2020']:
                df[col] = df[col].astype(str).str.replace('.0', '', regex=False)

            # ── Drop TBI-only columns that aren't part of the canonical schema
            cols_to_drop = [c for c in self._CLEANING_ONLY_COLUMNS if c in df.columns]
            df.drop(columns=cols_to_drop, inplace=True)

            # ── Rename raw TBI columns to canonical names ────────────────
            df.rename(columns=self.COLUMN_MAP, inplace=True)

            # ── Map raw purpose labels to canonical activity types ────────
            for col in [self.ORIGIN_PURPOSE, self.DESTINATION_PURPOSE]:
                unmapped = set(df[col].unique()) - set(self.PURPOSE_MAP.keys())
                if unmapped:
                    logger.warning(f"Unmapped purpose values in {col}: {unmapped} — mapping to '{self.ACT_OTHER}'")
                df[col] = df[col].map(self.PURPOSE_MAP).fillna(self.ACT_OTHER)

            # ── Map raw mode labels to canonical transport modes ──────────
            unmapped_modes = set(df[self.MODE_TYPE].unique()) - set(self.MODE_MAP.keys())
            if unmapped_modes:
                logger.warning(f"Unmapped mode values: {unmapped_modes} — mapping to '{self.MODE_OTHER}'")
            df[self.MODE_TYPE] = df[self.MODE_TYPE].map(self.MODE_MAP).fillna(self.MODE_OTHER)

            # ── Add source metadata columns ──────────────────────────────
            df[self.SOURCE_TYPE] = self.metadata['source_type']
            df[self.SOURCE_YEAR] = self.metadata.get('source_year', '')

            final_count = len(df)
            logger.info(f"Cleaning complete. {initial_count - final_count} records removed. Final: {final_count}")

            self.data = df

            # ── Validate canonical schema ────────────────────────────────
            self.validate_schema()

            # ── Detect census geography level from origin_loc values ─────
            self.detect_geo_level()

        except Exception as e:
            logger.error(f"Error cleaning data: {e}")
            raise

from typing import Dict, List, Optional
import pandas as pd
from utils.logger import setup_logger
from data_sources.base_survey_trip import BaseSurveyTrip
from models.models import SurveyTrip, initialize_tables

logger = setup_logger(__name__)


# ── Survey roles ────────────────────────────────────────────────────────
# A survey does up to five jobs. Each entry in data.surveys has one
# ``weight`` for all of them; an optional ``roles`` dict overrides it per job:
#
#   person_days  P(travel), P(commute), purpose mix and segments (demand_budget)
#   chains       activity sequences (chain models, budget chain pools)
#   times        departure / trip time and activity duration models
#   modes        mode shares per purpose (ModeChoiceModel)
#   od           survey OD matrix and survey trip rates (needs locations)
#
# For each job the weights are normalised over the sources that can do it.
# A source "cannot" do a job when its data does not support it: no person
# file (load_person_days() returns None) or no locations (origin_loc null).
# It is then skipped for that job. Example: a local survey with no zero-trip
# days takes chains/times/modes, and NHTS takes person-days only:
#   {"type": "bham_local", "weight": 1},
#   {"type": "nhts", "weight": 0, "roles": {"person_days": 1}}
ROLE_PERSON_DAYS = 'person_days'
ROLE_CHAINS = 'chains'
ROLE_TIMES = 'times'
ROLE_MODES = 'modes'
ROLE_OD = 'od'
ROLES = (ROLE_PERSON_DAYS, ROLE_CHAINS, ROLE_TIMES, ROLE_MODES, ROLE_OD)
# Jobs that read the trip table. A source with any of these > 0 is a "trip
# source" (SurveyManager.sources); one with only person_days > 0 is loaded
# for the demand budget alone.
TRIP_ROLES = (ROLE_CHAINS, ROLE_TIMES, ROLE_MODES, ROLE_OD)
# Every run needs these; od may be empty (the gravity model is used alone).
REQUIRED_TRIP_ROLES = (ROLE_CHAINS, ROLE_TIMES, ROLE_MODES)


def role_weight(entry: Dict, role: str) -> float:
    """Weight of one survey entry for one job: roles[role], else weight."""
    roles = entry.get('roles') or {}
    return float(roles.get(role, entry.get('weight', 1.0)))


def is_active_entry(entry: Dict) -> bool:
    """True when the entry does at least one job."""
    return any(role_weight(entry, r) > 0 for r in ROLES)


def validate_survey_roles(survey_configs: List[Dict]) -> None:
    """Reject unknown role names, negative weights and runs with no source for a job.

    An empty list is not checked here (it was never rejected at this point).
    """
    if not survey_configs:
        return
    for entry in survey_configs:
        roles = entry.get('roles') or {}
        if not isinstance(roles, dict):
            raise ValueError(f"data.surveys[{entry.get('type')}].roles must be an object")
        unknown = set(roles) - set(ROLES)
        if unknown:
            raise ValueError(f"data.surveys[{entry.get('type')}].roles has unknown job(s) "
                             f"{sorted(unknown)}; valid: {list(ROLES)}")
        for r in ROLES:
            if role_weight(entry, r) < 0:
                raise ValueError(f"data.surveys[{entry.get('type')}]: weight for '{r}' is negative")
    for r in REQUIRED_TRIP_ROLES + (ROLE_PERSON_DAYS,):
        if not any(role_weight(e, r) > 0 for e in survey_configs):
            raise ValueError(f"No survey in data.surveys does the job '{r}'. Give a survey "
                             f"weight > 0, or add \"roles\": {{\"{r}\": 1}} to its entry.")


def role_weights_from_shared(shared_data: Dict, role: str) -> Dict[str, float]:
    """Per-source weights of one job from a worker's shared_data.

    Falls back to the single 'blend_weights' dict written by older callers.
    """
    rw = shared_data.get('role_weights')
    if rw and role in rw:
        return rw[role]
    return shared_data.get('blend_weights', {})


def select_for_role(per_source: Dict, weights: Dict[str, float]) -> Dict:
    """Keep only the sources whose weight for the job is > 0."""
    return {k: v for k, v in per_source.items() if weights.get(k, 0) > 0}


def ensure_surveys(config: Dict) -> None:
    """Ensure survey data exists in the database for all active survey sources.

    For each survey entry in config['data']['surveys'] that does at least one
    job (see ROLES), checks whether the survey_trips table already has rows
    for that (source_type, source_year).  If not, runs the full ETL pipeline:
    extract_data → clean_data → save_data.
    """
    survey_configs = config['data'].get('surveys', [])
    active_entries = [e for e in survey_configs if is_active_entry(e)]
    if not active_entries:
        return

    data_dir = config['data']['data_dir']
    db_manager = initialize_tables(data_dir)

    try:
        # Check which (source_type, source_year) pairs already exist
        with db_manager.session_scope() as session:
            existing_rows = session.query(
                SurveyTrip.source_type,
                SurveyTrip.source_year,
            ).distinct().all()
            existing_pairs = {(row[0], row[1]) for row in existing_rows}

        missing_entries = [
            e for e in active_entries
            if (e['type'], e.get('year', '')) not in existing_pairs
        ]

        if not missing_entries:
            logger.info(
                f"Survey data already exists for all {len(active_entries)} "
                f"active source(s)"
            )
            return

        logger.info(
            f"Survey data missing for {len(missing_entries)} source(s): "
            f"{[e['type'] + '/' + e.get('year', '?') for e in missing_entries]}. "
            f"Running ETL..."
        )
    finally:
        db_manager.close()

    # Run ETL for each missing source
    SurveyManager._ensure_registry()
    for entry in missing_entries:
        survey_type = entry['type']
        year = entry.get('year', '')
        survey_class = SurveyManager.SURVEY_REGISTRY.get(survey_type)
        if survey_class is None:
            logger.warning(f"Unknown survey type '{survey_type}', skipping ETL")
            continue

        logger.info(f"ETL for {survey_type}/{year}...")
        source = survey_class(config)
        source.metadata['source_type'] = survey_type
        source.metadata['source_year'] = year

        file_path = entry.get('file', '')
        source.extract_data(year=year, file_path=file_path if file_path else None)
        source.clean_data()
        source.save_data()
        logger.info(f"ETL complete for {survey_type}/{year}")


class SurveyManager:
    """Facade that selects and manages survey sources based on config.

    Reads the ``data.surveys`` list from config, instantiates the
    appropriate ``BaseSurveyTrip`` subclass for each entry, and provides
    a single interface for downstream code to load data and process
    persons.

    Typical single-survey usage::

        manager = SurveyManager(config)
        survey_df = manager.get_survey_df()       # single DataFrame
        persons   = manager.get_persons()          # single persons dict

    Multi-survey usage (consumed by blending in Step 6)::

        all_data    = manager.load_data()          # {'tbi': df, 'nhts': df2}
        all_persons = manager.process_persons()    # {'tbi': {...}, 'nhts': {...}}
        weights     = manager.get_blend_weights()  # {'tbi': 0.7, 'nhts': 0.3}
    """

    # Registry mapping survey type strings to their classes.
    # New survey types are registered here.
    SURVEY_REGISTRY: Dict[str, type] = {}

    @classmethod
    def _ensure_registry(cls) -> None:
        """Lazily populate the registry to avoid circular imports."""
        if cls.SURVEY_REGISTRY:
            return
        from data_sources.tbi_survey import TBISurveyTrip
        from data_sources.nhts_survey_trip import NHTSSurveyTrip
        from data_sources.bham_local_survey import BirminghamLocalSurveyTrip
        cls.SURVEY_REGISTRY = {
            'tbi': TBISurveyTrip,
            'nhts': NHTSSurveyTrip,
            'bham_local': BirminghamLocalSurveyTrip,
        }

    # data.survey_months = "regular": no summer, no December/January holidays.
    # Counts should come from one of these months too (counts.fha.month).
    REGULAR_MONTHS = frozenset({3, 4, 5, 9, 10, 11})
    # A source keeps its month filter only when every segment still has this
    # many person-days inside the window; otherwise it falls back to all months.
    MIN_SEGMENT_DAYS_IN_WINDOW = 200

    def __init__(self, config: Dict):
        self.config = config
        self.survey_configs: List[Dict] = config['data']['surveys']
        validate_survey_roles(self.survey_configs)
        # Trip sources: every source with a trip job (chains/times/modes/od).
        # All trip consumers (load_data, process_persons, get_survey_df, ...)
        # read only these.
        self.sources: Dict[str, BaseSurveyTrip] = {}
        # Sources with person_days > 0. May include sources that are not trip
        # sources (e.g. NHTS used for person-days only).
        self.person_day_sources: Dict[str, BaseSurveyTrip] = {}
        self._person_days: Optional[Dict[str, Optional[pd.DataFrame]]] = None
        # Per source: ('person', set_of_ids) | ('person_date', set_of_pairs)
        # | ('month', months) | None (no month filter).
        self._month_filters: Dict[str, Optional[tuple]] = {}
        # Make sure every active survey is ingested into the DB before any
        # load_data() call. ensure_surveys() is idempotent: it inspects the
        # existing (source_type, source_year) pairs and only runs the ETL for
        # sources that are missing.
        ensure_surveys(config)
        self._init_sources()

    def _init_sources(self) -> None:
        """Instantiate one BaseSurveyTrip subclass per config entry that does a job."""
        self._ensure_registry()

        for entry in self.survey_configs:
            survey_type = entry['type']
            if not is_active_entry(entry):
                logger.info(f"Skipping survey source '{survey_type}' (no job has weight > 0)")
                continue
            survey_class = self.SURVEY_REGISTRY.get(survey_type)
            if survey_class is None:
                raise ValueError(
                    f"Unknown survey type '{survey_type}'. "
                    f"Registered types: {list(self.SURVEY_REGISTRY.keys())}"
                )
            source = survey_class(self.config)
            # Set metadata from config entry
            source.metadata['source_type'] = survey_type
            source.metadata['source_year'] = entry.get('year', '')
            if any(role_weight(entry, r) > 0 for r in TRIP_ROLES):
                self.sources[survey_type] = source
            if role_weight(entry, ROLE_PERSON_DAYS) > 0:
                self.person_day_sources[survey_type] = source
            logger.info(f"Initialized survey source: {survey_type} (year={entry.get('year', '?')})")
        self.log_roles()

    def role_table(self) -> Dict[str, Dict[str, float]]:
        """{job: {source: configured weight}} for every active source."""
        return {r: {e['type']: role_weight(e, r) for e in self.survey_configs if is_active_entry(e)}
                for r in ROLES}

    def log_roles(self) -> None:
        """Log which source does which job (configured weights, before normalising)."""
        table = self.role_table()
        names = [e['type'] for e in self.survey_configs if is_active_entry(e)]
        logger.info("SURVEY ROLES (configured weights; a source that cannot do a job is skipped)")
        logger.info("  " + f"{'job':12s}" + "".join(f"{n:>14s}" for n in names))
        for r in ROLES:
            logger.info("  " + f"{r:12s}" + "".join(f"{table[r][n]:>14.2f}" for n in names))

    # ── Day-type filtering ──────────────────────────────────────────────

    def _day_type(self) -> str:
        """Which travel days to model: 'weekday' (default), 'weekend' or 'all'.

        Weekday is the default because everything the model is validated
        against is weekday-only: both counts loaders filter to Mon-Fri
        (CountsGenerator._load_custom_counts, FHACountsManager). Modelling a
        72/28 weekday/weekend mixture against a weekday yardstick flattens
        the morning peak and inflates the evening. Measured on NHTS 2022:
        07-09 holds 21.3% of weekday departures but 12.2% of weekend ones,
        and 19-23 holds 7.5% against 16.0%. Activity durations move too: on
        the weekday-only fit a median School stay is 411 min against 315 when
        weekend days are pooled in, and Social is 95 against 105.

        Note this does NOT address the 0-4 shortfall -- weekday and weekend
        night departures are both far below what the counts show. It is a
        peak-shape and duration correction.
        """
        value = str(self.config.get('data', {}).get('day_type', 'weekday')).lower()
        if value not in ('weekday', 'weekend', 'all'):
            raise ValueError(
                f"data.day_type must be 'weekday', 'weekend' or 'all', "
                f"got '{value}'"
            )
        return value

    def _filter_day_type(self, df: pd.DataFrame, source_key: str) -> pd.DataFrame:
        """Drop trips that do not match the configured day type.

        The travel day is read off ``depart_time`` rather than carried in a
        column of its own, so nothing has to change in the database: TBI
        records a real calendar date, and the NHTS loader encodes TRAVDAY
        into the synthetic date it builds (see NHTSSurveyTrip).

        A source whose dates carry no day-of-week variation — every trip on
        one weekday — cannot have been given a real travel day, so it is
        passed through untouched with a warning rather than being wholly
        dropped or wholly kept by accident.
        """
        day_type = self._day_type()
        if day_type == 'all':
            return df

        depart = df.get(BaseSurveyTrip.DEPART_TIME)
        if depart is None:
            logger.warning(
                f"Survey '{source_key}' has no '{BaseSurveyTrip.DEPART_TIME}' "
                f"column — cannot filter to {day_type}; using all its trips."
            )
            return df

        depart = pd.to_datetime(depart, errors='coerce')
        weekday = depart.dt.weekday  # Monday=0 .. Sunday=6

        # Data ingested before the loader preserved the travel day sits on a
        # single synthetic date, so every trip reads as the same weekday.
        # Filtering on that would keep everything or drop everything for the
        # wrong reason; say so instead.
        distinct_days = int(weekday.dropna().nunique())
        if distinct_days <= 1:
            logger.warning(
                f"Survey '{source_key}': every trip falls on the same weekday, "
                f"so its travel day was not preserved (data ingested before "
                f"day-type tracking, or a survey with no day information). "
                f"Using all its trips instead of filtering to {day_type}. "
                f"Delete its rows from the survey_trips table to re-run the "
                f"ETL and enable filtering."
            )
            return df

        is_weekend = weekday >= 5
        keep = is_weekend if day_type == 'weekend' else ~is_weekend
        # A trip whose depart_time could not be parsed has no day and is
        # excluded: it cannot be placed in the modelled day.
        keep = keep & weekday.notna()

        filtered = df[keep]
        n_dropped = len(df) - len(filtered)
        if n_dropped:
            n_unknown = int(weekday.isna().sum())
            logger.info(
                f"Survey '{source_key}': kept {len(filtered):,}/{len(df):,} "
                f"{day_type} trips (dropped {n_dropped:,}"
                + (f", of which {n_unknown:,} had an unparseable date" if n_unknown else "")
                + ")"
            )
        if filtered.empty:
            raise ValueError(
                f"Survey '{source_key}' has no {day_type} trips after day-type "
                f"filtering. Set data.day_type='all' to disable the filter."
            )
        return filtered

    # ── Survey months and person-days ───────────────────────────────────

    def survey_months(self) -> Optional[frozenset]:
        """Months to use from the surveys (data.survey_months), or None = all.

        "regular" (the default) = Mar, Apr, May, Sep, Oct, Nov; "all"; or a
        list of month numbers.
        """
        value = self.config.get('data', {}).get('survey_months', 'regular')
        if isinstance(value, str):
            v = value.lower()
            if v == 'all':
                return None
            if v == 'regular':
                return self.REGULAR_MONTHS
            raise ValueError(f"data.survey_months must be 'regular', 'all' or a list "
                             f"of months, got '{value}'")
        months = frozenset(int(m) for m in value)
        if not months or not months <= set(range(1, 13)):
            raise ValueError(f"data.survey_months list must hold months 1-12, got {value}")
        return months

    def get_person_days(self) -> Dict[str, Optional[pd.DataFrame]]:
        """Person-day table per person_days source, filtered by day type and months.

        A source without a person file maps to None (it cannot do the
        person_days job). The month window of each source is decided here,
        and the same window is later applied to its trips (see
        _filter_months), so the day types, the chains and the time models all
        describe the same days. The window is decided for every active source,
        also for trip sources whose person_days weight is 0; only the
        person_days sources are returned.
        """
        if self._person_days is None:
            self._person_days = self._load_person_days_all()
        return {k: v for k, v in self._person_days.items() if k in self.person_day_sources}

    def _all_active_sources(self) -> Dict[str, BaseSurveyTrip]:
        return {**self.sources, **self.person_day_sources}

    def _load_person_days_all(self) -> Dict[str, Optional[pd.DataFrame]]:
        day_type = self._day_type()
        months = self.survey_months()
        result: Dict[str, Optional[pd.DataFrame]] = {}
        for key, source in self._all_active_sources().items():
            pd_df = source.load_person_days()
            if pd_df is None or pd_df.empty:
                result[key] = None
                self._month_filters[key] = ('month', months) if months else None
                continue

            wd = pd_df[BaseSurveyTrip.PD_WEEKDAY]
            if day_type == 'weekday':
                pd_df = pd_df[wd < 5]
            elif day_type == 'weekend':
                pd_df = pd_df[wd >= 5]

            if months:
                in_window = pd_df[pd_df[BaseSurveyTrip.PD_MONTH].isin(months)]
                counts = in_window.groupby(BaseSurveyTrip.PD_SEGMENT).size()
                segments = [BaseSurveyTrip.SEG_WORKER, BaseSurveyTrip.SEG_STUDENT,
                            BaseSurveyTrip.SEG_NONWORKER_ADULT]
                thin = {s: int(counts.get(s, 0)) for s in segments
                        if counts.get(s, 0) < self.MIN_SEGMENT_DAYS_IN_WINDOW}
                if thin:
                    logger.warning(
                        f"Survey '{key}': too few person-days in months {sorted(months)} "
                        f"for {thin} (need {self.MIN_SEGMENT_DAYS_IN_WINDOW}); "
                        f"using ALL months for this source")
                else:
                    logger.info(f"Survey '{key}': month window {sorted(months)} keeps "
                                f"{len(in_window):,}/{len(pd_df):,} {day_type} person-days")
                    pd_df = in_window

            has_dates = pd_df[BaseSurveyTrip.PD_DATE].notna().any()
            if has_dates:
                keys = set(zip(pd_df[BaseSurveyTrip.PD_PERSON_ID].astype(str),
                               pd_df[BaseSurveyTrip.PD_DATE].astype(str)))
                self._month_filters[key] = ('person_date', keys)
            else:
                self._month_filters[key] = ('person', set(pd_df[BaseSurveyTrip.PD_PERSON_ID].astype(str)))
            result[key] = pd_df.reset_index(drop=True)

        self._person_days = result
        return result

    def _filter_months(self, df: pd.DataFrame, source_key: str) -> pd.DataFrame:
        """Keep only the trips of the person-days selected by get_person_days().

        A source without person-days is filtered by the month of depart_time
        when its dates carry real months; otherwise it is kept whole.
        """
        self.get_person_days()
        rule = self._month_filters.get(source_key)
        if rule is None or df.empty:
            return df
        kind, value = rule
        pid = df[BaseSurveyTrip.PERSON_ID].astype(str)
        if kind == 'person':
            keep = pid.isin(value)
        elif kind == 'person_date':
            date = pd.to_datetime(df[BaseSurveyTrip.DEPART_TIME], errors='coerce').dt.strftime('%Y-%m-%d')
            keep = pd.Series([k in value for k in zip(pid, date)], index=df.index)
        else:  # 'month' — no person-days
            month = pd.to_datetime(df[BaseSurveyTrip.DEPART_TIME], errors='coerce').dt.month
            if month.nunique() <= 1:
                logger.warning(f"Survey '{source_key}': no person-days and no real months "
                               f"in its dates; the month filter is not applied")
                return df
            keep = month.isin(value)
        filtered = df[keep]
        logger.info(f"Survey '{source_key}': month/person-day filter kept "
                    f"{len(filtered):,}/{len(df):,} trips")
        if filtered.empty:
            raise ValueError(f"Survey '{source_key}' has no trips left after the month filter. "
                             f"Check data.survey_months or the person-day files.")
        return filtered

    # ── Multi-source interface ──────────────────────────────────────────

    def load_data(self) -> Dict[str, pd.DataFrame]:
        """Load data from DB for each active source.

        Returns:
            ``{'tbi': df1, 'nhts': df2, ...}``
        """
        result = {}
        for key, source in self.sources.items():
            df = self._filter_day_type(source.load_data(), key)
            result[key] = self._filter_months(df, key)
            logger.info(f"Loaded {len(result[key])} records for '{key}'")
        return result

    def process_persons(self, role: Optional[str] = None) -> Dict[str, Dict]:
        """Process persons from each trip source (or each source of *role*).

        ``role=ROLE_PERSON_DAYS`` returns the persons of the person_days
        sources, which the demand budget needs to match trips to person-days
        even when such a source does no trip job.

        Returns:
            ``{'tbi': persons_dict, 'nhts': persons_dict, ...}``
        """
        if role == ROLE_PERSON_DAYS:
            sources = self.person_day_sources
        elif role is None:
            sources = self.sources
        else:
            w = self.get_blend_weights(role)
            sources = {k: s for k, s in self.sources.items() if w.get(k, 0) > 0}
        result = {}
        for key, source in sources.items():
            # process_persons() groups whatever sits in source.data, so the
            # day-type filter has to be applied to that frame rather than to
            # the result. Otherwise the activity duration model — which is
            # built from persons, not from the trip frame — would keep every
            # weekend day.
            #
            # source.data is restored afterwards: the filter is a view of this
            # call, not a permanent edit to the source. Leaving it filtered
            # would make a later load_data() filter an already-filtered frame
            # and report misleading counts.
            if source.data is None:
                source.load_data()
            original = source.data
            try:
                source.data = self._filter_months(self._filter_day_type(original, key), key)
                result[key] = source.process_persons()
            finally:
                source.data = original
            logger.info(f"Processed {len(result[key])} persons for '{key}'")
        return result

    def get_blend_weights(self, role: Optional[str] = None) -> Dict[str, float]:
        """Per-source weights (> 0) for one job; see ROLES.

        ``role=None`` keeps the old meaning: the entry ``weight`` of every
        trip source. Callers that blend a specific job should pass its role.

        Returns:
            ``{'tbi': 0.7, 'nhts': 0.3}``
        """
        out = {}
        for entry in self.survey_configs:
            name = entry['type']
            if role is None:
                w = entry.get('weight', 1.0)
            else:
                w = role_weight(entry, role)
            # Trip jobs only blend trip sources; person_days has its own set.
            eligible = name in (self.person_day_sources if role == ROLE_PERSON_DAYS
                                else self.sources)
            if w > 0 and eligible:
                out[name] = w
        return out

    def get_role_weights(self) -> Dict[str, Dict[str, float]]:
        """{job: {source: weight > 0}} for every job; passed to worker processes."""
        return {r: self.get_blend_weights(r) for r in ROLES}

    def has_multiple_sources(self) -> bool:
        """Return True when more than one survey supplies trips (any trip job)."""
        return len(self.sources) > 1

    def filter_df_by_role(self, df: pd.DataFrame, role: str) -> pd.DataFrame:
        """Rows of a joined survey frame whose source does *role* (weight > 0)."""
        col = BaseSurveyTrip.SOURCE_TYPE
        if df is None or df.empty or col not in df.columns:
            return df
        return df[df[col].isin(set(self.get_blend_weights(role)))]

    def get_surveys_with_locations(self, all_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """Filter loaded survey DataFrames to those with non-null location data.

        A survey "has locations" if its ``origin_loc`` column contains at
        least one non-null value.  Surveys like NHTS (public-use) set
        ``origin_loc`` to ``None`` for every row and are therefore
        excluded from OD matrix and trip-rate blending.

        Args:
            all_data: Result of ``load_data()`` — ``{source_key: DataFrame}``.

        Returns:
            Subset dict containing only sources with location data.
        """
        o_col = BaseSurveyTrip.ORIGIN_LOC
        result = {}
        for name, df in all_data.items():
            if o_col in df.columns and df[o_col].notna().any():
                result[name] = df
            else:
                logger.info(
                    f"Survey '{name}' excluded from location-based models "
                    f"(no non-null {o_col} values)"
                )
        return result

    @staticmethod
    def detect_geo_level_from_df(df: pd.DataFrame) -> Optional[str]:
        """Detect census geography level from non-null origin_loc values in a DataFrame.

        Mirrors BaseSurveyTrip.detect_geo_level() but operates on an already-loaded
        DataFrame rather than a live survey instance.  Used when data is loaded from
        the database (where clean_data() is not re-run and metadata is not populated).

        Returns:
            A geo level constant from BaseSurveyTrip (e.g. 'block_group', 'tract'),
            or None if all origin_loc values are null.

        Raises:
            ValueError: If GEOID lengths are non-uniform or the length is unrecognised.
        """
        o_col = BaseSurveyTrip.ORIGIN_LOC
        if o_col not in df.columns:
            return None

        non_null = df[o_col].dropna()
        non_null = non_null[non_null.astype(str).str.strip() != '']

        if non_null.empty:
            return None

        lengths = non_null.astype(str).str.strip().str.len().unique()

        if len(lengths) > 1:
            raise ValueError(
                f"detect_geo_level_from_df: non-uniform GEOID lengths in origin_loc: "
                f"{sorted(lengths)}. Check for dirty data or mixed geography types."
            )

        length = int(lengths[0])
        geo_level = BaseSurveyTrip.GEOID_LENGTH_TO_GEO_LEVEL.get(length)

        if geo_level is None:
            raise ValueError(
                f"detect_geo_level_from_df: GEOID length {length} does not match any "
                f"known census geography. Supported lengths: "
                f"{list(BaseSurveyTrip.GEOID_LENGTH_TO_GEO_LEVEL.keys())}"
            )

        return geo_level

    # ── Single-source convenience methods ───────────────────────────────

    def get_single_source(self) -> Optional[BaseSurveyTrip]:
        """Return the single source when only one survey is configured.

        Returns ``None`` if multiple sources are active.
        """
        if len(self.sources) == 1:
            return next(iter(self.sources.values()))
        return None

    def get_survey_df(self) -> pd.DataFrame:
        """Convenience: load and return a single combined DataFrame.

        When one survey is configured this returns its DataFrame directly.
        When multiple surveys are configured this concatenates them (each
        row retains its ``source_type`` column for downstream filtering).
        """
        all_data = self.load_data()
        if len(all_data) == 1:
            return next(iter(all_data.values()))
        return pd.concat(all_data.values(), ignore_index=True)

    def get_persons(self) -> Dict:
        """Convenience: process and return a single persons dict.

        When one survey is configured this returns its persons dict
        directly.  When multiple surveys are configured this merges them
        (person IDs are already unique per survey since they include
        source-specific identifiers).
        """
        all_persons = self.process_persons()
        if len(all_persons) == 1:
            return next(iter(all_persons.values()))
        merged = {}
        for persons_dict in all_persons.values():
            merged.update(persons_dict)
        return merged

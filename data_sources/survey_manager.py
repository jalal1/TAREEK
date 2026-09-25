from typing import Dict, List, Optional
import pandas as pd
from utils.logger import setup_logger
from data_sources.base_survey_trip import BaseSurveyTrip
from models.models import SurveyTrip, initialize_tables

logger = setup_logger(__name__)


def ensure_surveys(config: Dict) -> None:
    """Ensure survey data exists in the database for all active survey sources.

    For each survey entry in config['data']['surveys'] with weight > 0,
    checks whether the survey_trips table already has rows for that
    (source_type, source_year).  If not, runs the full ETL pipeline:
    extract_data → clean_data → save_data.
    """
    survey_configs = config['data'].get('surveys', [])
    active_entries = [e for e in survey_configs if e.get('weight', 1.0) > 0]
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
        cls.SURVEY_REGISTRY = {
            'tbi': TBISurveyTrip,
            'nhts': NHTSSurveyTrip,
        }

    def __init__(self, config: Dict):
        self.config = config
        self.survey_configs: List[Dict] = config['data']['surveys']
        self.sources: Dict[str, BaseSurveyTrip] = {}
        # Make sure every active survey is ingested into the DB before any
        # load_data() call. ensure_surveys() is idempotent: it inspects the
        # existing (source_type, source_year) pairs and only runs the ETL for
        # sources that are missing.
        ensure_surveys(config)
        self._init_sources()

    def _init_sources(self) -> None:
        """Instantiate one BaseSurveyTrip subclass per config entry with weight > 0."""
        self._ensure_registry()

        for entry in self.survey_configs:
            survey_type = entry['type']
            weight = entry.get('weight', 1.0)
            if weight <= 0:
                logger.info(f"Skipping survey source '{survey_type}' (weight={weight})")
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
            self.sources[survey_type] = source
            logger.info(f"Initialized survey source: {survey_type} (year={entry.get('year', '?')})")

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

    # ── Multi-source interface ──────────────────────────────────────────

    def load_data(self) -> Dict[str, pd.DataFrame]:
        """Load data from DB for each active source.

        Returns:
            ``{'tbi': df1, 'nhts': df2, ...}``
        """
        result = {}
        for key, source in self.sources.items():
            result[key] = self._filter_day_type(source.load_data(), key)
            logger.info(f"Loaded {len(result[key])} records for '{key}'")
        return result

    def process_persons(self) -> Dict[str, Dict]:
        """Process persons from each active source.

        Returns:
            ``{'tbi': persons_dict, 'nhts': persons_dict, ...}``
        """
        result = {}
        for key, source in self.sources.items():
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
                source.data = self._filter_day_type(original, key)
                result[key] = source.process_persons()
            finally:
                source.data = original
            logger.info(f"Processed {len(result[key])} persons for '{key}'")
        return result

    def get_blend_weights(self) -> Dict[str, float]:
        """Build weights dict from active config entries (weight > 0).

        Returns:
            ``{'tbi': 0.7, 'nhts': 0.3}``
        """
        return {
            entry['type']: entry.get('weight', 1.0)
            for entry in self.survey_configs
            if entry.get('weight', 1.0) > 0
        }

    def has_multiple_sources(self) -> bool:
        """Return True when more than one survey is configured with weight > 0."""
        active = [
            entry for entry in self.survey_configs
            if entry.get('weight', 1.0) > 0
        ]
        return len(active) > 1

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

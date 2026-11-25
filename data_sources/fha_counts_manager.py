# SPDX-License-Identifier: GPL-3.0-or-later
"""
FHA/TMAS Traffic Counts Manager

Handles extraction, transformation, and loading of Federal Highway Administration
Traffic Monitoring Analysis System (TMAS) data. Reads pipe-delimited .STA (station)
and .VOL (volume) files from zip archives, filters by configured counties, aggregates
to per-direction hourly averages (one row per station-direction), and stores results
in the database.

Follows the GTFSManager pattern: a manager with a setup() method called from
run_experiment.py, with data cached in the DB so ETL only runs once per region.
"""

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, Set

import pandas as pd

from models.models import Base, FHAStation, FHAHourlyVolume
from utils.logger import setup_logger

logger = setup_logger(__name__)

# FIPS state code -> 2-letter postal abbreviation (all 50 states + DC)
STATE_FIPS_TO_ABBR = {
    '01': 'AL', '02': 'AK', '04': 'AZ', '05': 'AR', '06': 'CA',
    '08': 'CO', '09': 'CT', '10': 'DE', '11': 'DC', '12': 'FL',
    '13': 'GA', '15': 'HI', '16': 'ID', '17': 'IL', '18': 'IN',
    '19': 'IA', '20': 'KS', '21': 'KY', '22': 'LA', '23': 'ME',
    '24': 'MD', '25': 'MA', '26': 'MI', '27': 'MN', '28': 'MS',
    '29': 'MO', '30': 'MT', '31': 'NE', '32': 'NV', '33': 'NH',
    '34': 'NJ', '35': 'NM', '36': 'NY', '37': 'NC', '38': 'ND',
    '39': 'OH', '40': 'OK', '41': 'OR', '42': 'PA', '44': 'RI',
    '45': 'SC', '46': 'SD', '47': 'TN', '48': 'TX', '49': 'UT',
    '50': 'VT', '51': 'VA', '53': 'WA', '54': 'WV', '55': 'WI',
    '56': 'WY',
}

# Opposite direction pairs per FHWA coding: 1=N, 2=NE, 3=E, 4=SE, 5=S, 6=SW, 7=W, 8=NW
OPPOSITE_DIRS = {1: 5, 5: 1, 3: 7, 7: 3, 2: 6, 6: 2, 4: 8, 8: 4}


class FHASchemaError(RuntimeError):
    """Raised when the FHA tables cannot be brought to the per-direction schema.

    An old-shape DB is upgraded automatically (see
    FHACountsManager._check_schema), so this now signals that the automatic
    rebuild itself failed — a fatal, user-actionable condition. Callers must
    NOT swallow it and continue, or the pipeline would silently run without
    FHA validation against an incompatible DB.
    """


class FHACountsManager:
    """
    Manages FHA/TMAS traffic count data: discovery, extraction, aggregation, and DB loading.

    Usage:
        manager = FHACountsManager(config, db_manager)
        success = manager.setup()
    """

    def __init__(self, config: Dict[str, Any], db_manager):
        self.config = config
        self.db_manager = db_manager

        counts_config = config.get('counts', {})
        fha_config = counts_config.get('fha', {})

        self.data_dir = Path(fha_config.get('data_dir', 'data/FHA_counts'))
        self.year = fha_config.get('year', 2024)
        self.month = fha_config.get('month', 7)

        # Month number -> 3-letter abbreviation for volume file names
        self._month_abbrs = {
            1: 'JAN', 2: 'FEB', 3: 'MAR', 4: 'APR', 5: 'MAY', 6: 'JUN',
            7: 'JUL', 8: 'AUG', 9: 'SEP', 10: 'OCT', 11: 'NOV', 12: 'DEC',
        }

    def setup(self, rebuild: bool = False) -> bool:
        """
        Full ETL pipeline: extract from zips, filter, aggregate, load to DB.

        Args:
            rebuild: When True, clear any existing FHA data for the configured
                states and re-run the ETL, even if data is already in the DB.
                Use this to pick up changes to year/month or the county list.

        Returns:
            True if data was loaded successfully, False otherwise.
        """
        logger.info("Setting up FHA counts data...")

        # Schema guard: the FHA tables now key on travel_dir (per-direction).
        # An old-shape table (pre per-direction) is incompatible — refuse to
        # run rather than fail cryptically on insert.
        self._check_schema()

        # Determine which states/counties we need
        needed = self._get_needed_states()
        if not needed:
            logger.warning("FHA: no counties configured — cannot load FHA data")
            return False

        if not rebuild and self.has_data_for_region():
            logger.info("FHA counts data already loaded in DB — skipping ETL")
            return True

        # Find zip files
        station_zip = self.data_dir / f"{self.year}_station_data.zip"
        month_abbr = self._month_abbrs.get(self.month, 'JUL').lower()
        volume_zip = self.data_dir / f"{month_abbr}_{self.year}_ccs_data.zip"

        # TAREEK does not download these files: the FHWA site does not allow
        # automated downloads. The repository ships 2024 stations + October.
        where = ("Download it from the FHWA 'U.S. Traffic Volume Data' (TMAS) page "
                 "(https://highways.dot.gov/policy/policy-information/special-tabulations/"
                 f"us-traffic-volume-data) and put it in {self.data_dir}, or set "
                 "fha.year/fha.month to a file that is there.")
        missing_zip = next((z for z in (station_zip, volume_zip) if not z.exists()), None)
        if missing_zip is not None:
            # Without the zips the DB cannot be reloaded. Keep the rows that
            # are there (the old behaviour) rather than clear them: a machine
            # may have the DB but not the zips.
            if not rebuild and self._db_has_rows_for(needed):
                logger.warning(f"FHA zip not found: {missing_zip}. Using the stations "
                               f"already in the DB; they may belong to another region, "
                               f"year or month. {where}")
                return True
            logger.error(f"FHA zip not found: {missing_zip}. {where}")
            return False

        # Rebuild, or rows of another region / year / month: clear the
        # states first, so no station of the old region stays behind.
        logger.info("FHA counts: clearing existing data for the needed states and re-running ETL"
                    + (" (rebuild requested)" if rebuild else ""))
        self._clear_region_data(needed)

        all_stations = []
        all_volumes = []

        for state_fips, county_codes in needed.items():
            state_abbr = self._state_fips_to_abbr(state_fips)
            if not state_abbr:
                logger.warning(f"FHA: unknown state FIPS '{state_fips}' — skipping")
                continue

            logger.info(f"FHA: parsing stations for state {state_abbr}, "
                        f"filtering to counties {sorted(county_codes)}")
            stations_df = self._parse_stations(station_zip, state_abbr, state_fips, county_codes)

            if stations_df.empty:
                logger.warning(f"FHA: no stations found for state {state_abbr} "
                               f"counties {sorted(county_codes)}")
                continue

            station_ids = set(stations_df['station_id'].unique())
            logger.info(f"FHA: parsing volumes for state {state_abbr}, "
                        f"{len(station_ids)} station IDs")
            volumes_df = self._parse_volumes(volume_zip, state_abbr, state_fips, station_ids)

            all_stations.append(stations_df)
            if not volumes_df.empty:
                all_volumes.append(volumes_df)

        if not all_stations:
            logger.warning("FHA: no stations found for configured counties — "
                           "counts.xml will not be generated")
            return False

        stations_combined = pd.concat(all_stations, ignore_index=True)
        if not all_volumes:
            logger.warning("FHA: no volume data found — counts.xml will not be generated")
            return False

        volumes_combined = pd.concat(all_volumes, ignore_index=True)

        # Aggregate to per-direction hourly averages (one row per station-direction)
        agg_volumes = self._aggregate_by_direction(volumes_combined)
        if agg_volumes.empty:
            logger.warning("FHA: aggregation produced no volume rows — "
                           "counts.xml will not be generated")
            return False

        # Keep only station-directions that exist in BOTH the STA and VOL data
        # (a direction in one file but not the other can't be used).
        sta_keys = set(zip(stations_combined['station_id'], stations_combined['travel_dir']))
        vol_keys = set(zip(agg_volumes['station_id'], agg_volumes['travel_dir']))
        only_sta = sta_keys - vol_keys
        only_vol = vol_keys - sta_keys
        if only_sta:
            logger.info(f"FHA: {len(only_sta)} station-directions in STA have no "
                        f"volume data — skipped")
        if only_vol:
            logger.info(f"FHA: {len(only_vol)} station-directions in VOL have no "
                        f"station metadata — skipped")
        common = sta_keys & vol_keys

        def _key_mask(df):
            return df.apply(lambda r: (r['station_id'], r['travel_dir']) in common, axis=1)

        stations_with_vol = stations_combined[_key_mask(stations_combined)].copy()
        agg_volumes = agg_volumes[_key_mask(agg_volumes)].copy()

        # Load to DB
        self._load_to_db(stations_with_vol, agg_volumes)
        self._write_region_marker()

        logger.info(f"FHA: loaded {len(stations_with_vol)} station-directions, "
                    f"{len(agg_volumes)} volume records for "
                    f"{len(self._get_needed_states())} state(s)")
        return True

    def _check_schema(self):
        """Bring a pre-per-direction FHA schema up to date, in place.

        Older DBs have fha_stations / fha_hourly_volumes without a travel_dir
        column. Inserting per-direction records there would fail or corrupt the
        data.

        Both tables hold only derived data: every row is re-ingested from the
        TMAS zip archives in data/FHA_counts on demand, and setup() refills
        them later in this same call via has_data_for_region(). So the upgrade
        is a drop + recreate with nothing to preserve, and there is no reason
        to stop the run and make the user do it by hand — a fresh clone would
        hit this on its first run against an existing DB.

        scripts/migrate_fha_perdirection.py remains for running the same
        upgrade standalone; this method is the automatic path.
        """
        stale = [
            table for table in ('fha_stations', 'fha_hourly_volumes')
            if (cols := self.db_manager.get_table_columns(table))
            and 'travel_dir' not in cols
        ]
        if not stale:
            return

        logger.warning(
            f"FHA tables {stale} use the old (pre per-direction) schema — "
            f"missing 'travel_dir'. Rebuilding them empty in the new schema; "
            f"the counts data re-ingests from the zip archives in this run."
        )
        try:
            self.db_manager.drop_table(FHAHourlyVolume)
            self.db_manager.drop_table(FHAStation)
            with self.db_manager.write_engine_scope() as engine:
                Base.metadata.create_all(engine)
        except Exception as exc:  # noqa: BLE001 - re-raised as FHASchemaError
            raise FHASchemaError(
                f"Could not upgrade the FHA tables to the per-direction schema: "
                f"{exc}\nRun the migration manually:\n"
                f"    python scripts/migrate_fha_perdirection.py --config <config.json>"
            ) from exc

        # Verify rather than assume: a silent failure here would surface later
        # as a confusing insert error.
        for table in ('fha_stations', 'fha_hourly_volumes'):
            cols = self.db_manager.get_table_columns(table)
            if not cols or 'travel_dir' not in cols:
                raise FHASchemaError(
                    f"FHA table '{table}' still lacks 'travel_dir' after the "
                    f"automatic rebuild. Run the migration manually:\n"
                    f"    python scripts/migrate_fha_perdirection.py --config <config.json>"
                )
        logger.info("FHA tables rebuilt in the per-direction schema.")

    def has_data_for_region(self) -> bool:
        """Check if FHA data is already loaded in the DB for the configured region.

        Returns True if at least one station exists for each needed state.
        Some counties may legitimately have no FHA stations — that's not a reason
        to re-run the ETL.
        """
        needed = self._get_needed_states()
        if not needed:
            return False

        # The DB keeps one region per state: the stations of the counties of
        # the last ETL. A run with other counties in the same state, or another
        # fha.year/month, must reload, or it silently uses the old stations.
        marker = self._read_region_marker()
        signature = self._region_signature()
        for state_fips in needed:
            if marker.get(state_fips) != signature[state_fips]:
                logger.info(f"FHA: DB rows for state {state_fips} were loaded for "
                            f"{marker.get(state_fips) or 'an unknown region'}; this run "
                            f"needs {signature[state_fips]} -> reloading")
                return False
        return self._db_has_rows_for(needed)

    def _db_has_rows_for(self, needed) -> bool:
        """True when the DB has at least one station for every needed state."""
        for state_fips in needed:
            if not self.db_manager.query_all(FHAStation, filters={'state_code': state_fips}):
                return False
        return True

    def _clear_region_data(self, needed: Dict[str, Set[str]]):
        """Delete existing FHA stations and hourly volumes for the needed states.

        Called on rebuild so stale rows (e.g. from a different year/month or a
        wider county list) don't shadow a fresh ETL via has_data_for_region().
        """
        for state_fips in needed:
            self.db_manager.delete_records(FHAHourlyVolume, filters={'state_code': state_fips})
            self.db_manager.delete_records(FHAStation, filters={'state_code': state_fips})
        logger.info(f"FHA: cleared existing data for state(s) {sorted(needed)}")

    def _get_needed_states(self) -> Dict[str, Set[str]]:
        """
        From configured county GEOIDs, build {state_fips: {county_code, ...}}.

        Returns:
            Dict mapping 2-digit state FIPS to set of 3-digit county codes.
        """
        region_config = self.config.get('region', {})
        counties = region_config.get('counties') or self.config.get('network', {}).get('counties', [])

        result = {}
        for geoid in counties:
            state_fips = geoid[:2]
            county_code = geoid[2:]
            result.setdefault(state_fips, set()).add(county_code)
        return result

    def _state_fips_to_abbr(self, state_fips: str) -> str:
        """Convert 2-digit FIPS state code to 2-letter postal abbreviation."""
        return STATE_FIPS_TO_ABBR.get(state_fips, '')

    def _parse_stations(self, zip_path: Path, state_abbr: str,
                        state_fips: str, county_codes: Set[str]) -> pd.DataFrame:
        """
        Parse station data from a .STA file inside the zip, filtered by county.

        Returns:
            DataFrame with columns: station_id, lat, lon, county_code, f_system,
            station_location, state_code, year. One row per unique station
            (deduplicated from per-lane rows).
        """
        entry_name = f"{state_abbr}_{self.year} (TMAS).STA"

        try:
            with zipfile.ZipFile(zip_path) as zf:
                with zf.open(entry_name) as f:
                    df = pd.read_csv(f, sep='|', dtype=str, encoding='utf-8',
                                     on_bad_lines='skip')
        except KeyError:
            logger.warning(f"FHA: entry '{entry_name}' not found in {zip_path.name}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"FHA: error reading {entry_name}: {e}")
            return pd.DataFrame()

        # Strip whitespace from column values
        for col in ['station_id', 'county_code', 'latitude', 'longitude']:
            if col in df.columns:
                df[col] = df[col].str.strip()

        # Convert lat/lon: scaled integers → decimal, negate longitude for US
        df['lat'] = pd.to_numeric(df['latitude'], errors='coerce') / 1_000_000
        df['lon'] = -pd.to_numeric(df['longitude'], errors='coerce') / 1_000_000

        # Filter to our counties by LOCATION, not by the STA county_code.
        # States mis-code county_code (often '000'): Wisconsin codes nearly all
        # Dane County stations '000', so the code filter kept 10 of 59
        # station-directions for Madison, 100 of 136 for the Twin Cities and
        # 2 of 8 for Stearns (item 7, 2026-11-25). The counts generator
        # matches stations to links by their coordinates anyway.
        df = self._filter_to_region(df, state_fips, county_codes)
        if df.empty:
            return pd.DataFrame()

        # Direction code: keep only cardinal directions (1=N,3=E,5=S,7=W).
        # Diagonal codes (2/4/6/8) are rare and can't be matched to a single
        # network link bearing reliably, so we drop them.
        df['travel_dir'] = pd.to_numeric(df['travel_dir'], errors='coerce')
        n_before = len(df)
        df = df[df['travel_dir'].isin([1, 3, 5, 7])].copy()
        n_dropped = n_before - len(df)
        if n_dropped > 0:
            logger.info(f"FHA: dropped {n_dropped} station rows with non-cardinal "
                        f"travel_dir (diagonal codes 2/4/6/8)")
        if df.empty:
            return pd.DataFrame()
        df['travel_dir'] = df['travel_dir'].astype(int)

        # Deduplicate: keep one row per (station_id, travel_dir) — the STA file
        # has one row per direction (and per lane); we want a single row per
        # station-direction carrying the shared location.
        stations = df.drop_duplicates(subset=['station_id', 'travel_dir'], keep='first')

        result = pd.DataFrame({
            'station_id': stations['station_id'],
            'travel_dir': stations['travel_dir'],
            'lat': stations['lat'],
            'lon': stations['lon'],
            'county_code': stations['county_code'],
            'f_system': stations['f_system'].str.strip() if 'f_system' in stations.columns else '',
            'station_location': (stations['station_location'].str.strip()
                                 if 'station_location' in stations.columns else ''),
            'state_code': state_fips,
            'year': self.year,
        })

        return result.reset_index(drop=True)

    def _filter_to_region(self, df: pd.DataFrame, state_fips: str,
                          county_codes: Set[str]) -> pd.DataFrame:
        """Rows whose (lat, lon) is inside the configured counties of this state.

        Falls back to the STA county_code when the county polygons cannot be
        loaded (no shapefile and no download).
        """
        from utils.region_utils import load_county_polygons
        geoids = [state_fips + c for c in sorted(county_codes)]
        data_dir = self.config.get('data', {}).get('data_dir', 'data')
        polygons = load_county_polygons(geoids, data_dir)
        if not polygons:
            logger.warning(f"FHA: county polygons for {geoids} not available; "
                           f"filtering stations by the STA county_code (may drop "
                           f"mis-coded stations)")
            return df[df['county_code'].isin(county_codes)].copy()

        import geopandas as gpd
        from shapely.ops import unary_union
        region = unary_union(polygons)
        ok = df['lat'].notna() & df['lon'].notna()
        pts = gpd.GeoSeries(gpd.points_from_xy(df.loc[ok, 'lon'], df.loc[ok, 'lat']),
                            index=df.index[ok], crs='EPSG:4326')
        inside = pts.within(region)
        keep = df.loc[inside[inside].index].copy()
        by_code = df['county_code'].isin(county_codes)
        n_code = int(by_code.sum())
        n_gained = int((~by_code.loc[keep.index]).sum())
        n_lost = int((by_code & ~df.index.isin(keep.index)).sum())
        logger.info(f"FHA: {len(keep)} station rows inside the region counties "
                    f"(county_code filter would keep {n_code}: +{n_gained} mis-coded "
                    f"inside, -{n_lost} coded here but located outside)")
        return keep

    def _region_marker_path(self) -> Path:
        """Beside the DB file: the marker describes what the DB holds, so two
        DBs that share one FHA zip folder must not share one marker."""
        db_path = getattr(self.db_manager, 'db_path', None)
        if db_path:
            return Path(db_path).with_name(Path(db_path).stem + '.fha_region.json')
        return self.data_dir / '.loaded_region.json'

    def _region_signature(self) -> Dict[str, Any]:
        """What the DB rows of each state were loaded for."""
        return {st: {'counties': sorted(codes), 'year': int(self.year), 'month': int(self.month)}
                for st, codes in self._get_needed_states().items()}

    def _read_region_marker(self) -> Dict[str, Any]:
        try:
            with open(self._region_marker_path(), encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _write_region_marker(self) -> None:
        marker = self._read_region_marker()
        marker.update(self._region_signature())
        try:
            with open(self._region_marker_path(), 'w', encoding='utf-8') as f:
                json.dump(marker, f, indent=1, sort_keys=True)
        except OSError as e:
            logger.warning(f"FHA: could not write {self._region_marker_path()}: {e}")

    def _parse_volumes(self, zip_path: Path, state_abbr: str,
                       state_fips: str, station_ids: Set[str]) -> pd.DataFrame:
        """
        Parse volume data from a .VOL file inside the zip, filtered to given stations.

        Returns:
            DataFrame with columns: station_id, state_code, travel_dir, travel_lane,
            day_of_week, hour_00..hour_23
        """
        month_abbr = self._month_abbrs.get(self.month, 'JUL')
        entry_name = f"{state_abbr}_{month_abbr}_{self.year} (TMAS).VOL"

        try:
            with zipfile.ZipFile(zip_path) as zf:
                with zf.open(entry_name) as f:
                    df = pd.read_csv(f, sep='|', dtype=str, encoding='utf-8',
                                     on_bad_lines='skip')
        except KeyError:
            logger.warning(f"FHA: entry '{entry_name}' not found in {zip_path.name}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"FHA: error reading {entry_name}: {e}")
            return pd.DataFrame()

        # Strip station_id whitespace
        if 'station_id' in df.columns:
            df['station_id'] = df['station_id'].str.strip()

        # Filter to our stations
        df = df[df['station_id'].isin(station_ids)].copy()
        if df.empty:
            return pd.DataFrame()

        # Convert numeric columns
        hour_cols = [f'hour_{i:02d}' for i in range(24)]
        for col in hour_cols + ['travel_dir', 'travel_lane', 'day_of_week']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Keep only cardinal directions (1=N,3=E,5=S,7=W); drop diagonal codes
        # so they never reach aggregation (matches _parse_stations).
        n_before = len(df)
        df = df[df['travel_dir'].isin([1, 3, 5, 7])].copy()
        n_dropped = n_before - len(df)
        if n_dropped > 0:
            logger.info(f"FHA: dropped {n_dropped} volume rows with non-cardinal "
                        f"travel_dir (diagonal codes 2/4/6/8)")

        df['state_code'] = state_fips

        return df

    def _aggregate_by_direction(self, volumes_df: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate raw volume data to one row per (station, travel_dir) with 24
        per-direction hourly averages:
          1. Filter to weekdays only (day_of_week 2-6 = Mon-Fri)
          2. Sum across lanes per (station, direction, day, hour)
          3. Average across weekdays per (station, direction, hour)

        Opposite directions are NOT summed — each direction is kept separate so
        the real directional split is preserved (a 50/50 split is wrong on most
        commuter corridors).

        Returns:
            DataFrame with columns: station_id, state_code, travel_dir,
            h01..h24, num_weekdays_averaged
        """
        hour_cols = [f'hour_{i:02d}' for i in range(24)]

        # Step 1: Filter weekdays (2=Mon .. 6=Fri)
        df = volumes_df[volumes_df['day_of_week'].between(2, 6)].copy()
        if df.empty:
            logger.warning("FHA: no weekday volume data found")
            return pd.DataFrame()

        # Step 2: Sum across lanes per (station, direction, day_of_week, date-like grouping)
        # Since we have per-day rows, group by station+dir+day_record to sum lanes
        day_col = 'day_record' if 'day_record' in df.columns else 'day_of_week'
        group_cols = ['station_id', 'state_code', 'travel_dir', day_col]
        lane_summed = df.groupby(group_cols, as_index=False)[hour_cols].sum()

        # Step 3: Average across weekdays per (station, direction, hour)
        dir_avg = lane_summed.groupby(
            ['station_id', 'state_code', 'travel_dir'], as_index=False
        )[hour_cols].mean()

        # Count weekdays per (station, direction) for metadata
        weekday_counts = lane_summed.groupby(
            ['station_id', 'travel_dir'], as_index=False
        )[day_col].nunique()
        weekday_counts.columns = ['station_id', 'travel_dir', 'num_weekdays_averaged']

        # Rename hour_00..hour_23 -> h01..h24 (no opposite-direction sum)
        rename_map = {f'hour_{i:02d}': f'h{i+1:02d}' for i in range(24)}
        bidir = dir_avg.rename(columns=rename_map)

        # Merge weekday counts per (station, direction)
        bidir = bidir.merge(weekday_counts, on=['station_id', 'travel_dir'], how='left')

        return bidir

    def _load_to_db(self, stations_df: pd.DataFrame, volumes_df: pd.DataFrame):
        """Load stations and volumes to the database."""
        # Build station records (PK includes travel_dir: one row per direction)
        station_records = []
        for _, row in stations_df.iterrows():
            travel_dir = int(row['travel_dir'])
            pk = f"{row['state_code']}_{row['station_id']}_{travel_dir}"
            station_records.append({
                'id': pk,
                'state_code': str(row['state_code']),
                'station_id': str(row['station_id']),
                'travel_dir': travel_dir,
                'lat': float(row['lat']),
                'lon': float(row['lon']),
                'county_code': str(row['county_code']),
                'f_system': str(row.get('f_system', '')),
                'station_location': str(row.get('station_location', '')),
                'year': int(row['year']),
            })

        # Build volume records (PK includes travel_dir: one row per direction)
        hour_cols = [f'h{i:02d}' for i in range(1, 25)]
        volume_records = []
        for _, row in volumes_df.iterrows():
            travel_dir = int(row['travel_dir'])
            pk = f"{row['state_code']}_{row['station_id']}_{travel_dir}"
            rec = {
                'id': pk,
                'station_pk': pk,
                'state_code': str(row['state_code']),
                'station_id': str(row['station_id']),
                'travel_dir': travel_dir,
                'num_weekdays_averaged': int(row.get('num_weekdays_averaged', 0)),
            }
            for hcol in hour_cols:
                rec[hcol] = float(row[hcol]) if pd.notna(row.get(hcol)) else 0.0
            volume_records.append(rec)

        # Insert to DB
        if station_records:
            self.db_manager.insert_records(FHAStation, station_records)
        if volume_records:
            self.db_manager.insert_records(FHAHourlyVolume, volume_records)

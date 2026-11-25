# SPDX-License-Identifier: GPL-3.0-or-later
"""FHA stations are kept by location, and the DB reloads for a new region (item 7).

States mis-code the TMAS county_code (often '000'): the code filter kept 10
of 59 Madison station-directions. The station location decides now. The DB
holds one region per state, so a marker file records what was loaded and a
run for other counties / year / month reloads.
"""

import pandas as pd
import pytest
from shapely.geometry import box

import utils.region_utils as ru
from data_sources.fha_counts_manager import FHACountsManager


def _manager(tmp_path, counties=('27003',), year=2024, month=10):
    cfg = {'region': {'counties': list(counties)}, 'data': {'data_dir': str(tmp_path)},
           'counts': {'fha': {'data_dir': str(tmp_path), 'year': year, 'month': month}}}
    return FHACountsManager(cfg, db_manager=None)


@pytest.mark.smoke
def test_station_kept_by_location_not_county_code(tmp_path, monkeypatch):
    # County 27003 = the box lon -94..-93, lat 45..46
    monkeypatch.setattr(ru, 'load_county_polygons',
                        lambda geoids, data_dir, utm_epsg=None: [box(-94, 45, -93, 46)])
    df = pd.DataFrame({
        'station_id': ['in_miscoded', 'in_coded', 'out_coded'],
        'county_code': ['000', '003', '003'],
        'lat': [45.5, 45.2, 47.0],
        'lon': [-93.5, -93.2, -93.5],
    })
    kept = _manager(tmp_path)._filter_to_region(df, '27', {'003'})
    assert sorted(kept['station_id']) == ['in_coded', 'in_miscoded']


@pytest.mark.smoke
def test_without_polygons_falls_back_to_county_code(tmp_path, monkeypatch):
    monkeypatch.setattr(ru, 'load_county_polygons', lambda *a, **k: [])
    df = pd.DataFrame({'station_id': ['a', 'b'], 'county_code': ['003', '000'],
                       'lat': [45.5, 45.5], 'lon': [-93.5, -93.5]})
    kept = _manager(tmp_path)._filter_to_region(df, '27', {'003'})
    assert list(kept['station_id']) == ['a']


@pytest.mark.smoke
def test_marker_forces_reload_for_other_region_or_month(tmp_path):
    anoka = _manager(tmp_path, counties=('27003',))
    anoka._write_region_marker()
    assert anoka._read_region_marker()['27'] == {'counties': ['003'], 'year': 2024, 'month': 10}

    class DB:
        def query_all(self, model, filters=None):
            return [object()]

    anoka.db_manager = DB()
    assert anoka.has_data_for_region()

    tc = _manager(tmp_path, counties=('27003', '27053'))
    tc.db_manager = DB()
    assert not tc.has_data_for_region()      # other counties in the same state

    july = _manager(tmp_path, counties=('27003',), month=7)
    july.db_manager = DB()
    assert not july.has_data_for_region()    # other month


@pytest.mark.smoke
def test_missing_zips_keep_existing_rows(tmp_path):
    """No zips on this machine: keep the DB rows; never clear them first."""
    cleared = []

    class DB:
        db_path = str(tmp_path / 'db' / 'x.duckdb')

        def get_table_columns(self, table):
            return ['travel_dir']

        def query_all(self, model, filters=None):
            return [object()]

        def delete_records(self, model, filters=None):
            cleared.append(filters)

    m = _manager(tmp_path / 'fha_zips_absent')
    m.db_manager = DB()
    assert m.setup() is True            # marker missing, zips missing -> keep rows
    assert cleared == []
    assert m.setup(rebuild=True) is False   # a rebuild cannot run without zips
    assert cleared == []
    assert m._region_marker_path().name == 'x.fha_region.json'

"""Smoke tests for four general fixes found on the Chicago region (2026-09-29).

  - counts: a freeway count is split over parallel roadways of its direction
    (local + express lanes), and only there;
  - GTFS: tables with a space after each comma (``stop_id, stop_lat``) load;
  - GTFS: a catalog feed without a bounding box, in a state of the region,
    gets its bounding box from its stops;
  - DuckDB: a write engine can run with a fixed number of threads.

Tiny synthetic inputs only (no network download, no Java).
"""

import pandas as pd
import pytest

from matsim.counts_generator import HOUR_COLS_UPPER
from tests.smoke.test_fha_perdirection import _load_links, _make_generator, _station_rows


# ---------------------------------------------------------------------------
# Parallel roadways
# ---------------------------------------------------------------------------

def _local_and_express():
    """Northbound and southbound local (6000) and express (8000) roadways.

    The station sits on the northbound local roadway at (527, 500). The
    express roadways are 33 m further east.
    """
    rows = []
    for lid, x, y0, y1, cap in [
        ('locN', 527, 400, 600, 6000.0), ('locS', 517, 600, 400, 6000.0),
        ('expN', 560, 400, 600, 8000.0), ('expS', 570, 600, 400, 8000.0),
    ]:
        rows.append({'link_id': lid, 'from_node': f'{lid}_a', 'to_node': f'{lid}_b',
                     'from_x': x, 'from_y': y0, 'to_x': x, 'to_y': y1,
                     'capacity': cap, 'freespeed': 26.8})
    return pd.DataFrame(rows)


def _wire(g, links):
    _load_links(g, links)
    g._link_nodes = {r['link_id']: (r['from_node'], r['to_node']) for _, r in links.iterrows()}
    g._link_modes = {r['link_id']: {'car'} for _, r in links.iterrows()}


def _stations_at(base, dirs_and_vols, f_system, x=527, y=500):
    volumes, stations = _station_rows(base, dirs_and_vols, f_system=f_system)
    stations['utm_x'] = x
    stations['utm_y'] = y
    return volumes, stations


@pytest.mark.smoke
def test_freeway_count_split_over_parallel_roadways_by_capacity():
    g = _make_generator()
    _wire(g, _local_and_express())
    volumes, stations = _stations_at('FHA_17_000001', [(1, 1000), (5, 900)], '1U')
    out = g.match_fha_directional_to_links(volumes, stations).set_index('LOCAL_ID')

    assert set(out.index) == {'FHA_17_000001_1', 'FHA_17_000001-p2_1',
                              'FHA_17_000001_5', 'FHA_17_000001-p2_5'}
    assert out.loc['FHA_17_000001_1', 'matched_link_id'] == 'locN'
    assert out.loc['FHA_17_000001-p2_1', 'matched_link_id'] == 'expN'
    # Split by capacity, and the direction total is kept.
    assert out.loc['FHA_17_000001_1', 'H08'] == pytest.approx(1000 * 6 / 14)
    assert out.loc['FHA_17_000001-p2_1', 'H08'] == pytest.approx(1000 * 8 / 14)
    north = out.loc[['FHA_17_000001_1', 'FHA_17_000001-p2_1'], HOUR_COLS_UPPER].sum()
    assert north.sum() == pytest.approx(1000 * 24)


@pytest.mark.smoke
def test_arterial_count_is_not_split():
    g = _make_generator()
    _wire(g, _local_and_express())
    volumes, stations = _stations_at('FHA_17_000002', [(1, 1000), (5, 900)], '3U')
    out = g.match_fha_directional_to_links(volumes, stations)
    assert len(out) == 2
    assert not out['LOCAL_ID'].str.contains('-p').any()


@pytest.mark.smoke
def test_next_link_of_same_roadway_is_not_a_parallel_roadway():
    """Collinear links ahead of the matched link are not parallel roadways,
    even when they are not connected to it directly."""
    links = pd.DataFrame([
        {'link_id': 'n1', 'from_node': 'a', 'to_node': 'b', 'from_x': 527, 'from_y': 480,
         'to_x': 527, 'to_y': 520, 'capacity': 6000.0, 'freespeed': 26.8},
        {'link_id': 'n2', 'from_node': 'b', 'to_node': 'c', 'from_x': 527, 'from_y': 520,
         'to_x': 527, 'to_y': 540, 'capacity': 6000.0, 'freespeed': 26.8},
        {'link_id': 'n3', 'from_node': 'c', 'to_node': 'd', 'from_x': 527, 'from_y': 540,
         'to_x': 527, 'to_y': 600, 'capacity': 6000.0, 'freespeed': 26.8},
        {'link_id': 's1', 'from_node': 'b', 'to_node': 'a', 'from_x': 527, 'from_y': 520,
         'to_x': 527, 'to_y': 480, 'capacity': 6000.0, 'freespeed': 26.8},
    ])
    g = _make_generator()
    _wire(g, links)
    volumes, stations = _stations_at('FHA_17_000003', [(1, 1000), (5, 900)], '1U')
    out = g.match_fha_directional_to_links(volumes, stations)
    assert not out['LOCAL_ID'].str.contains('-p').any()


@pytest.mark.smoke
def test_parallel_roadway_matched_by_another_station_is_not_used():
    g = _make_generator()
    _wire(g, _local_and_express())
    matched = pd.DataFrame([
        dict({h: 600.0 for h in HOUR_COLS_UPPER}, LOCAL_ID='FHA_17_000004_1',
             matched_link_id='locN', f_system='1U', utm_x=527, utm_y=500),
        dict({h: 800.0 for h in HOUR_COLS_UPPER}, LOCAL_ID='FHA_17_000005_1',
             matched_link_id='expN', f_system='1U', utm_x=560, utm_y=500),
    ])
    out = g.split_parallel_roadways(matched)
    assert list(out['LOCAL_ID']) == ['FHA_17_000004_1', 'FHA_17_000005_1']
    assert out['H01'].tolist() == [600.0, 800.0]


# ---------------------------------------------------------------------------
# GTFS tables with a space after each comma
# ---------------------------------------------------------------------------

SPACED_STOPS = ("stop_id, stop_name, stop_desc, stop_lat, stop_lon\n"
                "GENEVA, Geneva, ,41.8816667,-88.3100000\n"
                "OTC, Ogilvie, ,41.8830,-87.6400\n")


@pytest.mark.smoke
def test_read_gtfs_csv_strips_spaces(tmp_path):
    from data_sources.gtfs_manager import read_gtfs_csv
    p = tmp_path / 'stops.txt'
    p.write_text(SPACED_STOPS)
    df = read_gtfs_csv(p)
    assert list(df.columns) == ['stop_id', 'stop_name', 'stop_desc', 'stop_lat', 'stop_lon']
    assert df['stop_name'].tolist() == ['Geneva', 'Ogilvie']
    chunks = list(read_gtfs_csv(p, chunksize=1, usecols=['stop_id', 'stop_lat']))
    assert [list(c.columns) for c in chunks] == [['stop_id', 'stop_lat']] * 2


@pytest.mark.smoke
def test_network_filter_reads_spaced_gtfs(tmp_path):
    from matsim.network_generator import _copy_gtfs_table_clean, _read_gtfs_rows
    p = tmp_path / 'stops.txt'
    p.write_text(SPACED_STOPS)
    rows, fields = _read_gtfs_rows(p)
    assert fields[3:] == ['stop_lat', 'stop_lon']
    assert rows[0]['stop_lat'] == '41.8816667'
    out = tmp_path / 'clean.txt'
    _copy_gtfs_table_clean(p, out)
    assert out.read_text().splitlines()[0] == 'stop_id,stop_name,stop_desc,stop_lat,stop_lon'

    # A byte that is not UTF-8 (Windows-1252 quote) passes through unchanged.
    raw = tmp_path / 'notes.txt'
    raw.write_bytes(b'id, note\r\n1, \x93quoted\x94\r\n')
    _copy_gtfs_table_clean(raw, out)
    assert out.read_bytes() == b'id,note\r\n1,\x93quoted\x94\r\n'


# ---------------------------------------------------------------------------
# Catalog feed without a bounding box
# ---------------------------------------------------------------------------

CATALOG_COLS = ['id', 'data_type', 'location.country_code', 'status', 'provider',
                'urls.direct_download', 'location.subdivision_name', 'location.municipality',
                'location.bounding_box.minimum_latitude', 'location.bounding_box.maximum_latitude',
                'location.bounding_box.minimum_longitude', 'location.bounding_box.maximum_longitude']


@pytest.mark.smoke
def test_feed_without_catalog_bbox_uses_its_stops(tmp_path, monkeypatch):
    from data_sources.gtfs_manager import BBox, GTFSManager
    rows = [
        ['mdb-1', 'gtfs', 'US', 'active', 'Metra', 'http://x/metra.zip', 'Illinois', 'Chicago',
         '', '', '', ''],
        ['mdb-2', 'gtfs', 'US', 'active', 'Far Away', 'http://x/far.zip', 'California', 'LA',
         '', '', '', ''],
    ]
    pd.DataFrame(rows, columns=CATALOG_COLS).to_csv(tmp_path / 'feeds_v2.csv', index=False)
    m = GTFSManager({'gtfs': {'cache_dir': str(tmp_path)}}, db_manager=None)
    m._region_states = {'illinois'}

    downloaded = []

    def fake_download(feed):
        downloaded.append(feed.feed_id)
        d = tmp_path / feed.feed_id
        d.mkdir(exist_ok=True)
        (d / 'stops.txt').write_text(SPACED_STOPS)
        return d

    monkeypatch.setattr(m, 'download_feed', fake_download)
    region = BBox(min_lat=41.4, max_lat=42.2, min_lon=-88.3, max_lon=-87.5)
    feeds = m.discover_feeds(region)

    assert [f.feed_id for f in feeds] == ['mdb-1']
    assert downloaded == ['mdb-1']  # the feed of another state is not downloaded
    assert feeds[0].bbox.min_lon == pytest.approx(-88.31, abs=0.01)


# ---------------------------------------------------------------------------
# DuckDB threads
# ---------------------------------------------------------------------------

@pytest.mark.smoke
def test_write_engine_threads(tmp_path):
    from sqlalchemy import text
    from utils.duckdb_manager import DBManager
    db = DBManager.__new__(DBManager)
    db.db_path = str(tmp_path / 't.duckdb')
    engine = db._make_engine(read_only=False, threads=1)
    try:
        with engine.connect() as c:
            assert int(c.execute(text("SELECT current_setting('threads')")).scalar()) == 1
    finally:
        engine.dispose()

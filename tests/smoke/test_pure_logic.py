# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke tests for small, pure pieces of modeling logic.

These need realistic-but-tiny inputs (drawn from the smoke fixture config where
a config is required), not full DB/survey data. They guard the math/contract of
helpers that the pipeline leans on heavily.
"""

import json

import pytest

from models.mode_availability import haversine_meters
from utils.poi_weighting import POIWeighting


# ---------------------------------------------------------------------------
# haversine_meters
# ---------------------------------------------------------------------------

@pytest.mark.smoke
def test_haversine_zero_distance():
    assert haversine_meters(44.9778, -93.2650, 44.9778, -93.2650) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.smoke
def test_haversine_known_distance():
    """Minneapolis <-> St. Paul city centers are ~13-15 km apart."""
    d = haversine_meters(44.9778, -93.2650, 44.9537, -93.0900)
    assert 12_000 < d < 16_000


@pytest.mark.smoke
def test_haversine_symmetric():
    a = haversine_meters(44.9778, -93.2650, 44.9537, -93.0900)
    b = haversine_meters(44.9537, -93.0900, 44.9778, -93.2650)
    assert a == pytest.approx(b, rel=1e-9)


# ---------------------------------------------------------------------------
# POIWeighting (uses the Shopping purpose config from the smoke fixture)
# ---------------------------------------------------------------------------

@pytest.fixture
def smoke_config(smoke_config_path):
    return json.loads(smoke_config_path.read_text(encoding="utf-8"))


@pytest.mark.smoke
def test_poi_weighting_disabled_returns_one(smoke_config):
    """A purpose without poi_weighting config should yield uniform weight 1.0."""
    # 'Work' is not a nonwork purpose, so no weighting config -> disabled.
    w = POIWeighting(smoke_config, purpose="Work")
    assert w.is_enabled() is False
    assert w.calculate_weight({"name": "Anything", "tags": None}) == 1.0


@pytest.mark.smoke
def test_poi_weighting_brand_and_shop_type(smoke_config):
    """A named supermarket brand should score above an unnamed plain POI."""
    w = POIWeighting(smoke_config, purpose="Shopping")
    assert w.is_enabled() is True

    target_supermarket = {
        "osm_id": "1",
        "name": "Target Store",
        "tags": json.dumps({"shop": "supermarket"}),
    }
    plain_unnamed = {
        "osm_id": "2",
        "name": "",
        "tags": json.dumps({"shop": "convenience"}),
    }

    high = w.calculate_weight(target_supermarket)
    low = w.calculate_weight(plain_unnamed)

    # Shopping config: has_name=1.5, Target=3.0, shop_type supermarket=2.5
    # => 1.5 * 3.0 * 2.5 = 11.25
    assert high == pytest.approx(1.5 * 3.0 * 2.5, rel=1e-6)
    assert high > low
    assert low >= 1.0


@pytest.mark.smoke
def test_poi_weighting_handles_bad_tags_json(smoke_config):
    """Malformed tags JSON must not crash; falls back to no tag bonus."""
    w = POIWeighting(smoke_config, purpose="Shopping")
    poi = {"osm_id": "3", "name": "", "tags": "{not valid json"}
    # Should not raise; with no name and unparseable tags, weight stays 1.0.
    assert w.calculate_weight(poi) == pytest.approx(1.0, rel=1e-6)

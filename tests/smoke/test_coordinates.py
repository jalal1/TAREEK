# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke tests for utils.coordinates: pure, deterministic coordinate logic.

Known-good values lifted from the module's own __main__ self-test block
(Minneapolis, EPSG:26915 / UTM zone 15N).
"""

import pytest

from utils.coordinates import (
    detect_utm_epsg,
    CoordinateConverter,
)

MINNEAPOLIS_LAT = 44.9778
MINNEAPOLIS_LON = -93.2650


@pytest.mark.smoke
def test_detect_utm_epsg_minneapolis():
    assert detect_utm_epsg(MINNEAPOLIS_LAT, MINNEAPOLIS_LON) == "EPSG:26915"


@pytest.mark.smoke
@pytest.mark.parametrize(
    "lat,lon,expected",
    [
        (34.05, -118.24, "EPSG:26911"),   # Los Angeles, zone 11
        (40.71, -74.01, "EPSG:26918"),    # New York, zone 18
        (38.90, -77.04, "EPSG:26918"),    # Washington DC, zone 18
        (33.52, -86.81, "EPSG:26916"),    # Birmingham AL, zone 16
    ],
)
def test_detect_utm_epsg_known_cities(lat, lon, expected):
    assert detect_utm_epsg(lat, lon) == expected


@pytest.mark.smoke
def test_detect_utm_epsg_outside_us_raises():
    # London ~ zone 30, well outside the supported US 10-19 range.
    with pytest.raises(ValueError):
        detect_utm_epsg(51.5, -0.12)


@pytest.mark.smoke
def test_latlon_utm_round_trip():
    """lat/lon -> UTM -> lat/lon should return the original within ~1e-4 deg."""
    conv = CoordinateConverter("EPSG:26915")
    x, y = conv.latlon_to_utm(MINNEAPOLIS_LAT, MINNEAPOLIS_LON)

    # UTM easting/northing should be in a sane range for zone 15N.
    assert 400_000 < x < 600_000
    assert 4_900_000 < y < 5_100_000

    lat, lon = conv.utm_to_latlon(x, y)
    assert lat == pytest.approx(MINNEAPOLIS_LAT, abs=1e-4)
    assert lon == pytest.approx(MINNEAPOLIS_LON, abs=1e-4)


@pytest.mark.smoke
def test_batch_matches_scalar():
    conv = CoordinateConverter("EPSG:26915")
    coords = [(44.9778, -93.2650), (44.9537, -93.0900)]
    batch = conv.batch_latlon_to_utm(coords)
    assert len(batch) == 2
    for (lat, lon), (bx, by) in zip(coords, batch):
        sx, sy = conv.latlon_to_utm(lat, lon)
        assert bx == pytest.approx(sx, abs=1e-6)
        assert by == pytest.approx(sy, abs=1e-6)


@pytest.mark.smoke
def test_batch_empty_returns_empty():
    conv = CoordinateConverter("EPSG:26915")
    assert conv.batch_latlon_to_utm([]) == []

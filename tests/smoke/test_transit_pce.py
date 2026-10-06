"""Transit vehicle PCE is scaled to the sample size, once."""

import json
import re

import pytest

from matsim.transit_pce import MARKER_NAME, scale_transit_pce

VEHICLES = """<?xml version="1.0" encoding="UTF-8"?>

<vehicleDefinitions xmlns="http://www.matsim.org/files/dtd">

\t<vehicleType id="Bus">
\t\t<capacity seats="70" standingRoomInPersons="0">

\t\t</capacity>
\t\t<length meter="18.0"/>
\t\t<passengerCarEquivalents pce="2.8"/>
\t\t<networkMode networkMode="bus"/>
\t</vehicleType>

\t<vehicleType id="Rail">
\t\t<length meter="200.0"/>
\t\t<passengerCarEquivalents pce="27.1"/>
\t\t<networkMode networkMode="rail"/>
\t</vehicleType>

\t<vehicle id="veh_0_bus" type="Bus"/>
\t<vehicle id="veh_1_rail" type="Rail"/>
</vehicleDefinitions>
"""


def _pces(path):
    return [float(x) for x in re.findall(r'pce="([^"]+)"', path.read_text())]


@pytest.mark.smoke
def test_scales_once_and_is_idempotent(tmp_path):
    vehicles = tmp_path / 'transitVehicles.xml'
    vehicles.write_text(VEHICLES)

    result = scale_transit_pce(vehicles, 0.1)
    assert result == {'Bus': {'original': 2.8, 'scaled': 0.28},
                      'Rail': {'original': 27.1, 'scaled': 2.71}}
    assert _pces(vehicles) == [0.28, 2.71]
    after_first = vehicles.read_text()

    # A rerun in the same folder (plan reuse) must not scale again.
    scale_transit_pce(vehicles, 0.1)
    assert vehicles.read_text() == after_first

    marker = json.loads((tmp_path / MARKER_NAME).read_text())
    assert marker['types']['Bus'] == {'original': 2.8, 'scaled': 0.28}

    # Everything except the PCE values is left as it was.
    assert after_first == VEHICLES.replace('"2.8"', '"0.28"').replace('"27.1"', '"2.71"')


@pytest.mark.smoke
def test_new_factor_rescales_from_original(tmp_path):
    vehicles = tmp_path / 'transitVehicles.xml'
    vehicles.write_text(VEHICLES)
    scale_transit_pce(vehicles, 0.1)
    scale_transit_pce(vehicles, 0.2)
    assert _pces(vehicles) == [0.56, 5.42]


@pytest.mark.smoke
def test_fresh_copy_with_old_marker_is_scaled(tmp_path):
    # The marker survives but the file is replaced with an unscaled copy
    # (e.g. rebuild_network): the full-size values are the new originals.
    vehicles = tmp_path / 'transitVehicles.xml'
    vehicles.write_text(VEHICLES)
    scale_transit_pce(vehicles, 0.1)
    vehicles.write_text(VEHICLES)
    scale_transit_pce(vehicles, 0.1)
    assert _pces(vehicles) == [0.28, 2.71]


# What ElementTree writes back when network_generator patches the file.
VEHICLES_NS0 = """<?xml version='1.0' encoding='UTF-8'?>
<ns0:vehicleDefinitions xmlns:ns0="http://www.matsim.org/files/dtd">
    <ns0:vehicleType id="Bus">
        <ns0:length meter="18.0" />
        <ns0:passengerCarEquivalents pce="2.8" />
        <ns0:networkMode networkMode="bus" />
    </ns0:vehicleType>
    <ns0:vehicleType id="Subway">
        <ns0:passengerCarEquivalents pce="4.4" />
    </ns0:vehicleType>
    <ns0:vehicle id="veh_0_bus" type="Bus" />
</ns0:vehicleDefinitions>
"""


@pytest.mark.smoke
def test_namespace_prefixed_file(tmp_path):
    vehicles = tmp_path / 'transitVehicles.xml'
    vehicles.write_text(VEHICLES_NS0)
    scale_transit_pce(vehicles, 0.1)
    assert _pces(vehicles) == [0.28, 0.44]
    assert '<ns0:passengerCarEquivalents pce="0.28" />' in vehicles.read_text()

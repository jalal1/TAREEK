# SPDX-License-Identifier: GPL-3.0-or-later
"""Car passengers (ride) and school buses (todo item 1).

Surveys count a car passenger as a car trip. The model drove every one of
them, so the plans had about 1.3x the survey's car vehicle trips (School
about 5x). Now the loaders split car trips into Car (driver) and Ride
(passenger), mode choice uses trip-weighted shares, and MATSim teleports
ride and school_bus legs, so they put no vehicle on the network.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data_sources.base_survey_trip import BaseSurveyTrip as B
from data_sources.nhts_survey_trip import NHTSSurveyTrip
from data_sources.tbi_survey import TBISurveyTrip
from models.mode_choice import ModeChoiceModel
from models.mode_types import (ModeType, NHTS_2022_DRIVER_SHARE, effective_modes_config,
                               is_mode_enabled)

REPO = Path(__file__).resolve().parents[2]


# ── Loaders ──────────────────────────────────────────────────────────────

def _nhts_trip_csv(path: Path):
    rows = []
    # (TRPTRANS, DRVR_FLG): car driver, car passenger, car unknown, walk, school bus
    for i, (mode, drv) in enumerate([(3, 1), (3, 2), (1, -9), (20, -1), (9, -1)], start=1):
        rows.append({'HOUSEID': 1, 'PERSONID': i, 'TRIPID': 1, 'TRPTRANS': mode,
                     'WHYTO': 3, 'WHYFROM': 1, 'WHYTRP1S': 10, 'STRTTIME': 800,
                     'ENDTIME': 820, 'TRVLCMIN': 20, 'TRPMILES': 5.0, 'WTTRDFIN': 100.0,
                     'TDAYDATE': 202210, 'TRAVDAY': 3, 'DRVR_FLG': drv})
    pd.DataFrame(rows).to_csv(path, index=False)


@pytest.mark.smoke
def test_nhts_loader_splits_car_by_drvr_flg(tmp_path):
    _nhts_trip_csv(tmp_path / 'trips.csv')
    cfg = {'data': {'data_dir': str(tmp_path),
                    'surveys': [{'type': 'nhts', 'year': '2022', 'file': 'trips.csv'}]}}
    src = NHTSSurveyTrip(cfg)
    df = src.extract_data('2022', 'trips.csv').set_index(B.PERSON_ID)
    assert df.loc['1_1', B.MODE_TYPE] == B.MODE_CAR      # DRVR_FLG 1
    assert df.loc['1_2', B.MODE_TYPE] == B.MODE_RIDE     # DRVR_FLG 2
    assert df.loc['1_3', B.MODE_TYPE] == B.MODE_CAR      # not ascertained -> driver
    assert df.loc['1_4', B.MODE_TYPE] == B.MODE_WALK
    assert df.loc['1_5', B.MODE_TYPE] == B.MODE_SCHOOL_BUS
    assert NHTSSurveyTrip.LOADER_VERSION >= 2


@pytest.mark.smoke
def test_tbi_passenger_mask_uses_driver_field_and_age(tmp_path):
    pd.DataFrame({'person_id': ['a', 'k', 'z'],
                  'age': ['35 to 44', '5 to 15', '25 to 34']}).to_csv(tmp_path / 'per.csv', index=False)
    cfg = {'data': {'data_dir': str(tmp_path), 'surveys': [
        {'type': 'tbi', 'year': '2023', 'person_file': 'per.csv'}]}}
    src = TBISurveyTrip(cfg)
    src.metadata['source_year'] = '2023'
    df = pd.DataFrame({
        'person_id': ['a', 'a', 'a', 'k', 'k', 'z'],
        'mode_type': ['Household Vehicle', 'Household Vehicle', 'Other Vehicle',
                      'Household Vehicle', 'Walk', 'Household Vehicle'],
        'driver': ['Driver', 'Passenger', 'Missing', 'Missing', 'Missing',
                   'Both (switched drivers during trip)'],
    })
    mask = src._passenger_mask(df).tolist()
    # driver, passenger, empty+adult -> driver, empty+child -> passenger,
    # walk -> never, both -> driver
    assert mask == [False, True, False, True, False, False]


@pytest.mark.smoke
def test_tbi_without_driver_column_keeps_every_vehicle_trip_as_driver(tmp_path):
    src = TBISurveyTrip({'data': {'data_dir': str(tmp_path), 'surveys': []}})
    df = pd.DataFrame({'person_id': ['a'], 'mode_type': ['Household Vehicle']})
    assert not src._passenger_mask(df).any()


# ── Mode choice ──────────────────────────────────────────────────────────

def _survey(modes, weights, purpose='Work'):
    return pd.DataFrame({'mode_type': modes, 'destination_purpose': purpose,
                         'trip_weight': weights})


def _model(survey, modes_cfg=None, mode_choice=None):
    cfg = {'modes': modes_cfg or {'car': {'matsim_mode': 'car', 'availability': 'universal'}},
           'mode_choice': {'min_samples_per_purpose': 1, **(mode_choice or {})},
           'plan_generation': {'random_seed': 7}}
    return ModeChoiceModel(cfg, survey_data={'s': survey}, survey_weights={'s': 1.0})


@pytest.mark.smoke
def test_ride_and_school_bus_are_on_by_default_and_can_be_switched_off():
    assert is_mode_enabled({}, 'ride') and is_mode_enabled({}, 'school_bus')
    modes = effective_modes_config({'modes': {'ride': {'enabled': False}}})
    assert modes['ride']['enabled'] is False and modes['ride']['matsim_mode'] == 'ride'
    m = _model(_survey(['Car'] * 40, [1.0] * 40))
    assert ModeType.RIDE in m.mode_configs and ModeType.SCHOOL_BUS in m.mode_configs
    assert m.get_output_mode(ModeType.RIDE) == 'ride'
    assert m.get_output_mode(ModeType.SCHOOL_BUS) == 'school_bus'


@pytest.mark.smoke
def test_mode_shares_are_trip_weighted():
    # 30 car trips of weight 1, 10 ride trips of weight 9: weighted ride share 0.75
    s = _survey(['Car'] * 30 + ['Ride'] * 10, [1.0] * 30 + [9.0] * 10)
    rates = _model(s).survey_rates['Work']
    assert rates[ModeType.RIDE] == pytest.approx(0.75)
    rates = _model(s, mode_choice={'weighted_shares': False}).survey_rates['Work']
    assert rates[ModeType.RIDE] == pytest.approx(0.25)


@pytest.mark.smoke
def test_ride_disabled_counts_passengers_as_car():
    s = _survey(['Car'] * 30 + ['Ride'] * 10, [1.0] * 40)
    rates = _model(s, modes_cfg={'car': {'matsim_mode': 'car'},
                                 'ride': {'enabled': False}}).survey_rates['Work']
    assert ModeType.RIDE not in rates
    assert rates[ModeType.CAR] == pytest.approx(1.0)


@pytest.mark.smoke
def test_source_without_driver_field_is_split_with_nhts_shares():
    s = _survey(['Car'] * 40, [1.0] * 40, purpose='School')
    rates = _model(s).survey_rates['School']
    d = NHTS_2022_DRIVER_SHARE['School']
    assert rates[ModeType.CAR] == pytest.approx(d)
    assert rates[ModeType.RIDE] == pytest.approx(1 - d)


@pytest.mark.smoke
def test_ride_chain_needs_no_car_and_is_repeatable():
    from models.mode_availability import Location
    from types import SimpleNamespace
    s = _survey(['Car'] * 20 + ['Ride'] * 20, [1.0] * 40)
    acts = [SimpleNamespace(type=t) for t in ('Home', 'Work', 'Home')]
    locs = [Location(lat=45.0, lon=-93.0), Location(lat=45.05, lon=-93.0),
            Location(lat=45.0, lon=-93.0)]
    runs = []
    for _ in range(2):
        m = _model(s)
        rng = np.random.default_rng(3)
        runs.append([tuple(m.choose_modes_for_chain(acts, locs, rng)) for _ in range(50)])
    assert runs[0] == runs[1]
    chains = set(runs[0])
    assert (ModeType.RIDE, ModeType.RIDE) in chains          # whole chain as passenger
    assert all(len(set(c)) == 1 for c in chains)              # chain consistency


# ── MATSim config ────────────────────────────────────────────────────────

def _teleport_tree(config):
    from matsim.config_manager import ConfigManager
    tree = ET.parse(REPO / 'matsim' / 'configs' / 'basic' / 'config.xml')
    cm = ConfigManager(config)
    cm.configure_teleported_modes(tree)
    return tree


def _routing(tree):
    root = tree.getroot()
    mod = next((m for m in root.findall('module') if m.get('name') == 'routing'), None)
    if mod is None:
        return None, {}
    sets = {}
    for ps in mod.findall("parameterset[@type='teleportedModeParameters']"):
        sets[ps.find("param[@name='mode']").get('value')] = {
            p.get('name'): p.get('value') for p in ps.findall('param')}
    return mod, sets


@pytest.mark.smoke
def test_matsim_config_teleports_ride_and_school_bus():
    tree = _teleport_tree({'modes': {'car': {'matsim_mode': 'car'}}})
    mod, sets = _routing(tree)
    assert mod is not None
    params = {p.get('name'): p.get('value') for p in mod.findall('param')}
    assert params['clearDefaultTeleportedModeParams'] == 'true'
    # MATSim defaults are kept explicitly
    assert {'bike', 'walk', 'non_network_walk', 'pt'} <= set(sets)
    assert float(sets['ride']['teleportedModeFreespeedFactor']) == pytest.approx(1.0)
    assert float(sets['school_bus']['teleportedModeSpeed']) == pytest.approx(16.6 / 3.6)
    assert float(sets['school_bus']['beelineDistanceFactor']) == pytest.approx(1.3)
    # not network modes, not switchable in replanning, but scored
    root = tree.getroot()
    for m in root.findall('module'):
        for p in m.findall('param'):
            if p.get('name') == 'networkModes':
                assert 'ride' not in p.get('value')
    smc = next(m for m in root.findall('module') if m.get('name') == 'subtourModeChoice')
    smc_modes = smc.find("param[@name='modes']").get('value').split(',')
    assert 'ride' not in smc_modes and 'school_bus' not in smc_modes
    scored = {p.find("param[@name='mode']").get('value')
              for p in root.iter('parameterset') if p.get('type') == 'modeParams'}
    assert {'ride', 'school_bus'} <= scored


@pytest.mark.smoke
def test_matsim_config_has_no_routing_block_when_both_modes_are_off():
    tree = _teleport_tree({'modes': {'car': {'matsim_mode': 'car'},
                                     'ride': {'enabled': False},
                                     'school_bus': {'enabled': False}}})
    mod, _ = _routing(tree)
    assert mod is None


@pytest.mark.smoke
def test_teleport_values_can_be_set_in_the_config():
    tree = _teleport_tree({'modes': {'school_bus': {'teleport': {'freespeed_factor': 2.0}}}})
    _, sets = _routing(tree)
    assert 'teleportedModeSpeed' not in sets['school_bus']
    assert float(sets['school_bus']['teleportedModeFreespeedFactor']) == pytest.approx(2.0)


# ── Survey re-ingest on a loader version change ─────────────────────────

@pytest.mark.smoke
def test_loader_version_change_reloads_the_survey_rows(tmp_path, monkeypatch):
    from data_sources import survey_manager as sm

    class FakeSurvey(B):
        LOADER_VERSION = 1

        def __init__(self, config):
            super().__init__(config)
            self.metadata = {'source_type': 'fake'}

        def extract_data(self, year, file_path=None):
            self.data = pd.DataFrame({
                B.PERSON_ID: ['p1'], B.MODE_TYPE: [f'v{FakeSurvey.LOADER_VERSION}'],
                B.ORIGIN_LOC: [None], B.DESTINATION_LOC: [None],
                B.ORIGIN_PURPOSE: ['Home'], B.DESTINATION_PURPOSE: ['Work'],
                B.DEPART_TIME: [pd.Timestamp('2022-01-03 08:00')],
                B.ARRIVE_TIME: [pd.Timestamp('2022-01-03 08:20')],
                B.DURATION: [1200.0], B.DISTANCE: [3.0], B.TRIP_WEIGHT: [1.0],
                B.SOURCE_TYPE: ['fake'], B.SOURCE_YEAR: ['1']})
            return self.data

        def clean_data(self):
            pass

    monkeypatch.setattr(sm.SurveyManager, 'SURVEY_REGISTRY', {'fake': FakeSurvey})
    config = {'data': {'data_dir': str(tmp_path),
                       'surveys': [{'type': 'fake', 'year': '1', 'weight': 1}]}}

    def modes_in_db():
        src = FakeSurvey(config)
        src.metadata['source_year'] = '1'
        return sorted(src.load_data()[B.MODE_TYPE])

    sm.ensure_surveys(config)
    assert modes_in_db() == ['v1']
    sm.ensure_surveys(config)                  # same version: no reload, no duplicate
    assert modes_in_db() == ['v1']
    FakeSurvey.LOADER_VERSION = 2
    sm.ensure_surveys(config)                  # newer loader: rows replaced
    assert modes_in_db() == ['v2']
    marker = next(tmp_path.rglob('*.survey_versions.json'))
    assert json.loads(marker.read_text()) == {'fake/1': 2}

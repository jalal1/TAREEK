"""Smoke tests for person-first demand (models/demand_budget.py and its inputs).

Covers the pieces that decide how many plans are made, with tiny synthetic
inputs and no DB or network access:

  * survey person-day loaders (NHTS perv2pub.csv, TBI Day + Person files)
  * SurveyManager month window, day-type filter and the trip filter that
    follows the selected person-days
  * the budget helpers (main purpose, day weight, segment probabilities,
    source blend) and compute_demand_budget() end to end
  * the config validator rules for the new keys, and the departure KDE
    bandwidth setting

Design: TECHNICAL_REPORT.md, section 5.2.
"""

import json

import numpy as np
import pandas as pd
import pytest

from data_sources.base_survey_trip import BaseSurveyTrip as B
from data_sources.nhts_survey_trip import NHTSSurveyTrip
from data_sources.survey_manager import SurveyManager
from data_sources.tbi_survey import TBISurveyTrip
from models import demand_budget as db
from models.time import DEFAULT_TIME_BANDWIDTH_MINUTES, _time_bandwidth_minutes
from utils.config_validator import ConfigValidationError, ConfigValidator

PURPOSES = ['Shopping', 'School', 'Social', 'Dining', 'Other']


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _day(stops, date='2023-10-03', weight=1.0):
    """Trips of one day from [(destination, depart 'HH:MM', arrive 'HH:MM'), ...]."""
    rows = []
    for dest, dep, arr in stops:
        rows.append({
            B.DESTINATION_PURPOSE: dest,
            B.DEPART_TIME: pd.Timestamp(f"{date} {dep}"),
            B.ARRIVE_TIME: pd.Timestamp(f"{date} {arr}"),
            B.TRIP_WEIGHT: weight,
        })
    return pd.DataFrame(rows)


def _person_days(rows):
    """Person-day frame from [(pid, date, weight, segment, month, weekday, n_trips), ...]."""
    return pd.DataFrame(rows, columns=B.PERSON_DAY_COLUMNS)


def _bare_manager(config, sources=None):
    """A SurveyManager without its DB-backed __init__ (ensure_surveys)."""
    sm = SurveyManager.__new__(SurveyManager)
    sm.config = config
    sm.survey_configs = config['data'].get('surveys', [])
    sm.sources = sources or {}
    sm.person_day_sources = dict(sm.sources)
    sm._person_days = None
    sm._month_filters = {}
    return sm


class _FakeSource:
    def __init__(self, person_days):
        self._pd = person_days

    def load_person_days(self):
        return None if self._pd is None else self._pd.copy()


# ---------------------------------------------------------------------------
# main_purpose / _day_weight
# ---------------------------------------------------------------------------

@pytest.mark.smoke
def test_main_purpose_is_longest_non_home_non_work_dwell():
    trips = _day([('Shopping', '09:00', '09:10'),   # dwell 09:10 -> 09:40 = 30 min
                  ('Social', '09:40', '09:50'),     # dwell 09:50 -> 11:20 = 90 min
                  ('Home', '11:20', '11:30')])
    assert db.main_purpose(trips) == 'Social'


@pytest.mark.smoke
def test_main_purpose_skips_home_and_work():
    trips = _day([('Work', '07:00', '07:30'), ('Home', '16:00', '16:30')])
    assert db.main_purpose(trips) is None


@pytest.mark.smoke
def test_main_purpose_last_stop_without_home_has_zero_dwell():
    trips = _day([('Dining', '12:00', '12:10'),     # dwell 12:10 -> 12:20 = 10 min
                  ('Other', '12:20', '12:30')])     # last stop, no known dwell -> 0
    assert db.main_purpose(trips) == 'Dining'


@pytest.mark.smoke
def test_day_weight_is_mean_of_positive_trip_weights():
    trips = _day([('Shopping', '09:00', '09:10'), ('Home', '10:00', '10:10')])
    trips[B.TRIP_WEIGHT] = [2.0, 4.0]
    assert db._day_weight(trips, use_weight=True) == pytest.approx(3.0)
    assert db._day_weight(trips, use_weight=False) == 1.0
    trips[B.TRIP_WEIGHT] = [0.0, 0.0]
    assert db._day_weight(trips, use_weight=True) == 0.0


# ---------------------------------------------------------------------------
# _source_day_records / _segment_probs / _blend
# ---------------------------------------------------------------------------

@pytest.mark.smoke
def test_source_day_records_dated_keys_commute_and_purpose_fallback():
    pdays = _person_days([
        ('p1', '2023-10-03', 1.0, B.SEG_WORKER, 10, 1, 2),
        ('p2', '2023-10-03', 1.0, B.SEG_NONWORKER_ADULT, 10, 1, 2),
    ])
    persons = {
        'p1': {'2023-10-03': _day([('Work', '08:00', '08:30'), ('Home', '17:00', '17:30')])},
        # 'Escort' is not an enabled purpose -> falls back to Other
        'p2': {'2023-10-03': _day([('Escort', '08:00', '08:10'), ('Home', '09:00', '09:10')])},
    }
    df = db._source_day_records(persons, pdays, PURPOSES, use_weight=True)
    rec = {k: row for k, (_, row) in zip(df['key'], df.iterrows())}
    assert set(rec) == {('p1', '2023-10-03'), ('p2', '2023-10-03')}   # dated keys
    assert bool(rec[('p1', '2023-10-03')]['commute']) is True
    assert rec[('p1', '2023-10-03')]['main_purpose'] is None
    assert rec[('p2', '2023-10-03')]['main_purpose'] == 'Other'
    assert rec[('p2', '2023-10-03')]['segment'] == B.SEG_NONWORKER_ADULT
    assert rec[('p2', '2023-10-03')]['pd_weight'] == pytest.approx(1.0)


@pytest.mark.smoke
def test_segment_probs_day_types_and_purpose_mix():
    # 4 worker days: 3 with travel (2 commute, 1 other travel), 1 without travel.
    pdays = _person_days([
        ('w1', None, 1.0, B.SEG_WORKER, 10, 1, 2),
        ('w2', None, 1.0, B.SEG_WORKER, 10, 1, 2),
        ('w3', None, 1.0, B.SEG_WORKER, 10, 1, 3),
        ('w4', None, 1.0, B.SEG_WORKER, 10, 1, 0),
    ])
    days = pd.DataFrame({
        'key': ['w1', 'w2', 'w3'], 'segment': [B.SEG_WORKER] * 3,
        'commute': [True, True, False], 'main_purpose': [None, None, 'Shopping'],
        'chain_weight': [1.0] * 3, 'pd_weight': [1.0] * 3,
    })
    probs, mix = db._segment_probs(pdays, days, PURPOSES)
    w = probs[B.SEG_WORKER]
    assert w['travel'] == pytest.approx(0.75)
    assert w['commute'] == pytest.approx(0.5)
    assert w['other_travel'] == pytest.approx(0.25)
    assert w['no_travel'] == pytest.approx(0.25)
    assert w['commute'] + w['other_travel'] + w['no_travel'] == pytest.approx(1.0)
    assert mix[B.SEG_WORKER]['Shopping'] == pytest.approx(1.0)
    assert B.SEG_STUDENT not in probs   # no student person-days -> no entry


@pytest.mark.smoke
def test_blend_is_weighted_mean_and_ignores_zero_weight():
    a = {B.SEG_WORKER: {'commute': 0.4}}
    b = {B.SEG_WORKER: {'commute': 0.8}}
    out = db._blend({'nhts': a, 'tbi': b}, {'nhts': 1.0, 'tbi': 3.0})
    assert out[B.SEG_WORKER]['commute'] == pytest.approx(0.7)
    out = db._blend({'nhts': a, 'tbi': b}, {'nhts': 1.0, 'tbi': 0.0})
    assert out[B.SEG_WORKER]['commute'] == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# compute_demand_budget end to end (no DB, no ACS)
# ---------------------------------------------------------------------------

class _FakeBudgetManager:
    def __init__(self, person_days):
        self._pd = person_days

    def get_person_days(self):
        return self._pd

    def get_blend_weights(self, role=None):
        return {'nhts': 1.0}


def _budget_inputs():
    pdays = _person_days([
        ('w1', None, 1.0, B.SEG_WORKER, 10, 1, 2),
        ('w2', None, 1.0, B.SEG_WORKER, 10, 1, 2),
        ('s1', None, 1.0, B.SEG_STUDENT, 10, 1, 2),
        ('a1', None, 1.0, B.SEG_NONWORKER_ADULT, 10, 1, 2),
        ('a2', None, 1.0, B.SEG_NONWORKER_ADULT, 10, 1, 0),
    ])
    persons = {
        'w1': {'d': _day([('Work', '08:00', '08:30'), ('Home', '17:00', '17:30')])},
        'w2': {'d': _day([('Shopping', '10:00', '10:10'), ('Home', '11:00', '11:10')])},
        's1': {'d': _day([('School', '07:30', '07:50'), ('Home', '15:00', '15:20')])},
        'a1': {'d': _day([('Social', '13:00', '13:10'), ('Home', '16:00', '16:10')])},
    }
    home = {
        '270030001001000': {'n_employees': 100, 'non_employees': 100,
                            'state_fips': '27', 'county_fips': '003'},
        '270030001001001': {'n_employees': 50, 'non_employees': 0,
                            'state_fips': '27', 'county_fips': '003'},
    }
    return pdays, persons, home


def _budget_config(share=1.0, shopping_blend=None):
    nw = {'nonwork_trip_share': share}
    for p in PURPOSES:
        nw[p] = {'enabled': True, 'trip_generation': {'config_rate': 0.25, 'blend_weight': 0}}
    if shopping_blend is not None:
        nw['Shopping']['trip_generation'] = shopping_blend
    return {'region': {'counties': ['27003']}, 'data': {'data_dir': '.'},
            'chains': {'use_weighted_chains': True}, 'nonwork_purposes': nw}


@pytest.fixture
def no_acs(monkeypatch):
    shares = {'27003': {'age_0_4': 0.10, 'age_5_17': 0.20}}
    monkeypatch.setattr(db, 'fetch_county_age_shares', lambda config: (shares, 'test'))


@pytest.mark.smoke
def test_compute_demand_budget_segments_and_origins(no_acs):
    pdays, persons, home = _budget_inputs()
    b = db.compute_demand_budget(_budget_config(), _FakeBudgetManager({'nhts': pdays}),
                                 {'nhts': persons}, home, build_chains=False)
    # P(commute) of workers = 1 commute day of 2 worker days
    assert b.p_commute == pytest.approx(0.5)
    # 200 persons in block 1: 20 children, 40 students, 40 adults, 100 workers
    assert b.segment_population[B.SEG_WORKER] == pytest.approx(150)
    assert b.segment_population[B.SEG_CHILD] == pytest.approx(20)
    assert b.segment_population[B.SEG_STUDENT] == pytest.approx(40)
    assert b.segment_population[B.SEG_NONWORKER_ADULT] == pytest.approx(40)
    # origins per block add up to the purpose totals
    for p in PURPOSES:
        total = sum(d[db.origin_key(p)] for d in home.values())
        assert total == pytest.approx(b.purpose_origin_totals[p])
    # workers: other travel 0.5, all of it Shopping -> 150 * 0.5 = 75 Shopping persons
    # students: School on every travel day -> 40 School persons
    assert b.purpose_origin_totals['Shopping'] == pytest.approx(75)
    assert b.purpose_origin_totals['School'] == pytest.approx(40)
    # adults: travel 0.5, all Social -> 40 * 0.5 = 20
    assert b.purpose_origin_totals['Social'] == pytest.approx(20)
    summary = b.summary()
    assert summary['p_commute_workers'] == pytest.approx(0.5)
    assert summary['knob_factors']['Shopping'] == pytest.approx(1.0)


@pytest.mark.smoke
def test_nonwork_trip_share_scales_every_purpose(no_acs):
    pdays, persons, home = _budget_inputs()
    base = db.compute_demand_budget(_budget_config(1.0), _FakeBudgetManager({'nhts': pdays}),
                                    {'nhts': persons}, json.loads(json.dumps(home)), build_chains=False)
    more = db.compute_demand_budget(_budget_config(1.8), _FakeBudgetManager({'nhts': pdays}),
                                    {'nhts': persons}, json.loads(json.dumps(home)), build_chains=False)
    for p in PURPOSES:
        assert more.purpose_origin_totals[p] == pytest.approx(1.8 * base.purpose_origin_totals[p])
        assert more.purpose_factors[p] == pytest.approx(1.8)
    # the knob acts on non-work only: P(commute) is unchanged
    assert more.p_commute == pytest.approx(base.p_commute)


@pytest.mark.smoke
def test_blend_weight_moves_rate_toward_config_rate(no_acs):
    pdays, persons, home = _budget_inputs()
    b = db.compute_demand_budget(
        _budget_config(shopping_blend={'config_rate': 0.45, 'blend_weight': 1.0}),
        _FakeBudgetManager({'nhts': pdays}), {'nhts': persons}, home, build_chains=False)
    total_pop = sum(b.segment_population.values())
    # survey Shopping rate = 75 / 250 = 0.30 per person; blend_weight 1.0 -> config_rate exactly
    assert b.purpose_origin_totals['Shopping'] / total_pop == pytest.approx(0.45)
    assert b.purpose_factors['Shopping'] == pytest.approx(1.5)
    assert b.purpose_factors['Social'] == pytest.approx(1.0)   # other purposes unchanged


@pytest.mark.smoke
def test_compute_demand_budget_needs_person_days(no_acs):
    _, persons, home = _budget_inputs()
    with pytest.raises(ValueError, match="person-days"):
        db.compute_demand_budget(_budget_config(), _FakeBudgetManager({'nhts': None}),
                                 {'nhts': persons}, home, build_chains=False)


@pytest.mark.smoke
def test_write_budget_json_roundtrip(tmp_path, no_acs):
    pdays, persons, home = _budget_inputs()
    b = db.compute_demand_budget(_budget_config(), _FakeBudgetManager({'nhts': pdays}),
                                 {'nhts': persons}, home, build_chains=False)
    path = tmp_path / 'demand_budget.json'
    db.write_budget_json(b, path, extra={'run': 'test'})
    data = json.loads(path.read_text())
    assert data['run'] == 'test'
    assert data['p_commute_workers'] == pytest.approx(0.5)
    assert set(data['nonwork_persons_unscaled']) == set(PURPOSES)


# ---------------------------------------------------------------------------
# SurveyManager: months, day type, person-day and trip filters
# ---------------------------------------------------------------------------

@pytest.mark.smoke
@pytest.mark.parametrize('value, expected', [
    ('regular', frozenset({3, 4, 5, 9, 10, 11})),
    ('Regular', frozenset({3, 4, 5, 9, 10, 11})),
    ('all', None),
    ([10, 11], frozenset({10, 11})),
])
def test_survey_months_values(value, expected):
    sm = _bare_manager({'data': {'survey_months': value, 'surveys': []}})
    assert sm.survey_months() == expected


@pytest.mark.smoke
@pytest.mark.parametrize('value', ['summer', [0, 5], [13], []])
def test_survey_months_invalid(value):
    sm = _bare_manager({'data': {'survey_months': value, 'surveys': []}})
    with pytest.raises(ValueError):
        sm.survey_months()


def _nhts_like_days(n_per_seg, month):
    rows = []
    for seg in (B.SEG_WORKER, B.SEG_STUDENT, B.SEG_NONWORKER_ADULT):
        for i in range(n_per_seg):
            rows.append((f"{seg}_{month}_{i}", None, 1.0, seg, month, 1, 2))
    return rows


@pytest.mark.smoke
def test_get_person_days_keeps_month_window_and_weekdays():
    rows = _nhts_like_days(3, 10) + _nhts_like_days(3, 7)
    rows.append(('weekend_1', None, 1.0, B.SEG_WORKER, 10, 5, 2))   # Saturday
    sm = _bare_manager({'data': {'survey_months': 'regular', 'day_type': 'weekday', 'surveys': []}},
                       {'nhts': _FakeSource(_person_days(rows))})
    sm.MIN_SEGMENT_DAYS_IN_WINDOW = 2
    out = sm.get_person_days()['nhts']
    assert set(out[B.PD_MONTH]) == {10}                 # July dropped
    assert 'weekend_1' not in set(out[B.PD_PERSON_ID])  # weekend dropped
    kind, ids = sm._month_filters['nhts']
    assert kind == 'person' and len(ids) == 9


@pytest.mark.smoke
def test_get_person_days_falls_back_to_all_months_when_a_segment_is_thin():
    rows = _nhts_like_days(3, 10) + _nhts_like_days(3, 7)
    sm = _bare_manager({'data': {'survey_months': 'regular', 'surveys': []}},
                       {'nhts': _FakeSource(_person_days(rows))})
    sm.MIN_SEGMENT_DAYS_IN_WINDOW = 5    # only 3 per segment in October -> fall back
    out = sm.get_person_days()['nhts']
    assert set(out[B.PD_MONTH]) == {7, 10}


@pytest.mark.smoke
def test_get_person_days_dated_source_uses_person_date_rule():
    rows = [('t1', '2023-10-03', 1.0, B.SEG_WORKER, 10, 1, 2),
            ('t1', '2023-10-04', 1.0, B.SEG_WORKER, 10, 2, 2)]
    sm = _bare_manager({'data': {'survey_months': 'all', 'surveys': []}},
                       {'tbi': _FakeSource(_person_days(rows))})
    sm.get_person_days()
    kind, keys = sm._month_filters['tbi']
    assert kind == 'person_date'
    assert keys == {('t1', '2023-10-03'), ('t1', '2023-10-04')}


@pytest.mark.smoke
def test_filter_months_person_date_keeps_only_selected_days():
    sm = _bare_manager({'data': {'surveys': []}})
    sm._person_days = {}
    sm._month_filters = {'tbi': ('person_date', {('t1', '2023-10-03')})}
    trips = pd.DataFrame({B.PERSON_ID: ['t1', 't1', 't2'],
                          B.DEPART_TIME: pd.to_datetime(['2023-10-03 08:00', '2023-10-04 08:00',
                                                         '2023-10-03 08:00'])})
    out = sm._filter_months(trips, 'tbi')
    assert len(out) == 1 and out.iloc[0][B.DEPART_TIME].day == 3


@pytest.mark.smoke
def test_filter_months_month_rule_and_single_month_passthrough():
    sm = _bare_manager({'data': {'surveys': []}})
    sm._person_days = {}
    sm._month_filters = {'x': ('month', frozenset({10}))}
    trips = pd.DataFrame({B.PERSON_ID: ['a', 'b'],
                          B.DEPART_TIME: pd.to_datetime(['2022-10-03 08:00', '2022-07-03 08:00'])})
    assert len(sm._filter_months(trips, 'x')) == 1
    # a source whose dates all share one month has no real months -> kept whole
    one_month = trips.assign(**{B.DEPART_TIME: pd.to_datetime(['2022-01-02 08:00', '2022-01-03 09:00'])})
    assert len(sm._filter_months(one_month, 'x')) == 2


@pytest.mark.smoke
def test_filter_months_raises_when_nothing_is_left():
    sm = _bare_manager({'data': {'surveys': []}})
    sm._person_days = {}
    sm._month_filters = {'x': ('person', {'nobody'})}
    trips = pd.DataFrame({B.PERSON_ID: ['a'], B.DEPART_TIME: pd.to_datetime(['2022-10-03 08:00'])})
    with pytest.raises(ValueError, match="no trips left"):
        sm._filter_months(trips, 'x')


# ---------------------------------------------------------------------------
# Person-day loaders
# ---------------------------------------------------------------------------

@pytest.mark.smoke
def test_nhts_load_person_days(tmp_path):
    (tmp_path / 'nhts').mkdir()
    pd.DataFrame({
        'HOUSEID': [1, 1, 2, 3, 4],
        'PERSONID': [1, 2, 1, 1, 1],
        'WTPERFIN': [10.0, 5.0, 2.0, 0.0, 3.0],
        'R_AGE': [40, 12, 70, 30, 45],
        'WORKER': [1, -1, 2, 1, 1],
        'TRAVDAY': [2, 3, 1, 4, 7],          # Mon, Tue, Sun, Wed, Sat
        'TDAYDATE': [202210, 202211, 202207, 202210, 202203],
        'CNTTDTR': [3, 2, 0, 1, 4],
        'MSASIZE': [4, 4, 5, 4, 1],
    }).to_csv(tmp_path / 'nhts' / 'per.csv', index=False)
    cfg = {'data': {'data_dir': str(tmp_path), 'surveys': [
        {'type': 'nhts', 'year': '2022', 'weight': 1, 'person_file': 'nhts/per.csv'}]}}
    src = NHTSSurveyTrip(cfg)
    src.metadata['source_year'] = '2022'
    out = src.load_person_days().set_index(B.PD_PERSON_ID)
    assert '3_1' not in out.index                     # zero weight dropped
    assert out.loc['1_1', B.PD_SEGMENT] == B.SEG_WORKER
    assert out.loc['1_2', B.PD_SEGMENT] == B.SEG_STUDENT
    assert out.loc['2_1', B.PD_SEGMENT] == B.SEG_NONWORKER_ADULT
    assert out.loc['1_1', B.PD_WEEKDAY] == 0          # TRAVDAY 2 = Monday
    assert out.loc['2_1', B.PD_WEEKDAY] == 6          # TRAVDAY 1 = Sunday
    assert out.loc['1_1', B.PD_MONTH] == 10
    assert out[B.PD_DATE].isna().all()                # one day per person
    # msa_sizes keeps only persons from metros of that size
    cfg['data']['surveys'][0]['msa_sizes'] = [4]
    src = NHTSSurveyTrip(cfg)
    src.metadata['source_year'] = '2022'
    assert set(src.load_person_days()[B.PD_PERSON_ID]) == {'1_1', '1_2'}


@pytest.mark.smoke
def test_nhts_load_person_days_without_person_file_returns_none(tmp_path):
    cfg = {'data': {'data_dir': str(tmp_path), 'surveys': [{'type': 'nhts', 'year': '2022', 'weight': 1}]}}
    src = NHTSSurveyTrip(cfg)
    src.metadata['source_year'] = '2022'
    assert src.load_person_days() is None


@pytest.mark.smoke
def test_tbi_load_person_days(tmp_path):
    d = tmp_path / 'tbi'
    d.mkdir()
    pd.DataFrame({
        'person_id': ['101', '101', '102', '103', '104'],
        'travel_date': ['2023-10-03', '2023-10-04', '2023-10-03', '2023-04-11', '2023-10-03'],
        'travel_dow': ['Tuesday', 'Wednesday', 'Tuesday', 'Tuesday', 'Tuesday'],
        'num_trips': [4, 0, 2, 3, 1],
        'day_weight': [1.5, 1.5, 2.0, 0.0, 1.0],
    }).to_csv(d / 'day.csv', index=False)
    pd.DataFrame({
        'person_id': ['101', '102', '103', '104'],
        'age': ['35 to 44', '5 to 15', '65 to 74', 'Missing'],
        'employment': ['Employed full-time', 'Missing', 'Retired', 'Missing'],
    }).to_csv(d / 'person.csv', index=False)
    cfg = {'data': {'data_dir': str(tmp_path), 'surveys': [
        {'type': 'tbi', 'year': '2023', 'weight': 1,
         'person_file': 'tbi/person.csv', 'day_file': 'tbi/day.csv'}]}}
    src = TBISurveyTrip(cfg)
    src.metadata['source_year'] = '2023'
    out = src.load_person_days()
    # 103 has zero day weight, 104 has no usable age or employment -> both dropped
    assert set(out[B.PD_PERSON_ID]) == {'101', '102'}
    p101 = out[out[B.PD_PERSON_ID] == '101']
    assert len(p101) == 2                              # several days per person
    assert set(p101[B.PD_DATE]) == {'2023-10-03', '2023-10-04'}
    assert (p101[B.PD_SEGMENT] == B.SEG_WORKER).all()
    assert out[out[B.PD_PERSON_ID] == '102'][B.PD_SEGMENT].iloc[0] == B.SEG_STUDENT
    assert set(p101[B.PD_WEEKDAY]) == {1, 2}           # Tuesday, Wednesday
    assert (out[B.PD_MONTH] == 10).all()


@pytest.mark.smoke
def test_tbi_load_person_days_missing_file_raises(tmp_path):
    cfg = {'data': {'data_dir': str(tmp_path), 'surveys': [
        {'type': 'tbi', 'year': '2023', 'weight': 1,
         'person_file': 'tbi/person.csv', 'day_file': 'tbi/day.csv'}]}}
    src = TBISurveyTrip(cfg)
    src.metadata['source_year'] = '2023'
    with pytest.raises(FileNotFoundError):
        src.load_person_days()


# ---------------------------------------------------------------------------
# Departure KDE bandwidth
# ---------------------------------------------------------------------------

@pytest.mark.smoke
def test_time_bandwidth_setting():
    assert _time_bandwidth_minutes(None) == DEFAULT_TIME_BANDWIDTH_MINUTES
    assert _time_bandwidth_minutes({'time_models': {}}) == DEFAULT_TIME_BANDWIDTH_MINUTES
    assert _time_bandwidth_minutes({'time_models': {'departure_bandwidth_minutes': 'Scott'}}) == 'scott'
    assert _time_bandwidth_minutes({'time_models': {'departure_bandwidth_minutes': 5}}) == 5.0
    with pytest.raises(ValueError):
        _time_bandwidth_minutes({'time_models': {'departure_bandwidth_minutes': 0}})


# ---------------------------------------------------------------------------
# Config validator rules for the new keys
# ---------------------------------------------------------------------------

def _write_variant(tmp_path, smoke_config_path, mutate):
    config = json.loads(smoke_config_path.read_text(encoding='utf-8'))
    config['data']['data_dir'] = str((smoke_config_path.parent / config['data']['data_dir']).resolve())
    mutate(config)
    path = tmp_path / 'variant.json'
    path.write_text(json.dumps(config), encoding='utf-8')
    return path


@pytest.mark.smoke
def test_validator_requires_a_person_file(tmp_path, smoke_config_path):
    def drop(c):
        for s in c['data']['surveys']:
            s.pop('person_file', None)
    with pytest.raises(ConfigValidationError, match="person_file"):
        ConfigValidator(_write_variant(tmp_path, smoke_config_path, drop)).validate()


@pytest.mark.smoke
def test_validator_tbi_needs_day_file(tmp_path, smoke_config_path):
    def add_tbi(c):
        c['data']['surveys'].append({'type': 'tbi', 'year': '2023', 'weight': 1,
                                     'person_file': 'tbi/person.csv'})
    with pytest.raises(ConfigValidationError, match="day_file"):
        ConfigValidator(_write_variant(tmp_path, smoke_config_path, add_tbi)).validate()


@pytest.mark.smoke
@pytest.mark.parametrize('mutate, match', [
    (lambda c: c['data'].__setitem__('survey_months', 'summer'), 'survey_months'),
    (lambda c: c['data'].__setitem__('survey_months', [0, 13]), 'survey_months'),
    (lambda c: c['plan_generation'].__setitem__('work_scaling_multiplier', -1), 'work_scaling_multiplier'),
    (lambda c: c['nonwork_purposes'].__setitem__('nonwork_trip_share', 'x'), 'nonwork_trip_share'),
    (lambda c: c.setdefault('time_models', {}).__setitem__('departure_bandwidth_minutes', -5),
     'departure_bandwidth_minutes'),
])
def test_validator_rejects_bad_demand_values(tmp_path, smoke_config_path, mutate, match):
    with pytest.raises(ConfigValidationError, match=match):
        ConfigValidator(_write_variant(tmp_path, smoke_config_path, mutate)).validate()


@pytest.mark.smoke
def test_validator_accepts_non_neutral_knobs(tmp_path, smoke_config_path):
    def knobs(c):
        c['plan_generation']['work_scaling_multiplier'] = 1.2
        c['nonwork_purposes']['nonwork_trip_share'] = 1.8
        c['data']['survey_months'] = [9, 10]
    ConfigValidator(_write_variant(tmp_path, smoke_config_path, knobs)).validate()

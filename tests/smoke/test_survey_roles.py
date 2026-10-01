"""Smoke tests for survey roles and the Birmingham local survey reader.

Survey roles (data_sources/survey_manager.py, ROLES): each data.surveys entry
has one ``weight`` and an optional ``roles`` dict that overrides it per job
(person_days, chains, times, modes, od). Covered here, with no DB access:

  * role_weight defaults and overrides; validate_survey_roles errors
  * which sources become trip sources and which person-day sources
  * per-job blend weights, select_for_role, role_weights_from_shared
  * compute_demand_budget() loading a person_days-only source's trips
  * the bham_local reader: time parsing, midnight crossings, cleaning rules
"""

import pandas as pd
import pytest

from data_sources import survey_manager as smod
from data_sources.base_survey_trip import BaseSurveyTrip as B
from data_sources.bham_local_survey import BirminghamLocalSurveyTrip as Bham
from data_sources.survey_manager import (
    ROLE_CHAINS, ROLE_MODES, ROLE_OD, ROLE_PERSON_DAYS, ROLE_TIMES,
    SurveyManager, role_weight, role_weights_from_shared, select_for_role,
    validate_survey_roles,
)
from models import demand_budget as db


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

BHAM_ROLES = [
    {'type': 'bham_local', 'year': 'undated', 'weight': 1},
    {'type': 'nhts', 'year': '2022', 'weight': 0, 'roles': {'person_days': 1}},
]


class _Src:
    """Survey source stand-in: no DB, fixed person-days."""

    def __init__(self, config, person_days=None):
        self.config = config
        self.metadata = {}
        self.data = None
        self._pd = person_days

    def load_person_days(self):
        return None if self._pd is None else self._pd.copy()


def _manager(surveys, monkeypatch, person_days=None):
    """A SurveyManager built through its real __init__, with fake sources."""
    person_days = person_days or {}
    monkeypatch.setattr(smod, 'ensure_surveys', lambda config: None)
    registry = {}
    for e in surveys:
        name = e['type']
        registry[name] = (lambda n: (lambda cfg: _Src(cfg, person_days.get(n))))(name)
    monkeypatch.setattr(SurveyManager, 'SURVEY_REGISTRY', registry)
    return SurveyManager({'data': {'surveys': surveys, 'survey_months': 'all', 'day_type': 'all'}})


def _person_days(rows):
    return pd.DataFrame(rows, columns=B.PERSON_DAY_COLUMNS)


def _day(stops, date='2023-10-03'):
    return pd.DataFrame([{B.DESTINATION_PURPOSE: d, B.DEPART_TIME: pd.Timestamp(f"{date} {dep}"),
                          B.ARRIVE_TIME: pd.Timestamp(f"{date} {arr}"), B.TRIP_WEIGHT: 1.0}
                         for d, dep, arr in stops])


# ---------------------------------------------------------------------------
# role_weight / validation
# ---------------------------------------------------------------------------

@pytest.mark.smoke
def test_role_weight_defaults_to_weight_and_roles_override():
    e = {'type': 'nhts', 'weight': 0, 'roles': {'person_days': 1}}
    assert role_weight(e, ROLE_PERSON_DAYS) == 1.0
    assert role_weight(e, ROLE_CHAINS) == 0.0
    assert role_weight({'type': 'tbi'}, ROLE_TIMES) == 1.0      # no weight -> 1


@pytest.mark.smoke
def test_validate_rejects_unknown_role():
    with pytest.raises(ValueError, match='unknown job'):
        validate_survey_roles([{'type': 'nhts', 'weight': 1, 'roles': {'trips': 1}}])


@pytest.mark.smoke
def test_validate_rejects_negative_role_weight():
    with pytest.raises(ValueError, match='negative'):
        validate_survey_roles([{'type': 'nhts', 'weight': 1, 'roles': {'od': -1}}])


@pytest.mark.smoke
def test_validate_needs_a_source_for_every_required_job():
    with pytest.raises(ValueError, match="'chains'"):
        validate_survey_roles([{'type': 'nhts', 'weight': 0, 'roles': {'person_days': 1}}])
    with pytest.raises(ValueError, match="'person_days'"):
        validate_survey_roles([{'type': 'bham_local', 'weight': 1, 'roles': {'person_days': 0}}])
    validate_survey_roles(BHAM_ROLES)   # no error


# ---------------------------------------------------------------------------
# SurveyManager source sets and weights
# ---------------------------------------------------------------------------

@pytest.mark.smoke
def test_no_roles_keeps_old_behaviour(monkeypatch):
    sm = _manager([{'type': 'tbi', 'year': '2023', 'weight': 0.7},
                   {'type': 'nhts', 'year': '2022', 'weight': 0.3}], monkeypatch)
    assert set(sm.sources) == {'tbi', 'nhts'}
    assert set(sm.person_day_sources) == {'tbi', 'nhts'}
    assert sm.has_multiple_sources()
    for r in (None, ROLE_CHAINS, ROLE_TIMES, ROLE_MODES, ROLE_OD, ROLE_PERSON_DAYS):
        assert sm.get_blend_weights(r) == {'tbi': 0.7, 'nhts': 0.3}


@pytest.mark.smoke
def test_weight_zero_without_roles_skips_the_source(monkeypatch):
    sm = _manager([{'type': 'tbi', 'year': '2023', 'weight': 1},
                   {'type': 'nhts', 'year': '2022', 'weight': 0}], monkeypatch)
    assert set(sm.sources) == {'tbi'} and set(sm.person_day_sources) == {'tbi'}
    assert not sm.has_multiple_sources()


@pytest.mark.smoke
def test_person_days_only_source_is_not_a_trip_source(monkeypatch):
    sm = _manager(BHAM_ROLES, monkeypatch)
    assert set(sm.sources) == {'bham_local'}
    assert set(sm.person_day_sources) == {'bham_local', 'nhts'}
    assert not sm.has_multiple_sources()            # trips come from one survey
    assert sm.get_blend_weights(ROLE_CHAINS) == {'bham_local': 1.0}
    assert sm.get_blend_weights(ROLE_PERSON_DAYS) == {'bham_local': 1.0, 'nhts': 1.0}
    assert sm.get_role_weights()[ROLE_MODES] == {'bham_local': 1.0}


@pytest.mark.smoke
def test_per_job_split_between_two_trip_sources(monkeypatch):
    sm = _manager([{'type': 'tbi', 'year': '2023', 'weight': 0, 'roles': {'times': 1}},
                   {'type': 'nhts', 'year': '2022', 'weight': 1, 'roles': {'times': 0}}],
                  monkeypatch)
    assert set(sm.sources) == {'tbi', 'nhts'}
    assert set(sm.person_day_sources) == {'nhts'}
    assert sm.get_blend_weights(ROLE_TIMES) == {'tbi': 1.0}
    assert sm.get_blend_weights(ROLE_CHAINS) == {'nhts': 1.0}


@pytest.mark.smoke
def test_get_person_days_returns_only_person_days_sources(monkeypatch):
    rows = [('n1', None, 1.0, B.SEG_WORKER, 10, 1, 2)]
    sm = _manager([{'type': 'tbi', 'year': '2023', 'weight': 1, 'roles': {'person_days': 0}},
                   {'type': 'nhts', 'year': '2022', 'weight': 0, 'roles': {'person_days': 1}}],
                  monkeypatch, person_days={'tbi': _person_days([('t1', None, 1.0, B.SEG_WORKER, 10, 1, 2)]),
                                            'nhts': _person_days(rows)})
    out = sm.get_person_days()
    assert set(out) == {'nhts'}
    # the trip source still gets its own person-day filter for its trips
    assert sm._month_filters['tbi'] == ('person', {'t1'})


@pytest.mark.smoke
def test_filter_df_by_role(monkeypatch):
    sm = _manager([{'type': 'tbi', 'year': '2023', 'weight': 1, 'roles': {'od': 0}},
                   {'type': 'nhts', 'year': '2022', 'weight': 1}], monkeypatch)
    df = pd.DataFrame({B.SOURCE_TYPE: ['tbi', 'nhts', 'nhts']})
    assert list(sm.filter_df_by_role(df, ROLE_OD)[B.SOURCE_TYPE]) == ['nhts', 'nhts']


@pytest.mark.smoke
def test_select_for_role_and_shared_fallback():
    assert select_for_role({'a': 1, 'b': 2}, {'a': 1.0, 'b': 0}) == {'a': 1}
    shared = {'blend_weights': {'a': 1.0}, 'role_weights': {'times': {'b': 1.0}}}
    assert role_weights_from_shared(shared, 'times') == {'b': 1.0}
    assert role_weights_from_shared(shared, 'chains') == {'a': 1.0}   # old key


# ---------------------------------------------------------------------------
# demand budget: person-days from a source that supplies no trips
# ---------------------------------------------------------------------------

class _BudgetManager:
    """Trips from bham_local; person-days (and their trips) from nhts only."""

    def __init__(self, pdays, nhts_persons):
        self._pd, self._np = pdays, nhts_persons
        self.loaded_roles = []
        self.sources = {'bham_local': None}
        self.person_day_sources = {'nhts': None}

    def get_person_days(self):
        return {'nhts': self._pd}

    def get_blend_weights(self, role=None):
        return {'nhts': 1.0} if role == ROLE_PERSON_DAYS else {'bham_local': 1.0}

    def process_persons(self, role=None):
        self.loaded_roles.append(role)
        return {'nhts': self._np}


@pytest.mark.smoke
def test_budget_loads_trips_of_person_days_only_source(monkeypatch):
    monkeypatch.setattr(db, 'fetch_county_age_shares',
                        lambda config: ({'27003': {'age_0_4': 0.1, 'age_5_17': 0.2}}, 'test'))
    pdays = _person_days([
        ('w1', None, 1.0, B.SEG_WORKER, 10, 1, 2),
        ('w2', None, 1.0, B.SEG_WORKER, 10, 1, 0),
        ('s1', None, 1.0, B.SEG_STUDENT, 10, 1, 2),
        ('a1', None, 1.0, B.SEG_NONWORKER_ADULT, 10, 1, 2),
    ])
    nhts_persons = {
        'w1': {'d': _day([('Work', '08:00', '08:30'), ('Home', '17:00', '17:30')])},
        's1': {'d': _day([('School', '07:30', '07:50'), ('Home', '15:00', '15:20')])},
        'a1': {'d': _day([('Shopping', '13:00', '13:10'), ('Home', '16:00', '16:10')])},
    }
    bham_persons = {'b1': {'d': _day([('Shopping', '10:00', '10:10'), ('Home', '11:00', '11:10')])}}
    mgr = _BudgetManager(pdays, nhts_persons)
    config = {'region': {'counties': ['27003']}, 'data': {'data_dir': '.'},
              'chains': {'use_weighted_chains': True},
              'nonwork_purposes': {p: {'enabled': True, 'trip_generation': {}}
                                   for p in ('Shopping', 'School', 'Social', 'Dining', 'Other')}}
    home = {'270030001001000': {'n_employees': 10, 'non_employees': 10,
                                'state_fips': '27', 'county_fips': '003'}}
    b = db.compute_demand_budget(config, mgr, {'bham_local': bham_persons}, home, build_chains=True)
    assert mgr.loaded_roles == [ROLE_PERSON_DAYS]
    assert b.p_commute == pytest.approx(0.5)          # from NHTS: 1 commute day of 2 worker days
    assert b.person_day_weights == {'nhts': 1.0}
    # chain pools come from the chains source only
    assert set(b.per_source_purpose_chains_dfs) == {'bham_local'}


# ---------------------------------------------------------------------------
# bham_local reader
# ---------------------------------------------------------------------------

@pytest.mark.smoke
@pytest.mark.parametrize('raw, seconds', [
    ('16:30:00', 16 * 3600 + 1800),
    ('5:00:00', 5 * 3600),
    ('12:9:00', 12 * 3600 + 540),
    ('0.629166667', 15 * 3600 + 6 * 60),       # Excel day fraction
    ('16:00:00 AM', 16 * 3600),                # stray AM on a 24-hour time
    ('1:15 PM', 13 * 3600 + 900),
    ('24:00:00', 24 * 3600),
    ('', None),
    ('noon', None),
    ('12:75:00', None),
])
def test_bham_parse_time(raw, seconds):
    assert Bham.parse_time(raw) == seconds


@pytest.mark.smoke
def test_bham_unwrap_times_midnight_overlap_and_error():
    h = 3600
    assert Bham._unwrap_times([23 * h + 2700, 0]) == [23 * h + 2700, 24 * h]       # 23:45 -> 00:00
    assert Bham._unwrap_times([14 * h, 14 * h + 600, 14 * h + 300]) == [14 * h, 14 * h + 600, 14 * h + 600]
    assert Bham._unwrap_times([12 * h + 2700, 1 * h]) is None                       # 12:45 -> 01:00
    assert Bham._unwrap_times([24 * h, 13 * h]) is None                             # '24:00' then 13:00


def _bham_csv(tmp_path, rows):
    slots = ['1st', '2nd', '3rd'] + [f'{i}th' for i in range(4, 14)]
    cols = ['id', 'x0', 'y0', 'Loc_Type']
    for k, p in enumerate(slots, start=1):
        cols += [f'x{k}', f'y{k}', f'{p}_Trip_Start_Time', f'{p}_Trip_End_Time', f'{p}_activity',
                 f'{p}_Mode', f'{p}_Wait_Time_min', f'{p}_Company', f'{p}_Car_Availability']
    cols += ['x14', 'y14']
    recs = []
    for pid, start, home, trips in rows:
        r = {c: '' for c in cols}
        r.update({'id': pid, 'x0': start[0], 'y0': start[1], 'Loc_Type': start[2],
                  'x14': home[0], 'y14': home[1]})
        for k, (x, y, st, en, act, mode) in enumerate(trips, start=1):
            p = slots[k - 1]
            r.update({f'x{k}': x, f'y{k}': y, f'{p}_Trip_Start_Time': st, f'{p}_Trip_End_Time': en,
                      f'{p}_activity': act, f'{p}_Mode': mode})
        recs.append(r)
    path = tmp_path / 'survey.csv'
    pd.DataFrame(recs, columns=cols).to_csv(path, index=False)
    return path


@pytest.mark.smoke
def test_bham_reader_cleans_and_maps(tmp_path, monkeypatch):
    home = ('520000', '3700000')
    path = _bham_csv(tmp_path, [
        # good day; starts at home coordinates with a wrong start type
        ('001', (*home, 'Nightlife/ Bar'), home,
         [('521000', '3700000', '7:30:00', '7:50:00', 'Work', 'Car'),
          ('520000', '3700000', '17:00:00', '17:20:00', 'Home', 'car')]),
        # crosses midnight: kept
        ('002', (*home, 'Home'), home,
         [('521000', '3700500', '22:00:00', '22:10:00', 'Nightlife/ Bar', 'Uber/Lyft'),
          ('520000', '3700000', '23:45:00', '0:05:00', 'Home', 'Uber/Lyft')]),
        # mode cell holds a place: dropped
        ('003', (*home, 'Home'), home,
         [('521000', '3700000', '9:00:00', '9:10:00', 'Shopping- Retail', 'Home')]),
        # time goes backwards at noon: dropped
        ('004', (*home, 'Home'), home,
         [('521000', '3700000', '12:45:00', '1:00:00', 'Pick-up passenger', 'Car')]),
    ])
    monkeypatch.setattr(Bham, '_region_shape', lambda self: None)
    r = Bham({'data': {'data_dir': str(tmp_path), 'surveys': []}, 'region': {'counties': []}})
    r.extract_data('undated', str(path))
    r.clean_data()
    d = r.data
    assert set(d[B.PERSON_ID]) == {'bham_001', 'bham_002'}
    p1 = d[d[B.PERSON_ID] == 'bham_001'].sort_values(B.DEPART_TIME)
    assert list(p1[B.ORIGIN_PURPOSE]) == ['Home', 'Work']           # start fixed to Home
    assert list(p1[B.MODE_TYPE]) == ['Car', 'Car']
    p2 = d[d[B.PERSON_ID] == 'bham_002'].sort_values(B.DEPART_TIME)
    assert list(p2[B.DESTINATION_PURPOSE]) == ['Social', 'Home']
    assert list(p2[B.MODE_TYPE]) == ['Rideshare', 'Rideshare']
    assert p2[B.ARRIVE_TIME].iloc[-1] == Bham.REFERENCE_DATE + pd.Timedelta(hours=24, minutes=5)
    assert (d[B.DEPART_TIME].dt.weekday < 5).all()                   # weekday reference date
    assert d[B.ORIGIN_LOC].isna().all() and (d[B.TRIP_WEIGHT] == 1.0).all()
    assert d[B.DISTANCE].iloc[0] == pytest.approx(1000 / 1609.344)
    assert r.drop_counts['a mode cell is not a mode'] == 1
    assert r.drop_counts['trip times go backwards (not a midnight crossing)'] == 1
    assert r.load_person_days() is None

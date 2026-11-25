# SPDX-License-Identifier: GPL-3.0-or-later
"""Reused plans keep the survey activity durations for config.xml (P3).

A demand-cache hit or skip_if_exists skips the plan step, which is where
matsim._survey_typical_durations / _survey_activity_params are fitted.
Without them config.xml had no activityParams and MATSim stopped. They are
now stored beside plans.xml (demand_derived.json) and restored on reuse; an
old cache entry without them is a miss, not a broken run.
"""

import json
from pathlib import Path

import pytest

import run_experiment as rx

DERIVED = {'_survey_typical_durations': {'Work': 26100, 'Home': 43200},
           '_survey_activity_params': {'Work': {'typicalDuration': '07:15:00'}}}


def _runner(tmp_path: Path, matsim=None) -> rx.ExperimentRunner:
    r = rx.ExperimentRunner.__new__(rx.ExperimentRunner)
    r.experiment_dir = tmp_path / 'exp'
    r.experiment_dir.mkdir()
    r.plans_path = r.experiment_dir / 'plans.xml'
    r.config_path = tmp_path / 'config.json'
    r.config = {'matsim': dict(matsim or {}),
                'plan_generation': {'cache_demand': True},
                'data': {'data_dir': str(tmp_path / 'data')}}
    r.runtime = {}
    r._validate_plans_file = lambda p: True
    return r


@pytest.mark.smoke
def test_write_then_restore_roundtrip(tmp_path):
    src = _runner(tmp_path, matsim=DERIVED)
    path = tmp_path / 'demand_derived.json'
    src._write_demand_derived(path)

    (tmp_path / 'b').mkdir()
    dst = _runner(tmp_path / 'b')
    assert dst._restore_demand_derived(path)
    for k, v in DERIVED.items():
        assert dst.config['matsim'][k] == v


@pytest.mark.smoke
def test_restore_from_config_used_json(tmp_path):
    used = tmp_path / 'config_used.json'
    used.write_text(json.dumps({'matsim': DERIVED}))
    r = _runner(tmp_path)
    assert r._restore_demand_derived(tmp_path / 'missing.json', used)
    assert r.config['matsim']['_survey_typical_durations'] == DERIVED['_survey_typical_durations']


@pytest.mark.smoke
def test_cache_hit_restores_derived_and_old_entry_is_a_miss(tmp_path):
    r = _runner(tmp_path)
    key = r._demand_cache_key()
    cache = r._demand_cache_dir()
    cache.mkdir(parents=True)
    (cache / f'plans_{key}.xml').write_text('<population/>')

    # Old entry (no demand_derived.json): regenerate instead of a broken config.xml
    assert r._try_reuse_cached_demand() is False
    assert not r.plans_path.exists()

    (cache / f'{key}_demand_derived.json').write_text(json.dumps({'matsim': DERIVED}))
    assert r._try_reuse_cached_demand() is True
    assert r.plans_path.exists()
    assert r.config['matsim']['_survey_activity_params'] == DERIVED['_survey_activity_params']
    assert (r.experiment_dir / 'demand_derived.json').exists()

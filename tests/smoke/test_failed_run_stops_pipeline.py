# SPDX-License-Identifier: GPL-3.0-or-later
"""A failed MATSim run must not give metrics that look real (P6).

MATSim writes linkstats in each iteration and a countscompare at it.0, so a
run that fails in the middle leaves partial output. The runner must then
skip the evaluation, write a summary that says "failed" with no evaluation
and no matsim_output section, write a report that says the run failed, add
no row to the comparison CSV, and raise (so the CLI exits non-zero).
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

import run_experiment as rx


def _bare_runner(tmp_path: Path, status: dict) -> rx.ExperimentRunner:
    """A runner without its heavy __init__, with every pipeline step faked."""
    r = rx.ExperimentRunner.__new__(rx.ExperimentRunner)
    exp = tmp_path / 'exp'
    (exp / 'output' / 'ITERS' / 'it.0').mkdir(parents=True)
    # Partial output as a crash in it.1 leaves it.
    (exp / 'output' / 'ITERS' / 'it.0' / '0.countscompare.txt').write_text('x')
    (exp / 'output' / 'scorestats.csv').write_text('iteration;avg_executed\n0;50\n')
    (exp / 'matsim_output.log').write_text('line\nException in thread "main"\n')
    r.experiment_dir = exp
    r.experiment_id = 'exp'
    r.config = {'plan_generation': {'scaling_factor': 0.1}, 'matsim': {}}
    r.runtime = {}
    r.plan_stats = {}
    r.population_stats = {}
    r.data_quality_stats = {}
    r.network_stats = {}
    r.plans_file_size_mb = 0.0
    r.network_path = exp / 'network.xml'
    r.plans_path = exp / 'plans.xml'

    calls = []
    for step in ('validate_config', 'detect_coordinate_system',
                 'setup_experiment_directory', 'setup_matsim_config',
                 'setup_network', '_scale_transit_pce', 'generate_counts',
                 'generate_plans'):
        setattr(r, step, lambda *a, _s=step, **k: calls.append(_s))
    r.run_simulation = lambda skip_simulation=False: dict(status)
    r.run_evaluation = lambda: calls.append('run_evaluation') or {'num_comparisons': 5}
    r._calls = calls
    return r


@pytest.mark.smoke
def test_failed_simulation_stops_before_evaluation(tmp_path, monkeypatch):
    tracked = []
    monkeypatch.setattr(rx, 'ExperimentTracker',
                        lambda *a, **k: tracked.append('tracker'))
    r = _bare_runner(tmp_path, {'simulation_status': 'failed',
                                'matsim_return_code': 137})

    with pytest.raises(RuntimeError, match='MATSim failed'):
        r.run()

    assert 'run_evaluation' not in r._calls
    assert tracked == []

    summary = json.loads((r.experiment_dir / 'experiment_summary.json').read_text())
    assert summary['simulation_status'] == 'failed'
    assert summary['failure']['matsim_return_code'] == 137
    assert 'evaluation' not in summary
    assert 'matsim_output' not in summary

    report = (r.experiment_dir / 'report.md').read_text(encoding='utf-8')
    assert 'SIMULATION FAILED' in report
    assert 'Exception in thread' in report


@pytest.mark.smoke
def test_evaluation_without_input_gives_no_metrics(tmp_path, monkeypatch):
    """No countscompare.txt (plans-only run): no block of zeros in the summary."""
    r = _bare_runner(tmp_path, {'simulation_status': 'skipped'})
    del r.run_evaluation  # use the real method
    (r.experiment_dir / 'matched_devices.csv').write_text('device_id\n1\n')
    truth = tmp_path / 'truth'
    truth.mkdir()
    r.config['evaluation'] = {'ground_truth_data_dir': str(truth)}

    class FakeEvaluator:
        def __init__(self, **kw):
            pass

        def run_evaluation(self, **kw):
            return None, {'num_devices': 0, 'num_comparisons': 0,
                          'error': 'countscompare.txt not found'}

    monkeypatch.setattr(rx, 'SimulationEvaluator', FakeEvaluator)
    assert r.run_evaluation() is None


@pytest.mark.smoke
def test_estimator_feedback_skips_failed_runs(tmp_path):
    from estimators.demand_estimator import load_experiment_feedback
    import os
    import time

    root = tmp_path / 'experiments'
    good, bad = root / 'good', root / 'bad'
    for d, status in ((good, 'completed'), (bad, 'failed')):
        d.mkdir(parents=True)
        (d / 'experiment_summary.json').write_text(
            json.dumps({'simulation_status': status}))
    # The failed run is the newest one.
    now = time.time()
    os.utime(good / 'experiment_summary.json', (now - 100, now - 100))
    os.utime(bad / 'experiment_summary.json', (now, now))

    fb = load_experiment_feedback({'_config_dir': str(tmp_path)})
    assert fb is not None
    assert Path(fb['experiment_dir']).name == 'good'

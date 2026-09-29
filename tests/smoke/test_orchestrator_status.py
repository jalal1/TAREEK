"""Smoke tests for MATSimOrchestrator wiring that needs no Java.

  * the experiment folder follows ``experiments_root`` (the runner writes the
    network and plans there; the orchestrator must look in the same place)
  * a MATSim process that exits with an error is reported as failed, not
    completed
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from matsim.orchestrator import MATSimOrchestrator


def _bare_orchestrator(tmp_path, returncode):
    """An orchestrator without its heavy __init__, with setup and run faked."""
    orch = MATSimOrchestrator.__new__(MATSimOrchestrator)
    orch.config = {'matsim': {'run_simulation': True}}
    orch.experiments_root = tmp_path
    exp = tmp_path / 'exp'
    exp.mkdir()
    orch.setup_experiment = lambda **kw: {'paths': {'experiment': str(exp)}}
    orch.run_experiment = lambda path, blocking=True: SimpleNamespace(returncode=returncode)
    return orch


@pytest.mark.smoke
def test_failed_matsim_process_is_reported_as_failed(tmp_path):
    meta = _bare_orchestrator(tmp_path, returncode=1).create_and_run_experiment(
        experiment_id='exp', generate_network=False, run_simulation=True)
    assert meta['simulation_status'] == 'failed'
    assert meta['matsim_return_code'] == 1


@pytest.mark.smoke
def test_successful_matsim_process_is_reported_as_completed(tmp_path):
    meta = _bare_orchestrator(tmp_path, returncode=0).create_and_run_experiment(
        experiment_id='exp', generate_network=False, run_simulation=True)
    assert meta['simulation_status'] == 'completed'
    assert 'matsim_return_code' not in meta


@pytest.mark.smoke
def test_experiment_directory_follows_experiments_root(tmp_path):
    orch = MATSimOrchestrator.__new__(MATSimOrchestrator)
    orch.config = {}
    orch.experiments_root = tmp_path / 'custom_root'
    path = orch.create_experiment_directory('my_run')
    assert Path(path) == tmp_path / 'custom_root' / 'my_run'
    assert Path(path).is_dir()

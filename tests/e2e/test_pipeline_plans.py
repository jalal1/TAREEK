# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end smoke: run the real pipeline through plan + counts generation.

Marker: e2e (needs data/db/trafficsim1.2.duckdb).

This drives the actual ExperimentRunner on the minimal one-county fixture
config with --skip-simulation, then asserts the generated plans.xml is valid
and non-trivial. It is the "is the system still working after a bug fix"
check for everything up to (but not including) the MATSim JVM run.

Output is redirected to a temp experiments root, so a test run never touches
the real ./experiments dir or experiment_comparison.csv.
"""

import xml.etree.ElementTree as ET

import pytest

from run_experiment import ExperimentRunner


@pytest.mark.e2e
def test_pipeline_generates_valid_plans(smoke_config_path, tmp_experiments_root, require_db):
    runner = ExperimentRunner(
        config_path=smoke_config_path,
        experiment_id="e2e_plans",
        experiments_root=tmp_experiments_root,
    )

    runner.run(skip_simulation=True)

    exp_dir = tmp_experiments_root / "e2e_plans"
    plans_path = exp_dir / "plans.xml"
    network_path = exp_dir / "network.xml"

    # Files exist
    assert plans_path.exists(), f"plans.xml was not generated at {plans_path}"
    assert network_path.exists(), f"network.xml was not generated at {network_path}"

    # plans.xml is valid and non-trivial
    assert plans_path.stat().st_size > 0, "plans.xml is empty"
    root = ET.parse(plans_path).getroot()
    assert root.tag == "population", f"unexpected root tag: {root.tag!r}"

    persons = root.findall("person")
    assert len(persons) > 0, "plans.xml contains no <person> entries"

    # Reuse the runner's own structural validators as a second check.
    assert runner._validate_plans_file(plans_path) is True
    assert runner._validate_network_file(network_path) is True


@pytest.mark.e2e
def test_pipeline_does_not_touch_real_experiments(
    smoke_config_path, tmp_experiments_root, require_db, repo_root
):
    """Confirm the experiments_root override actually redirects output."""
    runner = ExperimentRunner(
        config_path=smoke_config_path,
        experiment_id="e2e_isolation",
        experiments_root=tmp_experiments_root,
    )
    runner.run(skip_simulation=True)

    # The redirected dir got the output...
    assert (tmp_experiments_root / "e2e_isolation").exists()
    # ...and nothing leaked into the real experiments dir under this id.
    assert not (repo_root / "experiments" / "e2e_isolation").exists()

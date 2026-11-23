# SPDX-License-Identifier: GPL-3.0-or-later
"""Full end-to-end smoke incl. one MATSim iteration.

Marker: e2e_matsim (needs DuckDB + Java + the MATSim jar).

The slowest test: it runs the entire pipeline AND launches MATSim for a single
iteration (lastIteration=1 in the fixture config), confirming the JVM / config
/ network / plans wiring actually executes. Output is redirected to a temp
experiments root.

Run explicitly:  pytest -m e2e_matsim
"""

import pytest

from run_experiment import ExperimentRunner


@pytest.mark.e2e_matsim
def test_pipeline_runs_one_matsim_iteration(
    smoke_config_path, tmp_experiments_root, require_db, require_java
):
    runner = ExperimentRunner(
        config_path=smoke_config_path,
        experiment_id="e2e_matsim",
        experiments_root=tmp_experiments_root,
    )

    metadata = runner.run(skip_simulation=False)

    # The orchestrator reports completion.
    assert metadata.get("simulation_status") == "completed", (
        f"simulation did not complete: {metadata.get('simulation_status')!r}"
    )

    exp_dir = tmp_experiments_root / "e2e_matsim"
    output_dir = exp_dir / "output"

    # MATSim wrote *something* to its output directory.
    assert output_dir.exists(), f"MATSim output dir missing: {output_dir}"
    produced = list(output_dir.iterdir())
    assert produced, f"MATSim output dir is empty: {output_dir}"

    # A completed MATSim run always writes the output network back out.
    # (gzip-compressed by default.) Assert at least one recognizable artifact.
    names = {p.name for p in produced}
    expected_any = {"output_network.xml.gz", "output_network.xml", "output_plans.xml.gz"}
    assert names & expected_any, (
        f"no recognizable MATSim output artifact found; got: {sorted(names)}"
    )

## Summary

<!-- Briefly describe your contribution and why it is useful. -->

## Contribution type

<!-- Select the category that best describes this PR. -->

- [ ] **Experiment contribution** — share a completed TAREEK simulation under `examples/`
- [ ] Bug fix
- [ ] New feature / enhancement
- [ ] Refactoring / performance improvement
- [ ] Documentation
- [ ] Maintenance / dependencies / tooling
- [ ] Other (describe below)

## What changed?

<!-- For an experiment: describe the region, scenario, and key results.
For code: describe the behavior added, fixed, or changed. -->

-

## Experiment contribution checklist

<!-- Only complete this section if sharing an experiment. Follow examples/CONTRIBUTING.md. -->

- [ ] My experiment lives in `examples/<region>-<author>-<YYYYMMDD>/` (maintainers may omit `<author>`)
- [ ] I added a `README.md` describing the experiment, configuration, and results
- [ ] I included `report.html` generated using `python scripts/experiment_report.py experiments/<experiment-id> --no-pdf`
- [ ] I included `config_used.json` and any relevant small result CSVs / figures
- [ ] I did **not** commit large or regenerable inputs (such as OSM extracts or MATSim networks/plans)
- [ ] My contribution targets under 50 MB
- [ ] I replaced all live API keys and secrets in configuration and other files with placeholders
- [ ] I documented any external services or keys needed to reproduce the experiment
- [ ] I added my experiment to the index in `examples/README.md`
- [ ] Not applicable — this PR does not share an experiment

**Experiment details (if applicable):**

- Region:
- Scenario / purpose:
- Key results:
- Reproduction notes:

## Code contribution checklist

<!-- Complete relevant items for bug fixes, features, refactoring, and maintenance. -->

- [ ] I tested the change locally
- [ ] Relevant existing tests pass
- [ ] I added or updated tests where appropriate
- [ ] I updated documentation where behavior or setup changed
- [ ] I verified any affected webapp UI / API behavior
- [ ] I verified exported JSON and simulation-engine compatibility if configuration behavior changed
- [ ] I ran an experiment or relevant smoke test if simulation behavior changed
- [ ] Not applicable — this PR only contributes an experiment or documentation

**Testing commands / results:**

<!-- Include the commands you ran, manual steps, and relevant output. -->

## Evidence

<!-- Add before/after screenshots for UI changes, reproduction steps for bug fixes,
or report links, plots, and metrics for experiments. -->

## Related issues

<!-- Example: Closes #123 -->

## Additional notes

<!-- Breaking changes, new dependencies, limitations, follow-up work, etc. -->

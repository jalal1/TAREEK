## Summary

<!-- Briefly describe your contribution and why it is useful. -->

## Contribution type

<!-- Select the category that best describes this PR. -->

- [ ] **Experiment preset** — add `examples/<id>/` (only `README.md`, `config_used.json`, `config.xml`) for an experiment whose full results are in [TAREEK-examples](https://github.com/jalal1/TAREEK-examples)
- [ ] Bug fix
- [ ] New feature / enhancement
- [ ] Refactoring / performance improvement
- [ ] Documentation
- [ ] Maintenance / dependencies / tooling
- [ ] Other (describe below)

## License agreement and sources

<!-- Required for every pull request, also for experiment contributions. -->

- [ ] I signed the [Contributor License Agreement](https://github.com/jalal1/TAREEK/blob/main/CLA.md). If this is my first pull request, I posted the signature comment from [CONTRIBUTING.md](https://github.com/jalal1/TAREEK/blob/main/CONTRIBUTING.md#how-to-sign-the-cla) on it.
- [ ] I wrote this code myself, or I gave the source and license of each part that I did not write.

## What changed?

<!-- For an experiment: describe the region, scenario, and key results.
For code: describe the behavior added, fixed, or changed. -->

-

## Experiment preset checklist

<!-- Share the full results of an experiment (report, figures, data) in TAREEK-examples
(https://github.com/jalal1/TAREEK-examples), with its own pull request and checklist.
Complete this section only if this PR adds the small preset folder to examples/. -->

- [ ] The full results of my experiment are in TAREEK-examples (link: )
- [ ] My folder is `examples/<region>-<author>-<YYYYMMDD>/`, with the same name as in TAREEK-examples (maintainers may omit `<author>`)
- [ ] The folder has only `README.md`, `config_used.json` and `config.xml`
- [ ] The first line of `README.md` links to the full results in TAREEK-examples, before the title
- [ ] I replaced all live API keys and secrets in the configuration files with placeholders
- [ ] I added my experiment to the table in `examples/README.md`
- [ ] Not applicable — this PR does not add an experiment preset

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

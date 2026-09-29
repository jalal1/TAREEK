# Tests

Three tiers, gated by pytest markers. Plain `pytest` runs only the fast
`smoke` tier (see `addopts` in `pyproject.toml`), so a checkout without the
DuckDB / Java stays green.

| Command | Tier | Needs | Speed | Use |
|---|---|---|---|---|
| `pytest` | `smoke` | nothing | seconds | after every bug fix / commit |
| `pytest -m e2e` | `e2e` | `data/db/trafficsim1.2.duckdb` | minutes | before pushing pipeline changes |
| `pytest -m e2e_matsim` | `e2e_matsim` | DuckDB + Java + jar | many minutes | when touching MATSim wiring |
| `pytest -m ""` | all | all of the above | slow | full sweep (fails loudly if deps missing) |

## What each tier covers

- **`smoke/`** — every first-party module imports (auto-discovered via
  `walk_packages`, so new modules are covered with no edits), the real and
  fixture configs validate, coordinate math, and small pure-logic helpers.
  Includes `test_fha_perdirection.py`: link-bearing math, bearing-based
  travel_dir→link assignment (antiparallel pairing + missing-antiparallel
  drop), and the evaluator's countscompare.txt reader.
  Includes `test_person_first_demand.py`: the survey person-day loaders (NHTS,
  TBI), the survey-month window and trip filter, the demand budget helpers and
  `compute_demand_budget()` end to end (no DB, no ACS), and the validator
  rules for `person_file`, `survey_months` and the demand knobs.
- **`e2e/`** — runs the real `ExperimentRunner` on `fixtures/config_smoke.json`
  (one county, tiny scaling, `--skip-simulation`) and asserts `plans.xml` /
  `network.xml` are valid and non-trivial.
- **`e2e_matsim`** — same, plus one MATSim iteration; asserts the run completes
  and writes output artifacts.

## Conventions for new tests

- **Missing heavy deps fail loudly** (not skip): use the `require_db` /
  `require_java` fixtures.
- **Never write to the real `experiments/`**: pass `experiments_root=` (the
  `tmp_experiments_root` fixture) to `ExperimentRunner`.
- **Shared inputs** live in `tests/fixtures/`.
- **Future step tests** (per-stage: network, counts, plans in isolation) should
  go in a new `tests/steps/` dir, reuse `tests/fixtures/`, and get their own
  marker registered in `pyproject.toml`.

## Note on the `code` shadowing guard

`conftest.py` restores the stdlib `code` module at import time. A sibling
working directory (`E:\projects\code`) is a package named `code` that otherwise
shadows the stdlib and crashes pytest's debugger plugin. Leave that guard in
place.

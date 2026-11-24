# Simulation Config Wizard

A web-based step-by-step wizard for building MATSim simulation configuration files.

## Prerequisites

- Python 3.9+ with the project's `.venv` activated
- Required packages: `fastapi`, `uvicorn`, `geopandas`, `requests`

## Setup

1. **Install dependencies** (from project root):

   ```bash
   .venv/Scripts/pip install fastapi "uvicorn[standard]"
   ```

   (`geopandas` and `requests` should already be installed in the project venv.)

2. **Ensure county shapefile exists** at `data/counties/cb_2022_us_county_500k.shp`.
   If missing, the server will auto-download it on first startup from the Census Bureau.

## Running

From the `webapp/` directory:

```bash
cd webapp
../.venv/Scripts/python run.py
```

The server starts at **http://localhost:8000**.

## First Startup

On first launch, the backend will:
1. Convert the county shapefile to simplified GeoJSON
2. Fetch county population data from the Census API

These are cached to `data/counties/counties.geojson` and `data/counties/county_population.json` and reused on subsequent starts.

## Structure

```
webapp/
  backend/
    main.py              # FastAPI routes, county data, static hosting
    config_service.py    # Configuration loading, migrations, validation/export
    preset_service.py    # Registered experiments and public preset metadata
    requirements.txt     # Backend dependencies
  frontend/
    index.html           # Main wizard page
    css/style.css        # Design system (single stylesheet)
    js/app.js            # Wizard logic, map, form state, export
    js/config-state.js   # Shared configuration, snapshots and field paths
  run.py                 # Entry point (uvicorn launcher)
```

## Wizard Panels

1. **Select Region** — Select a regional experiment from a map pin or customize counties on the map.
2. **Surveys** — Review survey weights and regional input paths on the execution host.
3. **Transportation Modes** — Enable/disable car, bus, rail, walk, bike with per-mode settings.
4. **Transit** — GTFS feed settings and pt2matsim mapping parameters.
5. **Travel Demand** — Scaling factor, activity chains, non-work trip purposes.
6. **Time & Duration** — Activity duration constraints, time model settings.
7. **Simulation** — MATSim iterations, capacity factors, traffic counts, evaluation settings.
8. **Review & Export** — See the values you changed and a short "Check before you run" list
    (data folder, CPU/memory values that do not fit this computer, removed credentials),
    then download the complete `config.json`. Validation runs automatically when exporting.

The selected experiment's complete configuration stays in memory. Controls update
only their corresponding fields; freight, MATSim settings, survey roles,
and other unexposed parameters survive export. Changing the starting configuration
replaces current settings after confirmation if there are edits. Fields not shown
in the wizard are preserved in the exported JSON and can be edited there.
Credential keys, authenticated URLs, runtime fields, and metadata are redacted
from review values. Invalid wizard inputs block export.

Export sends the current complete configuration to `/api/export`, which validates
and returns the JSON to download. The wizard starts with baseline settings but
no counties or experiment selected. Selecting an example replaces its data folder (a path on the server where it
was run) with the local one from `config/config_local.json` (`../data`, the
repository's `data/` folder when `config.json` is saved in `config/`). Change
`data_dir` in `config.json` if your data is in a different folder. CPU and
memory values are in their wizard sections, with the limits of this computer. Input-file availability and machine readiness remain separate
execution-host checks.

The final step validates and exports `config.json` for `run_experiment.py`; the
wizard does not execute simulations. Source examples and the maintained baseline
are never written by the frontend. The frontend has no Node installation or build step.

## Adding an Experiment to the Map

Experiments are found automatically. There is no list to edit.

1. Add the experiment folder under `examples/`, for example
   `examples/myregion-20261117/`. It must contain:
   - `config_used.json`: the engine configuration. Its parameters are applied
     when the user picks the experiment. It must pass the backend's structural
     validation.
   - `config.xml`: the MATSim configuration of the run. A folder without it is
     not shown on the map.
2. Optional but recommended: a `README.md` whose first line is a title such as
   `# My Region, ST experiment — 2026-11-17`. The text before ` experiment` or
   the first ` — ` is the region name. The first paragraph is the description.
   Without a README, the region name comes from the folder name (`Myregion`).
3. Refresh the page (restart the backend if it does not reload).

The full results of an experiment (report, figures and data) go in the
[TAREEK-examples](https://github.com/jalal1/TAREEK-examples) repository, not in `examples/`. See its
[CONTRIBUTING.md](https://github.com/jalal1/TAREEK-examples/blob/main/CONTRIBUTING.md). Put the link to the full
results in a line before the README title, so that it does not change the
region name or the description.

The backend derives the rest:

- **Pin location**: the population-weighted center of the counties in
  `region.counties`, from the county data the map already uses. MATSim
  `config.xml` cannot give a location: it holds only `coordinateSystem`
  (a UTM zone, which is a 6° longitude band). If no county is known, the
  experiment gets no pin.
- **Button label**: the main survey (the first one with a weight above zero)
  and the date from the folder name, for example `NHTS (2026-11-17)`.
- **Grouping**: experiments with the same region name share one pin, with one
  button for each experiment in its popup.

For developer architecture, state flow, API contracts, and testing guidance, see
[`DOCS/WEBAPP_GUIDE.md`](DOCS/WEBAPP_GUIDE.md).

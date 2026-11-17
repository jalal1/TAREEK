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
8. **Review & Export** — Compare user edits with the normalized starting config,
    download the complete `config.json`, and see export diagnostics. Validation
    runs automatically when exporting; there is no separate validation action.

The selected experiment's complete configuration stays in memory. Controls update
only their corresponding fields; freight, MATSim settings, survey roles,
and other unexposed parameters survive export. Changing the starting configuration
replaces current settings after confirmation if there are edits. Fields not shown
in the wizard are preserved in the exported JSON and can be edited there.
Credential keys, authenticated URLs, runtime fields, and metadata are redacted
from review values. Invalid wizard inputs block export.

Export sends the current complete configuration to `/api/export`, which validates
and returns the JSON to download. The wizard starts with baseline settings but
no counties or experiment selected. Selecting an example shows a brief hardware
notice. Input-file availability and machine readiness remain separate
execution-host checks.

The final step validates and exports `config.json` for `run_experiment.py`; the
wizard does not execute simulations. Source examples and the maintained baseline
are never written by the frontend. The frontend has no Node installation or build step.

## Adding an Experiment to the Map

1. Add the experiment configuration at
   `examples/myregion-20261117/config_used.json` (relative to the repository root).
   The configuration must pass the backend's structural validation.
2. Add an entry to `PRESETS` in [`backend/preset_service.py`](backend/preset_service.py):

   ```python
   'myregion-20261117': (
       'My Region — NHTS',
       'My Region',
       'Example experiment description.',
       (43.07, -89.40),
   ),
   ```

   The key must match the example folder name exactly. The tuple contains the
   display name, region name, description, and marker coordinates in
   `(latitude, longitude)` order.
3. Let the development server reload (or restart the backend), then refresh
   the page. The frontend fetches the registered experiments automatically;
   no frontend code changes are needed.

A new region name creates a new marker. Reusing an existing region name adds
another experiment button to that marker's popup. Use the same region text and
coordinates for experiments that share a marker. Adding a folder under
`examples` alone does not register it with the map.

For developer architecture, state flow, API contracts, and testing guidance, see
[`DOCS/WEBAPP_GUIDE.md`](DOCS/WEBAPP_GUIDE.md).

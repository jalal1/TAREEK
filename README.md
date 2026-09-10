# TAREEK

An agent-based travel demand model that generates synthetic populations and activity plans for [MATSim](https://matsim.org/) traffic simulations. Given a set of US counties, it builds a complete simulation from census data, survey trips, transit feeds, and road networks.

For architecture details, extending the system, and contributor guidance, see the [Technical Report](TECHNICAL_REPORT.md).

## Quick Start

### 1. Prerequisites

- Python 3.12+
- Java 17+ (for MATSim)
- `osmium-tool` (required for network generation; see [docs/osm-tools-installation.md](docs/osm-tools-installation.md))

### 2. Setup

```bash
git clone https://github.com/YOUR_USERNAME/TAREEK.git
cd TAREEK

python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure

`config/config_local.json` is ready to run as-is. To model a different area, update the `counties` field with FIPS GEOIDs (2-digit state + 3-digit county) — find codes at [census.gov](https://www.census.gov/library/reference/code-lists/ansi.html). Example configs for various cities are in `config/USA/`.

#### Optional API keys

The system runs without these, but you may see warnings in the logs and missing data (no ACS calibration; certain transit feeds skipped). Both are **free**:

| Key | Where to register | What it's for | Where to put it in `config.json` |
|---|---|---|---|
| Census API key | https://api.census.gov/data/key_signup.html | Fetches ACS commute data (B08301, B08303) used to calibrate mode shares | `data.census_api_key` |
| WMATA API key | https://developer.wmata.com/ | Authenticates GTFS downloads for feeds that require it (e.g., DC Metro) | `gtfs.api_keys["wmata.com"]` |

Replace the placeholder values (`YOUR_CENSUS_API_KEY_HERE`, `YOUR_WMATA_API_KEY`) in your config file with the issued keys. The WMATA key is only needed if your region pulls a feed hosted on `wmata.com`; add other domain keys under `gtfs.api_keys` the same way if needed.

### 4. Run

```bash
python run_experiment.py --config config/config_local.json
```

Options:

| Flag | Description |
|---|---|
| `--config` | Path to config JSON (required) |
| `--experiment-id` | Custom experiment name (optional, auto-generated) |
| `--skip-simulation` | Generate plans only, don't run MATSim |

Output goes to `experiments/<experiment-id>/`.

---

## Config Wizard (Web UI)

Instead of editing JSON manually, you can use the Config Wizard to build a config file for any county in the US through an interactive web interface. Select counties on a map, configure modes, set scaling factors, and export a ready-to-use `config.json`.

[Demo](https://www.youtube.com/watch?v=Vlc4IO8HXN4)

```bash
cd webapp
python run.py
```

Opens at **http://localhost:8000**. See [webapp/README.md](webapp/README.md) for details.

Once the wizard generates your `config.json`, place it in the `config/` directory and run the experiment from the command line:

```bash
python run_experiment.py --config config/config.json
```

> **Coming soon:** Running simulations directly from the web app.

---

## Project Structure

```
TAREEK/
  run_experiment.py          # Main entry point
  config/
    USA/                     # Example configs for different cities
  data/
    db/                      # DuckDB database with reference data
    counties/                # US county shapefiles
    nhts/                    # NHTS survey data (included)
    FHA_counts/              # FHA traffic counts (included)
    evaluation/              # Ground-truth counts for validation (region-specific)
  data_sources/              # Survey and counts data loaders
  models/                    # Plan generation, OD matrices, mode choice
  matsim/                    # Network generation, MATSim runner, evaluation
  utils/                     # DB manager, logging, spatial utilities
  webapp/                    # Optional web visualization
```

---

## License

Copyright (C) 2026 TAREEK Contributors

This program is free software; you can redistribute it and/or modify
it under the terms of the [GNU General Public License](LICENSE) as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

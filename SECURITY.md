# Security policy

## Report a security problem

Do not report a security problem in a public issue, pull request, or
discussion. Report it privately with
[GitHub private vulnerability reporting](https://github.com/jalal1/TAREEK/security/advisories/new).
If you cannot use GitHub, contact the maintainer through
[jalal1.github.io](https://jalal1.github.io/).

Include this data in your report:

- What you did, and what occurred.
- The TAREEK commit that you use (`git rev-parse --short HEAD`). TAREEK has
  no release numbers.
- Your operating system, your Python version, and your Java version.
- A small config file or input that shows the problem, if you have one.

Do not send real API keys, passwords, or private data. A made-up example is
sufficient.

The maintainer replies to each report. We try to fix a confirmed problem
quickly. Please give us time to fix the problem before you tell other people
about it.

## Supported versions

Only the latest commit on the `main` branch gets fixes. Before you report a
problem, make sure that it also occurs on the latest `main`.

## What is a security problem

- A config file, a survey file, a GTFS feed, or downloaded map data that
  causes TAREEK to run code. Java (MATSim and pt2matsim) and the OSM tools
  that TAREEK starts on purpose are not in this group.
- An input or a web app request that causes TAREEK to read or write files
  outside the project folder and the folders in your config.
- TAREEK sends an API key to a service that the key is not for, or writes a
  key into a log, a report, or `config_used.json` in a way that the
  documentation does not tell you about.
- TAREEK sends data to a service that is not in the list below.

## Network use

TAREEK uses the network to get public data. The code uses these services:

| Part | Service | What for |
|---|---|---|
| Pipeline | OpenStreetMap data from Geofabrik (`download.geofabrik.de`) and Overpass API mirrors (`overpass-api.de`, `overpass.kumi.systems`, `overpass.private.coffee`, `overpass.openstreetmap.ru`) | Road network and points of interest |
| Pipeline | U.S. Census Bureau (`api.census.gov`, `www2.census.gov`, and LODES files through the `pygris` library) | Population, commute data, county boundaries, home and work locations. Sends `data.census_api_key` if you set it. |
| Pipeline | Mobility Database catalog (`files.mobilitydatabase.org`) and the GTFS feed servers that it lists | Transit schedules. Sends a key from `gtfs.api_keys` only to the domain that the key is for. |
| Pipeline | FHWA HPMS data on ArcGIS Online (`services2.arcgis.com`) | Truck shares and road volumes for freight |
| Web app (server) | U.S. Census Bureau (`www2.census.gov`, `api.census.gov`) | County boundaries and population for the map |
| Web app (browser) | OpenStreetMap tiles (`tile.openstreetmap.org`), `unpkg.com` (Leaflet), `fonts.googleapis.com` (font) | Background map and page assets. These services can see your IP address and the map area that you look at. |

The pipeline sends a `User-Agent` that names TAREEK to the Overpass API.

The current code does not read the `.env` file and does not call an AI model
service. The file `.env.example` is for AI agent code that is not in this
repository now.

## Known limits

- The config wizard web app (`webapp/run.py`) has no login. It listens on all
  network interfaces (`0.0.0.0`, port 8000). Any person who can connect to
  that port can use it. Run it only on a computer and a network that you
  trust.
- TAREEK writes your config, with your API keys, to
  `experiments/<id>/config_used.json`. Remove the keys before you share an
  experiment. See [CONTRIBUTING.md in TAREEK-examples](https://github.com/jalal1/TAREEK-examples/blob/main/CONTRIBUTING.md).

## What is not a security problem

Report these items as usual
[issues](https://github.com/jalal1/TAREEK/issues):

- A crash, a hang, or too much memory use from a bad config or a very large
  region, if it does not cause one of the problems above.
- Data that goes to the services in the list above.
- A problem in MATSim, pt2matsim, or a Python library. Report it to that
  project. Tell us if TAREEK must change because of it.

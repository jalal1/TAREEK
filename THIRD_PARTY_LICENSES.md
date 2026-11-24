# Third-party software and data

This repository contains some files that other people made. The TAREEK
license does not apply to these files. Each file keeps its own license, and
the Contributor License Agreement does not change it.

TAREEK installs its Python libraries with `pip` from `requirements.txt` and
`webapp/backend/requirements.txt`. These libraries are not in this
repository, and each one has its own license.

## Programs in this repository

### MATSim

| Item | Value |
|---|---|
| File | `matsim/matsim_25/matsim_25.jar` |
| Version | MATSim 2025.0 (`org.matsim:matsim:2025.0`) |
| License | GNU General Public License, version 2 or (at your option) any later version (`GPL-2.0-or-later`) |
| Source code | https://github.com/matsim-org/matsim-libs/tree/2025.0 |
| Project | https://www.matsim.org/ |

### pt2matsim

| Item | Value |
|---|---|
| File | `matsim/pt2matsim/pt2matsim-25.2-shaded.jar` |
| Version | pt2matsim 25.2 (`org.matsim:pt2matsim:25.2`) |
| License | GNU General Public License, version 2 or (at your option) any later version (`GPL-2.0-or-later`) |
| Source code | https://github.com/matsim-org/pt2matsim/tree/v25.2 |

Both jar files also contain libraries from other projects, for example
GeoTools, Hibernate, Jackson, and GlassFish. These libraries have their own
licenses. The license files are in the `META-INF/` folder of each jar file.

TAREEK starts MATSim and pt2matsim as separate Java programs. It does not
link its own code to them.

### DuckDB command-line program

| Item | Value |
|---|---|
| File | `data/db/duckdb.exe` |
| Version | DuckDB v1.1.3 |
| License | MIT License |
| Source code | https://github.com/duckdb/duckdb/tree/v1.1.3 |

```text
Copyright 2018-2024 Stichting DuckDB Foundation

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Data in this repository

| Data | Files | Source | License |
|---|---|---|---|
| County boundaries | `data/counties/` | U.S. Census Bureau, cartographic boundary files 2022 | U.S. Government work, public domain |
| County population | `data/counties/county_population.json` | U.S. Census Bureau, American Community Survey | U.S. Government work, public domain |
| Traffic counts | `data/FHA_counts/` | Federal Highway Administration (FHWA), Travel Monitoring Analysis System | U.S. Government work, public domain |
| National Household Travel Survey | `data/nhts/csv/` | FHWA, NHTS 2022 public-use files | U.S. Government work, public domain |
| Twin Cities Travel Behavior Inventory 2023 | `data/surveys/twincities_tbi_2023/` | Metropolitan Council | Public domain. See the [README](data/surveys/twincities_tbi_2023/README.md). |
| Custom count stations and volumes | `data/evaluation/` | Minnesota Department of Transportation (MnDOT) traffic counts, Twin Cities | Public government data. No license is stated. |
| Birmingham local survey | `data/surveys/birmingham_al_local/` | Jalal Khalil | MIT License. See the [README](data/surveys/birmingham_al_local/README.md). |

## Results that use OpenStreetMap data

The road networks in the TAREEK runs come from OpenStreetMap. The example
results in [TAREEK-examples](https://github.com/jalal1/TAREEK-examples) (for example `report.html`, `counts.xml`,
and `matched_devices.csv`) and the example figures in `docs/images/` use
these networks. TAREEK-examples has its own license file and third-party
notices.

Map data © OpenStreetMap contributors, available under the
[Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/).
See https://www.openstreetmap.org/copyright.

If you publish results from TAREEK, give the same credit.

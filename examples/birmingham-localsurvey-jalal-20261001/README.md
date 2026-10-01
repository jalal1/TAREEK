# Birmingham, AL — local survey (first run) — Jalal, 2026-10-01

> **This is the first run with the Birmingham custom local survey. More tuning is needed.**
> The demand shape comes from a **local Birmingham travel survey** (`bham_local`, 451 people,
> [published online](https://almt0.github.io/background_traffic/index.html)), not from NHTS.
> NHTS 2022 still sets *how many* people travel (person-days), because the local survey
> has no no-travel days and no children. Every other setting is the same as in the NHTS
> example of the region, [`birmingham-jalal-20260928`](../birmingham-jalal-20260928/).
> The knobs were tuned for NHTS, not for this survey.

A full Tareek run for Jefferson and Shelby counties, compared against FHA directional
traffic counts. It is also the first run that uses **survey roles**: each survey entry can
say which jobs it does (see [Survey roles](#survey-roles)).

- **Experiment ID:** `bham_local_hermes_w12_nw20_fr03_10iter`
- **Survey:** **bham_local (weight 1)** for chains, times and modes · NHTS 2022 for person-days only (`weight 0`, `roles: {person_days: 1}`)
- **Region:** 2 counties — Jefferson (01073), Shelby (01117)
- **Scaling factor:** `0.25` (25% population sample) · **MATSim iterations:** 10 · **Mobsim:** `hermes` · **Seed:** 42
- **Demand:** person-first; `work_scaling_multiplier` 1.2, `nonwork_trip_share` 2.0 (same as the NHTS example)
- **Freight:** on, boundary trucks from HPMS, `demand_scale` 0.3
- **Runtime:** 66 min total (plans 13 min, MATSim 44 min, evaluation 8 min) on a 32-CPU server

---

## Full report

**[`report.html`](report.html)** is the complete experiment report: the verdict, the demand
check against the local survey, the demand budget, the count validation, freight, and all the
evaluation figures. It is one self-contained file.

> **How to open it:** GitHub does not show HTML pages. Open [`report.html`](report.html) on
> GitHub, click **Download raw file**, then open the file in a web browser.

---

## The custom survey

The survey file is in the repository:
[`data/surveys/birmingham_al_local/`](../../data/surveys/birmingham_al_local/). Its README
describes the columns, the limits and the label mappings. The reader is
[`data_sources/bham_local_survey.py`](../../data_sources/bham_local_survey.py).

| Item | Value |
|---|---|
| Source | J. Khalil, [Two research works on transport simulation for Birmingham, AL](https://almt0.github.io/background_traffic/index.html) (MIT License); used in *Realistic Transport Simulation: Tackling the Small Data Challenge with Open Data*, IEEE BigData 2019 |
| Layout | one row per person, up to 13 trips per row, UTM 16N coordinates |
| Size | 443 rows, 1,129 trips; after cleaning 423 persons, 1,071 trips (2.53 trips per person) |
| Weights | none (every trip has weight 1) |
| Travel day | no date; all days are weekdays |
| Not in the survey | no-travel days, persons under 18, household ids |

What the survey cannot do, and how the run handles it:

- **Person-days.** Every respondent has at least one trip, and nobody is under 18. So the
  survey cannot say how many people stay at home, or how students aged 5-17 travel. NHTS
  2022 does this job alone.
- **OD matrix.** 1,071 trips are too few for a block-group OD matrix. The reader leaves the
  locations empty, as NHTS does, so the LODES / gravity matrices are used.
- **Rideshare.** 6.8% of the survey trips are Uber/Lyft or taxi. Birmingham enables only car,
  bus and walk, so these trips have no mode of their own in the model.

### Survey roles

```json
"surveys": [
  { "type": "bham_local", "year": "undated",
    "file": "surveys/birmingham_al_local/birmingham_al_local_survey.csv",
    "weight": 1 },
  { "type": "nhts", "year": "2022", "file": "nhts/csv/tripv2pub.csv",
    "person_file": "nhts/csv/perv2pub.csv",
    "weight": 0, "roles": { "person_days": 1 } }
]
```

A survey does up to five jobs: `person_days`, `chains`, `times`, `modes` and `od`.
`weight` applies to all of them, and `roles` overrides it per job. A survey that cannot do a
job is skipped for it. Resolved for this run:

| Job | bham_local | nhts |
|---|---:|---:|
| person_days | — (cannot) | 1.0 |
| chains | 1.0 | 0 |
| times | 1.0 | 0 |
| modes | 1.0 | 0 |
| od | — (no locations) | 0 |

### The survey against NHTS 2022 (weekdays)

| Quantity | bham_local | NHTS US | NHTS East South Central, metros 0.5-3 M |
|---|---:|---:|---:|
| Trips per travelling person | 2.53 | 2.80 | 2.71 |
| Days that start and end at Home | 57% | 85% | — |
| Work / Shopping / Dining (% of trips) | 22.0 / 23.8 / 8.0 | 15.2 / 20.6 / 6.5 | 19.5 / 20.6 / 5.7 |
| Social / School (% of trips) | 2.1 / 3.8 | 8.1 / 7.3 | 5.9 / 7.1 |
| Car / Rideshare / Walk / Bus (% of trips) | 88.4 / 6.8 / 2.6 / 1.9 | 85.1 / 0.5 / 7.0 / 1.2 | 91.4 / 0.0 / 1.9 / 1.0 |
| Departures 05-07 h / 07-09 h | 3.7% / 18.5% | 5.5% / 17.3% | 8.4% / 16.2% |
| Departures 19-22 h / 22-24 h | 9.2% / 2.4% | 8.2% / 1.6% | 6.0% / 1.7% |

The sample is not representative: 75% of respondents are female, 70% are aged 18-44, and
ride-hailing use is high.

---

## How to reproduce

This run used [`config_used.json`](config_used.json). To run it again:

```bash
# from the repository root, with the virtualenv activated
cp examples/birmingham-localsurvey-jalal-20261001/config_used.json config/bham_local.json
python run_experiment.py --config config/bham_local.json
```

Before you start, change these values in the config for your machine:

| Field | Value in this run | Change to |
|-------|-------------------|-----------|
| `data.data_dir` | server path | the `data/` folder of your clone |
| `matsim.heap_size_gb` | 70 | less than your RAM |
| `plan_generation.num_processes` | 30 | your CPU count, or less |

The first run reads the survey CSV into the `survey_trips` table (a few seconds). If you
change the reader, delete its rows (`DELETE FROM survey_trips WHERE source_type='bham_local'`)
so that the next run reads the file again.

The large files (`network.xml`, `plans.xml`, the MATSim `output/` folder) are **not** in
this folder. The run makes them again from the config. For the setup steps, see the
**[project README](../../README.md#quick-start)**. The API keys in the config are
**optional** — see [Optional API keys](#optional-api-keys).

---

## Headline results

| Metric | Value | Target | Status |
|---|---:|---|:--:|
| Overall volume (sim/obs) | **0.965** | 1.0 ± 0.10 | PASS |
| Volume level (iqr_mean) | **0.954** | 1.0 ± 0.10 | PASS |
| Per-station ratio CV | 0.746 | < 0.35 | CHECK |
| Correlation | 0.757 | > 0.85 | CHECK |
| % hourly counts GEH < 5 | 24.7 | > 85 | CHECK |
| MAE (vehicles/hour) | 470 | — | — |
| Stuck agents | 173 | — | — |

41 physical stations, 58 station-directions, 1,392 station-hours.

### Time of day

| Block | Hours | Observed | Simulated | Sim/Obs |
|---|---|---:|---:|---:|
| Night | 0-3 | 29,287 | 21,199 | **0.72** |
| Morning | 4-9 | 409,828 | 438,140 | **1.07** |
| Midday | 10-17 | 764,792 | 672,842 | **0.88** |
| Evening | 18-23 | 264,053 | 284,442 | **1.08** |

### Against the NHTS example (same stations)

> **Read this before you compare with [`birmingham-jalal-20260928`](../birmingham-jalal-20260928/).**
> The count set was rebuilt after that run (parallel-roadway counts): 41 stations here,
> 36 there. The road network is the same. The table below uses only the 1,152
> station-hours that both runs share, so it shows the effect of the survey alone.

| Metric (common station-hours) | NHTS example | This run |
|---|---:|---:|
| Overall volume (sim/obs) | 0.929 | 0.881 |
| Volume level (iqr_mean) | 0.887 | 0.843 |
| Per-station ratio CV | 0.735 | 0.739 |
| Correlation | 0.806 | 0.792 |
| % hourly counts GEH < 5 | 22.3 | 24.7 |
| Night / Morning / Midday / Evening | 0.35 / 1.09 / 0.88 / 0.88 | 0.63 / 0.98 / 0.80 / 0.98 |

Sim/obs per hour, common station-hours:

| Hour | 00 | 03 | 05 | 06 | 07-09 | 12-13 | 14-17 | 18-21 | 22-23 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NHTS example | 0.36 | 0.33 | 0.96 | 0.94 | 1.07-1.24 | 0.82-0.84 | 0.78-0.88 | 0.84-0.93 | 0.82-0.88 |
| This run | 0.56 | 1.21 | 0.44 | 0.60 | 1.08-1.24 | 0.78-0.79 | 0.72-0.78 | 0.94-1.02 | 1.07 |

- **Better:** night (0-1 h), evening (18-21 h close to 1.0), GEH < 5, fewer stuck agents.
- **Worse:** early morning (05-06 h; the survey has few departures before 07:00), afternoon
  (14-17 h), late evening now overshoots (22-23 h), total level, correlation.
- **Noise:** hour 03 (1.21) comes from about 6 survey trips at that hour.

### Demand against the survey

| Quantity | Simulated | bham_local | NHTS example (simulated) |
|---|---:|---:|---:|
| Trips per person per day | 2.86 | 2.50 | 2.83 |
| Trip length, median km | 4.86 | 6.02 | 5.71 |
| Car / walk / pt (% of trips) | 90.8 / 8.7 / 0.5 | 95.2 / 2.6 / 1.9 | 92.6 / 7.0 / 0.5 |
| Departures night / morning / midday / evening | 1.0 / 28.2 / 53.5 / 17.3 | 2.0 / 28.9 / 50.4 / 18.7 | 0.4 / 30.5 / 53.8 / 15.2 |

(The survey car share includes rideshare. The departure blocks are 0-3, 4-9, 10-17 and 18-23 h.)

The departure profile follows its own survey closely. The trip rate stays near NHTS,
because NHTS sets who travels.

---

## Known issues and next tuning steps

This run changes only the survey. The knobs and settings were tuned for NHTS. These points
need work before the local survey can replace NHTS for Birmingham:

1. **Chains that do not return home.** Only 57% of survey days start and end at Home, so 25%
   of the plans do not end at Home (11% with NHTS).
2. **School.** The survey is adults only, so "School" means college visits: the typical
   School stay is 2 h 55 (7 h with NHTS). Children aged 5-17 inherit it. NHTS should keep the
   `times` job for School, or students should get their own source.
3. **Early morning.** The survey has 3.7% of departures at 05-07 h (NHTS 5.5%), and the counts
   at 05-06 h fall to 0.44-0.60.
4. **Rideshare and walk.** The survey's 6.8% Uber/Lyft has no mode in the model. Walk rises to
   8.7% (survey 2.6%).
5. **Knobs.** `nonwork_trip_share` 2.0 and `work_scaling_multiplier` 1.2 were set for NHTS
   chains. Re-check them with a plans-only projection before the next MATSim run.
6. **Sample size.** 423 persons and no weights. Single hours with few survey trips (03 h) give
   lumpy departure shapes.

---

## MATSim count graphs

MATSim's own count graphs for iteration 10 are in [`graphs/`](graphs/). GitHub does not show
them. Download or clone the folder and open `graphs/start.html` in a browser.

## Evaluation figures

Selected figures are in [`evaluation/`](evaluation/): hourly bias and error, station ratios,
the 8 am and 5 pm highway heatmaps, departure and arrival profiles (demand and simulation),
and one count report per device in [`evaluation/device_reports/`](evaluation/device_reports/).
MATSim mode and score statistics and the iteration-10 `countscompare.txt` are in
[`matsim_output/`](matsim_output/).

---

## Optional API keys

`config_used.json` refers to external services. They are **optional**. The pipeline runs
without them, with warnings and some missing data (no live ACS age split and mode-share
calibration, and no `wmata.com` transit feed). The keys in this config are **redacted**
(`YOUR_..._KEY`).

| Field in config | Service | Register (free) |
|-----------------|---------|-----------------|
| `data.census_api_key` | U.S. Census API — ACS data | https://api.census.gov/data/key_signup.html |
| `gtfs.api_keys["wmata.com"]` | WMATA GTFS feed | https://developer.wmata.com/ |

The freight module reads the public HPMS service, which needs no key.

**Never commit real keys.**

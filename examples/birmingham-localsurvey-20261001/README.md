# Birmingham, AL — local survey (first run) — 2026-10-01

> **This is the first run with the Birmingham custom local survey. More tuning is needed.**
> The demand shape comes from a **local Birmingham travel survey** (`bham_local`, 451 people,
> [published online](https://almt0.github.io/background_traffic/index.html)), not from NHTS.
> NHTS 2022 still sets *how many* people travel (person-days), because the local survey
> has no no-travel days and no children. Every other setting is the same as in the NHTS
> example of the region, [`birmingham-20260928`](../birmingham-20260928/).
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
cp examples/birmingham-localsurvey-20261001/config_used.json config/bham_local.json
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

## Configuration

- [`config_used.json`](config_used.json) — the full Tareek config for this run
- [`config.xml`](config.xml) — the MATSim config that Tareek made
- [`counts.xml`](counts.xml) — the observed counts given to MATSim (41 stations, rebuilt with the parallel-roadway counts)
- [`matched_devices.csv`](matched_devices.csv) — FHA count devices matched to network links
- [`demand_budget.json`](demand_budget.json) — the person-first demand budget from the NHTS person-days
- [`freight_summary.json`](freight_summary.json) — freight cordons, trip totals and checks
- [`od_matrix_diagnostics.json`](od_matrix_diagnostics.json) — checks on the work OD matrix
- [`experiment_summary.json`](experiment_summary.json) — the full machine-readable run summary
- [`experiment_20261001_180911.log`](experiment_20261001_180911.log) — the run log

### Key parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `data.surveys` | **bham_local = 1.0, NHTS 2022 = 0** (`person_days` 1) | see [Survey roles](#survey-roles) |
| `scaling_factor` (population) | **0.25** | 25% sample of the full population |
| MATSim iterations | **10** | innovation stops after iteration 8 |
| `controller.mobsim` | **hermes** | `hermes.endTime` 36:00:00 |
| `flowCapacityFactor` | 0.25 | equal to the scaling factor, copied to hermes |
| `storageCapacityFactor` | 0.30 | 1.2 × the flow factor, copied to hermes |
| `countsScaleFactor` | 4.0 | 1 / flowCapacityFactor |
| `work_scaling_multiplier` | **1.2** | calibration knob (tuned for NHTS) |
| `nonwork_trip_share` | **2.0** | calibration knob (tuned for NHTS) |
| `freight.demand_scale` | **0.3** | see [Freight](#freight) |
| `data.survey_months` | `regular` | Mar-May, Sep-Nov survey days |
| `counts.fha.month` | 10 | October 2024 counts |
| `chain_sampling_method` | `direct` | |
| `first_departure_source` | `first_of_day` | |
| `over_budget` | `resample` | |

All the other values are the same as in the NHTS example
[`birmingham-20260928`](../birmingham-20260928/).

### Scenario scale

| | |
|---|---|
| Total population (2 counties) | 893,851 |
| Agents simulated | 305,847 (87,170 work · 214,107 non-work · 4,570 freight) |
| Stuck agents | 173 |
| Network | 89,851 nodes · 204,379 links |
| Generated mode split (legs) | car 90.9% · walk 7.6% · pt 1.4% |

---

## Headline results

Simulated against observed link volumes at **41 physical count stations**
(58 directional counts, 1,392 station-hours). Values are MATSim's count comparison, the
average of iterations 1-10.

| Metric | Value | Target | Status |
|--------|------:|--------|:------:|
| **Overall volume (sim/obs)** | **0.965** | 1.0 ± 0.10 | PASS |
| Volume level (interquartile mean) | 0.954 | 1.0 ± 0.10 | PASS |
| Per-station ratio CV | 0.746 | < 0.35 | CHECK |
| Correlation (sim vs obs) | 0.757 | > 0.85 | CHECK |
| % hourly counts with GEH < 5 | 24.7% | > 85% | CHECK |
| MAE / RMSE | 470 / 704 veh/h | | |

The PASS values are not a like-for-like gain over the NHTS example: the count set changed.
See [Against the NHTS example](#against-the-nhts-example-same-stations).

### Time of day

| Block | Hours | Observed | Simulated | Sim/Obs |
|---|---|---:|---:|---:|
| Night | 0-3 | 29,287 | 21,199 | **0.72** |
| Morning | 4-9 | 409,828 | 438,140 | **1.07** |
| Midday | 10-17 | 764,792 | 672,842 | **0.88** |
| Evening | 18-23 | 264,053 | 284,442 | **1.08** |

**Final iteration.** At iteration 10 alone (from its events) the total is 1.06, the
morning is 1.19 and the evening is 1.17, because the walk and pt plans made during
innovation are dropped at iteration 9.

### Against the NHTS example (same stations)

> **Read this before you compare with [`birmingham-20260928`](../birmingham-20260928/).**
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

### Freight

Measured from the events of iteration 10 on the count links
([`evaluation/freight_share_it10.txt`](evaluation/freight_share_it10.txt)):

| Block | Freight share of simulated volume | Ratio | Ratio without freight |
|-------|----------------------------------:|------:|----------------------:|
| Night | 21.5% | 0.77 | 0.60 |
| Morning | 2.5% | 1.19 | 1.16 |
| Midday | 3.5% | 0.97 | 0.94 |
| Evening | 3.7% | 1.17 | 1.13 |
| **All** | **3.5%** | **1.06** | **1.03** |

Freight is the same as in the NHTS example (4,570 boundary truck trips) and is 3.7% of the
observed volume. The night share is lower than in the NHTS example (38%), because this run
puts more cars on the road at night.

### Where the error is

| | |
|---|---|
| ![Station ratios](evaluation/station_ratio_dotplot.png) | ![Hourly error](evaluation/hourly_relative_error_box.png) |
| Sim/obs ratio per station, sorted | Signed relative error per hour, all stations |
| ![Hourly bias](evaluation/hourly_bias.png) | ![Departures and arrivals in the simulation](evaluation/dep_arr_by_activity_sim.png) |
| Mean relative error and mean bias (veh/h) per hour | Departures and arrivals per hour by activity, iteration 10 |

More figures are in [`evaluation/`](evaluation/): the 8 am and 5 pm highway heatmaps, the
count error maps at 07 h and 17 h, the activity durations, and the trip durations per hour.
The full set, with captions, is in [`report.html`](report.html).

Data: [`evaluation/volume_comparison.csv`](evaluation/volume_comparison.csv) (per hour,
per station) · [`evaluation/trip_timing_check.json`](evaluation/trip_timing_check.json)
· [`matsim_output/10.countscompare.txt`](matsim_output/10.countscompare.txt) (MATSim's
own count comparison) · [`matsim_output/`](matsim_output/) (mode and score statistics)

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

## Per-device count reports

Observed and simulated hourly profiles for each matched count direction
(`dir` = FHA direction code, `link` = matched network link). Click a thumbnail to see
it at full size. There are 54 reports for 58 directional counts: the 4 counts that merge
two FHA devices on one link (`000146` dir1 and dir5, `001381`, `001402`) have no
single-device report.

<table>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000114_1_linkid_14240.png"><img src="evaluation/device_reports/device_FHA_01_000114_1_linkid_14240.png" width="100%"></a><br><sub>AL 000114 dir1 (link 14240)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000114_5_linkid_57301.png"><img src="evaluation/device_reports/device_FHA_01_000114_5_linkid_57301.png" width="100%"></a><br><sub>AL 000114 dir5 (link 57301)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000115-p2_5_linkid_181728.png"><img src="evaluation/device_reports/device_FHA_01_000115-p2_5_linkid_181728.png" width="100%"></a><br><sub>AL 000115 (parallel road) dir5 (link 181728)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000115_1_linkid_14256.png"><img src="evaluation/device_reports/device_FHA_01_000115_1_linkid_14256.png" width="100%"></a><br><sub>AL 000115 dir1 (link 14256)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000115_5_linkid_81860.png"><img src="evaluation/device_reports/device_FHA_01_000115_5_linkid_81860.png" width="100%"></a><br><sub>AL 000115 dir5 (link 81860)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000116_1_linkid_176314.png"><img src="evaluation/device_reports/device_FHA_01_000116_1_linkid_176314.png" width="100%"></a><br><sub>AL 000116 dir1 (link 176314)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000116_5_linkid_18294.png"><img src="evaluation/device_reports/device_FHA_01_000116_5_linkid_18294.png" width="100%"></a><br><sub>AL 000116 dir5 (link 18294)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000117_1_linkid_62831.png"><img src="evaluation/device_reports/device_FHA_01_000117_1_linkid_62831.png" width="100%"></a><br><sub>AL 000117 dir1 (link 62831)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000117_5_linkid_159046.png"><img src="evaluation/device_reports/device_FHA_01_000117_5_linkid_159046.png" width="100%"></a><br><sub>AL 000117 dir5 (link 159046)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000118_1_linkid_66619.png"><img src="evaluation/device_reports/device_FHA_01_000118_1_linkid_66619.png" width="100%"></a><br><sub>AL 000118 dir1 (link 66619)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000118_5_linkid_76481.png"><img src="evaluation/device_reports/device_FHA_01_000118_5_linkid_76481.png" width="100%"></a><br><sub>AL 000118 dir5 (link 76481)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000119_1_linkid_141936.png"><img src="evaluation/device_reports/device_FHA_01_000119_1_linkid_141936.png" width="100%"></a><br><sub>AL 000119 dir1 (link 141936)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000119_5_linkid_155974.png"><img src="evaluation/device_reports/device_FHA_01_000119_5_linkid_155974.png" width="100%"></a><br><sub>AL 000119 dir5 (link 155974)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000122_1_linkid_76679.png"><img src="evaluation/device_reports/device_FHA_01_000122_1_linkid_76679.png" width="100%"></a><br><sub>AL 000122 dir1 (link 76679)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000122_5_linkid_76614.png"><img src="evaluation/device_reports/device_FHA_01_000122_5_linkid_76614.png" width="100%"></a><br><sub>AL 000122 dir5 (link 76614)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000123_1_linkid_62751.png"><img src="evaluation/device_reports/device_FHA_01_000123_1_linkid_62751.png" width="100%"></a><br><sub>AL 000123 dir1 (link 62751)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000123_5_linkid_176307.png"><img src="evaluation/device_reports/device_FHA_01_000123_5_linkid_176307.png" width="100%"></a><br><sub>AL 000123 dir5 (link 176307)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000129_1_linkid_62312.png"><img src="evaluation/device_reports/device_FHA_01_000129_1_linkid_62312.png" width="100%"></a><br><sub>AL 000129 dir1 (link 62312)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000129_5_linkid_175052.png"><img src="evaluation/device_reports/device_FHA_01_000129_5_linkid_175052.png" width="100%"></a><br><sub>AL 000129 dir5 (link 175052)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000134_1_linkid_79982.png"><img src="evaluation/device_reports/device_FHA_01_000134_1_linkid_79982.png" width="100%"></a><br><sub>AL 000134 dir1 (link 79982)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000134_5_linkid_79983.png"><img src="evaluation/device_reports/device_FHA_01_000134_5_linkid_79983.png" width="100%"></a><br><sub>AL 000134 dir5 (link 79983)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000148-p2_5_linkid_9208.png"><img src="evaluation/device_reports/device_FHA_01_000148-p2_5_linkid_9208.png" width="100%"></a><br><sub>AL 000148 (parallel road) dir5 (link 9208)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000148_1_linkid_26653.png"><img src="evaluation/device_reports/device_FHA_01_000148_1_linkid_26653.png" width="100%"></a><br><sub>AL 000148 dir1 (link 26653)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000148_5_linkid_24792.png"><img src="evaluation/device_reports/device_FHA_01_000148_5_linkid_24792.png" width="100%"></a><br><sub>AL 000148 dir5 (link 24792)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000422_3_linkid_98424.png"><img src="evaluation/device_reports/device_FHA_01_000422_3_linkid_98424.png" width="100%"></a><br><sub>AL 000422 dir3 (link 98424)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000422_7_linkid_98425.png"><img src="evaluation/device_reports/device_FHA_01_000422_7_linkid_98425.png" width="100%"></a><br><sub>AL 000422 dir7 (link 98425)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000426_1_linkid_175311.png"><img src="evaluation/device_reports/device_FHA_01_000426_1_linkid_175311.png" width="100%"></a><br><sub>AL 000426 dir1 (link 175311)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000426_5_linkid_175310.png"><img src="evaluation/device_reports/device_FHA_01_000426_5_linkid_175310.png" width="100%"></a><br><sub>AL 000426 dir5 (link 175310)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000701_3_linkid_48269.png"><img src="evaluation/device_reports/device_FHA_01_000701_3_linkid_48269.png" width="100%"></a><br><sub>AL 000701 dir3 (link 48269)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000701_7_linkid_16819.png"><img src="evaluation/device_reports/device_FHA_01_000701_7_linkid_16819.png" width="100%"></a><br><sub>AL 000701 dir7 (link 16819)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000717_1_linkid_202744.png"><img src="evaluation/device_reports/device_FHA_01_000717_1_linkid_202744.png" width="100%"></a><br><sub>AL 000717 dir1 (link 202744)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000717_5_linkid_62531.png"><img src="evaluation/device_reports/device_FHA_01_000717_5_linkid_62531.png" width="100%"></a><br><sub>AL 000717 dir5 (link 62531)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001382-p2_5_linkid_97471.png"><img src="evaluation/device_reports/device_FHA_01_001382-p2_5_linkid_97471.png" width="100%"></a><br><sub>AL 001382 (parallel road) dir5 (link 97471)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001382_5_linkid_97470.png"><img src="evaluation/device_reports/device_FHA_01_001382_5_linkid_97470.png" width="100%"></a><br><sub>AL 001382 dir5 (link 97470)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001383_5_linkid_30246.png"><img src="evaluation/device_reports/device_FHA_01_001383_5_linkid_30246.png" width="100%"></a><br><sub>AL 001383 dir5 (link 30246)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001384_1_linkid_79986.png"><img src="evaluation/device_reports/device_FHA_01_001384_1_linkid_79986.png" width="100%"></a><br><sub>AL 001384 dir1 (link 79986)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001401_5_linkid_78445.png"><img src="evaluation/device_reports/device_FHA_01_001401_5_linkid_78445.png" width="100%"></a><br><sub>AL 001401 dir5 (link 78445)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001461_1_linkid_193953.png"><img src="evaluation/device_reports/device_FHA_01_001461_1_linkid_193953.png" width="100%"></a><br><sub>AL 001461 dir1 (link 193953)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001461_5_linkid_154144.png"><img src="evaluation/device_reports/device_FHA_01_001461_5_linkid_154144.png" width="100%"></a><br><sub>AL 001461 dir5 (link 154144)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001462_1_linkid_139305.png"><img src="evaluation/device_reports/device_FHA_01_001462_1_linkid_139305.png" width="100%"></a><br><sub>AL 001462 dir1 (link 139305)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001463_1_linkid_185074.png"><img src="evaluation/device_reports/device_FHA_01_001463_1_linkid_185074.png" width="100%"></a><br><sub>AL 001463 dir1 (link 185074)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001464-p2_5_linkid_79988.png"><img src="evaluation/device_reports/device_FHA_01_001464-p2_5_linkid_79988.png" width="100%"></a><br><sub>AL 001464 (parallel road) dir5 (link 79988)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001464_5_linkid_139543.png"><img src="evaluation/device_reports/device_FHA_01_001464_5_linkid_139543.png" width="100%"></a><br><sub>AL 001464 dir5 (link 139543)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001465_5_linkid_19043.png"><img src="evaluation/device_reports/device_FHA_01_001465_5_linkid_19043.png" width="100%"></a><br><sub>AL 001465 dir5 (link 19043)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_021381-p2_5_linkid_203935.png"><img src="evaluation/device_reports/device_FHA_01_021381-p2_5_linkid_203935.png" width="100%"></a><br><sub>AL 021381 (parallel road) dir5 (link 203935)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_021382_1_linkid_203612.png"><img src="evaluation/device_reports/device_FHA_01_021382_1_linkid_203612.png" width="100%"></a><br><sub>AL 021382 dir1 (link 203612)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_021383_1_linkid_203621.png"><img src="evaluation/device_reports/device_FHA_01_021383_1_linkid_203621.png" width="100%"></a><br><sub>AL 021383 dir1 (link 203621)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_021384_5_linkid_203597.png"><img src="evaluation/device_reports/device_FHA_01_021384_5_linkid_203597.png" width="100%"></a><br><sub>AL 021384 dir5 (link 203597)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_021401_3_linkid_198390.png"><img src="evaluation/device_reports/device_FHA_01_021401_3_linkid_198390.png" width="100%"></a><br><sub>AL 021401 dir3 (link 198390)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_021461_1_linkid_19034.png"><img src="evaluation/device_reports/device_FHA_01_021461_1_linkid_19034.png" width="100%"></a><br><sub>AL 021461 dir1 (link 19034)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_031381_1_linkid_203620.png"><img src="evaluation/device_reports/device_FHA_01_031381_1_linkid_203620.png" width="100%"></a><br><sub>AL 031381 dir1 (link 203620)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_031382_5_linkid_97472.png"><img src="evaluation/device_reports/device_FHA_01_031382_5_linkid_97472.png" width="100%"></a><br><sub>AL 031382 dir5 (link 97472)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_031383_5_linkid_203622.png"><img src="evaluation/device_reports/device_FHA_01_031383_5_linkid_203622.png" width="100%"></a><br><sub>AL 031383 dir5 (link 203622)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_031384_1_linkid_203923.png"><img src="evaluation/device_reports/device_FHA_01_031384_1_linkid_203923.png" width="100%"></a><br><sub>AL 031384 dir1 (link 203923)</sub></td>
</tr>
</table>

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

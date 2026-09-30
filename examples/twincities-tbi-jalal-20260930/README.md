# Twin Cities, MN-WI — TBI 2023 custom local survey — Jalal, 2026-09-30

> **This example uses a custom local household travel survey, not NHTS.**
> The demand comes from the **Travel Behavior Inventory (TBI) 2023** of the Metropolitan
> Council, the household travel survey of the Twin Cities region. NHTS 2022 is loaded
> but has weight 0. Compare it with the NHTS example of the same region,
> [`twincities-jalal-20260928`](../twincities-jalal-20260928/).

A full Tareek run for the 15-county Minneapolis–Saint Paul region, compared against FHA
directional traffic counts. Tareek uses NHTS as the fallback survey for any US region. A
region that has its own survey can load it with its own survey reader. This run shows
that path for the Twin Cities.

- **Experiment ID:** `tc_tbi_hermes_nw16_10iter`
- **Survey:** **TBI 2023 (weight 1.0)** · NHTS 2022 (weight 0)
- **Region:** 15 counties — Minnesota: Anoka, Carver, Chisago, Dakota, Hennepin, Isanti,
  Le Sueur, Mille Lacs, Ramsey, Scott, Sherburne, Washington, Wright; Wisconsin: Pierce,
  St. Croix
- **Scaling factor:** `0.15` (15% population sample) · **MATSim iterations:** 10 · **Mobsim:** `hermes`
- **Demand:** person-first (survey person-days set who commutes and who travels), from TBI 2023
- **Demand knobs:** `nonwork_trip_share` **1.6**, `work_scaling_multiplier` 1.0
- **Freight:** on, boundary trucks from HPMS, `demand_scale` 0.3
- **Runtime:** ~172 min total (plans 22 min, MATSim 126 min, evaluation 22 min) on a 32-CPU server

---

## Full report

**[`report.html`](report.html)** is the complete experiment report: the verdict, the
demand check against the TBI survey, the demand budget, the count validation, freight, and
all the evaluation figures. It is one self-contained file. All the images are inside it.

> **How to open it:** GitHub does not show HTML pages. Open
> [`report.html`](report.html) on GitHub, click **Download raw file**, then open the
> downloaded file in a web browser. Or clone the repository and open the file locally.

---

## The custom survey: TBI 2023

### How it is loaded

Each survey has its own reader that maps the survey's own columns and labels to Tareek's
common schema (`data_sources/base_survey_trip.py`). The TBI reader is
`data_sources/tbi_survey.py`. The survey entry in the config:

```json
"surveys": [
  {
    "type": "tbi",
    "year": "2023",
    "file": "csv_society_tbi_home_interview2023/TravelBehaviorInventory2023Trip.csv.gz",
    "linked_trip_file": "csv_society_tbi_home_interview2023/TravelBehaviorInventory2023LinkedTrip.csv.gz",
    "person_file": "csv_society_tbi_home_interview2023/TravelBehaviorInventory2023Person.csv.gz",
    "day_file": "csv_society_tbi_home_interview2023/TravelBehaviorInventory2023Day.csv.gz",
    "weight": 1
  },
  { "type": "nhts", "year": "2022", "file": "nhts/csv/tripv2pub.csv",
    "person_file": "nhts/csv/perv2pub.csv", "weight": 0 }
]
```

| TBI file | Used for |
|----------|----------|
| `LinkedTrip.csv` | the trips. One linked trip joins the legs of a trip with transfers (walk → bus → walk). |
| `Trip.csv` | the 2020 block groups of each linked trip (first leg's origin, last leg's destination) |
| `Day.csv` | the person-days (weighted days only, Tuesday to Thursday), and where each day began |
| `Person.csv` | the person group (worker, student, adult, child), and the reported commute days |

The reader:

- keeps the trips of the 15 counties (by state + county code of both block groups);
- fills the "Missing" origin of the first trip of a day from the Day file's `begin_day`
  (2,687 trips; TBI leaves it empty on about a third of the weighted days);
- keeps trips whose trip survey is incomplete when TBI weights them and their purpose and
  mode are known. The walk access legs of transit trips are often incomplete, so a filter
  on this field removed most transit trips;
- converts the UTC times to local time.

Of 104,611 linked trips, 90,151 are kept.

### What the survey changes in the demand

The same region and settings with NHTS 2022 give these plans (plans only, non-work ×1.4):

| | NHTS 2022 | TBI 2023 |
|---|---:|---:|
| Trips per plan | 2.86 | 3.91 |
| Mean trip length (straight line) | 10.4 km | 7.7 km |
| P(commute) of workers (diary) | 52.5% | 51.1% |
| Car / walk / pt legs | 92.5 / 5.9 / 1.6% | 88.3 / 9.8 / 1.8% |
| Trips to Shopping / School | 20.2% / 9.9% | 29.5% / 4.9% |
| Departures 7–9 / 18–24 | 18.2% / 14.7% | 14.6% / 19.6% |

TBI has more trips per person, and they are shorter. The car-km changes only +3.7%.
TBI workers also report how many days a week they commute (Person file): 61.8% of
weekdays, against 51.1% of the diary days. The report shows this as a check; it does not
change the demand.

### Survey against survey, same settings

Four 10-iteration runs, all with hermes, freight 0.3 and the same seed. Only the survey
weights and the non-work knob change.

| | NHTS only | TBI only | TBI 0.5 + NHTS 0.5 | **TBI only (this run)** |
|---|---:|---:|---:|---:|
| `nonwork_trip_share` | 1.4 | 1.4 | 1.4 | **1.6** |
| Overall volume (sim/obs) | 0.868 | 0.875 | 0.865 | **0.925** |
| Interquartile mean | 0.891 | 0.894 | 0.885 | **0.948** |
| Per-station CV | 0.276 | 0.283 | 0.278 | 0.277 |
| GEH < 5 | 23.1% | 24.5% | 25.1% | **27.2%** |
| Correlation | 0.875 | 0.880 | 0.884 | 0.882 |
| Night / morning / midday / evening | 0.45 / 1.06 / 0.82 / 0.75 | 0.45 / 1.03 / 0.83 / 0.81 | 0.47 / 1.02 / 0.82 / 0.81 | 0.46 / 1.07 / 0.89 / 0.86 |
| Car share error against own survey | +6.0 pp | +2.4 pp | +4.3 pp (TBI) | +2.4 pp |
| Morning departure error against own survey | +6.8 pp | +2.6 pp | +2.8 pp (TBI) | +2.6 pp |

- With the same settings (non-work ×1.4), TBI is equal to or better than NHTS on all the
  count measures. It is clearly nearer to its own survey (car share, time of day).
- A 50/50 blend is not better than TBI alone. For this region, use TBI alone.
- The step from non-work 1.4 to 1.6 came from a projection on the plans before MATSim
  (projected total 0.926, measured 0.925). At 1.7 the projected morning is 1.11, so the
  morning sets the limit.

---

## How to reproduce

This run used [`config_used.json`](config_used.json). To run it again, copy the config
into the `config/` folder and start it:

```bash
# from the repository root, with the virtualenv activated
cp examples/twincities-tbi-jalal-20260930/config_used.json config/twincities_tbi.json
python run_experiment.py --config config/twincities_tbi.json
```

The TBI 2023 files are **in the repository**, in
[`data/csv_society_tbi_home_interview2023/`](../../data/csv_society_tbi_home_interview2023/)
(public domain, gzip-compressed, with the publisher's metadata and notice). You do not
need to download them. The run used the same files as uncompressed CSV; the
`config_used.json` here points to the `.csv.gz` files, and the content is identical.

Before you start, change these values in the config for your machine:

| Field | Value in this run | Change to |
|-------|-------------------|-----------|
| `data.data_dir` | server path | the `data/` folder of your clone |
| `matsim.heap_size_gb` | 70 | less than your RAM |
| `plan_generation.num_processes` | 30 | your CPU count, or less |

The first run with TBI reads the CSV files into the `survey_trips` table of the database
(about 1 minute). Later runs read the table. If you change the TBI reader, delete the TBI
rows (`DELETE FROM survey_trips WHERE source_type='tbi'`) so that the next run reads the
files again.

Output goes to `experiments/<experiment-id>/`. The large files (`network.xml` ≈ 329 MB,
`plans.xml`, the MATSim `output/` folder) are **not** in this folder. The run above makes
them again from the config.

For the setup steps, see the **[project README](../../README.md#quick-start)**. The API
keys in the config are **optional** — see [Optional API keys](#optional-api-keys).

---

## Configuration

- [`config_used.json`](config_used.json) — the full Tareek config for this run
- [`config.xml`](config.xml) — the MATSim config that Tareek made
- [`counts.xml`](counts.xml) — the observed counts given to MATSim
- [`matched_devices.csv`](matched_devices.csv) — FHA count devices matched to network links
- [`demand_budget.json`](demand_budget.json) — the person-first demand budget from the TBI person-days (with the reported commute check)
- [`freight_summary.json`](freight_summary.json) — freight cordons, trip totals and checks
- [`od_matrix_diagnostics.json`](od_matrix_diagnostics.json) — checks on the work OD matrix
- [`experiment_summary.json`](experiment_summary.json) — the full machine-readable run summary
- [`experiment_20260930_072013.log`](experiment_20260930_072013.log) — the run log

### Key parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `data.surveys` | **TBI 2023 = 1.0, NHTS 2022 = 0** | the custom local survey |
| `scaling_factor` (population) | **0.15** | 15% sample of the full population |
| MATSim iterations | **10** | innovation stops after iteration 8 |
| `controller.mobsim` | **hermes** | `hermes.endTime` 36:00:00 |
| `flowCapacityFactor` | 0.15 | equal to the scaling factor, copied to hermes |
| `storageCapacityFactor` | 0.18 | 1.2 × the flow factor, copied to hermes |
| `countsScaleFactor` | 6.67 | 1 / flowCapacityFactor |
| `nonwork_trip_share` | **1.6** | calibration knob, see above |
| `work_scaling_multiplier` | 1.0 | neutral |
| `freight.demand_scale` | **0.3** | see [Freight](#freight) |
| `data.survey_months` | `regular` | Mar-May, Sep-Nov survey days |
| `counts.fha.month` | 10 | October 2024 counts |

All the other values are the same as in the NHTS example
[`twincities-jalal-20260928`](../twincities-jalal-20260928/).

### Scenario scale

| | |
|---|---|
| Total population (15 counties) | 3,689,612 |
| Agents simulated | 597,527 (158,088 work · 426,608 non-work · 12,831 freight) |
| Stuck agents | 641 |
| Network | 275,034 nodes · 634,245 links |
| Generated mode split (legs) | car 88.6% · walk 9.5% · pt 1.9% |

---

## Headline results

Simulated against observed link volumes at **49 physical count stations**
(96 directional counts, 2,304 station-hours). Values are MATSim's count comparison, the
average of iterations 1-10.

| Metric | Value | Target | Status |
|--------|------:|--------|:------:|
| **Overall volume (sim/obs)** | **0.925** | 1.0 ± 0.10 | PASS |
| Volume level (interquartile mean) | 0.948 | 1.0 ± 0.10 | PASS |
| Per-station ratio CV | 0.277 | < 0.35 | PASS |
| Correlation (sim vs obs) | 0.882 | > 0.85 | PASS |
| % hourly counts with GEH < 5 | 27.2% | > 85% | CHECK |
| MAE / RMSE | 474 / 712 veh/h | | |

### Time of day

| Block | Hours | NHTS example | This run |
|-------|-------|-------------:|---------:|
| Night | 0–3 | 0.45 | 0.46 |
| Morning | 4–9 | 1.06 | 1.07 |
| Midday | 10–17 | 0.82 | 0.89 |
| Evening | 18–23 | 0.75 | 0.86 |

The morning is at 1.07, so a further level increase would overshoot it. The midday and
evening gap is a time-of-day shape problem, not a level problem.

**Final iteration.** At iteration 10 alone (from its events) the total is 1.00 and the
morning is 1.17. At iteration 9 the walk and pt plans made during innovation are dropped
(walk 16.4% → 9.6%, pt 2.9% → 1.1%), so more trips go by car.

### Demand against the survey (TBI 2023)

| Quantity | Simulated | TBI 2023 | Ratio |
|----------|----------:|---------:|------:|
| Trips per person per day | 3.83 | 3.84 | 1.00 |
| Car share | 89.3% | 86.9% | +2.4 pp |
| Walk share | 9.6% | 8.4% | +1.2 pp |
| Transit share | 1.1% | 3.05% | −2.0 pp |
| Departures 4–9 / 10–17 / 18–23 | 26.5 / 53.8 / 19.2% | 23.9 / 57.7 / 17.8% | |

The trips per person is per simulated agent (travellers only).

### Freight

Measured from the events of iteration 10 on the count links
([`evaluation/freight_share_it10.txt`](evaluation/freight_share_it10.txt)):

| Block | Freight share of simulated volume | Ratio | Ratio without freight |
|-------|----------------------------------:|------:|----------------------:|
| Night | 50% | 0.47 | 0.24 |
| Morning | 5.4% | 1.17 | 1.11 |
| Midday | 8.0% | 0.97 | 0.89 |
| Evening | 7.7% | 0.90 | 0.84 |
| **All** | **7.5%** | **1.00** | **0.93** |

Freight is the same as in the NHTS example (12,831 boundary truck trips). See that example
for the notes on the freight level.

### Where the error is

| | |
|---|---|
| ![Station ratios](evaluation/station_ratio_dotplot.png) | ![Hourly error](evaluation/hourly_relative_error_box.png) |
| Sim/obs ratio per station, sorted | Signed relative error per hour, all stations |

More figures are in [`evaluation/`](evaluation/). The full set, with captions, is in
[`report.html`](report.html).

Data: [`evaluation/volume_comparison.csv`](evaluation/volume_comparison.csv) (per hour,
per station) · [`evaluation/trip_timing_check.json`](evaluation/trip_timing_check.json)
· [`matsim_output/10.countscompare.txt`](matsim_output/10.countscompare.txt) (MATSim's
own count comparison) · [`matsim_output/`](matsim_output/) (mode and score statistics)

---

## MATSim count graphs

MATSim's own count graphs for iteration 10 are in [`graphs/`](graphs/). GitHub does not
show them. Download or clone the folder and open `graphs/start.html` in a browser.

---

## Per-device count reports

Observed and simulated hourly profiles for each matched count direction
(`dir` = FHA direction code, `link` = matched network link). Click a thumbnail to see
it at full size.

<table>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_000040_1_linkid_182997.png"><img src="evaluation/device_reports/device_FHA_27_000040_1_linkid_182997.png" width="100%"></a><br><sub>MN 000040 dir1 (link 182997)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_000040_5_linkid_350001.png"><img src="evaluation/device_reports/device_FHA_27_000040_5_linkid_350001.png" width="100%"></a><br><sub>MN 000040 dir5 (link 350001)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_000042_1_linkid_383835.png"><img src="evaluation/device_reports/device_FHA_27_000042_1_linkid_383835.png" width="100%"></a><br><sub>MN 000042 dir1 (link 383835)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_000042_5_linkid_594015.png"><img src="evaluation/device_reports/device_FHA_27_000042_5_linkid_594015.png" width="100%"></a><br><sub>MN 000042 dir5 (link 594015)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_000382_1_linkid_279370.png"><img src="evaluation/device_reports/device_FHA_27_000382_1_linkid_279370.png" width="100%"></a><br><sub>MN 000382 dir1 (link 279370)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_000382_5_linkid_599453.png"><img src="evaluation/device_reports/device_FHA_27_000382_5_linkid_599453.png" width="100%"></a><br><sub>MN 000382 dir5 (link 599453)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_006461_3_linkid_216638.png"><img src="evaluation/device_reports/device_FHA_27_006461_3_linkid_216638.png" width="100%"></a><br><sub>MN 006461 dir3 (link 216638)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_006461_7_linkid_437849.png"><img src="evaluation/device_reports/device_FHA_27_006461_7_linkid_437849.png" width="100%"></a><br><sub>MN 006461 dir7 (link 437849)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_009110_1_linkid_86860.png"><img src="evaluation/device_reports/device_FHA_27_009110_1_linkid_86860.png" width="100%"></a><br><sub>MN 009110 dir1 (link 86860)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_009110_5_linkid_86871.png"><img src="evaluation/device_reports/device_FHA_27_009110_5_linkid_86871.png" width="100%"></a><br><sub>MN 009110 dir5 (link 86871)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_009556_3_linkid_273233.png"><img src="evaluation/device_reports/device_FHA_27_009556_3_linkid_273233.png" width="100%"></a><br><sub>MN 009556 dir3 (link 273233)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_009556_7_linkid_273234.png"><img src="evaluation/device_reports/device_FHA_27_009556_7_linkid_273234.png" width="100%"></a><br><sub>MN 009556 dir7 (link 273234)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010069_1_linkid_614318.png"><img src="evaluation/device_reports/device_FHA_27_010069_1_linkid_614318.png" width="100%"></a><br><sub>MN 010069 dir1 (link 614318)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010069_5_linkid_267086.png"><img src="evaluation/device_reports/device_FHA_27_010069_5_linkid_267086.png" width="100%"></a><br><sub>MN 010069 dir5 (link 267086)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010205_1_linkid_599475.png"><img src="evaluation/device_reports/device_FHA_27_010205_1_linkid_599475.png" width="100%"></a><br><sub>MN 010205 dir1 (link 599475)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010205_5_linkid_485401.png"><img src="evaluation/device_reports/device_FHA_27_010205_5_linkid_485401.png" width="100%"></a><br><sub>MN 010205 dir5 (link 485401)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010206_3_linkid_330203.png"><img src="evaluation/device_reports/device_FHA_27_010206_3_linkid_330203.png" width="100%"></a><br><sub>MN 010206 dir3 (link 330203)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010206_7_linkid_611478.png"><img src="evaluation/device_reports/device_FHA_27_010206_7_linkid_611478.png" width="100%"></a><br><sub>MN 010206 dir7 (link 611478)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010225_3_linkid_296940.png"><img src="evaluation/device_reports/device_FHA_27_010225_3_linkid_296940.png" width="100%"></a><br><sub>MN 010225 dir3 (link 296940)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010225_7_linkid_118471.png"><img src="evaluation/device_reports/device_FHA_27_010225_7_linkid_118471.png" width="100%"></a><br><sub>MN 010225 dir7 (link 118471)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010310_1_linkid_2867.png"><img src="evaluation/device_reports/device_FHA_27_010310_1_linkid_2867.png" width="100%"></a><br><sub>MN 010310 dir1 (link 2867)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010310_5_linkid_2220.png"><img src="evaluation/device_reports/device_FHA_27_010310_5_linkid_2220.png" width="100%"></a><br><sub>MN 010310 dir5 (link 2220)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010338_1_linkid_63099.png"><img src="evaluation/device_reports/device_FHA_27_010338_1_linkid_63099.png" width="100%"></a><br><sub>MN 010338 dir1 (link 63099)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010338_5_linkid_559393.png"><img src="evaluation/device_reports/device_FHA_27_010338_5_linkid_559393.png" width="100%"></a><br><sub>MN 010338 dir5 (link 559393)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010390_1_linkid_614815.png"><img src="evaluation/device_reports/device_FHA_27_010390_1_linkid_614815.png" width="100%"></a><br><sub>MN 010390 dir1 (link 614815)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010390_5_linkid_396159.png"><img src="evaluation/device_reports/device_FHA_27_010390_5_linkid_396159.png" width="100%"></a><br><sub>MN 010390 dir5 (link 396159)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010398_3_linkid_388817.png"><img src="evaluation/device_reports/device_FHA_27_010398_3_linkid_388817.png" width="100%"></a><br><sub>MN 010398 dir3 (link 388817)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010398_7_linkid_256197.png"><img src="evaluation/device_reports/device_FHA_27_010398_7_linkid_256197.png" width="100%"></a><br><sub>MN 010398 dir7 (link 256197)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010730_1_linkid_132947.png"><img src="evaluation/device_reports/device_FHA_27_010730_1_linkid_132947.png" width="100%"></a><br><sub>MN 010730 dir1 (link 132947)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010730_5_linkid_192350.png"><img src="evaluation/device_reports/device_FHA_27_010730_5_linkid_192350.png" width="100%"></a><br><sub>MN 010730 dir5 (link 192350)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010794_3_linkid_551626.png"><img src="evaluation/device_reports/device_FHA_27_010794_3_linkid_551626.png" width="100%"></a><br><sub>MN 010794 dir3 (link 551626)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010794_7_linkid_96910.png"><img src="evaluation/device_reports/device_FHA_27_010794_7_linkid_96910.png" width="100%"></a><br><sub>MN 010794 dir7 (link 96910)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010800_3_linkid_559300.png"><img src="evaluation/device_reports/device_FHA_27_010800_3_linkid_559300.png" width="100%"></a><br><sub>MN 010800 dir3 (link 559300)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010800_7_linkid_362774.png"><img src="evaluation/device_reports/device_FHA_27_010800_7_linkid_362774.png" width="100%"></a><br><sub>MN 010800 dir7 (link 362774)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010808_1_linkid_24632.png"><img src="evaluation/device_reports/device_FHA_27_010808_1_linkid_24632.png" width="100%"></a><br><sub>MN 010808 dir1 (link 24632)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010808_5_linkid_221155.png"><img src="evaluation/device_reports/device_FHA_27_010808_5_linkid_221155.png" width="100%"></a><br><sub>MN 010808 dir5 (link 221155)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010830_1_linkid_50648.png"><img src="evaluation/device_reports/device_FHA_27_010830_1_linkid_50648.png" width="100%"></a><br><sub>MN 010830 dir1 (link 50648)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010830_5_linkid_594011.png"><img src="evaluation/device_reports/device_FHA_27_010830_5_linkid_594011.png" width="100%"></a><br><sub>MN 010830 dir5 (link 594011)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010840_3_linkid_442423.png"><img src="evaluation/device_reports/device_FHA_27_010840_3_linkid_442423.png" width="100%"></a><br><sub>MN 010840 dir3 (link 442423)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010840_7_linkid_556282.png"><img src="evaluation/device_reports/device_FHA_27_010840_7_linkid_556282.png" width="100%"></a><br><sub>MN 010840 dir7 (link 556282)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010899_3_linkid_39132.png"><img src="evaluation/device_reports/device_FHA_27_010899_3_linkid_39132.png" width="100%"></a><br><sub>MN 010899 dir3 (link 39132)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010899_7_linkid_618468.png"><img src="evaluation/device_reports/device_FHA_27_010899_7_linkid_618468.png" width="100%"></a><br><sub>MN 010899 dir7 (link 618468)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010919_3_linkid_346143.png"><img src="evaluation/device_reports/device_FHA_27_010919_3_linkid_346143.png" width="100%"></a><br><sub>MN 010919 dir3 (link 346143)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010919_7_linkid_456898.png"><img src="evaluation/device_reports/device_FHA_27_010919_7_linkid_456898.png" width="100%"></a><br><sub>MN 010919 dir7 (link 456898)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011191_3_linkid_106577.png"><img src="evaluation/device_reports/device_FHA_27_011191_3_linkid_106577.png" width="100%"></a><br><sub>MN 011191 dir3 (link 106577)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011191_7_linkid_462133.png"><img src="evaluation/device_reports/device_FHA_27_011191_7_linkid_462133.png" width="100%"></a><br><sub>MN 011191 dir7 (link 462133)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011196_3_linkid_324718.png"><img src="evaluation/device_reports/device_FHA_27_011196_3_linkid_324718.png" width="100%"></a><br><sub>MN 011196 dir3 (link 324718)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011196_7_linkid_602210.png"><img src="evaluation/device_reports/device_FHA_27_011196_7_linkid_602210.png" width="100%"></a><br><sub>MN 011196 dir7 (link 602210)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011205_3_linkid_113976.png"><img src="evaluation/device_reports/device_FHA_27_011205_3_linkid_113976.png" width="100%"></a><br><sub>MN 011205 dir3 (link 113976)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011205_7_linkid_304090.png"><img src="evaluation/device_reports/device_FHA_27_011205_7_linkid_304090.png" width="100%"></a><br><sub>MN 011205 dir7 (link 304090)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011228_1_linkid_124592.png"><img src="evaluation/device_reports/device_FHA_27_011228_1_linkid_124592.png" width="100%"></a><br><sub>MN 011228 dir1 (link 124592)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011228_5_linkid_120450.png"><img src="evaluation/device_reports/device_FHA_27_011228_5_linkid_120450.png" width="100%"></a><br><sub>MN 011228 dir5 (link 120450)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011236_3_linkid_440281.png"><img src="evaluation/device_reports/device_FHA_27_011236_3_linkid_440281.png" width="100%"></a><br><sub>MN 011236 dir3 (link 440281)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011236_7_linkid_117344.png"><img src="evaluation/device_reports/device_FHA_27_011236_7_linkid_117344.png" width="100%"></a><br><sub>MN 011236 dir7 (link 117344)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011238_3_linkid_500373.png"><img src="evaluation/device_reports/device_FHA_27_011238_3_linkid_500373.png" width="100%"></a><br><sub>MN 011238 dir3 (link 500373)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011238_7_linkid_226404.png"><img src="evaluation/device_reports/device_FHA_27_011238_7_linkid_226404.png" width="100%"></a><br><sub>MN 011238 dir7 (link 226404)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011273_1_linkid_456448.png"><img src="evaluation/device_reports/device_FHA_27_011273_1_linkid_456448.png" width="100%"></a><br><sub>MN 011273 dir1 (link 456448)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011273_5_linkid_525557.png"><img src="evaluation/device_reports/device_FHA_27_011273_5_linkid_525557.png" width="100%"></a><br><sub>MN 011273 dir5 (link 525557)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011280_1_linkid_24596.png"><img src="evaluation/device_reports/device_FHA_27_011280_1_linkid_24596.png" width="100%"></a><br><sub>MN 011280 dir1 (link 24596)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011280_5_linkid_58756.png"><img src="evaluation/device_reports/device_FHA_27_011280_5_linkid_58756.png" width="100%"></a><br><sub>MN 011280 dir5 (link 58756)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011283-p2_7_linkid_313967.png"><img src="evaluation/device_reports/device_FHA_27_011283-p2_7_linkid_313967.png" width="100%"></a><br><sub>MN 011283 (parallel road) dir7 (link 313967)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011283_3_linkid_102886.png"><img src="evaluation/device_reports/device_FHA_27_011283_3_linkid_102886.png" width="100%"></a><br><sub>MN 011283 dir3 (link 102886)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011283_7_linkid_498942.png"><img src="evaluation/device_reports/device_FHA_27_011283_7_linkid_498942.png" width="100%"></a><br><sub>MN 011283 dir7 (link 498942)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011464_1_linkid_603866.png"><img src="evaluation/device_reports/device_FHA_27_011464_1_linkid_603866.png" width="100%"></a><br><sub>MN 011464 dir1 (link 603866)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011464_5_linkid_92394.png"><img src="evaluation/device_reports/device_FHA_27_011464_5_linkid_92394.png" width="100%"></a><br><sub>MN 011464 dir5 (link 92394)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011510_1_linkid_21327.png"><img src="evaluation/device_reports/device_FHA_27_011510_1_linkid_21327.png" width="100%"></a><br><sub>MN 011510 dir1 (link 21327)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011510_5_linkid_330960.png"><img src="evaluation/device_reports/device_FHA_27_011510_5_linkid_330960.png" width="100%"></a><br><sub>MN 011510 dir5 (link 330960)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011516_1_linkid_396046.png"><img src="evaluation/device_reports/device_FHA_27_011516_1_linkid_396046.png" width="100%"></a><br><sub>MN 011516 dir1 (link 396046)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011516_5_linkid_557307.png"><img src="evaluation/device_reports/device_FHA_27_011516_5_linkid_557307.png" width="100%"></a><br><sub>MN 011516 dir5 (link 557307)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011517_1_linkid_464961.png"><img src="evaluation/device_reports/device_FHA_27_011517_1_linkid_464961.png" width="100%"></a><br><sub>MN 011517 dir1 (link 464961)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011517_5_linkid_109783.png"><img src="evaluation/device_reports/device_FHA_27_011517_5_linkid_109783.png" width="100%"></a><br><sub>MN 011517 dir5 (link 109783)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011726-p2_7_linkid_20674.png"><img src="evaluation/device_reports/device_FHA_27_011726-p2_7_linkid_20674.png" width="100%"></a><br><sub>MN 011726 (parallel road) dir7 (link 20674)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011726_3_linkid_458819.png"><img src="evaluation/device_reports/device_FHA_27_011726_3_linkid_458819.png" width="100%"></a><br><sub>MN 011726 dir3 (link 458819)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011726_7_linkid_458818.png"><img src="evaluation/device_reports/device_FHA_27_011726_7_linkid_458818.png" width="100%"></a><br><sub>MN 011726 dir7 (link 458818)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011747_3_linkid_193768.png"><img src="evaluation/device_reports/device_FHA_27_011747_3_linkid_193768.png" width="100%"></a><br><sub>MN 011747 dir3 (link 193768)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011747_7_linkid_591375.png"><img src="evaluation/device_reports/device_FHA_27_011747_7_linkid_591375.png" width="100%"></a><br><sub>MN 011747 dir7 (link 591375)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011749_3_linkid_273580.png"><img src="evaluation/device_reports/device_FHA_27_011749_3_linkid_273580.png" width="100%"></a><br><sub>MN 011749 dir3 (link 273580)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011749_7_linkid_273628.png"><img src="evaluation/device_reports/device_FHA_27_011749_7_linkid_273628.png" width="100%"></a><br><sub>MN 011749 dir7 (link 273628)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011759_1_linkid_149608.png"><img src="evaluation/device_reports/device_FHA_27_011759_1_linkid_149608.png" width="100%"></a><br><sub>MN 011759 dir1 (link 149608)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011759_5_linkid_184708.png"><img src="evaluation/device_reports/device_FHA_27_011759_5_linkid_184708.png" width="100%"></a><br><sub>MN 011759 dir5 (link 184708)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_042507_3_linkid_479639.png"><img src="evaluation/device_reports/device_FHA_27_042507_3_linkid_479639.png" width="100%"></a><br><sub>MN 042507 dir3 (link 479639)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_042507_7_linkid_479057.png"><img src="evaluation/device_reports/device_FHA_27_042507_7_linkid_479057.png" width="100%"></a><br><sub>MN 042507 dir7 (link 479057)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550002_3_linkid_436126.png"><img src="evaluation/device_reports/device_FHA_55_550002_3_linkid_436126.png" width="100%"></a><br><sub>WI 550002 dir3 (link 436126)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550002_7_linkid_325449.png"><img src="evaluation/device_reports/device_FHA_55_550002_7_linkid_325449.png" width="100%"></a><br><sub>WI 550002 dir7 (link 325449)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550006_3_linkid_600152.png"><img src="evaluation/device_reports/device_FHA_55_550006_3_linkid_600152.png" width="100%"></a><br><sub>WI 550006 dir3 (link 600152)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550006_7_linkid_137440.png"><img src="evaluation/device_reports/device_FHA_55_550006_7_linkid_137440.png" width="100%"></a><br><sub>WI 550006 dir7 (link 137440)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550008_3_linkid_478973.png"><img src="evaluation/device_reports/device_FHA_55_550008_3_linkid_478973.png" width="100%"></a><br><sub>WI 550008 dir3 (link 478973)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550008_7_linkid_478972.png"><img src="evaluation/device_reports/device_FHA_55_550008_7_linkid_478972.png" width="100%"></a><br><sub>WI 550008 dir7 (link 478972)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550153_3_linkid_266168.png"><img src="evaluation/device_reports/device_FHA_55_550153_3_linkid_266168.png" width="100%"></a><br><sub>WI 550153 dir3 (link 266168)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550153_7_linkid_505330.png"><img src="evaluation/device_reports/device_FHA_55_550153_7_linkid_505330.png" width="100%"></a><br><sub>WI 550153 dir7 (link 505330)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550154_3_linkid_314887.png"><img src="evaluation/device_reports/device_FHA_55_550154_3_linkid_314887.png" width="100%"></a><br><sub>WI 550154 dir3 (link 314887)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550154_7_linkid_424822.png"><img src="evaluation/device_reports/device_FHA_55_550154_7_linkid_424822.png" width="100%"></a><br><sub>WI 550154 dir7 (link 424822)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550216_1_linkid_220059.png"><img src="evaluation/device_reports/device_FHA_55_550216_1_linkid_220059.png" width="100%"></a><br><sub>WI 550216 dir1 (link 220059)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550216_5_linkid_449002.png"><img src="evaluation/device_reports/device_FHA_55_550216_5_linkid_449002.png" width="100%"></a><br><sub>WI 550216 dir5 (link 449002)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550880_1_linkid_103323.png"><img src="evaluation/device_reports/device_FHA_55_550880_1_linkid_103323.png" width="100%"></a><br><sub>WI 550880 dir1 (link 103323)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550880_5_linkid_628070.png"><img src="evaluation/device_reports/device_FHA_55_550880_5_linkid_628070.png" width="100%"></a><br><sub>WI 550880 dir5 (link 628070)</sub></td>
</tr>
</table>

---

## Optional API keys

`config_used.json` refers to two external services. They are **optional**. The pipeline
runs without them, with warnings and some missing data (no live ACS age split and
mode-share calibration, and no `wmata.com` transit feed). The keys in this config are
**redacted** (`YOUR_..._KEY`). Both are free:

| Field in config | Service | Register (free) |
|-----------------|---------|-----------------|
| `data.census_api_key` | U.S. Census API — ACS data | https://api.census.gov/data/key_signup.html |
| `gtfs.api_keys["wmata.com"]` | WMATA GTFS feed | https://developer.wmata.com/ |

The freight module reads the public HPMS service, which needs no key.

**Never commit real keys.**

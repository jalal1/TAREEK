# Twin Cities, MN-WI experiment — Jalal, 2026-09-28

A full Tareek run for the 15-county Minneapolis–Saint Paul region, compared against FHA
directional traffic counts. This is the first Twin Cities example, and the first example
with person-first demand, freight and the Hermes mobsim.

- **Experiment ID:** `tc_pf_hermes_nw14_fr03_10iter`
- **Region:** 15 counties — Minnesota: Anoka, Carver, Chisago, Dakota, Hennepin, Isanti,
  Le Sueur, Mille Lacs, Ramsey, Scott, Sherburne, Washington, Wright; Wisconsin: Pierce,
  St. Croix
- **Scaling factor:** `0.15` (15% population sample) · **MATSim iterations:** 10 · **Mobsim:** `hermes`
- **Demand:** person-first (survey person-days set who commutes and who travels), NHTS 2022
- **Demand knobs:** `nonwork_trip_share` 1.4, `work_scaling_multiplier` 1.0
- **Freight:** on, boundary trucks from HPMS, `demand_scale` 0.3
- **Runtime:** ~144 min total (plans 19 min, MATSim 102 min, evaluation 20 min) on a 32-CPU server

---

## Full report

**[`report.html`](report.html)** is the complete experiment report: the verdict, the
demand check against the household survey, the count validation, freight, and all the
evaluation figures. It is one self-contained file. All the images are inside it.

> **How to open it:** GitHub does not show HTML pages. Open
> [`report.html`](report.html) on GitHub, click **Download raw file**, then open the
> downloaded file in a web browser. Or clone the repository and open the file locally.

To make the same report for your own run:

```bash
python scripts/experiment_report.py experiments/<experiment-id> --no-pdf
```

---

## What is new in this run

### Person-first demand

Earlier runs gave every job one commute per day, so there were too many work trips.
Person-first demand starts from the persons of each home block. The survey person-days
(NHTS 2022, regular months) give, for each person group, the share of days with a
commute, with other travel only, and with no travel. For workers the commute share is
0.525. Work trips then come from the LODES work places multiplied by this share.

### Calibration from the plans, before MATSim

The first person-first run (`tc_pf_20iter`, qsim, no freight) had a count total of only
0.69. This run raises the demand with two config changes:

| Change | Value | Effect in the plans |
|--------|-------|---------------------|
| `nonwork_purposes.nonwork_trip_share` | 1.0 → **1.4** | non-work travellers +40% (253,417 → 354,523 plans) |
| `freight.enabled` | **true**, `demand_scale` 0.3 | 12,728 boundary truck trips |

The values come from a projection made on the generated plans, before MATSim: the old
count ratio of each time block, multiplied by the planned car-km of the new plans divided
by the old. A first attempt (work ×1.2, non-work ×1.3, full freight) projected a morning
of 1.33, so it was stopped before MATSim and changed. For this run the projection gave a
total of 0.864; MATSim gave 0.868.

### Hermes

`controller.mobsim` is `hermes` (with `hermes.endTime` 36:00:00). Iterations 2-9 took
about 7 min each for 529,891 agents. qsim took about 10.5 min for 416,057 agents on the
same region, so Hermes is about 1.9 times faster per agent. MATSim
logs "Hermes should be run with one thread per handler" (`eventsManager.oneThreadPerHandler`);
this setting is not yet in the template.

---

## How to reproduce

This run used [`config_used.json`](config_used.json). To run it again, copy the config
into the `config/` folder and start it:

```bash
# from the repository root, with the virtualenv activated
cp examples/twincities-jalal-20260928/config_used.json config/twincities.json
python run_experiment.py --config config/twincities.json
```

Before you start, change these values in the config for your machine:

| Field | Value in this run | Change to |
|-------|-------------------|-----------|
| `data.data_dir` | server path | the `data/` folder of your clone |
| `matsim.heap_size_gb` | 70 | less than your RAM |
| `plan_generation.num_processes` | 30 | your CPU count, or less |

Output goes to `experiments/<experiment-id>/`. The large files (`network.xml` ≈ 346 MB,
`plans.xml` ≈ 258 MB, the MATSim `output/` folder) are **not** in this folder. The run
above makes them again from the config. The first freight run downloads the HPMS road
data (about 10 minutes); later runs use the cache in `data/hpms`.

For the setup steps, see the **[project README](../../README.md#quick-start)**. The API
keys in the config are **optional** — see [Optional API keys](#optional-api-keys).

---

## Configuration

- [`config_used.json`](config_used.json) — the full Tareek config for this run
- [`config.xml`](config.xml) — the MATSim config that Tareek made
- [`counts.xml`](counts.xml) — the observed counts given to MATSim
- [`matched_devices.csv`](matched_devices.csv) — FHA count devices matched to network links
- [`demand_budget.json`](demand_budget.json) — the person-first demand budget (day types, purpose mix, persons per purpose)
- [`freight_summary.json`](freight_summary.json) — freight cordons, trip totals and checks
- [`od_matrix_diagnostics.json`](od_matrix_diagnostics.json) — checks on the work OD matrix
- [`experiment_summary.json`](experiment_summary.json) — the full machine-readable run summary
- [`experiment_20260927_214951.log`](experiment_20260927_214951.log) — the run log

### Key parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `scaling_factor` (population) | **0.15** | 15% sample of the full population |
| MATSim iterations | **10** | innovation stops after iteration 8 |
| `controller.mobsim` | **hermes** | `hermes.endTime` 36:00:00 |
| `flowCapacityFactor` | 0.15 | equal to the scaling factor, copied to hermes |
| `storageCapacityFactor` | 0.18 | 1.2 × the flow factor, copied to hermes |
| `countsScaleFactor` | 6.67 | 1 / flowCapacityFactor |
| `nonwork_trip_share` | **1.4** | calibration knob, see above |
| `work_scaling_multiplier` | 1.0 | neutral |
| `freight.demand_scale` | **0.3** | see [Freight](#freight) |
| `data.survey_months` | `regular` | Mar-May, Sep-Nov survey days |
| `counts.fha.month` | 10 | October 2024 counts |
| `first_departure_source` | `first_of_day` | |
| `over_budget` | `resample` | |

### Scenario scale

| | |
|---|---|
| Total population (15 counties) | 3,689,612 |
| Agents simulated | 529,891 (162,640 work · 354,523 non-work · 12,728 freight) |
| Stuck agents | 387 |
| Network | 276,140 nodes · 636,217 links |
| Generated mode split (legs) | car 92.6% · walk 5.8% · pt 1.6% |

---

## Headline results

Simulated against observed link volumes at **47 physical count stations**
(94 directional counts, 2,256 station-hours). Values are MATSim's count comparison, the
average of iterations 1-10.

| Metric | Value | Target | Status |
|--------|------:|--------|:------:|
| **Overall volume (sim/obs)** | **0.868** | 1.0 ± 0.10 | CHECK |
| Volume level (interquartile mean) | 0.891 | 1.0 ± 0.10 | CHECK |
| Per-station ratio CV | 0.276 | < 0.35 | PASS |
| Correlation (sim vs obs) | 0.875 | > 0.85 | PASS |
| % hourly counts with GEH < 5 | 23.1% | > 85% | CHECK |
| MAE / RMSE | 511 / 754 veh/h | | |

Against the first person-first run (`tc_pf_20iter`: qsim, no freight, knobs neutral):

| Metric | tc_pf_20iter | This run |
|--------|-------------:|---------:|
| Overall volume | 0.688 | **0.868** |
| Interquartile mean | 0.677 | **0.891** |
| Per-station CV | 0.303 | **0.276** |
| GEH < 5 | 12.3% | **23.1%** |

### Time of day

| Block | Hours | tc_pf_20iter | This run |
|-------|-------|-------------:|---------:|
| Night | 0–3 | 0.20 | 0.45 |
| Morning | 4–9 | 0.90 | 1.06 |
| Midday | 10–17 | 0.63 | 0.82 |
| Evening | 18–23 | 0.58 | 0.75 |

The morning is now at 1.06, so a further level increase would overshoot it. The midday
and evening gap is a time-of-day shape problem, not a level problem.

**Final iteration.** At iteration 10 alone (from its events) the total is 0.95 and the
morning is 1.18. At iteration 9 the walk and pt plans made during innovation are dropped
(walk 14.0% → 5.7%, pt 3.4% → 0.9%), so more trips go by car.

### Demand against the survey (NHTS 2022)

| Quantity | Simulated | NHTS 2022 | Ratio |
|----------|----------:|----------:|------:|
| Trips per person per day | 2.81 | 2.82 | 1.00 |
| Median trip length (km, after the 1.25 network correction) | 3.43 | 6.93 | 0.50 |
| Car share | 93.4% | 87.4% | +6.0 pp |
| Transit share | 0.9% | 4.4% | −3.5 pp |

The trips per person is per simulated agent (travellers only). No local household travel
survey is loaded for this region, so the reference is the national survey.

### Freight

Measured from the events of iteration 10 on the count links
([`evaluation/freight_share_it10.txt`](evaluation/freight_share_it10.txt)):

| Block | Freight share of simulated volume | Ratio | Ratio without freight |
|-------|----------------------------------:|------:|----------------------:|
| Night | 53% | 0.47 | 0.22 |
| Morning | 5.1% | 1.18 | 1.12 |
| Midday | 8.4% | 0.90 | 0.82 |
| Evening | 8.5% | 0.82 | 0.75 |
| **All** | **7.7%** | **0.95** | **0.88** |

- Freight is 7.4% of the observed volume. TMAS measured 3.87% heavy trucks at these
  stations, so `demand_scale` 0.3 is still about 2 times too high. About 0.15 matches TMAS.
- All freight trips cross the region boundary, and there are no truck trips inside the
  region. So freight is concentrated at the edge stations (27-43% of the simulated volume
  at the Wisconsin I-94 stations), and the median station has 5.8%.

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
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_000040_1_linkid_183265.png"><img src="evaluation/device_reports/device_FHA_27_000040_1_linkid_183265.png" width="100%"></a><br><sub>MN 000040 dir1 (link 183265)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_000040_5_linkid_350844.png"><img src="evaluation/device_reports/device_FHA_27_000040_5_linkid_350844.png" width="100%"></a><br><sub>MN 000040 dir5 (link 350844)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_000042_1_linkid_384876.png"><img src="evaluation/device_reports/device_FHA_27_000042_1_linkid_384876.png" width="100%"></a><br><sub>MN 000042 dir1 (link 384876)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_000042_5_linkid_595597.png"><img src="evaluation/device_reports/device_FHA_27_000042_5_linkid_595597.png" width="100%"></a><br><sub>MN 000042 dir5 (link 595597)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_000382_1_linkid_279806.png"><img src="evaluation/device_reports/device_FHA_27_000382_1_linkid_279806.png" width="100%"></a><br><sub>MN 000382 dir1 (link 279806)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_000382_5_linkid_601137.png"><img src="evaluation/device_reports/device_FHA_27_000382_5_linkid_601137.png" width="100%"></a><br><sub>MN 000382 dir5 (link 601137)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_006461_3_linkid_216921.png"><img src="evaluation/device_reports/device_FHA_27_006461_3_linkid_216921.png" width="100%"></a><br><sub>MN 006461 dir3 (link 216921)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_006461_7_linkid_438999.png"><img src="evaluation/device_reports/device_FHA_27_006461_7_linkid_438999.png" width="100%"></a><br><sub>MN 006461 dir7 (link 438999)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_009110_1_linkid_86947.png"><img src="evaluation/device_reports/device_FHA_27_009110_1_linkid_86947.png" width="100%"></a><br><sub>MN 009110 dir1 (link 86947)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_009110_5_linkid_86958.png"><img src="evaluation/device_reports/device_FHA_27_009110_5_linkid_86958.png" width="100%"></a><br><sub>MN 009110 dir5 (link 86958)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_009556_3_linkid_273688.png"><img src="evaluation/device_reports/device_FHA_27_009556_3_linkid_273688.png" width="100%"></a><br><sub>MN 009556 dir3 (link 273688)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_009556_7_linkid_273689.png"><img src="evaluation/device_reports/device_FHA_27_009556_7_linkid_273689.png" width="100%"></a><br><sub>MN 009556 dir7 (link 273689)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010069_1_linkid_616023.png"><img src="evaluation/device_reports/device_FHA_27_010069_1_linkid_616023.png" width="100%"></a><br><sub>MN 010069 dir1 (link 616023)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010069_5_linkid_267515.png"><img src="evaluation/device_reports/device_FHA_27_010069_5_linkid_267515.png" width="100%"></a><br><sub>MN 010069 dir5 (link 267515)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010205_1_linkid_601160.png"><img src="evaluation/device_reports/device_FHA_27_010205_1_linkid_601160.png" width="100%"></a><br><sub>MN 010205 dir1 (link 601160)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010205_5_linkid_418858.png"><img src="evaluation/device_reports/device_FHA_27_010205_5_linkid_418858.png" width="100%"></a><br><sub>MN 010205 dir5 (link 418858)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010206_3_linkid_331001.png"><img src="evaluation/device_reports/device_FHA_27_010206_3_linkid_331001.png" width="100%"></a><br><sub>MN 010206 dir3 (link 331001)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010206_7_linkid_613184.png"><img src="evaluation/device_reports/device_FHA_27_010206_7_linkid_613184.png" width="100%"></a><br><sub>MN 010206 dir7 (link 613184)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010225_3_linkid_297376.png"><img src="evaluation/device_reports/device_FHA_27_010225_3_linkid_297376.png" width="100%"></a><br><sub>MN 010225 dir3 (link 297376)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010225_7_linkid_118544.png"><img src="evaluation/device_reports/device_FHA_27_010225_7_linkid_118544.png" width="100%"></a><br><sub>MN 010225 dir7 (link 118544)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010310_1_linkid_2872.png"><img src="evaluation/device_reports/device_FHA_27_010310_1_linkid_2872.png" width="100%"></a><br><sub>MN 010310 dir1 (link 2872)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010310_5_linkid_2225.png"><img src="evaluation/device_reports/device_FHA_27_010310_5_linkid_2225.png" width="100%"></a><br><sub>MN 010310 dir5 (link 2225)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010338_1_linkid_63207.png"><img src="evaluation/device_reports/device_FHA_27_010338_1_linkid_63207.png" width="100%"></a><br><sub>MN 010338 dir1 (link 63207)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010338_5_linkid_560915.png"><img src="evaluation/device_reports/device_FHA_27_010338_5_linkid_560915.png" width="100%"></a><br><sub>MN 010338 dir5 (link 560915)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010390_1_linkid_616521.png"><img src="evaluation/device_reports/device_FHA_27_010390_1_linkid_616521.png" width="100%"></a><br><sub>MN 010390 dir1 (link 616521)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010390_5_linkid_397204.png"><img src="evaluation/device_reports/device_FHA_27_010390_5_linkid_397204.png" width="100%"></a><br><sub>MN 010390 dir5 (link 397204)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010398_3_linkid_389891.png"><img src="evaluation/device_reports/device_FHA_27_010398_3_linkid_389891.png" width="100%"></a><br><sub>MN 010398 dir3 (link 389891)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010398_7_linkid_256564.png"><img src="evaluation/device_reports/device_FHA_27_010398_7_linkid_256564.png" width="100%"></a><br><sub>MN 010398 dir7 (link 256564)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010730_1_linkid_133075.png"><img src="evaluation/device_reports/device_FHA_27_010730_1_linkid_133075.png" width="100%"></a><br><sub>MN 010730 dir1 (link 133075)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010730_5_linkid_192643.png"><img src="evaluation/device_reports/device_FHA_27_010730_5_linkid_192643.png" width="100%"></a><br><sub>MN 010730 dir5 (link 192643)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010794_3_linkid_553222.png"><img src="evaluation/device_reports/device_FHA_27_010794_3_linkid_553222.png" width="100%"></a><br><sub>MN 010794 dir3 (link 553222)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010794_7_linkid_96972.png"><img src="evaluation/device_reports/device_FHA_27_010794_7_linkid_96972.png" width="100%"></a><br><sub>MN 010794 dir7 (link 96972)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010800_3_linkid_560822.png"><img src="evaluation/device_reports/device_FHA_27_010800_3_linkid_560822.png" width="100%"></a><br><sub>MN 010800 dir3 (link 560822)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010800_7_linkid_363641.png"><img src="evaluation/device_reports/device_FHA_27_010800_7_linkid_363641.png" width="100%"></a><br><sub>MN 010800 dir7 (link 363641)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010808_1_linkid_24616.png"><img src="evaluation/device_reports/device_FHA_27_010808_1_linkid_24616.png" width="100%"></a><br><sub>MN 010808 dir1 (link 24616)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010808_5_linkid_221467.png"><img src="evaluation/device_reports/device_FHA_27_010808_5_linkid_221467.png" width="100%"></a><br><sub>MN 010808 dir5 (link 221467)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010830_1_linkid_50755.png"><img src="evaluation/device_reports/device_FHA_27_010830_1_linkid_50755.png" width="100%"></a><br><sub>MN 010830 dir1 (link 50755)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010830_5_linkid_595594.png"><img src="evaluation/device_reports/device_FHA_27_010830_5_linkid_595594.png" width="100%"></a><br><sub>MN 010830 dir5 (link 595594)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010840_3_linkid_443713.png"><img src="evaluation/device_reports/device_FHA_27_010840_3_linkid_443713.png" width="100%"></a><br><sub>MN 010840 dir3 (link 443713)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010840_7_linkid_557805.png"><img src="evaluation/device_reports/device_FHA_27_010840_7_linkid_557805.png" width="100%"></a><br><sub>MN 010840 dir7 (link 557805)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010899_3_linkid_39168.png"><img src="evaluation/device_reports/device_FHA_27_010899_3_linkid_39168.png" width="100%"></a><br><sub>MN 010899 dir3 (link 39168)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010899_7_linkid_620177.png"><img src="evaluation/device_reports/device_FHA_27_010899_7_linkid_620177.png" width="100%"></a><br><sub>MN 010899 dir7 (link 620177)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010919_3_linkid_346960.png"><img src="evaluation/device_reports/device_FHA_27_010919_3_linkid_346960.png" width="100%"></a><br><sub>MN 010919 dir3 (link 346960)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_010919_7_linkid_458289.png"><img src="evaluation/device_reports/device_FHA_27_010919_7_linkid_458289.png" width="100%"></a><br><sub>MN 010919 dir7 (link 458289)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011191_3_linkid_106635.png"><img src="evaluation/device_reports/device_FHA_27_011191_3_linkid_106635.png" width="100%"></a><br><sub>MN 011191 dir3 (link 106635)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011191_7_linkid_463621.png"><img src="evaluation/device_reports/device_FHA_27_011191_7_linkid_463621.png" width="100%"></a><br><sub>MN 011191 dir7 (link 463621)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011196_3_linkid_325306.png"><img src="evaluation/device_reports/device_FHA_27_011196_3_linkid_325306.png" width="100%"></a><br><sub>MN 011196 dir3 (link 325306)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011196_7_linkid_603939.png"><img src="evaluation/device_reports/device_FHA_27_011196_7_linkid_603939.png" width="100%"></a><br><sub>MN 011196 dir7 (link 603939)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011205_3_linkid_114022.png"><img src="evaluation/device_reports/device_FHA_27_011205_3_linkid_114022.png" width="100%"></a><br><sub>MN 011205 dir3 (link 114022)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011205_7_linkid_304624.png"><img src="evaluation/device_reports/device_FHA_27_011205_7_linkid_304624.png" width="100%"></a><br><sub>MN 011205 dir7 (link 304624)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011228_1_linkid_124719.png"><img src="evaluation/device_reports/device_FHA_27_011228_1_linkid_124719.png" width="100%"></a><br><sub>MN 011228 dir1 (link 124719)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011228_5_linkid_120543.png"><img src="evaluation/device_reports/device_FHA_27_011228_5_linkid_120543.png" width="100%"></a><br><sub>MN 011228 dir5 (link 120543)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011236_3_linkid_441455.png"><img src="evaluation/device_reports/device_FHA_27_011236_3_linkid_441455.png" width="100%"></a><br><sub>MN 011236 dir3 (link 441455)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011236_7_linkid_117433.png"><img src="evaluation/device_reports/device_FHA_27_011236_7_linkid_117433.png" width="100%"></a><br><sub>MN 011236 dir7 (link 117433)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011238_3_linkid_501898.png"><img src="evaluation/device_reports/device_FHA_27_011238_3_linkid_501898.png" width="100%"></a><br><sub>MN 011238 dir3 (link 501898)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011238_7_linkid_226719.png"><img src="evaluation/device_reports/device_FHA_27_011238_7_linkid_226719.png" width="100%"></a><br><sub>MN 011238 dir7 (link 226719)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011273_1_linkid_457837.png"><img src="evaluation/device_reports/device_FHA_27_011273_1_linkid_457837.png" width="100%"></a><br><sub>MN 011273 dir1 (link 457837)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011273_5_linkid_527132.png"><img src="evaluation/device_reports/device_FHA_27_011273_5_linkid_527132.png" width="100%"></a><br><sub>MN 011273 dir5 (link 527132)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011280_1_linkid_24580.png"><img src="evaluation/device_reports/device_FHA_27_011280_1_linkid_24580.png" width="100%"></a><br><sub>MN 011280 dir1 (link 24580)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011280_5_linkid_58875.png"><img src="evaluation/device_reports/device_FHA_27_011280_5_linkid_58875.png" width="100%"></a><br><sub>MN 011280 dir5 (link 58875)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011283_3_linkid_102956.png"><img src="evaluation/device_reports/device_FHA_27_011283_3_linkid_102956.png" width="100%"></a><br><sub>MN 011283 dir3 (link 102956)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011283_7_linkid_500467.png"><img src="evaluation/device_reports/device_FHA_27_011283_7_linkid_500467.png" width="100%"></a><br><sub>MN 011283 dir7 (link 500467)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011464_1_linkid_605591.png"><img src="evaluation/device_reports/device_FHA_27_011464_1_linkid_605591.png" width="100%"></a><br><sub>MN 011464 dir1 (link 605591)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011464_5_linkid_92471.png"><img src="evaluation/device_reports/device_FHA_27_011464_5_linkid_92471.png" width="100%"></a><br><sub>MN 011464 dir5 (link 92471)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011510_1_linkid_21307.png"><img src="evaluation/device_reports/device_FHA_27_011510_1_linkid_21307.png" width="100%"></a><br><sub>MN 011510 dir1 (link 21307)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011510_5_linkid_331807.png"><img src="evaluation/device_reports/device_FHA_27_011510_5_linkid_331807.png" width="100%"></a><br><sub>MN 011510 dir5 (link 331807)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011516_1_linkid_397091.png"><img src="evaluation/device_reports/device_FHA_27_011516_1_linkid_397091.png" width="100%"></a><br><sub>MN 011516 dir1 (link 397091)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011516_5_linkid_558831.png"><img src="evaluation/device_reports/device_FHA_27_011516_5_linkid_558831.png" width="100%"></a><br><sub>MN 011516 dir5 (link 558831)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011517_1_linkid_466434.png"><img src="evaluation/device_reports/device_FHA_27_011517_1_linkid_466434.png" width="100%"></a><br><sub>MN 011517 dir1 (link 466434)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011517_5_linkid_109829.png"><img src="evaluation/device_reports/device_FHA_27_011517_5_linkid_109829.png" width="100%"></a><br><sub>MN 011517 dir5 (link 109829)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011726_3_linkid_460281.png"><img src="evaluation/device_reports/device_FHA_27_011726_3_linkid_460281.png" width="100%"></a><br><sub>MN 011726 dir3 (link 460281)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011726_7_linkid_460280.png"><img src="evaluation/device_reports/device_FHA_27_011726_7_linkid_460280.png" width="100%"></a><br><sub>MN 011726 dir7 (link 460280)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011747_3_linkid_194060.png"><img src="evaluation/device_reports/device_FHA_27_011747_3_linkid_194060.png" width="100%"></a><br><sub>MN 011747 dir3 (link 194060)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011747_7_linkid_592946.png"><img src="evaluation/device_reports/device_FHA_27_011747_7_linkid_592946.png" width="100%"></a><br><sub>MN 011747 dir7 (link 592946)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011749_3_linkid_274038.png"><img src="evaluation/device_reports/device_FHA_27_011749_3_linkid_274038.png" width="100%"></a><br><sub>MN 011749 dir3 (link 274038)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011749_7_linkid_274086.png"><img src="evaluation/device_reports/device_FHA_27_011749_7_linkid_274086.png" width="100%"></a><br><sub>MN 011749 dir7 (link 274086)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011759_1_linkid_149804.png"><img src="evaluation/device_reports/device_FHA_27_011759_1_linkid_149804.png" width="100%"></a><br><sub>MN 011759 dir1 (link 149804)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_011759_5_linkid_184969.png"><img src="evaluation/device_reports/device_FHA_27_011759_5_linkid_184969.png" width="100%"></a><br><sub>MN 011759 dir5 (link 184969)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_042507_3_linkid_481141.png"><img src="evaluation/device_reports/device_FHA_27_042507_3_linkid_481141.png" width="100%"></a><br><sub>MN 042507 dir3 (link 481141)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_27_042507_7_linkid_480537.png"><img src="evaluation/device_reports/device_FHA_27_042507_7_linkid_480537.png" width="100%"></a><br><sub>MN 042507 dir7 (link 480537)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550002_3_linkid_437236.png"><img src="evaluation/device_reports/device_FHA_55_550002_3_linkid_437236.png" width="100%"></a><br><sub>WI 550002 dir3 (link 437236)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550002_7_linkid_326038.png"><img src="evaluation/device_reports/device_FHA_55_550002_7_linkid_326038.png" width="100%"></a><br><sub>WI 550002 dir7 (link 326038)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550006_3_linkid_601842.png"><img src="evaluation/device_reports/device_FHA_55_550006_3_linkid_601842.png" width="100%"></a><br><sub>WI 550006 dir3 (link 601842)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550006_7_linkid_137592.png"><img src="evaluation/device_reports/device_FHA_55_550006_7_linkid_137592.png" width="100%"></a><br><sub>WI 550006 dir7 (link 137592)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550008_3_linkid_480452.png"><img src="evaluation/device_reports/device_FHA_55_550008_3_linkid_480452.png" width="100%"></a><br><sub>WI 550008 dir3 (link 480452)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550008_7_linkid_480451.png"><img src="evaluation/device_reports/device_FHA_55_550008_7_linkid_480451.png" width="100%"></a><br><sub>WI 550008 dir7 (link 480451)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550153_3_linkid_266598.png"><img src="evaluation/device_reports/device_FHA_55_550153_3_linkid_266598.png" width="100%"></a><br><sub>WI 550153 dir3 (link 266598)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550153_7_linkid_506892.png"><img src="evaluation/device_reports/device_FHA_55_550153_7_linkid_506892.png" width="100%"></a><br><sub>WI 550153 dir7 (link 506892)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550154_3_linkid_315440.png"><img src="evaluation/device_reports/device_FHA_55_550154_3_linkid_315440.png" width="100%"></a><br><sub>WI 550154 dir3 (link 315440)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550154_7_linkid_425888.png"><img src="evaluation/device_reports/device_FHA_55_550154_7_linkid_425888.png" width="100%"></a><br><sub>WI 550154 dir7 (link 425888)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550216_1_linkid_220380.png"><img src="evaluation/device_reports/device_FHA_55_550216_1_linkid_220380.png" width="100%"></a><br><sub>WI 550216 dir1 (link 220380)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550216_5_linkid_450419.png"><img src="evaluation/device_reports/device_FHA_55_550216_5_linkid_450419.png" width="100%"></a><br><sub>WI 550216 dir5 (link 450419)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550880_1_linkid_103381.png"><img src="evaluation/device_reports/device_FHA_55_550880_1_linkid_103381.png" width="100%"></a><br><sub>WI 550880 dir1 (link 103381)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_55_550880_5_linkid_629789.png"><img src="evaluation/device_reports/device_FHA_55_550880_5_linkid_629789.png" width="100%"></a><br><sub>WI 550880 dir5 (link 629789)</sub></td>
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

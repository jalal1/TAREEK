# Chicago, IL experiment — 2026-10-03

A full Tareek run for the Chicago metro core, compared against FHA directional traffic
counts. It uses person-first demand, freight and the Hermes mobsim, in the same way as
the [Twin Cities](../twincities-20260928/) and [Birmingham](../birmingham-20260928/)
examples. It is the first Chicago example and the largest example run to date.

- **Experiment ID:** `chi_s20_w11_nw20_b12_fr018_10iter`
- **Region:** 3 Illinois counties — Cook (`17031`), DuPage (`17043`), Lake (`17097`)
- **Scaling factor:** `0.20` (20% population sample) · **MATSim iterations:** 10 · **Mobsim:** `hermes`
- **Demand:** person-first, NHTS 2022 · **Knobs:** `work_scaling_multiplier` 1.1, `nonwork_trip_share` 2.0
- **Non-work destinations:** distance decay `beta` lowered to 1.2 (Social, Dining, Other) and 1.3 (Shopping)
- **Freight:** on, boundary trucks from HPMS, `demand_scale` 0.18
- **Runtime:** ~10.4 h total (plans 77 min, MATSim 8.7 h, evaluation 23 min) on a 64-CPU, 245 GB server

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

## How this run was calibrated

The first Chicago run with neutral knobs (`chi_s20_w10_nw10_fr018_10iter`) passed the
survey checks on the plans, but its count total was only 0.60. The counts were too low in
every hour, and most in the afternoon. Two more runs raised the demand in steps:

| Run | Work | Non-work | Non-work `beta` | Agents | Total sim/obs |
|-----|-----:|---------:|-----------------|-------:|--------------:|
| `chi_s20_w10_nw10_fr018_10iter` | 1.0 | 1.0 | 1.4–1.6 | 1,099,789 | 0.597 |
| `chi_s20_w11_nw16_b12_fr018_10iter_h107` | 1.1 | 1.6 | 1.2–1.3 | 1,532,168 | 0.807 |
| **This run** | **1.1** | **2.0** | **1.2–1.3** | **1,792,916** | **0.887** |

- **Work stays near neutral.** The morning was already the best block (0.72) and the most
  congested. Most of the deficit was at midday and in the afternoon, which is non-work time.
- **Lower non-work `beta`.** The non-work trips were short (median 0.63 of NHTS after the
  network correction), so they stayed on local roads and did not reach the count
  stations on highways and arterials. A lower `beta` makes the destinations farther away.
- **No further increase.** From non-work 1.6 to 2.0 the total rose by only 0.08. Hours
  22–23 went above 1.0, and stuck agents rose from 66k to 89k. The remaining errors are
  in the shape of the day and in the station spread, not in the level (see
  [Known limits](#known-limits)).

---

## How to reproduce

This run used [`config_used.json`](config_used.json). To run it again, copy the config
into the `config/` folder and start it:

```bash
# from the repository root, with the virtualenv activated
cp examples/chicago-20261003/config_used.json config/chicago.json
python run_experiment.py --config config/chicago.json
```

Before you start, change these values in the config for your machine:

| Field | Value in this run | Change to |
|-------|-------------------|-----------|
| `data.data_dir` | server path | the `data/` folder of your clone |
| `matsim.heap_size_gb` | 180 (with `matsim.heap_ram_fraction` 0.80) | less than your RAM |
| `plan_generation.num_processes` | 60 | your CPU count, or less |
| `matsim.configurable_params.global.numberOfThreads` | 60 | your CPU count, or less |

> **Memory.** This run needs a large Java heap. With 1.53 million agents, a run with an
> 85 GB heap stopped with `OutOfMemoryError` in iteration 4; 107 GB was enough. This run
> (1.79 million agents) used a 180 GB heap. The heap is the smaller of `heap_size_gb` and
> `heap_ram_fraction` × RAM (default 0.70), so set both. For a smaller machine, lower
> `scaling_factor`.

Output goes to `experiments/<experiment-id>/`. The large files (`network.xml` ≈ 327 MB,
`plans.xml` ≈ 870 MB, the MATSim `output/` folder ≈ 33 GB) are **not** in this folder.
The run above makes them again from the config.

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
- [`experiment_20261003_190652.log`](experiment_20261003_190652.log) — the run log

### Key parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `scaling_factor` (population) | **0.20** | 20% sample of the full population |
| MATSim iterations | **10** | innovation stops after iteration 8 |
| `controller.mobsim` | **hermes** | `hermes.endTime` 36:00:00 |
| `flowCapacityFactor` | 0.20 | equal to the scaling factor, copied to hermes |
| `storageCapacityFactor` | 0.24 | 1.2 × the flow factor, copied to hermes |
| `countsScaleFactor` | 5.0 | 1 / flowCapacityFactor |
| `work_scaling_multiplier` | **1.1** | calibration knob, see above |
| `nonwork_trip_share` | **2.0** | calibration knob, see above |
| Non-work `od_matrix.beta` | Shopping **1.3**, Social/Dining/Other **1.2**, School 2.0 | longer non-work trips |
| `freight.demand_scale` | **0.18** | see [Freight](#freight) |
| `data.survey_months` | `regular` | Mar-May, Sep-Nov survey days |
| `counts.fha.month` | 10 | October 2024 counts |

### Scenario scale

| | |
|---|---|
| Total population (3 counties) | 6,921,456 |
| Agents simulated | 1,792,916 (452,801 work · 1,305,705 non-work · 34,410 freight) |
| Stuck agents | 88,735 (4.9%) |
| Network | 269,272 nodes · 643,032 links |
| Transit (GTFS) | bus, rail (Metra) and subway (CTA 'L') |
| Generated mode split (legs) | car 87.7% · pt 9.5% · walk 2.8% |

---

## Headline results

Simulated against observed link volumes at **23 physical count stations**
(42 directional counts, 1,008 station-hours). Values are MATSim's count comparison, the
average of iterations 1-10.

| Metric | Value | Target | Status |
|--------|------:|--------|:------:|
| **Overall volume (sim/obs)** | **0.887** | 1.0 ± 0.10 | CHECK |
| Volume level (interquartile mean) | 0.881 | 1.0 ± 0.10 | CHECK |
| Per-station ratio CV | 0.549 | < 0.35 | CHECK |
| Correlation (sim vs obs) | 0.815 | > 0.85 | CHECK |
| % hourly counts with GEH < 5 | 30.5% | > 85% | CHECK |
| MAE / RMSE | 364 / 633 veh/h | | |

Against the first Chicago run with neutral knobs:

| Metric | Neutral knobs (0.597 run) | This run |
|--------|-------------:|---------:|
| Overall volume | 0.597 | **0.887** |
| Interquartile mean | 0.556 | **0.881** |
| Median station ratio | 0.554 | **0.863** |
| Station ratio p10 / p90 | 0.20 / 0.82 | 0.37 / 1.47 |
| Per-station CV | **0.467** | 0.549 |
| Correlation | **0.864** | 0.815 |
| GEH < 5 | 19.8% | **30.5%** |
| Mean leg duration | **33 min** | 57 min |

### Time of day

| Block | Hours | Neutral knobs | Non-work 1.6 | This run |
|-------|-------|--------------:|-------------:|---------:|
| Night | 0–3 | 0.25 | 0.29 | 0.31 |
| Morning | 4–9 | 0.72 | 0.86 | 0.91 |
| Midday | 10–17 | 0.57 | 0.82 | 0.89 |
| Evening | 18–23 | 0.54 | 0.79 | 0.93 |

Sim/obs per hour:

```
hour   0    1    2    3    4    5    6    7    8    9   10   11   12   13   14   15   16   17   18   19   20   21   22   23
     0.31 0.21 0.40 0.31 0.56 0.69 0.80 1.02 1.01 1.03 1.07 1.00 0.92 0.90 0.89 0.87 0.79 0.76 0.80 0.88 0.92 0.98 1.04 1.19
```

### Demand against the survey (NHTS 2022)

| Quantity | Simulated | NHTS 2022 | Ratio |
|----------|----------:|----------:|------:|
| Trips per person per day | 2.78 | 2.82 | 0.99 |
| Median trip length (km) | 5.71 | 6.93 | 0.82 (0.66 after the 1.25 network correction) |
| Car share | 82.6% | 87.4% | −4.8 pp |
| Transit share | 9.4% | 4.4% | +5.0 pp |

The trips per person is per simulated agent (travellers only), so it does not show the
knobs: with non-work 2.0 there are many more travellers per resident than the survey
gives. NHTS is the national survey; Chicago has more transit than the national mean, so a
higher transit share is expected. No local household travel survey is loaded for this
region.

### Freight

Measured from the events of iteration 10 on the count links
([`evaluation/freight_share_it10.txt`](evaluation/freight_share_it10.txt)):

| Block | Freight share of simulated volume | Ratio | Ratio without freight |
|-------|----------------------------------:|------:|----------------------:|
| Night | 31.5% | 0.31 | 0.22 |
| Morning | 3.1% | 1.00 | 0.97 |
| Midday | 4.4% | 1.00 | 0.96 |
| Evening | 4.3% | 1.00 | 0.96 |
| **All** | **4.3%** | **0.98** | **0.94** |

- Freight is 4.2% of the observed volume. TMAS measures about 4% heavy trucks in this
  region, so `demand_scale` 0.18 is about right.
- The median count direction has 2.1% freight. All freight trips cross the region
  boundary, so the freight is concentrated at the edge stations (up to 15.5%).

**Final iteration.** At iteration 10 alone (from its events) the total is 0.98 and the
three day blocks are all at 1.00. The headline values above are lower (0.887) because
the earlier, more congested iterations are in them too.

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

## Known limits

- **Afternoon peak.** 16–17 h is the lowest daytime hour (0.76–0.79). In the plans the
  afternoon departures peak at 15 h, but the counts peak at 17 h. Most work arrivals are
  at 6–7 h, so the trips home start too early. A higher demand level does not fix this.
- **Late evening.** 22–23 h is above 1.0 (1.04 and 1.19). A further non-work increase
  would make it worse.
- **Station spread.** 12 of 42 count directions are above 1.0 while others stay near 0.4
  (CV 0.55). The demand increase went partly to corridors that already had enough
  traffic. In the first run, most of the missing volume was at arterial stations where
  the simulated traffic flowed freely.
- **Congestion.** The mean leg takes 57 min and 4.9% of agents are stuck. The demand is
  above what the survey gives per resident, and the morning work trips are long (boundary
  commuters).
- **Night.** 0–3 h is at 0.31. The plans have almost no night trips.
- **Few counts.** Only 23 physical stations are matched in a region of 6.9 million
  people.

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
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001050_1_linkid_430023.png"><img src="evaluation/device_reports/device_FHA_17_001050_1_linkid_430023.png" width="100%"></a><br><sub>IL 001050 dir1 (link 430023)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001050_5_linkid_430021.png"><img src="evaluation/device_reports/device_FHA_17_001050_5_linkid_430021.png" width="100%"></a><br><sub>IL 001050 dir5 (link 430021)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001121-p2_1_linkid_562936.png"><img src="evaluation/device_reports/device_FHA_17_001121-p2_1_linkid_562936.png" width="100%"></a><br><sub>IL 001121-p2 dir1 (link 562936)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001121_1_linkid_88952.png"><img src="evaluation/device_reports/device_FHA_17_001121_1_linkid_88952.png" width="100%"></a><br><sub>IL 001121 dir1 (link 88952)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001125-p2_5_linkid_374298.png"><img src="evaluation/device_reports/device_FHA_17_001125-p2_5_linkid_374298.png" width="100%"></a><br><sub>IL 001125-p2 dir5 (link 374298)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001125_5_linkid_562926.png"><img src="evaluation/device_reports/device_FHA_17_001125_5_linkid_562926.png" width="100%"></a><br><sub>IL 001125 dir5 (link 562926)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001170_1_linkid_647413.png"><img src="evaluation/device_reports/device_FHA_17_001170_1_linkid_647413.png" width="100%"></a><br><sub>IL 001170 dir1 (link 647413)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001170_5_linkid_647412.png"><img src="evaluation/device_reports/device_FHA_17_001170_5_linkid_647412.png" width="100%"></a><br><sub>IL 001170 dir5 (link 647412)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001180_3_linkid_539722.png"><img src="evaluation/device_reports/device_FHA_17_001180_3_linkid_539722.png" width="100%"></a><br><sub>IL 001180 dir3 (link 539722)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001180_7_linkid_539721.png"><img src="evaluation/device_reports/device_FHA_17_001180_7_linkid_539721.png" width="100%"></a><br><sub>IL 001180 dir7 (link 539721)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001190_1_linkid_140698.png"><img src="evaluation/device_reports/device_FHA_17_001190_1_linkid_140698.png" width="100%"></a><br><sub>IL 001190 dir1 (link 140698)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001190_5_linkid_140699.png"><img src="evaluation/device_reports/device_FHA_17_001190_5_linkid_140699.png" width="100%"></a><br><sub>IL 001190 dir5 (link 140699)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001200_1_linkid_286505.png"><img src="evaluation/device_reports/device_FHA_17_001200_1_linkid_286505.png" width="100%"></a><br><sub>IL 001200 dir1 (link 286505)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001200_5_linkid_286504.png"><img src="evaluation/device_reports/device_FHA_17_001200_5_linkid_286504.png" width="100%"></a><br><sub>IL 001200 dir5 (link 286504)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001210_3_linkid_340598.png"><img src="evaluation/device_reports/device_FHA_17_001210_3_linkid_340598.png" width="100%"></a><br><sub>IL 001210 dir3 (link 340598)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001210_7_linkid_340597.png"><img src="evaluation/device_reports/device_FHA_17_001210_7_linkid_340597.png" width="100%"></a><br><sub>IL 001210 dir7 (link 340597)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001220_1_linkid_282336.png"><img src="evaluation/device_reports/device_FHA_17_001220_1_linkid_282336.png" width="100%"></a><br><sub>IL 001220 dir1 (link 282336)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001220_5_linkid_282337.png"><img src="evaluation/device_reports/device_FHA_17_001220_5_linkid_282337.png" width="100%"></a><br><sub>IL 001220 dir5 (link 282337)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001260_3_linkid_215411.png"><img src="evaluation/device_reports/device_FHA_17_001260_3_linkid_215411.png" width="100%"></a><br><sub>IL 001260 dir3 (link 215411)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001260_7_linkid_487733.png"><img src="evaluation/device_reports/device_FHA_17_001260_7_linkid_487733.png" width="100%"></a><br><sub>IL 001260 dir7 (link 487733)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001270_3_linkid_21555.png"><img src="evaluation/device_reports/device_FHA_17_001270_3_linkid_21555.png" width="100%"></a><br><sub>IL 001270 dir3 (link 21555)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001270_7_linkid_21556.png"><img src="evaluation/device_reports/device_FHA_17_001270_7_linkid_21556.png" width="100%"></a><br><sub>IL 001270 dir7 (link 21556)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001280_1_linkid_23943.png"><img src="evaluation/device_reports/device_FHA_17_001280_1_linkid_23943.png" width="100%"></a><br><sub>IL 001280 dir1 (link 23943)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001280_5_linkid_23944.png"><img src="evaluation/device_reports/device_FHA_17_001280_5_linkid_23944.png" width="100%"></a><br><sub>IL 001280 dir5 (link 23944)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001310_1_linkid_374509.png"><img src="evaluation/device_reports/device_FHA_17_001310_1_linkid_374509.png" width="100%"></a><br><sub>IL 001310 dir1 (link 374509)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001310_5_linkid_321196.png"><img src="evaluation/device_reports/device_FHA_17_001310_5_linkid_321196.png" width="100%"></a><br><sub>IL 001310 dir5 (link 321196)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001320_3_linkid_487320.png"><img src="evaluation/device_reports/device_FHA_17_001320_3_linkid_487320.png" width="100%"></a><br><sub>IL 001320 dir3 (link 487320)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001320_7_linkid_496973.png"><img src="evaluation/device_reports/device_FHA_17_001320_7_linkid_496973.png" width="100%"></a><br><sub>IL 001320 dir7 (link 496973)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001330_3_linkid_418916.png"><img src="evaluation/device_reports/device_FHA_17_001330_3_linkid_418916.png" width="100%"></a><br><sub>IL 001330 dir3 (link 418916)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001330_7_linkid_418915.png"><img src="evaluation/device_reports/device_FHA_17_001330_7_linkid_418915.png" width="100%"></a><br><sub>IL 001330 dir7 (link 418915)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001340_1_linkid_343082.png"><img src="evaluation/device_reports/device_FHA_17_001340_1_linkid_343082.png" width="100%"></a><br><sub>IL 001340 dir1 (link 343082)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001340_5_linkid_333300.png"><img src="evaluation/device_reports/device_FHA_17_001340_5_linkid_333300.png" width="100%"></a><br><sub>IL 001340 dir5 (link 333300)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001350_1_linkid_445117.png"><img src="evaluation/device_reports/device_FHA_17_001350_1_linkid_445117.png" width="100%"></a><br><sub>IL 001350 dir1 (link 445117)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001350_5_linkid_445118.png"><img src="evaluation/device_reports/device_FHA_17_001350_5_linkid_445118.png" width="100%"></a><br><sub>IL 001350 dir5 (link 445118)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001500_1_linkid_193379.png"><img src="evaluation/device_reports/device_FHA_17_001500_1_linkid_193379.png" width="100%"></a><br><sub>IL 001500 dir1 (link 193379)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001500_5_linkid_193378.png"><img src="evaluation/device_reports/device_FHA_17_001500_5_linkid_193378.png" width="100%"></a><br><sub>IL 001500 dir5 (link 193378)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001520_3_linkid_20088.png"><img src="evaluation/device_reports/device_FHA_17_001520_3_linkid_20088.png" width="100%"></a><br><sub>IL 001520 dir3 (link 20088)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001520_7_linkid_20115.png"><img src="evaluation/device_reports/device_FHA_17_001520_7_linkid_20115.png" width="100%"></a><br><sub>IL 001520 dir7 (link 20115)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001530_3_linkid_282627.png"><img src="evaluation/device_reports/device_FHA_17_001530_3_linkid_282627.png" width="100%"></a><br><sub>IL 001530 dir3 (link 282627)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001530_7_linkid_282628.png"><img src="evaluation/device_reports/device_FHA_17_001530_7_linkid_282628.png" width="100%"></a><br><sub>IL 001530 dir7 (link 282628)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001560_3_linkid_140747.png"><img src="evaluation/device_reports/device_FHA_17_001560_3_linkid_140747.png" width="100%"></a><br><sub>IL 001560 dir3 (link 140747)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_17_001560_7_linkid_140748.png"><img src="evaluation/device_reports/device_FHA_17_001560_7_linkid_140748.png" width="100%"></a><br><sub>IL 001560 dir7 (link 140748)</sub></td>
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

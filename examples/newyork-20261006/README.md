# New York, NY-NJ experiment — 2026-10-06

A full Tareek run for the New York metro core, compared against FHA directional traffic
counts. It uses person-first demand, freight and the Hermes mobsim, in the same way as
the [Chicago example](../chicago-20261003/). It is the first New York example.

- **Experiment ID:** `ny_s10_modes28_pce_10iter`
- **Region:** 10 counties — the five boroughs: New York (`36061`), Kings (`36047`),
  Queens (`36081`), Bronx (`36005`), Richmond (`36085`); Westchester (`36119`); and in New
  Jersey: Bergen (`34003`), Hudson (`34017`), Essex (`34013`), Union (`34039`)
- **Scaling factor:** `0.10` (10% population sample) · **MATSim iterations:** 10 · **Mobsim:** `hermes`
- **Demand:** person-first, NHTS 2022 · **Knobs:** `work_scaling_multiplier` 1.1, `nonwork_trip_share` 2.0
- **Freight:** on, boundary trucks from HPMS, `demand_scale` 0.18
- **Runtime:** ~10.7 h total (plans 1.7 h, MATSim 8.5 h, evaluation 30 min) on a 64-CPU,
  245 GB server. The first run in a new region also builds the NY+NJ network.

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

New York has much more transit than the other example regions, so this run changes the
mode rates and the transit vehicles:

| Change | Earlier examples | This run |
|--------|---------|----------|
| Mode rates | NHTS national rates (car about 87% of trips) | set from the ACS 2023 commute shares of the 10 counties: `config_rate` car **0.28**, rail **0.32**, bus **0.14**, walk **0.26**, all `blend_weight` **1.0** |
| Transit vehicle PCE | full size (bus 2.8) | scaled by `flowCapacityFactor` (bus **0.28**, rail 2.71, subway 0.44, tram 0.52), with the new `matsim.scale_transit_pce` (default on) |
| Count matching | nearest link | car links only, and a station skips a link that cannot carry its observed peak |
| `storageCapacityFactor` | 1.2 × the flow factor | **0.18** (about flow^0.75) |

- **Mode rates.** ACS 2023 (table B08301) gives car 44.4%, transit 42.5% and walk 8.8% of
  the commuters in these 10 counties (Manhattan: car 9%, transit 59%). The mode
  availability filter moves legs back to car, so the configured car rate (0.28) is lower
  than the target. The generated work legs are car 48.7% · pt 42.0% · walk 9.3%.
- **Transit vehicle PCE.** pt2matsim writes the transit vehicles at full size, but the
  road capacity is scaled to the 10% sample, and Hermes applies the PCE. Without the
  scaling, one bus takes the road space of 28 sampled cars.

---

## How to reproduce

This run used [`config_used.json`](config_used.json). To run it again, copy the config
into the `config/` folder and start it:

```bash
# from the repository root, with the virtualenv activated
cp examples/newyork-20261006/config_used.json config/newyork.json
python run_experiment.py --config config/newyork.json
```

Before you start, change these values in the config for your machine:

| Field | Value in this run | Change to |
|-------|-------------------|-----------|
| `plan_generation.skip_if_exists` | `true` | `false`, so that the run makes its own plans |
| `data.data_dir` | server path | the `data/` folder of your clone |
| `matsim.heap_size_gb` | 200 (with `matsim.heap_ram_fraction` 0.85) | less than your RAM |
| `plan_generation.num_processes` | 60 | your CPU count, or less |
| `matsim.configurable_params.global.numberOfThreads` | 60 | your CPU count, or less |

> **Memory.** This run needs a large Java heap: 1.65 million agents on a network with
> 745,284 links used a 200 GB heap. The heap is the smaller of `heap_size_gb` and
> `heap_ram_fraction` × RAM (default 0.70), so set both. For a smaller machine, lower
> `scaling_factor`.

Output goes to `experiments/<experiment-id>/`. The large files (`network.xml` ≈ 387 MB,
`plans.xml` ≈ 807 MB, the MATSim `output/` folder ≈ 23 GB) are **not** in this folder.
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
- [`experiment_20261005_160806.log`](experiment_20261005_160806.log) — the run log

### Key parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `scaling_factor` (population) | **0.10** | 10% sample of the full population |
| MATSim iterations | **10** | innovation stops after iteration 8 |
| `controller.mobsim` | **hermes** | `hermes.endTime` 36:00:00, `stuckTime` 10 s |
| `flowCapacityFactor` | 0.10 | equal to the scaling factor, copied to hermes |
| `storageCapacityFactor` | 0.18 | about flow^0.75, copied to hermes |
| `countsScaleFactor` | 10.0 | 1 / flowCapacityFactor |
| `work_scaling_multiplier` | **1.1** | calibration knob |
| `nonwork_trip_share` | **2.0** | calibration knob |
| Non-work `od_matrix.beta` | Shopping **1.3**, Social/Dining/Other **1.2**, School 2.0 | longer non-work trips |
| Mode `config_rate` | car **0.28**, rail **0.32**, bus **0.14**, walk **0.26** | `blend_weight` 1.0, see above |
| Scoring | `pt.constant` 1.5, `walk.constant` −1.5, `waitingPt` −1.0 | |
| `freight.demand_scale` | **0.18** | see [Freight](#freight) |
| `matsim.scale_transit_pce` | `true` (default) | see above |
| `data.survey_months` | `regular` | Mar-May, Sep-Nov survey days |
| `counts.fha.month` | 10 | October 2024 counts |

### Scenario scale

| | |
|---|---|
| Total population (10 counties) | 12,946,426 |
| Agents simulated | 1,647,405 (410,468 work · 1,225,839 non-work · 11,098 freight) |
| Stuck agents | 251,393 (15.3%) |
| Network | 318,445 nodes · 745,284 links |
| Transit (GTFS) | bus, subway, rail and tram; 31,805 routes, 91,409 departures |
| Generated mode split (legs) | car 45.2% · pt 46.2% · walk 8.6% |

---

## Headline results

Simulated against observed link volumes at **30 physical count stations**
(46 directional counts, 1,104 station-hours; 22 stations in New Jersey, 8 in New York).
Values are MATSim's count comparison, the average of iterations 1-10.

| Metric | Value | Target | Status |
|--------|------:|--------|:------:|
| **Overall volume (sim/obs)** | **0.827** | 1.0 ± 0.10 | CHECK |
| Volume level (interquartile mean) | 0.763 | 1.0 ± 0.10 | CHECK |
| Per-station ratio CV | 0.807 | < 0.35 | CHECK |
| Correlation (sim vs obs) | 0.659 | > 0.85 | CHECK |
| % hourly counts with GEH < 5 | 11.2% | > 85% | CHECK |
| MAE / RMSE | 897 / 1,206 veh/h | | |

### Time of day

| Block | Hours | This run |
|-------|-------|---------:|
| Night | 0–3 | 0.31 |
| Morning | 4–9 | 0.89 |
| Midday | 10–17 | 0.81 |
| Evening | 18–23 | 0.88 |

Sim/obs per hour:

```
hour   0    1    2    3    4    5    6    7    8    9   10   11   12   13   14   15   16   17   18   19   20   21   22   23
     0.28 0.21 0.38 0.38 0.56 0.82 0.84 0.97 0.94 0.94 0.96 0.91 0.86 0.80 0.76 0.75 0.74 0.73 0.74 0.78 0.87 0.94 1.04 1.23
```

The morning is the best block. The afternoon (14–19 h) is the lowest daytime period
(0.73–0.78), and 22–23 h is above 1.0.

**Final iteration.** At iteration 10 alone (from its events) the total is 0.95, and the
morning and evening blocks are at 1.0. The headline values above are lower (0.827)
because the earlier, more congested iterations are in them too.

### Demand against the survey (NHTS 2022)

| Quantity | Simulated | NHTS 2022 | Ratio |
|----------|----------:|----------:|------:|
| Trips per person per day | 2.69 | 2.82 | 0.96 |
| Median trip length (km) | 3.23 | 6.93 | 0.47 (0.37 after the 1.25 network correction) |
| Car share | 52.2% | 87.4% | −35.2 pp |
| Transit share | 29.5% | 4.4% | +25.0 pp |

NHTS is the national survey. New York has much more transit and shorter trips than the
national mean, so the large car and transit differences are expected. The mode target
for this region is the ACS commute split (see
[What is new in this run](#what-is-new-in-this-run)): the generated work legs are within
5 pp of it. No local household travel survey is loaded for this region.

### Freight

Measured from the events of iteration 10 on the count links
([`evaluation/freight_share_it10.txt`](evaluation/freight_share_it10.txt)):

| Block | Freight share of simulated volume | Ratio | Ratio without freight |
|-------|----------------------------------:|------:|----------------------:|
| Night | 25.3% | 0.33 | 0.24 |
| Morning | 2.7% | 1.01 | 0.98 |
| Midday | 3.8% | 0.93 | 0.89 |
| Evening | 3.5% | 1.03 | 1.00 |
| **All** | **3.7%** | **0.95** | **0.91** |

- Freight is 3.5% of the observed volume.
- The median count direction has 3.1% freight. All freight trips cross the region
  boundary, so the freight is concentrated at the edge stations (up to 22.9%).

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

- **Congestion.** 15.3% of agents do not finish their day by 36:00, and 17% of car legs
  and 14% of pt legs take more than 2 h. The queues build from 7 h and stay until 23 h.
  Of all delay, 26% is on 1-lane motorway ramps and 16% on residential streets that carry
  only through traffic.
- **Hudson crossings.** The lanes in the network follow OSM and look correct, but the
  simulated volume on the George Washington Bridge and the Lincoln and Holland tunnels
  (about 690k vehicles a day) is about 1.5 times the real volume (an approximate value
  from Port Authority toll figures). The Lincoln and Holland
  tunnels run at capacity until 23 h.
- **PATH is missing.** The PATH GTFS feed is not loaded, so there is no rail
  between Jersey City/Hoboken and lower Manhattan. Those trips go by car or bus.
- **Walk across water.** Walk is teleported along a straight line. At iteration 10, about
  475k walk trips a day cross the Hudson (3.7k in the plans). Walk rises from 8.6% of the
  generated legs to 17.5% in the simulation when car and pt are congested.
- **NJ freeways too low.** The New Jersey Turnpike stations are at 0.12–0.15, and I-280 and
  I-287 are also low. Through traffic and external traffic (other than freight) are not
  in the demand.
- **Suspect count.** The Clearview Expressway station `FHA_36_000598` observes only
  11–12k vehicles a day, and the simulation gives 2.6–3.8 times that. The count is
  probably wrong.
- **Night.** 0–3 h is at 0.31. The plans have almost no night trips.
- **Few counts.** Only 30 physical stations are matched in a region of 12.9 million
  people, and only 8 of them are in New York State. The HPMS download for freight stopped
  at its 80,000-segment limit.

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
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_000017_5_linkid_315260.png"><img src="evaluation/device_reports/device_FHA_34_000017_5_linkid_315260.png" width="100%"></a><br><sub>NJ 000017 dir5 (link 315260)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_00003R-p2_3_linkid_598889.png"><img src="evaluation/device_reports/device_FHA_34_00003R-p2_3_linkid_598889.png" width="100%"></a><br><sub>NJ 00003R-p2 dir3 (link 598889)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_00003R-p2_7_linkid_598890.png"><img src="evaluation/device_reports/device_FHA_34_00003R-p2_7_linkid_598890.png" width="100%"></a><br><sub>NJ 00003R-p2 dir7 (link 598890)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_00003R_3_linkid_33938.png"><img src="evaluation/device_reports/device_FHA_34_00003R_3_linkid_33938.png" width="100%"></a><br><sub>NJ 00003R dir3 (link 33938)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_00003R_7_linkid_730001.png"><img src="evaluation/device_reports/device_FHA_34_00003R_7_linkid_730001.png" width="100%"></a><br><sub>NJ 00003R dir7 (link 730001)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_000208_1_linkid_100972.png"><img src="evaluation/device_reports/device_FHA_34_000208_1_linkid_100972.png" width="100%"></a><br><sub>NJ 000208 dir1 (link 100972)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_000208_5_linkid_580109.png"><img src="evaluation/device_reports/device_FHA_34_000208_5_linkid_580109.png" width="100%"></a><br><sub>NJ 000208 dir5 (link 580109)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_00022C_3_linkid_78074.png"><img src="evaluation/device_reports/device_FHA_34_00022C_3_linkid_78074.png" width="100%"></a><br><sub>NJ 00022C dir3 (link 78074)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_000280_7_linkid_564920.png"><img src="evaluation/device_reports/device_FHA_34_000280_7_linkid_564920.png" width="100%"></a><br><sub>NJ 000280 dir7 (link 564920)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_000287_1_linkid_566410.png"><img src="evaluation/device_reports/device_FHA_34_000287_1_linkid_566410.png" width="100%"></a><br><sub>NJ 000287 dir1 (link 566410)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_000287_5_linkid_566715.png"><img src="evaluation/device_reports/device_FHA_34_000287_5_linkid_566715.png" width="100%"></a><br><sub>NJ 000287 dir5 (link 566715)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_0080DL-p2_3_linkid_184746.png"><img src="evaluation/device_reports/device_FHA_34_0080DL-p2_3_linkid_184746.png" width="100%"></a><br><sub>NJ 0080DL-p2 dir3 (link 184746)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_0080DL-p2_7_linkid_132973.png"><img src="evaluation/device_reports/device_FHA_34_0080DL-p2_7_linkid_132973.png" width="100%"></a><br><sub>NJ 0080DL-p2 dir7 (link 132973)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_0080DL_3_linkid_488795.png"><img src="evaluation/device_reports/device_FHA_34_0080DL_3_linkid_488795.png" width="100%"></a><br><sub>NJ 0080DL dir3 (link 488795)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_0080DL_7_linkid_253124.png"><img src="evaluation/device_reports/device_FHA_34_0080DL_7_linkid_253124.png" width="100%"></a><br><sub>NJ 0080DL dir7 (link 253124)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_E02123_3_linkid_714945.png"><img src="evaluation/device_reports/device_FHA_34_E02123_3_linkid_714945.png" width="100%"></a><br><sub>NJ E02123 dir3 (link 714945)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_E02132_3_linkid_226105.png"><img src="evaluation/device_reports/device_FHA_34_E02132_3_linkid_226105.png" width="100%"></a><br><sub>NJ E02132 dir3 (link 226105)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_E03123_3_linkid_262261.png"><img src="evaluation/device_reports/device_FHA_34_E03123_3_linkid_262261.png" width="100%"></a><br><sub>NJ E03123 dir3 (link 262261)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_N00440_1_linkid_730028.png"><img src="evaluation/device_reports/device_FHA_34_N00440_1_linkid_730028.png" width="100%"></a><br><sub>NJ N00440 dir1 (link 730028)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_N02120_1_linkid_172626.png"><img src="evaluation/device_reports/device_FHA_34_N02120_1_linkid_172626.png" width="100%"></a><br><sub>NJ N02120 dir1 (link 172626)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_N02131_1_linkid_18991.png"><img src="evaluation/device_reports/device_FHA_34_N02131_1_linkid_18991.png" width="100%"></a><br><sub>NJ N02131 dir1 (link 18991)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_N03121_1_linkid_370725.png"><img src="evaluation/device_reports/device_FHA_34_N03121_1_linkid_370725.png" width="100%"></a><br><sub>NJ N03121 dir1 (link 370725)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_S00440_5_linkid_494174.png"><img src="evaluation/device_reports/device_FHA_34_S00440_5_linkid_494174.png" width="100%"></a><br><sub>NJ S00440 dir5 (link 494174)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_S02120_5_linkid_559164.png"><img src="evaluation/device_reports/device_FHA_34_S02120_5_linkid_559164.png" width="100%"></a><br><sub>NJ S02120 dir5 (link 559164)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_S02131_5_linkid_480549.png"><img src="evaluation/device_reports/device_FHA_34_S02131_5_linkid_480549.png" width="100%"></a><br><sub>NJ S02131 dir5 (link 480549)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_S03121_5_linkid_370726.png"><img src="evaluation/device_reports/device_FHA_34_S03121_5_linkid_370726.png" width="100%"></a><br><sub>NJ S03121 dir5 (link 370726)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_W02123_7_linkid_714948.png"><img src="evaluation/device_reports/device_FHA_34_W02123_7_linkid_714948.png" width="100%"></a><br><sub>NJ W02123 dir7 (link 714948)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_34_W03123_7_linkid_750933.png"><img src="evaluation/device_reports/device_FHA_34_W03123_7_linkid_750933.png" width="100%"></a><br><sub>NJ W03123 dir7 (link 750933)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000180_1_linkid_541118.png"><img src="evaluation/device_reports/device_FHA_36_000180_1_linkid_541118.png" width="100%"></a><br><sub>NY 000180 dir1 (link 541118)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000180_5_linkid_520820.png"><img src="evaluation/device_reports/device_FHA_36_000180_5_linkid_520820.png" width="100%"></a><br><sub>NY 000180 dir5 (link 520820)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000191_1_linkid_493574.png"><img src="evaluation/device_reports/device_FHA_36_000191_1_linkid_493574.png" width="100%"></a><br><sub>NY 000191 dir1 (link 493574)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000191_5_linkid_359139.png"><img src="evaluation/device_reports/device_FHA_36_000191_5_linkid_359139.png" width="100%"></a><br><sub>NY 000191 dir5 (link 359139)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000299_3_linkid_258274.png"><img src="evaluation/device_reports/device_FHA_36_000299_3_linkid_258274.png" width="100%"></a><br><sub>NY 000299 dir3 (link 258274)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000299_7_linkid_706213.png"><img src="evaluation/device_reports/device_FHA_36_000299_7_linkid_706213.png" width="100%"></a><br><sub>NY 000299 dir7 (link 706213)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000580_3_linkid_300434.png"><img src="evaluation/device_reports/device_FHA_36_000580_3_linkid_300434.png" width="100%"></a><br><sub>NY 000580 dir3 (link 300434)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000580_7_linkid_225872.png"><img src="evaluation/device_reports/device_FHA_36_000580_7_linkid_225872.png" width="100%"></a><br><sub>NY 000580 dir7 (link 225872)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000581_1_linkid_26932.png"><img src="evaluation/device_reports/device_FHA_36_000581_1_linkid_26932.png" width="100%"></a><br><sub>NY 000581 dir1 (link 26932)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000581_5_linkid_476650.png"><img src="evaluation/device_reports/device_FHA_36_000581_5_linkid_476650.png" width="100%"></a><br><sub>NY 000581 dir5 (link 476650)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000597_3_linkid_584262.png"><img src="evaluation/device_reports/device_FHA_36_000597_3_linkid_584262.png" width="100%"></a><br><sub>NY 000597 dir3 (link 584262)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000598_1_linkid_169791.png"><img src="evaluation/device_reports/device_FHA_36_000598_1_linkid_169791.png" width="100%"></a><br><sub>NY 000598 dir1 (link 169791)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000598_5_linkid_332954.png"><img src="evaluation/device_reports/device_FHA_36_000598_5_linkid_332954.png" width="100%"></a><br><sub>NY 000598 dir5 (link 332954)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000640_1_linkid_497064.png"><img src="evaluation/device_reports/device_FHA_36_000640_1_linkid_497064.png" width="100%"></a><br><sub>NY 000640 dir1 (link 497064)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_36_000640_5_linkid_497071.png"><img src="evaluation/device_reports/device_FHA_36_000640_5_linkid_497071.png" width="100%"></a><br><sub>NY 000640 dir5 (link 497071)</sub></td>
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

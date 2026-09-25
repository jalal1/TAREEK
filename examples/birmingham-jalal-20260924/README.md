# Birmingham, AL experiment — Jalal, 2026-09-24

A full Tareek run for the Birmingham metro core, compared against FHA directional
traffic counts.

- **Experiment ID:** `bham_stage2e_c2chains`
- **Region:** 2 Alabama counties — Jefferson (`01073`, Birmingham) and Shelby (`01117`)
- **Scaling factor:** `0.25` (25% population sample) · **MATSim iterations:** 10 · **Mobsim:** `qsim`
- **Chain sampling:** `generated` (the Markov chain sampler with the length-aware stop rule)
- **Runtime:** ~91 min total (plans 6 min, MATSim 76 min, evaluation 7 min) on a 32-CPU server

---

## Full report

**[`report.html`](report.html)** is the complete experiment report: the verdict, the
demand check against the household survey, the count validation, and all the
evaluation figures (hourly error maps, heatmaps, trip timing and more). It is one
self-contained file. All the images are inside it.

> **How to open it:** GitHub does not show HTML pages. Open
> [`report.html`](report.html) on GitHub, click **Download raw file**, then open the
> downloaded file in a web browser. Or clone the repository and open the file locally.

To make the same report for your own run:

```bash
python scripts/experiment_report.py experiments/<experiment-id> --no-pdf
```

---

## How to reproduce

This run used [`config_used.json`](config_used.json). To run it again, copy the config
into the `config/` folder and start it:

```bash
# from the repository root, with the virtualenv activated
cp examples/birmingham-jalal-20260924/config_used.json config/birmingham.json
python run_experiment.py --config config/birmingham.json
```

Before you start, change these values in the config for your machine:

| Field | Value in this run | Change to |
|-------|-------------------|-----------|
| `data.data_dir` | server path | the `data/` folder of your clone |
| `matsim.heap_size_gb` | 70 | less than your RAM |
| `plan_generation.num_processes` | 30 | your CPU count, or less |

Output goes to `experiments/<experiment-id>/`. The large files (`network.xml` ≈ 98 MB,
`plans.xml` ≈ 107 MB, the MATSim `output/` folder) are **not** in this folder. The run
above makes them again from the config.

For the setup steps, see the **[project README](../../README.md#quick-start)**. The two
API keys in the config are **optional** — see [Optional API keys](#optional-api-keys).

---

## Configuration

- [`config_used.json`](config_used.json) — the full Tareek config for this run
- [`config.xml`](config.xml) — the MATSim config that Tareek made
- [`counts.xml`](counts.xml) — the observed counts given to MATSim
- [`matched_devices.csv`](matched_devices.csv) — FHA count devices matched to network links
- [`od_matrix_diagnostics.json`](od_matrix_diagnostics.json) — checks on the work OD matrix
- [`experiment_summary.json`](experiment_summary.json) — the full machine-readable run summary
- [`experiment_20260924_213725.log`](experiment_20260924_213725.log) — the run log

### Key parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `scaling_factor` (population) | **0.25** | 25% sample of the full population |
| MATSim iterations | **10** | |
| `flowCapacityFactor` | 0.25 | equal to the scaling factor |
| `storageCapacityFactor` | 0.30 | 1.2 × the flow factor |
| `stuckTime` | 10 s | the MATSim default |
| `countsScaleFactor` | 4.0 | 1 / flowCapacityFactor |
| `chain_sampling_method` | `generated` | |

### Scenario scale

| | |
|---|---|
| Total population (2 counties) | 893,851 |
| Agents simulated | 223,499 (100% of plans made) |
| Stuck agents | 605 |
| Network | 89,851 nodes · 204,379 links |
| Generated mode split (legs) | car 93.0% · walk 5.8% · pt 1.2% |
| Transit supply | 14 routes · 998 trips · 951 stops |

---

## Headline results

Simulated against observed link volumes at **36 physical count stations**
(53 directional counts, 1,272 station-hours).

| Metric | Value | Target | Status |
|--------|------:|--------|:------:|
| **Overall volume (sim/obs)** | **0.945** | 1.0 ± 0.10 | PASS |
| Volume level (interquartile mean) | 0.884 | 1.0 ± 0.10 | CHECK |
| Per-station ratio CV | 0.761 | < 0.35 | CHECK |
| Correlation (sim vs obs) | 0.776 | > 0.85 | CHECK |
| % hourly counts with GEH < 5 | 22.4% | > 85% | CHECK |
| MAE / RMSE | 453 / 671 veh/h | | |

The total volume is correct, but the stations do not agree: 17 station-directions are
above 1.1 and 32 are below 0.9. The error is at specific locations, not a uniform
factor.

### Time of day

| Block | Hours | Sim/Obs |
|-------|-------|--------:|
| Night | 0–3 | 0.16 |
| Morning | 4–9 | 1.09 |
| Midday | 10–17 | 0.82 |
| Evening | 18–23 | 1.19 |

### Demand against the survey (NHTS 2022)

| Quantity | Simulated | NHTS 2022 | Ratio |
|----------|----------:|----------:|------:|
| Trips per person per day | 2.98 | 2.82 | 1.06 |
| Median trip length (km, after the 1.25 network correction) | 6.91 | 6.93 | 1.00 |
| Car share | 93.2% | 87.4% | +5.9 pp |
| Transit share | 0.3% | 4.4% | −4.1 pp |

No local household travel survey is loaded for this region, so the reference is the
national survey.

### Where the error is

| | |
|---|---|
| ![Station ratios](evaluation/station_ratio_dotplot.png) | ![Hourly error](evaluation/hourly_relative_error_box.png) |
| Sim/obs ratio per station, sorted | Signed relative error per hour, all stations |

![Spatial overview](evaluation/spatial_overview.png)

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
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000114_1_linkid_14240.png"><img src="evaluation/device_reports/device_FHA_01_000114_1_linkid_14240.png" width="100%"></a><br><sub>AL 000114 dir1 (link 14240)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000114_5_linkid_57301.png"><img src="evaluation/device_reports/device_FHA_01_000114_5_linkid_57301.png" width="100%"></a><br><sub>AL 000114 dir5 (link 57301)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000115_1_linkid_14256.png"><img src="evaluation/device_reports/device_FHA_01_000115_1_linkid_14256.png" width="100%"></a><br><sub>AL 000115 dir1 (link 14256)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000115_5_linkid_81860.png"><img src="evaluation/device_reports/device_FHA_01_000115_5_linkid_81860.png" width="100%"></a><br><sub>AL 000115 dir5 (link 81860)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000116_1_linkid_176314.png"><img src="evaluation/device_reports/device_FHA_01_000116_1_linkid_176314.png" width="100%"></a><br><sub>AL 000116 dir1 (link 176314)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000116_5_linkid_18294.png"><img src="evaluation/device_reports/device_FHA_01_000116_5_linkid_18294.png" width="100%"></a><br><sub>AL 000116 dir5 (link 18294)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000117_1_linkid_62831.png"><img src="evaluation/device_reports/device_FHA_01_000117_1_linkid_62831.png" width="100%"></a><br><sub>AL 000117 dir1 (link 62831)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000117_5_linkid_159046.png"><img src="evaluation/device_reports/device_FHA_01_000117_5_linkid_159046.png" width="100%"></a><br><sub>AL 000117 dir5 (link 159046)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000118_1_linkid_66619.png"><img src="evaluation/device_reports/device_FHA_01_000118_1_linkid_66619.png" width="100%"></a><br><sub>AL 000118 dir1 (link 66619)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000118_5_linkid_76481.png"><img src="evaluation/device_reports/device_FHA_01_000118_5_linkid_76481.png" width="100%"></a><br><sub>AL 000118 dir5 (link 76481)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000119_1_linkid_141936.png"><img src="evaluation/device_reports/device_FHA_01_000119_1_linkid_141936.png" width="100%"></a><br><sub>AL 000119 dir1 (link 141936)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000119_5_linkid_155974.png"><img src="evaluation/device_reports/device_FHA_01_000119_5_linkid_155974.png" width="100%"></a><br><sub>AL 000119 dir5 (link 155974)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000122_1_linkid_76679.png"><img src="evaluation/device_reports/device_FHA_01_000122_1_linkid_76679.png" width="100%"></a><br><sub>AL 000122 dir1 (link 76679)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000122_5_linkid_76614.png"><img src="evaluation/device_reports/device_FHA_01_000122_5_linkid_76614.png" width="100%"></a><br><sub>AL 000122 dir5 (link 76614)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000123_1_linkid_62751.png"><img src="evaluation/device_reports/device_FHA_01_000123_1_linkid_62751.png" width="100%"></a><br><sub>AL 000123 dir1 (link 62751)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000123_5_linkid_176307.png"><img src="evaluation/device_reports/device_FHA_01_000123_5_linkid_176307.png" width="100%"></a><br><sub>AL 000123 dir5 (link 176307)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000129_1_linkid_62312.png"><img src="evaluation/device_reports/device_FHA_01_000129_1_linkid_62312.png" width="100%"></a><br><sub>AL 000129 dir1 (link 62312)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000129_5_linkid_175052.png"><img src="evaluation/device_reports/device_FHA_01_000129_5_linkid_175052.png" width="100%"></a><br><sub>AL 000129 dir5 (link 175052)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000134_1_linkid_79982.png"><img src="evaluation/device_reports/device_FHA_01_000134_1_linkid_79982.png" width="100%"></a><br><sub>AL 000134 dir1 (link 79982)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000134_5_linkid_79983.png"><img src="evaluation/device_reports/device_FHA_01_000134_5_linkid_79983.png" width="100%"></a><br><sub>AL 000134 dir5 (link 79983)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000148_1_linkid_26653.png"><img src="evaluation/device_reports/device_FHA_01_000148_1_linkid_26653.png" width="100%"></a><br><sub>AL 000148 dir1 (link 26653)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000148_5_linkid_24792.png"><img src="evaluation/device_reports/device_FHA_01_000148_5_linkid_24792.png" width="100%"></a><br><sub>AL 000148 dir5 (link 24792)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000422_3_linkid_98424.png"><img src="evaluation/device_reports/device_FHA_01_000422_3_linkid_98424.png" width="100%"></a><br><sub>AL 000422 dir3 (link 98424)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000422_7_linkid_98425.png"><img src="evaluation/device_reports/device_FHA_01_000422_7_linkid_98425.png" width="100%"></a><br><sub>AL 000422 dir7 (link 98425)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000426_1_linkid_175311.png"><img src="evaluation/device_reports/device_FHA_01_000426_1_linkid_175311.png" width="100%"></a><br><sub>AL 000426 dir1 (link 175311)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000426_5_linkid_175310.png"><img src="evaluation/device_reports/device_FHA_01_000426_5_linkid_175310.png" width="100%"></a><br><sub>AL 000426 dir5 (link 175310)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000701_3_linkid_48269.png"><img src="evaluation/device_reports/device_FHA_01_000701_3_linkid_48269.png" width="100%"></a><br><sub>AL 000701 dir3 (link 48269)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000701_7_linkid_16819.png"><img src="evaluation/device_reports/device_FHA_01_000701_7_linkid_16819.png" width="100%"></a><br><sub>AL 000701 dir7 (link 16819)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000717_1_linkid_202744.png"><img src="evaluation/device_reports/device_FHA_01_000717_1_linkid_202744.png" width="100%"></a><br><sub>AL 000717 dir1 (link 202744)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_000717_5_linkid_62531.png"><img src="evaluation/device_reports/device_FHA_01_000717_5_linkid_62531.png" width="100%"></a><br><sub>AL 000717 dir5 (link 62531)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001382_5_linkid_97470.png"><img src="evaluation/device_reports/device_FHA_01_001382_5_linkid_97470.png" width="100%"></a><br><sub>AL 001382 dir5 (link 97470)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001383_5_linkid_30246.png"><img src="evaluation/device_reports/device_FHA_01_001383_5_linkid_30246.png" width="100%"></a><br><sub>AL 001383 dir5 (link 30246)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001384_1_linkid_79986.png"><img src="evaluation/device_reports/device_FHA_01_001384_1_linkid_79986.png" width="100%"></a><br><sub>AL 001384 dir1 (link 79986)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001401_5_linkid_78445.png"><img src="evaluation/device_reports/device_FHA_01_001401_5_linkid_78445.png" width="100%"></a><br><sub>AL 001401 dir5 (link 78445)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001461_1_linkid_193953.png"><img src="evaluation/device_reports/device_FHA_01_001461_1_linkid_193953.png" width="100%"></a><br><sub>AL 001461 dir1 (link 193953)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001461_5_linkid_154144.png"><img src="evaluation/device_reports/device_FHA_01_001461_5_linkid_154144.png" width="100%"></a><br><sub>AL 001461 dir5 (link 154144)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001462_1_linkid_139305.png"><img src="evaluation/device_reports/device_FHA_01_001462_1_linkid_139305.png" width="100%"></a><br><sub>AL 001462 dir1 (link 139305)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001463_1_linkid_185074.png"><img src="evaluation/device_reports/device_FHA_01_001463_1_linkid_185074.png" width="100%"></a><br><sub>AL 001463 dir1 (link 185074)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001464_5_linkid_139543.png"><img src="evaluation/device_reports/device_FHA_01_001464_5_linkid_139543.png" width="100%"></a><br><sub>AL 001464 dir5 (link 139543)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_001465_5_linkid_19043.png"><img src="evaluation/device_reports/device_FHA_01_001465_5_linkid_19043.png" width="100%"></a><br><sub>AL 001465 dir5 (link 19043)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_021382_1_linkid_203612.png"><img src="evaluation/device_reports/device_FHA_01_021382_1_linkid_203612.png" width="100%"></a><br><sub>AL 021382 dir1 (link 203612)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_021383_1_linkid_203621.png"><img src="evaluation/device_reports/device_FHA_01_021383_1_linkid_203621.png" width="100%"></a><br><sub>AL 021383 dir1 (link 203621)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_021384_5_linkid_203597.png"><img src="evaluation/device_reports/device_FHA_01_021384_5_linkid_203597.png" width="100%"></a><br><sub>AL 021384 dir5 (link 203597)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_021401_3_linkid_198390.png"><img src="evaluation/device_reports/device_FHA_01_021401_3_linkid_198390.png" width="100%"></a><br><sub>AL 021401 dir3 (link 198390)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_021461_1_linkid_19034.png"><img src="evaluation/device_reports/device_FHA_01_021461_1_linkid_19034.png" width="100%"></a><br><sub>AL 021461 dir1 (link 19034)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_031381_1_linkid_203620.png"><img src="evaluation/device_reports/device_FHA_01_031381_1_linkid_203620.png" width="100%"></a><br><sub>AL 031381 dir1 (link 203620)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_031382_5_linkid_97472.png"><img src="evaluation/device_reports/device_FHA_01_031382_5_linkid_97472.png" width="100%"></a><br><sub>AL 031382 dir5 (link 97472)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_031383_5_linkid_203622.png"><img src="evaluation/device_reports/device_FHA_01_031383_5_linkid_203622.png" width="100%"></a><br><sub>AL 031383 dir5 (link 203622)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_01_031384_1_linkid_203923.png"><img src="evaluation/device_reports/device_FHA_01_031384_1_linkid_203923.png" width="100%"></a><br><sub>AL 031384 dir1 (link 203923)</sub></td>
</tr>
</table>

---

## Optional API keys

`config_used.json` refers to two external services. They are **optional**. The pipeline
runs without them, with warnings and some missing data (no ACS mode-share calibration,
and no `wmata.com` transit feed). The keys in this config are **redacted**
(`YOUR_..._KEY`). Both are free:

| Field in config | Service | Register (free) |
|-----------------|---------|-----------------|
| `data.census_api_key` | U.S. Census API — ACS commute data | https://api.census.gov/data/key_signup.html |
| `gtfs.api_keys["wmata.com"]` | WMATA GTFS feed | https://developer.wmata.com/ |

**Never commit real keys.**

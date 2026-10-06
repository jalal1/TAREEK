# Los Angeles, CA experiment — 2026-10-06

A full Tareek run for the Los Angeles–Long Beach–Anaheim metro area, compared against FHA
directional traffic counts. It uses person-first demand, freight and the Hermes mobsim, in
the same way as the [New York](../newyork-20261006/) and [Chicago](../chicago-20261003/)
examples. It is the first Los Angeles example.

- **Experiment ID:** `la_s10_pt9_10iter`
- **Region:** 2 counties, the metropolitan statistical area (MSA) — Los Angeles (`06037`)
  and Orange (`06059`). Riverside, San Bernardino and Ventura (the larger combined area)
  are not in the region.
- **Scaling factor:** `0.10` (10% population sample) · **MATSim iterations:** 10 · **Mobsim:** `hermes`
- **Demand:** person-first, NHTS 2022 · **Knobs:** `work_scaling_multiplier` 1.1, `nonwork_trip_share` 2.0
- **Freight:** on, boundary trucks from HPMS, `demand_scale` 0.18
- **Runtime:** ~13.8 h total (plans 2.0 h, MATSim 11.1 h, evaluation 47 min) on a 64-CPU,
  245 GB server. The network was built before, in a plans-only run (~25 min for the
  network and the transit schedule).

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

| Change | Earlier examples | This run |
|--------|---------|----------|
| Transit mode rates | NHTS rates (Chicago: bus 0.12 / rail 0.13, blend 0.7; New York: all modes from ACS) | bus **0.06**, rail **0.03**, `blend_weight` **1.0**, set from the ACS commute share; car and walk stay on the NHTS rates |
| GTFS clean-up before pt2matsim | none | an empty `transfer_type` is set to 0, and `shapes.txt` is removed when `trips.txt` has no `shape_id` (see below) |
| Scoring | New York: `pt.constant` 1.5, `walk.constant` −1.5, `waitingPt` −1.0 | Chicago values: `pt.constant` 1.0, `walk.constant` −1.0, `waitingPt` −3.0 |
| Non-work POI radius | New York: 2 km | 4 km (`poi_assignment.initial_radius_m`, as in Chicago) |

- **Mode rates.** ACS 2023 (table B08301) gives car 90.4%, transit 4.1% and walk 2.7% of
  the commuters in the two counties (Los Angeles: car 89%, transit 5%; Orange: car 94%,
  transit 1%). With only the modes that Tareek models, the target is car 93.0% · pt 4.2%
  · walk 2.8%. A plans-only run with the pure NHTS rates gave only 0.9% pt on the work
  legs, because the availability filter removes about half of the pt legs. The odds-ratio
  correction gives bus 0.06 + rail 0.03. The generated work legs are car 90.8% · pt 4.5%
  · walk 4.7%.
- **GTFS clean-up.** pt2matsim stopped on two feeds that the GTFS rules allow. Big Blue Bus
  has an empty `transfer_type` in `transfers.txt` (pt2matsim reads it as a number).
  Metrolink has a `shapes.txt` but no `shape_id` column in `trips.txt` (pt2matsim fails
  in `loadTrips`). Without the clean-up, both operators were not in the transit schedule.

---

## How to reproduce

This run used [`config_used.json`](config_used.json). To run it again, copy the config
into the `config/` folder and start it:

```bash
# from the repository root, with the virtualenv activated
cp examples/losangeles-20261006/config_used.json config/losangeles.json
python run_experiment.py --config config/losangeles.json
```

Before you start, change these values in the config for your machine:

| Field | Value in this run | Change to |
|-------|-------------------|-----------|
| `data.data_dir` | server path | the `data/` folder of your clone |
| `matsim.heap_size_gb` | 200 (with `matsim.heap_ram_fraction` 0.85) | less than your RAM |
| `plan_generation.num_processes` | 60 | your CPU count, or less |
| `matsim.configurable_params.global.numberOfThreads` | 60 | your CPU count, or less |

`network.rebuild_network` and `counts.rebuild` are `false` because this run used the
network and counts of the plans-only run. In a new experiment folder, Tareek builds
them anyway.

> **Memory.** This run needs a large Java heap: 1.70 million agents on a network with
> 1,100,904 links used up to 193 GB of a 200 GB heap (in iteration 10). The heap is the
> smaller of `heap_size_gb` and `heap_ram_fraction` × RAM (default 0.70), so set both.
> For a smaller machine, lower `scaling_factor`.

Output goes to `experiments/<experiment-id>/`. The large files (`network.xml` ≈ 606 MB,
`plans.xml` ≈ 829 MB, the MATSim `output/` folder ≈ 38 GB) are **not** in this folder.
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
- [`experiment_20261006_052346.log`](experiment_20261006_052346.log) — the run log

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
| Mode `config_rate` | bus **0.06**, rail **0.03** (`blend_weight` 1.0); car, walk from NHTS | see above |
| Scoring | `pt.constant` 1.0, `walk.constant` −1.0, `waitingPt` −3.0 | |
| `freight.demand_scale` | **0.18** | see [Freight](#freight) |
| `matsim.scale_transit_pce` | `true` (default) | bus PCE 0.28 |
| `data.survey_months` | `regular` | Mar-May, Sep-Nov survey days |
| `counts.fha.month` | 10 | October 2024 counts |

### Scenario scale

| | |
|---|---|
| Total population (2 counties) | 13,205,523 |
| Agents simulated | 1,695,438 (422,722 work · 1,246,554 non-work · 26,162 freight) |
| Stuck agents | 169,163 (10.0%) |
| Network | 491,840 nodes · 1,100,904 links |
| Transit (GTFS) | 44 feeds (LA Metro bus and rail, Metrolink, OCTA, LADOT, Foothill, Long Beach Transit, Big Blue Bus and others); 14,814 route patterns, 32,691 departures |
| Generated mode split (legs) | car 91.5% · pt 5.8% · walk 2.7% |

---

## Headline results

Simulated against observed link volumes at **21 physical count stations**
(35 directional counts, 840 station-hours, all on freeways or state highways).
Values are MATSim's count comparison, the average of iterations 1-10.

| Metric | Value | Target | Status |
|--------|------:|--------|:------:|
| **Overall volume (sim/obs)** | **0.935** | 1.0 ± 0.10 | PASS |
| Volume level (interquartile mean) | 1.090 | 1.0 ± 0.10 | PASS |
| Per-station ratio CV | 0.491 | < 0.35 | CHECK |
| Correlation (sim vs obs) | 0.704 | > 0.85 | CHECK |
| % hourly counts with GEH < 5 | 10.8% | > 85% | CHECK |
| MAE / RMSE | 1,655 / 2,203 veh/h | | |

The MAE is larger than in the other examples because the LA count stations are large
freeways (60,000–190,000 vehicles a day per direction).

### Time of day

| Block | Hours | This run |
|-------|-------|---------:|
| Night | 0–3 | 0.40 |
| Morning | 4–9 | 0.96 |
| Midday | 10–17 | 0.91 |
| Evening | 18–23 | 1.02 |

Sim/obs per hour:

```
hour   0    1    2    3    4    5    6    7    8    9   10   11   12   13   14   15   16   17   18   19   20   21   22   23
     0.34 0.36 0.49 0.46 0.48 0.77 0.98 1.09 1.04 1.04 1.05 0.99 0.92 0.89 0.87 0.89 0.87 0.85 0.86 0.90 0.98 1.07 1.23 1.54
```

From 6 h to 21 h every hour is between 0.85 and 1.09. The afternoon (16–18 h) is the
lowest daytime period, and 22–23 h is too high (1.23 and 1.54), because the queues of the
day do not clear (see [Known limits](#known-limits)).

**Final iteration.** At iteration 10 alone (from its events) the total is 1.06: morning
1.06, midday 1.03, evening 1.23. The headline values above are lower (0.935) because the
earlier, more congested iterations are in them too.

### Demand against the survey (NHTS 2022)

| Quantity | Simulated | NHTS 2022 | Ratio |
|----------|----------:|----------:|------:|
| Trips per person per day | 2.77 | 2.82 | 0.98 |
| Median trip length (km) | 5.98 | 6.93 | 0.86 (0.69 after the 1.25 network correction) |
| Car share | 89.2% | 87.4% | +1.8 pp |
| Transit share | 5.2% | 4.4% | +0.7 pp |

The mode target for this region is the ACS commute split (see
[What is new in this run](#what-is-new-in-this-run)): the generated work legs are within
2.2 pp of it. No local household travel survey is loaded for this region.

### Freight

Measured from the events of iteration 10 on the count links
([`evaluation/freight_share_it10.txt`](evaluation/freight_share_it10.txt)):

| Block | Freight share of simulated volume | Ratio | Ratio without freight |
|-------|----------------------------------:|------:|----------------------:|
| Night | 33.2% | 0.42 | 0.28 |
| Morning | 3.9% | 1.06 | 1.02 |
| Midday | 5.3% | 1.03 | 0.98 |
| Evening | 4.8% | 1.23 | 1.17 |
| **All** | **5.2%** | **1.06** | **1.01** |

- Freight is 5.5% of the observed volume. The median count direction has 5.1% freight;
  HPMS gives 4.7% trucks on the urban interstates of the two counties.
- All freight trips cross the region boundary, so the freight is concentrated at the edge
  stations (up to 32.5% on I-10 at Pomona).

### Where the error is

| | |
|---|---|
| ![Station ratios](evaluation/station_ratio_dotplot.png) | ![Hourly error](evaluation/hourly_relative_error_box.png) |
| Sim/obs ratio per station, sorted | Signed relative error per hour, all stations |

The error is spatial. The stations near the region boundary are much too low, and the
stations in the core are too high:

| Group | Stations (daily sim/obs per direction) |
|-------|-----------------------------------------|
| Edge, too low | I-10 San Bernardino Fwy at Pomona (0.18, 0.23) · I-5 at San Clemente (0.15, 0.23) · I-210 Foothill Fwy at San Dimas (0.34, 0.46) · US-101 Ventura Fwy at Agoura Hills (0.42) · I-5 Santa Ana Fwy at Tustin (0.39, 0.69) · I-10 at Covina (0.59) |
| Core, too high | I-405 at Sepulveda (1.23, 1.36) · US-101 Hollywood Fwy (1.26) · Arroyo Seco Pkwy (1.61) · I-210 at Pasadena (1.45, 1.95) · I-405 at Long Beach (1.48, 1.58) |

More figures are in [`evaluation/`](evaluation/). The full set, with captions, is in
[`report.html`](report.html).

Data: [`evaluation/volume_comparison.csv`](evaluation/volume_comparison.csv) (per hour,
per station) · [`evaluation/trip_timing_check.json`](evaluation/trip_timing_check.json)
· [`matsim_output/10.countscompare.txt`](matsim_output/10.countscompare.txt) (MATSim's
own count comparison) · [`matsim_output/`](matsim_output/) (mode and score statistics)

---

## Known limits

- **Edge stations too low.** The work OD matrix has 1,267,008 inbound and 727,455
  outbound commutes that cross the region boundary. The `anchor` boundary policy keeps
  them, but it moves the outside end to the boundary zone that the trip crosses. A
  station near the county line is often outside that zone, so the trip does not pass it.
  Through traffic (for example Inland Empire ↔ Ventura or San Diego) and visitors from
  outside the region are not in the demand. A knob cannot correct this: a higher demand
  also raises the core stations, which are already too high.
- **Congestion.** 10.0% of agents do not finish their day by 36:00, and 14% of car legs
  and 15% of pt legs take more than 2 h. Severe congestion covers 11.6% of the used
  highway km at 8 AM, about 10% for the full day, and still 4.3% at 11 PM. Of all delay,
  21% is on motorway ramps, 18% on motorways and 18% on primary roads. Many of the worst
  links are 1-lane roads at the edges of the region (Antelope Valley, south Orange County).
- **Late evening.** 22–23 h is at 1.23 and 1.54, because the traffic that the queues hold
  during the day arrives late.
- **Walk drift.** Walk rises from 2.7% of the generated legs to 11.8% at iteration 8, then
  falls back to 6.6% at iteration 9 when innovation stops. The same snap-back occurs in
  the other examples.
- **Non-work transit.** The bus and rail `config_rate` values apply to all trip purposes,
  so the non-work legs also get about 4–6% pt. This is probably more than the real
  non-work transit use in LA.
- **Missing transit feeds.** Torrance Transit, Glendale Beeline and the West Hollywood
  shuttle are not loaded: their download servers return HTTP 403, and the Mobility
  Database has no copy. LA Metro lines also serve these areas.
- **Night.** 0–3 h is at 0.40. The plans have almost no night trips.
- **Few counts.** Only 21 physical stations are matched in a region of 13.2 million
  people (FHA October 2024; 140 station-directions in the two counties have no volume
  data). All of them are on freeways or state highways. The HPMS download for freight
  stopped at its 80,000-segment limit.

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
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_070540_3_linkid_784993.png"><img src="evaluation/device_reports/device_FHA_06_070540_3_linkid_784993.png" width="100%"></a><br><sub>CA 070540 dir3 (link 784993)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_070540_7_linkid_866457.png"><img src="evaluation/device_reports/device_FHA_06_070540_7_linkid_866457.png" width="100%"></a><br><sub>CA 070540 dir7 (link 866457)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_071280_3_linkid_839652.png"><img src="evaluation/device_reports/device_FHA_06_071280_3_linkid_839652.png" width="100%"></a><br><sub>CA 071280 dir3 (link 839652)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_071280_7_linkid_839654.png"><img src="evaluation/device_reports/device_FHA_06_071280_7_linkid_839654.png" width="100%"></a><br><sub>CA 071280 dir7 (link 839654)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_071730_3_linkid_367556.png"><img src="evaluation/device_reports/device_FHA_06_071730_3_linkid_367556.png" width="100%"></a><br><sub>CA 071730 dir3 (link 367556)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_072030_1_linkid_452332.png"><img src="evaluation/device_reports/device_FHA_06_072030_1_linkid_452332.png" width="100%"></a><br><sub>CA 072030 dir1 (link 452332)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_072110_5_linkid_1047591.png"><img src="evaluation/device_reports/device_FHA_06_072110_5_linkid_1047591.png" width="100%"></a><br><sub>CA 072110 dir5 (link 1047591)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_073600_5_linkid_89969.png"><img src="evaluation/device_reports/device_FHA_06_073600_5_linkid_89969.png" width="100%"></a><br><sub>CA 073600 dir5 (link 89969)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_074110_1_linkid_1021322.png"><img src="evaluation/device_reports/device_FHA_06_074110_1_linkid_1021322.png" width="100%"></a><br><sub>CA 074110 dir1 (link 1021322)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_074210_1_linkid_429919.png"><img src="evaluation/device_reports/device_FHA_06_074210_1_linkid_429919.png" width="100%"></a><br><sub>CA 074210 dir1 (link 429919)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_074650_1_linkid_120593.png"><img src="evaluation/device_reports/device_FHA_06_074650_1_linkid_120593.png" width="100%"></a><br><sub>CA 074650 dir1 (link 120593)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_077020_5_linkid_88205.png"><img src="evaluation/device_reports/device_FHA_06_077020_5_linkid_88205.png" width="100%"></a><br><sub>CA 077020 dir5 (link 88205)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_077210-p2_3_linkid_647729.png"><img src="evaluation/device_reports/device_FHA_06_077210-p2_3_linkid_647729.png" width="100%"></a><br><sub>CA 077210-p2 dir3 (link 647729)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_077210_3_linkid_647734.png"><img src="evaluation/device_reports/device_FHA_06_077210_3_linkid_647734.png" width="100%"></a><br><sub>CA 077210 dir3 (link 647734)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_077590_3_linkid_231024.png"><img src="evaluation/device_reports/device_FHA_06_077590_3_linkid_231024.png" width="100%"></a><br><sub>CA 077590 dir3 (link 231024)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_077590_7_linkid_301615.png"><img src="evaluation/device_reports/device_FHA_06_077590_7_linkid_301615.png" width="100%"></a><br><sub>CA 077590 dir7 (link 301615)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_079020_1_linkid_145673.png"><img src="evaluation/device_reports/device_FHA_06_079020_1_linkid_145673.png" width="100%"></a><br><sub>CA 079020 dir1 (link 145673)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_079020_5_linkid_145671.png"><img src="evaluation/device_reports/device_FHA_06_079020_5_linkid_145671.png" width="100%"></a><br><sub>CA 079020 dir5 (link 145671)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_122190_1_linkid_18558.png"><img src="evaluation/device_reports/device_FHA_06_122190_1_linkid_18558.png" width="100%"></a><br><sub>CA 122190 dir1 (link 18558)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_122190_5_linkid_548927.png"><img src="evaluation/device_reports/device_FHA_06_122190_5_linkid_548927.png" width="100%"></a><br><sub>CA 122190 dir5 (link 548927)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_122260_3_linkid_374186.png"><img src="evaluation/device_reports/device_FHA_06_122260_3_linkid_374186.png" width="100%"></a><br><sub>CA 122260 dir3 (link 374186)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_122260_7_linkid_757704.png"><img src="evaluation/device_reports/device_FHA_06_122260_7_linkid_757704.png" width="100%"></a><br><sub>CA 122260 dir7 (link 757704)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_124010_1_linkid_47252.png"><img src="evaluation/device_reports/device_FHA_06_124010_1_linkid_47252.png" width="100%"></a><br><sub>CA 124010 dir1 (link 47252)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_124010_5_linkid_343598.png"><img src="evaluation/device_reports/device_FHA_06_124010_5_linkid_343598.png" width="100%"></a><br><sub>CA 124010 dir5 (link 343598)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_126230_1_linkid_174004.png"><img src="evaluation/device_reports/device_FHA_06_126230_1_linkid_174004.png" width="100%"></a><br><sub>CA 126230 dir1 (link 174004)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_126230_5_linkid_4512.png"><img src="evaluation/device_reports/device_FHA_06_126230_5_linkid_4512.png" width="100%"></a><br><sub>CA 126230 dir5 (link 4512)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_126580_5_linkid_410511.png"><img src="evaluation/device_reports/device_FHA_06_126580_5_linkid_410511.png" width="100%"></a><br><sub>CA 126580 dir5 (link 410511)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_126590-p2_1_linkid_895369.png"><img src="evaluation/device_reports/device_FHA_06_126590-p2_1_linkid_895369.png" width="100%"></a><br><sub>CA 126590-p2 dir1 (link 895369)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_126590-p2_5_linkid_895562.png"><img src="evaluation/device_reports/device_FHA_06_126590-p2_5_linkid_895562.png" width="100%"></a><br><sub>CA 126590-p2 dir5 (link 895562)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_126590_1_linkid_375608.png"><img src="evaluation/device_reports/device_FHA_06_126590_1_linkid_375608.png" width="100%"></a><br><sub>CA 126590 dir1 (link 375608)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_126590_5_linkid_862620.png"><img src="evaluation/device_reports/device_FHA_06_126590_5_linkid_862620.png" width="100%"></a><br><sub>CA 126590 dir5 (link 862620)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_129010_1_linkid_382420.png"><img src="evaluation/device_reports/device_FHA_06_129010_1_linkid_382420.png" width="100%"></a><br><sub>CA 129010 dir1 (link 382420)</sub></td>
</tr>
<tr>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_129010_5_linkid_318055.png"><img src="evaluation/device_reports/device_FHA_06_129010_5_linkid_318055.png" width="100%"></a><br><sub>CA 129010 dir5 (link 318055)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_129050_1_linkid_273145.png"><img src="evaluation/device_reports/device_FHA_06_129050_1_linkid_273145.png" width="100%"></a><br><sub>CA 129050 dir1 (link 273145)</sub></td>
<td width="25%"><a href="evaluation/device_reports/device_FHA_06_129050_5_linkid_661734.png"><img src="evaluation/device_reports/device_FHA_06_129050_5_linkid_661734.png" width="100%"></a><br><sub>CA 129050 dir5 (link 661734)</sub></td>
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

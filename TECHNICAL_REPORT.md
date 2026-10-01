# TAREEK Technical Report

This document describes the architecture, design decisions, and internals of TAREEK for contributors who want to understand, extend, or fork the system. For instructions on running the system, see the [README](README.md).

For the full academic treatment including formal equations, experimental results, and comparisons with related systems, see:

> TBA.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Configuration Schema](#2-configuration-schema)
3. [Data Ingestion and Storage](#3-data-ingestion-and-storage)
4. [Network Generation](#4-network-generation)
5. [Synthetic Demand Generation](#5-synthetic-demand-generation)
6. [Multimodal Transit Integration](#6-multimodal-transit-integration)
7. [Mode Choice](#7-mode-choice)
8. [MATSim Simulation](#8-matsim-simulation)
9. [Traffic Counts and Validation](#9-traffic-counts-and-validation)
10. [Boundary Freight](#10-boundary-freight)
11. [Survey Data and Multi-Survey Blending](#11-survey-data-and-multi-survey-blending)
12. [Scalability](#12-scalability)
13. [Extending the System](#13-extending-the-system)

---

## 1. System Overview

TAREEK is an open-source, configuration-driven system that automates the full pipeline from region specification to validated agent-based traffic simulation. Given a set of FIPS county codes in a JSON configuration file, the system:

1. **Ingests data** from Census LODES (employment), decennial Census (population), GTFS feeds (transit), OpenStreetMap (roads and POIs), FHWA/TMAS (traffic counts), and household travel surveys (NHTS and/or regional surveys) into a DuckDB database.
2. **Generates a road network** by converting OSM data to a MATSim network via pt2matsim, optionally creating a multimodal network with transit schedules.
3. **Synthesizes travel demand** by creating a synthetic population, sampling activity chains from survey data, assigning origin-destination pairs via gravity models, selecting transportation modes, and assigning departure times using kernel density estimation.
4. **Runs the MATSim simulation** using the Hermes or QSim engine with iterative co-evolutionary optimization.
5. **Validates results** by matching FHWA/TMAS monitoring stations to network links and comparing simulated volumes against ground-truth counts using GEH statistics, RMSE, and Pearson correlation.

All stages are driven by a single `config.json` file. No code changes are needed to simulate a different US metropolitan area.

### Workflow Orchestration

The experiment runner (`run_experiment.py`) executes the following workflow:

```
1. Validate configuration and generate network (with optional GTFS transit)
2. Generate work plans (gravity model + IPF)
3. For each enabled non-work purpose: generate non-work plans
4. Combine all plans into a single plan file
5. Generate traffic count files for calibration
6. Run MATSim simulation
7. Evaluate simulation output against ground-truth counts
8. Save experiment summary and metrics
```

Shared resources (home locations, POIs, survey data, KDE time models, spatial indices, GTFS stop coordinates) are loaded once and distributed to all plan generators to avoid redundant database queries. Work and non-work plans are generated in parallel across purposes and combined into a single MATSim plan file.

---

## 2. Configuration Schema

The configuration JSON is a declarative specification of the entire experiment. Key sections include:

- **Region specification**: A list of 5-digit FIPS GEOIDs (2-digit state + 3-digit county). County boundaries are looked up automatically via OSMnx. Any US county can be simulated by specifying its FIPS code.
- **Survey sources**: Multiple surveys with configurable weights. When a regional survey is unavailable (weight=0), the system falls back to the national NHTS, ensuring function for any US metro. At least one active survey must have a person file (`person_file`, and `day_file` for TBI), because the demand budget needs survey person-days (Section 5.2). `data.survey_months` (default `"regular"`) and `data.day_type` (default `"weekday"`) select the survey days.
- **Demand knobs**: `plan_generation.work_scaling_multiplier` and `nonwork_purposes.nonwork_trip_share` scale the survey values (neutral = 1.0). See Section 5.2.
- **Mode definitions**: A flat structure where each mode (car, bus, rail, walk, bike) has its own availability constraint:
  - *Universal*: car is always available.
  - *Distance-based*: walk and bike are available when origin-destination distance falls within configurable thresholds.
  - *GTFS-based*: bus and rail require transit stops within a configurable access buffer of both origin and destination.
- **Scaling factor**: Controls the fraction of the population to simulate (e.g., `scaling_factor=0.1` for a 10% sample). MATSim flow and storage capacity factors are adjusted proportionally.
- **Counts configuration**: FHA/TMAS counts and/or custom CSV counts with blending weights.
- **Evaluation settings**: Ground-truth data directory and evaluation toggle.

Example configs for various US cities are in `config/USA/`.

---

## 3. Data Ingestion and Storage

### DuckDB as Central Data Store

The system uses DuckDB, an embedded OLAP database, as the central data store. DuckDB operates as a single file within the `data/db/` directory, requiring no external setup and enabling full portability. Its columnar storage engine is well-suited to the county-filtered aggregations and crosstab queries over survey data.

The database schema includes:
- **Census data**: Block-level population (decennial Census) and employment (LODES RAC).
- **OpenStreetMap POIs**: Points of interest categorized by activity type (shopping, dining, social, etc.).
- **GTFS transit data**: Feeds, routes, trips, stops, and stop times across five normalized tables.
- **Survey trip records**: From multiple sources with origin/destination purposes and modes.
- **FHWA/TMAS traffic counts**: Station locations with hourly volumes.

B-tree indices on county and state FIPS columns enable fast SQL-level filtering, ensuring that only data for the configured region is loaded into memory.

### Data Sources

| Source | What It Provides | Filtering |
|--------|-----------------|-----------|
| Census LODES | Block-level employee counts | By configured counties |
| Decennial Census P1 | Block-level total population | By configured counties |
| OpenStreetMap (Overpass API) | Roads, POIs by activity type | By county bounding box |
| GTFS feeds (Mobility Database) | Transit schedules, stops, routes | By study region polygon |
| NHTS / Regional surveys | Trip chains, modes, departure times | County-level or national |
| FHWA/TMAS | Traffic monitoring station volumes | By configured counties |

---

## 4. Network Generation

### OSM to MATSim Conversion

The network generator converts OpenStreetMap data to a MATSim-compatible network. The system wraps pt2matsim, a Java library, handling all preprocessing, configuration generation, multi-feed merging, and post-processing.

**Preprocessing**: Each GTFS feed is spatially filtered to retain only stops within the study region bounding box and filtered by route type. The OSM input is converted from PBF to XML if needed (pt2matsim requires XML). For each pt2matsim step, the system programmatically generates an XML configuration file specifying highway and railway defaults (free speed, lanes, capacity per road class), the auto-detected UTM coordinate system, and routing parameters.

**Core conversion (pt2matsim)**: Three converters are invoked sequentially:
1. `Osm2MultimodalNetwork` — converts the OSM file into a MATSim network with road and rail links.
2. `Gtfs2TransitSchedule` — converts each GTFS feed into an unmapped transit schedule and vehicle file.
3. `PublicTransitMapper` — maps the transit schedule onto the road network by snapping stops to links and routing between consecutive stops via A* search.

**Multi-feed merging**: When multiple GTFS feeds are discovered, the system merges per-feed schedule and vehicle outputs into consolidated files. Stop facility and transit line identifiers are prefixed with the feed ID to prevent collisions.

**Post-processing and validation**: The system applies multi-pass validation to fix common pt2matsim output issues:
- Dead-end transit stops receive reverse links to ensure vehicles can depart.
- Routes with disconnected link sequences or stops mapped to links outside the route path are removed.
- Terminal stops unreachable from the road network (detected via directed graph reachability analysis) are flagged and their routes removed.
- Orphaned stop facilities no longer referenced by any surviving route are pruned.

The pipeline produces three output files: `network.xml`, `transitSchedule.xml`, and `transitVehicles.xml`.

### Coordinate System

The coordinate system is auto-detected from the configured counties' centroids by determining the appropriate NAD83 UTM zone, with an optional user override in the configuration.

---

## 5. Synthetic Demand Generation

Demand generation is the core of the system. It produces synthetic daily activity plans for every agent in the population. The pipeline has five stages: population synthesis, the demand budget (who travels on the modelled day, and why), activity chain sampling, spatial assignment (OD matrix), and temporal assignment.

### 5.1 Population Synthesis from Census Data

The synthetic population is derived from two Census products:
- **LODES RAC** provides block-level employee counts.
- **Decennial Census P1** provides block-level total population.

Non-employees (retirees, students, unemployed) are computed as `max(0, P_b - n_emp_b)`, where `P_b` is the total population and `n_emp_b` is the employee count for block `b`. Each block is geocoded to its TIGER/Line centroid.

**Agent allocation**: Given a configurable scaling factor `s`, the target number of agents is `N = s * sum(P_b)`. Agents are allocated to blocks using Hamilton's largest-remainder method, guaranteeing exactly N agents with no accumulated rounding drift. Within each block, agents are spatially jittered by a Gaussian offset (~50 m) to avoid unrealistic clustering.

**Block group aggregation**: A full block-level OD matrix would be prohibitively expensive at metropolitan scale (e.g., 50K x 50K for Twin Cities). The system aggregates to 12-digit block group GEOIDs, reducing each matrix to approximately 4K x 3K entries. Fine-grained spatial resolution is recovered when agents are assigned to individual blocks within those groups.

### 5.2 Demand Budget: Who Travels on the Modelled Day

Census and LODES give the persons and workers of each block, but not how often they travel. A LODES job is a job held, not a trip made: if every job made one commute per day, a region would get far too many work trips (in the Twin Cities, 61% of all plans were work plans against 33.5% of survey person-days). The demand budget (`models/demand_budget.py`) is the single place that decides how many persons of each group travel, and for which main purpose. The work generator, the non-work generators and the demand estimator all read it, so the demand that is reported is the demand that is generated.

Each source has one job:

| Source | Gives |
|---|---|
| Census + LODES RAC | Persons and workers per block |
| LODES OD | Where the workers of a block work |
| ACS B01001 (county) | Age split of non-workers into children 0-4, students 5-17 and adults (a national split is used when the API is not available; the result is cached in `data/acs_cache/`) |
| Survey person-days | For each person group: the share of days with a commute, with other travel only, and with no travel; and the main purpose of the other-travel days |

**Person-days**: A trip table cannot show a person who stayed at home, because that person has no trips. So each survey class returns a person-day table from `load_person_days()`, one row per surveyed day including days with no trips (columns: person id, date, weight, segment, month, weekday, number of trips). NHTS reads its person file (`person_file`: `perv2pub.csv`, one day per person). TBI reads its Day and Person files (`day_file` and `person_file`, several days per person, so each row keeps its calendar date). A survey without a person file returns `None`; it still feeds chains and time models, but it cannot set day types.

**Day types**: For each segment (worker, student, non-working adult), a day is a *commute* day if it has a trip to Work, an *other-travel* day if it has trips but none to Work, and a *no-travel* day otherwise. The *main purpose* of an other-travel day is the non-Home, non-Work stop with the longest dwell. Probabilities are weighted with the person-day weights and blended across the surveys that do the `person_days` job, with their `data.surveys[].weight` or `roles.person_days` (Section 11). Children 0-4 get no plan of their own; adult escort trips cover them.

**Survey months**: `data.survey_months` selects the survey days that describe a regular weekday: `"regular"` (March-May and September-November, the default), `"all"`, or a list of months. The same person-days also select the trips, so day types, chains and time models describe the same days. A source keeps the month window only if every segment still has at least 200 person-days in it; otherwise that source uses all months. The counts month (`counts.fha.month`) should be inside the window; the validator warns when it is not.

**Work plans**: `LODES OD × P(commute) of workers × work_scaling_multiplier`. P(commute) comes from the survey (0.525 on NHTS 2022 weekdays in regular months).

**Non-work plans**: For each block and purpose P, the expected travellers are `sum over segments of persons × P(other travel) × share of P among other-travel days`, written to the block as `nw_origin_<P>`. One generator per main purpose uses these origins. Its chain pool holds only the survey days with that main purpose, re-weighted so that the segment mix of the pool matches the region.

**Knobs**: The survey values are the default. Two knobs act on top of them, and 1.0 (or 0 for a blend weight) keeps the survey value:
- `plan_generation.work_scaling_multiplier` scales P(commute).
- `nonwork_purposes.nonwork_trip_share` scales every non-work purpose; `nonwork_purposes.<P>.trip_generation.config_rate` with `blend_weight` blends the rate of one purpose toward a configured rate.

The validator reports each non-neutral knob, because it makes more (or less) demand than the survey describes. A knob can close a count gap for the wrong reason; for example, a count shortfall at midday is often a time-of-day problem, and a level knob then also raises the morning peak.

**Outputs**: `experiments/<id>/demand_budget.json` holds the segment populations, day-type probabilities per segment and per source, P(commute), the purpose mix, the travellers per purpose and the knob factors. The experiment report shows it in the *Demand budget* section, before the count validation.

### 5.3 Activity Chain Generation

Each agent requires a daily activity chain — an ordered sequence of activities such as Home -> Work -> Shopping -> Home. The system models chains as a second-order Markov process over seven activity types: Home, Work, Shopping, School, Dining, Social, and Other.

**Transition estimation**: From survey trip records, the system extracts per-respondent daily trip chains and estimates second-order transition probabilities `P(a_t | a_{t-2}, a_{t-1})`. When a particular second-order context is unobserved, the system falls back to first-order transitions.

**Work and non-work chain separation**: Survey chains are partitioned into work chains (containing at least one Work activity) and non-work chains (no Work activity). Work plans draw from the work pool. Non-work plans draw from one pool per main purpose (Section 5.2): the Shopping generator samples only survey days whose main purpose is Shopping, re-weighted to the segment mix of the region.

**Home-Work-Home dominance handling**: The Markov transition model is trained on filtered work chains to learn realistic activity transitions conditional on Work being present, while the chain-length distribution is estimated from the full unfiltered survey corpus. This ensures realistic chain lengths even though transition structure is constrained to work-relevant sequences.

**Sampling with early stopping**: The model samples a start activity, draws a target chain length, and iteratively applies second-order transition probabilities. A probabilistic early-stopping mechanism ramps the stopping probability as the chain approaches the target length. An alternative direct pattern replay strategy that uniformly samples complete observed chains from the survey corpus is also available.

**Multi-source blending**: At sampling time, a source is selected proportionally to its weight, and a chain is drawn from that source's model.

### 5.4 Spatial Assignment: OD Matrix Generation

**Work trips** use a doubly-constrained gravity model that distributes workers from residential block groups to employment block groups. The trip probability between origin `i` and destination `j` is:

```
T_ij = A_i * O_i * B_j * D_j * f(c_ij)
```

where `A_i` and `B_j` are balancing factors computed via Iterative Proportional Fitting (IPF), `O_i` is the number of workers in block group `i`, `D_j` is the number of jobs in block group `j`, and `f(c_ij) = c_ij^(-beta)` is a distance-decay function. The default `beta = 1.5` reflects typical metropolitan commuting patterns.

**Non-work trips** use a singly-constrained gravity model where only origin totals are enforced. Destination attractiveness is defined by the count of relevant POIs in each block group.

**Survey-gravity blending**: When survey-based OD data is available, the system blends it with the gravity matrix using a configurable parameter `alpha`:

```
T_combined = alpha * T_survey + (1 - alpha) * T_gravity   (where survey data exists)
T_combined = T_gravity                                     (otherwise)
```

**POI discovery**: Points of interest are fetched from OpenStreetMap via the Overpass API using a three-strategy fallback: (1) FIPS code boundary relation, (2) Wikipedia/Wikidata tag query, (3) bounding box query with post-hoc spatial filtering. POIs are categorized into activity types using a curated mapping of OSM tags.

### 5.5 Temporal Assignment: KDE-Based Time Modeling

Departure times and activity durations are modeled using Gaussian kernel density estimation (KDE) fitted to survey trip records.

**Departure times**: For each (origin purpose, destination purpose) pair observed in the survey, a separate KDE is fitted over departure times expressed as minutes since midnight. When a pair has too few observations, the system falls back to a global time model that pools departure times across all purpose pairs.

**Activity durations**: Durations are extracted from consecutive survey trips and partitioned into four arrival-time bins (morning 0-10h, midday 10-14h, afternoon 14-18h, evening 18-24h). A separate KDE is fitted per (activity type, time bin) pair.

**Duration blending**: Sampled durations can be blended with a configurable target distribution (e.g., Gaussian with configurable mean and standard deviation for Work activities).

**Survey days used**: The time models use only the survey days selected for the demand budget: the configured day type (`data.day_type`, weekday by default) and the survey months (Section 5.2). All KDEs use the survey expansion weights.

**Kernel width**: Departure-time KDEs use a fixed kernel of `time_models.departure_bandwidth_minutes` (10 min by default; `"scott"` gives Scott's rule). Scott's rule assumes one Gaussian peak. Departure times have several narrow peaks (early shift, 7-8 h, school start), and on Twin Cities NHTS first departures Scott's rule gave 34-88 min kernels that moved a quarter of the 7 h peak into 5-6 h. A small fixed kernel keeps the peaks, and it also spreads the survey's rounding to the full hour over both sides of the hour.

### 5.6 Feasibility Enforcement and Retry Mechanism

The complete daily plan must satisfy three constraints:
1. The sum of all activity durations and inter-activity travel times must not exceed 1440 minutes.
2. The agent must return home before midnight.
3. No two activities may overlap in time.

Plan generation involves multiple stages that may fail. Each stage has its own configurable retry limit (`max_chain_retries`, `max_time_retries`, `max_poi_retries`). A plan is discarded only when all retries at any stage are exhausted, resulting in a failure rate of approximately 1% across experiments.

---

## 6. Multimodal Transit Integration

### GTFS Feed Discovery and Loading

Setting `transit_network: true` in the configuration triggers automatic transit integration.

**Discovery**: The system downloads the Mobility Database catalog (~2000 feeds worldwide), filters to active US feeds, and tests each feed's bounding box for intersection with the study region polygon. Partially overlapping feeds are conservatively included.

**Loading and spatial indexing**: Discovered feeds are downloaded, cached locally (re-downloaded after a configurable age, default 30 days), and ingested into DuckDB. A spatial filter retains only stops within the study region plus a 5 km buffer. The system builds separate STR-packed R-tree spatial indices per transit mode, grouping stops by GTFS route type.

### Network Conversion Pipeline

The transit network conversion wraps pt2matsim's three core converters (see Section 4). The system handles all preprocessing, configuration generation, multi-feed merging, and post-processing automatically.

During plan generation, the spatial indices support mode availability buffer queries: bus and rail require transit stops within a configurable access buffer (default 800 m for bus, 1200 m for rail) of both the origin and the destination. This check uses STR-packed R-tree spatial indices built over GTFS stop coordinates.

---

## 7. Mode Choice

Modes are assigned using a survey-based sampling approach that respects geographic availability constraints.

**Base rates**: Mode shares are computed from survey data for each trip purpose pair (e.g., Home->Work: 85% car, 10% transit, 3% bike, 2% walk). When multiple survey sources are loaded, shares are blended proportionally to their configured weights.

**Availability filtering**: Before sampling, modes are filtered by three availability checkers:
- *Universal*: car is always available.
- *Distance-based*: walk and bike are available only when the haversine distance between origin and destination falls within configurable thresholds (default 2 km for walk, 8 km for bike).
- *GTFS-based*: bus and rail require transit stops within a configurable access buffer of both origin and destination.

**Chain consistency**: By default, a single mode is sampled for the entire activity chain by computing the intersection of available mode sets across all legs. If no single mode is available for all legs, the system falls back to per-leg independent sampling.

**MATSim-side mode choice**: MATSim can also refine mode choices during simulation via its SubtourModeChoice replanning strategy, which probabilistically switches the mode of entire subtours while respecting chain-based constraints.

---

## 8. MATSim Simulation

The MATSim orchestrator executes the agent-based simulation using either the QSim or Hermes engine, running iterative co-evolutionary optimization of agent plans. The system programmatically generates the MATSim configuration XML with all necessary parameters (network paths, plan files, iteration count, scoring parameters, replanning strategies, etc.).

The output includes event files, link volume data, and agent plan evolution across iterations. These outputs feed into the evaluation pipeline.

**QSim or Hermes**: `matsim.configurable_params."controller.mobsim"` selects the engine. Hermes is a simplified queue model; on the three example regions it made MATSim about 2 times faster per agent than QSim. Notes for Hermes:
- It reads its own `hermes` module, so the configuration manager copies `qsim.flowCapacityFactor` and `qsim.storageCapacityFactor` into it.
- `hermes.endTime` can be set as a configurable parameter (the examples use `36:00:00`, like QSim). Without it Hermes stops at 30:00:00; it cannot hang, because it uses a fixed number of time steps. QSim must always have `endTime`: without it, one agent that never finishes keeps QSim running indefinitely.
- The `hermes` module rejects unknown parameters as a fatal error. QSim-only parameters such as `vehiclesSource` are therefore written to `qsim` only; Hermes still applies PCE through the scenario vehicle types.
- `hermes.stuckTime` is an integer (default 10 s).
- MATSim warns that Hermes should run with `eventsManager.oneThreadPerHandler`; the base template does not set this yet.

---

## 9. Traffic Counts and Validation

### Traffic Count Sources

The system supports two sources of traffic count data:

**FHA/TMAS counts**: The included FHA station and volume zip files (`data/FHA_counts/`) provide national coverage. The system automatically filters to stations within the configured counties and extracts hourly volumes for the configured year and month.

**Custom CSV counts**: Users can provide their own station locations (`counts_stations.csv`) and hourly volumes (`counts_volumes.csv`) in `data/evaluation/`. Multiple days per station are averaged (weekdays only).

Both sources can be blended with configurable weights.

### Evaluation Pipeline

The multi-metric evaluator:
1. Matches FHWA/TMAS monitoring stations to MATSim network links.
2. Compares simulated hourly link volumes against ground-truth counts.
3. Computes GEH statistics, RMSE, MAE, percentage of hours with GEH < 5, and Pearson correlation.
4. Generates per-station validation reports including spatial match maps, 24-hour volume comparison plots, and hourly GEH bar charts.
5. Records all metrics to a comparison CSV for systematic cross-run analysis.

The experiment report (`scripts/experiment_report.py`) puts the demand checks before the counts: first the demand against the household survey, then the demand budget (Section 5.2), then the count validation by time block. The count comparison that MATSim writes is the average of the iterations given by `averageCountsOverIterations` (all iterations of a 10-iteration run). The final iteration alone can differ, because at the innovation cutoff the walk and pt plans made during innovation are dropped and more trips go by car.

### Vehicle-Class Metrics

The metrics above are computed on **total link volume**, because no MATSim output reports link volume broken down by vehicle type or subpopulation — `countscompare.txt` and `linkstats.txt.gz` carry totals only, and while `output_trips.csv` does identify persons, it records no link path. When a run includes freight (Section 10), the vehicle streams are separated from the events file and an additional set of metrics is reported — the set that travel-model validation practice expects from a model carrying more than one vehicle class:

| metric | why practice reports it |
|---|---|
| **VMT / VKT by vehicle class** | The headline output of regional models and the basis of emissions inventories. FHWA's VMT forecasting method and SCAG's heavy-duty truck model both validate class VMT against HPMS. |
| **Truck percentage by functional class** | The number HPMS publishes and DOTs quote. Here it also closes a loop: demand is *derived* from a truck share, so the realised share checks derivation against assignment. |
| **%RMSE by volume group** | The FHWA *Validation and Reasonableness Checking Manual* stratifies error by volume group because a pooled figure hides systematically worse error on low-volume links. Reported against the manual's maximum-desirable targets. |
| **Screenline / cordon totals** | Practice puts screenline agreement within 5–10%. For a boundary freight model the cordons *are* the screenline, making this the most direct test that the right number of trucks entered the network. |
| **Trip length distribution by class** | A model can match volumes at every cordon and still distribute trips wrongly inside the region. Only trip length exposes that, and it is the check on the friction parameter. |
| **Hourly counts and share** | Counts *and* share are reported together deliberately: truck share peaks at night because car volume collapses, not because truck volume rises. Validating on share alone is a known error. |

These live in `models/freight/reporting.py` and are written to `freight_summary.json`.

### Interpretation

The evaluation is designed to demonstrate the pipeline's ability to produce a calibratable baseline from open data alone, not to claim calibrated accuracy. Demand calibration is inherently iterative and context-dependent. The per-station reports equip practitioners with the diagnostics needed to refine the baseline through parameter adjustments (e.g., increasing the scaling factor or blending local survey data) without modifying code.

Freight is a single-digit to low-double-digit percentage of traffic. It will not repair a large aggregate count error, and the module is not judged on whether total GEH improves — if the aggregate ratio was already near 1.0, adding freight pushes it past, which is information about car demand rather than a freight failure. Freight's contribution is therefore always reported separately from the total.

---

## 10. Boundary Freight

An optional module adds truck trips that cross the region boundary, so freeway and highway volumes are not short of the traffic real corridors carry. It is off by default (`freight.enabled`).

### Scope

Only trips with at least one end outside the region: **E→I** (enters and stops), **I→E** (starts and leaves), **E→E** (passes through). Internal freight is out of scope. This is the standard external-model form — FHWA's *Quick Response Freight Methods* documents the Memphis MPO truck model as exactly this split, with the internal truck model kept separate.

This is not a freight research model: no commodities, shipments, tours, or logistics. It produces trips, and MATSim does the rest.

### Where trucks cross — cordon detection

Standard practice places external stations by hand from a map. The module derives them from the network so it works for any region with no manual setup. Two intuitive methods were measured and both fail: severed boundary stubs do not exist in the cleaned network (0 dead-end nodes), and a band around the network's bounding rectangle puts every cordon on one side, because a min/max extent is defined by outlier nodes.

What works is the conjunction of a topological and a geometric test: a corridor link whose upstream node has no other incoming corridor link is a gateway (**terminus**), *and* it must lie near the network's outer envelope in its own direction (**peripherality**), because 60% of raw termini are interior breaks where a capacity filter interrupts a chain mid-region. Cordons are directional — opposite carriageways never merge, or trucks would be injected the wrong way up a divided highway.

### How many — derived per region

Truck share is resolved through four layers, degrading gracefully and never able to fail a run: a pinned config value, an on-disk cache, a live HPMS query, and a vendored national table (FHWA/LTPP) that needs no network at all. Which layer supplied the value is recorded, so a national-average result is never mistaken for a measured one.

This matters because truck share varies by roughly **three times between regions** — measured live: Alabama urban interstate 16.3%, Minnesota 6.2%. A single global default would be wrong nearly everywhere.

Two arithmetic corrections are applied and recorded: crossings are converted to trips by `1 / (1 + through_share)` (0.77 at the default, **not** a flat 0.5, which would be correct only if every trip were a through trip), and freight is scaled by `scaling_factor` like all other demand, since MATSim's `countsScaleFactor` multiplies every simulated vehicle when comparing against counts.

### When — two profiles by trip class

The FHWA/LTPP study identifies two distinct truck patterns, and the distinction maps exactly onto the trip classes. E→I and I→E have a real stop in the region and follow the **business-day** pattern (a broad 09:00–15:00 plateau). E→E is long-haul by definition and follows the **through** pattern, which is nearly flat across the day because long-distance drivers are paid by the mile and travel at night to avoid congestion.

### Integration

Freight becomes a third plan stream beside work and non-work. A freight plan is two activities and one leg, carrying a `subpopulation` person attribute so MATSim applies freight-specific replanning: `ReRoute` plus a selector only. Mode choice and time mutation are deliberately excluded — re-routing around congestion is the reason to simulate trucks, but a truck must not become a pedestrian or drift off its sampled departure time.

Trucks route as `car` and take their physical effect from a vehicle type's passenger-car equivalent (default 2.05 at a 45:55 single-unit/combination mix). PCE is a separate, single-variable change, because it alters congestion and therefore routes and counts on links that carry no trucks at all.

### Validation

Three tiers, described in Section 9: internal consistency (every region, no external data), the HPMS corridor check (any region with Federal-Aid highways), and classification counts where sensors report FHWA vehicle classes.

### Freight Estimation

Tier 2 measures freight parameters from a finished experiment, which is what an estimator does, so it lives in `estimators/freight_estimator.py` alongside the demand and mode-share estimators and follows the same contract: cold start writes `<config_dir>/<stem>_estimated.json`, feedback takes a region folder plus `--experiment-dir` and writes `<region>/config_estimated.json`, and neither ever edits `config.json`.

It is deliberately **not** part of `run_experiment.py`. Isolating the truck stream requires re-reading the MATSim events file (~20 minutes at 15-county scale), which would be a large recurring cost on every simulation run for an answer that is only occasionally needed. Instead the first estimator run extracts a compact artefact, `freight_link_volumes.json`, and later runs read that in milliseconds.

Three parameters have a measured path. `truck_share` and `vehicle_mix` are resolved cold-start from HPMS — the single-unit/combination split measures roughly 28:72 on Alabama urban interstate against a 45:55 default, and the two must be written together because a pinned share is split back out using the mix. `demand_scale` is derived in feedback mode from the tier-2 per-segment ratio. Everything else is left alone for a recorded reason: the distance-decay `beta` is inert at this scale, PCE is never auto-enabled because it gridlocked the fast tier, and the through share cannot be measured from our own output without circularity.

---

## 11. Survey Data and Multi-Survey Blending

### Supported Surveys

**NHTS (National Household Travel Survey)**: The pipeline reads the NHTS 2022 trip file (`data/nhts/csv/tripv2pub.csv`) and person file (`data/nhts/csv/perv2pub.csv`). It is a national survey that works as a default for any US region. The optional survey key `msa_sizes` (for example `[4, 5]`) keeps only persons from metros of that size.

**TBI (Twin Cities Travel Behavior Inventory 2023)**: The loader reads the trip file for chains and times, and the Day and Person files for person-days. TBI is set to weight 0 in the current configs. Before it can replace NHTS in the demand budget, the trip cleaning needs work: it drops work trips whose origin purpose is missing or "Change mode", so commute days become other-travel days (worker P(commute) 0.37 against 0.42 in the raw data); the broad "Work" purpose includes business trips; and trips between 0:00 and 3:00 get the next calendar date and do not match their Day row.

**Birmingham local survey (`bham_local`)**: A small published survey of 451 Birmingham residents (`data/surveys/birmingham_al_local/`, MIT License), one row per person with up to 13 trips. It has no weights, no dates, no no-travel days and no persons under 18, so it cannot do the `person_days` job; NHTS does that job for it (see Survey Roles below).

Custom (local) surveys are kept in `data/surveys/<region>_<survey>[_<year>]/`, each with a README. NHTS stays in `data/nhts/`.

**Regional surveys**: Region-specific surveys produce better results. The system provides an extensible survey framework (see Section 13.1).

Trips are stored in the DuckDB table `survey_trips`. The ETL runs only when a `(source_type, source_year)` pair is missing from the table, so a change to a trip loader has no effect until the rows of that source are deleted. Person-days are read from the survey files at run time and need no ETL.

### Multi-Survey Blending

The system supports blending multiple survey sources with configurable weights. Weights are normalized automatically. A blended trip chain model wraps per-source Markov models. At sampling time, a source is selected proportionally to its weight, and a chain is drawn from that source's model. Setting a regional weight to zero causes automatic fallback to NHTS-only chains. The demand budget blends the day-type probabilities and purpose mixes of the sources with the same weights.

### Survey Roles

A survey does up to five jobs: `person_days` (day-type probabilities and segments in the demand budget), `chains` (activity sequences), `times` (departure, trip and activity duration models), `modes` (mode shares per purpose) and `od` (survey OD matrix and survey trip rates). The entry's `weight` applies to all five. An optional `roles` object overrides it per job, for example `{"type": "nhts", "weight": 0, "roles": {"person_days": 1}}` uses NHTS for person-days only. For each job the weights are normalised over the surveys that can do it; a survey without a person-day table cannot do `person_days`, and one without locations cannot do `od`. `chains`, `times`, `modes` and `person_days` each need at least one survey, and the run stops with a clear message otherwise. A survey with only `person_days` is not a trip source: its trips are read only by the demand budget. The rules are in `data_sources/survey_manager.py` (`ROLES`).

### Demand Estimation

An optional pre-run estimation tool (`estimators/demand_estimator.py`) calibrates trip generation and transit mode parameters before plan generation begins. It computes benchmarks from the database and the survey person-days (trips per capita, average legs per chain, and the travel-day share, which now comes directly from the person-days instead of a config proxy), and it computes the demand budget of Section 5.2. It then proposes non-work trip shares, per-purpose generation rates, blend weights, and the scaling factor. It also fetches Census ACS B08301 commute-mode data at the county level to compute region-specific `config_rate`, `blend_weight`, and `access_buffer_meters` for bus and rail modes. A Census API key is required.

---

## 12. Scalability

The system scales along two dimensions:

**Geographic scalability**: All data loading operations filter by the configured county codes. GTFS feeds are auto-discovered from the Mobility Database catalog by intersecting feed bounding boxes with the study region. Cached network files are reused across experiments sharing the same region.

**Computational scalability**: Plan generation is parallelized across a configurable number of worker processes. Shared data is serialized as plain dictionaries and coordinate lists so that each worker reconstructs its own spatial indices, trading a small initialization cost for clean process isolation.

A population scaling factor (e.g., `scaling_factor=0.1` for a 10% sample) provides an additional lever, with MATSim's flow and storage capacity factors adjusted proportionally to enable rapid iteration during development.

---

## 13. Extending the System

### 13.1 Adding a New Survey Source

Create a new file in `data_sources/` that subclasses `BaseSurveyTrip` (see `data_sources/tbi_survey.py` as an example):

```python
from data_sources.base_survey_trip import BaseSurveyTrip

class MySurveyTrip(BaseSurveyTrip):
    def extract_data(self, year: str):
        # Read your CSV/file into self.data (a pandas DataFrame)
        ...

    def clean_data(self, **kwargs):
        # Map your raw columns to the canonical schema:
        #   person_id, mode_type, origin_purpose, destination_purpose,
        #   depart_time, arrive_time
        #
        # Map activities to: Home, Work, School, Shopping, Social, Dining, Escort, Other
        # Map modes to: Car, Bus, Rail, Walk, Bike, SchoolBus, Rideshare, Other
        #
        # Add metadata columns:
        #   self.data['source_type'] = 'my_survey'
        #   self.data['source_year'] = year
        #
        # Then validate:
        self.validate_schema()
```

Register it in `data_sources/survey_manager.py`:

```python
# In SurveyManager._ensure_registry():
from data_sources.my_survey import MySurveyTrip
cls.SURVEY_REGISTRY['my_survey'] = MySurveyTrip
```

Use it in your config:

```json
{ "type": "my_survey", "year": "2024", "file": "path/to/data.csv", "weight": 1,
  "person_file": "path/to/persons.csv" }
```

To let the survey set day types in the demand budget (Section 5.2), also override `load_person_days()`. It returns one row per surveyed person-day, including days with no trips, with the columns of `BaseSurveyTrip.PERSON_DAY_COLUMNS` (`person_id`, `date`, `weight`, `segment`, `month`, `weekday`, `n_trips`). Use `self._survey_entry()` and `self._resolve_data_path()` to read the file names from the survey config entry. `person_id` must match the trip table. For a survey with several days per person, set `date` (`YYYY-MM-DD`) so that each day matches its trips; for one day per person, leave it `None`. See `NHTSSurveyTrip.load_person_days()` and `TBISurveyTrip.load_person_days()`.

### 13.2 Adding a New Activity Purpose

To add a new non-work activity purpose (e.g., "Medical"):

1. Add the purpose to the activity type mapping in the survey data loader.
2. Add a corresponding OSM tag mapping for POI discovery so the system knows which POIs serve that purpose.
3. Enable the purpose in the configuration JSON under the non-work purposes section.
4. The plan generator, gravity model, and mode choice will automatically handle the new purpose since they operate generically over configured purposes.

### 13.3 Adding Custom Traffic Count Sources

Provide two CSV files in `data/evaluation/`:

**counts_stations.csv** — one row per station:
```csv
station_id,latitude,longitude
10069,44.81059,-93.21900
```

**counts_volumes.csv** — hourly volumes per station per day:
```csv
station_id,date,h01,h02,...,h24
10069,2024-05-23,587,391,...,1150
```

Enable custom counts in the configuration:
```json
"counts": {
  "enabled": true,
  "custom": { "enabled": true, "weight": 1 }
}
```

### 13.4 Key Extension Points

| What You Want To Do | Where To Look |
|---|---|
| Add a new survey source | `data_sources/` — subclass `BaseSurveyTrip` |
| Change the gravity model | `models/` — OD matrix generation |
| Modify mode choice logic | `models/` — mode choice module |
| Add a new transit mode | Configuration JSON mode definitions + GTFS route type mapping |
| Change the network generation | `matsim/` — pt2matsim wrapper |
| Add new evaluation metrics | `matsim/` — evaluation module |
| Extend the web UI | `webapp/` — Flask application |
| Add new data sources to the DB | `utils/` — DB manager |

### 13.5 Forking and Contributing

1. **Fork** the repository on GitHub.
2. **Clone** your fork and create a feature branch.
3. **Follow the existing patterns**: survey sources subclass `BaseSurveyTrip`, plan generators follow the parallel worker pattern, and all configuration is declarative JSON.
4. **Test** on a small region with a low scaling factor (e.g., 0.01) for fast iteration.
5. **Submit a pull request** against the main branch with a description of the changes and any new configuration parameters.

---

## License

Copyright (C) 2026 TAREEK Contributors

This program is free software; you can redistribute it and/or modify it under the terms of the [GNU General Public License](LICENSE) as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version.

# Examples

Shared experiments for Tareek. Each example documents a real run for a
specific region — what was run, the configuration used, and the results.

Each example is a folder with a `README.md` and whatever supporting files the author
wants to show (config, small result CSVs, plots). Newer examples also include
`report.html`, the full experiment report from `scripts/experiment_report.py`. It is one
self-contained file; download it and open it in a browser, because GitHub does not show
HTML pages. Keep them small: commit the recipe
and the results, not large or regenerable inputs (OSM extracts, full MATSim
networks/plans).

## Index

| Region | Author | Date | Highlights |
|--------|--------|------|------------|
| [Twin Cities, MN-WI — **TBI 2023 local survey**](twincities-tbi-jalal-20260930/) | Jalal | 2026-09-30 | **Custom local survey (TBI 2023) instead of NHTS**; 15 counties, 0.15 scaling, 10 iters, hermes, person-first demand, non-work ×1.6, freight on; sim/obs 0.925, iqr 0.948, corr 0.882, CV 0.277, 96 counts; with a TBI vs NHTS vs blend comparison; [full report](twincities-tbi-jalal-20260930/report.html) |
| [Twin Cities, MN-WI](twincities-jalal-20260928/) | Jalal | 2026-09-28 | 15 counties, 0.15 scaling, 10 iters, hermes, person-first demand, non-work ×1.4, freight on; sim/obs 0.868, corr 0.875, CV 0.276, 94 counts; [full report](twincities-jalal-20260928/report.html) |
| [Birmingham, AL](birmingham-jalal-20260928/) | Jalal | 2026-09-28 | 2 counties, 0.25 scaling, 10 iters, hermes, person-first demand, work ×1.2, non-work ×2.0, freight on; sim/obs 0.912, corr 0.81, CV 0.717, 53 counts; [full report](birmingham-jalal-20260928/report.html) |
| [Madison, WI](madison-jalal-20260928/) | Jalal | 2026-09-28 | Dane County, 0.25 scaling, 10 iters, hermes, person-first demand, work ×1.1, non-work ×1.8, freight on; sim/obs 0.813, corr 0.97, CV 0.148, only 10 counts; [full report](madison-jalal-20260928/report.html) |

## Contributing

It's simple — see [CONTRIBUTING.md](CONTRIBUTING.md):

1. Fork the repo and add a folder `examples/<region>-<author>-<YYYYMMDD>/`.
2. Write a `README.md` showing whatever you want about your experiment. Use the
   existing examples in this folder as a guide.
3. Open a pull request.

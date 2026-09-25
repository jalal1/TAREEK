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
| [Birmingham, AL](birmingham-jalal-20260924/) | Jalal | 2026-09-24 | 2 counties, 0.25 scaling, 10 iters, qsim; sim/obs 0.945, corr 0.78, 53 counts; [full report](birmingham-jalal-20260924/report.html) |
| [Madison, WI (cold start)](madison-jalal-20260925/) | Jalal | 2026-09-25 | Dane County, estimator-seeded config, 0.25 scaling, 10 iters; sim/obs 1.009, corr 0.96, only 8 counts; [full report](madison-jalal-20260925/report.html) |

## Contributing

It's simple — see [CONTRIBUTING.md](CONTRIBUTING.md):

1. Fork the repo and add a folder `examples/<region>-<author>-<YYYYMMDD>/`.
2. Write a `README.md` showing whatever you want about your experiment. Use the
   existing examples in this folder as a guide.
3. Open a pull request.

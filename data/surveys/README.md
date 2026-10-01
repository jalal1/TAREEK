# Custom (local) travel surveys

Each folder holds one regional household travel survey and its own README. The README describes the source, the files, the size, the limits and the label mappings. Folder names are `<region>_<survey>[_<year>]`.

| Folder | Region | Survey type (`data.surveys[].type`) | Reader |
|---|---|---|---|
| `twincities_tbi_2023/` | Twin Cities, MN | `tbi` | `data_sources/tbi_survey.py` |
| `birmingham_al_local/` | Birmingham, AL | `bham_local` | `data_sources/bham_local_survey.py` |

NHTS is a national survey and stays in `data/nhts/`.

## Paths in the config

Survey paths are relative to `data.data_dir`, for example `"file": "surveys/twincities_tbi_2023/TravelBehaviorInventory2023Trip.csv.gz"`.

## Roles

A survey does up to five jobs: `person_days`, `chains`, `times`, `modes` and `od`. Its `weight` applies to all five. An optional `roles` object overrides the weight for each job. A survey that cannot do a job is skipped for it, for example a survey with no person file (`person_days`) or with no locations (`od`). See `data_sources/survey_manager.py` (`ROLES`) for the full rules.

## Adding a survey

1. Make a folder here and write its README.
2. Write a `BaseSurveyTrip` subclass in `data_sources/` and register it in `SurveyManager._ensure_registry`.
3. If the survey has no person file with no-travel days, return None from `load_person_days()`. Then pair it with a survey that has one, for example NHTS with `"roles": {"person_days": 1}`.
4. Survey rows go into the `survey_trips` table only once. After a reader change, delete the survey's rows so that the ETL runs again.

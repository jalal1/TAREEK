# Birmingham, AL local travel survey

Survey type in the config: `bham_local`. Reader: `data_sources/bham_local_survey.py`.

## Source

| Item | Value |
|---|---|
| File | `birmingham_al_local_survey.csv` (250 KB). Byte-identical to the published `survey.csv`. |
| Author | Jalal Khalil |
| Published | [Two research works on transport simulation for Birmingham, AL](https://almt0.github.io/background_traffic/index.html) ([survey.csv](https://almt0.github.io/background_traffic/survey.csv)) |
| Licence | MIT License (as stated on the page above) |
| Used in | *Realistic Transport Simulation: Tackling the Small Data Challenge with Open Data*, IEEE BigData 2019 |
| Survey year | Not in the file; collected before 2019. The config uses the year label `undated`. |

## Layout

The file has one row per respondent and 132 columns ("wide" format):

| Columns | Content |
|---|---|
| `id` | Respondent id (001-451, 443 rows) |
| `x0, y0, Loc_Type` | Where the day starts, and its type |
| `xk, yk` (k = 1..13) | Destination of trip k |
| `<k>_Trip_Start_Time`, `<k>_Trip_End_Time` | Departure and arrival time, `H:MM:SS` |
| `<k>_activity` | Destination purpose (10 labels) |
| `<k>_Mode` | Mode (Car, Uber/Lyft, Walk, Carpool/Vanpool, Transit, Taxi, Car rental, Bike) |
| `<k>_Wait_Time_min`, `<k>_Company`, `<k>_Car_Availability` | Ride-hailing questions only |
| demographic columns | Gender, age band, employment, occupation, industry, household income, degree, car ownership |
| `x14, y14` | Home location |

Coordinates are UTM zone 16N in metres (EPSG:32616).

## Size

- 443 persons and 1,129 trips (2.55 trips per person).
- After cleaning: 423 persons and 1,071 trips (2.53 trips per person).

## Limits

- There are no weights. Each trip has `trip_weight = 1`.
- There are no household ids.
- There is no travel date or day of the week. The data owner says all days are weekdays. The reader puts every trip on one reference Wednesday (2024-10-16).
- Every respondent reported at least one trip, so there are **no no-travel days**.
- All respondents are 18 or older, so there are **no students aged 5-17**.
- The survey **cannot do the `person_days` job**, and `load_person_days()` returns None. Use it together with a survey that has a person file, for example NHTS with `"roles": {"person_days": 1}`.
- The sample is not representative:
  - 75% of respondents are female.
  - 70% are aged 18-44.
  - Uber/Lyft is 6.3% of trips. The survey asks ride-hailing wait times and companies.
- Only 57% of days start and end at Home.
- The reader leaves `origin_loc`/`destination_loc` empty. With 1,071 trips, a block-group OD matrix would be noise, so the survey does no `od` job.

## Damaged cells

Excel damaged some cells. The reader handles each case as follows:

| Cell | Example | Handling |
|---|---|---|
| Time as an Excel day fraction | `0.629166667` | Read as 15:06 |
| One-digit minutes | `12:9:00` | Read as 12:09 |
| 24-hour time with "AM" | `16:00:00 AM` | Read as 16:00 |
| Arrival after midnight | `23:45 -> 0:00` | Kept; arrival is the next day |
| Time goes backwards (not at midnight) | `24:00 -> 13:00`, `12:45 -> 1:00` | Person dropped (4 persons) |
| A place in the mode column | `Home` | Person dropped (1 person) |
| Trip end without coordinates | | Person dropped (3 persons) |
| Trip end outside the region counties | | Person dropped (12 persons) |
| Day start type is not Home, but the start is at the home coordinates | `Nightlife/ Bar` at 05:00 | Start set to Home (8 persons) |
| Car availability `2-Jan`, `5-Mar` (were `1-2`, `3-5`) | | Not used |
| One row has its demographic fields shifted by one column | | Not used |

The reader drops whole persons, not single trips, so every kept day is an unbroken chain.

## Mappings

Purposes:

| Survey label | Tareek activity | Note |
|---|---|---|
| Home, Work, School | Home, Work, School | |
| Shopping- Grocery, Shopping- Retail | Shopping | |
| Eat/ Get take-out | Dining | |
| Nightlife/ Bar | Social | Judgment: the only leisure label |
| Services (e.g. Bank, post office) | Other | Judgment: NHTS puts errands in Shopping |
| Pick-up passenger, Drop-off passenger | Shopping | Judgment: same as TBI Escort and NHTS "transport someone" |

Modes:

| Survey label | Tareek mode | Note |
|---|---|---|
| Car, Car rental | Car | |
| Carpool/Vanpool | Car | Judgment: driver or passenger is not asked |
| Uber/Lyft | Rideshare | |
| Taxi | Rideshare | Judgment: same as NHTS taxi |
| Transit | Bus | Judgment: Birmingham has no rail transit |
| Walk, Bike | Walk, Bike | |

## Config entry

```json
"surveys": [
  { "type": "bham_local", "year": "undated",
    "file": "surveys/birmingham_al_local/birmingham_al_local_survey.csv",
    "weight": 1 },
  { "type": "nhts", "year": "2022", "file": "nhts/csv/tripv2pub.csv",
    "person_file": "nhts/csv/perv2pub.csv",
    "weight": 0, "roles": { "person_days": 1 } }
]
```

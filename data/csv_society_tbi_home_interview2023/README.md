# Travel Behavior Inventory (TBI) 2023 — Twin Cities household travel survey

This folder holds the parts of the **Metropolitan Council Travel Behavior Inventory
(TBI) 2023 Household Survey** that Tareek reads. TBI is the household travel survey of
the Twin Cities region. The survey was in the field from January 12, 2023 to
January 16, 2024.

Tareek uses it as a **custom local survey** in place of the national NHTS. See the
example [`examples/twincities-tbi-jalal-20260930`](../../examples/twincities-tbi-jalal-20260930/).

## Source and license

- **Publisher:** Metropolitan Council, 390 Robert Street North, St. Paul, MN 55101
- **Dataset:** Metropolitan Council Travel Behavior Inventory (TBI) 2023 Household
  Survey (metadata date 2025-03-05), distributed as `csv_society_tbi_home_interview2023`
- **License:** from the dataset metadata: *"This dataset is public domain under the
  Minnesota Government Data Practices Act (Minnesota Statutes Chapter 13)."*

The full metadata is in [`metadata/`](metadata/) (`metadata.xml`, `metadata.html`), with the
variable and value lists and the questionnaire.

### Notice from the Metropolitan Council

> NOTICE: The Geographic Information System (GIS) Data to which this notice is attached
> are made available pursuant to the Minnesota Government Data Practices Act (Minnesota
> Statutes Chapter 13). THE GIS DATA ARE PROVIDED TO YOU AS IS AND WITHOUT ANY WARRANTY
> AS TO THEIR PERFORMANCE, MERCHANTABILITY, OR FITNESS FOR ANY PARTICULAR PURPOSE. The GIS
> Data were developed by the Metropolitan Council for its own internal business purposes.
> The Metropolitan Council does not represent or warrant that the GIS Data or the data
> documentation are error-free, complete, current, or accurate. You are responsible for
> any consequences resulting from your use of the GIS Data or your reliance on the GIS
> Data. You should consult the data documentation for this particular GIS Data to
> determine the limitations of the GIS Data and the precision with which the GIS Data may
> depict distance, direction, location, or other geographic features. If you transmit or
> provide the GIS Data (or any portion of it) to another user, it is recommended that the
> GIS Data include a copy of this disclaimer and this metadata.

## Files

The CSV files are **gzip-compressed** (`.csv.gz`) so that each file is below the GitHub
file size limit. The content is not changed: each file unzips to the published CSV,
byte for byte. pandas reads `.csv.gz` directly, so Tareek needs no extra step.

| File | Size (compressed) | Tareek uses it for |
|------|------------------:|--------------------|
| `TravelBehaviorInventory2023LinkedTrip.csv.gz` | 11 MB | the trips; a linked trip joins the legs of a trip with transfers |
| `TravelBehaviorInventory2023Trip.csv.gz` | 14 MB | the 2020 block groups of each linked trip |
| `TravelBehaviorInventory2023Day.csv.gz` | 0.7 MB | the weighted person-days, and where each day began |
| `TravelBehaviorInventory2023Person.csv.gz` | 0.6 MB | the person group, and the reported commute days |
| `metadata/` | 1.1 MB | documentation from the publisher (not read by Tareek) |

The other tables of the published dataset (Household, Vehicle, Locations, TripPurpose)
are not used by Tareek and are not in this folder.

## Use in a config

```json
{
  "type": "tbi",
  "year": "2023",
  "file": "csv_society_tbi_home_interview2023/TravelBehaviorInventory2023Trip.csv.gz",
  "linked_trip_file": "csv_society_tbi_home_interview2023/TravelBehaviorInventory2023LinkedTrip.csv.gz",
  "person_file": "csv_society_tbi_home_interview2023/TravelBehaviorInventory2023Person.csv.gz",
  "day_file": "csv_society_tbi_home_interview2023/TravelBehaviorInventory2023Day.csv.gz",
  "weight": 1
}
```

The reader is `data_sources/tbi_survey.py`. The first run reads the files into the
`survey_trips` table of the database; later runs read the table.

# NYPD Complaint Data Historic - Data Quality Report

Generated at UTC: `2026-07-04T02:30:05.162635+00:00`

## Source

- File: `data/raw/NYPD_Complaint_Data_Historic.csv`

- Provenance: [reviewed NYC Open Data snapshot](../data/source/nyc_open_data/nypd_complaint_data_historic.md)

- File size GB: `3.19`

- Row count: `10,071,507`

- Column count: `35`


## Column Profile

Lexical minima and maxima are intentionally omitted because they can reproduce
event-level identifiers, exact coordinates, or location examples. The aggregate
missingness and cardinality measures are retained.

| column_name       |   missing_pct |   approx_unique_count |
|:------------------|--------------:|----------------------:|
| HADEVELOPT        |  99.6497      |                    35 |
| PARKS_NM          |  99.5613      |                  1371 |
| STATION_NAME      |  97.4201      |                   458 |
| TRANSIT_DISTRICT  |  97.4201      |                    13 |
| HOUSING_PSA       |  92.6347      |                  4498 |
| SUSP_AGE_GROUP    |  46.7461      |                   350 |
| SUSP_SEX          |  39.169       |                     3 |
| SUSP_RACE         |  37.8448      |                     9 |
| LOC_OF_OCCUR_DESC |  20.6552      |                     5 |
| CMPLNT_TO_DT      |  18.615       |                 10842 |
| CMPLNT_TO_TM      |  18.5524      |                  1082 |
| VIC_AGE_GROUP     |  16.1204      |                   335 |
| PREM_TYP_DESC     |   0.539314    |                   103 |
| OFNS_DESC         |   0.187728    |                    85 |
| BORO_NM           |   0.100064    |                     5 |
| PD_CD             |   0.0822518   |                   555 |
| PD_DESC           |   0.0822518   |                   430 |
| VIC_RACE          |   0.00937298  |                     9 |
| ADDR_PCT_CD       |   0.00765526  |                    79 |
| CMPLNT_FR_DT      |   0.0065035   |                 11920 |
| PATROL_BORO       |   0.00585811  |                     9 |
| Lat_Lon           |   0.00475599  |                193538 |
| Longitude         |   0.00475599  |                163716 |
| Latitude          |   0.00475599  |                158693 |
| Y_COORD_CD        |   0.00471628  |                 70018 |
| X_COORD_CD        |   0.00471628  |                 68763 |
| VIC_SEX           |   0.00305813  |                     6 |
| CRM_ATPT_CPTD_CD  |   0.00166807  |                     2 |
| CMPLNT_FR_TM      |   0.000476592 |                  1082 |
| CMPLNT_NUM        |   0           |              12095559 |
| RPT_DT            |   0           |                  8877 |
| KY_CD             |   0           |                    79 |
| JURIS_DESC        |   0           |                    29 |
| JURISDICTION_CODE |   0           |                    25 |
| LAW_CAT_CD        |   0           |                     3 |


## Data Quality Rule Counts

| rule_name                          |   issue_count |   issue_pct |
|:-----------------------------------|--------------:|------------:|
| missing_offense_description        |         18907 | 0.187728    |
| missing_borough                    |         10078 | 0.100064    |
| duplicate_complaint_number_surplus |          1106 | 0.0109815   |
| missing_precinct                   |           771 | 0.00765526  |
| missing_or_invalid_from_date       |           655 | 0.0065035   |
| missing_latitude_or_longitude      |           479 | 0.00475599  |
| to_date_before_from_date           |            77 | 0.000764533 |
| coordinates_outside_nyc_bounds     |            33 | 0.000327657 |
| report_date_before_incident_date   |            16 | 0.000158864 |
| missing_or_invalid_report_date     |             0 | 0           |
| missing_complaint_number           |             0 | 0           |
| invalid_from_time                  |             0 | 0           |
| invalid_law_category               |             0 | 0           |


## Date Quality

This exploratory table compares parsed calendar dates only, so
`to_date_before_from_date` is 77. The production cleaning rule prefers full
start/end timestamps when both times parse and falls back to dates otherwise;
that broader current contract flags 579 rows. Governance correctly uses the
production cleaning count. These values describe different rules and must not
be reconciled by subtraction or summation.

|   row_count |   missing_or_invalid_from_date |   missing_or_invalid_to_date |   missing_or_invalid_report_date | min_from_date       | max_from_date       | min_to_date         | max_to_date         | min_report_date     | max_report_date     |   future_from_dates |   future_report_dates |   to_date_before_from_date |
|------------:|-------------------------------:|-----------------------------:|---------------------------------:|:--------------------|:--------------------|:--------------------|:--------------------|:--------------------|:--------------------|--------------------:|----------------------:|---------------------------:|
|    10071507 |                            655 |                  1.87481e+06 |                                0 | 1010-05-14 00:00:00 | 2025-12-31 00:00:00 | 1010-10-15 00:00:00 | 2090-04-06 00:00:00 | 2006-01-01 00:00:00 | 2025-12-31 00:00:00 |                   0 |                     0 |                         77 |


## Time Quality

|   row_count |   missing_from_time |   invalid_from_time |   missing_to_time |   invalid_to_time |   missing_or_invalid_from_timestamp |   missing_or_invalid_to_timestamp |
|------------:|--------------------:|--------------------:|------------------:|------------------:|------------------------------------:|----------------------------------:|
| 1.00715e+07 |                  48 |                   0 |       1.86851e+06 |                 0 |                                 702 |                       1.87656e+06 |


## Geographic Quality

Coordinate extrema are intentionally omitted because they can reproduce
event-derived locations. Aggregate quality counts are retained.

|   row_count |   missing_lat_or_lon |   zero_lat_or_lon |   valid_nyc_coordinates |   coordinates_outside_nyc_bounds |   missing_projected_coordinates |
|------------:|---------------------:|------------------:|------------------------:|---------------------------------:|--------------------------------:|
| 1.00715e+07 |                  479 |                25 |              1.0071e+07 |                               33 |                             475 |


## Missingness by Business Column Group

| group                |   column_count |   avg_missing_pct |   max_missing_pct | highest_missing_column   |
|:---------------------|---------------:|------------------:|------------------:|:-------------------------|
| location_context     |              7 |        72.5543    |       99.6497     | HADEVELOPT               |
| suspect_demographics |              3 |        41.2533    |       46.7461     | SUSP_AGE_GROUP           |
| incident_datetime    |              5 |         7.43489   |       18.615      | CMPLNT_TO_DT             |
| victim_demographics  |              3 |         5.37761   |       16.1204     | VIC_AGE_GROUP            |
| offense              |              6 |         0.0589832 |        0.187728   | OFNS_DESC                |
| location_admin       |              5 |         0.0227156 |        0.100064   | BORO_NM                  |
| coordinates          |              5 |         0.0047401 |        0.00475599 | Lat_Lon                  |
| identifier           |              1 |         0         |        0          | CMPLNT_NUM               |


## Top Boroughs

| value         |   row_count |       pct |
|:--------------|------------:|----------:|
| BROOKLYN      |     2940167 | 29.1929   |
| MANHATTAN     |     2424880 | 24.0766   |
| BRONX         |     2184541 | 21.6903   |
| QUEENS        |     2053345 | 20.3877   |
| STATEN ISLAND |      458496 |  4.55241  |
|               |       10078 |  0.100064 |


## Top Offenses

| value                           |   row_count |       pct |
|:--------------------------------|------------:|----------:|
| PETIT LARCENY                   |     1772206 | 17.5962   |
| HARRASSMENT 2                   |     1359235 | 13.4958   |
| ASSAULT 3 & RELATED OFFENSES    |     1059220 | 10.517    |
| CRIMINAL MISCHIEF & RELATED OF  |      952237 |  9.45476  |
| GRAND LARCENY                   |      880071 |  8.73823  |
| DANGEROUS DRUGS                 |      490641 |  4.87157  |
| OFF. AGNST PUB ORD SENSBLTY &   |      473080 |  4.69721  |
| FELONY ASSAULT                  |      423210 |  4.20205  |
| ROBBERY                         |      346607 |  3.44146  |
| BURGLARY                        |      323118 |  3.20824  |
| MISCELLANEOUS PENAL LAW         |      272553 |  2.70618  |
| GRAND LARCENY OF MOTOR VEHICLE  |      201767 |  2.00334  |
| DANGEROUS WEAPONS               |      200150 |  1.98729  |
| VEHICLE AND TRAFFIC LAWS        |      186564 |  1.85239  |
| OFFENSES AGAINST PUBLIC ADMINI  |      175025 |  1.73782  |
| SEX CRIMES                      |      131879 |  1.30943  |
| INTOXICATED & IMPAIRED DRIVING  |      112225 |  1.11428  |
| FORGERY                         |      102252 |  1.01526  |
| CRIMINAL TRESPASS               |       96468 |  0.957831 |
| THEFT-FRAUD                     |       93551 |  0.928868 |
| FRAUDS                          |       57064 |  0.566588 |
| POSSESSION OF STOLEN PROPERTY   |       47238 |  0.469026 |
| OFFENSES INVOLVING FRAUD        |       37352 |  0.370868 |
| RAPE                            |       30078 |  0.298644 |
| OTHER OFFENSES RELATED TO THEFT |       29534 |  0.293243 |


## Sensitive Field Handling

Victim and suspect demographic columns are profiled for data quality only. They should be excluded from the first forecasting model to avoid person-level profiling and proxy-based unfairness.

| column_name    |   missing_pct |   approx_unique_count |
|:---------------|--------------:|----------------------:|
| SUSP_AGE_GROUP |   46.7461     |                   350 |
| SUSP_SEX       |   39.169      |                     3 |
| SUSP_RACE      |   37.8448     |                     9 |
| VIC_AGE_GROUP  |   16.1204     |                   335 |
| VIC_RACE       |    0.00937298 |                     9 |
| VIC_SEX        |    0.00305813 |                     6 |


## Historical next actions

The actions below were the recommendations at the exploratory-analysis
milestone. They are now implemented by the deterministic cleaning, aggregate,
forecast, hotspot, anomaly, and dashboard-contract pipeline. See the
[project README](../README.md) for the current build order and the
[Governance report](dashboard_governance_view.md) for current quality semantics.

1. Normalize null-like values and invalid categories in a reproducible cleaning pipeline.

2. Use `CMPLNT_FR_DT` and `CMPLNT_FR_TM` to create a canonical incident timestamp.

3. Keep quality flags for invalid dates, long durations, missing boroughs, missing precincts, and invalid coordinates.

4. Use weekly and monthly aggregate parquet files for baseline forecasting and dashboard summaries.

5. Exclude suspect and victim demographic fields from the first prediction model; use them only for fairness and data coverage review.

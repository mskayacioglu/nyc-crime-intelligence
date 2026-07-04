# NYPD Complaint Data Historic - Data Quality Report

Generated at UTC: `2026-07-04T02:30:05.162635+00:00`

## Source

- File: `/content/drive/MyDrive/bir-nyc/data/raw/NYPD_Complaint_Data_Historic.csv`

- File size GB: `3.19`

- Row count: `10,071,507`

- Column count: `35`


## Column Profile

| column_name       |   missing_pct |   approx_unique_count | min_lexical_value                             | max_lexical_value              |
|:------------------|--------------:|----------------------:|:----------------------------------------------|:-------------------------------|
| HADEVELOPT        |  99.6497      |                    35 | AMSTERDAM                                     | WOODSIDE                       |
| PARKS_NM          |  99.5613      |                  1371 | "UNCLE" VITO E. MARANZANO GLENDALE PLAYGROUND | ZION TRIANGLE                  |
| STATION_NAME      |  97.4201      |                   458 | 1 AVENUE                                      | ZEREGA AVENUE                  |
| TRANSIT_DISTRICT  |  97.4201      |                    13 | 1                                             | 4                              |
| HOUSING_PSA       |  92.6347      |                  4498 | 10                                            | 9993                           |
| SUSP_AGE_GROUP    |  46.7461      |                   350 | -1                                            | UNKNOWN                        |
| SUSP_SEX          |  39.169       |                     3 | F                                             | U                              |
| SUSP_RACE         |  37.8448      |                     9 | AMERICAN INDIAN/ALASKAN NATIVE                | WHITE HISPANIC                 |
| LOC_OF_OCCUR_DESC |  20.6552      |                     5 | FRONT OF                                      | REAR OF                        |
| CMPLNT_TO_DT      |  18.615       |                 10842 | 01/01/1967                                    | 12/31/2025                     |
| CMPLNT_TO_TM      |  18.5524      |                  1082 | 00:00:00                                      | 23:59:00                       |
| VIC_AGE_GROUP     |  16.1204      |                   335 | -1                                            | UNKNOWN                        |
| PREM_TYP_DESC     |   0.539314    |                   103 | ABANDONED BUILDING                            | VIDEO STORE                    |
| OFNS_DESC         |   0.187728    |                    85 | ABORTION                                      | VEHICLE AND TRAFFIC LAWS       |
| BORO_NM           |   0.100064    |                     5 | BRONX                                         | STATEN ISLAND                  |
| PD_CD             |   0.0822518   |                   555 | 100                                           | 975                            |
| PD_DESC           |   0.0822518   |                   430 | A.B.C.,FALSE PROOF OF AGE                     | WEAPONS,PROHIBITED USE IMITATI |
| VIC_RACE          |   0.00937298  |                     9 | AMERICAN INDIAN/ALASKAN NATIVE                | WHITE HISPANIC                 |
| ADDR_PCT_CD       |   0.00765526  |                    79 | 1                                             | 94                             |
| CMPLNT_FR_DT      |   0.0065035   |                 11920 | 01/01/1948                                    | 12/31/2025                     |
| PATROL_BORO       |   0.00585811  |                     9 | PATROL BORO BKLYN NORTH                       | PATROL BORO STATEN ISLAND      |
| Lat_Lon           |   0.00475599  |                193538 | (0.0, 0.0)                                    | (40.91295931, -73.90245844)    |
| Longitude         |   0.00475599  |                163716 | -73.700286                                    | 0                              |
| Latitude          |   0.00475599  |                158693 | 0                                             | 40.91295931                    |
| Y_COORD_CD        |   0.00471628  |                 70018 | 0                                             | 271909                         |
| X_COORD_CD        |   0.00471628  |                 68763 | -74                                           | 999999                         |
| VIC_SEX           |   0.00305813  |                     6 | D                                             | U                              |
| CRM_ATPT_CPTD_CD  |   0.00166807  |                     2 | ATTEMPTED                                     | COMPLETED                      |
| CMPLNT_FR_TM      |   0.000476592 |                  1082 | 00:00:00                                      | 23:59:00                       |
| CMPLNT_NUM        |   0           |              12095559 | 10006319                                      | 9967306                        |
| RPT_DT            |   0           |                  8877 | 01/01/2006                                    | 12/31/2025                     |
| KY_CD             |   0           |                    79 | 101                                           | 881                            |
| JURIS_DESC        |   0           |                    29 | AMTRACK                                       | U.S. PARK POLICE               |
| JURISDICTION_CODE |   0           |                    25 | 0                                             | 97                             |
| LAW_CAT_CD        |   0           |                     3 | FELONY                                        | VIOLATION                      |


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

|   row_count |   missing_or_invalid_from_date |   missing_or_invalid_to_date |   missing_or_invalid_report_date | min_from_date       | max_from_date       | min_to_date         | max_to_date         | min_report_date     | max_report_date     |   future_from_dates |   future_report_dates |   to_date_before_from_date |
|------------:|-------------------------------:|-----------------------------:|---------------------------------:|:--------------------|:--------------------|:--------------------|:--------------------|:--------------------|:--------------------|--------------------:|----------------------:|---------------------------:|
|    10071507 |                            655 |                  1.87481e+06 |                                0 | 1010-05-14 00:00:00 | 2025-12-31 00:00:00 | 1010-10-15 00:00:00 | 2090-04-06 00:00:00 | 2006-01-01 00:00:00 | 2025-12-31 00:00:00 |                   0 |                     0 |                         77 |


## Time Quality

|   row_count |   missing_from_time |   invalid_from_time |   missing_to_time |   invalid_to_time |   missing_or_invalid_from_timestamp |   missing_or_invalid_to_timestamp |
|------------:|--------------------:|--------------------:|------------------:|------------------:|------------------------------------:|----------------------------------:|
| 1.00715e+07 |                  48 |                   0 |       1.86851e+06 |                 0 |                                 702 |                       1.87656e+06 |


## Geographic Quality

|   row_count |   missing_lat_or_lon |   zero_lat_or_lon |   valid_nyc_coordinates |   coordinates_outside_nyc_bounds |   min_latitude |   max_latitude |   min_longitude |   max_longitude |   missing_projected_coordinates |
|------------:|---------------------:|------------------:|------------------------:|---------------------------------:|---------------:|---------------:|----------------:|----------------:|--------------------------------:|
| 1.00715e+07 |                  479 |                25 |              1.0071e+07 |                               33 |              0 |         40.913 |         -74.255 |               0 |                             475 |


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


## Recommended Next Actions

1. Normalize null-like values and invalid categories in a reproducible cleaning pipeline.

2. Use `CMPLNT_FR_DT` and `CMPLNT_FR_TM` to create a canonical incident timestamp.

3. Keep quality flags for invalid dates, long durations, missing boroughs, missing precincts, and invalid coordinates.

4. Use weekly and monthly aggregate parquet files for baseline forecasting and dashboard summaries.

5. Exclude suspect and victim demographic fields from the first prediction model; use them only for fairness and data coverage review.

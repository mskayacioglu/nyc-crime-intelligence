# NYPD Complaint Data Historic - Exploratory Analysis

Generated at UTC: `2026-07-05T11:34:42.169299+00:00`

## Scope

This Phase 3 analytical baseline reads the cleaned Phase 2 Parquet outputs and produces dashboard-ready descriptive summaries. It does not implement forecasting, machine learning, APIs, or a dashboard UI.

## Inputs

- clean_events: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/complaints_clean.parquet`
- weekly_area: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/crime_weekly_area.parquet`
- monthly_area: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/crime_monthly_area.parquet`

## Analysis Window

| min_complaint_from_date | max_complaint_from_date | min_week_start | max_week_start | min_month_start | max_month_start |
| --- | --- | --- | --- | --- | --- |
| 2006-01-01 | 2025-12-31 | 2005-12-26 | 2025-12-29 | 2006-01-01 | 2025-12-01 |

## Key Findings

- The analytical baseline covers 10,049,687 clean aggregate events from 2006-01-01 through 2025-12-31.
- Annual volume peaks in 2024 with 574,192 complaints.
- The latest available year, 2025, has 567,668 complaints (-1.14% year over year).
- BROOKLYN ranks first by borough with 2,933,193 complaints (29.19% of clean aggregate events).
- Precinct 75 in BROOKLYN is the highest-volume precinct in the ranking with 320,571 complaints.
- PETIT LARCENY is the most common offense type (1,769,733 complaints; 17.61% of total).
- MISDEMEANOR is the largest law category at 54.81% of complaints.
- The busiest hour is 15:00 and the busiest day is Friday based on cleaned incident start timestamps.
- The fastest borough/offense increase is ADMINISTRATIVE CODE in BROOKLYN (174.42% over the prior window).
- The fastest borough/offense decrease is DISORDERLY CONDUCT in MANHATTAN (-82.66% over the prior window).
- The fastest precinct/offense increase is ADMINISTRATIVE CODE in precinct 77 (BROOKLYN); 209.3% over the prior window.
- The fastest precinct/offense decrease is DISORDERLY CONDUCT in precinct 14 (MANHATTAN); -92.24% over the prior window.
- 10,049,230 clean aggregate events (99.9955%) have map-ready coordinates. The highest-volume heatmap cell is centered at (40.755, -73.985).

## Yearly Trend

| year | crime_count | previous_year_count | year_over_year_change | year_over_year_pct_change |
| --- | --- | --- | --- | --- |
| 2006 | 530,219 |  |  |  |
| 2007 | 535,514 | 530,219 | 5,295 | 1 |
| 2008 | 529,009 | 535,514 | -6,505 | -1.21 |
| 2009 | 511,247 | 529,009 | -17,762 | -3.36 |
| 2010 | 510,418 | 511,247 | -829 | -0.16 |
| 2011 | 498,962 | 510,418 | -11,456 | -2.24 |
| 2012 | 505,106 | 498,962 | 6,144 | 1.23 |
| 2013 | 496,292 | 505,106 | -8,814 | -1.74 |
| 2014 | 492,577 | 496,292 | -3,715 | -0.75 |
| 2015 | 479,210 | 492,577 | -13,367 | -2.71 |
| 2016 | 478,780 | 479,210 | -430 | -0.09 |
| 2017 | 468,556 | 478,780 | -10,224 | -2.14 |
| 2018 | 462,931 | 468,556 | -5,625 | -1.2 |
| 2019 | 459,608 | 462,931 | -3,323 | -0.72 |
| 2020 | 414,277 | 459,608 | -45,331 | -9.86 |
| 2021 | 450,331 | 414,277 | 36,054 | 8.7 |
| 2022 | 531,322 | 450,331 | 80,991 | 17.98 |
| 2023 | 553,468 | 531,322 | 22,146 | 4.17 |
| 2024 | 574,192 | 553,468 | 20,724 | 3.74 |
| 2025 | 567,668 | 574,192 | -6,524 | -1.14 |

## Recent Monthly Trend

| month_start | month | crime_count | previous_month_count | month_over_month_change | month_over_month_pct_change |
| --- | --- | --- | --- | --- | --- |
| 2024-01-01 | 2024-01 | 46,494 | 45,461 | 1,033 | 2.27 |
| 2024-02-01 | 2024-02 | 43,659 | 46,494 | -2,835 | -6.1 |
| 2024-03-01 | 2024-03 | 46,552 | 43,659 | 2,893 | 6.63 |
| 2024-04-01 | 2024-04 | 45,562 | 46,552 | -990 | -2.13 |
| 2024-05-01 | 2024-05 | 50,110 | 45,562 | 4,548 | 9.98 |
| 2024-06-01 | 2024-06 | 49,797 | 50,110 | -313 | -0.62 |
| 2024-07-01 | 2024-07 | 50,810 | 49,797 | 1,013 | 2.03 |
| 2024-08-01 | 2024-08 | 50,175 | 50,810 | -635 | -1.25 |
| 2024-09-01 | 2024-09 | 48,845 | 50,175 | -1,330 | -2.65 |
| 2024-10-01 | 2024-10 | 50,591 | 48,845 | 1,746 | 3.57 |
| 2024-11-01 | 2024-11 | 47,205 | 50,591 | -3,386 | -6.69 |
| 2024-12-01 | 2024-12 | 44,392 | 47,205 | -2,813 | -5.96 |
| 2025-01-01 | 2025-01 | 46,117 | 44,392 | 1,725 | 3.89 |
| 2025-02-01 | 2025-02 | 42,191 | 46,117 | -3,926 | -8.51 |
| 2025-03-01 | 2025-03 | 48,830 | 42,191 | 6,639 | 15.74 |
| 2025-04-01 | 2025-04 | 48,665 | 48,830 | -165 | -0.34 |
| 2025-05-01 | 2025-05 | 50,914 | 48,665 | 2,249 | 4.62 |
| 2025-06-01 | 2025-06 | 48,874 | 50,914 | -2,040 | -4.01 |
| 2025-07-01 | 2025-07 | 49,984 | 48,874 | 1,110 | 2.27 |
| 2025-08-01 | 2025-08 | 49,205 | 49,984 | -779 | -1.56 |
| 2025-09-01 | 2025-09 | 48,666 | 49,205 | -539 | -1.1 |
| 2025-10-01 | 2025-10 | 48,936 | 48,666 | 270 | 0.55 |
| 2025-11-01 | 2025-11 | 45,335 | 48,936 | -3,601 | -7.36 |
| 2025-12-01 | 2025-12 | 39,951 | 45,335 | -5,384 | -11.88 |

## Recent Weekly Trend

| week_start | crime_count | previous_week_count | week_over_week_change | week_over_week_pct_change |
| --- | --- | --- | --- | --- |
| 2025-09-15 | 11,670 | 11,424 | 246 | 2.15 |
| 2025-09-22 | 11,162 | 11,670 | -508 | -4.35 |
| 2025-09-29 | 11,525 | 11,162 | 363 | 3.25 |
| 2025-10-06 | 11,237 | 11,525 | -288 | -2.5 |
| 2025-10-13 | 10,849 | 11,237 | -388 | -3.45 |
| 2025-10-20 | 10,828 | 10,849 | -21 | -0.19 |
| 2025-10-27 | 10,771 | 10,828 | -57 | -0.53 |
| 2025-11-03 | 11,107 | 10,771 | 336 | 3.12 |
| 2025-11-10 | 10,784 | 11,107 | -323 | -2.91 |
| 2025-11-17 | 10,625 | 10,784 | -159 | -1.47 |
| 2025-11-24 | 9,686 | 10,625 | -939 | -8.84 |
| 2025-12-01 | 10,120 | 9,686 | 434 | 4.48 |
| 2025-12-08 | 9,449 | 10,120 | -671 | -6.63 |
| 2025-12-15 | 9,470 | 9,449 | 21 | 0.22 |
| 2025-12-22 | 7,743 | 9,470 | -1,727 | -18.24 |
| 2025-12-29 | 3,169 | 7,743 | -4,574 | -59.07 |

## Borough Rankings

| rank | borough | crime_count | pct_total | avg_monthly_count | active_months |
| --- | --- | --- | --- | --- | --- |
| 1 | BROOKLYN | 2,933,193 | 29.19 | 12,221.64 | 240 |
| 2 | MANHATTAN | 2,420,027 | 24.08 | 10,083.45 | 240 |
| 3 | BRONX | 2,180,328 | 21.7 | 9,084.7 | 240 |
| 4 | QUEENS | 2,048,626 | 20.38 | 8,535.94 | 240 |
| 5 | STATEN ISLAND | 457,448 | 4.55 | 1,906.03 | 240 |
| 6 | UNKNOWN | 10,065 | 0.1 | 60.63 | 166 |

## Top Precinct Rankings

| rank | borough | precinct | crime_count | pct_total_known_precincts | avg_monthly_count | active_months |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | BROOKLYN | 75 | 320,571 | 3.19 | 1,335.71 | 240 |
| 2 | BRONX | 43 | 250,007 | 2.49 | 1,041.7 | 240 |
| 3 | BRONX | 44 | 249,084 | 2.48 | 1,037.85 | 240 |
| 4 | BRONX | 40 | 245,515 | 2.44 | 1,022.98 | 240 |
| 5 | MANHATTAN | 14 | 235,250 | 2.34 | 980.21 | 240 |
| 6 | BRONX | 46 | 208,378 | 2.07 | 868.24 | 240 |
| 7 | BRONX | 52 | 205,378 | 2.04 | 855.74 | 240 |
| 8 | BROOKLYN | 73 | 201,845 | 2.01 | 841.02 | 240 |
| 9 | BRONX | 47 | 196,864 | 1.96 | 820.27 | 240 |
| 10 | BROOKLYN | 67 | 191,045 | 1.9 | 796.02 | 240 |
| 11 | STATEN ISLAND | 120 | 187,783 | 1.87 | 782.43 | 240 |
| 12 | QUEENS | 114 | 187,147 | 1.86 | 779.78 | 240 |
| 13 | QUEENS | 109 | 173,463 | 1.73 | 722.76 | 240 |
| 14 | QUEENS | 103 | 167,678 | 1.67 | 698.66 | 240 |
| 15 | BRONX | 42 | 166,455 | 1.66 | 693.56 | 240 |

## Offense Type Distribution

| rank | offense_type | crime_count | pct_total |
| --- | --- | --- | --- |
| 1 | PETIT LARCENY | 1,769,733 | 17.61 |
| 2 | HARRASSMENT 2 | 1,357,710 | 13.51 |
| 3 | ASSAULT 3 & RELATED OFFENSES | 1,058,625 | 10.53 |
| 4 | CRIMINAL MISCHIEF & RELATED OF | 951,310 | 9.47 |
| 5 | GRAND LARCENY | 875,575 | 8.71 |
| 6 | DANGEROUS DRUGS | 490,505 | 4.88 |
| 7 | OFF. AGNST PUB ORD SENSBLTY & | 471,572 | 4.69 |
| 8 | FELONY ASSAULT | 423,045 | 4.21 |
| 9 | ROBBERY | 346,431 | 3.45 |
| 10 | BURGLARY | 322,778 | 3.21 |
| 11 | MISCELLANEOUS PENAL LAW | 272,290 | 2.71 |
| 12 | GRAND LARCENY OF MOTOR VEHICLE | 201,519 | 2.01 |
| 13 | DANGEROUS WEAPONS | 200,088 | 1.99 |
| 14 | VEHICLE AND TRAFFIC LAWS | 186,505 | 1.86 |
| 15 | OFFENSES AGAINST PUBLIC ADMINI | 174,960 | 1.74 |
| 16 | SEX CRIMES | 129,221 | 1.29 |
| 17 | INTOXICATED & IMPAIRED DRIVING | 112,192 | 1.12 |
| 18 | FORGERY | 101,917 | 1.01 |
| 19 | CRIMINAL TRESPASS | 96,422 | 0.96 |
| 20 | THEFT-FRAUD | 90,619 | 0.9 |

Other offense count outside the displayed top list: `217,253`.

## Law Category Distribution

| rank | law_category | crime_count | pct_total |
| --- | --- | --- | --- |
| 1 | MISDEMEANOR | 5,507,915 | 54.81 |
| 2 | FELONY | 3,157,265 | 31.42 |
| 3 | VIOLATION | 1,384,507 | 13.78 |

## Hour-of-Day Pattern

| hour_of_day | hour_label | crime_count | pct_total |
| --- | --- | --- | --- |
| 0 | 00:00 | 468,100 | 4.66 |
| 1 | 01:00 | 330,575 | 3.29 |
| 2 | 02:00 | 269,894 | 2.69 |
| 3 | 03:00 | 228,355 | 2.27 |
| 4 | 04:00 | 198,779 | 1.98 |
| 5 | 05:00 | 145,979 | 1.45 |
| 6 | 06:00 | 153,727 | 1.53 |
| 7 | 07:00 | 220,192 | 2.19 |
| 8 | 08:00 | 347,508 | 3.46 |
| 9 | 09:00 | 378,267 | 3.76 |
| 10 | 10:00 | 401,607 | 4 |
| 11 | 11:00 | 412,824 | 4.11 |
| 12 | 12:00 | 559,671 | 5.57 |
| 13 | 13:00 | 481,157 | 4.79 |
| 14 | 14:00 | 539,245 | 5.37 |
| 15 | 15:00 | 605,616 | 6.03 |
| 16 | 16:00 | 586,805 | 5.84 |
| 17 | 17:00 | 590,936 | 5.88 |
| 18 | 18:00 | 596,995 | 5.94 |
| 19 | 19:00 | 571,505 | 5.69 |
| 20 | 20:00 | 559,562 | 5.57 |
| 21 | 21:00 | 503,860 | 5.01 |
| 22 | 22:00 | 471,096 | 4.69 |
| 23 | 23:00 | 427,385 | 4.25 |

## Day-of-Week Pattern

| iso_day_of_week | day_name | crime_count | pct_total |
| --- | --- | --- | --- |
| 1 | Monday | 1,371,618 | 13.65 |
| 2 | Tuesday | 1,443,407 | 14.36 |
| 3 | Wednesday | 1,482,686 | 14.75 |
| 4 | Thursday | 1,457,993 | 14.51 |
| 5 | Friday | 1,541,436 | 15.34 |
| 6 | Saturday | 1,436,985 | 14.3 |
| 7 | Sunday | 1,315,562 | 13.09 |

## Growth and Decline Windows

| window_months | min_previous_period_count | previous_period_start | previous_period_end | current_period_start | current_period_end |
| --- | --- | --- | --- | --- | --- |
| 12 | 100 | 2024-01-01 | 2024-12-01 | 2025-01-01 | 2025-12-01 |

### Fastest Increasing Borough/Offense Combinations

| rank | borough | offense_type | previous_count | current_count | absolute_change | pct_change |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | BROOKLYN | ADMINISTRATIVE CODE | 985 | 2,703 | 1,718 | 174.42 |
| 2 | QUEENS | ADMINISTRATIVE CODE | 371 | 926 | 555 | 149.6 |
| 3 | QUEENS | PROSTITUTION & RELATED OFFENSES | 229 | 544 | 315 | 137.55 |
| 4 | QUEENS | OTHER STATE LAWS | 398 | 924 | 526 | 132.16 |
| 5 | BROOKLYN | GAMBLING | 123 | 249 | 126 | 102.44 |
| 6 | BROOKLYN | PETIT LARCENY OF MOTOR VEHICLE | 217 | 436 | 219 | 100.92 |
| 7 | BROOKLYN | OTHER STATE LAWS | 831 | 1,469 | 638 | 76.77 |
| 8 | STATEN ISLAND | OTHER OFFENSES RELATED TO THEFT | 253 | 445 | 192 | 75.89 |
| 9 | MANHATTAN | OTHER STATE LAWS | 470 | 794 | 324 | 68.94 |
| 10 | BRONX | OTHER STATE LAWS | 530 | 883 | 353 | 66.6 |

### Fastest Decreasing Borough/Offense Combinations

| rank | borough | offense_type | previous_count | current_count | absolute_change | pct_change |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | MANHATTAN | DISORDERLY CONDUCT | 248 | 43 | -205 | -82.66 |
| 2 | QUEENS | ARSON | 137 | 69 | -68 | -49.64 |
| 3 | BRONX | OFFENSES INVOLVING FRAUD | 826 | 473 | -353 | -42.74 |
| 4 | BRONX | ARSON | 218 | 132 | -86 | -39.45 |
| 5 | BROOKLYN | UNAUTHORIZED USE OF A VEHICLE | 518 | 343 | -175 | -33.78 |
| 6 | MANHATTAN | UNAUTHORIZED USE OF A VEHICLE | 177 | 120 | -57 | -32.2 |
| 7 | BROOKLYN | OFFENSES INVOLVING FRAUD | 707 | 481 | -226 | -31.97 |
| 8 | MANHATTAN | OFFENSES INVOLVING FRAUD | 970 | 673 | -297 | -30.62 |
| 9 | STATEN ISLAND | FRAUDS | 243 | 171 | -72 | -29.63 |
| 10 | STATEN ISLAND | GRAND LARCENY OF MOTOR VEHICLE | 332 | 240 | -92 | -27.71 |

### Fastest Increasing Precinct/Offense Combinations

| rank | borough | precinct | offense_type | previous_count | current_count | absolute_change | pct_change |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | BROOKLYN | 77 | ADMINISTRATIVE CODE | 129 | 399 | 270 | 209.3 |
| 2 | BROOKLYN | 78 | OTHER OFFENSES RELATED TO THEFT | 106 | 301 | 195 | 183.96 |
| 3 | MANHATTAN | 1 | FORGERY | 158 | 431 | 273 | 172.78 |
| 4 | MANHATTAN | 5 | FORGERY | 180 | 442 | 262 | 145.56 |
| 5 | BROOKLYN | 60 | OTHER OFFENSES RELATED TO THEFT | 243 | 587 | 344 | 141.56 |
| 6 | BROOKLYN | 81 | OTHER OFFENSES RELATED TO THEFT | 323 | 779 | 456 | 141.18 |
| 7 | BRONX | 46 | DANGEROUS DRUGS | 534 | 1,247 | 713 | 133.52 |
| 8 | QUEENS | 110 | PROSTITUTION & RELATED OFFENSES | 101 | 203 | 102 | 100.99 |
| 9 | QUEENS | 114 | DANGEROUS DRUGS | 165 | 329 | 164 | 99.39 |
| 10 | BROOKLYN | 77 | DANGEROUS DRUGS | 130 | 258 | 128 | 98.46 |

### Fastest Decreasing Precinct/Offense Combinations

| rank | borough | precinct | offense_type | previous_count | current_count | absolute_change | pct_change |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | MANHATTAN | 14 | DISORDERLY CONDUCT | 116 | 9 | -107 | -92.24 |
| 2 | QUEENS | 104 | OTHER OFFENSES RELATED TO THEFT | 107 | 14 | -93 | -86.92 |
| 3 | BRONX | 46 | OFFENSES INVOLVING FRAUD | 109 | 32 | -77 | -70.64 |
| 4 | BRONX | 42 | OFFENSES INVOLVING FRAUD | 153 | 56 | -97 | -63.4 |
| 5 | MANHATTAN | 5 | OFFENSES INVOLVING FRAUD | 115 | 44 | -71 | -61.74 |
| 6 | QUEENS | 103 | FORGERY | 259 | 108 | -151 | -58.3 |
| 7 | QUEENS | 105 | GRAND LARCENY OF MOTOR VEHICLE | 434 | 194 | -240 | -55.3 |
| 8 | STATEN ISLAND | 123 | VEHICLE AND TRAFFIC LAWS | 192 | 88 | -104 | -54.17 |
| 9 | QUEENS | 115 | OTHER OFFENSES RELATED TO THEFT | 227 | 105 | -122 | -53.74 |
| 10 | QUEENS | 105 | CRIMINAL MISCHIEF & RELATED OF | 779 | 367 | -412 | -52.89 |

## Map-Ready Summary

- Coordinate filter: `is_clean_event_for_aggregate and non-missing, non-zero coordinates inside broad NYC bounds`
- Heatmap grid size degrees: `0.01`
- Heatmap cells emitted: `500`

### Highest-Volume Precinct Map Rows

| rank | borough | precinct | crime_count | pct_valid_coordinate_events | centroid_latitude | centroid_longitude | valid_coordinate_count | top_offense_type | top_offense_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | BROOKLYN | 75 | 320,701 | 3.19 | 40.66909 | -73.88189 | 320,701 | HARRASSMENT 2 | 41,680 |
| 2 | BRONX | 43 | 250,034 | 2.49 | 40.82743 | -73.86502 | 250,034 | HARRASSMENT 2 | 34,617 |
| 3 | BRONX | 44 | 249,104 | 2.48 | 40.83419 | -73.91931 | 249,104 | PETIT LARCENY | 34,176 |
| 4 | BRONX | 40 | 245,539 | 2.45 | 40.81354 | -73.91724 | 245,539 | HARRASSMENT 2 | 33,436 |
| 5 | MANHATTAN | 14 | 235,262 | 2.34 | 40.75259 | -73.98832 | 235,262 | PETIT LARCENY | 77,153 |
| 6 | BRONX | 46 | 208,397 | 2.08 | 40.85318 | -73.90676 | 208,397 | HARRASSMENT 2 | 29,757 |
| 7 | BRONX | 52 | 205,389 | 2.05 | 40.86954 | -73.89135 | 205,389 | PETIT LARCENY | 33,435 |
| 8 | BROOKLYN | 73 | 201,878 | 2.01 | 40.66915 | -73.91087 | 201,878 | HARRASSMENT 2 | 29,746 |
| 9 | BRONX | 47 | 196,880 | 1.96 | 40.88545 | -73.85313 | 196,880 | HARRASSMENT 2 | 29,237 |
| 10 | BROOKLYN | 67 | 191,058 | 1.9 | 40.65019 | -73.93569 | 191,058 | HARRASSMENT 2 | 31,428 |
| 11 | QUEENS | 114 | 189,935 | 1.89 | 40.76388 | -73.92243 | 189,935 | PETIT LARCENY | 36,432 |
| 12 | STATEN ISLAND | 120 | 187,802 | 1.87 | 40.62966 | -74.09942 | 187,802 | HARRASSMENT 2 | 34,811 |
| 13 | QUEENS | 109 | 173,476 | 1.73 | 40.76565 | -73.82342 | 173,476 | PETIT LARCENY | 39,777 |
| 14 | QUEENS | 103 | 167,702 | 1.67 | 40.70343 | -73.79253 | 167,702 | PETIT LARCENY | 24,429 |
| 15 | BRONX | 42 | 166,461 | 1.66 | 40.83091 | -73.90034 | 166,461 | HARRASSMENT 2 | 26,047 |

### Highest-Volume Heatmap Cells

| rank | latitude | longitude | crime_count | pct_top_cells_total | dominant_borough | top_offense_type | top_offense_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 40.755 | -73.985 | 129,471 | 1.29 | MANHATTAN | PETIT LARCENY | 49,813 |
| 2 | 40.755 | -73.995 | 79,622 | 0.79 | MANHATTAN | PETIT LARCENY | 16,131 |
| 3 | 40.835 | -73.915 | 75,567 | 0.75 | BRONX | ASSAULT 3 & RELATED OFFENSES | 9,131 |
| 4 | 40.855 | -73.905 | 75,456 | 0.75 | BRONX | ASSAULT 3 & RELATED OFFENSES | 10,005 |
| 5 | 40.795 | -73.945 | 75,271 | 0.75 | MANHATTAN | HARRASSMENT 2 | 10,840 |
| 6 | 40.865 | -73.895 | 72,682 | 0.72 | BRONX | PETIT LARCENY | 13,910 |
| 7 | 40.745 | -73.985 | 66,913 | 0.67 | MANHATTAN | PETIT LARCENY | 19,515 |
| 8 | 40.805 | -73.945 | 66,886 | 0.67 | MANHATTAN | PETIT LARCENY | 14,986 |
| 9 | 40.725 | -73.995 | 66,064 | 0.66 | MANHATTAN | PETIT LARCENY | 25,842 |
| 10 | 40.765 | -73.985 | 65,870 | 0.66 | MANHATTAN | PETIT LARCENY | 15,041 |
| 11 | 40.815 | -73.915 | 63,816 | 0.64 | BRONX | PETIT LARCENY | 11,297 |
| 12 | 40.735 | -73.995 | 63,654 | 0.63 | MANHATTAN | PETIT LARCENY | 23,474 |
| 13 | 40.825 | -73.945 | 61,950 | 0.62 | MANHATTAN | HARRASSMENT 2 | 9,043 |
| 14 | 40.735 | -73.985 | 61,840 | 0.62 | MANHATTAN | PETIT LARCENY | 16,644 |
| 15 | 40.745 | -73.995 | 61,449 | 0.61 | MANHATTAN | PETIT LARCENY | 16,643 |

## Ethics Constraint

Victim and suspect demographic fields are intentionally excluded from this dashboard summary. They are not used as grouping fields, ranking features, heatmap dimensions, or future model features in this Phase 3 work.

Excluded fields:

- `SUSP_AGE_GROUP`
- `SUSP_RACE`
- `SUSP_SEX`
- `VIC_AGE_GROUP`
- `VIC_RACE`
- `VIC_SEX`

## Limitations

- These findings are descriptive and should be interpreted with source-data coverage, reporting practices, and cleaned-date filters in mind.
- The latest weekly bucket can be a partial week when the source max date falls before the end of that calendar week.
- Heatmap cells are an initial dashboard-ready spatial aggregate, not a formal hotspot or anomaly layer.

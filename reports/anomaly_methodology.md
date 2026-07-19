# NYPD Complaint Data Historic - Anomaly Methodology

Generated at UTC: `2026-07-07T12:43:01.375556+00:00`

## Scope

The anomaly builder identifies unusually high aggregate weekly complaint counts
for borough, precinct, offense type, and law category segments. Its output is
integrated into the dashboard's aggregate list/detail experience, while the
builder remains responsible only for retrospective anomaly analysis. It does
not create an API, patrol recommendation, or person-level score.

## Inputs and Outputs

- Input weekly_area: `data/processed/crime_weekly_area.parquet`
- Input ml_predictions: `data/processed/ml_predictions.parquet`
- Input ml_model_manifest: `models/weekly_forecast/model_manifest.json`
- Output anomalies: `data/processed/anomalies.parquet`
- Output metrics: `data/processed/anomaly_metrics.json`
- Output report: `reports/anomaly_methodology.md`

## Methodology

The script builds a zero-filled weekly panel after each segment first appears. For every segment-week it computes trailing 8-, 13-, and 26-week statistics using only weeks before the target week.

Scoring formulas:

- `expected_historical_count = mean(prior 13 weekly counts)`.
- `expected_ml_count = predicted_crime_count` from the reviewed ML backtest when
  a safe prediction exists.
- `expected_count = expected_ml_count` when available, otherwise `expected_historical_count`.
- `residual_count = actual_crime_count - expected_count`.
- `historical_residual_count = actual_crime_count - expected_historical_count`.
- `pct_change_vs_trailing_8_week_mean = (actual - trailing_8_mean) / trailing_8_mean * 100`.
- `rolling_z_score = (actual - trailing_13_mean) / trailing_13_std`.
- `robust_z_score = (actual - rolling_26_median) / (1.4826 * rolling_26_mad)`.
- `ml_residual_scaled_score = (actual - expected_ml_count) / sqrt(expected_ml_count + 1)`.

A segment-week can be flagged only when it has enough prior history, enough recent volume, a meaningful positive residual, and either historical or ML evidence. The default volume gate requires at least 13 prior complaints over the 13-week baseline window, at least 4 actual complaints in the target week, and at least 3 complaints above expected.

## Leakage Controls

- Historical rolling windows end at one week before the scored week.
- No random splits are used.
- Missing segment-weeks are zero-filled only after the segment first appears.
- The latest source week is excluded from scoring by default because it may be partial.
- ML residuals use only reviewed backtest predictions with actual counts;
  next-week forecast rows are excluded.
- ML prediction use status: `used`.

## Evaluation Summary

| min_week_start | max_week_start | scoring_end_week | latest_week_excluded_from_scoring | min_evaluated_week_start | max_evaluated_week_start | segment_count | candidate_segment_weeks | evaluated_segment_weeks | volume_eligible_segment_weeks | anomaly_rows |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2005-12-26 | 2025-12-29 | 2025-12-22 | 1 | 2006-03-27 | 2025-12-22 | 8,466 | 6,884,684 | 6,774,787 | 730,926 | 89,362 |

## Anomaly Counts by Severity

| anomaly_severity | anomaly_count | actual_event_count | avg_anomaly_score | max_anomaly_score |
| --- | --- | --- | --- | --- |
| low | 53,301 | 659,563 | 1.8895 | 5.3111 |
| medium | 25,683 | 326,717 | 2.6067 | 7.7968 |
| high | 7,301 | 125,911 | 3.3507 | 7.9768 |
| critical | 3,077 | 73,474 | 4.8943 | 53.603 |

## Top Recent Anomalies

| week_start | borough | precinct | offense_type | law_category | actual_crime_count | expected_count | expected_count_source | residual_count | pct_change_vs_trailing_8_week_mean | rolling_z_score | robust_z_score | anomaly_severity | anomaly_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-12-22 | BRONX | 48 | SEX CRIMES | MISDEMEANOR | 10 | 2.525 | ml_prediction | 7.475 | 280.9524 | 5.0252 | 5.3959 | high | 4.6237 |
| 2025-12-22 | MANHATTAN | 30 | CRIMINAL MISCHIEF & RELATED OF | FELONY | 7 | 1.5125 | ml_prediction | 5.4875 | 330.7692 | 4.2147 | 4.0469 | medium | 3.9207 |
| 2025-12-22 | QUEENS | 115 | GRAND LARCENY OF MOTOR VEHICLE | FELONY | 13 | 5.325 | ml_prediction | 7.675 | 153.6585 | 3.0877 | 5.3959 | high | 3.3038 |
| 2025-12-22 | BROOKLYN | 76 | PETIT LARCENY | MISDEMEANOR | 15 | 5.2625 | ml_prediction | 9.7375 | 192.6829 | 3.8942 | 2.698 | high | 3.2579 |
| 2025-12-22 | QUEENS | 109 | SEX CRIMES | MISDEMEANOR | 10 | 2.9125 | ml_prediction | 7.0875 | 280.9524 | 2.7188 | 4.7214 | high | 3.252 |
| 2025-12-22 | BRONX | 44 | SEX CRIMES | MISDEMEANOR | 8 | 3.3625 | ml_prediction | 4.6375 | 146.1538 | 3.2577 | 2.698 | medium | 2.6581 |
| 2025-12-22 | QUEENS | 101 | SEX CRIMES | MISDEMEANOR | 7 | 2.475 | ml_prediction | 4.525 | 166.6667 | 2.7569 | 3.3725 | medium | 2.6524 |
| 2025-12-22 | BRONX | 41 | DANGEROUS DRUGS | MISDEMEANOR | 5 | 1.6 | ml_prediction | 3.4 | 185.7143 | 3.3571 | 2.0235 | low | 2.6506 |
| 2025-12-22 | STATEN ISLAND | 121 | SEX CRIMES | MISDEMEANOR | 4 | 0.8125 | ml_prediction | 3.1875 | 300 | 2.846 | 2.0235 | low | 2.5319 |
| 2025-12-22 | QUEENS | 108 | SEX CRIMES | MISDEMEANOR | 5 | 1.425 | ml_prediction | 3.575 | 263.6364 | 2.8706 | 2.0235 | low | 2.4871 |
| 2025-12-22 | QUEENS | 116 | BURGLARY | FELONY | 4 | 0.95 | ml_prediction | 3.05 | 255.5556 | 2.5495 | 2.0235 | low | 2.3627 |
| 2025-12-22 | QUEENS | 106 | BURGLARY | FELONY | 5 | 1.7625 | ml_prediction | 3.2375 | 207.6923 | 2.7035 | 2.0235 | low | 2.3106 |
| 2025-12-22 | MANHATTAN | 9 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 7 | 2.575 | ml_prediction | 4.425 | 180 | 2.5614 | 2.0235 | medium | 2.2806 |
| 2025-12-22 | BROOKLYN | 60 | MISCELLANEOUS PENAL LAW | FELONY | 13 | 6.05 | ml_prediction | 6.95 | 126.087 | 2.0921 | 3.1476 | medium | 2.238 |
| 2025-12-22 | BRONX | 45 | OFF. AGNST PUB ORD SENSBLTY & | MISDEMEANOR | 12 | 5.15 | ml_prediction | 6.85 | 174.2857 | 2.3239 | 1.7537 | medium | 2.2028 |
| 2025-12-22 | MANHATTAN | 30 | OFF. AGNST PUB ORD SENSBLTY & | MISDEMEANOR | 6 | 2.6375 | ml_prediction | 3.3625 | 118.1818 | 2.5399 | 2.0235 | low | 2.0984 |
| 2025-12-22 | QUEENS | 109 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 10 | 5.5625 | ml_prediction | 4.4375 | 77.7778 | 2.7488 | 1.349 | low | 1.9657 |
| 2025-12-22 | BROOKLYN | 60 | ROBBERY | FELONY | 6 | 2.25 | ml_prediction | 3.75 | 152.6316 | 2.3598 | 1.349 | low | 1.9499 |
| 2025-12-22 | MANHATTAN | 19 | MISCELLANEOUS PENAL LAW | FELONY | 4 | 0.9375 | ml_prediction | 3.0625 | 255.5556 | 1.5396 | 2.0235 | low | 1.8226 |
| 2025-12-22 | STATEN ISLAND | 123 | HARRASSMENT 2 | VIOLATION | 17 | 10.375 | ml_prediction | 6.625 | 49.4505 | 2.1459 | 1.8548 | low | 1.79 |
| 2025-12-22 | BRONX | 43 | BURGLARY | FELONY | 11 | 5.6 | ml_prediction | 5.4 | 100 | 1.8007 | 2.0235 | low | 1.7084 |
| 2025-12-22 | BRONX | 46 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 11 | 6.8375 | ml_prediction | 4.1625 | 60 | 2.0558 | 1.6862 | low | 1.6704 |
| 2025-12-22 | BROOKLYN | 83 | GRAND LARCENY OF MOTOR VEHICLE | FELONY | 5 | 1.8375 | ml_prediction | 3.1625 | 207.6923 | 1.6958 | 0.8993 | low | 1.5704 |
| 2025-12-22 | BROOKLYN | 75 | ASSAULT 3 & RELATED OFFENSES | MISDEMEANOR | 47 | 34.3375 | ml_prediction | 12.6625 | 38.2353 | 2.1368 | 0.6295 | low | 1.5513 |
| 2025-12-22 | QUEENS | 115 | DANGEROUS DRUGS | MISDEMEANOR | 5 | 1.6875 | ml_prediction | 3.3125 | 185.7143 | 1.75 | 0.6745 | low | 1.5241 |

## Top Overall Anomalies

| week_start | borough | precinct | offense_type | law_category | actual_crime_count | expected_count | expected_count_source | residual_count | pct_change_vs_trailing_8_week_mean | rolling_z_score | robust_z_score | anomaly_severity | anomaly_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2020-06-01 | BRONX | 46 | BURGLARY | FELONY | 118 | 4 | rolling_13_week_mean | 114 | 2,597.1429 | 80.6102 | 76.8919 | critical | 53.603 |
| 2015-12-28 | BROOKLYN | 61 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 129 | 7.1538 | rolling_13_week_mean | 121.8462 | 1,884.6154 | 51.8856 | 55.0834 | critical | 36.3152 |
| 2018-01-01 | MANHATTAN | 24 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 118 | 4.6154 | rolling_13_week_mean | 113.3846 | 3,396.2963 | 41.0714 | 38.1087 | critical | 28.0539 |
| 2018-12-31 | MANHATTAN | 24 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 104 | 5.2308 | rolling_13_week_mean | 98.7692 | 1,980 | 35.917 | 45.1909 | critical | 27.1508 |
| 2011-12-26 | MANHATTAN | 14 | DANGEROUS DRUGS | MISDEMEANOR | 87 | 3.3077 | rolling_13_week_mean | 83.6923 | 2,576.9231 | 28.4159 | 56.6572 | critical | 26.0686 |
| 2024-02-05 | BRONX | 46 | POSSESSION OF STOLEN PROPERTY | FELONY | 33 | 1 | rolling_13_week_mean | 32 | 6,500 | 33.3067 | 21.5837 | critical | 21.2548 |
| 2022-08-29 | MANHATTAN | 25 | GRAND LARCENY | FELONY | 91 | 12.0769 | rolling_13_week_mean | 78.9231 | 700 | 33.3229 | 21.4488 | critical | 21.2351 |
| 2016-12-26 | QUEENS | 104 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 78 | 8.6154 | rolling_13_week_mean | 69.3846 | 860 | 32.0108 | 22.9327 | critical | 20.9414 |
| 2021-11-15 | QUEENS | 115 | GRAND LARCENY | FELONY | 175 | 16.8462 | rolling_13_week_mean | 158.1538 | 815.0327 | 27.1942 | 31.0266 | critical | 20.3927 |
| 2021-11-22 | QUEENS | 109 | GRAND LARCENY | FELONY | 234 | 19 | rolling_13_week_mean | 215 | 994.7368 | 26.6517 | 29.4752 | critical | 19.8383 |
| 2020-06-01 | MANHATTAN | 14 | BURGLARY | FELONY | 71 | 5.5385 | rolling_13_week_mean | 65.4615 | 1,036 | 24.7108 | 29.9024 | critical | 19.0503 |
| 2015-12-28 | QUEENS | 112 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 62 | 4.8462 | rolling_13_week_mean | 57.1538 | 1,140 | 25.0465 | 26.0803 | critical | 18.437 |
| 2022-09-19 | QUEENS | 110 | GRAND LARCENY | FELONY | 91 | 18.2308 | rolling_13_week_mean | 72.7692 | 398.6301 | 25.6898 | 24.6189 | critical | 18.2821 |
| 2020-06-01 | BRONX | 52 | BURGLARY | FELONY | 37 | 2.3846 | rolling_13_week_mean | 34.6154 | 1,186.9565 | 24.9232 | 22.9327 | critical | 17.752 |
| 2021-12-27 | MANHATTAN | 23 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 52 | 6.2308 | rolling_13_week_mean | 45.7692 | 732 | 25.9927 | 20.4596 | critical | 17.7386 |
| 2016-12-26 | BROOKLYN | 61 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 87 | 7.3846 | rolling_13_week_mean | 79.6154 | 1,142.8571 | 22.9041 | 26.6424 | critical | 17.5853 |
| 2023-08-28 | MANHATTAN | 25 | GRAND LARCENY | FELONY | 83 | 11.8462 | rolling_13_week_mean | 71.1538 | 629.6703 | 23.6481 | 24.6189 | critical | 17.5154 |
| 2018-12-31 | BROOKLYN | 70 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 56 | 8.4615 | rolling_13_week_mean | 47.5385 | 611.1111 | 24.9405 | 21.3589 | critical | 17.445 |
| 2018-01-01 | QUEENS | 103 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 111 | 8.2308 | rolling_13_week_mean | 102.7692 | 1,918.1818 | 21.599 | 27.789 | critical | 17.2273 |
| 2020-05-25 | MANHATTAN | 6 | CRIMINAL MISCHIEF & RELATED OF | FELONY | 33 | 2.4615 | rolling_13_week_mean | 30.5385 | 1,452.9412 | 13.2333 | 42.4929 | critical | 16.4036 |
| 2023-05-22 | QUEENS | 105 | FORGERY | FELONY | 18 | 1.4615 | rolling_13_week_mean | 16.5385 | 1,340 | 22.1756 | 22.2582 | critical | 16.3807 |
| 2020-06-01 | MANHATTAN | 13 | BURGLARY | FELONY | 53 | 7.1538 | rolling_13_week_mean | 45.8462 | 657.1429 | 18.0689 | 31.0266 | critical | 16.2863 |
| 2014-12-29 | BROOKLYN | 61 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 138 | 10.9231 | rolling_13_week_mean | 127.0769 | 1,050 | 10.3311 | 44.1791 | critical | 15.4348 |
| 2009-12-28 | QUEENS | 104 | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 122 | 15.4615 | rolling_13_week_mean | 106.5385 | 693.4959 | 19.0821 | 23.832 | critical | 15.3033 |
| 2012-12-24 | MANHATTAN | 14 | DANGEROUS DRUGS | MISDEMEANOR | 106 | 10.6154 | rolling_13_week_mean | 95.3846 | 748 | 19.8203 | 21.8085 | critical | 15.2308 |

## Hardest or Most Volatile Borough-Offense Groups

These borough/offense groups have the largest average absolute historical residuals after the minimum-volume gate. Groups must have at least 52 evaluated segment-weeks and 100 actual complaints in this table. They are useful candidates for ongoing forecast-error review; they are not filter-specific guarantees or policing priorities.

| borough | offense_type | evaluated_segment_weeks | actual_event_count | anomaly_count | high_or_critical_anomaly_count | anomaly_rate_pct | avg_trailing_13_week_std | avg_abs_historical_residual | max_anomaly_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MANHATTAN | PETIT LARCENY | 21,648 | 548,507 | 1,556 | 257 | 7.1877 | 5.3298 | 4.9574 | 6.8919 |
| BRONX | PETIT LARCENY | 12,366 | 295,369 | 839 | 135 | 6.7847 | 5.2968 | 4.8913 | 7.1734 |
| STATEN ISLAND | HARRASSMENT 2 | 3,724 | 87,771 | 239 | 32 | 6.4178 | 5.0956 | 4.6404 | 7.0947 |
| QUEENS | PETIT LARCENY | 16,293 | 355,176 | 1,142 | 194 | 7.0091 | 5.007 | 4.5301 | 9.1456 |
| BRONX | HARRASSMENT 2 | 12,363 | 298,018 | 749 | 103 | 6.0584 | 5.0152 | 4.5276 | 4.3191 |
| BRONX | ASSAULT 3 & RELATED OFFENSES | 12,267 | 262,129 | 799 | 98 | 6.5134 | 4.8911 | 4.3814 | 5.0319 |
| BROOKLYN | PETIT LARCENY | 23,648 | 474,185 | 1,650 | 236 | 6.9773 | 4.7252 | 4.3245 | 9.6228 |
| STATEN ISLAND | PETIT LARCENY | 3,657 | 70,455 | 267 | 45 | 7.3011 | 4.7108 | 4.2659 | 12.6646 |
| BRONX | POSSESSION OF STOLEN PROPERTY | 67 | 385 | 34 | 7 | 50.7463 | 1.4801 | 4.2067 | 21.2548 |
| MANHATTAN | OTHER OFFENSES RELATED TO THEFT | 585 | 5,983 | 151 | 38 | 25.812 | 3.962 | 4.0647 | 12.298 |
| BRONX | OTHER OFFENSES RELATED TO THEFT | 658 | 7,180 | 123 | 27 | 18.693 | 4.3203 | 4.0422 | 8.8301 |
| BRONX | DANGEROUS DRUGS | 11,328 | 152,837 | 1,587 | 188 | 14.0095 | 4.0988 | 3.83 | 10.1149 |
| QUEENS | HARRASSMENT 2 | 16,347 | 285,231 | 1,105 | 134 | 6.7597 | 4.2272 | 3.8004 | 5.8361 |
| STATEN ISLAND | CRIMINAL MISCHIEF & RELATED OF | 4,315 | 51,898 | 603 | 111 | 13.9745 | 4.2335 | 3.7017 | 10.6509 |
| BROOKLYN | HARRASSMENT 2 | 23,316 | 399,386 | 1,566 | 206 | 6.7164 | 4.1187 | 3.6856 | 5.2388 |
| MANHATTAN | ADMINISTRATIVE CODE | 56 | 372 | 23 | 6 | 41.0714 | 2.8961 | 3.6827 | 10.826 |
| MANHATTAN | GRAND LARCENY | 20,205 | 319,396 | 1,665 | 208 | 8.2405 | 3.9571 | 3.5482 | 21.2351 |
| QUEENS | OTHER OFFENSES RELATED TO THEFT | 231 | 1,989 | 59 | 12 | 25.5411 | 3.2596 | 3.4882 | 7.0379 |
| BROOKLYN | OTHER OFFENSES RELATED TO THEFT | 824 | 7,016 | 208 | 37 | 25.2427 | 3.3661 | 3.435 | 8.0402 |
| QUEENS | ASSAULT 3 & RELATED OFFENSES | 15,424 | 214,576 | 1,155 | 124 | 7.4883 | 3.8618 | 3.4257 | 8.0464 |
| BRONX | CRIMINAL MISCHIEF & RELATED OF | 15,405 | 187,013 | 1,557 | 233 | 10.1071 | 3.8641 | 3.4248 | 12.4076 |
| BROOKLYN | ASSAULT 3 & RELATED OFFENSES | 22,282 | 310,784 | 1,747 | 221 | 7.8404 | 3.7969 | 3.3318 | 5.8691 |
| QUEENS | ADMINISTRATIVE CODE | 57 | 321 | 24 | 5 | 42.1053 | 1.895 | 3.3279 | 5.6827 |
| BROOKLYN | POSSESSION OF STOLEN PROPERTY | 104 | 512 | 33 | 9 | 31.7308 | 1.5039 | 3.3084 | 5.9466 |
| STATEN ISLAND | OTHER OFFENSES RELATED TO THEFT | 61 | 498 | 13 | 3 | 21.3115 | 3.366 | 3.3077 | 5.1896 |

## Limitations and dashboard context

Anomalies are integrated with a complete list/detail experience and display
expected count, residual, prior volume, lifecycle, and limitation context. See
the [dashboard README](../dashboard/README.md) and
[final project report](final_project_report.md) for the browser contract and
responsible-use boundary.

- The layer identifies unusually high aggregate counts; it does not explain causality.
- The latest source week may be partial depending on the upstream data extract.
- Reported complaint counts can be affected by reporting delay, policy changes, classification changes, and data revisions.
- The reviewed thresholds are conservative defaults and should be monitored for
  signal volume by borough and offense type when the analytical snapshot changes.
- No uncertainty intervals, holidays, special events, spatial spillover terms, or reporting-lag corrections are included yet.
- The dashboard shows expected count, residual, prior volume gate, and model
  lifecycle context with anomaly results.

## Ethics Constraint

Suspect and victim demographic fields are excluded. Outputs are aggregate trend intelligence only and must not be interpreted as person-level predictions, automated enforcement actions, or patrol recommendations.

Excluded fields:

- `SUSP_AGE_GROUP`
- `SUSP_RACE`
- `SUSP_SEX`
- `VIC_AGE_GROUP`
- `VIC_RACE`
- `VIC_SEX`

# NYPD Complaint Data Historic - Baseline Forecast Model

Generated at UTC: `2026-07-05T12:13:45.983331+00:00`

## Scope

This Phase 4 baseline reads `crime_weekly_area.parquet` and predicts the next weekly `crime_count` for each borough, precinct, offense type, and law category segment. It implements explainable historical baselines only; no Phase 5 machine-learning model is trained.

## Inputs and Outputs

- Input weekly_area: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/crime_weekly_area.parquet`
- Output model_manifest: `/Users/mskayacioglu/Documents/projects/bir-nyc/models/baseline_forecast/model_manifest.json`
- Output predictions: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/baseline_predictions.parquet`
- Output metrics: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/baseline_metrics.json`
- Output report: `/Users/mskayacioglu/Documents/projects/bir-nyc/reports/baseline_model_report.md`

## Forecast Setup

| min_week_start | max_week_start | backtest_start_week | backtest_end_week | next_week_forecast_week | segment_count | backtest_rows | next_week_forecast_rows |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2005-12-26 | 2025-12-29 | 2024-12-30 | 2025-12-22 | 2026-01-05 | 8,466 | 437,144 | 8,466 |

Missing weekly rows are zero-filled after a segment first appears. All baseline windows exclude the target week, so backtest predictions use historical weeks only.

## Baseline Definitions

- `previous_week`: prior week's count.
- `trailing_4_week_mean`: mean of the prior 4 weekly counts, emitted only when all 4 prior weeks exist in the zero-filled segment panel.
- `trailing_8_week_mean`: mean of the prior 8 weekly counts, emitted only when all 8 prior weeks exist in the zero-filled segment panel.
- `previous_year_same_week`: count from 52 weeks prior, emitted only when that history exists.

## Overall Backtest Metrics

| baseline_method | prediction_count | total_backtest_rows | prediction_coverage_pct | actual_event_count | mae | rmse | weighted_mae |
| --- | --- | --- | --- | --- | --- | --- | --- |
| previous_week | 437,007 | 437,144 | 99.97 | 567,162 | 0.601 | 1.7764 | 4.5649 |
| previous_year_same_week | 426,818 | 437,144 | 97.64 | 564,841 | 0.6796 | 2.0772 | 5.2965 |
| trailing_4_week_mean | 436,570 | 437,144 | 99.87 | 567,121 | 0.5058 | 1.4537 | 3.7967 |
| trailing_8_week_mean | 435,942 | 437,144 | 99.73 | 566,983 | 0.4929 | 1.4128 | 3.7023 |

Weighted MAE uses actual `crime_count` as the row weight over rows where the baseline produced a prediction.

## Top-K High-Volume Capture

| baseline_method | top_k_fraction | evaluated_weeks | avg_weekly_top_k_rows | actual_top_k_event_count | captured_top_k_event_count | top_k_capture_rate |
| --- | --- | --- | --- | --- | --- | --- |
| previous_week | 0.1 | 52 | 840.81 | 485,500 | 436,271 | 0.8986 |
| previous_year_same_week | 0.1 | 52 | 821.27 | 481,425 | 424,023 | 0.8808 |
| trailing_4_week_mean | 0.1 | 52 | 839.94 | 485,353 | 447,964 | 0.923 |
| trailing_8_week_mean | 0.1 | 52 | 838.73 | 485,088 | 449,728 | 0.9271 |

Top-K capture measures how much actual crime volume in the true highest-volume segment-weeks is captured by the baseline's predicted highest-volume segment-weeks for the same week.

## Best Baseline

`trailing_8_week_mean` has the lowest overall MAE (0.4929) with RMSE 1.4128 and 99.73% prediction coverage.

## Borough Metrics for Best Baseline

| baseline_method | borough | prediction_count | prediction_coverage_pct | actual_event_count | mae | rmse | weighted_mae |
| --- | --- | --- | --- | --- | --- | --- | --- |
| trailing_8_week_mean | BRONX | 63,696 | 99.84 | 127,826 | 0.6593 | 1.7633 | 4.045 |
| trailing_8_week_mean | BROOKLYN | 107,022 | 99.67 | 158,964 | 0.5829 | 1.4708 | 3.4129 |
| trailing_8_week_mean | MANHATTAN | 99,542 | 99.75 | 133,943 | 0.5364 | 1.4961 | 3.9531 |
| trailing_8_week_mean | QUEENS | 74,665 | 99.45 | 121,333 | 0.6224 | 1.5596 | 3.5474 |
| trailing_8_week_mean | STATEN ISLAND | 17,873 | 99.71 | 23,618 | 0.5337 | 1.3878 | 3.2953 |
| trailing_8_week_mean | UNKNOWN | 73,144 | 99.95 | 1,299 | 0.0151 | 0.1551 | 1.4131 |

## Hardest Offense Types for Best Baseline

| baseline_method | offense_type | prediction_count | actual_event_count | mae | rmse | weighted_mae |
| --- | --- | --- | --- | --- | --- | --- |
| trailing_8_week_mean | OTHER OFFENSES RELATED TO THEFT | 4,546 | 16,296 | 1.7365 | 2.9552 | 4.1642 |
| trailing_8_week_mean | PETIT LARCENY | 15,082 | 103,219 | 1.4301 | 3.5091 | 5.8685 |
| trailing_8_week_mean | VEHICLE AND TRAFFIC LAWS | 7,591 | 25,322 | 1.2364 | 2.2782 | 3.1231 |
| trailing_8_week_mean | HARRASSMENT 2 | 13,941 | 84,904 | 1.2191 | 2.9233 | 4.7795 |
| trailing_8_week_mean | ASSAULT 3 & RELATED OFFENSES | 13,170 | 60,255 | 1.111 | 2.6092 | 4.2577 |
| trailing_8_week_mean | FELONY ASSAULT | 9,404 | 29,439 | 1.0438 | 2.1557 | 3.1854 |
| trailing_8_week_mean | GRAND LARCENY | 13,533 | 45,587 | 0.9131 | 2.1772 | 3.6019 |
| trailing_8_week_mean | GRAND LARCENY OF MOTOR VEHICLE | 7,870 | 13,365 | 0.7974 | 1.5737 | 2.4379 |
| trailing_8_week_mean | CRIMINAL MISCHIEF & RELATED OF | 19,663 | 35,502 | 0.7653 | 1.5595 | 2.2728 |
| trailing_8_week_mean | BURGLARY | 8,372 | 12,681 | 0.7581 | 1.4354 | 2.019 |
| trailing_8_week_mean | DANGEROUS DRUGS | 15,285 | 18,605 | 0.6837 | 1.4474 | 2.6325 |
| trailing_8_week_mean | OFFENSES AGAINST PUBLIC ADMINI | 7,938 | 9,542 | 0.6742 | 1.3274 | 2.0836 |
| trailing_8_week_mean | ROBBERY | 9,855 | 15,026 | 0.6636 | 1.3755 | 2.1308 |
| trailing_8_week_mean | FORGERY | 6,749 | 6,452 | 0.6582 | 1.3864 | 2.5635 |
| trailing_8_week_mean | OFF. AGNST PUB ORD SENSBLTY & | 11,513 | 17,239 | 0.6421 | 1.4134 | 2.2528 |

## Hardest Borough/Offense Segments

Rows are filtered to segments with at least 50 actual backtest complaints.

| borough | offense_type | prediction_count | actual_event_count | mae | rmse |
| --- | --- | --- | --- | --- | --- |
| BRONX | OTHER OFFENSES RELATED TO THEFT | 624 | 4,428 | 2.7774 | 4.3931 |
| MANHATTAN | PETIT LARCENY | 2,756 | 32,434 | 2.2687 | 4.8261 |
| QUEENS | PETIT LARCENY | 2,080 | 23,002 | 2.2361 | 4.5621 |
| STATEN ISLAND | HARRASSMENT 2 | 468 | 4,639 | 2.1402 | 4.0242 |
| MANHATTAN | OTHER OFFENSES RELATED TO THEFT | 1,144 | 4,618 | 2.1042 | 3.2719 |
| BROOKLYN | OTHER OFFENSES RELATED TO THEFT | 1,244 | 5,226 | 2.0711 | 3.0187 |
| QUEENS | ASSAULT 3 & RELATED OFFENSES | 1,664 | 13,095 | 2.0189 | 3.5478 |
| QUEENS | VEHICLE AND TRAFFIC LAWS | 1,141 | 6,025 | 1.9142 | 2.7767 |
| BRONX | FELONY ASSAULT | 1,248 | 8,861 | 1.8553 | 3.4084 |
| BROOKLYN | FELONY ASSAULT | 1,593 | 8,362 | 1.7566 | 2.7809 |
| BRONX | HARRASSMENT 2 | 1,924 | 19,952 | 1.755 | 3.891 |
| BRONX | VEHICLE AND TRAFFIC LAWS | 1,092 | 6,217 | 1.7461 | 3.0425 |
| BROOKLYN | VEHICLE AND TRAFFIC LAWS | 1,669 | 7,973 | 1.729 | 2.6953 |
| QUEENS | GRAND LARCENY OF MOTOR VEHICLE | 1,090 | 4,450 | 1.6864 | 2.5215 |
| BROOKLYN | HARRASSMENT 2 | 2,969 | 25,219 | 1.686 | 3.4354 |

## Hardest Precinct/Offense Segments

| borough | precinct | offense_type | prediction_count | actual_event_count | mae | rmse |
| --- | --- | --- | --- | --- | --- | --- |
| MANHATTAN | 13 | PETIT LARCENY | 52 | 2,797 | 9.0192 | 12.5133 |
| BRONX | 40 | OTHER OFFENSES RELATED TO THEFT | 52 | 1,395 | 8.6995 | 11.0103 |
| MANHATTAN | 1 | PETIT LARCENY | 52 | 3,394 | 8.613 | 10.9149 |
| MANHATTAN | 14 | PETIT LARCENY | 52 | 4,088 | 8.5673 | 11.604 |
| MANHATTAN | 19 | PETIT LARCENY | 52 | 2,601 | 8.5529 | 10.9656 |
| BROOKLYN | 75 | HARRASSMENT 2 | 52 | 3,061 | 8.3846 | 10.0968 |
| MANHATTAN | 14 | OTHER OFFENSES RELATED TO THEFT | 52 | 1,336 | 7.9111 | 9.3804 |
| BROOKLYN | 75 | PETIT LARCENY | 52 | 2,543 | 7.7644 | 9.9221 |
| QUEENS | 109 | PETIT LARCENY | 52 | 2,564 | 7.5264 | 9.4869 |
| BRONX | 49 | PETIT LARCENY | 52 | 1,735 | 7.4591 | 9.5583 |
| QUEENS | 114 | PETIT LARCENY | 52 | 2,329 | 7.137 | 9.2488 |
| MANHATTAN | 9 | PETIT LARCENY | 52 | 1,472 | 7.137 | 8.4879 |
| QUEENS | 110 | PETIT LARCENY | 52 | 2,322 | 7.0144 | 9.0074 |
| BROOKLYN | 67 | HARRASSMENT 2 | 52 | 2,596 | 7.0096 | 8.2287 |
| BROOKLYN | 75 | ASSAULT 3 & RELATED OFFENSES | 52 | 2,023 | 6.9423 | 8.5748 |

## Interpretation

- Best overall baseline: `trailing_8_week_mean` by MAE. Lower RMSE and weighted MAE should also be reviewed before treating this as the operational benchmark.
- The hardest segments are high-volume borough/offense and precinct/offense series with volatile week-to-week counts; these are the first places Phase 5 should test explicit trend, seasonality, holiday, and anomaly features.
- `previous_year_same_week` has lower coverage for newer or sparse segments because it requires at least 52 prior zero-filled weekly observations.

## Limitations Before Phase 5 ML

- Missing weeks are inferred as zero after first observation because the Phase 2 aggregate stores observed event groups, not a complete zero-filled panel.
- The latest source week is excluded from backtesting by default because it may be partial; the next-week forecast still uses it as the latest available observation.
- Baselines do not model holidays, reporting delays, structural breaks, spatial spillover, or long-run trend shifts.
- Forecast intervals are not produced in Phase 4; Phase 5 should add uncertainty estimates before dashboard use.

## Ethics Constraint

Suspect and victim demographic fields are excluded. These outputs are aggregate trend forecasts and must not be interpreted as person-level predictions or automatic enforcement recommendations.

Excluded fields:

- `SUSP_AGE_GROUP`
- `SUSP_RACE`
- `SUSP_SEX`
- `VIC_AGE_GROUP`
- `VIC_RACE`
- `VIC_SEX`

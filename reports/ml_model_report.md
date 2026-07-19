# NYPD Complaint Data Historic - ML Forecast Model

Generated at UTC: `2026-07-05T12:40:05.068774+00:00`

## Scope

The model builder reads `crime_weekly_area.parquet` and forecasts next-week
`crime_count` for each borough, precinct, offense type, and law category
segment. Its output is integrated into the browser-safe forecast contracts, but
the builder itself remains responsible only for aggregate model training,
historical evaluation, and fixed-horizon prediction. It does not produce an API
or any enforcement recommendation.

## Inputs and Outputs

- Input weekly_area: `data/processed/crime_weekly_area.parquet`
- Input baseline_manifest: `models/baseline_forecast/model_manifest.json`
- Output model_manifest: `models/weekly_forecast/model_manifest.json`
- Output predictions: `data/processed/ml_predictions.parquet`
- Output metrics: `data/processed/ml_metrics.json`
- Output report: `reports/ml_model_report.md`

## Forecast Setup

| min_week_start | max_week_start | validation_start_week | validation_end_week | backtest_start_week | backtest_end_week | next_week_forecast_week | segment_count | backtest_rows |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2005-12-26 | 2025-12-29 | 2024-01-01 | 2024-12-23 | 2024-12-30 | 2025-12-22 | 2026-01-05 | 8,466 | 437,144 |

The baseline backtest window is reused. All lag and rolling features are
computed with windows ending one row before the target week.

## Model

`duckdb_lag_ensemble_regressor` is a deterministic lag-ensemble regressor selected by validation_rmse. It uses the pinned DuckDB dependency and the Python standard library; scikit-learn is not a project dependency.

Formula:

`max(0, shrinkage * (trailing_8_week_mean + alpha * (trailing_4_week_mean - trailing_8_week_mean) + beta * (lag_1_week_count - trailing_4_week_mean) + gamma * (lag_52_week_count - trailing_8_week_mean)))`

Selected parameters:

| alpha | beta | gamma | shrinkage | validation_prediction_count | validation_actual_event_count | validation_mae | validation_rmse | validation_weighted_mae |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.25 | 0.1 | 0.05 | 1 | 426,818 | 571,385 | 0.4978 | 1.4279 | 3.7957 |

Validation metrics for the selected parameters:

| validation_prediction_count | validation_actual_event_count | validation_mae | validation_rmse | validation_weighted_mae |
| --- | --- | --- | --- | --- |
| 426,818 | 571,385 | 0.4978 | 1.4279 | 3.7957 |

## Overall Backtest Metrics

| prediction_count | total_backtest_rows | prediction_coverage_pct | actual_event_count | mae | rmse | weighted_mae |
| --- | --- | --- | --- | --- | --- | --- |
| 437,144 | 437,144 | 100 | 567,306 | 0.4894 | 1.3943 | 3.6555 |

## Comparison with the selected baseline

| model | prediction_count | prediction_coverage_pct | mae | rmse | weighted_mae |
| --- | --- | --- | --- | --- | --- |
| `trailing_8_week_mean` | 435,942 | 99.73 | 0.4929 | 1.4128 | 3.7023 |
| `duckdb_lag_ensemble_regressor` | 437,144 | 100 | 0.4894 | 1.3943 | 3.6555 |
| Delta ML - baseline |  |  | -0.0035 | -0.0185 | -0.0468 |

The ML model recorded lower MAE, RMSE, and weighted MAE than the selected
baseline in the manifest-level comparison.
The comparison uses different prediction coverage—435,942 baseline rows versus 437,144 ML rows. It is not a matched-row, like-for-like gain; the metric deltas are descriptive.

## Borough Metrics

| borough | prediction_count | prediction_coverage_pct | actual_event_count | mae | rmse | weighted_mae |
| --- | --- | --- | --- | --- | --- | --- |
| BRONX | 63,801 | 100 | 127,839 | 0.6544 | 1.7429 | 4.0118 |
| BROOKLYN | 107,374 | 100 | 159,018 | 0.578 | 1.4517 | 3.3751 |
| MANHATTAN | 99,788 | 100 | 133,975 | 0.5316 | 1.4678 | 3.8706 |
| QUEENS | 75,079 | 100 | 121,546 | 0.6187 | 1.5455 | 3.5118 |
| STATEN ISLAND | 17,925 | 100 | 23,625 | 0.5299 | 1.3707 | 3.2585 |
| UNKNOWN | 73,177 | 100 | 1,303 | 0.0153 | 0.155 | 1.4249 |

## Hardest Offense Types

| offense_type | prediction_count | actual_event_count | mae | rmse | weighted_mae |
| --- | --- | --- | --- | --- | --- |
| OTHER OFFENSES RELATED TO THEFT | 4,580 | 16,301 | 1.6768 | 2.8524 | 4.0515 |
| PETIT LARCENY | 15,105 | 103,222 | 1.3998 | 3.4237 | 5.7255 |
| VEHICLE AND TRAFFIC LAWS | 7,614 | 25,381 | 1.2223 | 2.252 | 3.0987 |
| HARRASSMENT 2 | 13,949 | 84,905 | 1.2145 | 2.9108 | 4.7622 |
| ASSAULT 3 & RELATED OFFENSES | 13,191 | 60,259 | 1.1043 | 2.587 | 4.2258 |
| FELONY ASSAULT | 9,428 | 29,443 | 1.0446 | 2.1448 | 3.1772 |
| GRAND LARCENY | 13,592 | 45,594 | 0.8991 | 2.1413 | 3.5451 |
| GRAND LARCENY OF MOTOR VEHICLE | 7,880 | 13,374 | 0.7957 | 1.5667 | 2.4228 |
| CRIMINAL MISCHIEF & RELATED OF | 19,696 | 35,509 | 0.7624 | 1.5536 | 2.2623 |
| BURGLARY | 8,372 | 12,681 | 0.7526 | 1.4256 | 2.0049 |
| DANGEROUS DRUGS | 15,316 | 18,614 | 0.6765 | 1.4213 | 2.6107 |
| OFFENSES AGAINST PUBLIC ADMINI | 7,964 | 9,559 | 0.6733 | 1.3217 | 2.0834 |
| ROBBERY | 9,864 | 15,027 | 0.6612 | 1.3686 | 2.1115 |
| FORGERY | 6,757 | 6,453 | 0.6494 | 1.3518 | 2.4935 |
| OFF. AGNST PUB ORD SENSBLTY & | 11,525 | 17,240 | 0.6426 | 1.411 | 2.2549 |

## Hardest Borough/Offense Segments

Rows are filtered to segments with at least 50 actual backtest complaints.

| borough | offense_type | prediction_count | actual_event_count | mae | rmse | weighted_mae |
| --- | --- | --- | --- | --- | --- | --- |
| BRONX | OTHER OFFENSES RELATED TO THEFT | 624 | 4,428 | 2.6983 | 4.2298 | 4.845 |
| QUEENS | PETIT LARCENY | 2,080 | 23,002 | 2.2023 | 4.4982 | 5.9521 |
| MANHATTAN | PETIT LARCENY | 2,756 | 32,434 | 2.1958 | 4.6441 | 6.5804 |
| STATEN ISLAND | HARRASSMENT 2 | 468 | 4,639 | 2.0798 | 3.9419 | 4.9923 |
| MANHATTAN | OTHER OFFENSES RELATED TO THEFT | 1,144 | 4,618 | 2.0569 | 3.2174 | 4.4785 |
| QUEENS | ASSAULT 3 & RELATED OFFENSES | 1,665 | 13,096 | 2.0256 | 3.5434 | 4.2554 |
| BROOKLYN | OTHER OFFENSES RELATED TO THEFT | 1,258 | 5,228 | 1.9807 | 2.8849 | 3.4195 |
| QUEENS | VEHICLE AND TRAFFIC LAWS | 1,144 | 6,082 | 1.8923 | 2.7541 | 2.8552 |
| BRONX | FELONY ASSAULT | 1,248 | 8,861 | 1.8489 | 3.3645 | 4.1215 |
| BRONX | HARRASSMENT 2 | 1,924 | 19,952 | 1.7556 | 3.8985 | 5.6661 |
| BROOKLYN | FELONY ASSAULT | 1,601 | 8,364 | 1.7538 | 2.7673 | 3.1067 |
| BRONX | VEHICLE AND TRAFFIC LAWS | 1,092 | 6,217 | 1.7226 | 3.008 | 3.684 |
| QUEENS | GRAND LARCENY OF MOTOR VEHICLE | 1,092 | 4,458 | 1.6888 | 2.5211 | 2.7477 |
| BROOKLYN | VEHICLE AND TRAFFIC LAWS | 1,685 | 7,974 | 1.6866 | 2.6313 | 3.0202 |
| BROOKLYN | HARRASSMENT 2 | 2,977 | 25,220 | 1.684 | 3.4232 | 4.9578 |

## Hardest Precinct/Offense Segments

| borough | precinct | offense_type | prediction_count | actual_event_count | mae | rmse | weighted_mae |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MANHATTAN | 13 | PETIT LARCENY | 52 | 2,797 | 8.7123 | 11.882 | 8.9156 |
| MANHATTAN | 19 | PETIT LARCENY | 52 | 2,601 | 8.5512 | 10.7506 | 8.3969 |
| BROOKLYN | 75 | HARRASSMENT 2 | 52 | 3,061 | 8.2392 | 9.7505 | 8.3471 |
| BRONX | 40 | OTHER OFFENSES RELATED TO THEFT | 52 | 1,395 | 8.1517 | 10.4737 | 8.5202 |
| MANHATTAN | 14 | PETIT LARCENY | 52 | 4,088 | 8.1495 | 10.7747 | 8.2848 |
| MANHATTAN | 1 | PETIT LARCENY | 52 | 3,394 | 8.1375 | 10.4171 | 8.2147 |
| MANHATTAN | 14 | OTHER OFFENSES RELATED TO THEFT | 52 | 1,336 | 7.5791 | 9.2176 | 7.8107 |
| BROOKLYN | 75 | PETIT LARCENY | 52 | 2,543 | 7.5103 | 9.7119 | 7.8346 |
| QUEENS | 109 | PETIT LARCENY | 52 | 2,564 | 7.3536 | 9.3014 | 7.0377 |
| QUEENS | 110 | PETIT LARCENY | 52 | 2,322 | 7.1382 | 8.9435 | 7.3535 |
| BRONX | 49 | PETIT LARCENY | 52 | 1,735 | 7.0603 | 9.2882 | 8.2509 |
| QUEENS | 114 | PETIT LARCENY | 52 | 2,329 | 7.0447 | 9.0618 | 7.2134 |
| BROOKLYN | 67 | HARRASSMENT 2 | 52 | 2,596 | 6.8882 | 8.1853 | 6.9451 |
| MANHATTAN | 18 | PETIT LARCENY | 52 | 2,371 | 6.8651 | 8.4721 | 7.0549 |
| BRONX | 40 | HARRASSMENT 2 | 52 | 2,215 | 6.7784 | 8.3877 | 6.8936 |

## Top-K High-Volume Capture

| top_k_fraction | evaluated_weeks | avg_weekly_top_k_rows | actual_top_k_event_count | captured_top_k_event_count | top_k_capture_rate |
| --- | --- | --- | --- | --- | --- |
| 0.1 | 52 | 841.08 | 485,544 | 450,565 | 0.928 |

## Interpretation

- Baseline comparison: The ML model recorded lower MAE, RMSE, and weighted MAE
  than the selected baseline in the manifest-level comparison.
- Coverage qualification: The comparison uses different prediction coverage—435,942 baseline rows versus 437,144 ML rows. It is not a matched-row, like-for-like gain; the metric deltas are descriptive.
- Hardest segments: `BRONX / OTHER OFFENSES RELATED TO THEFT` is among the highest-error borough/offense groups after filtering for meaningful volume; these errors are concentrated in high-volume, volatile offense categories.
- Important features and limitations: the strongest signal is short-term history from the prior 4 and 8 weeks, adjusted by last-week and 52-week references. The model does not yet include holidays, reporting-delay corrections, exogenous events, spatial spillover, or uncertainty intervals.
- Lifecycle limitations: no prediction interval, formal drift monitor, model-age
  threshold, or general retraining cadence is established. The fixed
  historical/demo dashboard is not operational guidance; it provides point
  estimates and does not invent any of those capabilities or policies.

## Ethics Constraint

Suspect and victim demographic fields are excluded. Outputs are aggregate trend forecasts and must not be interpreted as person-level predictions or automatic enforcement recommendations.

Excluded fields:

- `SUSP_AGE_GROUP`
- `SUSP_RACE`
- `SUSP_SEX`
- `VIC_AGE_GROUP`
- `VIC_RACE`
- `VIC_SEX`

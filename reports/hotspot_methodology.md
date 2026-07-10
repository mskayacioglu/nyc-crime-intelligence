# NYPD Complaint Data Historic - Hotspot Methodology

Deterministic output timestamp UTC: `2025-12-30T00:00:00+00:00`

Deterministic metadata timestamp derived from scoring_end_date at 00:00 UTC so reproduced outputs do not change across runs.

## Scope

This Phase 6B layer identifies elevated recent aggregate crime density for precinct/offense/law-category and grid-cell/offense/law-category groups. It implements only hotspot detection; it does not create dashboard UI, APIs, patrol recommendations, enforcement recommendations, or person-level scores.

## Inputs and Outputs

- Input clean_events: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/complaints_clean.parquet`
- Input weekly_area: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/crime_weekly_area.parquet`
- Output hotspots: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/hotspots.parquet`
- Output metrics: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/hotspot_metrics.json`
- Output report: `/Users/mskayacioglu/Documents/projects/bir-nyc/reports/hotspot_methodology.md`

## Window Definitions

| baseline_start_date | baseline_end_date | recent_90_start_date | recent_30_start_date | recent_7_start_date | scoring_end_date | latest_date_excluded_from_scoring |
| --- | --- | --- | --- | --- | --- | --- |
| 2024-10-02 | 2025-10-01 | 2025-10-02 | 2025-12-01 | 2025-12-24 | 2025-12-30 | true |

The latest cleaned event date is excluded by default because upstream extracts can contain a partial final day. Baseline counts end before the 90-day recent window starts, so baseline and recent windows do not overlap.

## Methodology

The script uses only rows where `is_clean_event_for_aggregate = true`. Precinct hotspots use all aggregate-safe events and attach a precinct centroid from valid coordinates where available. Grid hotspots use only events with map-ready coordinates.

Scoring formulas:

- `recent_event_count = recent_30_day_count`.
- `baseline_expected_recent_count = baseline_event_count * recent_window_days / baseline_window_days`.
- `recent_share_total_events = recent_event_count / all recent events in the same grain * 100`.
- `baseline_share_total_events = baseline_event_count / all baseline events in the same grain * 100`.
- `share_change_pct_points = recent_share_total_events - baseline_share_total_events`.
- `recent_baseline_ratio = recent_event_count / baseline_expected_recent_count`.
- `recent_vs_baseline_lift_pct = (recent_baseline_ratio - 1) * 100`.
- `density_score` is a 0-100 log-scaled recent-count score using grain-specific reference counts.
- `recency_weighted_score` is a 0-100 log-scaled score from 7-, 30-, and 90-day weighted counts.
- `composite_score = 0.35*density + 0.25*lift + 0.20*share_increase + 0.15*recency + 0.05*coordinate_quality`.

Share denominators differ by grain: precinct shares use all aggregate-safe events in the relevant time window, while grid shares use only valid-coordinate events because grid candidates require map-ready coordinates.

A row can be flagged only after minimum recent and baseline volume gates are met. Defaults require at least 25 recent and 50 baseline complaints for precinct groups, and at least 8 recent and 8 baseline complaints for grid groups.

`hotspots.parquet` contains only rows where `is_hotspot = true`; candidate and evaluated-row counts are retained in `hotspot_metrics.json`.

## Coordinate Filters

- Broad NYC latitude bounds: `40.4774` to `40.9176`
- Broad NYC longitude bounds: `-74.2591` to `-73.7004`
- Coordinates must be non-missing and non-zero.
- Phase 2 coordinate quality flags must not mark the row as missing, zero, or out of bounds.
- Grid size: `0.01` degrees.

## Evaluation Summary

| clean_aggregate_event_rows | valid_coordinate_event_rows | candidate_precinct_offense_rows | candidate_grid_offense_rows | evaluated_precinct_offense_rows | evaluated_grid_offense_rows | hotspot_rows | high_or_critical_hotspot_rows |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 10,049,687 | 10,049,230 | 4,176 | 24,362 | 447 | 1,254 | 396 | 26 |

## Hotspot Counts by Severity

| hotspot_grain | hotspot_severity | hotspot_count | recent_event_count | avg_composite_score | max_composite_score |
| --- | --- | --- | --- | --- | --- |
| precinct | low | 20 | 816 | 47.4875 | 60.3466 |
| precinct | medium | 14 | 470 | 57.8737 | 77.9419 |
| precinct | high | 2 | 166 | 79.6631 | 83.2434 |
| precinct | critical | 0 | 0 |  |  |
| grid | low | 160 | 2,355 | 52.5427 | 68.1205 |
| grid | medium | 176 | 2,152 | 64.758 | 84.0376 |
| grid | high | 21 | 520 | 81.9033 | 97.6693 |
| grid | critical | 3 | 131 | 97.5138 | 100 |

## Top Precinct Hotspots

| rank_overall | hotspot_grain | borough | precinct | grid_latitude | grid_longitude | offense_type | law_category | map_latitude | map_longitude | recent_event_count | baseline_event_count | recent_baseline_ratio | share_change_pct_points | density_score | recency_weighted_score | composite_score | hotspot_severity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20 | precinct | BRONX | 46 |  |  | DANGEROUS DRUGS | MISDEMEANOR | 40.85318 | -73.90676 | 99 | 496 | 2.4284 | 0.1672 | 83.3447 | 78.7666 | 83.2434 | high |
| 37 | precinct | QUEENS | 110 |  |  | ADMINISTRATIVE CODE | VIOLATION | 40.74189 | -73.87012 | 25 | 104 | 2.9247 | 0.0459 | 58.9652 | 54.9702 | 77.9419 | medium |
| 43 | precinct | MANHATTAN | 1 |  |  | FORGERY | FELONY | 40.71476 | -74.00751 | 67 | 349 | 2.3357 | 0.1108 | 76.3649 | 62.5241 | 76.0828 | high |
| 61 | precinct | BROOKLYN | 73 |  |  | ADMINISTRATIVE CODE | VIOLATION | 40.66915 | -73.91087 | 39 | 200 | 2.3725 | 0.0651 | 66.7616 | 59.4121 | 73.1603 | medium |
| 65 | precinct | BROOKLYN | 77 |  |  | DANGEROUS DRUGS | MISDEMEANOR | 40.67363 | -73.94172 | 28 | 139 | 2.4508 | 0.0475 | 60.9415 | 52.006 | 71.94 | medium |
| 145 | precinct | BROOKLYN | 70 |  |  | VEHICLE AND TRAFFIC LAWS | MISDEMEANOR | 40.63746 | -73.95929 | 53 | 355 | 1.8164 | 0.074 | 72.1929 | 63.9529 | 62.0586 | medium |
| 164 | precinct | BROOKLYN | 90 |  |  | PETIT LARCENY | MISDEMEANOR | 40.70767 | -73.94854 | 134 | 1,160 | 1.4055 | 0.1414 | 88.776 | 81.2661 | 60.3466 | low |
| 207 | precinct | BRONX | 45 |  |  | VEHICLE AND TRAFFIC LAWS | MISDEMEANOR | 40.84329 | -73.8286 | 56 | 429 | 1.5882 | 0.0688 | 73.1714 | 64.955 | 56.9348 | medium |
| 214 | precinct | QUEENS | 107 |  |  | BURGLARY | FELONY | 40.72354 | -73.80299 | 32 | 221 | 1.7617 | 0.0435 | 63.28 | 54.4864 | 56.1719 | medium |
| 236 | precinct | MANHATTAN | 1 |  |  | BURGLARY | FELONY | 40.71476 | -74.00751 | 25 | 169 | 1.7998 | 0.0346 | 58.9652 | 50.5701 | 55.0123 | medium |
| 279 | precinct | QUEENS | 115 |  |  | GRAND LARCENY OF MOTOR VEHICLE | FELONY | 40.75536 | -73.87631 | 34 | 263 | 1.5729 | 0.0413 | 64.3449 | 54.8396 | 51.9515 | medium |
| 280 | precinct | MANHATTAN | 23 |  |  | CRIMINAL MISCHIEF & RELATED OF | MISDEMEANOR | 40.79181 | -73.94473 | 31 | 235 | 1.605 | 0.0385 | 62.7231 | 53.3362 | 51.9481 | medium |
| 286 | precinct | BROOKLYN | 62 |  |  | MISCELLANEOUS PENAL LAW | FELONY | 40.60702 | -73.99328 | 37 | 296 | 1.5208 | 0.0433 | 65.8333 | 56.8249 | 51.4897 | medium |
| 287 | precinct | BROOKLYN | 69 |  |  | MISCELLANEOUS PENAL LAW | FELONY | 40.64019 | -73.90062 | 26 | 193 | 1.639 | 0.033 | 59.6483 | 51.5923 | 51.4486 | medium |
| 298 | precinct | MANHATTAN | 23 |  |  | VEHICLE AND TRAFFIC LAWS | MISDEMEANOR | 40.79181 | -73.94473 | 28 | 212 | 1.6069 | 0.0348 | 60.9415 | 51.3818 | 51.0795 | medium |
| 304 | precinct | BROOKLYN | 69 |  |  | VEHICLE AND TRAFFIC LAWS | MISDEMEANOR | 40.64019 | -73.90062 | 29 | 224 | 1.5751 | 0.0353 | 61.5551 | 52.057 | 50.6136 | medium |
| 306 | precinct | MANHATTAN | 18 |  |  | FORGERY | FELONY | 40.76257 | -73.98352 | 47 | 408 | 1.4016 | 0.0494 | 70.0612 | 59.6817 | 50.4627 | low |
| 313 | precinct | BRONX | 44 |  |  | OTHER OFFENSES RELATED TO THEFT | MISDEMEANOR | 40.83419 | -73.91931 | 53 | 489 | 1.3187 | 0.0507 | 72.1929 | 65.4725 | 50.038 | low |
| 318 | precinct | BRONX | 46 |  |  | MISCELLANEOUS PENAL LAW | FELONY | 40.85318 | -73.90676 | 32 | 261 | 1.4917 | 0.0366 | 63.28 | 56.3888 | 49.8137 | low |
| 334 | precinct | QUEENS | 110 |  |  | VEHICLE AND TRAFFIC LAWS | MISDEMEANOR | 40.74189 | -73.87012 | 39 | 348 | 1.3635 | 0.0394 | 66.7616 | 60.879 | 48.5511 | low |
| 338 | precinct | BRONX | 48 |  |  | MISCELLANEOUS PENAL LAW | FELONY | 40.84893 | -73.88847 | 27 | 216 | 1.5208 | 0.0316 | 60.3064 | 49.6622 | 48.4807 | medium |
| 342 | precinct | BROOKLYN | 83 |  |  | OTHER OFFENSES RELATED TO THEFT | MISDEMEANOR | 40.69618 | -73.91926 | 36 | 312 | 1.4038 | 0.0379 | 65.3506 | 55.0568 | 48.1767 | low |
| 343 | precinct | MANHATTAN | 14 |  |  | FORGERY | FELONY | 40.75259 | -73.98832 | 44 | 403 | 1.3284 | 0.0426 | 68.8932 | 59.1729 | 48.1766 | low |
| 346 | precinct | BROOKLYN | 68 |  |  | VEHICLE AND TRAFFIC LAWS | MISDEMEANOR | 40.6268 | -74.02284 | 45 | 426 | 1.2852 | 0.0412 | 69.291 | 63.9 | 47.9628 | low |
| 348 | precinct | BRONX | 43 |  |  | BURGLARY | FELONY | 40.82743 | -73.86501 | 31 | 266 | 1.4179 | 0.0331 | 62.7231 | 55.8594 | 47.7238 | low |

## Top Grid Hotspots

| rank_overall | hotspot_grain | borough | precinct | grid_latitude | grid_longitude | offense_type | law_category | map_latitude | map_longitude | recent_event_count | baseline_event_count | recent_baseline_ratio | share_change_pct_points | density_score | recency_weighted_score | composite_score | hotspot_severity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | grid | BRONX |  | 40.845 | -73.905 | DANGEROUS DRUGS | MISDEMEANOR | 40.845 | -73.905 | 69 | 197 | 4.2614 | 0.1424 | 100 | 100 | 100 | critical |
| 2 | grid | BROOKLYN |  | 40.675 | -73.905 | ADMINISTRATIVE CODE | VIOLATION | 40.675 | -73.905 | 38 | 146 | 3.1667 | 0.0719 | 100 | 94.54 | 99.181 | critical |
| 3 | grid | BROOKLYN |  | 40.705 | -73.955 | PETIT LARCENY | MISDEMEANOR | 40.705 | -73.955 | 74 | 320 | 2.8135 | 0.1338 | 100 | 100 | 97.6693 | high |
| 4 | grid | BRONX |  | 40.825 | -73.835 | VEHICLE AND TRAFFIC LAWS | MISDEMEANOR | 40.825 | -73.835 | 24 | 48 | 6.0833 | 0.0531 | 93.7358 | 70.353 | 93.3605 | critical |
| 5 | grid | BROOKLYN |  | 40.675 | -73.955 | OFFENSES AGAINST PUBLIC ADMINI | MISDEMEANOR | 40.675 | -73.955 | 21 | 93 | 2.7473 | 0.0376 | 90.0132 | 78.1727 | 90.0719 | high |
| 6 | grid | QUEENS |  | 40.665 | -73.785 | GRAND LARCENY | FELONY | 40.665 | -73.785 | 16 | 64 | 3.0417 | 0.0298 | 82.5051 | 71.9958 | 89.6762 | high |
| 7 | grid | MANHATTAN |  | 40.715 | -74.005 | FORGERY | FELONY | 40.715 | -74.005 | 79 | 429 | 2.2405 | 0.1277 | 100 | 100 | 87.6323 | high |
| 8 | grid | BROOKLYN |  | 40.665 | -73.895 | DANGEROUS DRUGS | MISDEMEANOR | 40.665 | -73.895 | 14 | 57 | 2.9883 | 0.0259 | 78.8602 | 63.6593 | 87.0038 | high |
| 9 | grid | QUEENS |  | 40.745 | -73.895 | ADMINISTRATIVE CODE | VIOLATION | 40.745 | -73.895 | 25 | 132 | 2.3043 | 0.041 | 94.8779 | 92.9088 | 86.3452 | high |
| 10 | grid | BROOKLYN |  | 40.675 | -73.905 | DANGEROUS DRUGS | MISDEMEANOR | 40.675 | -73.905 | 13 | 55 | 2.8758 | 0.0237 | 76.8511 | 68.0546 | 85.5531 | high |
| 11 | grid | BROOKLYN |  | 40.695 | -73.915 | ADMINISTRATIVE CODE | VIOLATION | 40.695 | -73.915 | 13 | 46 | 3.4384 | 0.0253 | 76.8511 | 56.2472 | 85.335 | high |
| 12 | grid | QUEENS |  | 40.775 | -73.915 | PETIT LARCENY | MISDEMEANOR | 40.775 | -73.915 | 51 | 293 | 2.1177 | 0.0796 | 100 | 100 | 84.6118 | high |
| 13 | grid | BROOKLYN |  | 40.675 | -73.945 | VEHICLE AND TRAFFIC LAWS | MISDEMEANOR | 40.675 | -73.945 | 12 | 48 | 3.0417 | 0.0224 | 74.693 | 56.0354 | 84.5479 | high |
| 14 | grid | BROOKLYN |  | 40.675 | -73.955 | DANGEROUS DRUGS | MISDEMEANOR | 40.675 | -73.955 | 17 | 82 | 2.5224 | 0.0293 | 84.1696 | 72.8435 | 84.4154 | high |
| 15 | grid | BROOKLYN |  | 40.685 | -73.985 | ADMINISTRATIVE CODE | VIOLATION | 40.685 | -73.985 | 10 | 40 | 3.0417 | 0.0186 | 69.8283 | 63.9846 | 84.0376 | medium |
| 16 | grid | BROOKLYN |  | 40.685 | -73.975 | DANGEROUS DRUGS | MISDEMEANOR | 40.685 | -73.975 | 11 | 17 | 7.8726 | 0.0252 | 72.3621 | 57.6881 | 83.98 | medium |
| 17 | grid | QUEENS |  | 40.795 | -73.825 | OFFENSES INVOLVING FRAUD | MISDEMEANOR | 40.795 | -73.825 | 11 | 47 | 2.8475 | 0.02 | 72.3621 | 69.0231 | 83.7742 | medium |
| 18 | grid | BRONX |  | 40.825 | -73.925 | OTHER OFFENSES RELATED TO THEFT | MISDEMEANOR | 40.825 | -73.925 | 42 | 242 | 2.1116 | 0.0654 | 100 | 94.0832 | 83.5723 | high |
| 19 | grid | BRONX |  | 40.835 | -73.865 | BURGLARY | FELONY | 40.835 | -73.865 | 11 | 44 | 3.0417 | 0.0205 | 72.3621 | 54.5081 | 83.503 | medium |
| 21 | grid | QUEENS |  | 40.795 | -73.825 | VEHICLE AND TRAFFIC LAWS | MISDEMEANOR | 40.795 | -73.825 | 11 | 34 | 3.9363 | 0.0222 | 72.3621 | 51.6878 | 83.0799 | medium |
| 22 | grid | BRONX |  | 40.805 | -73.905 | BURGLARY | FELONY | 40.805 | -73.905 | 11 | 23 | 5.8188 | 0.0242 | 72.3621 | 49.3775 | 82.7334 | medium |
| 23 | grid | BRONX |  | 40.825 | -73.905 | DANGEROUS DRUGS | MISDEMEANOR | 40.825 | -73.905 | 10 | 37 | 3.2883 | 0.0192 | 69.8283 | 50.6835 | 82.0424 | medium |
| 24 | grid | BROOKLYN |  | 40.645 | -73.905 | VEHICLE AND TRAFFIC LAWS | MISDEMEANOR | 40.645 | -73.905 | 10 | 39 | 3.1197 | 0.0188 | 69.8283 | 49.9069 | 81.9259 | medium |
| 25 | grid | MANHATTAN |  | 40.715 | -74.015 | BURGLARY | FELONY | 40.715 | -74.015 | 9 | 31 | 3.5323 | 0.0176 | 67.0528 | 53.366 | 81.4734 | medium |
| 26 | grid | QUEENS |  | 40.705 | -73.795 | DANGEROUS DRUGS | FELONY | 40.705 | -73.795 | 10 | 37 | 3.2883 | 0.0192 | 69.8283 | 45.6791 | 81.2918 | medium |

## Coordinate Coverage and Limitations

| aggregate_event_rows | valid_coordinate_event_rows | valid_coordinate_coverage_pct | missing_coordinate_event_rows | zero_coordinate_event_rows | out_of_bounds_coordinate_event_rows |
| --- | --- | --- | --- | --- | --- |
| 10,049,687 | 10,049,230 | 99.9955 | 424 | 25 | 33 |

- Precinct rows can be scored without coordinates, but map centroids are available only where valid coordinate history exists.
- Grid rows exclude missing, zero, and out-of-bounds coordinates, so they represent only map-ready complaint events.
- A 0.01-degree grid is deterministic and easy to reproduce, but it is not an equal-area spatial index.
- Coordinate centroids summarize complaint locations and should not be interpreted as exact incident addresses.

## Limitations Before Dashboard Use

- Hotspots describe elevated aggregate complaint density; they do not explain causality.
- Reported complaint counts can be affected by reporting delay, classification changes, policy changes, and data revisions.
- Fixed thresholds should be monitored for alert volume by borough, offense, and law category before dashboard release.
- A dashboard should show volume gates, baseline counts, lift, coordinate coverage, and scoring window dates next to every hotspot.
- This layer does not include uncertainty intervals, reporting-lag correction, event calendars, street-network topology, or spatial smoothing.

## Ethics Constraint

Suspect and victim demographic fields are excluded. Outputs are aggregate trend intelligence only and must not be interpreted as person-level predictions, automated enforcement actions, or patrol recommendations.

Excluded fields:

- `SUSP_AGE_GROUP`
- `SUSP_RACE`
- `SUSP_SEX`
- `VIC_AGE_GROUP`
- `VIC_RACE`
- `VIC_SEX`

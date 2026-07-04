# NYPD Complaint Data Historic - Cleaning and Aggregation Report

Generated at UTC: `2026-07-04T18:23:29.485937+00:00`

## Source

- File: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/raw/NYPD_Complaint_Data_Historic.csv`
- File size GB: `3.19`
- Sample rows mode: `None`

## Clean Event Definition

A row is included in dashboard and modeling aggregates when `is_clean_event_for_aggregate` is true: the canonical incident start date parses successfully, is on or after the configured minimum incident date, and is not after the configured as-of date. Other quality issues are preserved as flags so analysts can filter or audit them without silently dropping useful records.

- Minimum aggregate incident date: `2006-01-01`
- As-of date for future-date checks: `2026-07-04`
- Broad NYC latitude bounds: `40.4774` to `40.9176`
- Broad NYC longitude bounds: `-74.2591` to `-73.7004`

## Outputs

- Clean event parquet: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/complaints_clean.parquet`
- Weekly aggregate parquet: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/crime_weekly_area.parquet`
- Monthly aggregate parquet: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/crime_monthly_area.parquet`
- Cleaning summary JSON: `/Users/mskayacioglu/Documents/projects/bir-nyc/data/processed/cleaning_summary.json`
- Cleaning report: `/Users/mskayacioglu/Documents/projects/bir-nyc/reports/cleaning_report.md`

## Overall Counts

| row_count | clean_event_count_for_aggregates | distinct_complaint_numbers |
| --- | --- | --- |
| 10,071,507 | 10,049,687 | 10,070,401 |

## Date Coverage

| min_complaint_from_date | max_complaint_from_date | min_complaint_to_date | max_complaint_to_date | min_report_date | max_report_date |
| --- | --- | --- | --- | --- | --- |
| 1010-05-14 | 2025-12-31 | 1010-10-15 | 2090-04-06 | 2006-01-01 | 2025-12-31 |

## Quality Flags

| quality_flag | issue_count | issue_pct |
| --- | --- | --- |
| flag_implausibly_old_complaint_start_date | 21,165 | 0.2101 |
| flag_missing_offense | 18,907 | 0.1877 |
| flag_missing_borough | 10,078 | 0.1001 |
| flag_missing_precinct | 771 | 0.0077 |
| flag_missing_invalid_complaint_start_date | 655 | 0.0065 |
| flag_complaint_end_before_start | 579 | 0.0057 |
| flag_missing_coordinates | 479 | 0.0048 |
| flag_coordinates_outside_broad_nyc_bounds | 33 | 0.0003 |
| flag_zero_coordinates | 25 | 0.0002 |
| flag_report_date_before_complaint_start | 16 | 0.0002 |
| flag_future_complaint_end_date | 5 | 0 |
| flag_future_complaint_start_date | 0 | 0 |
| flag_invalid_law_category | 0 | 0 |

## Aggregate Output Summary

### Weekly

| aggregate_rows | event_rows | min_week_start | max_week_start |
| --- | --- | --- | --- |
| 1,761,447 | 10,049,687 | 2005-12-26 | 2025-12-29 |

### Monthly

| aggregate_rows | event_rows | min_month_start | max_month_start |
| --- | --- | --- | --- |
| 604,132 | 10,049,687 | 2006-01-01 | 2025-12-01 |

## Sensitive Field Handling

Victim and suspect demographic columns are intentionally excluded from `complaints_clean.parquet` and are not used as modeling features. They remain appropriate only for separate coverage, data quality, and fairness risk audits.

Excluded columns:

- `SUSP_AGE_GROUP`
- `SUSP_RACE`
- `SUSP_SEX`
- `VIC_AGE_GROUP`
- `VIC_RACE`
- `VIC_SEX`

## Validation Notes

For local smoke validation, run this script with `--sample-rows` and temporary output directories. Full execution scans the complete 3.2 GB CSV and should be run in Colab or another environment with DuckDB installed.

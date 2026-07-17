#!/usr/bin/env python3
"""Build cleaned NYPD complaint events and aggregate model tables.

The raw NYPD complaint CSV is too large for an in-memory Pandas workflow on many
machines. This script uses DuckDB to stream the CSV as strings, normalize dirty
values, create typed fields and quality flags, and write Parquet outputs.

Install the runtime dependency before running:

    python -m pip install -r requirements.txt

Example full run from the repository root:

    python src/data/build_clean_dataset.py

Example smoke run that does not touch the default generated outputs:

    python src/data/build_clean_dataset.py --sample-rows 10000 \
      --processed-dir .cache/bir-nyc-smoke/processed \
      --reports-dir .cache/bir-nyc-smoke/reports
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


RAW_CSV_RELATIVE_PATH = Path("data/raw/NYPD_Complaint_Data_Historic.csv")
DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_REPORTS_DIR = Path("reports")
DEFAULT_DUCKDB_DATABASE = Path(".cache/cleaning/cleaning.duckdb")

DEFAULT_MIN_INCIDENT_DATE = "2006-01-01"
NYC_LAT_MIN = 40.4774
NYC_LAT_MAX = 40.9176
NYC_LON_MIN = -74.2591
NYC_LON_MAX = -73.7004

NULL_LIKE_VALUES = [
    "",
    "(null)",
    "NULL",
    "null",
    "Null",
    "N/A",
    "n/a",
    "NA",
    "na",
    "NaN",
    "nan",
    "None",
    "none",
    "NONE",
]

VALID_BOROUGHS = ["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]
VALID_LAW_CATEGORIES = ["FELONY", "MISDEMEANOR", "VIOLATION"]

SENSITIVE_COLUMNS = [
    "SUSP_AGE_GROUP",
    "SUSP_RACE",
    "SUSP_SEX",
    "VIC_AGE_GROUP",
    "VIC_RACE",
    "VIC_SEX",
]

EXPECTED_SOURCE_COLUMNS = [
    "CMPLNT_NUM",
    "CMPLNT_FR_DT",
    "CMPLNT_FR_TM",
    "CMPLNT_TO_DT",
    "CMPLNT_TO_TM",
    "ADDR_PCT_CD",
    "RPT_DT",
    "KY_CD",
    "OFNS_DESC",
    "PD_CD",
    "PD_DESC",
    "CRM_ATPT_CPTD_CD",
    "LAW_CAT_CD",
    "BORO_NM",
    "LOC_OF_OCCUR_DESC",
    "PREM_TYP_DESC",
    "JURIS_DESC",
    "JURISDICTION_CODE",
    "PARKS_NM",
    "HADEVELOPT",
    "HOUSING_PSA",
    "X_COORD_CD",
    "Y_COORD_CD",
    "TRANSIT_DISTRICT",
    "Latitude",
    "Longitude",
    "Lat_Lon",
    "PATROL_BORO",
    "STATION_NAME",
    *SENSITIVE_COLUMNS,
]

QUALITY_FLAGS = [
    "flag_missing_invalid_complaint_start_date",
    "flag_implausibly_old_complaint_start_date",
    "flag_future_complaint_start_date",
    "flag_future_complaint_end_date",
    "flag_complaint_end_before_start",
    "flag_report_date_before_complaint_start",
    "flag_missing_borough",
    "flag_missing_precinct",
    "flag_missing_offense",
    "flag_missing_coordinates",
    "flag_zero_coordinates",
    "flag_coordinates_outside_broad_nyc_bounds",
    "flag_invalid_law_category",
]

CLEAN_EVENT_COLUMNS = [
    "source_row_id",
    "complaint_number",
    "complaint_from_date",
    "complaint_to_date",
    "report_date",
    "complaint_from_ts",
    "complaint_to_ts",
    "complaint_from_time",
    "complaint_to_time",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "ky_cd",
    "pd_cd",
    "pd_description",
    "attempt_status",
    "jurisdiction_code",
    "jurisdiction_description",
    "location_of_occur",
    "premise_type",
    "patrol_borough",
    "x_coord",
    "y_coord",
    "latitude",
    "longitude",
    *QUALITY_FLAGS,
    "is_clean_event_for_aggregate",
]

WEEKLY_COLUMNS = [
    "week_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "crime_count",
]

MONTHLY_COLUMNS = [
    "month_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "crime_count",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean and aggregate the NYPD Complaint Historic CSV."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Repository/project root. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--raw-csv",
        type=Path,
        default=None,
        help="Raw CSV path. Defaults to data/raw/NYPD_Complaint_Data_Historic.csv under project root.",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=None,
        help="Output directory for processed Parquet and JSON files.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=None,
        help="Output directory for Markdown reports.",
    )
    parser.add_argument(
        "--duckdb-database",
        type=Path,
        default=None,
        help="DuckDB database file used for temporary work.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=max(1, min(4, os.cpu_count() or 1)),
        help="DuckDB worker threads.",
    )
    parser.add_argument(
        "--sample-rows",
        type=int,
        default=None,
        help="Limit the raw CSV to the first N rows for a fast smoke run.",
    )
    parser.add_argument(
        "--min-incident-date",
        default=DEFAULT_MIN_INCIDENT_DATE,
        help=(
            "Earliest incident start date included in dashboard/model aggregates. "
            "Default is 2006-01-01, matching the source reporting period."
        ),
    )
    parser.add_argument(
        "--as-of-date",
        default=date.today().isoformat(),
        help="Dates after this YYYY-MM-DD value are flagged as future. Defaults to today.",
    )
    return parser.parse_args()


def require_duckdb() -> Any:
    try:
        import duckdb  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: duckdb. From the repository root, run "
            "`python -m pip install -r requirements.txt`."
        ) from exc
    return duckdb


def resolve_path(project_root: Path, value: Path | None, default_relative: Path) -> Path:
    if value is None:
        return (project_root / default_relative).resolve()
    if value.is_absolute():
        return value
    return (project_root / value).resolve()


def sql_string(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def sql_list(values: list[str]) -> str:
    return "[" + ", ".join(sql_string(value) for value in values) + "]"


def sql_in(values: list[str]) -> str:
    return "(" + ", ".join(sql_string(value) for value in values) + ")"


def ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def normalized_expr(column: str) -> str:
    col = ident(column)
    null_values = sql_in([value.upper() for value in NULL_LIKE_VALUES])
    return (
        "CASE "
        f"WHEN {col} IS NULL THEN NULL "
        f"WHEN upper(trim({col})) IN {null_values} THEN NULL "
        f"ELSE regexp_replace(trim({col}), '\\\\s+', ' ', 'g') "
        "END"
    )


def upper_normalized_expr(column: str) -> str:
    return f"upper({normalized_expr(column)})"


def fetch_dicts(con: Any, sql: str) -> list[dict[str, Any]]:
    result = con.execute(sql)
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def fetch_one(con: Any, sql: str) -> dict[str, Any]:
    rows = fetch_dicts(con, sql)
    if not rows:
        raise RuntimeError("Expected one row but query returned no rows.")
    return rows[0]


def json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def markdown_table(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    if not rows:
        return "No rows."
    columns = columns or list(rows[0].keys())
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(format_value(row.get(column)) for column in columns) + " |")
    return "\n".join([header, separator, *body])


def unlink_existing_outputs(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def build_raw_view(con: Any, raw_csv_path: Path, sample_rows: int | None) -> None:
    raw_scan = f"""
        read_csv_auto(
            {sql_string(raw_csv_path)},
            header=true,
            all_varchar=true,
            ignore_errors=true,
            nullstr={sql_list(NULL_LIKE_VALUES)}
        )
    """
    source_sql = f"SELECT * FROM {raw_scan}"
    if sample_rows is not None:
        source_sql += f" LIMIT {int(sample_rows)}"
    con.execute(
        f"""
        CREATE OR REPLACE VIEW complaints_raw AS
        SELECT
            row_number() OVER () AS source_row_id,
            *
        FROM ({source_sql}) raw_rows
        """
    )


def validate_source_columns(con: Any) -> dict[str, list[str]]:
    actual_columns = [row[0] for row in con.execute("DESCRIBE complaints_raw").fetchall()]
    actual_without_row_id = [column for column in actual_columns if column != "source_row_id"]
    missing = [column for column in EXPECTED_SOURCE_COLUMNS if column not in actual_without_row_id]
    unexpected = [column for column in actual_without_row_id if column not in EXPECTED_SOURCE_COLUMNS]
    if missing:
        raise ValueError(f"Raw CSV is missing expected columns: {missing}")
    return {"missing_columns": missing, "unexpected_columns": unexpected}


def build_clean_views(con: Any, min_incident_date: str, as_of_date: str) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE VIEW complaints_prepared AS
        SELECT
            source_row_id,
            {normalized_expr("CMPLNT_NUM")} AS complaint_number,
            {normalized_expr("CMPLNT_FR_DT")} AS complaint_from_date_text,
            {normalized_expr("CMPLNT_TO_DT")} AS complaint_to_date_text,
            {normalized_expr("RPT_DT")} AS report_date_text,
            {normalized_expr("CMPLNT_FR_TM")} AS complaint_from_time,
            {normalized_expr("CMPLNT_TO_TM")} AS complaint_to_time,
            {upper_normalized_expr("BORO_NM")} AS borough_raw,
            {normalized_expr("ADDR_PCT_CD")} AS precinct_text,
            {upper_normalized_expr("OFNS_DESC")} AS offense_type,
            {upper_normalized_expr("LAW_CAT_CD")} AS law_category_raw,
            {normalized_expr("KY_CD")} AS ky_cd_text,
            {normalized_expr("PD_CD")} AS pd_cd_text,
            {upper_normalized_expr("PD_DESC")} AS pd_description,
            {upper_normalized_expr("CRM_ATPT_CPTD_CD")} AS attempt_status,
            {normalized_expr("JURISDICTION_CODE")} AS jurisdiction_code_text,
            {upper_normalized_expr("JURIS_DESC")} AS jurisdiction_description,
            {upper_normalized_expr("LOC_OF_OCCUR_DESC")} AS location_of_occur,
            {upper_normalized_expr("PREM_TYP_DESC")} AS premise_type,
            {upper_normalized_expr("PATROL_BORO")} AS patrol_borough,
            {normalized_expr("X_COORD_CD")} AS x_coord_text,
            {normalized_expr("Y_COORD_CD")} AS y_coord_text,
            {normalized_expr("Latitude")} AS latitude_text,
            {normalized_expr("Longitude")} AS longitude_text
        FROM complaints_raw
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW complaints_typed AS
        SELECT
            source_row_id,
            complaint_number,
            try_strptime(complaint_from_date_text, '%m/%d/%Y')::DATE AS complaint_from_date,
            try_strptime(complaint_to_date_text, '%m/%d/%Y')::DATE AS complaint_to_date,
            try_strptime(report_date_text, '%m/%d/%Y')::DATE AS report_date,
            try_strptime(
                complaint_from_date_text || ' ' || complaint_from_time,
                '%m/%d/%Y %H:%M:%S'
            ) AS complaint_from_ts,
            try_strptime(
                complaint_to_date_text || ' ' || complaint_to_time,
                '%m/%d/%Y %H:%M:%S'
            ) AS complaint_to_ts,
            complaint_from_time,
            complaint_to_time,
            CASE
                WHEN borough_raw IN {sql_in(VALID_BOROUGHS)} THEN borough_raw
                ELSE NULL
            END AS borough,
            try_cast(precinct_text AS INTEGER) AS precinct,
            offense_type,
            CASE
                WHEN law_category_raw IN {sql_in(VALID_LAW_CATEGORIES)} THEN law_category_raw
                ELSE NULL
            END AS law_category,
            law_category_raw,
            try_cast(ky_cd_text AS INTEGER) AS ky_cd,
            try_cast(pd_cd_text AS INTEGER) AS pd_cd,
            pd_description,
            attempt_status,
            try_cast(jurisdiction_code_text AS INTEGER) AS jurisdiction_code,
            jurisdiction_description,
            location_of_occur,
            premise_type,
            patrol_borough,
            try_cast(x_coord_text AS DOUBLE) AS x_coord,
            try_cast(y_coord_text AS DOUBLE) AS y_coord,
            try_cast(latitude_text AS DOUBLE) AS latitude,
            try_cast(longitude_text AS DOUBLE) AS longitude
        FROM complaints_prepared
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW complaints_clean_view AS
        SELECT
            source_row_id,
            complaint_number,
            complaint_from_date,
            complaint_to_date,
            report_date,
            complaint_from_ts,
            complaint_to_ts,
            complaint_from_time,
            complaint_to_time,
            borough,
            precinct,
            offense_type,
            law_category,
            ky_cd,
            pd_cd,
            pd_description,
            attempt_status,
            jurisdiction_code,
            jurisdiction_description,
            location_of_occur,
            premise_type,
            patrol_borough,
            x_coord,
            y_coord,
            latitude,
            longitude,
            complaint_from_date IS NULL AS flag_missing_invalid_complaint_start_date,
            COALESCE(complaint_from_date < DATE {sql_string(min_incident_date)}, false)
                AS flag_implausibly_old_complaint_start_date,
            COALESCE(complaint_from_date > DATE {sql_string(as_of_date)}, false)
                AS flag_future_complaint_start_date,
            COALESCE(complaint_to_date > DATE {sql_string(as_of_date)}, false)
                AS flag_future_complaint_end_date,
            CASE
                WHEN complaint_from_ts IS NOT NULL AND complaint_to_ts IS NOT NULL
                    THEN complaint_to_ts < complaint_from_ts
                WHEN complaint_from_date IS NOT NULL AND complaint_to_date IS NOT NULL
                    THEN complaint_to_date < complaint_from_date
                ELSE false
            END AS flag_complaint_end_before_start,
            COALESCE(report_date < complaint_from_date, false)
                AS flag_report_date_before_complaint_start,
            borough IS NULL AS flag_missing_borough,
            precinct IS NULL AS flag_missing_precinct,
            offense_type IS NULL AS flag_missing_offense,
            latitude IS NULL OR longitude IS NULL AS flag_missing_coordinates,
            COALESCE(latitude = 0, false) OR COALESCE(longitude = 0, false)
                AS flag_zero_coordinates,
            latitude IS NOT NULL
                AND longitude IS NOT NULL
                AND NOT (
                    latitude BETWEEN {NYC_LAT_MIN} AND {NYC_LAT_MAX}
                    AND longitude BETWEEN {NYC_LON_MIN} AND {NYC_LON_MAX}
                ) AS flag_coordinates_outside_broad_nyc_bounds,
            law_category_raw IS NULL OR law_category_raw NOT IN {sql_in(VALID_LAW_CATEGORIES)}
                AS flag_invalid_law_category,
            complaint_from_date IS NOT NULL
                AND complaint_from_date >= DATE {sql_string(min_incident_date)}
                AND complaint_from_date <= DATE {sql_string(as_of_date)}
                AS is_clean_event_for_aggregate
        FROM complaints_typed
        """
    )


def write_clean_outputs(con: Any, processed_dir: Path) -> dict[str, Path]:
    outputs = {
        "clean_events": processed_dir / "complaints_clean.parquet",
        "weekly": processed_dir / "crime_weekly_area.parquet",
        "monthly": processed_dir / "crime_monthly_area.parquet",
    }
    unlink_existing_outputs(list(outputs.values()))

    con.execute(
        f"""
        COPY (
            SELECT {", ".join(ident(column) for column in CLEAN_EVENT_COLUMNS)}
            FROM complaints_clean_view
        ) TO {sql_string(outputs["clean_events"])} (FORMAT PARQUET)
        """
    )

    clean_events_relation = f"read_parquet({sql_string(outputs['clean_events'])})"

    con.execute(
        f"""
        COPY (
            SELECT
                date_trunc('week', complaint_from_date)::DATE AS week_start,
                COALESCE(borough, 'UNKNOWN') AS borough,
                COALESCE(CAST(precinct AS VARCHAR), 'UNKNOWN') AS precinct,
                COALESCE(offense_type, 'UNKNOWN') AS offense_type,
                COALESCE(law_category, 'UNKNOWN') AS law_category,
                COUNT(*)::BIGINT AS crime_count
            FROM {clean_events_relation}
            WHERE is_clean_event_for_aggregate
            GROUP BY 1, 2, 3, 4, 5
        ) TO {sql_string(outputs["weekly"])} (FORMAT PARQUET)
        """
    )

    con.execute(
        f"""
        COPY (
            SELECT
                date_trunc('month', complaint_from_date)::DATE AS month_start,
                COALESCE(borough, 'UNKNOWN') AS borough,
                COALESCE(CAST(precinct AS VARCHAR), 'UNKNOWN') AS precinct,
                COALESCE(offense_type, 'UNKNOWN') AS offense_type,
                COALESCE(law_category, 'UNKNOWN') AS law_category,
                COUNT(*)::BIGINT AS crime_count
            FROM {clean_events_relation}
            WHERE is_clean_event_for_aggregate
            GROUP BY 1, 2, 3, 4, 5
        ) TO {sql_string(outputs["monthly"])} (FORMAT PARQUET)
        """
    )

    return outputs


def build_quality_counts(con: Any, clean_events_path: Path, row_count: int) -> list[dict[str, Any]]:
    clean_events_relation = f"read_parquet({sql_string(clean_events_path)})"
    union_sql = "\nUNION ALL\n".join(
        f"""
        SELECT
            {sql_string(flag)} AS quality_flag,
            COUNT(*) FILTER (WHERE {ident(flag)})::BIGINT AS issue_count
        FROM {clean_events_relation}
        """
        for flag in QUALITY_FLAGS
    )
    rows = fetch_dicts(con, union_sql)
    for row in rows:
        row["issue_pct"] = (row["issue_count"] / row_count * 100) if row_count else 0.0
    return rows


def summarize_outputs(con: Any, outputs: dict[str, Path]) -> dict[str, Any]:
    weekly_path = sql_string(outputs["weekly"])
    monthly_path = sql_string(outputs["monthly"])
    return {
        "weekly": fetch_one(
            con,
            f"""
            SELECT
                COUNT(*)::BIGINT AS aggregate_rows,
                SUM(crime_count)::BIGINT AS event_rows,
                MIN(week_start) AS min_week_start,
                MAX(week_start) AS max_week_start
            FROM read_parquet({weekly_path})
            """,
        ),
        "monthly": fetch_one(
            con,
            f"""
            SELECT
                COUNT(*)::BIGINT AS aggregate_rows,
                SUM(crime_count)::BIGINT AS event_rows,
                MIN(month_start) AS min_month_start,
                MAX(month_start) AS max_month_start
            FROM read_parquet({monthly_path})
            """,
        ),
    }


def write_summary_json(
    summary_path: Path,
    *,
    raw_csv_path: Path,
    processed_dir: Path,
    reports_dir: Path,
    outputs: dict[str, Path],
    column_validation: dict[str, list[str]],
    config: dict[str, Any],
    overall: dict[str, Any],
    date_quality: dict[str, Any],
    quality_counts: list[dict[str, Any]],
    output_summary: dict[str, Any],
) -> None:
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": str(raw_csv_path),
        "source_file_size_gb": raw_csv_path.stat().st_size / (1024**3),
        "processed_dir": str(processed_dir),
        "reports_dir": str(reports_dir),
        "config": config,
        "column_validation": column_validation,
        "outputs": {name: str(path) for name, path in outputs.items()},
        "overall": overall,
        "date_quality": date_quality,
        "quality_flags": quality_counts,
        "aggregate_outputs": output_summary,
        "sensitive_columns_excluded_from_clean_events": SENSITIVE_COLUMNS,
    }
    with summary_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, default=json_default)


def write_cleaning_report(
    report_path: Path,
    *,
    raw_csv_path: Path,
    outputs: dict[str, Path],
    config: dict[str, Any],
    overall: dict[str, Any],
    date_quality: dict[str, Any],
    quality_counts: list[dict[str, Any]],
    output_summary: dict[str, Any],
) -> None:
    sorted_quality = sorted(quality_counts, key=lambda row: row["issue_count"], reverse=True)
    lines = [
        "# NYPD Complaint Data Historic - Cleaning and Aggregation Report",
        "",
        f"Generated at UTC: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "## Source",
        "",
        f"- File: `{raw_csv_path}`",
        f"- File size GB: `{raw_csv_path.stat().st_size / (1024**3):,.2f}`",
        f"- Sample rows mode: `{config.get('sample_rows')}`",
        "",
        "## Clean Event Definition",
        "",
        (
            "A row is included in dashboard and modeling aggregates when "
            "`is_clean_event_for_aggregate` is true: the canonical incident start "
            "date parses successfully, is on or after the configured minimum incident "
            "date, and is not after the configured as-of date. Other quality issues "
            "are preserved as flags so analysts can filter or audit them without "
            "silently dropping useful records."
        ),
        "",
        f"- Minimum aggregate incident date: `{config['min_incident_date']}`",
        f"- As-of date for future-date checks: `{config['as_of_date']}`",
        f"- Broad NYC latitude bounds: `{NYC_LAT_MIN}` to `{NYC_LAT_MAX}`",
        f"- Broad NYC longitude bounds: `{NYC_LON_MIN}` to `{NYC_LON_MAX}`",
        "",
        "## Outputs",
        "",
        f"- Clean event parquet: `{outputs['clean_events']}`",
        f"- Weekly aggregate parquet: `{outputs['weekly']}`",
        f"- Monthly aggregate parquet: `{outputs['monthly']}`",
        f"- Cleaning summary JSON: `{outputs['summary']}`",
        f"- Cleaning report: `{report_path}`",
        "",
        "## Overall Counts",
        "",
        markdown_table([overall]),
        "",
        "## Date Coverage",
        "",
        markdown_table([date_quality]),
        "",
        "## Quality Flags",
        "",
        markdown_table(sorted_quality, ["quality_flag", "issue_count", "issue_pct"]),
        "",
        "## Aggregate Output Summary",
        "",
        "### Weekly",
        "",
        markdown_table([output_summary["weekly"]]),
        "",
        "### Monthly",
        "",
        markdown_table([output_summary["monthly"]]),
        "",
        "## Sensitive Field Handling",
        "",
        (
            "Victim and suspect demographic columns are intentionally excluded from "
            "`complaints_clean.parquet` and are not used as modeling features. They "
            "remain appropriate only for separate coverage, data quality, and fairness "
            "risk audits."
        ),
        "",
        "Excluded columns:",
        "",
        "\n".join(f"- `{column}`" for column in SENSITIVE_COLUMNS),
        "",
        "## Validation Notes",
        "",
        (
            "For local smoke validation, run this script with `--sample-rows` and "
            "temporary output directories. Full execution scans the complete 3.2 GB CSV "
            "and should be run in Colab or another environment with DuckDB installed."
        ),
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    project_root = args.project_root.resolve()
    raw_csv_path = resolve_path(project_root, args.raw_csv, RAW_CSV_RELATIVE_PATH)
    processed_dir = resolve_path(project_root, args.processed_dir, DEFAULT_PROCESSED_DIR)
    reports_dir = resolve_path(project_root, args.reports_dir, DEFAULT_REPORTS_DIR)
    duckdb_database = resolve_path(project_root, args.duckdb_database, DEFAULT_DUCKDB_DATABASE)

    if not raw_csv_path.exists():
        raise FileNotFoundError(f"Raw CSV not found: {raw_csv_path}")
    if args.sample_rows is not None and args.sample_rows <= 0:
        raise ValueError("--sample-rows must be positive when provided.")

    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    duckdb_database.parent.mkdir(parents=True, exist_ok=True)

    duckdb = require_duckdb()
    con = duckdb.connect(database=str(duckdb_database))
    con.execute(f"PRAGMA threads={int(args.threads)}")

    config = {
        "threads": int(args.threads),
        "sample_rows": args.sample_rows,
        "min_incident_date": args.min_incident_date,
        "as_of_date": args.as_of_date,
        "nyc_bounds": {
            "latitude_min": NYC_LAT_MIN,
            "latitude_max": NYC_LAT_MAX,
            "longitude_min": NYC_LON_MIN,
            "longitude_max": NYC_LON_MAX,
        },
    }

    print(f"Reading raw CSV with DuckDB: {raw_csv_path}")
    build_raw_view(con, raw_csv_path, args.sample_rows)
    column_validation = validate_source_columns(con)

    print("Creating typed clean event view.")
    build_clean_views(con, args.min_incident_date, args.as_of_date)

    print(f"Writing Parquet outputs under: {processed_dir}")
    outputs = write_clean_outputs(con, processed_dir)

    summary_path = processed_dir / "cleaning_summary.json"
    report_path = reports_dir / "cleaning_report.md"
    outputs["summary"] = summary_path
    clean_events_relation = f"read_parquet({sql_string(outputs['clean_events'])})"

    overall = fetch_one(
        con,
        f"""
        SELECT
            COUNT(*)::BIGINT AS row_count,
            COUNT(*) FILTER (WHERE is_clean_event_for_aggregate)::BIGINT
                AS clean_event_count_for_aggregates,
            COUNT(DISTINCT complaint_number)::BIGINT AS distinct_complaint_numbers
        FROM {clean_events_relation}
        """,
    )
    date_quality = fetch_one(
        con,
        f"""
        SELECT
            MIN(complaint_from_date) AS min_complaint_from_date,
            MAX(complaint_from_date) AS max_complaint_from_date,
            MIN(complaint_to_date) AS min_complaint_to_date,
            MAX(complaint_to_date) AS max_complaint_to_date,
            MIN(report_date) AS min_report_date,
            MAX(report_date) AS max_report_date
        FROM {clean_events_relation}
        """,
    )
    quality_counts = build_quality_counts(con, outputs["clean_events"], int(overall["row_count"]))
    output_summary = summarize_outputs(con, outputs)

    print(f"Writing cleaning summary: {summary_path}")
    write_summary_json(
        summary_path,
        raw_csv_path=raw_csv_path,
        processed_dir=processed_dir,
        reports_dir=reports_dir,
        outputs=outputs,
        column_validation=column_validation,
        config=config,
        overall=overall,
        date_quality=date_quality,
        quality_counts=quality_counts,
        output_summary=output_summary,
    )

    print(f"Writing cleaning report: {report_path}")
    write_cleaning_report(
        report_path,
        raw_csv_path=raw_csv_path,
        outputs=outputs,
        config=config,
        overall=overall,
        date_quality=date_quality,
        quality_counts=quality_counts,
        output_summary=output_summary,
    )

    print("Cleaning and aggregation pipeline complete.")
    print(f"Clean events: {outputs['clean_events']}")
    print(f"Weekly aggregates: {outputs['weekly']}")
    print(f"Monthly aggregates: {outputs['monthly']}")
    print(f"Summary JSON: {summary_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Interrupted.")

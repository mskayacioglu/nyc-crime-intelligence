#!/usr/bin/env python3
"""Build Phase 3 dashboard-ready analytical summaries.

This script reads the Phase 2 processed Parquet outputs and writes:

    reports/exploratory_analysis.md
    data/processed/dashboard_summary.json

It intentionally stays in the analytical-baseline scope: descriptive trends,
rankings, distributions, time patterns, recent growth/decline, and first
map-ready summaries. It does not train models, build forecasts, expose APIs, or
use suspect/victim demographic fields.

Install the runtime dependency before running:

    python -m pip install -r requirements.txt

Example from the repository root:

    python3 src/analytics/build_dashboard_summary.py
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_REPORTS_DIR = Path("reports")

CLEAN_EVENTS_FILE = "complaints_clean.parquet"
WEEKLY_FILE = "crime_weekly_area.parquet"
MONTHLY_FILE = "crime_monthly_area.parquet"
DASHBOARD_SUMMARY_FILE = "dashboard_summary.json"
EXPLORATORY_REPORT_FILE = "exploratory_analysis.md"

SENSITIVE_COLUMNS = [
    "SUSP_AGE_GROUP",
    "SUSP_RACE",
    "SUSP_SEX",
    "VIC_AGE_GROUP",
    "VIC_RACE",
    "VIC_SEX",
]

ANALYTICS_COLUMNS_USED = [
    "complaint_from_date",
    "complaint_from_ts",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "latitude",
    "longitude",
    "flag_missing_coordinates",
    "flag_zero_coordinates",
    "flag_coordinates_outside_broad_nyc_bounds",
    "is_clean_event_for_aggregate",
]

CLEAN_EVENTS_REQUIRED_COLUMNS = [
    "complaint_from_date",
    "complaint_from_ts",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "latitude",
    "longitude",
    "flag_missing_coordinates",
    "flag_zero_coordinates",
    "flag_coordinates_outside_broad_nyc_bounds",
    "is_clean_event_for_aggregate",
]

WEEKLY_REQUIRED_COLUMNS = [
    "week_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "crime_count",
]

MONTHLY_REQUIRED_COLUMNS = [
    "month_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "crime_count",
]

DASHBOARD_SUMMARY_REQUIRED_SECTIONS = [
    "generated_at_utc",
    "inputs",
    "analytics_columns_used",
    "analysis_window",
    "record_counts",
    "trends",
    "rankings",
    "distributions",
    "temporal_patterns",
    "growth_decline",
    "map_ready",
    "ethics",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Phase 3 dashboard summaries from processed Parquet files."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Repository/project root. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=None,
        help="Directory containing Phase 2 processed Parquet outputs.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=None,
        help="Directory for Markdown report outputs.",
    )
    parser.add_argument(
        "--dashboard-summary",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to data/processed/dashboard_summary.json.",
    )
    parser.add_argument(
        "--exploratory-report",
        type=Path,
        default=None,
        help="Output Markdown path. Defaults to reports/exploratory_analysis.md.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=max(1, min(4, os.cpu_count() or 1)),
        help="DuckDB worker threads.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=25,
        help="Default number of ranked rows to include in dashboard summaries.",
    )
    parser.add_argument(
        "--growth-window-months",
        type=int,
        default=12,
        help="Months in the recent and previous windows used for growth/decline.",
    )
    parser.add_argument(
        "--min-growth-baseline-count",
        type=int,
        default=100,
        help="Minimum previous-window count for growth/decline rankings.",
    )
    parser.add_argument(
        "--heatmap-grid-size",
        type=float,
        default=0.01,
        help="Latitude/longitude grid size in degrees for first heatmap cells.",
    )
    parser.add_argument(
        "--heatmap-limit",
        type=int,
        default=500,
        help="Maximum heatmap cells written to dashboard_summary.json.",
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


def repository_relative_path(project_root: Path, value: str | Path) -> str:
    """Return a deterministic POSIX path rooted within the repository."""
    root = project_root.resolve()
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.resolve().relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "Dashboard summary paths must be inside the project root."
        ) from exc
    return relative.as_posix()


def repository_relative_paths(
    project_root: Path, values: dict[str, Path]
) -> dict[str, str]:
    """Normalize a named path collection for portable summaries and reports."""
    return {
        name: repository_relative_path(project_root, path)
        for name, path in values.items()
    }


def sql_string(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


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


def clean_number(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: clean_number(value) for key, value in row.items()}
        for row in rows
    ]


def pct_change(current_count: int | float | None, previous_count: int | float | None) -> float | None:
    if previous_count in (None, 0):
        return None
    if current_count is None:
        current_count = 0
    return (float(current_count) - float(previous_count)) / float(previous_count) * 100.0


def percent(part: int | float | None, whole: int | float | None) -> float:
    if not whole:
        return 0.0
    return (float(part or 0) / float(whole)) * 100.0


def format_value(value: Any, column: str | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if column and ("latitude" in column or "longitude" in column):
            return f"{value:,.5f}".rstrip("0").rstrip(".")
        if column == "pct_aggregate_events_with_valid_coordinates":
            return f"{value:,.4f}".rstrip("0").rstrip(".")
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        if column in {
            "active_months",
            "heatmap_cell_limit",
            "hour_of_day",
            "iso_day_of_week",
            "min_previous_period_count",
            "rank",
            "window_months",
            "year",
        }:
            return str(value)
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
    body = [
        "| " + " | ".join(format_value(row.get(column), column) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def validate_dashboard_summary_payload(payload: dict[str, Any]) -> None:
    missing_sections = [
        section for section in DASHBOARD_SUMMARY_REQUIRED_SECTIONS if section not in payload
    ]
    if missing_sections:
        raise ValueError(f"Dashboard summary is missing required sections: {missing_sections}")

    columns_used = set(payload.get("analytics_columns_used") or [])
    sensitive_columns = set(payload.get("ethics", {}).get("sensitive_columns_excluded") or [])
    overlap = columns_used.intersection(sensitive_columns)
    if overlap:
        raise ValueError(f"Sensitive columns cannot be used in dashboard analytics: {sorted(overlap)}")

    required_nested = {
        "trends": ["yearly", "monthly", "weekly"],
        "rankings": ["boroughs", "precincts"],
        "distributions": ["offense_types", "law_categories"],
        "temporal_patterns": ["hour_of_day", "day_of_week"],
        "growth_decline": ["borough_offense", "precinct_offense"],
        "map_ready": ["precinct_summary", "heatmap_cells"],
    }
    for section, keys in required_nested.items():
        missing = [key for key in keys if key not in payload.get(section, {})]
        if missing:
            raise ValueError(f"Dashboard summary section `{section}` missing keys: {missing}")


def validate_parquet_columns(con: Any, path: Path, required_columns: list[str]) -> None:
    rows = fetch_dicts(con, f"DESCRIBE SELECT * FROM read_parquet({sql_string(path)})")
    actual_columns = {row["column_name"] for row in rows}
    missing = [column for column in required_columns if column not in actual_columns]
    if missing:
        raise ValueError(f"{path} is missing required columns: {missing}")


def create_input_views(con: Any, clean_events_path: Path, weekly_path: Path, monthly_path: Path) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE VIEW clean_events AS
        SELECT
            complaint_from_date,
            complaint_from_ts,
            borough,
            precinct,
            offense_type,
            law_category,
            latitude,
            longitude,
            flag_missing_coordinates,
            flag_zero_coordinates,
            flag_coordinates_outside_broad_nyc_bounds,
            is_clean_event_for_aggregate
        FROM read_parquet({sql_string(clean_events_path)})
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE VIEW weekly_area AS
        SELECT
            week_start,
            borough,
            precinct,
            offense_type,
            law_category,
            crime_count
        FROM read_parquet({sql_string(weekly_path)})
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE VIEW monthly_area AS
        SELECT
            month_start,
            borough,
            precinct,
            offense_type,
            law_category,
            crime_count
        FROM read_parquet({sql_string(monthly_path)})
        """
    )


def build_record_counts(con: Any) -> dict[str, Any]:
    clean_counts = fetch_one(
        con,
        """
        SELECT
            COUNT(*)::BIGINT AS clean_event_rows,
            COUNT(*) FILTER (WHERE is_clean_event_for_aggregate)::BIGINT
                AS aggregate_event_rows,
            COUNT(*) FILTER (
                WHERE is_clean_event_for_aggregate
                    AND NOT flag_missing_coordinates
                    AND NOT flag_zero_coordinates
                    AND NOT flag_coordinates_outside_broad_nyc_bounds
            )::BIGINT AS valid_coordinate_event_rows
        FROM clean_events
        """,
    )
    aggregate_counts = fetch_one(
        con,
        """
        SELECT
            (SELECT COUNT(*)::BIGINT FROM weekly_area) AS weekly_aggregate_rows,
            (SELECT COUNT(*)::BIGINT FROM monthly_area) AS monthly_aggregate_rows,
            (SELECT SUM(crime_count)::BIGINT FROM weekly_area) AS weekly_event_rows,
            (SELECT SUM(crime_count)::BIGINT FROM monthly_area) AS monthly_event_rows
        """,
    )
    return {**clean_counts, **aggregate_counts}


def build_analysis_window(con: Any) -> dict[str, Any]:
    return fetch_one(
        con,
        """
        SELECT
            MIN(complaint_from_date) FILTER (WHERE is_clean_event_for_aggregate)
                AS min_complaint_from_date,
            MAX(complaint_from_date) FILTER (WHERE is_clean_event_for_aggregate)
                AS max_complaint_from_date,
            (SELECT MIN(week_start) FROM weekly_area) AS min_week_start,
            (SELECT MAX(week_start) FROM weekly_area) AS max_week_start,
            (SELECT MIN(month_start) FROM monthly_area) AS min_month_start,
            (SELECT MAX(month_start) FROM monthly_area) AS max_month_start
        FROM clean_events
        """,
    )


def build_yearly_trends(con: Any) -> list[dict[str, Any]]:
    return normalize_rows(
        fetch_dicts(
            con,
            """
            WITH yearly AS (
                SELECT
                    EXTRACT(year FROM month_start)::INTEGER AS year,
                    SUM(crime_count)::BIGINT AS crime_count
                FROM monthly_area
                GROUP BY 1
            ),
            with_previous AS (
                SELECT
                    year,
                    crime_count,
                    LAG(crime_count) OVER (ORDER BY year) AS previous_year_count
                FROM yearly
            )
            SELECT
                year,
                crime_count,
                previous_year_count,
                CASE
                    WHEN previous_year_count IS NULL THEN NULL
                    ELSE crime_count - previous_year_count
                END AS year_over_year_change,
                CASE
                    WHEN previous_year_count > 0
                        THEN ROUND((crime_count - previous_year_count) * 100.0 / previous_year_count, 2)
                    ELSE NULL
                END AS year_over_year_pct_change
            FROM with_previous
            ORDER BY year
            """,
        )
    )


def build_monthly_trends(con: Any) -> list[dict[str, Any]]:
    return normalize_rows(
        fetch_dicts(
            con,
            """
            WITH monthly AS (
                SELECT
                    month_start,
                    SUM(crime_count)::BIGINT AS crime_count
                FROM monthly_area
                GROUP BY 1
            ),
            with_previous AS (
                SELECT
                    month_start,
                    crime_count,
                    LAG(crime_count) OVER (ORDER BY month_start) AS previous_month_count
                FROM monthly
            )
            SELECT
                month_start,
                STRFTIME(month_start, '%Y-%m') AS month,
                crime_count,
                previous_month_count,
                CASE
                    WHEN previous_month_count IS NULL THEN NULL
                    ELSE crime_count - previous_month_count
                END AS month_over_month_change,
                CASE
                    WHEN previous_month_count > 0
                        THEN ROUND((crime_count - previous_month_count) * 100.0 / previous_month_count, 2)
                    ELSE NULL
                END AS month_over_month_pct_change
            FROM with_previous
            ORDER BY month_start
            """,
        )
    )


def build_weekly_trends(con: Any) -> list[dict[str, Any]]:
    return normalize_rows(
        fetch_dicts(
            con,
            """
            WITH weekly AS (
                SELECT
                    week_start,
                    SUM(crime_count)::BIGINT AS crime_count
                FROM weekly_area
                GROUP BY 1
            ),
            with_previous AS (
                SELECT
                    week_start,
                    crime_count,
                    LAG(crime_count) OVER (ORDER BY week_start) AS previous_week_count
                FROM weekly
            )
            SELECT
                week_start,
                crime_count,
                previous_week_count,
                CASE
                    WHEN previous_week_count IS NULL THEN NULL
                    ELSE crime_count - previous_week_count
                END AS week_over_week_change,
                CASE
                    WHEN previous_week_count > 0
                        THEN ROUND((crime_count - previous_week_count) * 100.0 / previous_week_count, 2)
                    ELSE NULL
                END AS week_over_week_pct_change
            FROM with_previous
            ORDER BY week_start
            """,
        )
    )


def build_borough_rankings(con: Any) -> list[dict[str, Any]]:
    return normalize_rows(
        fetch_dicts(
            con,
            """
            WITH totals AS (
                SELECT SUM(crime_count)::DOUBLE AS total_count
                FROM monthly_area
            ),
            borough_counts AS (
                SELECT
                    borough,
                    SUM(crime_count)::BIGINT AS crime_count,
                    COUNT(DISTINCT month_start)::INTEGER AS active_months
                FROM monthly_area
                GROUP BY 1
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY crime_count DESC, borough) AS rank,
                borough,
                crime_count,
                ROUND(crime_count * 100.0 / total_count, 2) AS pct_total,
                ROUND(crime_count * 1.0 / active_months, 2) AS avg_monthly_count,
                active_months
            FROM borough_counts, totals
            ORDER BY rank
            """,
        )
    )


def build_precinct_rankings(con: Any, top_n: int) -> list[dict[str, Any]]:
    return normalize_rows(
        fetch_dicts(
            con,
            f"""
            WITH totals AS (
                SELECT SUM(crime_count)::DOUBLE AS total_count
                FROM monthly_area
                WHERE precinct <> 'UNKNOWN'
            ),
            precinct_counts AS (
                SELECT
                    borough,
                    precinct,
                    SUM(crime_count)::BIGINT AS crime_count,
                    COUNT(DISTINCT month_start)::INTEGER AS active_months
                FROM monthly_area
                WHERE precinct <> 'UNKNOWN'
                GROUP BY 1, 2
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY crime_count DESC, borough, precinct) AS rank,
                borough,
                precinct,
                crime_count,
                ROUND(crime_count * 100.0 / total_count, 2) AS pct_total_known_precincts,
                ROUND(crime_count * 1.0 / active_months, 2) AS avg_monthly_count,
                active_months
            FROM precinct_counts, totals
            ORDER BY rank
            LIMIT {int(top_n)}
            """,
        )
    )


def build_offense_distribution(con: Any, top_n: int) -> dict[str, Any]:
    total = fetch_one(con, "SELECT SUM(crime_count)::BIGINT AS total_count FROM monthly_area")
    rows = normalize_rows(
        fetch_dicts(
            con,
            f"""
            WITH offense_counts AS (
                SELECT
                    offense_type,
                    SUM(crime_count)::BIGINT AS crime_count
                FROM monthly_area
                GROUP BY 1
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY crime_count DESC, offense_type) AS rank,
                offense_type,
                crime_count,
                ROUND(crime_count * 100.0 / SUM(crime_count) OVER (), 2) AS pct_total
            FROM offense_counts
            ORDER BY rank
            LIMIT {int(top_n)}
            """,
        )
    )
    visible_count = sum(row["crime_count"] for row in rows)
    return {
        "top": rows,
        "other_count": int(total["total_count"] - visible_count),
        "other_pct_total": round(percent(total["total_count"] - visible_count, total["total_count"]), 2),
    }


def build_law_category_distribution(con: Any) -> list[dict[str, Any]]:
    return normalize_rows(
        fetch_dicts(
            con,
            """
            WITH law_counts AS (
                SELECT
                    law_category,
                    SUM(crime_count)::BIGINT AS crime_count
                FROM monthly_area
                GROUP BY 1
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY crime_count DESC, law_category) AS rank,
                law_category,
                crime_count,
                ROUND(crime_count * 100.0 / SUM(crime_count) OVER (), 2) AS pct_total
            FROM law_counts
            ORDER BY rank
            """,
        )
    )


def build_hour_patterns(con: Any) -> list[dict[str, Any]]:
    return normalize_rows(
        fetch_dicts(
            con,
            """
            WITH hourly AS (
                SELECT
                    EXTRACT(hour FROM complaint_from_ts)::INTEGER AS hour_of_day,
                    COUNT(*)::BIGINT AS crime_count
                FROM clean_events
                WHERE is_clean_event_for_aggregate
                    AND complaint_from_ts IS NOT NULL
                GROUP BY 1
            )
            SELECT
                hour_of_day,
                LPAD(CAST(hour_of_day AS VARCHAR), 2, '0') || ':00' AS hour_label,
                crime_count,
                ROUND(crime_count * 100.0 / SUM(crime_count) OVER (), 2) AS pct_total
            FROM hourly
            ORDER BY hour_of_day
            """,
        )
    )


def build_day_patterns(con: Any) -> list[dict[str, Any]]:
    return normalize_rows(
        fetch_dicts(
            con,
            """
            WITH daily AS (
                SELECT
                    CASE CAST(STRFTIME(complaint_from_date, '%w') AS INTEGER)
                        WHEN 0 THEN 7
                        ELSE CAST(STRFTIME(complaint_from_date, '%w') AS INTEGER)
                    END AS iso_day_of_week,
                    CASE CAST(STRFTIME(complaint_from_date, '%w') AS INTEGER)
                        WHEN 0 THEN 'Sunday'
                        WHEN 1 THEN 'Monday'
                        WHEN 2 THEN 'Tuesday'
                        WHEN 3 THEN 'Wednesday'
                        WHEN 4 THEN 'Thursday'
                        WHEN 5 THEN 'Friday'
                        WHEN 6 THEN 'Saturday'
                    END AS day_name,
                    COUNT(*)::BIGINT AS crime_count
                FROM clean_events
                WHERE is_clean_event_for_aggregate
                    AND complaint_from_date IS NOT NULL
                GROUP BY 1, 2
            )
            SELECT
                iso_day_of_week,
                day_name,
                crime_count,
                ROUND(crime_count * 100.0 / SUM(crime_count) OVER (), 2) AS pct_total
            FROM daily
            ORDER BY iso_day_of_week
            """,
        )
    )


def build_growth_bounds(con: Any, window_months: int) -> dict[str, Any]:
    previous_offset = int(window_months * 2 - 1)
    previous_end_offset = int(window_months)
    current_start_offset = int(window_months - 1)
    return fetch_one(
        con,
        f"""
        WITH latest AS (
            SELECT MAX(month_start) AS latest_month
            FROM monthly_area
        )
        SELECT
            DATE_TRUNC('month', latest_month - INTERVAL '{previous_offset} months')::DATE
                AS previous_period_start,
            DATE_TRUNC('month', latest_month - INTERVAL '{previous_end_offset} months')::DATE
                AS previous_period_end,
            DATE_TRUNC('month', latest_month - INTERVAL '{current_start_offset} months')::DATE
                AS current_period_start,
            latest_month AS current_period_end
        FROM latest
        """,
    )


def build_growth_rows(
    con: Any,
    *,
    scope: str,
    direction: str,
    top_n: int,
    min_baseline_count: int,
    bounds: dict[str, Any],
) -> list[dict[str, Any]]:
    if scope == "borough_offense":
        group_columns = ["borough", "offense_type"]
        where_clause = "borough <> 'UNKNOWN' AND offense_type <> 'UNKNOWN'"
        select_columns = "borough, offense_type"
        order_columns = "borough, offense_type"
    elif scope == "precinct_offense":
        group_columns = ["borough", "precinct", "offense_type"]
        where_clause = (
            "borough <> 'UNKNOWN' AND precinct <> 'UNKNOWN' AND offense_type <> 'UNKNOWN'"
        )
        select_columns = "borough, precinct, offense_type"
        order_columns = "borough, precinct, offense_type"
    else:
        raise ValueError(f"Unsupported growth scope: {scope}")

    order_direction = "DESC" if direction == "increasing" else "ASC"
    group_sql = ", ".join(group_columns)
    return normalize_rows(
        fetch_dicts(
            con,
            f"""
            WITH base AS (
                SELECT
                    {group_sql},
                    SUM(crime_count) FILTER (
                        WHERE month_start BETWEEN DATE {sql_string(bounds["current_period_start"])}
                            AND DATE {sql_string(bounds["current_period_end"])}
                    )::BIGINT AS current_count,
                    SUM(crime_count) FILTER (
                        WHERE month_start BETWEEN DATE {sql_string(bounds["previous_period_start"])}
                            AND DATE {sql_string(bounds["previous_period_end"])}
                    )::BIGINT AS previous_count
                FROM monthly_area
                WHERE {where_clause}
                    AND month_start BETWEEN DATE {sql_string(bounds["previous_period_start"])}
                        AND DATE {sql_string(bounds["current_period_end"])}
                GROUP BY {group_sql}
            ),
            enriched AS (
                SELECT
                    {select_columns},
                    COALESCE(current_count, 0)::BIGINT AS current_count,
                    COALESCE(previous_count, 0)::BIGINT AS previous_count,
                    (COALESCE(current_count, 0) - COALESCE(previous_count, 0))::BIGINT
                        AS absolute_change,
                    CASE
                        WHEN previous_count > 0
                            THEN ROUND((COALESCE(current_count, 0) - previous_count) * 100.0 / previous_count, 2)
                        ELSE NULL
                    END AS pct_change
                FROM base
                WHERE COALESCE(previous_count, 0) >= {int(min_baseline_count)}
            )
            SELECT
                ROW_NUMBER() OVER (
                    ORDER BY pct_change {order_direction}, absolute_change {order_direction}, {order_columns}
                ) AS rank,
                {select_columns},
                previous_count,
                current_count,
                absolute_change,
                pct_change
            FROM enriched
            WHERE pct_change IS NOT NULL
            ORDER BY rank
            LIMIT {int(top_n)}
            """,
        )
    )


def build_growth_decline(
    con: Any,
    *,
    window_months: int,
    top_n: int,
    min_baseline_count: int,
) -> dict[str, Any]:
    bounds = build_growth_bounds(con, window_months)
    return {
        "comparison": {
            "window_months": window_months,
            "min_previous_period_count": min_baseline_count,
            "previous_period": {
                "start": bounds["previous_period_start"],
                "end": bounds["previous_period_end"],
            },
            "current_period": {
                "start": bounds["current_period_start"],
                "end": bounds["current_period_end"],
            },
        },
        "borough_offense": {
            "fastest_increasing": build_growth_rows(
                con,
                scope="borough_offense",
                direction="increasing",
                top_n=top_n,
                min_baseline_count=min_baseline_count,
                bounds=bounds,
            ),
            "fastest_decreasing": build_growth_rows(
                con,
                scope="borough_offense",
                direction="decreasing",
                top_n=top_n,
                min_baseline_count=min_baseline_count,
                bounds=bounds,
            ),
        },
        "precinct_offense": {
            "fastest_increasing": build_growth_rows(
                con,
                scope="precinct_offense",
                direction="increasing",
                top_n=top_n,
                min_baseline_count=min_baseline_count,
                bounds=bounds,
            ),
            "fastest_decreasing": build_growth_rows(
                con,
                scope="precinct_offense",
                direction="decreasing",
                top_n=top_n,
                min_baseline_count=min_baseline_count,
                bounds=bounds,
            ),
        },
    }


def build_precinct_map_summary(con: Any) -> list[dict[str, Any]]:
    return normalize_rows(
        fetch_dicts(
            con,
            """
            WITH valid_geo_events AS (
                SELECT
                    COALESCE(borough, 'UNKNOWN') AS borough,
                    COALESCE(CAST(precinct AS VARCHAR), 'UNKNOWN') AS precinct,
                    COALESCE(offense_type, 'UNKNOWN') AS offense_type,
                    latitude,
                    longitude
                FROM clean_events
                WHERE is_clean_event_for_aggregate
                    AND NOT flag_missing_coordinates
                    AND NOT flag_zero_coordinates
                    AND NOT flag_coordinates_outside_broad_nyc_bounds
                    AND borough IS NOT NULL
                    AND precinct IS NOT NULL
            ),
            precinct_counts AS (
                SELECT
                    precinct,
                    COUNT(*)::BIGINT AS crime_count,
                    ROUND(AVG(latitude), 6) AS centroid_latitude,
                    ROUND(AVG(longitude), 6) AS centroid_longitude,
                    COUNT(*)::BIGINT AS valid_coordinate_count
                FROM valid_geo_events
                GROUP BY 1
            ),
            borough_counts AS (
                SELECT
                    precinct,
                    borough,
                    COUNT(*)::BIGINT AS borough_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY precinct
                        ORDER BY COUNT(*) DESC, borough
                    ) AS borough_rank
                FROM valid_geo_events
                GROUP BY 1, 2
            ),
            offense_counts AS (
                SELECT
                    precinct,
                    offense_type,
                    COUNT(*)::BIGINT AS offense_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY precinct
                        ORDER BY COUNT(*) DESC, offense_type
                    ) AS offense_rank
                FROM valid_geo_events
                GROUP BY 1, 2
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY p.crime_count DESC, b.borough, p.precinct) AS rank,
                b.borough,
                p.precinct,
                p.crime_count,
                ROUND(p.crime_count * 100.0 / SUM(p.crime_count) OVER (), 2)
                    AS pct_valid_coordinate_events,
                p.centroid_latitude,
                p.centroid_longitude,
                p.valid_coordinate_count,
                o.offense_type AS top_offense_type,
                o.offense_count AS top_offense_count
            FROM precinct_counts p
            LEFT JOIN borough_counts b
                ON p.precinct = b.precinct
                AND b.borough_rank = 1
            LEFT JOIN offense_counts o
                ON p.precinct = o.precinct
                AND o.offense_rank = 1
            ORDER BY rank
            """,
        )
    )


def build_heatmap_cells(con: Any, grid_size: float, limit: int) -> list[dict[str, Any]]:
    return normalize_rows(
        fetch_dicts(
            con,
            f"""
            WITH valid_geo_events AS (
                SELECT
                    COALESCE(borough, 'UNKNOWN') AS borough,
                    COALESCE(offense_type, 'UNKNOWN') AS offense_type,
                    ROUND(FLOOR(latitude / {float(grid_size)}) * {float(grid_size)}
                        + {float(grid_size)} / 2, 5) AS latitude,
                    ROUND(FLOOR(longitude / {float(grid_size)}) * {float(grid_size)}
                        + {float(grid_size)} / 2, 5) AS longitude
                FROM clean_events
                WHERE is_clean_event_for_aggregate
                    AND NOT flag_missing_coordinates
                    AND NOT flag_zero_coordinates
                    AND NOT flag_coordinates_outside_broad_nyc_bounds
            ),
            cell_counts AS (
                SELECT
                    latitude,
                    longitude,
                    COUNT(*)::BIGINT AS crime_count
                FROM valid_geo_events
                GROUP BY 1, 2
            ),
            borough_counts AS (
                SELECT
                    latitude,
                    longitude,
                    borough,
                    COUNT(*)::BIGINT AS borough_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY latitude, longitude
                        ORDER BY COUNT(*) DESC, borough
                    ) AS borough_rank
                FROM valid_geo_events
                GROUP BY 1, 2, 3
            ),
            offense_counts AS (
                SELECT
                    latitude,
                    longitude,
                    offense_type,
                    COUNT(*)::BIGINT AS offense_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY latitude, longitude
                        ORDER BY COUNT(*) DESC, offense_type
                    ) AS offense_rank
                FROM valid_geo_events
                GROUP BY 1, 2, 3
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY c.crime_count DESC, c.latitude, c.longitude) AS rank,
                c.latitude,
                c.longitude,
                c.crime_count,
                ROUND(c.crime_count * 100.0 / SUM(c.crime_count) OVER (), 2)
                    AS pct_top_cells_total,
                b.borough AS dominant_borough,
                o.offense_type AS top_offense_type,
                o.offense_count AS top_offense_count
            FROM cell_counts c
            LEFT JOIN borough_counts b
                ON c.latitude = b.latitude
                AND c.longitude = b.longitude
                AND b.borough_rank = 1
            LEFT JOIN offense_counts o
                ON c.latitude = o.latitude
                AND c.longitude = o.longitude
                AND o.offense_rank = 1
            ORDER BY rank
            LIMIT {int(limit)}
            """,
        )
    )


def build_map_ready(con: Any, grid_size: float, heatmap_limit: int) -> dict[str, Any]:
    valid_geo_counts = fetch_one(
        con,
        """
        WITH counts AS (
            SELECT
                COUNT(*) FILTER (
                    WHERE is_clean_event_for_aggregate
                        AND NOT flag_missing_coordinates
                        AND NOT flag_zero_coordinates
                        AND NOT flag_coordinates_outside_broad_nyc_bounds
                )::BIGINT AS valid_coordinate_event_rows,
                COUNT(*) FILTER (WHERE is_clean_event_for_aggregate)::BIGINT
                    AS aggregate_event_rows
            FROM clean_events
        )
        SELECT
            valid_coordinate_event_rows,
            ROUND(valid_coordinate_event_rows * 100.0 / NULLIF(aggregate_event_rows, 0), 4)
                AS pct_aggregate_events_with_valid_coordinates
        FROM counts
        """,
    )
    return {
        "coordinate_filter": (
            "is_clean_event_for_aggregate and non-missing, non-zero coordinates inside broad NYC bounds"
        ),
        "heatmap_grid_size_degrees": grid_size,
        "heatmap_cell_limit": heatmap_limit,
        **valid_geo_counts,
        "precinct_summary": build_precinct_map_summary(con),
        "heatmap_cells": build_heatmap_cells(con, grid_size, heatmap_limit),
    }


def build_dashboard_summary(
    con: Any,
    *,
    project_root: Path,
    inputs: dict[str, Path],
    top_n: int,
    growth_window_months: int,
    min_growth_baseline_count: int,
    heatmap_grid_size: float,
    heatmap_limit: int,
) -> dict[str, Any]:
    portable_inputs = repository_relative_paths(project_root, inputs)
    record_counts = build_record_counts(con)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "Phase 3 - Analytical Baseline",
        "inputs": portable_inputs,
        "analytics_columns_used": ANALYTICS_COLUMNS_USED,
        "analysis_window": build_analysis_window(con),
        "record_counts": record_counts,
        "trends": {
            "yearly": build_yearly_trends(con),
            "monthly": build_monthly_trends(con),
            "weekly": build_weekly_trends(con),
        },
        "rankings": {
            "boroughs": build_borough_rankings(con),
            "precincts": build_precinct_rankings(con, top_n),
        },
        "distributions": {
            "offense_types": build_offense_distribution(con, top_n),
            "law_categories": build_law_category_distribution(con),
        },
        "temporal_patterns": {
            "hour_of_day": build_hour_patterns(con),
            "day_of_week": build_day_patterns(con),
        },
        "growth_decline": build_growth_decline(
            con,
            window_months=growth_window_months,
            top_n=top_n,
            min_baseline_count=min_growth_baseline_count,
        ),
        "map_ready": build_map_ready(con, heatmap_grid_size, heatmap_limit),
        "ethics": {
            "sensitive_columns_excluded": SENSITIVE_COLUMNS,
            "note": (
                "Suspect and victim demographic fields are not used as dashboard "
                "features or analytical grouping fields in this Phase 3 baseline."
            ),
        },
    }
    validate_dashboard_summary_payload(payload)
    return payload


def latest_rows(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    return rows[-count:] if len(rows) > count else rows


def top_row(rows: list[dict[str, Any]], key: str = "crime_count") -> dict[str, Any]:
    if not rows:
        return {}
    return max(rows, key=lambda row: row.get(key) or 0)


def write_dashboard_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, default=json_default)
        file.write("\n")


def write_exploratory_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    yearly = payload["trends"]["yearly"]
    monthly = payload["trends"]["monthly"]
    weekly = payload["trends"]["weekly"]
    boroughs = payload["rankings"]["boroughs"]
    precincts = payload["rankings"]["precincts"]
    offenses = payload["distributions"]["offense_types"]["top"]
    law_categories = payload["distributions"]["law_categories"]
    hours = payload["temporal_patterns"]["hour_of_day"]
    days = payload["temporal_patterns"]["day_of_week"]
    growth = payload["growth_decline"]
    map_ready = payload["map_ready"]

    peak_year = top_row(yearly)
    latest_year = yearly[-1] if yearly else {}
    top_borough = boroughs[0] if boroughs else {}
    top_precinct = precincts[0] if precincts else {}
    top_offense = offenses[0] if offenses else {}
    top_law = law_categories[0] if law_categories else {}
    peak_hour = top_row(hours)
    peak_day = top_row(days)
    fastest_borough_increase = (
        growth["borough_offense"]["fastest_increasing"][0]
        if growth["borough_offense"]["fastest_increasing"]
        else {}
    )
    fastest_borough_decrease = (
        growth["borough_offense"]["fastest_decreasing"][0]
        if growth["borough_offense"]["fastest_decreasing"]
        else {}
    )
    fastest_precinct_increase = (
        growth["precinct_offense"]["fastest_increasing"][0]
        if growth["precinct_offense"]["fastest_increasing"]
        else {}
    )
    fastest_precinct_decrease = (
        growth["precinct_offense"]["fastest_decreasing"][0]
        if growth["precinct_offense"]["fastest_decreasing"]
        else {}
    )
    top_heatmap_cell = map_ready["heatmap_cells"][0] if map_ready["heatmap_cells"] else {}
    coordinate_pct = format_value(
        map_ready["pct_aggregate_events_with_valid_coordinates"],
        "pct_aggregate_events_with_valid_coordinates",
    )
    growth_comparison = growth["comparison"]
    growth_comparison_rows = [
        {
            "window_months": growth_comparison["window_months"],
            "min_previous_period_count": growth_comparison["min_previous_period_count"],
            "previous_period_start": growth_comparison["previous_period"]["start"],
            "previous_period_end": growth_comparison["previous_period"]["end"],
            "current_period_start": growth_comparison["current_period"]["start"],
            "current_period_end": growth_comparison["current_period"]["end"],
        }
    ]

    lines = [
        "# NYPD Complaint Data Historic - Exploratory Analysis",
        "",
        f"Generated at UTC: `{payload['generated_at_utc']}`",
        "",
        "## Scope",
        "",
        (
            "The exploratory analysis reads the canonical cleaned Parquet outputs and "
            "produces dashboard-ready descriptive summaries. Forecasting, machine "
            "learning, and browser-contract construction are handled by separate builders."
        ),
        "",
        "## Inputs",
        "",
        "\n".join(f"- {name}: `{path}`" for name, path in payload["inputs"].items()),
        "",
        "## Analysis Window",
        "",
        markdown_table([payload["analysis_window"]]),
        "",
        "## Key Findings",
        "",
        (
            f"- The analytical baseline covers {format_value(payload['record_counts']['aggregate_event_rows'])} "
            f"clean aggregate events from {format_value(payload['analysis_window']['min_complaint_from_date'])} "
            f"through {format_value(payload['analysis_window']['max_complaint_from_date'])}."
        ),
        (
            f"- Annual volume peaks in {peak_year.get('year')} with "
            f"{format_value(peak_year.get('crime_count'))} complaints."
        ),
        (
            f"- The latest available year, {latest_year.get('year')}, has "
            f"{format_value(latest_year.get('crime_count'))} complaints "
            f"({format_value(latest_year.get('year_over_year_pct_change'))}% year over year)."
        ),
        (
            f"- {top_borough.get('borough')} ranks first by borough with "
            f"{format_value(top_borough.get('crime_count'))} complaints "
            f"({format_value(top_borough.get('pct_total'))}% of clean aggregate events)."
        ),
        (
            f"- Precinct {top_precinct.get('precinct')} in {top_precinct.get('borough')} "
            f"is the highest-volume precinct in the ranking with "
            f"{format_value(top_precinct.get('crime_count'))} complaints."
        ),
        (
            f"- {top_offense.get('offense_type')} is the most common offense type "
            f"({format_value(top_offense.get('crime_count'))} complaints; "
            f"{format_value(top_offense.get('pct_total'))}% of total)."
        ),
        (
            f"- {top_law.get('law_category')} is the largest law category at "
            f"{format_value(top_law.get('pct_total'))}% of complaints."
        ),
        (
            f"- The busiest hour is {peak_hour.get('hour_label')} and the busiest day is "
            f"{peak_day.get('day_name')} based on cleaned incident start timestamps."
        ),
        (
            f"- The fastest borough/offense increase is {fastest_borough_increase.get('offense_type')} "
            f"in {fastest_borough_increase.get('borough')} "
            f"({format_value(fastest_borough_increase.get('pct_change'))}% over the prior window)."
        ),
        (
            f"- The fastest borough/offense decrease is {fastest_borough_decrease.get('offense_type')} "
            f"in {fastest_borough_decrease.get('borough')} "
            f"({format_value(fastest_borough_decrease.get('pct_change'))}% over the prior window)."
        ),
        (
            f"- The fastest precinct/offense increase is {fastest_precinct_increase.get('offense_type')} "
            f"in precinct {fastest_precinct_increase.get('precinct')} "
            f"({fastest_precinct_increase.get('borough')}); "
            f"{format_value(fastest_precinct_increase.get('pct_change'))}% over the prior window."
        ),
        (
            f"- The fastest precinct/offense decrease is {fastest_precinct_decrease.get('offense_type')} "
            f"in precinct {fastest_precinct_decrease.get('precinct')} "
            f"({fastest_precinct_decrease.get('borough')}); "
            f"{format_value(fastest_precinct_decrease.get('pct_change'))}% over the prior window."
        ),
        (
            f"- {format_value(map_ready['valid_coordinate_event_rows'])} clean aggregate events "
            f"({coordinate_pct}%) have "
            "map-ready coordinates. The highest-volume heatmap cell is centered at "
            f"({top_heatmap_cell.get('latitude')}, {top_heatmap_cell.get('longitude')})."
        ),
        "",
        "## Yearly Trend",
        "",
        markdown_table(yearly),
        "",
        "## Recent Monthly Trend",
        "",
        markdown_table(latest_rows(monthly, 24)),
        "",
        "## Recent Weekly Trend",
        "",
        markdown_table(latest_rows(weekly, 16)),
        "",
        "## Borough Rankings",
        "",
        markdown_table(boroughs),
        "",
        "## Top Precinct Rankings",
        "",
        markdown_table(precincts[:15]),
        "",
        "## Offense Type Distribution",
        "",
        markdown_table(offenses[:20]),
        "",
        "Other offense count outside the displayed top list: "
        f"`{format_value(payload['distributions']['offense_types']['other_count'])}`.",
        "",
        "## Law Category Distribution",
        "",
        markdown_table(law_categories),
        "",
        "## Hour-of-Day Pattern",
        "",
        markdown_table(hours),
        "",
        "## Day-of-Week Pattern",
        "",
        markdown_table(days),
        "",
        "## Growth and Decline Windows",
        "",
        markdown_table(growth_comparison_rows),
        "",
        "### Fastest Increasing Borough/Offense Combinations",
        "",
        markdown_table(growth["borough_offense"]["fastest_increasing"][:10]),
        "",
        "### Fastest Decreasing Borough/Offense Combinations",
        "",
        markdown_table(growth["borough_offense"]["fastest_decreasing"][:10]),
        "",
        "### Fastest Increasing Precinct/Offense Combinations",
        "",
        markdown_table(growth["precinct_offense"]["fastest_increasing"][:10]),
        "",
        "### Fastest Decreasing Precinct/Offense Combinations",
        "",
        markdown_table(growth["precinct_offense"]["fastest_decreasing"][:10]),
        "",
        "## Map-Ready Summary",
        "",
        f"- Coordinate filter: `{map_ready['coordinate_filter']}`",
        f"- Heatmap grid size degrees: `{map_ready['heatmap_grid_size_degrees']}`",
        f"- Heatmap cells emitted: `{len(map_ready['heatmap_cells'])}`",
        "",
        "### Highest-Volume Precinct Map Rows",
        "",
        markdown_table(map_ready["precinct_summary"][:15]),
        "",
        "### Highest-Volume Heatmap Cells",
        "",
        markdown_table(map_ready["heatmap_cells"][:15]),
        "",
        "## Ethics Constraint",
        "",
        (
            "Victim and suspect demographic fields are intentionally excluded from "
            "this dashboard summary. They are not used as grouping fields, ranking "
            "features, heatmap dimensions, or model features."
        ),
        "",
        "Excluded fields:",
        "",
        "\n".join(f"- `{column}`" for column in payload["ethics"]["sensitive_columns_excluded"]),
        "",
        "## Limitations",
        "",
        (
            "- These findings are descriptive and should be interpreted with source-data "
            "coverage, reporting practices, and cleaned-date filters in mind."
        ),
        (
            "- The latest weekly bucket can be a partial week when the source max date "
            "falls before the end of that calendar week."
        ),
        (
            "- Heatmap cells are an initial dashboard-ready spatial aggregate, not a "
            "formal hotspot or anomaly layer."
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    if args.top_n <= 0:
        raise ValueError("--top-n must be positive.")
    if args.growth_window_months <= 0:
        raise ValueError("--growth-window-months must be positive.")
    if args.min_growth_baseline_count < 0:
        raise ValueError("--min-growth-baseline-count cannot be negative.")
    if args.heatmap_grid_size <= 0:
        raise ValueError("--heatmap-grid-size must be positive.")
    if args.heatmap_limit <= 0:
        raise ValueError("--heatmap-limit must be positive.")

    project_root = args.project_root.resolve()
    processed_dir = resolve_path(project_root, args.processed_dir, DEFAULT_PROCESSED_DIR)
    reports_dir = resolve_path(project_root, args.reports_dir, DEFAULT_REPORTS_DIR)
    dashboard_summary_path = resolve_path(
        project_root,
        args.dashboard_summary,
        DEFAULT_PROCESSED_DIR / DASHBOARD_SUMMARY_FILE,
    )
    exploratory_report_path = resolve_path(
        project_root,
        args.exploratory_report,
        DEFAULT_REPORTS_DIR / EXPLORATORY_REPORT_FILE,
    )

    inputs = {
        "clean_events": processed_dir / CLEAN_EVENTS_FILE,
        "weekly_area": processed_dir / WEEKLY_FILE,
        "monthly_area": processed_dir / MONTHLY_FILE,
    }
    repository_relative_paths(
        project_root,
        {
            **inputs,
            "processed_dir": processed_dir,
            "reports_dir": reports_dir,
            "dashboard_summary": dashboard_summary_path,
            "exploratory_report": exploratory_report_path,
        },
    )
    missing_inputs = [path for path in inputs.values() if not path.exists()]
    if missing_inputs:
        raise FileNotFoundError(f"Missing processed input files: {missing_inputs}")

    reports_dir.mkdir(parents=True, exist_ok=True)
    dashboard_summary_path.parent.mkdir(parents=True, exist_ok=True)
    exploratory_report_path.parent.mkdir(parents=True, exist_ok=True)

    duckdb = require_duckdb()
    con = duckdb.connect(database=":memory:")
    con.execute(f"PRAGMA threads={int(args.threads)}")

    print("Validating processed Parquet schemas.")
    validate_parquet_columns(con, inputs["clean_events"], CLEAN_EVENTS_REQUIRED_COLUMNS)
    validate_parquet_columns(con, inputs["weekly_area"], WEEKLY_REQUIRED_COLUMNS)
    validate_parquet_columns(con, inputs["monthly_area"], MONTHLY_REQUIRED_COLUMNS)

    print("Creating analytical views.")
    create_input_views(con, inputs["clean_events"], inputs["weekly_area"], inputs["monthly_area"])

    print("Building dashboard summary payload.")
    payload = build_dashboard_summary(
        con,
        project_root=project_root,
        inputs=inputs,
        top_n=args.top_n,
        growth_window_months=args.growth_window_months,
        min_growth_baseline_count=args.min_growth_baseline_count,
        heatmap_grid_size=args.heatmap_grid_size,
        heatmap_limit=args.heatmap_limit,
    )

    print(f"Writing dashboard summary JSON: {dashboard_summary_path}")
    write_dashboard_summary(dashboard_summary_path, payload)
    print(f"Writing exploratory report: {exploratory_report_path}")
    write_exploratory_report(exploratory_report_path, payload)
    print("Phase 3 analytical baseline complete.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Interrupted.")

#!/usr/bin/env python3
"""Build Phase 4 weekly baseline forecasts.

This script reads the Phase 2 weekly aggregate table and writes:

    reports/baseline_model_report.md
    data/processed/baseline_predictions.parquet
    data/processed/baseline_metrics.json

The forecasts are intentionally simple and explainable. Every prediction for a
target week is computed only from prior weeks in the same borough/precinct/
offense/law-category segment. No suspect or victim demographic fields are read
or used.

Example from the repository root:

    python3 src/models/build_baseline_forecast.py
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_REPORTS_DIR = Path("reports")
DEFAULT_MODEL_DIR = Path("models/baseline_forecast")

WEEKLY_FILE = "crime_weekly_area.parquet"
PREDICTIONS_FILE = "baseline_predictions.parquet"
METRICS_FILE = "baseline_metrics.json"
REPORT_FILE = "baseline_model_report.md"
MODEL_MANIFEST_FILE = "model_manifest.json"

SENSITIVE_COLUMNS = [
    "SUSP_AGE_GROUP",
    "SUSP_RACE",
    "SUSP_SEX",
    "VIC_AGE_GROUP",
    "VIC_RACE",
    "VIC_SEX",
]

WEEKLY_REQUIRED_COLUMNS = [
    "week_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "crime_count",
]

FORECAST_COLUMNS_USED = WEEKLY_REQUIRED_COLUMNS.copy()

BASELINE_METHODS = [
    "previous_week",
    "trailing_4_week_mean",
    "trailing_8_week_mean",
    "previous_year_same_week",
]

PREDICTION_COLUMNS = [
    "week_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "actual_crime_count",
    "previous_week",
    "trailing_4_week_mean",
    "trailing_8_week_mean",
    "previous_year_same_week",
    "is_backtest_week",
    "is_next_week_forecast",
    "segment_first_week",
    "segment_last_observed_week",
    "segment_observed_week_count",
    "segment_total_crime_count",
]

BASELINE_METRICS_REQUIRED_SECTIONS = [
    "generated_at_utc",
    "phase",
    "inputs",
    "outputs",
    "forecast_columns_used",
    "prediction_columns",
    "forecast_config",
    "analysis_window",
    "record_counts",
    "metrics",
    "top_k_capture",
    "hardest_segments",
    "ethics",
]

BASELINE_MODEL_RULES = [
    {
        "baseline_method": "previous_week",
        "rule": "Use the immediately prior weekly crime_count for the same segment.",
        "required_prior_weeks": 1,
    },
    {
        "baseline_method": "trailing_4_week_mean",
        "rule": "Use the arithmetic mean of the prior 4 weekly crime_count values for the same segment.",
        "required_prior_weeks": 4,
    },
    {
        "baseline_method": "trailing_8_week_mean",
        "rule": "Use the arithmetic mean of the prior 8 weekly crime_count values for the same segment.",
        "required_prior_weeks": 8,
    },
    {
        "baseline_method": "previous_year_same_week",
        "rule": "Use the weekly crime_count from 52 weeks prior for the same segment.",
        "required_prior_weeks": 52,
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Phase 4 baseline weekly crime forecasts."
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
        "--model-dir",
        type=Path,
        default=None,
        help="Directory for lightweight baseline model artifacts.",
    )
    parser.add_argument(
        "--weekly-input",
        type=Path,
        default=None,
        help="Weekly aggregate input path. Defaults to data/processed/crime_weekly_area.parquet.",
    )
    parser.add_argument(
        "--predictions-output",
        type=Path,
        default=None,
        help="Output Parquet path. Defaults to data/processed/baseline_predictions.parquet.",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to data/processed/baseline_metrics.json.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=None,
        help="Output Markdown path. Defaults to reports/baseline_model_report.md.",
    )
    parser.add_argument(
        "--model-manifest-output",
        type=Path,
        default=None,
        help="Output model manifest JSON path. Defaults to models/baseline_forecast/model_manifest.json.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=max(1, min(4, os.cpu_count() or 1)),
        help="DuckDB worker threads.",
    )
    parser.add_argument(
        "--backtest-weeks",
        type=int,
        default=52,
        help="Number of recent weekly buckets to evaluate in the backtest.",
    )
    parser.add_argument(
        "--include-latest-week",
        action="store_true",
        help=(
            "Include the latest input week in backtesting. By default it is excluded "
            "because source extracts can contain a partial latest week."
        ),
    )
    parser.add_argument(
        "--top-k-fraction",
        type=float,
        default=0.10,
        help="Fraction of segment-week predictions used for high-volume capture scoring.",
    )
    parser.add_argument(
        "--hardest-segment-limit",
        type=int,
        default=15,
        help="Maximum hardest segment rows included in the report payload.",
    )
    parser.add_argument(
        "--min-hard-segment-actual-count",
        type=int,
        default=50,
        help="Minimum backtest actual count for a segment to appear in hardest-segment tables.",
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
            "Model manifest paths must be inside the project root."
        ) from exc
    return relative.as_posix()


def sql_string(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def sql_date(value: date) -> str:
    return f"DATE {sql_string(value.isoformat())}"


def ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


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


def format_value(value: Any, column: str | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if column and ("pct" in column or "rate" in column):
            return f"{value:,.4f}".rstrip("0").rstrip(".")
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
    body = [
        "| " + " | ".join(format_value(row.get(column), column) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def unlink_existing_outputs(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def validate_parquet_columns(con: Any, path: Path, required_columns: list[str]) -> None:
    rows = fetch_dicts(con, f"DESCRIBE SELECT * FROM read_parquet({sql_string(path)})")
    actual_columns = {row["column_name"] for row in rows}
    missing = [column for column in required_columns if column not in actual_columns]
    if missing:
        raise ValueError(f"{path} is missing required columns: {missing}")


def validate_weekly_source(con: Any, weekly_path: Path) -> None:
    validation = fetch_one(
        con,
        f"""
        SELECT
            COUNT(*) FILTER (WHERE week_start IS NULL)::BIGINT AS missing_week_start_rows,
            COUNT(*) FILTER (WHERE crime_count IS NULL)::BIGINT AS missing_crime_count_rows,
            COUNT(*) FILTER (WHERE crime_count < 0)::BIGINT AS negative_crime_count_rows
        FROM read_parquet({sql_string(weekly_path)})
        """,
    )
    invalid = {key: value for key, value in validation.items() if value}
    if invalid:
        raise ValueError(f"Weekly aggregate input has invalid rows: {invalid}")


def create_input_views(con: Any, weekly_path: Path) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW weekly_area AS
        SELECT
            week_start::DATE AS week_start,
            COALESCE(CAST(borough AS VARCHAR), 'UNKNOWN') AS borough,
            COALESCE(CAST(precinct AS VARCHAR), 'UNKNOWN') AS precinct,
            COALESCE(CAST(offense_type AS VARCHAR), 'UNKNOWN') AS offense_type,
            COALESCE(CAST(law_category AS VARCHAR), 'UNKNOWN') AS law_category,
            SUM(CAST(crime_count AS DOUBLE)) AS crime_count
        FROM read_parquet({sql_string(weekly_path)})
        GROUP BY 1, 2, 3, 4, 5
        """
    )


def build_input_summary(con: Any) -> dict[str, Any]:
    return fetch_one(
        con,
        """
        SELECT
            COUNT(*)::BIGINT AS weekly_aggregate_rows,
            SUM(crime_count)::BIGINT AS aggregate_event_count,
            MIN(week_start) AS min_week_start,
            MAX(week_start) AS max_week_start,
            COUNT(DISTINCT week_start)::BIGINT AS distinct_week_count,
            COUNT(DISTINCT borough || chr(31) || precinct || chr(31) || offense_type || chr(31) || law_category)::BIGINT
                AS segment_count
        FROM weekly_area
        """,
    )


def get_week_bounds(con: Any) -> tuple[date, date]:
    bounds = fetch_one(
        con,
        """
        SELECT
            MIN(week_start) AS min_week_start,
            MAX(week_start) AS max_week_start
        FROM weekly_area
        """,
    )
    if bounds["min_week_start"] is None or bounds["max_week_start"] is None:
        raise ValueError("Weekly aggregate input is empty.")
    return bounds["min_week_start"], bounds["max_week_start"]


def compute_backtest_window(
    min_week: date,
    max_week: date,
    *,
    backtest_weeks: int,
    include_latest_week: bool,
) -> tuple[date, date]:
    if backtest_weeks <= 0:
        raise ValueError("--backtest-weeks must be positive.")

    backtest_end = max_week if include_latest_week else max_week - timedelta(weeks=1)
    if backtest_end < min_week:
        backtest_end = max_week

    backtest_start = backtest_end - timedelta(weeks=backtest_weeks - 1)
    if backtest_start < min_week:
        backtest_start = min_week

    return backtest_start, backtest_end


def create_prediction_views(
    con: Any,
    *,
    min_week: date,
    max_week: date,
    forecast_week: date,
    backtest_start: date,
    backtest_end: date,
) -> None:
    con.execute(
        """
        CREATE OR REPLACE TEMP VIEW forecast_segments AS
        SELECT
            borough,
            precinct,
            offense_type,
            law_category,
            MIN(week_start) AS segment_first_week,
            MAX(week_start) AS segment_last_observed_week,
            COUNT(*)::BIGINT AS segment_observed_week_count,
            SUM(crime_count)::BIGINT AS segment_total_crime_count
        FROM weekly_area
        GROUP BY 1, 2, 3, 4
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW forecast_calendar AS
        SELECT week_start::DATE AS week_start
        FROM generate_series(
            {sql_date(min_week)},
            {sql_date(forecast_week)},
            INTERVAL '1 week'
        ) AS calendar(week_start)
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW baseline_panel AS
        SELECT
            c.week_start,
            s.borough,
            s.precinct,
            s.offense_type,
            s.law_category,
            CASE
                WHEN c.week_start <= {sql_date(max_week)} THEN COALESCE(w.crime_count, 0)
                ELSE NULL
            END AS history_crime_count,
            s.segment_first_week,
            s.segment_last_observed_week,
            s.segment_observed_week_count,
            s.segment_total_crime_count
        FROM forecast_segments s
        JOIN forecast_calendar c
            ON c.week_start BETWEEN s.segment_first_week AND {sql_date(forecast_week)}
        LEFT JOIN weekly_area w
            ON c.week_start = w.week_start
            AND s.borough = w.borough
            AND s.precinct = w.precinct
            AND s.offense_type = w.offense_type
            AND s.law_category = w.law_category
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW baseline_predictions_all AS
        WITH rolled AS (
            SELECT
                week_start,
                borough,
                precinct,
                offense_type,
                law_category,
                history_crime_count,
                LAG(history_crime_count, 1) OVER segment_window AS previous_week_raw,
                COUNT(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING
                ) AS trailing_4_week_count,
                AVG(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING
                ) AS trailing_4_week_mean_raw,
                COUNT(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING
                ) AS trailing_8_week_count,
                AVG(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING
                ) AS trailing_8_week_mean_raw,
                LAG(history_crime_count, 52) OVER segment_window AS previous_year_same_week_raw,
                segment_first_week,
                segment_last_observed_week,
                segment_observed_week_count,
                segment_total_crime_count
            FROM baseline_panel
            WINDOW segment_window AS (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
            )
        )
        SELECT
            week_start,
            borough,
            precinct,
            offense_type,
            law_category,
            CASE
                WHEN history_crime_count IS NULL THEN NULL
                ELSE ROUND(history_crime_count)::BIGINT
            END AS actual_crime_count,
            previous_week_raw AS previous_week,
            CASE
                WHEN trailing_4_week_count = 4 THEN trailing_4_week_mean_raw
                ELSE NULL
            END AS trailing_4_week_mean,
            CASE
                WHEN trailing_8_week_count = 8 THEN trailing_8_week_mean_raw
                ELSE NULL
            END AS trailing_8_week_mean,
            previous_year_same_week_raw AS previous_year_same_week,
            week_start BETWEEN {sql_date(backtest_start)} AND {sql_date(backtest_end)}
                AS is_backtest_week,
            week_start = {sql_date(forecast_week)} AS is_next_week_forecast,
            segment_first_week,
            segment_last_observed_week,
            segment_observed_week_count,
            segment_total_crime_count
        FROM rolled
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP VIEW baseline_predictions AS
        SELECT *
        FROM baseline_predictions_all
        WHERE is_backtest_week OR is_next_week_forecast
        """
    )


def write_predictions(con: Any, predictions_path: Path) -> None:
    columns_sql = ", ".join(ident(column) for column in PREDICTION_COLUMNS)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    unlink_existing_outputs([predictions_path])
    con.execute(
        f"""
        COPY (
            SELECT {columns_sql}
            FROM baseline_predictions
            ORDER BY week_start, borough, precinct, offense_type, law_category
        ) TO {sql_string(predictions_path)} (FORMAT PARQUET)
        """
    )


def baseline_methods_values_sql() -> str:
    rows = ", ".join(f"({sql_string(method)})" for method in BASELINE_METHODS)
    return f"(VALUES {rows}) AS methods(baseline_method)"


def baseline_long_sql() -> str:
    return "\nUNION ALL\n".join(
        f"""
        SELECT
            {sql_string(method)} AS baseline_method,
            week_start,
            borough,
            precinct,
            offense_type,
            law_category,
            actual_crime_count,
            {ident(method)} AS predicted_crime_count,
            is_backtest_week
        FROM baseline_predictions
        """
        for method in BASELINE_METHODS
    )


def build_metrics(con: Any, group_columns: list[str] | None = None) -> list[dict[str, Any]]:
    group_columns = group_columns or []
    method_values = baseline_methods_values_sql()
    long_sql = baseline_long_sql()

    if group_columns:
        group_select = ", ".join(ident(column) for column in group_columns)
        group_join = " AND ".join(
            f"groups.{ident(column)} = agg.{ident(column)}" for column in group_columns
        )
        group_order = ", ".join(f"groups.{ident(column)}" for column in group_columns)
        select_group_columns = ",\n            ".join(
            f"groups.{ident(column)}" for column in group_columns
        )
        agg_group_columns = ", ".join(ident(column) for column in group_columns)
        sql = f"""
        WITH methods AS (
            SELECT baseline_method FROM {method_values}
        ),
        groups AS (
            SELECT
                {group_select},
                COUNT(*)::BIGINT AS total_backtest_rows,
                SUM(actual_crime_count)::BIGINT AS total_actual_event_count
            FROM baseline_predictions
            WHERE is_backtest_week
            GROUP BY {group_select}
        ),
        long_predictions AS (
            {long_sql}
        ),
        eligible AS (
            SELECT
                *,
                ABS(predicted_crime_count - actual_crime_count) AS abs_error,
                POWER(predicted_crime_count - actual_crime_count, 2) AS squared_error
            FROM long_predictions
            WHERE is_backtest_week
                AND actual_crime_count IS NOT NULL
                AND predicted_crime_count IS NOT NULL
        ),
        agg AS (
            SELECT
                baseline_method,
                {agg_group_columns},
                COUNT(*)::BIGINT AS prediction_count,
                SUM(actual_crime_count)::BIGINT AS actual_event_count,
                ROUND(AVG(abs_error), 4) AS mae,
                ROUND(SQRT(AVG(squared_error)), 4) AS rmse,
                ROUND(
                    SUM(abs_error * actual_crime_count) / NULLIF(SUM(actual_crime_count), 0),
                    4
                ) AS weighted_mae
            FROM eligible
            GROUP BY baseline_method, {agg_group_columns}
        )
        SELECT
            methods.baseline_method,
            {select_group_columns},
            COALESCE(agg.prediction_count, 0)::BIGINT AS prediction_count,
            groups.total_backtest_rows,
            ROUND(
                COALESCE(agg.prediction_count, 0) * 100.0 / NULLIF(groups.total_backtest_rows, 0),
                2
            ) AS prediction_coverage_pct,
            COALESCE(agg.actual_event_count, 0)::BIGINT AS actual_event_count,
            groups.total_actual_event_count,
            agg.mae,
            agg.rmse,
            agg.weighted_mae
        FROM groups
        CROSS JOIN methods
        LEFT JOIN agg
            ON methods.baseline_method = agg.baseline_method
            AND {group_join}
        ORDER BY methods.baseline_method, {group_order}
        """
    else:
        sql = f"""
        WITH methods AS (
            SELECT baseline_method FROM {method_values}
        ),
        groups AS (
            SELECT
                COUNT(*)::BIGINT AS total_backtest_rows,
                SUM(actual_crime_count)::BIGINT AS total_actual_event_count
            FROM baseline_predictions
            WHERE is_backtest_week
        ),
        long_predictions AS (
            {long_sql}
        ),
        eligible AS (
            SELECT
                *,
                ABS(predicted_crime_count - actual_crime_count) AS abs_error,
                POWER(predicted_crime_count - actual_crime_count, 2) AS squared_error
            FROM long_predictions
            WHERE is_backtest_week
                AND actual_crime_count IS NOT NULL
                AND predicted_crime_count IS NOT NULL
        ),
        agg AS (
            SELECT
                baseline_method,
                COUNT(*)::BIGINT AS prediction_count,
                SUM(actual_crime_count)::BIGINT AS actual_event_count,
                ROUND(AVG(abs_error), 4) AS mae,
                ROUND(SQRT(AVG(squared_error)), 4) AS rmse,
                ROUND(
                    SUM(abs_error * actual_crime_count) / NULLIF(SUM(actual_crime_count), 0),
                    4
                ) AS weighted_mae
            FROM eligible
            GROUP BY baseline_method
        )
        SELECT
            methods.baseline_method,
            COALESCE(agg.prediction_count, 0)::BIGINT AS prediction_count,
            groups.total_backtest_rows,
            ROUND(
                COALESCE(agg.prediction_count, 0) * 100.0 / NULLIF(groups.total_backtest_rows, 0),
                2
            ) AS prediction_coverage_pct,
            COALESCE(agg.actual_event_count, 0)::BIGINT AS actual_event_count,
            groups.total_actual_event_count,
            agg.mae,
            agg.rmse,
            agg.weighted_mae
        FROM methods
        CROSS JOIN groups
        LEFT JOIN agg
            ON methods.baseline_method = agg.baseline_method
        ORDER BY methods.baseline_method
        """
    return normalize_rows(fetch_dicts(con, sql))


def build_top_k_capture(con: Any, top_k_fraction: float) -> list[dict[str, Any]]:
    method_values = baseline_methods_values_sql()
    long_sql = baseline_long_sql()
    return normalize_rows(
        fetch_dicts(
            con,
            f"""
            WITH methods AS (
                SELECT baseline_method FROM {method_values}
            ),
            long_predictions AS (
                {long_sql}
            ),
            eligible AS (
                SELECT *
                FROM long_predictions
                WHERE is_backtest_week
                    AND actual_crime_count IS NOT NULL
                    AND predicted_crime_count IS NOT NULL
            ),
            ranked AS (
                SELECT
                    *,
                    COUNT(*) OVER (PARTITION BY baseline_method, week_start) AS rows_in_week,
                    ROW_NUMBER() OVER (
                        PARTITION BY baseline_method, week_start
                        ORDER BY actual_crime_count DESC, borough, precinct, offense_type, law_category
                    ) AS actual_rank,
                    ROW_NUMBER() OVER (
                        PARTITION BY baseline_method, week_start
                        ORDER BY predicted_crime_count DESC, borough, precinct, offense_type, law_category
                    ) AS predicted_rank
                FROM eligible
            ),
            ranked_with_k AS (
                SELECT
                    *,
                    GREATEST(1, CEIL(rows_in_week * {float(top_k_fraction)}))::BIGINT AS top_k_count
                FROM ranked
            ),
            weekly_capture AS (
                SELECT
                    baseline_method,
                    week_start,
                    MAX(top_k_count)::BIGINT AS top_k_count,
                    SUM(actual_crime_count) FILTER (
                        WHERE actual_rank <= top_k_count
                    )::BIGINT AS actual_top_k_event_count,
                    SUM(actual_crime_count) FILTER (
                        WHERE actual_rank <= top_k_count
                            AND predicted_rank <= top_k_count
                    )::BIGINT AS captured_top_k_event_count
                FROM ranked_with_k
                GROUP BY 1, 2
            )
            SELECT
                methods.baseline_method,
                {float(top_k_fraction)} AS top_k_fraction,
                COUNT(weekly_capture.week_start)::BIGINT AS evaluated_weeks,
                ROUND(AVG(weekly_capture.top_k_count), 2) AS avg_weekly_top_k_rows,
                SUM(weekly_capture.actual_top_k_event_count)::BIGINT
                    AS actual_top_k_event_count,
                SUM(weekly_capture.captured_top_k_event_count)::BIGINT
                    AS captured_top_k_event_count,
                ROUND(
                    SUM(weekly_capture.captured_top_k_event_count) * 1.0
                        / NULLIF(SUM(weekly_capture.actual_top_k_event_count), 0),
                    4
                ) AS top_k_capture_rate
            FROM methods
            LEFT JOIN weekly_capture
                ON methods.baseline_method = weekly_capture.baseline_method
            GROUP BY methods.baseline_method
            ORDER BY methods.baseline_method
            """,
        )
    )


def determine_best_baseline(overall_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        row for row in overall_metrics
        if row.get("prediction_count", 0) > 0 and row.get("mae") is not None
    ]
    if not candidates:
        return {}
    return min(
        candidates,
        key=lambda row: (
            row["mae"],
            row["weighted_mae"] if row.get("weighted_mae") is not None else float("inf"),
            -row.get("prediction_coverage_pct", 0),
            row["baseline_method"],
        ),
    )


def build_hardest_segments(
    con: Any,
    *,
    baseline_method: str,
    group_columns: list[str],
    min_actual_count: int,
    limit: int,
) -> list[dict[str, Any]]:
    if baseline_method not in BASELINE_METHODS:
        raise ValueError(f"Unsupported baseline method: {baseline_method}")

    group_sql = ", ".join(ident(column) for column in group_columns)
    return normalize_rows(
        fetch_dicts(
            con,
            f"""
            WITH scored AS (
                SELECT
                    {group_sql},
                    actual_crime_count,
                    {ident(baseline_method)} AS predicted_crime_count,
                    ABS({ident(baseline_method)} - actual_crime_count) AS abs_error,
                    POWER({ident(baseline_method)} - actual_crime_count, 2) AS squared_error
                FROM baseline_predictions
                WHERE is_backtest_week
                    AND actual_crime_count IS NOT NULL
                    AND {ident(baseline_method)} IS NOT NULL
            )
            SELECT
                {group_sql},
                COUNT(*)::BIGINT AS prediction_count,
                SUM(actual_crime_count)::BIGINT AS actual_event_count,
                ROUND(AVG(abs_error), 4) AS mae,
                ROUND(SQRT(AVG(squared_error)), 4) AS rmse
            FROM scored
            GROUP BY {group_sql}
            HAVING SUM(actual_crime_count) >= {int(min_actual_count)}
            ORDER BY mae DESC, rmse DESC, actual_event_count DESC, {group_sql}
            LIMIT {int(limit)}
            """,
        )
    )


def build_record_counts(con: Any) -> dict[str, Any]:
    return fetch_one(
        con,
        """
        SELECT
            COUNT(*)::BIGINT AS output_rows,
            COUNT(*) FILTER (WHERE is_backtest_week)::BIGINT AS backtest_rows,
            COUNT(*) FILTER (WHERE is_next_week_forecast)::BIGINT AS next_week_forecast_rows,
            COUNT(DISTINCT borough || chr(31) || precinct || chr(31) || offense_type || chr(31) || law_category)::BIGINT
                AS output_segment_count,
            SUM(actual_crime_count) FILTER (WHERE is_backtest_week)::BIGINT
                AS backtest_actual_event_count
        FROM baseline_predictions
        """,
    )


def validate_baseline_metrics_payload(payload: dict[str, Any]) -> None:
    missing_sections = [
        section for section in BASELINE_METRICS_REQUIRED_SECTIONS if section not in payload
    ]
    if missing_sections:
        raise ValueError(f"Baseline metrics payload is missing required sections: {missing_sections}")

    columns_used = set(payload.get("forecast_columns_used") or [])
    sensitive_columns = set(payload.get("ethics", {}).get("sensitive_columns_excluded") or [])
    overlap = columns_used.intersection(sensitive_columns)
    if overlap:
        raise ValueError(f"Sensitive columns cannot be used in baseline forecasting: {sorted(overlap)}")

    if payload.get("prediction_columns") != PREDICTION_COLUMNS:
        raise ValueError("Baseline metrics payload has an unexpected prediction column contract.")

    metrics = payload.get("metrics") or {}
    for key in ["overall", "by_borough", "by_offense_type", "by_borough_offense"]:
        if key not in metrics:
            raise ValueError(f"Baseline metrics payload is missing metrics section: {key}")


def build_metrics_payload(
    con: Any,
    *,
    inputs: dict[str, Path],
    outputs: dict[str, Path],
    input_summary: dict[str, Any],
    backtest_start: date,
    backtest_end: date,
    forecast_week: date,
    backtest_weeks: int,
    include_latest_week: bool,
    top_k_fraction: float,
    hardest_segment_limit: int,
    min_hard_segment_actual_count: int,
) -> dict[str, Any]:
    overall_metrics = build_metrics(con)
    best_baseline = determine_best_baseline(overall_metrics)
    best_method = best_baseline.get("baseline_method") or "previous_week"
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "Phase 4 - Baseline Forecast Model",
        "inputs": {name: str(path) for name, path in inputs.items()},
        "outputs": {name: str(path) for name, path in outputs.items()},
        "forecast_columns_used": FORECAST_COLUMNS_USED,
        "prediction_columns": PREDICTION_COLUMNS,
        "forecast_config": {
            "target": "next-week crime_count by week_start, borough, precinct, offense_type, law_category",
            "backtest_weeks_requested": backtest_weeks,
            "include_latest_week_in_backtest": include_latest_week,
            "latest_week_exclusion_reason": (
                None if include_latest_week else "Latest source week can be partial in fixed-date extracts."
            ),
            "zero_fill_rule": (
                "Missing weekly rows are treated as zero crime_count after a segment's first observed week."
            ),
            "baseline_methods": BASELINE_METHODS,
            "baseline_model_rules": BASELINE_MODEL_RULES,
            "weighted_mae_definition": (
                "SUM(abs_error * actual_crime_count) / SUM(actual_crime_count) "
                "over rows with a prediction."
            ),
            "top_k_fraction": top_k_fraction,
        },
        "analysis_window": {
            **input_summary,
            "backtest_start_week": backtest_start,
            "backtest_end_week": backtest_end,
            "next_week_forecast_week": forecast_week,
        },
        "record_counts": build_record_counts(con),
        "metrics": {
            "overall": overall_metrics,
            "by_borough": build_metrics(con, ["borough"]),
            "by_offense_type": build_metrics(con, ["offense_type"]),
            "by_borough_offense": build_metrics(con, ["borough", "offense_type"]),
        },
        "top_k_capture": build_top_k_capture(con, top_k_fraction),
        "hardest_segments": {
            "baseline_method": best_method,
            "min_actual_count": min_hard_segment_actual_count,
            "borough_offense": build_hardest_segments(
                con,
                baseline_method=best_method,
                group_columns=["borough", "offense_type"],
                min_actual_count=min_hard_segment_actual_count,
                limit=hardest_segment_limit,
            ),
            "precinct_offense": build_hardest_segments(
                con,
                baseline_method=best_method,
                group_columns=["borough", "precinct", "offense_type"],
                min_actual_count=min_hard_segment_actual_count,
                limit=hardest_segment_limit,
            ),
        },
        "best_baseline": best_baseline,
        "ethics": {
            "sensitive_columns_excluded": SENSITIVE_COLUMNS,
            "note": (
                "Baseline forecasts use only aggregate weekly counts and segment keys. "
                "They do not use suspect or victim demographics and do not create "
                "person-level predictions or enforcement recommendations."
            ),
        },
    }
    validate_baseline_metrics_payload(payload)
    return payload


def write_metrics_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, default=json_default)
        file.write("\n")


def build_model_manifest(
    payload: dict[str, Any], *, project_root: Path
) -> dict[str, Any]:
    """Build a small model artifact for deterministic baseline formulas."""
    return {
        "artifact_type": "baseline_forecast_model",
        "artifact_version": 1,
        "generated_at_utc": payload["generated_at_utc"],
        "phase": payload["phase"],
        "source_script": "src/models/build_baseline_forecast.py",
        "training_input": repository_relative_path(
            project_root, payload["inputs"]["weekly_area"]
        ),
        "prediction_output": repository_relative_path(
            project_root, payload["outputs"]["predictions"]
        ),
        "metrics_output": repository_relative_path(
            project_root, payload["outputs"]["metrics"]
        ),
        "report_output": repository_relative_path(
            project_root, payload["outputs"]["report"]
        ),
        "target": payload["forecast_config"]["target"],
        "segment_keys": [
            "borough",
            "precinct",
            "offense_type",
            "law_category",
        ],
        "training_window": {
            "min_week_start": payload["analysis_window"]["min_week_start"],
            "max_week_start": payload["analysis_window"]["max_week_start"],
            "segment_count": payload["analysis_window"]["segment_count"],
        },
        "backtest_window": {
            "backtest_start_week": payload["analysis_window"]["backtest_start_week"],
            "backtest_end_week": payload["analysis_window"]["backtest_end_week"],
            "backtest_rows": payload["record_counts"]["backtest_rows"],
        },
        "forecast_week": payload["analysis_window"]["next_week_forecast_week"],
        "baseline_model_rules": payload["forecast_config"]["baseline_model_rules"],
        "selected_baseline": payload.get("best_baseline") or {},
        "overall_metrics": payload["metrics"]["overall"],
        "leakage_controls": {
            "split_type": "time_based_backtest",
            "target_week_excluded_from_features": True,
            "latest_week_excluded_from_backtest": (
                not payload["forecast_config"]["include_latest_week_in_backtest"]
            ),
            "zero_fill_rule": payload["forecast_config"]["zero_fill_rule"],
        },
        "feature_policy": {
            "forecast_columns_used": payload["forecast_columns_used"],
            "sensitive_columns_excluded": payload["ethics"]["sensitive_columns_excluded"],
            "person_level_prediction": False,
            "enforcement_recommendations": False,
        },
    }


def write_model_manifest(
    path: Path, payload: dict[str, Any], *, project_root: Path
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_model_manifest(payload, project_root=project_root)
    with path.open("w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, default=json_default)
        file.write("\n")


def rows_for_baseline(rows: list[dict[str, Any]], baseline_method: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("baseline_method") == baseline_method]


def write_baseline_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    best = payload.get("best_baseline") or {}
    best_method = best.get("baseline_method", "")
    by_borough = rows_for_baseline(payload["metrics"]["by_borough"], best_method)
    by_offense = rows_for_baseline(payload["metrics"]["by_offense_type"], best_method)
    by_offense = sorted(
        by_offense,
        key=lambda row: (
            row.get("mae") is None,
            -(row.get("mae") or 0),
            -(row.get("actual_event_count") or 0),
            row.get("offense_type") or "",
        ),
    )

    lines = [
        "# NYPD Complaint Data Historic - Baseline Forecast Model",
        "",
        f"Generated at UTC: `{payload['generated_at_utc']}`",
        "",
        "## Scope",
        "",
        (
            "This Phase 4 baseline reads `crime_weekly_area.parquet` and predicts the "
            "next weekly `crime_count` for each borough, precinct, offense type, and "
            "law category segment. It implements explainable historical baselines only; "
            "no Phase 5 machine-learning model is trained."
        ),
        "",
        "## Inputs and Outputs",
        "",
        "\n".join(f"- Input {name}: `{path}`" for name, path in payload["inputs"].items()),
        "\n".join(f"- Output {name}: `{path}`" for name, path in payload["outputs"].items()),
        "",
        "## Forecast Setup",
        "",
        markdown_table(
            [
                {
                    "min_week_start": payload["analysis_window"]["min_week_start"],
                    "max_week_start": payload["analysis_window"]["max_week_start"],
                    "backtest_start_week": payload["analysis_window"]["backtest_start_week"],
                    "backtest_end_week": payload["analysis_window"]["backtest_end_week"],
                    "next_week_forecast_week": payload["analysis_window"]["next_week_forecast_week"],
                    "segment_count": payload["analysis_window"]["segment_count"],
                    "backtest_rows": payload["record_counts"]["backtest_rows"],
                    "next_week_forecast_rows": payload["record_counts"]["next_week_forecast_rows"],
                }
            ]
        ),
        "",
        "Missing weekly rows are zero-filled after a segment first appears. All baseline "
        "windows exclude the target week, so backtest predictions use historical weeks only.",
        "",
        "## Baseline Definitions",
        "",
        "- `previous_week`: prior week's count.",
        "- `trailing_4_week_mean`: mean of the prior 4 weekly counts, emitted only when all 4 prior weeks exist in the zero-filled segment panel.",
        "- `trailing_8_week_mean`: mean of the prior 8 weekly counts, emitted only when all 8 prior weeks exist in the zero-filled segment panel.",
        "- `previous_year_same_week`: count from 52 weeks prior, emitted only when that history exists.",
        "",
        "## Overall Backtest Metrics",
        "",
        markdown_table(
            payload["metrics"]["overall"],
            [
                "baseline_method",
                "prediction_count",
                "total_backtest_rows",
                "prediction_coverage_pct",
                "actual_event_count",
                "mae",
                "rmse",
                "weighted_mae",
            ],
        ),
        "",
        "Weighted MAE uses actual `crime_count` as the row weight over rows where the baseline produced a prediction.",
        "",
        "## Top-K High-Volume Capture",
        "",
        markdown_table(payload["top_k_capture"]),
        "",
        "Top-K capture measures how much actual crime volume in the true highest-volume "
        "segment-weeks is captured by the baseline's predicted highest-volume segment-weeks "
        "for the same week.",
        "",
        "## Best Baseline",
        "",
        (
            f"`{best_method}` has the lowest overall MAE "
            f"({format_value(best.get('mae'))}) with RMSE {format_value(best.get('rmse'))} "
            f"and {format_value(best.get('prediction_coverage_pct'))}% prediction coverage."
            if best
            else "No baseline produced evaluable predictions."
        ),
        "",
        "## Borough Metrics for Best Baseline",
        "",
        markdown_table(
            by_borough,
            [
                "baseline_method",
                "borough",
                "prediction_count",
                "prediction_coverage_pct",
                "actual_event_count",
                "mae",
                "rmse",
                "weighted_mae",
            ],
        ),
        "",
        "## Hardest Offense Types for Best Baseline",
        "",
        markdown_table(
            by_offense[:15],
            [
                "baseline_method",
                "offense_type",
                "prediction_count",
                "actual_event_count",
                "mae",
                "rmse",
                "weighted_mae",
            ],
        ),
        "",
        "## Hardest Borough/Offense Segments",
        "",
        (
            "Rows are filtered to segments with at least "
            f"{payload['hardest_segments']['min_actual_count']} actual backtest complaints."
        ),
        "",
        markdown_table(payload["hardest_segments"]["borough_offense"]),
        "",
        "## Hardest Precinct/Offense Segments",
        "",
        markdown_table(payload["hardest_segments"]["precinct_offense"]),
        "",
        "## Interpretation",
        "",
        (
            f"- Best overall baseline: `{best_method}` by MAE. Lower RMSE and weighted MAE "
            "should also be reviewed before treating this as the operational benchmark."
            if best
            else "- No best baseline could be selected because there were no evaluable predictions."
        ),
        (
            "- The hardest segments are high-volume borough/offense and precinct/offense "
            "series with volatile week-to-week counts; these are the first places Phase 5 "
            "should test explicit trend, seasonality, holiday, and anomaly features."
        ),
        (
            "- `previous_year_same_week` has lower coverage for newer or sparse segments "
            "because it requires at least 52 prior zero-filled weekly observations."
        ),
        "",
        "## Limitations Before Phase 5 ML",
        "",
        "- Missing weeks are inferred as zero after first observation because the Phase 2 aggregate stores observed event groups, not a complete zero-filled panel.",
        "- The latest source week is excluded from backtesting by default because it may be partial; the next-week forecast still uses it as the latest available observation.",
        "- Baselines do not model holidays, reporting delays, structural breaks, spatial spillover, or long-run trend shifts.",
        "- Forecast intervals are not produced in Phase 4; Phase 5 should add uncertainty estimates before dashboard use.",
        "",
        "## Ethics Constraint",
        "",
        (
            "Suspect and victim demographic fields are excluded. These outputs are aggregate "
            "trend forecasts and must not be interpreted as person-level predictions or "
            "automatic enforcement recommendations."
        ),
        "",
        "Excluded fields:",
        "",
        "\n".join(f"- `{column}`" for column in payload["ethics"]["sensitive_columns_excluded"]),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    if args.threads <= 0:
        raise ValueError("--threads must be positive.")
    if args.top_k_fraction <= 0 or args.top_k_fraction > 1:
        raise ValueError("--top-k-fraction must be in the range (0, 1].")
    if args.hardest_segment_limit <= 0:
        raise ValueError("--hardest-segment-limit must be positive.")
    if args.min_hard_segment_actual_count < 0:
        raise ValueError("--min-hard-segment-actual-count cannot be negative.")

    project_root = args.project_root.resolve()
    processed_dir = resolve_path(project_root, args.processed_dir, DEFAULT_PROCESSED_DIR)
    reports_dir = resolve_path(project_root, args.reports_dir, DEFAULT_REPORTS_DIR)
    model_dir = resolve_path(project_root, args.model_dir, DEFAULT_MODEL_DIR)
    weekly_path = resolve_path(
        project_root,
        args.weekly_input,
        DEFAULT_PROCESSED_DIR / WEEKLY_FILE,
    )
    predictions_path = resolve_path(
        project_root,
        args.predictions_output,
        DEFAULT_PROCESSED_DIR / PREDICTIONS_FILE,
    )
    metrics_path = resolve_path(
        project_root,
        args.metrics_output,
        DEFAULT_PROCESSED_DIR / METRICS_FILE,
    )
    report_path = resolve_path(
        project_root,
        args.report_output,
        DEFAULT_REPORTS_DIR / REPORT_FILE,
    )
    model_manifest_path = resolve_path(
        project_root,
        args.model_manifest_output,
        DEFAULT_MODEL_DIR / MODEL_MANIFEST_FILE,
    )

    if not weekly_path.exists():
        raise FileNotFoundError(f"Missing weekly aggregate input: {weekly_path}")

    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    model_manifest_path.parent.mkdir(parents=True, exist_ok=True)

    duckdb = require_duckdb()
    con = duckdb.connect(database=":memory:")
    con.execute(f"PRAGMA threads={int(args.threads)}")

    print("Validating weekly aggregate schema.")
    validate_parquet_columns(con, weekly_path, WEEKLY_REQUIRED_COLUMNS)
    validate_weekly_source(con, weekly_path)

    print("Creating weekly aggregate view.")
    create_input_views(con, weekly_path)
    input_summary = build_input_summary(con)
    min_week, max_week = get_week_bounds(con)
    forecast_week = max_week + timedelta(weeks=1)
    backtest_start, backtest_end = compute_backtest_window(
        min_week,
        max_week,
        backtest_weeks=args.backtest_weeks,
        include_latest_week=args.include_latest_week,
    )

    print("Building leakage-safe baseline predictions.")
    create_prediction_views(
        con,
        min_week=min_week,
        max_week=max_week,
        forecast_week=forecast_week,
        backtest_start=backtest_start,
        backtest_end=backtest_end,
    )

    print(f"Writing baseline predictions: {predictions_path}")
    write_predictions(con, predictions_path)

    outputs = {
        "model_manifest": model_manifest_path,
        "predictions": predictions_path,
        "metrics": metrics_path,
        "report": report_path,
    }
    inputs = {"weekly_area": weekly_path}

    print("Building baseline metrics payload.")
    payload = build_metrics_payload(
        con,
        inputs=inputs,
        outputs=outputs,
        input_summary=input_summary,
        backtest_start=backtest_start,
        backtest_end=backtest_end,
        forecast_week=forecast_week,
        backtest_weeks=args.backtest_weeks,
        include_latest_week=args.include_latest_week,
        top_k_fraction=args.top_k_fraction,
        hardest_segment_limit=args.hardest_segment_limit,
        min_hard_segment_actual_count=args.min_hard_segment_actual_count,
    )

    print(f"Writing baseline metrics JSON: {metrics_path}")
    write_metrics_json(metrics_path, payload)
    print(f"Writing baseline model manifest: {model_manifest_path}")
    write_model_manifest(model_manifest_path, payload, project_root=project_root)
    print(f"Writing baseline model report: {report_path}")
    write_baseline_report(report_path, payload)
    print("Phase 4 baseline forecast model complete.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Interrupted.")

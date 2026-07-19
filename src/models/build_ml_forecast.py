#!/usr/bin/env python3
"""Build Phase 5 weekly ML forecasts.

This script reads the Phase 2 weekly aggregate table and Phase 4 baseline
manifest, then writes:

    reports/ml_model_report.md
    data/processed/ml_predictions.parquet
    data/processed/ml_metrics.json
    models/weekly_forecast/model_manifest.json

The initial ML model is intentionally lightweight because this repository does
not require scikit-learn. It uses DuckDB to build leakage-safe lag and rolling
features, then selects a small linear lag-ensemble model on a validation window
that ends before the Phase 4 backtest window starts. No random splits are used.
No suspect or victim demographic fields are read or used.

Example from the repository root:

    .venv/bin/python src/models/build_ml_forecast.py
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
DEFAULT_MODEL_DIR = Path("models/weekly_forecast")
DEFAULT_BASELINE_MODEL_DIR = Path("models/baseline_forecast")

WEEKLY_FILE = "crime_weekly_area.parquet"
BASELINE_MANIFEST_FILE = "model_manifest.json"
PREDICTIONS_FILE = "ml_predictions.parquet"
METRICS_FILE = "ml_metrics.json"
REPORT_FILE = "ml_model_report.md"
MODEL_MANIFEST_FILE = "model_manifest.json"

MODEL_NAME = "duckdb_lag_ensemble_regressor"
MODEL_VERSION = 1
SELECTION_OBJECTIVE = "validation_rmse"

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

SEGMENT_KEYS = [
    "borough",
    "precinct",
    "offense_type",
    "law_category",
]

MODEL_FEATURE_COLUMNS = [
    "lag_1_week_count",
    "lag_52_week_count",
    "trailing_4_week_mean",
    "trailing_8_week_mean",
]

ENGINEERED_FEATURE_COLUMNS = [
    "year",
    "month",
    "iso_week",
    "quarter",
    "week_index",
    "lag_1_week_count",
    "lag_2_week_count",
    "lag_4_week_count",
    "lag_8_week_count",
    "lag_52_week_count",
    "trailing_4_week_mean",
    "trailing_4_week_std",
    "trailing_4_week_min",
    "trailing_4_week_max",
    "trailing_8_week_mean",
    "trailing_8_week_std",
    "trailing_8_week_min",
    "trailing_8_week_max",
    "segment_prior_week_count",
    "segment_prior_total_count",
    "segment_prior_mean_count",
]

PREDICTION_COLUMNS = [
    "week_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "actual_crime_count",
    "predicted_crime_count",
    "ml_model_name",
    "lag_1_week_count",
    "lag_52_week_count",
    "trailing_4_week_mean",
    "trailing_8_week_mean",
    "segment_prior_mean_count",
    "is_backtest_week",
    "is_next_week_forecast",
    "segment_first_week",
    "segment_last_observed_week",
    "segment_observed_week_count",
    "segment_total_crime_count",
]

ML_METRICS_REQUIRED_SECTIONS = [
    "generated_at_utc",
    "phase",
    "inputs",
    "outputs",
    "forecast_columns_used",
    "engineered_feature_columns",
    "model_feature_columns",
    "prediction_columns",
    "model_config",
    "analysis_window",
    "record_counts",
    "metrics",
    "baseline_comparison",
    "hardest_segments",
    "ethics",
]

ALPHA_GRID = [round(value * 0.05, 2) for value in range(-2, 11)]
BETA_GRID = [-0.10, -0.05, 0.0, 0.05, 0.10]
GAMMA_GRID = [-0.05, 0.0, 0.05]
SHRINKAGE_GRID = [0.95, 1.0, 1.05]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Phase 5 ML weekly crime forecasts."
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
        help="Directory containing processed Parquet outputs.",
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
        help="Directory for Phase 5 model artifacts.",
    )
    parser.add_argument(
        "--weekly-input",
        type=Path,
        default=None,
        help="Weekly aggregate input path. Defaults to data/processed/crime_weekly_area.parquet.",
    )
    parser.add_argument(
        "--baseline-manifest",
        type=Path,
        default=None,
        help="Phase 4 baseline manifest. Defaults to models/baseline_forecast/model_manifest.json.",
    )
    parser.add_argument(
        "--predictions-output",
        type=Path,
        default=None,
        help="Output Parquet path. Defaults to data/processed/ml_predictions.parquet.",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to data/processed/ml_metrics.json.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=None,
        help="Output Markdown path. Defaults to reports/ml_model_report.md.",
    )
    parser.add_argument(
        "--model-manifest-output",
        type=Path,
        default=None,
        help="Output model manifest JSON path. Defaults to models/weekly_forecast/model_manifest.json.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=max(1, min(4, os.cpu_count() or 1)),
        help="DuckDB worker threads.",
    )
    parser.add_argument(
        "--validation-weeks",
        type=int,
        default=52,
        help="Weeks immediately before the backtest window used for parameter selection.",
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
            "Missing dependency: duckdb. Run in the local virtual environment "
            "or install the repository requirements."
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


def repository_relative_paths(
    project_root: Path, values: dict[str, Path]
) -> dict[str, str]:
    """Normalize a named path collection for portable metrics and reports."""
    return {
        name: repository_relative_path(project_root, path)
        for name, path in values.items()
    }


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


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def parse_iso_date(value: Any, field_name: str) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"Expected ISO date string for {field_name}, got {value!r}.")
    return date.fromisoformat(value)


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


def compute_default_backtest_window(
    min_week: date,
    max_week: date,
    *,
    backtest_weeks: int = 52,
) -> tuple[date, date]:
    backtest_end = max_week - timedelta(weeks=1)
    if backtest_end < min_week:
        backtest_end = max_week
    backtest_start = backtest_end - timedelta(weeks=backtest_weeks - 1)
    if backtest_start < min_week:
        backtest_start = min_week
    return backtest_start, backtest_end


def get_backtest_window_from_baseline(
    baseline_manifest: dict[str, Any],
    *,
    min_week: date,
    max_week: date,
) -> tuple[date, date]:
    window = baseline_manifest.get("backtest_window") or {}
    try:
        backtest_start = parse_iso_date(window["backtest_start_week"], "backtest_start_week")
        backtest_end = parse_iso_date(window["backtest_end_week"], "backtest_end_week")
    except (KeyError, ValueError):
        return compute_default_backtest_window(min_week, max_week)

    if backtest_start < min_week or backtest_end > max_week or backtest_start > backtest_end:
        return compute_default_backtest_window(min_week, max_week)
    return backtest_start, backtest_end


def compute_validation_window(
    min_week: date,
    backtest_start: date,
    *,
    validation_weeks: int,
) -> tuple[date, date]:
    if validation_weeks <= 0:
        raise ValueError("--validation-weeks must be positive.")

    validation_end = backtest_start - timedelta(weeks=1)
    if validation_end < min_week:
        raise ValueError("Backtest window starts before there is room for validation.")

    validation_start = validation_end - timedelta(weeks=validation_weeks - 1)
    if validation_start < min_week:
        validation_start = min_week
    return validation_start, validation_end


def create_ml_feature_views(
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
        CREATE OR REPLACE TEMP VIEW ml_panel AS
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
        CREATE OR REPLACE TEMP VIEW ml_feature_rows AS
        WITH rolled AS (
            SELECT
                *,
                LAG(history_crime_count, 1) OVER segment_window AS lag_1_raw,
                LAG(history_crime_count, 2) OVER segment_window AS lag_2_raw,
                LAG(history_crime_count, 4) OVER segment_window AS lag_4_raw,
                LAG(history_crime_count, 8) OVER segment_window AS lag_8_raw,
                LAG(history_crime_count, 52) OVER segment_window AS lag_52_raw,
                AVG(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING
                ) AS trailing_4_mean_raw,
                STDDEV_POP(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING
                ) AS trailing_4_std_raw,
                MIN(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING
                ) AS trailing_4_min_raw,
                MAX(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING
                ) AS trailing_4_max_raw,
                AVG(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING
                ) AS trailing_8_mean_raw,
                STDDEV_POP(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING
                ) AS trailing_8_std_raw,
                MIN(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING
                ) AS trailing_8_min_raw,
                MAX(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING
                ) AS trailing_8_max_raw,
                COUNT(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ) AS segment_prior_week_count,
                SUM(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ) AS segment_prior_total_raw,
                AVG(history_crime_count) OVER (
                    PARTITION BY borough, precinct, offense_type, law_category
                    ORDER BY week_start
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ) AS segment_prior_mean_raw
            FROM ml_panel
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
            EXTRACT('year' FROM week_start)::DOUBLE AS year,
            EXTRACT('month' FROM week_start)::DOUBLE AS month,
            EXTRACT('week' FROM week_start)::DOUBLE AS iso_week,
            EXTRACT('quarter' FROM week_start)::DOUBLE AS quarter,
            date_diff('week', {sql_date(min_week)}, week_start)::DOUBLE AS week_index,
            COALESCE(lag_1_raw, segment_prior_mean_raw, 0)::DOUBLE AS lag_1_week_count,
            COALESCE(lag_2_raw, segment_prior_mean_raw, 0)::DOUBLE AS lag_2_week_count,
            COALESCE(lag_4_raw, segment_prior_mean_raw, 0)::DOUBLE AS lag_4_week_count,
            COALESCE(lag_8_raw, segment_prior_mean_raw, 0)::DOUBLE AS lag_8_week_count,
            COALESCE(lag_52_raw, segment_prior_mean_raw, 0)::DOUBLE AS lag_52_week_count,
            COALESCE(trailing_4_mean_raw, segment_prior_mean_raw, 0)::DOUBLE
                AS trailing_4_week_mean,
            COALESCE(trailing_4_std_raw, 0)::DOUBLE AS trailing_4_week_std,
            COALESCE(trailing_4_min_raw, segment_prior_mean_raw, 0)::DOUBLE
                AS trailing_4_week_min,
            COALESCE(trailing_4_max_raw, segment_prior_mean_raw, 0)::DOUBLE
                AS trailing_4_week_max,
            COALESCE(trailing_8_mean_raw, segment_prior_mean_raw, 0)::DOUBLE
                AS trailing_8_week_mean,
            COALESCE(trailing_8_std_raw, 0)::DOUBLE AS trailing_8_week_std,
            COALESCE(trailing_8_min_raw, segment_prior_mean_raw, 0)::DOUBLE
                AS trailing_8_week_min,
            COALESCE(trailing_8_max_raw, segment_prior_mean_raw, 0)::DOUBLE
                AS trailing_8_week_max,
            COALESCE(segment_prior_week_count, 0)::BIGINT AS segment_prior_week_count,
            COALESCE(segment_prior_total_raw, 0)::DOUBLE AS segment_prior_total_count,
            COALESCE(segment_prior_mean_raw, 0)::DOUBLE AS segment_prior_mean_count,
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


def model_prediction_expr(
    *,
    alpha: float | str,
    beta: float | str,
    gamma: float | str,
    shrinkage: float | str,
) -> str:
    return (
        "GREATEST(0.0, "
        f"({shrinkage}) * ("
        "trailing_8_week_mean "
        f"+ ({alpha}) * (trailing_4_week_mean - trailing_8_week_mean) "
        f"+ ({beta}) * (lag_1_week_count - trailing_4_week_mean) "
        f"+ ({gamma}) * (lag_52_week_count - trailing_8_week_mean)"
        "))"
    )


def parameter_grid_values_sql() -> str:
    rows = []
    for alpha in ALPHA_GRID:
        for beta in BETA_GRID:
            for gamma in GAMMA_GRID:
                for shrinkage in SHRINKAGE_GRID:
                    rows.append(f"({alpha:.2f}, {beta:.2f}, {gamma:.2f}, {shrinkage:.2f})")
    return ", ".join(rows)


def fit_lag_ensemble_model(
    con: Any,
    *,
    validation_start: date,
    validation_end: date,
) -> dict[str, Any]:
    parameter_values = parameter_grid_values_sql()
    pred_expr = model_prediction_expr(
        alpha="params.alpha",
        beta="params.beta",
        gamma="params.gamma",
        shrinkage="params.shrinkage",
    )
    row = fetch_one(
        con,
        f"""
        WITH params(alpha, beta, gamma, shrinkage) AS (
            VALUES {parameter_values}
        ),
        scored AS (
            SELECT
                params.alpha,
                params.beta,
                params.gamma,
                params.shrinkage,
                actual_crime_count,
                {pred_expr} AS predicted_crime_count
            FROM ml_feature_rows
            CROSS JOIN params
            WHERE week_start BETWEEN {sql_date(validation_start)} AND {sql_date(validation_end)}
                AND actual_crime_count IS NOT NULL
        ),
        metrics AS (
            SELECT
                alpha,
                beta,
                gamma,
                shrinkage,
                COUNT(*)::BIGINT AS validation_prediction_count,
                SUM(actual_crime_count)::BIGINT AS validation_actual_event_count,
                ROUND(AVG(ABS(predicted_crime_count - actual_crime_count)), 5) AS mae,
                ROUND(SQRT(AVG(POWER(predicted_crime_count - actual_crime_count, 2))), 5) AS rmse,
                ROUND(
                    SUM(ABS(predicted_crime_count - actual_crime_count) * actual_crime_count)
                        / NULLIF(SUM(actual_crime_count), 0),
                    5
                ) AS weighted_mae
            FROM scored
            GROUP BY 1, 2, 3, 4
        )
        SELECT
            alpha::DOUBLE AS alpha,
            beta::DOUBLE AS beta,
            gamma::DOUBLE AS gamma,
            shrinkage::DOUBLE AS shrinkage,
            validation_prediction_count,
            validation_actual_event_count,
            mae AS validation_mae,
            rmse AS validation_rmse,
            weighted_mae AS validation_weighted_mae
        FROM metrics
        WHERE validation_prediction_count > 0
        ORDER BY
            validation_rmse ASC,
            validation_mae ASC,
            COALESCE(validation_weighted_mae, 1e18) ASC,
            ABS(shrinkage - 1.0) ASC,
            ABS(alpha) ASC,
            ABS(beta) ASC,
            ABS(gamma) ASC
        LIMIT 1
        """,
    )
    return normalize_rows([row])[0]


def create_prediction_view(con: Any, model_params: dict[str, Any]) -> None:
    pred_expr = model_prediction_expr(
        alpha=float(model_params["alpha"]),
        beta=float(model_params["beta"]),
        gamma=float(model_params["gamma"]),
        shrinkage=float(model_params["shrinkage"]),
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW ml_predictions AS
        SELECT
            week_start,
            borough,
            precinct,
            offense_type,
            law_category,
            actual_crime_count,
            ROUND({pred_expr}, 6) AS predicted_crime_count,
            {sql_string(MODEL_NAME)} AS ml_model_name,
            lag_1_week_count,
            lag_52_week_count,
            trailing_4_week_mean,
            trailing_8_week_mean,
            segment_prior_mean_count,
            is_backtest_week,
            is_next_week_forecast,
            segment_first_week,
            segment_last_observed_week,
            segment_observed_week_count,
            segment_total_crime_count
        FROM ml_feature_rows
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
            FROM ml_predictions
            ORDER BY week_start, borough, precinct, offense_type, law_category
        ) TO {sql_string(predictions_path)} (FORMAT PARQUET)
        """
    )


def build_metrics(con: Any, group_columns: list[str] | None = None) -> list[dict[str, Any]]:
    group_columns = group_columns or []
    if group_columns:
        group_select = ", ".join(ident(column) for column in group_columns)
        group_order = ", ".join(ident(column) for column in group_columns)
        sql = f"""
        WITH eligible AS (
            SELECT
                *,
                ABS(predicted_crime_count - actual_crime_count) AS abs_error,
                POWER(predicted_crime_count - actual_crime_count, 2) AS squared_error
            FROM ml_predictions
            WHERE is_backtest_week
                AND actual_crime_count IS NOT NULL
                AND predicted_crime_count IS NOT NULL
        ),
        groups AS (
            SELECT
                {group_select},
                COUNT(*)::BIGINT AS total_backtest_rows,
                SUM(actual_crime_count)::BIGINT AS total_actual_event_count
            FROM ml_predictions
            WHERE is_backtest_week
            GROUP BY {group_select}
        ),
        agg AS (
            SELECT
                {group_select},
                COUNT(*)::BIGINT AS prediction_count,
                SUM(actual_crime_count)::BIGINT AS actual_event_count,
                ROUND(AVG(abs_error), 4) AS mae,
                ROUND(SQRT(AVG(squared_error)), 4) AS rmse,
                ROUND(
                    SUM(abs_error * actual_crime_count) / NULLIF(SUM(actual_crime_count), 0),
                    4
                ) AS weighted_mae
            FROM eligible
            GROUP BY {group_select}
        )
        SELECT
            {", ".join(f"groups.{ident(column)}" for column in group_columns)},
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
        LEFT JOIN agg
            ON {" AND ".join(f"groups.{ident(column)} = agg.{ident(column)}" for column in group_columns)}
        ORDER BY {group_order}
        """
    else:
        sql = """
        WITH eligible AS (
            SELECT
                *,
                ABS(predicted_crime_count - actual_crime_count) AS abs_error,
                POWER(predicted_crime_count - actual_crime_count, 2) AS squared_error
            FROM ml_predictions
            WHERE is_backtest_week
                AND actual_crime_count IS NOT NULL
                AND predicted_crime_count IS NOT NULL
        ),
        groups AS (
            SELECT
                COUNT(*)::BIGINT AS total_backtest_rows,
                SUM(actual_crime_count)::BIGINT AS total_actual_event_count
            FROM ml_predictions
            WHERE is_backtest_week
        ),
        agg AS (
            SELECT
                COUNT(*)::BIGINT AS prediction_count,
                SUM(actual_crime_count)::BIGINT AS actual_event_count,
                ROUND(AVG(abs_error), 4) AS mae,
                ROUND(SQRT(AVG(squared_error)), 4) AS rmse,
                ROUND(
                    SUM(abs_error * actual_crime_count) / NULLIF(SUM(actual_crime_count), 0),
                    4
                ) AS weighted_mae
            FROM eligible
        )
        SELECT
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
        CROSS JOIN agg
        """
    return normalize_rows(fetch_dicts(con, sql))


def build_top_k_capture(con: Any, top_k_fraction: float) -> dict[str, Any]:
    return normalize_rows(
        fetch_dicts(
            con,
            f"""
            WITH eligible AS (
                SELECT *
                FROM ml_predictions
                WHERE is_backtest_week
                    AND actual_crime_count IS NOT NULL
                    AND predicted_crime_count IS NOT NULL
            ),
            ranked AS (
                SELECT
                    *,
                    COUNT(*) OVER (PARTITION BY week_start) AS rows_in_week,
                    ROW_NUMBER() OVER (
                        PARTITION BY week_start
                        ORDER BY actual_crime_count DESC, borough, precinct, offense_type, law_category
                    ) AS actual_rank,
                    ROW_NUMBER() OVER (
                        PARTITION BY week_start
                        ORDER BY predicted_crime_count DESC, borough, precinct, offense_type, law_category
                    ) AS predicted_rank
                FROM eligible
            ),
            ranked_with_k AS (
                SELECT
                    *,
                    GREATEST(1, CEIL(rows_in_week * {float(top_k_fraction)}))::BIGINT
                        AS top_k_count
                FROM ranked
            ),
            weekly_capture AS (
                SELECT
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
                GROUP BY 1
            )
            SELECT
                {float(top_k_fraction)} AS top_k_fraction,
                COUNT(week_start)::BIGINT AS evaluated_weeks,
                ROUND(AVG(top_k_count), 2) AS avg_weekly_top_k_rows,
                SUM(actual_top_k_event_count)::BIGINT AS actual_top_k_event_count,
                SUM(captured_top_k_event_count)::BIGINT AS captured_top_k_event_count,
                ROUND(
                    SUM(captured_top_k_event_count) * 1.0
                        / NULLIF(SUM(actual_top_k_event_count), 0),
                    4
                ) AS top_k_capture_rate
            FROM weekly_capture
            """,
        )
    )[0]


def build_hardest_segments(
    con: Any,
    *,
    group_columns: list[str],
    min_actual_count: int,
    limit: int,
) -> list[dict[str, Any]]:
    group_sql = ", ".join(ident(column) for column in group_columns)
    return normalize_rows(
        fetch_dicts(
            con,
            f"""
            WITH scored AS (
                SELECT
                    {group_sql},
                    actual_crime_count,
                    predicted_crime_count,
                    ABS(predicted_crime_count - actual_crime_count) AS abs_error,
                    POWER(predicted_crime_count - actual_crime_count, 2) AS squared_error
                FROM ml_predictions
                WHERE is_backtest_week
                    AND actual_crime_count IS NOT NULL
                    AND predicted_crime_count IS NOT NULL
            )
            SELECT
                {group_sql},
                COUNT(*)::BIGINT AS prediction_count,
                SUM(actual_crime_count)::BIGINT AS actual_event_count,
                ROUND(AVG(abs_error), 4) AS mae,
                ROUND(SQRT(AVG(squared_error)), 4) AS rmse,
                ROUND(
                    SUM(abs_error * actual_crime_count) / NULLIF(SUM(actual_crime_count), 0),
                    4
                ) AS weighted_mae
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
        FROM ml_predictions
        """,
    )


def baseline_reference_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    selected = manifest.get("selected_baseline") or {}
    return {
        "baseline_method": selected.get("baseline_method", "trailing_8_week_mean"),
        "prediction_count": selected.get("prediction_count"),
        "total_backtest_rows": selected.get("total_backtest_rows"),
        "prediction_coverage_pct": selected.get("prediction_coverage_pct"),
        "actual_event_count": selected.get("actual_event_count"),
        "mae": selected.get("mae"),
        "rmse": selected.get("rmse"),
        "weighted_mae": selected.get("weighted_mae"),
    }


def compare_to_baseline(
    *,
    ml_overall: dict[str, Any],
    baseline_reference: dict[str, Any],
) -> dict[str, Any]:
    rows = [
        {
            "model": f"Phase 4 {baseline_reference.get('baseline_method')}",
            "prediction_count": baseline_reference.get("prediction_count"),
            "prediction_coverage_pct": baseline_reference.get("prediction_coverage_pct"),
            "mae": baseline_reference.get("mae"),
            "rmse": baseline_reference.get("rmse"),
            "weighted_mae": baseline_reference.get("weighted_mae"),
        },
        {
            "model": f"Phase 5 {MODEL_NAME}",
            "prediction_count": ml_overall.get("prediction_count"),
            "prediction_coverage_pct": ml_overall.get("prediction_coverage_pct"),
            "mae": ml_overall.get("mae"),
            "rmse": ml_overall.get("rmse"),
            "weighted_mae": ml_overall.get("weighted_mae"),
        },
    ]
    deltas: dict[str, Any] = {"model": "Delta ML - baseline"}
    beats = {}
    for metric in ["mae", "rmse", "weighted_mae"]:
        baseline_value = baseline_reference.get(metric)
        ml_value = ml_overall.get(metric)
        if baseline_value is None or ml_value is None:
            deltas[metric] = None
            beats[metric] = None
        else:
            deltas[metric] = round(float(ml_value) - float(baseline_value), 4)
            beats[metric] = float(ml_value) < float(baseline_value)
    rows.append(deltas)
    return {
        "baseline_reference": baseline_reference,
        "comparison_rows": rows,
        "beats_baseline": beats,
        "beats_baseline_all_core_metrics": all(value is True for value in beats.values()),
    }


def validate_metrics_payload(payload: dict[str, Any]) -> None:
    missing_sections = [
        section for section in ML_METRICS_REQUIRED_SECTIONS if section not in payload
    ]
    if missing_sections:
        raise ValueError(f"ML metrics payload is missing required sections: {missing_sections}")

    columns_used = set(payload.get("forecast_columns_used") or [])
    sensitive_columns = set(payload.get("ethics", {}).get("sensitive_columns_excluded") or [])
    overlap = columns_used.intersection(sensitive_columns)
    if overlap:
        raise ValueError(f"Sensitive columns cannot be used in ML forecasting: {sorted(overlap)}")

    if payload.get("prediction_columns") != PREDICTION_COLUMNS:
        raise ValueError("ML metrics payload has an unexpected prediction column contract.")

    metrics = payload.get("metrics") or {}
    for key in ["overall", "by_borough", "by_offense_type", "by_borough_offense"]:
        if key not in metrics:
            raise ValueError(f"ML metrics payload is missing metrics section: {key}")


def build_metrics_payload(
    con: Any,
    *,
    project_root: Path,
    inputs: dict[str, Path],
    outputs: dict[str, Path],
    input_summary: dict[str, Any],
    baseline_manifest: dict[str, Any],
    backtest_start: date,
    backtest_end: date,
    validation_start: date,
    validation_end: date,
    forecast_week: date,
    validation_weeks: int,
    model_params: dict[str, Any],
    top_k_fraction: float,
    hardest_segment_limit: int,
    min_hard_segment_actual_count: int,
) -> dict[str, Any]:
    overall_metrics = build_metrics(con)[0]
    baseline_reference = baseline_reference_from_manifest(baseline_manifest)
    baseline_comparison = compare_to_baseline(
        ml_overall=overall_metrics,
        baseline_reference=baseline_reference,
    )
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "Phase 5 - ML Forecast Model",
        "inputs": repository_relative_paths(project_root, inputs),
        "outputs": repository_relative_paths(project_root, outputs),
        "forecast_columns_used": FORECAST_COLUMNS_USED,
        "engineered_feature_columns": ENGINEERED_FEATURE_COLUMNS,
        "model_feature_columns": MODEL_FEATURE_COLUMNS,
        "prediction_columns": PREDICTION_COLUMNS,
        "model_config": {
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "dependency_mode": "stdlib_plus_duckdb_no_sklearn",
            "target": "next-week crime_count by week_start, borough, precinct, offense_type, law_category",
            "selection_objective": SELECTION_OBJECTIVE,
            "validation_weeks_requested": validation_weeks,
            "validation_window": {
                "validation_start_week": validation_start,
                "validation_end_week": validation_end,
            },
            "selected_parameters": model_params,
            "parameter_grid": {
                "alpha": ALPHA_GRID,
                "beta": BETA_GRID,
                "gamma": GAMMA_GRID,
                "shrinkage": SHRINKAGE_GRID,
            },
            "prediction_formula": (
                "max(0, shrinkage * (trailing_8_week_mean "
                "+ alpha * (trailing_4_week_mean - trailing_8_week_mean) "
                "+ beta * (lag_1_week_count - trailing_4_week_mean) "
                "+ gamma * (lag_52_week_count - trailing_8_week_mean)))"
            ),
            "feature_imputation_rule": (
                "Missing lag and rolling mean features are filled from the segment's "
                "prior mean only; if the segment has no prior weeks they are zero."
            ),
            "zero_fill_rule": (
                "Missing weekly rows are treated as zero crime_count after a segment's first observed week."
            ),
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
            "overall": [overall_metrics],
            "by_borough": build_metrics(con, ["borough"]),
            "by_offense_type": build_metrics(con, ["offense_type"]),
            "by_borough_offense": build_metrics(con, ["borough", "offense_type"]),
        },
        "top_k_capture": build_top_k_capture(con, top_k_fraction),
        "baseline_comparison": baseline_comparison,
        "hardest_segments": {
            "min_actual_count": min_hard_segment_actual_count,
            "borough_offense": build_hardest_segments(
                con,
                group_columns=["borough", "offense_type"],
                min_actual_count=min_hard_segment_actual_count,
                limit=hardest_segment_limit,
            ),
            "precinct_offense": build_hardest_segments(
                con,
                group_columns=["borough", "precinct", "offense_type"],
                min_actual_count=min_hard_segment_actual_count,
                limit=hardest_segment_limit,
            ),
        },
        "ethics": {
            "sensitive_columns_excluded": SENSITIVE_COLUMNS,
            "note": (
                "ML forecasts use aggregate weekly counts and segment keys only. "
                "They do not use suspect or victim demographics and do not create "
                "person-level predictions or enforcement recommendations."
            ),
        },
    }
    validate_metrics_payload(payload)
    return payload


def write_metrics_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, default=json_default)
        file.write("\n")


def build_model_manifest(
    payload: dict[str, Any], *, project_root: Path
) -> dict[str, Any]:
    return {
        "artifact_type": "weekly_forecast_ml_model",
        "artifact_version": 1,
        "generated_at_utc": payload["generated_at_utc"],
        "phase": payload["phase"],
        "source_script": "src/models/build_ml_forecast.py",
        "training_input": repository_relative_path(
            project_root, payload["inputs"]["weekly_area"]
        ),
        "baseline_manifest_input": repository_relative_path(
            project_root, payload["inputs"]["baseline_manifest"]
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
        "target": payload["model_config"]["target"],
        "model": {
            "model_name": payload["model_config"]["model_name"],
            "model_version": payload["model_config"]["model_version"],
            "dependency_mode": payload["model_config"]["dependency_mode"],
            "selection_objective": payload["model_config"]["selection_objective"],
            "selected_parameters": payload["model_config"]["selected_parameters"],
            "prediction_formula": payload["model_config"]["prediction_formula"],
        },
        "segment_keys": SEGMENT_KEYS,
        "feature_groups": {
            "time": ["year", "month", "iso_week", "quarter", "week_index"],
            "lag": [
                "lag_1_week_count",
                "lag_2_week_count",
                "lag_4_week_count",
                "lag_8_week_count",
                "lag_52_week_count",
            ],
            "rolling_prior_weeks": [
                "trailing_4_week_mean",
                "trailing_4_week_std",
                "trailing_4_week_min",
                "trailing_4_week_max",
                "trailing_8_week_mean",
                "trailing_8_week_std",
                "trailing_8_week_min",
                "trailing_8_week_max",
            ],
            "segment_history": [
                "segment_prior_week_count",
                "segment_prior_total_count",
                "segment_prior_mean_count",
            ],
            "segment_identifiers": SEGMENT_KEYS,
        },
        "model_feature_columns": payload["model_feature_columns"],
        "training_window": {
            "min_week_start": payload["analysis_window"]["min_week_start"],
            "max_week_start": payload["analysis_window"]["max_week_start"],
            "segment_count": payload["analysis_window"]["segment_count"],
        },
        "validation_window": payload["model_config"]["validation_window"],
        "backtest_window": {
            "backtest_start_week": payload["analysis_window"]["backtest_start_week"],
            "backtest_end_week": payload["analysis_window"]["backtest_end_week"],
            "backtest_rows": payload["record_counts"]["backtest_rows"],
        },
        "forecast_week": payload["analysis_window"]["next_week_forecast_week"],
        "overall_metrics": payload["metrics"]["overall"],
        "baseline_comparison": payload["baseline_comparison"],
        "leakage_controls": {
            "split_type": "time_based_validation_and_backtest",
            "random_splits_used": False,
            "target_week_excluded_from_features": True,
            "validation_window_precedes_backtest": True,
            "phase_4_backtest_window_reused": True,
            "zero_fill_rule": payload["model_config"]["zero_fill_rule"],
        },
        "feature_policy": {
            "forecast_columns_used": payload["forecast_columns_used"],
            "engineered_feature_columns": payload["engineered_feature_columns"],
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


def write_ml_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    overall = payload["metrics"]["overall"][0]
    comparison = payload["baseline_comparison"]
    beats = comparison["beats_baseline"]
    by_borough = payload["metrics"]["by_borough"]
    by_offense = sorted(
        payload["metrics"]["by_offense_type"],
        key=lambda row: (
            row.get("mae") is None,
            -(row.get("mae") or 0),
            -(row.get("actual_event_count") or 0),
            row.get("offense_type") or "",
        ),
    )
    hardest_borough_offense = payload["hardest_segments"]["borough_offense"]
    hardest_precinct_offense = payload["hardest_segments"]["precinct_offense"]
    selected_params = payload["model_config"]["selected_parameters"]
    comparison_rows_for_report = []
    for row in comparison["comparison_rows"]:
        report_row = dict(row)
        model_label = str(report_row.get("model", ""))
        if model_label.startswith("Phase 4 "):
            report_row["model"] = f"`{model_label.removeprefix('Phase 4 ')}`"
        elif model_label.startswith("Phase 5 "):
            report_row["model"] = f"`{model_label.removeprefix('Phase 5 ')}`"
        comparison_rows_for_report.append(report_row)

    beat_sentence = (
        "The ML model recorded lower MAE, RMSE, and weighted MAE than the selected "
        "baseline in the manifest-level comparison."
        if comparison["beats_baseline_all_core_metrics"]
        else (
            "The ML model did not record a lower value than the selected baseline "
            "on every core metric in the manifest-level comparison. "
            f"Beat flags: MAE={beats.get('mae')}, RMSE={beats.get('rmse')}, "
            f"weighted MAE={beats.get('weighted_mae')}."
        )
    )
    baseline_reference = comparison["baseline_reference"]
    baseline_prediction_count = baseline_reference.get("prediction_count")
    ml_prediction_count = overall.get("prediction_count")
    coverage_note = (
        "The comparison uses different prediction coverage—"
        f"{format_value(baseline_prediction_count)} baseline rows versus "
        f"{format_value(ml_prediction_count)} ML rows. It is not a matched-row, "
        "like-for-like gain; the metric deltas are descriptive."
        if baseline_prediction_count != ml_prediction_count
        else (
            "The comparison records equal prediction counts, but the aggregate metrics do not "
            "establish that the evaluated rows are identical; the metric deltas are descriptive."
        )
    )

    hardest_label = (
        f"{hardest_borough_offense[0].get('borough')} / "
        f"{hardest_borough_offense[0].get('offense_type')}"
        if hardest_borough_offense
        else "No hardest segment was available"
    )

    lines = [
        "# NYPD Complaint Data Historic - ML Forecast Model",
        "",
        f"Generated at UTC: `{payload['generated_at_utc']}`",
        "",
        "## Scope",
        "",
        (
            "The model builder reads `crime_weekly_area.parquet` and forecasts next-week "
            "`crime_count` for each borough, precinct, offense type, and law category segment. "
            "Its output is integrated into the browser-safe forecast contracts, but the "
            "builder itself remains responsible only for aggregate model training, "
            "historical evaluation, and fixed-horizon prediction. It does not produce an "
            "API or any enforcement recommendation."
        ),
        "",
        "## Inputs and Outputs",
        "",
        "\n".join(f"- Input {name}: `{path_value}`" for name, path_value in payload["inputs"].items()),
        "\n".join(f"- Output {name}: `{path_value}`" for name, path_value in payload["outputs"].items()),
        "",
        "## Forecast Setup",
        "",
        markdown_table(
            [
                {
                    "min_week_start": payload["analysis_window"]["min_week_start"],
                    "max_week_start": payload["analysis_window"]["max_week_start"],
                    "validation_start_week": payload["model_config"]["validation_window"]["validation_start_week"],
                    "validation_end_week": payload["model_config"]["validation_window"]["validation_end_week"],
                    "backtest_start_week": payload["analysis_window"]["backtest_start_week"],
                    "backtest_end_week": payload["analysis_window"]["backtest_end_week"],
                    "next_week_forecast_week": payload["analysis_window"]["next_week_forecast_week"],
                    "segment_count": payload["analysis_window"]["segment_count"],
                    "backtest_rows": payload["record_counts"]["backtest_rows"],
                }
            ]
        ),
        "",
        "The baseline backtest window is reused. All lag and rolling features are computed "
        "with windows ending one row before the target week.",
        "",
        "## Model",
        "",
        (
            f"`{MODEL_NAME}` is a deterministic lag-ensemble regressor selected by "
            f"{payload['model_config']['selection_objective']}. It uses the pinned DuckDB "
            "dependency and the Python standard library; scikit-learn is not a project "
            "dependency."
        ),
        "",
        "Formula:",
        "",
        f"`{payload['model_config']['prediction_formula']}`",
        "",
        "Selected parameters:",
        "",
        markdown_table([selected_params]),
        "",
        "Validation metrics for the selected parameters:",
        "",
        markdown_table(
            [
                {
                    "validation_prediction_count": selected_params.get("validation_prediction_count"),
                    "validation_actual_event_count": selected_params.get("validation_actual_event_count"),
                    "validation_mae": selected_params.get("validation_mae"),
                    "validation_rmse": selected_params.get("validation_rmse"),
                    "validation_weighted_mae": selected_params.get("validation_weighted_mae"),
                }
            ]
        ),
        "",
        "## Overall Backtest Metrics",
        "",
        markdown_table(
            [overall],
            [
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
        "## Comparison with the selected baseline",
        "",
        markdown_table(
            comparison_rows_for_report,
            [
                "model",
                "prediction_count",
                "prediction_coverage_pct",
                "mae",
                "rmse",
                "weighted_mae",
            ],
        ),
        "",
        beat_sentence,
        coverage_note,
        "",
        "## Borough Metrics",
        "",
        markdown_table(
            by_borough,
            [
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
        "## Hardest Offense Types",
        "",
        markdown_table(
            by_offense[:15],
            [
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
        markdown_table(hardest_borough_offense),
        "",
        "## Hardest Precinct/Offense Segments",
        "",
        markdown_table(hardest_precinct_offense),
        "",
        "## Top-K High-Volume Capture",
        "",
        markdown_table([payload["top_k_capture"]]),
        "",
        "## Interpretation",
        "",
        f"- Baseline comparison: {beat_sentence}",
        f"- Coverage qualification: {coverage_note}",
        (
            f"- Hardest segments: `{hardest_label}` is among the highest-error borough/offense "
            "groups after filtering for meaningful volume; these errors are concentrated in "
            "high-volume, volatile offense categories."
        ),
        (
            "- Important features and limitations: the strongest signal is short-term history "
            "from the prior 4 and 8 weeks, adjusted by last-week and 52-week references. "
            "The model does not yet include holidays, reporting-delay corrections, exogenous "
            "events, spatial spillover, or uncertainty intervals."
        ),
        (
            "- Lifecycle limitations: no prediction interval, formal drift monitor, model-age "
            "threshold, or general retraining cadence is established. The fixed historical/demo "
            "dashboard is not operational guidance; it provides point estimates and does not "
            "invent any of those capabilities or policies."
        ),
        "",
        "## Ethics Constraint",
        "",
        (
            "Suspect and victim demographic fields are excluded. Outputs are aggregate "
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
    if args.validation_weeks <= 0:
        raise ValueError("--validation-weeks must be positive.")
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
    baseline_manifest_path = resolve_path(
        project_root,
        args.baseline_manifest,
        DEFAULT_BASELINE_MODEL_DIR / BASELINE_MANIFEST_FILE,
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
    if not baseline_manifest_path.exists():
        raise FileNotFoundError(f"Missing Phase 4 baseline manifest: {baseline_manifest_path}")

    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    model_manifest_path.parent.mkdir(parents=True, exist_ok=True)

    baseline_manifest = load_json(baseline_manifest_path)

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
    backtest_start, backtest_end = get_backtest_window_from_baseline(
        baseline_manifest,
        min_week=min_week,
        max_week=max_week,
    )
    validation_start, validation_end = compute_validation_window(
        min_week,
        backtest_start,
        validation_weeks=args.validation_weeks,
    )

    print("Building leakage-safe ML feature rows.")
    create_ml_feature_views(
        con,
        min_week=min_week,
        max_week=max_week,
        forecast_week=forecast_week,
        backtest_start=backtest_start,
        backtest_end=backtest_end,
    )

    print("Selecting lag-ensemble parameters on the pre-backtest validation window.")
    model_params = fit_lag_ensemble_model(
        con,
        validation_start=validation_start,
        validation_end=validation_end,
    )

    print("Building ML predictions.")
    create_prediction_view(con, model_params)

    print(f"Writing ML predictions: {predictions_path}")
    write_predictions(con, predictions_path)

    outputs = {
        "model_manifest": model_manifest_path,
        "predictions": predictions_path,
        "metrics": metrics_path,
        "report": report_path,
    }
    inputs = {
        "weekly_area": weekly_path,
        "baseline_manifest": baseline_manifest_path,
    }

    print("Building ML metrics payload.")
    payload = build_metrics_payload(
        con,
        project_root=project_root,
        inputs=inputs,
        outputs=outputs,
        input_summary=input_summary,
        baseline_manifest=baseline_manifest,
        backtest_start=backtest_start,
        backtest_end=backtest_end,
        validation_start=validation_start,
        validation_end=validation_end,
        forecast_week=forecast_week,
        validation_weeks=args.validation_weeks,
        model_params=model_params,
        top_k_fraction=args.top_k_fraction,
        hardest_segment_limit=args.hardest_segment_limit,
        min_hard_segment_actual_count=args.min_hard_segment_actual_count,
    )

    print(f"Writing ML metrics JSON: {metrics_path}")
    write_metrics_json(metrics_path, payload)
    print(f"Writing ML model manifest: {model_manifest_path}")
    write_model_manifest(model_manifest_path, payload, project_root=project_root)
    print(f"Writing ML model report: {report_path}")
    write_ml_report(report_path, payload)
    print("Phase 5 ML forecast model complete.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Interrupted.")

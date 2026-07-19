#!/usr/bin/env python3
"""Build Phase 6A aggregate weekly anomaly detection outputs.

This script reads the Phase 2 weekly aggregate table and, when available, the
Phase 5 ML backtest predictions. It writes:

    data/processed/anomalies.parquet
    data/processed/anomaly_metrics.json
    reports/anomaly_methodology.md

The layer is intentionally aggregate-only. It scores weekly borough/precinct/
offense/law-category segment counts against prior weekly history and optional
leakage-safe ML predictions. It does not read raw data, demographic fields,
hotspot map features, APIs, dashboards, or enforcement recommendations.

Example from the repository root:

    .venv/bin/python src/analytics/build_anomalies.py
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_REPORTS_DIR = Path("reports")
DEFAULT_MODEL_DIR = Path("models/weekly_forecast")

WEEKLY_FILE = "crime_weekly_area.parquet"
ML_PREDICTIONS_FILE = "ml_predictions.parquet"
MODEL_MANIFEST_FILE = "model_manifest.json"
ANOMALIES_FILE = "anomalies.parquet"
METRICS_FILE = "anomaly_metrics.json"
REPORT_FILE = "anomaly_methodology.md"

SENSITIVE_COLUMNS = [
    "SUSP_AGE_GROUP",
    "SUSP_RACE",
    "SUSP_SEX",
    "VIC_AGE_GROUP",
    "VIC_RACE",
    "VIC_SEX",
]

SEGMENT_KEYS = [
    "borough",
    "precinct",
    "offense_type",
    "law_category",
]

WEEKLY_REQUIRED_COLUMNS = [
    "week_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "crime_count",
]

ML_PREDICTION_REQUIRED_COLUMNS = [
    "week_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "actual_crime_count",
    "predicted_crime_count",
    "is_backtest_week",
    "is_next_week_forecast",
]

ANOMALY_COLUMNS_USED = WEEKLY_REQUIRED_COLUMNS.copy()

HISTORICAL_FEATURE_COLUMNS = [
    "trailing_8_week_mean",
    "trailing_13_week_mean",
    "trailing_26_week_mean",
    "trailing_13_week_std",
    "rolling_26_week_median",
    "rolling_26_week_mad",
    "prior_13_week_total_count",
    "prior_26_week_total_count",
    "recent_nonzero_week_count",
]

ANOMALY_OUTPUT_COLUMNS = [
    "rank_overall",
    "rank_in_week",
    "week_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "actual_crime_count",
    "expected_count",
    "expected_count_source",
    "expected_historical_count",
    "expected_ml_count",
    "residual_count",
    "historical_residual_count",
    "ml_residual_count",
    "pct_change_vs_trailing_8_week_mean",
    "trailing_8_week_mean",
    "trailing_13_week_mean",
    "trailing_26_week_mean",
    "trailing_13_week_std",
    "rolling_z_score",
    "rolling_26_week_median",
    "rolling_26_week_mad",
    "robust_z_score",
    "ml_residual_scaled_score",
    "prior_13_week_count",
    "prior_26_week_count",
    "prior_13_week_total_count",
    "prior_26_week_total_count",
    "recent_nonzero_week_count",
    "has_ml_prediction",
    "passes_volume_filter",
    "is_historical_anomaly",
    "is_ml_anomaly",
    "is_anomaly",
    "anomaly_severity",
    "anomaly_score",
]

ANOMALY_REPORT_COLUMNS = [
    "week_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "actual_crime_count",
    "expected_count",
    "expected_count_source",
    "residual_count",
    "pct_change_vs_trailing_8_week_mean",
    "rolling_z_score",
    "robust_z_score",
    "anomaly_severity",
    "anomaly_score",
]

SEVERITY_LABELS = ["low", "medium", "high", "critical"]

ANOMALY_METRICS_REQUIRED_SECTIONS = [
    "generated_at_utc",
    "phase",
    "inputs",
    "outputs",
    "anomaly_columns_used",
    "historical_feature_columns",
    "output_columns",
    "anomaly_config",
    "analysis_window",
    "record_counts",
    "severity_counts",
    "top_recent_anomalies",
    "volatile_borough_offense_groups",
    "leakage_controls",
    "ethics",
]


class AnomalyConfig:
    recent_window_weeks: int = 8
    baseline_window_weeks: int = 13
    long_window_weeks: int = 26
    min_prior_weeks: int = 13
    min_prior_total_count: int = 13
    min_actual_count: int = 4
    min_absolute_increase: int = 3
    min_pct_change: float = 75.0
    low_z_threshold: float = 2.0
    medium_z_threshold: float = 2.75
    high_z_threshold: float = 3.5
    critical_z_threshold: float = 4.5
    low_robust_z_threshold: float = 3.0
    medium_robust_z_threshold: float = 4.0
    high_robust_z_threshold: float = 5.0
    critical_robust_z_threshold: float = 6.0
    low_ml_scaled_threshold: float = 2.5
    medium_ml_scaled_threshold: float = 3.5
    high_ml_scaled_threshold: float = 4.5
    critical_ml_scaled_threshold: float = 6.0
    high_min_residual_count: int = 6
    critical_min_residual_count: int = 8
    critical_min_actual_count: int = 10
    volatile_group_min_actual_count: int = 100
    volatile_group_min_evaluated_weeks: int = 52

    _FIELDS = [
        "recent_window_weeks",
        "baseline_window_weeks",
        "long_window_weeks",
        "min_prior_weeks",
        "min_prior_total_count",
        "min_actual_count",
        "min_absolute_increase",
        "min_pct_change",
        "low_z_threshold",
        "medium_z_threshold",
        "high_z_threshold",
        "critical_z_threshold",
        "low_robust_z_threshold",
        "medium_robust_z_threshold",
        "high_robust_z_threshold",
        "critical_robust_z_threshold",
        "low_ml_scaled_threshold",
        "medium_ml_scaled_threshold",
        "high_ml_scaled_threshold",
        "critical_ml_scaled_threshold",
        "high_min_residual_count",
        "critical_min_residual_count",
        "critical_min_actual_count",
        "volatile_group_min_actual_count",
        "volatile_group_min_evaluated_weeks",
    ]

    def __init__(self, **overrides: Any) -> None:
        unexpected = sorted(set(overrides).difference(self._FIELDS))
        if unexpected:
            raise TypeError(f"Unknown anomaly config fields: {unexpected}")
        for field in self._FIELDS:
            setattr(self, field, overrides.get(field, getattr(type(self), field)))

    def as_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self._FIELDS}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Phase 6A aggregate weekly anomaly detection outputs."
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
        help="Directory containing the Phase 5 model manifest.",
    )
    parser.add_argument(
        "--weekly-input",
        type=Path,
        default=None,
        help="Weekly aggregate input path. Defaults to data/processed/crime_weekly_area.parquet.",
    )
    parser.add_argument(
        "--ml-predictions-input",
        type=Path,
        default=None,
        help="Optional ML predictions path. Defaults to data/processed/ml_predictions.parquet.",
    )
    parser.add_argument(
        "--model-manifest",
        type=Path,
        default=None,
        help="Optional Phase 5 model manifest. Defaults to models/weekly_forecast/model_manifest.json.",
    )
    parser.add_argument(
        "--anomalies-output",
        type=Path,
        default=None,
        help="Output Parquet path. Defaults to data/processed/anomalies.parquet.",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to data/processed/anomaly_metrics.json.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=None,
        help="Output Markdown path. Defaults to reports/anomaly_methodology.md.",
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
        help="Number of top anomaly rows and volatile groups to include in summaries.",
    )
    parser.add_argument(
        "--include-latest-week",
        action="store_true",
        help=(
            "Include the latest input week in anomaly scoring. By default it is excluded "
            "because source extracts can contain a partial latest week."
        ),
    )
    parser.add_argument(
        "--min-prior-total-count",
        type=int,
        default=AnomalyConfig.min_prior_total_count,
        help="Minimum prior 13-week total count required before a segment-week can be flagged.",
    )
    parser.add_argument(
        "--min-actual-count",
        type=int,
        default=AnomalyConfig.min_actual_count,
        help="Minimum actual weekly count required before a segment-week can be flagged.",
    )
    parser.add_argument(
        "--min-absolute-increase",
        type=int,
        default=AnomalyConfig.min_absolute_increase,
        help="Minimum positive residual required before a segment-week can be flagged.",
    )
    parser.add_argument(
        "--min-pct-change",
        type=float,
        default=AnomalyConfig.min_pct_change,
        help="Minimum percent change vs trailing 8-week mean for low historical anomaly evidence.",
    )
    parser.add_argument(
        "--volatile-group-min-actual-count",
        type=int,
        default=AnomalyConfig.volatile_group_min_actual_count,
        help="Minimum actual count for borough/offense groups in the volatile-group table.",
    )
    parser.add_argument(
        "--volatile-group-min-evaluated-weeks",
        type=int,
        default=AnomalyConfig.volatile_group_min_evaluated_weeks,
        help="Minimum evaluated segment-weeks for borough/offense groups in the volatile-group table.",
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
            "Anomaly metrics paths must be inside the project root."
        ) from exc
    return relative.as_posix()


def repository_relative_optional_paths(
    project_root: Path, values: dict[str, Path | None]
) -> dict[str, str | None]:
    """Normalize named optional paths for portable metrics and reports."""
    return {
        name: (
            repository_relative_path(project_root, path)
            if path is not None
            else None
        )
        for name, path in values.items()
    }


def repository_relative_ml_status(
    project_root: Path, ml_status: dict[str, Any]
) -> dict[str, Any]:
    """Normalize the path fields nested in ML availability metadata."""
    portable_status = dict(ml_status)
    for key, value in portable_status.items():
        if not key.endswith("_path") or value is None:
            continue
        portable_status[key] = repository_relative_path(project_root, value)
    return portable_status


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
        if column and ("score" in column or "pct" in column or "rate" in column):
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


def validate_config(config: AnomalyConfig) -> None:
    if config.recent_window_weeks <= 0:
        raise ValueError("recent_window_weeks must be positive.")
    if config.baseline_window_weeks <= 0:
        raise ValueError("baseline_window_weeks must be positive.")
    if config.long_window_weeks <= 0:
        raise ValueError("long_window_weeks must be positive.")
    if config.min_prior_weeks <= 0:
        raise ValueError("min_prior_weeks must be positive.")
    if config.min_prior_weeks > config.baseline_window_weeks:
        raise ValueError("min_prior_weeks cannot exceed baseline_window_weeks.")
    if config.long_window_weeks < config.baseline_window_weeks:
        raise ValueError("long_window_weeks should be at least baseline_window_weeks.")
    if config.min_prior_total_count < 0:
        raise ValueError("min_prior_total_count cannot be negative.")
    if config.min_actual_count < 0:
        raise ValueError("min_actual_count cannot be negative.")
    if config.min_absolute_increase < 0:
        raise ValueError("min_absolute_increase cannot be negative.")
    if config.volatile_group_min_actual_count < 0:
        raise ValueError("volatile_group_min_actual_count cannot be negative.")
    if config.volatile_group_min_evaluated_weeks < 0:
        raise ValueError("volatile_group_min_evaluated_weeks cannot be negative.")


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


def compute_scoring_end_week(
    min_week: date,
    max_week: date,
    *,
    include_latest_week: bool,
) -> date:
    if include_latest_week:
        return max_week

    scoring_end_week = max_week - timedelta(weeks=1)
    if scoring_end_week < min_week:
        return max_week
    return scoring_end_week


def ml_predictions_are_leakage_safe(manifest: dict[str, Any] | None) -> bool:
    if manifest is None:
        return False

    controls = manifest.get("leakage_controls") or {}
    target_excluded = controls.get("target_week_excluded_from_features") is True
    random_splits = controls.get("random_splits_used")
    split_type = str(controls.get("split_type") or "")
    random_safe = random_splits is False or (
        random_splits is None and split_type.startswith("time_based")
    )
    return target_excluded and random_safe


def create_empty_ml_prediction_view(con: Any) -> None:
    con.execute(
        """
        CREATE OR REPLACE TEMP VIEW ml_safe_predictions AS
        SELECT
            DATE '1900-01-01' AS week_start,
            CAST('' AS VARCHAR) AS borough,
            CAST('' AS VARCHAR) AS precinct,
            CAST('' AS VARCHAR) AS offense_type,
            CAST('' AS VARCHAR) AS law_category,
            CAST(NULL AS DOUBLE) AS expected_ml_count,
            CAST(NULL AS VARCHAR) AS ml_model_name
        WHERE false
        """
    )


def create_ml_prediction_view(con: Any, ml_predictions_path: Path) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW ml_safe_predictions AS
        SELECT
            week_start::DATE AS week_start,
            COALESCE(CAST(borough AS VARCHAR), 'UNKNOWN') AS borough,
            COALESCE(CAST(precinct AS VARCHAR), 'UNKNOWN') AS precinct,
            COALESCE(CAST(offense_type AS VARCHAR), 'UNKNOWN') AS offense_type,
            COALESCE(CAST(law_category AS VARCHAR), 'UNKNOWN') AS law_category,
            CAST(predicted_crime_count AS DOUBLE) AS expected_ml_count,
            CAST(COALESCE(ml_model_name, 'unknown_ml_model') AS VARCHAR) AS ml_model_name
        FROM read_parquet({sql_string(ml_predictions_path)})
        WHERE predicted_crime_count IS NOT NULL
            AND actual_crime_count IS NOT NULL
            AND COALESCE(is_backtest_week, false)
            AND NOT COALESCE(is_next_week_forecast, false)
        """
    )


def build_ml_prediction_summary(con: Any) -> dict[str, Any]:
    return fetch_one(
        con,
        """
        SELECT
            COUNT(*)::BIGINT AS safe_ml_prediction_rows,
            MIN(week_start) AS min_ml_prediction_week,
            MAX(week_start) AS max_ml_prediction_week,
            COUNT(DISTINCT borough || chr(31) || precinct || chr(31) || offense_type || chr(31) || law_category)::BIGINT
                AS ml_prediction_segment_count
        FROM ml_safe_predictions
        """,
    )


def create_anomaly_views(
    con: Any,
    *,
    min_week: date,
    max_week: date,
    config: AnomalyConfig,
) -> None:
    validate_config(config)
    recent = int(config.recent_window_weeks)
    baseline = int(config.baseline_window_weeks)
    long_window = int(config.long_window_weeks)
    min_prior = int(config.min_prior_weeks)
    min_prior_total = int(config.min_prior_total_count)
    min_actual = int(config.min_actual_count)
    min_increase = int(config.min_absolute_increase)

    con.execute(
        """
        CREATE OR REPLACE TEMP VIEW anomaly_segments AS
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
        CREATE OR REPLACE TEMP VIEW anomaly_calendar AS
        SELECT week_start::DATE AS week_start
        FROM generate_series(
            {sql_date(min_week)},
            {sql_date(max_week)},
            INTERVAL '1 week'
        ) AS calendar(week_start)
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW anomaly_panel AS
        SELECT
            c.week_start,
            s.borough,
            s.precinct,
            s.offense_type,
            s.law_category,
            COALESCE(w.crime_count, 0)::DOUBLE AS history_crime_count,
            s.segment_first_week,
            s.segment_last_observed_week,
            s.segment_observed_week_count,
            s.segment_total_crime_count
        FROM anomaly_segments s
        JOIN anomaly_calendar c
            ON c.week_start BETWEEN s.segment_first_week AND {sql_date(max_week)}
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
        CREATE OR REPLACE TEMP VIEW anomaly_rolled AS
        SELECT
            week_start,
            borough,
            precinct,
            offense_type,
            law_category,
            ROUND(history_crime_count)::BIGINT AS actual_crime_count,
            COUNT(history_crime_count) OVER (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
                ROWS BETWEEN {recent} PRECEDING AND 1 PRECEDING
            ) AS prior_8_week_count,
            SUM(history_crime_count) OVER (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
                ROWS BETWEEN {recent} PRECEDING AND 1 PRECEDING
            ) AS prior_8_total_raw,
            AVG(history_crime_count) OVER (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
                ROWS BETWEEN {recent} PRECEDING AND 1 PRECEDING
            ) AS trailing_8_week_mean_raw,
            COUNT(history_crime_count) OVER (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
                ROWS BETWEEN {baseline} PRECEDING AND 1 PRECEDING
            ) AS prior_13_week_count,
            SUM(history_crime_count) OVER (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
                ROWS BETWEEN {baseline} PRECEDING AND 1 PRECEDING
            ) AS prior_13_total_raw,
            SUM(CASE WHEN history_crime_count > 0 THEN 1 ELSE 0 END) OVER (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
                ROWS BETWEEN {baseline} PRECEDING AND 1 PRECEDING
            ) AS recent_nonzero_week_count,
            AVG(history_crime_count) OVER (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
                ROWS BETWEEN {baseline} PRECEDING AND 1 PRECEDING
            ) AS trailing_13_week_mean_raw,
            STDDEV_POP(history_crime_count) OVER (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
                ROWS BETWEEN {baseline} PRECEDING AND 1 PRECEDING
            ) AS trailing_13_week_std_raw,
            COUNT(history_crime_count) OVER (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
                ROWS BETWEEN {long_window} PRECEDING AND 1 PRECEDING
            ) AS prior_26_week_count,
            SUM(history_crime_count) OVER (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
                ROWS BETWEEN {long_window} PRECEDING AND 1 PRECEDING
            ) AS prior_26_total_raw,
            AVG(history_crime_count) OVER (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
                ROWS BETWEEN {long_window} PRECEDING AND 1 PRECEDING
            ) AS trailing_26_week_mean_raw,
            MEDIAN(history_crime_count) OVER (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
                ROWS BETWEEN {long_window} PRECEDING AND 1 PRECEDING
            ) AS rolling_26_week_median_raw,
            MAD(history_crime_count) OVER (
                PARTITION BY borough, precinct, offense_type, law_category
                ORDER BY week_start
                ROWS BETWEEN {long_window} PRECEDING AND 1 PRECEDING
            ) AS rolling_26_week_mad_raw,
            segment_first_week,
            segment_last_observed_week,
            segment_observed_week_count,
            segment_total_crime_count
        FROM anomaly_panel
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW anomaly_candidates AS
        WITH joined AS (
            SELECT
                r.*,
                m.expected_ml_count,
                m.ml_model_name,
                m.expected_ml_count IS NOT NULL AS has_ml_prediction
            FROM anomaly_rolled r
            LEFT JOIN ml_safe_predictions m
                ON r.week_start = m.week_start
                AND r.borough = m.borough
                AND r.precinct = m.precinct
                AND r.offense_type = m.offense_type
                AND r.law_category = m.law_category
        ),
        metrics AS (
            SELECT
                week_start,
                borough,
                precinct,
                offense_type,
                law_category,
                actual_crime_count,
                CASE
                    WHEN prior_13_week_count >= {min_prior} THEN trailing_13_week_mean_raw
                    ELSE NULL
                END AS expected_historical_count,
                expected_ml_count,
                CASE
                    WHEN expected_ml_count IS NOT NULL THEN expected_ml_count
                    WHEN prior_13_week_count >= {min_prior} THEN trailing_13_week_mean_raw
                    ELSE NULL
                END AS expected_count,
                CASE
                    WHEN expected_ml_count IS NOT NULL THEN 'ml_prediction'
                    WHEN prior_13_week_count >= {min_prior} THEN 'rolling_13_week_mean'
                    ELSE NULL
                END AS expected_count_source,
                CASE
                    WHEN prior_8_week_count = {recent} THEN trailing_8_week_mean_raw
                    ELSE NULL
                END AS trailing_8_week_mean,
                CASE
                    WHEN prior_13_week_count >= {min_prior} THEN trailing_13_week_mean_raw
                    ELSE NULL
                END AS trailing_13_week_mean,
                CASE
                    WHEN prior_26_week_count = {long_window} THEN trailing_26_week_mean_raw
                    ELSE NULL
                END AS trailing_26_week_mean,
                CASE
                    WHEN prior_13_week_count >= {min_prior} THEN trailing_13_week_std_raw
                    ELSE NULL
                END AS trailing_13_week_std,
                CASE
                    WHEN prior_26_week_count = {long_window} THEN rolling_26_week_median_raw
                    ELSE NULL
                END AS rolling_26_week_median,
                CASE
                    WHEN prior_26_week_count = {long_window} THEN rolling_26_week_mad_raw
                    ELSE NULL
                END AS rolling_26_week_mad,
                prior_13_week_count::BIGINT AS prior_13_week_count,
                prior_26_week_count::BIGINT AS prior_26_week_count,
                COALESCE(ROUND(prior_13_total_raw), 0)::BIGINT AS prior_13_week_total_count,
                COALESCE(ROUND(prior_26_total_raw), 0)::BIGINT AS prior_26_week_total_count,
                COALESCE(recent_nonzero_week_count, 0)::BIGINT AS recent_nonzero_week_count,
                has_ml_prediction,
                segment_first_week,
                segment_last_observed_week,
                segment_observed_week_count,
                segment_total_crime_count
            FROM joined
        ),
        residuals AS (
            SELECT
                *,
                CASE
                    WHEN expected_count IS NULL THEN NULL
                    ELSE actual_crime_count - expected_count
                END AS residual_count,
                CASE
                    WHEN expected_historical_count IS NULL THEN NULL
                    ELSE actual_crime_count - expected_historical_count
                END AS historical_residual_count,
                CASE
                    WHEN expected_ml_count IS NULL THEN NULL
                    ELSE actual_crime_count - expected_ml_count
                END AS ml_residual_count,
                CASE
                    WHEN trailing_8_week_mean > 0
                        THEN ROUND((actual_crime_count - trailing_8_week_mean) * 100.0 / trailing_8_week_mean, 4)
                    ELSE NULL
                END AS pct_change_vs_trailing_8_week_mean,
                CASE
                    WHEN trailing_13_week_std > 0
                        THEN ROUND((actual_crime_count - trailing_13_week_mean) / trailing_13_week_std, 4)
                    ELSE NULL
                END AS rolling_z_score,
                CASE
                    WHEN rolling_26_week_mad > 0
                        THEN ROUND((actual_crime_count - rolling_26_week_median) / (1.4826 * rolling_26_week_mad), 4)
                    ELSE NULL
                END AS robust_z_score,
                CASE
                    WHEN expected_ml_count IS NOT NULL
                        THEN ROUND((actual_crime_count - expected_ml_count) / GREATEST(SQRT(expected_ml_count + 1), 1), 4)
                    ELSE NULL
                END AS ml_residual_scaled_score
            FROM metrics
        ),
        filters AS (
            SELECT
                *,
                prior_13_week_count >= {min_prior} AS is_evaluable,
                prior_13_week_count >= {min_prior}
                    AND prior_13_week_total_count >= {min_prior_total}
                    AND actual_crime_count >= {min_actual}
                    AS passes_volume_filter
            FROM residuals
        ),
        flags AS (
            SELECT
                *,
                passes_volume_filter
                    AND historical_residual_count >= {min_increase}
                    AND (
                        COALESCE(rolling_z_score, -1000000.0) >= {float(config.low_z_threshold)}
                        OR COALESCE(robust_z_score, -1000000.0) >= {float(config.low_robust_z_threshold)}
                        OR COALESCE(pct_change_vs_trailing_8_week_mean, -1000000.0) >= {float(config.min_pct_change)}
                    ) AS is_historical_anomaly,
                has_ml_prediction
                    AND passes_volume_filter
                    AND ml_residual_count >= {min_increase}
                    AND (
                        COALESCE(ml_residual_scaled_score, -1000000.0) >= {float(config.low_ml_scaled_threshold)}
                        OR (
                            expected_ml_count > 0
                            AND actual_crime_count >= expected_ml_count * 1.75
                        )
                    ) AS is_ml_anomaly
            FROM filters
        ),
        scored AS (
            SELECT
                *,
                is_historical_anomaly OR is_ml_anomaly AS is_anomaly,
                CASE
                    WHEN is_historical_anomaly OR is_ml_anomaly THEN ROUND(
                        0.45 * GREATEST(COALESCE(rolling_z_score, 0), 0)
                        + 0.20 * GREATEST(COALESCE(robust_z_score, 0), 0)
                        + 0.15 * LEAST(
                            GREATEST(COALESCE(pct_change_vs_trailing_8_week_mean, 0) / 100.0, 0),
                            5.0
                        )
                        + 0.15 * LEAST(
                            GREATEST(
                                COALESCE(historical_residual_count, 0)
                                / GREATEST(SQRT(COALESCE(expected_historical_count, 0) + 1), 1),
                                0
                            ),
                            8.0
                        )
                        + 0.05 * LEAST(GREATEST(COALESCE(ml_residual_scaled_score, 0), 0), 8.0),
                        4
                    )
                    ELSE 0.0
                END AS anomaly_score
            FROM flags
        ),
        severity AS (
            SELECT
                *,
                CASE
                    WHEN NOT is_anomaly THEN 'none'
                    WHEN actual_crime_count >= {int(config.critical_min_actual_count)}
                        AND GREATEST(
                            COALESCE(historical_residual_count, -1000000.0),
                            COALESCE(ml_residual_count, -1000000.0)
                        ) >= {int(config.critical_min_residual_count)}
                        AND (
                            COALESCE(rolling_z_score, -1000000.0) >= {float(config.critical_z_threshold)}
                            OR COALESCE(robust_z_score, -1000000.0) >= {float(config.critical_robust_z_threshold)}
                            OR COALESCE(ml_residual_scaled_score, -1000000.0) >= {float(config.critical_ml_scaled_threshold)}
                            OR anomaly_score >= 4.5
                        )
                        THEN 'critical'
                    WHEN GREATEST(
                            COALESCE(historical_residual_count, -1000000.0),
                            COALESCE(ml_residual_count, -1000000.0)
                        ) >= {int(config.high_min_residual_count)}
                        AND (
                            COALESCE(rolling_z_score, -1000000.0) >= {float(config.high_z_threshold)}
                            OR COALESCE(robust_z_score, -1000000.0) >= {float(config.high_robust_z_threshold)}
                            OR COALESCE(ml_residual_scaled_score, -1000000.0) >= {float(config.high_ml_scaled_threshold)}
                            OR COALESCE(pct_change_vs_trailing_8_week_mean, -1000000.0) >= 200.0
                            OR anomaly_score >= 3.5
                        )
                        THEN 'high'
                    WHEN GREATEST(
                            COALESCE(historical_residual_count, -1000000.0),
                            COALESCE(ml_residual_count, -1000000.0)
                        ) >= {min_increase + 1}
                        AND (
                            COALESCE(rolling_z_score, -1000000.0) >= {float(config.medium_z_threshold)}
                            OR COALESCE(robust_z_score, -1000000.0) >= {float(config.medium_robust_z_threshold)}
                            OR COALESCE(ml_residual_scaled_score, -1000000.0) >= {float(config.medium_ml_scaled_threshold)}
                            OR COALESCE(pct_change_vs_trailing_8_week_mean, -1000000.0) >= 125.0
                            OR anomaly_score >= 2.5
                        )
                        THEN 'medium'
                    ELSE 'low'
                END AS anomaly_severity
            FROM scored
        )
        SELECT
            week_start,
            borough,
            precinct,
            offense_type,
            law_category,
            actual_crime_count,
            ROUND(expected_count, 6) AS expected_count,
            expected_count_source,
            ROUND(expected_historical_count, 6) AS expected_historical_count,
            ROUND(expected_ml_count, 6) AS expected_ml_count,
            ROUND(residual_count, 6) AS residual_count,
            ROUND(historical_residual_count, 6) AS historical_residual_count,
            ROUND(ml_residual_count, 6) AS ml_residual_count,
            pct_change_vs_trailing_8_week_mean,
            ROUND(trailing_8_week_mean, 6) AS trailing_8_week_mean,
            ROUND(trailing_13_week_mean, 6) AS trailing_13_week_mean,
            ROUND(trailing_26_week_mean, 6) AS trailing_26_week_mean,
            ROUND(trailing_13_week_std, 6) AS trailing_13_week_std,
            rolling_z_score,
            ROUND(rolling_26_week_median, 6) AS rolling_26_week_median,
            ROUND(rolling_26_week_mad, 6) AS rolling_26_week_mad,
            robust_z_score,
            ml_residual_scaled_score,
            prior_13_week_count,
            prior_26_week_count,
            prior_13_week_total_count,
            prior_26_week_total_count,
            recent_nonzero_week_count,
            has_ml_prediction,
            passes_volume_filter,
            is_historical_anomaly,
            is_ml_anomaly,
            is_anomaly,
            anomaly_severity,
            anomaly_score,
            is_evaluable,
            segment_first_week,
            segment_last_observed_week,
            segment_observed_week_count,
            segment_total_crime_count
        FROM severity
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP VIEW anomalies AS
        WITH ranked AS (
            SELECT
                ROW_NUMBER() OVER (
                    ORDER BY anomaly_score DESC, actual_crime_count DESC, week_start DESC,
                        borough, precinct, offense_type, law_category
                )::BIGINT AS rank_overall,
                ROW_NUMBER() OVER (
                    PARTITION BY week_start
                    ORDER BY anomaly_score DESC, actual_crime_count DESC,
                        borough, precinct, offense_type, law_category
                )::BIGINT AS rank_in_week,
                *
            FROM anomaly_candidates
            WHERE is_anomaly
        )
        SELECT
            rank_overall,
            rank_in_week,
            week_start,
            borough,
            precinct,
            offense_type,
            law_category,
            actual_crime_count,
            expected_count,
            expected_count_source,
            expected_historical_count,
            expected_ml_count,
            residual_count,
            historical_residual_count,
            ml_residual_count,
            pct_change_vs_trailing_8_week_mean,
            trailing_8_week_mean,
            trailing_13_week_mean,
            trailing_26_week_mean,
            trailing_13_week_std,
            rolling_z_score,
            rolling_26_week_median,
            rolling_26_week_mad,
            robust_z_score,
            ml_residual_scaled_score,
            prior_13_week_count,
            prior_26_week_count,
            prior_13_week_total_count,
            prior_26_week_total_count,
            recent_nonzero_week_count,
            has_ml_prediction,
            passes_volume_filter,
            is_historical_anomaly,
            is_ml_anomaly,
            is_anomaly,
            anomaly_severity,
            anomaly_score
        FROM ranked
        """
    )


def write_anomalies(con: Any, anomalies_path: Path) -> None:
    columns_sql = ", ".join(ident(column) for column in ANOMALY_OUTPUT_COLUMNS)
    anomalies_path.parent.mkdir(parents=True, exist_ok=True)
    unlink_existing_outputs([anomalies_path])
    con.execute(
        f"""
        COPY (
            SELECT {columns_sql}
            FROM anomalies
            ORDER BY rank_overall
        ) TO {sql_string(anomalies_path)} (FORMAT PARQUET)
        """
    )


def build_record_counts(con: Any) -> dict[str, Any]:
    return fetch_one(
        con,
        """
        SELECT
            (SELECT COUNT(*)::BIGINT FROM anomaly_candidates) AS candidate_segment_weeks,
            (SELECT COUNT(*) FILTER (WHERE is_evaluable)::BIGINT FROM anomaly_candidates)
                AS evaluated_segment_weeks,
            (SELECT COUNT(*) FILTER (WHERE passes_volume_filter)::BIGINT FROM anomaly_candidates)
                AS volume_eligible_segment_weeks,
            (SELECT COUNT(*)::BIGINT FROM anomalies) AS anomaly_rows,
            (SELECT COUNT(*) FILTER (WHERE is_historical_anomaly)::BIGINT FROM anomaly_candidates)
                AS historical_anomaly_rows,
            (SELECT COUNT(*) FILTER (WHERE is_ml_anomaly)::BIGINT FROM anomaly_candidates)
                AS ml_anomaly_rows,
            (SELECT COUNT(DISTINCT week_start)::BIGINT FROM anomalies) AS anomaly_week_count,
            (SELECT COUNT(DISTINCT borough || chr(31) || precinct || chr(31) || offense_type || chr(31) || law_category)::BIGINT
                FROM anomalies) AS anomaly_segment_count
        """
    )


def build_analysis_window(
    con: Any,
    input_summary: dict[str, Any],
    ml_summary: dict[str, Any],
    *,
    scoring_end_week: date,
    latest_week_excluded_from_scoring: bool,
) -> dict[str, Any]:
    scoring_window = fetch_one(
        con,
        """
        SELECT
            MIN(week_start) FILTER (WHERE is_evaluable) AS min_evaluated_week_start,
            MAX(week_start) FILTER (WHERE is_evaluable) AS max_evaluated_week_start,
            MIN(week_start) FILTER (WHERE is_anomaly) AS min_anomaly_week_start,
            MAX(week_start) FILTER (WHERE is_anomaly) AS max_anomaly_week_start
        FROM anomaly_candidates
        """,
    )
    return {
        **input_summary,
        "scoring_end_week": scoring_end_week,
        "latest_week_excluded_from_scoring": latest_week_excluded_from_scoring,
        **scoring_window,
        "ml_predictions": ml_summary,
    }


def build_severity_counts(con: Any) -> list[dict[str, Any]]:
    rows = fetch_dicts(
        con,
        """
        SELECT
            anomaly_severity,
            COUNT(*)::BIGINT AS anomaly_count,
            SUM(actual_crime_count)::BIGINT AS actual_event_count,
            ROUND(AVG(anomaly_score), 4) AS avg_anomaly_score,
            ROUND(MAX(anomaly_score), 4) AS max_anomaly_score
        FROM anomalies
        GROUP BY 1
        """
    )
    by_label = {row["anomaly_severity"]: row for row in rows}
    completed = []
    for label in SEVERITY_LABELS:
        row = by_label.get(label) or {
            "anomaly_severity": label,
            "anomaly_count": 0,
            "actual_event_count": 0,
            "avg_anomaly_score": None,
            "max_anomaly_score": None,
        }
        completed.append(row)
    return normalize_rows(completed)


def build_top_recent_anomalies(con: Any, *, max_week: date, top_n: int) -> list[dict[str, Any]]:
    columns_sql = ", ".join(ident(column) for column in ANOMALY_REPORT_COLUMNS)
    return normalize_rows(
        fetch_dicts(
            con,
            f"""
            SELECT {columns_sql}
            FROM anomalies
            WHERE week_start >= {sql_date(max_week)} - INTERVAL '8 weeks'
            ORDER BY week_start DESC, anomaly_score DESC, actual_crime_count DESC,
                borough, precinct, offense_type, law_category
            LIMIT {int(top_n)}
            """,
        )
    )


def build_top_overall_anomalies(con: Any, *, top_n: int) -> list[dict[str, Any]]:
    columns_sql = ", ".join(ident(column) for column in ANOMALY_REPORT_COLUMNS)
    return normalize_rows(
        fetch_dicts(
            con,
            f"""
            SELECT {columns_sql}
            FROM anomalies
            ORDER BY anomaly_score DESC, actual_crime_count DESC, week_start DESC,
                borough, precinct, offense_type, law_category
            LIMIT {int(top_n)}
            """,
        )
    )


def build_volatile_borough_offense_groups(
    con: Any,
    *,
    min_actual_count: int,
    min_evaluated_weeks: int,
    limit: int,
) -> list[dict[str, Any]]:
    return normalize_rows(
        fetch_dicts(
            con,
            f"""
            SELECT
                borough,
                offense_type,
                COUNT(*) FILTER (WHERE is_evaluable)::BIGINT AS evaluated_segment_weeks,
                SUM(actual_crime_count)::BIGINT AS actual_event_count,
                COUNT(*) FILTER (WHERE is_anomaly)::BIGINT AS anomaly_count,
                COUNT(*) FILTER (
                    WHERE anomaly_severity IN ('high', 'critical')
                )::BIGINT AS high_or_critical_anomaly_count,
                ROUND(
                    COUNT(*) FILTER (WHERE is_anomaly) * 100.0
                        / NULLIF(COUNT(*) FILTER (WHERE is_evaluable), 0),
                    4
                ) AS anomaly_rate_pct,
                ROUND(AVG(trailing_13_week_std), 4) AS avg_trailing_13_week_std,
                ROUND(AVG(ABS(historical_residual_count)), 4) AS avg_abs_historical_residual,
                ROUND(MAX(anomaly_score), 4) AS max_anomaly_score
            FROM anomaly_candidates
            WHERE is_evaluable
                AND passes_volume_filter
            GROUP BY 1, 2
            HAVING COUNT(*) FILTER (WHERE is_evaluable) >= {int(min_evaluated_weeks)}
                AND SUM(actual_crime_count) >= {int(min_actual_count)}
            ORDER BY
                avg_abs_historical_residual DESC NULLS LAST,
                avg_trailing_13_week_std DESC NULLS LAST,
                anomaly_count DESC,
                actual_event_count DESC,
                borough,
                offense_type
            LIMIT {int(limit)}
            """,
        )
    )


def validate_anomaly_metrics_payload(payload: dict[str, Any]) -> None:
    missing_sections = [
        section for section in ANOMALY_METRICS_REQUIRED_SECTIONS if section not in payload
    ]
    if missing_sections:
        raise ValueError(f"Anomaly metrics payload is missing required sections: {missing_sections}")

    used_columns = set(payload.get("anomaly_columns_used") or []).union(
        payload.get("historical_feature_columns") or []
    )
    sensitive_columns = set(payload.get("ethics", {}).get("sensitive_columns_excluded") or [])
    overlap = used_columns.intersection(sensitive_columns)
    if overlap:
        raise ValueError(f"Sensitive columns cannot be used in anomaly detection: {sorted(overlap)}")

    if payload.get("output_columns") != ANOMALY_OUTPUT_COLUMNS:
        raise ValueError("Anomaly metrics payload has an unexpected output column contract.")

    severity_labels = {
        row.get("anomaly_severity") for row in payload.get("severity_counts") or []
    }
    missing_labels = [label for label in SEVERITY_LABELS if label not in severity_labels]
    if missing_labels:
        raise ValueError(f"Anomaly severity counts missing labels: {missing_labels}")


def build_metrics_payload(
    con: Any,
    *,
    project_root: Path,
    inputs: dict[str, Path | None],
    outputs: dict[str, Path],
    input_summary: dict[str, Any],
    ml_summary: dict[str, Any],
    config: AnomalyConfig,
    ml_status: dict[str, Any],
    scoring_end_week: date,
    latest_week_excluded_from_scoring: bool,
    top_n: int,
) -> dict[str, Any]:
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "Phase 6A - Anomaly Detection Layer",
        "inputs": repository_relative_optional_paths(project_root, inputs),
        "outputs": repository_relative_optional_paths(project_root, outputs),
        "anomaly_columns_used": ANOMALY_COLUMNS_USED,
        "historical_feature_columns": HISTORICAL_FEATURE_COLUMNS,
        "output_columns": ANOMALY_OUTPUT_COLUMNS,
        "anomaly_config": {
            **config.as_dict(),
            "primary_historical_expected_count": "trailing_13_week_mean over prior weeks only",
            "recent_percent_change_baseline": "trailing_8_week_mean over prior weeks only",
            "robust_score_scale": "1.4826 * rolling_26_week_mad",
            "ml_prediction_rule": "Only Phase 5 backtest rows are joined; next-week forecast rows have no actual count and are excluded.",
        },
        "analysis_window": build_analysis_window(
            con,
            input_summary,
            ml_summary,
            scoring_end_week=scoring_end_week,
            latest_week_excluded_from_scoring=latest_week_excluded_from_scoring,
        ),
        "record_counts": build_record_counts(con),
        "severity_counts": build_severity_counts(con),
        "top_recent_anomalies": build_top_recent_anomalies(
            con,
            max_week=scoring_end_week,
            top_n=top_n,
        ),
        "top_overall_anomalies": build_top_overall_anomalies(con, top_n=top_n),
        "volatile_borough_offense_groups": build_volatile_borough_offense_groups(
            con,
            min_actual_count=config.volatile_group_min_actual_count,
            min_evaluated_weeks=config.volatile_group_min_evaluated_weeks,
            limit=top_n,
        ),
        "leakage_controls": {
            "historical_windows_use_prior_weeks_only": True,
            "window_frame": "ROWS BETWEEN N PRECEDING AND 1 PRECEDING",
            "zero_fill_rule": (
                "Missing weekly rows are treated as zero crime_count after a segment's first observed week."
            ),
            "random_splits_used": False,
            "latest_week_excluded_from_scoring": latest_week_excluded_from_scoring,
            "ml_prediction_status": repository_relative_ml_status(
                project_root, ml_status
            ),
        },
        "ethics": {
            "sensitive_columns_excluded": SENSITIVE_COLUMNS,
            "aggregate_trend_intelligence_only": True,
            "person_level_prediction": False,
            "enforcement_recommendations": False,
            "note": (
                "Anomaly detection uses only aggregate weekly counts and segment keys. "
                "It does not use suspect or victim demographics and does not produce "
                "patrol, enforcement, or person-level recommendations."
            ),
        },
    }
    validate_anomaly_metrics_payload(payload)
    return payload


def write_metrics_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, default=json_default)
        file.write("\n")


def write_anomaly_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    counts = payload["record_counts"]
    config = payload["anomaly_config"]
    window = payload["analysis_window"]
    ml_status = payload["leakage_controls"]["ml_prediction_status"]

    lines = [
        "# NYPD Complaint Data Historic - Anomaly Methodology",
        "",
        f"Generated at UTC: `{payload['generated_at_utc']}`",
        "",
        "## Scope",
        "",
        (
            "The anomaly builder identifies unusually high aggregate weekly complaint "
            "counts for borough, precinct, offense type, and law category segments. Its "
            "output is integrated into the dashboard's aggregate list/detail experience, "
            "while the builder remains responsible only for retrospective anomaly "
            "analysis. It does not create an API, patrol recommendation, or person-level score."
        ),
        "",
        "## Inputs and Outputs",
        "",
        "\n".join(f"- Input {name}: `{value}`" for name, value in payload["inputs"].items()),
        "\n".join(f"- Output {name}: `{value}`" for name, value in payload["outputs"].items()),
        "",
        "## Methodology",
        "",
        (
            "The script builds a zero-filled weekly panel after each segment first appears. "
            "For every segment-week it computes trailing 8-, 13-, and 26-week statistics "
            "using only weeks before the target week."
        ),
        "",
        "Scoring formulas:",
        "",
        "- `expected_historical_count = mean(prior 13 weekly counts)`.",
        "- `expected_ml_count = predicted_crime_count` from the reviewed ML backtest when a safe prediction exists.",
        "- `expected_count = expected_ml_count` when available, otherwise `expected_historical_count`.",
        "- `residual_count = actual_crime_count - expected_count`.",
        "- `historical_residual_count = actual_crime_count - expected_historical_count`.",
        "- `pct_change_vs_trailing_8_week_mean = (actual - trailing_8_mean) / trailing_8_mean * 100`.",
        "- `rolling_z_score = (actual - trailing_13_mean) / trailing_13_std`.",
        "- `robust_z_score = (actual - rolling_26_median) / (1.4826 * rolling_26_mad)`.",
        "- `ml_residual_scaled_score = (actual - expected_ml_count) / sqrt(expected_ml_count + 1)`.",
        "",
        "A segment-week can be flagged only when it has enough prior history, enough recent "
        "volume, a meaningful positive residual, and either historical or ML evidence. "
        "The default volume gate requires at least "
        f"{config['min_prior_total_count']} prior complaints over the 13-week baseline "
        f"window, at least {config['min_actual_count']} actual complaints in the target "
        f"week, and at least {config['min_absolute_increase']} complaints above expected.",
        "",
        "## Leakage Controls",
        "",
        "- Historical rolling windows end at one week before the scored week.",
        "- No random splits are used.",
        "- Missing segment-weeks are zero-filled only after the segment first appears.",
        "- The latest source week is excluded from scoring by default because it may be partial.",
        "- ML residuals use only reviewed backtest predictions with actual counts; next-week forecast rows are excluded.",
        f"- ML prediction use status: `{ml_status['status']}`.",
        "",
        "## Evaluation Summary",
        "",
        markdown_table(
            [
                {
                    "min_week_start": window["min_week_start"],
                    "max_week_start": window["max_week_start"],
                    "scoring_end_week": window["scoring_end_week"],
                    "latest_week_excluded_from_scoring": window["latest_week_excluded_from_scoring"],
                    "min_evaluated_week_start": window["min_evaluated_week_start"],
                    "max_evaluated_week_start": window["max_evaluated_week_start"],
                    "segment_count": window["segment_count"],
                    "candidate_segment_weeks": counts["candidate_segment_weeks"],
                    "evaluated_segment_weeks": counts["evaluated_segment_weeks"],
                    "volume_eligible_segment_weeks": counts["volume_eligible_segment_weeks"],
                    "anomaly_rows": counts["anomaly_rows"],
                }
            ]
        ),
        "",
        "## Anomaly Counts by Severity",
        "",
        markdown_table(payload["severity_counts"]),
        "",
        "## Top Recent Anomalies",
        "",
        markdown_table(payload["top_recent_anomalies"], ANOMALY_REPORT_COLUMNS),
        "",
        "## Top Overall Anomalies",
        "",
        markdown_table(payload["top_overall_anomalies"], ANOMALY_REPORT_COLUMNS),
        "",
        "## Hardest or Most Volatile Borough-Offense Groups",
        "",
        (
            "These borough/offense groups have the largest average absolute historical "
            "residuals after the minimum-volume gate. Groups must have at least "
            f"{config['volatile_group_min_evaluated_weeks']} evaluated segment-weeks and "
            f"{config['volatile_group_min_actual_count']} actual complaints in this table. "
            "They are useful candidates for ongoing forecast-error review; they are not "
            "filter-specific guarantees or policing priorities."
        ),
        "",
        markdown_table(payload["volatile_borough_offense_groups"]),
        "",
        "## Limitations and dashboard context",
        "",
        (
            "Anomalies are integrated with a complete list/detail experience and display "
            "expected count, residual, prior volume, lifecycle, and limitation context. "
            "See the [dashboard README](../dashboard/README.md) and "
            "[final project report](final_project_report.md) for the browser contract and "
            "responsible-use boundary."
        ),
        "",
        "- The layer identifies unusually high aggregate counts; it does not explain causality.",
        "- The latest source week may be partial depending on the upstream data extract.",
        "- Reported complaint counts can be affected by reporting delay, policy changes, classification changes, and data revisions.",
        "- The reviewed thresholds are conservative defaults and should be monitored for signal volume by borough and offense type when the analytical snapshot changes.",
        "- No uncertainty intervals, holidays, special events, spatial spillover terms, or reporting-lag corrections are included yet.",
        "- The dashboard shows expected count, residual, prior volume gate, and model lifecycle context with anomaly results.",
        "",
        "## Ethics Constraint",
        "",
        (
            "Suspect and victim demographic fields are excluded. Outputs are aggregate "
            "trend intelligence only and must not be interpreted as person-level "
            "predictions, automated enforcement actions, or patrol recommendations."
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
    if args.top_n <= 0:
        raise ValueError("--top-n must be positive.")

    project_root = args.project_root.resolve()
    processed_dir = resolve_path(project_root, args.processed_dir, DEFAULT_PROCESSED_DIR)
    reports_dir = resolve_path(project_root, args.reports_dir, DEFAULT_REPORTS_DIR)
    model_dir = resolve_path(project_root, args.model_dir, DEFAULT_MODEL_DIR)
    weekly_path = resolve_path(project_root, args.weekly_input, DEFAULT_PROCESSED_DIR / WEEKLY_FILE)
    ml_predictions_path = resolve_path(
        project_root,
        args.ml_predictions_input,
        DEFAULT_PROCESSED_DIR / ML_PREDICTIONS_FILE,
    )
    model_manifest_path = resolve_path(
        project_root,
        args.model_manifest,
        DEFAULT_MODEL_DIR / MODEL_MANIFEST_FILE,
    )
    anomalies_path = resolve_path(
        project_root,
        args.anomalies_output,
        DEFAULT_PROCESSED_DIR / ANOMALIES_FILE,
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
    repository_relative_optional_paths(
        project_root,
        {
            "processed_dir": processed_dir,
            "reports_dir": reports_dir,
            "model_dir": model_dir,
            "weekly_area": weekly_path,
            "ml_predictions": ml_predictions_path,
            "model_manifest": model_manifest_path,
            "anomalies": anomalies_path,
            "metrics": metrics_path,
            "report": report_path,
        },
    )
    config = AnomalyConfig(
        min_prior_total_count=args.min_prior_total_count,
        min_actual_count=args.min_actual_count,
        min_absolute_increase=args.min_absolute_increase,
        min_pct_change=args.min_pct_change,
        volatile_group_min_actual_count=args.volatile_group_min_actual_count,
        volatile_group_min_evaluated_weeks=args.volatile_group_min_evaluated_weeks,
    )
    validate_config(config)

    if not weekly_path.exists():
        raise FileNotFoundError(f"Missing weekly aggregate input: {weekly_path}")

    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    anomalies_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    duckdb = require_duckdb()
    con = duckdb.connect(database=":memory:")
    con.execute(f"PRAGMA threads={int(args.threads)}")

    print("Validating weekly aggregate schema.")
    validate_parquet_columns(con, weekly_path, WEEKLY_REQUIRED_COLUMNS)
    validate_weekly_source(con, weekly_path)
    create_input_views(con, weekly_path)
    input_summary = build_input_summary(con)
    min_week, max_week = get_week_bounds(con)
    scoring_end_week = compute_scoring_end_week(
        min_week,
        max_week,
        include_latest_week=args.include_latest_week,
    )
    latest_week_excluded_from_scoring = scoring_end_week < max_week
    if latest_week_excluded_from_scoring:
        print(f"Excluding latest input week {max_week} from anomaly scoring.")

    manifest = load_json(model_manifest_path) if model_manifest_path.exists() else None
    ml_status: dict[str, Any]
    if ml_predictions_path.exists():
        validate_parquet_columns(con, ml_predictions_path, ML_PREDICTION_REQUIRED_COLUMNS)
        if manifest is None:
            print("Skipping ML predictions because the Phase 5 model manifest is missing.")
            create_empty_ml_prediction_view(con)
            ml_status = {
                "status": "skipped_missing_manifest",
                "predictions_path": ml_predictions_path,
                "model_manifest_path": model_manifest_path,
                "manifest_available": False,
            }
        elif ml_predictions_are_leakage_safe(manifest):
            print("Using leakage-safe ML backtest predictions for residual scoring.")
            create_ml_prediction_view(con, ml_predictions_path)
            ml_status = {
                "status": "used",
                "predictions_path": ml_predictions_path,
                "model_manifest_path": model_manifest_path
                if model_manifest_path.exists()
                else None,
                "manifest_available": manifest is not None,
                "row_filter": "is_backtest_week AND NOT is_next_week_forecast AND actual_crime_count IS NOT NULL",
            }
        else:
            print("Skipping ML predictions because manifest leakage controls are insufficient.")
            create_empty_ml_prediction_view(con)
            ml_status = {
                "status": "skipped_manifest_leakage_controls",
                "predictions_path": ml_predictions_path,
                "model_manifest_path": model_manifest_path,
                "manifest_available": True,
            }
    else:
        print("ML predictions not found; using historical anomaly signals only.")
        create_empty_ml_prediction_view(con)
        ml_status = {
            "status": "not_available",
            "predictions_path": ml_predictions_path,
            "model_manifest_path": model_manifest_path
            if model_manifest_path.exists()
            else None,
            "manifest_available": manifest is not None,
        }
    ml_summary = build_ml_prediction_summary(con)

    print("Building prior-week anomaly features and severity labels.")
    create_anomaly_views(
        con,
        min_week=min_week,
        max_week=scoring_end_week,
        config=config,
    )
    print(f"Writing anomalies to {anomalies_path}.")
    write_anomalies(con, anomalies_path)

    outputs = {
        "anomalies": anomalies_path,
        "metrics": metrics_path,
        "report": report_path,
    }
    inputs = {
        "weekly_area": weekly_path,
        "ml_predictions": ml_predictions_path if ml_predictions_path.exists() else None,
        "ml_model_manifest": model_manifest_path if model_manifest_path.exists() else None,
    }
    metrics_payload = build_metrics_payload(
        con,
        project_root=project_root,
        inputs=inputs,
        outputs=outputs,
        input_summary=input_summary,
        ml_summary=ml_summary,
        config=config,
        ml_status=ml_status,
        scoring_end_week=scoring_end_week,
        latest_week_excluded_from_scoring=latest_week_excluded_from_scoring,
        top_n=args.top_n,
    )
    print(f"Writing anomaly metrics to {metrics_path}.")
    write_metrics_json(metrics_path, metrics_payload)
    print(f"Writing anomaly methodology report to {report_path}.")
    write_anomaly_report(report_path, metrics_payload)
    print(
        "Anomaly detection complete: "
        f"{metrics_payload['record_counts']['anomaly_rows']:,} anomalies from "
        f"{metrics_payload['record_counts']['evaluated_segment_weeks']:,} evaluated segment-weeks."
    )


if __name__ == "__main__":
    main()

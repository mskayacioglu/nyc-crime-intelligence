#!/usr/bin/env python3
"""Build Phase 6B aggregate hotspot detection outputs.

This script reads the Phase 2 cleaned complaint event table and writes:

    data/processed/hotspots.parquet
    data/processed/hotspot_metrics.json
    reports/hotspot_methodology.md

The layer is intentionally aggregate-only. It scores precinct/offense and
grid-cell/offense groups for recent concentration, historical lift, share
increase, recency-weighted volume, and coordinate quality. It does not read raw
data, use suspect/victim demographic fields, expose APIs, build dashboards, or
produce patrol/enforcement recommendations.

Example from the repository root:

    .venv/bin/python src/analytics/build_hotspots.py
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_REPORTS_DIR = Path("reports")

CLEAN_EVENTS_FILE = "complaints_clean.parquet"
WEEKLY_FILE = "crime_weekly_area.parquet"
HOTSPOTS_FILE = "hotspots.parquet"
METRICS_FILE = "hotspot_metrics.json"
REPORT_FILE = "hotspot_methodology.md"

NYC_LAT_MIN = 40.4774
NYC_LAT_MAX = 40.9176
NYC_LON_MIN = -74.2591
NYC_LON_MAX = -73.7004

SENSITIVE_COLUMNS = [
    "SUSP_AGE_GROUP",
    "SUSP_RACE",
    "SUSP_SEX",
    "VIC_AGE_GROUP",
    "VIC_RACE",
    "VIC_SEX",
]

CLEAN_EVENTS_REQUIRED_COLUMNS = [
    "complaint_from_date",
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

HOTSPOT_COLUMNS_USED = CLEAN_EVENTS_REQUIRED_COLUMNS.copy()

HOTSPOT_OUTPUT_COLUMNS = [
    "rank_overall",
    "rank_in_grain",
    "hotspot_grain",
    "borough",
    "precinct",
    "grid_latitude",
    "grid_longitude",
    "offense_type",
    "law_category",
    "map_latitude",
    "map_longitude",
    "recent_window_days",
    "baseline_window_days",
    "scoring_end_date",
    "recent_7_day_count",
    "recent_30_day_count",
    "recent_90_day_count",
    "recent_event_count",
    "baseline_event_count",
    "baseline_expected_recent_count",
    "recent_total_events",
    "baseline_total_events",
    "recent_share_total_events",
    "baseline_share_total_events",
    "share_change_pct_points",
    "recent_baseline_ratio",
    "recent_vs_baseline_lift_pct",
    "recency_weighted_event_count",
    "density_score",
    "lift_score",
    "share_increase_score",
    "recency_weighted_score",
    "coordinate_quality_score",
    "composite_score",
    "valid_coordinate_event_count",
    "coordinate_coverage_pct",
    "passes_volume_filter",
    "is_hotspot",
    "is_high_or_critical_hotspot",
    "hotspot_severity",
]

HOTSPOT_REPORT_COLUMNS = [
    "rank_overall",
    "hotspot_grain",
    "borough",
    "precinct",
    "grid_latitude",
    "grid_longitude",
    "offense_type",
    "law_category",
    "map_latitude",
    "map_longitude",
    "recent_event_count",
    "baseline_event_count",
    "recent_baseline_ratio",
    "share_change_pct_points",
    "density_score",
    "recency_weighted_score",
    "composite_score",
    "hotspot_severity",
]

SEVERITY_LABELS = ["low", "medium", "high", "critical"]

HOTSPOT_METRICS_REQUIRED_SECTIONS = [
    "generated_at_utc",
    "phase",
    "inputs",
    "outputs",
    "hotspot_columns_used",
    "output_columns",
    "hotspot_config",
    "analysis_window",
    "record_counts",
    "severity_counts",
    "top_precinct_hotspots",
    "top_grid_hotspots",
    "coordinate_quality",
    "leakage_controls",
    "ethics",
]


class HotspotConfig:
    short_window_days: int = 7
    recent_window_days: int = 30
    long_window_days: int = 90
    baseline_window_days: int = 365
    grid_size_degrees: float = 0.01
    min_precinct_recent_count: int = 25
    min_precinct_baseline_count: int = 50
    min_grid_recent_count: int = 8
    min_grid_baseline_count: int = 8
    min_recent_baseline_ratio: float = 1.25
    min_share_change_pct_points: float = 0.0
    min_hotspot_score: float = 30.0
    medium_score_threshold: float = 45.0
    high_score_threshold: float = 65.0
    critical_score_threshold: float = 85.0
    medium_ratio_threshold: float = 1.50
    high_ratio_threshold: float = 2.00
    critical_ratio_threshold: float = 3.00
    high_min_precinct_recent_count: int = 50
    critical_min_precinct_recent_count: int = 100
    high_min_grid_recent_count: int = 12
    critical_min_grid_recent_count: int = 20
    precinct_density_reference_count: int = 250
    grid_density_reference_count: int = 30

    _FIELDS = [
        "short_window_days",
        "recent_window_days",
        "long_window_days",
        "baseline_window_days",
        "grid_size_degrees",
        "min_precinct_recent_count",
        "min_precinct_baseline_count",
        "min_grid_recent_count",
        "min_grid_baseline_count",
        "min_recent_baseline_ratio",
        "min_share_change_pct_points",
        "min_hotspot_score",
        "medium_score_threshold",
        "high_score_threshold",
        "critical_score_threshold",
        "medium_ratio_threshold",
        "high_ratio_threshold",
        "critical_ratio_threshold",
        "high_min_precinct_recent_count",
        "critical_min_precinct_recent_count",
        "high_min_grid_recent_count",
        "critical_min_grid_recent_count",
        "precinct_density_reference_count",
        "grid_density_reference_count",
    ]

    def __init__(self, **overrides: Any) -> None:
        unexpected = sorted(set(overrides).difference(self._FIELDS))
        if unexpected:
            raise TypeError(f"Unknown hotspot config fields: {unexpected}")
        for field in self._FIELDS:
            setattr(self, field, overrides.get(field, getattr(type(self), field)))

    def as_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self._FIELDS}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Phase 6B aggregate hotspot detection outputs."
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
        "--clean-events-input",
        type=Path,
        default=None,
        help="Clean event input path. Defaults to data/processed/complaints_clean.parquet.",
    )
    parser.add_argument(
        "--weekly-input",
        type=Path,
        default=None,
        help=(
            "Optional weekly aggregate input path for validation context. Defaults to "
            "data/processed/crime_weekly_area.parquet when present."
        ),
    )
    parser.add_argument(
        "--hotspots-output",
        type=Path,
        default=None,
        help="Output Parquet path. Defaults to data/processed/hotspots.parquet.",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to data/processed/hotspot_metrics.json.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=None,
        help="Output Markdown path. Defaults to reports/hotspot_methodology.md.",
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
        help="Number of top hotspot rows to include in metrics and report summaries.",
    )
    parser.add_argument(
        "--include-latest-date",
        action="store_true",
        help=(
            "Include the latest cleaned event date in hotspot scoring. By default it "
            "is excluded because source extracts can contain a partial latest day."
        ),
    )
    parser.add_argument(
        "--grid-size-degrees",
        type=float,
        default=HotspotConfig.grid_size_degrees,
        help="Latitude/longitude grid size in degrees.",
    )
    parser.add_argument(
        "--min-precinct-recent-count",
        type=int,
        default=HotspotConfig.min_precinct_recent_count,
        help="Minimum 30-day count required for a precinct/offense hotspot.",
    )
    parser.add_argument(
        "--min-precinct-baseline-count",
        type=int,
        default=HotspotConfig.min_precinct_baseline_count,
        help="Minimum baseline-window count required for a precinct/offense hotspot.",
    )
    parser.add_argument(
        "--min-grid-recent-count",
        type=int,
        default=HotspotConfig.min_grid_recent_count,
        help="Minimum 30-day count required for a grid/offense hotspot.",
    )
    parser.add_argument(
        "--min-grid-baseline-count",
        type=int,
        default=HotspotConfig.min_grid_baseline_count,
        help="Minimum baseline-window count required for a grid/offense hotspot.",
    )
    parser.add_argument(
        "--min-recent-baseline-ratio",
        type=float,
        default=HotspotConfig.min_recent_baseline_ratio,
        help="Minimum normalized recent-vs-baseline ratio required for a hotspot.",
    )
    parser.add_argument(
        "--min-hotspot-score",
        type=float,
        default=HotspotConfig.min_hotspot_score,
        help="Minimum composite score required for a hotspot.",
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


def deterministic_generated_at_utc(scoring_end_date: date) -> str:
    return f"{scoring_end_date.isoformat()}T00:00:00+00:00"


def format_value(value: Any, column: str | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        if column and ("latitude" in column or "longitude" in column):
            return f"{value:,.5f}".rstrip("0").rstrip(".")
        if column and ("score" in column or "ratio" in column or "pct" in column):
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


def validate_config(config: HotspotConfig) -> None:
    if config.short_window_days <= 0:
        raise ValueError("short_window_days must be positive.")
    if config.recent_window_days <= 0:
        raise ValueError("recent_window_days must be positive.")
    if config.long_window_days <= 0:
        raise ValueError("long_window_days must be positive.")
    if config.baseline_window_days <= 0:
        raise ValueError("baseline_window_days must be positive.")
    if not config.short_window_days <= config.recent_window_days <= config.long_window_days:
        raise ValueError("Expected short_window_days <= recent_window_days <= long_window_days.")
    if config.grid_size_degrees <= 0:
        raise ValueError("grid_size_degrees must be positive.")
    count_fields = [
        "min_precinct_recent_count",
        "min_precinct_baseline_count",
        "min_grid_recent_count",
        "min_grid_baseline_count",
        "high_min_precinct_recent_count",
        "critical_min_precinct_recent_count",
        "high_min_grid_recent_count",
        "critical_min_grid_recent_count",
        "precinct_density_reference_count",
        "grid_density_reference_count",
    ]
    for field in count_fields:
        if getattr(config, field) < 0:
            raise ValueError(f"{field} cannot be negative.")
    if config.precinct_density_reference_count <= 0:
        raise ValueError("precinct_density_reference_count must be positive.")
    if config.grid_density_reference_count <= 0:
        raise ValueError("grid_density_reference_count must be positive.")
    if config.min_recent_baseline_ratio < 0:
        raise ValueError("min_recent_baseline_ratio cannot be negative.")
    if config.critical_ratio_threshold < config.high_ratio_threshold:
        raise ValueError("critical_ratio_threshold cannot be below high_ratio_threshold.")
    if config.high_ratio_threshold < config.medium_ratio_threshold:
        raise ValueError("high_ratio_threshold cannot be below medium_ratio_threshold.")


def validate_parquet_columns(con: Any, path: Path, required_columns: list[str]) -> None:
    rows = fetch_dicts(con, f"DESCRIBE SELECT * FROM read_parquet({sql_string(path)})")
    actual_columns = {row["column_name"] for row in rows}
    missing = [column for column in required_columns if column not in actual_columns]
    if missing:
        raise ValueError(f"{path} is missing required columns: {missing}")


def validate_clean_source(con: Any, clean_events_path: Path) -> None:
    validation = fetch_one(
        con,
        f"""
        SELECT
            COUNT(*) FILTER (WHERE is_clean_event_for_aggregate IS NULL)::BIGINT
                AS missing_clean_flag_rows,
            COUNT(*) FILTER (
                WHERE is_clean_event_for_aggregate
                    AND complaint_from_date IS NULL
            )::BIGINT AS clean_rows_missing_event_date
        FROM read_parquet({sql_string(clean_events_path)})
        """,
    )
    invalid = {key: value for key, value in validation.items() if value}
    if invalid:
        raise ValueError(f"Clean event input has invalid rows for hotspot scoring: {invalid}")


def create_input_views(con: Any, clean_events_path: Path) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW clean_events AS
        SELECT
            complaint_from_date::DATE AS complaint_from_date,
            COALESCE(CAST(borough AS VARCHAR), 'UNKNOWN') AS borough,
            COALESCE(CAST(precinct AS VARCHAR), 'UNKNOWN') AS precinct,
            COALESCE(CAST(offense_type AS VARCHAR), 'UNKNOWN') AS offense_type,
            COALESCE(CAST(law_category AS VARCHAR), 'UNKNOWN') AS law_category,
            CAST(latitude AS DOUBLE) AS latitude,
            CAST(longitude AS DOUBLE) AS longitude,
            COALESCE(CAST(flag_missing_coordinates AS BOOLEAN), false)
                AS flag_missing_coordinates,
            COALESCE(CAST(flag_zero_coordinates AS BOOLEAN), false)
                AS flag_zero_coordinates,
            COALESCE(CAST(flag_coordinates_outside_broad_nyc_bounds AS BOOLEAN), false)
                AS flag_coordinates_outside_broad_nyc_bounds,
            CAST(is_clean_event_for_aggregate AS BOOLEAN) AS is_clean_event_for_aggregate
        FROM read_parquet({sql_string(clean_events_path)})
        WHERE is_clean_event_for_aggregate
            AND complaint_from_date IS NOT NULL
        """
    )


def build_input_summary(con: Any, weekly_path: Path | None = None) -> dict[str, Any]:
    summary = fetch_one(
        con,
        f"""
        SELECT
            COUNT(*)::BIGINT AS clean_aggregate_event_rows,
            MIN(complaint_from_date) AS min_complaint_from_date,
            MAX(complaint_from_date) AS max_complaint_from_date,
            COUNT(*) FILTER (
                WHERE latitude IS NOT NULL
                    AND longitude IS NOT NULL
                    AND latitude <> 0
                    AND longitude <> 0
                    AND latitude BETWEEN {NYC_LAT_MIN} AND {NYC_LAT_MAX}
                    AND longitude BETWEEN {NYC_LON_MIN} AND {NYC_LON_MAX}
                    AND NOT flag_missing_coordinates
                    AND NOT flag_zero_coordinates
                    AND NOT flag_coordinates_outside_broad_nyc_bounds
            )::BIGINT AS valid_coordinate_event_rows,
            COUNT(DISTINCT borough || chr(31) || precinct || chr(31) || offense_type || chr(31) || law_category)::BIGINT
                AS precinct_offense_segment_count
        FROM clean_events
        """,
    )
    if weekly_path is not None:
        weekly_summary = fetch_one(
            con,
            f"""
            SELECT
                COUNT(*)::BIGINT AS weekly_aggregate_rows,
                SUM(crime_count)::BIGINT AS weekly_aggregate_event_count,
                MIN(week_start) AS min_week_start,
                MAX(week_start) AS max_week_start
            FROM read_parquet({sql_string(weekly_path)})
            """,
        )
        return {**summary, **weekly_summary}
    return summary


def get_event_date_bounds(con: Any) -> tuple[date, date]:
    bounds = fetch_one(
        con,
        """
        SELECT
            MIN(complaint_from_date) AS min_event_date,
            MAX(complaint_from_date) AS max_event_date
        FROM clean_events
        """,
    )
    if bounds["min_event_date"] is None or bounds["max_event_date"] is None:
        raise ValueError("Clean event input has no aggregate-safe event dates.")
    return bounds["min_event_date"], bounds["max_event_date"]


def compute_scoring_end_date(
    min_event_date: date,
    max_event_date: date,
    *,
    include_latest_date: bool,
) -> date:
    if include_latest_date:
        return max_event_date

    scoring_end_date = max_event_date - timedelta(days=1)
    if scoring_end_date < min_event_date:
        return max_event_date
    return scoring_end_date


def compute_window_bounds(scoring_end_date: date, config: HotspotConfig) -> dict[str, date]:
    recent_7_start = scoring_end_date - timedelta(days=config.short_window_days - 1)
    recent_30_start = scoring_end_date - timedelta(days=config.recent_window_days - 1)
    recent_90_start = scoring_end_date - timedelta(days=config.long_window_days - 1)
    baseline_end = recent_90_start - timedelta(days=1)
    baseline_start = recent_90_start - timedelta(days=config.baseline_window_days)
    return {
        "baseline_start_date": baseline_start,
        "baseline_end_date": baseline_end,
        "recent_90_start_date": recent_90_start,
        "recent_30_start_date": recent_30_start,
        "recent_7_start_date": recent_7_start,
        "scoring_end_date": scoring_end_date,
    }


def create_hotspot_views(
    con: Any,
    *,
    windows: dict[str, date],
    config: HotspotConfig,
) -> None:
    validate_config(config)

    grid_size = float(config.grid_size_degrees)
    short_days = int(config.short_window_days)
    recent_days = int(config.recent_window_days)
    long_days = int(config.long_window_days)
    baseline_days = int(config.baseline_window_days)

    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW valid_geo_events AS
        SELECT
            complaint_from_date,
            borough,
            precinct,
            offense_type,
            law_category,
            latitude,
            longitude,
            ROUND(FLOOR(latitude / {grid_size}) * {grid_size} + {grid_size} / 2, 5)
                AS grid_latitude,
            ROUND(FLOOR(longitude / {grid_size}) * {grid_size} + {grid_size} / 2, 5)
                AS grid_longitude
        FROM clean_events
        WHERE latitude IS NOT NULL
            AND longitude IS NOT NULL
            AND latitude <> 0
            AND longitude <> 0
            AND latitude BETWEEN {NYC_LAT_MIN} AND {NYC_LAT_MAX}
            AND longitude BETWEEN {NYC_LON_MIN} AND {NYC_LON_MAX}
            AND NOT flag_missing_coordinates
            AND NOT flag_zero_coordinates
            AND NOT flag_coordinates_outside_broad_nyc_bounds
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW analysis_events AS
        SELECT *
        FROM clean_events
        WHERE complaint_from_date BETWEEN {sql_date(windows['baseline_start_date'])}
            AND {sql_date(windows['scoring_end_date'])}
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW analysis_geo_events AS
        SELECT *
        FROM valid_geo_events
        WHERE complaint_from_date BETWEEN {sql_date(windows['baseline_start_date'])}
            AND {sql_date(windows['scoring_end_date'])}
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW precinct_window_totals AS
        SELECT
            COUNT(*) FILTER (
                WHERE complaint_from_date BETWEEN {sql_date(windows['recent_30_start_date'])}
                    AND {sql_date(windows['scoring_end_date'])}
            )::DOUBLE AS recent_total_events,
            COUNT(*) FILTER (
                WHERE complaint_from_date BETWEEN {sql_date(windows['baseline_start_date'])}
                    AND {sql_date(windows['baseline_end_date'])}
            )::DOUBLE AS baseline_total_events
        FROM analysis_events
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW grid_window_totals AS
        SELECT
            COUNT(*) FILTER (
                WHERE complaint_from_date BETWEEN {sql_date(windows['recent_30_start_date'])}
                    AND {sql_date(windows['scoring_end_date'])}
            )::DOUBLE AS recent_total_events,
            COUNT(*) FILTER (
                WHERE complaint_from_date BETWEEN {sql_date(windows['baseline_start_date'])}
                    AND {sql_date(windows['baseline_end_date'])}
            )::DOUBLE AS baseline_total_events
        FROM analysis_geo_events
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW precinct_centroids AS
        SELECT
            borough,
            precinct,
            ROUND(AVG(latitude), 6) AS map_latitude,
            ROUND(AVG(longitude), 6) AS map_longitude,
            COUNT(*)::BIGINT AS centroid_event_count
        FROM valid_geo_events
        WHERE complaint_from_date <= {sql_date(windows['scoring_end_date'])}
            AND precinct <> 'UNKNOWN'
        GROUP BY 1, 2
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW precinct_hotspot_base AS
        WITH counted AS (
            SELECT
                borough,
                precinct,
                offense_type,
                law_category,
                COUNT(*) FILTER (
                    WHERE complaint_from_date BETWEEN {sql_date(windows['recent_7_start_date'])}
                        AND {sql_date(windows['scoring_end_date'])}
                )::BIGINT AS recent_7_day_count,
                COUNT(*) FILTER (
                    WHERE complaint_from_date BETWEEN {sql_date(windows['recent_30_start_date'])}
                        AND {sql_date(windows['scoring_end_date'])}
                )::BIGINT AS recent_30_day_count,
                COUNT(*) FILTER (
                    WHERE complaint_from_date BETWEEN {sql_date(windows['recent_90_start_date'])}
                        AND {sql_date(windows['scoring_end_date'])}
                )::BIGINT AS recent_90_day_count,
                COUNT(*) FILTER (
                    WHERE complaint_from_date BETWEEN {sql_date(windows['baseline_start_date'])}
                        AND {sql_date(windows['baseline_end_date'])}
                )::BIGINT AS baseline_event_count
            FROM analysis_events
            GROUP BY 1, 2, 3, 4
        ),
        valid_recent_coordinates AS (
            SELECT
                borough,
                precinct,
                offense_type,
                law_category,
                COUNT(*)::BIGINT AS valid_coordinate_event_count
            FROM analysis_geo_events
            WHERE complaint_from_date BETWEEN {sql_date(windows['recent_30_start_date'])}
                AND {sql_date(windows['scoring_end_date'])}
            GROUP BY 1, 2, 3, 4
        )
        SELECT
            'precinct' AS hotspot_grain,
            c.borough,
            c.precinct,
            CAST(NULL AS DOUBLE) AS grid_latitude,
            CAST(NULL AS DOUBLE) AS grid_longitude,
            c.offense_type,
            c.law_category,
            p.map_latitude,
            p.map_longitude,
            c.recent_7_day_count,
            c.recent_30_day_count,
            c.recent_90_day_count,
            c.recent_30_day_count AS recent_event_count,
            c.baseline_event_count,
            ROUND(c.baseline_event_count * {float(recent_days)} / {float(baseline_days)}, 6)
                AS baseline_expected_recent_count,
            t.recent_total_events,
            t.baseline_total_events,
            COALESCE(v.valid_coordinate_event_count, 0)::BIGINT AS valid_coordinate_event_count
        FROM counted c
        CROSS JOIN precinct_window_totals t
        LEFT JOIN valid_recent_coordinates v
            ON c.borough = v.borough
            AND c.precinct = v.precinct
            AND c.offense_type = v.offense_type
            AND c.law_category = v.law_category
        LEFT JOIN precinct_centroids p
            ON c.borough = p.borough
            AND c.precinct = p.precinct
        WHERE c.recent_90_day_count > 0
            OR c.baseline_event_count > 0
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW grid_hotspot_base AS
        WITH counted AS (
            SELECT
                grid_latitude,
                grid_longitude,
                offense_type,
                law_category,
                COUNT(*) FILTER (
                    WHERE complaint_from_date BETWEEN {sql_date(windows['recent_7_start_date'])}
                        AND {sql_date(windows['scoring_end_date'])}
                )::BIGINT AS recent_7_day_count,
                COUNT(*) FILTER (
                    WHERE complaint_from_date BETWEEN {sql_date(windows['recent_30_start_date'])}
                        AND {sql_date(windows['scoring_end_date'])}
                )::BIGINT AS recent_30_day_count,
                COUNT(*) FILTER (
                    WHERE complaint_from_date BETWEEN {sql_date(windows['recent_90_start_date'])}
                        AND {sql_date(windows['scoring_end_date'])}
                )::BIGINT AS recent_90_day_count,
                COUNT(*) FILTER (
                    WHERE complaint_from_date BETWEEN {sql_date(windows['baseline_start_date'])}
                        AND {sql_date(windows['baseline_end_date'])}
                )::BIGINT AS baseline_event_count
            FROM analysis_geo_events
            GROUP BY 1, 2, 3, 4
        ),
        borough_counts AS (
            SELECT
                grid_latitude,
                grid_longitude,
                offense_type,
                law_category,
                borough,
                COUNT(*)::BIGINT AS borough_count,
                ROW_NUMBER() OVER (
                    PARTITION BY grid_latitude, grid_longitude, offense_type, law_category
                    ORDER BY COUNT(*) DESC, borough
                ) AS borough_rank
            FROM analysis_geo_events
            GROUP BY 1, 2, 3, 4, 5
        )
        SELECT
            'grid' AS hotspot_grain,
            COALESCE(b.borough, 'UNKNOWN') AS borough,
            CAST(NULL AS VARCHAR) AS precinct,
            c.grid_latitude,
            c.grid_longitude,
            c.offense_type,
            c.law_category,
            c.grid_latitude AS map_latitude,
            c.grid_longitude AS map_longitude,
            c.recent_7_day_count,
            c.recent_30_day_count,
            c.recent_90_day_count,
            c.recent_30_day_count AS recent_event_count,
            c.baseline_event_count,
            ROUND(c.baseline_event_count * {float(recent_days)} / {float(baseline_days)}, 6)
                AS baseline_expected_recent_count,
            t.recent_total_events,
            t.baseline_total_events,
            c.recent_30_day_count::BIGINT AS valid_coordinate_event_count
        FROM counted c
        CROSS JOIN grid_window_totals t
        LEFT JOIN borough_counts b
            ON c.grid_latitude = b.grid_latitude
            AND c.grid_longitude = b.grid_longitude
            AND c.offense_type = b.offense_type
            AND c.law_category = b.law_category
            AND b.borough_rank = 1
        WHERE c.recent_90_day_count > 0
            OR c.baseline_event_count > 0
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW hotspot_candidates AS
        WITH combined AS (
            SELECT * FROM precinct_hotspot_base
            UNION ALL
            SELECT * FROM grid_hotspot_base
        ),
        metrics AS (
            SELECT
                *,
                {recent_days}::INTEGER AS recent_window_days,
                {baseline_days}::INTEGER AS baseline_window_days,
                {sql_date(windows['scoring_end_date'])} AS scoring_end_date,
                CASE
                    WHEN recent_total_events > 0
                        THEN ROUND(recent_event_count * 100.0 / recent_total_events, 6)
                    ELSE 0.0
                END AS recent_share_total_events,
                CASE
                    WHEN baseline_total_events > 0
                        THEN ROUND(baseline_event_count * 100.0 / baseline_total_events, 6)
                    ELSE 0.0
                END AS baseline_share_total_events,
                CASE
                    WHEN baseline_expected_recent_count > 0
                        THEN ROUND(recent_event_count / baseline_expected_recent_count, 6)
                    ELSE NULL
                END AS recent_baseline_ratio,
                CASE
                    WHEN baseline_expected_recent_count > 0
                        THEN ROUND((recent_event_count / baseline_expected_recent_count - 1) * 100.0, 6)
                    ELSE NULL
                END AS recent_vs_baseline_lift_pct,
                ROUND(
                    recent_7_day_count * 0.50
                    + GREATEST(recent_30_day_count - recent_7_day_count, 0) * 0.35
                    + GREATEST(recent_90_day_count - recent_30_day_count, 0) * 0.15,
                    6
                ) AS recency_weighted_event_count,
                CASE
                    WHEN recent_event_count > 0
                        THEN ROUND(valid_coordinate_event_count * 100.0 / recent_event_count, 6)
                    ELSE 0.0
                END AS coordinate_coverage_pct
            FROM combined
        ),
        scored AS (
            SELECT
                *,
                ROUND(recent_share_total_events - baseline_share_total_events, 6)
                    AS share_change_pct_points,
                ROUND(
                    100.0
                    * LEAST(
                        LN(1 + recent_event_count)
                        / LN(
                            1 + CASE
                                WHEN hotspot_grain = 'precinct'
                                    THEN {int(config.precinct_density_reference_count)}
                                ELSE {int(config.grid_density_reference_count)}
                            END
                        ),
                        1.0
                    ),
                    4
                ) AS density_score,
                ROUND(
                    100.0
                    * LEAST(
                        GREATEST(
                            (COALESCE(recent_baseline_ratio, 0.0) - 1.0)
                            / GREATEST({float(config.critical_ratio_threshold)} - 1.0, 0.0001),
                            0.0
                        ),
                        1.0
                    ),
                    4
                ) AS lift_score,
                ROUND(
                    100.0
                    * LEAST(
                        GREATEST(
                            (
                                CASE
                                    WHEN baseline_share_total_events > 0
                                        THEN recent_share_total_events / baseline_share_total_events
                                    ELSE 0.0
                                END
                                - 1.0
                            )
                            / GREATEST({float(config.critical_ratio_threshold)} - 1.0, 0.0001),
                            0.0
                        ),
                        1.0
                    ),
                    4
                ) AS share_increase_score,
                ROUND(
                    100.0
                    * LEAST(
                        LN(1 + recency_weighted_event_count)
                        / LN(
                            1 + CASE
                                WHEN hotspot_grain = 'precinct'
                                    THEN {int(config.precinct_density_reference_count)}
                                ELSE {int(config.grid_density_reference_count)}
                            END
                        ),
                        1.0
                    ),
                    4
                ) AS recency_weighted_score,
                ROUND(LEAST(GREATEST(coordinate_coverage_pct, 0.0), 100.0), 4)
                    AS coordinate_quality_score,
                CASE
                    WHEN hotspot_grain = 'precinct'
                        THEN recent_event_count >= {int(config.min_precinct_recent_count)}
                            AND baseline_event_count >= {int(config.min_precinct_baseline_count)}
                    ELSE recent_event_count >= {int(config.min_grid_recent_count)}
                        AND baseline_event_count >= {int(config.min_grid_baseline_count)}
                END
                AND baseline_expected_recent_count > 0 AS passes_volume_filter
            FROM metrics
        ),
        composite AS (
            SELECT
                *,
                ROUND(
                    0.35 * density_score
                    + 0.25 * lift_score
                    + 0.20 * share_increase_score
                    + 0.15 * recency_weighted_score
                    + 0.05 * coordinate_quality_score,
                    4
                ) AS composite_score
            FROM scored
        ),
        flagged AS (
            SELECT
                *,
                passes_volume_filter
                    AND COALESCE(recent_baseline_ratio, 0.0) >= {float(config.min_recent_baseline_ratio)}
                    AND share_change_pct_points > {float(config.min_share_change_pct_points)}
                    AND composite_score >= {float(config.min_hotspot_score)}
                    AS is_hotspot
            FROM composite
        ),
        severity AS (
            SELECT
                *,
                CASE
                    WHEN NOT is_hotspot THEN 'none'
                    WHEN composite_score >= {float(config.critical_score_threshold)}
                        AND COALESCE(recent_baseline_ratio, 0.0) >= {float(config.critical_ratio_threshold)}
                        AND (
                            (hotspot_grain = 'precinct'
                                AND recent_event_count >= {int(config.critical_min_precinct_recent_count)})
                            OR (hotspot_grain = 'grid'
                                AND recent_event_count >= {int(config.critical_min_grid_recent_count)})
                        )
                        THEN 'critical'
                    WHEN composite_score >= {float(config.high_score_threshold)}
                        AND COALESCE(recent_baseline_ratio, 0.0) >= {float(config.high_ratio_threshold)}
                        AND (
                            (hotspot_grain = 'precinct'
                                AND recent_event_count >= {int(config.high_min_precinct_recent_count)})
                            OR (hotspot_grain = 'grid'
                                AND recent_event_count >= {int(config.high_min_grid_recent_count)})
                        )
                        THEN 'high'
                    WHEN composite_score >= {float(config.medium_score_threshold)}
                        AND COALESCE(recent_baseline_ratio, 0.0) >= {float(config.medium_ratio_threshold)}
                        THEN 'medium'
                    ELSE 'low'
                END AS hotspot_severity
            FROM flagged
        )
        SELECT
            hotspot_grain,
            borough,
            precinct,
            grid_latitude,
            grid_longitude,
            offense_type,
            law_category,
            map_latitude,
            map_longitude,
            recent_window_days,
            baseline_window_days,
            scoring_end_date,
            recent_7_day_count,
            recent_30_day_count,
            recent_90_day_count,
            recent_event_count,
            baseline_event_count,
            baseline_expected_recent_count,
            recent_total_events::BIGINT AS recent_total_events,
            baseline_total_events::BIGINT AS baseline_total_events,
            recent_share_total_events,
            baseline_share_total_events,
            share_change_pct_points,
            recent_baseline_ratio,
            recent_vs_baseline_lift_pct,
            recency_weighted_event_count,
            density_score,
            lift_score,
            share_increase_score,
            recency_weighted_score,
            coordinate_quality_score,
            composite_score,
            valid_coordinate_event_count,
            coordinate_coverage_pct,
            passes_volume_filter,
            is_hotspot,
            hotspot_severity IN ('high', 'critical') AS is_high_or_critical_hotspot,
            hotspot_severity
        FROM severity
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TEMP VIEW hotspots AS
        WITH ranked AS (
            SELECT
                ROW_NUMBER() OVER (
                    ORDER BY composite_score DESC, recent_event_count DESC,
                        recent_baseline_ratio DESC NULLS LAST,
                        hotspot_grain, borough, precinct, grid_latitude, grid_longitude,
                        offense_type, law_category
                )::BIGINT AS rank_overall,
                ROW_NUMBER() OVER (
                    PARTITION BY hotspot_grain
                    ORDER BY composite_score DESC, recent_event_count DESC,
                        recent_baseline_ratio DESC NULLS LAST,
                        borough, precinct, grid_latitude, grid_longitude,
                        offense_type, law_category
                )::BIGINT AS rank_in_grain,
                *
            FROM hotspot_candidates
            WHERE is_hotspot
        )
        SELECT
            rank_overall,
            rank_in_grain,
            hotspot_grain,
            borough,
            precinct,
            grid_latitude,
            grid_longitude,
            offense_type,
            law_category,
            map_latitude,
            map_longitude,
            recent_window_days,
            baseline_window_days,
            scoring_end_date,
            recent_7_day_count,
            recent_30_day_count,
            recent_90_day_count,
            recent_event_count,
            baseline_event_count,
            baseline_expected_recent_count,
            recent_total_events,
            baseline_total_events,
            recent_share_total_events,
            baseline_share_total_events,
            share_change_pct_points,
            recent_baseline_ratio,
            recent_vs_baseline_lift_pct,
            recency_weighted_event_count,
            density_score,
            lift_score,
            share_increase_score,
            recency_weighted_score,
            coordinate_quality_score,
            composite_score,
            valid_coordinate_event_count,
            coordinate_coverage_pct,
            passes_volume_filter,
            is_hotspot,
            is_high_or_critical_hotspot,
            hotspot_severity
        FROM ranked
        """
    )


def write_hotspots(con: Any, hotspots_path: Path) -> None:
    columns_sql = ", ".join(ident(column) for column in HOTSPOT_OUTPUT_COLUMNS)
    hotspots_path.parent.mkdir(parents=True, exist_ok=True)
    unlink_existing_outputs([hotspots_path])
    con.execute(
        f"""
        COPY (
            SELECT {columns_sql}
            FROM hotspots
            ORDER BY rank_overall
        ) TO {sql_string(hotspots_path)} (FORMAT PARQUET)
        """
    )


def build_record_counts(con: Any) -> dict[str, Any]:
    return fetch_one(
        con,
        """
        SELECT
            (SELECT COUNT(*)::BIGINT FROM precinct_hotspot_base)
                AS candidate_precinct_offense_rows,
            (SELECT COUNT(*)::BIGINT FROM grid_hotspot_base)
                AS candidate_grid_offense_rows,
            (SELECT COUNT(*) FILTER (
                WHERE hotspot_grain = 'precinct'
                    AND passes_volume_filter
            )::BIGINT FROM hotspot_candidates) AS evaluated_precinct_offense_rows,
            (SELECT COUNT(*) FILTER (
                WHERE hotspot_grain = 'grid'
                    AND passes_volume_filter
            )::BIGINT FROM hotspot_candidates) AS evaluated_grid_offense_rows,
            (SELECT COUNT(*)::BIGINT FROM hotspots) AS hotspot_rows,
            (SELECT COUNT(*) FILTER (WHERE hotspot_grain = 'precinct')::BIGINT FROM hotspots)
                AS precinct_hotspot_rows,
            (SELECT COUNT(*) FILTER (WHERE hotspot_grain = 'grid')::BIGINT FROM hotspots)
                AS grid_hotspot_rows,
            (SELECT COUNT(*) FILTER (WHERE hotspot_severity IN ('high', 'critical'))::BIGINT
                FROM hotspots) AS high_or_critical_hotspot_rows
        """
    )


def build_analysis_window(
    con: Any,
    input_summary: dict[str, Any],
    *,
    windows: dict[str, date],
    scoring_end_date: date,
    latest_date_excluded_from_scoring: bool,
) -> dict[str, Any]:
    scored_window = fetch_one(
        con,
        """
        SELECT
            MIN(scoring_end_date) AS candidate_scoring_end_date,
            MIN(recent_window_days)::INTEGER AS recent_window_days,
            MIN(baseline_window_days)::INTEGER AS baseline_window_days
        FROM hotspot_candidates
        """,
    )
    return {
        **input_summary,
        **windows,
        "scoring_end_date": scoring_end_date,
        "latest_date_excluded_from_scoring": latest_date_excluded_from_scoring,
        **scored_window,
    }


def build_severity_counts(con: Any) -> list[dict[str, Any]]:
    rows = fetch_dicts(
        con,
        """
        SELECT
            hotspot_grain,
            hotspot_severity,
            COUNT(*)::BIGINT AS hotspot_count,
            SUM(recent_event_count)::BIGINT AS recent_event_count,
            ROUND(AVG(composite_score), 4) AS avg_composite_score,
            ROUND(MAX(composite_score), 4) AS max_composite_score
        FROM hotspots
        GROUP BY 1, 2
        """
    )
    by_key = {
        (row["hotspot_grain"], row["hotspot_severity"]): row
        for row in rows
    }
    completed = []
    for grain in ["precinct", "grid"]:
        for label in SEVERITY_LABELS:
            row = by_key.get((grain, label)) or {
                "hotspot_grain": grain,
                "hotspot_severity": label,
                "hotspot_count": 0,
                "recent_event_count": 0,
                "avg_composite_score": None,
                "max_composite_score": None,
            }
            completed.append(row)
    return normalize_rows(completed)


def build_top_hotspots(con: Any, *, grain: str, top_n: int) -> list[dict[str, Any]]:
    columns_sql = ", ".join(ident(column) for column in HOTSPOT_REPORT_COLUMNS)
    return normalize_rows(
        fetch_dicts(
            con,
            f"""
            SELECT {columns_sql}
            FROM hotspots
            WHERE hotspot_grain = {sql_string(grain)}
            ORDER BY rank_in_grain
            LIMIT {int(top_n)}
            """,
        )
    )


def build_coordinate_quality(con: Any) -> dict[str, Any]:
    return fetch_one(
        con,
        f"""
        WITH source_counts AS (
            SELECT
                COUNT(*)::BIGINT AS aggregate_event_rows,
                COUNT(*) FILTER (
                    WHERE latitude IS NOT NULL
                        AND longitude IS NOT NULL
                        AND latitude <> 0
                        AND longitude <> 0
                        AND latitude BETWEEN {NYC_LAT_MIN} AND {NYC_LAT_MAX}
                        AND longitude BETWEEN {NYC_LON_MIN} AND {NYC_LON_MAX}
                        AND NOT flag_missing_coordinates
                        AND NOT flag_zero_coordinates
                        AND NOT flag_coordinates_outside_broad_nyc_bounds
                )::BIGINT AS valid_coordinate_event_rows,
                COUNT(*) FILTER (
                    WHERE latitude IS NULL
                        OR longitude IS NULL
                        OR flag_missing_coordinates
                )::BIGINT AS missing_coordinate_event_rows,
                COUNT(*) FILTER (
                    WHERE latitude = 0
                        OR longitude = 0
                        OR flag_zero_coordinates
                )::BIGINT AS zero_coordinate_event_rows,
                COUNT(*) FILTER (
                    WHERE flag_coordinates_outside_broad_nyc_bounds
                        OR (
                            latitude IS NOT NULL
                            AND longitude IS NOT NULL
                            AND latitude <> 0
                            AND longitude <> 0
                            AND NOT (
                                latitude BETWEEN {NYC_LAT_MIN} AND {NYC_LAT_MAX}
                                AND longitude BETWEEN {NYC_LON_MIN} AND {NYC_LON_MAX}
                            )
                        )
                )::BIGINT AS out_of_bounds_coordinate_event_rows
            FROM clean_events
        )
        SELECT
            aggregate_event_rows,
            valid_coordinate_event_rows,
            ROUND(valid_coordinate_event_rows * 100.0 / NULLIF(aggregate_event_rows, 0), 6)
                AS valid_coordinate_coverage_pct,
            missing_coordinate_event_rows,
            zero_coordinate_event_rows,
            out_of_bounds_coordinate_event_rows
        FROM source_counts
        """
    )


def validate_hotspot_metrics_payload(payload: dict[str, Any]) -> None:
    missing_sections = [
        section for section in HOTSPOT_METRICS_REQUIRED_SECTIONS if section not in payload
    ]
    if missing_sections:
        raise ValueError(f"Hotspot metrics payload is missing required sections: {missing_sections}")

    used_columns = set(payload.get("hotspot_columns_used") or [])
    sensitive_columns = set(payload.get("ethics", {}).get("sensitive_columns_excluded") or [])
    overlap = used_columns.intersection(sensitive_columns)
    if overlap:
        raise ValueError(f"Sensitive columns cannot be used in hotspot detection: {sorted(overlap)}")

    if payload.get("output_columns") != HOTSPOT_OUTPUT_COLUMNS:
        raise ValueError("Hotspot metrics payload has an unexpected output column contract.")

    severity_pairs = {
        (row.get("hotspot_grain"), row.get("hotspot_severity"))
        for row in payload.get("severity_counts") or []
    }
    missing_pairs = [
        (grain, label)
        for grain in ["precinct", "grid"]
        for label in SEVERITY_LABELS
        if (grain, label) not in severity_pairs
    ]
    if missing_pairs:
        raise ValueError(f"Hotspot severity counts missing labels: {missing_pairs}")


def build_metrics_payload(
    con: Any,
    *,
    inputs: dict[str, Any],
    outputs: dict[str, Path],
    input_summary: dict[str, Any],
    windows: dict[str, date],
    config: HotspotConfig,
    scoring_end_date: date,
    latest_date_excluded_from_scoring: bool,
    top_n: int,
) -> dict[str, Any]:
    generated_at_utc = deterministic_generated_at_utc(scoring_end_date)
    payload = {
        "generated_at_utc": generated_at_utc,
        "phase": "Phase 6B - Aggregate Hotspot Detection Layer",
        "inputs": inputs,
        "outputs": {name: str(path) for name, path in outputs.items()},
        "run_metadata": {
            "generated_at_utc": generated_at_utc,
            "generated_at_utc_basis": (
                "Deterministic metadata timestamp derived from scoring_end_date "
                "at 00:00 UTC so reproduced outputs do not change across runs."
            ),
        },
        "hotspot_columns_used": HOTSPOT_COLUMNS_USED,
        "output_columns": HOTSPOT_OUTPUT_COLUMNS,
        "hotspot_config": {
            **config.as_dict(),
            "primary_recent_count": "recent_30_day_count",
            "baseline_expected_recent_count": (
                "baseline_event_count * recent_window_days / baseline_window_days"
            ),
            "coordinate_filter": (
                "non-missing, non-zero latitude/longitude inside broad NYC bounds "
                "and not flagged by Phase 2 coordinate quality flags"
            ),
            "recency_weighted_event_count": (
                "0.50 * recent_7_day_count + 0.35 * events from days 8-30 + "
                "0.15 * events from days 31-90"
            ),
            "output_filter": (
                "hotspots.parquet contains only rows where is_hotspot is true; "
                "candidate and evaluated-row counts are retained in hotspot_metrics.json."
            ),
            "share_denominators": {
                "precinct": (
                    "recent and baseline shares use all aggregate-safe events in the "
                    "corresponding time window."
                ),
                "grid": (
                    "recent and baseline shares use only valid-coordinate events in "
                    "the corresponding time window."
                ),
            },
        },
        "analysis_window": build_analysis_window(
            con,
            input_summary,
            windows=windows,
            scoring_end_date=scoring_end_date,
            latest_date_excluded_from_scoring=latest_date_excluded_from_scoring,
        ),
        "record_counts": build_record_counts(con),
        "severity_counts": build_severity_counts(con),
        "top_precinct_hotspots": build_top_hotspots(con, grain="precinct", top_n=top_n),
        "top_grid_hotspots": build_top_hotspots(con, grain="grid", top_n=top_n),
        "coordinate_quality": build_coordinate_quality(con),
        "leakage_controls": {
            "random_splits_used": False,
            "windows_based_on_max_clean_event_date": True,
            "latest_date_excluded_from_scoring": latest_date_excluded_from_scoring,
            "baseline_window_ends_before_recent_90_day_window": True,
            "baseline_end_date": windows["baseline_end_date"],
            "recent_90_start_date": windows["recent_90_start_date"],
            "future_events_after_scoring_end_used": False,
        },
        "ethics": {
            "sensitive_columns_excluded": SENSITIVE_COLUMNS,
            "aggregate_trend_intelligence_only": True,
            "person_level_prediction": False,
            "enforcement_recommendations": False,
            "note": (
                "Hotspot detection uses aggregate-safe event dates, locations, "
                "precincts, offense types, and law categories. It does not use "
                "suspect or victim demographics and does not produce patrol, "
                "enforcement, or person-level recommendations."
            ),
        },
    }
    validate_hotspot_metrics_payload(payload)
    return payload


def write_metrics_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, default=json_default)
        file.write("\n")


def write_hotspot_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    config = payload["hotspot_config"]
    window = payload["analysis_window"]
    counts = payload["record_counts"]
    coordinate_quality = payload["coordinate_quality"]

    lines = [
        "# NYPD Complaint Data Historic - Hotspot Methodology",
        "",
        f"Deterministic output timestamp UTC: `{payload['generated_at_utc']}`",
        "",
        payload["run_metadata"]["generated_at_utc_basis"],
        "",
        "## Scope",
        "",
        (
            "This Phase 6B layer identifies elevated recent aggregate crime density "
            "for precinct/offense/law-category and grid-cell/offense/law-category "
            "groups. It implements only hotspot detection; it does not create "
            "dashboard UI, APIs, patrol recommendations, enforcement recommendations, "
            "or person-level scores."
        ),
        "",
        "## Inputs and Outputs",
        "",
        "\n".join(f"- Input {name}: `{value}`" for name, value in payload["inputs"].items()),
        "\n".join(f"- Output {name}: `{value}`" for name, value in payload["outputs"].items()),
        "",
        "## Window Definitions",
        "",
        markdown_table(
            [
                {
                    "baseline_start_date": window["baseline_start_date"],
                    "baseline_end_date": window["baseline_end_date"],
                    "recent_90_start_date": window["recent_90_start_date"],
                    "recent_30_start_date": window["recent_30_start_date"],
                    "recent_7_start_date": window["recent_7_start_date"],
                    "scoring_end_date": window["scoring_end_date"],
                    "latest_date_excluded_from_scoring": window[
                        "latest_date_excluded_from_scoring"
                    ],
                }
            ]
        ),
        "",
        (
            "The latest cleaned event date is excluded by default because upstream "
            "extracts can contain a partial final day. Baseline counts end before "
            "the 90-day recent window starts, so baseline and recent windows do not overlap."
        ),
        "",
        "## Methodology",
        "",
        (
            "The script uses only rows where `is_clean_event_for_aggregate = true`. "
            "Precinct hotspots use all aggregate-safe events and attach a precinct "
            "centroid from valid coordinates where available. Grid hotspots use only "
            "events with map-ready coordinates."
        ),
        "",
        "Scoring formulas:",
        "",
        "- `recent_event_count = recent_30_day_count`.",
        "- `baseline_expected_recent_count = baseline_event_count * recent_window_days / baseline_window_days`.",
        "- `recent_share_total_events = recent_event_count / all recent events in the same grain * 100`.",
        "- `baseline_share_total_events = baseline_event_count / all baseline events in the same grain * 100`.",
        "- `share_change_pct_points = recent_share_total_events - baseline_share_total_events`.",
        "- `recent_baseline_ratio = recent_event_count / baseline_expected_recent_count`.",
        "- `recent_vs_baseline_lift_pct = (recent_baseline_ratio - 1) * 100`.",
        "- `density_score` is a 0-100 log-scaled recent-count score using grain-specific reference counts.",
        "- `recency_weighted_score` is a 0-100 log-scaled score from 7-, 30-, and 90-day weighted counts.",
        "- `composite_score = 0.35*density + 0.25*lift + 0.20*share_increase + 0.15*recency + 0.05*coordinate_quality`.",
        "",
        (
            "Share denominators differ by grain: precinct shares use all aggregate-safe "
            "events in the relevant time window, while grid shares use only "
            "valid-coordinate events because grid candidates require map-ready coordinates."
        ),
        "",
        (
            "A row can be flagged only after minimum recent and baseline volume gates "
            "are met. Defaults require at least "
            f"{config['min_precinct_recent_count']} recent and "
            f"{config['min_precinct_baseline_count']} baseline complaints for precinct "
            "groups, and at least "
            f"{config['min_grid_recent_count']} recent and "
            f"{config['min_grid_baseline_count']} baseline complaints for grid groups."
        ),
        "",
        (
            "`hotspots.parquet` contains only rows where `is_hotspot = true`; "
            "candidate and evaluated-row counts are retained in `hotspot_metrics.json`."
        ),
        "",
        "## Coordinate Filters",
        "",
        f"- Broad NYC latitude bounds: `{NYC_LAT_MIN}` to `{NYC_LAT_MAX}`",
        f"- Broad NYC longitude bounds: `{NYC_LON_MIN}` to `{NYC_LON_MAX}`",
        "- Coordinates must be non-missing and non-zero.",
        "- Phase 2 coordinate quality flags must not mark the row as missing, zero, or out of bounds.",
        f"- Grid size: `{config['grid_size_degrees']}` degrees.",
        "",
        "## Evaluation Summary",
        "",
        markdown_table(
            [
                {
                    "clean_aggregate_event_rows": window["clean_aggregate_event_rows"],
                    "valid_coordinate_event_rows": window["valid_coordinate_event_rows"],
                    "candidate_precinct_offense_rows": counts[
                        "candidate_precinct_offense_rows"
                    ],
                    "candidate_grid_offense_rows": counts["candidate_grid_offense_rows"],
                    "evaluated_precinct_offense_rows": counts[
                        "evaluated_precinct_offense_rows"
                    ],
                    "evaluated_grid_offense_rows": counts["evaluated_grid_offense_rows"],
                    "hotspot_rows": counts["hotspot_rows"],
                    "high_or_critical_hotspot_rows": counts[
                        "high_or_critical_hotspot_rows"
                    ],
                }
            ]
        ),
        "",
        "## Hotspot Counts by Severity",
        "",
        markdown_table(payload["severity_counts"]),
        "",
        "## Top Precinct Hotspots",
        "",
        markdown_table(payload["top_precinct_hotspots"], HOTSPOT_REPORT_COLUMNS),
        "",
        "## Top Grid Hotspots",
        "",
        markdown_table(payload["top_grid_hotspots"], HOTSPOT_REPORT_COLUMNS),
        "",
        "## Coordinate Coverage and Limitations",
        "",
        markdown_table([coordinate_quality]),
        "",
        "- Precinct rows can be scored without coordinates, but map centroids are available only where valid coordinate history exists.",
        "- Grid rows exclude missing, zero, and out-of-bounds coordinates, so they represent only map-ready complaint events.",
        "- A 0.01-degree grid is deterministic and easy to reproduce, but it is not an equal-area spatial index.",
        "- Coordinate centroids summarize complaint locations and should not be interpreted as exact incident addresses.",
        "",
        "## Limitations Before Dashboard Use",
        "",
        "- Hotspots describe elevated aggregate complaint density; they do not explain causality.",
        "- Reported complaint counts can be affected by reporting delay, classification changes, policy changes, and data revisions.",
        "- Fixed thresholds should be monitored for alert volume by borough, offense, and law category before dashboard release.",
        "- A dashboard should show volume gates, baseline counts, lift, coordinate coverage, and scoring window dates next to every hotspot.",
        "- This layer does not include uncertainty intervals, reporting-lag correction, event calendars, street-network topology, or spatial smoothing.",
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
    clean_events_path = resolve_path(
        project_root,
        args.clean_events_input,
        DEFAULT_PROCESSED_DIR / CLEAN_EVENTS_FILE,
    )
    weekly_path = resolve_path(
        project_root,
        args.weekly_input,
        DEFAULT_PROCESSED_DIR / WEEKLY_FILE,
    )
    hotspots_path = resolve_path(
        project_root,
        args.hotspots_output,
        DEFAULT_PROCESSED_DIR / HOTSPOTS_FILE,
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
    config = HotspotConfig(
        grid_size_degrees=args.grid_size_degrees,
        min_precinct_recent_count=args.min_precinct_recent_count,
        min_precinct_baseline_count=args.min_precinct_baseline_count,
        min_grid_recent_count=args.min_grid_recent_count,
        min_grid_baseline_count=args.min_grid_baseline_count,
        min_recent_baseline_ratio=args.min_recent_baseline_ratio,
        min_hotspot_score=args.min_hotspot_score,
    )
    validate_config(config)

    if not clean_events_path.exists():
        raise FileNotFoundError(f"Missing clean event input: {clean_events_path}")
    weekly_available = weekly_path.exists()

    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    hotspots_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    duckdb = require_duckdb()
    con = duckdb.connect(database=":memory:")
    con.execute(f"PRAGMA threads={int(args.threads)}")

    print("Validating clean event schema.")
    validate_parquet_columns(con, clean_events_path, CLEAN_EVENTS_REQUIRED_COLUMNS)
    validate_clean_source(con, clean_events_path)
    if weekly_available:
        print("Validating optional weekly aggregate schema.")
        validate_parquet_columns(con, weekly_path, WEEKLY_REQUIRED_COLUMNS)

    print("Creating aggregate-safe input views.")
    create_input_views(con, clean_events_path)
    input_summary = build_input_summary(con, weekly_path if weekly_available else None)
    min_event_date, max_event_date = get_event_date_bounds(con)
    scoring_end_date = compute_scoring_end_date(
        min_event_date,
        max_event_date,
        include_latest_date=args.include_latest_date,
    )
    latest_date_excluded_from_scoring = scoring_end_date < max_event_date
    if latest_date_excluded_from_scoring:
        print(f"Excluding latest input date {max_event_date} from hotspot scoring.")
    windows = compute_window_bounds(scoring_end_date, config)

    print("Building precinct and grid hotspot candidates.")
    create_hotspot_views(con, windows=windows, config=config)
    print(f"Writing hotspots to {hotspots_path}.")
    write_hotspots(con, hotspots_path)

    outputs = {
        "hotspots": hotspots_path,
        "metrics": metrics_path,
        "report": report_path,
    }
    inputs = {
        "clean_events": str(clean_events_path),
        "weekly_area": str(weekly_path) if weekly_available else None,
    }
    metrics_payload = build_metrics_payload(
        con,
        inputs=inputs,
        outputs=outputs,
        input_summary=input_summary,
        windows=windows,
        config=config,
        scoring_end_date=scoring_end_date,
        latest_date_excluded_from_scoring=latest_date_excluded_from_scoring,
        top_n=args.top_n,
    )
    print(f"Writing hotspot metrics to {metrics_path}.")
    write_metrics_json(metrics_path, metrics_payload)
    print(f"Writing hotspot methodology report to {report_path}.")
    write_hotspot_report(report_path, metrics_payload)
    print(
        "Hotspot detection complete: "
        f"{metrics_payload['record_counts']['hotspot_rows']:,} hotspots from "
        f"{metrics_payload['record_counts']['evaluated_precinct_offense_rows']:,} "
        "evaluated precinct/offense rows and "
        f"{metrics_payload['record_counts']['evaluated_grid_offense_rows']:,} "
        "evaluated grid/offense rows."
    )


if __name__ == "__main__":
    main()

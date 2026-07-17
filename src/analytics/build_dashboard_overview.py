#!/usr/bin/env python3
"""Build the compact, aggregate-safe Phase 7A Overview data contract.

The browser receives a small JSON metadata/signal document plus a gzip-compressed
columnar cube.  It never receives complaint-level records.  All dates and the
generated timestamp are derived from the processed data rather than the clock.

Run from the repository root:

    .venv/bin/python src/analytics/build_dashboard_overview.py
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import os
import shutil
import sys
from array import array
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_DASHBOARD_DATA_DIR = Path("dashboard/public/data")
DEFAULT_MODEL_DIR = Path("models/weekly_forecast")
DEFAULT_BASELINE_MODEL_DIR = Path("models/baseline_forecast")

CLEAN_EVENTS_FILE = "complaints_clean.parquet"
WEEKLY_FILE = "crime_weekly_area.parquet"
ANOMALIES_FILE = "anomalies.parquet"
HOTSPOTS_FILE = "hotspots.parquet"
ML_PREDICTIONS_FILE = "ml_predictions.parquet"
ANOMALY_METRICS_FILE = "anomaly_metrics.json"
HOTSPOT_METRICS_FILE = "hotspot_metrics.json"
ML_METRICS_FILE = "ml_metrics.json"
MODEL_MANIFEST_FILE = "model_manifest.json"

OVERVIEW_FILE = "overview.json"
CUBE_FILE = "overview-cube.bin.gz"
PROCESSED_OVERVIEW_FILE = "dashboard_overview.json"
PROCESSED_CUBE_FILE = "dashboard_overview_cube.bin.gz"
SCHEMA_VERSION = "1.0.0"

SENSITIVE_COLUMNS = [
    "SUSP_AGE_GROUP",
    "SUSP_RACE",
    "SUSP_SEX",
    "VIC_AGE_GROUP",
    "VIC_RACE",
    "VIC_SEX",
]

QUALITY_FLAG_FIELDS = {
    "missingInvalidComplaintStartDate": "flag_missing_invalid_complaint_start_date",
    "implausiblyOldComplaintStartDate": "flag_implausibly_old_complaint_start_date",
    "futureComplaintStartDate": "flag_future_complaint_start_date",
    "futureComplaintEndDate": "flag_future_complaint_end_date",
    "complaintEndBeforeStart": "flag_complaint_end_before_start",
    "reportDateBeforeComplaintStart": "flag_report_date_before_complaint_start",
    "missingBorough": "flag_missing_borough",
    "missingPrecinct": "flag_missing_precinct",
    "missingOffense": "flag_missing_offense",
    "missingCoordinates": "flag_missing_coordinates",
    "zeroCoordinates": "flag_zero_coordinates",
    "coordinatesOutsideBroadNycBounds": (
        "flag_coordinates_outside_broad_nyc_bounds"
    ),
    "invalidLawCategory": "flag_invalid_law_category",
}
CLEAN_DIMENSION_FIELDS = {
    "borough": "borough",
    "precinct": "precinct",
    "offense": "offense_type",
    "lawCategory": "law_category",
}
CLEAN_REQUIRED_COLUMNS = [
    "complaint_from_date",
    "is_clean_event_for_aggregate",
    *CLEAN_DIMENSION_FIELDS.values(),
    *QUALITY_FLAG_FIELDS.values(),
]
WEEKLY_REQUIRED_COLUMNS = [
    "week_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "crime_count",
]
ANOMALY_REQUIRED_COLUMNS = [
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
    "is_anomaly",
    "passes_volume_filter",
    "anomaly_severity",
    "anomaly_score",
]
ANOMALY_SEVERITIES = ["low", "medium", "high", "critical"]
ANOMALY_STATUSES = {"available", "missing", "invalid", "stale", "incompatible"}
ANOMALY_METRICS_PHASE = "Phase 6A - Anomaly Detection Layer"
ANOMALY_HISTORICAL_METHOD = "trailing_13_week_mean over prior weeks only"
ANOMALY_ARITHMETIC_TOLERANCE = 0.000001
HOTSPOT_REQUIRED_COLUMNS = [
    "hotspot_grain",
    "borough",
    "precinct",
    "grid_latitude",
    "grid_longitude",
    "offense_type",
    "law_category",
    "scoring_end_date",
    "recent_event_count",
    "baseline_expected_recent_count",
    "recent_vs_baseline_lift_pct",
    "composite_score",
    "is_high_or_critical_hotspot",
    "hotspot_severity",
]
FORECAST_REQUIRED_COLUMNS = [
    "week_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "predicted_crime_count",
    "ml_model_name",
    "is_next_week_forecast",
]

ANOMALY_ROW_COLUMNS = [
    "weekIndex",
    "boroughIndex",
    "precinctIndex",
    "offenseTypeIndex",
    "lawCategoryIndex",
    "actualCount",
    "expectedCount",
    "residualCount",
    "score",
    "severityIndex",
    "expectedSourceIndex",
]
HOTSPOT_ROW_COLUMNS = [
    "grainIndex",
    "boroughIndex",
    "precinctIndex",
    "offenseTypeIndex",
    "lawCategoryIndex",
    "scoringEndDate",
    "locationLabel",
    "recentCount",
    "expectedRecentCount",
    "liftPct",
    "score",
    "severityIndex",
]
FORECAST_ROW_COLUMNS = [
    "weekIndex",
    "boroughIndex",
    "precinctIndex",
    "offenseTypeIndex",
    "lawCategoryIndex",
    "predictedCount",
    "modelNameIndex",
]

CUBE_COLUMN_ORDER = [
    "counts",
    "weeks",
    "boroughs",
    "precincts",
    "offenses",
    "laws",
    "weekRowOffsets",
]
CUBE_TYPES = {
    "counts": "uint32",
    "weeks": "uint16",
    "boroughs": "uint8",
    "precincts": "uint8",
    "offenses": "uint8",
    "laws": "uint8",
    "weekRowOffsets": "uint32",
}
CUBE_TYPE_WIDTHS = {"uint32": 4, "uint16": 2, "uint8": 1}


class OptionalContractError(ValueError):
    """A frontend-unsafe optional analytical value or shape."""


def require_duckdb() -> Any:
    try:
        import duckdb  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment failure
        raise SystemExit(
            "Missing dependency: duckdb. Run in the local virtual environment "
            "or install the repository requirements."
        ) from exc
    return duckdb


def sql_string(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def resolve_path(project_root: Path, value: Path | None, default_relative: Path) -> Path:
    candidate = default_relative if value is None else value
    return candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()


def fetch_dicts(con: Any, sql: str) -> list[dict[str, Any]]:
    result = con.execute(sql)
    names = [column[0] for column in result.description]
    return [dict(zip(names, row)) for row in result.fetchall()]


def iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value)


def compact_number(value: Any, digits: int = 4) -> int | float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    rounded = round(number, digits)
    return int(rounded) if rounded.is_integer() else rounded


def required_number(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    integer: bool = False,
) -> int | float:
    if value is None or isinstance(value, bool):
        raise OptionalContractError(f"Invalid required numeric field: {label}.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OptionalContractError(
            f"Invalid required numeric field: {label}."
        ) from exc
    if (
        not math.isfinite(number)
        or (minimum is not None and number < minimum)
        or (maximum is not None and number > maximum)
    ):
        raise OptionalContractError(f"Invalid required numeric field: {label}.")
    if integer:
        if not number.is_integer():
            raise OptionalContractError(f"Invalid required integer field: {label}.")
        return int(number)
    compact = compact_number(number)
    if compact is None:  # protected by the finite check; retained for contract clarity
        raise OptionalContractError(f"Invalid required numeric field: {label}.")
    return compact


def required_date(value: Any, label: str) -> str:
    text = iso_date(value)
    if text is None:
        raise OptionalContractError(f"Missing required date field: {label}.")
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise OptionalContractError(f"Invalid required date field: {label}.") from exc
    return text


def required_text(value: Any, label: str) -> str:
    if value is None or not str(value).strip():
        raise OptionalContractError(f"Missing required text field: {label}.")
    return str(value).strip()


def validate_unique_records(
    records: list[dict[str, Any]], key_fields: tuple[str, ...], label: str
) -> None:
    seen: set[tuple[Any, ...]] = set()
    for record in records:
        key = tuple(record[field] for field in key_fields)
        if key in seen:
            raise OptionalContractError(f"Duplicate {label} logical key detected.")
        seen.add(key)


def normalized_string(value: Any, *, nullable: bool = False) -> str | None:
    if value is None:
        return None if nullable else "UNKNOWN"
    text = str(value).strip()
    if not text:
        return None if nullable else "UNKNOWN"
    return text


def deterministic_generated_at_utc(max_safe_event_date: date | None) -> str | None:
    return None if max_safe_event_date is None else f"{max_safe_event_date.isoformat()}T00:00:00Z"


def parquet_columns(con: Any, path: Path) -> set[str]:
    return {
        str(row[0])
        for row in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet({sql_string(path)})"
        ).fetchall()
    }


def parquet_column_types(con: Any, path: Path) -> dict[str, str]:
    return {
        str(row[0]): str(row[1]).upper()
        for row in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet({sql_string(path)})"
        ).fetchall()
    }


def require_parquet_columns(
    con: Any, path: Path, required: list[str], label: str
) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required {label} input not found: {path}")
    missing = sorted(set(required).difference(parquet_columns(con, path)))
    if missing:
        raise ValueError(f"{label} input is missing required columns: {', '.join(missing)}")


def optional_error(path: Path, reason: str) -> dict[str, Any]:
    return {
        "status": "invalid",
        "sourceFile": path.name,
        "reason": reason,
        "records": [],
    }


def little_endian_array_bytes(values: array) -> bytes:
    if sys.byteorder == "little" or values.itemsize == 1:
        return values.tobytes()
    copy = array(values.typecode, values)
    copy.byteswap()
    return copy.tobytes()


def _missing_optional(path: Path) -> dict[str, Any]:
    return {"status": "missing", "sourceFile": path.name, "records": []}


def _require_anomaly_parquet_types(con: Any, path: Path) -> None:
    types = parquet_column_types(con, path)
    required_exact = {
        "week_start": "DATE",
        "borough": "VARCHAR",
        "precinct": "VARCHAR",
        "offense_type": "VARCHAR",
        "law_category": "VARCHAR",
        "expected_count_source": "VARCHAR",
        "is_anomaly": "BOOLEAN",
        "passes_volume_filter": "BOOLEAN",
        "anomaly_severity": "VARCHAR",
    }
    for column, expected_type in required_exact.items():
        if types.get(column) != expected_type:
            raise OptionalContractError(
                f"Anomaly column {column} must be {expected_type}."
            )
    if not types.get("actual_crime_count", "").startswith(
        (
            "TINYINT",
            "SMALLINT",
            "INTEGER",
            "BIGINT",
            "HUGEINT",
            "UTINYINT",
            "USMALLINT",
            "UINTEGER",
            "UBIGINT",
        )
    ):
        raise OptionalContractError(
            "Anomaly column actual_crime_count must be an integer."
        )
    numeric_prefixes = (
        "TINYINT",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "HUGEINT",
        "UTINYINT",
        "USMALLINT",
        "UINTEGER",
        "UBIGINT",
        "FLOAT",
        "DOUBLE",
        "DECIMAL",
    )
    for column in (
        "expected_count",
        "expected_historical_count",
        "expected_ml_count",
        "residual_count",
        "anomaly_score",
    ):
        if not types.get(column, "").startswith(numeric_prefixes):
            raise OptionalContractError(f"Anomaly column {column} must be numeric.")


def _validate_anomaly_source(con: Any, path: Path) -> dict[str, Any]:
    stats = fetch_dicts(
        con,
        f"""
        SELECT
            COUNT(*)::BIGINT AS source_row_count,
            COUNT(DISTINCT (
                week_start, borough, precinct, offense_type, law_category
            ))::BIGINT AS distinct_logical_key_count,
            MIN(week_start) AS min_week,
            MAX(week_start) AS max_week,
            COUNT(*) FILTER (
                WHERE week_start IS NULL OR dayofweek(week_start) != 1
            )::BIGINT AS invalid_week_rows,
            COUNT(*) FILTER (
                WHERE borough IS NULL OR trim(borough) = ''
                   OR precinct IS NULL OR trim(precinct) = ''
                   OR offense_type IS NULL OR trim(offense_type) = ''
                   OR law_category IS NULL OR trim(law_category) = ''
            )::BIGINT AS invalid_dimension_rows,
            COUNT(*) FILTER (
                WHERE actual_crime_count IS NULL OR actual_crime_count < 0
            )::BIGINT AS invalid_actual_rows,
            COUNT(*) FILTER (
                WHERE expected_count IS NULL OR NOT isfinite(expected_count)
                   OR expected_count < 0
                   OR expected_historical_count IS NOT NULL
                      AND (NOT isfinite(expected_historical_count)
                           OR expected_historical_count < 0)
                   OR expected_ml_count IS NOT NULL
                      AND (NOT isfinite(expected_ml_count) OR expected_ml_count < 0)
            )::BIGINT AS invalid_expected_rows,
            COUNT(*) FILTER (
                WHERE residual_count IS NULL OR NOT isfinite(residual_count)
            )::BIGINT AS invalid_residual_rows,
            COUNT(*) FILTER (
                WHERE anomaly_score IS NULL OR NOT isfinite(anomaly_score)
                   OR anomaly_score < 0
            )::BIGINT AS invalid_score_rows,
            COUNT(*) FILTER (
                WHERE expected_count_source IS NULL
                   OR expected_count_source NOT IN ('ml_prediction', 'rolling_13_week_mean')
            )::BIGINT AS invalid_expected_source_rows,
            COUNT(*) FILTER (
                WHERE anomaly_severity IS NULL
                   OR anomaly_severity NOT IN ('low', 'medium', 'high', 'critical')
            )::BIGINT AS invalid_severity_rows,
            COUNT(*) FILTER (
                WHERE is_anomaly IS DISTINCT FROM true
                   OR passes_volume_filter IS DISTINCT FROM true
            )::BIGINT AS invalid_flag_rows,
            COUNT(*) FILTER (
                WHERE abs(
                    CAST(actual_crime_count AS DOUBLE) - expected_count - residual_count
                ) > {ANOMALY_ARITHMETIC_TOLERANCE}
            )::BIGINT AS inconsistent_residual_rows,
            COUNT(*) FILTER (
                WHERE anomaly_severity IN ('high', 'critical')
                  AND residual_count <= 0
            )::BIGINT AS nonpositive_published_residual_rows,
            COUNT(*) FILTER (
                WHERE expected_count_source = 'rolling_13_week_mean'
                  AND (
                      expected_historical_count IS NULL
                      OR NOT isfinite(expected_historical_count)
                      OR abs(expected_count - expected_historical_count)
                         > {ANOMALY_ARITHMETIC_TOLERANCE}
                  )
            )::BIGINT AS inconsistent_historical_source_rows,
            COUNT(*) FILTER (
                WHERE expected_count_source = 'ml_prediction'
                  AND (
                      expected_ml_count IS NULL
                      OR NOT isfinite(expected_ml_count)
                      OR abs(expected_count - expected_ml_count)
                         > {ANOMALY_ARITHMETIC_TOLERANCE}
                  )
            )::BIGINT AS inconsistent_ml_source_rows
        FROM read_parquet({sql_string(path)})
        """,
    )[0]
    checks = (
        ("invalid_week_rows", "Anomaly weeks must be non-null Mondays."),
        ("invalid_dimension_rows", "Anomaly dimensions must be nonblank text."),
        ("invalid_actual_rows", "Anomaly actual counts must be nonnegative integers."),
        (
            "invalid_expected_rows",
            "Anomaly expected_count values must be finite and nonnegative.",
        ),
        ("invalid_residual_rows", "Anomaly residual values must be finite."),
        ("invalid_score_rows", "Anomaly scores must be finite and nonnegative."),
        ("invalid_expected_source_rows", "Anomaly expected-count source is unsupported."),
        ("invalid_severity_rows", "Anomaly severity is unsupported."),
        ("invalid_flag_rows", "Anomaly and volume-eligibility flags must both be true."),
        ("inconsistent_residual_rows", "Anomaly residual arithmetic is inconsistent."),
        (
            "nonpositive_published_residual_rows",
            "High and critical anomaly residuals must be positive.",
        ),
        (
            "inconsistent_historical_source_rows",
            "Historical anomaly reference does not match its documented source value.",
        ),
        (
            "inconsistent_ml_source_rows",
            "ML anomaly reference does not match its documented source value.",
        ),
    )
    for key, reason in checks:
        if int(stats[key]):
            raise OptionalContractError(reason)
    if int(stats["source_row_count"]) != int(stats["distinct_logical_key_count"]):
        raise OptionalContractError("Duplicate anomaly logical key detected.")
    severity_counts = {
        str(row["anomaly_severity"]): int(row["anomaly_count"])
        for row in fetch_dicts(
            con,
            f"""
            SELECT anomaly_severity, COUNT(*)::BIGINT AS anomaly_count
            FROM read_parquet({sql_string(path)})
            GROUP BY anomaly_severity
            ORDER BY anomaly_severity
            """,
        )
    }
    return {
        "sourceRowCount": int(stats["source_row_count"]),
        "severityCounts": {
            severity: severity_counts.get(severity, 0)
            for severity in ANOMALY_SEVERITIES
        },
        "minWeek": iso_date(stats["min_week"]),
        "maxWeek": iso_date(stats["max_week"]),
    }


def load_optional_anomalies(con: Any, path: Path) -> dict[str, Any]:
    if not path.exists():
        return _missing_optional(path)
    try:
        missing = sorted(set(ANOMALY_REQUIRED_COLUMNS).difference(parquet_columns(con, path)))
        if missing:
            return optional_error(path, f"Missing required columns: {missing}")
        _require_anomaly_parquet_types(con, path)
        source_summary = _validate_anomaly_source(con, path)
        rows = fetch_dicts(
            con,
            f"""
            SELECT
                week_start,
                borough,
                precinct,
                offense_type,
                law_category,
                actual_crime_count,
                expected_count,
                expected_count_source,
                residual_count,
                anomaly_score,
                anomaly_severity AS severity
            FROM read_parquet({sql_string(path)})
            WHERE is_anomaly IS TRUE
              AND anomaly_severity IN ('high', 'critical')
            ORDER BY
                CASE anomaly_severity
                    WHEN 'critical' THEN 0 ELSE 1
                END,
                anomaly_score DESC NULLS LAST,
                week_start DESC,
                borough, precinct, offense_type, law_category
            """,
        )
        records = []
        for row in rows:
            record = {
                "week": required_date(row["week_start"], "anomaly week_start"),
                "borough": required_text(row["borough"], "anomaly borough"),
                "precinct": required_text(row["precinct"], "anomaly precinct"),
                "offenseType": required_text(
                    row["offense_type"], "anomaly offense_type"
                ),
                "lawCategory": required_text(
                    row["law_category"], "anomaly law_category"
                ),
                "actualCount": required_number(
                    row["actual_crime_count"],
                    "anomaly actual_crime_count",
                    minimum=0,
                    integer=True,
                ),
                "expectedCount": required_number(
                    row["expected_count"], "anomaly expected_count", minimum=0
                ),
                "expectedSource": required_text(
                    row["expected_count_source"], "anomaly expected_count_source"
                ),
                "residualCount": required_number(
                    row["residual_count"], "anomaly residual_count"
                ),
                "score": required_number(
                    row["anomaly_score"], "anomaly anomaly_score", minimum=0
                ),
                "severity": required_text(
                    row["severity"], "anomaly anomaly_severity"
                ),
            }
            if float(record["residualCount"]) <= 0:
                raise OptionalContractError(
                    "High and critical anomaly residuals must remain positive after publication rounding."
                )
            if not math.isclose(
                float(record["actualCount"]) - float(record["expectedCount"]),
                float(record["residualCount"]),
                rel_tol=0,
                abs_tol=0.0001,
            ):
                raise OptionalContractError(
                    "Published anomaly residual arithmetic is inconsistent."
                )
            records.append(record)
        validate_unique_records(
            records,
            ("week", "borough", "precinct", "offenseType", "lawCategory"),
            "anomaly",
        )
        records.sort(
            key=lambda record: (
                0 if record["severity"] == "critical" else 1,
                -float(record["score"]),
                -date.fromisoformat(record["week"]).toordinal(),
                record["borough"],
                record["precinct"],
                record["offenseType"],
                record["lawCategory"],
                -int(record["actualCount"]),
                -float(record["expectedCount"]),
                record["expectedSource"],
                -float(record["residualCount"]),
            )
        )
        return {
            "status": "available",
            "sourceFile": path.name,
            "records": records,
            **source_summary,
        }
    except OptionalContractError as exc:
        return optional_error(path, str(exc))
    except Exception as exc:  # optional data must not break the Overview
        return optional_error(path, f"{type(exc).__name__}: input could not be read")


def load_optional_hotspots(
    con: Any, path: Path, safe_event_end_date: date | datetime | str
) -> dict[str, Any]:
    if not path.exists():
        return _missing_optional(path)
    try:
        missing = sorted(set(HOTSPOT_REQUIRED_COLUMNS).difference(parquet_columns(con, path)))
        if missing:
            return optional_error(path, f"Missing required columns: {missing}")
        snapshot_stats = fetch_dicts(
            con,
            f"""
            SELECT
                COUNT(*)::BIGINT AS row_count,
                COUNT(*) FILTER (WHERE scoring_end_date IS NULL)::BIGINT AS null_dates,
                COUNT(DISTINCT scoring_end_date)::BIGINT AS distinct_dates,
                MIN(scoring_end_date) AS min_date,
                MAX(scoring_end_date) AS max_date
            FROM read_parquet({sql_string(path)})
            """,
        )[0]
        if snapshot_stats["null_dates"]:
            raise OptionalContractError("Hotspot snapshot contains a missing scoring date.")
        if int(snapshot_stats["distinct_dates"]) > 1:
            raise OptionalContractError(
                "Hotspot output must contain exactly one scoring snapshot date."
            )
        snapshot_date = (
            required_date(snapshot_stats["max_date"], "hotspot scoring_end_date")
            if snapshot_stats["row_count"]
            else None
        )
        safe_date = required_date(safe_event_end_date, "maximum safe event date")
        if snapshot_date is not None and snapshot_date > safe_date:
            raise OptionalContractError(
                "Hotspot snapshot date cannot exceed the maximum aggregate-safe event date."
            )
        snapshot_age_days = (
            (date.fromisoformat(safe_date) - date.fromisoformat(snapshot_date)).days
            if snapshot_date is not None
            else None
        )

        rows = fetch_dicts(
            con,
            f"""
            SELECT
                lower(CAST(hotspot_grain AS VARCHAR)) AS grain,
                CAST(borough AS VARCHAR) AS borough,
                CAST(precinct AS VARCHAR) AS precinct,
                grid_latitude,
                grid_longitude,
                CAST(offense_type AS VARCHAR) AS offense_type,
                CAST(law_category AS VARCHAR) AS law_category,
                scoring_end_date,
                recent_event_count,
                baseline_expected_recent_count,
                recent_vs_baseline_lift_pct,
                composite_score,
                lower(CAST(hotspot_severity AS VARCHAR)) AS severity
            FROM read_parquet({sql_string(path)})
            WHERE is_high_or_critical_hotspot IS TRUE
              AND lower(CAST(hotspot_severity AS VARCHAR)) IN ('high', 'critical')
            ORDER BY
                CASE lower(CAST(hotspot_severity AS VARCHAR))
                    WHEN 'critical' THEN 0 ELSE 1
                END,
                composite_score DESC NULLS LAST,
                hotspot_grain, borough, precinct NULLS LAST, offense_type, law_category
            """,
        )
        records = []
        for row in rows:
            grain = required_text(row["grain"], "hotspot hotspot_grain").lower()
            if grain not in {"grid", "precinct"}:
                raise OptionalContractError("Unsupported hotspot grain.")
            precinct = normalized_string(row["precinct"], nullable=True)
            location_label = None
            if grain == "grid":
                latitude = float(
                    required_number(row["grid_latitude"], "hotspot grid_latitude")
                )
                longitude = float(
                    required_number(row["grid_longitude"], "hotspot grid_longitude")
                )
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    raise OptionalContractError("Hotspot grid coordinates are invalid.")
                location_label = f"GRID {latitude:.3f}, {longitude:.3f}"
            elif precinct is None:
                raise OptionalContractError(
                    "Precinct hotspot is missing its aggregate precinct identifier."
                )
            record_date = required_date(
                row["scoring_end_date"], "hotspot scoring_end_date"
            )
            if snapshot_date is not None and record_date != snapshot_date:
                raise OptionalContractError(
                    "Hotspot rows do not share the declared snapshot date."
                )
            records.append(
                {
                    "grain": grain,
                    "borough": normalized_string(row["borough"]),
                    "precinct": precinct,
                    "offenseType": normalized_string(row["offense_type"]),
                    "lawCategory": normalized_string(row["law_category"]),
                    "scoringEndDate": record_date,
                    "locationLabel": location_label,
                    "recentCount": required_number(
                        row["recent_event_count"],
                        "hotspot recent_event_count",
                        minimum=0,
                        integer=True,
                    ),
                    "expectedRecentCount": required_number(
                        row["baseline_expected_recent_count"],
                        "hotspot baseline_expected_recent_count",
                        minimum=0,
                    ),
                    "liftPct": required_number(
                        row["recent_vs_baseline_lift_pct"],
                        "hotspot recent_vs_baseline_lift_pct",
                    ),
                    "score": required_number(
                        row["composite_score"],
                        "hotspot composite_score",
                        minimum=0,
                    ),
                    "severity": required_text(
                        row["severity"], "hotspot hotspot_severity"
                    ),
                }
            )
        validate_unique_records(
            records,
            (
                "scoringEndDate",
                "grain",
                "borough",
                "precinct",
                "locationLabel",
                "offenseType",
                "lawCategory",
            ),
            "hotspot",
        )
        records.sort(
            key=lambda record: (
                0 if record["severity"] == "critical" else 1,
                -float(record["score"]),
                record["grain"],
                record["borough"],
                record["precinct"] or "",
                record["locationLabel"] or "",
                record["offenseType"],
                record["lawCategory"],
                record["scoringEndDate"],
                -int(record["recentCount"]),
                -float(record["expectedRecentCount"]),
                -float(record["liftPct"]),
            )
        )
        return {
            "status": "available",
            "sourceFile": path.name,
            "records": records,
            "snapshotDate": snapshot_date,
            "snapshotAgeDays": snapshot_age_days,
        }
    except OptionalContractError as exc:
        return optional_error(path, str(exc))
    except Exception as exc:
        return optional_error(path, f"{type(exc).__name__}: input could not be read")


def load_optional_forecasts(con: Any, path: Path) -> dict[str, Any]:
    if not path.exists():
        return _missing_optional(path)
    try:
        missing = sorted(set(FORECAST_REQUIRED_COLUMNS).difference(parquet_columns(con, path)))
        if missing:
            return optional_error(path, f"Missing required columns: {missing}")
        rows = fetch_dicts(
            con,
            f"""
            SELECT
                week_start,
                CAST(borough AS VARCHAR) AS borough,
                CAST(precinct AS VARCHAR) AS precinct,
                CAST(offense_type AS VARCHAR) AS offense_type,
                CAST(law_category AS VARCHAR) AS law_category,
                predicted_crime_count,
                CAST(ml_model_name AS VARCHAR) AS model_name
            FROM read_parquet({sql_string(path)})
            WHERE is_next_week_forecast IS TRUE
            ORDER BY week_start, borough, precinct, offense_type, law_category, model_name
            """,
        )
        records = []
        for row in rows:
            records.append(
                {
                    "week": required_date(row["week_start"], "forecast week_start"),
                    "borough": normalized_string(row["borough"]),
                    "precinct": normalized_string(row["precinct"]),
                    "offenseType": normalized_string(row["offense_type"]),
                    "lawCategory": normalized_string(row["law_category"]),
                    "predictedCount": required_number(
                        row["predicted_crime_count"],
                        "forecast predicted_crime_count",
                        minimum=0,
                    ),
                    "modelName": required_text(
                        row["model_name"], "forecast ml_model_name"
                    ),
                }
            )
        validate_unique_records(
            records,
            (
                "week",
                "borough",
                "precinct",
                "offenseType",
                "lawCategory",
                "modelName",
            ),
            "forecast",
        )
        records.sort(
            key=lambda record: (
                record["week"],
                record["borough"],
                record["precinct"],
                record["offenseType"],
                record["lawCategory"],
                record["modelName"],
                float(record["predictedCount"]),
            )
        )
        return {"status": "available", "sourceFile": path.name, "records": records}
    except OptionalContractError as exc:
        return optional_error(path, str(exc))
    except Exception as exc:
        return optional_error(path, f"{type(exc).__name__}: input could not be read")


def read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "sourceFile": path.name, "data": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON root is not an object")
        return {"status": "available", "sourceFile": path.name, "data": data}
    except Exception as exc:
        return {
            "status": "invalid",
            "sourceFile": path.name,
            "reason": f"{type(exc).__name__}: metadata could not be read",
            "data": None,
        }


def metadata_version(source: dict[str, Any], *, model: bool = False) -> dict[str, Any]:
    if source["status"] != "available":
        result = {"status": source["status"], "sourceFile": source["sourceFile"]}
        if source.get("reason"):
            result["reason"] = source["reason"]
        return result
    data = source["data"]
    result: dict[str, Any] = {"status": "available", "sourceFile": source["sourceFile"]}
    for input_key, output_key in (
        ("phase", "phase"),
        ("generated_at_utc", "generatedAtUtc"),
        ("artifact_type", "artifactType"),
        ("artifact_version", "artifactVersion"),
        ("forecast_week", "forecastWeek"),
    ):
        if data.get(input_key) is not None:
            result[output_key] = data[input_key]
    if model:
        config = data.get("model") or data.get("model_config") or {}
        if config.get("model_name") is not None:
            result["modelName"] = config["model_name"]
        if config.get("model_version") is not None:
            result["modelVersion"] = config["model_version"]
    # Published error context comes from the metrics artifact, whose `overall`
    # section has one unambiguous selected-model row.  Manifests can contain
    # several candidate rows and are retained as version metadata only.
    overall = (data.get("metrics") or {}).get("overall") or []
    if overall:
        metric = overall[0]
        if metric.get("mae") is not None:
            result["backtestMae"] = compact_number(metric["mae"])
        if metric.get("rmse") is not None:
            result["backtestRmse"] = compact_number(metric["rmse"])
        if metric.get("weighted_mae") is not None:
            result["backtestWeightedMae"] = compact_number(metric["weighted_mae"])
        if metric.get("prediction_coverage_pct") is not None:
            result["predictionCoveragePct"] = compact_number(metric["prediction_coverage_pct"])
    return result


def _unavailable_anomalies(
    source: dict[str, Any],
    status: str,
    reason: str,
    *,
    scoring_end_week: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "sourceFile": source["sourceFile"],
        "reason": reason,
        "records": [],
    }
    if scoring_end_week is not None:
        result["scoringEndWeek"] = scoring_end_week
    return result


def gate_anomalies_with_metrics(
    anomalies: dict[str, Any],
    metrics: dict[str, Any],
    date_range: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed unless anomaly rows and their methodology horizon reconcile."""
    if anomalies["status"] != "available":
        return anomalies
    if metrics["status"] != "available":
        return _unavailable_anomalies(
            anomalies,
            metrics["status"],
            (
                "Anomaly signals were withheld because the companion anomaly metrics "
                f"artifact is {metrics['status']}."
            ),
        )

    data = metrics.get("data")
    if not isinstance(data, dict):
        return _unavailable_anomalies(
            anomalies, "invalid", "Anomaly metrics must be a JSON object."
        )
    if data.get("phase") != ANOMALY_METRICS_PHASE:
        return _unavailable_anomalies(
            anomalies,
            "incompatible",
            "Anomaly metrics identity is incompatible with the Phase 6A contract.",
        )
    if data.get("anomaly_columns_used") != WEEKLY_REQUIRED_COLUMNS:
        return _unavailable_anomalies(
            anomalies,
            "incompatible",
            "Anomaly metrics do not declare the established weekly aggregate inputs.",
        )
    output_columns = data.get("output_columns")
    if not isinstance(output_columns, list) or not set(ANOMALY_REQUIRED_COLUMNS).issubset(
        output_columns
    ):
        return _unavailable_anomalies(
            anomalies,
            "incompatible",
            "Anomaly metrics output-column contract is incompatible.",
        )
    config = data.get("anomaly_config")
    if not isinstance(config, dict) or config.get(
        "primary_historical_expected_count"
    ) != ANOMALY_HISTORICAL_METHOD:
        return _unavailable_anomalies(
            anomalies,
            "incompatible",
            "Anomaly metrics do not document the established historical expectation.",
        )
    leakage = data.get("leakage_controls")
    if not isinstance(leakage, dict) or not (
        leakage.get("historical_windows_use_prior_weeks_only") is True
        and leakage.get("random_splits_used") is False
    ):
        return _unavailable_anomalies(
            anomalies,
            "incompatible",
            "Anomaly metrics do not verify prior-only leakage controls.",
        )

    try:
        generated_at = required_text(
            data.get("generated_at_utc"), "anomaly metrics generated_at_utc"
        )
        generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        if generated.tzinfo is None:
            raise ValueError("timestamp has no timezone")
        analysis = data.get("analysis_window")
        if not isinstance(analysis, dict):
            raise OptionalContractError("Anomaly metrics analysis window is missing.")
        scoring_end_week = required_date(
            analysis.get("scoring_end_week"), "anomaly metrics scoring_end_week"
        )
        metrics_first_week = required_date(
            analysis.get("min_week_start"), "anomaly metrics min_week_start"
        )
        metrics_last_week = required_date(
            analysis.get("max_week_start"), "anomaly metrics max_week_start"
        )
        latest_excluded = analysis.get("latest_week_excluded_from_scoring")
        if not isinstance(latest_excluded, bool):
            raise OptionalContractError(
                "Anomaly metrics latest-week exclusion flag is invalid."
            )
        record_counts = data.get("record_counts")
        if not isinstance(record_counts, dict):
            raise OptionalContractError("Anomaly metrics record counts are missing.")
        anomaly_row_count = required_number(
            record_counts.get("anomaly_rows"),
            "anomaly metrics anomaly_rows",
            minimum=0,
            integer=True,
        )
        severity_rows = data.get("severity_counts")
        if not isinstance(severity_rows, list):
            raise OptionalContractError("Anomaly metrics severity counts are missing.")
        metrics_severity_counts: dict[str, int] = {}
        for row in severity_rows:
            if not isinstance(row, dict):
                raise OptionalContractError(
                    "Anomaly metrics severity-count row is invalid."
                )
            severity = required_text(
                row.get("anomaly_severity"), "anomaly metrics severity label"
            )
            if severity not in ANOMALY_SEVERITIES or severity in metrics_severity_counts:
                raise OptionalContractError(
                    "Anomaly metrics severity labels are invalid or duplicated."
                )
            metrics_severity_counts[severity] = int(
                required_number(
                    row.get("anomaly_count"),
                    "anomaly metrics severity count",
                    minimum=0,
                    integer=True,
                )
            )
        if set(metrics_severity_counts) != set(ANOMALY_SEVERITIES):
            raise OptionalContractError(
                "Anomaly metrics severity counts are incomplete."
            )
    except (OptionalContractError, TypeError, ValueError) as exc:
        return _unavailable_anomalies(
            anomalies, "invalid", f"Invalid anomaly metrics: {exc}"
        )

    if int(anomaly_row_count) != anomalies["sourceRowCount"]:
        return _unavailable_anomalies(
            anomalies,
            "invalid",
            "Anomaly metrics row count does not reconcile to the source artifact.",
        )
    if metrics_severity_counts != anomalies["severityCounts"]:
        return _unavailable_anomalies(
            anomalies,
            "invalid",
            "Anomaly metrics severity counts do not reconcile to the source artifact.",
        )

    scoring_date = date.fromisoformat(scoring_end_week)
    metrics_first = date.fromisoformat(metrics_first_week)
    metrics_last = date.fromisoformat(metrics_last_week)
    overview_first = date.fromisoformat(date_range["firstWeek"])
    overview_last = date.fromisoformat(date_range["lastWeek"])
    overview_latest_complete = date.fromisoformat(date_range["latestCompleteWeek"])
    if any(
        value.isoweekday() != 1
        for value in (scoring_date, metrics_first, metrics_last)
    ):
        return _unavailable_anomalies(
            anomalies,
            "invalid",
            "Anomaly metrics analysis dates must be Monday week starts.",
        )
    if not metrics_first <= scoring_date <= metrics_last:
        return _unavailable_anomalies(
            anomalies,
            "invalid",
            "Anomaly metrics analysis horizon is internally inconsistent.",
        )
    if latest_excluded is not (scoring_date < metrics_last):
        return _unavailable_anomalies(
            anomalies,
            "invalid",
            "Anomaly metrics latest-week exclusion does not match its horizon.",
        )
    source_min = (
        date.fromisoformat(anomalies["minWeek"]) if anomalies["minWeek"] else None
    )
    source_max = (
        date.fromisoformat(anomalies["maxWeek"]) if anomalies["maxWeek"] else None
    )
    if source_min is not None and source_min < overview_first:
        return _unavailable_anomalies(
            anomalies,
            "invalid",
            "Anomaly source predates the validated Overview observation horizon.",
        )
    if source_max is not None and source_max > scoring_date:
        return _unavailable_anomalies(
            anomalies,
            "invalid",
            "Anomaly source extends beyond its documented scoring horizon.",
        )
    if metrics_first < overview_first or metrics_last > overview_last:
        return _unavailable_anomalies(
            anomalies,
            "incompatible",
            "Anomaly metrics observation horizon exceeds the Overview source horizon.",
        )
    if metrics_first > overview_first or metrics_last < overview_last:
        return _unavailable_anomalies(
            anomalies,
            "stale",
            "Anomaly metrics are behind the validated Overview observation horizon.",
            scoring_end_week=scoring_end_week,
        )
    if scoring_date < overview_latest_complete:
        return _unavailable_anomalies(
            anomalies,
            "stale",
            "Anomaly scoring is behind the latest complete Overview week.",
            scoring_end_week=scoring_end_week,
        )
    if scoring_date > overview_latest_complete:
        return _unavailable_anomalies(
            anomalies,
            "incompatible",
            "Anomaly scoring exceeds the latest complete Overview week.",
        )

    anomalies["scoringEndWeek"] = scoring_end_week
    return anomalies


def clean_data_quality_stats(con: Any, clean_path: Path) -> dict[str, Any]:
    """Return deterministic, aggregate-safe quality metadata for publication."""
    types = parquet_column_types(con, clean_path)
    if types.get("complaint_from_date") != "DATE":
        raise ValueError("Clean complaint_from_date must be DATE.")
    if types.get("is_clean_event_for_aggregate") != "BOOLEAN":
        raise ValueError("Clean aggregate eligibility must be BOOLEAN.")
    malformed_flags = sorted(
        column
        for column in QUALITY_FLAG_FIELDS.values()
        if types.get(column) != "BOOLEAN"
    )
    if malformed_flags:
        raise ValueError(
            "Clean quality flags must be BOOLEAN: " + ", ".join(malformed_flags)
        )

    issue_expression = " + ".join(
        f"CAST({column} AS INTEGER)" for column in QUALITY_FLAG_FIELDS.values()
    )
    issue_columns = ",\n            ".join(
        f"COUNT(*) FILTER (WHERE {column})::BIGINT AS {output_key}"
        for output_key, column in QUALITY_FLAG_FIELDS.items()
    )
    unknown_columns = ",\n            ".join(
        (
            "COUNT(*) FILTER (WHERE is_clean_event_for_aggregate IS TRUE "
            f"AND {column} IS NULL)::BIGINT AS unknown_{output_key}"
        )
        for output_key, column in CLEAN_DIMENSION_FIELDS.items()
    )
    stats = fetch_dicts(
        con,
        f"""
        SELECT
            COUNT(*)::BIGINT AS population_count,
            COUNT(*) FILTER (
                WHERE is_clean_event_for_aggregate IS NULL
            )::BIGINT AS null_aggregate_eligibility_rows,
            COUNT(*) FILTER (
                WHERE {' OR '.join(f'{column} IS NULL' for column in QUALITY_FLAG_FIELDS.values())}
            )::BIGINT AS null_quality_flag_rows,
            {issue_columns},
            COUNT(*) FILTER (WHERE ({issue_expression}) > 0)::BIGINT
                AS rows_with_any_issue,
            COUNT(*) FILTER (WHERE ({issue_expression}) > 1)::BIGINT
                AS rows_with_multiple_issues,
            COALESCE(MAX({issue_expression}), 0)::INTEGER AS maximum_issues_per_row,
            {unknown_columns}
        FROM read_parquet({sql_string(clean_path)})
        """,
    )[0]
    if stats["null_aggregate_eligibility_rows"]:
        raise ValueError("Clean aggregate eligibility contains null values.")
    if stats["null_quality_flag_rows"]:
        raise ValueError("Clean quality flags contain null values.")

    population_count = int(stats["population_count"])
    issue_counts = {
        output_key: int(stats[output_key]) for output_key in QUALITY_FLAG_FIELDS
    }
    rows_with_any_issue = int(stats["rows_with_any_issue"])
    rows_with_multiple_issues = int(stats["rows_with_multiple_issues"])
    maximum_issues_per_row = int(stats["maximum_issues_per_row"])
    if (
        any(count < 0 or count > population_count for count in issue_counts.values())
        or not 0 <= rows_with_multiple_issues <= rows_with_any_issue <= population_count
        or not 0 <= maximum_issues_per_row <= len(QUALITY_FLAG_FIELDS)
        or (rows_with_any_issue == 0 and maximum_issues_per_row != 0)
        or (rows_with_any_issue > 0 and maximum_issues_per_row < 1)
        or (rows_with_multiple_issues > 0 and maximum_issues_per_row < 2)
        or sum(issue_counts.values()) < rows_with_any_issue
    ):
        raise ValueError("Clean source issue counts are internally inconsistent.")

    source_issue_counts = {
        "populationCount": population_count,
        **issue_counts,
        "rowsWithAnyIssue": rows_with_any_issue,
        "rowsWithMultipleIssues": rows_with_multiple_issues,
        "maximumIssuesPerRow": maximum_issues_per_row,
        "categoriesOverlap": True,
        "countsAreNonAdditive": True,
    }
    aggregate_safe_unknown_counts = {
        "populationCount": None,
        **{
            output_key: int(stats[f"unknown_{output_key}"])
            for output_key in CLEAN_DIMENSION_FIELDS
        },
        "valuesRetained": True,
        "categoriesOverlap": True,
    }
    return {
        "sourceIssueCounts": source_issue_counts,
        "aggregateSafeUnknownCounts": aggregate_safe_unknown_counts,
    }


def weekly_unknown_counts(con: Any, weekly_path: Path) -> dict[str, int]:
    columns = ",\n            ".join(
        (
            "COALESCE(SUM(crime_count) FILTER (WHERE "
            f"CAST({column} AS VARCHAR) = 'UNKNOWN'), 0)::HUGEINT AS {output_key}"
        )
        for output_key, column in CLEAN_DIMENSION_FIELDS.items()
    )
    row = fetch_dicts(
        con,
        f"""
        SELECT {columns}
        FROM read_parquet({sql_string(weekly_path)})
        """,
    )[0]
    return {key: int(row[key]) for key in CLEAN_DIMENSION_FIELDS}


def clean_source_stats(con: Any, clean_path: Path) -> dict[str, Any]:
    """Return the mandatory aggregate summary derived from the cleaned source."""
    require_parquet_columns(con, clean_path, CLEAN_REQUIRED_COLUMNS, "clean events")
    quality = clean_data_quality_stats(con, clean_path)
    clean = fetch_dicts(
        con,
        f"""
        SELECT
            COUNT(*)::BIGINT AS source_rows,
            COUNT(*) FILTER (WHERE is_clean_event_for_aggregate IS TRUE)::BIGINT AS safe_rows,
            COUNT(*) FILTER (
                WHERE is_clean_event_for_aggregate IS TRUE
                  AND complaint_from_date IS NULL
            )::BIGINT AS safe_rows_missing_date,
            MIN(complaint_from_date) FILTER (
                WHERE is_clean_event_for_aggregate IS TRUE
            ) AS min_safe_date,
            MAX(complaint_from_date) FILTER (
                WHERE is_clean_event_for_aggregate IS TRUE
            ) AS max_safe_date
        FROM read_parquet({sql_string(clean_path)})
        """,
    )[0]
    if clean["safe_rows_missing_date"]:
        raise ValueError("Aggregate-safe cleaned events contain missing complaint dates.")
    return {
        "cleanSourceRows": int(clean["source_rows"]),
        "safeEventCount": int(clean["safe_rows"]),
        "safeEventStartDate": clean["min_safe_date"],
        "safeEventEndDate": clean["max_safe_date"],
        **quality,
    }


def mandatory_stats(con: Any, clean_path: Path, weekly_path: Path) -> dict[str, Any]:
    clean = clean_source_stats(con, clean_path)
    weekly = fetch_dicts(
        con,
        f"""
        SELECT
            COUNT(*)::BIGINT AS source_rows,
            COALESCE(SUM(crime_count), 0)::HUGEINT AS aggregate_count,
            MIN(week_start) AS min_week,
            MAX(week_start) AS max_week,
            COUNT(*) FILTER (
                WHERE week_start IS NULL OR borough IS NULL OR precinct IS NULL
                   OR offense_type IS NULL OR law_category IS NULL
                   OR crime_count IS NULL OR crime_count < 0
            )::BIGINT AS invalid_rows,
            COALESCE(MAX(crime_count), 0)::HUGEINT AS max_count
        FROM read_parquet({sql_string(weekly_path)})
        """,
    )[0]
    if weekly["invalid_rows"]:
        raise ValueError("Weekly aggregate contains null dimensions or invalid counts.")
    if int(weekly["max_count"]) > 4_294_967_295:
        raise ValueError("Weekly aggregate count exceeds the uint32 cube contract.")
    if int(clean["safeEventCount"]) != int(weekly["aggregate_count"]):
        raise ValueError(
            "Aggregate-safe cleaned event count does not reconcile to the weekly "
            f"aggregate sum ({clean['safeEventCount']} != {weekly['aggregate_count']})."
        )
    aggregate_safe_unknown_counts = dict(clean["aggregateSafeUnknownCounts"])
    aggregate_safe_unknown_counts["populationCount"] = int(clean["safeEventCount"])
    unknown_counts = {
        key: aggregate_safe_unknown_counts[key]
        for key in CLEAN_DIMENSION_FIELDS
    }
    weekly_unknown = weekly_unknown_counts(con, weekly_path)
    if unknown_counts != weekly_unknown:
        raise ValueError(
            "Aggregate-safe UNKNOWN dimension counts do not reconcile to the weekly "
            "literal UNKNOWN totals."
        )
    return {
        **clean,
        "weeklySourceRows": int(weekly["source_rows"]),
        "weeklyAggregateCount": int(weekly["aggregate_count"]),
        "firstWeek": weekly["min_week"],
        "lastWeek": weekly["max_week"],
        "aggregateSafeUnknownCounts": aggregate_safe_unknown_counts,
    }


def compute_date_range(stats: dict[str, Any]) -> dict[str, Any]:
    first_week = stats["firstWeek"]
    last_week = stats["lastWeek"]
    max_event_date = stats["safeEventEndDate"]
    if not all((first_week, last_week, max_event_date)):
        raise ValueError("Overview inputs must contain dated aggregate-safe observations.")
    latest_is_partial = last_week + timedelta(days=6) > max_event_date
    latest_complete = last_week - timedelta(weeks=1) if latest_is_partial else last_week
    default_start = max(first_week, latest_complete - timedelta(weeks=51))
    return {
        "safeEventStartDate": iso_date(stats["safeEventStartDate"]),
        "safeEventEndDate": iso_date(max_event_date),
        "firstWeek": iso_date(first_week),
        "lastWeek": iso_date(last_week),
        "defaultStartWeek": iso_date(default_start),
        "defaultEndWeek": iso_date(latest_complete),
        "latestCompleteWeek": iso_date(latest_complete),
        "latestWeekIsPartial": latest_is_partial,
    }


def weekly_dimension_values(con: Any, weekly_path: Path) -> dict[str, set[str]]:
    values = {
        "weeks": set(),
        "boroughs": set(),
        "precincts": set(),
        "offenseTypes": set(),
        "lawCategories": set(),
    }
    rows = con.execute(
        f"""
        SELECT DISTINCT
            week_start,
            CAST(borough AS VARCHAR),
            CAST(precinct AS VARCHAR),
            CAST(offense_type AS VARCHAR),
            CAST(law_category AS VARCHAR)
        FROM read_parquet({sql_string(weekly_path)})
        """
    ).fetchall()
    for week, borough, precinct, offense, law in rows:
        values["weeks"].add(iso_date(week) or "")
        values["boroughs"].add(normalized_string(borough) or "UNKNOWN")
        values["precincts"].add(normalized_string(precinct) or "UNKNOWN")
        values["offenseTypes"].add(normalized_string(offense) or "UNKNOWN")
        values["lawCategories"].add(normalized_string(law) or "UNKNOWN")
    return values


def build_dimensions(
    con: Any,
    weekly_path: Path,
    anomalies: dict[str, Any],
    hotspots: dict[str, Any],
    forecasts: dict[str, Any],
) -> dict[str, list[str]]:
    values = weekly_dimension_values(con, weekly_path)
    severities: set[str] = set()
    grains: set[str] = set()
    model_names: set[str] = set()
    expected_sources: set[str] = set()
    for source in (anomalies, hotspots, forecasts):
        if source["status"] != "available":
            continue
        for record in source["records"]:
            if record.get("week"):
                values["weeks"].add(record["week"])
            for source_key, dimension_key in (
                ("borough", "boroughs"),
                ("precinct", "precincts"),
                ("offenseType", "offenseTypes"),
                ("lawCategory", "lawCategories"),
            ):
                if record.get(source_key) is not None:
                    values[dimension_key].add(record[source_key])
            if record.get("severity"):
                severities.add(record["severity"])
            if record.get("grain"):
                grains.add(record["grain"])
            if record.get("modelName"):
                model_names.add(record["modelName"])
            if record.get("expectedSource"):
                expected_sources.add(record["expectedSource"])
    dimensions = {key: sorted(item) for key, item in values.items()}
    dimensions.update(
        {
            "severities": sorted(severities),
            "hotspotGrains": sorted(grains),
            "modelNames": sorted(model_names),
            "anomalyExpectedSources": sorted(expected_sources),
        }
    )
    for name in ("boroughs", "precincts", "offenseTypes", "lawCategories"):
        if len(dimensions[name]) >= 256:
            raise ValueError(f"Dimension {name} exceeds the uint8 cube contract.")
    if len(dimensions["weeks"]) >= 65_536:
        raise ValueError("Week dimension exceeds the uint16 cube contract.")
    return dimensions


def build_precinct_filter_index(
    con: Any, weekly_path: Path, dimensions: dict[str, list[str]]
) -> dict[str, Any]:
    rows = fetch_dicts(
        con,
        f"""
        SELECT
            CAST(borough AS VARCHAR) AS borough,
            CAST(precinct AS VARCHAR) AS precinct,
            SUM(crime_count)::HUGEINT AS crime_count
        FROM read_parquet({sql_string(weekly_path)})
        GROUP BY borough, precinct
        ORDER BY precinct, crime_count DESC, borough
        """,
    )
    borough_values = dimensions["boroughs"]
    precinct_values = dimensions["precincts"]
    borough_indexes = {value: index for index, value in enumerate(borough_values)}
    precinct_indexes = {value: index for index, value in enumerate(precinct_values)}
    canonical: dict[str, str] = {}
    unknown_precinct_boroughs: set[str] = set()
    for row in rows:
        borough = normalized_string(row["borough"]) or "UNKNOWN"
        precinct = normalized_string(row["precinct"]) or "UNKNOWN"
        if precinct == "UNKNOWN":
            if int(row["crime_count"]) > 0:
                unknown_precinct_boroughs.add(borough)
            continue
        if precinct not in canonical:
            canonical[precinct] = borough
    by_borough: dict[str, list[str]] = {borough: [] for borough in borough_values}
    for precinct, borough in canonical.items():
        by_borough.setdefault(borough, []).append(precinct)
    if "UNKNOWN" in precinct_indexes:
        for borough in unknown_precinct_boroughs:
            by_borough.setdefault(borough, []).append("UNKNOWN")
    indexed_rows = [
        [
            borough_indexes[borough],
            sorted(precinct_indexes[value] for value in by_borough.get(borough, [])),
        ]
        for borough in borough_values
    ]
    return {
        "rowColumns": ["boroughIndex", "precinctIndexes"],
        "rows": indexed_rows,
        "knownPrecinctPolicy": (
            "Each known precinct is assigned to the borough with its largest all-time "
            "weekly aggregate count; ties use borough lexical order."
        ),
        "unknownPrecinctPolicy": (
            "UNKNOWN is listed only for boroughs with observed UNKNOWN-precinct counts."
        ),
    }


def index_optional_signals(
    dimensions: dict[str, list[str]],
    anomalies: dict[str, Any],
    hotspots: dict[str, Any],
    forecasts: dict[str, Any],
) -> dict[str, Any]:
    indexes = {
        name: {value: index for index, value in enumerate(values)}
        for name, values in dimensions.items()
    }

    anomaly_rows: list[list[Any]] = []
    anomaly_counts = {"high": 0, "critical": 0}
    if anomalies["status"] == "available":
        for record in anomalies["records"]:
            anomaly_counts[record["severity"]] += 1
            anomaly_rows.append(
                [
                    indexes["weeks"][record["week"]],
                    indexes["boroughs"][record["borough"]],
                    indexes["precincts"][record["precinct"]],
                    indexes["offenseTypes"][record["offenseType"]],
                    indexes["lawCategories"][record["lawCategory"]],
                    record["actualCount"],
                    record["expectedCount"],
                    record["residualCount"],
                    record["score"],
                    indexes["severities"][record["severity"]],
                    indexes["anomalyExpectedSources"][record["expectedSource"]],
                ]
            )
    anomaly_signal = {
        "status": anomalies["status"],
        "sourceFile": anomalies["sourceFile"],
        "rowColumns": ANOMALY_ROW_COLUMNS,
        "rows": anomaly_rows,
        "summary": {
            "rowCount": len(anomaly_rows)
            if anomalies["status"] == "available"
            else None,
            "highCount": anomaly_counts["high"]
            if anomalies["status"] == "available"
            else None,
            "criticalCount": anomaly_counts["critical"]
            if anomalies["status"] == "available"
            else None,
            "isEmpty": len(anomaly_rows) == 0
            if anomalies["status"] == "available"
            else False,
            "scoringEndWeek": anomalies.get("scoringEndWeek"),
        },
    }

    hotspot_rows: list[list[Any]] = []
    hotspot_counts = {"high": 0, "critical": 0}
    if hotspots["status"] == "available":
        for record in hotspots["records"]:
            hotspot_counts[record["severity"]] += 1
            hotspot_rows.append(
                [
                    indexes["hotspotGrains"][record["grain"]],
                    indexes["boroughs"][record["borough"]],
                    None
                    if record["precinct"] is None
                    else indexes["precincts"][record["precinct"]],
                    indexes["offenseTypes"][record["offenseType"]],
                    indexes["lawCategories"][record["lawCategory"]],
                    record["scoringEndDate"],
                    record["locationLabel"],
                    record["recentCount"],
                    record["expectedRecentCount"],
                    record["liftPct"],
                    record["score"],
                    indexes["severities"][record["severity"]],
                ]
            )
    hotspot_signal = {
        "status": hotspots["status"],
        "sourceFile": hotspots["sourceFile"],
        "rowColumns": HOTSPOT_ROW_COLUMNS,
        "rows": hotspot_rows,
        "summary": {
            "rowCount": len(hotspot_rows),
            "highCount": hotspot_counts["high"],
            "criticalCount": hotspot_counts["critical"],
            "snapshotDate": hotspots.get("snapshotDate"),
            "snapshotAgeDays": hotspots.get("snapshotAgeDays"),
        },
    }

    forecast_rows: list[list[Any]] = []
    predicted_total = 0.0
    if forecasts["status"] == "available":
        for record in forecasts["records"]:
            predicted = float(record["predictedCount"])
            predicted_total += predicted
            forecast_rows.append(
                [
                    indexes["weeks"][record["week"]],
                    indexes["boroughs"][record["borough"]],
                    indexes["precincts"][record["precinct"]],
                    indexes["offenseTypes"][record["offenseType"]],
                    indexes["lawCategories"][record["lawCategory"]],
                    record["predictedCount"],
                    indexes["modelNames"][record["modelName"]],
                ]
            )
    forecast_signal = {
        "status": forecasts["status"],
        "sourceFile": forecasts["sourceFile"],
        "rowColumns": FORECAST_ROW_COLUMNS,
        "rows": forecast_rows,
        "summary": {
            "rowCount": len(forecast_rows),
            "forecastWeeks": sorted(
                {record["week"] for record in forecasts.get("records", [])}
            ),
            "predictedEventCount": compact_number(predicted_total),
        },
    }
    for signal, source in (
        (anomaly_signal, anomalies),
        (hotspot_signal, hotspots),
        (forecast_signal, forecasts),
    ):
        if source.get("reason"):
            signal["reason"] = source["reason"]
    return {
        "anomalies": anomaly_signal,
        "hotspots": hotspot_signal,
        "forecast": forecast_signal,
    }


def build_cube(
    con: Any, weekly_path: Path, dimensions: dict[str, list[str]]
) -> tuple[bytes, dict[str, Any]]:
    indexes = {
        name: {value: index for index, value in enumerate(values)}
        for name, values in dimensions.items()
    }
    columns = {
        "counts": array("I"),
        "weeks": array("H"),
        "boroughs": array("B"),
        "precincts": array("B"),
        "offenses": array("B"),
        "laws": array("B"),
    }
    cursor = con.execute(
        f"""
        SELECT
            week_start,
            CAST(borough AS VARCHAR) AS borough,
            CAST(precinct AS VARCHAR) AS precinct,
            CAST(offense_type AS VARCHAR) AS offense_type,
            CAST(law_category AS VARCHAR) AS law_category,
            SUM(crime_count)::HUGEINT AS crime_count
        FROM read_parquet({sql_string(weekly_path)})
        GROUP BY week_start, borough, precinct, offense_type, law_category
        ORDER BY week_start, borough, precinct, offense_type, law_category
        """
    )
    while True:
        batch = cursor.fetchmany(50_000)
        if not batch:
            break
        for week, borough, precinct, offense, law, count in batch:
            count = int(count)
            if not 0 <= count <= 4_294_967_295:
                raise ValueError("Cube count is outside the uint32 range.")
            columns["counts"].append(count)
            columns["weeks"].append(indexes["weeks"][iso_date(week)])
            columns["boroughs"].append(indexes["boroughs"][str(borough)])
            columns["precincts"].append(indexes["precincts"][str(precinct)])
            columns["offenses"].append(indexes["offenseTypes"][str(offense)])
            columns["laws"].append(indexes["lawCategories"][str(law)])
    row_count = len(columns["counts"])
    observed_week_count = len(
        {index for index in columns["weeks"]}
    )
    week_counts = [0] * observed_week_count
    for week_index in columns["weeks"]:
        if week_index >= observed_week_count:
            raise ValueError("Observed cube week indexes must precede forecast-only weeks.")
        week_counts[week_index] += 1
    offsets = array("I", [0])
    running = 0
    for count in week_counts:
        running += count
        offsets.append(running)
    if running != row_count:
        raise ValueError("Week row offsets do not reconcile to the cube row count.")
    columns["weekRowOffsets"] = offsets

    dimension_for = {
        "weeks": "weeks",
        "boroughs": "boroughs",
        "precincts": "precincts",
        "offenses": "offenseTypes",
        "laws": "lawCategories",
    }
    metadata_columns: dict[str, Any] = {}
    chunks: list[bytes] = []
    offset_bytes = 0
    for name in CUBE_COLUMN_ORDER:
        chunk = little_endian_array_bytes(columns[name])
        descriptor: dict[str, Any] = {
            "type": CUBE_TYPES[name],
            "offsetBytes": offset_bytes,
            "byteLength": len(chunk),
            "length": len(columns[name]),
        }
        if name in dimension_for:
            descriptor["dimension"] = dimension_for[name]
        if name == "weekRowOffsets":
            descriptor["semantics"] = (
                "Start row for each observed week, followed by terminal rowCount."
            )
            descriptor["observedWeekCount"] = observed_week_count
        metadata_columns[name] = descriptor
        chunks.append(chunk)
        offset_bytes += len(chunk)
    uncompressed = b"".join(chunks)
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, compresslevel=9, mtime=0) as stream:
        stream.write(uncompressed)
    compressed = buffer.getvalue()
    return compressed, {
        "encoding": "columnar-arrays-v1",
        "compression": "gzip",
        "byteOrder": "little-endian",
        "rowCount": row_count,
        "observedWeekCount": observed_week_count,
        "columnOrder": CUBE_COLUMN_ORDER,
        "columns": metadata_columns,
        "uncompressedByteLength": len(uncompressed),
        "compressedByteLength": len(compressed),
        "uncompressedBytes": len(uncompressed),
        "compressedBytes": len(compressed),
    }


def _historical_error_context(
    ml_metrics: dict[str, Any],
    ml_manifest: dict[str, Any],
    forecasts: dict[str, Any],
) -> dict[str, Any]:
    version = metadata_version(ml_metrics)
    if version["status"] != "available":
        result = {"status": version["status"]}
        if version.get("reason"):
            result["reason"] = version["reason"]
        return result
    if ml_manifest["status"] != "available" or forecasts["status"] != "available":
        return {
            "status": "invalid",
            "reason": "Historical error context cannot be aligned to an available forecast.",
        }
    try:
        data = ml_metrics.get("data") or {}
        manifest = ml_manifest.get("data") or {}
        metric_model_config = data.get("model_config") or data.get("model") or {}
        manifest_model_config = manifest.get("model") or manifest.get("model_config") or {}
        metric_model_name = required_text(
            metric_model_config.get("model_name"), "ML metrics model_name"
        )
        manifest_model_name = required_text(
            manifest_model_config.get("model_name"), "ML manifest model_name"
        )
        metric_week = required_date(
            (data.get("analysis_window") or {}).get("next_week_forecast_week")
            or data.get("forecast_week"),
            "ML metrics forecast week",
        )
        manifest_week = required_date(
            manifest.get("forecast_week"), "ML manifest forecast week"
        )
        forecast_models = sorted(
            {record["modelName"] for record in forecasts.get("records", [])}
        )
        forecast_weeks = sorted(
            {record["week"] for record in forecasts.get("records", [])}
        )
        if (
            forecast_models != [metric_model_name]
            or metric_model_name != manifest_model_name
            or forecast_weeks != [metric_week]
            or metric_week != manifest_week
        ):
            raise OptionalContractError(
                "Historical error metrics do not match the published forecast model and week."
            )

        overall = (data.get("metrics") or {}).get("overall") or []
        if len(overall) != 1 or not isinstance(overall[0], dict):
            raise OptionalContractError(
                "Historical error metrics require one unambiguous overall backtest row."
            )
        metric = overall[0]
        context: dict[str, Any] = {
            "status": "available",
            "unit": "reported events per segment-week",
            "scope": "overall model backtest across all segments",
            "filterSemantics": "Historical errors are not recomputed for active dashboard filters.",
            "modelName": metric_model_name,
            "forecastWeek": metric_week,
            "mae": required_number(metric.get("mae"), "ML metrics MAE", minimum=0),
            "rmse": required_number(metric.get("rmse"), "ML metrics RMSE", minimum=0),
            "predictionCoveragePct": required_number(
                metric.get("prediction_coverage_pct"),
                "ML metrics prediction coverage",
                minimum=0,
                maximum=100,
            ),
        }
        if metric.get("weighted_mae") is not None:
            context["weightedMae"] = required_number(
                metric["weighted_mae"], "ML metrics weighted MAE", minimum=0
            )
        return context
    except OptionalContractError as exc:
        return {"status": "invalid", "reason": str(exc)}


def gate_forecast_with_manifest(
    forecasts: dict[str, Any],
    ml_manifest: dict[str, Any],
    last_observed_week: date | datetime | str,
) -> dict[str, Any]:
    """Publish only one manifest-aligned, strictly future forecast horizon."""
    if forecasts["status"] != "available":
        return forecasts
    if ml_manifest["status"] != "available":
        reason = (
            "Forecast withheld because the ML model manifest is "
            f"{ml_manifest['status']}; leakage controls cannot be verified."
        )
        return optional_error(Path(forecasts["sourceFile"]), reason)
    controls = (ml_manifest.get("data") or {}).get("leakage_controls") or {}
    safe = (
        controls.get("random_splits_used") is False
        and controls.get("target_week_excluded_from_features") is True
    )
    if not safe:
        return optional_error(
            Path(forecasts["sourceFile"]),
            (
                "Forecast withheld because the ML manifest does not verify time-based "
                "leakage controls (random_splits_used=false and "
                "target_week_excluded_from_features=true)."
            ),
        )

    records = forecasts.get("records") or []
    forecast_weeks = sorted({record["week"] for record in records})
    model_names = sorted({record["modelName"] for record in records})
    manifest = ml_manifest.get("data") or {}
    manifest_model = manifest.get("model") or manifest.get("model_config") or {}
    manifest_week = manifest.get("forecast_week")
    manifest_model_name = manifest_model.get("model_name")
    last_observed_week_iso = iso_date(last_observed_week)

    alignment_errors: list[str] = []
    if len(forecast_weeks) != 1:
        alignment_errors.append("exactly one forecast week is required")
    elif forecast_weeks[0] <= last_observed_week_iso:
        alignment_errors.append("the forecast week must follow the last observed week")
    if len(model_names) != 1:
        alignment_errors.append("exactly one forecast model is required")
    if manifest_week is None or forecast_weeks != [str(manifest_week)]:
        alignment_errors.append("the prediction week must match the ML manifest")
    if manifest_model_name is None or model_names != [str(manifest_model_name)]:
        alignment_errors.append("the prediction model must match the ML manifest")
    if alignment_errors:
        return optional_error(
            Path(forecasts["sourceFile"]),
            "Forecast withheld because " + "; ".join(alignment_errors) + ".",
        )
    return forecasts


def build_dashboard_overview(
    *,
    clean_events_path: Path,
    weekly_path: Path,
    overview_output_path: Path,
    cube_output_path: Path,
    anomalies_path: Path,
    hotspots_path: Path,
    ml_predictions_path: Path,
    anomaly_metrics_path: Path,
    hotspot_metrics_path: Path,
    ml_metrics_path: Path,
    ml_manifest_path: Path,
    baseline_manifest_path: Path,
    threads: int = 4,
) -> dict[str, Any]:
    duckdb = require_duckdb()
    con = duckdb.connect(database=":memory:")
    con.execute(f"PRAGMA threads={max(1, int(threads))}")
    require_parquet_columns(con, weekly_path, WEEKLY_REQUIRED_COLUMNS, "weekly area")

    stats = mandatory_stats(con, clean_events_path, weekly_path)
    date_range = compute_date_range(stats)
    anomalies = load_optional_anomalies(con, anomalies_path)
    hotspots = load_optional_hotspots(con, hotspots_path, stats["safeEventEndDate"])
    forecasts = load_optional_forecasts(con, ml_predictions_path)
    anomaly_metrics = read_optional_json(anomaly_metrics_path)
    hotspot_metrics = read_optional_json(hotspot_metrics_path)
    ml_metrics = read_optional_json(ml_metrics_path)
    ml_manifest = read_optional_json(ml_manifest_path)
    baseline_manifest = read_optional_json(baseline_manifest_path)

    anomalies = gate_anomalies_with_metrics(anomalies, anomaly_metrics, date_range)
    forecasts = gate_forecast_with_manifest(forecasts, ml_manifest, stats["lastWeek"])

    dimensions = build_dimensions(con, weekly_path, anomalies, hotspots, forecasts)
    signals = index_optional_signals(dimensions, anomalies, hotspots, forecasts)
    signals["forecast"]["summary"]["historicalError"] = _historical_error_context(
        ml_metrics, ml_manifest, forecasts
    )
    signals["forecast"]["summary"]["limitations"] = [
        (
            "No prediction interval or other uncertainty interval is available; only "
            "a point estimate is supplied."
        ),
        "The forecast horizon follows a source extract whose latest observed week may be partial.",
    ]
    compressed_cube, cube = build_cube(con, weekly_path, dimensions)
    cube["path"] = f"/data/{CUBE_FILE}"
    versions = {
        "dashboardContract": SCHEMA_VERSION,
        "anomalyMetrics": metadata_version(anomaly_metrics),
        "hotspotMetrics": metadata_version(hotspot_metrics),
        "mlMetrics": metadata_version(ml_metrics),
        "mlManifest": metadata_version(ml_manifest, model=True),
        "baselineManifest": metadata_version(baseline_manifest),
    }
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAtUtc": deterministic_generated_at_utc(stats["safeEventEndDate"]),
        "application": {
            "name": "NYC Crime Intelligence",
            "phase": "Phase 7A",
            "view": "Overview",
        },
        "dataRange": date_range,
        "observed": {
            "safeEventCount": stats["safeEventCount"],
            "weeklyAggregateCount": stats["weeklyAggregateCount"],
            "unit": "reported aggregate complaint events",
            "dateFilterSemantics": (
                "Inclusive week_start range over Monday-based weekly aggregate buckets."
            ),
            "latestWeekNote": (
                "The latest week is retained for freshness but excluded from the "
                "default range and comparisons when incomplete."
            ),
            "comparisonSemantics": (
                "Compare the most recent four complete selected weeks with the prior "
                "four complete selected weeks, or equal shorter windows when fewer than "
                "eight complete selected weeks are available; never include later observations."
            ),
        },
        "dimensions": dimensions,
        "filterIndex": {
            "precinctsByBorough": build_precinct_filter_index(
                con, weekly_path, dimensions
            )
        },
        "cube": cube,
        "signals": signals,
        "versions": versions,
        "dataQuality": {
            "cleanSourceRowCount": stats["cleanSourceRows"],
            "aggregateSafeEventCount": stats["safeEventCount"],
            "excludedEventCount": stats["cleanSourceRows"] - stats["safeEventCount"],
            "sourceIssueCounts": stats["sourceIssueCounts"],
            "aggregateSafeUnknownCounts": stats["aggregateSafeUnknownCounts"],
            "weeklySourceRowCount": stats["weeklySourceRows"],
            "weeklyAggregateCount": stats["weeklyAggregateCount"],
            "countsReconciled": stats["safeEventCount"] == stats["weeklyAggregateCount"],
            "cubeRowCount": cube["rowCount"],
            "safeRowsOnly": True,
            "dateBasis": (
                "Dates and generatedAtUtc use the maximum aggregate-safe cleaned event "
                "date, never the current clock."
            ),
        },
        "ethics": {
            "aggregateTrendIntelligenceOnly": True,
            "eventRecordsIncluded": False,
            "demographicAttributesIncluded": False,
            "personLevelScoring": False,
            "enforcementRecommendations": False,
            "patrolRecommendations": False,
        },
        "limitations": [
            "Counts describe reported aggregate complaint events and do not explain causality.",
            "The latest source week can be partial and is excluded from default comparisons.",
            "Reporting delays, classification changes, and later revisions can change counts.",
            (
                "Anomalies are observed deviations, hotspots are aggregate concentration "
                "signals, and forecasts are model estimates; these are distinct measures."
            ),
            (
                "Outputs are decision-support context and are not grounds for person-level "
                "or enforcement action."
            ),
            "Forecast outputs do not include uncertainty intervals and may follow a partial source week.",
        ],
    }
    validate_overview_payload(payload)
    overview_output_path.parent.mkdir(parents=True, exist_ok=True)
    cube_output_path.parent.mkdir(parents=True, exist_ok=True)
    cube_output_path.write_bytes(compressed_cube)
    overview_output_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    return payload


def validate_overview_payload(payload: dict[str, Any]) -> None:
    required = {
        "schemaVersion",
        "generatedAtUtc",
        "application",
        "dataRange",
        "observed",
        "dimensions",
        "filterIndex",
        "cube",
        "signals",
        "versions",
        "dataQuality",
        "ethics",
        "limitations",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"Overview payload is missing required sections: {missing}")
    if payload["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError("Unexpected Overview schema version.")
    for name, values in payload["dimensions"].items():
        if not isinstance(values, list) or values != sorted(values):
            raise ValueError(f"Dimension {name} must be a sorted list.")
        if not all(isinstance(value, str) for value in values):
            raise ValueError(f"Dimension {name} contains a non-string value.")
    for week in payload["dimensions"]["weeks"]:
        date.fromisoformat(week)
    cube = payload["cube"]
    if cube["columnOrder"] != CUBE_COLUMN_ORDER:
        raise ValueError("Cube columns are not in the required order.")
    offset = 0
    for name in CUBE_COLUMN_ORDER:
        column = cube["columns"].get(name)
        if not column or column["type"] != CUBE_TYPES[name]:
            raise ValueError(f"Invalid cube column metadata for {name}.")
        expected_length = (
            cube["observedWeekCount"] + 1
            if name == "weekRowOffsets"
            else cube["rowCount"]
        )
        if column["offsetBytes"] != offset or column["length"] != expected_length:
            raise ValueError(f"Invalid cube offset or length for {name}.")
        expected_bytes = expected_length * CUBE_TYPE_WIDTHS[column["type"]]
        if column["byteLength"] != expected_bytes:
            raise ValueError(f"Invalid cube byte length for {name}.")
        offset += expected_bytes
    if offset != cube["uncompressedByteLength"]:
        raise ValueError("Cube uncompressed byte length does not match its columns.")
    if payload["observed"]["safeEventCount"] != payload["observed"]["weeklyAggregateCount"]:
        raise ValueError("Observed event and weekly aggregate counts do not reconcile.")
    data_quality = payload["dataQuality"]
    source_issue_counts = data_quality.get("sourceIssueCounts")
    expected_source_issue_keys = {
        "populationCount",
        *QUALITY_FLAG_FIELDS,
        "rowsWithAnyIssue",
        "rowsWithMultipleIssues",
        "maximumIssuesPerRow",
        "categoriesOverlap",
        "countsAreNonAdditive",
    }
    if (
        not isinstance(source_issue_counts, dict)
        or set(source_issue_counts) != expected_source_issue_keys
        or source_issue_counts.get("categoriesOverlap") is not True
        or source_issue_counts.get("countsAreNonAdditive") is not True
    ):
        raise ValueError("Overview source issue-count schema is invalid.")
    source_population = source_issue_counts["populationCount"]
    rows_with_any_issue = source_issue_counts["rowsWithAnyIssue"]
    rows_with_multiple_issues = source_issue_counts["rowsWithMultipleIssues"]
    maximum_issues_per_row = source_issue_counts["maximumIssuesPerRow"]
    issue_values = [source_issue_counts[key] for key in QUALITY_FLAG_FIELDS]
    integer_values = [
        source_population,
        rows_with_any_issue,
        rows_with_multiple_issues,
        maximum_issues_per_row,
        *issue_values,
    ]
    if (
        any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in integer_values
        )
        or source_population != data_quality.get("cleanSourceRowCount")
        or not 0 <= rows_with_multiple_issues <= rows_with_any_issue <= source_population
        or maximum_issues_per_row > len(QUALITY_FLAG_FIELDS)
        or any(value > source_population for value in issue_values)
        or sum(issue_values) < rows_with_any_issue
        or (rows_with_any_issue == 0 and maximum_issues_per_row != 0)
        or (rows_with_any_issue > 0 and maximum_issues_per_row < 1)
        or (rows_with_multiple_issues > 0 and maximum_issues_per_row < 2)
    ):
        raise ValueError("Overview source issue counts are inconsistent.")

    unknown_counts = data_quality.get("aggregateSafeUnknownCounts")
    expected_unknown_keys = {
        "populationCount",
        *CLEAN_DIMENSION_FIELDS,
        "valuesRetained",
        "categoriesOverlap",
    }
    if (
        not isinstance(unknown_counts, dict)
        or set(unknown_counts) != expected_unknown_keys
        or unknown_counts.get("valuesRetained") is not True
        or unknown_counts.get("categoriesOverlap") is not True
    ):
        raise ValueError("Overview aggregate-safe UNKNOWN-count schema is invalid.")
    unknown_population = unknown_counts["populationCount"]
    unknown_values = [unknown_counts[key] for key in CLEAN_DIMENSION_FIELDS]
    if (
        isinstance(unknown_population, bool)
        or not isinstance(unknown_population, int)
        or unknown_population < 0
        or unknown_population != data_quality.get("aggregateSafeEventCount")
        or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= unknown_population
            for value in unknown_values
        )
    ):
        raise ValueError("Overview aggregate-safe UNKNOWN counts are inconsistent.")
    for family in ("anomalies", "hotspots", "forecast"):
        signal = payload["signals"].get(family)
        allowed_statuses = (
            ANOMALY_STATUSES
            if family == "anomalies"
            else {"available", "missing", "invalid"}
        )
        if not signal or signal.get("status") not in allowed_statuses:
            raise ValueError(f"Invalid optional signal status for {family}.")
        if signal["status"] != "available" and signal["rows"]:
            raise ValueError(f"Unavailable optional signal {family} contains rows.")
    anomaly_signal = payload["signals"]["anomalies"]
    anomaly_summary = anomaly_signal.get("summary")
    if not isinstance(anomaly_summary, dict):
        raise ValueError("Anomaly signal summary is missing.")
    if anomaly_signal["status"] == "available":
        if (
            anomaly_summary.get("rowCount") != len(anomaly_signal["rows"])
            or anomaly_summary.get("isEmpty") is not (len(anomaly_signal["rows"]) == 0)
            or not isinstance(anomaly_summary.get("scoringEndWeek"), str)
        ):
            raise ValueError("Available anomaly summary does not reconcile.")
        date.fromisoformat(anomaly_summary["scoringEndWeek"])
    elif (
        anomaly_summary.get("rowCount") is not None
        or anomaly_summary.get("highCount") is not None
        or anomaly_summary.get("criticalCount") is not None
        or anomaly_summary.get("isEmpty") is not False
    ):
        raise ValueError("Unavailable anomaly summary contains valid-zero totals.")
    serialized = json.dumps(payload, allow_nan=False).upper()
    leaked = [column for column in SENSITIVE_COLUMNS if column in serialized]
    if leaked:
        raise ValueError(f"Sensitive demographic fields leaked into Overview payload: {leaked}")
    for forbidden in (
        "COMPLAINT_NUMBER",
        "SOURCE_ROW_ID",
        "/USERS/",
        "/CONTENT/",
    ):
        if forbidden in serialized:
            raise ValueError(f"Unsafe source metadata leaked into Overview payload: {forbidden}")


def decode_cube(payload: dict[str, Any], compressed_bytes: bytes) -> dict[str, list[int]]:
    raw = gzip.decompress(compressed_bytes)
    cube = payload["cube"]
    if len(raw) != cube["uncompressedByteLength"]:
        raise ValueError("Cube byte length does not match Overview metadata.")
    decoded: dict[str, list[int]] = {}
    for name in cube["columnOrder"]:
        descriptor = cube["columns"][name]
        chunk = raw[
            descriptor["offsetBytes"] : descriptor["offsetBytes"]
            + descriptor["byteLength"]
        ]
        type_name = descriptor["type"]
        type_code = {"uint8": "B", "uint16": "H", "uint32": "I"}[type_name]
        values = array(type_code)
        values.frombytes(chunk)
        if sys.byteorder != "little" and values.itemsize > 1:
            values.byteswap()
        decoded[name] = list(values)
    return decoded


def aggregate_cube(
    payload: dict[str, Any],
    compressed_bytes: bytes,
    *,
    start_week: str | None = None,
    end_week: str | None = None,
    borough: str | None = None,
    precinct: str | None = None,
    offense_type: str | None = None,
    law_category: str | None = None,
) -> int:
    decoded = decode_cube(payload, compressed_bytes)
    dimensions = payload["dimensions"]
    requested = {
        "boroughs": borough,
        "precincts": precinct,
        "offenseTypes": offense_type,
        "lawCategories": law_category,
    }
    selected: dict[str, int | None] = {}
    for name, value in requested.items():
        if value is None:
            selected[name] = None
        elif value not in dimensions[name]:
            return 0
        else:
            selected[name] = dimensions[name].index(value)
    total = 0
    for row_index, count in enumerate(decoded["counts"]):
        week = dimensions["weeks"][decoded["weeks"][row_index]]
        if start_week is not None and week < start_week:
            continue
        if end_week is not None and week > end_week:
            continue
        if selected["boroughs"] is not None and decoded["boroughs"][row_index] != selected["boroughs"]:
            continue
        if selected["precincts"] is not None and decoded["precincts"][row_index] != selected["precincts"]:
            continue
        if selected["offenseTypes"] is not None and decoded["offenses"][row_index] != selected["offenseTypes"]:
            continue
        if selected["lawCategories"] is not None and decoded["laws"][row_index] != selected["lawCategories"]:
            continue
        total += count
    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the Phase 7A dashboard Overview JSON and binary cube."
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--processed-dir", type=Path, default=None)
    parser.add_argument("--dashboard-data-dir", type=Path, default=None)
    parser.add_argument("--clean-events", type=Path, default=None)
    parser.add_argument("--weekly-area", type=Path, default=None)
    parser.add_argument("--anomalies", type=Path, default=None)
    parser.add_argument("--hotspots", type=Path, default=None)
    parser.add_argument("--ml-predictions", type=Path, default=None)
    parser.add_argument("--anomaly-metrics", type=Path, default=None)
    parser.add_argument("--hotspot-metrics", type=Path, default=None)
    parser.add_argument("--ml-metrics", type=Path, default=None)
    parser.add_argument("--ml-manifest", type=Path, default=None)
    parser.add_argument("--baseline-manifest", type=Path, default=None)
    parser.add_argument("--overview-output", type=Path, default=None)
    parser.add_argument("--cube-output", type=Path, default=None)
    parser.add_argument(
        "--skip-dashboard-copy",
        action="store_true",
        help="Write canonical processed outputs without copying them into dashboard/public/data.",
    )
    parser.add_argument(
        "--threads", type=int, default=max(1, min(4, os.cpu_count() or 1))
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = args.project_root.resolve()
    processed_dir = resolve_path(
        project_root, args.processed_dir, DEFAULT_PROCESSED_DIR
    )
    dashboard_data_dir = resolve_path(
        project_root, args.dashboard_data_dir, DEFAULT_DASHBOARD_DATA_DIR
    )
    overview_output = resolve_path(
        project_root,
        args.overview_output,
        processed_dir / PROCESSED_OVERVIEW_FILE,
    )
    cube_output = resolve_path(
        project_root,
        args.cube_output,
        processed_dir / PROCESSED_CUBE_FILE,
    )
    payload = build_dashboard_overview(
        clean_events_path=resolve_path(
            project_root, args.clean_events, processed_dir / CLEAN_EVENTS_FILE
        ),
        weekly_path=resolve_path(
            project_root, args.weekly_area, processed_dir / WEEKLY_FILE
        ),
        anomalies_path=resolve_path(
            project_root, args.anomalies, processed_dir / ANOMALIES_FILE
        ),
        hotspots_path=resolve_path(
            project_root, args.hotspots, processed_dir / HOTSPOTS_FILE
        ),
        ml_predictions_path=resolve_path(
            project_root, args.ml_predictions, processed_dir / ML_PREDICTIONS_FILE
        ),
        anomaly_metrics_path=resolve_path(
            project_root, args.anomaly_metrics, processed_dir / ANOMALY_METRICS_FILE
        ),
        hotspot_metrics_path=resolve_path(
            project_root, args.hotspot_metrics, processed_dir / HOTSPOT_METRICS_FILE
        ),
        ml_metrics_path=resolve_path(
            project_root, args.ml_metrics, processed_dir / ML_METRICS_FILE
        ),
        ml_manifest_path=resolve_path(
            project_root,
            args.ml_manifest,
            DEFAULT_MODEL_DIR / MODEL_MANIFEST_FILE,
        ),
        baseline_manifest_path=resolve_path(
            project_root,
            args.baseline_manifest,
            DEFAULT_BASELINE_MODEL_DIR / MODEL_MANIFEST_FILE,
        ),
        overview_output_path=overview_output,
        cube_output_path=cube_output,
        threads=args.threads,
    )
    if not args.skip_dashboard_copy:
        dashboard_data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(overview_output, dashboard_data_dir / OVERVIEW_FILE)
        shutil.copyfile(cube_output, dashboard_data_dir / CUBE_FILE)
    print(
        "Built Phase 7A Overview data: "
        f"{payload['cube']['rowCount']:,} cube rows, "
        f"{payload['observed']['safeEventCount']:,} aggregate-safe events."
    )
    print(f"Canonical metadata: {overview_output}")
    print(f"Canonical cube: {cube_output}")
    if not args.skip_dashboard_copy:
        print(f"Frontend data: {dashboard_data_dir}")


if __name__ == "__main__":
    main()

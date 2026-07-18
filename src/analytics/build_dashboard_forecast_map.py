#!/usr/bin/env python3
"""Build the deterministic, aggregate-only Phase 7C.1 Forecast Map contract."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_DASHBOARD_DATA_DIR = Path("dashboard/public/data")
DEFAULT_MODEL_DIR = Path("models/weekly_forecast")
DEFAULT_BASELINE_MODEL_DIR = Path("models/baseline_forecast")

WEEKLY_FILE = "crime_weekly_area.parquet"
OVERVIEW_FILE = "dashboard_overview.json"
ML_PREDICTIONS_FILE = "ml_predictions.parquet"
ML_METRICS_FILE = "ml_metrics.json"
MODEL_MANIFEST_FILE = "model_manifest.json"
BASELINE_PREDICTIONS_FILE = "baseline_predictions.parquet"
PROCESSED_FORECAST_MAP_FILE = "dashboard_forecast_map.json"
FORECAST_MAP_FILE = "forecast-map.json"

SCHEMA_VERSION = "1.0.0"
NUMERIC_DIGITS = 6
ARITHMETIC_TOLERANCE = 1e-6
MODEL_ARTIFACT_TYPE = "weekly_forecast_ml_model"
BASELINE_ARTIFACT_TYPE = "baseline_forecast_model"
INDEPENDENT_TRAINING_TIME = {
    "status": "unavailable",
    "timestamp": None,
    "reason": "No independent training-completion timestamp is recorded.",
}
EXPECTED_SEGMENT_KEYS = [
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
BASELINE_REQUIRED_COLUMNS = [
    "week_start",
    "borough",
    "precinct",
    "offense_type",
    "law_category",
    "is_next_week_forecast",
]
BASELINE_METHOD_COLUMNS = {
    "previous_week": "previous_week",
    "trailing_4_week_mean": "trailing_4_week_mean",
    "trailing_8_week_mean": "trailing_8_week_mean",
    "previous_year_same_week": "previous_year_same_week",
}
BASELINE_RULES = {
    "previous_week": (
        "Use the immediately prior weekly crime_count for the same segment.",
        1,
    ),
    "trailing_4_week_mean": (
        "Use the arithmetic mean of the prior 4 weekly crime_count values for the same segment.",
        4,
    ),
    "trailing_8_week_mean": (
        "Use the arithmetic mean of the prior 8 weekly crime_count values for the same segment.",
        8,
    ),
    "previous_year_same_week": (
        "Use the weekly crime_count from 52 weeks prior for the same segment.",
        52,
    ),
}
BASELINE_ZERO_FILL_RULE = (
    "Missing weekly rows are treated as zero crime_count after a segment's first observed week."
)
ROW_COLUMNS = [
    "forecastWeekIndex",
    "boroughIndex",
    "precinctIndex",
    "offenseTypeIndex",
    "lawCategoryIndex",
    "predictedCount",
    "historicalBaseline",
    "expectedChangeCount",
    "expectedChangePct",
    "precinctLocationKey",
]
DIMENSION_KEYS = [
    "forecastWeeks",
    "boroughs",
    "precincts",
    "offenseTypes",
    "lawCategories",
]
FORECAST_STATUSES = {"available", "missing", "invalid", "stale"}
OPTIONAL_STATUSES = {"available", "missing", "invalid", "stale"}
UNKNOWN_LABELS = {"", "UNKNOWN", "NULL", "(NULL)"}
PRECINCT_RE = re.compile(r"[1-9][0-9]{0,2}\Z")
MODEL_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")

# Existing forecast artifacts may contain aggregate model features, but never these
# event-, person-, demographic-, recommendation-, or exact-location fields.
UNSAFE_SOURCE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(^|_)complaint(_|$)",
        r"(^|_)cmplnt(_|$)",
        r"(^|_)event_id($|_)",
        r"(^|_)source(_row)?_?id($|_)",
        r"(^|_)latitude($|_)",
        r"(^|_)longitude($|_)",
        r"(^|_)(addr|address|street)($|_)",
        r"(^|_)(x_coord|y_coord)($|_)",
        r"(^|_)person(_|$)",
        r"(^|_)(person|victim|suspect|first|last|full)_name($|_)",
        r"(^|_)(vic|victim|susp|suspect)(_.*)?(age|race|sex|gender)",
        r"(^|_)demographic(_|$)",
        r"(^|_)patrol(_|$)",
        r"(^|_)enforcement(_|$)",
    )
]


class ForecastMapContractError(ValueError):
    """A malformed or incompatible Forecast Map source or payload."""


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


def resolve_path(project_root: Path, value: Path | None, default: Path) -> Path:
    candidate = default if value is None else value
    return candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()


def fetch_dicts(con: Any, sql: str) -> list[dict[str, Any]]:
    result = con.execute(sql)
    names = [column[0] for column in result.description]
    return [dict(zip(names, row)) for row in result.fetchall()]


def parquet_columns(con: Any, path: Path) -> list[str]:
    return [
        str(row[0])
        for row in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet({sql_string(path)})"
        ).fetchall()
    ]


def parquet_column_types(con: Any, path: Path) -> dict[str, str]:
    return {
        str(row[0]).lower(): str(row[1]).upper()
        for row in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet({sql_string(path)})"
        ).fetchall()
    }


def required_text(value: Any, label: str) -> str:
    if value is None or not isinstance(value, str) or not value.strip():
        raise ForecastMapContractError(f"Missing or malformed text field: {label}.")
    result = value.strip()
    if len(result) > 500 or any(ord(character) < 32 for character in result):
        raise ForecastMapContractError(f"Unsafe text field: {label}.")
    return result


def required_source_filename(value: Any, label: str) -> str:
    result = required_text(value, label)
    if Path(result).name != result or "/" in result or "\\" in result:
        raise ForecastMapContractError(f"Source filename exposes a path: {label}.")
    return result


def required_date(value: Any, label: str) -> date:
    if isinstance(value, datetime):
        result = value.date()
    elif isinstance(value, date):
        result = value
    elif isinstance(value, str):
        try:
            result = date.fromisoformat(value)
        except ValueError as exc:
            raise ForecastMapContractError(f"Malformed date field: {label}.") from exc
    else:
        raise ForecastMapContractError(f"Missing or malformed date field: {label}.")
    return result


def required_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ForecastMapContractError(f"Missing timestamp field: {label}.")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as exc:
        raise ForecastMapContractError(f"Malformed timestamp field: {label}.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ForecastMapContractError(f"Timestamp must include a UTC offset: {label}.")
    return parsed.astimezone(timezone.utc)


def required_number(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    integer: bool = False,
) -> int | float:
    if value is None or isinstance(value, bool) or not isinstance(
        value, (int, float, Decimal)
    ):
        raise ForecastMapContractError(f"Missing or malformed numeric field: {label}.")
    number = float(value)
    if not math.isfinite(number):
        raise ForecastMapContractError(f"Non-finite numeric field: {label}.")
    if minimum is not None and number < minimum:
        raise ForecastMapContractError(f"Numeric field is below its minimum: {label}.")
    if maximum is not None and number > maximum:
        raise ForecastMapContractError(f"Numeric field is above its maximum: {label}.")
    if integer:
        if not number.is_integer():
            raise ForecastMapContractError(f"Expected an integer field: {label}.")
        return int(number)
    rounded = round(number, NUMERIC_DIGITS)
    return int(rounded) if rounded.is_integer() else rounded


def optional_number(value: Any, label: str, *, minimum: float | None = None) -> int | float | None:
    return None if value is None else required_number(value, label, minimum=minimum)


def compact_sum(values: list[int | float]) -> int | float:
    return required_number(sum(float(value) for value in values), "aggregate numeric total")


def compact_pct(numerator: int | float, denominator: int | float) -> int | float | None:
    if float(denominator) == 0:
        return None
    return required_number(float(numerator) / float(denominator) * 100, "percentage")


def is_unknown(value: str) -> bool:
    return value.strip().upper() in UNKNOWN_LABELS


def location_key(precinct: str) -> str:
    if not PRECINCT_RE.fullmatch(precinct):
        raise ForecastMapContractError("Cannot construct a safe key for an unmappable precinct.")
    return f"nypd-precinct:{precinct}"


def _unsafe_columns(columns: list[str]) -> list[str]:
    return sorted(
        column
        for column in columns
        if any(pattern.search(column) for pattern in UNSAFE_SOURCE_PATTERNS)
    )


def _required_columns(con: Any, path: Path, required: list[str], label: str) -> list[str]:
    columns = parquet_columns(con, path)
    lowered = {column.lower() for column in columns}
    missing = sorted(set(required).difference(lowered))
    if missing:
        raise ForecastMapContractError(f"{label} is missing required columns: {missing}.")
    return columns


def _require_parquet_types(
    con: Any,
    path: Path,
    *,
    dates: list[str] | None = None,
    text: list[str] | None = None,
    numeric: list[str] | None = None,
    booleans: list[str] | None = None,
) -> None:
    types = parquet_column_types(con, path)
    for column in dates or []:
        if types.get(column) != "DATE":
            raise ForecastMapContractError(f"Parquet column {column} must be DATE.")
    for column in text or []:
        if types.get(column) != "VARCHAR":
            raise ForecastMapContractError(f"Parquet column {column} must be VARCHAR.")
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
    for column in numeric or []:
        if not types.get(column, "").startswith(numeric_prefixes):
            raise ForecastMapContractError(f"Parquet column {column} must be numeric.")
    for column in booleans or []:
        if types.get(column) != "BOOLEAN":
            raise ForecastMapContractError(f"Parquet column {column} must be BOOLEAN.")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ForecastMapContractError(f"{label} is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise ForecastMapContractError(f"{label} JSON root must be an object.")
    return value


def _source_state(path: Path, status: str, reason: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "sourceFile": path.name,
        "records": [],
    }
    if reason:
        result["reason"] = reason
    return result


def load_weekly_context(con: Any, path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required weekly aggregate input not found: {path}")
    _required_columns(con, path, WEEKLY_REQUIRED_COLUMNS, "Weekly aggregate")
    _require_parquet_types(
        con,
        path,
        dates=["week_start"],
        text=["borough", "precinct", "offense_type", "law_category"],
        numeric=["crime_count"],
    )
    stats = fetch_dicts(
        con,
        f"""
        SELECT
            COUNT(*)::BIGINT AS row_count,
            COALESCE(SUM(crime_count), 0)::HUGEINT AS aggregate_count,
            MIN(week_start) AS first_week,
            MAX(week_start) AS latest_week,
            COUNT(DISTINCT (week_start, borough, precinct, offense_type, law_category))::BIGINT
                AS unique_key_count,
            COUNT(DISTINCT (borough, precinct, offense_type, law_category))::BIGINT
                AS segment_count,
            COUNT(*) FILTER (
                WHERE week_start IS NULL OR borough IS NULL OR trim(CAST(borough AS VARCHAR)) = ''
                   OR precinct IS NULL OR trim(CAST(precinct AS VARCHAR)) = ''
                   OR offense_type IS NULL OR trim(CAST(offense_type AS VARCHAR)) = ''
                   OR law_category IS NULL OR trim(CAST(law_category AS VARCHAR)) = ''
                   OR crime_count IS NULL OR crime_count < 0
            )::BIGINT AS malformed_rows,
            COUNT(*) FILTER (WHERE extract(isodow FROM week_start) <> 1)::BIGINT AS non_monday_rows
        FROM read_parquet({sql_string(path)})
        """,
    )[0]
    if int(stats["row_count"]) == 0:
        raise ForecastMapContractError("Weekly aggregate must contain observations.")
    if int(stats["malformed_rows"]):
        raise ForecastMapContractError("Weekly aggregate contains malformed rows.")
    if int(stats["non_monday_rows"]):
        raise ForecastMapContractError("Weekly aggregate contains non-Monday week starts.")
    if int(stats["row_count"]) != int(stats["unique_key_count"]):
        raise ForecastMapContractError("Weekly aggregate contains duplicate logical keys.")

    mapping_rows = fetch_dicts(
        con,
        f"""
        WITH totals AS (
            SELECT
                trim(CAST(borough AS VARCHAR)) AS borough,
                trim(CAST(precinct AS VARCHAR)) AS precinct,
                SUM(crime_count)::HUGEINT AS aggregate_count
            FROM read_parquet({sql_string(path)})
            GROUP BY borough, precinct
        ), ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY precinct ORDER BY aggregate_count DESC, borough
            ) AS mapping_rank
            FROM totals
        )
        SELECT borough, precinct, aggregate_count
        FROM ranked
        WHERE mapping_rank = 1
        ORDER BY precinct
        """,
    )
    canonical: dict[str, str] = {}
    for row in mapping_rows:
        borough = required_text(row["borough"], "weekly borough mapping")
        precinct = required_text(row["precinct"], "weekly precinct mapping")
        if is_unknown(borough) or is_unknown(precinct) or not PRECINCT_RE.fullmatch(precinct):
            continue
        canonical[precinct] = borough
    if not canonical:
        raise ForecastMapContractError("Weekly aggregate has no safe known-precinct mapping.")
    segment_keys = {
        tuple(str(value) for value in row)
        for row in con.execute(
            f"""
            SELECT DISTINCT
                CAST(borough AS VARCHAR),
                CAST(precinct AS VARCHAR),
                CAST(offense_type AS VARCHAR),
                CAST(law_category AS VARCHAR)
            FROM read_parquet({sql_string(path)})
            """
        ).fetchall()
    }
    if len(segment_keys) != int(stats["segment_count"]):
        raise ForecastMapContractError("Weekly segment coverage does not reconcile.")
    return {
        "sourceFile": path.name,
        "rowCount": int(stats["row_count"]),
        "aggregateCount": int(stats["aggregate_count"]),
        "firstWeek": required_date(stats["first_week"], "weekly first week"),
        "latestWeek": required_date(stats["latest_week"], "weekly latest week"),
        "segmentCount": int(stats["segment_count"]),
        "segmentKeys": segment_keys,
        "canonicalPrecinctBorough": canonical,
    }


def load_observation_context(path: Path, weekly: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required Overview contract not found: {path}")
    payload = _read_json(path, "Overview contract")
    if payload.get("schemaVersion") != "1.0.0":
        raise ForecastMapContractError("Overview contract schema is incompatible.")
    data_range = payload.get("dataRange")
    if not isinstance(data_range, dict):
        raise ForecastMapContractError("Overview contract is missing dataRange metadata.")
    safe_start = required_date(data_range.get("safeEventStartDate"), "Overview safe start")
    safe_end = required_date(data_range.get("safeEventEndDate"), "Overview safe end")
    first_week = required_date(data_range.get("firstWeek"), "Overview first week")
    latest_week = required_date(data_range.get("lastWeek"), "Overview latest week")
    latest_complete = required_date(
        data_range.get("latestCompleteWeek"), "Overview latest complete week"
    )
    latest_partial = data_range.get("latestWeekIsPartial")
    if not isinstance(latest_partial, bool):
        raise ForecastMapContractError("Overview latest-week partial flag is malformed.")
    if first_week != weekly["firstWeek"] or latest_week != weekly["latestWeek"]:
        raise ForecastMapContractError("Overview and weekly aggregate week ranges do not match.")
    if not (latest_week <= safe_end <= latest_week + timedelta(days=6)):
        raise ForecastMapContractError("Overview safe end date is outside its latest week.")
    expected_partial = latest_week + timedelta(days=6) > safe_end
    expected_complete = latest_week - timedelta(weeks=1) if expected_partial else latest_week
    if latest_partial != expected_partial or latest_complete != expected_complete:
        raise ForecastMapContractError("Overview latest-complete-week metadata is inconsistent.")
    generated = required_timestamp(payload.get("generatedAtUtc"), "Overview generatedAtUtc")
    expected_generated = datetime.combine(safe_end, datetime.min.time(), timezone.utc)
    if generated != expected_generated:
        raise ForecastMapContractError("Overview generation metadata is not source-derived.")

    ethics = payload.get("ethics")
    if not isinstance(ethics, dict) or not (
        ethics.get("aggregateTrendIntelligenceOnly") is True
        and ethics.get("eventRecordsIncluded") is False
        and ethics.get("demographicAttributesIncluded") is False
        and ethics.get("personLevelScoring") is False
        and ethics.get("enforcementRecommendations") is False
        and ethics.get("patrolRecommendations") is False
    ):
        raise ForecastMapContractError("Overview privacy and ethics flags are unsafe.")

    dimensions = payload.get("dimensions")
    filter_index = (payload.get("filterIndex") or {}).get("precinctsByBorough")
    if not isinstance(dimensions, dict) or not isinstance(filter_index, dict):
        raise ForecastMapContractError("Overview precinct filter reference is missing.")
    boroughs = dimensions.get("boroughs")
    precincts = dimensions.get("precincts")
    if not isinstance(boroughs, list) or not isinstance(precincts, list):
        raise ForecastMapContractError("Overview location dimensions are malformed.")
    if filter_index.get("rowColumns") != ["boroughIndex", "precinctIndexes"]:
        raise ForecastMapContractError("Overview precinct filter schema is incompatible.")
    decoded: dict[str, str] = {}
    for filter_row in filter_index.get("rows", []):
        if not isinstance(filter_row, list) or len(filter_row) != 2:
            raise ForecastMapContractError("Overview precinct filter row is malformed.")
        borough_index, precinct_indexes = filter_row
        if isinstance(borough_index, bool) or not isinstance(borough_index, int):
            raise ForecastMapContractError("Overview borough filter index is malformed.")
        if not 0 <= borough_index < len(boroughs) or not isinstance(precinct_indexes, list):
            raise ForecastMapContractError("Overview precinct filter index is out of range.")
        for precinct_index in precinct_indexes:
            if isinstance(precinct_index, bool) or not isinstance(precinct_index, int):
                raise ForecastMapContractError("Overview precinct index is malformed.")
            if not 0 <= precinct_index < len(precincts):
                raise ForecastMapContractError("Overview precinct index is out of range.")
            precinct = str(precincts[precinct_index])
            borough = str(boroughs[borough_index])
            if PRECINCT_RE.fullmatch(precinct) and not is_unknown(borough):
                if precinct in decoded:
                    raise ForecastMapContractError(
                        "Overview assigns a known precinct to multiple boroughs."
                    )
                decoded[precinct] = borough
    if decoded != weekly["canonicalPrecinctBorough"]:
        raise ForecastMapContractError(
            "Overview and weekly aggregate precinct-to-borough mappings do not match."
        )
    return {
        "sourceFile": path.name,
        "safeEventStartDate": safe_start,
        "safeEventEndDate": safe_end,
        "firstObservedWeek": first_week,
        "latestObservedWeek": latest_week,
        "latestCompleteWeek": latest_complete,
        "latestWeekIsPartial": latest_partial,
    }


def load_forecast_predictions(con: Any, path: Path) -> dict[str, Any]:
    if not path.exists():
        return _source_state(path, "missing", "Forecast prediction artifact is missing.")
    try:
        columns = _required_columns(con, path, FORECAST_REQUIRED_COLUMNS, "ML predictions")
        _require_parquet_types(
            con,
            path,
            dates=["week_start"],
            text=[
                "borough",
                "precinct",
                "offense_type",
                "law_category",
                "ml_model_name",
            ],
            numeric=["predicted_crime_count"],
            booleans=["is_next_week_forecast"],
        )
        unsafe = _unsafe_columns(columns)
        if unsafe:
            raise ForecastMapContractError(
                "ML predictions contain event-, person-, demographic-, recommendation-, "
                "or exact-location columns."
            )
        null_flags = con.execute(
            f"""
            SELECT COUNT(*) FILTER (WHERE is_next_week_forecast IS NULL)::BIGINT
            FROM read_parquet({sql_string(path)})
            """
        ).fetchone()[0]
        if int(null_flags):
            raise ForecastMapContractError("ML predictions contain a missing forecast flag.")
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
        records: list[dict[str, Any]] = []
        keys: set[tuple[str, str, str, str, str]] = set()
        for row in rows:
            week = required_date(row["week_start"], "forecast week_start")
            if week.isoweekday() != 1:
                raise ForecastMapContractError("Forecast week must start on Monday.")
            borough = required_text(row["borough"], "forecast borough")
            precinct = required_text(row["precinct"], "forecast precinct")
            offense = required_text(row["offense_type"], "forecast offense type")
            law = required_text(row["law_category"], "forecast law category")
            model_name = required_text(row["model_name"], "forecast model name")
            key = (week.isoformat(), borough, precinct, offense, law)
            if key in keys:
                raise ForecastMapContractError("Forecast contains duplicate logical keys.")
            keys.add(key)
            records.append(
                {
                    "forecastWeek": week.isoformat(),
                    "borough": borough,
                    "precinct": precinct,
                    "offenseType": offense,
                    "lawCategory": law,
                    "predictedCount": required_number(
                        row["predicted_crime_count"],
                        "forecast predicted count",
                        minimum=0,
                    ),
                    "modelName": model_name,
                }
            )
        records.sort(
            key=lambda record: (
                record["forecastWeek"],
                record["borough"],
                record["precinct"],
                record["offenseType"],
                record["lawCategory"],
            )
        )
        return {
            "status": "available",
            "sourceFile": path.name,
            "records": records,
        }
    except ForecastMapContractError as exc:
        return _source_state(path, "invalid", str(exc))
    except Exception as exc:
        return _source_state(
            path,
            "invalid",
            f"{type(exc).__name__}: ML predictions could not be safely read.",
        )


def load_model_manifest(
    path: Path,
    observation: dict[str, Any],
    weekly: dict[str, Any],
    forecasts: dict[str, Any],
) -> dict[str, Any]:
    if not path.exists():
        return {
            "status": "missing",
            "sourceFile": path.name,
            "reason": "ML model manifest is missing.",
        }
    try:
        manifest = _read_json(path, "ML model manifest")
        artifact_type = required_text(manifest.get("artifact_type"), "ML artifact type")
        if artifact_type != MODEL_ARTIFACT_TYPE:
            raise ForecastMapContractError("ML manifest artifact type is incompatible.")
        artifact_version = required_number(
            manifest.get("artifact_version"), "ML artifact version", minimum=1, integer=True
        )
        artifact_generated_at = required_timestamp(
            manifest.get("generated_at_utc"), "ML artifact generated timestamp"
        )
        if manifest.get("segment_keys") != EXPECTED_SEGMENT_KEYS:
            raise ForecastMapContractError("ML manifest segment keys are incompatible.")
        model = manifest.get("model")
        if not isinstance(model, dict):
            raise ForecastMapContractError("ML manifest model identity is missing.")
        model_name = required_text(model.get("model_name"), "ML model name")
        if not MODEL_NAME_RE.fullmatch(model_name):
            raise ForecastMapContractError("ML model name is not browser-safe.")
        model_version = required_number(
            model.get("model_version"), "ML model version", minimum=1, integer=True
        )
        training = manifest.get("training_window")
        if not isinstance(training, dict):
            raise ForecastMapContractError("ML manifest training window is missing.")
        training_min = required_date(
            training.get("min_week_start"), "ML training minimum week"
        )
        training_max = required_date(
            training.get("max_week_start"), "ML training maximum week"
        )
        segment_count = required_number(
            training.get("segment_count"), "ML segment count", minimum=1, integer=True
        )
        manifest_week = required_date(manifest.get("forecast_week"), "ML forecast week")
        controls = manifest.get("leakage_controls")
        if not isinstance(controls, dict) or not (
            controls.get("random_splits_used") is False
            and controls.get("target_week_excluded_from_features") is True
        ):
            raise ForecastMapContractError(
                "ML manifest does not verify the required time-based leakage controls."
            )
        feature_policy = manifest.get("feature_policy")
        if not isinstance(feature_policy, dict) or not (
            feature_policy.get("person_level_prediction") is False
            and feature_policy.get("enforcement_recommendations") is False
        ):
            raise ForecastMapContractError("ML manifest feature-policy flags are unsafe.")
        if training_min != weekly["firstWeek"]:
            raise ForecastMapContractError("ML training start does not match the weekly source.")
        if int(segment_count) != weekly["segmentCount"]:
            raise ForecastMapContractError("ML segment count does not match the weekly source.")

        latest_observed = observation["latestObservedWeek"]
        expected_week = latest_observed + timedelta(weeks=1)
        stale_reason: str | None = None
        if training_max < latest_observed or manifest_week <= latest_observed:
            stale_reason = "ML model artifacts are behind the validated observation horizon."
        elif training_max > latest_observed:
            raise ForecastMapContractError(
                "ML training end exceeds the validated observation horizon."
            )
        elif manifest_week != expected_week:
            raise ForecastMapContractError(
                "ML manifest does not declare the single supported next-week horizon."
            )

        records = forecasts.get("records") or []
        if records:
            forecast_segment_keys = {
                (
                    record["borough"],
                    record["precinct"],
                    record["offenseType"],
                    record["lawCategory"],
                )
                for record in records
            }
            if forecast_segment_keys != weekly["segmentKeys"]:
                raise ForecastMapContractError(
                    "Forecast logical-key coverage does not match the weekly segment universe."
                )
            forecast_weeks = sorted({record["forecastWeek"] for record in records})
            model_names = sorted({record["modelName"] for record in records})
            if len(forecast_weeks) != 1:
                raise ForecastMapContractError("Forecast contains mixed or multiple horizons.")
            record_week = date.fromisoformat(forecast_weeks[0])
            if record_week <= latest_observed:
                stale_reason = "Forecast week is not after the validated observation horizon."
            elif record_week != expected_week:
                raise ForecastMapContractError("Forecast week is not the supported next week.")
            if record_week != manifest_week:
                raise ForecastMapContractError(
                    "Prediction and ML manifest forecast weeks do not match."
                )
            if model_names != [model_name]:
                raise ForecastMapContractError(
                    "Prediction and ML manifest model names do not match."
                )

        backtest = manifest.get("backtest_window")
        if not isinstance(backtest, dict):
            raise ForecastMapContractError("ML manifest backtest window is missing.")
        backtest_start = required_date(
            backtest.get("backtest_start_week"), "ML backtest start"
        )
        backtest_end = required_date(backtest.get("backtest_end_week"), "ML backtest end")
        if backtest_start > backtest_end or backtest_end > observation["latestCompleteWeek"]:
            raise ForecastMapContractError("ML backtest window is incompatible.")
        backtest_rows = required_number(
            backtest.get("backtest_rows"), "ML backtest row count", minimum=1, integer=True
        )
        manifest_overall = manifest.get("overall_metrics")
        if (
            not isinstance(manifest_overall, list)
            or len(manifest_overall) != 1
            or not isinstance(manifest_overall[0], dict)
        ):
            raise ForecastMapContractError(
                "ML manifest requires one unambiguous overall historical metric row."
            )
        manifest_metric = manifest_overall[0]
        manifest_historical_error = {
            "predictionCount": required_number(
                manifest_metric.get("prediction_count"),
                "manifest historical prediction count",
                minimum=0,
                integer=True,
            ),
            "totalBacktestRows": required_number(
                manifest_metric.get("total_backtest_rows"),
                "manifest historical total backtest rows",
                minimum=1,
                integer=True,
            ),
            "predictionCoveragePct": required_number(
                manifest_metric.get("prediction_coverage_pct"),
                "manifest historical prediction coverage",
                minimum=0,
                maximum=100,
            ),
            "mae": required_number(
                manifest_metric.get("mae"), "manifest historical MAE", minimum=0
            ),
            "rmse": required_number(
                manifest_metric.get("rmse"), "manifest historical RMSE", minimum=0
            ),
            "weightedMae": optional_number(
                manifest_metric.get("weighted_mae"),
                "manifest historical weighted MAE",
                minimum=0,
            ),
        }
        expected_manifest_coverage = round(
            float(manifest_historical_error["predictionCount"])
            / float(manifest_historical_error["totalBacktestRows"])
            * 100,
            2,
        )
        if not math.isclose(
            float(manifest_historical_error["predictionCoveragePct"]),
            float(expected_manifest_coverage),
            rel_tol=0,
            abs_tol=ARITHMETIC_TOLERANCE,
        ):
            raise ForecastMapContractError(
                "ML manifest historical prediction coverage arithmetic is inconsistent."
            )
        if int(backtest_rows) != int(manifest_historical_error["totalBacktestRows"]):
            raise ForecastMapContractError(
                "ML manifest backtest row count and historical metrics do not reconcile."
            )
        if stale_reason:
            return {
                "status": "stale",
                "sourceFile": path.name,
                "reason": stale_reason,
            }
        return {
            "status": "available",
            "sourceFile": path.name,
            "artifactType": artifact_type,
            "artifactVersion": int(artifact_version),
            "artifactGeneratedAtUtc": artifact_generated_at.isoformat(),
            "name": model_name,
            "version": int(model_version),
            "trainingStartWeek": training_min.isoformat(),
            "trainingThroughWeek": training_max.isoformat(),
            "forecastWeek": manifest_week.isoformat(),
            "backtestStartWeek": backtest_start.isoformat(),
            "backtestEndWeek": backtest_end.isoformat(),
            "backtestRowCount": int(backtest_rows),
            "expectedForecastRowCount": weekly["segmentCount"],
            "manifestHistoricalError": manifest_historical_error,
            "leakageControlsVerified": True,
            "pointEstimatesOnly": True,
            "predictionIntervalsAvailable": False,
        }
    except ForecastMapContractError as exc:
        return {"status": "invalid", "sourceFile": path.name, "reason": str(exc)}


def gate_forecast_source(
    forecasts: dict[str, Any], model: dict[str, Any]
) -> dict[str, Any]:
    if forecasts["status"] != "available":
        return forecasts
    if model["status"] == "stale":
        return _source_state(
            Path(forecasts["sourceFile"]), "stale", model.get("reason")
        )
    if model["status"] != "available":
        return _source_state(
            Path(forecasts["sourceFile"]),
            "invalid",
            "Forecast is withheld because the ML model manifest is unavailable or invalid.",
        )
    return forecasts


def load_historical_error(
    path: Path, model: dict[str, Any], forecast_status: str
) -> dict[str, Any]:
    if not path.exists():
        return {
            "status": "missing",
            "sourceFile": path.name,
            "reason": "ML historical metrics artifact is missing.",
        }
    if model["status"] != "available" or forecast_status not in {"available", "missing"}:
        return {
            "status": "invalid",
            "sourceFile": path.name,
            "reason": "Historical error context cannot align to an invalid or stale model.",
        }
    try:
        metrics = _read_json(path, "ML metrics")
        config = metrics.get("model_config")
        analysis = metrics.get("analysis_window")
        metric_groups = metrics.get("metrics")
        record_counts = metrics.get("record_counts")
        if not isinstance(config, dict) or not isinstance(analysis, dict) or not isinstance(
            metric_groups, dict
        ) or not isinstance(record_counts, dict):
            raise ForecastMapContractError("ML metrics metadata is malformed.")
        metric_model = required_text(config.get("model_name"), "metrics model name")
        metric_version = required_number(
            config.get("model_version"), "metrics model version", minimum=1, integer=True
        )
        metrics_generated_at = required_timestamp(
            metrics.get("generated_at_utc"), "ML metrics generated timestamp"
        )
        if metrics_generated_at != required_timestamp(
            model.get("artifactGeneratedAtUtc"), "published ML artifact generated timestamp"
        ):
            raise ForecastMapContractError(
                "ML metrics and manifest generation timestamps do not match."
            )
        metric_week = required_date(
            analysis.get("next_week_forecast_week"), "metrics forecast week"
        )
        if (
            metric_model != model["name"]
            or int(metric_version) != model["version"]
            or metric_week.isoformat() != model["forecastWeek"]
            or required_date(analysis.get("max_week_start"), "metrics latest week").isoformat()
            != model["trainingThroughWeek"]
        ):
            raise ForecastMapContractError(
                "ML metrics do not match the published forecast model and horizon."
            )
        if (
            required_date(
                analysis.get("backtest_start_week"), "metrics backtest start"
            ).isoformat()
            != model["backtestStartWeek"]
            or required_date(
                analysis.get("backtest_end_week"), "metrics backtest end"
            ).isoformat()
            != model["backtestEndWeek"]
        ):
            raise ForecastMapContractError("ML metrics backtest window is misaligned.")
        metrics_backtest_rows = required_number(
            record_counts.get("backtest_rows"),
            "metrics backtest row count",
            minimum=1,
            integer=True,
        )
        metrics_forecast_rows = required_number(
            record_counts.get("next_week_forecast_rows"),
            "metrics forecast row count",
            minimum=0,
            integer=True,
        )
        metrics_segment_count = required_number(
            record_counts.get("output_segment_count"),
            "metrics output segment count",
            minimum=1,
            integer=True,
        )
        metrics_output_rows = required_number(
            record_counts.get("output_rows"),
            "metrics output row count",
            minimum=1,
            integer=True,
        )
        if not (
            int(metrics_backtest_rows) == model["backtestRowCount"]
            and int(metrics_forecast_rows) == model["expectedForecastRowCount"]
            and int(metrics_segment_count) == model["expectedForecastRowCount"]
            and int(metrics_output_rows)
            == int(metrics_backtest_rows) + int(metrics_forecast_rows)
        ):
            raise ForecastMapContractError("ML metrics record counts are misaligned.")
        overall = metric_groups.get("overall")
        if not isinstance(overall, list) or len(overall) != 1 or not isinstance(overall[0], dict):
            raise ForecastMapContractError("ML metrics require one overall backtest row.")
        metric = overall[0]
        normalized_metric = {
            "predictionCount": required_number(
                metric.get("prediction_count"),
                "historical prediction count",
                minimum=0,
                integer=True,
            ),
            "totalBacktestRows": required_number(
                metric.get("total_backtest_rows"),
                "historical total backtest rows",
                minimum=1,
                integer=True,
            ),
            "predictionCoveragePct": required_number(
                metric.get("prediction_coverage_pct"),
                "historical prediction coverage",
                minimum=0,
                maximum=100,
            ),
            "mae": required_number(metric.get("mae"), "historical MAE", minimum=0),
            "rmse": required_number(metric.get("rmse"), "historical RMSE", minimum=0),
            "weightedMae": optional_number(
                metric.get("weighted_mae"), "historical weighted MAE", minimum=0
            ),
        }
        manifest_metric = model["manifestHistoricalError"]
        for key, actual in normalized_metric.items():
            expected = manifest_metric[key]
            if (actual is None) != (expected is None) or (
                actual is not None
                and not math.isclose(
                    float(actual),
                    float(expected),
                    rel_tol=0,
                    abs_tol=ARITHMETIC_TOLERANCE,
                )
            ):
                raise ForecastMapContractError(
                    "ML metrics and manifest historical errors do not reconcile."
                )
        expected_metric_coverage = round(
            float(normalized_metric["predictionCount"])
            / float(normalized_metric["totalBacktestRows"])
            * 100,
            2,
        )
        if not math.isclose(
            float(normalized_metric["predictionCoveragePct"]),
            float(expected_metric_coverage),
            rel_tol=0,
            abs_tol=ARITHMETIC_TOLERANCE,
        ):
            raise ForecastMapContractError(
                "ML metrics historical prediction coverage arithmetic is inconsistent."
            )
        return {
            "status": "available",
            "sourceFile": path.name,
            "unit": "reported events per segment-week",
            "scope": "overall time-based model backtest across all source segments",
            "filterSemantics": "Historical errors are not recomputed for dashboard filters.",
            "backtestStartWeek": model["backtestStartWeek"],
            "backtestEndWeek": model["backtestEndWeek"],
            "backtestRowCount": int(metrics_backtest_rows),
            "mae": normalized_metric["mae"],
            "rmse": normalized_metric["rmse"],
            "weightedMae": normalized_metric["weightedMae"],
            "predictionCoveragePct": normalized_metric["predictionCoveragePct"],
        }
    except ForecastMapContractError as exc:
        return {"status": "invalid", "sourceFile": path.name, "reason": str(exc)}


def load_baseline_manifest(
    path: Path,
    observation: dict[str, Any],
    weekly: dict[str, Any],
    forecast_week: str | None,
) -> dict[str, Any]:
    if not path.exists():
        return {
            "status": "missing",
            "sourceFile": path.name,
            "reason": "Baseline model manifest is missing.",
        }
    try:
        manifest = _read_json(path, "baseline model manifest")
        if required_text(manifest.get("artifact_type"), "baseline artifact type") != BASELINE_ARTIFACT_TYPE:
            raise ForecastMapContractError("Baseline manifest artifact type is incompatible.")
        artifact_version = required_number(
            manifest.get("artifact_version"),
            "baseline artifact version",
            minimum=1,
            integer=True,
        )
        if manifest.get("segment_keys") != EXPECTED_SEGMENT_KEYS:
            raise ForecastMapContractError("Baseline manifest segment keys are incompatible.")
        training = manifest.get("training_window")
        if not isinstance(training, dict):
            raise ForecastMapContractError("Baseline training window is missing.")
        training_min = required_date(
            training.get("min_week_start"), "baseline training minimum week"
        )
        training_max = required_date(
            training.get("max_week_start"), "baseline training maximum week"
        )
        segment_count = required_number(
            training.get("segment_count"), "baseline segment count", minimum=1, integer=True
        )
        baseline_week = required_date(
            manifest.get("forecast_week"), "baseline forecast week"
        )
        selected = manifest.get("selected_baseline")
        if not isinstance(selected, dict):
            raise ForecastMapContractError("Selected baseline metadata is missing.")
        method = required_text(selected.get("baseline_method"), "selected baseline method")
        if method not in BASELINE_METHOD_COLUMNS:
            raise ForecastMapContractError("Selected baseline method is unsupported.")
        rules = manifest.get("baseline_model_rules")
        if not isinstance(rules, list):
            raise ForecastMapContractError("Baseline model rules are missing.")
        rule = next(
            (
                item
                for item in rules
                if isinstance(item, dict) and item.get("baseline_method") == method
            ),
            None,
        )
        if not isinstance(rule, dict):
            raise ForecastMapContractError("Selected baseline rule is missing.")
        semantics = required_text(rule.get("rule"), "selected baseline rule")
        required_prior_weeks = required_number(
            rule.get("required_prior_weeks"),
            "selected baseline prior weeks",
            minimum=1,
            integer=True,
        )
        expected_semantics, expected_prior_weeks = BASELINE_RULES[method]
        if semantics != expected_semantics or int(required_prior_weeks) != expected_prior_weeks:
            raise ForecastMapContractError(
                "Selected baseline rule does not match the verified repository definition."
            )
        controls = manifest.get("leakage_controls")
        if not isinstance(controls, dict) or controls.get(
            "target_week_excluded_from_features"
        ) is not True:
            raise ForecastMapContractError(
                "Baseline manifest does not verify target-week exclusion."
            )
        if controls.get("zero_fill_rule") != BASELINE_ZERO_FILL_RULE:
            raise ForecastMapContractError("Baseline zero-fill rule is incompatible.")
        policy = manifest.get("feature_policy")
        if not isinstance(policy, dict) or not (
            policy.get("person_level_prediction") is False
            and policy.get("enforcement_recommendations") is False
        ):
            raise ForecastMapContractError("Baseline manifest feature-policy flags are unsafe.")
        if training_min != weekly["firstWeek"] or int(segment_count) != weekly["segmentCount"]:
            raise ForecastMapContractError("Baseline training metadata does not match the source.")
        if training_max < observation["latestObservedWeek"] or baseline_week <= observation[
            "latestObservedWeek"
        ]:
            return {
                "status": "stale",
                "sourceFile": path.name,
                "reason": "Baseline artifacts are behind the validated observation horizon.",
            }
        if training_max > observation["latestObservedWeek"]:
            raise ForecastMapContractError(
                "Baseline training end exceeds the validated observation horizon."
            )
        expected_week = observation["latestObservedWeek"] + timedelta(weeks=1)
        if baseline_week != expected_week or (
            forecast_week is not None and baseline_week.isoformat() != forecast_week
        ):
            raise ForecastMapContractError(
                "Baseline and ML forecast horizons do not match."
            )
        return {
            "status": "available",
            "sourceFile": path.name,
            "artifactType": BASELINE_ARTIFACT_TYPE,
            "artifactVersion": int(artifact_version),
            "method": method,
            "valueColumn": BASELINE_METHOD_COLUMNS[method],
            "semantics": expected_semantics,
            "requiredPriorWeeks": expected_prior_weeks,
            "forecastWeek": baseline_week.isoformat(),
            "trainingThroughWeek": training_max.isoformat(),
            "priorOnly": True,
            "zeroFillRule": BASELINE_ZERO_FILL_RULE,
        }
    except ForecastMapContractError as exc:
        return {"status": "invalid", "sourceFile": path.name, "reason": str(exc)}


def compute_expected_baseline_values(
    con: Any, weekly_path: Path, manifest: dict[str, Any]
) -> dict[tuple[str, str, str, str, str], int | float | None]:
    """Re-derive the selected prior-only baseline from the weekly aggregate."""
    forecast_week = date.fromisoformat(manifest["forecastWeek"])
    method = manifest["method"]
    if method == "previous_week":
        history_start = forecast_week - timedelta(weeks=1)
        history_end = history_start
        divisor = 1
    elif method == "trailing_4_week_mean":
        history_start = forecast_week - timedelta(weeks=4)
        history_end = forecast_week - timedelta(weeks=1)
        divisor = 4
    elif method == "trailing_8_week_mean":
        history_start = forecast_week - timedelta(weeks=8)
        history_end = forecast_week - timedelta(weeks=1)
        divisor = 8
    elif method == "previous_year_same_week":
        history_start = forecast_week - timedelta(weeks=52)
        history_end = history_start
        divisor = 1
    else:  # protected by manifest validation
        raise ForecastMapContractError("Selected baseline method is unsupported.")
    rows = fetch_dicts(
        con,
        f"""
        SELECT
            CAST(borough AS VARCHAR) AS borough,
            CAST(precinct AS VARCHAR) AS precinct,
            CAST(offense_type AS VARCHAR) AS offense_type,
            CAST(law_category AS VARCHAR) AS law_category,
            MIN(week_start) AS segment_first_week,
            CASE
                WHEN MIN(week_start) <= DATE {sql_string(history_start.isoformat())}
                THEN COALESCE(
                    SUM(crime_count) FILTER (
                        WHERE week_start BETWEEN DATE {sql_string(history_start.isoformat())}
                                             AND DATE {sql_string(history_end.isoformat())}
                    ),
                    0
                )::DOUBLE / {divisor}
                ELSE NULL
            END AS expected_baseline
        FROM read_parquet({sql_string(weekly_path)})
        GROUP BY borough, precinct, offense_type, law_category
        ORDER BY borough, precinct, offense_type, law_category
        """,
    )
    result: dict[tuple[str, str, str, str, str], int | float | None] = {}
    for row in rows:
        key = (
            manifest["forecastWeek"],
            required_text(row["borough"], "derived baseline borough"),
            required_text(row["precinct"], "derived baseline precinct"),
            required_text(row["offense_type"], "derived baseline offense type"),
            required_text(row["law_category"], "derived baseline law category"),
        )
        result[key] = optional_number(
            row["expected_baseline"], "derived historical baseline", minimum=0
        )
    return result


def load_baseline_values(
    con: Any,
    path: Path,
    weekly_path: Path,
    manifest: dict[str, Any],
    forecast_records: list[dict[str, Any]],
) -> dict[str, Any]:
    if manifest["status"] != "available":
        return {
            "status": manifest["status"],
            "sourceFile": path.name,
            "reason": manifest.get("reason", "Baseline manifest is unavailable."),
            "values": {},
        }
    if not path.exists():
        return {
            "status": "missing",
            "sourceFile": path.name,
            "reason": "Baseline prediction artifact is missing.",
            "values": {},
        }
    try:
        required = BASELINE_REQUIRED_COLUMNS + [manifest["valueColumn"]]
        columns = _required_columns(con, path, required, "Baseline predictions")
        _require_parquet_types(
            con,
            path,
            dates=["week_start"],
            text=["borough", "precinct", "offense_type", "law_category"],
            numeric=[manifest["valueColumn"]],
            booleans=["is_next_week_forecast"],
        )
        unsafe = _unsafe_columns(columns)
        if unsafe:
            raise ForecastMapContractError(
                "Baseline predictions contain unsafe event-, person-, demographic-, "
                "recommendation-, or exact-location columns."
            )
        null_flags = con.execute(
            f"""
            SELECT COUNT(*) FILTER (WHERE is_next_week_forecast IS NULL)::BIGINT
            FROM read_parquet({sql_string(path)})
            """
        ).fetchone()[0]
        if int(null_flags):
            raise ForecastMapContractError("Baseline predictions contain a missing forecast flag.")
        value_column = manifest["valueColumn"].replace('"', '""')
        rows = fetch_dicts(
            con,
            f"""
            SELECT
                week_start,
                CAST(borough AS VARCHAR) AS borough,
                CAST(precinct AS VARCHAR) AS precinct,
                CAST(offense_type AS VARCHAR) AS offense_type,
                CAST(law_category AS VARCHAR) AS law_category,
                \"{value_column}\" AS baseline_value
            FROM read_parquet({sql_string(path)})
            WHERE is_next_week_forecast IS TRUE
            ORDER BY week_start, borough, precinct, offense_type, law_category
            """,
        )
        values: dict[tuple[str, str, str, str, str], int | float | None] = {}
        for row in rows:
            week = required_date(row["week_start"], "baseline forecast week").isoformat()
            key = (
                week,
                required_text(row["borough"], "baseline borough"),
                required_text(row["precinct"], "baseline precinct"),
                required_text(row["offense_type"], "baseline offense type"),
                required_text(row["law_category"], "baseline law category"),
            )
            if key in values:
                raise ForecastMapContractError("Baseline contains duplicate logical keys.")
            values[key] = optional_number(
                row["baseline_value"], "historical baseline", minimum=0
            )
        forecast_keys = {
            (
                record["forecastWeek"],
                record["borough"],
                record["precinct"],
                record["offenseType"],
                record["lawCategory"],
            )
            for record in forecast_records
        }
        if set(values) != forecast_keys:
            raise ForecastMapContractError(
                "Baseline and ML forecast logical-key coverage does not match."
            )
        if values and {key[0] for key in values} != {manifest["forecastWeek"]}:
            raise ForecastMapContractError(
                "Baseline prediction week does not match its manifest."
            )
        expected_values = compute_expected_baseline_values(con, weekly_path, manifest)
        if set(expected_values) != forecast_keys:
            raise ForecastMapContractError(
                "Derived baseline coverage does not match the ML forecast segment universe."
            )
        for key, actual in values.items():
            expected = expected_values[key]
            if (actual is None) != (expected is None) or (
                actual is not None
                and not math.isclose(
                    float(actual),
                    float(expected),
                    rel_tol=0,
                    abs_tol=ARITHMETIC_TOLERANCE,
                )
            ):
                raise ForecastMapContractError(
                    "Baseline values do not match the verified prior-only weekly derivation."
                )
        return {"status": "available", "sourceFile": path.name, "values": values}
    except ForecastMapContractError as exc:
        return {"status": "invalid", "sourceFile": path.name, "reason": str(exc), "values": {}}
    except Exception as exc:
        return {
            "status": "invalid",
            "sourceFile": path.name,
            "reason": f"{type(exc).__name__}: baseline predictions could not be safely read.",
            "values": {},
        }


def prepare_publishable_records(
    source: dict[str, Any],
    canonical_mapping: dict[str, str],
    baseline_values: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    published: list[dict[str, Any]] = []
    withheld_counts = {"unmappableLocation": 0, "boroughMismatch": 0}
    withheld_values: list[int | float] = []
    source_values: list[int | float] = []
    unknown_offense_rows = 0
    baseline_available = baseline_values["status"] == "available"
    values = baseline_values.get("values") or {}
    for record in source.get("records", []):
        predicted = record["predictedCount"]
        source_values.append(predicted)
        precinct = record["precinct"]
        borough = record["borough"]
        canonical_borough = canonical_mapping.get(precinct)
        if (
            is_unknown(borough)
            or is_unknown(precinct)
            or not PRECINCT_RE.fullmatch(precinct)
            or canonical_borough is None
        ):
            withheld_counts["unmappableLocation"] += 1
            withheld_values.append(predicted)
            continue
        if borough != canonical_borough:
            withheld_counts["boroughMismatch"] += 1
            withheld_values.append(predicted)
            continue
        key = (
            record["forecastWeek"],
            borough,
            precinct,
            record["offenseType"],
            record["lawCategory"],
        )
        baseline = values.get(key) if baseline_available else None
        change_count: int | float | None = None
        change_pct: int | float | None = None
        if baseline is not None:
            change_count = required_number(
                float(predicted) - float(baseline), "expected change count"
            )
            if float(baseline) > 0:
                change_pct = required_number(
                    float(change_count) / float(baseline) * 100,
                    "expected change percentage",
                )
        item = dict(record)
        item.update(
            {
                "historicalBaseline": baseline,
                "expectedChangeCount": change_count,
                "expectedChangePct": change_pct,
                "precinctLocationKey": location_key(precinct),
            }
        )
        if is_unknown(record["offenseType"]):
            unknown_offense_rows += 1
        published.append(item)
    published.sort(
        key=lambda record: (
            record["forecastWeek"],
            record["borough"],
            record["precinct"],
            record["offenseType"],
            record["lawCategory"],
        )
    )
    return published, {
        "sourceValues": source_values,
        "withheldValues": withheld_values,
        "withheldReasonCounts": withheld_counts,
        "unknownOffenseRowCount": unknown_offense_rows,
    }


def build_dimensions(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "forecastWeeks": sorted({record["forecastWeek"] for record in records}),
        "boroughs": sorted({record["borough"] for record in records}),
        "precincts": sorted({record["precinct"] for record in records}),
        "offenseTypes": sorted({record["offenseType"] for record in records}),
        "lawCategories": sorted({record["lawCategory"] for record in records}),
    }


def build_filter_index(
    records: list[dict[str, Any]], dimensions: dict[str, list[str]]
) -> dict[str, Any]:
    borough_indexes = {value: index for index, value in enumerate(dimensions["boroughs"])}
    precinct_indexes = {value: index for index, value in enumerate(dimensions["precincts"])}
    by_borough = {borough: set() for borough in dimensions["boroughs"]}
    for record in records:
        by_borough[record["borough"]].add(record["precinct"])
    return {
        "precinctsByBorough": {
            "rowColumns": ["boroughIndex", "precinctIndexes"],
            "rows": [
                [
                    borough_indexes[borough],
                    sorted(precinct_indexes[value] for value in by_borough[borough]),
                ]
                for borough in dimensions["boroughs"]
            ],
            "semantics": (
                "Known precincts use the Overview all-time aggregate dominant-borough "
                "assignment; unmappable and noncanonical source rows are withheld."
            ),
        }
    }


def index_forecasts(
    source: dict[str, Any],
    records: list[dict[str, Any]],
    dimensions: dict[str, list[str]],
    audit: dict[str, Any],
) -> dict[str, Any]:
    indexes = {
        name: {value: index for index, value in enumerate(values)}
        for name, values in dimensions.items()
    }
    rows = [
        [
            indexes["forecastWeeks"][record["forecastWeek"]],
            indexes["boroughs"][record["borough"]],
            indexes["precincts"][record["precinct"]],
            indexes["offenseTypes"][record["offenseType"]],
            indexes["lawCategories"][record["lawCategory"]],
            record["predictedCount"],
            record["historicalBaseline"],
            record["expectedChangeCount"],
            record["expectedChangePct"],
            record["precinctLocationKey"],
        ]
        for record in records
    ]
    source_count = len(source.get("records") or []) if source["status"] == "available" else None
    source_segment_count = (
        source.get("expectedSegmentCount") if source["status"] == "available" else None
    )
    source_values = audit.get("sourceValues") or []
    withheld_values = audit.get("withheldValues") or []
    predicted_values = [record["predictedCount"] for record in records]
    counts_by_borough = [0] * len(dimensions["boroughs"])
    for row in rows:
        counts_by_borough[row[1]] += 1
    summary: dict[str, Any] = {
        "rowCount": len(rows),
        "sourceRowCount": source_count,
        "sourceSegmentCount": source_segment_count,
        "modelSegmentCoveragePct": (
            compact_pct(source_count, source_segment_count)
            if source_count is not None and source_segment_count
            else None
        ),
        "withheldRowCount": (
            None if source_count is None else source_count - len(rows)
        ),
        "withheldReasonCounts": audit.get("withheldReasonCounts")
        or {"unmappableLocation": 0, "boroughMismatch": 0},
        "sourcePredictedTotal": compact_sum(source_values) if source_values else None,
        "predictedTotal": compact_sum(predicted_values) if predicted_values else None,
        "withheldPredictedTotal": compact_sum(withheld_values) if withheld_values else (
            0 if source_values and len(rows) == len(source_values) else None
        ),
        "rowCoveragePct": (
            compact_pct(len(rows), source_count) if source_count else None
        ),
        "predictedVolumeCoveragePct": (
            compact_pct(compact_sum(predicted_values), compact_sum(source_values))
            if predicted_values and source_values and float(compact_sum(source_values)) > 0
            else None
        ),
        "publishedPrecinctCount": len(dimensions["precincts"]),
        "publishedBoroughCount": len(dimensions["boroughs"]),
        "unknownOffenseRowCount": audit.get("unknownOffenseRowCount", 0),
        "countsByBorough": counts_by_borough,
        "zeroPredictionRowCount": sum(
            1 for value in predicted_values if float(value) == 0
        ),
    }
    result: dict[str, Any] = {
        "status": source["status"],
        "sourceFile": source["sourceFile"],
        "isEmpty": source["status"] == "available" and not rows,
        "rowColumns": ROW_COLUMNS,
        "rows": rows,
        "summary": summary,
    }
    if source.get("reason"):
        result["reason"] = source["reason"]
    return result


def build_baseline_section(
    manifest: dict[str, Any],
    values: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    status = values["status"]
    available_count = sum(
        record["historicalBaseline"] is not None for record in records
    )
    change_count = sum(
        record["expectedChangeCount"] is not None for record in records
    )
    change_pct = sum(record["expectedChangePct"] is not None for record in records)
    section: dict[str, Any] = {
        "status": status,
        "sourceFile": values["sourceFile"],
        "manifestSourceFile": manifest["sourceFile"],
        "method": manifest.get("method") if status == "available" else None,
        "semantics": manifest.get("semantics") if status == "available" else None,
        "requiredPriorWeeks": (
            manifest.get("requiredPriorWeeks") if status == "available" else None
        ),
        "priorOnly": True if status == "available" else None,
        "zeroFillRule": manifest.get("zeroFillRule") if status == "available" else None,
        "valueAvailability": (
            "unavailable"
            if not records or available_count == 0
            else "available"
            if available_count == len(records)
            else "partial"
        ),
        "summary": {
            "publishedRowCount": len(records),
            "baselineAvailableRowCount": available_count,
            "baselineUnavailableRowCount": len(records) - available_count,
            "expectedChangeCountAvailableRowCount": change_count,
            "expectedChangePctAvailableRowCount": change_pct,
            "zeroBaselineRowCount": sum(
                record["historicalBaseline"] is not None
                and float(record["historicalBaseline"]) == 0
                for record in records
            ),
        },
    }
    if values.get("reason"):
        section["reason"] = values["reason"]
    return section


def availability_value(available: int, total: int) -> str:
    if total == 0 or available == 0:
        return "unavailable"
    return "available" if available == total else "partial"


def ensure_output_does_not_overwrite_inputs(
    output_path: Path, input_paths: list[Path]
) -> None:
    resolved_output = output_path.resolve()
    collisions = [path for path in input_paths if path.resolve() == resolved_output]
    if collisions:
        raise ForecastMapContractError(
            "Forecast Map output path must not overwrite a source artifact."
        )


def build_dashboard_forecast_map(
    *,
    weekly_path: Path,
    overview_path: Path,
    ml_predictions_path: Path,
    ml_metrics_path: Path,
    ml_manifest_path: Path,
    baseline_predictions_path: Path,
    baseline_manifest_path: Path,
    output_path: Path,
    threads: int = 4,
) -> dict[str, Any]:
    input_paths = [
        weekly_path,
        overview_path,
        ml_predictions_path,
        ml_metrics_path,
        ml_manifest_path,
        baseline_predictions_path,
        baseline_manifest_path,
    ]
    ensure_output_does_not_overwrite_inputs(output_path, input_paths)
    duckdb = require_duckdb()
    con = duckdb.connect(database=":memory:")
    try:
        con.execute(f"PRAGMA threads={max(1, int(threads))}")
        weekly = load_weekly_context(con, weekly_path)
        observation = load_observation_context(overview_path, weekly)
        forecast_source = load_forecast_predictions(con, ml_predictions_path)
        if forecast_source["status"] == "available":
            forecast_source["expectedSegmentCount"] = weekly["segmentCount"]
        model = load_model_manifest(
            ml_manifest_path, observation, weekly, forecast_source
        )
        forecast_source = gate_forecast_source(forecast_source, model)
        source_records = (
            forecast_source["records"] if forecast_source["status"] == "available" else []
        )
        forecast_week = (
            model.get("forecastWeek") if model.get("status") == "available" else None
        )
        baseline_manifest = load_baseline_manifest(
            baseline_manifest_path, observation, weekly, forecast_week
        )
        baseline_values = load_baseline_values(
            con,
            baseline_predictions_path,
            weekly_path,
            baseline_manifest,
            source_records,
        )
    finally:
        con.close()

    historical_error = load_historical_error(
        ml_metrics_path, model, forecast_source["status"]
    )
    audit = {
        "sourceValues": [],
        "withheldValues": [],
        "withheldReasonCounts": {"unmappableLocation": 0, "boroughMismatch": 0},
        "unknownOffenseRowCount": 0,
    }
    publishable: list[dict[str, Any]] = []
    if forecast_source["status"] == "available":
        publishable, audit = prepare_publishable_records(
            forecast_source,
            weekly["canonicalPrecinctBorough"],
            baseline_values,
        )
        if source_records and not publishable:
            forecast_source = _source_state(
                ml_predictions_path,
                "invalid",
                "Forecast has no publishable map-compatible precinct rows.",
            )
            publishable = []
            audit = {
                "sourceValues": [],
                "withheldValues": [],
                "withheldReasonCounts": {
                    "unmappableLocation": 0,
                    "boroughMismatch": 0,
                },
                "unknownOffenseRowCount": 0,
            }
    dimensions = build_dimensions(publishable)
    forecast = index_forecasts(forecast_source, publishable, dimensions, audit)
    filter_index = build_filter_index(publishable, dimensions)
    baseline = build_baseline_section(
        baseline_manifest, baseline_values, publishable
    )
    baseline_summary = baseline["summary"]
    supported_weeks = dimensions["forecastWeeks"] if forecast["status"] == "available" else []
    generated_at = f"{observation['safeEventEndDate'].isoformat()}T00:00:00Z"

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAtUtc": generated_at,
        "application": {
            "name": "NYC Crime Intelligence",
            "phase": "Phase 7C.1",
            "view": "Forecast Map Data Contract",
        },
        "dataRange": {
            "safeEventStartDate": observation["safeEventStartDate"].isoformat(),
            "safeEventEndDate": observation["safeEventEndDate"].isoformat(),
            "firstObservedWeek": observation["firstObservedWeek"].isoformat(),
            "latestObservedWeek": observation["latestObservedWeek"].isoformat(),
            "latestCompleteWeek": observation["latestCompleteWeek"].isoformat(),
            "latestWeekIsPartial": observation["latestWeekIsPartial"],
            "supportedForecastWeeks": supported_weeks,
        },
        "dimensions": dimensions,
        "filterIndex": filter_index,
        "forecast": forecast,
        "availability": {
            "forecastPointEstimates": (
                "available"
                if forecast["status"] == "available" and forecast["rows"]
                else "empty"
                if forecast["status"] == "available"
                else forecast["status"]
            ),
            "historicalBaseline": availability_value(
                baseline_summary["baselineAvailableRowCount"], len(publishable)
            ),
            "expectedChangeCount": availability_value(
                baseline_summary["expectedChangeCountAvailableRowCount"], len(publishable)
            ),
            "expectedChangePct": availability_value(
                baseline_summary["expectedChangePctAvailableRowCount"], len(publishable)
            ),
            "predictionIntervals": "unavailable",
            "precinctSpatialReference": "location-key-only",
        },
        "model": {
            "status": model["status"],
            "sourceFile": model["sourceFile"],
            "artifactType": model.get("artifactType"),
            "artifactVersion": model.get("artifactVersion"),
            "artifactGeneratedAtUtc": model.get("artifactGeneratedAtUtc"),
            "independentTrainingTime": dict(INDEPENDENT_TRAINING_TIME),
            "name": model.get("name"),
            "version": model.get("version"),
            "trainingStartWeek": model.get("trainingStartWeek"),
            "trainingThroughWeek": model.get("trainingThroughWeek"),
            "forecastWeek": model.get("forecastWeek"),
            "leakageControlsVerified": model.get("leakageControlsVerified", False),
            "pointEstimatesOnly": True,
            "predictionIntervalsAvailable": False,
            "historicalError": historical_error,
            **({"reason": model["reason"]} if model.get("reason") else {}),
        },
        "baseline": baseline,
        "forecastSemantics": {
            "horizon": "one-next-week",
            "weekStartDay": "Monday",
            "target": (
                "Expected aggregate reported complaint-event volume for one segment-week."
            ),
            "grain": (
                "forecast week + borough + precinct + offense type + law category"
            ),
            "observationHorizon": (
                "The forecast is next-week only relative to the fixed repository source "
                "horizon, not relative to the current wall clock."
            ),
            "partialWeekUse": (
                "The model and selected baseline may use the latest partial observed week "
                "as prior information; the target week itself is excluded from features."
            ),
            "interpretationBoundary": (
                "Point estimates describe aggregate reported-event volume; they do not "
                "predict individual behavior or a specific future incident location."
            ),
        },
        "locationKeySemantics": {
            "scheme": "nypd-precinct:<source precinct label>",
            "stableJoinKeyOnly": True,
            "spatialReferenceAvailable": False,
            "coordinatesIncluded": False,
            "geometryIncluded": False,
            "coverage": (
                "All known precinct labels that pass the canonical borough mapping have "
                "an opaque key. This key-only contract does not embed the separate verified "
                "Phase 7C.3 precinct geometry; runtime reconciliation validates its complete "
                "coverage against that dedicated contract."
            ),
        },
        "methodology": {
            "forecastSelection": "is_next_week_forecast = true",
            "precinctBoroughPolicy": (
                "For each known precinct, use the borough with the largest all-time weekly "
                "aggregate count; ties use borough lexical order. Source rows with UNKNOWN "
                "geography or a noncanonical borough are withheld, never remapped or summed."
            ),
            "baselineSelection": (
                "Use the manifest-selected documented prior-only baseline when its artifact "
                "matches every ML forecast logical key; otherwise publish null baseline/change values."
            ),
            "changeArithmetic": (
                "expectedChangeCount = rounded predictedCount - rounded historicalBaseline; "
                "expectedChangePct = expectedChangeCount / historicalBaseline * 100 only "
                "when baseline is positive."
            ),
            "numericRoundingDigits": NUMERIC_DIGITS,
            "arithmeticTolerance": ARITHMETIC_TOLERANCE,
            "generationTimestampPolicy": (
                "generatedAtUtc is deterministically the maximum aggregate-safe event date "
                "at 00:00:00Z; the current clock is never read."
            ),
            "freshnessPolicy": (
                "No wall-clock TTL is invented. Stale means the model training/forecast "
                "horizon is behind the validated weekly/Overview observation horizon."
            ),
        },
        "limitations": [
            "The contract contains point estimates only; no confidence or prediction interval exists.",
            *(
                [
                    "The latest observed source week is partial and can depress lag-based forecast values."
                ]
                if observation["latestWeekIsPartial"]
                else []
            ),
            (
                "The source forecast covers all historical model segments, including inactive "
                "and zero-prediction segments; published rows are the map-compatible subset."
            ),
            "UNKNOWN offense is an explicit aggregate classification label, not a fabricated category.",
            "Unmappable or noncanonical borough/precinct source rows are withheld and quantified.",
            (
                "This key-only contract embeds no coordinate, centroid, boundary, or geometry; "
                "the separate verified Phase 7C.3 spatial-reference contract supplies the "
                "complete administrative precinct boundaries."
            ),
            "Reporting, classification, delay, revision, and model error affect these estimates.",
            "Forecasts are not crime certainty, neighborhood-danger scores, or grounds for action.",
        ],
        "provenance": {
            "weeklyAggregate": {
                "status": "available",
                "sourceFile": weekly_path.name,
                "publishedUse": "Observation horizon and aggregate canonical precinct mapping only.",
            },
            "overview": {
                "status": "available",
                "sourceFile": overview_path.name,
                "publishedUse": "Validated safe dates, complete-week status, and filter alignment only.",
            },
            "mlPredictions": {
                "status": forecast_source["status"],
                "sourceFile": ml_predictions_path.name,
                "publishedUse": "Validated aggregate next-week point estimates only.",
            },
            "mlManifest": {
                "status": model["status"],
                "sourceFile": ml_manifest_path.name,
                "publishedUse": "Allowlisted model identity, horizon, window, and leakage controls only.",
            },
            "mlMetrics": {
                "status": historical_error["status"],
                "sourceFile": ml_metrics_path.name,
                "publishedUse": "Allowlisted aligned overall historical error metrics only.",
            },
            "baselinePredictions": {
                "status": baseline_values["status"],
                "sourceFile": baseline_predictions_path.name,
                "publishedUse": "Selected aggregate prior-only baseline values only.",
            },
            "baselineManifest": {
                "status": baseline_manifest["status"],
                "sourceFile": baseline_manifest_path.name,
                "publishedUse": "Allowlisted baseline selection and prior-only semantics only.",
            },
        },
        "privacy": {
            "aggregateOnly": True,
            "eventRecordsIncluded": False,
            "complaintIdentifiersIncluded": False,
            "sourceRowIdentifiersIncluded": False,
            "namesIncluded": False,
            "exactAddressesIncluded": False,
            "eventLevelCoordinatesIncluded": False,
            "demographicAttributesIncluded": False,
        },
        "ethics": {
            "aggregateReportedEventVolumeOnly": True,
            "individualBehaviorPrediction": False,
            "specificIncidentLocationPrediction": False,
            "personLevelScoring": False,
            "patrolRecommendations": False,
            "enforcementRecommendations": False,
        },
    }
    validate_forecast_map_payload(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
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


def _validate_sorted_dimensions(dimensions: dict[str, Any]) -> None:
    if set(dimensions) != set(DIMENSION_KEYS):
        raise ForecastMapContractError("Forecast Map dimensions do not match the schema.")
    for name in DIMENSION_KEYS:
        values = dimensions[name]
        if not isinstance(values, list) or values != sorted(values):
            raise ForecastMapContractError(f"Dimension {name} must be a sorted list.")
        if len(values) != len(set(values)) or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise ForecastMapContractError(f"Dimension {name} contains malformed labels.")
    for value in dimensions["forecastWeeks"]:
        if required_date(value, "forecast week dimension").isoweekday() != 1:
            raise ForecastMapContractError("Forecast week dimension must contain Mondays.")
    if any(is_unknown(value) for value in dimensions["boroughs"]):
        raise ForecastMapContractError("Unmappable borough labels may not be published.")
    if any(
        is_unknown(value) or not PRECINCT_RE.fullmatch(value)
        for value in dimensions["precincts"]
    ):
        raise ForecastMapContractError("Unmappable precinct labels may not be published.")


def _validate_filter_index(
    filter_index: dict[str, Any],
    dimensions: dict[str, list[str]],
    row_pairs: set[tuple[int, int]],
) -> None:
    if set(filter_index) != {"precinctsByBorough"}:
        raise ForecastMapContractError("Forecast Map filter index has unexpected sections.")
    index = filter_index["precinctsByBorough"]
    if not isinstance(index, dict) or index.get("rowColumns") != [
        "boroughIndex",
        "precinctIndexes",
    ]:
        raise ForecastMapContractError("Forecast Map precinct filter schema is invalid.")
    rows = index.get("rows")
    if not isinstance(rows, list) or len(rows) != len(dimensions["boroughs"]):
        raise ForecastMapContractError("Forecast Map precinct filter rows are incomplete.")
    decoded_pairs: set[tuple[int, int]] = set()
    assigned_precincts: set[int] = set()
    previous_borough = -1
    for row in rows:
        if not isinstance(row, list) or len(row) != 2:
            raise ForecastMapContractError("Forecast Map precinct filter row is malformed.")
        borough_index, precinct_indexes = row
        if isinstance(borough_index, bool) or not isinstance(borough_index, int):
            raise ForecastMapContractError("Forecast Map borough filter index is malformed.")
        if borough_index <= previous_borough or not 0 <= borough_index < len(
            dimensions["boroughs"]
        ):
            raise ForecastMapContractError("Forecast Map borough filter order is invalid.")
        previous_borough = borough_index
        if not isinstance(precinct_indexes, list) or precinct_indexes != sorted(
            precinct_indexes
        ) or len(precinct_indexes) != len(set(precinct_indexes)):
            raise ForecastMapContractError("Forecast Map precinct filter indexes are malformed.")
        for precinct_index in precinct_indexes:
            if (
                isinstance(precinct_index, bool)
                or not isinstance(precinct_index, int)
                or not 0 <= precinct_index < len(dimensions["precincts"])
            ):
                raise ForecastMapContractError("Forecast Map precinct filter index is out of range.")
            if precinct_index in assigned_precincts:
                raise ForecastMapContractError(
                    "Forecast Map precinct is assigned to multiple boroughs."
                )
            assigned_precincts.add(precinct_index)
            decoded_pairs.add((borough_index, precinct_index))
    if assigned_precincts != set(range(len(dimensions["precincts"]))):
        raise ForecastMapContractError("Forecast Map filter omits a precinct.")
    if decoded_pairs != row_pairs:
        raise ForecastMapContractError(
            "Forecast Map rows and precinct-to-borough filter index do not reconcile."
        )


def validate_forecast_map_payload(payload: dict[str, Any]) -> None:
    required_top_level = {
        "schemaVersion",
        "generatedAtUtc",
        "application",
        "dataRange",
        "dimensions",
        "filterIndex",
        "forecast",
        "availability",
        "model",
        "baseline",
        "forecastSemantics",
        "locationKeySemantics",
        "methodology",
        "limitations",
        "provenance",
        "privacy",
        "ethics",
    }
    if set(payload) != required_top_level:
        raise ForecastMapContractError("Forecast Map payload sections do not match the schema.")
    if payload["schemaVersion"] != SCHEMA_VERSION:
        raise ForecastMapContractError("Unexpected Forecast Map schema version.")
    if payload["application"] != {
        "name": "NYC Crime Intelligence",
        "phase": "Phase 7C.1",
        "view": "Forecast Map Data Contract",
    }:
        raise ForecastMapContractError("Forecast Map application identity is invalid.")

    data_range = payload["dataRange"]
    expected_range_keys = {
        "safeEventStartDate",
        "safeEventEndDate",
        "firstObservedWeek",
        "latestObservedWeek",
        "latestCompleteWeek",
        "latestWeekIsPartial",
        "supportedForecastWeeks",
    }
    if not isinstance(data_range, dict) or set(data_range) != expected_range_keys:
        raise ForecastMapContractError("Forecast Map data range is malformed.")
    safe_start = required_date(data_range["safeEventStartDate"], "safe start")
    safe_end = required_date(data_range["safeEventEndDate"], "safe end")
    first_week = required_date(data_range["firstObservedWeek"], "first observed week")
    latest_week = required_date(data_range["latestObservedWeek"], "latest observed week")
    latest_complete = required_date(
        data_range["latestCompleteWeek"], "latest complete week"
    )
    if not (safe_start <= safe_end and first_week <= latest_complete <= latest_week):
        raise ForecastMapContractError("Forecast Map data range ordering is invalid.")
    expected_partial = latest_week + timedelta(days=6) > safe_end
    if data_range["latestWeekIsPartial"] is not expected_partial:
        raise ForecastMapContractError("Forecast Map partial-week metadata is inconsistent.")
    if latest_complete != (
        latest_week - timedelta(weeks=1) if expected_partial else latest_week
    ):
        raise ForecastMapContractError("Forecast Map latest complete week is inconsistent.")
    generated = required_timestamp(payload["generatedAtUtc"], "generatedAtUtc")
    expected_generated = datetime.combine(safe_end, datetime.min.time(), timezone.utc)
    if generated != expected_generated:
        raise ForecastMapContractError(
            "Forecast Map generation metadata is future-dated or not source-derived."
        )

    dimensions = payload["dimensions"]
    if not isinstance(dimensions, dict):
        raise ForecastMapContractError("Forecast Map dimensions must be an object.")
    _validate_sorted_dimensions(dimensions)
    if data_range["supportedForecastWeeks"] != dimensions["forecastWeeks"]:
        raise ForecastMapContractError("Supported forecast weeks do not match dimensions.")
    if len(dimensions["forecastWeeks"]) > 1:
        raise ForecastMapContractError("Only one next-week forecast horizon is supported.")

    forecast = payload["forecast"]
    if not isinstance(forecast, dict) or forecast.get("status") not in FORECAST_STATUSES:
        raise ForecastMapContractError("Forecast availability status is invalid.")
    if forecast.get("rowColumns") != ROW_COLUMNS:
        raise ForecastMapContractError("Forecast row schema is invalid.")
    required_source_filename(forecast.get("sourceFile"), "forecast source file")
    rows = forecast.get("rows")
    if not isinstance(rows, list):
        raise ForecastMapContractError("Forecast rows must be a list.")
    if forecast["status"] != "available":
        if rows or not forecast.get("reason") or forecast.get("isEmpty") is not False:
            raise ForecastMapContractError(
                "Unavailable forecasts require a reason, no rows, and isEmpty=false."
            )
        if any(dimensions[name] for name in DIMENSION_KEYS):
            raise ForecastMapContractError("Unavailable forecast contains dimensions.")
    elif forecast.get("isEmpty") is not (len(rows) == 0):
        raise ForecastMapContractError("Forecast isEmpty flag is inconsistent.")
    if rows:
        if len(dimensions["forecastWeeks"]) != 1:
            raise ForecastMapContractError("Forecast rows require exactly one horizon.")
        expected_forecast = latest_week + timedelta(weeks=1)
        if date.fromisoformat(dimensions["forecastWeeks"][0]) != expected_forecast:
            raise ForecastMapContractError(
                "Forecast horizon is not strictly the next week after observations."
            )
        if generated.date() > expected_forecast:
            raise ForecastMapContractError("Generation metadata is after the forecast horizon.")

    keys: set[tuple[int, int, int, int, int]] = set()
    row_pairs: set[tuple[int, int]] = set()
    prior_sort_key: tuple[int, int, int, int, int] | None = None
    predicted_values: list[int | float] = []
    baseline_available = 0
    change_count_available = 0
    change_pct_available = 0
    zero_baseline = 0
    counts_by_borough = [0] * len(dimensions["boroughs"])
    for row in rows:
        if not isinstance(row, list) or len(row) != len(ROW_COLUMNS):
            raise ForecastMapContractError("Forecast positional row is malformed.")
        indexes = row[:5]
        bounds = [
            len(dimensions["forecastWeeks"]),
            len(dimensions["boroughs"]),
            len(dimensions["precincts"]),
            len(dimensions["offenseTypes"]),
            len(dimensions["lawCategories"]),
        ]
        for index, bound in zip(indexes, bounds):
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or not 0 <= index < bound
            ):
                raise ForecastMapContractError("Forecast dimension index is out of range.")
        key = tuple(indexes)
        if key in keys:
            raise ForecastMapContractError("Forecast payload contains duplicate logical keys.")
        if prior_sort_key is not None and key < prior_sort_key:
            raise ForecastMapContractError("Forecast rows are not in stable sorted order.")
        prior_sort_key = key
        keys.add(key)
        row_pairs.add((indexes[1], indexes[2]))
        counts_by_borough[indexes[1]] += 1
        predicted = required_number(row[5], "published predicted count", minimum=0)
        if predicted != row[5]:
            raise ForecastMapContractError("Published predicted count is not canonically rounded.")
        predicted_values.append(predicted)
        baseline_value = row[6]
        change_value = row[7]
        change_pct_value = row[8]
        precinct = dimensions["precincts"][indexes[2]]
        if row[9] != location_key(precinct):
            raise ForecastMapContractError("Forecast precinct location key is unsafe or inconsistent.")
        if baseline_value is None:
            if change_value is not None or change_pct_value is not None:
                raise ForecastMapContractError(
                    "Missing historical baseline must keep all change fields null."
                )
            continue
        baseline_number = required_number(
            baseline_value, "published historical baseline", minimum=0
        )
        if baseline_number != baseline_value:
            raise ForecastMapContractError("Historical baseline is not canonically rounded.")
        baseline_available += 1
        if change_value is None:
            raise ForecastMapContractError("Expected change count is missing for a baseline.")
        change_number = required_number(change_value, "published expected change count")
        expected_change = required_number(
            float(predicted) - float(baseline_number), "recomputed expected change"
        )
        if not math.isclose(
            float(change_number),
            float(expected_change),
            rel_tol=0,
            abs_tol=ARITHMETIC_TOLERANCE,
        ):
            raise ForecastMapContractError("Expected change count arithmetic is inconsistent.")
        change_count_available += 1
        if float(baseline_number) == 0:
            zero_baseline += 1
            if change_pct_value is not None:
                raise ForecastMapContractError(
                    "Expected change percentage must be null for a zero baseline."
                )
        else:
            if change_pct_value is None:
                raise ForecastMapContractError(
                    "Expected change percentage is missing for a positive baseline."
                )
            pct_number = required_number(
                change_pct_value, "published expected change percentage"
            )
            expected_pct = required_number(
                float(change_number) / float(baseline_number) * 100,
                "recomputed expected change percentage",
            )
            if not math.isclose(
                float(pct_number),
                float(expected_pct),
                rel_tol=0,
                abs_tol=ARITHMETIC_TOLERANCE,
            ):
                raise ForecastMapContractError(
                    "Expected change percentage arithmetic is inconsistent."
                )
            change_pct_available += 1

    _validate_filter_index(payload["filterIndex"], dimensions, row_pairs)
    summary = forecast.get("summary")
    required_summary_keys = {
        "rowCount",
        "sourceRowCount",
        "sourceSegmentCount",
        "modelSegmentCoveragePct",
        "withheldRowCount",
        "withheldReasonCounts",
        "sourcePredictedTotal",
        "predictedTotal",
        "withheldPredictedTotal",
        "rowCoveragePct",
        "predictedVolumeCoveragePct",
        "publishedPrecinctCount",
        "publishedBoroughCount",
        "unknownOffenseRowCount",
        "countsByBorough",
        "zeroPredictionRowCount",
    }
    if not isinstance(summary, dict) or set(summary) != required_summary_keys:
        raise ForecastMapContractError("Forecast summary schema is invalid.")
    if summary["rowCount"] != len(rows):
        raise ForecastMapContractError("Forecast row count does not reconcile.")
    if summary["publishedPrecinctCount"] != len(dimensions["precincts"]) or summary[
        "publishedBoroughCount"
    ] != len(dimensions["boroughs"]):
        raise ForecastMapContractError("Forecast published location counts do not reconcile.")
    if summary["countsByBorough"] != counts_by_borough:
        raise ForecastMapContractError("Forecast borough counts do not reconcile.")
    if summary["zeroPredictionRowCount"] != sum(
        float(value) == 0 for value in predicted_values
    ):
        raise ForecastMapContractError("Forecast zero-prediction count does not reconcile.")
    if summary["unknownOffenseRowCount"] != sum(
        dimensions["offenseTypes"][row[3]].upper() == "UNKNOWN" for row in rows
    ):
        raise ForecastMapContractError("Forecast unknown-offense count does not reconcile.")
    if rows:
        if summary["predictedTotal"] != compact_sum(predicted_values):
            raise ForecastMapContractError("Forecast predicted total does not reconcile.")
    elif summary["predictedTotal"] is not None:
        raise ForecastMapContractError("Empty or unavailable forecast must not publish a zero total.")
    if forecast["status"] == "available":
        source_count = required_number(
            summary["sourceRowCount"], "forecast source row count", minimum=0, integer=True
        )
        withheld_count = required_number(
            summary["withheldRowCount"], "forecast withheld row count", minimum=0, integer=True
        )
        if int(source_count) != len(rows) + int(withheld_count):
            raise ForecastMapContractError("Forecast source/withheld row counts do not reconcile.")
        source_segment_count = required_number(
            summary["sourceSegmentCount"],
            "weekly source segment count",
            minimum=1,
            integer=True,
        )
        expected_model_coverage = compact_pct(source_count, source_segment_count)
        if summary["modelSegmentCoveragePct"] != expected_model_coverage:
            raise ForecastMapContractError("Forecast model segment coverage does not reconcile.")
        if rows and int(source_count) != int(source_segment_count):
            raise ForecastMapContractError(
                "Nonempty forecast does not cover the complete weekly segment universe."
            )
        reasons = summary["withheldReasonCounts"]
        if not isinstance(reasons, dict) or set(reasons) != {
            "unmappableLocation",
            "boroughMismatch",
        }:
            raise ForecastMapContractError("Forecast withholding summary is malformed.")
        if sum(
            int(required_number(value, "withheld reason count", minimum=0, integer=True))
            for value in reasons.values()
        ) != int(withheld_count):
            raise ForecastMapContractError("Forecast withholding reasons do not reconcile.")
        expected_row_coverage = compact_pct(len(rows), int(source_count)) if source_count else None
        if summary["rowCoveragePct"] != expected_row_coverage:
            raise ForecastMapContractError("Forecast row coverage does not reconcile.")
        if rows:
            source_total = required_number(
                summary["sourcePredictedTotal"], "source predicted total", minimum=0
            )
            withheld_total = required_number(
                summary["withheldPredictedTotal"], "withheld predicted total", minimum=0
            )
            if not math.isclose(
                float(source_total),
                float(summary["predictedTotal"]) + float(withheld_total),
                rel_tol=0,
                abs_tol=ARITHMETIC_TOLERANCE,
            ):
                raise ForecastMapContractError("Forecast predicted coverage totals do not reconcile.")
            expected_volume = compact_pct(summary["predictedTotal"], source_total)
            if summary["predictedVolumeCoveragePct"] != expected_volume:
                raise ForecastMapContractError(
                    "Forecast predicted-volume coverage does not reconcile."
                )
        elif any(
            summary[key] is not None
            for key in (
                "sourcePredictedTotal",
                "withheldPredictedTotal",
                "predictedVolumeCoveragePct",
            )
        ):
            raise ForecastMapContractError("Available-empty forecast publishes numeric totals.")
    else:
        if any(
            summary[key] is not None
            for key in (
                "sourceRowCount",
                "sourceSegmentCount",
                "modelSegmentCoveragePct",
                "withheldRowCount",
                "sourcePredictedTotal",
                "withheldPredictedTotal",
                "rowCoveragePct",
                "predictedVolumeCoveragePct",
            )
        ):
            raise ForecastMapContractError("Unavailable forecast publishes source totals.")

    baseline = payload["baseline"]
    if not isinstance(baseline, dict) or baseline.get("status") not in OPTIONAL_STATUSES:
        raise ForecastMapContractError("Baseline availability status is invalid.")
    required_source_filename(baseline.get("sourceFile"), "baseline source file")
    required_source_filename(
        baseline.get("manifestSourceFile"), "baseline manifest source file"
    )
    baseline_summary = baseline.get("summary")
    expected_baseline_summary = {
        "publishedRowCount": len(rows),
        "baselineAvailableRowCount": baseline_available,
        "baselineUnavailableRowCount": len(rows) - baseline_available,
        "expectedChangeCountAvailableRowCount": change_count_available,
        "expectedChangePctAvailableRowCount": change_pct_available,
        "zeroBaselineRowCount": zero_baseline,
    }
    if baseline_summary != expected_baseline_summary:
        raise ForecastMapContractError("Baseline availability summary does not reconcile.")
    if baseline["status"] != "available" and any(row[6] is not None for row in rows):
        raise ForecastMapContractError("Unavailable baseline source publishes baseline values.")
    if baseline["status"] != "available" and not baseline.get("reason"):
        raise ForecastMapContractError("Unavailable baseline source requires a reason.")
    if baseline["status"] == "available" and not (
        isinstance(baseline.get("method"), str)
        and baseline.get("priorOnly") is True
        and isinstance(baseline.get("requiredPriorWeeks"), int)
    ):
        raise ForecastMapContractError("Available baseline metadata is incomplete.")
    expected_value_availability = availability_value(baseline_available, len(rows))
    if baseline.get("valueAvailability") != expected_value_availability:
        raise ForecastMapContractError("Baseline value availability is inconsistent.")

    availability = payload["availability"]
    expected_availability = {
        "forecastPointEstimates": (
            "available"
            if forecast["status"] == "available" and rows
            else "empty"
            if forecast["status"] == "available"
            else forecast["status"]
        ),
        "historicalBaseline": availability_value(baseline_available, len(rows)),
        "expectedChangeCount": availability_value(change_count_available, len(rows)),
        "expectedChangePct": availability_value(change_pct_available, len(rows)),
        "predictionIntervals": "unavailable",
        "precinctSpatialReference": "location-key-only",
    }
    if availability != expected_availability:
        raise ForecastMapContractError("Analytical availability metadata is inconsistent.")

    model = payload["model"]
    if not isinstance(model, dict) or model.get("status") not in OPTIONAL_STATUSES:
        raise ForecastMapContractError("Forecast model status is invalid.")
    expected_model_keys = {
        "status",
        "sourceFile",
        "artifactType",
        "artifactVersion",
        "artifactGeneratedAtUtc",
        "independentTrainingTime",
        "name",
        "version",
        "trainingStartWeek",
        "trainingThroughWeek",
        "forecastWeek",
        "leakageControlsVerified",
        "pointEstimatesOnly",
        "predictionIntervalsAvailable",
        "historicalError",
    }
    if model.get("reason") is not None:
        expected_model_keys.add("reason")
    if set(model) != expected_model_keys:
        raise ForecastMapContractError("Forecast model lifecycle schema is invalid.")
    required_source_filename(model.get("sourceFile"), "model source file")
    if model.get("independentTrainingTime") != INDEPENDENT_TRAINING_TIME:
        raise ForecastMapContractError(
            "Independent training-completion timestamp status is invalid."
        )
    if not (
        model.get("pointEstimatesOnly") is True
        and model.get("predictionIntervalsAvailable") is False
    ):
        raise ForecastMapContractError("Forecast model uncertainty metadata is unsafe.")
    if model["status"] == "available":
        if model.get("reason") is not None:
            raise ForecastMapContractError("Available forecast model has an error reason.")
        if model.get("artifactType") != MODEL_ARTIFACT_TYPE:
            raise ForecastMapContractError("Forecast model artifact type is incompatible.")
        required_number(
            model.get("artifactVersion"),
            "published ML artifact version",
            minimum=1,
            integer=True,
        )
        model_name = required_text(model.get("name"), "published ML model name")
        if not MODEL_NAME_RE.fullmatch(model_name):
            raise ForecastMapContractError("Published ML model name is not browser-safe.")
        required_number(
            model.get("version"),
            "published ML model version",
            minimum=1,
            integer=True,
        )
        training_start = required_date(
            model.get("trainingStartWeek"), "published ML training start"
        )
        training_through = required_date(
            model.get("trainingThroughWeek"), "published ML training end"
        )
        model_forecast_week = required_date(
            model.get("forecastWeek"), "published ML forecast week"
        )
        if not (
            training_start == first_week
            and training_through == latest_week
            and model_forecast_week == latest_week + timedelta(weeks=1)
        ):
            raise ForecastMapContractError(
                "Forecast model lifecycle dates do not match the observation horizon."
            )
        artifact_generated = required_timestamp(
            model.get("artifactGeneratedAtUtc"),
            "published ML artifact generated timestamp",
        )
        if model.get("artifactGeneratedAtUtc") != artifact_generated.isoformat():
            raise ForecastMapContractError(
                "Forecast model artifact timestamp is not canonical UTC."
            )
        if model.get("leakageControlsVerified") is not True:
            raise ForecastMapContractError(
                "Available forecast model lacks verified leakage controls."
            )
    else:
        if not model.get("reason"):
            raise ForecastMapContractError("Unavailable forecast model requires a reason.")
        unavailable_fields = (
            "artifactType",
            "artifactVersion",
            "artifactGeneratedAtUtc",
            "name",
            "version",
            "trainingStartWeek",
            "trainingThroughWeek",
            "forecastWeek",
        )
        if any(model.get(key) is not None for key in unavailable_fields) or (
            model.get("leakageControlsVerified") is not False
        ):
            raise ForecastMapContractError(
                "Unavailable forecast model publishes lifecycle values."
            )
    if rows and not (
        model["status"] == "available"
        and model.get("leakageControlsVerified") is True
        and model.get("pointEstimatesOnly") is True
        and model.get("predictionIntervalsAvailable") is False
        and model.get("forecastWeek") == dimensions["forecastWeeks"][0]
    ):
        raise ForecastMapContractError("Published forecast model metadata is unsafe or misaligned.")
    historical = model.get("historicalError")
    if not isinstance(historical, dict) or historical.get("status") not in {
        "available",
        "missing",
        "invalid",
    }:
        raise ForecastMapContractError("Historical error context status is invalid.")
    required_source_filename(
        historical.get("sourceFile"), "historical error source file"
    )
    if historical["status"] == "available":
        expected_historical_keys = {
            "status",
            "sourceFile",
            "mae",
            "rmse",
            "weightedMae",
            "predictionCoveragePct",
            "backtestRowCount",
            "backtestStartWeek",
            "backtestEndWeek",
            "unit",
            "scope",
            "filterSemantics",
        }
        if set(historical) != expected_historical_keys:
            raise ForecastMapContractError("Historical error context schema is invalid.")
        for key in ("mae", "rmse", "predictionCoveragePct"):
            required_number(
                historical.get(key),
                f"historical error {key}",
                minimum=0,
                maximum=100 if key == "predictionCoveragePct" else None,
            )
        optional_number(historical.get("weightedMae"), "historical weighted MAE", minimum=0)
        backtest_rows = required_number(
            historical.get("backtestRowCount"),
            "historical backtest row count",
            minimum=1,
            integer=True,
        )
        backtest_start = required_date(
            historical.get("backtestStartWeek"), "historical backtest start"
        )
        backtest_end = required_date(
            historical.get("backtestEndWeek"), "historical backtest end"
        )
        if (
            backtest_rows < 1
            or backtest_start.weekday() != 0
            or backtest_end.weekday() != 0
            or not first_week <= backtest_start <= backtest_end
            or backtest_end != latest_complete
        ):
            raise ForecastMapContractError("Historical backtest range is inconsistent.")
        for key in ("unit", "scope", "filterSemantics"):
            required_text(historical.get(key), f"historical error {key}")
    else:
        if set(historical) != {"status", "sourceFile", "reason"}:
            raise ForecastMapContractError("Unavailable historical error schema is invalid.")
        required_text(historical.get("reason"), "unavailable historical error reason")

    location = payload["locationKeySemantics"]
    if not isinstance(location, dict) or not (
        location.get("stableJoinKeyOnly") is True
        and location.get("spatialReferenceAvailable") is False
        and location.get("coordinatesIncluded") is False
        and location.get("geometryIncluded") is False
    ):
        raise ForecastMapContractError("Location-key semantics are unsafe.")
    privacy = payload["privacy"]
    expected_privacy = {
        "aggregateOnly": True,
        "eventRecordsIncluded": False,
        "complaintIdentifiersIncluded": False,
        "sourceRowIdentifiersIncluded": False,
        "namesIncluded": False,
        "exactAddressesIncluded": False,
        "eventLevelCoordinatesIncluded": False,
        "demographicAttributesIncluded": False,
    }
    if privacy != expected_privacy:
        raise ForecastMapContractError("Forecast Map privacy flags are absent or unsafe.")
    expected_ethics = {
        "aggregateReportedEventVolumeOnly": True,
        "individualBehaviorPrediction": False,
        "specificIncidentLocationPrediction": False,
        "personLevelScoring": False,
        "patrolRecommendations": False,
        "enforcementRecommendations": False,
    }
    if payload["ethics"] != expected_ethics:
        raise ForecastMapContractError("Forecast Map ethics flags are absent or unsafe.")

    provenance = payload["provenance"]
    expected_provenance = {
        "weeklyAggregate",
        "overview",
        "mlPredictions",
        "mlManifest",
        "mlMetrics",
        "baselinePredictions",
        "baselineManifest",
    }
    if not isinstance(provenance, dict) or set(provenance) != expected_provenance:
        raise ForecastMapContractError("Forecast Map provenance is not tightly allowlisted.")
    for item in provenance.values():
        if not isinstance(item, dict) or set(item) != {
            "status",
            "sourceFile",
            "publishedUse",
        }:
            raise ForecastMapContractError("Forecast Map provenance entry is malformed.")
        if item["status"] not in OPTIONAL_STATUSES:
            raise ForecastMapContractError("Forecast Map provenance status is invalid.")
        required_source_filename(item["sourceFile"], "provenance source file")

    serialized = json.dumps(payload, allow_nan=False).upper()
    forbidden_tokens = [
        "COMPLAINT_NUMBER",
        "CMPLNT_NUM",
        "SOURCE_ROW_ID",
        "VIC_RACE",
        "VIC_SEX",
        "VIC_AGE_GROUP",
        "SUSP_RACE",
        "SUSP_SEX",
        "SUSP_AGE_GROUP",
        "EVENT_LATITUDE",
        "EVENT_LONGITUDE",
    ]
    leaked = [token for token in forbidden_tokens if token in serialized]
    if leaked:
        raise ForecastMapContractError(
            f"Forecast Map payload contains unsafe source fields: {leaked}."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the aggregate-only Phase 7C.1 Forecast Map data contract."
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--processed-dir", type=Path, default=None)
    parser.add_argument("--dashboard-data-dir", type=Path, default=None)
    parser.add_argument("--weekly-area", type=Path, default=None)
    parser.add_argument("--overview", type=Path, default=None)
    parser.add_argument("--ml-predictions", type=Path, default=None)
    parser.add_argument("--ml-metrics", type=Path, default=None)
    parser.add_argument("--ml-manifest", type=Path, default=None)
    parser.add_argument("--baseline-predictions", type=Path, default=None)
    parser.add_argument("--baseline-manifest", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--skip-dashboard-copy",
        action="store_true",
        help=(
            "Write the canonical processed output without copying forecast-map.json "
            "to dashboard/public/data."
        ),
    )
    parser.add_argument(
        "--threads", type=int, default=max(1, min(4, os.cpu_count() or 1))
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = args.project_root.resolve()
    processed_dir = resolve_path(project_root, args.processed_dir, DEFAULT_PROCESSED_DIR)
    dashboard_data_dir = resolve_path(
        project_root, args.dashboard_data_dir, DEFAULT_DASHBOARD_DATA_DIR
    )
    output_path = resolve_path(
        project_root,
        args.output,
        processed_dir / PROCESSED_FORECAST_MAP_FILE,
    )
    input_paths = [
        resolve_path(project_root, args.weekly_area, processed_dir / WEEKLY_FILE),
        resolve_path(project_root, args.overview, processed_dir / OVERVIEW_FILE),
        resolve_path(
            project_root, args.ml_predictions, processed_dir / ML_PREDICTIONS_FILE
        ),
        resolve_path(project_root, args.ml_metrics, processed_dir / ML_METRICS_FILE),
        resolve_path(
            project_root, args.ml_manifest, DEFAULT_MODEL_DIR / MODEL_MANIFEST_FILE
        ),
        resolve_path(
            project_root,
            args.baseline_predictions,
            processed_dir / BASELINE_PREDICTIONS_FILE,
        ),
        resolve_path(
            project_root,
            args.baseline_manifest,
            DEFAULT_BASELINE_MODEL_DIR / MODEL_MANIFEST_FILE,
        ),
    ]
    frontend_path = dashboard_data_dir / FORECAST_MAP_FILE
    ensure_output_does_not_overwrite_inputs(output_path, input_paths)
    if not args.skip_dashboard_copy:
        ensure_output_does_not_overwrite_inputs(frontend_path, input_paths)
    payload = build_dashboard_forecast_map(
        weekly_path=input_paths[0],
        overview_path=input_paths[1],
        ml_predictions_path=input_paths[2],
        ml_metrics_path=input_paths[3],
        ml_manifest_path=input_paths[4],
        baseline_predictions_path=input_paths[5],
        baseline_manifest_path=input_paths[6],
        output_path=output_path,
        threads=args.threads,
    )
    if not args.skip_dashboard_copy:
        dashboard_data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output_path, frontend_path)
    summary = payload["forecast"]["summary"]
    print(
        "Built Phase 7C.1 Forecast Map data: "
        f"{summary['rowCount']:,} published aggregate forecast rows "
        f"({payload['forecast']['status']})."
    )
    print(f"Canonical forecast map data: {output_path}")
    if not args.skip_dashboard_copy:
        print(f"Frontend forecast map data: {frontend_path}")


if __name__ == "__main__":
    main()

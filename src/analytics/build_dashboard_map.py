#!/usr/bin/env python3
"""Build the compact, aggregate-safe Phase 7B Map data contract.

Only aggregate-safe date/count statistics are read from the cleaned event table.
Hotspots are optional and are published as indexed aggregate rows; complaint-level
records and demographic attributes are never written to the browser contract.

Run from the repository root:

    .venv/bin/python src/analytics/build_dashboard_map.py
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any


DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_DASHBOARD_DATA_DIR = Path("dashboard/public/data")
CLEAN_EVENTS_FILE = "complaints_clean.parquet"
HOTSPOTS_FILE = "hotspots.parquet"
HOTSPOT_METRICS_FILE = "hotspot_metrics.json"
PROCESSED_MAP_FILE = "dashboard_map.json"
MAP_FILE = "map.json"
SCHEMA_VERSION = "1.0.0"
CURRENT_MAX_AGE_DAYS = 1

NYC_LAT_MIN = 40.4774
NYC_LAT_MAX = 40.9176
NYC_LON_MIN = -74.2591
NYC_LON_MAX = -73.7004

CLEAN_REQUIRED_COLUMNS = ["complaint_from_date", "is_clean_event_for_aggregate"]
HOTSPOT_REQUIRED_COLUMNS = [
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
    "recent_window_days",
    "baseline_window_days",
    "scoring_end_date",
    "recent_event_count",
    "baseline_expected_recent_count",
    "recent_vs_baseline_lift_pct",
    "composite_score",
    "coordinate_coverage_pct",
    "is_hotspot",
    "hotspot_severity",
]
HOTSPOT_ROW_COLUMNS = [
    "rank",
    "grainIndex",
    "boroughIndex",
    "precinctIndex",
    "offenseTypeIndex",
    "lawCategoryIndex",
    "latitude",
    "longitude",
    "locationLabel",
    "recentCount",
    "expectedRecentCount",
    "liftPct",
    "score",
    "severityIndex",
    "coordinateCoveragePct",
]
DIMENSION_KEYS = [
    "hotspotGrains",
    "boroughs",
    "precincts",
    "offenseTypes",
    "lawCategories",
    "severities",
]
SEVERITIES = {"low", "medium", "high", "critical"}
GRAINS = {"grid", "precinct"}
SENSITIVE_COLUMNS = [
    "SUSP_AGE_GROUP",
    "SUSP_RACE",
    "SUSP_SEX",
    "VIC_AGE_GROUP",
    "VIC_RACE",
    "VIC_SEX",
]


class MapContractError(ValueError):
    """An optional Map input cannot be safely represented in the contract."""


def require_duckdb() -> Any:
    try:
        import duckdb  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment failure
        raise SystemExit(
            "Missing dependency: duckdb. Run in the repository virtual environment."
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


def require_clean_input(con: Any, path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required clean events input not found: {path}")
    columns = {column.lower() for column in parquet_columns(con, path)}
    missing = sorted(set(CLEAN_REQUIRED_COLUMNS).difference(columns))
    if missing:
        raise ValueError(f"Clean events input is missing required columns: {missing}")


def required_text(value: Any, label: str) -> str:
    if value is None or not str(value).strip():
        raise MapContractError(f"Missing required text field: {label}.")
    return str(value).strip()


def required_date(value: Any, label: str) -> str:
    if isinstance(value, datetime):
        value = value.date()
    text = value.isoformat() if isinstance(value, date) else str(value or "").strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise MapContractError(f"Invalid required date field: {label}.") from exc


def required_number(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    integer: bool = False,
) -> int | float:
    if value is None or isinstance(value, bool):
        raise MapContractError(f"Invalid required numeric field: {label}.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MapContractError(f"Invalid required numeric field: {label}.") from exc
    if not math.isfinite(number):
        raise MapContractError(f"Invalid required numeric field: {label}.")
    if minimum is not None and number < minimum:
        raise MapContractError(f"Invalid required numeric field: {label}.")
    if maximum is not None and number > maximum:
        raise MapContractError(f"Invalid required numeric field: {label}.")
    if integer:
        if not number.is_integer():
            raise MapContractError(f"Invalid required integer field: {label}.")
        return int(number)
    rounded = round(number, 6)
    return int(rounded) if rounded.is_integer() else rounded


def aggregate_safe_stats(con: Any, clean_path: Path) -> dict[str, Any]:
    require_clean_input(con, clean_path)
    stats = fetch_dicts(
        con,
        f"""
        SELECT
            COUNT(*)::BIGINT AS source_count,
            COUNT(*) FILTER (
                WHERE is_clean_event_for_aggregate IS TRUE
            )::BIGINT AS safe_count,
            COUNT(*) FILTER (
                WHERE is_clean_event_for_aggregate IS TRUE
                  AND complaint_from_date IS NULL
            )::BIGINT AS safe_missing_date_count,
            MIN(complaint_from_date) FILTER (
                WHERE is_clean_event_for_aggregate IS TRUE
            ) AS safe_start_date,
            MAX(complaint_from_date) FILTER (
                WHERE is_clean_event_for_aggregate IS TRUE
            ) AS safe_end_date
        FROM read_parquet({sql_string(clean_path)})
        """,
    )[0]
    if int(stats["safe_count"]) <= 0:
        raise ValueError("Clean events input contains no aggregate-safe rows.")
    if int(stats["safe_missing_date_count"]):
        raise ValueError("Aggregate-safe cleaned events contain missing complaint dates.")
    start = date.fromisoformat(required_date(stats["safe_start_date"], "safe start date"))
    end = date.fromisoformat(required_date(stats["safe_end_date"], "safe end date"))
    if start > end:
        raise ValueError("Aggregate-safe event date range is invalid.")
    return {
        "sourceCount": int(stats["source_count"]),
        "safeCount": int(stats["safe_count"]),
        "startDate": start,
        "endDate": end,
    }


def _unsafe_hotspot_columns(columns: list[str]) -> list[str]:
    unsafe: list[str] = []
    exact = {
        "source_row_id",
        "complaint_id",
        "complaint_number",
        "cmplnt_num",
        "person_id",
        "first_name",
        "last_name",
        "full_name",
    }
    for column in columns:
        lowered = column.lower()
        if (
            lowered in exact
            or lowered.startswith(("susp_", "vic_", "suspect_", "victim_"))
        ):
            unsafe.append(column)
    return sorted(unsafe)


def _empty_source(path: Path, status: str, reason: str | None = None) -> dict[str, Any]:
    source: dict[str, Any] = {
        "status": status,
        "sourceFile": path.name,
        "records": [],
        "scoringEndDate": None,
        "snapshotAgeDays": None,
        "recentWindowDays": None,
        "baselineWindowDays": None,
    }
    if reason is None and status == "missing":
        reason = (
            "Hotspot input is unavailable; no current aggregate snapshot can be displayed."
        )
    if reason:
        source["reason"] = reason
    return source


def _invalid_source(path: Path, reason: str) -> dict[str, Any]:
    return _empty_source(path, "invalid", reason)


def load_hotspots(
    con: Any, path: Path, safe_end_date: date
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return the publishable source plus validated rows used for methodology checks."""
    if not path.exists():
        return _empty_source(path, "missing"), []
    try:
        columns = parquet_columns(con, path)
        unsafe = _unsafe_hotspot_columns(columns)
        if unsafe:
            raise MapContractError(
                "Hotspot input contains unsafe event-level or demographic columns."
            )
        lowered = {column.lower() for column in columns}
        missing = sorted(set(HOTSPOT_REQUIRED_COLUMNS).difference(lowered))
        if missing:
            raise MapContractError(f"Missing required columns: {missing}")

        stats = fetch_dicts(
            con,
            f"""
            SELECT
                COUNT(*)::BIGINT AS row_count,
                COUNT(*) FILTER (WHERE is_hotspot IS DISTINCT FROM TRUE)::BIGINT
                    AS unsafe_rows,
                COUNT(*) FILTER (WHERE scoring_end_date IS NULL)::BIGINT AS null_dates,
                COUNT(DISTINCT scoring_end_date)::BIGINT AS distinct_dates,
                MIN(scoring_end_date) AS min_date,
                MAX(scoring_end_date) AS max_date,
                COUNT(*) FILTER (WHERE recent_window_days IS NULL)::BIGINT
                    AS null_recent_windows,
                COUNT(DISTINCT recent_window_days)::BIGINT AS distinct_recent_windows,
                MIN(recent_window_days) AS recent_window_days,
                COUNT(*) FILTER (WHERE baseline_window_days IS NULL)::BIGINT
                    AS null_baseline_windows,
                COUNT(DISTINCT baseline_window_days)::BIGINT AS distinct_baseline_windows,
                MIN(baseline_window_days) AS baseline_window_days
            FROM read_parquet({sql_string(path)})
            """,
        )[0]
        row_count = int(stats["row_count"])
        if row_count == 0:
            return _empty_source(path, "available"), []
        if int(stats["unsafe_rows"]):
            raise MapContractError(
                "Hotspot input contains rows not explicitly marked is_hotspot = true."
            )
        if int(stats["null_dates"]):
            raise MapContractError("Hotspot snapshot contains a missing scoring date.")
        if int(stats["distinct_dates"]) != 1:
            raise MapContractError(
                "Hotspot input must contain exactly one scoring snapshot date."
            )
        if int(stats["null_recent_windows"]) or int(stats["distinct_recent_windows"]) != 1:
            raise MapContractError("Hotspot rows must share one non-null recent window.")
        if int(stats["null_baseline_windows"]) or int(stats["distinct_baseline_windows"]) != 1:
            raise MapContractError("Hotspot rows must share one non-null baseline window.")

        scoring_text = required_date(stats["max_date"], "hotspot scoring_end_date")
        scoring_date = date.fromisoformat(scoring_text)
        recent_window = int(
            required_number(
                stats["recent_window_days"],
                "hotspot recent_window_days",
                minimum=1,
                integer=True,
            )
        )
        baseline_window = int(
            required_number(
                stats["baseline_window_days"],
                "hotspot baseline_window_days",
                minimum=1,
                integer=True,
            )
        )
        if scoring_date > safe_end_date:
            raise MapContractError(
                "Hotspot snapshot date cannot exceed the maximum aggregate-safe event date."
            )
        snapshot_age_days = (safe_end_date - scoring_date).days

        rows = fetch_dicts(
            con,
            f"""
            SELECT
                rank_overall,
                lower(trim(CAST(hotspot_grain AS VARCHAR))) AS grain,
                trim(CAST(borough AS VARCHAR)) AS borough,
                CASE WHEN precinct IS NULL THEN NULL
                     ELSE trim(CAST(precinct AS VARCHAR)) END AS precinct,
                grid_latitude,
                grid_longitude,
                trim(CAST(offense_type AS VARCHAR)) AS offense_type,
                trim(CAST(law_category AS VARCHAR)) AS law_category,
                map_latitude,
                map_longitude,
                recent_window_days,
                baseline_window_days,
                scoring_end_date,
                recent_event_count,
                baseline_expected_recent_count,
                recent_vs_baseline_lift_pct,
                composite_score,
                coordinate_coverage_pct,
                lower(trim(CAST(hotspot_severity AS VARCHAR))) AS severity
            FROM read_parquet({sql_string(path)})
            WHERE is_hotspot IS TRUE
            ORDER BY rank_overall, hotspot_grain, borough, precinct NULLS LAST,
                     grid_latitude NULLS LAST, grid_longitude NULLS LAST,
                     offense_type, law_category
            """,
        )
        records: list[dict[str, Any]] = []
        logical_keys: set[tuple[Any, ...]] = set()
        ranks: set[int] = set()
        precinct_boroughs: dict[str, str] = {}
        for row in rows:
            rank = int(
                required_number(
                    row["rank_overall"], "hotspot rank_overall", minimum=1, integer=True
                )
            )
            if rank in ranks:
                raise MapContractError("Duplicate hotspot rank detected.")
            ranks.add(rank)
            grain = required_text(row["grain"], "hotspot hotspot_grain").lower()
            if grain not in GRAINS:
                raise MapContractError("Unsupported hotspot grain.")
            borough = required_text(row["borough"], "hotspot borough")
            offense = required_text(row["offense_type"], "hotspot offense_type")
            law = required_text(row["law_category"], "hotspot law_category")
            severity = required_text(row["severity"], "hotspot hotspot_severity").lower()
            if severity not in SEVERITIES:
                raise MapContractError("Unsupported hotspot severity.")
            precinct = None if row["precinct"] is None else required_text(
                row["precinct"], "hotspot precinct"
            )
            latitude = float(
                required_number(
                    row["map_latitude"],
                    "hotspot map_latitude",
                    minimum=NYC_LAT_MIN,
                    maximum=NYC_LAT_MAX,
                )
            )
            longitude = float(
                required_number(
                    row["map_longitude"],
                    "hotspot map_longitude",
                    minimum=NYC_LON_MIN,
                    maximum=NYC_LON_MAX,
                )
            )
            grid_latitude: float | None = None
            grid_longitude: float | None = None
            if grain == "grid":
                if precinct is not None:
                    raise MapContractError("Grid hotspot must not contain a precinct identifier.")
                grid_latitude = float(
                    required_number(
                        row["grid_latitude"],
                        "hotspot grid_latitude",
                        minimum=NYC_LAT_MIN,
                        maximum=NYC_LAT_MAX,
                    )
                )
                grid_longitude = float(
                    required_number(
                        row["grid_longitude"],
                        "hotspot grid_longitude",
                        minimum=NYC_LON_MIN,
                        maximum=NYC_LON_MAX,
                    )
                )
                if abs(latitude - grid_latitude) > 1e-7 or abs(longitude - grid_longitude) > 1e-7:
                    raise MapContractError(
                        "Grid hotspot map coordinates must equal its aggregate grid center."
                    )
                location_label = f"GRID {latitude:.4f}, {longitude:.4f} · {borough}"
                location_key: Any = (round(grid_latitude, 7), round(grid_longitude, 7))
            else:
                if precinct is None:
                    raise MapContractError(
                        "Precinct hotspot is missing its aggregate precinct identifier."
                    )
                if row["grid_latitude"] is not None or row["grid_longitude"] is not None:
                    raise MapContractError("Precinct hotspot must not contain grid coordinates.")
                known_borough = precinct_boroughs.setdefault(precinct, borough)
                if known_borough != borough:
                    raise MapContractError(
                        "A precinct is associated with multiple boroughs in the hotspot snapshot."
                    )
                location_label = f"PRECINCT {precinct} · {borough}"
                location_key = precinct

            record_date = required_date(row["scoring_end_date"], "hotspot scoring_end_date")
            if record_date != scoring_text:
                raise MapContractError("Hotspot rows do not share the declared scoring date.")
            row_recent_window = int(
                required_number(
                    row["recent_window_days"],
                    "hotspot recent_window_days",
                    minimum=1,
                    integer=True,
                )
            )
            row_baseline_window = int(
                required_number(
                    row["baseline_window_days"],
                    "hotspot baseline_window_days",
                    minimum=1,
                    integer=True,
                )
            )
            if row_recent_window != recent_window or row_baseline_window != baseline_window:
                raise MapContractError("Hotspot row windows do not match snapshot metadata.")
            logical_key = (grain, borough, location_key, offense, law)
            if logical_key in logical_keys:
                raise MapContractError("Duplicate hotspot logical key detected.")
            logical_keys.add(logical_key)
            records.append(
                {
                    "rank": rank,
                    "grain": grain,
                    "borough": borough,
                    "precinct": precinct,
                    "gridLatitude": grid_latitude,
                    "gridLongitude": grid_longitude,
                    "offenseType": offense,
                    "lawCategory": law,
                    "latitude": required_number(latitude, "hotspot map_latitude"),
                    "longitude": required_number(longitude, "hotspot map_longitude"),
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
                        maximum=100,
                    ),
                    "severity": severity,
                    "coordinateCoveragePct": required_number(
                        row["coordinate_coverage_pct"],
                        "hotspot coordinate_coverage_pct",
                        minimum=0,
                        maximum=100,
                    ),
                }
            )

        records.sort(
            key=lambda item: (
                item["rank"],
                item["grain"],
                item["borough"],
                item["precinct"] or "",
                item["gridLatitude"] if item["gridLatitude"] is not None else -999.0,
                item["gridLongitude"] if item["gridLongitude"] is not None else -999.0,
                item["offenseType"],
                item["lawCategory"],
            )
        )
        common = {
            "sourceFile": path.name,
            "scoringEndDate": scoring_text,
            "snapshotAgeDays": snapshot_age_days,
            "recentWindowDays": recent_window,
            "baselineWindowDays": baseline_window,
        }
        if snapshot_age_days > CURRENT_MAX_AGE_DAYS:
            source = {
                "status": "stale",
                "reason": (
                    f"Hotspot snapshot is {snapshot_age_days} days older than the maximum "
                    f"aggregate-safe event date; current snapshots may be at most "
                    f"{CURRENT_MAX_AGE_DAYS} day old."
                ),
                "records": [],
                **common,
            }
            return source, records
        return {"status": "available", "records": records, **common}, records
    except MapContractError as exc:
        return _invalid_source(path, str(exc)), []
    except Exception as exc:  # optional input cannot break the required shell contract
        return _invalid_source(
            path, f"{type(exc).__name__}: hotspot input could not be safely read"
        ), []


def _grid_size_matches(records: list[dict[str, Any]], size: float) -> bool:
    grid_rows = [record for record in records if record["grain"] == "grid"]
    if not grid_rows:
        return False
    tolerance = 1e-5
    for record in grid_rows:
        for coordinate in (record["gridLatitude"], record["gridLongitude"]):
            centered_index = float(coordinate) / size - 0.5
            if abs(centered_index - round(centered_index)) > tolerance:
                return False
    return True


def load_methodology(
    path: Path,
    validated_records: list[dict[str, Any]],
    hotspot_source: dict[str, Any],
) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "sourceFile": path.name}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise MapContractError("Methodology JSON root must be an object.")
        config = data.get("hotspot_config")
        if not isinstance(config, dict):
            raise MapContractError("Methodology is missing hotspot_config.")
        grid_size = float(
            required_number(
                config.get("grid_size_degrees"),
                "methodology grid_size_degrees",
                minimum=0.000001,
                maximum=1,
            )
        )
        analysis = data.get("analysis_window")
        if analysis is not None and not isinstance(analysis, dict):
            raise MapContractError("Methodology analysis_window must be an object.")
        if isinstance(analysis, dict) and hotspot_source.get("scoringEndDate") is not None:
            comparisons = (
                ("scoring_end_date", "scoringEndDate", required_date),
                ("recent_window_days", "recentWindowDays", None),
                ("baseline_window_days", "baselineWindowDays", None),
            )
            for metric_key, source_key, date_validator in comparisons:
                if metric_key not in analysis:
                    continue
                actual = (
                    date_validator(analysis[metric_key], f"methodology {metric_key}")
                    if date_validator
                    else required_number(
                        analysis[metric_key],
                        f"methodology {metric_key}",
                        minimum=1,
                        integer=True,
                    )
                )
                if actual != hotspot_source[source_key]:
                    raise MapContractError(
                        "Methodology analysis window does not match the hotspot snapshot."
                    )
        verified = _grid_size_matches(validated_records, grid_size)
        result: dict[str, Any] = {
            "status": "available",
            "sourceFile": path.name,
            "gridSizeVerified": verified,
            "expectedRecentCountDefinition": (
                "Normalized historical reference scaled to the common recent window, "
                "as supplied by the aggregate hotspot artifact."
            ),
        }
        if verified:
            result["gridSizeDegrees"] = required_number(
                grid_size, "methodology grid_size_degrees"
            )
        return result
    except Exception as exc:  # optional methodology must never break valid hotspots
        reason = (
            str(exc)
            if isinstance(exc, MapContractError)
            else f"{type(exc).__name__}: methodology metadata could not be read"
        )
        return {
            "status": "invalid",
            "sourceFile": path.name,
            "reason": reason,
        }


def build_dimensions(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "hotspotGrains": sorted({record["grain"] for record in records}),
        "boroughs": sorted({record["borough"] for record in records}),
        "precincts": sorted(
            {record["precinct"] for record in records if record["precinct"] is not None}
        ),
        "offenseTypes": sorted({record["offenseType"] for record in records}),
        "lawCategories": sorted({record["lawCategory"] for record in records}),
        "severities": sorted({record["severity"] for record in records}),
    }


def index_hotspots(
    source: dict[str, Any], dimensions: dict[str, list[str]], grid_size: int | float | None
) -> dict[str, Any]:
    indexes = {
        key: {value: index for index, value in enumerate(values)}
        for key, values in dimensions.items()
    }
    rows: list[list[Any]] = []
    for record in source["records"]:
        rows.append(
            [
                record["rank"],
                indexes["hotspotGrains"][record["grain"]],
                indexes["boroughs"][record["borough"]],
                None
                if record["precinct"] is None
                else indexes["precincts"][record["precinct"]],
                indexes["offenseTypes"][record["offenseType"]],
                indexes["lawCategories"][record["lawCategory"]],
                record["latitude"],
                record["longitude"],
                record["locationLabel"],
                record["recentCount"],
                record["expectedRecentCount"],
                record["liftPct"],
                record["score"],
                indexes["severities"][record["severity"]],
                record["coordinateCoveragePct"],
            ]
        )
    by_grain = [0] * len(dimensions["hotspotGrains"])
    by_severity = [0] * len(dimensions["severities"])
    for row in rows:
        by_grain[row[1]] += 1
        by_severity[row[13]] += 1
    result: dict[str, Any] = {
        "status": source["status"],
        "sourceFile": source["sourceFile"],
        "rowColumns": HOTSPOT_ROW_COLUMNS,
        "rows": rows,
        "summary": {
            "rowCount": len(rows),
            "scoringEndDate": source.get("scoringEndDate"),
            "snapshotAgeDays": source.get("snapshotAgeDays"),
            "currentMaxAgeDays": CURRENT_MAX_AGE_DAYS,
            "recentWindowDays": source.get("recentWindowDays"),
            "baselineWindowDays": source.get("baselineWindowDays"),
            "gridSizeDegrees": grid_size,
            "counts": {
                "byGrain": by_grain,
                "bySeverity": by_severity,
            },
        },
    }
    if source.get("reason"):
        result["reason"] = source["reason"]
    return result


def build_filter_index(
    records: list[dict[str, Any]], dimensions: dict[str, list[str]]
) -> dict[str, Any]:
    borough_indexes = {value: index for index, value in enumerate(dimensions["boroughs"])}
    precinct_indexes = {value: index for index, value in enumerate(dimensions["precincts"])}
    by_borough: dict[str, set[str]] = {
        borough: set() for borough in dimensions["boroughs"]
    }
    for record in records:
        if record["precinct"] is not None:
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
                "Precinct choices are constrained to aggregate precinct-grain hotspot "
                "records in the current validated snapshot."
            ),
        }
    }


def validate_map_payload(payload: dict[str, Any]) -> None:
    required = {
        "schemaVersion",
        "generatedAtUtc",
        "application",
        "dataRange",
        "dimensions",
        "filterIndex",
        "hotspots",
        "methodology",
        "provenance",
        "filterSemantics",
        "dateSemantics",
        "grainSemantics",
        "coordinateSemantics",
        "limitations",
        "ethics",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"Map payload is missing required sections: {missing}")
    if payload["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError("Unexpected Map schema version.")
    dimensions = payload["dimensions"]
    if set(dimensions) != set(DIMENSION_KEYS):
        raise ValueError("Map dimensions do not match the required schema.")
    for name, values in dimensions.items():
        if not isinstance(values, list) or values != sorted(values):
            raise ValueError(f"Map dimension {name} must be a sorted list.")
        if len(values) != len(set(values)) or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise ValueError(f"Map dimension {name} contains invalid values.")
    if not set(dimensions["hotspotGrains"]).issubset(GRAINS):
        raise ValueError("Map grain dimension contains an unsupported value.")
    if not set(dimensions["severities"]).issubset(SEVERITIES):
        raise ValueError("Map severity dimension contains an unsupported value.")
    hotspots = payload["hotspots"]
    if hotspots["status"] not in {"available", "missing", "invalid", "stale"}:
        raise ValueError("Invalid Map hotspot status.")
    if hotspots["rowColumns"] != HOTSPOT_ROW_COLUMNS:
        raise ValueError("Unexpected Map hotspot row schema.")
    if hotspots["status"] != "available" and hotspots["rows"]:
        raise ValueError("Unavailable Map hotspot source contains rows.")
    if hotspots["status"] != "available" and not hotspots.get("reason"):
        raise ValueError("Unavailable Map hotspot source requires a reason.")
    if hotspots["summary"]["rowCount"] != len(hotspots["rows"]):
        raise ValueError("Map hotspot row count does not reconcile.")
    summary = hotspots["summary"]
    required_summary = {
        "rowCount",
        "scoringEndDate",
        "snapshotAgeDays",
        "currentMaxAgeDays",
        "recentWindowDays",
        "baselineWindowDays",
        "gridSizeDegrees",
        "counts",
    }
    if set(summary) != required_summary or summary["currentMaxAgeDays"] != CURRENT_MAX_AGE_DAYS:
        raise ValueError("Map hotspot summary schema is invalid.")
    counts = summary["counts"]
    if not isinstance(counts, dict) or set(counts) != {"byGrain", "bySeverity"}:
        raise ValueError("Map hotspot summary counts are invalid.")
    if len(counts["byGrain"]) != len(dimensions["hotspotGrains"]):
        raise ValueError("Map grain summary count width is invalid.")
    if len(counts["bySeverity"]) != len(dimensions["severities"]):
        raise ValueError("Map severity summary count width is invalid.")
    if (
        any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts["byGrain"])
        or any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts["bySeverity"])
        or sum(counts["byGrain"]) != len(hotspots["rows"])
        or sum(counts["bySeverity"]) != len(hotspots["rows"])
    ):
        raise ValueError("Map hotspot summary counts do not reconcile.")
    ranks: list[int] = []
    logical_keys: set[tuple[Any, ...]] = set()
    for row in hotspots["rows"]:
        if len(row) != len(HOTSPOT_ROW_COLUMNS):
            raise ValueError("Map hotspot row width is invalid.")
        for position, dimension_name in (
            (1, "hotspotGrains"),
            (2, "boroughs"),
            (4, "offenseTypes"),
            (5, "lawCategories"),
            (13, "severities"),
        ):
            index = row[position]
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or not 0 <= index < len(dimensions[dimension_name])
            ):
                raise ValueError(f"Map hotspot {dimension_name} index is invalid.")
        rank = row[0]
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            raise ValueError("Map hotspot rank is invalid.")
        ranks.append(rank)
        grain = dimensions["hotspotGrains"][row[1]]
        if (grain == "grid") != (row[3] is None):
            raise ValueError("Map hotspot precinct index does not match its grain.")
        if row[3] is not None and (
            not isinstance(row[3], int)
            or isinstance(row[3], bool)
            or not 0 <= row[3] < len(dimensions["precincts"])
        ):
            raise ValueError("Map hotspot precinct index is invalid.")
        numeric_positions = (6, 7, 9, 10, 11, 12, 14)
        if any(
            isinstance(row[position], bool)
            or not isinstance(row[position], (int, float))
            or not math.isfinite(float(row[position]))
            for position in numeric_positions
        ):
            raise ValueError("Map hotspot row contains an invalid numeric value.")
        if not NYC_LAT_MIN <= float(row[6]) <= NYC_LAT_MAX or not NYC_LON_MIN <= float(row[7]) <= NYC_LON_MAX:
            raise ValueError("Map hotspot coordinates are outside broad NYC bounds.")
        if (
            not isinstance(row[9], int)
            or isinstance(row[9], bool)
            or row[9] < 0
            or float(row[10]) < 0
            or not 0 <= float(row[12]) <= 100
            or not 0 <= float(row[14]) <= 100
        ):
            raise ValueError("Map hotspot numeric constraints are invalid.")
        if not isinstance(row[8], str) or not row[8].strip():
            raise ValueError("Map hotspot location label is invalid.")
        location_key: Any = (
            (round(float(row[6]), 7), round(float(row[7]), 7))
            if grain == "grid"
            else row[3]
        )
        logical_key = (row[1], row[2], location_key, row[4], row[5])
        if logical_key in logical_keys:
            raise ValueError("Duplicate indexed hotspot logical key detected.")
        logical_keys.add(logical_key)
    if ranks != sorted(ranks) or len(ranks) != len(set(ranks)):
        raise ValueError("Map hotspot ranks must be unique and deterministically ordered.")
    if payload["methodology"]["status"] not in {"available", "missing", "invalid"}:
        raise ValueError("Invalid Map methodology status.")
    serialized = json.dumps(payload, allow_nan=False).upper()
    leaked = [column for column in SENSITIVE_COLUMNS if column in serialized]
    if leaked:
        raise ValueError(f"Sensitive demographic fields leaked into Map payload: {leaked}")
    for forbidden in ("COMPLAINT_NUMBER", "SOURCE_ROW_ID", "PRIVATE-VALUE"):
        if forbidden in serialized:
            raise ValueError(f"Event-level value leaked into Map payload: {forbidden}")


def build_dashboard_map(
    *,
    clean_events_path: Path,
    hotspots_path: Path,
    hotspot_metrics_path: Path,
    output_path: Path,
    threads: int = 4,
) -> dict[str, Any]:
    duckdb = require_duckdb()
    con = duckdb.connect(database=":memory:")
    try:
        con.execute(f"PRAGMA threads={max(1, int(threads))}")
        stats = aggregate_safe_stats(con, clean_events_path)
        hotspot_source, validated_records = load_hotspots(
            con, hotspots_path, stats["endDate"]
        )
    finally:
        con.close()

    methodology = load_methodology(
        hotspot_metrics_path, validated_records, hotspot_source
    )
    grid_size = (
        methodology.get("gridSizeDegrees")
        if methodology.get("status") == "available"
        and methodology.get("gridSizeVerified") is True
        else None
    )
    publishable_records = hotspot_source["records"]
    dimensions = build_dimensions(publishable_records)
    hotspots = index_hotspots(hotspot_source, dimensions, grid_size)
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAtUtc": f"{stats['endDate'].isoformat()}T00:00:00Z",
        "application": {
            "name": "NYC Crime Intelligence",
            "phase": "Phase 7B",
            "view": "Map and Hotspot View",
        },
        "dataRange": {
            "safeEventStartDate": stats["startDate"].isoformat(),
            "safeEventEndDate": stats["endDate"].isoformat(),
            "aggregateSafeEventCount": stats["safeCount"],
            "sourceEventCount": stats["sourceCount"],
            "excludedEventCount": stats["sourceCount"] - stats["safeCount"],
            "unit": "reported aggregate complaint events",
        },
        "dimensions": dimensions,
        "filterIndex": build_filter_index(publishable_records, dimensions),
        "hotspots": hotspots,
        "methodology": methodology,
        "provenance": {
            "cleanEvents": {
                "status": "available",
                "sourceFile": clean_events_path.name,
                "selection": "is_clean_event_for_aggregate = true",
                "publishedUse": "Aggregate-safe count and minimum/maximum date only.",
            },
            "hotspots": {
                "status": hotspot_source["status"],
                "sourceFile": hotspots_path.name,
                "selection": "is_hotspot = true",
                "publishedUse": "Validated aggregate hotspot signals only.",
            },
        },
        "filterSemantics": {
            "borough": "Exact match against the indexed aggregate borough.",
            "precinct": (
                "Exact match for precinct-grain records; grid-grain records have no "
                "precinct and are excluded while a precinct is selected."
            ),
            "offenseType": "Exact match against the aggregate offense type.",
            "lawCategory": "Exact match against the aggregate law category.",
            "reset": "Restore all hotspot dimensions and the current snapshot scope.",
        },
        "dateSemantics": {
            "mode": "fixed-current-snapshot",
            "currentMaxAgeDays": CURRENT_MAX_AGE_DAYS,
            "displayRule": (
                "A snapshot is current only when its scoring date is no later than and "
                "at most one day before the maximum aggregate-safe event date."
            ),
            "historicalSelectionBehavior": (
                "The Map shows the fixed current snapshot when the selected Overview end "
                "week is greater than or equal to the Overview latestCompleteWeek. An earlier "
                "end week is an unsupported historical selection and must show a neutral "
                "state rather than zero."
            ),
        },
        "grainSemantics": {
            "precinct": (
                "Aggregate precinct/offense/law-category signal plotted at an aggregate "
                "coordinate context; it is not an address or person-level location."
            ),
            "grid": (
                "Aggregate analytical grid-cell/offense/law-category signal plotted at "
                "the cell center; it is not an event point."
            ),
        },
        "coordinateSemantics": {
            "latitudeLongitude": "WGS84 decimal degrees constrained to broad NYC bounds.",
            "precinct": (
                "Aggregate coordinate context supplied by the hotspot analytical output; "
                "not an official precinct polygon or event location."
            ),
            "grid": "Aggregate grid-cell center; never a complaint-level coordinate.",
        },
        "limitations": [
            "Hotspots are aggregate retrospective concentration signals, not predictions of individual behavior.",
            "Counts describe reported complaint events and can reflect reporting, classification, and revision effects.",
            "Precinct markers are aggregate coordinate context, not official precinct boundaries.",
            "A current fixed snapshot cannot answer unsupported historical date selections.",
            "Hotspot signals do not establish causality and do not justify patrol or enforcement action.",
        ],
        "ethics": {
            "aggregateTrendIntelligenceOnly": True,
            "eventRecordsIncluded": False,
            "demographicAttributesIncluded": False,
            "personLevelScoring": False,
            "enforcementRecommendations": False,
            "patrolRecommendations": False,
        },
    }
    validate_map_payload(payload)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the aggregate-safe Phase 7B Map data contract."
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--processed-dir", type=Path, default=None)
    parser.add_argument("--dashboard-data-dir", type=Path, default=None)
    parser.add_argument("--clean-events", type=Path, default=None)
    parser.add_argument("--hotspots", type=Path, default=None)
    parser.add_argument("--hotspot-metrics", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--skip-dashboard-copy",
        action="store_true",
        help="Write the canonical processed output without copying map.json to the dashboard.",
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
        project_root, args.output, processed_dir / PROCESSED_MAP_FILE
    )
    payload = build_dashboard_map(
        clean_events_path=resolve_path(
            project_root, args.clean_events, processed_dir / CLEAN_EVENTS_FILE
        ),
        hotspots_path=resolve_path(
            project_root, args.hotspots, processed_dir / HOTSPOTS_FILE
        ),
        hotspot_metrics_path=resolve_path(
            project_root,
            args.hotspot_metrics,
            processed_dir / HOTSPOT_METRICS_FILE,
        ),
        output_path=output_path,
        threads=args.threads,
    )
    if not args.skip_dashboard_copy:
        dashboard_data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output_path, dashboard_data_dir / MAP_FILE)
    print(
        "Built Phase 7B Map data: "
        f"{payload['hotspots']['summary']['rowCount']:,} published aggregate hotspots "
        f"({payload['hotspots']['status']})."
    )
    print(f"Canonical map data: {output_path}")
    if not args.skip_dashboard_copy:
        print(f"Frontend map data: {dashboard_data_dir / MAP_FILE}")


if __name__ == "__main__":
    main()

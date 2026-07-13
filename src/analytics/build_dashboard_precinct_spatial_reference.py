#!/usr/bin/env python3
"""Build the deterministic Phase 7C.3 NYPD precinct spatial contract.

The builder accepts only the reproducibly vendored NYC Open Data Police
Precincts GeoJSON and its reviewed provenance record.  It publishes official
administrative boundary geometry joined exactly to the Forecast Map precinct
location keys.  It never reads complaint/event coordinates or person-level
data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_SOURCE = Path(
    "data/source/nyc_open_data/police_precincts_y76i-bdw7_26b.geojson"
)
DEFAULT_PROVENANCE = Path(
    "data/source/nyc_open_data/police_precincts_y76i-bdw7_26b.provenance.json"
)
DEFAULT_FORECAST_MAP = Path("data/processed/dashboard_forecast_map.json")
DEFAULT_OUTPUT = Path("data/processed/dashboard_precinct_spatial_reference.json")
DEFAULT_DASHBOARD_OUTPUT = Path(
    "dashboard/public/data/precinct-spatial-reference.json"
)

SCHEMA_VERSION = "1.0.0"
FORECAST_SCHEMA_VERSION = "1.0.0"
LOCATION_KEY_SCHEME = "nypd-precinct:<source precinct label>"
LOCATION_KEY_PREFIX = "nypd-precinct:"
SOURCE_FEATURE_COUNT = 78
COORDINATE_DIGITS = 8
SPATIAL_FRESHNESS_DAYS = 120
PRECINCT_RE = re.compile(r"[1-9][0-9]{0,2}\Z")
DECIMAL_TEXT_RE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")

# Deliberately broader than the source's measured bounds, but narrow enough to
# reject swapped axes and non-NYC geometry.
NYC_LON_MIN = -74.30
NYC_LON_MAX = -73.65
NYC_LAT_MIN = 40.45
NYC_LAT_MAX = 40.95

APPLICATION = {
    "name": "NYC Crime Intelligence",
    "phase": "Phase 7C.3",
    "view": "Precinct Spatial Reference",
}
FORECAST_APPLICATION = {
    "name": "NYC Crime Intelligence",
    "phase": "Phase 7C.1",
    "view": "Forecast Map Data Contract",
}

DATASET_KEYS = {
    "title",
    "datasetId",
    "edition",
    "publisher",
    "updateFrequency",
    "dataDate",
    "datasetPageUrl",
    "publisherPageUrl",
    "metadataApiUrl",
    "metadataPdfUrl",
}
RETRIEVAL_KEYS = {
    "retrievalUrl",
    "retrievedAtUtc",
    "portalRowsUpdatedAtUtc",
    "originalFilename",
    "vendoredFilename",
    "mediaType",
    "byteSize",
    "sha256",
    "repeatDownloadByteIdentical",
}
SOURCE_SCHEMA_KEYS = {
    "rootType",
    "featureCount",
    "geometryType",
    "propertyFields",
    "nativeCoordinateReference",
    "nativeCoordinateReferenceName",
    "exportCoordinateReference",
    "exportAxisOrder",
    "conversion",
}
PUBLIC_USE_KEYS = {
    "namedLicense",
    "assessment",
    "termsUrl",
    "faqUrl",
    "technicalStandardsUrl",
    "summary",
}
SOURCE_PRIVACY = {
    "administrativeBoundaryGeometryOnly": True,
    "complaintOrEventRecordsPresent": False,
    "personOrAddressRecordsPresent": False,
    "demographicAttributesPresent": False,
    "aggregatePublicVisualizationSuitable": True,
}
OUTPUT_PRIVACY = {
    "administrativeBoundaryGeometryOnly": True,
    "aggregatePublicVisualizationSuitable": True,
    "complaintOrEventRecordsIncluded": False,
    "personOrAddressRecordsIncluded": False,
    "demographicAttributesIncluded": False,
    "eventLevelCoordinatesIncluded": False,
    "inferredCentroidsIncluded": False,
    "sourceShapeMetricsIncluded": False,
}
FRESHNESS_LIMITATION = (
    "Because the official source is quarterly, the browser treats this spatial "
    f"artifact as stale {SPATIAL_FRESHNESS_DAYS} calendar days after the recorded "
    "portalRowsUpdatedAtUtc timestamp unless a reviewed newer edition is vendored."
)
RESPONSIBLE_USE = {
    "aggregatePrecinctVisualizationOnly": True,
    "specificIncidentLocationPrediction": False,
    "personLevelScoring": False,
    "patrolRecommendations": False,
    "enforcementRecommendations": False,
    "riskOrDangerClassification": False,
}

EXPECTED_DATASET_VALUES = {
    "title": "Police Precincts",
    "datasetId": "y76i-bdw7",
    "edition": "26B",
    "publisher": "New York City Department of City Planning (DCP)",
    "updateFrequency": "Quarterly",
    "dataDate": "2026-05",
    "datasetPageUrl": (
        "https://data.cityofnewyork.us/City-Government/Police-Precincts/y76i-bdw7"
    ),
    "publisherPageUrl": (
        "https://www.nyc.gov/content/planning/pages/resources/datasets/police-precincts"
    ),
    "metadataApiUrl": "https://data.cityofnewyork.us/api/views/y76i-bdw7",
    "metadataPdfUrl": (
        "https://s-media.nyc.gov/agencies/dcp/assets/files/pdf/data-tools/bytes/"
        "nypp_metadata.pdf"
    ),
}
EXPECTED_PUBLIC_URLS = {
    "termsUrl": "https://opendata.cityofnewyork.us/overview/",
    "faqUrl": "https://opendata.cityofnewyork.us/faq/",
    "technicalStandardsUrl": (
        "https://opendata.cityofnewyork.us/wp-content/uploads/"
        "NYC_OpenData_TechnicalStandardsManual.pdf"
    ),
}
EXPECTED_RETRIEVAL_URL = (
    "https://data.cityofnewyork.us/api/geospatial/y76i-bdw7?"
    "method=export&format=GeoJSON"
)
EXPECTED_SOURCE_SCHEMA = {
    "rootType": "FeatureCollection",
    "featureCount": SOURCE_FEATURE_COUNT,
    "geometryType": "MultiPolygon",
    "propertyFields": ["precinct", "shape_area", "shape_leng"],
    "nativeCoordinateReference": "EPSG:2263",
    "nativeCoordinateReferenceName": (
        "NAD83 / New York Long Island (US survey feet)"
    ),
    "exportCoordinateReference": "OGC:CRS84",
    "exportAxisOrder": "longitude, latitude",
    "conversion": (
        "NYC Open Data supplied the GeoJSON export in WGS84 longitude/latitude; "
        "repository processing performs no reprojection."
    ),
}

FORBIDDEN_PROPERTY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(^|_)(complaint|cmplnt|event)(_|$)",
        r"(^|_)(person|victim|suspect|vic|susp)(_|$)",
        r"(^|_)(name|age|race|sex|gender)(_|$)",
        r"(^|_)(address|addr|street|house|apartment|zip)(_|$)",
        r"(^|_)(latitude|longitude|x_coord|y_coord)(_|$)",
        r"(^|_)(patrol|enforcement|demographic)(_|$)",
    )
]


class PrecinctSpatialReferenceContractError(ValueError):
    """A malformed, unsafe, or incompatible spatial artifact."""


def resolve_path(project_root: Path, value: Path | None, default: Path) -> Path:
    candidate = default if value is None else value
    return candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()


def _reject_nonfinite_constant(value: str) -> None:
    raise PrecinctSpatialReferenceContractError(
        f"JSON contains a non-finite numeric constant: {value}."
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PrecinctSpatialReferenceContractError(
                f"JSON contains a duplicate object key: {key}."
            )
        result[key] = value
    return result


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise PrecinctSpatialReferenceContractError(f"Missing {label}: {path}.")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PrecinctSpatialReferenceContractError(
            f"Malformed {label}: {path}."
        ) from exc
    if not isinstance(value, dict):
        raise PrecinctSpatialReferenceContractError(f"{label} must be a JSON object.")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expect_object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PrecinctSpatialReferenceContractError(
            f"{label} does not match the exact schema."
        )
    return value


def _required_text(value: Any, label: str, *, max_length: int = 2000) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PrecinctSpatialReferenceContractError(f"Missing or malformed text: {label}.")
    if len(value) > max_length or any(ord(character) < 32 for character in value):
        raise PrecinctSpatialReferenceContractError(f"Unsafe text: {label}.")
    return value


def _required_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PrecinctSpatialReferenceContractError(f"Malformed integer: {label}.")
    return value


def _required_utc_timestamp(value: Any, label: str) -> str:
    text = _required_text(value, label)
    if not text.endswith("Z"):
        raise PrecinctSpatialReferenceContractError(f"{label} must be UTC with a Z suffix.")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise PrecinctSpatialReferenceContractError(f"Malformed timestamp: {label}.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise PrecinctSpatialReferenceContractError(f"Malformed UTC timestamp: {label}.")
    return text


def _require_https_url(value: Any, label: str, expected: str) -> str:
    text = _required_text(value, label)
    parsed = urlparse(text)
    if text != expected or parsed.scheme != "https" or not parsed.hostname:
        raise PrecinctSpatialReferenceContractError(
            f"Unapproved or malformed official URL: {label}."
        )
    return text


def _unsafe_property_names(names: set[str]) -> list[str]:
    return sorted(
        name
        for name in names
        if any(pattern.search(name) for pattern in FORBIDDEN_PROPERTY_PATTERNS)
    )


def validate_provenance(
    provenance: dict[str, Any], *, source_path: Path, provenance_path: Path
) -> dict[str, Any]:
    if not source_path.is_file():
        raise PrecinctSpatialReferenceContractError(
            f"Missing authoritative precinct GeoJSON: {source_path}."
        )
    _expect_object(
        provenance,
        {"schemaVersion", "dataset", "retrieval", "sourceSchema", "publicUse", "privacy"},
        "Provenance root",
    )
    if provenance["schemaVersion"] != SCHEMA_VERSION:
        raise PrecinctSpatialReferenceContractError("Unsupported provenance schema version.")

    dataset = _expect_object(provenance["dataset"], DATASET_KEYS, "Provenance dataset")
    if dataset != EXPECTED_DATASET_VALUES:
        raise PrecinctSpatialReferenceContractError(
            "Provenance dataset identity or official URLs are invalid."
        )
    for key in ("datasetPageUrl", "publisherPageUrl", "metadataApiUrl", "metadataPdfUrl"):
        _require_https_url(dataset[key], f"dataset.{key}", EXPECTED_DATASET_VALUES[key])

    retrieval = _expect_object(
        provenance["retrieval"], RETRIEVAL_KEYS, "Provenance retrieval"
    )
    _require_https_url(retrieval["retrievalUrl"], "retrieval URL", EXPECTED_RETRIEVAL_URL)
    _required_utc_timestamp(retrieval["retrievedAtUtc"], "retrievedAtUtc")
    _required_utc_timestamp(
        retrieval["portalRowsUpdatedAtUtc"], "portalRowsUpdatedAtUtc"
    )
    if retrieval["originalFilename"] != "Police Precincts.geojson":
        raise PrecinctSpatialReferenceContractError("Original source filename is invalid.")
    if retrieval["vendoredFilename"] != source_path.name:
        raise PrecinctSpatialReferenceContractError("Vendored source filename does not reconcile.")
    if retrieval["mediaType"] != "application/vnd.geo+json":
        raise PrecinctSpatialReferenceContractError("Source media type is invalid.")
    if retrieval["repeatDownloadByteIdentical"] is not True:
        raise PrecinctSpatialReferenceContractError(
            "Repeat-download reproducibility was not verified."
        )
    expected_size = _required_int(retrieval["byteSize"], "source byte size", minimum=1)
    if source_path.stat().st_size != expected_size:
        raise PrecinctSpatialReferenceContractError(
            "Vendored source byte size does not match provenance."
        )
    expected_checksum = _required_text(retrieval["sha256"], "source SHA-256")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_checksum):
        raise PrecinctSpatialReferenceContractError("Source SHA-256 is malformed.")
    actual_checksum = sha256_file(source_path)
    if actual_checksum != expected_checksum:
        raise PrecinctSpatialReferenceContractError(
            "Vendored source SHA-256 does not match provenance."
        )

    source_schema = _expect_object(
        provenance["sourceSchema"], SOURCE_SCHEMA_KEYS, "Provenance source schema"
    )
    if source_schema != EXPECTED_SOURCE_SCHEMA:
        raise PrecinctSpatialReferenceContractError(
            "Provenance source schema or coordinate reference is invalid."
        )

    public_use = _expect_object(
        provenance["publicUse"], PUBLIC_USE_KEYS, "Provenance public-use assessment"
    )
    if public_use["namedLicense"] is not None:
        raise PrecinctSpatialReferenceContractError(
            "The provenance must not invent a named source license."
        )
    if public_use["assessment"] != "license-compatible public data":
        raise PrecinctSpatialReferenceContractError(
            "Source public-use compatibility was not affirmatively reviewed."
        )
    for key, expected_url in EXPECTED_PUBLIC_URLS.items():
        _require_https_url(public_use[key], f"publicUse.{key}", expected_url)
    summary = _required_text(public_use["summary"], "public-use summary")
    lowered_summary = summary.lower()
    if "no use restrictions" not in lowered_summary or "freely available" not in lowered_summary:
        raise PrecinctSpatialReferenceContractError(
            "Public-use summary does not record the reviewed reuse basis."
        )

    if provenance["privacy"] != SOURCE_PRIVACY:
        raise PrecinctSpatialReferenceContractError(
            "Source privacy and aggregate-use assertions are absent or unsafe."
        )

    return {
        "sourceSha256": actual_checksum,
        "sourceByteSize": expected_size,
        "provenanceSha256": sha256_file(provenance_path),
        "provenanceByteSize": provenance_path.stat().st_size,
    }


def _empty_geometry_stats() -> dict[str, Any]:
    return {
        "polygonCount": 0,
        "ringCount": 0,
        "positionCount": 0,
        "minLongitude": math.inf,
        "minLatitude": math.inf,
        "maxLongitude": -math.inf,
        "maxLatitude": -math.inf,
    }


def _merge_geometry_stats(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in ("polygonCount", "ringCount", "positionCount"):
        target[key] += source[key]
    target["minLongitude"] = min(target["minLongitude"], source["minLongitude"])
    target["minLatitude"] = min(target["minLatitude"], source["minLatitude"])
    target["maxLongitude"] = max(target["maxLongitude"], source["maxLongitude"])
    target["maxLatitude"] = max(target["maxLatitude"], source["maxLatitude"])


def _translated_ring_double_area(
    positions: list[tuple[float, float]],
) -> Decimal:
    """Return exact signed double-area using a local origin to avoid cancellation."""
    origin_x = Decimal(str(positions[0][0]))
    origin_y = Decimal(str(positions[0][1]))
    area = Decimal(0)
    for current, following in zip(positions, positions[1:]):
        current_x = Decimal(str(current[0])) - origin_x
        current_y = Decimal(str(current[1])) - origin_y
        following_x = Decimal(str(following[0])) - origin_x
        following_y = Decimal(str(following[1])) - origin_y
        area += current_x * following_y - following_x * current_y
    return area


def validate_multipolygon_geometry(
    geometry: Any, label: str, *, require_rounded: bool = False
) -> dict[str, Any]:
    geometry_object = _expect_object(geometry, {"type", "coordinates"}, label)
    if geometry_object["type"] != "MultiPolygon":
        raise PrecinctSpatialReferenceContractError(f"{label} must be a MultiPolygon.")
    multipolygon = geometry_object["coordinates"]
    if not isinstance(multipolygon, list) or not multipolygon:
        raise PrecinctSpatialReferenceContractError(f"{label} has no polygons.")

    stats = _empty_geometry_stats()
    for polygon_index, polygon in enumerate(multipolygon):
        if not isinstance(polygon, list) or not polygon:
            raise PrecinctSpatialReferenceContractError(
                f"{label} polygon {polygon_index} has no rings."
            )
        stats["polygonCount"] += 1
        for ring_index, ring in enumerate(polygon):
            ring_label = f"{label} polygon {polygon_index} ring {ring_index}"
            if not isinstance(ring, list) or len(ring) < 4:
                raise PrecinctSpatialReferenceContractError(
                    f"{ring_label} must contain at least four positions."
                )
            stats["ringCount"] += 1
            normalized_positions: list[tuple[float, float]] = []
            for position_index, position in enumerate(ring):
                if not isinstance(position, list) or len(position) != 2:
                    raise PrecinctSpatialReferenceContractError(
                        f"{ring_label} position {position_index} is malformed."
                    )
                longitude, latitude = position
                if (
                    isinstance(longitude, bool)
                    or isinstance(latitude, bool)
                    or not isinstance(longitude, (int, float))
                    or not isinstance(latitude, (int, float))
                ):
                    raise PrecinctSpatialReferenceContractError(
                        f"{ring_label} position {position_index} is not numeric."
                    )
                longitude_number = float(longitude)
                latitude_number = float(latitude)
                if not math.isfinite(longitude_number) or not math.isfinite(latitude_number):
                    raise PrecinctSpatialReferenceContractError(
                        f"{ring_label} contains a non-finite coordinate."
                    )
                if not (
                    NYC_LON_MIN <= longitude_number <= NYC_LON_MAX
                    and NYC_LAT_MIN <= latitude_number <= NYC_LAT_MAX
                ):
                    raise PrecinctSpatialReferenceContractError(
                        f"{ring_label} contains a coordinate outside plausible NYC bounds."
                    )
                if require_rounded and (
                    round(longitude_number, COORDINATE_DIGITS) != longitude_number
                    or round(latitude_number, COORDINATE_DIGITS) != latitude_number
                ):
                    raise PrecinctSpatialReferenceContractError(
                        f"{ring_label} is not canonically rounded."
                    )
                normalized_positions.append((longitude_number, latitude_number))
                stats["positionCount"] += 1
                stats["minLongitude"] = min(stats["minLongitude"], longitude_number)
                stats["minLatitude"] = min(stats["minLatitude"], latitude_number)
                stats["maxLongitude"] = max(stats["maxLongitude"], longitude_number)
                stats["maxLatitude"] = max(stats["maxLatitude"], latitude_number)
            if normalized_positions[0] != normalized_positions[-1]:
                raise PrecinctSpatialReferenceContractError(f"{ring_label} is not closed.")
            if len(set(normalized_positions[:-1])) < 3:
                raise PrecinctSpatialReferenceContractError(
                    f"{ring_label} must contain at least three distinct vertices."
                )
            if _translated_ring_double_area(normalized_positions) == 0:
                raise PrecinctSpatialReferenceContractError(
                    f"{ring_label} has zero area."
                )
    return stats


def validate_authoritative_source(
    source: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _expect_object(source, {"type", "features"}, "Authoritative GeoJSON root")
    if source["type"] != "FeatureCollection":
        raise PrecinctSpatialReferenceContractError(
            "Authoritative source must be a GeoJSON FeatureCollection."
        )
    features = source["features"]
    if not isinstance(features, list) or len(features) != SOURCE_FEATURE_COUNT:
        raise PrecinctSpatialReferenceContractError(
            f"Authoritative source must contain exactly {SOURCE_FEATURE_COUNT} features."
        )

    labels: set[str] = set()
    stats = _empty_geometry_stats()
    for feature_index, feature in enumerate(features):
        feature_object = _expect_object(
            feature, {"type", "properties", "geometry"}, f"Source feature {feature_index}"
        )
        if feature_object["type"] != "Feature":
            raise PrecinctSpatialReferenceContractError(
                f"Source feature {feature_index} has an invalid GeoJSON type."
            )
        properties = _expect_object(
            feature_object["properties"],
            {"precinct", "shape_area", "shape_leng"},
            f"Source feature {feature_index} properties",
        )
        unsafe_fields = _unsafe_property_names(set(properties))
        if unsafe_fields:
            raise PrecinctSpatialReferenceContractError(
                f"Source feature contains forbidden fields: {unsafe_fields}."
            )
        precinct = properties["precinct"]
        if not isinstance(precinct, str) or not PRECINCT_RE.fullmatch(precinct):
            raise PrecinctSpatialReferenceContractError(
                f"Source feature {feature_index} has an unsafe precinct identifier."
            )
        if precinct in labels:
            raise PrecinctSpatialReferenceContractError(
                f"Authoritative source contains duplicate precinct identifier: {precinct}."
            )
        labels.add(precinct)
        for field in ("shape_area", "shape_leng"):
            value = properties[field]
            if not isinstance(value, str) or not DECIMAL_TEXT_RE.fullmatch(value):
                raise PrecinctSpatialReferenceContractError(
                    f"Source feature {feature_index} has malformed {field}."
                )
            try:
                numeric_value = Decimal(value)
            except InvalidOperation as exc:
                raise PrecinctSpatialReferenceContractError(
                    f"Source feature {feature_index} has malformed {field}."
                ) from exc
            if not numeric_value.is_finite() or numeric_value <= 0:
                raise PrecinctSpatialReferenceContractError(
                    f"Source feature {feature_index} has invalid {field}."
                )
        feature_stats = validate_multipolygon_geometry(
            feature_object["geometry"], f"Source feature {precinct} geometry"
        )
        _merge_geometry_stats(stats, feature_stats)
    return features, stats


def _load_forecast_validator() -> Any:
    try:
        from src.analytics.build_dashboard_forecast_map import (  # type: ignore
            validate_forecast_map_payload,
        )
    except ModuleNotFoundError:  # Direct execution from src/analytics.
        from build_dashboard_forecast_map import (  # type: ignore
            validate_forecast_map_payload,
        )
    return validate_forecast_map_payload


def load_forecast_context(forecast_path: Path) -> dict[str, Any]:
    forecast = read_json(forecast_path, "Forecast Map contract")
    try:
        _load_forecast_validator()(forecast)
    except (ValueError, KeyError, TypeError) as exc:
        raise PrecinctSpatialReferenceContractError(
            "Forecast Map contract is invalid or unsafe."
        ) from exc
    if forecast.get("schemaVersion") != FORECAST_SCHEMA_VERSION:
        raise PrecinctSpatialReferenceContractError("Unsupported Forecast Map schema version.")
    if forecast.get("application") != FORECAST_APPLICATION:
        raise PrecinctSpatialReferenceContractError("Forecast Map application identity is invalid.")
    location_semantics = forecast.get("locationKeySemantics")
    if (
        not isinstance(location_semantics, dict)
        or location_semantics.get("scheme") != LOCATION_KEY_SCHEME
    ):
        raise PrecinctSpatialReferenceContractError("Forecast location-key scheme is incompatible.")
    dimensions = forecast.get("dimensions")
    labels = dimensions.get("precincts") if isinstance(dimensions, dict) else None
    if not isinstance(labels, list) or len(labels) != SOURCE_FEATURE_COUNT:
        raise PrecinctSpatialReferenceContractError(
            f"Forecast contract must publish exactly {SOURCE_FEATURE_COUNT} precinct labels."
        )
    if any(not isinstance(label, str) or not PRECINCT_RE.fullmatch(label) for label in labels):
        raise PrecinctSpatialReferenceContractError("Forecast precinct labels are unsafe.")
    if len(set(labels)) != len(labels):
        raise PrecinctSpatialReferenceContractError("Forecast precinct labels are duplicated.")
    expected_keys = {LOCATION_KEY_PREFIX + label for label in labels}

    forecast_section = forecast.get("forecast")
    if not isinstance(forecast_section, dict) or forecast_section.get("status") != "available":
        raise PrecinctSpatialReferenceContractError(
            "Spatial coverage cannot be established without an available Forecast contract."
        )
    columns = forecast_section.get("rowColumns")
    rows = forecast_section.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise PrecinctSpatialReferenceContractError("Forecast rows are malformed.")
    try:
        key_index = columns.index("precinctLocationKey")
    except ValueError as exc:
        raise PrecinctSpatialReferenceContractError(
            "Forecast rows omit the precinct location key."
        ) from exc
    published_keys = {
        row[key_index]
        for row in rows
        if isinstance(row, list) and len(row) == len(columns)
    }
    if published_keys != expected_keys:
        raise PrecinctSpatialReferenceContractError(
            "Forecast row location keys do not cover the declared precinct labels exactly."
        )
    return {
        "schemaVersion": forecast["schemaVersion"],
        "locationKeyScheme": location_semantics["scheme"],
        "labels": labels,
        "locationKeys": expected_keys,
    }


def _rounded_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    rounded_multipolygon: list[list[list[list[float]]]] = []
    for polygon in geometry["coordinates"]:
        rounded_polygon: list[list[list[float]]] = []
        for ring in polygon:
            rounded_ring = [
                [
                    round(float(position[0]), COORDINATE_DIGITS),
                    round(float(position[1]), COORDINATE_DIGITS),
                ]
                for position in ring
            ]
            # Preserve closure explicitly, even if future Python float formatting changes.
            rounded_ring[-1] = rounded_ring[0].copy()
            rounded_polygon.append(rounded_ring)
        rounded_multipolygon.append(rounded_polygon)
    return {"type": "MultiPolygon", "coordinates": rounded_multipolygon}


def _rounded_bounds(stats: dict[str, Any]) -> dict[str, float]:
    return {
        "minLongitude": round(float(stats["minLongitude"]), COORDINATE_DIGITS),
        "minLatitude": round(float(stats["minLatitude"]), COORDINATE_DIGITS),
        "maxLongitude": round(float(stats["maxLongitude"]), COORDINATE_DIGITS),
        "maxLatitude": round(float(stats["maxLatitude"]), COORDINATE_DIGITS),
    }


def reconcile_location_keys(
    source_keys: set[str], forecast_keys: set[str]
) -> tuple[list[str], list[str]]:
    missing = sorted(forecast_keys - source_keys)
    unexpected = sorted(source_keys - forecast_keys)
    if missing or unexpected:
        raise PrecinctSpatialReferenceContractError(
            "Precinct spatial/Forecast location-key mismatch: "
            f"missing={missing}, unexpected={unexpected}."
        )
    return missing, unexpected


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def build_dashboard_precinct_spatial_reference(
    *,
    source_path: Path,
    provenance_path: Path,
    forecast_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    ensure_output_does_not_overwrite_inputs(
        output_path, [source_path, provenance_path, forecast_path]
    )
    provenance = read_json(provenance_path, "source provenance")
    provenance_integrity = validate_provenance(
        provenance, source_path=source_path, provenance_path=provenance_path
    )
    source = read_json(source_path, "authoritative precinct GeoJSON")
    source_features, source_stats = validate_authoritative_source(source)
    forecast_context = load_forecast_context(forecast_path)

    output_features: list[dict[str, Any]] = []
    source_keys: set[str] = set()
    for source_feature in source_features:
        precinct_label = source_feature["properties"]["precinct"]
        location_key = LOCATION_KEY_PREFIX + precinct_label
        source_keys.add(location_key)
        output_features.append(
            {
                "type": "Feature",
                "properties": {
                    "precinctLabel": precinct_label,
                    "locationKey": location_key,
                },
                "geometry": _rounded_geometry(source_feature["geometry"]),
            }
        )
    output_features.sort(key=lambda feature: feature["properties"]["locationKey"])
    reconcile_location_keys(source_keys, forecast_context["locationKeys"])

    output_stats = _empty_geometry_stats()
    for feature in output_features:
        feature_stats = validate_multipolygon_geometry(
            feature["geometry"],
            f"Published feature {feature['properties']['locationKey']} geometry",
            require_rounded=True,
        )
        _merge_geometry_stats(output_stats, feature_stats)
    if any(
        source_stats[key] != output_stats[key]
        for key in ("polygonCount", "ringCount", "positionCount")
    ):
        raise PrecinctSpatialReferenceContractError(
            "Coordinate processing changed the source geometry structure."
        )

    source_retrieval = provenance["retrieval"]
    payload = {
        "type": "FeatureCollection",
        "schemaVersion": SCHEMA_VERSION,
        "generatedAtUtc": source_retrieval["retrievedAtUtc"],
        "application": APPLICATION,
        "provenance": {
            "dataset": provenance["dataset"],
            "retrieval": source_retrieval,
            "sourceSchema": provenance["sourceSchema"],
            "publicUse": provenance["publicUse"],
            "provenanceRecord": {
                "filename": provenance_path.name,
                "byteSize": provenance_integrity["provenanceByteSize"],
                "sha256": provenance_integrity["provenanceSha256"],
            },
        },
        "coordinateReference": {
            "sourceNative": {
                "identifier": provenance["sourceSchema"]["nativeCoordinateReference"],
                "name": provenance["sourceSchema"]["nativeCoordinateReferenceName"],
            },
            "officialGeoJsonExport": {
                "identifier": provenance["sourceSchema"]["exportCoordinateReference"],
                "axisOrder": provenance["sourceSchema"]["exportAxisOrder"],
            },
            "publishedCoordinateOrder": "longitude, latitude",
            "repositoryReprojectionApplied": False,
            "conversion": provenance["sourceSchema"]["conversion"],
            "bounds": _rounded_bounds(output_stats),
        },
        "locationKeySemantics": {
            "scheme": LOCATION_KEY_SCHEME,
            "sourceIdentifierField": "precinct",
            "publishedLabelField": "properties.precinctLabel",
            "publishedJoinField": "properties.locationKey",
            "mapping": (
                "Exact string mapping from the authoritative precinct property; "
                "no precinct is remapped, merged, dropped, or invented."
            ),
        },
        "compatibility": {
            "forecastMapSchemaVersion": forecast_context["schemaVersion"],
            "forecastMapView": FORECAST_APPLICATION["view"],
            "locationKeyScheme": forecast_context["locationKeyScheme"],
            "forecastLocationKeyCount": len(forecast_context["locationKeys"]),
            "reconciliation": "exact",
        },
        "processing": {
            "coordinateRoundingDigits": COORDINATE_DIGITS,
            "simplificationApplied": False,
            "simplificationAlgorithm": None,
            "simplificationTolerance": None,
            "vertexRemovalApplied": False,
            "sourcePositionCount": source_stats["positionCount"],
            "publishedPositionCount": output_stats["positionCount"],
            "featureOrdering": "Lexical ascending locationKey.",
            "canonicalJson": (
                "UTF-8, recursively sorted object keys, compact separators, "
                "finite JSON numbers, one trailing newline."
            ),
            "generationTimestampPolicy": (
                "generatedAtUtc equals the reviewed source retrieval timestamp; "
                "the wall clock is never read."
            ),
        },
        "coverage": {
            "expectedFeatureCount": SOURCE_FEATURE_COUNT,
            "featureCount": len(output_features),
            "forecastLocationKeyCount": len(forecast_context["locationKeys"]),
            "polygonCount": output_stats["polygonCount"],
            "ringCount": output_stats["ringCount"],
            "positionCount": output_stats["positionCount"],
            "missingForecastLocationKeys": [],
            "unexpectedSpatialLocationKeys": [],
            "duplicateLocationKeyCount": 0,
            "complete": True,
        },
        "privacy": OUTPUT_PRIVACY,
        "responsibleUse": RESPONSIBLE_USE,
        "limitations": [
            (
                "Boundaries reflect NYC Department of City Planning edition 26B, "
                "data date 2026-05, and can become stale after an official boundary update."
            ),
            FRESHNESS_LIMITATION,
            (
                "Geometry is an administrative precinct boundary, not an event "
                "location, inferred centroid, future incident location, or person-level record."
            ),
            (
                "Coordinates are rounded to eight decimal places, the minimum fixed "
                "precision verified to preserve at least three distinct vertices in "
                "every ring, without vertex simplification or repository reprojection."
            ),
            (
                "NYC and DCP provide the source for informational use without warranties "
                "of completeness, accuracy, content, or fitness for a particular use."
            ),
            (
                "The artifact supplies geography only and does not contain forecasts, "
                "confidence intervals, risk scores, patrol priorities, or enforcement targets."
            ),
        ],
        "features": output_features,
    }
    validate_precinct_spatial_reference_payload(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(_canonical_bytes(payload))
    validate_canonical_output(output_path)
    return payload


def validate_precinct_spatial_reference_payload(payload: dict[str, Any]) -> None:
    required_top_level = {
        "type",
        "schemaVersion",
        "generatedAtUtc",
        "application",
        "provenance",
        "coordinateReference",
        "locationKeySemantics",
        "compatibility",
        "processing",
        "coverage",
        "privacy",
        "responsibleUse",
        "limitations",
        "features",
    }
    _expect_object(payload, required_top_level, "Spatial-reference root")
    if payload["type"] != "FeatureCollection" or payload["schemaVersion"] != SCHEMA_VERSION:
        raise PrecinctSpatialReferenceContractError("Spatial-reference identity is invalid.")
    if payload["application"] != APPLICATION:
        raise PrecinctSpatialReferenceContractError("Spatial-reference application is invalid.")
    generated_at = _required_utc_timestamp(payload["generatedAtUtc"], "generatedAtUtc")

    provenance = _expect_object(
        payload["provenance"],
        {"dataset", "retrieval", "sourceSchema", "publicUse", "provenanceRecord"},
        "Published provenance",
    )
    if provenance["dataset"] != EXPECTED_DATASET_VALUES:
        raise PrecinctSpatialReferenceContractError("Published dataset provenance is invalid.")
    retrieval = _expect_object(provenance["retrieval"], RETRIEVAL_KEYS, "Published retrieval")
    if generated_at != retrieval["retrievedAtUtc"]:
        raise PrecinctSpatialReferenceContractError(
            "Generation timestamp does not reconcile to source retrieval."
        )
    _require_https_url(retrieval["retrievalUrl"], "retrieval URL", EXPECTED_RETRIEVAL_URL)
    _required_utc_timestamp(retrieval["portalRowsUpdatedAtUtc"], "portalRowsUpdatedAtUtc")
    if (
        retrieval["originalFilename"] != "Police Precincts.geojson"
        or retrieval["vendoredFilename"] != DEFAULT_SOURCE.name
        or retrieval["mediaType"] != "application/vnd.geo+json"
        or retrieval["repeatDownloadByteIdentical"] is not True
        or not isinstance(retrieval["sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", retrieval["sha256"]) is None
        or not isinstance(retrieval["byteSize"], int)
        or retrieval["byteSize"] <= 0
    ):
        raise PrecinctSpatialReferenceContractError("Published retrieval integrity is invalid.")
    if provenance["sourceSchema"] != EXPECTED_SOURCE_SCHEMA:
        raise PrecinctSpatialReferenceContractError("Published source schema is invalid.")
    public_use = _expect_object(
        provenance["publicUse"], PUBLIC_USE_KEYS, "Published public-use assessment"
    )
    if (
        public_use["namedLicense"] is not None
        or public_use["assessment"] != "license-compatible public data"
    ):
        raise PrecinctSpatialReferenceContractError("Published public-use assessment is unsafe.")
    for key, expected_url in EXPECTED_PUBLIC_URLS.items():
        _require_https_url(public_use[key], f"publicUse.{key}", expected_url)
    public_use_summary = _required_text(public_use["summary"], "public-use summary")
    if (
        "no use restrictions" not in public_use_summary.lower()
        or "freely available" not in public_use_summary.lower()
    ):
        raise PrecinctSpatialReferenceContractError(
            "Published public-use summary is incomplete."
        )
    provenance_record = _expect_object(
        provenance["provenanceRecord"],
        {"filename", "byteSize", "sha256"},
        "Published provenance record",
    )
    if (
        provenance_record["filename"] != DEFAULT_PROVENANCE.name
        or not isinstance(provenance_record["byteSize"], int)
        or provenance_record["byteSize"] <= 0
        or not isinstance(provenance_record["sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", provenance_record["sha256"]) is None
    ):
        raise PrecinctSpatialReferenceContractError(
            "Published provenance-record integrity is invalid."
        )

    coordinate_reference = _expect_object(
        payload["coordinateReference"],
        {
            "sourceNative",
            "officialGeoJsonExport",
            "publishedCoordinateOrder",
            "repositoryReprojectionApplied",
            "conversion",
            "bounds",
        },
        "Coordinate reference",
    )
    if coordinate_reference["sourceNative"] != {
        "identifier": "EPSG:2263",
        "name": "NAD83 / New York Long Island (US survey feet)",
    } or coordinate_reference["officialGeoJsonExport"] != {
        "identifier": "OGC:CRS84",
        "axisOrder": "longitude, latitude",
    }:
        raise PrecinctSpatialReferenceContractError("Coordinate reference identity is invalid.")
    if not (
        coordinate_reference["publishedCoordinateOrder"] == "longitude, latitude"
        and coordinate_reference["repositoryReprojectionApplied"] is False
        and coordinate_reference["conversion"] == EXPECTED_SOURCE_SCHEMA["conversion"]
    ):
        raise PrecinctSpatialReferenceContractError("Coordinate conversion semantics are invalid.")

    location_semantics = _expect_object(
        payload["locationKeySemantics"],
        {"scheme", "sourceIdentifierField", "publishedLabelField", "publishedJoinField", "mapping"},
        "Location-key semantics",
    )
    if not (
        location_semantics["scheme"] == LOCATION_KEY_SCHEME
        and location_semantics["sourceIdentifierField"] == "precinct"
        and location_semantics["publishedLabelField"] == "properties.precinctLabel"
        and location_semantics["publishedJoinField"] == "properties.locationKey"
        and isinstance(location_semantics["mapping"], str)
        and location_semantics["mapping"]
    ):
        raise PrecinctSpatialReferenceContractError("Location-key semantics are invalid.")

    compatibility = _expect_object(
        payload["compatibility"],
        {
            "forecastMapSchemaVersion",
            "forecastMapView",
            "locationKeyScheme",
            "forecastLocationKeyCount",
            "reconciliation",
        },
        "Forecast compatibility",
    )
    if compatibility != {
        "forecastMapSchemaVersion": FORECAST_SCHEMA_VERSION,
        "forecastMapView": FORECAST_APPLICATION["view"],
        "locationKeyScheme": LOCATION_KEY_SCHEME,
        "forecastLocationKeyCount": SOURCE_FEATURE_COUNT,
        "reconciliation": "exact",
    }:
        raise PrecinctSpatialReferenceContractError("Forecast compatibility is invalid.")

    processing = _expect_object(
        payload["processing"],
        {
            "coordinateRoundingDigits",
            "simplificationApplied",
            "simplificationAlgorithm",
            "simplificationTolerance",
            "vertexRemovalApplied",
            "sourcePositionCount",
            "publishedPositionCount",
            "featureOrdering",
            "canonicalJson",
            "generationTimestampPolicy",
        },
        "Processing metadata",
    )
    if not (
        processing["coordinateRoundingDigits"] == COORDINATE_DIGITS
        and processing["simplificationApplied"] is False
        and processing["simplificationAlgorithm"] is None
        and processing["simplificationTolerance"] is None
        and processing["vertexRemovalApplied"] is False
        and processing["featureOrdering"] == "Lexical ascending locationKey."
        and isinstance(processing["canonicalJson"], str)
        and isinstance(processing["generationTimestampPolicy"], str)
    ):
        raise PrecinctSpatialReferenceContractError("Processing metadata is invalid.")

    features = payload["features"]
    if not isinstance(features, list) or len(features) != SOURCE_FEATURE_COUNT:
        raise PrecinctSpatialReferenceContractError(
            f"Published spatial contract must contain exactly {SOURCE_FEATURE_COUNT} features."
        )
    stats = _empty_geometry_stats()
    location_keys: list[str] = []
    labels: set[str] = set()
    for feature_index, feature in enumerate(features):
        feature_object = _expect_object(
            feature, {"type", "properties", "geometry"}, f"Published feature {feature_index}"
        )
        if feature_object["type"] != "Feature":
            raise PrecinctSpatialReferenceContractError("Published feature type is invalid.")
        properties = _expect_object(
            feature_object["properties"],
            {"precinctLabel", "locationKey"},
            f"Published feature {feature_index} properties",
        )
        unsafe_fields = _unsafe_property_names(set(properties))
        if unsafe_fields:
            raise PrecinctSpatialReferenceContractError(
                f"Published feature contains forbidden fields: {unsafe_fields}."
            )
        label = properties["precinctLabel"]
        location_key = properties["locationKey"]
        if not isinstance(label, str) or not PRECINCT_RE.fullmatch(label):
            raise PrecinctSpatialReferenceContractError("Published precinct label is unsafe.")
        if location_key != LOCATION_KEY_PREFIX + label:
            raise PrecinctSpatialReferenceContractError("Published location key is unsafe.")
        if label in labels:
            raise PrecinctSpatialReferenceContractError("Published precinct labels are duplicated.")
        labels.add(label)
        location_keys.append(location_key)
        feature_stats = validate_multipolygon_geometry(
            feature_object["geometry"],
            f"Published feature {location_key} geometry",
            require_rounded=True,
        )
        _merge_geometry_stats(stats, feature_stats)
    if location_keys != sorted(location_keys) or len(set(location_keys)) != len(location_keys):
        raise PrecinctSpatialReferenceContractError(
            "Published features are duplicated or not in stable lexical location-key order."
        )

    bounds = _expect_object(
        coordinate_reference["bounds"],
        {"minLongitude", "minLatitude", "maxLongitude", "maxLatitude"},
        "Published coordinate bounds",
    )
    if bounds != _rounded_bounds(stats):
        raise PrecinctSpatialReferenceContractError("Published coordinate bounds do not reconcile.")
    coverage = _expect_object(
        payload["coverage"],
        {
            "expectedFeatureCount",
            "featureCount",
            "forecastLocationKeyCount",
            "polygonCount",
            "ringCount",
            "positionCount",
            "missingForecastLocationKeys",
            "unexpectedSpatialLocationKeys",
            "duplicateLocationKeyCount",
            "complete",
        },
        "Geometry coverage",
    )
    expected_coverage = {
        "expectedFeatureCount": SOURCE_FEATURE_COUNT,
        "featureCount": len(features),
        "forecastLocationKeyCount": SOURCE_FEATURE_COUNT,
        "polygonCount": stats["polygonCount"],
        "ringCount": stats["ringCount"],
        "positionCount": stats["positionCount"],
        "missingForecastLocationKeys": [],
        "unexpectedSpatialLocationKeys": [],
        "duplicateLocationKeyCount": 0,
        "complete": True,
    }
    if coverage != expected_coverage:
        raise PrecinctSpatialReferenceContractError("Geometry coverage does not reconcile.")
    if not (
        processing["sourcePositionCount"] == stats["positionCount"]
        and processing["publishedPositionCount"] == stats["positionCount"]
    ):
        raise PrecinctSpatialReferenceContractError("Geometry processing counts do not reconcile.")
    if payload["privacy"] != OUTPUT_PRIVACY:
        raise PrecinctSpatialReferenceContractError("Spatial privacy flags are absent or unsafe.")
    if payload["responsibleUse"] != RESPONSIBLE_USE:
        raise PrecinctSpatialReferenceContractError("Responsible-use flags are absent or unsafe.")
    limitations = payload["limitations"]
    if (
        not isinstance(limitations, list)
        or len(limitations) < 4
        or any(not isinstance(item, str) or not item for item in limitations)
        or FRESHNESS_LIMITATION not in limitations
    ):
        raise PrecinctSpatialReferenceContractError("Spatial limitations are incomplete.")


def validate_canonical_output(path: Path) -> dict[str, Any]:
    payload = read_json(path, "processed spatial-reference artifact")
    validate_precinct_spatial_reference_payload(payload)
    if path.read_bytes() != _canonical_bytes(payload):
        raise PrecinctSpatialReferenceContractError(
            "Processed spatial-reference artifact is not canonical JSON."
        )
    return payload


def ensure_output_does_not_overwrite_inputs(output_path: Path, input_paths: list[Path]) -> None:
    resolved_output = output_path.resolve()
    if any(path.resolve() == resolved_output for path in input_paths):
        raise PrecinctSpatialReferenceContractError(
            "Spatial-reference output path must not overwrite a source artifact."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the verified Phase 7C.3 precinct spatial-reference contract."
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--provenance", type=Path, default=None)
    parser.add_argument("--forecast-map", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--dashboard-output", type=Path, default=None)
    parser.add_argument(
        "--skip-dashboard-copy",
        action="store_true",
        help="Write only the canonical processed artifact.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = args.project_root.resolve()
    source_path = resolve_path(project_root, args.source, DEFAULT_SOURCE)
    provenance_path = resolve_path(project_root, args.provenance, DEFAULT_PROVENANCE)
    forecast_path = resolve_path(project_root, args.forecast_map, DEFAULT_FORECAST_MAP)
    output_path = resolve_path(project_root, args.output, DEFAULT_OUTPUT)
    dashboard_output = resolve_path(
        project_root, args.dashboard_output, DEFAULT_DASHBOARD_OUTPUT
    )
    input_paths = [source_path, provenance_path, forecast_path]
    ensure_output_does_not_overwrite_inputs(output_path, input_paths)
    if not args.skip_dashboard_copy:
        ensure_output_does_not_overwrite_inputs(dashboard_output, input_paths)
        if dashboard_output.resolve() == output_path.resolve():
            raise PrecinctSpatialReferenceContractError(
                "Canonical and dashboard output paths must be distinct."
            )
    payload = build_dashboard_precinct_spatial_reference(
        source_path=source_path,
        provenance_path=provenance_path,
        forecast_path=forecast_path,
        output_path=output_path,
    )
    if not args.skip_dashboard_copy:
        dashboard_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output_path, dashboard_output)
        if output_path.read_bytes() != dashboard_output.read_bytes():
            raise PrecinctSpatialReferenceContractError(
                "Canonical and dashboard spatial-reference copies differ."
            )
    print(
        "Built Phase 7C.3 precinct spatial reference: "
        f"{payload['coverage']['featureCount']} official MultiPolygon features, "
        f"{payload['coverage']['positionCount']:,} positions."
    )
    print(f"Canonical spatial-reference data: {output_path}")
    if not args.skip_dashboard_copy:
        print(f"Frontend spatial-reference data: {dashboard_output}")


if __name__ == "__main__":
    main()

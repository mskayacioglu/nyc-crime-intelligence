import copy
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    PROJECT_ROOT
    / "src"
    / "analytics"
    / "build_dashboard_precinct_spatial_reference.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_dashboard_precinct_spatial_reference", MODULE_PATH
)
spatial = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(spatial)

SOURCE = (
    PROJECT_ROOT
    / "data"
    / "source"
    / "nyc_open_data"
    / "police_precincts_y76i-bdw7_26b.geojson"
)
PROVENANCE = (
    PROJECT_ROOT
    / "data"
    / "source"
    / "nyc_open_data"
    / "police_precincts_y76i-bdw7_26b.provenance.json"
)
FORECAST = PROJECT_ROOT / "data" / "processed" / "dashboard_forecast_map.json"


class DashboardPrecinctSpatialReferenceContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for path in (SOURCE, PROVENANCE, FORECAST):
            if not path.is_file():
                raise AssertionError(f"Required repository fixture is missing: {path}")
        cls.source_payload = json.loads(SOURCE.read_text(encoding="utf-8"))
        cls.provenance_payload = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        cls.fixture_directory = tempfile.TemporaryDirectory()
        cls.fixture_output = Path(cls.fixture_directory.name) / "spatial.json"
        cls.payload = spatial.build_dashboard_precinct_spatial_reference(
            source_path=SOURCE,
            provenance_path=PROVENANCE,
            forecast_path=FORECAST,
            output_path=cls.fixture_output,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture_directory.cleanup()

    def write_source_bundle(
        self,
        directory: Path,
        *,
        mutate_source=None,
        mutate_provenance=None,
        synchronize_integrity: bool = True,
    ) -> tuple[Path, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        source_payload = copy.deepcopy(self.source_payload)
        if mutate_source is not None:
            mutate_source(source_payload)
        source_path = directory / SOURCE.name
        source_bytes = (
            json.dumps(
                source_payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        source_path.write_bytes(source_bytes)

        provenance_payload = copy.deepcopy(self.provenance_payload)
        if synchronize_integrity:
            provenance_payload["retrieval"]["byteSize"] = len(source_bytes)
            provenance_payload["retrieval"]["sha256"] = hashlib.sha256(
                source_bytes
            ).hexdigest()
        if mutate_provenance is not None:
            mutate_provenance(provenance_payload)
        provenance_path = directory / PROVENANCE.name
        provenance_path.write_text(
            json.dumps(provenance_payload, sort_keys=True), encoding="utf-8"
        )
        return source_path, provenance_path

    def build(
        self,
        directory: Path,
        *,
        source: Path = SOURCE,
        provenance: Path = PROVENANCE,
        forecast: Path = FORECAST,
    ) -> tuple[dict, Path]:
        output = directory / "precinct-spatial-reference.json"
        payload = spatial.build_dashboard_precinct_spatial_reference(
            source_path=source,
            provenance_path=provenance,
            forecast_path=forecast,
            output_path=output,
        )
        return payload, output

    def assert_contract_error(self, callback, pattern: str | None = None) -> None:
        if pattern is None:
            with self.assertRaises(spatial.PrecinctSpatialReferenceContractError):
                callback()
        else:
            with self.assertRaisesRegex(
                spatial.PrecinctSpatialReferenceContractError, pattern
            ):
                callback()

    def test_real_authoritative_source_builds_with_exact_78_key_coverage(self) -> None:
        payload = self.payload
        persisted = json.loads(self.fixture_output.read_text(encoding="utf-8"))
        forecast = json.loads(FORECAST.read_text(encoding="utf-8"))
        forecast_keys = {
            "nypd-precinct:" + label for label in forecast["dimensions"]["precincts"]
        }
        spatial_keys = {
            feature["properties"]["locationKey"] for feature in payload["features"]
        }

        self.assertEqual(payload, persisted)
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertEqual(payload["schemaVersion"], "1.0.0")
        self.assertEqual(payload["application"], spatial.APPLICATION)
        self.assertEqual(len(payload["features"]), 78)
        self.assertEqual(spatial_keys, forecast_keys)
        self.assertEqual(len(spatial_keys), 78)
        self.assertEqual(payload["coverage"]["featureCount"], 78)
        self.assertEqual(payload["coverage"]["polygonCount"], 235)
        self.assertEqual(payload["coverage"]["ringCount"], 236)
        self.assertEqual(payload["coverage"]["positionCount"], 98060)
        self.assertTrue(payload["coverage"]["complete"])
        self.assertEqual(payload["coverage"]["missingForecastLocationKeys"], [])
        self.assertEqual(payload["coverage"]["unexpectedSpatialLocationKeys"], [])
        self.assertEqual(
            payload["provenance"]["retrieval"]["sha256"],
            "5210830afa9d0875b7a7c769edfc4d2ebe984a9ab1e36f3b7fad8508828172aa",
        )
        self.assertEqual(payload["provenance"]["retrieval"]["byteSize"], 3842773)
        self.assertEqual(
            payload["provenance"]["provenanceRecord"],
            {
                "filename": PROVENANCE.name,
                "byteSize": 2676,
                "sha256": (
                    "48c20488e785dbfff204803d86f78d86dfb9e7513372cee51a830135864e385f"
                ),
            },
        )
        self.assertEqual(
            payload["coordinateReference"]["bounds"],
            {
                "minLongitude": -74.25559136,
                "minLatitude": 40.49613399,
                "maxLongitude": -73.70000906,
                "maxLatitude": 40.91553278,
            },
        )
        self.assertEqual(payload["processing"]["coordinateRoundingDigits"], 8)
        self.assertIn(spatial.FRESHNESS_LIMITATION, payload["limitations"])
        for feature in payload["features"]:
            for polygon in feature["geometry"]["coordinates"]:
                for ring in polygon:
                    self.assertGreaterEqual(len(set(map(tuple, ring[:-1]))), 3)
        collapsed_at_seven_decimals = []
        for feature in self.source_payload["features"]:
            for polygon_index, polygon in enumerate(
                feature["geometry"]["coordinates"]
            ):
                for ring_index, ring in enumerate(polygon):
                    rounded = {
                        (round(position[0], 7), round(position[1], 7))
                        for position in ring[:-1]
                    }
                    if len(rounded) < 3:
                        collapsed_at_seven_decimals.append(
                            (
                                feature["properties"]["precinct"],
                                polygon_index,
                                ring_index,
                            )
                        )
        self.assertIn(("63", 4, 0), collapsed_at_seven_decimals)
        self.assertTrue(payload["privacy"]["administrativeBoundaryGeometryOnly"])
        self.assertFalse(payload["privacy"]["eventLevelCoordinatesIncluded"])
        self.assertFalse(payload["responsibleUse"]["riskOrDangerClassification"])
        spatial.validate_precinct_spatial_reference_payload(persisted)
        spatial.validate_canonical_output(self.fixture_output)

    def test_deterministic_canonical_output_cli_copy_and_skip_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            canonical = root / "processed" / "spatial.json"
            dashboard = root / "public" / "data" / "precinct-spatial-reference.json"
            argv = [
                "build_dashboard_precinct_spatial_reference.py",
                "--project-root",
                str(PROJECT_ROOT),
                "--source",
                str(SOURCE),
                "--provenance",
                str(PROVENANCE),
                "--forecast-map",
                str(FORECAST),
                "--output",
                str(canonical),
                "--dashboard-output",
                str(dashboard),
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
                spatial.main()
            repeat_payload, repeat = self.build(root / "repeat")
            skipped = root / "skipped.json"
            skipped_dashboard = root / "must-not-exist.json"
            skip_argv = [
                *argv[:-4],
                "--output",
                str(skipped),
                "--dashboard-output",
                str(skipped_dashboard),
                "--skip-dashboard-copy",
            ]
            with patch.object(sys, "argv", skip_argv), redirect_stdout(io.StringIO()):
                spatial.main()

            canonical_bytes = canonical.read_bytes()
            dashboard_bytes = dashboard.read_bytes()
            repeat_bytes = repeat.read_bytes()
            skipped_bytes = skipped.read_bytes()

        self.assertEqual(canonical_bytes, dashboard_bytes)
        self.assertEqual(canonical_bytes, repeat_bytes)
        self.assertEqual(canonical_bytes, skipped_bytes)
        self.assertEqual(repeat_payload, self.payload)
        self.assertFalse(skipped_dashboard.exists())
        self.assertTrue(canonical_bytes.endswith(b"\n"))
        self.assertNotIn(b"\n ", canonical_bytes)

    def test_checksum_size_provenance_schema_urls_public_use_and_privacy_are_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, provenance = self.write_source_bundle(
                root / "checksum", synchronize_integrity=False
            )
            source.write_bytes(source.read_bytes() + b" ")
            self.assert_contract_error(
                lambda: self.build(root / "checksum-output", source=source, provenance=provenance),
                "byte size|SHA-256",
            )

            cases = {
                "size": lambda value: value["retrieval"].update({"byteSize": 1}),
                "source-schema": lambda value: value["sourceSchema"].update(
                    {"geometryType": "Polygon"}
                ),
                "official-url": lambda value: value["dataset"].update(
                    {"datasetPageUrl": "https://example.com/not-official"}
                ),
                "public-use": lambda value: value["publicUse"].update(
                    {"assessment": "unknown"}
                ),
                "privacy": lambda value: value["privacy"].update(
                    {"complaintOrEventRecordsPresent": True}
                ),
                "repeat-download": lambda value: value["retrieval"].update(
                    {"repeatDownloadByteIdentical": False}
                ),
            }
            for name, mutate in cases.items():
                with self.subTest(name=name):
                    case_source, case_provenance = self.write_source_bundle(
                        root / name, mutate_provenance=mutate
                    )
                    self.assert_contract_error(
                        lambda s=case_source, p=case_provenance, n=name: self.build(
                            root / f"{n}-output", source=s, provenance=p
                        )
                    )

    def test_duplicate_missing_and_unexpected_precinct_keys_are_rejected(self) -> None:
        first_label = self.source_payload["features"][0]["properties"]["precinct"]
        cases = {
            "duplicate": lambda value: value["features"][-1]["properties"].update(
                {"precinct": first_label}
            ),
            "missing": lambda value: value["features"].pop(),
            "unexpected": lambda value: value["features"][-1]["properties"].update(
                {"precinct": "999"}
            ),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, mutate in cases.items():
                with self.subTest(name=name):
                    source, provenance = self.write_source_bundle(
                        root / name, mutate_source=mutate
                    )
                    self.assert_contract_error(
                        lambda s=source, p=provenance, n=name: self.build(
                            root / f"{n}-output", source=s, provenance=p
                        )
                    )

    def test_malformed_geometry_nesting_type_and_positions_are_rejected(self) -> None:
        def short_ring(value: dict) -> None:
            value["features"][0]["geometry"]["coordinates"][0][0] = [
                [-74.0, 40.7],
                [-74.0, 40.7],
                [-74.0, 40.7],
            ]

        def bad_position(value: dict) -> None:
            value["features"][0]["geometry"]["coordinates"][0][0][0] = [
                -74.0,
                40.7,
                5,
            ]

        def degenerate_ring(value: dict) -> None:
            value["features"][0]["geometry"]["coordinates"][0][0] = [
                [-74.0, 40.7],
                [-74.000001, 40.700001],
                [-74.000001, 40.700001],
                [-74.0, 40.7],
            ]

        def zero_area_ring(value: dict) -> None:
            value["features"][0]["geometry"]["coordinates"][0][0] = [
                [-74.0, 40.7],
                [-73.99, 40.71],
                [-73.98, 40.72],
                [-74.0, 40.7],
            ]

        cases = {
            "wrong-type": lambda value: value["features"][0]["geometry"].update(
                {"type": "Polygon"}
            ),
            "empty": lambda value: value["features"][0]["geometry"].update(
                {"coordinates": []}
            ),
            "empty-ring": lambda value: value["features"][0]["geometry"].update(
                {"coordinates": [[[]]]}
            ),
            "short-ring": short_ring,
            "bad-position": bad_position,
            "degenerate-ring": degenerate_ring,
            "zero-area-ring": zero_area_ring,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, mutate in cases.items():
                with self.subTest(name=name):
                    source, provenance = self.write_source_bundle(
                        root / name, mutate_source=mutate
                    )
                    self.assert_contract_error(
                        lambda s=source, p=provenance, n=name: self.build(
                            root / f"{n}-output", source=s, provenance=p
                        )
                    )

    def test_nonfinite_out_of_bounds_and_unclosed_rings_are_rejected(self) -> None:
        def out_of_bounds(value: dict) -> None:
            ring = value["features"][0]["geometry"]["coordinates"][0][0]
            ring[0] = [-80.0, 40.7]
            ring[-1] = [-80.0, 40.7]

        def unclosed(value: dict) -> None:
            ring = value["features"][0]["geometry"]["coordinates"][0][0]
            ring[-1] = [-74.0, 40.7]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, mutate in {
                "out-of-bounds": out_of_bounds,
                "unclosed": unclosed,
            }.items():
                with self.subTest(name=name):
                    source, provenance = self.write_source_bundle(
                        root / name, mutate_source=mutate
                    )
                    self.assert_contract_error(
                        lambda s=source, p=provenance, n=name: self.build(
                            root / f"{n}-output", source=s, provenance=p
                        )
                    )

            invalid_json_source = root / "nonfinite" / SOURCE.name
            invalid_json_source.parent.mkdir(parents=True)
            invalid_json_source.write_bytes(SOURCE.read_bytes().replace(
                b"-74.04387761573918", b"NaN", 1
            ))
            invalid_provenance = copy.deepcopy(self.provenance_payload)
            invalid_bytes = invalid_json_source.read_bytes()
            invalid_provenance["retrieval"]["byteSize"] = len(invalid_bytes)
            invalid_provenance["retrieval"]["sha256"] = hashlib.sha256(
                invalid_bytes
            ).hexdigest()
            invalid_provenance_path = invalid_json_source.parent / PROVENANCE.name
            invalid_provenance_path.write_text(
                json.dumps(invalid_provenance), encoding="utf-8"
            )
            self.assert_contract_error(
                lambda: self.build(
                    root / "nonfinite-output",
                    source=invalid_json_source,
                    provenance=invalid_provenance_path,
                ),
                "non-finite",
            )

    def test_output_validator_rejects_order_schema_geometry_privacy_and_forbidden_fields(
        self,
    ) -> None:
        cases = {}

        def swapped(value: dict) -> None:
            value["features"][0], value["features"][1] = (
                value["features"][1],
                value["features"][0],
            )

        def nonfinite(value: dict) -> None:
            value["features"][0]["geometry"]["coordinates"][0][0][0][0] = float(
                "nan"
            )

        def unrounded(value: dict) -> None:
            ring = value["features"][0]["geometry"]["coordinates"][0][0]
            ring[0][0] = -74.043877611
            ring[-1][0] = -74.043877611

        def forbidden(value: dict) -> None:
            value["features"][0]["properties"]["vic_race"] = "withheld"

        cases.update(
            {
                "order": swapped,
                "nonfinite": nonfinite,
                "unrounded": unrounded,
                "forbidden": forbidden,
                "privacy": lambda value: value["privacy"].update(
                    {"eventLevelCoordinatesIncluded": True}
                ),
                "coverage": lambda value: value["coverage"].update(
                    {"featureCount": 77}
                ),
                "simplification": lambda value: value["processing"].update(
                    {"simplificationApplied": True}
                ),
            }
        )
        for name, mutate in cases.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(self.payload)
                mutate(changed)
                self.assert_contract_error(
                    lambda value=changed: spatial.validate_precinct_spatial_reference_payload(
                        value
                    )
                )

    def test_canonical_file_validator_rejects_pretty_or_noncanonical_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "pretty.json"
            output.write_text(json.dumps(self.payload, indent=2), encoding="utf-8")
            self.assert_contract_error(
                lambda: spatial.validate_canonical_output(output), "not canonical JSON"
            )

    def test_output_path_collision_raises_before_write_and_preserves_source(self) -> None:
        original = SOURCE.read_bytes()
        self.assert_contract_error(
            lambda: spatial.build_dashboard_precinct_spatial_reference(
                source_path=SOURCE,
                provenance_path=PROVENANCE,
                forecast_path=FORECAST,
                output_path=SOURCE,
            ),
            "must not overwrite",
        )
        self.assertEqual(SOURCE.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

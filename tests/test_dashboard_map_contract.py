import importlib.util
import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Any
from unittest import mock


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "analytics"
    / "build_dashboard_map.py"
)
SPEC = importlib.util.spec_from_file_location("build_dashboard_map", MODULE_PATH)
build_dashboard_map = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_dashboard_map)


class DashboardMapContractTest(unittest.TestCase):
    def write_inputs(
        self, directory: Path, *, safe_end: date = date(2024, 1, 14)
    ) -> dict[str, Any]:
        directory.mkdir(parents=True, exist_ok=True)
        paths = {
            "clean": directory / "aggregate_safe_source.parquet",
            "hotspots": directory / "hotspots.parquet",
            "metrics": directory / "hotspot_metrics.json",
            "stats": {
                "sourceCount": 3,
                "safeCount": 2,
                "startDate": date(2024, 1, 1),
                "endDate": safe_end,
            },
        }
        duckdb = build_dashboard_map.require_duckdb()
        con = duckdb.connect(database=":memory:")
        con.execute(
            """
            CREATE TABLE hotspot_input (
                rank_overall BIGINT,
                hotspot_grain VARCHAR,
                borough VARCHAR,
                precinct VARCHAR,
                grid_latitude DOUBLE,
                grid_longitude DOUBLE,
                offense_type VARCHAR,
                law_category VARCHAR,
                map_latitude DOUBLE,
                map_longitude DOUBLE,
                recent_window_days INTEGER,
                baseline_window_days INTEGER,
                scoring_end_date DATE,
                recent_event_count BIGINT,
                baseline_expected_recent_count DOUBLE,
                recent_vs_baseline_lift_pct DOUBLE,
                composite_score DOUBLE,
                coordinate_coverage_pct DOUBLE,
                is_hotspot BOOLEAN,
                hotspot_severity VARCHAR
            )
            """
        )
        con.executemany(
            "INSERT INTO hotspot_input VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    1,
                    "grid",
                    "BRONX",
                    None,
                    40.845,
                    -73.905,
                    "THEFT",
                    "FELONY",
                    40.845,
                    -73.905,
                    30,
                    365,
                    safe_end,
                    9,
                    5.48,
                    64.25,
                    91.5,
                    100.0,
                    True,
                    "critical",
                ),
                (
                    2,
                    "precinct",
                    "BROOKLYN",
                    "2",
                    None,
                    None,
                    "ASSAULT",
                    "MISDEMEANOR",
                    40.675,
                    -73.985,
                    30,
                    365,
                    safe_end,
                    3,
                    4.0,
                    -25.0,
                    68.0,
                    99.0,
                    True,
                    "high",
                ),
            ],
        )
        con.execute(
            f"COPY hotspot_input TO {build_dashboard_map.sql_string(paths['hotspots'])} "
            "(FORMAT PARQUET)"
        )
        con.close()
        paths["metrics"].write_text(
            json.dumps(
                {
                    "phase": "Phase 6B",
                    "hotspot_config": {"grid_size_degrees": 0.01},
                    "analysis_window": {
                        "scoring_end_date": safe_end.isoformat(),
                        "recent_window_days": 30,
                        "baseline_window_days": 365,
                    },
                }
            ),
            encoding="utf-8",
        )
        return paths

    def relation_copy(
        self, source: Path, output: Path, statements: list[str]
    ) -> Path:
        duckdb = build_dashboard_map.require_duckdb()
        con = duckdb.connect(database=":memory:")
        con.execute(
            f"CREATE TABLE changed AS SELECT * FROM read_parquet("
            f"{build_dashboard_map.sql_string(source)})"
        )
        for statement in statements:
            con.execute(statement)
        con.execute(
            f"COPY changed TO {build_dashboard_map.sql_string(output)} (FORMAT PARQUET)"
        )
        con.close()
        return output

    def test_aggregate_safe_stats_uses_aggregate_summary_without_event_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clean_path = Path(tmp) / "aggregate-safe-source.parquet"
            clean_path.write_bytes(b"")
            aggregate_row = {
                "source_count": 3,
                "safe_count": 2,
                "safe_missing_date_count": 0,
                "safe_start_date": date(2024, 1, 1),
                "safe_end_date": date(2024, 1, 14),
            }
            with (
                mock.patch.object(
                    build_dashboard_map,
                    "parquet_columns",
                    return_value=build_dashboard_map.CLEAN_REQUIRED_COLUMNS,
                ),
                mock.patch.object(
                    build_dashboard_map,
                    "fetch_dicts",
                    return_value=[aggregate_row],
                ),
            ):
                stats = build_dashboard_map.aggregate_safe_stats(object(), clean_path)
            with mock.patch.object(
                build_dashboard_map,
                "parquet_columns",
                return_value=["complaint_from_date"],
            ):
                with self.assertRaisesRegex(ValueError, "missing required columns"):
                    build_dashboard_map.aggregate_safe_stats(object(), clean_path)

        self.assertEqual(stats["sourceCount"], 3)
        self.assertEqual(stats["safeCount"], 2)
        self.assertEqual(stats["startDate"], date(2024, 1, 1))
        self.assertEqual(stats["endDate"], date(2024, 1, 14))

    def build(
        self,
        paths: dict[str, Any],
        output: Path,
        **overrides: Any,
    ) -> tuple[dict, Path]:
        actual = dict(paths)
        actual.update(overrides)
        with mock.patch.object(
            build_dashboard_map,
            "aggregate_safe_stats",
            return_value=actual["stats"],
        ) as aggregate_stats:
            payload = build_dashboard_map.build_dashboard_map(
                clean_events_path=actual["clean"],
                hotspots_path=actual["hotspots"],
                hotspot_metrics_path=actual["metrics"],
                output_path=output,
                threads=1,
            )
        aggregate_stats.assert_called_once()
        return payload, output

    def test_schema_indexes_grains_labels_coordinates_and_filter_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, output = self.build(
                self.write_inputs(root / "inputs"), root / "map.json"
            )
            ends_with_newline = output.read_bytes().endswith(b"\n")
        self.assertEqual(payload["schemaVersion"], "1.0.0")
        self.assertEqual(
            payload["hotspots"]["rowColumns"],
            build_dashboard_map.HOTSPOT_ROW_COLUMNS,
        )
        self.assertEqual(payload["hotspots"]["status"], "available")
        self.assertEqual(payload["hotspots"]["summary"]["rowCount"], 2)
        self.assertEqual(payload["hotspots"]["summary"]["gridSizeDegrees"], 0.01)
        self.assertEqual(payload["dimensions"]["hotspotGrains"], ["grid", "precinct"])
        columns = payload["hotspots"]["rowColumns"]
        decoded = []
        for row in payload["hotspots"]["rows"]:
            item = dict(zip(columns, row))
            item["grain"] = payload["dimensions"]["hotspotGrains"][item["grainIndex"]]
            decoded.append(item)
        grid, precinct = decoded
        self.assertEqual(grid["grain"], "grid")
        self.assertIsNone(grid["precinctIndex"])
        self.assertEqual((grid["latitude"], grid["longitude"]), (40.845, -73.905))
        self.assertEqual(grid["locationLabel"], "GRID 40.8450, -73.9050 · BRONX")
        self.assertEqual(precinct["grain"], "precinct")
        self.assertIsInstance(precinct["precinctIndex"], int)
        self.assertEqual(precinct["locationLabel"], "PRECINCT 2 · BROOKLYN")
        index = payload["filterIndex"]["precinctsByBorough"]
        self.assertEqual(index["rowColumns"], ["boroughIndex", "precinctIndexes"])
        self.assertEqual(len(index["rows"]), 2)
        self.assertTrue(ends_with_newline)

    def test_output_is_deterministic_and_compact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            first = self.build(paths, root / "first.json")
            second = self.build(paths, root / "second.json")
            first_bytes = first[1].read_bytes()
            second_bytes = second[1].read_bytes()
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(first[0]["generatedAtUtc"], "2024-01-14T00:00:00Z")
        self.assertNotIn(b"\n ", first_bytes)

    def test_data_range_uses_aggregate_safe_stats_without_event_fixture_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, _ = self.build(
                self.write_inputs(root / "inputs"), root / "map.json"
            )
        self.assertEqual(payload["dataRange"]["aggregateSafeEventCount"], 2)
        self.assertEqual(payload["dataRange"]["sourceEventCount"], 3)
        self.assertEqual(payload["dataRange"]["excludedEventCount"], 1)
        self.assertEqual(payload["dataRange"]["safeEventEndDate"], "2024-01-14")
        self.assertTrue(payload["ethics"]["aggregateTrendIntelligenceOnly"])
        self.assertFalse(payload["ethics"]["eventRecordsIncluded"])

    def test_negative_lift_is_preserved_and_numbers_are_not_clamped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, _ = self.build(
                self.write_inputs(root / "inputs"), root / "map.json"
            )
        lift_index = payload["hotspots"]["rowColumns"].index("liftPct")
        score_index = payload["hotspots"]["rowColumns"].index("score")
        self.assertEqual(payload["hotspots"]["rows"][1][lift_index], -25)
        self.assertEqual(payload["hotspots"]["rows"][0][score_index], 91.5)

    def test_missing_and_valid_empty_hotspots_degrade_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            missing_payload, _ = self.build(
                paths,
                root / "missing.json",
                hotspots=root / "does-not-exist.parquet",
            )
            empty = self.relation_copy(
                paths["hotspots"], root / "empty.parquet", ["DELETE FROM changed"]
            )
            empty_payload, _ = self.build(
                paths, root / "empty.json", hotspots=empty
            )
        self.assertEqual(missing_payload["hotspots"]["status"], "missing")
        self.assertEqual(missing_payload["hotspots"]["rows"], [])
        self.assertTrue(missing_payload["hotspots"]["reason"])
        self.assertEqual(empty_payload["hotspots"]["status"], "available")
        self.assertEqual(empty_payload["hotspots"]["rows"], [])
        self.assertIsNone(empty_payload["hotspots"]["summary"]["scoringEndDate"])

    def test_duplicate_future_mixed_and_null_snapshots_are_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            cases = {
                "duplicate": ["INSERT INTO changed SELECT * FROM changed WHERE rank_overall = 1"],
                "future": ["UPDATE changed SET scoring_end_date = DATE '2024-01-15'"],
                "mixed": [
                    "UPDATE changed SET scoring_end_date = DATE '2024-01-13' WHERE rank_overall = 2"
                ],
                "null": [
                    "UPDATE changed SET scoring_end_date = NULL WHERE rank_overall = 2"
                ],
            }
            payloads = {}
            for name, statements in cases.items():
                changed = self.relation_copy(
                    paths["hotspots"], root / f"{name}.parquet", statements
                )
                payloads[name] = self.build(
                    paths, root / f"{name}.json", hotspots=changed
                )[0]
        for name, payload in payloads.items():
            self.assertEqual(payload["hotspots"]["status"], "invalid", name)
            self.assertEqual(payload["hotspots"]["rows"], [], name)
            self.assertTrue(payload["hotspots"].get("reason"), name)
        self.assertIn("Duplicate", payloads["duplicate"]["hotspots"]["reason"])
        self.assertIn("cannot exceed", payloads["future"]["hotspots"]["reason"])
        self.assertIn("exactly one", payloads["mixed"]["hotspots"]["reason"])
        self.assertIn("missing scoring date", payloads["null"]["hotspots"]["reason"])

    def test_stale_snapshot_is_withheld_with_explicit_currentness_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs", safe_end=date(2024, 1, 14))
            stale = self.relation_copy(
                paths["hotspots"],
                root / "stale.parquet",
                ["UPDATE changed SET scoring_end_date = DATE '2024-01-12'"],
            )
            payload, _ = self.build(paths, root / "map.json", hotspots=stale)
        self.assertEqual(payload["hotspots"]["status"], "stale")
        self.assertEqual(payload["hotspots"]["rows"], [])
        self.assertEqual(payload["hotspots"]["summary"]["snapshotAgeDays"], 2)
        self.assertEqual(payload["hotspots"]["summary"]["currentMaxAgeDays"], 1)
        self.assertIn("2 days older", payload["hotspots"]["reason"])

    def test_invalid_numeric_values_are_rejected_without_clamping(self) -> None:
        for value in (None, float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(build_dashboard_map.MapContractError):
                build_dashboard_map.required_number(value, "test")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            cases = {
                "nan": [
                    "UPDATE changed SET composite_score = CAST('NaN' AS DOUBLE) WHERE rank_overall = 1"
                ],
                "over": ["UPDATE changed SET composite_score = 101 WHERE rank_overall = 1"],
                "negative_count": [
                    "UPDATE changed SET recent_event_count = -1 WHERE rank_overall = 1"
                ],
                "coverage": [
                    "UPDATE changed SET coordinate_coverage_pct = 100.1 WHERE rank_overall = 1"
                ],
            }
            for name, statements in cases.items():
                changed = self.relation_copy(
                    paths["hotspots"], root / f"{name}.parquet", statements
                )
                payload, _ = self.build(
                    paths, root / f"{name}.json", hotspots=changed
                )
                self.assertEqual(payload["hotspots"]["status"], "invalid", name)
                self.assertEqual(payload["hotspots"]["rows"], [], name)

    def test_grain_specific_fields_bounds_and_unsupported_values_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            cases = {
                "grid_precinct": [
                    "UPDATE changed SET precinct = '1' WHERE hotspot_grain = 'grid'"
                ],
                "precinct_grid": [
                    "UPDATE changed SET grid_latitude = 40.675 WHERE hotspot_grain = 'precinct'"
                ],
                "outside": [
                    "UPDATE changed SET map_latitude = 41 WHERE rank_overall = 1"
                ],
                "grain": [
                    "UPDATE changed SET hotspot_grain = 'address' WHERE rank_overall = 1"
                ],
                "severity": [
                    "UPDATE changed SET hotspot_severity = 'urgent' WHERE rank_overall = 1"
                ],
                "unsafe_flag": [
                    "UPDATE changed SET is_hotspot = FALSE WHERE rank_overall = 1"
                ],
            }
            for name, statements in cases.items():
                changed = self.relation_copy(
                    paths["hotspots"], root / f"{name}.parquet", statements
                )
                payload, _ = self.build(
                    paths, root / f"{name}.json", hotspots=changed
                )
                self.assertEqual(payload["hotspots"]["status"], "invalid", name)
                self.assertEqual(payload["hotspots"]["rows"], [], name)

    def test_missing_required_and_unsafe_columns_are_withheld(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            missing = self.relation_copy(
                paths["hotspots"],
                root / "missing-column.parquet",
                ["ALTER TABLE changed DROP COLUMN map_longitude"],
            )
            missing_payload, _ = self.build(
                paths, root / "missing-column.json", hotspots=missing
            )
            unsafe = self.relation_copy(
                paths["hotspots"],
                root / "unsafe-column.parquet",
                ["ALTER TABLE changed ADD COLUMN SUSP_RACE VARCHAR"],
            )
            unsafe_payload, _ = self.build(
                paths, root / "unsafe-column.json", hotspots=unsafe
            )
        self.assertEqual(missing_payload["hotspots"]["status"], "invalid")
        self.assertIn("Missing required columns", missing_payload["hotspots"]["reason"])
        self.assertEqual(unsafe_payload["hotspots"]["status"], "invalid")
        self.assertIn("unsafe event-level", unsafe_payload["hotspots"]["reason"])

    def test_metrics_are_optional_and_never_invalidate_valid_hotspots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            missing_payload, _ = self.build(
                paths,
                root / "missing-metrics.json",
                metrics=root / "does-not-exist.json",
            )
            malformed = root / "malformed.json"
            malformed.write_text("{not-json", encoding="utf-8")
            malformed_payload, _ = self.build(
                paths, root / "malformed-map.json", metrics=malformed
            )
            undecodable = root / "undecodable.json"
            undecodable.write_bytes(b"\xff\xfe\x00")
            undecodable_payload, _ = self.build(
                paths, root / "undecodable-map.json", metrics=undecodable
            )
            mismatch = root / "mismatch.json"
            mismatch.write_text(
                json.dumps(
                    {
                        "hotspot_config": {"grid_size_degrees": 0.02},
                        "analysis_window": {"scoring_end_date": "2024-01-13"},
                    }
                ),
                encoding="utf-8",
            )
            mismatch_payload, _ = self.build(
                paths, root / "mismatch-map.json", metrics=mismatch
            )
        self.assertEqual(missing_payload["hotspots"]["status"], "available")
        self.assertEqual(missing_payload["methodology"]["status"], "missing")
        self.assertIsNone(missing_payload["hotspots"]["summary"]["gridSizeDegrees"])
        self.assertEqual(malformed_payload["hotspots"]["status"], "available")
        self.assertEqual(malformed_payload["methodology"]["status"], "invalid")
        self.assertEqual(undecodable_payload["hotspots"]["status"], "available")
        self.assertEqual(undecodable_payload["methodology"]["status"], "invalid")
        self.assertEqual(mismatch_payload["hotspots"]["status"], "available")
        self.assertEqual(mismatch_payload["methodology"]["status"], "invalid")

    def test_final_payload_validation_rejects_bad_indexes_duplicates_and_nonfinite_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, _ = self.build(
                self.write_inputs(root / "inputs"), root / "map.json"
            )
        invalid_index = copy.deepcopy(payload)
        invalid_index["hotspots"]["rows"][0][1] = 999
        with self.assertRaises(ValueError):
            build_dashboard_map.validate_map_payload(invalid_index)
        duplicate = copy.deepcopy(payload)
        duplicate["hotspots"]["rows"][1][0] = duplicate["hotspots"]["rows"][0][0]
        with self.assertRaises(ValueError):
            build_dashboard_map.validate_map_payload(duplicate)
        nonfinite = copy.deepcopy(payload)
        nonfinite["hotspots"]["rows"][0][12] = float("nan")
        with self.assertRaises(ValueError):
            build_dashboard_map.validate_map_payload(nonfinite)


if __name__ == "__main__":
    unittest.main()

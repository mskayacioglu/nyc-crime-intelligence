import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "src" / "analytics" / "build_dashboard_forecast_map.py"
SPEC = importlib.util.spec_from_file_location("build_dashboard_forecast_map", MODULE_PATH)
build_dashboard_forecast_map = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_dashboard_forecast_map)


class DashboardForecastMapContractTest(unittest.TestCase):
    def write_inputs(self, directory: Path) -> dict[str, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        paths = {
            "weekly": directory / "crime_weekly_area.parquet",
            "overview": directory / "dashboard_overview.json",
            "forecast": directory / "ml_predictions.parquet",
            "metrics": directory / "ml_metrics.json",
            "manifest": directory / "ml_model_manifest.json",
            "baseline": directory / "baseline_predictions.parquet",
            "baseline_manifest": directory / "baseline_model_manifest.json",
        }
        duckdb = build_dashboard_forecast_map.require_duckdb()
        con = duckdb.connect(database=":memory:")
        con.execute(
            """
            CREATE TABLE weekly_input (
                week_start DATE,
                borough VARCHAR,
                precinct VARCHAR,
                offense_type VARCHAR,
                law_category VARCHAR,
                crime_count BIGINT
            )
            """
        )
        weeks = [date(2023, 11, 20) + timedelta(weeks=index) for index in range(8)]
        weekly_rows = [
            (week, "BRONX", "1", "THEFT", "FELONY", index + 1)
            for index, week in enumerate(weeks)
        ]
        weekly_rows.extend(
            (week, "BROOKLYN", "2", "ASSAULT", "MISDEMEANOR", 2)
            for week in weeks
        )
        # This segment begins too recently for a complete eight-week prior baseline.
        weekly_rows.extend(
            [
                (date(2024, 1, 1), "BRONX", "1", "UNKNOWN", "VIOLATION", 1),
                (date(2024, 1, 8), "BRONX", "1", "UNKNOWN", "VIOLATION", 0),
            ]
        )
        con.executemany(
            "INSERT INTO weekly_input VALUES (?, ?, ?, ?, ?, ?)", weekly_rows
        )
        con.execute(
            f"COPY weekly_input TO "
            f"{build_dashboard_forecast_map.sql_string(paths['weekly'])} (FORMAT PARQUET)"
        )

        con.execute(
            """
            CREATE TABLE forecast_input (
                week_start DATE,
                borough VARCHAR,
                precinct VARCHAR,
                offense_type VARCHAR,
                law_category VARCHAR,
                predicted_crime_count DOUBLE,
                ml_model_name VARCHAR,
                is_next_week_forecast BOOLEAN
            )
            """
        )
        # Deliberately insert out of order; the contract must canonicalize ordering.
        con.executemany(
            "INSERT INTO forecast_input VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    date(2024, 1, 15),
                    "BROOKLYN",
                    "2",
                    "ASSAULT",
                    "MISDEMEANOR",
                    2.5,
                    "fixture_model",
                    True,
                ),
                (
                    date(2024, 1, 15),
                    "BRONX",
                    "1",
                    "UNKNOWN",
                    "VIOLATION",
                    0.0,
                    "fixture_model",
                    True,
                ),
                (
                    date(2024, 1, 15),
                    "BRONX",
                    "1",
                    "THEFT",
                    "FELONY",
                    6.0,
                    "fixture_model",
                    True,
                ),
            ],
        )
        con.execute(
            f"COPY forecast_input TO "
            f"{build_dashboard_forecast_map.sql_string(paths['forecast'])} (FORMAT PARQUET)"
        )

        con.execute(
            """
            CREATE TABLE baseline_input (
                week_start DATE,
                borough VARCHAR,
                precinct VARCHAR,
                offense_type VARCHAR,
                law_category VARCHAR,
                trailing_8_week_mean DOUBLE,
                is_next_week_forecast BOOLEAN
            )
            """
        )
        con.executemany(
            "INSERT INTO baseline_input VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    date(2024, 1, 15),
                    "BRONX",
                    "1",
                    "THEFT",
                    "FELONY",
                    4.5,
                    True,
                ),
                (
                    date(2024, 1, 15),
                    "BROOKLYN",
                    "2",
                    "ASSAULT",
                    "MISDEMEANOR",
                    2.0,
                    True,
                ),
                (
                    date(2024, 1, 15),
                    "BRONX",
                    "1",
                    "UNKNOWN",
                    "VIOLATION",
                    None,
                    True,
                ),
            ],
        )
        con.execute(
            f"COPY baseline_input TO "
            f"{build_dashboard_forecast_map.sql_string(paths['baseline'])} (FORMAT PARQUET)"
        )
        con.close()

        paths["overview"].write_text(
            json.dumps(
                {
                    "schemaVersion": "1.0.0",
                    "generatedAtUtc": "2024-01-10T00:00:00Z",
                    "dataRange": {
                        "safeEventStartDate": "2023-11-20",
                        "safeEventEndDate": "2024-01-10",
                        "firstWeek": "2023-11-20",
                        "lastWeek": "2024-01-08",
                        "latestCompleteWeek": "2024-01-01",
                        "latestWeekIsPartial": True,
                    },
                    "dimensions": {
                        "boroughs": ["BRONX", "BROOKLYN"],
                        "precincts": ["1", "2"],
                    },
                    "filterIndex": {
                        "precinctsByBorough": {
                            "rowColumns": ["boroughIndex", "precinctIndexes"],
                            "rows": [[0, [0]], [1, [1]]],
                        }
                    },
                    "ethics": {
                        "aggregateTrendIntelligenceOnly": True,
                        "eventRecordsIncluded": False,
                        "demographicAttributesIncluded": False,
                        "personLevelScoring": False,
                        "enforcementRecommendations": False,
                        "patrolRecommendations": False,
                    },
                }
            ),
            encoding="utf-8",
        )
        paths["manifest"].write_text(
            json.dumps(
                {
                    "generated_at_utc": "2024-02-01T12:34:56.123456+00:00",
                    "artifact_type": "weekly_forecast_ml_model",
                    "artifact_version": 1,
                    "segment_keys": [
                        "borough",
                        "precinct",
                        "offense_type",
                        "law_category",
                    ],
                    "model": {"model_name": "fixture_model", "model_version": 1},
                    "training_window": {
                        "min_week_start": "2023-11-20",
                        "max_week_start": "2024-01-08",
                        "segment_count": 3,
                    },
                    "forecast_week": "2024-01-15",
                    "backtest_window": {
                        "backtest_start_week": "2024-01-01",
                        "backtest_end_week": "2024-01-01",
                        "backtest_rows": 3,
                    },
                    "overall_metrics": [
                        {
                            "prediction_count": 3,
                            "total_backtest_rows": 3,
                            "prediction_coverage_pct": 100.0,
                            "mae": 0.5,
                            "rmse": 1.25,
                            "weighted_mae": 2.5,
                        }
                    ],
                    "leakage_controls": {
                        "random_splits_used": False,
                        "target_week_excluded_from_features": True,
                    },
                    "feature_policy": {
                        "person_level_prediction": False,
                        "enforcement_recommendations": False,
                    },
                }
            ),
            encoding="utf-8",
        )
        paths["metrics"].write_text(
            json.dumps(
                {
                    "generated_at_utc": "2024-02-01T12:34:56.123456+00:00",
                    "model_config": {
                        "model_name": "fixture_model",
                        "model_version": 1,
                    },
                    "analysis_window": {
                        "max_week_start": "2024-01-08",
                        "next_week_forecast_week": "2024-01-15",
                        "backtest_start_week": "2024-01-01",
                        "backtest_end_week": "2024-01-01",
                    },
                    "record_counts": {
                        "output_rows": 6,
                        "backtest_rows": 3,
                        "next_week_forecast_rows": 3,
                        "output_segment_count": 3,
                        "backtest_actual_event_count": 10,
                    },
                    "metrics": {
                        "overall": [
                            {
                                "prediction_count": 3,
                                "total_backtest_rows": 3,
                                "mae": 0.5,
                                "rmse": 1.25,
                                "weighted_mae": 2.5,
                                "prediction_coverage_pct": 100.0,
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        paths["baseline_manifest"].write_text(
            json.dumps(
                {
                    "artifact_type": "baseline_forecast_model",
                    "artifact_version": 1,
                    "segment_keys": [
                        "borough",
                        "precinct",
                        "offense_type",
                        "law_category",
                    ],
                    "training_window": {
                        "min_week_start": "2023-11-20",
                        "max_week_start": "2024-01-08",
                        "segment_count": 3,
                    },
                    "forecast_week": "2024-01-15",
                    "selected_baseline": {
                        "baseline_method": "trailing_8_week_mean"
                    },
                    "baseline_model_rules": [
                        {
                            "baseline_method": "trailing_8_week_mean",
                            "rule": (
                                "Use the arithmetic mean of the prior 8 weekly crime_count "
                                "values for the same segment."
                            ),
                            "required_prior_weeks": 8,
                        }
                    ],
                    "leakage_controls": {
                        "target_week_excluded_from_features": True,
                        "zero_fill_rule": (
                            "Missing weekly rows are treated as zero crime_count after a "
                            "segment's first observed week."
                        ),
                    },
                    "feature_policy": {
                        "person_level_prediction": False,
                        "enforcement_recommendations": False,
                    },
                }
            ),
            encoding="utf-8",
        )
        return paths

    def relation_copy(
        self, source: Path, output: Path, statements: list[str]
    ) -> Path:
        duckdb = build_dashboard_forecast_map.require_duckdb()
        con = duckdb.connect(database=":memory:")
        con.execute(
            f"CREATE TABLE changed AS SELECT * FROM read_parquet("
            f"{build_dashboard_forecast_map.sql_string(source)})"
        )
        for statement in statements:
            con.execute(statement)
        con.execute(
            f"COPY changed TO {build_dashboard_forecast_map.sql_string(output)} "
            "(FORMAT PARQUET)"
        )
        con.close()
        return output

    def json_copy(self, source: Path, output: Path, mutate) -> Path:
        payload = json.loads(source.read_text(encoding="utf-8"))
        mutate(payload)
        output.write_text(json.dumps(payload), encoding="utf-8")
        return output

    def build(
        self,
        paths: dict[str, Path],
        output: Path,
        **overrides: Path,
    ) -> tuple[dict, Path]:
        actual = dict(paths)
        actual.update(overrides)
        payload = build_dashboard_forecast_map.build_dashboard_forecast_map(
            weekly_path=actual["weekly"],
            overview_path=actual["overview"],
            ml_predictions_path=actual["forecast"],
            ml_metrics_path=actual["metrics"],
            ml_manifest_path=actual["manifest"],
            baseline_predictions_path=actual["baseline"],
            baseline_manifest_path=actual["baseline_manifest"],
            output_path=output,
            threads=1,
        )
        return payload, output

    @staticmethod
    def decoded_rows(payload: dict) -> list[dict]:
        columns = payload["forecast"]["rowColumns"]
        return [dict(zip(columns, row)) for row in payload["forecast"]["rows"]]

    def test_fixture_schema_order_horizon_mapping_baseline_and_location_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, output = self.build(
                self.write_inputs(root / "inputs"), root / "forecast-map.json"
            )
            serialized = output.read_text(encoding="utf-8").upper()
            ends_with_newline = output.read_bytes().endswith(b"\n")

        self.assertEqual(payload["schemaVersion"], "1.0.0")
        self.assertEqual(payload["generatedAtUtc"], "2024-01-10T00:00:00Z")
        self.assertEqual(payload["dataRange"]["latestObservedWeek"], "2024-01-08")
        self.assertEqual(payload["dataRange"]["latestCompleteWeek"], "2024-01-01")
        self.assertEqual(payload["dimensions"]["forecastWeeks"], ["2024-01-15"])
        self.assertEqual(payload["dataRange"]["supportedForecastWeeks"], ["2024-01-15"])
        self.assertEqual(payload["forecast"]["rowColumns"], build_dashboard_forecast_map.ROW_COLUMNS)
        self.assertEqual(payload["forecast"]["status"], "available")
        self.assertFalse(payload["forecast"]["isEmpty"])
        self.assertEqual(payload["forecast"]["summary"]["rowCount"], 3)
        self.assertEqual(
            payload["model"]["artifactGeneratedAtUtc"],
            "2024-02-01T12:34:56.123456+00:00",
        )
        self.assertEqual(
            payload["model"]["independentTrainingTime"],
            build_dashboard_forecast_map.INDEPENDENT_TRAINING_TIME,
        )

        keys = [tuple(row[:5]) for row in payload["forecast"]["rows"]]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(keys), len(set(keys)))
        dimensions = payload["dimensions"]
        mappings = {
            dimensions["boroughs"][borough_index]: {
                dimensions["precincts"][precinct_index]
                for precinct_index in precinct_indexes
            }
            for borough_index, precinct_indexes in payload["filterIndex"][
                "precinctsByBorough"
            ]["rows"]
        }
        self.assertEqual(mappings, {"BRONX": {"1"}, "BROOKLYN": {"2"}})

        decoded = self.decoded_rows(payload)
        by_location = {row["precinctLocationKey"]: row for row in decoded}
        self.assertEqual(set(by_location), {"nypd-precinct:1", "nypd-precinct:2"})
        theft = next(row for row in decoded if row["predictedCount"] == 6)
        self.assertEqual(theft["historicalBaseline"], 4.5)
        self.assertEqual(theft["expectedChangeCount"], 1.5)
        self.assertEqual(theft["expectedChangePct"], 33.333333)
        nullable = next(
            row
            for row in decoded
            if dimensions["offenseTypes"][row["offenseTypeIndex"]] == "UNKNOWN"
        )
        self.assertIsNone(nullable["historicalBaseline"])
        self.assertIsNone(nullable["expectedChangeCount"])
        self.assertIsNone(nullable["expectedChangePct"])
        self.assertEqual(payload["baseline"]["valueAvailability"], "partial")
        self.assertTrue(payload["baseline"]["priorOnly"])
        self.assertEqual(payload["availability"]["predictionIntervals"], "unavailable")
        self.assertEqual(
            payload["availability"]["precinctSpatialReference"], "location-key-only"
        )
        self.assertTrue(ends_with_newline)
        for forbidden in (
            "COMPLAINT_NUMBER",
            "SOURCE_ROW_ID",
            "EVENT_LATITUDE",
            "EVENT_LONGITUDE",
            "VIC_RACE",
            "SUSP_RACE",
            "PATROL_RECOMMENDATION",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_cli_copies_canonical_bytes_and_repeated_builds_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            canonical = root / "processed" / "dashboard_forecast_map.json"
            dashboard_dir = root / "dashboard" / "public" / "data"
            argv = [
                "build_dashboard_forecast_map.py",
                "--project-root",
                str(root),
                "--dashboard-data-dir",
                str(dashboard_dir),
                "--weekly-area",
                str(paths["weekly"]),
                "--overview",
                str(paths["overview"]),
                "--ml-predictions",
                str(paths["forecast"]),
                "--ml-metrics",
                str(paths["metrics"]),
                "--ml-manifest",
                str(paths["manifest"]),
                "--baseline-predictions",
                str(paths["baseline"]),
                "--baseline-manifest",
                str(paths["baseline_manifest"]),
                "--output",
                str(canonical),
                "--threads",
                "1",
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
                build_dashboard_forecast_map.main()
            dashboard_copy = dashboard_dir / "forecast-map.json"
            repeat = root / "repeat.json"
            self.build(paths, repeat)
            canonical_bytes = canonical.read_bytes()
            dashboard_bytes = dashboard_copy.read_bytes()
            repeat_bytes = repeat.read_bytes()

        self.assertEqual(canonical_bytes, dashboard_bytes)
        self.assertEqual(canonical_bytes, repeat_bytes)
        self.assertNotIn(b"\n ", canonical_bytes)

    def test_real_repository_artifacts_build_and_validate(self) -> None:
        paths = {
            "weekly": PROJECT_ROOT / "data/processed/crime_weekly_area.parquet",
            "overview": PROJECT_ROOT / "data/processed/dashboard_overview.json",
            "forecast": PROJECT_ROOT / "data/processed/ml_predictions.parquet",
            "metrics": PROJECT_ROOT / "data/processed/ml_metrics.json",
            "manifest": PROJECT_ROOT / "models/weekly_forecast/model_manifest.json",
            "baseline": PROJECT_ROOT / "data/processed/baseline_predictions.parquet",
            "baseline_manifest": (
                PROJECT_ROOT / "models/baseline_forecast/model_manifest.json"
            ),
        }
        for path in paths.values():
            self.assertTrue(path.is_file(), f"Required repository fixture is missing: {path}")
        with tempfile.TemporaryDirectory() as tmp:
            payload, output = self.build(paths, Path(tmp) / "forecast-map.json")
            persisted = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["forecast"]["status"], "available")
        self.assertGreater(payload["forecast"]["summary"]["rowCount"], 0)
        self.assertEqual(len(payload["dimensions"]["forecastWeeks"]), 1)
        forecast_week = date.fromisoformat(payload["dimensions"]["forecastWeeks"][0])
        latest_observed = date.fromisoformat(payload["dataRange"]["latestObservedWeek"])
        self.assertEqual(forecast_week, latest_observed + timedelta(weeks=1))
        self.assertEqual(payload["model"]["forecastWeek"], forecast_week.isoformat())
        self.assertEqual(
            payload["model"]["artifactGeneratedAtUtc"],
            "2026-07-05T12:40:05.068774+00:00",
        )
        self.assertEqual(
            payload["model"]["independentTrainingTime"],
            {
                "status": "unavailable",
                "timestamp": None,
                "reason": (
                    "No independent training-completion timestamp is recorded."
                ),
            },
        )
        self.assertEqual(payload, persisted)
        build_dashboard_forecast_map.validate_forecast_map_payload(persisted)

    def test_missing_invalid_stale_and_available_empty_forecast_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            missing, _ = self.build(
                paths,
                root / "missing.json",
                forecast=root / "missing-predictions.parquet",
            )
            malformed = self.relation_copy(
                paths["forecast"],
                root / "malformed.parquet",
                ["ALTER TABLE changed DROP COLUMN predicted_crime_count"],
            )
            invalid, _ = self.build(
                paths, root / "invalid.json", forecast=malformed
            )
            stale_manifest = self.json_copy(
                paths["manifest"],
                root / "stale-manifest.json",
                lambda value: (
                    value["training_window"].update(
                        {"max_week_start": "2024-01-01"}
                    ),
                    value.update({"forecast_week": "2024-01-08"}),
                ),
            )
            stale_forecast = self.relation_copy(
                paths["forecast"],
                root / "stale-forecast.parquet",
                ["UPDATE changed SET week_start = DATE '2024-01-08'"],
            )
            stale, _ = self.build(
                paths,
                root / "stale.json",
                manifest=stale_manifest,
                forecast=stale_forecast,
            )
            empty_forecast = self.relation_copy(
                paths["forecast"], root / "empty-forecast.parquet", ["DELETE FROM changed"]
            )
            empty_baseline = self.relation_copy(
                paths["baseline"], root / "empty-baseline.parquet", ["DELETE FROM changed"]
            )
            empty, _ = self.build(
                paths,
                root / "empty.json",
                forecast=empty_forecast,
                baseline=empty_baseline,
            )

        self.assertEqual(missing["forecast"]["status"], "missing")
        self.assertEqual(missing["availability"]["forecastPointEstimates"], "missing")
        self.assertIsNone(missing["forecast"]["summary"]["predictedTotal"])
        self.assertEqual(invalid["forecast"]["status"], "invalid")
        self.assertEqual(invalid["forecast"]["rows"], [])
        self.assertTrue(invalid["forecast"]["reason"])
        self.assertEqual(stale["forecast"]["status"], "stale")
        self.assertEqual(stale["availability"]["forecastPointEstimates"], "stale")
        self.assertEqual(empty["forecast"]["status"], "available")
        self.assertTrue(empty["forecast"]["isEmpty"])
        self.assertEqual(empty["availability"]["forecastPointEstimates"], "empty")
        self.assertIsNone(empty["forecast"]["summary"]["predictedTotal"])

    def test_nonfinite_and_negative_prediction_sources_are_invalid_not_coerced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            cases = {
                "nan": "CAST('NaN' AS DOUBLE)",
                "positive-infinity": "CAST('Infinity' AS DOUBLE)",
                "negative-infinity": "CAST('-Infinity' AS DOUBLE)",
                "negative": "-0.25",
            }
            results = {}
            for name, expression in cases.items():
                changed = self.relation_copy(
                    paths["forecast"],
                    root / f"{name}.parquet",
                    [
                        "UPDATE changed SET predicted_crime_count = "
                        f"{expression} WHERE offense_type = 'THEFT'"
                    ],
                )
                results[name], _ = self.build(
                    paths, root / f"{name}.json", forecast=changed
                )

        for name, payload in results.items():
            with self.subTest(name=name):
                self.assertEqual(payload["forecast"]["status"], "invalid")
                self.assertEqual(payload["forecast"]["rows"], [])
                self.assertIsNone(payload["forecast"]["summary"]["predictedTotal"])

    def test_duplicate_null_and_unsafe_prediction_sources_are_withheld(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            cases = {
                "duplicate": ["INSERT INTO changed SELECT * FROM changed LIMIT 1"],
                "null-label": [
                    "UPDATE changed SET borough = NULL WHERE offense_type = 'THEFT'"
                ],
                "unsafe-column": [
                    "ALTER TABLE changed ADD COLUMN complaint_number VARCHAR",
                    "UPDATE changed SET complaint_number = 'private-id'",
                ],
            }
            results = {}
            for name, statements in cases.items():
                changed = self.relation_copy(
                    paths["forecast"], root / f"{name}.parquet", statements
                )
                results[name], _ = self.build(
                    paths, root / f"{name}.json", forecast=changed
                )

        for name, payload in results.items():
            with self.subTest(name=name):
                self.assertEqual(payload["forecast"]["status"], "invalid")
                self.assertEqual(payload["forecast"]["rows"], [])

    def test_model_name_and_forecast_week_mismatches_invalidate_forecast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            wrong_model = self.relation_copy(
                paths["forecast"],
                root / "wrong-model.parquet",
                ["UPDATE changed SET ml_model_name = 'another_model'"],
            )
            model_payload, _ = self.build(
                paths, root / "wrong-model.json", forecast=wrong_model
            )
            wrong_week = self.relation_copy(
                paths["forecast"],
                root / "wrong-week.parquet",
                ["UPDATE changed SET week_start = DATE '2024-01-22'"],
            )
            week_payload, _ = self.build(
                paths, root / "wrong-week.json", forecast=wrong_week
            )
            mixed_week = self.relation_copy(
                paths["forecast"],
                root / "mixed-week.parquet",
                [
                    "UPDATE changed SET week_start = DATE '2024-01-22' "
                    "WHERE offense_type = 'THEFT'"
                ],
            )
            mixed_payload, _ = self.build(
                paths, root / "mixed-week.json", forecast=mixed_week
            )

        for payload in (model_payload, week_payload, mixed_payload):
            self.assertEqual(payload["forecast"]["status"], "invalid")
            self.assertEqual(payload["forecast"]["rows"], [])
            self.assertEqual(payload["model"]["status"], "invalid")

    def test_missing_or_malformed_manifest_withholds_predictions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            missing, _ = self.build(
                paths,
                root / "missing-manifest.json",
                manifest=root / "does-not-exist.json",
            )
            malformed_manifest = root / "malformed-manifest.json"
            malformed_manifest.write_text("[not-an-object]", encoding="utf-8")
            malformed, _ = self.build(
                paths, root / "malformed.json", manifest=malformed_manifest
            )

        self.assertEqual(missing["model"]["status"], "missing")
        self.assertEqual(missing["forecast"]["status"], "invalid")
        self.assertEqual(malformed["model"]["status"], "invalid")
        self.assertEqual(malformed["forecast"]["status"], "invalid")

    def test_manifest_generation_timestamp_is_required_and_strictly_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            cases = {
                "missing": lambda value: value.pop("generated_at_utc"),
                "malformed": lambda value: value.update(
                    {"generated_at_utc": "not-a-timestamp"}
                ),
                "missing-offset": lambda value: value.update(
                    {"generated_at_utc": "2024-02-01T12:34:56"}
                ),
            }
            results = {}
            for name, mutate in cases.items():
                manifest = self.json_copy(
                    paths["manifest"], root / f"{name}-manifest.json", mutate
                )
                results[name], _ = self.build(
                    paths, root / f"{name}.json", manifest=manifest
                )

        for name, payload in results.items():
            with self.subTest(name=name):
                self.assertEqual(payload["model"]["status"], "invalid")
                self.assertIsNone(payload["model"]["artifactGeneratedAtUtc"])
                self.assertEqual(
                    payload["model"]["independentTrainingTime"],
                    build_dashboard_forecast_map.INDEPENDENT_TRAINING_TIME,
                )
                self.assertEqual(payload["forecast"]["status"], "invalid")

    def test_metrics_generation_timestamp_must_match_manifest_exact_instant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            cases = {
                "missing": lambda value: value.pop("generated_at_utc"),
                "malformed": lambda value: value.update(
                    {"generated_at_utc": "not-a-timestamp"}
                ),
                "mismatch": lambda value: value.update(
                    {"generated_at_utc": "2024-02-01T12:34:57.123456+00:00"}
                ),
            }
            results = {}
            for name, mutate in cases.items():
                metrics = self.json_copy(
                    paths["metrics"], root / f"{name}-metrics.json", mutate
                )
                results[name], _ = self.build(
                    paths, root / f"{name}.json", metrics=metrics
                )

        for name, payload in results.items():
            with self.subTest(name=name):
                self.assertEqual(payload["model"]["status"], "available")
                self.assertEqual(payload["forecast"]["status"], "available")
                self.assertEqual(
                    payload["model"]["historicalError"]["status"], "invalid"
                )
                self.assertTrue(payload["model"]["historicalError"]["reason"])

    def test_metrics_mismatch_withholds_error_context_not_point_estimates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            metrics = self.json_copy(
                paths["metrics"],
                root / "wrong-metrics.json",
                lambda value: value["model_config"].update(
                    {"model_name": "another_model"}
                ),
            )
            payload, _ = self.build(paths, root / "output.json", metrics=metrics)

        self.assertEqual(payload["forecast"]["status"], "available")
        self.assertEqual(payload["model"]["historicalError"]["status"], "invalid")
        self.assertNotIn("mae", payload["model"]["historicalError"])

    def test_missing_baseline_keeps_baseline_and_change_values_null(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            payload, _ = self.build(
                paths,
                root / "output.json",
                baseline=root / "missing-baseline.parquet",
            )

        self.assertEqual(payload["baseline"]["status"], "missing")
        self.assertEqual(payload["baseline"]["valueAvailability"], "unavailable")
        self.assertEqual(payload["availability"]["historicalBaseline"], "unavailable")
        for row in self.decoded_rows(payload):
            self.assertIsNone(row["historicalBaseline"])
            self.assertIsNone(row["expectedChangeCount"])
            self.assertIsNone(row["expectedChangePct"])

    def test_tampered_baseline_values_invalidate_the_whole_optional_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            tampered = self.relation_copy(
                paths["baseline"],
                root / "tampered-baseline.parquet",
                [
                    "UPDATE changed SET trailing_8_week_mean = 4.75 "
                    "WHERE offense_type = 'THEFT'"
                ],
            )
            payload, _ = self.build(
                paths, root / "output.json", baseline=tampered
            )

        self.assertEqual(payload["forecast"]["status"], "available")
        self.assertEqual(payload["baseline"]["status"], "invalid")
        self.assertIn("prior-only weekly derivation", payload["baseline"]["reason"])
        self.assertEqual(payload["baseline"]["valueAvailability"], "unavailable")
        for row in self.decoded_rows(payload):
            self.assertIsNone(row["historicalBaseline"])
            self.assertIsNone(row["expectedChangeCount"])
            self.assertIsNone(row["expectedChangePct"])

    def test_incomplete_nonempty_forecast_segment_universe_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            incomplete = self.relation_copy(
                paths["forecast"],
                root / "incomplete-forecast.parquet",
                ["DELETE FROM changed WHERE offense_type = 'UNKNOWN'"],
            )
            payload, _ = self.build(
                paths, root / "output.json", forecast=incomplete
            )

        self.assertEqual(payload["model"]["status"], "invalid")
        self.assertIn("segment universe", payload["model"]["reason"])
        self.assertEqual(payload["forecast"]["status"], "invalid")
        self.assertEqual(payload["forecast"]["rows"], [])
        self.assertIsNone(payload["forecast"]["summary"]["sourceRowCount"])

    def test_metrics_value_and_record_count_tampering_invalidates_error_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            changed_value = self.json_copy(
                paths["metrics"],
                root / "changed-value-metrics.json",
                lambda value: value["metrics"]["overall"][0].update({"mae": 0.51}),
            )
            changed_count = self.json_copy(
                paths["metrics"],
                root / "changed-count-metrics.json",
                lambda value: value["record_counts"].update({"backtest_rows": 4}),
            )
            value_payload, _ = self.build(
                paths, root / "changed-value.json", metrics=changed_value
            )
            count_payload, _ = self.build(
                paths, root / "changed-count.json", metrics=changed_count
            )

        for name, payload in (
            ("overall-value", value_payload),
            ("record-count", count_payload),
        ):
            with self.subTest(name=name):
                self.assertEqual(payload["forecast"]["status"], "available")
                historical_error = payload["model"]["historicalError"]
                self.assertEqual(historical_error["status"], "invalid")
                self.assertTrue(historical_error["reason"])
                self.assertNotIn("mae", historical_error)

    def test_malformed_baseline_parquet_types_invalidate_baseline_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            malformed = self.relation_copy(
                paths["baseline"],
                root / "malformed-baseline-types.parquet",
                [
                    "ALTER TABLE changed ALTER COLUMN trailing_8_week_mean "
                    "TYPE VARCHAR"
                ],
            )
            payload, _ = self.build(
                paths, root / "output.json", baseline=malformed
            )

        self.assertEqual(payload["forecast"]["status"], "available")
        self.assertEqual(payload["baseline"]["status"], "invalid")
        self.assertIn("must be numeric", payload["baseline"]["reason"])
        self.assertEqual(payload["availability"]["historicalBaseline"], "unavailable")
        self.assertTrue(
            all(row["historicalBaseline"] is None for row in self.decoded_rows(payload))
        )

    def test_output_path_collision_raises_before_write_and_preserves_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            original = paths["forecast"].read_bytes()
            with self.assertRaisesRegex(
                build_dashboard_forecast_map.ForecastMapContractError,
                "must not overwrite a source artifact",
            ):
                self.build(paths, paths["forecast"])
            preserved = paths["forecast"].read_bytes()

        self.assertEqual(preserved, original)

    def test_unmappable_and_borough_mismatch_rows_are_quantified_and_withheld(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            weekly = self.relation_copy(
                paths["weekly"],
                root / "weekly-with-unmappable-segments.parquet",
                [
                    """
                    INSERT INTO changed
                    SELECT
                        CAST(DATE '2023-11-20' + index * INTERVAL 7 DAY AS DATE),
                        'MANHATTAN', '1', 'FRAUD', 'FELONY', 0
                    FROM range(8) AS weeks(index)
                    """,
                    """
                    INSERT INTO changed
                    SELECT
                        CAST(DATE '2023-11-20' + index * INTERVAL 7 DAY AS DATE),
                        'BRONX', 'UNKNOWN', 'FRAUD', 'FELONY', 0
                    FROM range(8) AS weeks(index)
                    """,
                ],
            )
            forecast = self.relation_copy(
                paths["forecast"],
                root / "forecast-with-unmappable-segments.parquet",
                [
                    """
                    INSERT INTO changed VALUES
                        (DATE '2024-01-15', 'MANHATTAN', '1', 'FRAUD', 'FELONY',
                         1.0, 'fixture_model', TRUE),
                        (DATE '2024-01-15', 'BRONX', 'UNKNOWN', 'FRAUD', 'FELONY',
                         1.0, 'fixture_model', TRUE)
                    """
                ],
            )
            baseline = self.relation_copy(
                paths["baseline"],
                root / "baseline-with-unmappable-segments.parquet",
                [
                    """
                    INSERT INTO changed VALUES
                        (DATE '2024-01-15', 'MANHATTAN', '1', 'FRAUD', 'FELONY', 0.0, TRUE),
                        (DATE '2024-01-15', 'BRONX', 'UNKNOWN', 'FRAUD', 'FELONY', 0.0, TRUE)
                    """
                ],
            )
            manifest = self.json_copy(
                paths["manifest"],
                root / "five-segment-manifest.json",
                lambda value: value["training_window"].update({"segment_count": 5}),
            )
            baseline_manifest = self.json_copy(
                paths["baseline_manifest"],
                root / "five-segment-baseline-manifest.json",
                lambda value: value["training_window"].update({"segment_count": 5}),
            )
            metrics = self.json_copy(
                paths["metrics"],
                root / "five-segment-metrics.json",
                lambda value: value["record_counts"].update(
                    {
                        "output_rows": 8,
                        "next_week_forecast_rows": 5,
                        "output_segment_count": 5,
                    }
                ),
            )
            payload, _ = self.build(
                paths,
                root / "output.json",
                weekly=weekly,
                forecast=forecast,
                baseline=baseline,
                manifest=manifest,
                baseline_manifest=baseline_manifest,
                metrics=metrics,
            )

        summary = payload["forecast"]["summary"]
        self.assertEqual(payload["forecast"]["status"], "available")
        self.assertEqual(summary["sourceRowCount"], 5)
        self.assertEqual(summary["rowCount"], 3)
        self.assertEqual(summary["withheldRowCount"], 2)
        self.assertEqual(
            summary["withheldReasonCounts"],
            {"unmappableLocation": 1, "boroughMismatch": 1},
        )
        self.assertEqual(
            {row["precinctLocationKey"] for row in self.decoded_rows(payload)},
            {"nypd-precinct:1", "nypd-precinct:2"},
        )

    def test_payload_validator_rejects_malformed_rows_arithmetic_and_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, _ = self.build(
                self.write_inputs(root / "inputs"), root / "output.json"
            )

        cases = {}
        cases["short-row"] = copy.deepcopy(payload)
        cases["short-row"]["forecast"]["rows"][0].pop()
        cases["duplicate-row"] = copy.deepcopy(payload)
        cases["duplicate-row"]["forecast"]["rows"].append(
            copy.deepcopy(cases["duplicate-row"]["forecast"]["rows"][0])
        )
        cases["invalid-index"] = copy.deepcopy(payload)
        cases["invalid-index"]["forecast"]["rows"][0][1] = 999
        cases["negative"] = copy.deepcopy(payload)
        cases["negative"]["forecast"]["rows"][0][5] = -1
        cases["nonfinite"] = copy.deepcopy(payload)
        cases["nonfinite"]["forecast"]["rows"][0][5] = float("nan")
        cases["bad-change-count"] = copy.deepcopy(payload)
        baseline_row = next(
            row for row in cases["bad-change-count"]["forecast"]["rows"] if row[6] is not None
        )
        baseline_row[7] = baseline_row[7] + 0.01
        cases["bad-change-percent"] = copy.deepcopy(payload)
        baseline_row = next(
            row
            for row in cases["bad-change-percent"]["forecast"]["rows"]
            if row[8] is not None
        )
        baseline_row[8] = baseline_row[8] + 0.01
        cases["unsafe-key"] = copy.deepcopy(payload)
        cases["unsafe-key"]["forecast"]["rows"][0][9] = "40.7,-73.9"

        for name, changed in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(build_dashboard_forecast_map.ForecastMapContractError):
                    build_dashboard_forecast_map.validate_forecast_map_payload(changed)

    def test_payload_validator_rejects_future_metadata_and_unsafe_privacy_or_ethics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, _ = self.build(
                self.write_inputs(root / "inputs"), root / "output.json"
            )

        cases = {}
        cases["future-generated"] = copy.deepcopy(payload)
        cases["future-generated"]["generatedAtUtc"] = "2024-01-16T00:00:00Z"
        cases["privacy-absent"] = copy.deepcopy(payload)
        del cases["privacy-absent"]["privacy"]["aggregateOnly"]
        cases["privacy-unsafe"] = copy.deepcopy(payload)
        cases["privacy-unsafe"]["privacy"]["eventRecordsIncluded"] = True
        cases["ethics-unsafe"] = copy.deepcopy(payload)
        cases["ethics-unsafe"]["ethics"]["patrolRecommendations"] = True
        cases["event-field"] = copy.deepcopy(payload)
        cases["event-field"]["limitations"].append("complaint_number")
        cases["noncanonical-artifact-timestamp"] = copy.deepcopy(payload)
        cases["noncanonical-artifact-timestamp"]["model"][
            "artifactGeneratedAtUtc"
        ] = "2024-02-01T12:34:56.123456Z"
        cases["fabricated-training-time"] = copy.deepcopy(payload)
        cases["fabricated-training-time"]["model"]["independentTrainingTime"] = {
            "status": "available",
            "timestamp": "2024-02-01T12:00:00+00:00",
            "reason": None,
        }
        cases["zero-backtest-rows"] = copy.deepcopy(payload)
        cases["zero-backtest-rows"]["model"]["historicalError"][
            "backtestRowCount"
        ] = 0
        cases["reversed-backtest-range"] = copy.deepcopy(payload)
        cases["reversed-backtest-range"]["model"]["historicalError"].update(
            {
                "backtestStartWeek": "2024-01-15",
                "backtestEndWeek": "2024-01-08",
            }
        )
        for field, path in (
            (("forecast", "sourceFile"), "/Users/example/private/forecast.parquet"),
            (("baseline", "sourceFile"), "/Users/example/private/baseline.parquet"),
            (("baseline", "manifestSourceFile"), "/Users/example/private/manifest.json"),
            (("model", "sourceFile"), "/Users/example/private/model.json"),
            (("historicalError", "sourceFile"), "/Users/example/private/metrics.json"),
        ):
            changed = copy.deepcopy(payload)
            if field[0] == "historicalError":
                changed["model"]["historicalError"][field[1]] = path
            else:
                changed[field[0]][field[1]] = path
            cases[f"absolute-{field[0]}-{field[1]}"] = changed

        for name, changed in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(build_dashboard_forecast_map.ForecastMapContractError):
                    build_dashboard_forecast_map.validate_forecast_map_payload(changed)

    def test_safe_location_key_rejects_unknown_and_coordinate_like_labels(self) -> None:
        self.assertEqual(
            build_dashboard_forecast_map.location_key("123"), "nypd-precinct:123"
        )
        for value in ("UNKNOWN", "0", "1.5", "40.7,-73.9", "1/../../private"):
            with self.subTest(value=value):
                with self.assertRaises(build_dashboard_forecast_map.ForecastMapContractError):
                    build_dashboard_forecast_map.location_key(value)


if __name__ == "__main__":
    unittest.main()

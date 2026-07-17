import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "analytics"
    / "build_dashboard_overview.py"
)
SPEC = importlib.util.spec_from_file_location("build_dashboard_overview", MODULE_PATH)
build_dashboard_overview = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_dashboard_overview)


class DashboardOverviewContractTest(unittest.TestCase):
    def write_inputs(self, directory: Path) -> dict[str, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        paths = {
            "clean": directory / "complaints_clean.parquet",
            "weekly": directory / "crime_weekly_area.parquet",
            "anomalies": directory / "anomalies.parquet",
            "hotspots": directory / "hotspots.parquet",
            "forecast": directory / "ml_predictions.parquet",
            "anomaly_metrics": directory / "anomaly_metrics.json",
            "hotspot_metrics": directory / "hotspot_metrics.json",
            "ml_metrics": directory / "ml_metrics.json",
            "ml_manifest": directory / "ml_manifest.json",
            "baseline_manifest": directory / "baseline_manifest.json",
        }
        duckdb = build_dashboard_overview.require_duckdb()
        con = duckdb.connect(database=":memory:")
        quality_columns = list(build_dashboard_overview.QUALITY_FLAG_FIELDS.values())
        quality_column_sql = ",\n                ".join(
            f"{column} BOOLEAN" for column in quality_columns
        )
        con.execute(
            f"""
            CREATE TABLE clean_events (
                complaint_from_date DATE,
                is_clean_event_for_aggregate BOOLEAN,
                borough VARCHAR,
                precinct VARCHAR,
                offense_type VARCHAR,
                law_category VARCHAR,
                {quality_column_sql},
                complaint_number VARCHAR,
                SUSP_RACE VARCHAR
            )
            """
        )

        def clean_row(
            complaint_date,
            aggregate_safe,
            borough,
            precinct,
            offense,
            law_category,
            complaint_number,
            *active_flags,
        ):
            return (
                complaint_date,
                aggregate_safe,
                borough,
                precinct,
                offense,
                law_category,
                *(column in active_flags for column in quality_columns),
                complaint_number,
                "PRIVATE-VALUE",
            )

        missing_precinct = build_dashboard_overview.QUALITY_FLAG_FIELDS[
            "missingPrecinct"
        ]
        missing_coordinates = build_dashboard_overview.QUALITY_FLAG_FIELDS[
            "missingCoordinates"
        ]
        future_start = build_dashboard_overview.QUALITY_FLAG_FIELDS[
            "futureComplaintStartDate"
        ]
        clean_rows = [
            clean_row(date(2024, 1, 1), True, "BRONX", "1", "THEFT", "FELONY", "event-0"),
            clean_row(date(2024, 1, 1), True, "BRONX", "1", "THEFT", "FELONY", "event-1"),
            clean_row(date(2024, 1, 1), True, "BRONX", "1", "THEFT", "FELONY", "event-2"),
            clean_row(date(2024, 1, 1), True, "MANHATTAN", "1", "THEFT", "FELONY", "event-3"),
            clean_row(date(2024, 1, 8), True, "BRONX", "1", "THEFT", "FELONY", "event-4"),
            clean_row(date(2024, 1, 8), True, "BROOKLYN", "2", "ASSAULT", "MISDEMEANOR", "event-5"),
            clean_row(date(2024, 1, 8), True, "BROOKLYN", "2", "ASSAULT", "MISDEMEANOR", "event-6"),
            clean_row(date(2024, 1, 8), True, "QUEENS", "2", "ASSAULT", "MISDEMEANOR", "event-7"),
            clean_row(
                date(2024, 1, 14),
                True,
                "QUEENS",
                None,
                "FRAUD",
                "VIOLATION",
                "event-8",
                missing_precinct,
            ),
            clean_row(
                date(2024, 1, 14),
                True,
                "QUEENS",
                None,
                "FRAUD",
                "VIOLATION",
                "event-9",
                missing_precinct,
                missing_coordinates,
            ),
            clean_row(
                date(2099, 1, 1),
                False,
                "BRONX",
                "1",
                "THEFT",
                "FELONY",
                "unsafe-event",
                future_start,
            ),
        ]
        placeholders = ", ".join("?" for _ in clean_rows[0])
        con.executemany(
            f"INSERT INTO clean_events VALUES ({placeholders})", clean_rows
        )
        con.execute(
            f"COPY clean_events TO {build_dashboard_overview.sql_string(paths['clean'])} "
            "(FORMAT PARQUET)"
        )
        con.execute(
            """
            CREATE TABLE weekly_area (
                week_start DATE,
                borough VARCHAR,
                precinct VARCHAR,
                offense_type VARCHAR,
                law_category VARCHAR,
                crime_count BIGINT
            )
            """
        )
        weekly_rows = [
            (date(2024, 1, 1), "BRONX", "1", "THEFT", "FELONY", 3),
            (date(2024, 1, 1), "MANHATTAN", "1", "THEFT", "FELONY", 1),
            (date(2024, 1, 8), "BRONX", "1", "THEFT", "FELONY", 1),
            (date(2024, 1, 8), "BROOKLYN", "2", "ASSAULT", "MISDEMEANOR", 2),
            (date(2024, 1, 8), "QUEENS", "2", "ASSAULT", "MISDEMEANOR", 1),
            (date(2024, 1, 8), "QUEENS", "UNKNOWN", "FRAUD", "VIOLATION", 2),
        ]
        con.executemany("INSERT INTO weekly_area VALUES (?, ?, ?, ?, ?, ?)", weekly_rows)
        con.execute(
            f"COPY weekly_area TO {build_dashboard_overview.sql_string(paths['weekly'])} "
            "(FORMAT PARQUET)"
        )
        con.execute(
            """
            CREATE TABLE anomaly_input (
                week_start DATE,
                borough VARCHAR,
                precinct VARCHAR,
                offense_type VARCHAR,
                law_category VARCHAR,
                actual_crime_count BIGINT,
                expected_count DOUBLE,
                expected_count_source VARCHAR,
                expected_historical_count DOUBLE,
                expected_ml_count DOUBLE,
                residual_count DOUBLE,
                is_anomaly BOOLEAN,
                passes_volume_filter BOOLEAN,
                anomaly_severity VARCHAR,
                anomaly_score DOUBLE
            )
            """
        )
        con.executemany(
            "INSERT INTO anomaly_input VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    date(2024, 1, 8),
                    "BRONX",
                    "1",
                    "THEFT",
                    "FELONY",
                    5,
                    2.0,
                    "rolling_13_week_mean",
                    2.0,
                    None,
                    3.0,
                    True,
                    True,
                    "high",
                    4.2,
                ),
                (
                    date(2024, 1, 8),
                    "BROOKLYN",
                    "2",
                    "ASSAULT",
                    "MISDEMEANOR",
                    2,
                    1.0,
                    "rolling_13_week_mean",
                    1.0,
                    None,
                    1.0,
                    True,
                    True,
                    "low",
                    1.1,
                ),
            ],
        )
        con.execute(
            f"COPY anomaly_input TO {build_dashboard_overview.sql_string(paths['anomalies'])} "
            "(FORMAT PARQUET)"
        )
        con.execute(
            """
            CREATE TABLE hotspot_input (
                hotspot_grain VARCHAR,
                borough VARCHAR,
                precinct VARCHAR,
                grid_latitude DOUBLE,
                grid_longitude DOUBLE,
                offense_type VARCHAR,
                law_category VARCHAR,
                scoring_end_date DATE,
                recent_event_count BIGINT,
                baseline_event_count BIGINT,
                baseline_expected_recent_count DOUBLE,
                recent_vs_baseline_lift_pct DOUBLE,
                composite_score DOUBLE,
                is_high_or_critical_hotspot BOOLEAN,
                hotspot_severity VARCHAR
            )
            """
        )
        con.executemany(
            "INSERT INTO hotspot_input VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "grid",
                    "BRONX",
                    None,
                    40.845,
                    -73.905,
                    "THEFT",
                    "FELONY",
                    date(2024, 1, 14),
                    9,
                    20,
                    5.48,
                    64.25,
                    91.5,
                    True,
                    "critical",
                ),
                (
                    "precinct",
                    "BROOKLYN",
                    "2",
                    None,
                    None,
                    "ASSAULT",
                    "MISDEMEANOR",
                    date(2024, 1, 14),
                    3,
                    20,
                    2.73,
                    10.0,
                    44.0,
                    False,
                    "medium",
                ),
            ],
        )
        con.execute(
            f"COPY hotspot_input TO {build_dashboard_overview.sql_string(paths['hotspots'])} "
            "(FORMAT PARQUET)"
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
        con.executemany(
            "INSERT INTO forecast_input VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    date(2024, 1, 15),
                    "BRONX",
                    "1",
                    "THEFT",
                    "FELONY",
                    4.5,
                    "test_model",
                    True,
                ),
                (
                    date(2024, 1, 8),
                    "BRONX",
                    "1",
                    "THEFT",
                    "FELONY",
                    3.0,
                    "test_model",
                    False,
                ),
            ],
        )
        con.execute(
            f"COPY forecast_input TO {build_dashboard_overview.sql_string(paths['forecast'])} "
            "(FORMAT PARQUET)"
        )
        paths["anomaly_metrics"].write_text(
            json.dumps(
                {
                    "phase": "Phase 6A - Anomaly Detection Layer",
                    "generated_at_utc": "2024-01-14T00:00:00Z",
                    "anomaly_columns_used": build_dashboard_overview.WEEKLY_REQUIRED_COLUMNS,
                    "output_columns": build_dashboard_overview.ANOMALY_REQUIRED_COLUMNS,
                    "anomaly_config": {
                        "primary_historical_expected_count": (
                            "trailing_13_week_mean over prior weeks only"
                        )
                    },
                    "analysis_window": {
                        "min_week_start": "2024-01-01",
                        "max_week_start": "2024-01-08",
                        "scoring_end_week": "2024-01-08",
                        "latest_week_excluded_from_scoring": False,
                    },
                    "record_counts": {"anomaly_rows": 2},
                    "severity_counts": [
                        {"anomaly_severity": "low", "anomaly_count": 1},
                        {"anomaly_severity": "medium", "anomaly_count": 0},
                        {"anomaly_severity": "high", "anomaly_count": 1},
                        {"anomaly_severity": "critical", "anomaly_count": 0},
                    ],
                    "leakage_controls": {
                        "historical_windows_use_prior_weeks_only": True,
                        "random_splits_used": False,
                    },
                }
            )
        )
        paths["hotspot_metrics"].write_text(
            json.dumps({"phase": "Phase 6B", "generated_at_utc": "2024-01-14T00:00:00Z"})
        )
        paths["ml_metrics"].write_text(
            json.dumps(
                {
                    "phase": "Phase 5",
                    "generated_at_utc": "2024-01-14T00:00:00Z",
                    "model_config": {"model_name": "test_model", "model_version": 1},
                    "analysis_window": {
                        "next_week_forecast_week": "2024-01-15"
                    },
                    "metrics": {
                        "overall": [
                            {
                                "mae": 0.5,
                                "rmse": 1.25,
                                "weighted_mae": 2.5,
                                "prediction_coverage_pct": 99.0,
                            }
                        ]
                    },
                }
            )
        )
        paths["ml_manifest"].write_text(
            json.dumps(
                {
                    "phase": "Phase 5",
                    "artifact_type": "weekly_forecast_ml_model",
                    "artifact_version": 1,
                    "forecast_week": "2024-01-15",
                    "model": {"model_name": "test_model", "model_version": 1},
                    "leakage_controls": {
                        "random_splits_used": False,
                        "target_week_excluded_from_features": True,
                    },
                }
            )
        )
        paths["baseline_manifest"].write_text(
            json.dumps(
                {
                    "phase": "Phase 4",
                    "artifact_type": "baseline_forecast_model",
                    "artifact_version": 1,
                }
            )
        )
        con.close()
        return paths

    def build(
        self,
        paths: dict[str, Path],
        output_directory: Path,
        **path_overrides: Path,
    ):
        output_directory.mkdir(parents=True, exist_ok=True)
        actual = dict(paths)
        actual.update(path_overrides)
        overview = output_directory / "overview.json"
        cube = output_directory / "overview-cube.bin.gz"
        payload = build_dashboard_overview.build_dashboard_overview(
            clean_events_path=actual["clean"],
            weekly_path=actual["weekly"],
            overview_output_path=overview,
            cube_output_path=cube,
            anomalies_path=actual["anomalies"],
            hotspots_path=actual["hotspots"],
            ml_predictions_path=actual["forecast"],
            anomaly_metrics_path=actual["anomaly_metrics"],
            hotspot_metrics_path=actual["hotspot_metrics"],
            ml_metrics_path=actual["ml_metrics"],
            ml_manifest_path=actual["ml_manifest"],
            baseline_manifest_path=actual["baseline_manifest"],
            threads=1,
        )
        return payload, overview, cube

    def mutate_anomalies(
        self, source: Path, target: Path, statements: list[str]
    ) -> Path:
        duckdb = build_dashboard_overview.require_duckdb()
        con = duckdb.connect(database=":memory:")
        con.execute(
            f"CREATE TABLE anomaly_mutation AS SELECT * FROM read_parquet("
            f"{build_dashboard_overview.sql_string(source)})"
        )
        for statement in statements:
            con.execute(statement)
        con.execute(
            f"COPY anomaly_mutation TO "
            f"{build_dashboard_overview.sql_string(target)} (FORMAT PARQUET)"
        )
        con.close()
        return target

    def mutate_parquet(
        self,
        source: Path,
        target: Path,
        table_name: str,
        statements: list[str],
    ) -> Path:
        duckdb = build_dashboard_overview.require_duckdb()
        con = duckdb.connect(database=":memory:")
        con.execute(
            f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet("
            f"{build_dashboard_overview.sql_string(source)})"
        )
        for statement in statements:
            con.execute(statement)
        con.execute(
            f"COPY {table_name} TO {build_dashboard_overview.sql_string(target)} "
            "(FORMAT PARQUET)"
        )
        con.close()
        return target

    def mutate_anomaly_metrics(self, source: Path, target: Path, mutate) -> Path:
        payload = json.loads(source.read_text(encoding="utf-8"))
        mutate(payload)
        target.write_text(json.dumps(payload), encoding="utf-8")
        return target

    def test_overview_schema_binary_layout_and_week_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, _, cube_path = self.build(
                self.write_inputs(root / "inputs"), root / "output"
            )
            cube_bytes = cube_path.read_bytes()
        self.assertEqual(payload["schemaVersion"], "1.0.0")
        self.assertEqual(payload["cube"]["path"], "/data/overview-cube.bin.gz")
        self.assertEqual(payload["cube"]["columnOrder"], build_dashboard_overview.CUBE_COLUMN_ORDER)
        self.assertEqual(payload["cube"]["rowCount"], 6)
        self.assertEqual(payload["cube"]["observedWeekCount"], 2)
        self.assertEqual(cube_bytes[4:8], b"\x00\x00\x00\x00")
        decoded = build_dashboard_overview.decode_cube(payload, cube_bytes)
        self.assertEqual(decoded["weekRowOffsets"], [0, 2, 6])
        self.assertEqual(len(decoded["counts"]), 6)

    def test_identical_inputs_produce_byte_identical_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            first = self.build(paths, root / "one")
            second = self.build(paths, root / "two")
            self.assertEqual(first[1].read_bytes(), second[1].read_bytes())
            self.assertEqual(first[2].read_bytes(), second[2].read_bytes())
            self.assertEqual(first[0]["generatedAtUtc"], "2024-01-14T00:00:00Z")

    def test_cli_copies_canonical_overview_and_cube_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            canonical_overview = root / "processed" / "dashboard_overview.json"
            canonical_cube = root / "processed" / "dashboard_overview_cube.bin.gz"
            dashboard_dir = root / "dashboard" / "public" / "data"
            argv = [
                "build_dashboard_overview.py",
                "--project-root",
                str(root),
                "--dashboard-data-dir",
                str(dashboard_dir),
                "--clean-events",
                str(paths["clean"]),
                "--weekly-area",
                str(paths["weekly"]),
                "--anomalies",
                str(paths["anomalies"]),
                "--hotspots",
                str(paths["hotspots"]),
                "--ml-predictions",
                str(paths["forecast"]),
                "--anomaly-metrics",
                str(paths["anomaly_metrics"]),
                "--hotspot-metrics",
                str(paths["hotspot_metrics"]),
                "--ml-metrics",
                str(paths["ml_metrics"]),
                "--ml-manifest",
                str(paths["ml_manifest"]),
                "--baseline-manifest",
                str(paths["baseline_manifest"]),
                "--overview-output",
                str(canonical_overview),
                "--cube-output",
                str(canonical_cube),
                "--threads",
                "1",
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
                build_dashboard_overview.main()

            canonical_overview_bytes = canonical_overview.read_bytes()
            canonical_cube_bytes = canonical_cube.read_bytes()
            dashboard_overview_bytes = (dashboard_dir / "overview.json").read_bytes()
            dashboard_cube_bytes = (
                dashboard_dir / "overview-cube.bin.gz"
            ).read_bytes()

        self.assertEqual(canonical_overview_bytes, dashboard_overview_bytes)
        self.assertEqual(canonical_cube_bytes, dashboard_cube_bytes)

    def test_sensitive_fields_and_event_records_are_absent_and_unsafe_rows_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, overview, _ = self.build(
                self.write_inputs(root / "inputs"), root / "output"
            )
            serialized = overview.read_text(encoding="utf-8").upper()
        self.assertEqual(payload["observed"]["safeEventCount"], 10)
        self.assertEqual(payload["observed"]["weeklyAggregateCount"], 10)
        self.assertEqual(payload["dataQuality"]["excludedEventCount"], 1)
        self.assertTrue(payload["dataQuality"]["safeRowsOnly"])
        self.assertFalse(payload["ethics"]["eventRecordsIncluded"])
        self.assertNotIn("PRIVATE-VALUE", serialized)
        self.assertNotIn("COMPLAINT_NUMBER", serialized)
        for column in build_dashboard_overview.SENSITIVE_COLUMNS:
            self.assertNotIn(column, serialized)

    def test_quality_counts_distinguish_source_issues_and_retained_unknowns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, _, _ = self.build(
                self.write_inputs(root / "inputs"), root / "output"
            )
        source = payload["dataQuality"]["sourceIssueCounts"]
        self.assertEqual(source["populationCount"], 11)
        self.assertEqual(source["missingPrecinct"], 2)
        self.assertEqual(source["missingCoordinates"], 1)
        self.assertEqual(source["futureComplaintStartDate"], 1)
        self.assertEqual(source["missingBorough"], 0)
        self.assertEqual(source["invalidLawCategory"], 0)
        self.assertEqual(source["rowsWithAnyIssue"], 3)
        self.assertEqual(source["rowsWithMultipleIssues"], 1)
        self.assertEqual(source["maximumIssuesPerRow"], 2)
        self.assertTrue(source["categoriesOverlap"])
        self.assertTrue(source["countsAreNonAdditive"])

        unknown = payload["dataQuality"]["aggregateSafeUnknownCounts"]
        self.assertEqual(
            unknown,
            {
                "populationCount": 10,
                "borough": 0,
                "precinct": 2,
                "offense": 0,
                "lawCategory": 0,
                "valuesRetained": True,
                "categoriesOverlap": True,
            },
        )

    def test_quality_flags_require_boolean_non_null_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            missing_borough = build_dashboard_overview.QUALITY_FLAG_FIELDS[
                "missingBorough"
            ]
            invalid_type = self.mutate_parquet(
                paths["clean"],
                root / "invalid-flag-type.parquet",
                "invalid_flag_type",
                [
                    "ALTER TABLE invalid_flag_type ALTER COLUMN "
                    f"{missing_borough} TYPE INTEGER"
                ],
            )
            with self.assertRaisesRegex(ValueError, "flags must be BOOLEAN"):
                self.build(paths, root / "invalid-type-output", clean=invalid_type)

            null_flag = self.mutate_parquet(
                paths["clean"],
                root / "null-flag.parquet",
                "null_flag",
                [
                    f"UPDATE null_flag SET {missing_borough} = NULL "
                    "WHERE complaint_number = 'event-0'"
                ],
            )
            with self.assertRaisesRegex(ValueError, "flags contain null"):
                self.build(paths, root / "null-output", clean=null_flag)

    def test_retained_unknown_counts_must_reconcile_to_weekly_literals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            mismatched_weekly = self.mutate_parquet(
                paths["weekly"],
                root / "mismatched-unknown.parquet",
                "mismatched_unknown",
                ["UPDATE mismatched_unknown SET precinct = '3' WHERE precinct = 'UNKNOWN'"],
            )
            with self.assertRaisesRegex(ValueError, "UNKNOWN dimension counts"):
                self.build(
                    paths,
                    root / "mismatched-output",
                    weekly=mismatched_weekly,
                )

    def test_quality_payload_validation_rejects_unavailable_or_contradictory_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, _, _ = self.build(
                self.write_inputs(root / "inputs"), root / "output"
            )

        unavailable = json.loads(json.dumps(payload))
        unavailable["dataQuality"]["aggregateSafeUnknownCounts"]["lawCategory"] = None
        with self.assertRaisesRegex(ValueError, "UNKNOWN counts"):
            build_dashboard_overview.validate_overview_payload(unavailable)

        contradictory = json.loads(json.dumps(payload))
        contradictory["dataQuality"]["sourceIssueCounts"]["rowsWithAnyIssue"] = 0
        with self.assertRaisesRegex(ValueError, "source issue counts"):
            build_dashboard_overview.validate_overview_payload(contradictory)

    def test_cube_filters_reconcile_to_consistent_totals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, _, cube_path = self.build(
                self.write_inputs(root / "inputs"), root / "output"
            )
            cube = cube_path.read_bytes()
        aggregate = build_dashboard_overview.aggregate_cube
        self.assertEqual(aggregate(payload, cube), 10)
        self.assertEqual(aggregate(payload, cube, borough="BRONX"), 4)
        self.assertEqual(aggregate(payload, cube, borough="BRONX", precinct="1"), 4)
        self.assertEqual(
            aggregate(payload, cube, start_week="2024-01-08", end_week="2024-01-08"),
            6,
        )
        self.assertEqual(aggregate(payload, cube, offense_type="THEFT"), 5)
        self.assertEqual(aggregate(payload, cube, law_category="VIOLATION"), 2)
        self.assertEqual(aggregate(payload, cube, borough="STATEN ISLAND"), 0)

    def test_borough_precinct_mapping_uses_dominant_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, _, _ = self.build(
                self.write_inputs(root / "inputs"), root / "output"
            )
        dimensions = payload["dimensions"]
        rows = payload["filterIndex"]["precinctsByBorough"]["rows"]
        mapping = {
            dimensions["boroughs"][borough_index]: {
                dimensions["precincts"][precinct_index]
                for precinct_index in precinct_indexes
            }
            for borough_index, precinct_indexes in rows
        }
        self.assertIn("1", mapping["BRONX"])
        self.assertNotIn("1", mapping["MANHATTAN"])
        self.assertIn("2", mapping["BROOKLYN"])
        self.assertNotIn("2", mapping["QUEENS"])
        self.assertIn("UNKNOWN", mapping["QUEENS"])

    def test_optional_signals_are_filtered_and_forecast_has_error_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, _, _ = self.build(
                self.write_inputs(root / "inputs"), root / "output"
            )
        self.assertEqual(payload["signals"]["anomalies"]["summary"]["rowCount"], 1)
        self.assertEqual(payload["signals"]["hotspots"]["summary"]["rowCount"], 1)
        hotspot = payload["signals"]["hotspots"]
        expected_index = hotspot["rowColumns"].index("expectedRecentCount")
        location_index = hotspot["rowColumns"].index("locationLabel")
        self.assertEqual(hotspot["rows"][0][expected_index], 5.48)
        self.assertEqual(hotspot["rows"][0][location_index], "GRID 40.845, -73.905")
        self.assertNotIn("baselineCount", hotspot["rowColumns"])
        self.assertEqual(hotspot["summary"]["snapshotDate"], "2024-01-14")
        self.assertEqual(hotspot["summary"]["snapshotAgeDays"], 0)
        self.assertEqual(payload["signals"]["forecast"]["summary"]["rowCount"], 1)
        error = payload["signals"]["forecast"]["summary"]["historicalError"]
        self.assertEqual(error["mae"], 0.5)
        self.assertEqual(error["rmse"], 1.25)
        self.assertEqual(error["weightedMae"], 2.5)
        self.assertTrue(payload["signals"]["forecast"]["summary"]["limitations"])

    def test_anomaly_contract_preserves_zero_expectation_and_available_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            zero_anomaly = self.mutate_anomalies(
                paths["anomalies"],
                root / "zero-anomaly.parquet",
                [
                    "UPDATE anomaly_mutation SET expected_count = 0, "
                    "expected_historical_count = 0, residual_count = actual_crime_count "
                    "WHERE anomaly_severity = 'high'"
                ],
            )
            payload, _, _ = self.build(
                paths, root / "zero-output", anomalies=zero_anomaly
            )
            signal = payload["signals"]["anomalies"]
            self.assertEqual(signal["status"], "available")
            expected_index = signal["rowColumns"].index("expectedCount")
            residual_index = signal["rowColumns"].index("residualCount")
            self.assertEqual(signal["rows"][0][expected_index], 0)
            self.assertEqual(signal["rows"][0][residual_index], 5)

            empty_anomaly = self.mutate_anomalies(
                paths["anomalies"],
                root / "empty-anomaly.parquet",
                ["DELETE FROM anomaly_mutation"],
            )

            def zero_counts(metrics):
                metrics["record_counts"]["anomaly_rows"] = 0
                for row in metrics["severity_counts"]:
                    row["anomaly_count"] = 0

            empty_metrics = self.mutate_anomaly_metrics(
                paths["anomaly_metrics"], root / "empty-metrics.json", zero_counts
            )
            payload, _, _ = self.build(
                paths,
                root / "empty-output",
                anomalies=empty_anomaly,
                anomaly_metrics=empty_metrics,
            )
            signal = payload["signals"]["anomalies"]
            self.assertEqual(signal["status"], "available")
            self.assertEqual(signal["rows"], [])
            self.assertEqual(signal["summary"]["rowCount"], 0)
            self.assertTrue(signal["summary"]["isEmpty"])
            self.assertEqual(signal["summary"]["scoringEndWeek"], "2024-01-08")

    def test_anomaly_contract_rejects_duplicate_arithmetic_source_and_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            cases = [
                (
                    "duplicate",
                    [
                        "INSERT INTO anomaly_mutation SELECT * FROM anomaly_mutation "
                        "WHERE anomaly_severity = 'high'"
                    ],
                    "Duplicate anomaly",
                ),
                (
                    "arithmetic",
                    [
                        "UPDATE anomaly_mutation SET residual_count = residual_count + 1 "
                        "WHERE anomaly_severity = 'high'"
                    ],
                    "arithmetic",
                ),
                (
                    "source",
                    [
                        "UPDATE anomaly_mutation SET expected_count_source = 'ml_prediction' "
                        "WHERE anomaly_severity = 'high'"
                    ],
                    "ML anomaly reference",
                ),
                (
                    "flag",
                    [
                        "UPDATE anomaly_mutation SET passes_volume_filter = false "
                        "WHERE anomaly_severity = 'high'"
                    ],
                    "flags",
                ),
            ]
            for name, statements, reason in cases:
                with self.subTest(name=name):
                    anomaly_path = self.mutate_anomalies(
                        paths["anomalies"], root / f"{name}.parquet", statements
                    )
                    payload, _, _ = self.build(
                        paths, root / f"{name}-output", anomalies=anomaly_path
                    )
                    signal = payload["signals"]["anomalies"]
                    self.assertEqual(signal["status"], "invalid")
                    self.assertEqual(signal["rows"], [])
                    self.assertIn(reason, signal["reason"])
                    self.assertIsNone(signal["summary"]["rowCount"])
                    self.assertFalse(signal["summary"]["isEmpty"])

    def test_anomaly_contract_rejects_malformed_type_dimension_date_and_severity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            cases = [
                (
                    "blank-dimension",
                    [
                        "UPDATE anomaly_mutation SET borough = '' "
                        "WHERE anomaly_severity = 'high'"
                    ],
                    "dimensions",
                ),
                (
                    "non-monday",
                    [
                        "UPDATE anomaly_mutation SET week_start = DATE '2024-01-09' "
                        "WHERE anomaly_severity = 'high'"
                    ],
                    "Mondays",
                ),
                (
                    "unsupported-severity",
                    [
                        "UPDATE anomaly_mutation SET anomaly_severity = 'urgent' "
                        "WHERE anomaly_severity = 'high'"
                    ],
                    "severity",
                ),
                (
                    "null-source",
                    [
                        "UPDATE anomaly_mutation SET expected_count_source = NULL "
                        "WHERE anomaly_severity = 'low'"
                    ],
                    "source",
                ),
                (
                    "null-severity",
                    [
                        "UPDATE anomaly_mutation SET anomaly_severity = NULL "
                        "WHERE anomaly_severity = 'low'"
                    ],
                    "severity",
                ),
            ]
            for name, statements, reason in cases:
                with self.subTest(name=name):
                    anomaly_path = self.mutate_anomalies(
                        paths["anomalies"], root / f"{name}.parquet", statements
                    )
                    payload, _, _ = self.build(
                        paths, root / f"{name}-output", anomalies=anomaly_path
                    )
                    signal = payload["signals"]["anomalies"]
                    self.assertEqual(signal["status"], "invalid")
                    self.assertIn(reason, signal["reason"])

            duckdb = build_dashboard_overview.require_duckdb()
            con = duckdb.connect(database=":memory:")
            wrong_type = root / "wrong-type.parquet"
            con.execute(
                f"COPY (SELECT * REPLACE (CAST(actual_crime_count AS DOUBLE) "
                f"AS actual_crime_count) FROM read_parquet("
                f"{build_dashboard_overview.sql_string(paths['anomalies'])})) TO "
                f"{build_dashboard_overview.sql_string(wrong_type)} (FORMAT PARQUET)"
            )
            con.close()
            payload, _, _ = self.build(
                paths, root / "wrong-type-output", anomalies=wrong_type
            )
            self.assertEqual(payload["signals"]["anomalies"]["status"], "invalid")
            self.assertIn("must be an integer", payload["signals"]["anomalies"]["reason"])

    def test_anomaly_metrics_fail_closed_for_missing_malformed_counts_and_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            missing = root / "missing-metrics.json"
            payload, _, _ = self.build(
                paths, root / "missing-output", anomaly_metrics=missing
            )
            self.assertEqual(payload["signals"]["anomalies"]["status"], "missing")
            self.assertIn("artifact is missing", payload["signals"]["anomalies"]["reason"])

            malformed = root / "malformed-metrics.json"
            malformed.write_text("[", encoding="utf-8")
            payload, _, _ = self.build(
                paths, root / "malformed-output", anomaly_metrics=malformed
            )
            self.assertEqual(payload["signals"]["anomalies"]["status"], "invalid")

            def wrong_count(metrics):
                metrics["record_counts"]["anomaly_rows"] = 99

            count_metrics = self.mutate_anomaly_metrics(
                paths["anomaly_metrics"], root / "count-metrics.json", wrong_count
            )
            payload, _, _ = self.build(
                paths, root / "count-output", anomaly_metrics=count_metrics
            )
            self.assertEqual(payload["signals"]["anomalies"]["status"], "invalid")
            self.assertIn("row count", payload["signals"]["anomalies"]["reason"])

            def wrong_identity(metrics):
                metrics["phase"] = "Phase 6B"

            identity_metrics = self.mutate_anomaly_metrics(
                paths["anomaly_metrics"],
                root / "identity-metrics.json",
                wrong_identity,
            )
            payload, _, _ = self.build(
                paths, root / "identity-output", anomaly_metrics=identity_metrics
            )
            self.assertEqual(
                payload["signals"]["anomalies"]["status"], "incompatible"
            )

    def test_anomaly_metrics_distinguish_stale_and_incompatible_horizons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            empty_anomaly = self.mutate_anomalies(
                paths["anomalies"],
                root / "empty-anomaly.parquet",
                ["DELETE FROM anomaly_mutation"],
            )

            def empty_counts(metrics):
                metrics["record_counts"]["anomaly_rows"] = 0
                for row in metrics["severity_counts"]:
                    row["anomaly_count"] = 0

            def stale_metrics(metrics):
                empty_counts(metrics)
                metrics["analysis_window"]["scoring_end_week"] = "2024-01-01"
                metrics["analysis_window"]["latest_week_excluded_from_scoring"] = True

            stale = self.mutate_anomaly_metrics(
                paths["anomaly_metrics"], root / "stale-metrics.json", stale_metrics
            )
            payload, _, _ = self.build(
                paths,
                root / "stale-output",
                anomalies=empty_anomaly,
                anomaly_metrics=stale,
            )
            signal = payload["signals"]["anomalies"]
            self.assertEqual(signal["status"], "stale")
            self.assertEqual(signal["rows"], [])
            self.assertEqual(signal["summary"]["scoringEndWeek"], "2024-01-01")
            self.assertIsNone(signal["summary"]["rowCount"])

            def future_metrics(metrics):
                empty_counts(metrics)
                metrics["analysis_window"]["max_week_start"] = "2024-01-15"
                metrics["analysis_window"]["scoring_end_week"] = "2024-01-15"
                metrics["analysis_window"]["latest_week_excluded_from_scoring"] = False

            future = self.mutate_anomaly_metrics(
                paths["anomaly_metrics"], root / "future-metrics.json", future_metrics
            )
            payload, _, _ = self.build(
                paths,
                root / "future-output",
                anomalies=empty_anomaly,
                anomaly_metrics=future,
            )
            signal = payload["signals"]["anomalies"]
            self.assertEqual(signal["status"], "incompatible")
            self.assertEqual(signal["rows"], [])
            self.assertIsNone(signal["summary"]["rowCount"])

    def test_each_missing_optional_input_degrades_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            missing = root / "missing"
            cases = {
                "anomalies": ("anomalies", "anomalies"),
                "hotspots": ("hotspots", "hotspots"),
                "forecast": ("forecast", "forecast"),
            }
            for case, (path_key, family) in cases.items():
                payload, _, _ = self.build(
                    paths,
                    root / f"missing-{case}",
                    **{path_key: missing / f"{path_key}.parquet"},
                )
                self.assertEqual(payload["signals"][family]["status"], "missing")
                self.assertEqual(payload["signals"][family]["rows"], [])
            version_cases = {
                "anomaly_metrics": "anomalyMetrics",
                "hotspot_metrics": "hotspotMetrics",
                "baseline_manifest": "baselineManifest",
            }
            for path_key, version_key in version_cases.items():
                payload, _, _ = self.build(
                    paths,
                    root / f"missing-{path_key}",
                    **{path_key: missing / f"{path_key}.json"},
                )
                self.assertEqual(payload["versions"][version_key]["status"], "missing")
            payload, _, _ = self.build(
                paths,
                root / "missing-ml-metrics",
                ml_metrics=missing / "ml_metrics.json",
            )
            self.assertEqual(payload["versions"]["mlMetrics"]["status"], "missing")
            self.assertEqual(
                payload["signals"]["forecast"]["summary"]["historicalError"]["status"],
                "missing",
            )
            payload, _, _ = self.build(
                paths,
                root / "missing-ml-manifest",
                ml_manifest=missing / "ml_manifest.json",
            )
            self.assertEqual(payload["signals"]["forecast"]["status"], "invalid")
            self.assertIn("leakage controls", payload["signals"]["forecast"]["reason"])

    def test_malformed_and_unsafe_optional_inputs_are_withheld(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            duckdb = build_dashboard_overview.require_duckdb()
            con = duckdb.connect(database=":memory:")
            bad_anomalies = root / "bad-anomalies.parquet"
            con.execute("CREATE TABLE bad_anomalies (week_start DATE)")
            con.execute(
                f"COPY bad_anomalies TO {build_dashboard_overview.sql_string(bad_anomalies)} "
                "(FORMAT PARQUET)"
            )
            con.close()
            payload, _, _ = self.build(
                paths, root / "bad-anomalies-output", anomalies=bad_anomalies
            )
            self.assertEqual(payload["signals"]["anomalies"]["status"], "invalid")
            self.assertIn("Missing required columns", payload["signals"]["anomalies"]["reason"])
            unsafe_manifest = root / "unsafe-manifest.json"
            unsafe_manifest.write_text(
                json.dumps(
                    {
                        "leakage_controls": {
                            "random_splits_used": True,
                            "target_week_excluded_from_features": False,
                        }
                    }
                )
            )
            payload, _, _ = self.build(
                paths,
                root / "unsafe-manifest-output",
                ml_manifest=unsafe_manifest,
            )
            self.assertEqual(payload["signals"]["forecast"]["status"], "invalid")
            self.assertEqual(payload["signals"]["forecast"]["rows"], [])
            self.assertIn("Forecast withheld", payload["signals"]["forecast"]["reason"])

    def test_forecast_week_and_model_must_align_and_be_strictly_future(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            duckdb = build_dashboard_overview.require_duckdb()
            con = duckdb.connect(database=":memory:")

            mixed_forecast = root / "mixed-forecast.parquet"
            con.execute(
                f"CREATE TABLE mixed_forecast AS SELECT * FROM read_parquet("
                f"{build_dashboard_overview.sql_string(paths['forecast'])})"
            )
            con.execute(
                "INSERT INTO mixed_forecast VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    date(2024, 1, 22),
                    "BRONX",
                    "1",
                    "THEFT",
                    "FELONY",
                    5.0,
                    "other_model",
                    True,
                ],
            )
            con.execute(
                f"COPY mixed_forecast TO "
                f"{build_dashboard_overview.sql_string(mixed_forecast)} (FORMAT PARQUET)"
            )

            historical_forecast = root / "historical-forecast.parquet"
            con.execute(
                "CREATE TABLE historical_forecast AS "
                "SELECT * FROM mixed_forecast WHERE FALSE"
            )
            con.execute(
                "INSERT INTO historical_forecast VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    date(2024, 1, 8),
                    "BRONX",
                    "1",
                    "THEFT",
                    "FELONY",
                    4.0,
                    "test_model",
                    True,
                ],
            )
            con.execute(
                f"COPY historical_forecast TO "
                f"{build_dashboard_overview.sql_string(historical_forecast)} "
                "(FORMAT PARQUET)"
            )
            con.close()

            payload, _, _ = self.build(
                paths,
                root / "mixed-output",
                forecast=mixed_forecast,
            )
            self.assertEqual(payload["signals"]["forecast"]["status"], "invalid")
            self.assertIn("exactly one forecast week", payload["signals"]["forecast"]["reason"])
            self.assertIn("exactly one forecast model", payload["signals"]["forecast"]["reason"])

            historical_manifest = root / "historical-manifest.json"
            manifest = json.loads(paths["ml_manifest"].read_text(encoding="utf-8"))
            manifest["forecast_week"] = "2024-01-08"
            historical_manifest.write_text(json.dumps(manifest), encoding="utf-8")
            payload, _, _ = self.build(
                paths,
                root / "historical-output",
                forecast=historical_forecast,
                ml_manifest=historical_manifest,
            )
            self.assertEqual(payload["signals"]["forecast"]["status"], "invalid")
            self.assertIn("follow the last observed week", payload["signals"]["forecast"]["reason"])

    def test_optional_numeric_values_are_validated_without_clamping(self) -> None:
        for value in (None, float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(build_dashboard_overview.OptionalContractError):
                build_dashboard_overview.required_number(value, "test value")
        with self.assertRaises(build_dashboard_overview.OptionalContractError):
            build_dashboard_overview.required_number(-1, "test count", minimum=0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            duckdb = build_dashboard_overview.require_duckdb()
            con = duckdb.connect(database=":memory:")

            negative_forecast = root / "negative-forecast.parquet"
            con.execute(
                f"CREATE TABLE negative_forecast AS SELECT * FROM read_parquet("
                f"{build_dashboard_overview.sql_string(paths['forecast'])})"
            )
            con.execute(
                "UPDATE negative_forecast SET predicted_crime_count = -1 "
                "WHERE is_next_week_forecast IS TRUE"
            )
            con.execute(
                f"COPY negative_forecast TO "
                f"{build_dashboard_overview.sql_string(negative_forecast)} (FORMAT PARQUET)"
            )

            null_anomaly = root / "null-anomaly.parquet"
            con.execute(
                f"CREATE TABLE null_anomaly AS SELECT * FROM read_parquet("
                f"{build_dashboard_overview.sql_string(paths['anomalies'])})"
            )
            con.execute(
                "UPDATE null_anomaly SET expected_count = NULL "
                "WHERE lower(anomaly_severity) = 'high'"
            )
            con.execute(
                f"COPY null_anomaly TO "
                f"{build_dashboard_overview.sql_string(null_anomaly)} (FORMAT PARQUET)"
            )

            nan_hotspot = root / "nan-hotspot.parquet"
            con.execute(
                f"CREATE TABLE nan_hotspot AS SELECT * FROM read_parquet("
                f"{build_dashboard_overview.sql_string(paths['hotspots'])})"
            )
            con.execute(
                "UPDATE nan_hotspot SET composite_score = CAST('NaN' AS DOUBLE) "
                "WHERE is_high_or_critical_hotspot IS TRUE"
            )
            con.execute(
                f"COPY nan_hotspot TO "
                f"{build_dashboard_overview.sql_string(nan_hotspot)} (FORMAT PARQUET)"
            )
            con.close()

            payload, _, _ = self.build(
                paths, root / "negative-output", forecast=negative_forecast
            )
            self.assertEqual(payload["signals"]["forecast"]["status"], "invalid")
            self.assertIn("predicted_crime_count", payload["signals"]["forecast"]["reason"])
            payload, _, _ = self.build(
                paths, root / "null-output", anomalies=null_anomaly
            )
            self.assertEqual(payload["signals"]["anomalies"]["status"], "invalid")
            self.assertIn("expected_count", payload["signals"]["anomalies"]["reason"])
            payload, _, _ = self.build(
                paths, root / "nan-output", hotspots=nan_hotspot
            )
            self.assertEqual(payload["signals"]["hotspots"]["status"], "invalid")
            self.assertIn("composite_score", payload["signals"]["hotspots"]["reason"])

    def test_hotspot_snapshot_is_single_and_not_future_dated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            duckdb = build_dashboard_overview.require_duckdb()
            con = duckdb.connect(database=":memory:")

            mixed_hotspot = root / "mixed-hotspot.parquet"
            con.execute(
                f"CREATE TABLE mixed_hotspot AS SELECT * FROM read_parquet("
                f"{build_dashboard_overview.sql_string(paths['hotspots'])})"
            )
            con.execute(
                "UPDATE mixed_hotspot SET scoring_end_date = DATE '2024-01-13' "
                "WHERE is_high_or_critical_hotspot IS FALSE"
            )
            con.execute(
                f"COPY mixed_hotspot TO "
                f"{build_dashboard_overview.sql_string(mixed_hotspot)} (FORMAT PARQUET)"
            )

            future_hotspot = root / "future-hotspot.parquet"
            con.execute(
                f"CREATE TABLE future_hotspot AS SELECT * FROM read_parquet("
                f"{build_dashboard_overview.sql_string(paths['hotspots'])})"
            )
            con.execute(
                "UPDATE future_hotspot SET scoring_end_date = DATE '2024-01-15'"
            )
            con.execute(
                f"COPY future_hotspot TO "
                f"{build_dashboard_overview.sql_string(future_hotspot)} (FORMAT PARQUET)"
            )
            con.close()

            payload, _, _ = self.build(
                paths, root / "mixed-output", hotspots=mixed_hotspot
            )
            self.assertEqual(payload["signals"]["hotspots"]["status"], "invalid")
            self.assertIn("exactly one", payload["signals"]["hotspots"]["reason"])
            payload, _, _ = self.build(
                paths, root / "future-output", hotspots=future_hotspot
            )
            self.assertEqual(payload["signals"]["hotspots"]["status"], "invalid")
            self.assertIn("cannot exceed", payload["signals"]["hotspots"]["reason"])

    def test_duplicate_forecast_and_misaligned_metrics_are_withheld(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root / "inputs")
            duckdb = build_dashboard_overview.require_duckdb()
            con = duckdb.connect(database=":memory:")
            duplicate_forecast = root / "duplicate-forecast.parquet"
            con.execute(
                f"CREATE TABLE duplicate_forecast AS SELECT * FROM read_parquet("
                f"{build_dashboard_overview.sql_string(paths['forecast'])})"
            )
            con.execute(
                f"INSERT INTO duplicate_forecast SELECT * FROM read_parquet("
                f"{build_dashboard_overview.sql_string(paths['forecast'])}) "
                "WHERE is_next_week_forecast IS TRUE"
            )
            con.execute(
                f"COPY duplicate_forecast TO "
                f"{build_dashboard_overview.sql_string(duplicate_forecast)} "
                "(FORMAT PARQUET)"
            )
            con.close()

            payload, _, _ = self.build(
                paths, root / "duplicate-output", forecast=duplicate_forecast
            )
            self.assertEqual(payload["signals"]["forecast"]["status"], "invalid")
            self.assertIn("Duplicate forecast", payload["signals"]["forecast"]["reason"])

            mismatched_metrics = root / "mismatched-metrics.json"
            metrics = json.loads(paths["ml_metrics"].read_text(encoding="utf-8"))
            metrics["model_config"]["model_name"] = "different_model"
            mismatched_metrics.write_text(json.dumps(metrics), encoding="utf-8")
            payload, _, _ = self.build(
                paths,
                root / "mismatched-output",
                ml_metrics=mismatched_metrics,
            )
            error = payload["signals"]["forecast"]["summary"]["historicalError"]
            self.assertEqual(error["status"], "invalid")
            self.assertIn("do not match", error["reason"])


if __name__ == "__main__":
    unittest.main()

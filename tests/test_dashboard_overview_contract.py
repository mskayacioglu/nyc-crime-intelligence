import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path


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
        con.execute(
            """
            CREATE TABLE clean_events (
                complaint_from_date DATE,
                is_clean_event_for_aggregate BOOLEAN,
                complaint_number VARCHAR,
                SUSP_RACE VARCHAR
            )
            """
        )
        clean_rows = [
            (date(2024, 1, 1), True, f"event-{index}", "PRIVATE-VALUE")
            for index in range(9)
        ]
        clean_rows.extend(
            [
                (date(2024, 1, 14), True, "event-9", "PRIVATE-VALUE"),
                (date(2099, 1, 1), False, "unsafe-event", "PRIVATE-VALUE"),
            ]
        )
        con.executemany("INSERT INTO clean_events VALUES (?, ?, ?, ?)", clean_rows)
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
                residual_count DOUBLE,
                is_anomaly BOOLEAN,
                anomaly_severity VARCHAR,
                anomaly_score DOUBLE
            )
            """
        )
        con.executemany(
            "INSERT INTO anomaly_input VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    3.0,
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
            json.dumps({"phase": "Phase 6A", "generated_at_utc": "2024-01-14T00:00:00Z"})
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

import importlib.util
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "analytics" / "build_anomalies.py"
)
SPEC = importlib.util.spec_from_file_location("build_anomalies", MODULE_PATH)
build_anomalies = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_anomalies)
PROJECT_ROOT = MODULE_PATH.parents[2]


class AnomalyDetectionContractTest(unittest.TestCase):
    def test_metrics_and_nested_ml_status_paths_are_portable(self) -> None:
        inputs = {
            "weekly_area": PROJECT_ROOT / "data/processed/crime_weekly_area.parquet",
            "ml_predictions": PROJECT_ROOT / "data/processed/ml_predictions.parquet",
            "ml_model_manifest": PROJECT_ROOT
            / "models/weekly_forecast/model_manifest.json",
        }
        outputs = {
            "anomalies": PROJECT_ROOT / "data/processed/anomalies.parquet",
            "metrics": PROJECT_ROOT / "data/processed/anomaly_metrics.json",
            "report": PROJECT_ROOT / "reports/anomaly_methodology.md",
        }
        ml_status = {
            "status": "used",
            "predictions_path": inputs["ml_predictions"],
            "model_manifest_path": inputs["ml_model_manifest"],
            "manifest_available": True,
        }
        severity_counts = [
            {"anomaly_severity": label}
            for label in build_anomalies.SEVERITY_LABELS
        ]

        with (
            patch.object(build_anomalies, "build_analysis_window", return_value={}),
            patch.object(build_anomalies, "build_record_counts", return_value={}),
            patch.object(
                build_anomalies,
                "build_severity_counts",
                return_value=severity_counts,
            ),
            patch.object(
                build_anomalies, "build_top_recent_anomalies", return_value=[]
            ),
            patch.object(
                build_anomalies, "build_top_overall_anomalies", return_value=[]
            ),
            patch.object(
                build_anomalies,
                "build_volatile_borough_offense_groups",
                return_value=[],
            ),
        ):
            payload = build_anomalies.build_metrics_payload(
                None,
                project_root=PROJECT_ROOT,
                inputs=inputs,
                outputs=outputs,
                input_summary={},
                ml_summary={},
                config=build_anomalies.AnomalyConfig(),
                ml_status=ml_status,
                scoring_end_week=date(2024, 1, 29),
                latest_week_excluded_from_scoring=True,
                top_n=1,
            )

        self.assertEqual(
            payload["inputs"],
            {
                "weekly_area": "data/processed/crime_weekly_area.parquet",
                "ml_predictions": "data/processed/ml_predictions.parquet",
                "ml_model_manifest": "models/weekly_forecast/model_manifest.json",
            },
        )
        self.assertEqual(
            payload["outputs"],
            {
                "anomalies": "data/processed/anomalies.parquet",
                "metrics": "data/processed/anomaly_metrics.json",
                "report": "reports/anomaly_methodology.md",
            },
        )
        self.assertEqual(
            payload["leakage_controls"]["ml_prediction_status"],
            {
                "status": "used",
                "predictions_path": "data/processed/ml_predictions.parquet",
                "model_manifest_path": "models/weekly_forecast/model_manifest.json",
                "manifest_available": True,
            },
        )
        self.assertNotIn(str(PROJECT_ROOT), repr(payload["inputs"]))
        self.assertNotIn(
            str(PROJECT_ROOT),
            repr(payload["leakage_controls"]["ml_prediction_status"]),
        )

    def test_external_metrics_and_ml_status_paths_fail_closed(self) -> None:
        outside_path = PROJECT_ROOT.parent / "outside-anomaly-input.parquet"

        with self.assertRaisesRegex(ValueError, "inside the project root"):
            build_anomalies.repository_relative_path(PROJECT_ROOT, outside_path)
        with self.assertRaisesRegex(ValueError, "inside the project root"):
            build_anomalies.repository_relative_ml_status(
                PROJECT_ROOT,
                {
                    "status": "used",
                    "predictions_path": outside_path,
                    "model_manifest_path": None,
                },
            )

    def test_main_rejects_external_outputs_before_opening_duckdb(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            project_root = directory / "repository"
            project_root.mkdir()
            outside_path = directory / "anomalies.parquet"

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "build_anomalies.py",
                        "--project-root",
                        str(project_root),
                        "--anomalies-output",
                        str(outside_path),
                    ],
                ),
                patch.object(build_anomalies, "require_duckdb") as require_duckdb,
                self.assertRaisesRegex(ValueError, "inside the project root"),
            ):
                build_anomalies.main()

            require_duckdb.assert_not_called()

    def write_weekly_input(self, con, weekly_path: Path, rows: list[tuple]) -> None:
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
        con.executemany(
            "INSERT INTO weekly_input VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        con.execute(
            f"COPY weekly_input TO {build_anomalies.sql_string(weekly_path)} (FORMAT PARQUET)"
        )

    def build_views(self, weekly_path: Path, config: build_anomalies.AnomalyConfig):
        duckdb = build_anomalies.require_duckdb()
        con = duckdb.connect(database=":memory:")
        build_anomalies.create_input_views(con, weekly_path)
        build_anomalies.create_empty_ml_prediction_view(con)
        min_week, max_week = build_anomalies.get_week_bounds(con)
        build_anomalies.create_anomaly_views(
            con,
            min_week=min_week,
            max_week=max_week,
            config=config,
        )
        return con

    def test_output_schema_contract(self) -> None:
        self.assertEqual(
            build_anomalies.ANOMALY_OUTPUT_COLUMNS,
            [
                "rank_overall",
                "rank_in_week",
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
                "historical_residual_count",
                "ml_residual_count",
                "pct_change_vs_trailing_8_week_mean",
                "trailing_8_week_mean",
                "trailing_13_week_mean",
                "trailing_26_week_mean",
                "trailing_13_week_std",
                "rolling_z_score",
                "rolling_26_week_median",
                "rolling_26_week_mad",
                "robust_z_score",
                "ml_residual_scaled_score",
                "prior_13_week_count",
                "prior_26_week_count",
                "prior_13_week_total_count",
                "prior_26_week_total_count",
                "recent_nonzero_week_count",
                "has_ml_prediction",
                "passes_volume_filter",
                "is_historical_anomaly",
                "is_ml_anomaly",
                "is_anomaly",
                "anomaly_severity",
                "anomaly_score",
            ],
        )

    def test_sensitive_demographic_columns_are_not_anomaly_features(self) -> None:
        used_columns = set(build_anomalies.ANOMALY_COLUMNS_USED).union(
            build_anomalies.HISTORICAL_FEATURE_COLUMNS,
            build_anomalies.ANOMALY_OUTPUT_COLUMNS,
        )
        overlap = set(build_anomalies.SENSITIVE_COLUMNS).intersection(used_columns)
        self.assertEqual(overlap, set())

    def test_rolling_features_use_prior_weeks_only(self) -> None:
        duckdb = build_anomalies.require_duckdb()
        with tempfile.TemporaryDirectory() as tmpdir:
            weekly_path = Path(tmpdir) / "weekly.parquet"
            con = duckdb.connect(database=":memory:")
            start = date(2024, 1, 1)
            rows = [
                (
                    start + timedelta(weeks=week_index),
                    "B",
                    "1",
                    "THEFT",
                    "MISDEMEANOR",
                    week_index + 1,
                )
                for week_index in range(13)
            ]
            target_week = start + timedelta(weeks=13)
            rows.append((target_week, "B", "1", "THEFT", "MISDEMEANOR", 100))
            self.write_weekly_input(con, weekly_path, rows)

            scored_con = self.build_views(weekly_path, build_anomalies.AnomalyConfig())
            row = scored_con.execute(
                """
                SELECT
                    expected_historical_count,
                    trailing_8_week_mean,
                    prior_13_week_total_count,
                    historical_residual_count
                FROM anomaly_candidates
                WHERE week_start = DATE '2024-04-01'
                    AND borough = 'B'
                    AND precinct = '1'
                    AND offense_type = 'THEFT'
                    AND law_category = 'MISDEMEANOR'
                """
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertAlmostEqual(row[0], 7.0)
        self.assertAlmostEqual(row[1], 9.5)
        self.assertEqual(row[2], 91)
        self.assertAlmostEqual(row[3], 93.0)

    def test_sparse_segments_do_not_get_inflated_anomaly_severity(self) -> None:
        duckdb = build_anomalies.require_duckdb()
        with tempfile.TemporaryDirectory() as tmpdir:
            weekly_path = Path(tmpdir) / "weekly.parquet"
            con = duckdb.connect(database=":memory:")
            self.write_weekly_input(
                con,
                weekly_path,
                [
                    (date(2024, 1, 1), "B", "1", "RARE", "FELONY", 1),
                    (date(2024, 4, 1), "B", "1", "RARE", "FELONY", 4),
                ],
            )

            scored_con = self.build_views(weekly_path, build_anomalies.AnomalyConfig())
            row = scored_con.execute(
                """
                SELECT
                    prior_13_week_count,
                    prior_13_week_total_count,
                    actual_crime_count,
                    passes_volume_filter,
                    is_anomaly,
                    anomaly_severity
                FROM anomaly_candidates
                WHERE week_start = DATE '2024-04-01'
                """
            ).fetchone()
            anomaly_count = scored_con.execute("SELECT COUNT(*) FROM anomalies").fetchone()[0]

        self.assertEqual(row[0], 13)
        self.assertEqual(row[1], 1)
        self.assertEqual(row[2], 4)
        self.assertFalse(row[3])
        self.assertFalse(row[4])
        self.assertEqual(row[5], "none")
        self.assertEqual(anomaly_count, 0)

    def test_ml_manifest_leakage_controls_are_enforced(self) -> None:
        safe_manifest = {
            "leakage_controls": {
                "split_type": "time_based_validation_and_backtest",
                "random_splits_used": False,
                "target_week_excluded_from_features": True,
            }
        }
        unsafe_manifest = {
            "leakage_controls": {
                "split_type": "random",
                "random_splits_used": True,
                "target_week_excluded_from_features": False,
            }
        }
        self.assertFalse(build_anomalies.ml_predictions_are_leakage_safe(None))
        self.assertTrue(build_anomalies.ml_predictions_are_leakage_safe(safe_manifest))
        self.assertFalse(build_anomalies.ml_predictions_are_leakage_safe(unsafe_manifest))

    def test_latest_week_is_excluded_from_scoring_by_default(self) -> None:
        min_week = date(2024, 1, 1)
        max_week = date(2024, 2, 5)

        self.assertEqual(
            build_anomalies.compute_scoring_end_week(
                min_week,
                max_week,
                include_latest_week=False,
            ),
            date(2024, 1, 29),
        )
        self.assertEqual(
            build_anomalies.compute_scoring_end_week(
                min_week,
                max_week,
                include_latest_week=True,
            ),
            max_week,
        )

    def test_volatile_groups_require_minimum_evaluated_weeks(self) -> None:
        duckdb = build_anomalies.require_duckdb()
        con = duckdb.connect(database=":memory:")
        con.execute(
            """
            CREATE TABLE anomaly_candidates AS
            SELECT
                'B' AS borough,
                'SHORT' AS offense_type,
                true AS is_evaluable,
                true AS passes_volume_filter,
                10::BIGINT AS actual_crime_count,
                true AS is_anomaly,
                'high' AS anomaly_severity,
                2.0::DOUBLE AS trailing_13_week_std,
                5.0::DOUBLE AS historical_residual_count,
                4.0::DOUBLE AS anomaly_score
            FROM range(16)
            UNION ALL
            SELECT
                'B' AS borough,
                'STABLE' AS offense_type,
                true AS is_evaluable,
                true AS passes_volume_filter,
                10::BIGINT AS actual_crime_count,
                true AS is_anomaly,
                'high' AS anomaly_severity,
                1.0::DOUBLE AS trailing_13_week_std,
                4.0::DOUBLE AS historical_residual_count,
                3.0::DOUBLE AS anomaly_score
            FROM range(52)
            """
        )

        rows = build_anomalies.build_volatile_borough_offense_groups(
            con,
            min_actual_count=100,
            min_evaluated_weeks=52,
            limit=10,
        )

        self.assertEqual([row["offense_type"] for row in rows], ["STABLE"])


if __name__ == "__main__":
    unittest.main()

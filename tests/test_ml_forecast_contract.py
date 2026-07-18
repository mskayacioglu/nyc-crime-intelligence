import importlib.util
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "models" / "build_ml_forecast.py"
)
SPEC = importlib.util.spec_from_file_location("build_ml_forecast", MODULE_PATH)
build_ml_forecast = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_ml_forecast)


class MLForecastContractTest(unittest.TestCase):
    def test_prediction_schema_contract(self) -> None:
        self.assertEqual(
            build_ml_forecast.PREDICTION_COLUMNS,
            [
                "week_start",
                "borough",
                "precinct",
                "offense_type",
                "law_category",
                "actual_crime_count",
                "predicted_crime_count",
                "ml_model_name",
                "lag_1_week_count",
                "lag_52_week_count",
                "trailing_4_week_mean",
                "trailing_8_week_mean",
                "segment_prior_mean_count",
                "is_backtest_week",
                "is_next_week_forecast",
                "segment_first_week",
                "segment_last_observed_week",
                "segment_observed_week_count",
                "segment_total_crime_count",
            ],
        )

    def test_sensitive_demographic_columns_are_not_forecast_or_model_features(self) -> None:
        used_columns = set(build_ml_forecast.FORECAST_COLUMNS_USED).union(
            build_ml_forecast.ENGINEERED_FEATURE_COLUMNS,
            build_ml_forecast.MODEL_FEATURE_COLUMNS,
        )
        overlap = set(build_ml_forecast.SENSITIVE_COLUMNS).intersection(used_columns)
        self.assertEqual(overlap, set())

    def test_validation_window_ends_before_backtest_window(self) -> None:
        validation_start, validation_end = build_ml_forecast.compute_validation_window(
            date(2023, 1, 2),
            date(2024, 1, 1),
            validation_weeks=4,
        )
        self.assertEqual(validation_start, date(2023, 12, 4))
        self.assertEqual(validation_end, date(2023, 12, 25))
        self.assertLess(validation_end, date(2024, 1, 1))

    def test_baseline_manifest_backtest_window_is_reused_when_valid(self) -> None:
        manifest = {
            "backtest_window": {
                "backtest_start_week": "2024-12-30",
                "backtest_end_week": "2025-12-22",
            }
        }
        self.assertEqual(
            build_ml_forecast.get_backtest_window_from_baseline(
                manifest,
                min_week=date(2005, 12, 26),
                max_week=date(2025, 12, 29),
            ),
            (date(2024, 12, 30), date(2025, 12, 22)),
        )

    def test_feature_rows_zero_fill_missing_weeks_and_use_prior_weeks_only(self) -> None:
        duckdb = build_ml_forecast.require_duckdb()
        with tempfile.TemporaryDirectory() as tmpdir:
            weekly_path = Path(tmpdir) / "weekly.parquet"
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
            con.execute(
                """
                INSERT INTO weekly_input VALUES
                    (DATE '2024-01-01', 'B', '1', 'THEFT', 'MISDEMEANOR', 5),
                    (DATE '2024-01-15', 'B', '1', 'THEFT', 'MISDEMEANOR', 9),
                    (DATE '2024-01-29', 'B', '1', 'THEFT', 'MISDEMEANOR', 4)
                """
            )
            con.execute(
                f"COPY weekly_input TO {build_ml_forecast.sql_string(weekly_path)} (FORMAT PARQUET)"
            )

            build_ml_forecast.create_input_views(con, weekly_path)
            min_week, max_week = build_ml_forecast.get_week_bounds(con)
            forecast_week = max_week + timedelta(weeks=1)
            build_ml_forecast.create_ml_feature_views(
                con,
                min_week=min_week,
                max_week=max_week,
                forecast_week=forecast_week,
                backtest_start=date(2024, 1, 8),
                backtest_end=max_week,
            )

            rows = con.execute(
                """
                SELECT
                    week_start,
                    actual_crime_count,
                    lag_1_week_count,
                    trailing_4_week_mean,
                    trailing_8_week_mean,
                    segment_prior_mean_count,
                    is_next_week_forecast
                FROM ml_feature_rows
                ORDER BY week_start
                """
            ).fetchall()

        rows_by_week = {row[0]: row for row in rows}
        self.assertEqual(rows_by_week[date(2024, 1, 8)][1], 0)
        self.assertEqual(rows_by_week[date(2024, 1, 8)][2], 5)
        self.assertEqual(rows_by_week[date(2024, 1, 15)][2], 0)
        self.assertEqual(rows_by_week[date(2024, 1, 29)][2], 0)
        self.assertAlmostEqual(rows_by_week[date(2024, 1, 29)][3], 3.5)
        self.assertIsNone(rows_by_week[date(2024, 2, 5)][1])
        self.assertEqual(rows_by_week[date(2024, 2, 5)][2], 4)
        self.assertAlmostEqual(rows_by_week[date(2024, 2, 5)][3], 3.25)
        self.assertTrue(rows_by_week[date(2024, 2, 5)][6])

    def test_generated_metrics_and_report_are_portable_and_current(self) -> None:
        overall = {
            "prediction_count": 10,
            "total_backtest_rows": 10,
            "prediction_coverage_pct": 100.0,
            "actual_event_count": 42,
            "total_actual_event_count": 42,
            "mae": 0.48,
            "rmse": 1.39,
            "weighted_mae": 3.65,
        }
        baseline_manifest = {
            "selected_baseline": {
                "baseline_method": "trailing_8_week_mean",
                "prediction_count": 8,
                "total_backtest_rows": 10,
                "prediction_coverage_pct": 80.0,
                "actual_event_count": 40,
                "mae": 0.5,
                "rmse": 1.41,
                "weighted_mae": 3.7,
            }
        }
        model_params = {
            "alpha": 0.25,
            "beta": 0.1,
            "gamma": 0.05,
            "shrinkage": 1.0,
            "validation_prediction_count": 8,
            "validation_actual_event_count": 40,
            "validation_mae": 0.49,
            "validation_rmse": 1.4,
            "validation_weighted_mae": 3.68,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            inputs = {
                "weekly_area": project_root
                / "data/processed/crime_weekly_area.parquet",
                "baseline_manifest": project_root
                / "models/baseline_forecast/model_manifest.json",
            }
            outputs = {
                "model_manifest": project_root
                / "models/weekly_forecast/model_manifest.json",
                "predictions": project_root / "data/processed/ml_predictions.parquet",
                "metrics": project_root / "data/processed/ml_metrics.json",
                "report": project_root / "reports/ml_model_report.md",
            }
            with (
                patch.object(
                    build_ml_forecast,
                    "build_metrics",
                    side_effect=[[overall], [], [], []],
                ),
                patch.object(
                    build_ml_forecast,
                    "build_record_counts",
                    return_value={"backtest_rows": 10, "next_week_forecast_rows": 1},
                ),
                patch.object(
                    build_ml_forecast,
                    "build_top_k_capture",
                    return_value={"evaluated_weeks": 1},
                ),
                patch.object(
                    build_ml_forecast, "build_hardest_segments", return_value=[]
                ),
            ):
                payload = build_ml_forecast.build_metrics_payload(
                    None,
                    project_root=project_root,
                    inputs=inputs,
                    outputs=outputs,
                    input_summary={
                        "min_week_start": date(2024, 1, 1),
                        "max_week_start": date(2024, 1, 8),
                        "segment_count": 1,
                    },
                    baseline_manifest=baseline_manifest,
                    backtest_start=date(2024, 1, 1),
                    backtest_end=date(2024, 1, 1),
                    validation_start=date(2023, 12, 4),
                    validation_end=date(2023, 12, 25),
                    forecast_week=date(2024, 1, 15),
                    validation_weeks=4,
                    model_params=model_params,
                    top_k_fraction=0.1,
                    hardest_segment_limit=1,
                    min_hard_segment_actual_count=1,
                )

            build_ml_forecast.write_metrics_json(outputs["metrics"], payload)
            build_ml_forecast.write_model_manifest(
                outputs["model_manifest"], payload, project_root=project_root
            )
            build_ml_forecast.write_ml_report(outputs["report"], payload)
            metrics_text = outputs["metrics"].read_text(encoding="utf-8")
            manifest_text = outputs["model_manifest"].read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            report_text = outputs["report"].read_text(encoding="utf-8")

        self.assertEqual(
            payload["inputs"],
            {
                "weekly_area": "data/processed/crime_weekly_area.parquet",
                "baseline_manifest": "models/baseline_forecast/model_manifest.json",
            },
        )
        self.assertEqual(
            payload["outputs"],
            {
                "model_manifest": "models/weekly_forecast/model_manifest.json",
                "predictions": "data/processed/ml_predictions.parquet",
                "metrics": "data/processed/ml_metrics.json",
                "report": "reports/ml_model_report.md",
            },
        )
        self.assertEqual(
            {
                key: manifest[key]
                for key in (
                    "training_input",
                    "baseline_manifest_input",
                    "prediction_output",
                    "metrics_output",
                    "report_output",
                )
            },
            {
                "training_input": "data/processed/crime_weekly_area.parquet",
                "baseline_manifest_input": "models/baseline_forecast/model_manifest.json",
                "prediction_output": "data/processed/ml_predictions.parquet",
                "metrics_output": "data/processed/ml_metrics.json",
                "report_output": "reports/ml_model_report.md",
            },
        )
        for text in (metrics_text, manifest_text, report_text):
            self.assertNotIn(str(project_root), text)
        self.assertIn("8 baseline rows versus 10 ML rows", report_text)
        self.assertIn("not a matched-row, like-for-like gain", report_text)
        self.assertNotIn("Before dashboard use", report_text)
        self.assertNotIn("formalize retraining cadence", report_text)
        self.assertIn(
            "no prediction interval, formal drift monitor, model-age threshold, or "
            "general retraining cadence is established",
            report_text,
        )
        self.assertIn(
            "fixed historical/demo dashboard is not operational guidance", report_text
        )
        self.assertIn("does not invent any of those capabilities or policies", report_text)

    def test_model_manifest_records_ml_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            payload = {
                "generated_at_utc": "2026-07-05T00:00:00+00:00",
                "phase": "Phase 5 - ML Forecast Model",
                "inputs": {
                    "weekly_area": project_root
                    / "data/processed/crime_weekly_area.parquet",
                    "baseline_manifest": project_root
                    / "models/baseline_forecast/model_manifest.json",
                },
                "outputs": {
                    "model_manifest": project_root
                    / "models/weekly_forecast/model_manifest.json",
                    "predictions": project_root / "data/processed/ml_predictions.parquet",
                    "metrics": project_root / "data/processed/ml_metrics.json",
                    "report": project_root / "reports/ml_model_report.md",
                },
                "forecast_columns_used": build_ml_forecast.FORECAST_COLUMNS_USED,
                "engineered_feature_columns": build_ml_forecast.ENGINEERED_FEATURE_COLUMNS,
                "model_feature_columns": build_ml_forecast.MODEL_FEATURE_COLUMNS,
                "model_config": {
                    "model_name": build_ml_forecast.MODEL_NAME,
                    "model_version": build_ml_forecast.MODEL_VERSION,
                    "dependency_mode": "stdlib_plus_duckdb_no_sklearn",
                    "target": "next-week crime_count by week_start, borough, precinct, offense_type, law_category",
                    "selection_objective": build_ml_forecast.SELECTION_OBJECTIVE,
                    "selected_parameters": {
                        "alpha": 0.25,
                        "beta": 0.1,
                        "gamma": 0.05,
                        "shrinkage": 1.0,
                    },
                    "prediction_formula": "max(0, ...)",
                    "zero_fill_rule": "Missing weekly rows are treated as zero.",
                    "validation_window": {
                        "validation_start_week": date(2024, 1, 1),
                        "validation_end_week": date(2024, 12, 23),
                    },
                },
                "analysis_window": {
                    "min_week_start": date(2005, 12, 26),
                    "max_week_start": date(2025, 12, 29),
                    "segment_count": 8466,
                    "backtest_start_week": date(2024, 12, 30),
                    "backtest_end_week": date(2025, 12, 22),
                    "next_week_forecast_week": date(2026, 1, 5),
                },
                "record_counts": {"backtest_rows": 437144},
                "metrics": {"overall": []},
                "baseline_comparison": {"beats_baseline_all_core_metrics": True},
                "ethics": {
                    "sensitive_columns_excluded": build_ml_forecast.SENSITIVE_COLUMNS,
                },
            }

            manifest = build_ml_forecast.build_model_manifest(
                payload, project_root=project_root
            )

            payload["inputs"]["weekly_area"] = project_root.parent / "outside.parquet"
            with self.assertRaisesRegex(ValueError, "inside the project root"):
                build_ml_forecast.build_model_manifest(
                    payload, project_root=project_root
                )

        self.assertEqual(manifest["artifact_type"], "weekly_forecast_ml_model")
        self.assertEqual(
            {
                key: manifest[key]
                for key in (
                    "training_input",
                    "baseline_manifest_input",
                    "prediction_output",
                    "metrics_output",
                    "report_output",
                )
            },
            {
                "training_input": "data/processed/crime_weekly_area.parquet",
                "baseline_manifest_input": "models/baseline_forecast/model_manifest.json",
                "prediction_output": "data/processed/ml_predictions.parquet",
                "metrics_output": "data/processed/ml_metrics.json",
                "report_output": "reports/ml_model_report.md",
            },
        )
        self.assertEqual(manifest["model"]["model_name"], build_ml_forecast.MODEL_NAME)
        self.assertFalse(manifest["leakage_controls"]["random_splits_used"])
        overlap = set(manifest["feature_policy"]["engineered_feature_columns"]).intersection(
            manifest["feature_policy"]["sensitive_columns_excluded"]
        )
        self.assertEqual(overlap, set())


if __name__ == "__main__":
    unittest.main()

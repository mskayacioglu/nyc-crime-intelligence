import importlib.util
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


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

    def test_model_manifest_records_ml_contract(self) -> None:
        payload = {
            "generated_at_utc": "2026-07-05T00:00:00+00:00",
            "phase": "Phase 5 - ML Forecast Model",
            "inputs": {
                "weekly_area": "data/processed/crime_weekly_area.parquet",
                "baseline_manifest": "models/baseline_forecast/model_manifest.json",
            },
            "outputs": {
                "model_manifest": "models/weekly_forecast/model_manifest.json",
                "predictions": "data/processed/ml_predictions.parquet",
                "metrics": "data/processed/ml_metrics.json",
                "report": "reports/ml_model_report.md",
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

        manifest = build_ml_forecast.build_model_manifest(payload)

        self.assertEqual(manifest["artifact_type"], "weekly_forecast_ml_model")
        self.assertEqual(manifest["model"]["model_name"], build_ml_forecast.MODEL_NAME)
        self.assertFalse(manifest["leakage_controls"]["random_splits_used"])
        overlap = set(manifest["feature_policy"]["engineered_feature_columns"]).intersection(
            manifest["feature_policy"]["sensitive_columns_excluded"]
        )
        self.assertEqual(overlap, set())


if __name__ == "__main__":
    unittest.main()

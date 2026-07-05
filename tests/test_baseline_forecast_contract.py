import importlib.util
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "models" / "build_baseline_forecast.py"
)
SPEC = importlib.util.spec_from_file_location("build_baseline_forecast", MODULE_PATH)
build_baseline_forecast = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_baseline_forecast)


class BaselineForecastContractTest(unittest.TestCase):
    def test_prediction_schema_contract(self) -> None:
        self.assertEqual(
            build_baseline_forecast.PREDICTION_COLUMNS,
            [
                "week_start",
                "borough",
                "precinct",
                "offense_type",
                "law_category",
                "actual_crime_count",
                "previous_week",
                "trailing_4_week_mean",
                "trailing_8_week_mean",
                "previous_year_same_week",
                "is_backtest_week",
                "is_next_week_forecast",
                "segment_first_week",
                "segment_last_observed_week",
                "segment_observed_week_count",
                "segment_total_crime_count",
            ],
        )

    def test_sensitive_demographic_columns_are_not_forecast_features(self) -> None:
        overlap = set(build_baseline_forecast.SENSITIVE_COLUMNS).intersection(
            build_baseline_forecast.FORECAST_COLUMNS_USED
        )
        self.assertEqual(overlap, set())

    def test_backtest_window_excludes_latest_week_by_default(self) -> None:
        backtest_start, backtest_end = build_baseline_forecast.compute_backtest_window(
            date(2024, 1, 1),
            date(2024, 3, 25),
            backtest_weeks=4,
            include_latest_week=False,
        )
        self.assertEqual(backtest_start, date(2024, 2, 26))
        self.assertEqual(backtest_end, date(2024, 3, 18))

    def test_predictions_zero_fill_missing_weeks_and_use_prior_weeks_only(self) -> None:
        duckdb = build_baseline_forecast.require_duckdb()
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
                f"COPY weekly_input TO {build_baseline_forecast.sql_string(weekly_path)} (FORMAT PARQUET)"
            )

            build_baseline_forecast.validate_parquet_columns(
                con, weekly_path, build_baseline_forecast.WEEKLY_REQUIRED_COLUMNS
            )
            build_baseline_forecast.validate_weekly_source(con, weekly_path)
            build_baseline_forecast.create_input_views(con, weekly_path)
            min_week, max_week = build_baseline_forecast.get_week_bounds(con)
            forecast_week = max_week + timedelta(weeks=1)
            build_baseline_forecast.create_prediction_views(
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
                    previous_week,
                    trailing_4_week_mean,
                    is_next_week_forecast
                FROM baseline_predictions
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
        self.assertTrue(rows_by_week[date(2024, 2, 5)][4])

    def test_metrics_include_all_baseline_methods_when_coverage_is_zero(self) -> None:
        duckdb = build_baseline_forecast.require_duckdb()
        with tempfile.TemporaryDirectory() as tmpdir:
            weekly_path = Path(tmpdir) / "weekly.parquet"
            con = duckdb.connect(database=":memory:")
            con.execute(
                """
                CREATE TABLE weekly_input AS
                SELECT
                    DATE '2024-01-01' AS week_start,
                    'B' AS borough,
                    '1' AS precinct,
                    'THEFT' AS offense_type,
                    'MISDEMEANOR' AS law_category,
                    5::BIGINT AS crime_count
                """
            )
            con.execute(
                f"COPY weekly_input TO {build_baseline_forecast.sql_string(weekly_path)} (FORMAT PARQUET)"
            )
            build_baseline_forecast.create_input_views(con, weekly_path)
            build_baseline_forecast.create_prediction_views(
                con,
                min_week=date(2024, 1, 1),
                max_week=date(2024, 1, 1),
                forecast_week=date(2024, 1, 8),
                backtest_start=date(2024, 1, 1),
                backtest_end=date(2024, 1, 1),
            )
            overall = build_baseline_forecast.build_metrics(con)

        self.assertEqual(
            {row["baseline_method"] for row in overall},
            set(build_baseline_forecast.BASELINE_METHODS),
        )
        previous_year = [
            row for row in overall if row["baseline_method"] == "previous_year_same_week"
        ][0]
        self.assertEqual(previous_year["prediction_count"], 0)

    def test_model_manifest_records_baseline_contract(self) -> None:
        payload = {
            "generated_at_utc": "2026-07-05T00:00:00+00:00",
            "phase": "Phase 4 - Baseline Forecast Model",
            "inputs": {"weekly_area": "data/processed/crime_weekly_area.parquet"},
            "outputs": {
                "model_manifest": "models/baseline_forecast/model_manifest.json",
                "predictions": "data/processed/baseline_predictions.parquet",
                "metrics": "data/processed/baseline_metrics.json",
                "report": "reports/baseline_model_report.md",
            },
            "forecast_columns_used": build_baseline_forecast.FORECAST_COLUMNS_USED,
            "forecast_config": {
                "target": "next-week crime_count by week_start, borough, precinct, offense_type, law_category",
                "include_latest_week_in_backtest": False,
                "zero_fill_rule": "Missing weekly rows are treated as zero.",
                "baseline_model_rules": build_baseline_forecast.BASELINE_MODEL_RULES,
            },
            "analysis_window": {
                "min_week_start": date(2024, 1, 1),
                "max_week_start": date(2024, 12, 30),
                "segment_count": 10,
                "backtest_start_week": date(2024, 1, 8),
                "backtest_end_week": date(2024, 12, 23),
                "next_week_forecast_week": date(2025, 1, 6),
            },
            "record_counts": {"backtest_rows": 100},
            "metrics": {"overall": []},
            "best_baseline": {"baseline_method": "trailing_8_week_mean"},
            "ethics": {
                "sensitive_columns_excluded": build_baseline_forecast.SENSITIVE_COLUMNS,
            },
        }

        manifest = build_baseline_forecast.build_model_manifest(payload)

        self.assertEqual(manifest["artifact_type"], "baseline_forecast_model")
        self.assertEqual(manifest["selected_baseline"]["baseline_method"], "trailing_8_week_mean")
        self.assertEqual(
            {rule["baseline_method"] for rule in manifest["baseline_model_rules"]},
            set(build_baseline_forecast.BASELINE_METHODS),
        )
        overlap = set(manifest["feature_policy"]["forecast_columns_used"]).intersection(
            manifest["feature_policy"]["sensitive_columns_excluded"]
        )
        self.assertEqual(overlap, set())


if __name__ == "__main__":
    unittest.main()

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "analytics" / "build_dashboard_summary.py"
)
SPEC = importlib.util.spec_from_file_location("build_dashboard_summary", MODULE_PATH)
build_dashboard_summary = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_dashboard_summary)


class AnalyticsPipelineContractTest(unittest.TestCase):
    def minimal_payload(self) -> dict:
        return {
            "generated_at_utc": "2026-07-05T00:00:00+00:00",
            "inputs": {},
            "analytics_columns_used": build_dashboard_summary.ANALYTICS_COLUMNS_USED,
            "analysis_window": {},
            "record_counts": {},
            "trends": {"yearly": [], "monthly": [], "weekly": []},
            "rankings": {"boroughs": [], "precincts": []},
            "distributions": {"offense_types": {}, "law_categories": []},
            "temporal_patterns": {"hour_of_day": [], "day_of_week": []},
            "growth_decline": {"borough_offense": {}, "precinct_offense": {}},
            "map_ready": {"precinct_summary": [], "heatmap_cells": []},
            "ethics": {
                "sensitive_columns_excluded": build_dashboard_summary.SENSITIVE_COLUMNS,
            },
        }

    def test_dashboard_summary_required_sections_are_validated(self) -> None:
        payload = self.minimal_payload()
        build_dashboard_summary.validate_dashboard_summary_payload(payload)

        del payload["trends"]
        with self.assertRaisesRegex(ValueError, "missing required sections"):
            build_dashboard_summary.validate_dashboard_summary_payload(payload)

    def test_dashboard_summary_nested_sections_are_validated(self) -> None:
        payload = self.minimal_payload()
        del payload["temporal_patterns"]["day_of_week"]

        with self.assertRaisesRegex(ValueError, "temporal_patterns"):
            build_dashboard_summary.validate_dashboard_summary_payload(payload)

    def test_sensitive_demographic_columns_are_not_analytics_features(self) -> None:
        overlap = set(build_dashboard_summary.SENSITIVE_COLUMNS).intersection(
            build_dashboard_summary.ANALYTICS_COLUMNS_USED
        )
        self.assertEqual(overlap, set())

    def test_schema_contracts_include_dashboard_fields(self) -> None:
        self.assertEqual(
            build_dashboard_summary.WEEKLY_REQUIRED_COLUMNS,
            [
                "week_start",
                "borough",
                "precinct",
                "offense_type",
                "law_category",
                "crime_count",
            ],
        )
        self.assertEqual(
            build_dashboard_summary.MONTHLY_REQUIRED_COLUMNS,
            [
                "month_start",
                "borough",
                "precinct",
                "offense_type",
                "law_category",
                "crime_count",
            ],
        )
        for column in ["latitude", "longitude", "complaint_from_ts"]:
            self.assertIn(column, build_dashboard_summary.CLEAN_EVENTS_REQUIRED_COLUMNS)

    def test_pct_change_handles_zero_or_missing_baseline(self) -> None:
        self.assertIsNone(build_dashboard_summary.pct_change(10, 0))
        self.assertIsNone(build_dashboard_summary.pct_change(10, None))
        self.assertEqual(build_dashboard_summary.pct_change(150, 100), 50.0)


if __name__ == "__main__":
    unittest.main()

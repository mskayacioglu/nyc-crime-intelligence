import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def test_generated_summary_and_report_use_repository_relative_input_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "repository"
            project_root.mkdir()
            inputs = {
                "clean_events": project_root / "data/processed/complaints_clean.parquet",
                "weekly_area": project_root / "data/processed/crime_weekly_area.parquet",
                "monthly_area": project_root / "data/processed/crime_monthly_area.parquet",
            }
            growth = {
                "comparison": {
                    "window_months": 1,
                    "min_previous_period_count": 1,
                    "previous_period": {"start": "2025-10-01", "end": "2025-10-31"},
                    "current_period": {"start": "2025-11-01", "end": "2025-11-30"},
                },
                "borough_offense": {
                    "fastest_increasing": [],
                    "fastest_decreasing": [],
                },
                "precinct_offense": {
                    "fastest_increasing": [],
                    "fastest_decreasing": [],
                },
            }
            map_ready = {
                "coordinate_filter": "aggregate-safe coordinates",
                "heatmap_grid_size_degrees": 0.01,
                "valid_coordinate_event_rows": 0,
                "pct_aggregate_events_with_valid_coordinates": 0.0,
                "precinct_summary": [],
                "heatmap_cells": [],
            }
            with (
                patch.object(
                    build_dashboard_summary,
                    "build_record_counts",
                    return_value={"aggregate_event_rows": 0},
                ),
                patch.object(
                    build_dashboard_summary,
                    "build_analysis_window",
                    return_value={
                        "min_complaint_from_date": None,
                        "max_complaint_from_date": None,
                    },
                ),
                patch.object(build_dashboard_summary, "build_yearly_trends", return_value=[]),
                patch.object(build_dashboard_summary, "build_monthly_trends", return_value=[]),
                patch.object(build_dashboard_summary, "build_weekly_trends", return_value=[]),
                patch.object(build_dashboard_summary, "build_borough_rankings", return_value=[]),
                patch.object(build_dashboard_summary, "build_precinct_rankings", return_value=[]),
                patch.object(
                    build_dashboard_summary,
                    "build_offense_distribution",
                    return_value={"top": [], "other_count": 0},
                ),
                patch.object(
                    build_dashboard_summary, "build_law_category_distribution", return_value=[]
                ),
                patch.object(build_dashboard_summary, "build_hour_patterns", return_value=[]),
                patch.object(build_dashboard_summary, "build_day_patterns", return_value=[]),
                patch.object(build_dashboard_summary, "build_growth_decline", return_value=growth),
                patch.object(build_dashboard_summary, "build_map_ready", return_value=map_ready),
            ):
                payload = build_dashboard_summary.build_dashboard_summary(
                    None,
                    project_root=project_root,
                    inputs=inputs,
                    top_n=1,
                    growth_window_months=1,
                    min_growth_baseline_count=1,
                    heatmap_grid_size=0.01,
                    heatmap_limit=1,
                )

            summary_path = project_root / "data/processed/dashboard_summary.json"
            report_path = project_root / "reports/exploratory_analysis.md"
            build_dashboard_summary.write_dashboard_summary(summary_path, payload)
            build_dashboard_summary.write_exploratory_report(report_path, payload)
            summary_text = summary_path.read_text(encoding="utf-8")
            summary = json.loads(summary_text)
            report_text = report_path.read_text(encoding="utf-8")

        self.assertEqual(
            summary["inputs"],
            {
                "clean_events": "data/processed/complaints_clean.parquet",
                "weekly_area": "data/processed/crime_weekly_area.parquet",
                "monthly_area": "data/processed/crime_monthly_area.parquet",
            },
        )
        for text in (summary_text, report_text):
            self.assertNotIn(str(project_root), text)
        self.assertIn("`data/processed/complaints_clean.parquet`", report_text)

    def test_serialized_dashboard_input_paths_outside_project_root_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            project_root = directory / "repository"
            project_root.mkdir()
            outside_path = directory / "outside.parquet"

            with self.assertRaisesRegex(ValueError, "inside the project root"):
                build_dashboard_summary.repository_relative_path(
                    project_root, outside_path
                )

    def test_main_rejects_external_paths_before_opening_duckdb(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            project_root = directory / "repository"
            project_root.mkdir()
            outside_path = directory / "dashboard-summary.json"

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "build_dashboard_summary.py",
                        "--project-root",
                        str(project_root),
                        "--dashboard-summary",
                        str(outside_path),
                    ],
                ),
                patch.object(
                    build_dashboard_summary, "require_duckdb"
                ) as require_duckdb,
                self.assertRaisesRegex(ValueError, "inside the project root"),
            ):
                build_dashboard_summary.main()

            require_duckdb.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "data" / "build_clean_dataset.py"
SPEC = importlib.util.spec_from_file_location("build_clean_dataset", MODULE_PATH)
build_clean_dataset = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_clean_dataset)


class CleaningPipelineContractTest(unittest.TestCase):
    def test_weekly_schema_contract(self) -> None:
        self.assertEqual(
            build_clean_dataset.WEEKLY_COLUMNS,
            [
                "week_start",
                "borough",
                "precinct",
                "offense_type",
                "law_category",
                "crime_count",
            ],
        )

    def test_monthly_schema_contract(self) -> None:
        self.assertEqual(
            build_clean_dataset.MONTHLY_COLUMNS,
            [
                "month_start",
                "borough",
                "precinct",
                "offense_type",
                "law_category",
                "crime_count",
            ],
        )

    def test_required_quality_flags_are_present(self) -> None:
        expected_flags = {
            "flag_missing_invalid_complaint_start_date",
            "flag_implausibly_old_complaint_start_date",
            "flag_future_complaint_start_date",
            "flag_future_complaint_end_date",
            "flag_complaint_end_before_start",
            "flag_report_date_before_complaint_start",
            "flag_missing_borough",
            "flag_missing_precinct",
            "flag_missing_offense",
            "flag_missing_coordinates",
            "flag_zero_coordinates",
            "flag_coordinates_outside_broad_nyc_bounds",
            "flag_invalid_law_category",
        }
        self.assertTrue(expected_flags.issubset(set(build_clean_dataset.QUALITY_FLAGS)))
        self.assertTrue(expected_flags.issubset(set(build_clean_dataset.CLEAN_EVENT_COLUMNS)))

    def test_sensitive_demographic_columns_are_not_clean_event_features(self) -> None:
        overlap = set(build_clean_dataset.SENSITIVE_COLUMNS).intersection(
            build_clean_dataset.CLEAN_EVENT_COLUMNS
        )
        self.assertEqual(overlap, set())

    def test_generated_summary_and_report_use_repository_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "repository"
            raw_csv_path = project_root / "data/raw/source.csv"
            processed_dir = project_root / "data/processed"
            reports_dir = project_root / "reports"
            raw_csv_path.parent.mkdir(parents=True)
            processed_dir.mkdir(parents=True)
            reports_dir.mkdir(parents=True)
            raw_csv_path.write_text("header\n", encoding="utf-8")

            outputs = {
                "clean_events": processed_dir / "complaints_clean.parquet",
                "weekly": processed_dir / "crime_weekly_area.parquet",
                "monthly": processed_dir / "crime_monthly_area.parquet",
                "summary": processed_dir / "cleaning_summary.json",
            }
            config = {
                "sample_rows": None,
                "min_incident_date": "2006-01-01",
                "as_of_date": "2025-12-31",
            }
            overall = {"row_count": 1, "clean_event_count_for_aggregates": 1}
            date_quality = {
                "min_complaint_from_date": "2006-01-01",
                "max_complaint_from_date": "2025-12-31",
            }
            quality_counts = [
                {"quality_flag": "flag_missing_offense", "issue_count": 0, "issue_pct": 0.0}
            ]
            output_summary = {
                "weekly": {"aggregate_rows": 1, "event_rows": 1},
                "monthly": {"aggregate_rows": 1, "event_rows": 1},
            }
            report_path = reports_dir / "cleaning_report.md"

            build_clean_dataset.write_summary_json(
                outputs["summary"],
                project_root=project_root,
                raw_csv_path=raw_csv_path,
                processed_dir=processed_dir,
                reports_dir=reports_dir,
                outputs=outputs,
                column_validation={"missing": [], "unexpected": []},
                config=config,
                overall=overall,
                date_quality=date_quality,
                quality_counts=quality_counts,
                output_summary=output_summary,
            )
            build_clean_dataset.write_cleaning_report(
                report_path,
                project_root=project_root,
                raw_csv_path=raw_csv_path,
                outputs=outputs,
                config=config,
                overall=overall,
                date_quality=date_quality,
                quality_counts=quality_counts,
                output_summary=output_summary,
            )

            summary_text = outputs["summary"].read_text(encoding="utf-8")
            summary = json.loads(summary_text)
            report_text = report_path.read_text(encoding="utf-8")

        self.assertEqual(summary["source_file"], "data/raw/source.csv")
        self.assertEqual(summary["processed_dir"], "data/processed")
        self.assertEqual(summary["reports_dir"], "reports")
        self.assertEqual(
            summary["outputs"],
            {
                "clean_events": "data/processed/complaints_clean.parquet",
                "weekly": "data/processed/crime_weekly_area.parquet",
                "monthly": "data/processed/crime_monthly_area.parquet",
                "summary": "data/processed/cleaning_summary.json",
            },
        )
        for text in (summary_text, report_text):
            self.assertNotIn(str(project_root), text)
        self.assertIn("`data/raw/source.csv`", report_text)
        self.assertIn("`reports/cleaning_report.md`", report_text)

    def test_serialized_cleaning_paths_outside_project_root_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            project_root = directory / "repository"
            project_root.mkdir()
            outside_path = directory / "outside.csv"

            with self.assertRaisesRegex(ValueError, "inside the project root"):
                build_clean_dataset.repository_relative_path(
                    project_root, outside_path
                )

            outside_path.write_text("outside\n", encoding="utf-8")
            escaping_link = project_root / "escaping-link.csv"
            escaping_link.symlink_to(outside_path)
            with self.assertRaisesRegex(ValueError, "inside the project root"):
                build_clean_dataset.repository_relative_path(
                    project_root, escaping_link
                )

    def test_main_rejects_external_paths_before_opening_duckdb(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            project_root = directory / "repository"
            project_root.mkdir()
            outside_path = directory / "outside.duckdb"

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "build_clean_dataset.py",
                        "--project-root",
                        str(project_root),
                        "--duckdb-database",
                        str(outside_path),
                    ],
                ),
                patch.object(build_clean_dataset, "require_duckdb") as require_duckdb,
                self.assertRaisesRegex(ValueError, "inside the project root"),
            ):
                build_clean_dataset.main()

            require_duckdb.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import importlib.util
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()

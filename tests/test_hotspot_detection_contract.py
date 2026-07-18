import importlib.util
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "analytics" / "build_hotspots.py"
)
SPEC = importlib.util.spec_from_file_location("build_hotspots", MODULE_PATH)
build_hotspots = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_hotspots)
PROJECT_ROOT = MODULE_PATH.parents[2]


class HotspotDetectionContractTest(unittest.TestCase):
    def test_metrics_paths_are_portable_and_external_paths_fail_closed(self) -> None:
        inputs = {
            "clean_events": PROJECT_ROOT / "data/processed/complaints_clean.parquet",
            "weekly_area": None,
        }
        outputs = {
            "hotspots": PROJECT_ROOT / "data/processed/hotspots.parquet",
            "metrics": PROJECT_ROOT / "data/processed/hotspot_metrics.json",
            "report": PROJECT_ROOT / "reports/hotspot_methodology.md",
        }
        severity_counts = [
            {"hotspot_grain": grain, "hotspot_severity": label}
            for grain in ("precinct", "grid")
            for label in build_hotspots.SEVERITY_LABELS
        ]

        with (
            patch.object(build_hotspots, "build_analysis_window", return_value={}),
            patch.object(build_hotspots, "build_record_counts", return_value={}),
            patch.object(
                build_hotspots,
                "build_severity_counts",
                return_value=severity_counts,
            ),
            patch.object(build_hotspots, "build_top_hotspots", return_value=[]),
            patch.object(build_hotspots, "build_coordinate_quality", return_value={}),
        ):
            payload = build_hotspots.build_metrics_payload(
                None,
                project_root=PROJECT_ROOT,
                inputs=inputs,
                outputs=outputs,
                input_summary={},
                windows={
                    "baseline_end_date": date(2024, 1, 1),
                    "recent_90_start_date": date(2024, 1, 2),
                },
                config=build_hotspots.HotspotConfig(),
                scoring_end_date=date(2024, 1, 31),
                latest_date_excluded_from_scoring=True,
                top_n=1,
            )

        self.assertEqual(
            payload["inputs"],
            {
                "clean_events": "data/processed/complaints_clean.parquet",
                "weekly_area": None,
            },
        )
        self.assertEqual(
            payload["outputs"],
            {
                "hotspots": "data/processed/hotspots.parquet",
                "metrics": "data/processed/hotspot_metrics.json",
                "report": "reports/hotspot_methodology.md",
            },
        )
        self.assertNotIn(str(PROJECT_ROOT), repr(payload["inputs"]))
        self.assertNotIn(str(PROJECT_ROOT), repr(payload["outputs"]))

        with self.assertRaisesRegex(ValueError, "inside the project root"):
            build_hotspots.repository_relative_path(
                PROJECT_ROOT,
                PROJECT_ROOT.parent / "outside-hotspot-input.parquet",
            )

    def test_main_rejects_external_outputs_before_opening_duckdb(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            project_root = directory / "repository"
            project_root.mkdir()
            outside_path = directory / "hotspots.parquet"

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "build_hotspots.py",
                        "--project-root",
                        str(project_root),
                        "--hotspots-output",
                        str(outside_path),
                    ],
                ),
                patch.object(build_hotspots, "require_duckdb") as require_duckdb,
                self.assertRaisesRegex(ValueError, "inside the project root"),
            ):
                build_hotspots.main()

            require_duckdb.assert_not_called()

    def create_aggregate_bin_input(self, con, bins: list[tuple]) -> None:
        con.execute(
            f"""
            CREATE TABLE {build_hotspots.HOTSPOT_INPUT_BIN_VIEW} (
                bin_date DATE,
                borough VARCHAR,
                precinct VARCHAR,
                offense_type VARCHAR,
                law_category VARCHAR,
                latitude DOUBLE,
                longitude DOUBLE,
                flag_missing_coordinates BOOLEAN,
                flag_zero_coordinates BOOLEAN,
                flag_coordinates_outside_broad_nyc_bounds BOOLEAN,
                event_count BIGINT
            )
            """
        )
        con.executemany(
            f"INSERT INTO {build_hotspots.HOTSPOT_INPUT_BIN_VIEW} "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            bins,
        )
        build_hotspots.validate_aggregate_input_bins(con)

    def build_views(
        self,
        bins: list[tuple],
        config: build_hotspots.HotspotConfig | None = None,
        *,
        include_latest_date: bool = True,
    ):
        duckdb = build_hotspots.require_duckdb()
        con = duckdb.connect(database=":memory:")
        self.create_aggregate_bin_input(con, bins)
        min_event_date, max_event_date = build_hotspots.get_event_date_bounds(con)
        scoring_end_date = build_hotspots.compute_scoring_end_date(
            min_event_date,
            max_event_date,
            include_latest_date=include_latest_date,
        )
        config = config or build_hotspots.HotspotConfig()
        windows = build_hotspots.compute_window_bounds(scoring_end_date, config)
        build_hotspots.create_hotspot_views(con, windows=windows, config=config)
        return con, windows

    def test_output_schema_contract(self) -> None:
        self.assertEqual(
            build_hotspots.HOTSPOT_INPUT_BIN_COLUMNS,
            [
                "bin_date",
                "borough",
                "precinct",
                "offense_type",
                "law_category",
                "latitude",
                "longitude",
                "flag_missing_coordinates",
                "flag_zero_coordinates",
                "flag_coordinates_outside_broad_nyc_bounds",
                "event_count",
            ],
        )
        self.assertEqual(
            build_hotspots.HOTSPOT_OUTPUT_COLUMNS,
            [
                "rank_overall",
                "rank_in_grain",
                "hotspot_grain",
                "borough",
                "precinct",
                "grid_latitude",
                "grid_longitude",
                "offense_type",
                "law_category",
                "map_latitude",
                "map_longitude",
                "recent_window_days",
                "baseline_window_days",
                "scoring_end_date",
                "recent_7_day_count",
                "recent_30_day_count",
                "recent_90_day_count",
                "recent_event_count",
                "baseline_event_count",
                "baseline_expected_recent_count",
                "recent_total_events",
                "baseline_total_events",
                "recent_share_total_events",
                "baseline_share_total_events",
                "share_change_pct_points",
                "recent_baseline_ratio",
                "recent_vs_baseline_lift_pct",
                "recency_weighted_event_count",
                "density_score",
                "lift_score",
                "share_increase_score",
                "recency_weighted_score",
                "coordinate_quality_score",
                "composite_score",
                "valid_coordinate_event_count",
                "coordinate_coverage_pct",
                "passes_volume_filter",
                "is_hotspot",
                "is_high_or_critical_hotspot",
                "hotspot_severity",
            ],
        )

    def test_sensitive_demographic_columns_are_not_hotspot_features(self) -> None:
        used_columns = set(build_hotspots.HOTSPOT_COLUMNS_USED).union(
            build_hotspots.HOTSPOT_OUTPUT_COLUMNS
        )
        overlap = set(build_hotspots.SENSITIVE_COLUMNS).intersection(used_columns)
        self.assertEqual(overlap, set())

    def test_coordinate_filters_exclude_missing_zero_and_out_of_bounds(self) -> None:
        bins = [
            (
                date(2024, 4, 30),
                "BROOKLYN",
                "1",
                "THEFT",
                "MISDEMEANOR",
                40.7000,
                -73.9500,
                False,
                False,
                False,
                3,
            ),
            (
                date(2024, 4, 30),
                "BROOKLYN",
                "1",
                "THEFT",
                "MISDEMEANOR",
                None,
                None,
                True,
                False,
                False,
                4,
            ),
            (
                date(2024, 4, 30),
                "BROOKLYN",
                "1",
                "THEFT",
                "MISDEMEANOR",
                0.0,
                0.0,
                False,
                True,
                False,
                5,
            ),
            (
                date(2024, 4, 30),
                "BROOKLYN",
                "1",
                "THEFT",
                "MISDEMEANOR",
                41.2000,
                -73.9500,
                False,
                False,
                True,
                6,
            ),
            (
                date(2024, 4, 30),
                "BROOKLYN",
                "1",
                "THEFT",
                "MISDEMEANOR",
                40.7000,
                -72.0000,
                False,
                False,
                False,
                7,
            ),
        ]
        scored_con, _ = self.build_views(bins)
        valid_count = scored_con.execute(
            "SELECT COALESCE(SUM(event_count), 0) FROM valid_geo_bins"
        ).fetchone()[0]
        grid_recent_count = scored_con.execute(
            """
            SELECT SUM(recent_event_count)
            FROM hotspot_candidates
            WHERE hotspot_grain = 'grid'
            """
        ).fetchone()[0]
        scored_con.close()

        self.assertEqual(valid_count, 3)
        self.assertEqual(grid_recent_count, 3)

    def test_weighted_bins_preserve_counts_and_precinct_centroids(self) -> None:
        bins = [
            (
                date(2024, 4, 30),
                "BRONX",
                "46",
                "THEFT",
                "FELONY",
                40.7000,
                -73.9500,
                False,
                False,
                False,
                3,
            ),
            (
                date(2024, 4, 30),
                "BRONX",
                "46",
                "THEFT",
                "FELONY",
                40.8000,
                -73.8500,
                False,
                False,
                False,
                1,
            ),
        ]
        scored_con, _ = self.build_views(bins)
        centroid = scored_con.execute(
            """
            SELECT map_latitude, map_longitude, centroid_event_count
            FROM precinct_centroids
            WHERE borough = 'BRONX' AND precinct = '46'
            """
        ).fetchone()
        precinct_count = scored_con.execute(
            """
            SELECT recent_event_count
            FROM hotspot_candidates
            WHERE hotspot_grain = 'precinct'
                AND borough = 'BRONX'
                AND precinct = '46'
                AND offense_type = 'THEFT'
                AND law_category = 'FELONY'
            """
        ).fetchone()[0]
        input_summary = build_hotspots.build_input_summary(scored_con)
        coordinate_quality = build_hotspots.build_coordinate_quality(scored_con)
        scored_con.close()

        self.assertEqual(centroid, (40.725, -73.925, 4))
        self.assertEqual(precinct_count, 4)
        self.assertEqual(input_summary["clean_aggregate_event_rows"], 4)
        self.assertEqual(input_summary["valid_coordinate_event_rows"], 4)
        self.assertEqual(coordinate_quality["aggregate_event_rows"], 4)
        self.assertEqual(coordinate_quality["valid_coordinate_event_rows"], 4)

    def test_sparse_low_volume_cells_do_not_get_inflated_hotspot_severity(self) -> None:
        bins = [
            (
                date(2023, 12, 1),
                "QUEENS",
                "100",
                "RARE",
                "FELONY",
                40.7100,
                -73.8100,
                False,
                False,
                False,
                2,
            ),
            (
                date(2024, 4, 30),
                "QUEENS",
                "100",
                "RARE",
                "FELONY",
                40.7100,
                -73.8100,
                False,
                False,
                False,
                2,
            ),
        ]
        config = build_hotspots.HotspotConfig(
            min_grid_recent_count=5,
            min_grid_baseline_count=5,
            min_precinct_recent_count=5,
            min_precinct_baseline_count=5,
        )
        scored_con, _ = self.build_views(bins, config)
        row = scored_con.execute(
            """
            SELECT
                recent_event_count,
                baseline_event_count,
                passes_volume_filter,
                is_hotspot,
                hotspot_severity
            FROM hotspot_candidates
            WHERE hotspot_grain = 'grid'
                AND offense_type = 'RARE'
                AND law_category = 'FELONY'
            """
        ).fetchone()
        hotspot_count = scored_con.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]
        scored_con.close()

        self.assertEqual(row[0], 2)
        self.assertEqual(row[1], 2)
        self.assertFalse(row[2])
        self.assertFalse(row[3])
        self.assertEqual(row[4], "none")
        self.assertEqual(hotspot_count, 0)

    def test_recent_and_baseline_windows_are_deterministic_and_do_not_overlap(self) -> None:
        config = build_hotspots.HotspotConfig()
        min_event_date = date(2024, 1, 1)
        max_event_date = date(2024, 5, 31)
        scoring_end_date = build_hotspots.compute_scoring_end_date(
            min_event_date,
            max_event_date,
            include_latest_date=False,
        )
        windows = build_hotspots.compute_window_bounds(scoring_end_date, config)

        self.assertEqual(scoring_end_date, date(2024, 5, 30))
        self.assertEqual(
            windows["recent_7_start_date"],
            scoring_end_date - timedelta(days=config.short_window_days - 1),
        )
        self.assertEqual(
            windows["recent_30_start_date"],
            scoring_end_date - timedelta(days=config.recent_window_days - 1),
        )
        self.assertEqual(
            windows["recent_90_start_date"],
            scoring_end_date - timedelta(days=config.long_window_days - 1),
        )
        self.assertEqual(
            windows["baseline_end_date"],
            windows["recent_90_start_date"] - timedelta(days=1),
        )
        self.assertLess(windows["baseline_end_date"], windows["recent_90_start_date"])

    def test_generated_at_metadata_is_deterministic_from_scoring_end_date(self) -> None:
        self.assertEqual(
            build_hotspots.deterministic_generated_at_utc(date(2024, 5, 30)),
            "2024-05-30T00:00:00+00:00",
        )

    def test_hotspot_output_view_contains_only_flagged_hotspots(self) -> None:
        bins = [
            (
                date(2024, 4, 30),
                "BRONX",
                "46",
                "DANGEROUS DRUGS",
                "MISDEMEANOR",
                40.8450,
                -73.9050,
                False,
                False,
                False,
                5,
            ),
            (
                date(2023, 12, 1),
                "BRONX",
                "46",
                "DANGEROUS DRUGS",
                "MISDEMEANOR",
                40.8450,
                -73.9050,
                False,
                False,
                False,
                1,
            ),
            (
                date(2023, 12, 1),
                "BROOKLYN",
                "70",
                "PETIT LARCENY",
                "MISDEMEANOR",
                40.6450,
                -73.9550,
                False,
                False,
                False,
                30,
            ),
        ]
        config = build_hotspots.HotspotConfig(
            min_grid_recent_count=1,
            min_grid_baseline_count=1,
            min_precinct_recent_count=1,
            min_precinct_baseline_count=1,
            min_recent_baseline_ratio=1.0,
            min_hotspot_score=0.0,
        )
        scored_con, _ = self.build_views(bins, config)
        total_hotspots = scored_con.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]
        unflagged_hotspots = scored_con.execute(
            "SELECT COUNT(*) FROM hotspots WHERE NOT is_hotspot"
        ).fetchone()[0]
        scored_con.close()

        self.assertGreater(total_hotspots, 0)
        self.assertEqual(unflagged_hotspots, 0)


if __name__ == "__main__":
    unittest.main()

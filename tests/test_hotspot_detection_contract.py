import importlib.util
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "analytics" / "build_hotspots.py"
)
SPEC = importlib.util.spec_from_file_location("build_hotspots", MODULE_PATH)
build_hotspots = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_hotspots)


class HotspotDetectionContractTest(unittest.TestCase):
    def write_clean_input(self, con, clean_path: Path, rows: list[tuple]) -> None:
        con.execute(
            """
            CREATE TABLE clean_input (
                complaint_from_date DATE,
                borough VARCHAR,
                precinct VARCHAR,
                offense_type VARCHAR,
                law_category VARCHAR,
                latitude DOUBLE,
                longitude DOUBLE,
                flag_missing_coordinates BOOLEAN,
                flag_zero_coordinates BOOLEAN,
                flag_coordinates_outside_broad_nyc_bounds BOOLEAN,
                is_clean_event_for_aggregate BOOLEAN
            )
            """
        )
        con.executemany(
            "INSERT INTO clean_input VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        con.execute(
            f"COPY clean_input TO {build_hotspots.sql_string(clean_path)} (FORMAT PARQUET)"
        )

    def build_views(
        self,
        clean_path: Path,
        config: build_hotspots.HotspotConfig | None = None,
        *,
        include_latest_date: bool = True,
    ):
        duckdb = build_hotspots.require_duckdb()
        con = duckdb.connect(database=":memory:")
        build_hotspots.create_input_views(con, clean_path)
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
        duckdb = build_hotspots.require_duckdb()
        with tempfile.TemporaryDirectory() as tmpdir:
            clean_path = Path(tmpdir) / "clean.parquet"
            con = duckdb.connect(database=":memory:")
            rows = [
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
                    True,
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
                    True,
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
                    True,
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
                    True,
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
                    True,
                ),
            ]
            self.write_clean_input(con, clean_path, rows)

            scored_con, _ = self.build_views(clean_path)
            valid_count = scored_con.execute(
                "SELECT COUNT(*) FROM valid_geo_events"
            ).fetchone()[0]
            grid_recent_count = scored_con.execute(
                """
                SELECT SUM(recent_event_count)
                FROM hotspot_candidates
                WHERE hotspot_grain = 'grid'
                """
            ).fetchone()[0]

        self.assertEqual(valid_count, 1)
        self.assertEqual(grid_recent_count, 1)

    def test_sparse_low_volume_cells_do_not_get_inflated_hotspot_severity(self) -> None:
        duckdb = build_hotspots.require_duckdb()
        with tempfile.TemporaryDirectory() as tmpdir:
            clean_path = Path(tmpdir) / "clean.parquet"
            con = duckdb.connect(database=":memory:")
            rows = [
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
                    True,
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
                    True,
                ),
            ]
            self.write_clean_input(con, clean_path, rows)

            config = build_hotspots.HotspotConfig(
                min_grid_recent_count=5,
                min_grid_baseline_count=5,
                min_precinct_recent_count=5,
                min_precinct_baseline_count=5,
            )
            scored_con, _ = self.build_views(clean_path, config)
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

        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], 1)
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
        duckdb = build_hotspots.require_duckdb()
        with tempfile.TemporaryDirectory() as tmpdir:
            clean_path = Path(tmpdir) / "clean.parquet"
            con = duckdb.connect(database=":memory:")
            rows = []
            for _ in range(5):
                rows.append(
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
                        True,
                    )
                )
            rows.append(
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
                    True,
                )
            )
            for _ in range(30):
                rows.append(
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
                        True,
                    )
                )
            self.write_clean_input(con, clean_path, rows)

            config = build_hotspots.HotspotConfig(
                min_grid_recent_count=1,
                min_grid_baseline_count=1,
                min_precinct_recent_count=1,
                min_precinct_baseline_count=1,
                min_recent_baseline_ratio=1.0,
                min_hotspot_score=0.0,
            )
            scored_con, _ = self.build_views(clean_path, config)
            total_hotspots = scored_con.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]
            unflagged_hotspots = scored_con.execute(
                "SELECT COUNT(*) FROM hotspots WHERE NOT is_hotspot"
            ).fetchone()[0]

        self.assertGreater(total_hotspots, 0)
        self.assertEqual(unflagged_hotspots, 0)


if __name__ == "__main__":
    unittest.main()

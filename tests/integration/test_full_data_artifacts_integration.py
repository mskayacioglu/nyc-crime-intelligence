import importlib.util
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_builder(module_name: str):
    module_path = PROJECT_ROOT / "src" / "analytics" / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


build_dashboard_forecast_map = load_builder("build_dashboard_forecast_map")
build_dashboard_map = load_builder("build_dashboard_map")
build_dashboard_overview = load_builder("build_dashboard_overview")


class FullDataArtifactsIntegrationTest(unittest.TestCase):
    def require_full_data_artifacts(self, paths: dict[str, Path]) -> None:
        missing = [path for path in paths.values() if not path.is_file()]
        self.assertEqual(
            [],
            missing,
            "Run the documented full-data rebuild before this optional integration "
            f"suite. Missing artifacts: {missing}",
        )

    def test_full_aggregate_artifacts_reproduce_the_committed_forecast_contract(
        self,
    ) -> None:
        paths = {
            "weekly": PROJECT_ROOT / "data/processed/crime_weekly_area.parquet",
            "overview": PROJECT_ROOT / "data/processed/dashboard_overview.json",
            "forecast": PROJECT_ROOT / "data/processed/ml_predictions.parquet",
            "metrics": PROJECT_ROOT / "data/processed/ml_metrics.json",
            "manifest": PROJECT_ROOT / "models/weekly_forecast/model_manifest.json",
            "baseline": PROJECT_ROOT / "data/processed/baseline_predictions.parquet",
            "baseline_manifest": (
                PROJECT_ROOT / "models/baseline_forecast/model_manifest.json"
            ),
        }
        self.require_full_data_artifacts(paths)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "forecast-map.json"
            payload = build_dashboard_forecast_map.build_dashboard_forecast_map(
                weekly_path=paths["weekly"],
                overview_path=paths["overview"],
                ml_predictions_path=paths["forecast"],
                ml_metrics_path=paths["metrics"],
                ml_manifest_path=paths["manifest"],
                baseline_predictions_path=paths["baseline"],
                baseline_manifest_path=paths["baseline_manifest"],
                output_path=output,
                threads=1,
            )
            persisted = json.loads(output.read_text(encoding="utf-8"))
            output_bytes = output.read_bytes()

        self.assertEqual("available", payload["forecast"]["status"])
        self.assertGreater(payload["forecast"]["summary"]["rowCount"], 0)
        self.assertEqual(1, len(payload["dimensions"]["forecastWeeks"]))
        forecast_week = date.fromisoformat(payload["dimensions"]["forecastWeeks"][0])
        latest_observed = date.fromisoformat(payload["dataRange"]["latestObservedWeek"])
        self.assertEqual(latest_observed + timedelta(weeks=1), forecast_week)
        self.assertEqual(forecast_week.isoformat(), payload["model"]["forecastWeek"])
        self.assertEqual(
            "2026-07-05T12:40:05.068774+00:00",
            payload["model"]["artifactGeneratedAtUtc"],
        )
        self.assertEqual(
            {
                "status": "unavailable",
                "timestamp": None,
                "reason": "No independent training-completion timestamp is recorded.",
            },
            payload["model"]["independentTrainingTime"],
        )
        self.assertEqual(payload, persisted)
        build_dashboard_forecast_map.validate_forecast_map_payload(persisted)
        self.assertEqual(
            (PROJECT_ROOT / "dashboard/public/data/forecast-map.json").read_bytes(),
            output_bytes,
        )

    def test_private_clean_source_reproduces_the_committed_map_contract(self) -> None:
        paths = {
            "clean": PROJECT_ROOT / "data/processed/complaints_clean.parquet",
            "hotspots": PROJECT_ROOT / "data/processed/hotspots.parquet",
            "hotspot_metrics": PROJECT_ROOT / "data/processed/hotspot_metrics.json",
            "committed_map": PROJECT_ROOT / "dashboard/public/data/map.json",
        }
        self.require_full_data_artifacts(paths)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "map.json"
            payload = build_dashboard_map.build_dashboard_map(
                clean_events_path=paths["clean"],
                hotspots_path=paths["hotspots"],
                hotspot_metrics_path=paths["hotspot_metrics"],
                output_path=output,
                threads=1,
            )
            persisted = json.loads(output.read_text(encoding="utf-8"))
            output_bytes = output.read_bytes()

        self.assertEqual(payload, persisted)
        build_dashboard_map.validate_map_payload(persisted)
        self.assertGreater(payload["dataRange"]["aggregateSafeEventCount"], 0)
        self.assertEqual(
            payload["dataRange"]["sourceEventCount"]
            - payload["dataRange"]["aggregateSafeEventCount"],
            payload["dataRange"]["excludedEventCount"],
        )
        self.assertEqual("available", payload["hotspots"]["status"])
        self.assertEqual(paths["committed_map"].read_bytes(), output_bytes)

    def test_private_clean_source_reproduces_the_committed_overview_contract(
        self,
    ) -> None:
        paths = {
            "clean": PROJECT_ROOT / "data/processed/complaints_clean.parquet",
            "weekly": PROJECT_ROOT / "data/processed/crime_weekly_area.parquet",
            "anomalies": PROJECT_ROOT / "data/processed/anomalies.parquet",
            "hotspots": PROJECT_ROOT / "data/processed/hotspots.parquet",
            "forecast": PROJECT_ROOT / "data/processed/ml_predictions.parquet",
            "anomaly_metrics": PROJECT_ROOT / "data/processed/anomaly_metrics.json",
            "hotspot_metrics": PROJECT_ROOT / "data/processed/hotspot_metrics.json",
            "ml_metrics": PROJECT_ROOT / "data/processed/ml_metrics.json",
            "ml_manifest": PROJECT_ROOT / "models/weekly_forecast/model_manifest.json",
            "baseline_manifest": (
                PROJECT_ROOT / "models/baseline_forecast/model_manifest.json"
            ),
            "committed_overview": PROJECT_ROOT / "dashboard/public/data/overview.json",
            "committed_cube": (
                PROJECT_ROOT / "dashboard/public/data/overview-cube.bin.gz"
            ),
        }
        self.require_full_data_artifacts(paths)

        with tempfile.TemporaryDirectory() as tmp:
            overview_output = Path(tmp) / "overview.json"
            cube_output = Path(tmp) / "overview-cube.bin.gz"
            payload = build_dashboard_overview.build_dashboard_overview(
                clean_events_path=paths["clean"],
                weekly_path=paths["weekly"],
                anomalies_path=paths["anomalies"],
                hotspots_path=paths["hotspots"],
                ml_predictions_path=paths["forecast"],
                anomaly_metrics_path=paths["anomaly_metrics"],
                hotspot_metrics_path=paths["hotspot_metrics"],
                ml_metrics_path=paths["ml_metrics"],
                ml_manifest_path=paths["ml_manifest"],
                baseline_manifest_path=paths["baseline_manifest"],
                overview_output_path=overview_output,
                cube_output_path=cube_output,
                threads=1,
            )
            persisted = json.loads(overview_output.read_text(encoding="utf-8"))
            overview_bytes = overview_output.read_bytes()
            cube_bytes = cube_output.read_bytes()

        self.assertEqual(payload, persisted)
        build_dashboard_overview.validate_overview_payload(persisted)
        decoded_cube = build_dashboard_overview.decode_cube(persisted, cube_bytes)
        self.assertEqual(payload["cube"]["rowCount"], len(decoded_cube["counts"]))
        self.assertEqual(
            payload["observed"]["safeEventCount"],
            payload["observed"]["weeklyAggregateCount"],
        )
        self.assertTrue(payload["dataQuality"]["countsReconciled"])
        self.assertEqual(paths["committed_overview"].read_bytes(), overview_bytes)
        self.assertEqual(paths["committed_cube"].read_bytes(), cube_bytes)


if __name__ == "__main__":
    unittest.main()

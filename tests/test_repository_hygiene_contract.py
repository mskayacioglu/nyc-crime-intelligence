import json
import re
import subprocess
import unittest
from pathlib import Path, PurePosixPath
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(PROJECT_ROOT), *args],
        text=True,
        encoding="utf-8",
    )


def tracked_paths() -> list[PurePosixPath]:
    paths = {
        PurePosixPath(value)
        for value in git_output("ls-files", "-z").split("\0")
        if value
    }
    # The test is untracked during its first local run but tracked after this
    # change is committed, so include it in its own scan immediately.
    paths.add(PurePosixPath(__file__).relative_to(PROJECT_ROOT))
    return sorted(paths, key=str)


def tracked_text(path: PurePosixPath) -> str | None:
    data = (PROJECT_ROOT / path).read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


UNIX_LOCAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9:])/(?:Users|home|private|root|workspace|workspaces|"
    r"project|projects|app|apps|srv|build|builds|code|repos|repository|"
    r"repositories|tmp|opt|Volumes|mnt)/"
    r"[^\s'\"`<>()\[\]{},;]+"
    r"|(?<![A-Za-z0-9:])/var/(?:folders|tmp)/[^\s'\"`<>()\[\]{},;]+"
    r"|(?<![A-Za-z0-9:])/content/drive/[^\s'\"`<>()\[\]{},;]+"
)
WINDOWS_DRIVE_PATH_RE = re.compile(
    r"\b[A-Za-z]:[\\/][A-Za-z0-9._$~-]+"
    r"(?:[\\/][A-Za-z0-9._$~-]+)+"
)
WINDOWS_UNC_PATH_RE = re.compile(
    r"\\\\[A-Za-z0-9._-]+\\[A-Za-z0-9$._-]+"
    r"(?:\\[^\s'\"`<>()\[\]{},;]+)*"
)
EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+\b"
)


def local_absolute_paths(text: str) -> set[str]:
    return {
        match.group(0)
        for pattern in (
            UNIX_LOCAL_PATH_RE,
            WINDOWS_DRIVE_PATH_RE,
            WINDOWS_UNC_PATH_RE,
        )
        for match in pattern.finditer(text)
    }


def secret_literals(text: str) -> set[str]:
    patterns = (
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)"
            r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{8,}"
        ),
        re.compile(r"(?i)\btoken\s*=\s*secret\b"),
    )
    return {match.group(0) for pattern in patterns for match in pattern.finditer(text)}


# These exact literals are malicious test fixtures proving that frontend and
# contract error handling does not leak local details. The allowlist is by file
# and literal; no test file is skipped wholesale.
_LOCAL_FIXTURE_ROOT = "/" + "Users/example/private/"
ABSOLUTE_PATH_FIXTURES: dict[PurePosixPath, set[str]] = {
    PurePosixPath("dashboard/src/components/GovernanceView.test.tsx"): {
        _LOCAL_FIXTURE_ROOT + "map.json",
        _LOCAL_FIXTURE_ROOT + "spatial.json",
    },
    PurePosixPath("dashboard/src/data/decodeGovernance.test.ts"): {
        _LOCAL_FIXTURE_ROOT + "model_manifest.json",
        _LOCAL_FIXTURE_ROOT + "precinct-spatial-reference.json",
        _LOCAL_FIXTURE_ROOT + "source.json",
    },
    PurePosixPath("dashboard/src/data/loadForecastMap.test.ts"): {
        _LOCAL_FIXTURE_ROOT + "forecast.parquet",
        _LOCAL_FIXTURE_ROOT + "baseline.parquet",
        _LOCAL_FIXTURE_ROOT + "manifest.json",
        _LOCAL_FIXTURE_ROOT + "metrics.json",
    },
    PurePosixPath("tests/test_dashboard_forecast_map_contract.py"): {
        _LOCAL_FIXTURE_ROOT + "forecast.parquet",
        _LOCAL_FIXTURE_ROOT + "baseline.parquet",
        _LOCAL_FIXTURE_ROOT + "manifest.json",
        _LOCAL_FIXTURE_ROOT + "model.json",
        _LOCAL_FIXTURE_ROOT + "metrics.json",
    },
}
_TOKEN_SECRET_FIXTURE = "token=" + "secret"
SECRET_FIXTURES: dict[PurePosixPath, set[str]] = {
    PurePosixPath("dashboard/src/components/GovernanceView.test.tsx"): {
        _TOKEN_SECRET_FIXTURE
    },
    PurePosixPath("dashboard/src/data/decodeGovernance.test.ts"): {
        _TOKEN_SECRET_FIXTURE
    },
}


UNSAFE_NOTEBOOK_SOURCE_PATTERNS: dict[str, re.Pattern[str]] = {
    "environment-specific Google runtime": re.compile(
        r"(?i)\b(?:google\.colab|colab|drive\.mount)\b|/content/drive|MyDrive"
    ),
    "raw complaint preview": re.compile(
        r"(?is)SELECT\s+\*\s+FROM\s+complaints_(?:raw|enriched).*?\bLIMIT\s+\d+"
    ),
    "event/sample dataframe display": re.compile(
        r"(?i)\b(?:display|show_df|print)\s*\(\s*"
        r"(?:raw_preview|event_preview|sample_df|event_rows|person_examples)\b"
    ),
    "complaint identifier row query": re.compile(
        r"(?is)SELECT\b[^;]*\bCMPLNT_NUM\b[^;]*\bLIMIT\s+\d+"
    ),
    "event-level coordinate heatmap": re.compile(
        r"(?i)\b(?:HeatMap|folium\.Map)\s*\("
    ),
    "event-example variable": re.compile(
        r"(?i)\b(?:duplicate|invalid_date|invalid_coordinate)_examples\b"
    ),
}
UNAGGREGATED_COMPLAINT_QUERY_RE = re.compile(
    r"(?is)\bSELECT\b.*?\bFROM\s+complaints_(?:raw|enriched)\b.*?\bLIMIT\s+\d+"
)
AGGREGATE_QUERY_RE = re.compile(
    r"(?i)\bGROUP\s+BY\b|\b(?:COUNT|SUM|AVG|APPROX_COUNT_DISTINCT)\s*\("
)
SENSITIVE_EXTREMA_QUERY_RE = re.compile(
    r"(?i)\b(?:MIN|MAX)\s*\(\s*(?:CMPLNT_NUM|complaint_number|"
    r"Latitude(?:_num)?|Longitude(?:_num)?|X_COORD(?:_CD|_num)?|"
    r"Y_COORD(?:_CD|_num)?|Lat_Lon)\b"
)
VARIABLE_ASSIGNMENT_RE = re.compile(
    r"(?m)^\s*([A-Za-z_]\w*)\s*=\s*(.+)$"
)


def is_aggregate_safe_complaint_query(query: str) -> bool:
    return bool(AGGREGATE_QUERY_RE.search(query)) and not (
        SENSITIVE_EXTREMA_QUERY_RE.search(query)
    )


def notebook_findings(payload: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    event_row_variables = {
        "event_preview",
        "event_rows",
        "person_examples",
        "raw_preview",
        "sample_df",
    }
    if payload.get("metadata") != {}:
        findings.append("notebook metadata is not empty")

    for index, cell in enumerate(payload.get("cells", [])):
        if cell.get("metadata") != {}:
            findings.append(f"cell {index} metadata is not empty")
        if cell.get("attachments"):
            findings.append(f"cell {index} has saved attachments")

        source = "".join(cell.get("source", []))
        for label, pattern in UNSAFE_NOTEBOOK_SOURCE_PATTERNS.items():
            if pattern.search(source):
                findings.append(f"cell {index} contains {label}")

        for query_match in UNAGGREGATED_COMPLAINT_QUERY_RE.finditer(source):
            if not is_aggregate_safe_complaint_query(query_match.group(0)):
                findings.append(
                    f"cell {index} contains an unaggregated complaint/event row query"
                )

        for assignment in VARIABLE_ASSIGNMENT_RE.finditer(source):
            variable, expression = assignment.groups()
            expression_has_event_rows = any(
                re.search(rf"\b{re.escape(candidate)}\b", expression)
                for candidate in event_row_variables
            )
            query_match = UNAGGREGATED_COMPLAINT_QUERY_RE.search(expression)
            expression_has_event_query = bool(
                query_match
                and not is_aggregate_safe_complaint_query(query_match.group(0))
            )
            expression_is_aggregate = any(
                marker in expression
                for marker in (".agg(", ".groupby(", ".value_counts(")
            )
            if (expression_has_event_rows or expression_has_event_query) and not (
                expression_is_aggregate
            ):
                event_row_variables.add(variable)

        for variable in sorted(event_row_variables):
            if re.search(
                rf"(?i)\b(?:display|show_df|print)\s*\(\s*{re.escape(variable)}\b",
                source,
            ):
                findings.append(
                    f"cell {index} displays event-derived dataframe {variable}"
                )

        if "scatter_mapbox(" in source:
            required_aggregation_guards = (
                "ROUND(latitude_num, 3)",
                "ROUND(longitude_num, 3)",
                "HAVING COUNT(*) >= 10",
                "coord_grid",
            )
            if any(value not in source for value in required_aggregation_guards):
                findings.append(
                    f"cell {index} maps coordinates without the reviewed aggregate guards"
                )

        if cell.get("cell_type") == "code":
            if cell.get("execution_count") is not None:
                findings.append(f"cell {index} has an execution count")
            if cell.get("outputs") != []:
                findings.append(f"cell {index} has saved outputs")
            try:
                compile(source, f"notebook-cell-{index}", "exec")
            except SyntaxError as exc:
                findings.append(f"cell {index} does not compile: {exc.msg}")

    return findings


TABULAR_SUFFIXES = {
    ".csv",
    ".tsv",
    ".parquet",
    ".duckdb",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".feather",
    ".arrow",
    ".jsonl",
    ".ndjson",
}
# Tracked tabular files are rejected by default because their contents can be
# opaque or too large for a reliable source scan. Future aggregate-only lookup
# tables require an exact path review and entry here; directory-level exemptions
# are intentionally unsupported.
REVIEWED_SAFE_TABULAR_ARTIFACTS: frozenset[PurePosixPath] = frozenset()
UNSAFE_MODEL_SUFFIXES = {
    ".pkl",
    ".pickle",
    ".joblib",
    ".dill",
    ".sav",
    ".pt",
    ".pth",
    ".h5",
    ".hdf5",
    ".keras",
    ".onnx",
}


def unsafe_artifact_findings(
    path: PurePosixPath,
    data: bytes,
    *,
    reviewed_safe_tabular: frozenset[PurePosixPath] = REVIEWED_SAFE_TABULAR_ARTIFACTS,
) -> list[str]:
    findings: list[str] = []
    suffix = path.suffix.lower()
    if suffix in TABULAR_SUFFIXES and path not in reviewed_safe_tabular:
        findings.append("unreviewed tracked tabular artifact (raw-event risk)")
    if len(path.parts) >= 2 and path.parts[0] == "data" and path.parts[1] in {
        "raw",
        "processed",
    } and path.name != ".gitkeep":
        findings.append("tracked file in an ignored raw/processed data directory")
    if suffix in UNSAFE_MODEL_SUFFIXES:
        findings.append("unsafe serialized model suffix")
    if path.parts and path.parts[0] == "models" and suffix != ".json":
        findings.append("non-manifest file tracked under models")
    if len(data) >= 2 and data[0] == 0x80 and data[1] <= 0x05:
        findings.append("pickle-compatible binary magic")
    if data.startswith(b"\x89HDF\r\n\x1a\n"):
        findings.append("HDF5 binary magic")
    return findings


def normalized_key(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


UNSAFE_PUBLIC_EVENT_KEYS = {
    "address",
    "cmplnt_num",
    "cmplnt_fr_dt",
    "cmplnt_fr_tm",
    "cmplnt_to_dt",
    "cmplnt_to_tm",
    "complaint_id",
    "complaint_number",
    "event_id",
    "incident_id",
    "latitude",
    "longitude",
    "rpt_dt",
    "source_row_id",
    "complaint_from_ts",
    "complaint_to_ts",
    "victim_name",
    "suspect_name",
    "vic_age_group",
    "vic_race",
    "vic_sex",
    "susp_age_group",
    "susp_race",
    "susp_sex",
    "street_address",
    "full_address",
    "x_coord",
    "y_coord",
    "lat_lon",
}


def unsafe_public_keys(value: Any) -> set[str]:
    findings: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if normalized_key(str(key)) in UNSAFE_PUBLIC_EVENT_KEYS:
                findings.add(str(key))
            findings.update(unsafe_public_keys(child))
    elif isinstance(value, list):
        for child in value:
            findings.update(unsafe_public_keys(child))
    return findings


def is_safe_repository_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and value == path.as_posix()


class RepositoryHygieneContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.paths = tracked_paths()
        cls.text_by_path = {
            path: text
            for path in cls.paths
            if (text := tracked_text(path)) is not None
        }

    def test_fixture_allowlists_are_exact_and_consumed(self) -> None:
        for path, allowed in ABSOLUTE_PATH_FIXTURES.items():
            self.assertIn(path, self.text_by_path)
            self.assertTrue(allowed)
            self.assertTrue(allowed.issubset(local_absolute_paths(self.text_by_path[path])))
        for path, allowed in SECRET_FIXTURES.items():
            self.assertIn(path, self.text_by_path)
            self.assertTrue(allowed)
            self.assertTrue(allowed.issubset(secret_literals(self.text_by_path[path])))

    def test_tracked_text_has_no_unapproved_local_paths_or_personal_identifiers(self) -> None:
        findings: list[str] = []
        personal_home_component = "ms" + "kayacioglu"
        for path, text in self.text_by_path.items():
            allowed = ABSOLUTE_PATH_FIXTURES.get(path, set())
            for value in sorted(local_absolute_paths(text) - allowed):
                findings.append(f"{path}: local absolute path {value!r}")
            if EMAIL_RE.search(text):
                findings.append(f"{path}: email address")
            if personal_home_component.casefold() in text.casefold():
                findings.append(f"{path}: personal home-directory component")
        self.assertEqual([], findings)

    def test_tracked_text_has_no_unapproved_secrets(self) -> None:
        findings: list[str] = []
        for path, text in self.text_by_path.items():
            allowed = SECRET_FIXTURES.get(path, set())
            for value in sorted(secret_literals(text) - allowed):
                findings.append(f"{path}: likely secret {value!r}")
        self.assertEqual([], findings)

    def test_public_notebooks_have_no_outputs_metadata_or_unsafe_displays(self) -> None:
        notebooks = [path for path in self.paths if path.suffix == ".ipynb"]
        self.assertEqual(
            [
                PurePosixPath("notebooks/01_nypd_complaint_data_comprehensive_eda.ipynb"),
                PurePosixPath("notebooks/02_nypd_cleaning_and_aggregation_pipeline.ipynb"),
            ],
            notebooks,
        )
        for path in notebooks:
            payload = json.loads((PROJECT_ROOT / path).read_text(encoding="utf-8"))
            self.assertEqual([], notebook_findings(payload), str(path))

    def test_public_report_omits_raw_identifier_and_coordinate_extrema(self) -> None:
        report = (PROJECT_ROOT / "reports/data_quality_report.md").read_text(
            encoding="utf-8"
        )
        for field in (
            "min_lexical_value",
            "max_lexical_value",
            "min_latitude",
            "max_latitude",
            "min_longitude",
            "max_longitude",
        ):
            self.assertNotIn(field, report)

    def test_raw_event_tables_and_unsafe_model_serializations_are_untracked(self) -> None:
        findings: list[str] = []
        for path in self.paths:
            for reason in unsafe_artifact_findings(path, (PROJECT_ROOT / path).read_bytes()):
                findings.append(f"{path}: {reason}")
        self.assertEqual([], findings)

    def test_tracked_json_has_no_event_level_schema_keys(self) -> None:
        findings: list[str] = []
        for path in self.paths:
            if path.suffix != ".json":
                continue
            payload = json.loads((PROJECT_ROOT / path).read_text(encoding="utf-8"))
            keys = unsafe_public_keys(payload)
            if keys:
                findings.append(f"{path}: {sorted(keys)}")
        self.assertEqual([], findings)

    def test_model_manifests_are_portable_and_preserve_product_identity(self) -> None:
        baseline = json.loads(
            (PROJECT_ROOT / "models/baseline_forecast/model_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        model = json.loads(
            (PROJECT_ROOT / "models/weekly_forecast/model_manifest.json").read_text(
                encoding="utf-8"
            )
        )

        expected_baseline_paths = {
            "training_input": "data/processed/crime_weekly_area.parquet",
            "prediction_output": "data/processed/baseline_predictions.parquet",
            "metrics_output": "data/processed/baseline_metrics.json",
            "report_output": "reports/baseline_model_report.md",
        }
        expected_model_paths = {
            "training_input": "data/processed/crime_weekly_area.parquet",
            "baseline_manifest_input": "models/baseline_forecast/model_manifest.json",
            "prediction_output": "data/processed/ml_predictions.parquet",
            "metrics_output": "data/processed/ml_metrics.json",
            "report_output": "reports/ml_model_report.md",
        }
        self.assertEqual(expected_baseline_paths, {
            key: baseline[key] for key in expected_baseline_paths
        })
        self.assertEqual(expected_model_paths, {key: model[key] for key in expected_model_paths})
        for value in (*expected_baseline_paths.values(), *expected_model_paths.values()):
            self.assertTrue(is_safe_repository_path(value), value)

        self.assertEqual(1, baseline["artifact_version"])
        self.assertEqual("2026-01-05", baseline["forecast_week"])
        self.assertEqual(1, model["artifact_version"])
        self.assertEqual("duckdb_lag_ensemble_regressor", model["model"]["model_name"])
        self.assertEqual(1, model["model"]["model_version"])
        self.assertEqual("2026-01-05", model["forecast_week"])

        forecast = json.loads(
            (PROJECT_ROOT / "dashboard/public/data/forecast-map.json").read_text(
                encoding="utf-8"
            )
        )
        independent_time = forecast["model"]["independentTrainingTime"]
        self.assertEqual(
            {
                "reason": "No independent training-completion timestamp is recorded.",
                "status": "unavailable",
                "timestamp": None,
            },
            independent_time,
        )

    def test_sensitive_local_artifact_locations_are_ignored(self) -> None:
        ignored_examples = (
            "data/raw/private.csv",
            "data/processed/private.parquet",
            "models/private.pkl",
            "models/private.joblib",
            "models/private.onnx",
            ".env",
            "dashboard/node_modules/private.js",
        )
        for path in ignored_examples:
            result = subprocess.run(
                ["git", "-C", str(PROJECT_ROOT), "check-ignore", "-q", "--no-index", path],
                check=False,
            )
            self.assertEqual(0, result.returncode, path)
        self.assertEqual("", git_output("ls-files", "-ci", "--exclude-standard"))

    def test_detectors_reject_synthetic_local_paths_personal_ids_and_secrets(self) -> None:
        local_path = "/" + "Users/" + ("real" + "person") + "/" + "project/file.json"
        root_path = "/" + "root/" + ("real" + "person") + "/" + "project/file.json"
        workspace_path = "/" + "workspace/" + "project/file.json"
        project_path = "/" + "project/" + "build/file.json"
        app_path = "/" + "app/" + "project/file.json"
        server_path = "/" + "srv/" + "build/file.json"
        windows_path = "C:" + "\\Users\\" + ("real" + "person") + "\\file.json"
        generic_windows_path = "D:" + "\\work\\project\\file.json"
        unc_path = "\\\\" + "server\\share\\project\\file.json"
        email = "analyst" + "@" + "gmail.com"
        api_key = "api_" + "key=" + "A" * 24
        self.assertEqual({local_path}, local_absolute_paths(local_path))
        self.assertEqual({root_path}, local_absolute_paths(root_path))
        self.assertEqual({workspace_path}, local_absolute_paths(workspace_path))
        self.assertEqual({project_path}, local_absolute_paths(project_path))
        self.assertEqual({app_path}, local_absolute_paths(app_path))
        self.assertEqual({server_path}, local_absolute_paths(server_path))
        self.assertEqual({windows_path}, local_absolute_paths(windows_path))
        self.assertEqual(
            {generic_windows_path}, local_absolute_paths(generic_windows_path)
        )
        self.assertEqual({unc_path}, local_absolute_paths(unc_path))
        self.assertIsNotNone(EMAIL_RE.search(email))
        self.assertIn(api_key, secret_literals(api_key))

    def test_notebook_detector_rejects_synthetic_saved_event_output(self) -> None:
        payload = {
            "metadata": {"kernelspec": {"display_name": "personal"}},
            "cells": [
                {
                    "cell_type": "code",
                    "metadata": {"colab": "identity"},
                    "execution_count": 7,
                    "outputs": [{"output_type": "stream", "text": ["event row"]}],
                    "source": [
                        "raw_preview = q('SELECT * FROM complaints_raw LIMIT 5')\n",
                        "display(raw_preview)\n",
                        "coordinate_rows = q('SELECT Latitude, Longitude FROM complaints_enriched LIMIT 5')\n",
                        "display(coordinate_rows)\n",
                        "person_rows = sample_df[['VIC_AGE_GROUP', 'VIC_SEX']]\n",
                        "display(person_rows)\n",
                        "coordinate_extrema = q('SELECT COUNT(*), MIN(latitude_num), MAX(longitude_num) FROM complaints_enriched LIMIT 1')\n",
                        "display(coordinate_extrema)\n",
                    ],
                }
            ],
        }
        findings = notebook_findings(payload)
        self.assertTrue(any("metadata" in value for value in findings))
        self.assertTrue(any("saved outputs" in value for value in findings))
        self.assertTrue(any("execution count" in value for value in findings))
        self.assertTrue(any("raw complaint preview" in value for value in findings))
        self.assertTrue(any("unaggregated complaint/event row query" in value for value in findings))
        self.assertTrue(
            any("displays event-derived dataframe coordinate_rows" in value for value in findings)
        )
        self.assertTrue(
            any("displays event-derived dataframe person_rows" in value for value in findings)
        )
        self.assertTrue(
            any("displays event-derived dataframe coordinate_extrema" in value for value in findings)
        )

    def test_artifact_detectors_reject_synthetic_raw_and_serialized_models(self) -> None:
        self.assertIn(
            "unreviewed tracked tabular artifact (raw-event risk)",
            unsafe_artifact_findings(
                PurePosixPath("probes/unreviewed.csv"), b"column\nvalue\n"
            ),
        )
        self.assertIn(
            "unreviewed tracked tabular artifact (raw-event risk)",
            unsafe_artifact_findings(
                PurePosixPath("probes/unreviewed.jsonl"),
                b'{"prohibited":"value"}\n',
            ),
        )
        reviewed_lookup = PurePosixPath("fixtures/borough_lookup.csv")
        self.assertNotIn(
            "unreviewed tracked tabular artifact (raw-event risk)",
            unsafe_artifact_findings(
                reviewed_lookup,
                b"borough,code\nManhattan,MN\n",
                reviewed_safe_tabular=frozenset({reviewed_lookup}),
            ),
        )
        self.assertIn(
            "unsafe serialized model suffix",
            unsafe_artifact_findings(PurePosixPath("models/model.pkl"), b"not needed"),
        )
        self.assertIn(
            "pickle-compatible binary magic",
            unsafe_artifact_findings(PurePosixPath("models/disguised.json"), b"\x80\x04x"),
        )
        unsafe_keys = {
            "complaintId": "synthetic",
            "complaintNumber": "synthetic",
            "eventId": "synthetic",
            "incidentId": "synthetic",
            "Latitude": 40.0,
            "Longitude": -73.0,
        }
        for key, value in unsafe_keys.items():
            self.assertEqual({key}, unsafe_public_keys({key: value}))


if __name__ == "__main__":
    unittest.main()

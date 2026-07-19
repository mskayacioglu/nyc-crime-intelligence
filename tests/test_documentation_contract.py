import json
import re
import subprocess
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINAL_REPORT = PROJECT_ROOT / "reports" / "final_project_report.md"
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\n]+)\)")
URL_RE = re.compile(r"https?://[^\s<>()`]+")
TURKISH_SPECIFIC_CHARACTERS = set("ÇĞİÖŞÜçğıöşü")
ASCII_TURKISH_MARKERS = re.compile(
    r"\b(?:aciklama|analizler|ayrica|bulunmaktadir|degildir|dogrulama|eksik|"
    r"gereklidir|haftalik|harita|icin|kullanici|modelleme|olarak|proje|raporu|"
    r"sonuclar|tahmin|temizleme|veriler|yonetisim)\b",
    re.IGNORECASE,
)


def tracked_markdown_paths() -> list[Path]:
    output = subprocess.check_output(
        ["git", "-C", str(PROJECT_ROOT), "ls-files", "-z", "--", "*.md"],
        text=True,
        encoding="utf-8",
    )
    paths = {
        PROJECT_ROOT / value
        for value in output.split("\0")
        if value
    }
    if FINAL_REPORT.is_file():
        paths.add(FINAL_REPORT)
    return sorted(paths)


def link_destination(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


class DocumentationContractTest(unittest.TestCase):
    def test_all_markdown_local_links_resolve_and_web_urls_are_well_formed(self) -> None:
        findings: list[str] = []
        for document in tracked_markdown_paths():
            text = document.read_text(encoding="utf-8")
            for raw in MARKDOWN_LINK_RE.findall(text):
                destination = unquote(link_destination(raw))
                parsed = urlparse(destination)
                if parsed.scheme in {"http", "https"}:
                    if not parsed.netloc:
                        findings.append(f"{document.relative_to(PROJECT_ROOT)}: {destination}")
                    continue
                if parsed.scheme or destination.startswith("mailto:"):
                    continue
                path_text = destination.split("#", 1)[0]
                target = document if not path_text else document.parent / path_text
                if not target.resolve().is_relative_to(PROJECT_ROOT.resolve()):
                    findings.append(
                        f"{document.relative_to(PROJECT_ROOT)}: link escapes repository: "
                        f"{destination}"
                    )
                elif not target.exists():
                    findings.append(
                        f"{document.relative_to(PROJECT_ROOT)}: missing target: {destination}"
                    )
            for value in URL_RE.findall(text):
                parsed = urlparse(value.rstrip("'\".,;:"))
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    findings.append(
                        f"{document.relative_to(PROJECT_ROOT)}: malformed URL: {value}"
                    )
        self.assertEqual([], findings)

    def test_documentation_and_notebook_prose_is_english_only(self) -> None:
        findings: list[str] = []
        for document in tracked_markdown_paths():
            text = document.read_text(encoding="utf-8")
            found = sorted(TURKISH_SPECIFIC_CHARACTERS.intersection(text))
            if found:
                findings.append(f"{document.relative_to(PROJECT_ROOT)}: {found}")
            markers = sorted(set(ASCII_TURKISH_MARKERS.findall(text.lower())))
            if markers:
                findings.append(
                    f"{document.relative_to(PROJECT_ROOT)}: ASCII Turkish markers {markers}"
                )
        for notebook in sorted((PROJECT_ROOT / "notebooks").glob("*.ipynb")):
            payload = json.loads(notebook.read_text(encoding="utf-8"))
            prose = "\n".join(
                "".join(cell.get("source", []))
                for cell in payload.get("cells", [])
                if cell.get("cell_type") == "markdown"
            )
            found = sorted(TURKISH_SPECIFIC_CHARACTERS.intersection(prose))
            if found:
                findings.append(f"{notebook.relative_to(PROJECT_ROOT)}: {found}")
            markers = sorted(set(ASCII_TURKISH_MARKERS.findall(prose.lower())))
            if markers:
                findings.append(
                    f"{notebook.relative_to(PROJECT_ROOT)}: ASCII Turkish markers {markers}"
                )
        self.assertEqual([], findings)

    def test_python_requirements_are_pinned(self) -> None:
        for filename in ("requirements.txt", "requirements-eda.txt"):
            lines = [
                line.strip()
                for line in (PROJECT_ROOT / filename).read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            unpinned = [
                line
                for line in lines
                if not line.startswith("-r ") and "==" not in line
            ]
            self.assertEqual([], unpinned, filename)

    def test_code_license_and_data_terms_are_explicit(self) -> None:
        license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")
        data_terms = (PROJECT_ROOT / "DATA_SOURCES.md").read_text(encoding="utf-8")
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("MIT License", license_text)
        self.assertIn("Copyright (c) 2026", license_text)
        self.assertIn(
            "The raw **NYPD Complaint Data Historic** dataset is not included",
            data_terms,
        )
        self.assertIn("qgea-i56i", data_terms)
        self.assertIn("https://opendata.cityofnewyork.us/faq/", data_terms)
        self.assertIn("NYC Open Data terms and disclaimer", data_terms)
        self.assertIn("does not relicense third-party source data", data_terms)
        self.assertIn("[Data sources and terms](DATA_SOURCES.md)", readme)

    def test_notebooks_do_not_install_packages_or_write_canonical_eda_outputs(self) -> None:
        for notebook in sorted((PROJECT_ROOT / "notebooks").glob("*.ipynb")):
            payload = json.loads(notebook.read_text(encoding="utf-8"))
            code = "\n".join(
                "".join(cell.get("source", []))
                for cell in payload.get("cells", [])
                if cell.get("cell_type") == "code"
            )
            self.assertNotRegex(code, r"subprocess\.(?:check_call|run).*pip")
            self.assertNotIn('PROJECT_ROOT / "data" / "processed"', code)
        exploratory = json.loads(
            (
                PROJECT_ROOT
                / "notebooks/01_nypd_complaint_data_comprehensive_eda.ipynb"
            ).read_text(encoding="utf-8")
        )
        exploratory_source = "\n".join(
            "".join(cell.get("source", [])) for cell in exploratory["cells"]
        )
        self.assertIn('OUTPUT_DIR = CACHE_DIR / "outputs"', exploratory_source)

    def test_runtime_and_clean_install_contracts_are_declared_consistently(self) -> None:
        package = json.loads(
            (PROJECT_ROOT / "dashboard/package.json").read_text(encoding="utf-8")
        )
        lock = json.loads(
            (PROJECT_ROOT / "dashboard/package-lock.json").read_text(encoding="utf-8")
        )
        expected_node = "^20.19.0 || ^22.13.0 || >=24.0.0"
        self.assertEqual(expected_node, package["engines"]["node"])
        self.assertEqual(expected_node, lock["packages"][""]["engines"]["node"])
        self.assertEqual("24.5.0", (PROJECT_ROOT / ".nvmrc").read_text().strip())
        self.assertEqual(
            "3.11.15", (PROJECT_ROOT / ".python-version").read_text().strip()
        )
        root_readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        normalized_readme = normalize_whitespace(root_readme)
        self.assertIn("Python 3.10 through 3.14", normalized_readme)
        self.assertIn(
            "EDA environment supports Python 3.11 through 3.13",
            normalized_readme,
        )
        for readme in (PROJECT_ROOT / "README.md", PROJECT_ROOT / "dashboard/README.md"):
            text = readme.read_text(encoding="utf-8")
            self.assertIn("npm ci", text, readme)
            self.assertIn(expected_node, text, readme)

    def test_root_launcher_is_executable_documented_and_syntax_valid(self) -> None:
        launcher = PROJECT_ROOT / "run.sh"
        self.assertTrue(launcher.is_file())
        self.assertTrue(launcher.stat().st_mode & 0o111)

        source = launcher.read_text(encoding="utf-8")
        self.assertIn("npm ci", source)
        self.assertIn("exec npm run dev", source)
        self.assertIn("DASHBOARD_HOST", source)
        self.assertIn("DASHBOARD_PORT", source)
        self.assertIn("./run.sh", (PROJECT_ROOT / "README.md").read_text(encoding="utf-8"))

        syntax_check = subprocess.run(
            ["bash", "-n", str(launcher)],
            check=False,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(0, syntax_check.returncode, syntax_check.stderr)

    def test_final_report_covers_required_scope_without_status_overclaim(self) -> None:
        self.assertTrue(FINAL_REPORT.is_file())
        report = FINAL_REPORT.read_text(encoding="utf-8")
        normalized = normalize_whitespace(report)
        required_terms = (
            "Project question and scope",
            "Data sources and provenance",
            "Cleaning and missing-data semantics",
            "Weekly aggregation and partial-week behavior",
            "Baseline forecasting",
            "duckdb_lag_ensemble_regressor",
            "Training through",
            "Artifact generated",
            "Independent training-completion timestamp",
            "Fixed retrospective forecast horizon",
            "Hotspots and anomalies",
            "Overview",
            "Map & Hotspots",
            "Forecast",
            "Expected Change",
            "Anomalies",
            "Governance",
            "Automated and practical verification",
            "Reproducibility instructions",
            "Data and model limitations",
            "Privacy and aggregate-only boundary",
            "Responsible-use and prohibited-use boundary",
            "Genuinely unavailable information",
            "Accessibility verification note",
            "final manual accessibility review",
        )
        for term in required_terms:
            self.assertIn(normalize_whitespace(term), normalized)
        self.assertIn("fixed retrospective repository demonstration", normalized)
        self.assertIn("not a rolling or real-time service", normalized)

    def test_public_documentation_has_a_clear_current_information_architecture(self) -> None:
        root_readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        roadmap = (PROJECT_ROOT / "Roadmap.md").read_text(encoding="utf-8")
        dashboard_readme = (PROJECT_ROOT / "dashboard/README.md").read_text(
            encoding="utf-8"
        )
        normalized_root_readme = normalize_whitespace(root_readme)
        normalized_roadmap = normalize_whitespace(roadmap)
        normalized_dashboard = normalize_whitespace(dashboard_readme)

        for term in (
            "## Project status",
            "https://huggingface.co/",
            "nyc-crime-intelligence-weekly-forecast",
            "rows excluded by the date-eligibility rule",
            "literal `UNKNOWN` categories",
            "## Known limitations",
        ):
            self.assertIn(term, root_readme if term.startswith("##") else normalized_root_readme)

        for term in (
            "## Delivered scope",
            "## Known limitations",
            "## Possible future improvements",
            "## Explicitly out of scope",
        ):
            self.assertIn(term, roadmap)

        for term in (
            "./run.sh",
            "136 Python contract tests and 214 Vitest tests",
            "final manual accessibility review",
            "## Analytical and responsible-use boundaries",
        ):
            self.assertIn(term, normalized_dashboard)

        legacy_reports = (
            "phase_7a_dashboard_overview.md",
            "phase_7b_map_hotspot_view.md",
            "phase_7c_forecast_map_contract.md",
            "phase_7c2_predictive_map_ui.md",
            "phase_7c3_precinct_spatial_rendering.md",
            "dashboard_anomalies_view.md",
            "dashboard_governance_view.md",
        )
        for filename in legacy_reports:
            self.assertFalse((PROJECT_ROOT / "reports" / filename).exists(), filename)

        for stale_term in (
            "verification-incomplete",
            "in-app browser",
            "synthetic browser mechanism",
            "Initial Tasks",
            "Sprint Plan",
        ):
            self.assertNotIn(stale_term, root_readme)
            self.assertNotIn(stale_term, roadmap)
            self.assertNotIn(stale_term, dashboard_readme)

    def test_project_documentation_does_not_claim_external_status(self) -> None:
        findings: list[str] = []
        for document in tracked_markdown_paths():
            text = document.read_text(encoding="utf-8")
            for pattern in (
                r"(?i)\b(?:project|product|dashboard|application|repository|forecast) "
                r"(?:is|are|was|were|remains?|has been|have been) (?!not\b)(?:now )?"
                r"(?:published|released|live|real[- ]time|operational)\b",
                r"(?i)\b(?:now|currently) "
                r"(?:live|current|real[- ]time|operational|published|released)\b",
            ):
                if match := re.search(pattern, text):
                    findings.append(
                        f"{document.relative_to(PROJECT_ROOT)}: {match.group(0)!r}"
                    )
        self.assertEqual([], findings)


if __name__ == "__main__":
    unittest.main()

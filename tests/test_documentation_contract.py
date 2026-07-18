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
        self.assertIn("Python 3.10 through\n3.14", root_readme)
        self.assertIn("EDA\nenvironment supports Python 3.11 through 3.13", root_readme)
        for readme in (PROJECT_ROOT / "README.md", PROJECT_ROOT / "dashboard/README.md"):
            text = readme.read_text(encoding="utf-8")
            self.assertIn("npm ci", text, readme)
            self.assertIn(expected_node, text, readme)

    def test_final_report_covers_required_scope_without_status_overclaim(self) -> None:
        self.assertTrue(FINAL_REPORT.is_file())
        report = FINAL_REPORT.read_text(encoding="utf-8")
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
            "Phase 7C.3 state",
            "verification-incomplete",
            "single remaining Phase 7C.3 gate",
            "milestone must remain verification-incomplete",
        )
        for term in required_terms:
            self.assertIn(term, report)
        for prohibited in (
            "published",
            "released",
            "live",
            "current",
            "real-time",
            "operational",
        ):
            self.assertIsNone(
                re.search(rf"\b{re.escape(prohibited)}\b", report, re.IGNORECASE),
                prohibited,
            )

    def test_local_scope_and_phase_7c3_blocker_are_explicit(self) -> None:
        root_readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        roadmap = (PROJECT_ROOT / "Roadmap.md").read_text(encoding="utf-8")
        normalized_root_readme = normalize_whitespace(root_readme)
        normalized_roadmap = normalize_whitespace(roadmap)

        for term in (
            "Phase 7C.3 remains verification-incomplete for one practical keyboard check",
            "no alternate or synthetic browser mechanism is used to close that gate",
            "rows excluded by the date-eligibility rule",
            "literal `UNKNOWN` categories",
        ):
            self.assertIn(term, normalized_root_readme)

        for term in (
            "The local implementation roadmap is delivered except for the explicitly open Phase 7C.3 practical native-keyboard verification gate",
            "Any external publication or release work is intentionally deferred",
            "outside this local implementation roadmap",
            "Phase 7C.3 remains verification-incomplete until this final practical keyboard gate is successfully repeated",
        ):
            self.assertIn(term, normalized_roadmap)

        for text in (root_readme, roadmap):
            self.assertIn("verification-incomplete", text)

        required_blocker_relationships = {
            PROJECT_ROOT / "dashboard/README.md": (
                "This recorded browser-channel limitation does not change or close the separate Phase 7C.3 verification blocker below",
                "Phase 7C.3 remains verification-incomplete for one practical browser check",
            ),
            PROJECT_ROOT / "reports/dashboard_anomalies_view.md": (
                "it does not modify or close the separate Phase 7C.3 keyboard blocker",
                "Phase 7C.3 verification-incomplete browser blocker were preserved",
            ),
            PROJECT_ROOT / "reports/dashboard_governance_view.md": (
                "This browser-channel limitation does not change or close the separate Phase 7C.3 verification blocker",
                "the existing Phase 7C.3 blocker remains verification-incomplete",
            ),
            PROJECT_ROOT / "reports/phase_7c2_predictive_map_ui.md": (
                "Phase 7C.3 remains verification-incomplete",
                "This clarification does not close or weaken that blocker",
            ),
            PROJECT_ROOT / "reports/phase_7c3_precinct_spatial_rendering.md": (
                "The milestone therefore remains verification-incomplete",
                "no alternate surface was used",
            ),
            PROJECT_ROOT / "reports/phase_7c_forecast_map_contract.md": (
                "remaining practical native-keyboard verification blocker",
                "this contract does not close or weaken it",
            ),
            PROJECT_ROOT / "reports/phase_7b_map_hotspot_view.md": (
                "current implemented product",
                "delivered behavior and verification evidence",
            ),
        }
        for document, required_phrases in required_blocker_relationships.items():
            normalized = normalize_whitespace(document.read_text(encoding="utf-8"))
            for phrase in required_phrases:
                self.assertIn(phrase, normalized, document)

        forbidden_chrome_closure = (
            "acceptance run in Chrome",
            "Chrome acceptance",
            "closing Chrome",
            "successful Chrome",
            "genuine Chrome",
            "Chrome subsequently completed",
        )
        for document in tracked_markdown_paths():
            text = document.read_text(encoding="utf-8").casefold()
            for phrase in forbidden_chrome_closure:
                self.assertNotIn(phrase.casefold(), text, document)

    def test_project_documentation_does_not_claim_external_status(self) -> None:
        findings: list[str] = []
        for document in tracked_markdown_paths():
            text = document.read_text(encoding="utf-8")
            for pattern in (
                r"(?i)\bpublish(?:ed|es|ing)?\b",
                r"(?i)\breleas(?:ed|es|ing)\b",
                r"(?i)\boperational (?:screen|view|environment)\b",
                r"(?i)\b(?:project|product|dashboard|application|repository|forecast) "
                r"(?:is|are|was|were|remains?) (?!not\b)(?:now )?"
                r"(?:live|current|real[- ]time|operational)\b",
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

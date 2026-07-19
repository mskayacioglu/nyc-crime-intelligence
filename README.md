# NYC Crime Intelligence

NYC Crime Intelligence is an aggregate-only analytical project built from the
NYPD Complaint Data Historic dataset. It combines deterministic data cleaning,
weekly aggregation, historical analysis, baseline and machine-learning
forecasts, hotspot and anomaly signals, and a browser dashboard.

The product is designed for transparent trend exploration. It does not predict
individual behavior, assign person-level risk, or recommend patrol,
enforcement, deployment, or intervention decisions.

## Local product status

The repository includes these dashboard experiences:

| Experience | Purpose | Time semantics |
| --- | --- | --- |
| Overview | Filtered aggregate totals, trends, borough/offense comparisons, and concise context | Observed weekly history |
| Map & Hotspots | Retrospective aggregate concentration signals with a complete list/detail path | Fixed historical snapshot |
| Forecast | Precinct-level aggregate point estimates | Fixed week of 2026-01-05 |
| Expected Change | Forecast minus the documented prior-only historical baseline | Same fixed forecast week |
| Anomalies | Unusually high aggregate increases that have already been observed | Historical observed weeks |
| Governance | Dataset/model coverage, quality warnings, lifecycle facts, readiness, and responsible-use limits | Dataset/model artifact scope, independent of dashboard filters |

Overview, Map & Hotspots, Forecast, Expected Change, Anomalies, and Governance
are implemented. Verified precinct rendering is also implemented and passes its
automated checks. Phase 7C.3 remains verification-incomplete for one practical
keyboard check: the permitted in-app browser can render the focused native
precinct control and its visible focus ring, but its Tab/Enter/Space channel has
not delivered a successful activation to the application. Automated
native-button coverage passes, and no alternate or synthetic browser mechanism
is used to close that gate.

## Reviewed data and model context

The reviewed browser-safe artifacts describe:

- event coverage from 2006-01-01 through 2025-12-31;
- Monday-starting weekly buckets from 2005-12-26 through 2025-12-29;
- latest complete week beginning 2025-12-22;
- a partial latest bucket beginning 2025-12-29;
- 10,071,507 cleaned source rows;
- 10,049,687 included aggregate-safe rows; and
- 21,820 rows excluded by the date-eligibility rule.

The exclusions are not missing-dimension counts. Date-eligible rows with missing
borough, precinct, or offense values remain in aggregate output as literal
`UNKNOWN` categories. Source-quality flags can overlap and are also a separate
population; neither the flags nor retained `UNKNOWN` values should be summed or
equated with the 21,820 exclusions.

The earlier 2005-12-26 bucket is a Monday boundary containing the first covered
event on 2006-01-01. It does not claim that event coverage begins in 2005.

The committed model manifest identifies `duckdb_lag_ensemble_regressor`, model version 1,
artifact version 1. Its training-data window ends on 2025-12-29, and the model
artifact was generated at `2026-07-05T12:40:05.068774+00:00`. No independent
training-completion timestamp exists, so Governance reports **Not independently
recorded** instead of relabeling artifact generation as “last trained.”

The forecast is a fixed retrospective repository/demo horizon, not a live,
rolling, or real-time operational forecast. Forecast values are point estimates;
the reviewed model does not provide prediction intervals. Overall historical
errors are context for the full backtest and are not filter-specific guarantees.

## Prerequisites

The canonical builders and normal contract suite support Python 3.10 through
3.14: DuckDB 1.5.4 declares Python 3.10 or newer, its package classifiers cover
3.10–3.14, and the source uses Python 3.10 syntax. The separately pinned EDA
environment supports Python 3.11 through 3.13; IPython 9.4.0, NumPy 2.3.1, and
SciPy 1.16.0 require Python 3.11 or newer, while the pinned NumPy and PyArrow
builds provide binary support through Python 3.13. The reproducibility target
in `.python-version` is Python 3.11.15, which lies in both supported ranges and
is the version used for the complete canonical verification run.

The locked frontend dependency intersection supports Node.js
`^20.19.0 || ^22.13.0 || >=24.0.0` and npm 10 or newer. `.nvmrc` selects the
verified Node 24.5.0 target; the verified npm version is 11.12.1. Python is not
needed merely to view the committed browser-safe artifacts. Rebuilding data,
models, reports, or dashboard contracts requires the pinned Python dependency
in `requirements.txt`.

## Quick start: run the dashboard

The committed browser-safe artifacts are sufficient to run the local UI.
From the repository root:

```bash
./run.sh
```

Open <http://127.0.0.1:4173/>. Stop the server with `Ctrl+C` when finished.
The launcher verifies Node.js and npm, installs locked frontend dependencies
when they are missing or stale, and then starts the Vite development server.
Set `DASHBOARD_PORT` or `DASHBOARD_HOST` to override its local defaults; run
`./run.sh --help` for an example.

The equivalent manual commands are:

```bash
cd dashboard
npm ci
npm run dev -- --port 4173 --strictPort
```

Use **Governance** for dataset/model-wide metadata and limitations. Governance
does not show the global filter toolbar, but the App preserves filter state for
the return to Overview, Map & Hotspots, or Anomalies.

## Python environment

Analytical rebuilds use Python and DuckDB:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The core Python dependency is pinned to DuckDB 1.5.4. Rebuilding analytical
artifacts also requires the raw complaint CSV described below. The raw dataset
is large, is ignored by Git, and is never sent to the browser.

The scripts under `src/` are the canonical reproducible build path. The
notebooks are optional exploratory or wrapper documents. The historical EDA
notebook writes only under `.cache/eda/outputs` and cannot replace canonical
artifacts. Its optional direct dependencies are version-pinned separately in
`requirements-eda.txt`; install them with
`python -m pip install -r requirements-eda.txt`. The cleaning notebook delegates
to the canonical script and does not install packages from inside the notebook.

## Full analytical rebuild

The raw input is the NYC Open Data
[NYPD Complaint Data Historic](https://data.cityofnewyork.us/Public-Safety/NYPD-Complaint-Data-Historic/qgea-i56i)
CSV. Place the downloaded export at:

```text
data/raw/NYPD_Complaint_Data_Historic.csv
```

The checked-in reports describe the reviewed 3.19 GB, 10,071,507-row snapshot.
Its exact byte count and SHA-256, along with the fields that were not recorded,
are documented in the
[complaint-source provenance note](data/source/nyc_open_data/nypd_complaint_data_historic.md).
The raw file is not committed, so reproducing that exact snapshot requires the
same source export; a newer portal download may produce different dates, counts,
and derived artifacts. The source data is complaint-report data and must not be
treated as complete causal truth.

With the Python environment active, run the established stages from the
repository root in dependency order:

```bash
.venv/bin/python src/data/build_clean_dataset.py --as-of-date 2026-07-04
.venv/bin/python src/analytics/build_dashboard_summary.py
.venv/bin/python src/models/build_baseline_forecast.py
.venv/bin/python src/models/build_ml_forecast.py
.venv/bin/python src/analytics/build_hotspots.py
.venv/bin/python src/analytics/build_anomalies.py
```

The cleaning, analytical-summary, baseline, ML, hotspot, and anomaly builders
serialize allowlisted file references as stable POSIX paths relative to the
declared project root. They fail closed before writing metadata if a referenced
path escapes that root, so generated JSON and Markdown do not retain a local
username or absolute filesystem prefix.

These are full-data builds and can require substantial disk, memory, and run
time. The explicit `--as-of-date 2026-07-04` reproduces the review horizon used
by the reviewed cleaning report; the CLI otherwise defaults to the invocation
date. Advance that value only as part of an intentional source refresh
and record the new review horizon. For a non-destructive cleaning smoke test,
use separate output paths as shown in
`src/data/build_clean_dataset.py --help`; do not point a sampled run at the
committed report or processed-output locations.

## Analytical and dashboard pipeline

The primary deterministic build path is:

```text
raw NYPD complaint data
  -> src/data/build_clean_dataset.py
  -> cleaned events and weekly/monthly aggregate tables
  -> src/models/build_baseline_forecast.py
  -> src/models/build_ml_forecast.py
  -> src/analytics/build_hotspots.py
  -> src/analytics/build_anomalies.py
  -> dashboard contract builders
  -> dashboard/public/data/*
```

After established analytical outputs have been refreshed, regenerate the
dashboard artifacts from the repository root with:

```bash
.venv/bin/python src/analytics/build_dashboard_overview.py
.venv/bin/python src/analytics/build_dashboard_map.py
.venv/bin/python src/analytics/build_dashboard_forecast_map.py
.venv/bin/python src/analytics/build_dashboard_precinct_spatial_reference.py
```

The builders validate inputs and write deterministic canonical artifacts under
`data/processed/` plus browser-safe copies under `dashboard/public/data/`.
Canonical and public copies are expected to remain byte-identical. Do not edit
the staged JSON files manually, expose raw manifests, or use the wall clock
as a substitute for source-derived timestamps.

See [dashboard/README.md](dashboard/README.md) for detailed refresh ordering,
runtime contracts, failure behavior, and UI operation.

## Verification

After activating the Python environment, one command performs the normal local
verification: Python contracts, documentation/link/language checks,
privacy/path/notebook hygiene, a clean `npm ci`, lint, Vitest, the production
build, the production dependency audit, `git diff --check`, and port 4173
checks.

```bash
./scripts/verify_local.sh
```

The normal suite uses deterministic aggregate-only test inputs and the tracked
browser-safe artifacts. It does not require `data/raw`, ignored
`data/processed` files, or a local package cache. Tests fail when a required
fixture or contract is absent; the primary suite does not skip because private
data is unavailable.

After completing the full analytical rebuild, add the explicit full-data
artifact integration check with:

```bash
./scripts/verify_local.sh --full-data
```

That optional mode requires the ignored aggregate/model artifacts and private
cleaned source. It reproduces the committed Forecast Map and Map JSON, Overview
JSON, and compressed Overview cube in temporary paths and compares every output
byte-for-byte. Practical dashboard checks cover 1280 × 900, 768 × 1024, and
390 × 844 viewports.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/data/` | Cleaning and aggregate-data construction |
| `src/models/` | Baseline and ML forecast builders |
| `src/analytics/` | Hotspot, anomaly, and dashboard artifact builders |
| `data/processed/` | Deterministic analytical and canonical dashboard outputs |
| `models/` | Reviewed model and baseline manifests/artifacts |
| `dashboard/` | React/Vite application, runtime decoders, tests, and public data |
| `tests/` | Python contract and pipeline tests |
| `reports/` | Methodology, phase implementation, verification, and limitation reports |
| `scripts/verify_local.sh` | One-command normal verification and optional full-data integration mode |
| `Roadmap.md` | Product roadmap and completed-increment status |

## Documentation map

Start with:

- [Data sources and terms](DATA_SOURCES.md) — code-license boundary, official
  source links, NYC Open Data terms, and the raw-data exclusion policy.
- [Final project report](reports/final_project_report.md) — end-to-end question,
  provenance, methods, model, views, verification, limitations, and use bounds.
- [Roadmap](Roadmap.md) — product scope, completed increments, and remaining
  work.
- [Dashboard README](dashboard/README.md) — frontend architecture, operation,
  refresh, contracts, and verification.
- [Governance view report](reports/dashboard_governance_view.md) — authoritative
  metadata semantics and Governance verification.
- [Anomalies view report](reports/dashboard_anomalies_view.md) — observed
  anomaly semantics and Anomalies verification.

Data and analytical methodology:

- [Data quality](reports/data_quality_report.md)
- [Cleaning and aggregation](reports/cleaning_report.md)
- [Exploratory analysis](reports/exploratory_analysis.md)
- [Baseline forecast](reports/baseline_model_report.md)
- [ML forecast](reports/ml_model_report.md)
- [Hotspot methodology](reports/hotspot_methodology.md)
- [Anomaly methodology](reports/anomaly_methodology.md)

Dashboard phases:

- [Overview](reports/phase_7a_dashboard_overview.md)
- [Map and Hotspots](reports/phase_7b_map_hotspot_view.md)
- [Forecast Map contract](reports/phase_7c_forecast_map_contract.md)
- [Predictive Map UI](reports/phase_7c2_predictive_map_ui.md)
- [Verified precinct spatial rendering](reports/phase_7c3_precinct_spatial_rendering.md)

Official precinct source provenance is documented in
[data/source/nyc_open_data/README.md](data/source/nyc_open_data/README.md).
Complaint-source provenance and exact reviewed-snapshot identity are documented
in
[data/source/nyc_open_data/nypd_complaint_data_historic.md](data/source/nyc_open_data/nypd_complaint_data_historic.md).

## License

Original project software and documentation are available under the
[MIT License](LICENSE). The raw NYPD complaint dataset is not part of this
repository, and the MIT License does not relicense third-party data, map tiles,
or other third-party material. See [Data sources and terms](DATA_SOURCES.md) for
the authoritative dataset reference and applicable source terms.

## Responsible-use boundary

- Reported complaints are not causal truth or a complete measure of harm.
- Reporting delays, revisions, under-reporting, and classification changes can
  affect aggregates.
- The partial latest week is not directly comparable with complete weeks.
- The project uses aggregate analysis and does not expose complaint identifiers,
  exact addresses, event coordinates, demographics, or person-level attributes
  in dashboard contracts.
- Hotspot and anomaly severity describe analytical signals, not offense
  seriousness, neighborhood danger, policing priority, or a recommendation for
  action.
- No individual risk label, patrol recommendation, enforcement recommendation,
  deployment recommendation, or operational allocation is produced.
- No formal model drift monitor or general retraining cadence is currently
  established.

These boundaries are enforced in both deterministic builders and browser
runtime validation, not only documented as UI copy.

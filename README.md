# NYC Crime Intelligence

NYC Crime Intelligence is an aggregate-only analytical project built from the
NYPD Complaint Data Historic dataset. It combines deterministic data cleaning,
weekly aggregation, historical analysis, baseline and machine-learning
forecasts, hotspot and anomaly signals, and a browser dashboard.

The product is designed for transparent trend exploration. It does not predict
individual behavior, assign person-level risk, or recommend patrol,
enforcement, deployment, or intervention decisions.

## Current product status

The repository currently includes these dashboard experiences:

| Experience | Purpose | Time semantics |
| --- | --- | --- |
| Overview | Filtered aggregate totals, trends, borough/offense comparisons, and concise context | Observed weekly history |
| Map & Hotspots | Retrospective aggregate concentration signals with a complete list/detail path | Fixed historical snapshot |
| Forecast | Precinct-level aggregate point estimates | Fixed week of 2026-01-05 |
| Expected Change | Forecast minus the documented prior-only historical baseline | Same fixed forecast week |
| Anomalies | Unusually high aggregate increases that have already been observed | Historical observed weeks |
| Governance | Dataset/model coverage, quality warnings, lifecycle facts, readiness, and responsible-use limits | Published artifact scope, independent of dashboard filters |

Overview, Map & Hotspots, Forecast, Expected Change, Anomalies, and Governance
are implemented. Verified precinct rendering is also implemented and passes its
automated checks. Phase 7C.3 remains verification-incomplete for one practical
keyboard check: the permitted in-app browser can render the focused native
precinct control and its visible focus ring, but its Tab/Enter/Space channel has
not delivered a successful activation to the application. Automated
native-button coverage passes, and no alternate or synthetic browser mechanism
is used to close that gate.

## Published data and model context

The current browser-safe artifacts describe:

- event coverage from 2006-01-01 through 2025-12-31;
- Monday-starting weekly buckets from 2005-12-26 through 2025-12-29;
- latest complete week beginning 2025-12-22;
- a partial latest bucket beginning 2025-12-29;
- 10,071,507 cleaned source rows;
- 10,049,687 included aggregate-safe rows; and
- 21,820 excluded rows.

The earlier 2005-12-26 bucket is a Monday boundary containing the first covered
event on 2006-01-01. It does not claim that event coverage begins in 2005.

The published model is `duckdb_lag_ensemble_regressor`, model version 1,
artifact version 1. Its training-data window ends on 2025-12-29, and the model
artifact was generated at `2026-07-05T12:40:05.068774+00:00`. No independent
training-completion timestamp exists, so Governance reports **Not independently
recorded** instead of relabeling artifact generation as “last trained.”

The forecast is a fixed retrospective repository/demo horizon, not a live,
rolling, or real-time operational forecast. Forecast values are point estimates;
the current model does not provide prediction intervals. Overall historical
errors are context for the full backtest and are not filter-specific guarantees.

## Prerequisites

Running the committed dashboard requires npm and a Node.js version accepted by
the locked Vite toolchain: `^20.19.0 || ^22.12.0 || >=24.0.0`. Python is not
required merely to view the committed browser-safe artifacts. Rebuilding data,
models, reports, or dashboard contracts requires Python 3 and the dependency in
`requirements.txt`.

## Quick start: run the dashboard

The committed browser-safe artifacts are sufficient to run the current UI.
From the repository root:

```bash
cd dashboard
npm ci
npm run dev -- --port 4173 --strictPort
```

Open <http://127.0.0.1:4173/>. Stop the server with `Ctrl+C` when finished.

Use **Governance** for dataset/model-wide metadata and limitations. Governance
does not show the global filter toolbar, but the App preserves filter state for
the return to Overview, Map & Hotspots, or Anomalies.

## Python environment

Analytical rebuilds use Python and DuckDB:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The current pinned Python dependency is DuckDB 1.5.4. Rebuilding analytical
artifacts also requires the raw complaint CSV described below. The raw dataset
is large, is ignored by Git, and is never sent to the browser.

The scripts under `src/` are the canonical reproducible build path. The
notebooks are optional exploratory or wrapper documents. In particular,
`notebooks/01_nypd_complaint_data_comprehensive_eda.ipynb` installs additional
unversioned visualization/scientific packages and should be treated as a
historical analysis environment, not as the production dependency lock.

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
.venv/bin/python src/models/build_baseline_forecast.py
.venv/bin/python src/models/build_ml_forecast.py
.venv/bin/python src/analytics/build_hotspots.py
.venv/bin/python src/analytics/build_anomalies.py
```

These are full-data builds and can require substantial disk, memory, and run
time. The explicit `--as-of-date 2026-07-04` reproduces the review horizon used
by the published cleaning report; the CLI otherwise defaults to the viewer's
current date. Advance that value only as part of an intentional source refresh
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
current dashboard artifacts from the repository root with:

```bash
.venv/bin/python src/analytics/build_dashboard_overview.py
.venv/bin/python src/analytics/build_dashboard_map.py
.venv/bin/python src/analytics/build_dashboard_forecast_map.py
.venv/bin/python src/analytics/build_dashboard_precinct_spatial_reference.py
```

The builders validate inputs and write deterministic canonical artifacts under
`data/processed/` plus browser-safe copies under `dashboard/public/data/`.
Canonical and public copies are expected to remain byte-identical. Do not edit
the staged JSON files manually, expose raw manifests, or use the current clock
as a substitute for source-derived timestamps.

See [dashboard/README.md](dashboard/README.md) for detailed refresh ordering,
runtime contracts, failure behavior, and UI operation.

## Verification

Run all Python contract tests from the repository root:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*_contract.py'
```

Run frontend checks from `dashboard/`:

```bash
npm run lint
npm test
npm run build
npm audit --omit=dev
```

At the Governance increment, the verified baseline is 99 Python contract tests
and 212 Vitest tests across 15 files, with a zero-vulnerability production
dependency audit. The practical dashboard checks cover 1280 × 900, 768 × 1024,
and 390 × 844 viewports.

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
| `Roadmap.md` | Product roadmap and completed-increment status |

## Documentation map

Start with:

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

# NYC Crime Intelligence

NYC Crime Intelligence is an aggregate-only analytical project built from the
official NYPD Complaint Data Historic dataset. It combines deterministic data
cleaning, weekly aggregation, historical analysis, baseline and
machine-learning forecasts, hotspot and anomaly signals, and a local browser
dashboard.

The project is intended for transparent, retrospective exploration of reported
complaint patterns. It does not predict individual behavior, assign person-level
risk, label neighborhoods as dangerous, or recommend patrol, enforcement,
deployment, intervention, or resource-allocation decisions.

## Project status

The analytical pipeline and dashboard are complete for the reviewed repository
snapshot. The dashboard includes:

| View | Purpose | Time semantics |
| --- | --- | --- |
| Overview | Aggregate totals, weekly trends, and borough/offense comparisons | Observed weekly history |
| Map & Hotspots | Retrospective aggregate concentration signals with a complete list/detail path | Fixed historical snapshot |
| Forecast | Precinct-level aggregate point estimates | Fixed week of 2026-01-05 |
| Expected Change | Forecast minus the documented prior-only historical baseline | Same fixed forecast week |
| Anomalies | Unusually high aggregate increases that have already been observed | Historical observed weeks |
| Governance | Dataset/model coverage, quality warnings, lifecycle facts, and responsible-use limits | Dataset/model artifact scope |

This repository is prepared for public source-code hosting, but this document
does not claim that a GitHub repository, hosted demo, or Hugging Face model page
already exists. Those links can be added after the owner creates them.

## Quick start

The committed browser-safe artifacts are sufficient to run the dashboard; the
raw complaint dataset is not required.

Prerequisites:

- Node.js `^20.19.0 || ^22.13.0 || >=24.0.0`
- npm 10 or newer

From the repository root:

```bash
./run.sh
```

Open <http://127.0.0.1:4173/> and stop the server with `Ctrl+C`. The launcher
checks Node.js and npm, installs the locked frontend dependencies when needed,
and starts Vite. Use `./run.sh --help` to see the supported host and port
overrides.

The equivalent manual commands are:

```bash
cd dashboard
npm ci
npm run dev -- --port 4173 --strictPort
```

## Reviewed data and model context

The committed browser-safe artifacts describe:

- event coverage from 2006-01-01 through 2025-12-31;
- Monday-starting weekly buckets from 2005-12-26 through 2025-12-29;
- the latest complete week beginning 2025-12-22;
- a partial final bucket beginning 2025-12-29;
- 10,071,507 source rows evaluated;
- 10,049,687 rows included in aggregates; and
- 21,820 rows excluded by the date-eligibility rule.

The 2005-12-26 bucket is the Monday boundary containing the first covered event
on 2006-01-01; it does not claim event coverage in 2005. Rows excluded by the
date rule are also not interchangeable with missing-dimension counts. Eligible
rows with missing borough, precinct, or offense values remain in aggregate
output as literal `UNKNOWN` categories, and source-quality flags can overlap.

The reviewed model is `duckdb_lag_ensemble_regressor`, model version 1 and
artifact version 1. Its training-data window ends on 2025-12-29, and its
artifact-generation timestamp is `2026-07-05T12:40:05.068774+00:00`. There is
no independently recorded training-completion timestamp.

The forecast is a fixed retrospective demonstration horizon, not a rolling or
real-time service. Values are point estimates; the model does not provide
prediction intervals, and overall historical error is not a guarantee for an
active filter selection.

## Data source and license boundary

The raw analytical input is the official NYC Open Data
[NYPD Complaint Data Historic](https://data.cityofnewyork.us/Public-Safety/NYPD-Complaint-Data-Historic/qgea-i56i)
dataset (`qgea-i56i`). It is deliberately excluded from Git and must not be
added to the repository.

The checked-in reports describe a reviewed 3.19 GB, 10,071,507-row local
snapshot. Its exact byte count, SHA-256, source URLs, and reproduction limits
are recorded in the
[complaint-source provenance note](data/source/nyc_open_data/nypd_complaint_data_historic.md).
A newer portal export can produce different dates, counts, and derived
artifacts.

Original project software and documentation use the [MIT License](LICENSE).
That license does not relicense source datasets, map tiles, or other third-party
material. See [Data sources and terms](DATA_SOURCES.md) for the authoritative
dataset references, NYC Open Data terms, and the raw-data exclusion policy.

## Python environment

Canonical builders and normal contract tests support Python 3.10 through 3.14.
The separately pinned optional EDA environment supports Python 3.11 through
3.13. `.python-version` selects the verified common target, Python 3.11.15.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

DuckDB is pinned to 1.5.4. The scripts under `src/` are the canonical build
path. Notebooks are optional exploratory or wrapper documents; the historical
EDA notebook writes only below `.cache/eda/outputs`. Its direct dependencies
are isolated in `requirements-eda.txt`.

## Full analytical rebuild

Download the raw complaint CSV from the official dataset page and place it at:

```text
data/raw/NYPD_Complaint_Data_Historic.csv
```

Then run the stages in dependency order:

```bash
.venv/bin/python src/data/build_clean_dataset.py --as-of-date 2026-07-04
.venv/bin/python src/analytics/build_dashboard_summary.py
.venv/bin/python src/models/build_baseline_forecast.py
.venv/bin/python src/models/build_ml_forecast.py
.venv/bin/python src/analytics/build_hotspots.py
.venv/bin/python src/analytics/build_anomalies.py
.venv/bin/python src/analytics/build_dashboard_overview.py
.venv/bin/python src/analytics/build_dashboard_map.py
.venv/bin/python src/analytics/build_dashboard_forecast_map.py
.venv/bin/python src/analytics/build_dashboard_precinct_spatial_reference.py
```

These source-dependent stages can require substantial disk, memory, and time.
The explicit `--as-of-date` is part of the reviewed reproduction contract.
Changing the source checksum or review horizon creates a different analytical
snapshot and must be documented as such.

Builders validate their inputs and write deterministic canonical artifacts
under `data/processed/` plus browser-safe copies under
`dashboard/public/data/`. Do not hand-edit staged JSON, expose raw manifests,
or replace source-derived timestamps with the wall clock.

## Verification

After activating the Python environment, run:

```bash
./scripts/verify_local.sh
```

The normal suite covers Python contracts, documentation and local links,
privacy/path/notebook hygiene, a clean `npm ci`, lint, Vitest, the production
build, the production dependency audit, whitespace checks, and local port
hygiene. It uses aggregate-only fixtures and committed browser artifacts; the
raw complaint CSV is not required.

After a complete analytical rebuild, also run:

```bash
./scripts/verify_local.sh --full-data
```

This optional mode requires the ignored local analytical artifacts and compares
regenerated dashboard outputs byte-for-byte with the committed browser-safe
files.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/data/` | Cleaning and aggregate-data construction |
| `src/models/` | Baseline and ML forecast builders |
| `src/analytics/` | Hotspot, anomaly, and dashboard artifact builders |
| `models/` | Reviewed model and baseline manifests/artifacts |
| `dashboard/` | React/Vite application, runtime validation, tests, and public data |
| `tests/` | Python contracts and pipeline tests |
| `reports/` | Data, methodology, model, verification, and limitation reports |
| `scripts/verify_local.sh` | Normal verification and optional full-data integration mode |
| `Roadmap.md` | Delivered scope, known limitations, and possible future work |

## Documentation

Start with:

- [Data sources and terms](DATA_SOURCES.md) — code/data license boundary,
  official source links, and raw-data exclusion policy.
- [Final project report](reports/final_project_report.md) — end-to-end scope,
  provenance, methods, evaluation, limitations, and use boundaries.
- [Dashboard README](dashboard/README.md) — frontend architecture, operation,
  refresh process, contracts, and verification.
- [Roadmap](Roadmap.md) — delivered scope, remaining limitations, and possible
  future improvements.

Method and evidence:

- [Data quality](reports/data_quality_report.md)
- [Cleaning and aggregation](reports/cleaning_report.md)
- [Exploratory analysis](reports/exploratory_analysis.md)
- [Baseline forecast](reports/baseline_model_report.md)
- [ML forecast](reports/ml_model_report.md)
- [Hotspot methodology](reports/hotspot_methodology.md)
- [Anomaly methodology](reports/anomaly_methodology.md)

Official precinct-source provenance is documented in
[data/source/nyc_open_data/README.md](data/source/nyc_open_data/README.md).

## Known limitations

- Complaint records reflect reporting behavior, delay, revision,
  under-reporting, classification, and policy change.
- Counts are source-row counts, not verified unique incidents, victims, harms,
  or causal effects.
- The final source week contains only Monday through Wednesday and can depress
  lag-based inputs relative to a full week.
- Model improvement over the selected baseline is small and was measured on one
  historical split; baseline and ML headline metrics are not matched-row
  comparisons.
- Forecasts lack prediction intervals, calibration analysis, filter-specific
  error estimates, formal drift monitoring, and a general retraining cadence.
- Hotspot thresholds are fixed, and 0.01-degree grid cells are not equal-area.
- Precinct polygons depend on a reviewed quarterly source, while raster tiles
  depend on an external provider.
- Automated keyboard behavior and visible-focus checks pass, but the precinct
  list's native keyboard activation should be repeated during a final manual
  accessibility review on the target browser/platform combination.

## Responsible-use boundary

- Reported complaints are not causal truth or a complete measure of harm.
- Dashboard contracts exclude complaint identifiers, exact addresses, event
  coordinates, demographics, and person-level attributes.
- Hotspot and anomaly severity describe aggregate analytical signals, not
  offense seriousness, neighborhood danger, policing priority, or a
  recommendation for action.
- No individual risk label, patrol recommendation, enforcement recommendation,
  deployment recommendation, or operational allocation is produced.
- Missing, malformed, stale, or incompatible data is not silently converted to
  zero.

These boundaries are enforced by deterministic builders and browser runtime
validation, not only by interface copy.

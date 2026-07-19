# NYC Crime Intelligence Dashboard

The React, TypeScript, and Vite application presents aggregate-only observed
trends, retrospective signals, and one fixed forecast horizon. It has six user
experiences:

| View | Purpose |
| --- | --- |
| Overview | Aggregate totals, weekly trend, and category/geography comparisons |
| Map & Hotspots | Fixed retrospective hotspot snapshot with map-independent list/detail access |
| Forecast | Precinct-aggregated point estimates for 2026-01-05 |
| Expected Change | Forecast minus the prior-only trailing-eight-week baseline |
| Anomalies | High and critical already-observed deviations from historical expectation |
| Governance | Source coverage, data quality, model lifecycle, artifact readiness, and use limits |

The browser never receives complaint-level records, complaint identifiers,
names, exact addresses, event coordinates, victim or suspect demographics,
person-level scores, or patrol/enforcement recommendations.

## Run locally

From the repository root, the recommended command is:

```bash
./run.sh
```

Open <http://127.0.0.1:4173/>. The launcher checks the runtime, performs a
locked install when dependencies are missing or stale, and starts the Vite
development server.

Manual startup requires npm 10 or newer and a Node.js version satisfying
`^20.19.0 || ^22.13.0 || >=24.0.0`. `.nvmrc` selects the verified Node 24.5.0
target.

```bash
cd dashboard
npm ci
npm run dev -- --port 4173 --strictPort
```

## Architecture

The application loads these committed browser-safe artifacts:

- `public/data/overview.json`
- `public/data/overview-cube.bin.gz`
- `public/data/map.json`
- `public/data/forecast-map.json`
- `public/data/precinct-spatial-reference.json`

Overview metadata and the compressed weekly cube drive observed charts and
filters. Map & Hotspots uses a separate fixed-snapshot contract. Forecast and
Expected Change use the forecast contract plus official precinct geometry.
Anomalies is projected from the Overview contract. Governance reconciles
allowlisted fields from the same artifacts and does not introduce a parallel
browser dataset.

Every loader validates unknown JSON before rendering. Validation covers exact
application and schema identity, versions, timestamps, date ranges, finite
metrics, unique stable keys, deterministic order, arithmetic, source/forecast
alignment, availability state, and aggregate-only privacy and ethics flags.
Malformed or contradictory values fail closed.

Optional sources remain independent. A missing, invalid, stale, or
incompatible Forecast, Hotspot, Expected Change, anomaly, or spatial artifact
is not converted into an empty result, numeric zero, or generic healthy state.
Valid zero, available-empty, and filtered-empty states remain distinguishable.

## Data and time semantics

Events cover 2006-01-01 through 2025-12-31. Monday-starting weekly buckets
cover 2005-12-26 through 2025-12-29 because the first covered Sunday belongs to
the bucket beginning 2005-12-26. The latest complete bucket begins 2025-12-22;
the bucket beginning 2025-12-29 is partial.

Source, included aggregate-safe, and date-excluded populations are 10,071,507,
10,049,687, and 21,820 rows. Source quality flags overlap and are separate from
aggregate-safe retained `UNKNOWN` dimensions. Missing and malformed values do
not become zero; a verified numeric zero remains zero.

The committed model is `duckdb_lag_ensemble_regressor`, model version 1 and
artifact version 1. Its fixed forecast week is 2026-01-05. The artifact was
generated at `2026-07-05T12:40:05.068774+00:00`, but an independent
training-completion time was not recorded. Governance keeps those facts
separate rather than relabeling artifact generation as “last trained.”

Overall MAE, RMSE, weighted MAE, and coverage describe historical validation
for the complete backtest. They are not filter-specific error estimates or
uncertainty intervals. The forecast is a fixed retrospective point-estimate
demonstration, not a rolling or real-time service.

## Map and filter contract

The Map workspace provides Hotspots, Forecast, and Expected Change modes.
Borough, precinct, offense, and law-category selections are shared with the
filter-aware application views. Borough changes constrain precinct choices.

Hotspots are a fixed 2025-12-30 snapshot. They appear only when the selected
date range includes the latest complete Overview week and are not recomputed in
the browser. Precinct-grain rows can be filtered by precinct; grid rows have no
precinct assignment and are omitted when a precinct filter is active.

Forecast rows are aggregated to one row per precinct after active categorical
filters. Baselines are summed only when every contributing row has sufficient
history. Partial history is disclosed and aggregate change is withheld rather
than treated as zero. Date filters gate compatibility; they do not generate
additional forecast horizons.

Forecast and Expected Change use official MultiPolygon boundaries from the NYC
Department of City Planning / NYC Open Data Police Precincts dataset
(`y76i-bdw7`), edition 26B. The spatial contract covers all 78 forecast precinct
keys exactly once and does not reuse complaint-derived hotspot centroids.
Polygon, list, and detail selection share one state.

Raster tiles provide geographic context only. Vector polygons/points, filters,
legends, lists, and details remain usable if tiles fail. The official quarterly
geometry is withheld as stale after its declared 120-day review window until a
new edition is reviewed; forecast list/detail values remain available.

## Accessibility and responsive behavior

- Native landmarks, headings, controls, lists, status behavior, accessible
  names, and visible focus are preserved.
- Map experiences have a complete list/detail path that does not require
  pointer interaction with the map.
- Anomaly rows are native buttons with `aria-pressed`; selection, detail, and
  polite status share one identity.
- Governance uses native navigation and `details`/`summary` disclosure.
- Severity uses text and shape in addition to color, and touch controls have a
  44 px minimum target.
- Desktop, tablet, and mobile layouts avoid page-level horizontal overflow.
- `prefers-reduced-motion` removes or simplifies depth and transition effects.
- Solid-color and structural-border fallbacks preserve content when blur or
  transparency support is unavailable.

Automated native-button activation, selection synchronization, and
visible-focus coverage pass. The precinct list's keyboard activation should
also be repeated during a final manual accessibility review on the intended
browser/platform combination before describing that manual review as closed.

## Refresh dashboard data

Use the project Python environment from the repository root. A full refresh
requires the reviewed raw complaint CSV at the path documented in the root
README and must rebuild every dependency in order:

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

Advance `--as-of-date` only with an intentional source refresh and record the
new horizon. A different checksum or review date creates a different analytical
snapshot. See the [root README](../README.md),
[data-source terms](../DATA_SOURCES.md), and
[complaint-source provenance note](../data/source/nyc_open_data/nypd_complaint_data_historic.md).

If all analytical outputs and manifests are already regenerated and only the
browser projections need restaging, run:

```bash
.venv/bin/python src/analytics/build_dashboard_overview.py
.venv/bin/python src/analytics/build_dashboard_map.py
.venv/bin/python src/analytics/build_dashboard_forecast_map.py
.venv/bin/python src/analytics/build_dashboard_precinct_spatial_reference.py
```

If anomaly analysis alone changes, rebuild Overview after
`build_anomalies.py`. Governance metadata is also projected by existing
Overview and Forecast Map builders; no separate Governance build exists.

Canonical/browser pairs are:

| Canonical output | Browser-safe copy |
| --- | --- |
| `data/processed/dashboard_overview.json` | `dashboard/public/data/overview.json` |
| `data/processed/dashboard_overview_cube.bin.gz` | `dashboard/public/data/overview-cube.bin.gz` |
| `data/processed/dashboard_map.json` | `dashboard/public/data/map.json` |
| `data/processed/dashboard_forecast_map.json` | `dashboard/public/data/forecast-map.json` |
| `data/processed/dashboard_precinct_spatial_reference.json` | `dashboard/public/data/precinct-spatial-reference.json` |

The paired artifacts must remain byte-identical. Builders use stable
repository-relative POSIX references and reject paths outside the declared
project root. Do not hand-edit staged JSON, infer missing timestamps, or use
build time as a substitute for source-derived time. Builders that support
`--skip-dashboard-copy` can update only the canonical artifact when that is an
intentional intermediate step.

The spatial source is the official `y76i-bdw7` bulk GeoJSON, DCP edition 26B,
retrieved 2026-07-12. Its SHA-256 is
`5210830afa9d0875b7a7c769edfc4d2ebe984a9ab1e36f3b7fad8508828172aa`.
The portal does not provide a named dataset-specific license; the repository
records the official NYC Open Data and DCP public-use terms without inventing a
license name. See the
[spatial provenance documentation](../data/source/nyc_open_data/README.md).

## Verification

The normal all-in-one check runs from the repository root after the Python
environment is active:

```bash
./scripts/verify_local.sh
```

It runs deterministic aggregate-only Python contracts, documentation and
hygiene checks, `npm ci`, ESLint, all Vitest tests, the TypeScript/Vite
production build, the production dependency audit, whitespace checks, and port
hygiene. Raw complaint data is not required.

The latest local acceptance pass completed 136 Python contract tests and 214
Vitest tests, plus lint, production build, dependency audit, documentation,
privacy/path/notebook, history, and whitespace checks. Counts are a snapshot of
that reviewed run rather than a compatibility promise.

After a full analytical rebuild, run the explicit integration mode:

```bash
./scripts/verify_local.sh --full-data
```

That mode requires ignored local analytical inputs and compares regenerated
Forecast Map, Map, Overview, and compressed Overview cube artifacts
byte-for-byte with the committed browser-safe files.

Focused frontend checks can be run from `dashboard/`:

```bash
npm run lint
npm test
npm run build
npm audit --omit=dev
```

Manual review should cover desktop, tablet, and mobile widths; every filter and
Reset; empty, missing, invalid, stale, incompatible, and network states;
map/list/detail synchronization; valid-zero and unavailable-baseline states;
keyboard operation; focus visibility; reduced motion; tile-failure resilience;
overflow; and console/request errors.

## Analytical and responsible-use boundaries

- Overview dates select inclusive Monday-based aggregate buckets.
- Trend baselines use prior weeks only; anomalies describe already-observed
  aggregate deviations and are not probabilities or forecasts.
- Forecasts are shown only with aligned historical error context and do not
  include prediction intervals.
- Hotspot centroids and grid centers are aggregate summaries, not exact event
  locations. Degree-based grid cells are not equal-area.
- Source rows with unknown or unreconciled geography are withheld and counted;
  they are not silently remapped.
- No complaint IDs, event rows, names, exact addresses, event coordinates,
  demographics, or person-level attributes are exposed.
- Signals do not identify a specific future incident, score neighborhood
  danger, predict individual behavior, or recommend patrol, enforcement,
  deployment, intervention, or resource allocation.

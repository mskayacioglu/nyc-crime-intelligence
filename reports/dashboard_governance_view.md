# Dashboard Governance View

## Status and scope

The dedicated **Governance** experience is implemented as the fourth,
lazy-loaded dashboard view. It provides a complete non-chart path for committed
data coverage, data-quality warnings, model identity and lifecycle, analytical
artifact readiness, and responsible-use limits. Its values are dataset- and
model-wide; they do not pretend to change with the selected borough, precinct,
offense, law-category, or date filters.

The concise Overview **About the data** disclosure remains concise. Governance
does not restore phase names, raw source paths, unrestricted manifests, or
development metadata to Overview. No event-level or person-level artifact is
added, and the increment does not change model inputs, predictions, anomaly or
hotspot definitions, geometry, or analytical thresholds.

The initial repository audit matched the requested state exactly:

- HEAD `b1cb77ce325b373be83e8d1282d1b904ec702c2c` on `main`, subject
  `Implement Anomalies dashboard experience`;
- clean worktree and index, empty unstaged and staged diffs, and clean
  `git diff --check`;
- no listener on port 4173; and
- no applicable repository `AGENTS.md`.

There was no initial-state discrepancy. The Anomalies commit was not amended,
rewritten, or otherwise altered.

## Authoritative data chain

Governance does not introduce a parallel browser artifact. It strictly projects
allowlisted fields from existing frontend-safe contracts:

```text
data/processed/complaints_clean.parquet
+ data/processed/crime_weekly_area.parquet
+ established anomaly / hotspot / forecast metadata
  -> src/analytics/build_dashboard_overview.py
  -> data/processed/dashboard_overview.json
  -> dashboard/public/data/overview.json

data/processed/dashboard_overview.json
+ data/processed/ml_predictions.parquet
+ data/processed/ml_metrics.json
+ models/weekly_forecast/model_manifest.json
+ established baseline predictions and manifest
  -> src/analytics/build_dashboard_forecast_map.py
  -> data/processed/dashboard_forecast_map.json
  -> dashboard/public/data/forecast-map.json

data/processed/dashboard_map.json
  -> dashboard/public/data/map.json

data/processed/dashboard_precinct_spatial_reference.json
  -> dashboard/public/data/precinct-spatial-reference.json
```

The minimal contract extension was necessary because the former browser-safe
projection did not include the complete aggregate quality distinction or an
honest independent-training-time state. The existing Overview contract now
includes deterministic source quality counts and aggregate-safe `UNKNOWN`
counts. The existing Forecast Map contract now distinguishes model artifact
generation from an explicitly unavailable independent training-completion
timestamp. Both builders continue to produce their canonical and public copies;
raw manifests are not exposed.

## Coverage and population semantics

The committed coverage values reconcile as follows:

| Meaning | Authoritative value |
| --- | ---: |
| Event-date coverage | 2006-01-01 through 2025-12-31 |
| Weekly bucket range | 2005-12-26 through 2025-12-29 |
| Latest complete Monday bucket | 2025-12-22 |
| Latest observed Monday bucket | 2025-12-29, partial |
| Clean source rows evaluated | 10,071,507 |
| Included aggregate-safe rows | 10,049,687 |
| Excluded rows | 21,820 |

Weekly dates are Monday bucket boundaries. The first event is 2006-01-01, but
it belongs to the weekly bucket beginning 2005-12-26. Governance explains that
this earlier bucket label is not evidence of an earlier event. The last bucket
begins 2025-12-29 and is incomplete because event coverage ends on Wednesday,
2025-12-31. It is not presented as comparable with complete weeks.

## Data quality and missing-data warnings

The source-level cleaning flags are shown from the full clean-source population:

| Source issue flag | Rows |
| --- | ---: |
| Missing offense | 18,907 |
| Missing borough | 10,078 |
| Missing precinct | 771 |
| Missing or invalid complaint start date | 655 |
| Implausibly old complaint start date | 21,165 |
| Future complaint start date | 0 |
| Future complaint end date | 5 |
| Complaint end before start | 579 |
| Report date before complaint start | 16 |
| Missing coordinates | 479 |
| Zero coordinates | 25 |
| Coordinates outside broad NYC bounds | 33 |
| Invalid law category | 0 |

There are 52,050 rows with at least one listed flag, 605 rows with more than one,
and at most three flags on one row. These categories overlap and must not be
summed. They are not the excluded-row count.

The aggregate-safe retained population has separate literal `UNKNOWN` counts:

| Retained aggregate dimension | `UNKNOWN` rows |
| --- | ---: |
| Borough | 10,065 |
| Precinct | 713 |
| Offense | 18,847 |
| Law category | 0 |

Governance keeps these populations distinct. A missing borough, precinct, or
offense may remain in aggregate output as `UNKNOWN`; it does not imply that the
row was excluded. A verified zero remains zero. Missing, malformed,
incompatible, or unavailable values are never converted to zero.

## Model identity, lifecycle, and validation context

The model is presented as **DuckDB lag ensemble regressor** with committed
identity `duckdb_lag_ensemble_regressor`, model version 1, and artifact version
1. Lifecycle fields remain distinct:

| Field | Meaning and value |
| --- | --- |
| Training-data window | 2005-12-26 through 2025-12-29 |
| Training data through | 2025-12-29; a data horizon, not a completion time |
| Independent last-training time | **Not independently recorded** |
| Model artifact generated | `2026-07-05T12:40:05.068774+00:00` |
| Fixed forecast horizon | Week of 2026-01-05 |

The artifact-generation timestamp is never relabeled as “last trained.” The
forecast is described as a fixed repository/demo horizon generated
retrospectively, not a live, current, real-time, or rolling operational
forecast. The contract-derived timestamp, spatial source-retrieval timestamp,
spatial portal-update timestamp, and viewer clock are separately labeled in a
collapsed safe-provenance glossary. The viewer clock is used only for the
already-documented spatial TTL.

Overall historical validation covers 437,144 segment-weeks from 2024-12-30
through 2025-12-22: MAE 0.4894, RMSE 1.3943, weighted MAE 3.6555, and 100%
prediction coverage. These are overall backtest context only. The interface
does not present them as filter-specific error, a guarantee, or an uncertainty
interval. Forecasts remain point estimates and no prediction interval exists.

No general retraining cadence, formal drift monitor, model-age threshold, or
universal wall-clock staleness rule is invented.

## Artifact and signal readiness

The view keeps adjacent products semantically distinct:

| Product | Governance meaning |
| --- | --- |
| Hotspots | Retrospective fixed-snapshot aggregate concentration; 396 rows |
| Anomalies | Already-observed weekly aggregate deviations; 10,378 high/critical rows |
| Forecast | Fixed-horizon aggregate point estimates; 5,852 rows for 2026-01-05 |
| Expected Change | Forecast minus the prior-only baseline; 5,848 count changes, 2,797 percentage changes |
| Precinct boundaries | Official aggregate-only spatial reference; 78 complete features |

Expected Change honestly reports partial percentage availability: 3,051
baselines are valid zero values, so their percentage change is undefined, and
four rows have no count change because their baseline is unavailable. Neither
case is converted to zero or described as healthy.

The Overview, Map, Forecast Map, and spatial contracts are decoded independently
and reconciled. Supported `available`, `empty`, `missing`, `invalid`, `stale`,
`incompatible`, `partial`, and network-unavailable states retain textual labels
and sanitized reasons. Core Overview failure produces the dedicated loading,
unavailable, invalid, or incompatible page state. Optional model, analytical,
or spatial failures remain localized so valid coverage and lifecycle facts are
not erased. The established 120-day portal-update TTL is applied only to the
official spatial source. No generic “all systems healthy” classification is
created.

## Runtime validation and failure behavior

The Python builders and TypeScript loaders fail closed on:

- malformed, reversed, non-Monday, or inconsistent dates and ranges;
- malformed timestamps, including a non-midnight contract-derived data date;
- unsupported identities, versions, artifact types, or model names;
- negative or non-finite counts, percentages, and validation metrics;
- duplicate rows, dimensions, keys, or nondeterministic order;
- contradictory status, reason, availability, and row-count combinations;
- disagreement between Overview, Map, Forecast Map, model, historical error,
  and spatial keys or horizons;
- false aggregate-only privacy, ethics, or responsible-use flags; and
- absolute paths, local usernames, unsafe source filenames, and unrestricted
  provenance or manifest fields.

Network failures are not confused with fulfilled but invalid contracts.
Recovery reruns the normal loaders and restores the validated state when valid
artifacts become available. Automated tests cover loading, network error,
invalid, incompatible, optional-unavailable, stale, empty, retry/recovery, and
valid-zero behavior.

## User experience, navigation, and filters

Governance is the fourth native navigation button after Overview, Map &
hotspots, and Anomalies. The selected button uses `aria-current="page"`, the
skip link names and targets the selected view, headings form a semantic
hierarchy, readiness is stated in text, and the safe provenance glossary uses
native `details`/`summary`.

Governance intentionally omits the global filter toolbar. App-owned filter
state remains mounted, so entering and leaving Governance preserves all
non-default date, borough, precinct, offense, and law-category selections. The
existing borough-to-precinct constraint and Reset behavior remain unchanged in
filter-aware views.

No custom keyboard handlers or unnecessary live regions were added. Native
controls retain visible focus treatment and a minimum 44-pixel target. Long
timestamps, model identifiers, status reasons, and limitation text use wrapping
and overflow-safe containers. On mobile, the four navigation buttons form a
readable two-by-two grid rather than a squeezed single row.

## Responsible-use boundaries

The visible limitations state that:

- reported complaint events are not causal truth or a complete measure of harm;
- reporting delays, revisions, under-reporting, and classification or policy
  changes can affect aggregates;
- the latest partial week is not directly comparable with complete weeks;
- the forecast is a fixed historical/repository demo horizon, not real-time
  operational guidance;
- forecasts are point estimates without prediction intervals;
- overall validation errors are not filter-specific guarantees;
- the model does not account for every holiday, exogenous event, reporting
  delay, or spatial spillover;
- no formal drift monitor or general retraining cadence exists;
- analysis is aggregate-only and uses no demographics or person-level scoring;
- no individual risk labels are produced; and
- no patrol, enforcement, deployment, intervention, or operational allocation
  recommendation is produced.

Analytical availability, severity, status, or priority must not be framed as a
policing priority.

## Practical browser verification

Only the installed in-app Browser and semantic locators were used. No Chrome,
raw CDP, Playwright CLI, external browser automation, manually dispatched
events, JavaScript `focus()`/`click()`, application-state mutation, or
coordinate-click substitute was used.

Checks passed at the required viewports:

- **1280 × 900:** no page-level horizontal overflow; four native 44-pixel
  navigation targets; 44-pixel collapsed disclosure target; long visible values
  wrapped without clipping.
- **768 × 1024:** no page-level horizontal overflow or clipped Governance card;
  all four navigation targets remained 44 pixels high and readable.
- **390 × 844:** no page-level horizontal overflow or clipped long value; the
  navigation rendered exactly two columns and two rows with 175.5 × 44-pixel
  buttons; no visible native target measured below 44 pixels.

The screen showed the real coverage dates and row populations, partial-week
warning, issue and `UNKNOWN` counts, model identity and versions, independent
training-time unavailability, artifact-generation timestamp, fixed forecast
horizon, overall validation context, no-interval wording, all five distinct
artifact/signal statuses, and responsible-use limits. No filter toolbar, raw
filesystem path, local username, phase label, source path, or unrestricted
manifest content appeared.

A non-default round trip preserved 2025-01-13 through 2025-02-24, Brooklyn,
Precinct 60, Burglary, and Felony. Changing Brooklyn to Bronx reset the precinct
to **All in borough**, retained Bronx precincts such as 40, and removed Brooklyn
Precinct 60. Reset restored the complete default range and all categorical
filters.

Regression checks retained Overview's five metrics, four chart regions, and
concise **About the data** disclosure; all 396 default Hotspots; Forecast and
Expected Change with 78 precincts; and all 645 default Anomalies with the
deterministic first Manhattan Precinct 5 selection. The clean session loaded
`overview.json`, the Overview cube, `map.json`, `forecast-map.json`, and the
precinct spatial artifact. No browser warning or error and no failed required
request surfaced.

The Governance lazy-loading status was observed before the two contracts
completed. Practical network-error injection was not attempted because the
allowed browser surface provides no safe request-interception facility and no
temporary production switch or harness was justified; explicit error and
recovery behavior is covered automatically.

Pointer activation opened and collapsed the native provenance disclosure. An
earlier in-app browser channel left focus on the Governance button after a Tab
request while showing its visible two-pixel focus ring. Its Enter/Space delivery
to the focused native summary failed because that channel could not maintain the
focused locator target. No custom handler or synthetic event was used. Native
navigation and disclosure keyboard behavior pass automated tests. This remains
historical tool-channel evidence. Phase 7C.3 later completed genuine Chrome
Enter/Tab/Space acceptance on the real predictive native-button path; the
Governance channel result is not an open local completion gate.

Every temporary browser tab and viewport override was finalized, the
development server was stopped, and port 4173 was left free.

## Final automated verification

The final focused frontend pass completed 88 tests in five files covering the
Governance decoder, component states and recovery, App navigation/filter state,
responsive rules, and Forecast Map loader. The full frontend pass completed all
212 Vitest tests in 15 files.

The five requested focused Python suites completed 59 tests:

| Suite | Tests |
| --- | ---: |
| Dashboard Overview contract | 22 |
| Dashboard Forecast Map contract | 21 |
| Cleaning pipeline contract | 4 |
| ML forecast contract | 6 |
| Baseline forecast contract | 6 |

The full `test_*_contract.py` discovery completed all 99 tests. ESLint,
TypeScript compilation, the Vite production build, and `git diff --check`
passed. The production dependency audit reported zero vulnerabilities.

The production build transformed 2,365 modules and reported these raw/gzip
sizes:

| Asset | Size |
| --- | ---: |
| HTML | 0.64 / 0.36 kB |
| MapView CSS | 15.09 / 6.36 kB |
| Main CSS | 66.39 / 11.33 kB |
| Anomaly decoder | 7.95 / 2.80 kB |
| JSX runtime | 9.25 / 3.50 kB |
| Lazy Anomalies view | 10.09 / 3.12 kB |
| Lazy Governance view | 39.61 / 10.26 kB |
| Spatial loader | 39.86 / 11.38 kB |
| Lazy Map view | 190.13 / 54.23 kB |
| Main JavaScript | 219.61 / 68.81 kB |
| Overview charts | 404.31 / 113.53 kB |

Canonical/public equality passed for Overview JSON, the Overview cube, Map JSON,
Forecast Map JSON, and the precinct spatial JSON. The Overview cube and all
unrelated analytical definitions remain unchanged.

## Refresh and operation

From the repository root, use a full dependency-ordered refresh whenever the
raw source, weekly aggregates, models, or hotspot/anomaly outputs change:

```bash
.venv/bin/python src/data/build_clean_dataset.py --as-of-date 2026-07-04
.venv/bin/python src/models/build_baseline_forecast.py
.venv/bin/python src/models/build_ml_forecast.py
.venv/bin/python src/analytics/build_hotspots.py
.venv/bin/python src/analytics/build_anomalies.py
.venv/bin/python src/analytics/build_dashboard_overview.py
.venv/bin/python src/analytics/build_dashboard_map.py
.venv/bin/python src/analytics/build_dashboard_forecast_map.py
.venv/bin/python src/analytics/build_dashboard_precinct_spatial_reference.py
```

When all established analytical artifacts and manifests have already been
regenerated and reconciled and only their browser-safe projections need
restaging, run the four
`build_dashboard_*` commands only. The [root README](../README.md) documents
raw-source identity, environment setup, the full build, and the explicit
cleaning review horizon. A projection-only refresh must not be used to conceal
an older model, hotspot snapshot, or anomaly source.

The Overview builder recomputes aggregate quality metadata from the established
clean and weekly processed outputs. The Forecast Map builder reads the existing
model and baseline artifacts; it does not retrain either model. Canonical and
public Overview, cube, Forecast Map, and spatial copies must remain
byte-identical. Use the builders' existing `--skip-dashboard-copy` option only
when intentionally refreshing a canonical copy without staging the browser
copy.

For local operation:

```bash
cd dashboard
npm ci
npm run dev -- --port 4173 --strictPort
```

Open Governance from the fourth navigation button. Stop the server after
verification. If the core Overview artifact is unavailable or invalid, correct
and regenerate that contract. If only Forecast, Expected Change, Map, or spatial
metadata is unavailable, inspect the corresponding established builder input;
do not edit the staged JSON manually or substitute the wall clock.

## Genuine limitations

- No independent training-completion timestamp exists; Governance accurately
  reports **Not independently recorded**.
- No prediction interval, formal drift monitor, model-age SLA, or general
  retraining cadence exists.
- The forecast horizon is fixed to 2026-01-05 and is not a live operational
  forecast.
- Historical error metrics are overall context and cannot be interpreted as
  filter-specific performance.
- Spatial freshness is the only documented wall-clock TTL classification.
- An earlier in-app browser channel could not complete the Governance
  Tab/Shift+Tab/Enter/Space pass. Automated native-control coverage passes, and
  the completed Phase 7C.3 Chrome run separately supplies genuine predictive
  native-button Enter/Tab/Space evidence on the real local application.

## Implementation inventory

The increment changes:

- Overview and Forecast Map deterministic builders, generated public contracts,
  and Python contract tests;
- TypeScript Overview/Forecast/Governance types and runtime decoders/loaders;
- the lazy Governance view, application navigation, tests, responsive styles,
  and shared fixtures;
- Roadmap and dashboard operation documentation; and
- this implementation and verification report.

No dependency, complaint-level artifact, browser harness, screenshot fixture,
temporary production switch, model change, retraining output, or geometry change
was added.

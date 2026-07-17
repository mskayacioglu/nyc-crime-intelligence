# NYC Crime Intelligence Dashboard

The dashboard provides aggregate-only Overview, Hotspot, Predictive Map,
Anomalies, and Governance experiences:

- **Overview** remains the first screen and reads compact metadata plus the
  gzip-compressed weekly aggregate cube.
- **Map & hotspots** reads a separate compact hotspot snapshot and adds both a
  visual map and a keyboard-accessible aggregate hotspot list/detail view.
- **Predictive Map** strictly loads the browser-safe contract and adds Forecast
  and Expected change modes to the existing Map workspace.
- **Anomalies** reads the already-established Overview anomaly signal and shows
  unusually high observed weekly aggregate increases against their documented
  historical expectation.
- **Governance** lazily reconciles the existing published contracts into a
  dedicated non-chart account of data coverage, missing-data warnings, model
  identity and lifecycle, artifact readiness, and responsible-use limits.

The browser never receives complaint-level records, complaint identifiers,
victim or suspect demographics, person-level scores, or recommendations about
patrol or enforcement.

## Architecture

The Vite, React, and TypeScript project loads or stages these frontend-safe outputs:

- `public/data/overview.json`
- `public/data/overview-cube.bin.gz`
- `public/data/map.json`
- `public/data/forecast-map.json` (runtime-validated with `cache: 'no-cache'`)
- `public/data/precinct-spatial-reference.json` (runtime-validated with
  `cache: 'no-cache'`)

Governance introduces no parallel browser artifact. It projects only
allowlisted, aggregate-safe fields from the existing Overview, Map, Forecast
Map, and precinct-spatial contracts. The Overview build now deterministically
publishes source-level cleaning issue counts and aggregate-safe literal
`UNKNOWN` counts. The Forecast Map build publishes the model artifact-generation
timestamp separately from an explicit unavailable independent training time.
Both builders continue to write their established canonical and public copies.

The Governance runtime decoder fails closed on malformed identity, version,
date, timestamp, range, count, finite metric, privacy, ethics, availability, or
reason fields. It also reconciles event and weekly coverage, row populations,
model identity and version, training window, fixed forecast horizon, historical
validation context, Map coverage, and spatial Forecast keys across contracts.
Absolute paths, unsafe source names, contradictory status/row combinations,
non-finite values, and unreviewed extra quality fields are rejected rather than
rendered. Optional artifact failures are sanitized and remain independent; an
unavailable Forecast, Hotspot, Expected change, or spatial source is never
converted into an empty row, a numeric zero, or an all-systems-healthy label.

### Governance contract semantics

The coverage contract distinguishes event dates from Monday-starting bucket
dates. Events cover 2006-01-01 through 2025-12-31, while weekly buckets cover
2005-12-26 through 2025-12-29. The earlier bucket contains the first event on
2006-01-01; it does not claim an earlier event. The latest complete bucket begins
2025-12-22, and the bucket beginning 2025-12-29 is explicitly partial. Source,
included aggregate-safe, and excluded populations are respectively 10,071,507,
10,049,687, and 21,820 rows.

Source-level quality flags and aggregate-safe retained `UNKNOWN` values are
different populations. Source examples include missing offense 18,907, borough
10,078, precinct 771, missing/invalid start date 655, missing coordinates 479,
zero coordinates 25, and out-of-bounds coordinates 33. The corresponding
aggregate-safe retained dimensions include borough 10,065, precinct 713,
offense 18,847, and law category 0. Source issue categories overlap: 52,050 rows
have at least one flag and 605 have more than one, so flags must not be summed or
equated with excluded rows. A verified zero remains zero; unavailable values do
not become zero.

The model identity is `duckdb_lag_ensemble_regressor`, model version 1, artifact
version 1. Its data window is 2005-12-26 through 2025-12-29, its artifact was
generated at `2026-07-05T12:40:05.068774+00:00`, and its fixed forecast week is
2026-01-05. There is no independently recorded training-completion timestamp,
so Governance shows **Not independently recorded** and never relabels artifact
generation as “last trained.” Overall MAE, RMSE, weighted MAE, and coverage are
historical validation context, not filter-specific errors or uncertainty
intervals. The published forecast remains a fixed repository/demo point
estimate, not a live or real-time operational forecast.

Governance separately labels the training-data horizon, artifact generation,
fixed forecast horizon, event coverage, latest complete and partial buckets,
contract-derived data timestamp, spatial retrieval and portal-update
timestamps, and current viewer clock. The viewer clock is used only for the
already-documented spatial TTL. No general retraining cadence, drift SLA,
model-age threshold, or universal wall-clock staleness rule is inferred.

Anomalies adds no parallel frontend artifact. The dedicated view lazily decodes
`signals.anomalies` from `overview.json`, whose source is the established
`crime_weekly_area.parquet` -> `anomalies.parquet` / `anomaly_metrics.json` ->
dashboard Overview build chain. The browser-safe publication contains high and
critical rows only. Each row carries the observed Monday-starting week,
borough, precinct, offense, law category, observed aggregate count, selected
historical reference, signed positive residual, existing anomaly score, and
severity.

The anomaly decoder accepts only the exact Overview identity and row schema,
known dimensions and expectation sources, finite nonnegative counts/references
and scores, positive residuals that reconcile within the four-decimal
publication tolerance of `0.0001`, unique stable
logical identities, deterministic order, matching summary counts, aligned
scoring horizon, and the aggregate-only ethics flags. Contract-declared
`missing`, `invalid`, `stale`, and `incompatible` states remain distinct;
available-empty and filtered-empty are also separate. Unavailable or malformed
values are never converted to zero, while a documented reference value of zero
remains valid data and makes only the relative percentage unavailable.

The Forecast loader validates unknown JSON without coercion: exact identity and
schema, deterministic dates and one-week horizon, dimensions/indexes, stable
unique rows, location keys, borough assignments, arithmetic, summaries,
model/error alignment, baseline nullability, and privacy/ethics flags. Network
or malformed JSON errors are separate from contract-declared missing, invalid,
stale, and available-empty states; a valid zero is retained as data.

The independent precinct-spatial loader applies the same strict boundary to
the official 78-feature geometry contract. It validates exact application and
schema identity, official provenance and checksums, CRS and coordinate order,
finite eight-decimal NYC-plausible coordinates, MultiPolygon nesting, closed
nondegenerate nonzero-area rings, declared counts and bounds, lexical key ordering, complete
Forecast key reconciliation, and aggregate-safe privacy/responsible-use flags.
Missing, malformed, incomplete, duplicate, mismatched, or incompatible spatial
data receives a distinct neutral state; unavailable geography is never decoded
as an empty result.

Because the official dataset is quarterly, the runtime treats the artifact as
stale 120 calendar days after its recorded portal update unless a reviewed newer
edition is vendored. Stale geography is withheld while Forecast list/detail
values remain available.

The Map workspace offers **Hotspots**, **Forecast**, and **Expected change**.
Predictive rows are aggregated to one row per precinct after applying borough,
precinct, offense, and law filters. Baselines are summed only when every
contributing row has history; partial coverage is disclosed and aggregate
change is withheld. Historical Overview ranges that exclude the latest
complete source week show a neutral unsupported-date state. Older/newer safe
dates or observation horizons show explicit mismatch states.

Forecast and Expected change render official administrative MultiPolygon
boundaries from NYC Department of City Planning / NYC Open Data's May 2026 26B
**Police Precincts** dataset (`y76i-bdw7`). The spatial contract covers every
one of the 78 `nypd-precinct:<label>` Forecast keys exactly once and does not
reuse complaint-derived hotspot centroids. Polygon, list, and detail selection
share one state; the complete keyboard-accessible list/detail path remains
usable without touching the map and while raster tiles fail.

Forecast uses a sequential aggregate-volume scale with an explicit zero class
and four positive steps capped at the filtered 95th percentile. Expected change
uses a symmetric diverging domain based on the filtered 95th percentile of
absolute changes and the established `0.000001` approximately-equal tolerance.
Direction and exact values remain textually available. Missing or partial
baseline is never treated as zero: change is withheld and polygons use lower
fill opacity plus distinct dashed-outline semantics described in the legend.

The Phase 7A observed-count cube and core Overview metrics remain unchanged.
The Anomalies increment strengthens the optional anomaly family inside the
existing Overview schema, and Governance adds deterministic aggregate-quality
metadata to that same contract rather than creating another artifact. Phase 7B
uses a separate deterministic `map.json` contract so fixed-snapshot hotspot
semantics do not become entangled with the weekly observed-count cube. Leaflet
is loaded directly and lazily only after the user opens the Map view; no React
map wrapper is required.

## Interface hierarchy and visual system

The redesigned shell leads with active scope, geography, severity, change, and
the analytical result. Overview stays the default view: compact primary
metrics establish the current scope, then the weekly trend and geographic and
category comparisons receive the largest analytical surfaces. Map makes the
geographic canvas dominant, with the selected-signal detail and accessible
hotspot list presented as adjacent analytical panes. Anomalies uses a bounded
complete result register beside a synchronized detail pane so every published
signal remains available without a chart or map.

Repeated methodology and responsible-use copy was removed from the primary
filter-aware workspace. Phase names, raw source filenames, unrestricted
manifest fields, and development metadata are not rendered there. Overview's
initially collapsed **About the data** disclosure retains only coverage, quality
counts, forecast interpretation, and concise analytical limits. The dedicated
Governance view instead centralizes the allowlisted product-facing model
identity/version, artifact timestamp, readiness labels, quality warnings, and
limitations without repopulating Overview. The Map uses one similarly compact
**About hotspots** disclosure. Critical date semantics, stale or incompatible
data, historical-snapshot behavior, active filters, and data-quality warnings
remain visible when relevant. One persistent responsible-use boundary remains
in the shell.

The original civic visual system uses a near-black architectural field, cold
blue and ice-white analytical light, smoked-glass panes, dark-steel frames, and
subtle structural grid and scan-line texture. Amber is reserved for elevated or
high conditions, red for critical conditions, and gray-blue for historical or
reference values. Edge light, transparency, and depth are deliberately subdued;
there is no franchise imagery or copied entertainment interface.

The dark city basemap keeps moderate luminance and desaturation so roads,
shorelines, and place labels remain legible beneath the hotspot signals.

The presentation is CSS-only and uses centralized tokens. No UI, animation, or
other runtime dependency was added, and the existing lazy Map/Leaflet boundary
is retained.

### Responsive and accessible operation

- At desktop widths, charts and Map dominate while bounded secondary panes sit
  alongside them.
- At tablet widths, filters remain usable, the Map keeps a stable interaction
  area, and detail/list panes move below it without becoming compressed.
- On mobile, metrics and charts follow a single-column sequence; filters can be
  collapsed, and Map, detail, and list stack without page-level horizontal
  overflow.
- Native landmarks, headings, controls, lists, live status behavior, visible
  focus, keyboard list navigation, and accessible names are preserved.
- The Anomalies register uses native buttons with `aria-pressed`; visible
  selection, the polite live detail, and the deterministic first matching row
  share one selected identity. No custom keyboard handler is used.
- Governance uses native navigation and `details`/`summary`, semantic headings
  and description lists, visible textual status labels, long-value wrapping,
  and no global filter toolbar. Its four mobile navigation items form a readable
  two-by-two grid while preserving App-owned filter state for the return trip.
- Severity is encoded with text and shape as well as color. Touch controls use
  a 44 px minimum target.
- Translucent panes retain structural borders without blur, and a solid-color
  fallback is provided where transparency or `backdrop-filter` is unsupported.
- `prefers-reduced-motion` removes or simplifies depth and transition effects.

## Refresh dashboard data

From the repository root, use the project Python environment. There are two
different refresh scopes; do not use the projection-only sequence after an
upstream data or model change.

For a full analytical refresh, place the reviewed raw CSV at the documented
path and rebuild every dependency in order. The explicit as-of date reproduces
the currently published cleaning horizon:

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

Advance `--as-of-date` only as part of an intentional source refresh and record
the new review horizon. See the [root README](../README.md) and
[complaint-source provenance note](../data/source/nyc_open_data/nypd_complaint_data_historic.md)
for the raw snapshot checksum and exact-reproduction limitation.

When the cleaned aggregates, forecasts, hotspot/anomaly outputs, and model
manifests are already current and only the browser projections need to be
restaged, run only the dashboard builders:

```bash
.venv/bin/python src/analytics/build_dashboard_overview.py
.venv/bin/python src/analytics/build_dashboard_map.py
.venv/bin/python src/analytics/build_dashboard_forecast_map.py
.venv/bin/python src/analytics/build_dashboard_precinct_spatial_reference.py
```

If only anomaly analysis was intentionally regenerated, rebuild Overview after
`build_anomalies.py` so the published anomaly family and shared context agree.

The Forecast Map build writes byte-identical copies:

- `data/processed/dashboard_forecast_map.json` — canonical processed contract
- `dashboard/public/data/forecast-map.json` — staged frontend-safe copy

Pass `--skip-dashboard-copy` when only the canonical Forecast Map artifact
should be updated. The build consumes the validated weekly aggregate, Overview
date/filter context, ML predictions/metrics/manifest, and the selected baseline
predictions/manifest. It never modifies those source artifacts.

Forecast availability is explicit: `available`, `missing`, `invalid`, or
`stale`; an `available` artifact can also be genuinely empty. Missing, invalid,
or stale input is never represented as a valid zero forecast. The contract
publishes one next-week point-estimate horizon only. Its selected prior-only
trailing-eight-week baseline and expected-change fields are nullable where
history is insufficient, and change percentage remains null when the baseline
is zero. No prediction interval exists.

The spatial build consumes the unmodified official source and reviewed
provenance record in `data/source/nyc_open_data/`, then reconciles it against the
real Forecast Map artifact. It writes byte-identical canonical and browser
copies:

- `data/processed/dashboard_precinct_spatial_reference.json`
- `dashboard/public/data/precinct-spatial-reference.json`

The vendored source is NYC Open Data dataset `y76i-bdw7`, DCP edition 26B,
retrieved 2026-07-12 from the official bulk GeoJSON endpoint. Its SHA-256 is
`5210830afa9d0875b7a7c769edfc4d2ebe984a9ab1e36f3b7fad8508828172aa`.
The portal does not attach a named license; the reviewed public-use assessment
instead records NYC Open Data's no-use-restrictions statement and DCP's freely
available/no-fee metadata together with the City's informational/no-warranty
terms. See the adjacent provenance JSON and source README for exact URLs,
retrieval metadata, schema, CRS, checksum, and reproduction command.

The official GeoJSON export is already OGC:CRS84 longitude/latitude; repository
processing performs no reprojection and no simplification. Coordinates are
serialized to eight decimal places without removing vertices. Six- and
seven-decimal trials each collapsed a small authoritative ring, so eight is the
minimum verified precision that preserves every ring's closure and three
distinct non-closing vertices. Feature order, generation time, JSON encoding,
and copies are deterministic. Pass `--skip-dashboard-copy` when only the
canonical spatial artifact should be written. The current edition's runtime
refresh deadline is 2026-09-23T19:46:58Z, derived deterministically from the
recorded portal update plus the documented 120-day quarterly-source window.

The Map build writes:

- `data/processed/dashboard_map.json` — canonical processed contract
- `dashboard/public/data/map.json` — frontend-safe copy

The Overview build continues to write:

- `data/processed/dashboard_overview.json`
- `data/processed/dashboard_overview_cube.bin.gz`
- `dashboard/public/data/overview.json`
- `dashboard/public/data/overview-cube.bin.gz`

For Governance, the Overview build derives quality metadata directly from the
established cleaned complaint parquet and aggregate-safe weekly output. The
Forecast Map build projects only allowlisted lifecycle and historical-validation
metadata from the existing forecast, metrics, and manifest inputs. Neither
builder retrains a model. Do not hand-edit staged JSON, infer a missing training
timestamp, or substitute build time/current time for source-derived time. After
refreshing, verify byte equality between each canonical artifact and its public
copy before running the frontend checks.

`build_anomalies.py` deterministically derives aggregate-only
`data/processed/anomalies.parquet` and `anomaly_metrics.json` from the validated
weekly-area output and the established safe historical backtest predictions.
For each already-observed segment-week, the selected reference is the
leakage-safe model estimate when one exists; otherwise it is the prior-only
13-week mean. The candidate gate requires sufficient prior history and volume,
at least four observed events, and at least three events above expectation.
The Overview builder validates the source schema, arithmetic, flags, unique
keys, ordering, expectation-source reconciliation, and the companion metrics'
identity, configuration, leakage controls, counts, and horizon before
publishing. It regenerates the existing Overview artifacts; there is no
Anomalies-specific browser file.

Pass `--skip-dashboard-copy` to the Map build when only the canonical processed
artifact should be updated. Missing optional hotspot inputs produce an explicit
neutral status. Invalid, duplicate, mixed-date, future-dated, or more-than-one-
safe-data-day-old snapshots are withheld rather than converted to zeroes.
Missing or malformed `hotspot_metrics.json` affects methodology metadata only;
it does not invalidate an otherwise valid hotspot parquet file.

The Overview contract continues to represent optional hotspot, anomaly, and
forecast families with explicit availability states. Missing optional outputs
do not prevent observed trend analysis from loading. Unsafe optional numerics,
duplicate logical keys, mixed/future hotspot snapshots, and forecast artifacts
that do not align with their manifest are withheld rather than coerced. The
anomaly family additionally distinguishes stale source horizons and
incompatible methodology/identity from malformed input.

## Run locally

Use npm with a Node.js version accepted by the locked Vite toolchain:
`^20.19.0 || ^22.12.0 || >=24.0.0`. A clean checkout should use the lockfile:

```bash
cd dashboard
npm ci
npm run dev -- --port 4173 --strictPort
```

Open the URL printed by Vite. Overview is the default application view. Use
**Anomalies** for the observed-deviation register, or use **Map & hotspots** and
then choose **Forecast** or **Expected change** above the workspace. The
verified polygons load on first entry into a predictive mode.
Use **Governance** for dataset/model-wide coverage, quality, lifecycle,
readiness, and responsible-use information. Governance intentionally hides the
global filter toolbar; the selections remain preserved for the return to a
filter-aware view.
Use the shared filters and select a precinct through either its polygon or the
keyboard-operable list; both update the same detail and model context. The list
remains the complete non-map path. In Anomalies, select any native result button
to synchronize the visible selected row, `aria-pressed` state, and detail.
The verified development server for this redesign is
<http://127.0.0.1:4173/>.

## Verify

The current repository baseline is 212 Vitest tests across 15 files and 99
discovered Python contract tests. The named subsections below retain the exact
counts, bundle sizes, and practical results recorded at each milestone; older
totals are historical snapshots, not competing current baselines.

From the repository root:

```bash
.venv/bin/python -m unittest tests.test_anomaly_detection_contract
.venv/bin/python -m unittest tests.test_dashboard_overview_contract
.venv/bin/python -m unittest tests.test_dashboard_forecast_map_contract
.venv/bin/python -m unittest tests.test_dashboard_precinct_spatial_reference_contract
.venv/bin/python -m unittest tests/test_dashboard_map_contract.py
.venv/bin/python -m unittest discover -s tests -p 'test_*_contract.py'
```

From `dashboard/`:

```bash
npm run lint
npm test
npm run build
npm audit --omit=dev
npm run dev
```

Start the development server only for manual browser verification and stop it
when finished. Check desktop, tablet, and mobile widths. Exercise every filter,
reset, hotspot selection, keyboard list navigation, the historical-snapshot explanation, and
the missing/empty/error states; also check polygon/list/detail synchronization,
zero and partial-baseline presentation, overflow, focus visibility, reduced
motion, tile-failure resilience, map asset loading, and the browser console. For
Anomalies, also check signed deviation and direction text, reference-source and
severity agreement, native result selection, list/detail/`aria-pressed`
synchronization, source-empty versus filtered-empty, and valid-zero reference
presentation.
For Governance, check the exact event and bucket ranges, complete/partial-week
warning, source and aggregate-safe populations, overlapping issue disclosure,
retained `UNKNOWN` counts, model/training/artifact/forecast timestamp
distinctions, overall-versus-filter-specific validation wording, point-estimate
limitation, independent artifact statuses, responsible-use boundaries, native
disclosure, filter-state round trip, two-by-two mobile navigation, 44 px targets,
long-value wrapping, page overflow, console output, and observed required data
resources. Loading, invalid, incompatible, optional-unavailable, and retry states
also have focused automated coverage; do not create temporary production
switches merely to force a browser-visible delay or failure.

### Redesign verification

The current redesign passes ESLint, all 41 Vitest tests, the 59-test Python
contract suite, and the production build (2,353 modules in 543 ms). The
production dependency audit reports zero vulnerabilities. No dependency was added. Production bundle
comparison, uncompressed/gzip, is:

| Asset | Baseline | Redesigned |
| --- | ---: | ---: |
| Main CSS | 45.56 / 7.57 kB | 44.45 / 8.46 kB |
| Lazy Map JavaScript | 175.26 / 51.38 kB | 170.21 / 49.99 kB |
| Main JavaScript | 231.05 / 72.70 kB | 226.10 / 71.32 kB |
| Overview charts JavaScript | 405.05 / 113.79 kB | 404.27 / 113.51 kB |

Browser checks found zero horizontal overflow at 1440 × 1000, 820 × 1180,
and 390 × 844. Desktop rendered four real chart SVGs and a roughly 969 × 583
Map beside the detail/list panes. Tablet rendered a 762 × 450 Map with two
375 × 540 panes below it. Mobile rendered a 346 × 390 Map followed by a
348 × 420 detail pane and 348 × 500 hotspot list, with single-column metrics and
charts, collapsible filters, 44 px filter/zoom controls, and the persistent use
statement still visible.

The real 396-row hotspot contract, vector canvas, 360 grid and 36 precinct
layers, selection/detail flow, list keyboard path, all global filters,
borough-to-precinct constraint, reset, layer controls, historical behavior,
loading/error/missing/invalid/stale/mismatch/empty states, and both product-facing
data disclosures were exercised. All 20 observed tiles loaded. Composited small-text
contrast measured 5.93–6.30:1 and the warning notice measured 9.32:1. The
reduced-motion rule was confirmed in the loaded CSS, although the available
browser did not expose runtime media emulation. The temporary state harness
used to exercise non-default states was removed after verification.

A final targeted Map recheck confirmed that roads, shorelines, and place labels
remain legible beneath the hotspot layer. All six tiles visible in that viewport
loaded, the vector canvas remained present, horizontal overflow was zero, and
the browser console contained no warnings or errors.

The final product-copy pass was rechecked at 1280 × 720: four chart SVGs and all
15 visible Map tiles rendered, the vector canvas remained present, both concise
data disclosures opened correctly, horizontal overflow stayed at zero, and no
development metadata or browser warning/error remained.

### Anomalies increment verification

The current regenerated Overview contract publishes 10,378 deterministic high
and critical anomaly rows: 3,077 critical and 7,301 high. The default inclusive
complete-week range, 2024-12-30 through 2025-12-22, contains 645 rows: 175
critical and 470 high. The deterministic first row is the week of 2025-06-09,
Manhattan Precinct 5, `OFFENSES AGAINST PUBLIC ADMINI`, misdemeanor, with 31
observed aggregate events against a 3.0625 historical backtest estimate,
`+27.9375` signed deviation, and anomaly score 11.8988.

The final increment checks pass ESLint, all 147 Vitest tests in 12 files, the
2,363-module production build, the zero-vulnerability production dependency
audit, 64 focused anomaly/Overview/Map/Forecast Map/spatial Python tests, and all
92 discovered `test_*_contract.py` tests.
Decoder/filter-only coverage includes malformed identity/schema/dimensions,
duplicate or misordered rows, non-finite and inconsistent arithmetic,
summary/horizon disagreement, every availability state, filtering and stable
ordering, signed direction, analytical priority, valid-zero reference handling,
native selection and focus retention, Reset, borough/precinct constraints, and
responsive overflow rules.

The final production build reports these raw/gzip sizes:

| Asset | Size |
| --- | ---: |
| HTML | 0.64 / 0.36 kB |
| MapView CSS | 15.09 / 6.36 kB |
| Main CSS | 56.86 / 10.22 kB |
| JSX runtime | 9.25 / 3.50 kB |
| Lazy Anomalies JavaScript | 17.98 / 5.62 kB |
| Main JavaScript | 218.12 / 68.57 kB |
| Map JavaScript | 229.08 / 64.79 kB |
| Overview JavaScript | 404.31 / 113.53 kB |

Practical in-app browser verification at 1280 × 900, 768 × 1024, and
390 × 844 found zero page-level horizontal overflow. Mobile controls measured
44 px and anomaly result buttons at least 109.5 px. The real selected row,
visible selection, `aria-pressed`, polite live detail, reference, signed
deviation, direction, score, and severity agreed. Pointer activation of native
result buttons worked, and focused controls showed their visible focus state.

Shared categorical filtering produced 117 BRONX rows, 16 after choosing BRONX
Precinct 49, and six after also choosing Petit Larceny. A deliberately
mismatched law category exercised filtered-empty, and Reset restored all 645
default-range rows. A Sunday date value outside the Monday-based weekly
dimension was correctly rejected; valid date filtering is covered by the
automated suite. Overview retained five metrics, four chart SVGs, and its
attention table. Map regression checks retained all 396 Hotspots and opened
Forecast and Expected change successfully.

A deliberate global network failure produced the recoverable **Data
unavailable** state, and restarting the server restored the application. The
loading state completed too quickly for a defensible browser observation and is
therefore claimed only from automated coverage. Clean passes before and after
the recovery contained no console warnings or errors. The required
`overview.json`, Overview cube, Map, Forecast, and spatial assets were observed,
and no failed request surfaced in the clean session. No temporary production
fixture or state harness was added or left behind.

The installed in-app browser again focused the native anomaly result and showed
the visible focus ring, but it did not deliver genuine Tab/Enter/Space
activation to the application. No custom keyboard handler or alternate browser
surface was used. Native-button Enter/Space behavior and selection/detail
synchronization pass in Vitest. This recorded browser-channel limitation does
not change or close the separate Phase 7C.3 verification blocker below.

### Governance increment verification

The final Governance-focused frontend pass completed 88 tests in five files,
and the full dashboard pass completed all 212 Vitest tests in 15 files. The five
requested focused Overview, Forecast Map, cleaning, ML forecast, and baseline
forecast Python suites completed 59 tests; full contract discovery completed all
99 tests. ESLint, TypeScript compilation, the 2,365-module production build,
`git diff --check`, and the zero-vulnerability production audit passed.

The final build reports 39.61 / 10.26 kB for lazy Governance JavaScript,
66.39 / 11.33 kB for main CSS, 190.13 / 54.23 kB for lazy Map JavaScript,
219.61 / 68.81 kB for main JavaScript, and 404.31 / 113.53 kB for Overview
charts (raw/gzip). Canonical/public Overview JSON, Overview cube, Map, Forecast
Map, and precinct spatial artifacts are byte-identical.

Practical in-app browser verification at 1280 × 900, 768 × 1024, and
390 × 844 found zero page-level horizontal overflow, no clipped visible long
values, and no native target below 44 pixels. Mobile navigation rendered two
columns by two rows. The real coverage, complete/partial-week semantics,
source/aggregate-safe populations, overlapping issue flags, retained `UNKNOWN`
values, model identity/versions, unavailable independent training time,
artifact timestamp, fixed forecast horizon, overall validation context,
readiness labels, and responsible-use limits all rendered without a global
filter toolbar or raw/development metadata.

A Brooklyn / Precinct 60 / Burglary / Felony non-default filter round trip
returned unchanged. Switching to Bronx reset the precinct to the constrained
all-in-borough choice and removed Precinct 60; Reset restored the default scope.
Overview retained five metrics, four chart regions, and its concise disclosure;
Hotspots retained 396 rows; Forecast and Expected change retained 78 precincts;
and Anomalies retained 645 default rows with the deterministic first selection.
All five required browser data artifacts were observed, with no console warning,
console error, or failed required request in the clean session.

The Governance loading state was observed. Browser-visible network failure and
recovery were not forced because the allowed surface provides no safe request
interception and no temporary production harness was justified; those states
pass focused automated coverage. Pointer activation opened and collapsed the
native disclosure. The in-app browser showed the visible two-pixel focus ring
but again did not move focus on a genuine Tab request, and its Enter/Space
delivery could not maintain the focused summary target. No custom handler,
alternate browser, or synthetic event was used. This Governance browser-channel
limitation does not change or close the Phase 7C.3 blocker below.

### Phase 7C.3 verification

The final automated Phase 7C.3 pass builds all 78 real official MultiPolygon
features and 98,060 positions; passes the 19 Forecast Map and nine spatial
focused Python tests, all 87 Python contract tests, ESLint, all 92 Vitest tests,
the 2,359-module production build, the zero-vulnerability production audit, and
`git diff --check`. The canonical and public spatial JSON files are
byte-identical at 2,643,692 bytes with SHA-256
`ee23fc904a94c30515df0073ce8b1b3a5d6446292758928d057bcaa88c91edeb`.

The final build reports 229.04 / 64.78 kB for lazy Map JavaScript, 226.25 /
71.36 kB for main JavaScript, 404.27 / 113.51 kB for Overview JavaScript,
15.09 / 6.36 kB for Map CSS, and 48.66 / 9.21 kB for main CSS (raw/gzip).
Compared with Phase 7C.2, lazy Map JavaScript adds 40.57 / 10.32 kB while main
and Overview remain effectively unchanged.

Practical browser checks passed for the real Overview (five metric cards and
four chart SVGs), the 396-row Hotspots regression with 360 grid/36 precinct
layers, and Forecast/Expected change with all 78 precincts and exactly 12 under
BRONX. Direct polygon selection synchronized the polygon, list, and detail.
All categorical filters, Reset, an explicit empty-filter result, the valid-zero
fixture, the real `0.00102` fixture, Precinct 1 partial and missing baselines,
the historical state, and both older/newer date mismatches were exercised.

Missing, network, malformed, invalid, incomplete, key-mismatch, stale,
unsupported-version, and incompatible-identity spatial states all withheld
polygons while preserving the full 78-row list/detail path. A forced 20/20 tile
failure left all 78 vector polygons, filters, legend, list, and detail usable
and showed the expected notice. A fresh post-harness tab loaded all five data
artifacts and 20/20 CARTO tiles with no console warnings/errors. The temporary
harness was removed and the server was stopped.

At 1280 × 900, 768 × 1024, and 390 × 844 there was zero page horizontal
overflow, the map and stacked panes fit their layouts, and no visible native
control measured below 44 pixels. Mobile filters opened and closed normally.
The browser exposed no reduced-motion emulation; one loaded reduced-motion rule
and its Vitest contract were confirmed without claiming runtime emulation.

Phase 7C.3 remains verification-incomplete for one practical browser check.
The in-app browser focused the exact native precinct button and rendered the
visible 2-pixel focus ring, but its documented Tab/Enter/Space channels did not
dispatch activation, so the selected detail did not change. The native-button
keyboard test passes in Vitest, but policy was not bypassed through another
browser surface. A successful allowed practical keyboard activation is the
exact remaining gate.

## Map contract and filter semantics

`map.json` contains data-range metadata, sorted indexed local dimensions, a
compact array-row hotspot payload, methodology, coordinate/date semantics,
limitations, and an explicit privacy/ethics contract. The Map view uses the
existing Overview filter metadata for the shared borough-to-precinct
constraint. Each row provides only aggregate location context and defensible
source metrics:

- rank and hotspot grain
- borough and optional precinct
- offense type and law category
- aggregate map coordinate and location label
- recent count and optional normalized expected recent count
- optional lift percentage
- composite score, severity, and coordinate coverage

The common scoring date and 30-day recent/365-day baseline windows are stored
once in the snapshot summary. Numeric values are validated as finite and are
never silently clamped.

The global borough, precinct, offense, and law-category selections apply to
both screens. Borough changes constrain the precinct choices. Precinct-grain
rows are filterable by precinct; grid rows have no precinct assignment and are
therefore deliberately omitted whenever a precinct filter is active. The Map
layer control can otherwise show both grains, precinct only, or grid only.
Reset restores the same default current scope used by Overview.

Overview dates are inclusive Monday-based weekly buckets. Hotspots are not
historically recomputed in the browser: the current fixed snapshot is available
only when the selected weekly range includes the latest complete Overview week.
A historical selection displays a neutral explanation, not a fabricated zero.
Snapshots later than the aggregate-safe event maximum are invalid; snapshots
more than one safe-data day behind it are marked stale and their rows are not
published. The frontend also requires the declared snapshot age to equal the
calendar-day difference between the scoring and aggregate-safe end dates. The
UI requires the Map and Overview contracts to report the
same aggregate-safe end date. An older Map contract asks for a data refresh; a
newer one is treated as incompatible. Neither mismatch is rendered as current.

## Analytical and responsible-use boundaries

- Overview date controls select inclusive Monday-based weekly aggregate
  buckets.
- The Overview trend baseline for each week uses only its prior eight weeks;
  recent change compares up to four complete weeks with an equal prior window.
- Anomalies remain observed aggregate deviations from a documented expectation.
- The Anomalies view publishes high and critical rows only, using a safe
  historical-week backtest reference where available and the prior-only
  13-week mean otherwise. Its score and signal priority are not probabilities,
  policing priorities, or recommendations.
- Literal unavailable aggregate labels in the source are displayed as
  unavailable rather than inferred or remapped.
- Forecasts remain future model estimates shown only with aligned historical
  error context. Overall backtest errors are not recomputed for active filters,
  and the current model does not provide prediction intervals.
- The staged Forecast Map contract describes expected aggregate reported-event
  volume for the single week after its fixed source horizon. It does not predict
  individual behavior, identify a specific future incident location, score
  neighborhood danger, or recommend patrol or enforcement action.
- Source rows with unknown geography or borough/precinct combinations that do
  not match the established aggregate-derived canonical mapping are withheld
  and quantified; they are never silently remapped or combined.
- Hotspot precinct points are aggregate centroids, not precinct boundaries or
  exact event locations. Predictive modes use the separate official precinct
  boundary contract and never use those centroids.
- Grid points represent 0.01-degree cells; degree grids are not equal-area.
- Recent hotspot counts are compared with a 365-day historical rate normalized
  to the same 30-day duration when that reference is available.
- Severity and composite score describe aggregate concentration signals. They
  are not predictions of individual behavior and do not justify enforcement.
- The map does not expose complaint IDs, event records, names, race, sex, age
  groups, or victim/suspect demographics.
- Phase 7B does not add anomaly mapping, forecasts, uncertainty intervals,
  precinct boundaries, a standalone API, authentication, deployment, or live
  ingestion.
- Phase 7C.1 does not add Forecast UI, a frontend loader, a forecast map layer,
  grid forecasts, a new model, an API, deployment, authentication, or real-time
  inference. Those product integration steps begin with Phase 7C.2.
- Phase 7C.3 adds only verified precinct geography and rendering. It does not
  alter the Forecast model or artifacts, add event/person/address/demographic
  fields, infer centroids, fabricate geometry, add intervals, or recommend risk,
  patrol, or enforcement actions.
- CARTO/OpenStreetMap raster tiles provide geographic context, but aggregate
  markers/shapes and the adjacent list/detail remain usable independently of a
  tile-loading failure.

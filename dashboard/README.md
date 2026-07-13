# NYC Crime Intelligence Dashboard

Phases 7A, 7B, and 7C provide aggregate-only Overview, Hotspot, and Predictive
Map experiences:

- **Overview** remains the first screen and reads compact metadata plus the
  gzip-compressed weekly aggregate cube.
- **Map & hotspots** reads a separate compact hotspot snapshot and adds both a
  visual map and a keyboard-accessible aggregate hotspot list/detail view.
- **Predictive Map** strictly loads the browser-safe contract and adds Forecast
  and Expected change modes to the existing Map workspace.

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

The Phase 7A Overview contract and deterministic cube are unchanged. Phase 7B
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
hotspot list presented as adjacent analytical panes.

Repeated methodology and responsible-use copy was removed from the primary
workspace. Phase names, contract and artifact versions, source filenames,
generation timestamps, and readiness status are not rendered in the product UI.
An initially collapsed **About the data** disclosure retains only coverage,
quality counts, forecast interpretation, and concise analytical limits. The Map
uses one similarly compact **About hotspots** disclosure. Critical date
semantics, stale or incompatible data, historical-snapshot behavior, active
filters, and data-quality warnings remain visible when relevant. One persistent
responsible-use boundary remains in the shell.

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
- Severity is encoded with text and shape as well as color. Touch controls use
  a 44 px minimum target.
- Translucent panes retain structural borders without blur, and a solid-color
  fallback is provided where transparency or `backdrop-filter` is unsupported.
- `prefers-reduced-motion` removes or simplifies depth and transition effects.

## Refresh dashboard data

From the repository root, use the project Python environment. Refresh Overview
first so its shared date/filter context is current, then refresh Map and the
staged Forecast Map contract:

```bash
.venv/bin/python src/analytics/build_dashboard_overview.py
.venv/bin/python src/analytics/build_dashboard_map.py
.venv/bin/python src/analytics/build_dashboard_forecast_map.py
.venv/bin/python src/analytics/build_dashboard_precinct_spatial_reference.py
```

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
that do not align with their manifest are withheld rather than coerced.

## Run locally

```bash
cd dashboard
npm install
npm run dev
```

Open the URL printed by Vite. Overview is the default application view; use
**Map & hotspots**, then choose **Forecast** or **Expected change** above the
workspace. The verified polygons load on first entry into a predictive mode.
Use the shared filters and select a precinct through either its polygon or the
keyboard-operable list; both update the same detail and model context. The list
remains the complete non-map path.
The verified development server for this redesign is
<http://127.0.0.1:4173/>.

## Verify

From the repository root:

```bash
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
motion, tile-failure resilience, map asset loading, and the browser console.

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

Practical browser checks passed for the real Overview and 396-row Hotspots
regressions, Forecast and Expected change with all 78 precincts, categorical
filters, Reset, valid zero, partial baseline, the historical state, visible
focus, 20 loaded tiles, desktop/tablet overflow, and 44-pixel controls. The
browser security layer blocked further localhost interaction during the
390 × 844 switch. Mobile/state/tile-failure/reduced-motion/console behavior is
covered by automated tests but still needs a successful practical rerun before
the Phase 7C.3 verification gate can be called complete. The temporary server
was stopped. The later small-positive formatting, spatial-stale, and zero-area
ring hardening passes automated coverage but was not re-opened in that blocked
browser session.

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

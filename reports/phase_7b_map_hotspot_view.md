# Phase 7B — Map and Hotspot View

## Scope

Phase 7B extends the Phase 7A dashboard with a real **Map & hotspots** view and
navigation from Overview. Overview remains the first operational screen and its
weekly observed-count contract is unchanged. This phase does not implement
Trends, Forecast, Governance, authentication, deployment, a standalone API,
real-time ingestion, person-level scoring, or recommendations about patrol or
enforcement.

## Architecture

The implementation keeps observed history and fixed-snapshot hotspot signals as
two separate frontend contracts:

1. `src/analytics/build_dashboard_overview.py` continues to create the Phase 7A
   Overview metadata and compressed deterministic weekly cube.
2. `src/analytics/build_dashboard_map.py` uses DuckDB to validate the actual
   hotspot inputs and creates a separate compact, deterministic Map contract.
3. The Vite/React application loads Overview first. Map code and Leaflet are
   loaded lazily only when Map is opened. Leaflet is used directly, without the
   additional weight and abstraction of a React map wrapper.
4. Visual markers are complemented by a filterable, keyboard-accessible hotspot
   list and aggregate detail panel, so the map is not the only access path.

This separation preserves the efficient Phase 7A weekly cube and makes the
different time semantics explicit: Overview represents selectable historical
weeks; Map represents one validated hotspot scoring snapshot.

## Inspected input schemas and current data

The inputs were inspected directly with DuckDB before the Map contract was
designed.

### `hotspots.parquet`

The actual parquet schema has 40 fields. Its relevant groups are:

- Identity and grain: `rank_overall`, `rank_in_grain`, `hotspot_grain`,
  `borough`, `precinct`, `grid_latitude`, `grid_longitude`, `offense_type`, and
  `law_category`.
- Aggregate map context: `map_latitude`, `map_longitude`,
  `valid_coordinate_event_count`, and `coordinate_coverage_pct`.
- Snapshot/window context: `recent_window_days`, `baseline_window_days`, and
  `scoring_end_date`.
- Aggregate measures: 7-, 30-, and 90-day counts, `recent_event_count`,
  `baseline_event_count`, `baseline_expected_recent_count`, aggregate shares,
  `recent_baseline_ratio`, and `recent_vs_baseline_lift_pct`.
- Analytical signals: component scores, `composite_score`, volume/hotspot flags,
  and `hotspot_severity`.

The current source contains 396 unique logical records on one scoring date,
2025-12-30:

| Grain | Rows | Borough labels | Precincts | Severity distribution |
| --- | ---: | ---: | ---: | --- |
| Grid | 360 | 5 | Not applicable | 160 low, 176 medium, 21 high, 3 critical |
| Precinct | 36 | 4 | 27 | 20 low, 14 medium, 2 high, 0 critical |

Across both grains the source contains 21 offense types, all three law
categories, and all four severity levels. All 396 current map coordinates are
non-null and finite, and all 396 inspected logical keys are unique. The source
reports 30-day recent windows and 365-day baselines. Composite scores span
42.2076–83.2434 for precinct records and 43.2852–100 for grid records.

Precinct coordinates are six-decimal means of all valid-coordinate aggregate-
safe events in that borough/precinct through the scoring date. They are display
centroids, not precinct geometries. Grid coordinates are the centers of
0.01-degree cells. A grid row has no precinct; its borough is the dominant
borough label for that cell/offense/law segment, with deterministic lexical
tie-breaking in the Phase 6 pipeline.

### `hotspot_metrics.json`

The current metrics artifact identifies the Phase 6B hotspot method, the same
2025-12-30 scoring date, 30-day recent and 365-day baseline windows, a
0.01-degree grid, scoring thresholds, source/output columns, record and severity
counts, and deterministic run metadata. Map treats it as optional explanatory
metadata: its absence or malformation does not turn valid hotspot records into
invalid records.

### Aggregate-safe freshness source

`complaints_clean.parquet` contains event-level preparation fields, including a
complaint identifier that is never selected for the frontend contract. The Map
builder consults this source only through rows satisfying
`is_clean_event_for_aggregate = true` to establish aggregate-safe coverage and
freshness. The inspected safe population is 10,049,687 rows spanning 2006-01-01
through 2025-12-31. The current hotspot snapshot is therefore one safe-data day
behind the maximum and is eligible to display.

The Overview weekly aggregate remains 1,761,447 rows reconciling to the same
10,049,687 aggregate-safe events. Neither complaint-level table nor any event
row is sent to the browser.

## Input and output paths

Required for Map freshness validation:

- `data/processed/complaints_clean.parquet`

Optional analytical inputs:

- `data/processed/hotspots.parquet`
- `data/processed/hotspot_metrics.json`

Generated Map outputs:

- `data/processed/dashboard_map.json` — canonical processed contract
- `dashboard/public/data/map.json` — frontend-safe application copy

Existing Overview outputs remain unchanged:

- `data/processed/dashboard_overview.json`
- `data/processed/dashboard_overview_cube.bin.gz`
- `dashboard/public/data/overview.json`
- `dashboard/public/data/overview-cube.bin.gz`

Refresh Overview first and Map second:

```bash
.venv/bin/python src/analytics/build_dashboard_overview.py
.venv/bin/python src/analytics/build_dashboard_map.py
```

`build_dashboard_map.py --skip-dashboard-copy` updates only the canonical
processed Map output.

## Map contract

The compact JSON document has these top-level sections:

| Field | Purpose |
| --- | --- |
| `schemaVersion`, `generatedAtUtc` | Contract version and deterministic data-derived generation time |
| `application` | Product, phase, and view identity |
| `dataRange` | Aggregate-safe event dates and safe record count |
| `dimensions` | Sorted grains, boroughs, precincts, offenses, laws, and severities |
| `filterIndex` | Snapshot-local borough/precinct relationships for audit; the UI still uses Overview controls |
| `hotspots` | Status, reason, compact rows, shared summary, and source path |
| `methodology` | Optional hotspot window/grid/method metadata and its own availability status |
| `provenance` | Whitelisted source filenames and aggregate-safe selection rules |
| `filterSemantics`, `grainSemantics` | Explicit categorical and grid/precinct behavior |
| `coordinateSemantics` | Precinct-centroid and grid-cell coordinate meaning |
| `dateSemantics` | Fixed-snapshot versus weekly historical behavior |
| `limitations` | Visible analytical and geographic caveats |
| `ethics` | Machine-checked aggregate-only and no-recommendation assertions |

Hotspot records are positional arrays whose fields are declared by
`hotspots.rowColumns`:

```text
rank
grainIndex
boroughIndex
precinctIndex
offenseTypeIndex
lawCategoryIndex
latitude
longitude
locationLabel
recentCount
expectedRecentCount
liftPct
score
severityIndex
coordinateCoveragePct
```

Common values such as scoring date, snapshot age, current maximum age, recent
window, baseline window, grid size, and counts are stored once in
`hotspots.summary`. `expectedRecentCount` and `liftPct` may be null when the
source cannot defend them; the interface omits those metrics rather than
inventing them. Indexed dimensions and deterministic total ordering keep the
contract compact and byte-stable for identical inputs.

## Date and filter semantics

Overview continues to use inclusive Monday-based `week_start` filters. Map does
not rescore hotspots for an arbitrary historical range. Its fixed current
snapshot is shown only when the selected range includes the latest complete
Overview week. Moving the end date into history produces a neutral explanation
that the current snapshot is incompatible with the selection; it does not
present a zero count.

The Map shares the Overview borough, precinct, offense-type, law-category, date,
and reset state. Borough-to-precinct controls read the existing Overview
metadata. The Map contract also retains a snapshot-local index for validation
and provenance, but it does not replace the global control mapping:

- Borough selection constrains the precinct menu through the same deterministic
  borough/precinct relationship used by Overview.
- Changing borough clears an incompatible precinct.
- Offense and law filters apply identically to both grains.
- A selected precinct matches precinct-grain records only. Grid rows have no
  precinct assignment and are explicitly omitted from precinct-filtered results.
- The layer control supports both grains, precinct only, and grid only whenever
  the current filters support them.
- Reset restores the Phase 7A default scope and current-date window.
- Stable dimensions are retained while filters change so the map and detail
  region do not collapse or jump.
- Map and Overview must report the same aggregate-safe end date. An older Map
  contract is neutrally withheld with a refresh instruction; a newer Map
  contract is incompatible with the older Overview context. Neither mismatch is
  shown as a current snapshot.

## Hotspot grain semantics

**Precinct grain** is one aggregate borough/precinct/offense/law signal placed
at the precinct's valid-coordinate event centroid. The point does not assert
that the underlying signal occurred at that exact coordinate and does not show
the legal precinct outline.

**Grid grain** is one aggregate offense/law signal for a 0.01-degree cell placed
at its cell center. A cell has a dominant borough label but no precinct key.
Degree-based cells vary in physical area and can cross administrative
boundaries, so grid and precinct scores should not be treated as interchangeable
area-normalized rates.

## Missing, invalid, mixed, future, and stale inputs

Availability is explicit and rows are never silently coerced:

| Input condition | Map status and behavior |
| --- | --- |
| Hotspot parquet absent | `missing`; empty rows and a neutral explanation |
| Valid parquet with zero rows | `available`; genuine empty state |
| Metrics JSON absent | Hotspots remain usable; methodology is `missing` |
| Metrics JSON malformed | Hotspots remain usable; methodology is `invalid` |
| Malformed/unsafe hotspot schema or value | `invalid`; rows withheld |
| Null/non-finite/out-of-range required numeric | `invalid`; no clamping |
| Duplicate logical hotspot key or rank | `invalid`; rows withheld |
| More than one scoring date | `invalid`; mixed snapshots are not merged |
| Snapshot after safe event maximum | `invalid`; future-dated rows withheld |
| Snapshot zero or one safe-data day old | Eligible as current |
| Snapshot more than one safe-data day old | `stale`; rows withheld with reason |

Even when the data-build status is `available`, the frontend performs the
additional Map/Overview safe-end-date compatibility check described above.
It also rejects an available snapshot when its declared age contradicts the
calendar-day difference between `scoringEndDate` and the aggregate-safe end
date, preventing stale data from being mislabeled as current.

Logical-key uniqueness includes grain, aggregate location context, borough,
precinct where applicable, offense, law category, and snapshot identity. Sorted
dimensions and row ordering make repeated valid builds deterministic.

## Information hierarchy and progressive disclosure

The interface was simplified before the visual restyle. The primary workspace
now leads with active scope, geography, severity, change, and the analytical
result. Repeated ethics language, methodology paragraphs, provenance detail,
contract and artifact status, filenames, section kickers, and implementation-
oriented helper copy were removed or consolidated. State messaging now uses a
clear title and one short action or explanation while preserving necessary
historical, stale, missing, invalid, mismatch, empty, loading, and error
distinctions.

Overview remains the first operational view. Compact metrics establish scope,
but the weekly trend and geographic/category comparisons carry the strongest
visual hierarchy. Map makes the geographic surface dominant and places the
selected aggregate signal and keyboard-accessible hotspot list in adjacent bounded
panes. Active filter state, freshness, critical date semantics, and relevant
data-quality warnings stay in the main flow.

Phase names, contract and artifact versions, provenance filenames, generation
timestamps, and source-readiness status were removed from the product UI rather
than relocated. An initially collapsed native **About the data** disclosure now
contains only coverage, quality counts, forecast interpretation, and three
concise analytical limits. The selected Map detail uses one compact **About
hotspots** disclosure for the baseline period, area-level location meaning, and
score interpretation. A single short responsible-use statement remains in the
shell.

## Nocturnal civic visual system

Centralized tokens now define a near-black architectural field, cold
desaturated blue and ice-white analytical light, smoked-glass surfaces,
dark-steel structural frames, fine edge illumination, and subtle grid/scan-line
texture. Gray-blue distinguishes historical and reference values; amber is
reserved for elevated/high conditions and restrained red for critical
conditions. Transparency, blur, reflection, and depth remain low-intensity so
the screen reads as one continuous operational environment rather than a grid
of conventional cards.

The CARTO dark basemap now retains moderate luminance with controlled
desaturation. Roads, shorelines, and place labels stay legible beneath the
aggregate hotspot layer without competing with signal markers.

The visual language is an original NYC civic intelligence treatment. It uses no
franchise marks, characters, silhouettes, props, copied production design, or
entertainment branding. It also avoids purple dominance, rainbow effects,
glitch animation, excessive bloom, and decorative motion. Structural gradients
are used sparingly rather than as a default surface treatment.

Implementation remains CSS-only on the existing React/Vite structure. No UI
framework, animation library, or other dependency was added. The Map and
Leaflet stay behind the existing lazy-loading boundary.

## Accessibility and responsive behavior

- Overview/Map navigation uses native buttons and an accessible current-page
  state.
- The map region, hotspot results, status text, and detail panel have semantic
  headings/regions; loading and selection changes use appropriate status text.
- Every hotspot is available through a keyboard-accessible list/table; visual
  markers are an additional representation.
- The selected detail exposes recent/expected/difference metrics, signal score,
  and text severity. The snapshot date and layer are shown once in the Map
  header, while concise interpretation lives in **About hotspots**.
- Icon-only actions and map controls have accessible names and unfamiliar
  interactions have explanatory text/tooltips.
- Severity is expressed by label and shape/icon treatment, not color alone.
- A text-labeled low/medium/high/critical key accompanies the map.
- Visible focus treatment uses the centralized focus token.
- Filter, navigation, disclosure, hotspot-list, and zoom controls maintain
  comfortable 44 px touch targets where applicable.
- Desktop uses a dense command-center composition with dominant charts/Map and
  adjacent bounded panes. Tablet keeps the Map interaction area wide and moves
  detail/list panes below it. Mobile uses a deliberate single-column
  sequence with collapsible filters, primary metrics and Map before secondary
  context, and no overlapping controls.
- Map/detail heights remain stable across filter transitions, internal scrolling
  is bounded where needed, and page-level horizontal overflow is avoided.
- The interface does not require blur to understand boundaries: translucent
  panes retain borders, and solid-color fallbacks cover unsupported transparency
  or `backdrop-filter`.
- `prefers-reduced-motion` removes nonessential depth and transition effects.
- Loading, error, source-missing, valid-empty, stale, and historical-selection
  states have explicit non-map alternatives.

## Data-quality limitations

- Hotspots describe aggregate concentration in reported complaint data, not
  confirmed causality, future individual behavior, or risk posed by a person.
- Reporting delays, revisions, under-reporting, historical classification
  changes, and cleaning exclusions can affect counts and scores.
- Precinct markers are event-coordinate centroids, not precinct boundaries,
  population-normalized rates, or exact complaint locations.
- Grid cells are 0.01 degrees and not equal-area; the dominant borough label can
  simplify a cell that intersects more than one administrative area.
- Phase 7B includes points/aggregate shapes, not authoritative precinct boundary
  polygons.
- The current map has no anomaly overlay, forecast layer, uncertainty interval,
  or causal explanation for a score.
- A fixed snapshot cannot answer historical-map questions. Historical date
  selection is therefore withheld rather than approximated.
- External CARTO/OpenStreetMap raster availability can affect geographic
  context. Leaflet vector markers/shapes render independently of tile success,
  and the aggregate list/detail remains the non-map access path.

## Ethics and privacy safeguards

Only aggregate-safe analytical records are published. Event-level data is
consulted only with `is_clean_event_for_aggregate = true` for safe coverage and
freshness checks. The frontend outputs exclude complaint IDs, source row IDs,
event records, names, race, sex, age groups, victim demographics, and suspect
demographics.

The interface calls hotspots **aggregate signals**. It does not characterize a
place or population as criminal, predict individual behavior, or imply that a
hotspot justifies enforcement or patrol action. The contract includes explicit
false flags for event-record inclusion, demographic inclusion, person-level
scoring, patrol recommendations, and enforcement recommendations.

## Known limitations

- Map state is client-side and is not represented as a shareable URL route.
- The snapshot is local/static until the data-build commands are run again.
- No standalone API, server-side spatial query, offline basemap bundle, or live
  update channel is included.
- Precinct polygons, equal-area spatial indexing, anomaly mapping, historical
  hotspot snapshots, and uncertainty presentation are not part of this focused
  interface redesign.

## Verification

### Automated verification

- The real Map build published 396 rows with `available` status.
- Canonical and frontend outputs are byte-identical at 46,835 bytes, with
  SHA-256 `669ce7600094056c697cd751eeeb9305768e51ae0570435ac7c05ea14f7bd7ef`.
- Focused Map data-contract tests passed 12/12.
- The full practical Python contract suite passed 59/59.
- Frontend ESLint passed; Vitest passed 41/41 tests.
- The strict TypeScript and Vite production build passed, processing 2,353
  modules in 543 ms.
- The real generated contract passed the frontend loader integration test with
  360 grid and 36 precinct records.
- Static responsive tests verify tablet stacking and mobile single-column map,
  detail, list, and layer-control rules. `git diff --check` passed.
- Runtime dependencies reported zero production audit vulnerabilities.

No dependency was added. The Map/Leaflet lazy boundary remains intact, and the
production bundle comparison is:

| Asset | Phase 7B baseline, raw/gzip | Redesigned, raw/gzip |
| --- | ---: | ---: |
| Main CSS | 45.56 / 7.57 kB | 44.45 / 8.46 kB |
| Lazy Map JavaScript | 175.26 / 51.38 kB | 170.21 / 49.99 kB |
| Main JavaScript | 231.05 / 72.70 kB | 226.10 / 71.32 kB |
| Overview charts JavaScript | 405.05 / 113.79 kB | 404.27 / 113.51 kB |

Removing dead scope, measure-key, provenance, and detail-context styles brought
the main stylesheet below the raw Phase 7B baseline. All JavaScript chunks also
remain below their baselines.

### Browser verification

The verified local development URL is <http://127.0.0.1:4173/>.

- **Desktop, 1440 × 1000:** zero horizontal overflow; four real chart SVGs;
  a roughly 969 × 583 real Map with adjacent detail/list panes; a real
  vector canvas; all 20 observed raster tiles loaded.
- **Tablet, 820 × 1180:** zero horizontal overflow; a 762 × 450 Map; 375 × 540
  detail and hotspot-list panes positioned side-by-side below it.
- **Mobile, 390 × 844:** zero horizontal overflow; collapsed and expanded
  filter states; 44 px filter and zoom controls; a 346 × 390 Map followed by a
  348 × 420 detail pane and 348 × 500 hotspot list; single-column metrics/charts;
  the persistent responsible-use statement remains visible.

Overview was the initial view. Overview-to-Map navigation, all borough,
precinct, offense, law, start-date, end-date, and reset controls, the
borough-to-precinct constraint, both layer controls (360 grid and 36 precinct),
real hotspot selection/detail, keyboard list navigation, focus ring,
historical selection, and loading/error/missing/invalid/stale/mismatch/empty
states were exercised. The initially collapsed and expanded **About the data**
and **About hotspots** disclosures were also checked. Severity remained identified
by text and shape rather than color alone.

Composited small-text contrast checks measured 5.93–6.30:1; the warning notice
measured 9.32:1. The reduced-motion rule was verified statically and in the
loaded CSS, but the available browser did not provide runtime media emulation.
The temporary state harness used to exercise non-default states was removed
after verification.

A final targeted Map recheck confirmed that roads, shorelines, and place labels
remain legible beneath the hotspot layer. All six tiles visible in that viewport
loaded, the vector canvas remained present, horizontal overflow was zero, and
the browser console contained no warnings or errors.

The final product-copy pass was rechecked at 1280 × 720. Four chart SVGs, all 15
visible Map tiles, and the vector canvas rendered; both concise disclosures
opened; horizontal overflow remained zero; and a full page-text scan found no
phase, contract, artifact, manifest, filename, readiness, or generation-status
language. The browser console contained no warnings or errors.

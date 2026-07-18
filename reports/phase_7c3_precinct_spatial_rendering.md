# Phase 7C.3 — Verified Precinct Spatial Reference and Rendering

## Status

The implementation is code-complete. The authoritative source, deterministic
builder, Python and browser runtime contracts, and Forecast/Expected Change
polygon rendering are in place, and every required automated verification
command passes. The practical rerun completed desktop, tablet, mobile, state,
tile-failure, precision, responsive, console, and network checks. The remaining
blocker is native keyboard activation in the in-app browser. In a fresh
1280 x 900 session, Forecast started on Precinct 75 with exactly 78 polygons
and 78 native list buttons. The semantic Playwright key channel focused
Precinct 14 for Enter and Precinct 40 for Space and rendered the expected
2-pixel outline with 3-pixel offset, but both buttons remained
`aria-pressed="false"`; the pressed list row and detail remained Precinct 75.
CUA and DOM-CUA Enter/Space produced the same non-dispatch result. Tab and
Shift+Tab also left focus on the Forecast mode button, and the advertised
visibility capability did not present a visible webview. Expected Change
repeated the same focused-but-not-activated result on Precinct 14 while its
Precinct 75 detail and textual below-baseline semantics remained unchanged. No
alternate browser surface, raw CDP, CLI automation, synthetic state mutation,
or direct event dispatch was used. The milestone therefore remains
verification-incomplete until that final keyboard check succeeds in an allowed
browser session.

## Initial repository audit

Before implementation, the complete roadmap and every applicable Phase 7B,
7C.1, and 7C.2 report, dashboard README, Forecast Map builder and Python tests,
frontend Forecast contracts/loaders/filters, Map and Hotspot components,
Vitest coverage, responsive/accessibility checks, style tokens, and the lazy
Leaflet boundary were reviewed. The worktree started clean at Phase 7C.2 commit
`04a06ad`; no applicable repository `AGENTS.md` was present.

The real Forecast Map artifact—not the roadmap prose—was used as the join
authority. It contains 78 unique labels and 78 unique keys using
`nypd-precinct:<source precinct label>`. Repository-wide spatial search found
no existing complete, authoritative precinct boundary artifact:

- the Phase 7B hotspot contract contains only 27 locations and its centroids
  are derived from event coordinates;
- `dashboard_summary.json` contains 78 centroid values built from complaint
  latitude/longitude averages; and
- neither source is a verified administrative boundary or acceptable input for
  a future-facing map.

Those artifacts were explicitly rejected. No event coordinate, complaint
coordinate, inferred centroid, or fabricated geometry is used in Phase 7C.3.
An alternate official feature-service endpoint was also rejected after it
returned only 77 precincts and omitted precinct 123. The reproducible NYC Open
Data GeoJSON export described below contains all 78 reviewed features.

Pre-edit verification passed: all 78 Python contract tests, dashboard lint, all
52 dashboard tests, the production build, and the production dependency audit.

## Authoritative source and public-use assessment

The selected source is the official New York City Department of City Planning
(DCP) **Police Precincts**, edition 26B, data date May 2026, available through
NYC Open Data. DCP identifies the dataset as quarterly. The reviewed source was
selected for this implementation and directly describes NYPD precinct
administrative boundaries.

| Field | Verified value |
| --- | --- |
| Publisher | New York City Department of City Planning (DCP) |
| Dataset | Police Precincts, edition 26B |
| NYC Open Data identifier | `y76i-bdw7` |
| Official dataset page | <https://data.cityofnewyork.us/City-Government/Police-Precincts/y76i-bdw7> |
| Official DCP page | <https://www.nyc.gov/content/planning/pages/resources/datasets/police-precincts> |
| Metadata API | <https://data.cityofnewyork.us/api/views/y76i-bdw7> |
| DCP metadata | <https://s-media.nyc.gov/agencies/dcp/assets/files/pdf/data-tools/bytes/nypp_metadata.pdf> |
| GeoJSON retrieval URL | <https://data.cityofnewyork.us/api/geospatial/y76i-bdw7?method=export&format=GeoJSON> |
| Retrieval UTC | `2026-07-12T18:35:09Z` |
| Portal rows updated UTC | `2026-05-26T19:46:58Z` |
| Original filename | `Police Precincts.geojson` |
| Vendored filename | `police_precincts_y76i-bdw7_26b.geojson` |
| Source size | 3,842,773 bytes (1,388,135 bytes with local gzip) |
| Source SHA-256 | `5210830afa9d0875b7a7c769edfc4d2ebe984a9ab1e36f3b7fad8508828172aa` |

The same retrieval was repeated and produced byte-identical source bytes. The
exact command, URL, timestamp, filename, checksum, and verification procedure
are recorded beside the vendored source.

The portal does not assign a named dataset-specific license, so the repository
does not invent one. NYC Open Data states that Open Data has no use
restrictions, and the DCP metadata states that the dataset is freely available
to the public with no fee. NYC and DCP also disclaim warranties of
completeness, accuracy, content, and fitness for a particular use. On that
documented basis the source is assessed as **license-compatible public data**,
not as data under an unverified named license. The reviewed terms and FAQ are
recorded at <https://opendata.cityofnewyork.us/overview/> and
<https://opendata.cityofnewyork.us/faq/>.

## Source schema and coordinate reference

The official download is a GeoJSON `FeatureCollection` with 78 features. Every
feature is a `MultiPolygon`. Its only properties are `precinct`, `shape_area`,
and `shape_leng`; it contains no complaint, event, address, person, or
demographic record.

DCP documents the native dataset as **EPSG:2263**, NAD83 / New York Long Island
(US survey feet). NYC Open Data's GeoJSON export supplies coordinates as
**OGC:CRS84**, longitude then latitude. Repository processing performs no
reprojection. The browser-safe artifact records both references, the axis order,
and the measured output bounds:

`[-74.25559136, 40.49613399, -73.70000906, 40.91553278]`.

These bounds are plausible for New York City and keep the axes unambiguous.

## Exact Forecast reconciliation

The builder reads the actual Forecast Map contract and derives its expected
labels and keys. It joins the authoritative `precinct` property by exact string
identity to `nypd-precinct:<source precinct label>`. The reconciliation is:

- 78 Forecast keys;
- 78 source precinct identifiers;
- 78 browser-safe spatial features;
- zero missing Forecast keys;
- zero unexpected spatial keys;
- zero duplicate or ambiguous identifiers; and
- exactly one verified `MultiPolygon` per included Forecast precinct.

No identifier is hardcoded from the milestone prompt. No precinct is renamed,
merged, split, dropped, substituted, or invented, and no reviewed exception map
was necessary. Features are written in deterministic lexical `locationKey`
order. The output contains 235 polygons, 236 rings, and 98,060 positions.

## Deterministic vendoring and processing

`build_dashboard_precinct_spatial_reference.py` accepts only the vendored
edition-26B source, its exact provenance record, and the compatible Forecast
Map contract. It verifies the reviewed source and provenance checksums and
schemas before geometry processing. Generation never reads the wall clock:
`generatedAtUtc` is the reviewed source retrieval timestamp.

The canonical output is UTF-8 JSON with recursively sorted object keys, compact
separators, finite JSON numbers, and one trailing newline. Features are ordered
lexically by location key. The processed copy and the public dashboard copy are
both 2,643,692 bytes with SHA-256
`ee23fc904a94c30515df0073ce8b1b3a5d6446292758928d057bcaa88c91edeb` and are
byte-identical. A local gzip of the browser artifact is 771,936 bytes.

GeoJSON was retained instead of adding a TopoJSON runtime dependency or a
topology-changing conversion. No geometry simplification or vertex removal is
applied: source and output both contain 98,060 positions. Coordinates are
rounded deterministically to eight decimal places. Precision trials were part
of the validation decision: six decimals collapsed a small ring in precinct
106, and seven decimals still collapsed a ring in precinct 63. Eight decimals
was the minimum fixed precision that preserved closure and at least three
distinct non-closing vertices in every ring. This saves bytes through canonical
number formatting while avoiding the visibly and structurally incorrect ring
loss observed at lower precision.

## Builder validation and output contract

The Python builder fails closed on malformed JSON, duplicate object keys,
non-finite values, source/provenance/checksum drift, an unreviewed public-use
assessment, source schema drift, unexpected properties, and an incompatible
Forecast contract. Geometry validation requires:

- exact `FeatureCollection`/`Feature`/`MultiPolygon` schemas;
- nonempty polygons and rings;
- at least four positions, three distinct non-closing positions, and nonzero
  translated-origin shoelace area per ring;
- exact ring closure;
- finite longitude/latitude pairs at the declared eight-decimal precision;
- coordinates inside deliberately broad NYC-plausible bounds;
- unique, safe, exact precinct labels and location keys;
- deterministic ordering and canonical JSON;
- exact declared feature, polygon, ring, position, and bounds summaries;
- complete 78-key Forecast reconciliation; and
- byte-identical processed and dashboard copies.

Forbidden-field checks reject event, complaint, person, victim, suspect,
address, demographic, latitude/longitude, patrol, and enforcement-like
properties. Source shape metrics are reviewed but are not included because
the frontend does not need them.

The compact browser contract contains only identity/version metadata,
provenance and public-use metadata, coordinate-reference/conversion semantics,
location-key semantics, coverage/processing summaries, privacy and
responsible-use flags, limitations, precinct label/key, and `MultiPolygon`
geometry.

## Runtime contract and loader

`precinctSpatialReference.ts` defines the frontend contract and
`loadPrecinctSpatialReference.ts` fetches
`/data/precinct-spatial-reference.json` with `cache: 'no-cache'`. The loader
decodes from `unknown`; it does not coerce strings, fabricate defaults, discard
unknown fields, or turn a bad value into an empty collection.

Runtime validation covers the exact top-level and nested schemas; application,
view, and supported schema identities; source and provenance byte sizes and
checksums; official URLs and coordinate references; finite eight-decimal
coordinates; polygon nesting, closure, and distinct vertices; bounds and
declared geometry counts; unique keys; stable ordering; safe/privacy flags; and
forbidden fields. Ring area is computed exactly on eight-decimal scaled integer
coordinates so the legitimate tiny precinct 63 ring is not lost to floating
cancellation. It then reconciles the spatial features against the loaded
Forecast Map contract and requires exact schema compatibility and all 78 keys.

The official source declares a quarterly update frequency. The loader applies a
documented 120-calendar-day refresh window from `portalRowsUpdatedAtUtc`; the
reviewed edition remains accepted through `2026-09-23T19:46:58Z` and then raises
the distinct `stale` state unless a reviewed newer edition is vendored.

Distinct errors are retained for missing artifact, network failure, stale
source edition, malformed JSON, unsupported version, incompatible identity,
invalid provenance, invalid coordinate reference, invalid contract, invalid
geometry, duplicate keys, unstable ordering, incomplete coverage, key mismatch, and Forecast
incompatibility. Existing Overview, Hotspot, and Forecast loaders are not
weakened.

## Forecast and Expected Change rendering

The existing Map workspace and lazy Leaflet boundary are preserved. Hotspots
continues to use its retrospective map, layers, point/list behavior, and loader.
Forecast and Expected Change load the new spatial contract only when a
predictive mode is requested. They draw the official administrative boundary
for every filtered precinct result; they do not create event markers or use
centroids.

Polygon, precinct-list, and detail selection share the same location key.
Clicking a polygon selects the existing detail. Selecting a precinct with the
keyboard-accessible list highlights the same polygon and detail. A filter/reset
that changes the result key set performs a nonanimated safe `fitBounds`;
selection and mode changes restyle in place and do not repeatedly move the
viewport. Exact values always remain in the list and detail, so the map is not
required to understand or operate the result.

Forecast uses a sequential aggregate-volume scale computed deterministically
from the active filtered precinct aggregates. A linearly interpolated 95th
percentile of positive predictions is divided into four equal positive steps;
values above the cap retain their exact text value and share the darkest step.
This limits extreme-value compression without clipping or changing displayed
numbers. A valid zero has a separate style and explicit “valid zero forecast”
semantics. Predictive legends, tooltips, list rows, and details preserve up to
the contract's six decimal places, so a real `0.00102` positive forecast cannot
be displayed as `0.0` or confused with the valid-zero class.

Expected Change uses a diverging scale centered on zero. Its symmetric domain
is the positive and negative linearly interpolated 95th percentile of absolute,
complete-baseline, non-neutral changes, divided into three magnitude steps on
each side. The existing six-decimal (`0.000001`) arithmetic tolerance defines
“approximately equal.” Text labels always state **above**, **below**,
**approximately equal**, or **unavailable**.

Incomplete baselines are never treated as zero. Partial coverage uses a
distinct long-dash border, lower fill opacity, and coverage text. Missing
coverage uses a distinct short-dash border, still lower fill opacity, and
“baseline missing” text. Other unavailable coverage has its own dash semantics.
These differences are explained by the accessible legend and tooltips, so
Expected Change meaning is not encoded by color alone.

## Accessibility, responsiveness, and tile resilience

The complete native-button precinct list remains the primary keyboard path and
retains 44-pixel targets, synchronized mouse selection, complete values, and a
visible 2-pixel focus outline with 3-pixel offset. The map is a named region
with mode-specific accessible labeling and an associated textual description;
zoom controls have predictive-map names. Legends expose scale method,
direction, zero, and unavailable-baseline semantics in text. Loading, error,
neutral, historical, and tile states are announced with the existing status
patterns.

The predictive workspace uses the established desktop/tablet/mobile stacking
rules, minimum touch targets, overflow protections, and reduced-motion rules.
At the 1280 × 900 override, the rendered Forecast map measured 853 × 586.125 pixels,
reported 78 features, loaded all 20 visible tiles, had zero page-level
horizontal overflow, and exposed no visible native control below 44 pixels. At
768 × 1024, the map measured 693 × 467.25 pixels; the 341.5 × 540 detail and
list panes sat side by side below it, all 78 rows remained usable, overflow was
zero, and the minimum visible native-control height was 44 pixels. At the
390 × 844 override (375 × 844 document client area after the vertical
scrollbar), the map measured 331 × 460 pixels, followed by a 333 × 420 detail
and 333 × 500 list. The filter disclosure opened and closed, every visible
control remained at least 44 pixels high, text remained separated, and page
horizontal overflow was zero.

The browser advertised viewport and visibility capabilities but no
reduced-motion emulation. Runtime `matchMedia` therefore remained false; the
loaded page contained one `prefers-reduced-motion: reduce` rule and the
responsive Vitest contract verifies its motion removal. No unsupported runtime
emulation claim is made.

The practical keyboard channel remains the only blocked release check. At
1280 x 900, the exact native Forecast button named `Select precinct 14,
232.6625 expected aggregate reported events` received semantic Playwright
Enter focus, and `Select precinct 40, 216.2125 expected aggregate reported
events` received semantic Playwright Space focus. Each displayed the solid
2-pixel focus outline with 3-pixel offset, but each remained
`aria-pressed="false"`; the selected row, Precinct 75 detail, and shared polygon
selection did not change. CUA and DOM-CUA Enter/Space also left Precinct 75
selected. Semantic Playwright and CUA Tab/Shift+Tab attempts from the focused
Forecast mode button did not advance focus. Expected Change likewise focused
the exact native `Select precinct 14, below baseline, -23.0875` button on
Enter, but retained the selected `Select precinct 75, below baseline,
-23.0375` row and Precinct 75 detail. The in-app browser's supported visibility
request still reported false. Native-button keyboard activation continues to
pass the Vitest integration test; this run does not substitute that automated
evidence for the missing practical activation.

CARTO raster tiles are an optional backdrop. A tile failure produces a visible
notice but does not remove official vector polygons, filters, legends, the
keyboard list, or detail values. The implementation makes no geographic value
dependent on raster-tile success.

## Explicit state behavior

Unavailable geography is never converted into empty or zero data. The
predictive list and detail remain usable while the map surface reports a
specific spatial state for loader/network failure, missing artifact, stale
source edition, malformed or invalid contract, incomplete precinct coverage,
location-key mismatch, unsupported identity/version, invalid
provenance/CRS/geometry, and Forecast incompatibility.

Forecast states remain separate for missing, invalid, stale, and empty
artifacts; valid zero totals; no rows under active filters; unsupported
historical selection; Overview older than Forecast; Overview newer than
Forecast; and missing, partial, or invalid historical baseline/error context.
The spatial contract is version-coupled to Forecast Map schema 1.0.0, view
identity, key scheme, and exact key set. It intentionally has no Forecast safe
date: precinct boundary edition/date and Forecast observation date are
independent concepts. Boundary staleness is instead exposed through DCP edition
26B, data date 2026-05, quarterly frequency, and the artifact limitations;
Forecast/Overview safe-date mismatches continue to use their existing explicit
states.

## Privacy and responsible use

Both the provenance record and output contract assert that the source is
administrative boundary geometry suitable for aggregate public visualization.
The builder and runtime contract enforce that the browser-safe artifact contains:

- no complaint or event records;
- no event-level coordinates or inferred centroids;
- no person, victim, suspect, address, or demographic records;
- no source shape metrics;
- no forecast values or prediction intervals; and
- no patrol, enforcement, danger, or risk classification.

UI copy describes expected aggregate reported-event counts and administrative
precinct boundaries. It does not describe a precise future incident location,
certainty, neighborhood danger, patrol priority, or enforcement target. The
forecasting model and its inputs/outputs are unchanged.

## Files created or changed

Authoritative source and deterministic build:

- `data/source/nyc_open_data/police_precincts_y76i-bdw7_26b.geojson`
- `data/source/nyc_open_data/police_precincts_y76i-bdw7_26b.provenance.json`
- `data/source/nyc_open_data/README.md`
- `src/analytics/build_dashboard_precinct_spatial_reference.py`
- `data/processed/dashboard_precinct_spatial_reference.json`
- `dashboard/public/data/precinct-spatial-reference.json`
- `tests/test_dashboard_precinct_spatial_reference_contract.py`

Frontend contract, scales, and map:

- `dashboard/src/types/precinctSpatialReference.ts`
- `dashboard/src/data/loadPrecinctSpatialReference.ts`
- `dashboard/src/data/loadPrecinctSpatialReference.test.ts`
- `dashboard/src/components/precinctForecastScale.ts`
- `dashboard/src/components/PrecinctForecastMap.tsx`
- `dashboard/src/components/PrecinctForecastMap.test.ts`
- `dashboard/src/components/PrecinctForecastMap.render.test.tsx`

Integration and regression coverage:

- `dashboard/src/types/forecastMap.ts`
- `dashboard/src/data/loadForecastMap.ts`
- `dashboard/src/data/loadForecastMap.test.ts`
- `dashboard/src/components/MapView.tsx`
- `dashboard/src/components/MapView.test.tsx`
- `dashboard/src/App.tsx`
- `dashboard/src/styles/tokens.css`
- `dashboard/src/styles/app.css`
- `dashboard/src/styles/mapResponsive.test.ts`

Documentation:

- `Roadmap.md`
- `dashboard/README.md`
- `reports/phase_7c2_predictive_map_ui.md`
- `reports/phase_7c3_precinct_spatial_rendering.md`

## Verification status

Final automated verification passed:

- fresh real-source spatial build: 78 official MultiPolygon features and
  98,060 positions;
- focused Forecast Map Python contract: 19/19;
- focused precinct spatial Python contract: 9/9;
- all Python `test_*_contract.py` suites: 87/87;
- processed and public spatial artifacts: byte-identical with the declared
  SHA-256;
- ESLint: passed;
- full Vitest: 8 files and 92/92 tests;
- TypeScript plus Vite production build: passed, 2,359 modules;
- production dependency audit: zero vulnerabilities; and
- `git diff --check`: passed.

Focused Vitest coverage includes 12 spatial-loader tests, eight predictive
scale/render tests, and 32 Map workspace tests for spatial failures, Forecast
states, list/polygon/detail synchronization, keyboard selection, legends,
baseline states, date mismatches, responsive rules, and tile failure.

Practical browser verification used the real rendered application and semantic
locators. Overview rendered five metric cards and four chart SVGs with no
loading/error state or page overflow. Hotspots loaded all 396 real rows, its
360-grid/36-precinct layer counts, vector canvas, 20/20 visible raster tiles,
layer controls, list, and detail. Mouse list selection updated the Hotspot
detail.

Forecast rendered exactly 78 polygons and 78 list rows at the default scope;
BRONX rendered exactly 12 of each. A direct canvas-polygon click changed the
shared polygon/list/detail selection to Precinct 48. Borough, precinct, offense,
and law filters all operated; Reset restored 78, and a MANHATTAN/ABORTION scope
showed an explicit zero-result message, zero polygons, and “No precinct
selected,” not a zero forecast.

The BRONX / Precinct 40 / AGRICULTURE & MRKTS LAW-UNCLASSIFIED /
MISDEMEANOR fixture displayed a valid `0.0`, “approximately equal,” and “Not
defined for a zero baseline.” The BROOKLYN / Precinct 66 / UNLAWFUL POSS. WEAP.
ON SCHOOL / VIOLATION fixture displayed `0.00102` and `+0.00102`; its Forecast
legend used distinct `0.000255`, `0.00051`, and `0.000765` boundaries rather
than repeated zero labels. Precinct 1 showed a real 72/73 partial baseline at
the aggregate scope and a 0/1 missing baseline for CHILD ABANDONMENT/NON
SUPPORT 1 / FELONY. Both withheld change and used distinct long-dash/short-dash
polygon rendering plus explicit partial/missing text.

The end week `2025-12-15` withheld the fixed future forecast. A temporary
development-only harness also verified Forecast-newer and Overview-newer
mismatch copy, then was removed. The same removed harness exercised missing,
network, malformed, invalid, incomplete coverage, location-key mismatch,
stale, unsupported-version, and incompatible-identity spatial states. Every
state withheld polygons while preserving all 78 list rows and detail values.

A forced 20/20 raster-tile failure produced the visible tile notice while all
78 vector polygons, filters, legend, list, and detail remained usable. A fresh
post-harness tab then loaded all five required data artifacts and 20/20 CARTO
tiles, showed zero horizontal overflow, and produced no console warnings or
errors, including no React key/state-update, Leaflet, or accessibility warning.
The state and tile harnesses were removed before final verification, and the
temporary Vite server was stopped.

Still pending before milestone completion is one successful practical native
keyboard activation through an allowed in-app browser session. At 1280 x 900,
the current browser focused Precinct 14 for Enter and Precinct 40 for Space but
left `aria-pressed`, the Precinct 75 detail, and shared polygon selection
unchanged. Expected Change repeated the Precinct 14 Enter attempt with the same
result. The Playwright, CUA, and DOM-CUA key channels were tried; policy was not
bypassed through another surface.

## Artifact and production bundle impact

| Asset | Raw | Gzip/local gzip |
| --- | ---: | ---: |
| Vendored official GeoJSON | 3,842,773 bytes | 1,388,135 bytes |
| Processed/public spatial JSON | 2,643,692 bytes | 771,936 bytes |
| Final lazy Map JavaScript | 229.04 kB | 64.78 kB |
| Main JavaScript | 226.25 kB | 71.36 kB |
| Overview JavaScript | 404.27 kB | 113.51 kB |
| Final Map CSS chunk | 15.09 kB | 6.36 kB |
| Main CSS | 48.66 kB | 9.21 kB |

Compared with Phase 7C.2, the lazy Map JavaScript increased from 188.47 kB /
54.46 kB gzip by approximately 40.57 kB / 10.32 kB gzip. Main JavaScript moved
only about 0.10 kB / 0.02 kB gzip, and Overview remained unchanged. This keeps
Leaflet and predictive geometry rendering behind the Map lazy boundary. The
2.64 MB spatial JSON is fetched with `no-cache` only when a predictive map mode
needs it; the 3.84 MB authoritative source is not shipped by the dashboard.
These figures are from the final successful production rebuild.

## Known limitations and remaining work

- The official boundaries are edition 26B with a May 2026 data date. The
  browser withholds them as stale after the documented 120-day quarterly-source
  window; a reviewed revendor/rebuild is required by 2026-09-23T19:46:58Z.
- The portal supplies no named dataset-specific license. The public-use
  assessment is based on official NYC Open Data and DCP terms and is recorded
  without claiming a license name.
- Preserving every authoritative vertex makes the frontend artifact 2.64 MB
  raw. No simplification or topology conversion was accepted for this
  milestone; a future size optimization would need measured topology/error
  validation and the same exact 78-key/privacy gates.
- Validators enforce exact nesting, closure, distinct vertices, finite bounds,
  and nonzero area, but do not repair or simplify source topology. A future
  topology/simplicity audit must preserve the authoritative 78-feature result
  and the tiny valid rings.
- Raster tiles depend on an external service and can fail, although the vector
  geography and accessible values remain available.
- The underlying Forecast Map still represents one fixed next-week horizon,
  has partial baseline coverage in some filters, exposes overall rather than
  filter-specific historical errors, and supplies no prediction interval.
- Administrative polygons communicate aggregate precinct membership only; they
  do not locate a future event or indicate risk, danger, patrol priority, or
  enforcement need.
- A successful practical native-button Enter/Space activation in an allowed
  browser session remains before the milestone can be marked complete. At
  1280 x 900, the current in-app browser focused the exact Precinct 14 and
  Precinct 40 targets and showed visible focus, but Playwright, CUA, and DOM-CUA
  did not dispatch activation; no alternate surface was used.

No model, API, authentication, deployment, real-time inference, event-level
geography, commit, or push is part of this work.

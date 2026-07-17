# Phase 7C.2 — Predictive Map UI & Integration

## Audit and decision

The complete roadmap, Phase 7A/7B/7C.1 reports, builder, Python contract tests,
dashboard documentation, existing loaders/components/tests/styles, and both
Forecast Map copies were inspected before editing. The real contract contains
the single 2026-01-05 horizon after the 2025-12-29 observation horizon, 5,852
published rows from 8,466 source rows, 78 precincts, five boroughs, 75 offense
labels, three law categories, partial trailing-eight-week baselines, and aligned
overall backtest errors. It contains no coordinates, geometry, or intervals.

Repository search found no complete verified aggregate-safe precinct geometry
or centroid source. The 27-precinct hotspot centroid subset was not reused.
Forecast and Expected change therefore display an explicit spatial-reference-
unavailable canvas and provide the full result through the precinct list and
detail. Future rendering requires a reproducibly vendored, license-compatible,
aggregate-safe spatial artifact covering all 78 opaque precinct keys.

## Runtime contract and semantics

`types/forecastMap.ts` defines the strict contract. `loadForecastMap.ts` fetches
`/data/forecast-map.json` with `cache: 'no-cache'` and validates from unknown:
exact identity/version/top-level shape, deterministic UTC/date compatibility,
one next-week horizon, dimensions and filter indexes, exact rows, finite and
nonnegative values, ordering/uniqueness, borough/location-key consistency,
baseline nullability/change arithmetic at 0.000001 tolerance, summary and
coverage reconciliation, model/error alignment, point-estimate-only status,
spatial limitations, and safe privacy/ethics assertions. It does not mutate or
coerce the decoded input.

Categorical filters match labels across independent Overview and Forecast
indexes. The primary result is one row per precinct. Predicted values sum. A
baseline is aggregated only when every contributing row has a defensible
baseline; partial coverage is shown and change is withheld. Percent change is
shown only for a positive complete baseline. A valid zero remains distinct from
missing, invalid, stale, empty, and filter-empty states.

The fixed forecast is compatible only when Overview and Forecast safe dates and
observation horizons align and the selected Overview range includes the latest
complete source week. Historical selections and older/newer contracts receive
separate neutral explanations.

## UX, accessibility, and responsibility

The existing Map workspace now has Hotspots, Forecast, and Expected change mode
buttons. Hotspots retains its prior map/layer/list behavior. Forecast presents
expected aggregate reported-event counts; Expected change presents signed
above/below/approximately-equal text and values, never color alone. All matching
precincts are native buttons with visible focus and synchronized detail state.
The responsive layout stacks the neutral canvas, detail, and scrollable list at
tablet/mobile breakpoints and inherits reduced-motion and 44px target rules.

Details show forecast week, prediction, baseline, signed count/percentage,
baseline coverage, model name/version, overall MAE/RMSE/weighted MAE and
historical coverage. Copy explicitly states errors are overall backtest context,
not filter-specific uncertainty, and that no prediction interval is available.
It does not imply certainty, specific incidents, person-level behavior,
neighborhood danger, patrol priority, or enforcement action.

## Files changed

- `dashboard/src/types/forecastMap.ts`
- `dashboard/src/data/loadForecastMap.ts` and test
- `dashboard/src/data/filterForecastMap.ts`
- `dashboard/src/components/MapView.tsx` and test
- `dashboard/src/App.tsx`
- `dashboard/src/styles/app.css`
- `dashboard/README.md`, `Roadmap.md`, and this report

## Verification, bundle, and limitations

Pre-edit checks passed: 19 Forecast Map Python tests and 41 dashboard tests.
Final verification passed:

- focused Python Forecast Map contract: 19/19;
- all Python contract suites: 78/78;
- ESLint: passed;
- Vitest: 5 files and 52/52 tests;
- TypeScript and Vite production build: passed, 2,356 modules;
- production dependency audit: zero vulnerabilities;
- `git diff --check`: passed.

Practical browser verification used the real Overview, Map, and Forecast
artifacts. Overview charts/metrics and the 396-row Hotspots map/list rendered.
Forecast rendered the honest neutral canvas plus all 78 precinct list entries.
The Bronx filter produced 12 precincts, Expected change supplied signed direction
text, keyboard focus/selection and Reset worked, and a historical end week showed
the unsupported-date state. At 1280 desktop, 820 × 1180 tablet, and 390 × 844
mobile widths there was zero page horizontal overflow; mobile mode targets were
44px and the canvas/detail were 333px wide. The browser console had no warnings
or errors. The temporary Vite server was stopped.

Current clarification: the phrase “keyboard focus/selection” above records the
Phase 7C.2 report's original conclusion, but it is not evidence of a successful
native Tab/Shift+Tab/Enter/Space activation. Later allowed-browser checks could
focus a native precinct control and show its focus ring but could not deliver
activation to the application. The exact remaining gate is documented in the
[Phase 7C.3 report](phase_7c3_precinct_spatial_rendering.md), and Phase 7C.3
remains verification-incomplete. This clarification does not close or weaken
that blocker.

The predictive implementation adds no dependency. The lazy Map JavaScript is
188.47 kB / 54.46 kB gzip, about +18.26 / +4.47 kB versus the documented Phase
7B baseline. Main JavaScript remains 226.15 / 71.34 kB gzip and Overview charts
remain 404.27 / 113.51 kB gzip; the predictive logic stays in the lazy Map
boundary.

Known limitations remain: one fixed next-week precinct horizon; partial latest
source week and baseline coverage; overall rather than filter-specific errors;
no interval; withheld noncanonical geography; and no predictive polygons or
markers until the complete spatial prerequisite exists. These are explicit UI
states, not silently filled gaps.

## Phase 7C.3 resolution

The spatial limitation recorded above was accurate for the Phase 7C.2 commit
`04a06ad` and remains part of that milestone's audit history. Phase 7C.3 now
resolves it with the reproducibly vendored NYC Department of City Planning / NYC
Open Data Police Precincts dataset `y76i-bdw7`, edition 26B (May 2026). The
official geometry reconciles exactly to all 78 Forecast location keys and is
published through a separately validated browser contract. Forecast and
Expected change now render verified administrative precinct MultiPolygons while
retaining the full keyboard-accessible list/detail experience and explicit
missing, invalid, incomplete, and mismatch states. See the
[Phase 7C.3 report](phase_7c3_precinct_spatial_rendering.md) for provenance,
public-use assessment, processing, rendering semantics, safeguards, and
verification.

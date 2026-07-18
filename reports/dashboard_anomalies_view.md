# Dashboard Anomalies View

## Status and scope

The dedicated **Anomalies** experience is implemented against the existing
aggregate anomaly definition. It shows unusually high weekly aggregate
increases that have already been observed, together with area, offense, law
category, date, observed value, documented historical expectation, signed
deviation, anomaly score, and analytical signal priority.

This increment does not change the forecasting model, its inputs, or its
outputs. It does not introduce an Anomalies-specific browser artifact, a new
scoring definition, person-level data, complaint identifiers, exact addresses,
event coordinates, inferred geometry, prediction intervals, risk labels,
patrol recommendations, or enforcement recommendations.

The initial repository audit found the requested state exactly:

- HEAD `459d95c35075618a77adb858d79426da6c5319da` on `main`, subject
  `Expand keyboard activation test documentation`;
- clean worktree and index, empty unstaged and staged diffs, and clean
  `git diff --check`;
- no listener on port 4173; and
- no applicable repository `AGENTS.md` outside dependency-owned content.

No initial-state discrepancy was present. Existing work and the separate Phase
7C.3 verification-incomplete browser blocker were preserved.

## Authoritative data chain

The screen reuses the established analytical chain:

```text
data/processed/crime_weekly_area.parquet
  -> src/analytics/build_anomalies.py
  -> data/processed/anomalies.parquet
  +  data/processed/anomaly_metrics.json
  -> src/analytics/build_dashboard_overview.py
  -> data/processed/dashboard_overview.json
  -> dashboard/public/data/overview.json
```

`dashboard/public/data/overview.json` is the existing frontend-safe metadata
contract. The dedicated view decodes its `signals.anomalies` section; it does
not fetch or stage `anomalies.parquet` in the browser. The weekly Overview cube
continues to contain observed aggregate history and is not duplicated for this
screen.

The underlying Phase 6A anomaly source contains 89,362 unique flagged
segment-weeks over the evaluated 2006-03-27 through 2025-12-22 range:

| Severity | Source rows |
| --- | ---: |
| Low | 53,301 |
| Medium | 25,683 |
| High | 7,301 |
| Critical | 3,077 |

The browser-safe projection intentionally contains the 10,378 high and critical
rows only. It does not recalculate or relabel lower-severity records in the
frontend. The default inclusive complete-week scope, 2024-12-30 through
2025-12-22, contains 645 browser rows: 175 critical and 470 high.

The source can carry its established literal `UNKNOWN` aggregate dimension
label. The reviewed high/critical projection contains eight rows with an
unknown borough label and five with an unknown offense label. The interface
renders those labels as `Unknown / not reported`; it does not infer, remap, or
fabricate the missing dimension.

## Expectation and signal semantics

Every anomaly refers to an already-observed Monday-starting aggregate week for
one borough, precinct, offense-type, and law-category segment.

The established calculation is:

- use the leakage-safe historical-week model estimate when a safe Phase 5
  backtest value exists;
- otherwise use the mean of the prior 13 weekly counts;
- compute `residual_count = actual_crime_count - expected_count`; and
- retain the existing composite `anomaly_score` and documented severity from
  the analytical artifact.

All historical rolling windows stop before the target week. Random splitting
is disabled. The latest potentially partial source week is excluded from
scoring. Forecast rows for a future week are not used as historical anomaly
references.

The candidate gate requires sufficient prior history and recent volume, at
least 13 prior events across the 13-week reference window, at least four
observed events in the target week, and at least three events above expectation.
The established **high** rule additionally requires at least six events of
historical-or-ML residual evidence and at least one of its documented
standardized, robust, scaled-ML, percentage-change, or score gates. The
**critical** rule requires at least 10 observed events, at least eight events of
that residual evidence, and a stricter standardized, robust, scaled-ML, or
score gate. The exact thresholds remain recorded in `anomaly_metrics.json` and
`reports/anomaly_methodology.md`; the dashboard does not recalculate them.

The composite score incorporates established deviation evidence; it is not a
probability or an event count. High and critical labels are exposed as **High
signal priority** and **Critical signal priority**. They indicate analytical
deviation strength, not offense seriousness, neighborhood risk, policing
priority, or a recommendation for action.

These semantics distinguish the screen from all adjacent products:

| Experience | Time and analytical meaning |
| --- | --- |
| Anomalies | Already-observed weekly aggregate increase against a prior-only or safe historical-week expectation |
| Hotspots | Reviewed fixed-snapshot aggregate concentration over documented recent and baseline windows |
| Forecast | Future one-week model point estimate |
| Expected change | Future Forecast point estimate minus its trailing historical baseline |

No prediction interval is added because neither the anomaly source nor the
forecast model provides one.

## Build and runtime contract hardening

`src/analytics/build_dashboard_overview.py` now fails closed before writing
anomalies. It verifies:

- exact required parquet source types and nonblank logical key dimensions;
- valid Monday dates inside the established analysis horizon;
- finite nonnegative observed, expectation, and score values;
- positive high/critical residuals;
- source-level `actual - expected = residual` within the existing `0.000001`
  tolerance;
- known expectation sources and severity values;
- reference/source consistency with the stored ML or prior-13-week value;
- anomaly flags, unique logical keys, and deterministic ordering; and
- companion metrics identity, required source/output columns, documented
  historical method, prior-only leakage controls, generation timestamp,
  analysis horizon, record counts, and all four severity totals.

The metrics scoring end must align with the Overview latest complete week. A
source horizon behind it is `stale`; incompatible identity/configuration is
`incompatible`; malformed content or internal disagreement is `invalid`; and
missing inputs remain `missing`. Rows and aggregate counts are withheld for
every unavailable state. Staleness is based on the documented source horizon,
not the viewer's wall clock.

An available anomaly section contains exact compact row columns and a summary
containing row count, high count, critical count, `isEmpty`, and
`scoringEndWeek`. Regenerating Overview through the established builder updated
the existing canonical and public Overview JSON; no parallel data contract was
introduced.

The TypeScript decoder independently validates unknown runtime input. It
requires the exact Overview application/schema/dashboard identity, aggregate-
only ethics flags, exact row width and columns, valid unique dimensions and
indexes, known expectation sources, high/critical severities only, Monday
weeks, finite values, arithmetic reconciliation, unique stable identities,
deterministic source order, exact summary shape and counts, and aligned scoring
horizon. The browser reconciles independently rounded four-decimal projection
values within `0.0001`, the strict tolerance supported by that encoding. It
preserves a valid zero historical reference and marks only the relative
percentage unavailable when division by that zero would be undefined.
It never turns absent, non-finite, negative, duplicate, malformed, stale, or
incompatible input into valid zero data.

## User experience

The application shell now exposes a lazy-loaded **Anomalies** navigation view
beside Overview and Map & hotspots. The shared Overview metadata, global filter
state, and Reset action remain owned by the application, so moving between
screens does not create a parallel filter interpretation.

The screen provides:

- an explicit introduction describing observed aggregate deviations and their
  distinction from Hotspots, Forecast, Expected change, and individual
  behavior;
- filtered result, critical, and high counters;
- a bounded complete ordered list of every matching browser record;
- a synchronized detail showing the week, borough and precinct, offense, law
  category, observed aggregate value, named expectation source and value,
  signed deviation, relative deviation when defined, direction text, anomaly
  score, and analytical priority; and
- an expandable methodology disclosure covering expectation selection,
  candidate gates, ordering, interpretation, limitations, and responsible-use
  boundaries.

The deterministic ranking is critical first, then high, descending score,
newest week, and stable aggregate identity tie-breakers. A row identity is the
encoded week/borough/precinct/offense/law tuple. The first matching row is
selected deterministically. A user's selection survives filter changes while
the row remains present; if a filter removes it, selection falls back to the
new deterministic first row. Reset clears the prior selection and restores the
default filter scope.

For the default real data, the first row is:

| Field | Value |
| --- | --- |
| Week | 2025-06-09 |
| Area | Manhattan, Precinct 5 |
| Offense | `OFFENSES AGAINST PUBLIC ADMINI` |
| Law category | Misdemeanor |
| Observed aggregate | 31 |
| Reference | Historical backtest estimate, 3.0625 |
| Signed deviation | +27.9375, above expectation |
| Score | 11.8988 |
| Priority | Critical signal priority |

## Global filters

The established shared filters apply inclusively to anomaly rows:

- start and end dates select Monday-based observed weekly buckets;
- borough matches the aggregate borough in the contract;
- precinct matches the aggregate precinct in the contract;
- offense matches offense type; and
- law category matches the law category in the contract.

Borough changes reuse the Overview borough-to-precinct index and clear an
incompatible precinct. Reset restores 2024-12-30 through 2025-12-22 and all
categorical dimensions. No browser-side imputation broadens a match.

Practical categorical filtering returned 117 BRONX rows, 16 after choosing
BRONX Precinct 49, and six after also selecting Petit Larceny. Combining that
scope with a law category absent from the result exercised filtered-empty.
Reset restored all 645 default rows. An attempted Sunday date outside the
Monday week dimension was correctly rejected by the established controlled
date semantics; valid inclusive date filtering is covered by automated tests.

## Accessibility and selection synchronization

The non-chart path is the complete experience, not a summary of a visual-only
surface:

- every result is a native `button` inside a semantic ordered list;
- each button has an explicit accessible selection label and `aria-pressed`;
- selected styling, `aria-pressed`, result identity, and the polite live detail
  derive from the same state;
- headings, landmarks, status/alert roles, filter labels, and native controls
  remain semantic;
- direction and severity use text and icons/borders in addition to color;
- focus-visible styling remains explicit; and
- interactive targets meet the 44 px minimum where applicable.

No custom keydown, roving-tabindex, or synthetic activation handler was added.
Native button Enter and Space behavior, focus retention, filter fallback, and
list/detail/accessibility synchronization pass in automated browser-DOM tests.

The permitted in-app browser focused the exact native result and displayed the
visible focus ring, but it again did not deliver genuine Tab/Enter/Space
activation events to the application. Another browser surface, script-dispatched
events, JavaScript `focus()`/`click()`, or direct state mutation was not used as
a substitute. This is recorded as a browser-channel limitation, with automated
native-control regression coverage; it does not modify or close the separate
Phase 7C.3 keyboard blocker.

## Explicit state behavior

| State | Visible behavior |
| --- | --- |
| Lazy loading / Overview loading | Stable loading status; no result or zero is implied |
| Network / top-level load error | Recoverable Data unavailable state and existing Reload action |
| Missing anomaly source or companion metrics | Missing message; no rows or counts |
| Invalid anomaly source/metrics | Alert explaining validation failure; no coercion |
| Stale anomaly horizon | Refresh instruction; stale rows withheld |
| Incompatible identity/horizon | Incompatible alert; rows withheld |
| Available and empty | Source-empty explanation, distinct from a numeric zero |
| Available but filters match none | Filtered-empty explanation and Reset path |
| Valid zero reference | Reference displays `valid zero`; relative deviation is unavailable rather than infinite or zero |

A deliberate global network interruption exercised the recoverable error state;
restarting the development server restored the real data. The loading state was
too fast for a defensible screenshot or semantic observation and is claimed
from automated coverage only. Missing, malformed, invalid, stale,
incompatible, source-empty, filtered-empty, and valid-zero branches have
focused automated coverage without temporary production code.

## Responsive behavior

The desktop layout presents the bounded list and detail side by side. Tablet
and mobile stack those panes while retaining the complete list in its own
bounded scrolling region. Mobile detail metrics become a single column, and
the shared filters retain their disclosure behavior.

Practical checks at the required viewports found:

| Viewport | Result |
| --- | --- |
| 1280 × 900 | Two-pane analytical workspace, no page-level horizontal overflow |
| 768 × 1024 | Stacked list/detail workspace, no page-level horizontal overflow |
| 390 × 844 | Single-column details, 44 px controls, result buttons at least 109.5 px, no page-level horizontal overflow |

The result region may scroll internally by design; the document does not
overflow horizontally.

## Regression checks

The practical browser session also confirmed that this navigation and shared
state change did not replace or weaken existing experiences:

- Overview retained five real metric cards, four rendered chart SVGs, and the
  attention table;
- Map & hotspots retained the real 396-row Hotspots contract; and
- Forecast and Expected change modes opened and retained their existing
  controls and aggregate detail behavior.

Clean browser passes before and after the deliberate network interruption had
no console warnings or errors. The Overview metadata/cube, Map, Forecast, and
spatial artifacts were observed, and the clean recovered session surfaced no
failed request. No temporary fixture or state harness was added or left behind.

## Final automated verification

The completed checks are:

- focused anomaly/Overview/Map/Forecast Map/spatial Python tests: 64 passed;
- full `test_*_contract.py` Python discovery: 92 passed;
- decoder/filter-focused Vitest coverage: 39 passed;
- combined Anomalies/App/responsive focused Vitest coverage: 65 passed;
- complete frontend Vitest suite: 147 passed in 12 test files;
- ESLint: passed;
- production Vite build: passed, 2,363 modules transformed;
- production dependency audit: zero vulnerabilities; and
- `git diff --check`: passed after documentation updates.

The production build reported:

| Asset | Raw | Gzip |
| --- | ---: | ---: |
| `index.html` | 0.64 kB | 0.36 kB |
| MapView CSS | 15.09 kB | 6.36 kB |
| Main CSS | 56.86 kB | 10.22 kB |
| JSX runtime | 9.25 kB | 3.50 kB |
| Lazy Anomalies JavaScript | 17.98 kB | 5.62 kB |
| Main JavaScript | 218.12 kB | 68.57 kB |
| Map JavaScript | 229.08 kB | 64.79 kB |
| Overview JavaScript | 404.31 kB | 113.53 kB |

## Refresh and operation

After refreshing the validated weekly aggregate and established analytical
inputs, regenerate in this order from the repository root:

```bash
.venv/bin/python src/analytics/build_anomalies.py
.venv/bin/python src/analytics/build_dashboard_overview.py
```

The first command refreshes the authoritative anomaly parquet and metrics. The
second performs the stricter reconciliation and refreshes the existing Overview
canonical/browser artifacts. Map and Predictive Map refresh commands remain
unchanged and independent.

Run the interface from `dashboard/`:

```bash
npm run dev -- --port 4173 --strictPort
```

Use the **Anomalies** shell navigation item. Stop the development server after
practical verification.

## Genuine limitations and responsible-use boundary

- Anomalies identify unusual aggregate increases; they do not explain cause.
- Reported complaint totals are affected by reporting delays, revisions,
  classification changes, and changes in reporting behavior.
- The reviewed method does not model holidays, special events, reporting lag, or
  spatial spillover and does not provide an uncertainty interval.
- A safe historical backtest reference exists only for the historical weeks
  represented by the established model output; otherwise the prior-only
  13-week mean is used and labeled.
- The screen contains only high and critical signals. It is not a complete
  browser copy of all low/medium analytical rows.
- Analytical priority is not policing priority, offense severity, a causal
  finding, or justification for patrol, investigation, enforcement, or action
  against a person or community.
- Aggregate area labels can be literal `UNKNOWN` in the source and are displayed
  as `Unknown / not reported` rather than inferred.
- The in-app browser's genuine Tab/Enter/Space delivery remains unavailable for
  practical activation verification. Native semantics and automated coverage
  are retained without application-specific compensation.

Only aggregate-safe area/time/category signals are included. Complaint IDs,
records, names, exact addresses, event-level coordinates, person attributes,
victim or suspect demographics, person-level scores, and recommendations are
absent.

## Implementation inventory

The increment changes the established Overview builder and its contract tests,
adds strict Anomalies types/decoder/filter utilities and tests, adds the lazy
Anomalies view and its interaction/accessibility tests, integrates navigation
and shared filters in the application shell, extends responsive CSS and CSS
contract tests, regenerates `dashboard/public/data/overview.json`, and updates
the roadmap and dashboard documentation.

No dependency, temporary fixture, browser harness, commit, history rewrite, or
push is part of this increment.

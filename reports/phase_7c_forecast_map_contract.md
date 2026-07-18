# Phase 7C.1 — Forecast Map Data Contract

## Scope

Phase 7C.1 adds the data-contract and build-pipeline foundation for a future
Predictive Map. `src/analytics/build_dashboard_forecast_map.py` validates the
existing weekly aggregate, Overview date context, ML forecast artifacts, model
metadata, historical error metrics, and selected baseline artifacts before it
writes a compact aggregate-only JSON contract.

This phase does not add a Forecast interface, forecast map layer, frontend
loader, API, deployment, authentication, real-time inference, new model, grid
forecast, person/event prediction, or patrol/enforcement recommendation. Phase
7A Overview and Phase 7B Map & Hotspots behavior remain unchanged.

Generated outputs are:

- `data/processed/dashboard_forecast_map.json` — canonical analytical contract.
- `dashboard/public/data/forecast-map.json` — byte-identical browser-safe copy.

The builder never modifies the weekly, model, baseline, metrics, manifest, or
other source artifacts. `--skip-dashboard-copy` writes only the canonical
output.

## Audited source artifacts

The source audit inspected the actual repository artifacts rather than assuming
their columns, horizon, model identity, category coverage, or baseline meaning.

| Artifact | Audited content and role |
| --- | --- |
| `data/processed/crime_weekly_area.parquet` | Six-column aggregate weekly source: `week_start`, `borough`, `precinct`, `offense_type`, `law_category`, and `crime_count`. It has 1,761,447 unique weekly logical rows, 10,049,687 aggregate reported events, 1,045 Mondays from 2005-12-26 through 2025-12-29, and 8,466 historical segment keys. It has no duplicate keys or malformed/null/negative required values. |
| `data/processed/dashboard_overview.json` | Phase 7A safe-date and complete-week authority, plus the established aggregate precinct-to-borough reference and privacy flags. Safe event dates are 2006-01-01 through 2025-12-31; the latest observed week is 2025-12-29, is partial, and the latest complete week is 2025-12-22. |
| `data/processed/ml_predictions.parquet` | Nineteen fields covering the five logical keys, actual/predicted counts, model name, aggregate lag/rolling features, forecast/backtest flags, and aggregate segment-history metadata. It has 445,610 rows: 437,144 backtest rows and 8,466 `is_next_week_forecast = true` rows. Only the allowlisted aggregate forecast fields are selected for the browser-safe projection. |
| `models/weekly_forecast/model_manifest.json` | `weekly_forecast_ml_model`, artifact version 1; model `duckdb_lag_ensemble_regressor`, model version 1; the exact four segment keys; training window; forecast week; backtest window; leakage controls; and aggregate-only feature policy. Arbitrary manifest content and filesystem paths are not copied. |
| `data/processed/ml_metrics.json` | Model/training/feature metadata and error analysis. Only one aligned overall historical-error record is included; category-specific metrics and training internals remain outside the browser contract. |
| `data/processed/baseline_predictions.parquet` | Sixteen fields covering the five logical keys, observed count, four prior-only baseline candidates, forecast/backtest flags, and aggregate segment-history metadata. It also has 445,610 rows, including 8,466 next-week rows with exact logical-key parity with the ML forecast. |
| `models/baseline_forecast/model_manifest.json` | `baseline_forecast_model`, artifact version 1; documented candidate rules, selected method, training/forecast windows, zero-fill rule, leakage controls, and aggregate-only feature policy. |
| Phase 7B Map artifacts and report | Existing precinct coordinates are event-derived display centroids for only the scored hotspot subset (27 precincts in the audited snapshot), not a complete verified precinct spatial reference. No complete safe precinct boundary/centroid artifact was found. |

The feature audit also checked the model's declared aggregate time, lag,
rolling-prior-week, and segment-history feature groups. The Forecast Map does
not include these features. The only model context exposed is the tightly
allowlisted identity, version, training-through week, forecast week, leakage
status, point-estimate limitation, and aligned overall backtest errors.

## Forecast audit and actual analytical grain

The 8,466 next-week prediction rows contain exactly one forecast Monday,
`2026-01-05`, and exactly one model name,
`duckdb_lag_ensemble_regressor`. Their logical grain is:

```text
forecast week
+ borough
+ precinct
+ offense type
+ law category
```

`2026-01-05` is exactly one week after the latest observed Monday,
`2025-12-29`, and is strictly after the observation horizon. It matches the ML
manifest, ML metrics, baseline manifest, and baseline predictions. The ML and
baseline manifests both report training from 2005-12-26 through 2025-12-29 and
8,466 segments, matching the weekly source.

The ML manifest and metrics share the source artifact timestamp
`2026-07-05T12:40:05.068774+00:00`; the baseline manifest was generated at
`2026-07-05T12:13:45.983331+00:00`. These timestamps show that the repository
artifacts were built retrospectively after their fixed `2026-01-05` target
week. They are audited alignment metadata, not a claim that the forecast is
fresh in wall-clock time, and they are not reused as the deterministic
contract-generation timestamp.

The source forecast has six borough labels, 79 precinct labels, 75 offense
labels, and three law categories. That source coverage includes `UNKNOWN`
geography and historical borough/precinct label conflicts, so it is not all
safe to place on a precinct map. The builder uses the Overview-compatible
all-time dominant-borough assignment for each known precinct. It withholds
rather than remaps 1,481 rows with unknown or unmappable geography and 1,133
rows whose borough is not the canonical borough for their precinct.

The resulting contract contains 5,852 unique rows across five boroughs, 78
known precincts, 75 offense labels, and the three law categories `FELONY`,
`MISDEMEANOR`, and `VIOLATION`. `UNKNOWN` offense remains an explicit source
classification and accounts for 181 browser-safe rows; no category is fabricated.
The output records 69.123553% row coverage and 99.617827% predicted-volume
coverage. Its browser-safe predicted total is 8,137.102083 reported events versus
8,168.319168 across all source forecast rows; the withheld total is 31.217085.
The model-segment coverage is separately recorded as 100%: all 8,466 weekly
source segment keys have exactly one next-week prediction before the explicit
spatial withholding step.
There are 2,909 valid zero point estimates, which remain zero estimates rather
than missing-state substitutes.

The audited next-week ML rows have no duplicate logical keys, missing required
fields, non-finite predictions, or negative predictions. The baseline artifact
also has exact key parity, no duplicate keys, and no negative or non-finite
selected values. Its selected baseline is null for 12 of the 8,466 source rows;
four of those nulls remain among the 5,852 mappable spatial rows.

## Model and historical error alignment

The contract includes model context only after the following identities align:

- manifest artifact type `weekly_forecast_ml_model`, artifact version 1;
- model name `duckdb_lag_ensemble_regressor`, model version 1;
- four manifest segment keys in the expected order;
- 8,466 manifest/source segments;
- training-through week `2025-12-29`;
- prediction, manifest, metrics, and baseline forecast week `2026-01-05`;
- prediction model name and manifest model name; and
- target-week exclusion and time-based leakage controls.

The aligned overall historical context covers the time-based backtest from
2024-12-30 through 2025-12-22 over 437,144 segment-weeks. It reports 100%
prediction coverage, MAE 0.4894, RMSE 1.3943, and weighted MAE 3.6555, in
reported events per segment-week. These are overall historical errors, not
filter-specific errors and not uncertainty bounds. The reviewed model produces
point estimates only, so the contract explicitly marks prediction intervals as
unavailable and never synthesizes confidence or prediction intervals.

## Baseline and expected-change decision

The existing Phase 4 baseline is defensible at the exact ML prediction grain.
The baseline manifest selected `trailing_8_week_mean`: the arithmetic mean of
the eight weekly `crime_count` values immediately before the target week for
the same borough/precinct/offense/law segment. It is emitted only when all eight
prior weeks exist in the segment's zero-filled panel. Missing weekly rows after
a segment's first observed week are treated as zero; weeks before that first
observation are not invented. The target week is excluded, so the calculation
is prior-only and does not leak future observations.

The builder does not trust the selected baseline column by name alone. It
re-derives the declared method from `crime_weekly_area.parquet` for every source
segment and requires null/value parity within the contract tolerance. A
tampered baseline artifact is therefore marked invalid and all baseline/change
fields are withheld while an otherwise valid point forecast remains available.

For each browser-safe row:

```text
expectedChangeCount = predictedCount - historicalBaseline
expectedChangePct   = expectedChangeCount / historicalBaseline * 100
```

Values are computed from the canonically rounded inputs and checked with an
absolute tolerance of `0.000001`.

Baseline availability is deliberately partial:

- 5,848 of 5,852 rows have a defensible historical baseline and change count.
- Four rows lack all eight required prior weeks; `historicalBaseline`,
  `expectedChangeCount`, and `expectedChangePct` remain null.
- 3,051 rows have a valid baseline of zero. Their change count remains
  derivable, but their percentage change is null because division by zero has
  no defensible percentage meaning.
- 2,797 rows have a positive baseline and therefore an included percentage
  change.

A missing value is never replaced with zero. A missing, invalid, or stale
baseline artifact leaves all baseline/change fields null and records the
corresponding baseline status and reason; it does not invalidate an otherwise
aligned point forecast.

## Browser contract

The schema version is `1.0.0`. Its top-level sections are:

| Section | Purpose |
| --- | --- |
| `schemaVersion`, `generatedAtUtc`, `application` | Contract version, deterministic source-derived generation time, and Phase 7C.1/view identity. |
| `dataRange` | Safe event dates, first/latest observed weeks, latest complete week, partial-week flag, and supported forecast week. |
| `dimensions` | Sorted forecast weeks, boroughs, precincts, offense types, and law categories. |
| `filterIndex` | Compact precinct indexes grouped by their canonical borough index. |
| `forecast` | Availability status, source filename, empty flag, positional row schema/rows, and reconciled row/volume/coverage summary. |
| `availability` | Point-estimate, baseline, change-count, change-percentage, interval, and spatial-reference availability. |
| `model`, `baseline` | Allowlisted aligned model/error context and exact selected prior-only baseline semantics/coverage. |
| `forecastSemantics`, `locationKeySemantics`, `methodology` | Grain, horizon, interpretation, spatial-key policy, rounding, change arithmetic, timestamp, mapping, and freshness rules. |
| `limitations` | Partial-week, model-error, classification, spatial, and responsible-interpretation caveats. |
| `provenance` | Seven tightly allowlisted source filenames, statuses, and browser uses; no source paths or raw manifest blobs. |
| `privacy`, `ethics` | Machine-validated aggregate-only and no-person/no-recommendation assertions. |

Forecast records are positional arrays declared by `forecast.rowColumns`:

```text
forecastWeekIndex
boroughIndex
precinctIndex
offenseTypeIndex
lawCategoryIndex
predictedCount
historicalBaseline
expectedChangeCount
expectedChangePct
precinctLocationKey
```

Dimensions and rows are validated together. Each row index must be an integer
within its declared dimension, rows must be in ascending total logical-key
order, logical keys must be unique, every precinct must have exactly one
borough assignment in the filter index, and the filter index must reconcile to
the row set.

## Availability and withholding behavior

The contract distinguishes unavailable inputs from genuine zero forecasts:

| Condition | Contract behavior |
| --- | --- |
| Valid forecast with rows | `forecast.status = "available"`; point-estimate availability is `available`. |
| Valid forecast artifact with no next-week rows | `forecast.status = "available"`, `isEmpty = true`, point-estimate availability is `empty`, and numeric totals stay null. |
| Missing forecast artifact | `missing`; reason present; rows and dimensions empty; no zero total. |
| Malformed or incompatible forecast/model artifact | `invalid`; reason present; forecast rows withheld. |
| Model/forecast horizon behind the validated observation horizon | `stale`; reason present; forecast rows withheld. |
| Baseline unavailable for every/some/no rows | Analytical availability is `unavailable`, `partial`, or `available`; unavailable values remain null. |

No wall-clock time-to-live policy is invented. `stale` specifically means the
model training or forecast horizon is behind the validated weekly/Overview
observation horizon. A fixed repository forecast is not mislabeled stale merely
because the wall clock has advanced.

The weekly aggregate and Overview contract are required observation authorities;
if either is malformed or mutually incompatible, the builder fails without
writing a replacement. Optional prediction, manifest, metrics, and baseline
failures are represented explicitly or cause dependent values to be withheld.

## Location-key decision

At the Phase 7C.1 milestone, no complete verified aggregate-safe precinct
coordinate, centroid, boundary, or geometry source existed in the repository.
The Phase 7B hotspot centroids covered only a scored subset and were derived from
valid-coordinate aggregate-safe events; extrapolating them to all forecast
precincts would have fabricated spatial coverage. Phase 7C.1 therefore includes
no latitude, longitude, centroid, or geometry. Phase 7C.3 later supplied the
separately validated official 78-feature precinct-boundary contract without
changing this Forecast Map data contract's aggregate point-estimate role.

Each mappable precinct receives the stable opaque join key:

```text
nypd-precinct:<source precinct label>
```

For example, precinct `40` becomes `nypd-precinct:40`. The key is validated
against the indexed precinct label and is explicitly documented as a join key,
not a coordinate or boundary. Unknown, blank, malformed, or uncanonically
mapped locations are withheld and quantified.

## Validation rules

The builder and payload validator reject or safely withhold:

- missing required columns, malformed JSON/Parquet, malformed labels, non-Monday
  weeks, null forecast flags, and unsafe source columns;
- null/non-finite predicted values, negative predicted counts, non-finite or
  negative baseline counts, and values that are not canonically rounded;
- duplicate source or payload logical keys and unstable row/dimension ordering;
- zero, mixed, past, multiple, or non-next-week horizons when forecast rows are
  present;
- forecast-week, model-name, model-version, training-window, segment-count,
  metrics, baseline-key, and manifest mismatches;
- training that extends beyond the observation horizon, stale training/forecast
  artifacts, and generation metadata that is future-dated or not derived from
  the safe data end date;
- unmappable borough/precinct labels, missing or multiple borough assignments,
  invalid dimension/filter indexes, and unsafe/inconsistent location keys;
- inconsistent predicted/baseline/change arithmetic, including non-null
  percentage change when the baseline is zero;
- unsafe or absent privacy/ethics assertions, unexpected top-level payload
  fields, non-allowlisted provenance structure, exposed filesystem paths, and
  known complaint, demographic, or event-coordinate field names.

Invalid numbers are not clamped, coerced, or substituted. JSON serialization
uses `allow_nan=False`, so non-standard `NaN`/infinity output is impossible.

## Deterministic build behavior

Identical validated inputs produce identical bytes:

- dimensions are lexically sorted;
- forecast rows use a complete stable logical-key ordering;
- numeric output is rounded to six decimal places;
- JSON keys are sorted and serialized with compact fixed separators, UTF-8, and
  one trailing newline;
- `generatedAtUtc` is the aggregate-safe maximum event date at `00:00:00Z`, not
  the wall clock; the audited value is `2025-12-31T00:00:00Z`;
- the dashboard copy is made directly from the canonical bytes.

Build commands:

```bash
.venv/bin/python src/analytics/build_dashboard_forecast_map.py
.venv/bin/python src/analytics/build_dashboard_forecast_map.py --skip-dashboard-copy
```

At the audited real-data snapshot, each output is 308,096 bytes including its
trailing newline, contains 5,852 forecast rows, and has SHA-256:

```text
99ede5cf258c4051b89fcab0d6dd384925a5e48908c7bf763c258607ffb193db
```

## Privacy and ethical boundaries

The browser-safe rows are aggregate segment-week point estimates only. The
contract contains no complaint identifier, source-row identifier, event record,
name, address, event-level coordinate, victim/suspect demographic, person-level
score, or patrol/enforcement recommendation. Input schemas are checked for
unsafe field-name patterns before an optional artifact can be included, and
the final payload is checked for forbidden source tokens.

Machine-validated flags state that the data are aggregate-only, that event and
demographic fields are absent, and that the forecast concerns aggregate
reported-event volume only. A forecast does not predict individual behavior,
identify a specific future incident location, establish crime certainty, score
neighborhood danger, or justify action. Reporting behavior, classification,
delay, revision, incomplete recent-week data, and historical model error remain
explicit limitations.

## Verification

All required checks passed from the requested working directories:

- Focused Forecast Map suite:
  `.venv/bin/python -m unittest tests.test_dashboard_forecast_map_contract` —
  19 of 19 tests passed.
- Full practical Python contract suite:
  `.venv/bin/python -m unittest discover -s tests -p 'test_*_contract.py' -v` —
  78 of 78 tests passed.
- Affected existing Overview, ML forecast, and baseline forecast suites — 24 of
  24 tests passed in their separate targeted run.
- A fresh one-thread real build exactly matched the final canonical bytes; the
  canonical, dashboard, and repeated-build files share the 308,096-byte size
  and SHA-256 recorded above.
- `dashboard/` `npm run lint` — passed.
- `dashboard/` `npm test` — 4 files and 41 of 41 tests passed.
- `dashboard/` `npm run build` — passed; Vite transformed 2,353 modules and
  produced the existing application bundles without adding a Forecast loader or
  UI chunk.
- `dashboard/` `npm audit --omit=dev` — zero vulnerabilities.
- Repository-root `git diff --check` — passed.

## Phase 7C.1 limitations

- Only one fixed next-week horizon, `2026-01-05`, is supported. There is no
  multi-week, monthly, grid, or real-time forecast.
- The latest observed week is partial. Although both the ML model and baseline
  are prior-only relative to the target, that incomplete week can depress lag
  and rolling inputs.
- Forecast rows span historical model segments, including inactive and zero-
  prediction segments. They are expected aggregate reported-event volume, not
  incident occurrence claims.
- Geography in this Phase 7C.1 contract is precinct-key-only. The contract
  cannot itself place rows on a map; Phase 7C.3 later resolves rendering through
  the separate official precinct-boundary artifact.
- Source geography requires withholding 2,614 of 8,466 logical rows. Coverage
  metrics make this loss explicit; withheld rows are not silently remapped.
- Four mappable rows lack enough prior history for the selected trailing-
  eight-week baseline, and 3,051 valid zero baselines cannot support percentage
  change.
- Historical errors are overall backtest context and cannot be presented as
  per-filter uncertainty. No prediction interval exists.
- No frontend loader or UI compatibility logic is implemented in Phase 7C.1;
  those responsibilities were delivered by Phases 7C.2 and 7C.3.

## Phase 7C.2 and Phase 7C.3 resolution

Phase 7C.2 delivered the runtime-validating TypeScript loader and accessible
Forecast / Expected Change list/detail layers using this contract, including
Overview-date and filter compatibility plus neutral missing, invalid, stale,
empty, and mismatch states. Phase 7C.3 then added the separately validated
official precinct spatial reference keyed by
`nypd-precinct:<source precinct label>` and synchronized polygon rendering. The
completed UI continues to present point estimates and overall historical error
context without inventing intervals, danger scores, incident locations, or
patrol/enforcement guidance. Its genuine Chrome native-keyboard acceptance is
recorded in the [Phase 7C.3 report](phase_7c3_precinct_spatial_rendering.md).

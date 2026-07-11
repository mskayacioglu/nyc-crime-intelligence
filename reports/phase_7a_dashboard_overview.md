# Phase 7A - Dashboard Foundation and Overview

## Scope

Phase 7A adds the first operational screen for **NYC Crime Intelligence**. It is a
single aggregate Overview: no map, API, authentication, deployment, live
ingestion, patrol recommendation, enforcement recommendation, or person-level
score is included.

## Architecture

The dashboard uses a two-stage local architecture:

1. `src/analytics/build_dashboard_overview.py` validates the processed inputs
   with DuckDB and prepares a compact, deterministic frontend contract.
2. `dashboard/` is a Vite, React, and TypeScript application that loads only the
   compact Overview metadata and compressed weekly aggregate cube. It never
   loads `complaints_clean.parquet` or complaint-level rows in the browser.

Observed weekly counts are stored as typed, little-endian column arrays and
compressed with deterministic gzip metadata. A compact `weekRowOffsets` column
bounds scans to the selected weeks. Dimension values and optional analytical
signals remain in an indexed JSON contract. This keeps the full historical
filter surface practical without adding a standalone API.

## Inputs and outputs

Required inputs:

- `data/processed/complaints_clean.parquet`
- `data/processed/crime_weekly_area.parquet`

Optional inputs:

- `data/processed/hotspots.parquet`
- `data/processed/hotspot_metrics.json`
- `data/processed/anomalies.parquet`
- `data/processed/anomaly_metrics.json`
- `data/processed/ml_predictions.parquet`
- `data/processed/ml_metrics.json`
- `models/weekly_forecast/model_manifest.json`
- `models/baseline_forecast/model_manifest.json`

Generated contract files:

- `data/processed/dashboard_overview.json`
- `data/processed/dashboard_overview_cube.bin.gz`
- `dashboard/public/data/overview.json`
- `dashboard/public/data/overview-cube.bin.gz`

The files under `dashboard/public/data/` are frontend-safe copies used by the
local application and production build.

## Overview metrics

- Selected-period observed complaint count.
- Recent complete-week change against an equal-length immediately preceding
  period.
- Weekly observed trend with a prior-only trailing baseline.
- Borough comparison.
- Top offense types.
- Law-category distribution.
- High and critical hotspot counts when the snapshot exists.
- High and critical anomaly counts when anomaly output exists.
- Next-week aggregate model estimate only when the forecast output and its
  validation context support it.
- A compact attention table that keeps hotspot scores, anomaly deviations, and
  forecast estimates explicitly distinct from observed counts.

The generated production contract contains 1,761,447 weekly aggregate rows and
reconciles exactly to 10,049,687 aggregate-safe events. Its default complete-week
window contains 567,306 observed events. The optional current outputs contribute
26 high/critical hotspot rows, 10,378 high/critical anomaly rows, and 8,466
next-week forecast rows.

## Filter semantics

The date controls select an inclusive range of Monday-based `week_start`
buckets. Borough, precinct, offense type, and law category filters are applied
to the same weekly aggregate rows for every observed metric and chart. Changing
borough constrains the precinct menu; the mapping assigns a known precinct to
the borough with its largest all-time aggregate count, using lexical order to
break ties. The exact stored borough/precinct combination is still used when
calculating counts.

The default range ends at the latest complete week because the bucket beginning
2025-12-29 is partial. Recent change uses up to four complete selected weeks and
the same number of directly preceding complete weeks. A comparison is omitted
when there is not enough prior coverage. No later observations contribute to a
historical baseline.

Hotspots are a fixed analytical snapshot and are not re-scored in the browser.
They respond to supported categorical filters and retain their scoring date.
The attention table compares the hotspot recent count with
`baseline_expected_recent_count`, which normalizes the historical rate to the
same recent-window duration; it does not compare the recent window with the raw
365-day baseline total. Grid-grain hotspots carry a deterministic rounded grid
cell label so rows remain distinguishable without implementing the Phase 7B map.
The data build accepts only one hotspot scoring date and rejects snapshots later
than the maximum aggregate-safe event date; the current snapshot is one data day
behind that event date.
Anomalies use their own observed week and respond to the selected date range.
Forecasts retain their future forecast week and are not presented as observed
events.

## Optional-input behavior

Each optional source has an explicit `available`, `missing`, or `invalid` status
and a reason where applicable. Missing hotspot, anomaly, forecast, metrics, or
manifest files do not prevent observed Overview analysis. The UI renders a
neutral unavailable state rather than a fabricated zero.

The current forecast has historical error context but no uncertainty interval.
Its source horizon includes a partial final week, so the UI exposes that caveat
and avoids language implying certainty. Forecast rows are withheld when the ML
manifest does not verify disabled random splits and exclusion of the target week
from features. They are also withheld unless the prediction file contains
exactly one model and one forecast week, the week is strictly later than the
latest observed aggregate week, and both identifiers match the ML manifest.
Historical error context is published only when the metrics artifact model and
forecast week align with both files. MAE/RMSE values are labeled as overall model
backtest errors and are not represented as filter-specific errors.

Optional analytical families are rejected as `invalid` when required numeric
fields are null, non-finite, negative where counts/forecasts require nonnegative
values, or when logical segment keys are duplicated. Processed forecast values
are never silently clamped. A deterministic total ordering is applied after
validation.

## Visual system

The interface uses centralized CSS tokens for near-black charcoal backgrounds,
gunmetal and concrete surfaces, off-white text, muted amber warnings,
restrained red critical states, cold desaturated cyan analytical/forecast
signals, and gray historical baselines. Surfaces are matte, borders are thin,
corners remain at or below 8px, and the chart grid is visually dominant over
the summary counters. No purple, neon, glow, gradient, or copyrighted fictional
branding is used.

`dashboard/public/assets/nyc-civic-grid.webp` is an original generated raster
texture depicting rain-darkened civic architecture. It is optimized for web
delivery and used decoratively behind the compact application header under a
solid contrast treatment.

## Accessibility

- Semantic headings, labels, tables, and native controls.
- Text alternatives for status icons and labels for icon-only actions.
- Visible keyboard focus treatment.
- Accessible contrast across normal, warning, critical, and analytical states;
  the smallest muted text is at least 4.57:1 against its darkest semantic
  surface.
- Stable loading placeholders and explicit empty/error messages.
- Reduced-motion rules that suppress nonessential transitions.
- Responsive desktop, tablet, and single-column mobile layouts without page
  horizontal overflow.
- A compact artifact provenance register exposes availability, phase/model or
  artifact version, generated timestamp, and source file where reported.

## Data quality and limitations

- The aggregate-safe source covers 2006-01-01 through 2025-12-31.
- The latest weekly bucket is incomplete and can understate a full week.
- Counts describe reported complaints, not confirmed causality or individual
  behavior; reporting delays, revisions, and classification changes apply.
- Hotspot scores measure aggregate concentration, anomaly scores measure
  historical deviation, and forecasts are model estimates. They are not
  interchangeable.
- The forecast has backtest error context but no confidence interval.
- Current forecast backtest context is MAE 0.4894, RMSE 1.3943, and weighted MAE
  3.6555 with 100% prediction coverage.
- Map analysis remains out of scope until Phase 7B.

## Verification

- Repeated real-data generation produced byte-identical artifacts:
  - metadata SHA-256 `21c30b5e8d573a0a20c431b1f44d814c0c10c7e8b37a8305296b1504ed184284`
  - cube SHA-256 `737954008cfc7a1361a9be5acc00a0b29c3b4a2daf25472e61ffb04c55114e3b`
- The practical Python suite passed 47/47 tests.
- Frontend ESLint passed, Vitest passed 10/10 tests, and the Vite production
  build completed successfully.
- The running application was exercised at desktop (1440 × 1000), tablet
  (820 × 1180), and mobile (390 × 844) viewport overrides. All four chart SVGs
  had rendered marks and nonzero widths; the page had no horizontal overflow.
- Borough, constrained precinct, offense, law-category, both date filters,
  reset, mobile filter disclosure, and a real empty result were exercised.
- The header texture, compact provenance register, grid hotspot labels, internal
  table scrolling, keyboard-visible focus, and reduced-motion CSS rule were
  verified. Browser console warning/error output was empty in the clean final
  session.
- Measured small-text contrast was at least 4.57:1 across muted, warning, and
  critical semantic surfaces.

## Ethics and privacy contract

Only rows with `is_clean_event_for_aggregate = true` establish the safe count
and freshness window. The browser contract contains aggregate buckets and
aggregate analytical signals only. Complaint identifiers, event-level records,
victim demographics, and suspect demographics are absent. The product provides
neutral trend context and does not recommend patrol, enforcement, or action
against any person or group.

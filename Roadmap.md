# NYC Crime Intelligence Roadmap

## Status

The reviewed analytical pipeline and local dashboard are delivered. This file
records the implemented scope, remaining limitations, and reasonable future
improvements; it is not a sprint log or a promise of scheduled work.

The repository represents a fixed retrospective snapshot. Creating a GitHub
repository, publishing a Hugging Face model page, and deploying a hosted demo
are owner-controlled distribution steps and are not asserted here as complete.

## Delivered scope

### Data and provenance

- Deterministic cleaning of the reviewed NYPD Complaint Data Historic export.
- Explicit source identity, snapshot checksum, date horizon, and reproduction
  limits.
- Monday-starting weekly and monthly aggregate outputs.
- Separate handling of excluded dates, overlapping quality flags, retained
  `UNKNOWN` dimensions, and valid numeric zeroes.
- Raw source exclusion from Git and from browser-facing artifacts.
- Official police-precinct geometry with source metadata, checksum, schema,
  coordinate-system, and freshness validation.

### Analysis and modeling

- Transparent prior-only baseline comparison.
- A deterministic DuckDB lag-ensemble point forecast with time-based backtest
  evidence and an immutable fixed forecast horizon.
- Retrospective hotspot scoring at aggregate precinct and grid grains.
- Observed anomaly scoring against leakage-safe historical expectations.
- Aggregate-only model manifests, metrics, and methodology reports.

### Dashboard

- Overview, Map & Hotspots, Forecast, Expected Change, Anomalies, and Governance
  views.
- Shared borough, precinct, offense, law-category, and date filters where the
  analytical contract supports them.
- Strict runtime validation with distinct missing, invalid, stale,
  incompatible, available-empty, and filtered-empty states.
- Complete list/detail alternatives for map-based experiences.
- Responsive desktop, tablet, and mobile layouts; visible focus; reduced-motion
  support; non-color-only states; and minimum touch targets.
- One-command local startup through `./run.sh`.

### Reproducibility and governance

- Pinned Python, Node.js, npm, and frontend dependency contracts.
- Normal aggregate-only verification plus an explicit optional full-data
  integration mode.
- Privacy, path, secret, notebook-output, data-license, history, and large-blob
  hygiene checks.
- MIT licensing for original code and documentation, without relicensing
  third-party source data.
- Explicit responsible-use and prohibited-use boundaries.

## Known limitations

### Data

- Complaint data reflects reporting behavior, under-reporting, delay, revision,
  classification, and policy change.
- Aggregate counts are source-row counts, not verified unique incidents,
  victims, harms, or causal effects.
- The final source week is partial and remains an input to lag-based forecast
  features.
- Zero-filling begins only after a segment first appears and cannot distinguish
  a true zero from an upstream reporting absence.

### Model and analysis

- Model improvement over the selected baseline is small and is evaluated on one
  historical split.
- Headline baseline and ML metrics have different prediction coverage and are
  not a matched-row comparison.
- Forecasts are point estimates without prediction intervals, calibration
  analysis, or filter-specific error estimates.
- No formal drift monitor, general retraining cadence, or model-age service
  threshold is defined.
- Features omit holidays, exogenous events, reporting-delay correction,
  long-run structural breaks, and spatial spillover.
- Hotspot thresholds are fixed, and degree-based grid cells are not equal-area.

### Product and accessibility

- The dashboard uses committed fixed artifacts; it has no API, scheduler,
  authentication system, or automatic data refresh.
- Forecasting covers one fixed next-week horizon rather than arbitrary future
  dates.
- Raster map context depends on an external tile provider; analytical vectors,
  filters, lists, and details remain usable without those tiles.
- Automated native-keyboard and visible-focus checks pass, but precinct-list
  keyboard activation should be repeated in a final manual accessibility review
  on the target browser/platform combination.

## Possible future improvements

These are candidates, not commitments:

1. Evaluate baseline and model performance on an identical matched-row sample.
2. Add prediction intervals and calibration evidence before expanding forecast
   interpretation.
3. Evaluate holiday, reporting-delay, structural-break, and spatial-context
   features with the same leakage-safe time split.
4. Define an explicit artifact refresh, drift review, and model versioning
   policy.
5. Add automated source-edition monitoring while preserving manual provenance
   review and checksum recording.
6. Repeat a documented manual accessibility audit across target browsers and
   assistive-technology combinations.
7. Add owner-created GitHub, Hugging Face, and optional hosted-demo links after
   those destinations exist.

## Explicitly out of scope

- Person-level, demographic, or individual risk scoring.
- Exact incident-location or individual-behavior prediction.
- Neighborhood danger, safety, worth, or blame labels.
- Patrol, enforcement, deployment, intervention, or resource-allocation
  recommendations.
- Automated adverse decisions or operational alerting.
- Causal claims from complaint counts, hotspots, anomalies, or forecasts.
- Real-time inference, live incident monitoring, or public-safety dispatch.

## Change policy

A new source checksum, review date, spatial edition, feature definition, model,
or forecast horizon creates a new analytical version. Such a change should be
rebuilt through the canonical scripts, verified against the documented
contracts, and recorded in provenance and model metadata before any browser
artifact is replaced.

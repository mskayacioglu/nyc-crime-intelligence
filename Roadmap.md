# Crime Intelligence Dashboard Roadmap

## 1. Project Objective

The objective of this project is to develop a crime intelligence dashboard that analyzes crime incidents over time and geography using the historical NYPD Complaint dataset, produces short-term volume forecasts, and presents explainable insights to decision-makers.

The initial product objective is not to make person-level predictions. The product should answer the following aggregate analytical questions:

- In which areas is crime volume increasing?
- Which crime types increase at which times?
- Based on historical trends, which areas are expected to have higher volume next week or next month?
- Which area/crime-type combinations deviate from normal patterns?
- Where do hotspot areas appear on the map?

## 2. Reviewed Data Status

The project's initial data source is:

```text
data/raw/NYPD_Complaint_Data_Historic.csv
```

The data contains approximately 10 million rows and 35 columns. Notable column groups include:

- Incident date and time: `CMPLNT_FR_DT`, `CMPLNT_FR_TM`, `CMPLNT_TO_DT`, `CMPLNT_TO_TM`, `RPT_DT`
- Offense type and category: `OFNS_DESC`, `PD_DESC`, `LAW_CAT_CD`, `KY_CD`, `PD_CD`
- Location: `BORO_NM`, `ADDR_PCT_CD`, `Latitude`, `Longitude`, `X_COORD_CD`, `Y_COORD_CD`
- Premises type: `PREM_TYP_DESC`, `LOC_OF_OCCUR_DESC`, `JURIS_DESC`
- Victim and suspect demographics: `VIC_AGE_GROUP`, `VIC_RACE`, `VIC_SEX`, `SUSP_AGE_GROUP`, `SUSP_RACE`, `SUSP_SEX`

Because the demographic fields have high missingness and present ethical risks, they should not be used as inputs to the initial model. These fields should be evaluated only for data-quality and fairness reviews.

## 3. Product Principles

- The model will not predict criminality at the level of individuals, race, sex, or age group.
- The dashboard will be designed as a decision-support tool; it will not generate automated enforcement or patrol decisions.
- Model outputs will always be presented with historical trends, validated
  uncertainty or historical-error context, and data-quality context. When an
  interval is unavailable, the product must say so instead of inventing one.
- Explainable, auditable, and understandable metrics will take priority.
- The initial local product scope prioritizes a reliable data pipeline and correct problem definition over a perfect model.

## 4. MVP Scope

### Roadmap status and scope boundary

The local implementation roadmap is delivered except for the explicitly open
Phase 7C.3 practical native-keyboard verification gate. Sections 5 through 11
preserve the original plan and its delivered results; their proposal, task,
sprint, and expected-output language is historical context rather than an open
implementation queue. The reviewed local state is:

| Product work | Local status |
| --- | --- |
| Data exploration, cleaning, aggregation, analytical baseline, baseline forecast, ML forecast, hotspots, and anomalies | Complete and verified |
| Overview, Map & Hotspots, Forecast, Expected Change, Anomalies, and Governance | Complete and distinct |
| Phase 7C.3 official precinct rendering, responsive behavior, and failure states | Implementation and automated checks complete; practical native-keyboard verification incomplete |

Any external publication or release work is intentionally deferred to a future,
separate discussion. Hosting, distribution, adding a Git remote, creating tags
or release records, and preparing an external model or dataset upload are
outside this local implementation roadmap, and none is performed here.
The historical API, database, framework, and deployment ideas in Sections 12–14
were exploratory options, not delivered requirements or prerequisites for local
completion.

The first MVP should include the following capabilities:

- Overall crime trends
- Borough- and precinct-level comparisons
- Crime-type distribution
- Patterns by day, week, month, and hour
- Crime volume on a map
- Hotspot view
- Weekly incident-count forecasts by area and crime type
- Anomaly list showing unexpected increases
- The model's training-data range, artifact-generation time, independently
  recorded training-time status, and known limitations

The following topics will be excluded from the MVP:

- Person or suspect profiling
- Real-time police deployment
- Enforcement recommendations based on automated risk scores
- Criminality predictions by demographic group

## 5. Phase 1: Data Exploration and Quality Analysis

Objective: Understand the raw data, identify risky fields, and produce a data dictionary suitable for modeling.

Tasks:

- Determine the data types of the CSV columns
- Determine the date range
- Calculate the row count, missing-value rates, and unique-value counts
- Analyze the distributions of `BORO_NM`, `ADDR_PCT_CD`, `OFNS_DESC`, and `LAW_CAT_CD`
- Check whether coordinates fall within valid NYC boundaries
- Flag invalid date, time, age-group, and category values
- Examine data consistency by year
- Produce a data-quality report

Expected output:

```text
reports/data_quality_report.md
data/processed/schema_profile.json
```

## 6. Phase 2: Clean Data and Aggregation Pipeline

Objective: Make the raw incident data usable by the model and dashboard.

Tasks:

- Produce a standardized incident timestamp from `CMPLNT_FR_DT` and `CMPLNT_FR_TM`
- Normalize empty, `(null)`, and invalid values
- Simplify crime-type categories
- Clean borough, precinct, and coordinate fields
- Group incidents into weekly and monthly time buckets
- Produce an aggregate modeling table from incident-level data

Proposed primary modeling table:

```text
week_start | borough | precinct | offense_type | law_category | crime_count
```

Expected output:

```text
data/processed/complaints_clean.parquet
data/processed/crime_weekly_area.parquet
data/processed/crime_monthly_area.parquet
```

## 7. Phase 3: Analytical Baseline

Objective: Establish the dashboard's core analytical value before modeling.

Tasks:

- Produce annual, monthly, and weekly crime trends
- Create borough- and precinct-level rankings
- Analyze trends by crime type
- Produce hour-of-day and day-of-week patterns
- Produce the first heatmap and volume analysis
- Identify the fastest-increasing and fastest-decreasing crime-type/area combinations

Expected output:

```text
reports/exploratory_analysis.md
data/processed/dashboard_summary.json
```

## 8. Phase 4: Baseline Forecasting Model

Objective: Establish simple and strong forecasting baselines for comparison before developing an ML model.

Initial target variable:

```text
The next week's incident count for a specific crime type within a specific precinct or borough.
```

Baseline approaches:

- Use the previous week's value as the forecast
- Use the average of the last 4 weeks
- Use the arithmetic average of the last 8 weeks
- Use the same week of the previous year as a reference

Evaluation metrics:

- MAE
- RMSE
- Weighted MAE
- Top-K volume capture rate
- Time-based backtesting results

Expected output:

```text
models/baseline_forecast/
reports/baseline_model_report.md
data/processed/baseline_predictions.parquet
```

## 9. Phase 5: Machine-Learning Model

Objective: Develop an explainable forecasting model and compare it transparently with the baseline models.

Initial proposal:

- A LightGBM- or XGBoost-based regression model

Implemented result:

- `duckdb_lag_ensemble_regressor`, version 1, a deterministic prior-only lag
  ensemble selected by time-ordered validation RMSE
- Formula inputs: the one-week and 52-week lags plus the trailing four- and
  eight-week arithmetic means
- Implementation dependency: the Python standard library and pinned DuckDB;
  LightGBM and XGBoost are not used

Proposed feature groups:

- Time: week, month, year, day of week, season
- Geography: borough, precinct, patrol borough
- Crime type: `OFNS_DESC`, `LAW_CAT_CD`
- Lagged values: incident counts from the last 1, 2, 4, and 8 weeks
- Rolling statistics: rolling mean, standard deviation, minimum, maximum
- Trend signals: rate of change over the last 4 weeks and the last 8 weeks

Fields not recommended for initial use:

- `SUSP_RACE`
- `SUSP_SEX`
- `SUSP_AGE_GROUP`
- `VIC_RACE`
- `VIC_SEX`
- `VIC_AGE_GROUP`

These fields should be excluded from the initial model because of both missingness and ethical risk.

Expected output:

```text
models/weekly_forecast/
reports/ml_model_report.md
data/processed/ml_predictions.parquet
```

## 10. Phase 6: Hotspot and Anomaly Layer

Objective: Add two distinct analytical layers that provide intelligence value beyond forecasting.

Hotspot approach:

- Precinct-level density score
- Grid- or H3-based density score
- Density weighted over the last 7, 30, and 90 days
- Map layer with a crime-type filter

Anomaly approach:

- Deviation from the historical mean by area/crime type
- Rolling mean and rolling standard deviation
- Z-score or robust z-score
- Deviation from the seasonally expected value

Expected output:

```text
data/processed/hotspots.parquet
data/processed/anomalies.parquet
reports/anomaly_methodology.md
```

## 11. Phase 7: Dashboard Design

Objective: Turn model and analytical outputs into an understandable local product.

Proposed views:

### Overview

- Total incident count
- Trend for the selected date range
- Most common crime types
- Borough comparison
- Weekly change indicators

### Map

- Heatmap
- Precinct or grid layer
- Crime-type filter
- Date-range filter
- Hotspot overlay

### Trends

- Time-series charts
- Crime-type breakdown
- Borough/precinct comparison
- Hourly and daily patterns

### Forecast

- Next-week or next-month forecast
- Actual vs. forecast chart
- Validated historical error context, with an explicit unavailable state when
  the model does not provide a prediction interval
- Areas with the highest expected increases

### Phase 7C — Predictive Map

Status: Phase 7C.1 — Forecast Map Data Contract and Phase 7C.2 — Predictive Map UI
& Integration are complete. The Phase 7C.3 — Verified Precinct Spatial Rendering
implementation and all automated checks are complete. Practical responsive checks
at 1280 × 900, 768 × 1024, and 390 × 844 passed, as did checks for spatial
error/stale/mismatch states, tile-failure resilience, and clean console/network
activity. However, although
the in-app browser's documented keyboard channels correctly focused the native
list button and displayed its visible focus ring, they did not deliver the
Enter/Space activation event to the page. Policy was not bypassed by using another
browser surface; Phase 7C.3 remains verification-incomplete until this final
practical keyboard gate is successfully repeated. The May 2026 26B Police
Precincts source from the NYC Department of City Planning / NYC Open Data was
vendored reproducibly, validated one-to-one against all 78
`nypd-precinct:<label>` keys in the Forecast contract, and used to render
aggregate precinct polygons in Forecast and Expected Change modes. A complete,
map-independent keyboard-accessible list/detail path was retained; missing,
invalid, or incompatible spatial states are not represented as zero or empty
geography.

Objective: Place the existing weekly forecasts in geographic context so users
can see not only historical concentrations, but also the expected aggregate
incident volume for the next week and its difference from historical expectations.

Initial delivery scope:

- The first forecast horizon will be the next week.
- The first geographic level will be the precinct; the reviewed model output
  carries borough, precinct, crime-type, and law-category keys.
- The Map view will allow switching among the **Hotspots**, **Forecast**, and
  **Expected change** layers.
- Global date, borough, precinct, crime-type, and law-category filters will
  retain the same meaning in the forecast layer.
- The selected precinct detail will show the predicted incident count, historical
  expectation, absolute and percentage difference, forecast week, and appropriate
  model-error context.
- The map will show only aggregate precinct signals, not people or incident points.

Frontend-safe output:

```text
data/processed/dashboard_forecast_map.json
dashboard/public/data/forecast-map.json
data/processed/dashboard_precinct_spatial_reference.json
dashboard/public/data/precinct-spatial-reference.json
```

Proposed forecast row:

```text
forecast_week
| borough
| precinct
| offense_type
| law_category
| predicted_count
| historical_baseline
| expected_change_count
| expected_change_pct
| precinct_location_key
```

The contract should also include the data end date, forecast generation date,
supported forecast weeks, backtest error context, filter dimensions, and
aggregate-only safety flags. Incident records, exact addresses, complaint IDs,
personal information, and demographic fields must not be sent to the browser.

Validation and state behavior:

- The forecast week must be strictly later than the last observed week.
- A week/precinct/crime/law key must not be duplicated.
- Forecast, baseline, difference, and error values must be finite and defensible.
- The Forecast, model manifest, and Overview data dates must be mutually consistent.
- Missing, invalid, stale, empty, and Overview/Forecast mismatch states must remain
  distinct; an incompatible forecast must not be presented as compatible.
- A historical filter selection must not make the fixed future forecast appear
  historical; unsupported scope must produce a neutral state.
- Unless the reviewed model produces a prediction interval, the interface must show
  only a point estimate and validated backtest error context, and must not generate
  a confidence interval.

Accessibility and product language:

- Forecast differences must not be communicated by color alone; direction, value,
  and a text label must be used together.
- All forecast areas must be available in a keyboard-accessible list that remains
  synchronized with map selection.
- Language must not say "crime will occur here in the future" or "high-risk area";
  it should say that "aggregate incident volume is expected to be above/below the
  historical level."
- Model output must not be presented as an automated patrol, enforcement, or
  person-level decision recommendation.

Out of scope for the initial local product:

- Grid-level forecasting
- Monthly or multi-horizon forecast maps
- Real-time inference
- Incident- or person-level prediction
- Automated enforcement/patrol recommendations
- API or deployment work

Success criteria:

- Users must be able to distinguish clearly between historical hotspots and the
  next-week forecast within the same Map view.
- Precinct forecasts must match the existing global filters deterministically.
- Forecast, baseline, and expected-change values must come from the same
  frontend-safe contract.
- The loader must enforce duplicate, future-horizon, malformed, stale, and
  date-mismatch checks through tests.
- The Forecast layer must not break hotspot behavior on desktop, tablet, mobile,
  or during keyboard use.
- Official precinct geometry must match all 78 forecast keys completely and
  uniquely; checksum, provenance, CRS, ring structure, NYC bounds, and
  aggregate-safe field restrictions must be validated at both build and browser
  boundaries.

### Anomalies

Status: complete. The separate **Anomalies** view displays already-observed weekly
aggregate increases rather than forward-looking forecasts or hotspot intensity. No
new anomaly definition or browser artifact was produced; the existing
`crime_weekly_area.parquet` -> `anomalies.parquet` /
`anomaly_metrics.json` -> `dashboard_overview.json` chain and the frontend-safe
high/critical signals in `overview.json` were used.

Delivered experience:

- The anomaly week, borough, precinct, crime type, and law category are shown
  together.
- The observed aggregate count is compared with the leakage-safe historical-week
  backtest prediction when available; otherwise, it is compared only with the
  average of the previous 13 weeks.
- Signed deviation, direction text, the existing anomaly score, and high/critical
  analytical-signal priority are shown together; direction and importance are not
  encoded by color alone.
- Sorting is deterministic by critical, high, score, week, and stable aggregate
  identity. The priority label is not a measure of crime severity or police
  priority, nor is it a patrol or enforcement recommendation.
- Global date, borough, precinct, offense, and law filters use the same semantics
  as Overview; borough limits the available precinct options, and Reset restores
  the default completed-week range.
- The complete list of native buttons, visible selection, `aria-pressed`, live
  detail, and stable initial selection share the same state. Missing, invalid,
  stale, incompatible, source-empty, filtered-empty, loading, and network-error
  states remain distinct without producing zero values.
- At 1280 x 900, 768 x 1024, and 390 x 844, there is no page-level horizontal
  overflow; mobile controls are at least 44 px.

The current in-app browser focused the native button and displayed a visible
focus ring, but did not deliver actual Tab/Enter/Space events to the application.
No application-specific keyboard handler was added; native-control behavior was
validated with automated regression tests. This tool limitation does not change
or close the separate Phase 7C.3 verification-incomplete gate described above.

The implementation, data contract, validation, and boundaries are documented in
`reports/dashboard_anomalies_view.md`.

### Governance

Status: complete. The separate, lazy-loaded **Governance** view presents the scope,
data quality, model lifecycle, analytical-readiness states, and responsible-use
boundaries of the committed aggregate artifacts in a single chart-free route,
without filling filter-dependent product views with development metadata. The
short **About the data** explanation in Overview was intentionally left unchanged;
Governance does not show the global filter toolbar and explains that its values
describe the committed data/model artifacts as a whole, not the active
filtered slice.

Delivered experience:

- The incident coverage of 2006-01-01–2025-12-31, Monday-aligned bucket coverage of
  2005-12-26–2025-12-29, latest complete week of 2025-12-22, and partial status of
  the final week beginning 2025-12-29 are shown with distinct meanings. It is
  explained that the pre-2006 bucket date does not imply that incidents occurred
  before 2006.
- The 10,071,507 clean source rows, 10,049,687 included aggregate-safe rows, and
  21,820 excluded rows are reconciled. Source-quality flags and aggregate-safe
  `UNKNOWN` dimension counts are presented as separate populations; overlapping
  quality categories are not summed, and `UNKNOWN` values are not assumed to have
  been excluded automatically.
- The model is displayed by its human-readable name and committed
  `duckdb_lag_ensemble_regressor` identifier; the model/artifact version is 1.
  The training-data range of 2005-12-26–2025-12-29, artifact-generation time of
  `2026-07-05T12:40:05.068774+00:00`, and fixed demo forecast week of 2026-01-05
  are separate fields. Because no independent training-completion time exists,
  **Not independently recorded** is shown; the artifact-generation time is not
  relabeled as "last trained."
- Overall backtest MAE/RMSE/weighted MAE/coverage information is shown only as
  historical model context; it is not presented as active-filter-specific error,
  a guarantee, or an uncertainty interval. It is visible that forecasts are point
  estimates and that no prediction interval is available.
- Hotspots, Anomalies, Forecast, Expected Change, and precinct-boundary readiness
  remain semantically distinct. Available, partial, empty, missing, invalid,
  stale, incompatible, and unavailable states are shown with text labels and
  sanitized reasons; missing output is not presented as zero or "healthy."
- It is explained that complaint records are not causal truth; that delays,
  revisions, and classification changes can affect aggregates; that a partial week
  cannot be compared directly with complete weeks; that the forecast is not live
  or real-time operational guidance; and that no drift monitor or general
  retraining cadence exists.
- Only aggregate analysis is used. There are no demographics, person-level scores,
  individual risk labels, or patrol/enforcement/deployment/intervention
  recommendations, and analytical-signal priority is not framed as policing
  priority.
- The four native navigation buttons retain their stable order, visible
  `aria-current` selection, skip-link target, and global filter state. Date,
  borough, precinct, offense, and law selections remain unchanged after a visit to
  Governance; the borough–precinct constraint and Reset behavior on filtered views
  are preserved. Mobile navigation uses a two-by-two grid, and native interaction
  targets are at least 44 px.

No new parallel browser artifact was produced for Governance. Only deterministic
aggregate-quality fields were added to the existing Overview metadata contract,
while separate artifact-generation and independent-training-time-unavailable
fields were added to the Forecast Map model contract. Canonical/public copies are
generated by the same builders; the TypeScript runtime projection reconciles these
contracts with the Map and official spatial artifacts in a fail-closed manner.
The implementation, data sources, failure behavior, validation, and actual
limitations are documented in `reports/dashboard_governance_view.md`.

## 12. Historical Technical Proposal and Delivered Architecture

The initial proposal was:

```text
Raw CSV
  -> Data cleaning pipeline
  -> Processed Parquet files
  -> Feature pipeline
  -> Forecast, hotspot, anomaly outputs
  -> API
  -> Dashboard
```

The delivered local architecture does not include an API or service process:

```text
Raw CSV (ignored local input)
  -> deterministic cleaning and aggregate builders
  -> ignored Parquet analytical artifacts and committed JSON manifests
  -> deterministic browser-safe contract builders
  -> committed aggregate-only dashboard artifacts
  -> local React/Vite dashboard
```

The tools below were exploratory options. They are retained as planning history,
not as uncompleted local requirements:

- Data processing: DuckDB, Polars, or PySpark
- Modeling: scikit-learn, LightGBM, XGBoost
- API: FastAPI
- Dashboard: React or Next.js
- Map: Mapbox GL, Deck.gl, or Leaflet
- Storage: start with Parquet, then move to Postgres/PostGIS if needed
- Experiment tracking: MLflow or a simple model-registry directory structure

## 13. Historical Repository Structure Proposal

This proposal also predates the delivered structure documented in `README.md`.
Missing proposal-only directories such as `src/api/` are not gaps in the local
product.

```text
data/
  raw/
  processed/
notebooks/
src/
  data/
  features/
  models/
  evaluation/
  api/
dashboard/
models/
reports/
```

## 14. Sprint Plan

The sprint list is a historical plan. Its product outcomes are complete where
implemented, while proposal-only API work is outside the delivered local scope;
none of the bullets below represents pending publication work.

### Sprint 1: Data Profiling

- Produce the data dictionary
- Perform missing-value analysis
- Run date and location quality checks
- Produce the initial data-quality report

Success criterion:

- The reliable, incomplete, and risky columns should be clearly identified.

### Sprint 2: Cleaning and Aggregation

- Produce the clean incident table
- Create the weekly area/crime-type aggregation
- Prepare summary metrics for the dashboard

Success criterion:

- The model and dashboard should be able to use the same cleaned table.

### Sprint 3: Initial Analytical Dashboard Prototype

- Trend charts
- Borough/precinct comparisons
- Crime-type distributions
- Initial map view

Success criterion:

- A dashboard prototype should support data exploration even without a model.

### Sprint 4: Baseline Forecast

- Implement baseline forecasting methods
- Perform backtesting
- Report the metrics
- Convert forecast outputs into dashboard format

Success criterion:

- Comparable baseline metrics should be available for next-week crime counts.

### Sprint 5: ML Forecast Model

- Build the feature pipeline
- Train the initial LightGBM/XGBoost model
- Compare it with the baselines
- Save the forecast results

Success criterion:

- The ML model should either perform meaningfully better than the baselines or be
  compared with them in an explainable way.

### Sprint 6: Hotspot and Anomaly

- Produce hotspot scores
- Define anomaly rules
- Provide data to the map and anomaly views

Success criterion:

- The dashboard should not only show the past; it should also highlight changes
  that warrant attention.

### Sprint 7: Product Hardening

- Build the API layer
- Improve dashboard filters
- Add model versioning
- Make data and model limitations visible

Success criterion:

- The project should reach a demo-ready, reproducible, and extensible MVP level.

## 15. Initial Tasks

The best first tasks are:

1. Create the `reports/` and `src/` directory structure
2. Write the data-quality/profiling script
3. Produce a sample profile and full-data profile from the raw CSV
4. Produce cleaned date, location, and crime-type columns
5. Create the weekly aggregation table
6. Run the first baseline forecast
7. Draw the dashboard wireframe

Initial technical milestone:

```text
Produce a clean weekly precinct/crime-type aggregation table from raw NYPD data.
```

Model or dashboard development should not be expanded before this milestone is
complete.

## 16. Success Metrics

Product success:

- Can users quickly understand the crime trend for a selected area and date range?
- Can the dashboard display increases and anomalies clearly?
- Do the map, tables, and charts use the same data definition?
- Can forecast results be compared with the baselines?

Model success:

- Does the ML model perform better than a naive baseline?
- Is the error rate controlled in low-volume areas?
- Does the model meaningfully capture the highest-volume aggregate segments in
  historical backtests?
- Are the model outputs explainable?

Data success:

- Is the cleaning pipeline reproducible?
- Are missing- and invalid-data rates reported?
- Can the same pipeline run when new data arrives?

## 17. Risks and Mitigations

### Data Quality

Risk: Date, location, and category fields may contain errors.

Mitigation: The data-quality report and cleaning rules must be required in the
first sprint.

### Ethics and Bias

Risk: Misuse of demographic fields could produce discriminatory outcomes.

Mitigation: Demographic fields must not be used in the initial model, and the
product must focus on area and time aggregation.

### False Confidence

Risk: Users may interpret a model forecast as certain fact.

Mitigation: The dashboard should present forecasts with prediction intervals
when the model supplies validated intervals. Otherwise it should present
validated historical error, an explicit interval-unavailable statement, and
explanatory text.

### Performance

Risk: A CSV with more than 10 million rows may be slow when used directly in the
dashboard or a notebook.

Mitigation: Processed Parquet tables and an aggregation layer should be used.

### Model Complexity

Risk: Developing a complex model too early may slow product progress.

Mitigation: Follow a baseline-first, ML-model-second approach.

## 18. Local Implementation Objective

The implemented local product, with the Phase 7C.3 practical verification gate
still open as documented above, is:

```text
NYC Crime Intelligence Dashboard
```

This product is a decision-support dashboard that cleans and analyzes
historical crime data, displays geographic and temporal trends, flags hotspot and
anomaly areas, produces short-term crime-volume forecasts, and presents all
outputs in an explainable manner.

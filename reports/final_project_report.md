# NYC Crime Intelligence — Final Project Report

Review date: `2026-07-18`

## Review basis

This report describes the reviewed repository snapshot and its committed
browser-safe artifacts. It distinguishes source coverage, data-derived dates,
artifact construction times, model evaluation windows, and the viewer clock.
The analytical results are a fixed retrospective repository demonstration; the
repository contains no API, scheduled refresh, update channel, or service
process.

The scripts under `src/` are the canonical build path. The two notebooks are
optional: the cleaning notebook delegates to the canonical cleaning script,
while the historical EDA notebook writes only to `.cache/eda/outputs` and does
not replace project artifacts.

## Project question and scope

The project asks three aggregate questions about reported NYPD complaints:

1. How does reported complaint volume vary by week, borough, precinct, offense
   type, and law category?
2. Which aggregate area/category combinations show retrospective concentration
   or unusually high already-observed counts relative to prior-only history?
3. For one fixed week, how does a transparent aggregate estimate compare with
   an explainable prior-eight-week baseline?

The unit of analysis is an aggregate time/area/category segment. The project
does not infer why complaints occurred, estimate an individual's behavior,
label people or neighborhoods as dangerous, locate a future incident, or
recommend policing action.

## Data sources and provenance

### Complaint source

The authoritative analytical source is the official NYC Open Data **NYPD
Complaint Data Historic** dataset, identifier `qgea-i56i`, attributed to the
New York City Police Department. The exact source identity and reproduction
limits are recorded in the
[complaint-source provenance note](../data/source/nyc_open_data/nypd_complaint_data_historic.md).

| Field | Reviewed value |
| --- | --- |
| Dataset page | [NYPD Complaint Data Historic](https://data.cityofnewyork.us/Public-Safety/NYPD-Complaint-Data-Historic/qgea-i56i) |
| Expected local path | `data/raw/NYPD_Complaint_Data_Historic.csv` |
| Byte size | `3,429,157,518` |
| CSV rows evaluated | `10,071,507` |
| SHA-256 | `759016def1c04aafaaeaa8e35c622d13abdd4af82a69f7b9e2b5549c08e47827` |
| Independent retrieval timestamp | Unavailable; it was not recorded |

The raw CSV is ignored by Git. Exact analytical reproduction requires source
bytes with the recorded checksum; a later portal export is a different source
snapshot even if its filename is unchanged. The cleaning review date and local
file modification time are not substitutes for a retrieval timestamp.

Complaint data reflects reports and recording practices. Delays, revisions,
under-reporting, classification changes, and policy changes can alter the
observed counts. Public access to the source does not make the records complete
causal truth.

### Precinct geometry source

Forecast polygons use a separate role-specific source: New York City
Department of City Planning **Police Precincts**, NYC Open Data identifier
`y76i-bdw7`, edition 26B, data date May 2026. The vendored GeoJSON has 78
`MultiPolygon` features and no complaint, person, address, or demographic
records. See the [spatial provenance note](../data/source/nyc_open_data/README.md)
and adjacent provenance JSON.

| Field | Reviewed value |
| --- | --- |
| Retrieved at UTC | `2026-07-12T18:35:09Z` |
| Portal rows updated at UTC | `2026-05-26T19:46:58Z` |
| Byte size | `3,842,773` |
| SHA-256 | `5210830afa9d0875b7a7c769edfc4d2ebe984a9ab1e36f3b7fad8508828172aa` |
| Feature coverage | 78 of 78 Forecast precinct keys |
| Named dataset-specific license | Not supplied by the portal |

The repository records a public-use compatibility assessment from official NYC
Open Data and DCP terms without inventing a license name. An alternate
77-feature endpoint that omitted precinct 123 was rejected.

## Cleaning and missing-data semantics

The canonical cleaning script reads the CSV columns as text, maps reviewed
null-like tokens to null, trims values and collapses repeated whitespace,
uppercases selected categories, parses dates with `%m/%d/%Y`, and uses safe
numeric casts. It preserves quality flags for audit.

A row enters weekly and monthly aggregates only when its canonical complaint
start date:

- parses successfully;
- is on or after `2006-01-01`; and
- is on or before the explicit review parameter `2026-07-04`.

Other conditions—missing dimensions, missing or invalid coordinates, an end
date before the start, or report chronology—are flagged but do not by
themselves remove an otherwise date-eligible row. Consequently:

| Population | Rows |
| --- | ---: |
| Source rows evaluated | 10,071,507 |
| Rows included in aggregates | 10,049,687 |
| Rows excluded by the date eligibility rule | 21,820 |

Quality flags overlap. There are 52,050 rows with at least one listed flag and
605 with more than one, so flag counts must not be summed or equated with the
21,820 exclusions.

Missing retained dimensions become literal `UNKNOWN` categories rather than
numeric zero: 10,065 aggregate-safe event rows for borough, 713 for precinct,
18,847 for offense, and zero for law category. A verified numeric zero remains zero;
missing, malformed, incompatible, or unavailable data is never converted to
zero. Victim and suspect demographic columns are excluded from the cleaned
modeling projection and model features.

The full semantics and reviewed quality counts are in the
[cleaning report](cleaning_report.md) and
[data-quality report](data_quality_report.md).

## Weekly aggregation and partial-week behavior

DuckDB `date_trunc('week', ...)` creates Monday-starting buckets. The aggregate
grain is:

```text
week_start × borough × precinct × offense_type × law_category
```

Counts are row counts of date-eligible source records. No deduplication claim is
made, and no person count is inferred.

| Time concept | Value |
| --- | --- |
| Eligible event-date coverage | `2006-01-01` through `2025-12-31` |
| Weekly bucket labels | `2005-12-26` through `2025-12-29` |
| Latest complete Monday bucket | `2025-12-22` |
| Final Monday bucket | `2025-12-29`, partial through Wednesday `2025-12-31` |

The first eligible event, Sunday `2006-01-01`, belongs to the bucket beginning
`2005-12-26`; that bucket label does not assert 2005 event coverage.

Missing segment-weeks are zero-filled only after a segment first appears.
Earlier history is not invented. The partial final bucket remains in the
weekly table and in the model training-data horizon. It is excluded from the
baseline backtest and anomaly scoring, but it supplies prior information to the
fixed forecast. This asymmetry is deliberate and is also a limitation: three
days of final-week data can depress lag-based inputs relative to a seven-day
week.

## Baseline forecasting

Phase 4 evaluates four deterministic, target-week-excluding rules for each
aggregate segment:

| Baseline | Formula and history requirement |
| --- | --- |
| Previous week | Count one week before the target; one prior week |
| Trailing four-week mean | Arithmetic mean of the four prior weekly counts; four prior weeks |
| Trailing eight-week mean | Arithmetic mean of the eight prior weekly counts; eight prior weeks |
| Previous-year same week | Count 52 weeks before the target; 52 prior weeks |

The implemented eight-week baseline is an arithmetic mean, not the weighted
average suggested in an early roadmap proposal. The selected baseline is
`trailing_8_week_mean`, chosen by overall MAE with the other recorded metrics
retained for context.

| Backtest result | Trailing eight-week mean |
| --- | ---: |
| Window | `2024-12-30` through `2025-12-22` |
| Predictions / segment-weeks | 435,942 / 437,144 |
| Coverage | 99.73% |
| MAE | 0.4929 |
| RMSE | 1.4128 |
| Actual-count-weighted MAE | 3.7023 |

See the [baseline model report](baseline_model_report.md) and committed baseline
manifest for borough, offense, and high-volume capture breakdowns.

## ML model identity, formula, features, versions, and evaluation

The Phase 5 implementation is not the roadmap's proposed LightGBM/XGBoost
model. It is a deterministic formula model implemented with the Python standard
library and DuckDB:

| Field | Value |
| --- | --- |
| Model identity | `duckdb_lag_ensemble_regressor` |
| Model version | 1 |
| Artifact version | 1 |
| Dependency mode | Python standard library plus DuckDB; no scikit-learn |
| Selection objective | Time-ordered validation RMSE |
| Persisted binary estimator | None; formula and parameters are in JSON |

The exact prediction formula is:

```text
max(
  0,
  shrinkage * (
    trailing_8_week_mean
    + alpha * (trailing_4_week_mean - trailing_8_week_mean)
    + beta * (lag_1_week_count - trailing_4_week_mean)
    + gamma * (lag_52_week_count - trailing_8_week_mean)
  )
)
```

Selected parameters are `alpha = 0.25`, `beta = 0.10`, `gamma = 0.05`, and
`shrinkage = 1.0`. The four formula inputs are the one-week lag, 52-week lag,
trailing-four-week arithmetic mean, and trailing-eight-week arithmetic mean.

The manifest also records a broader engineered audit context: year, month, ISO
week, quarter, week index; lags 1, 2, 4, 8, and 52; trailing four- and eight-week
mean, standard deviation, minimum, and maximum; prior segment count, total, and
mean; and the four segment identifiers. Those recorded columns are not all
formula inputs. Features use prior rows only, random splits are not used, and
missing lag/mean inputs fall back to prior segment history and then zero.

### Evaluation

| Evaluation | Window / result |
| --- | --- |
| Parameter validation | `2024-01-01` through `2024-12-23` |
| Validation MAE / RMSE / weighted MAE | 0.49776 / 1.42785 / 3.79574 |
| Held-out backtest | `2024-12-30` through `2025-12-22` |
| Backtest predictions / coverage | 437,144 / 100% |
| Backtest MAE / RMSE / weighted MAE | 0.4894 / 1.3943 / 3.6555 |

Compared with the selected baseline, the differences are small: MAE −0.0035,
RMSE −0.0185, and weighted MAE −0.0468. These are overall time-based backtest
summaries, not filter-specific guarantees. They are also manifest-level
summaries with different prediction coverage—435,942 baseline rows versus
437,144 ML rows—not a matched-row comparison, so the deltas are descriptive
rather than a clean like-for-like gain. The model emits point estimates and does
not emit prediction intervals. See the [ML model report](ml_model_report.md).

## Model lifecycle and fixed retrospective forecast horizon

Lifecycle fields must remain distinct:

| Field | Value and meaning |
| --- | --- |
| Training-data window | `2005-12-26` through `2025-12-29` |
| Training through | `2025-12-29`; a source-data horizon, not a completion time |
| Artifact generated | `2026-07-05T12:40:05.068774+00:00` |
| Independent training-completion timestamp | Unavailable; no independent timestamp was recorded |
| Fixed retrospective forecast horizon | Week beginning `2026-01-05` |

The forecast target precedes artifact construction, so the result is a fixed
retrospective demonstration. The Forecast Map's `generatedAtUtc` value,
`2025-12-31T00:00:00Z`, is a deterministic source-derived data date and must not
be relabeled as the model construction time. The artifact construction time
must not be relabeled as training completion.

The model starts with 8,466 aggregate segments. The browser-safe precinct
subset has 5,852 rows over 78 precincts; 2,614 source rows are withheld for
unmappable or borough-mismatched geography. This retains 69.123553% of rows and
99.617827% of predicted volume. Expected Change has a baseline for 5,848 rows;
four lack sufficient history. Of the available baselines, 3,051 are valid zero
values, so percentage change is undefined, while 2,797 rows have a percentage
change.

## Hotspots and anomalies

### Hotspots

The hotspot layer is a fixed retrospective snapshot with scoring end date
`2025-12-30`; the final source day is excluded. It compares a recent 30-day
count with a non-overlapping 365-day baseline ending `2025-10-01`, while 7- and
90-day counts supply recency context.

The composite score is:

```text
0.35 × density
+ 0.25 × baseline lift
+ 0.20 × share increase
+ 0.15 × recency
+ 0.05 × coordinate quality
```

Volume gates require at least 25 recent and 50 baseline complaints for precinct
groups and 8 recent and 8 baseline complaints for grid groups. The reviewed
output has 396 rows: 36 precinct and 360 grid signals, including 26 high or
critical signals.

Precinct display points are aggregate event-derived centroids; grid points are
0.01-degree cell centers derived after coordinate quality checks. Neither is an
exact complaint location or a substitute for the official administrative
polygons. The grid is not equal-area. Scores indicate aggregate concentration,
not causality, harm severity, danger, or action priority. Full details are in
the [hotspot methodology](hotspot_methodology.md).

### Anomalies

Anomalies are unusually high already-observed weekly aggregate counts. The
detector builds a zero-filled post-appearance panel and uses only prior weeks:
trailing 8- and 13-week means, 13-week standard deviation, and 26-week median
and median absolute deviation. A leakage-safe model backtest estimate is the
expected count when aligned; otherwise the prior-13-week mean is used.

The final partial week is excluded, so scoring ends `2025-12-22`. The method
requires adequate prior history and volume, at least four observed complaints,
and at least three complaints above expectation. The analytical output contains
89,362 flagged rows. The browser-safe contract retains 10,378 high/critical
rows; its default complete-week range contains 645. Anomaly scores are neither
probabilities nor forecasts. See the [anomaly methodology](anomaly_methodology.md).

## Dashboard views

| View | Meaning and behavior |
| --- | --- |
| Overview | Filtered observed totals, Monday-week trend, borough/offense/law comparisons, and concise aggregate signal context. Recent change uses up to four selected complete weeks against the directly preceding equal window; partial weeks are excluded from that comparison. |
| Map & Hotspots | The fixed `2025-12-30` concentration snapshot, aggregate points, methodology context, filters, and a complete map-independent list/detail path. It is not recomputed in the browser. |
| Forecast | Precinct-aggregated point estimates for `2026-01-05`, rendered with the reviewed 78-feature administrative geometry and mirrored in a complete list/detail path. Date filters gate compatibility; they do not generate other forecast weeks. |
| Expected Change | Forecast minus the prior-only trailing-eight-week arithmetic mean. Count and percentage states distinguish complete baseline coverage, missing history, and a valid zero baseline. |
| Anomalies | High/critical observed deviations with actual, expected, residual, score, source, severity, filters, and a complete native-button list/detail path. |
| Governance | Filter-independent source coverage, overlapping quality flags, retained `UNKNOWN` values, model identity and lifecycle, artifact readiness, limitations, safe provenance, and use boundaries. It omits the global filter toolbar but preserves filter state for the return to filter-aware views. |

The Forecast and hotspot base maps request CARTO raster tiles. Tile failure does
not remove vector polygons/points, filters, lists, or details. The spatial
loader applies a 120-day review window from the portal update timestamp. Edition
26B is accepted through `2026-09-23T19:46:58Z`; after that instant polygons are
withheld as stale until a reviewed source refresh, while Forecast list/detail
values remain accessible.

## Automated and practical verification

### Automated verification

The normal automated verification pass runs from the reviewed `main` tree. Python uses
the pinned project environment, and the dashboard is reinstalled from its
lockfile with `npm ci`; ignored raw and processed artifacts are used only by the
explicit full-data integration pass. Portability contracts construct temporary
repository roots, require stable POSIX-relative references in cleaning,
analytical-summary, baseline, ML, hotspot, and anomaly metadata, and reject any
reference that escapes its declared root. Clean-copy contracts separately reject
project-root leakage from tracked reports and browser-safe artifacts.

The normal verification command checks:

- all Python `test_*_contract.py` suites, using deterministic aggregate-only
  inputs and no raw/private data;
- relative Markdown targets, web-link syntax, and automated language markers;
- pinned requirements and declared Python/Node/npm ranges;
- notebook output/metadata, self-install, canonical-path, privacy, local-path,
  personal-identifier, secret, and tracked-artifact hygiene;
- `npm ci`, ESLint, all Vitest tests, and the TypeScript/Vite production build;
- `npm audit --omit=dev`;
- `git diff --check HEAD`; and
- port 4173 before and after the run.

On 2026-07-18, the combined full-data acceptance run completed on `main` with
no configured remote: the then-existing 129 Python contract tests, all three
full-data integration tests, ESLint, and all 214 Vitest tests across 15 files
passed; the TypeScript/Vite build transformed 2,365 modules. The subsequent
portable-path preflight hardening added four Python contracts without changing
frontend code or browser-safe artifacts; final Python discovery passed all 133
tests and the directly affected documentation/builder suites passed 43 tests.
The fresh `npm ci` install audited 278 packages with zero vulnerabilities, the
explicit production audit also reported zero vulnerabilities,
Markdown/language/privacy/path/notebook hygiene passed, `git diff --check HEAD`
passed, and port 4173 was free before and after verification.

On 2026-07-19, after adding the code-license and third-party-data boundary and
rewriting the shareable branch history, the normal verification command passed
all 135 Python contract tests and all 214 Vitest tests. ESLint and the
TypeScript/Vite production build passed, both dependency audits reported zero
vulnerabilities, `git diff --check HEAD` passed, and port 4173 was free before
and after the run. The history hygiene contract also confirmed that public
branch and tag history contains neither the raw complaint CSV path nor the
legacy output-bearing EDA notebook path, and no reachable blob exceeds 5 MiB.

That production build reported these raw/gzip sizes:

| Asset | Size |
| --- | ---: |
| HTML | 0.64 / 0.36 kB |
| Map CSS | 15.09 / 6.36 kB |
| Main CSS | 66.46 / 11.35 kB |
| Anomaly decoder JavaScript | 7.95 / 2.80 kB |
| JSX runtime JavaScript | 9.25 / 3.50 kB |
| Anomalies JavaScript | 10.09 / 3.12 kB |
| Governance JavaScript | 39.73 / 10.28 kB |
| Spatial-reference loader JavaScript | 39.86 / 11.38 kB |
| Map JavaScript | 190.14 / 54.24 kB |
| Main JavaScript | 219.61 / 68.81 kB |
| Overview charts JavaScript | 404.31 / 113.53 kB |

All tracked Markdown and notebook narrative also received an English-language
review. The offline contract rejects Turkish-specific characters and common
ASCII Turkish prose markers; all repository-local Markdown targets resolve,
and the finite external URL set was checked separately for reachability.

The explicit optional full-data integration suite uses ignored local aggregate,
model, and private cleaned artifacts to rebuild the Forecast Map, Map, Overview,
and compressed Overview cube contracts in temporary paths. All outputs compare
byte-for-byte with their committed browser-safe files. Each test fails with a
list of missing artifacts rather than skipping. With the reviewed local
full-data artifacts present, all three integration tests passed on 2026-07-18.

### Practical verification

Practical checks cover 1280 × 900, 768 × 1024, and 390 × 844 layouts; loading,
empty, invalid, incompatible, stale, network, and tile-failure states; map/list/
detail synchronization; zero and missing baselines; visible focus; overflow;
console output; and required data requests. The separate Phase 7C.3 keyboard
gate is recorded below and is not concealed by automated coverage.

## Reproducibility instructions

### Supported runtimes

- Canonical builders and normal contracts: Python 3.10–3.14 with DuckDB 1.5.4.
- Optional EDA direct dependencies: version-pinned for Python 3.11–3.13, the
  interpreter intersection supported by IPython, NumPy, SciPy, and PyArrow.
- `.python-version` selects 3.11.15, which lies in both ranges; the canonical
  suite was verified with that interpreter.
- DuckDB exactly 1.5.4 from `requirements.txt`.
- Node `^20.19.0 || ^22.13.0 || >=24.0.0`; `.nvmrc` selects 24.5.0.
- npm 10 or newer; the reviewed run uses 11.12.1.

### Dashboard from committed browser-safe artifacts

```bash
cd dashboard
npm ci
npm run dev -- --port 4173 --strictPort
```

The tracked files under `dashboard/public/data` are sufficient; raw and ignored
processed data are not required.

### Normal verification

From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
./scripts/verify_local.sh
```

### Full analytical rebuild

Place source bytes matching the reviewed checksum at
`data/raw/NYPD_Complaint_Data_Historic.csv`, activate the pinned environment,
and run:

```bash
python src/data/build_clean_dataset.py --as-of-date 2026-07-04
python src/analytics/build_dashboard_summary.py
python src/models/build_baseline_forecast.py
python src/models/build_ml_forecast.py
python src/analytics/build_hotspots.py
python src/analytics/build_anomalies.py
python src/analytics/build_dashboard_overview.py
python src/analytics/build_dashboard_map.py
python src/analytics/build_dashboard_forecast_map.py
python src/analytics/build_dashboard_precinct_spatial_reference.py
```

The source-dependent stages require substantial disk, memory, and time. The
explicit cleaning date is part of the reproduction contract. A different
source checksum or review date constitutes a different analytical snapshot and
must be documented as such.

After the rebuild, run:

```bash
./scripts/verify_local.sh --full-data
```

The optional EDA direct dependencies are separately version-pinned in
`requirements-eda.txt`. Its notebook outputs remain under `.cache`.

## Data and model limitations

- Complaint reports are affected by reporting behavior, delay, revision,
  under-reporting, classification, and policy change.
- The aggregate counts are row counts, not verified unique incidents, victims,
  harms, or causal effects.
- Missing dimensions retained as `UNKNOWN` can blur category comparisons.
- The final source week contains only Monday through Wednesday; it is used by
  lag features even though it is excluded from backtest and anomaly scoring.
- Zero-fill after first segment appearance assumes a missing aggregate row means
  zero; it cannot distinguish a true zero from upstream reporting absence.
- The model improvement over the selected baseline is small and is measured on
  one historical split.
- Baseline/ML metric deltas use different prediction coverage and are not a
  matched-row comparison.
- Formula inputs omit holidays, exogenous events, reporting-delay corrections,
  long-run structural breaks, and spatial spillover.
- Forecast values have no prediction intervals, calibration analysis, or
  filter-specific error estimates.
- No formal drift monitor, general retraining cadence, or model-age service
  threshold is defined.
- Browser forecast geography withholds 2,614 source rows that cannot be mapped
  safely to the reviewed precinct contract.
- Hotspot thresholds are fixed; 0.01-degree grid cells are unequal in area and
  no spatial smoothing or street-network model is applied.
- Precinct polygons depend on a reviewed quarterly source and become stale by
  the declared time rule; raster tiles depend on an external provider.

## Privacy and aggregate-only boundary

The raw complaint CSV and cleaned event parquet are ignored local build inputs.
They must not be committed or sent to the browser. Tracked reports, model
manifests, browser contracts, and analytical test fixtures are aggregate-only.
Negative hygiene tests contain only minimal synthetic prohibited-key probes,
not event records, so the rejection rules themselves are exercised. The
repository hygiene contracts reject tracked raw/processed tables, unsafe model
serializations, event-level JSON keys, personal paths, secrets, notebook event
displays, and saved notebook outputs.

Browser-facing data excludes complaint/source-row identifiers, names, exact
addresses, exact event coordinates, victim/suspect demographics, and
person-level attributes. Hotspot grid centers and precinct display centroids
are aggregate spatial summaries. Official precinct polygons are administrative
boundaries and contain no complaint records or inferred event points.

The model uses weekly counts and aggregate segment keys only. Demographic
fields are excluded from the cleaned modeling projection, baseline features,
ML features, hotspot/anomaly browser contracts, and dashboard filters.

## Responsible-use and prohibited-use boundary

Appropriate use is limited to transparent retrospective exploration of
aggregate reported-complaint patterns, methods, data quality, and model error.
Every signal requires the displayed time window, population, denominator,
baseline, and limitation context.

The following uses are prohibited by the project's design and documentation:

- person-level or demographic scoring;
- individual risk labels or behavior predictions;
- exact future-incident location claims;
- neighborhood danger, safety, worth, or blame labels;
- causal claims from complaint counts or model output;
- patrol, enforcement, deployment, intervention, or resource-allocation
  recommendations;
- treating hotspot/anomaly severity as offense seriousness or policing
  priority;
- automated adverse decisions; and
- presenting overall backtest errors as a guarantee for a selected filter.

## Genuinely unavailable information

| Information | Honest state |
| --- | --- |
| Raw complaint-source retrieval timestamp | Unavailable. No independent timestamp was recorded; file modification time and cleaning review date are not substitutes. |
| Independent model training-completion timestamp | Unavailable. Artifact construction time is a different field. |
| Prediction interval | Unavailable. The formula emits point estimates only. |
| Filter-specific model errors | Unavailable. Recorded metrics summarize the overall time-based backtest. |
| Expected Change percentage | Undefined for 3,051 valid zero baselines; unavailable for four rows without required prior history. |
| Named precinct-dataset license | Not supplied by the portal; only the documented public-use compatibility assessment is asserted. |
| Drift/retraining policy | No formal drift monitor, general cadence, or model-age threshold is defined. |

These gaps are not filled with inferred timestamps, fabricated intervals,
zeros, generic health labels, or guessed policy.

## Phase 7C.3 state

Phase 7C.3 is code-complete and automated-check complete, but
**verification-incomplete**. The official 78-feature precinct geometry,
deterministic builder, Python and browser validators, and Forecast/Expected
Change polygon rendering are implemented. Desktop, tablet, mobile, state,
tile-failure, precision, responsive, console, and network checks passed.

In the allowed in-app browser, native Precinct 14 and Precinct 40 controls
received focus and displayed the expected focus ring, but Tab/Enter/Space did
not activate them; `aria-pressed`, the Precinct 75 detail, and polygon selection
remained unchanged. Automated native-button coverage passes. No alternate
browser surface, direct event dispatch, raw protocol access, or synthetic state
mutation was used to claim success.

The single remaining Phase 7C.3 gate is one successful practical native-button
activation through an allowed in-app browser session. Until that observation
is recorded, the milestone must remain verification-incomplete. The detailed
evidence is in the
[Phase 7C.3 spatial rendering report](phase_7c3_precinct_spatial_rendering.md).

# NYC Crime Intelligence Dashboard

Phase 7A is a single-screen React and TypeScript Overview application. It reads a
compact, aggregate-only metadata contract and a gzip-compressed columnar weekly
cube from `public/data/`; the browser never receives complaint-level records.

## Refresh dashboard data

From the repository root, use the project Python environment:

```bash
.venv/bin/python src/analytics/build_dashboard_overview.py
```

The deterministic build writes the canonical processed Overview outputs and
copies the frontend-safe files to:

- `dashboard/public/data/overview.json`
- `dashboard/public/data/overview-cube.bin.gz`

Optional hotspot, anomaly, and forecast inputs are represented with an explicit
availability status. Missing optional outputs do not prevent observed trend
analysis from loading. Frontend-unsafe optional numerics, duplicate logical
keys, mixed/future hotspot snapshots, or forecast artifacts that do not align
with their manifest are withheld as invalid rather than coerced.

## Run locally

```bash
cd dashboard
npm install
npm run dev
```

Open the local URL printed by Vite. The application fetches `/data/overview.json`
and follows the cube path declared by that contract.

## Verify the frontend

```bash
npm run lint
npm test
npm run build
```

Vitest and Testing Library cover loading, actionable error, empty results,
missing optional inputs, borough-to-precinct constraints, filter-consistent
totals, and reset behavior. The production build is emitted to ignored `dist/`.

## Analytical and responsible-use boundaries

- Date controls select inclusive Monday-based weekly aggregate buckets.
- The trend baseline for each week uses only its prior eight weeks.
- Recent change compares up to four complete weeks with an equal prior window.
- Hotspots are a fixed current aggregate-concentration snapshot.
- Hotspot recent counts are compared with the historical rate normalized to the
  same recent-window duration, not with the raw full baseline-window total.
- Grid hotspot rows include an aggregate grid-cell label for unambiguous scanning.
- Anomalies are observed aggregate deviations from a documented expectation.
- Forecasts are future model estimates and are shown only with historical error
  context; publication also requires one strictly future model/week aligned to
  the ML manifest and matching metrics context. Error figures are overall model
  backtest values and are not recomputed for active filters. The current model
  does not provide prediction intervals.
- No event records, victim or suspect demographics, person-level scores, patrol
  recommendations, or enforcement recommendations are included.

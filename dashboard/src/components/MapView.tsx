import {
  AlertTriangle,
  ChevronDown,
  Crosshair,
  Database,
  Info,
  Layers3,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { filterMapHotspots } from '../data/filterMap'
import { aggregateForecastPrecincts, forecastCompatibility } from '../data/filterForecastMap'
import { loadMap } from '../data/loadMap'
import { loadForecastMap } from '../data/loadForecastMap'
import {
  loadPrecinctSpatialReference,
  PrecinctSpatialReferenceError,
  reconcilePrecinctSpatialReference,
  type PrecinctSpatialReferenceErrorCode,
} from '../data/loadPrecinctSpatialReference'
import type { ForecastMapContract, ForecastMapLoader, PrecinctForecast, PredictiveMode } from '../types/forecastMap'
import type {
  HotspotLayer,
  MapDataContract,
  MapHotspot,
  MapHotspotStatus,
  MapLoader,
} from '../types/map'
import type { OverviewFilters, OverviewMetadata } from '../types/overview'
import type {
  PrecinctSpatialReferenceContract,
  PrecinctSpatialReferenceLoader,
} from '../types/precinctSpatialReference'
import { formatDate, formatDecimal, formatInteger } from '../utils/format'
import { FilterToolbar } from './FilterToolbar'
import { HotspotMap } from './HotspotMap'
import {
  PrecinctForecastMap,
  type PredictiveTileStatus,
} from './PrecinctForecastMap'
import {
  createExpectedChangeScale,
  createForecastVolumeScale,
  formatPredictiveValue,
} from './precinctForecastScale'

export interface MapViewProps {
  metadata: OverviewMetadata
  filters: OverviewFilters
  onFilters: (filters: OverviewFilters) => void
  onReset: () => void
  mapLoader?: MapLoader
  forecastMapLoader?: ForecastMapLoader
  precinctSpatialReferenceLoader?: PrecinctSpatialReferenceLoader
}

type MapLoadState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; contract: MapDataContract }

type ForecastLoadState = { status: 'loading' } | { status: 'error' } | { status: 'ready'; contract: ForecastMapContract }
type SpatialLoadState =
  | { status: 'idle' | 'loading' }
  | { status: 'error'; code: PrecinctSpatialReferenceErrorCode }
  | { status: 'ready'; contract: PrecinctSpatialReferenceContract }
type AnalyticalMode = 'hotspots' | PredictiveMode

const LAYERS: Array<{ value: HotspotLayer; label: string; shortLabel: string }> = [
  { value: 'all', label: 'Show all hotspot layers', shortLabel: 'All' },
  { value: 'grid', label: 'Show grid cells', shortLabel: 'Grid' },
  { value: 'precinct', label: 'Show precinct markers', shortLabel: 'Precinct' },
]

function normalized(value: string): string {
  return value.trim().toLocaleLowerCase('en-US')
}

function severityClass(severity: string): string {
  const value = normalized(severity)
  return ['low', 'medium', 'high', 'critical'].includes(value) ? value : 'unknown'
}

function formatLift(value: number): string {
  return `${value > 0 ? '+' : ''}${formatDecimal(value)}%`
}

function SourceState({
  status,
  onRetry,
}: {
  status: Exclude<MapHotspotStatus, 'available'>
  onRetry: () => void
}) {
  const copy = {
    missing: {
      title: 'No hotspot data',
      body: 'No current snapshot is available. Try again later.',
    },
    invalid: {
      title: 'Hotspot data unavailable',
      body: 'The current snapshot could not be verified. Try reloading.',
    },
    stale: {
      title: 'Hotspot data out of date',
      body: 'Reload to check for a newer snapshot.',
    },
  }[status]

  return (
    <section className={`map-state-panel map-state-panel--${status}`} role="status">
      <ShieldAlert aria-hidden="true" size={26} />
      <div>
        <h2>{copy.title}</h2>
        <p>{copy.body}</p>
        <button type="button" onClick={onRetry}>
          <RefreshCw aria-hidden="true" size={15} />
          Reload
        </button>
      </div>
    </section>
  )
}

function HistoricalState({
  filters,
  metadata,
  contract,
}: {
  filters: OverviewFilters
  metadata: OverviewMetadata
  contract: MapDataContract
}) {
  const scoringEndDate = contract.hotspots.summary.scoringEndDate
  return (
    <section className="map-state-panel map-state-panel--historical" role="status">
      <Info aria-hidden="true" size={26} />
      <div>
        <h2>Historical hotspots unavailable</h2>
        <p>
          End week {formatDate(filters.endWeek)} is outside this map snapshot.
          Set it to {formatDate(metadata.dataRange.latestCompleteWeek)} or later
          {scoringEndDate ? ` to view ${formatDate(scoringEndDate)}` : ''}.
        </p>
      </div>
    </section>
  )
}

function LoadingMapState() {
  return (
    <section className="map-state-panel map-state-panel--loading" aria-busy="true">
      <div className="map-loading-status" role="status">
        <Database aria-hidden="true" size={20} />
        <div>
          <strong>Loading hotspots</strong>
          <span>Preparing the map.</span>
        </div>
      </div>
      <div className="map-loading-layout" aria-hidden="true">
        <div className="skeleton-block map-loading-canvas" />
        <div className="skeleton-block map-loading-detail" />
      </div>
    </section>
  )
}

function ErrorMapState({ retry }: { retry: () => void }) {
  return (
    <section className="map-state-panel map-state-panel--error" role="alert">
      <AlertTriangle aria-hidden="true" size={26} />
      <div>
        <h2>Map unavailable</h2>
        <p>Try loading the map again.</p>
        <button type="button" onClick={retry}>
          <RefreshCw aria-hidden="true" size={15} />
          Retry
        </button>
      </div>
    </section>
  )
}

function ContractMismatchState({
  mapEndDate,
  overviewEndDate,
  retry,
}: {
  mapEndDate: string
  overviewEndDate: string
  retry: () => void
}) {
  return (
    <section className="map-state-panel map-state-panel--mismatch" role="status">
      <Info aria-hidden="true" size={26} />
      <div>
        <h2>Map temporarily unavailable</h2>
        <p>
          Overview was updated {formatDate(overviewEndDate)}; the map was updated{' '}
          {formatDate(mapEndDate)}. Reload to synchronize them.
        </p>
        <button type="button" onClick={retry}>
          <RefreshCw aria-hidden="true" size={15} />
          Reload
        </button>
      </div>
    </section>
  )
}

function LayerControl({
  layer,
  counts,
  onLayer,
}: {
  layer: HotspotLayer
  counts: Record<HotspotLayer, number>
  onLayer: (layer: HotspotLayer) => void
}) {
  return (
    <div className="map-layer-control" role="group" aria-label="Hotspot layer">
      <span>
        <Layers3 aria-hidden="true" size={15} />
        Layer
      </span>
      {LAYERS.map((option) => (
        <button
          key={option.value}
          type="button"
          className={layer === option.value ? 'is-active' : undefined}
          aria-label={option.label}
          aria-pressed={layer === option.value}
          title={option.label}
          onClick={() => onLayer(option.value)}
        >
          {option.shortLabel}
          <small>{formatInteger(counts[option.value])}</small>
        </button>
      ))}
    </div>
  )
}

function HotspotDetail({
  hotspot,
  contract,
}: {
  hotspot: MapHotspot | null
  contract: MapDataContract
}) {
  const summary = contract.hotspots.summary
  if (!hotspot) {
    return (
      <aside className="hotspot-detail" aria-labelledby="hotspot-detail-title">
        <div className="hotspot-detail__heading">
          <h3 id="hotspot-detail-title">No hotspot selected</h3>
        </div>
        <p className="hotspot-detail__empty">
          No hotspots match the active filters and selected layer.
        </p>
      </aside>
    )
  }

  const recentLabel = summary.recentWindowDays
    ? `Recent (${summary.recentWindowDays} days)`
    : 'Recent count'
  const expectedLabel =
    summary.recentWindowDays
      ? `Expected (${summary.recentWindowDays} days)`
      : 'Expected count'

  return (
    <aside
      className="hotspot-detail"
      aria-labelledby="hotspot-detail-title"
      aria-live="polite"
    >
      <div className="hotspot-detail__heading">
        <div>
          <h3 id="hotspot-detail-title">{hotspot.locationLabel}</h3>
        </div>
        <span
          className={`severity-label severity-label--${severityClass(hotspot.severity)}`}
        >
          <span aria-hidden="true" />
          {hotspot.severity}
        </span>
      </div>
      <p className="hotspot-detail__context">
        {hotspot.borough}
        {hotspot.precinct ? ` · Precinct ${hotspot.precinct}` : ''} ·{' '}
        {hotspot.offenseType} · {hotspot.lawCategory}
      </p>
      <dl className="hotspot-detail__metrics">
        <div>
          <dt>{recentLabel}</dt>
          <dd>{formatInteger(hotspot.recentCount)}</dd>
        </div>
        {hotspot.expectedRecentCount !== null && (
          <div>
            <dt>{expectedLabel}</dt>
            <dd>{formatDecimal(hotspot.expectedRecentCount)}</dd>
          </div>
        )}
        {hotspot.liftPct !== null && (
          <div>
            <dt>Difference from expected</dt>
            <dd>{formatLift(hotspot.liftPct)}</dd>
          </div>
        )}
        <div>
          <dt>Signal score</dt>
          <dd>{formatDecimal(hotspot.score)}</dd>
        </div>
      </dl>
      <details className="data-context">
        <summary>
          <span>About hotspots</span>
          <ChevronDown aria-hidden="true" size={15} />
        </summary>
        <div className="data-context__body">
          <ul className="data-context__list">
            <li>
              Expected values scale the prior {summary.baselineWindowDays ?? 365} days
              to the same recent period.
            </li>
            <li>Grid cells and precinct markers are areas, not exact incident locations.</li>
            <li>Scores rank unusual concentration; they do not establish cause.</li>
          </ul>
        </div>
      </details>
    </aside>
  )
}

function HotspotRegister({
  rows,
  selectedId,
  onSelect,
}: {
  rows: MapHotspot[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  return (
    <section className="hotspot-register" aria-labelledby="hotspot-register-title">
      <div className="hotspot-register__heading">
        <div>
          <h3 id="hotspot-register-title">Hotspot list</h3>
        </div>
        <span aria-live="polite">{formatInteger(rows.length)} results</span>
      </div>
      {rows.length === 0 ? (
        <p className="hotspot-register__empty" role="status">
          No hotspots match this scope.
        </p>
      ) : (
        <ol className="hotspot-register__list">
          {rows.map((hotspot) => {
            const selected = hotspot.id === selectedId
            return (
              <li key={hotspot.id}>
                <button
                  type="button"
                  className={selected ? 'is-selected' : undefined}
                  aria-pressed={selected}
                  aria-label={`Select rank ${hotspot.rank} ${hotspot.grain} hotspot at ${hotspot.locationLabel}, ${hotspot.severity} severity`}
                  onClick={() => onSelect(hotspot.id)}
                >
                  <span className="hotspot-register__rank">#{hotspot.rank}</span>
                  <span className="hotspot-register__identity">
                    <strong>{hotspot.locationLabel}</strong>
                    <small>
                      {hotspot.grain} · {hotspot.offenseType} · {hotspot.lawCategory}
                    </small>
                  </span>
                  <span
                    className={`severity-label severity-label--${severityClass(hotspot.severity)}`}
                  >
                    <span aria-hidden="true" />
                    {hotspot.severity}
                  </span>
                  <span className="hotspot-register__score">
                    <small>Score</small>
                    {formatDecimal(hotspot.score)}
                  </span>
                </button>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}

function OperationalMap({
  contract,
  metadata,
  filters,
  layer,
  selectedId,
  onLayer,
  onSelect,
}: {
  contract: MapDataContract
  metadata: OverviewMetadata
  filters: OverviewFilters
  layer: HotspotLayer
  selectedId: string | null
  onLayer: (layer: HotspotLayer) => void
  onSelect: (id: string) => void
}) {
  const filtered = useMemo(
    () => filterMapHotspots(contract, metadata, filters, layer),
    [contract, filters, layer, metadata],
  )
  const selected =
    filtered.rows.find((hotspot) => hotspot.id === selectedId) ??
    filtered.rows[0] ??
    null
  const effectiveSelectedId = selected?.id ?? null
  const summary = contract.hotspots.summary
  const sourceEmpty = summary.rowCount === 0

  return (
    <section className="map-operational" aria-labelledby="map-operational-title">
      <div className="map-operational__heading">
        <div>
          <h2 id="map-operational-title">Hotspots</h2>
          <p>
            {summary.scoringEndDate
              ? `Snapshot ${formatDate(summary.scoringEndDate)}`
              : 'Snapshot date unavailable'}
          </p>
        </div>
        <LayerControl
          layer={layer}
          counts={filtered.layerCounts}
          onLayer={onLayer}
        />
      </div>

      {filtered.gridExcludedByPrecinct && (
        <div className="map-scope-notice" role="note">
          <Info aria-hidden="true" size={16} />
          <p>
            Grid cells are unavailable while a precinct is selected.
          </p>
        </div>
      )}

      {(sourceEmpty || filtered.rows.length === 0) && (
        <div className="map-empty-notice" role="status">
          <Crosshair aria-hidden="true" size={18} />
          <div>
            <strong>
              {sourceEmpty
                ? 'No hotspots available'
                : 'No hotspots match these filters'}
            </strong>
            <span>
              {sourceEmpty
                ? 'The current snapshot contains no signals.'
                : 'Adjust the filters or choose another layer.'}
            </span>
          </div>
        </div>
      )}

      <div className="map-workspace">
        <section className="map-canvas-panel" aria-labelledby="map-canvas-title">
          <h3 id="map-canvas-title" className="visually-hidden">Hotspot map</h3>
          <div className="map-severity-legend" aria-label="Hotspot severity key">
            <span>Severity</span>
            {(['low', 'medium', 'high', 'critical'] as const).map((severity) => (
              <span
                key={severity}
                className={`severity-label severity-label--${severity}`}
              >
                <span aria-hidden="true" />
                {severity}
              </span>
            ))}
          </div>
          <HotspotMap
            hotspots={filtered.rows}
            selectedId={effectiveSelectedId}
            onSelect={onSelect}
            gridSizeDegrees={summary.gridSizeDegrees}
            descriptionId="hotspot-map-description"
          />
          <p id="hotspot-map-description" className="visually-hidden">
            Markers represent aggregated areas. Use the hotspot list for keyboard navigation.
          </p>
        </section>

        <div className="map-side-stack">
          <HotspotDetail hotspot={selected} contract={contract} />
          <HotspotRegister
            rows={filtered.rows}
            selectedId={effectiveSelectedId}
            onSelect={onSelect}
          />
        </div>
      </div>
    </section>
  )
}

const signed = (value: number) => `${value > 0 ? '+' : ''}${formatPredictiveValue(value)}`

function ForecastDetail({ row, contract }: { row: PrecinctForecast | null; contract: ForecastMapContract }) {
  if (!row) return <aside className="hotspot-detail" aria-label="Forecast detail"><h3>No precinct selected</h3><p className="hotspot-detail__empty">No forecast rows match the active filters.</p></aside>
  const error=contract.model.historicalError
  return <aside className="hotspot-detail forecast-detail" aria-labelledby="forecast-detail-title" aria-live="polite">
    <div className="hotspot-detail__heading"><h3 id="forecast-detail-title">{row.borough} · Precinct {row.precinct}</h3></div>
    <p className="hotspot-detail__context">Expected aggregate reported-event volume · week of {formatDate(row.forecastWeek)}</p>
    <dl className="hotspot-detail__metrics">
      <div><dt>Forecast</dt><dd>{formatPredictiveValue(row.predictedCount)}</dd></div>
      <div><dt>Historical baseline</dt><dd>{row.historicalBaseline===null?'Unavailable':formatPredictiveValue(row.historicalBaseline)}</dd></div>
      <div><dt>Expected change</dt><dd>{row.expectedChangeCount===null?'Unavailable':`${row.direction} · ${signed(row.expectedChangeCount)}`}</dd></div>
      <div><dt>Expected change %</dt><dd>{row.historicalBaseline===0?'Not defined for a zero baseline':row.expectedChangePct===null?'Not available':`${signed(row.expectedChangePct)}%`}</dd></div>
    </dl>
    {row.baselineRows<row.totalRows && <p className="forecast-baseline-note" role="note">{row.baselineRows===0?'Historical baseline is unavailable for every contributing row':`Baseline coverage is partial (${row.baselineRows} of ${row.totalRows} contributing rows)`}; aggregate change is withheld rather than treating missing history as zero.</p>}
    <details className="data-context"><summary><span>Model and responsible use</span><ChevronDown aria-hidden="true" size={15}/></summary><div className="data-context__body">
      <p>{contract.model.name} v{contract.model.version}.</p>
      {error.status==='available' && error.mae!==undefined && error.rmse!==undefined && error.predictionCoveragePct!==undefined
        ? <p>Overall historical MAE {formatDecimal(error.mae)}, RMSE {formatDecimal(error.rmse)}{error.weightedMae!==undefined&&error.weightedMae!==null?`, weighted MAE ${formatDecimal(error.weightedMae)}`:''}; coverage {formatDecimal(error.predictionCoveragePct)}%. These are overall backtest errors, not filter-specific uncertainty.</p>
        : <p>Historical backtest error context is unavailable; the interface does not infer uncertainty from missing metrics.</p>}
      <p>No prediction interval is available.</p>
      <p>Point estimates describe aggregate reported-event volume, not certainty, individual behavior, a specific future incident location, or grounds for patrol or enforcement action.</p>
    </div></details>
  </aside>
}

type SpatialResolution =
  | { status: 'idle' | 'loading' }
  | { status: 'error'; code: PrecinctSpatialReferenceErrorCode }
  | { status: 'ready'; contract: PrecinctSpatialReferenceContract }

function resolveSpatialReference(
  state: SpatialLoadState,
  forecast: ForecastMapContract,
): SpatialResolution {
  if (state.status !== 'ready') return state
  try {
    return {
      status: 'ready',
      contract: reconcilePrecinctSpatialReference(state.contract, forecast),
    }
  } catch (error) {
    return {
      status: 'error',
      code:
        error instanceof PrecinctSpatialReferenceError
          ? error.code
          : 'invalid-contract',
    }
  }
}

function PredictiveLegend({
  rows,
  mode,
}: {
  rows: PrecinctForecast[]
  mode: PredictiveMode
}) {
  if (mode === 'forecast') {
    const scale = createForecastVolumeScale(rows)
    const [first, second, third] = scale.thresholds
    return (
      <div className="predictive-map-legend" role="group" aria-label="Forecast aggregate-volume scale">
        <strong>Expected aggregate volume</strong>
        <span><i className="forecast-volume-swatch forecast-volume-swatch--zero" aria-hidden="true" />0 (valid zero)</span>
        {scale.maximum > 0 ? <>
          <span><i className="forecast-volume-swatch forecast-volume-swatch--1" aria-hidden="true" />&gt;0–{formatPredictiveValue(first)}</span>
          <span><i className="forecast-volume-swatch forecast-volume-swatch--2" aria-hidden="true" />{formatPredictiveValue(first)}–{formatPredictiveValue(second)}</span>
          <span><i className="forecast-volume-swatch forecast-volume-swatch--3" aria-hidden="true" />{formatPredictiveValue(second)}–{formatPredictiveValue(third)}</span>
          <span><i className="forecast-volume-swatch forecast-volume-swatch--4" aria-hidden="true" />Above {formatPredictiveValue(third)}</span>
          <small>Four positive steps use the filtered 95th-percentile cap ({formatPredictiveValue(scale.maximum)}); values retain up to the contract's six decimal places in the legend, list, and detail.</small>
        </> : <small>No positive forecasts are present in this filtered scope.</small>}
      </div>
    )
  }

  const scale = createExpectedChangeScale(rows)
  return (
    <div className="predictive-map-legend" role="group" aria-label="Expected-change direction and magnitude scale">
      <strong>Expected change from baseline</strong>
      <span><i className="change-swatch change-swatch--below" aria-hidden="true" />Below baseline</span>
      <span><i className="change-swatch change-swatch--equal" aria-hidden="true" />Approximately equal (±0.000001)</span>
      <span><i className="change-swatch change-swatch--above" aria-hidden="true" />Above baseline</span>
      <span><i className="change-swatch change-swatch--unavailable" aria-hidden="true" />Baseline unavailable or partial</span>
      <small>Darker fill means larger absolute change on a symmetric filtered 95th-percentile domain (±{formatPredictiveValue(scale.magnitudeMaximum)}). Dashed outlines identify missing or partial baseline coverage.</small>
    </div>
  )
}

const SPATIAL_STATE_COPY: Record<
  PrecinctSpatialReferenceErrorCode,
  { title: string; body: string }
> = {
  'missing-artifact': {
    title: 'Precinct geography unavailable',
    body: 'The verified precinct boundary artifact is missing. Forecast values remain available in the complete list and detail.',
  },
  network: {
    title: 'Precinct geography could not load',
    body: 'The boundary artifact could not be retrieved. Forecast values remain available in the complete list and detail.',
  },
  stale: {
    title: 'Precinct geography out of date',
    body: 'The reviewed official boundary edition is past its quarterly refresh window. Forecast values remain available in the complete list and detail.',
  },
  'malformed-json': {
    title: 'Precinct geography invalid',
    body: 'The boundary response is malformed, so no polygons are drawn. Forecast values remain available in the complete list and detail.',
  },
  'unsupported-version': {
    title: 'Precinct geography version mismatch',
    body: 'This boundary contract version is not supported by the Forecast view. No polygons are drawn.',
  },
  'incompatible-identity': {
    title: 'Precinct geography identity mismatch',
    body: 'The boundary artifact does not identify the verified precinct spatial reference. No polygons are drawn.',
  },
  'invalid-provenance': {
    title: 'Precinct geography provenance invalid',
    body: 'Publisher, retrieval, checksum, or public-use metadata could not be verified. No polygons are drawn.',
  },
  'invalid-coordinate-reference': {
    title: 'Precinct coordinate reference invalid',
    body: 'The artifact does not declare the supported WGS84 longitude/latitude semantics. No polygons are drawn.',
  },
  'invalid-contract': {
    title: 'Precinct geography invalid',
    body: 'The boundary contract could not be verified. Forecast values remain available in the complete list and detail.',
  },
  'invalid-geometry': {
    title: 'Precinct geometry invalid',
    body: 'One or more polygon rings or coordinates are invalid. Partial geography is not drawn.',
  },
  'duplicate-location-key': {
    title: 'Duplicate precinct geography',
    body: 'A precinct is represented more than once. Ambiguous geography is not drawn.',
  },
  'unstable-feature-order': {
    title: 'Precinct geography ordering invalid',
    body: 'The spatial artifact is not in its required deterministic order. No polygons are drawn.',
  },
  'incomplete-coverage': {
    title: 'Precinct geography incomplete',
    body: 'The spatial artifact does not cover every published Forecast precinct. Partial geography is not drawn.',
  },
  'location-key-mismatch': {
    title: 'Precinct geography key mismatch',
    body: 'The spatial and Forecast precinct keys do not match exactly. No polygons are drawn.',
  },
  'forecast-incompatible': {
    title: 'Forecast and geography versions do not align',
    body: 'The Forecast and spatial contracts cannot be safely reconciled. Forecast values remain available in the complete list and detail.',
  },
}

function PredictiveMapCanvas({
  resolution,
  rows,
  mode,
  selectedId,
  onSelect,
  onRetry,
}: {
  resolution: SpatialResolution
  rows: PrecinctForecast[]
  mode: PredictiveMode
  selectedId: string | null
  onSelect: (id: string) => void
  onRetry: () => void
}) {
  const [tileStatus, setTileStatus] = useState<PredictiveTileStatus>('loading')

  if (resolution.status !== 'ready') {
    const loading = resolution.status === 'idle' || resolution.status === 'loading'
    let copy: { title: string; body: string }
    if (resolution.status === 'error') {
      copy = SPATIAL_STATE_COPY[resolution.code]
    } else {
      copy = {
        title: 'Loading precinct boundaries',
        body: 'The complete precinct list and detail remain available while verified geography loads.',
      }
    }
    return (
      <section
        className="map-canvas-panel forecast-canvas-neutral"
        aria-labelledby="forecast-canvas-title"
        aria-busy={loading || undefined}
        role="status"
      >
        <div>
          {loading ? <Database aria-hidden="true" size={34} /> : <ShieldAlert aria-hidden="true" size={34} />}
          <h3 id="forecast-canvas-title">{copy.title}</h3>
          <p>{copy.body}</p>
          {!loading && <button type="button" onClick={onRetry}><RefreshCw aria-hidden="true" size={15} />Reload boundaries</button>}
        </div>
      </section>
    )
  }

  return (
    <section className="map-canvas-panel predictive-map-panel" aria-labelledby="forecast-canvas-title">
      <h3 id="forecast-canvas-title" className="visually-hidden">
        {mode === 'forecast' ? 'Forecast precinct map' : 'Expected-change precinct map'}
      </h3>
      <div className="predictive-map-context">
        <PredictiveLegend rows={rows} mode={mode} />
        {tileStatus === 'error' && <p className="predictive-tile-notice" role="status">Base map tiles are unavailable. Verified precinct polygons and the list/detail remain usable.</p>}
      </div>
      <PrecinctForecastMap
        spatial={resolution.contract}
        rows={rows}
        mode={mode}
        selectedId={selectedId}
        onSelect={onSelect}
        descriptionId="predictive-map-description"
        onTileStatus={setTileStatus}
      />
      <p id="predictive-map-description" className="visually-hidden">
        Verified administrative precinct polygons represent aggregate expected values, not precise future incident locations. Color is repeated as text in the legend, list, and detail. Use the precinct list for keyboard selection and complete values.
      </p>
    </section>
  )
}

function PredictiveWorkspace({
  contract,
  metadata,
  filters,
  mode,
  selectedId,
  onSelect,
  spatialState,
  retrySpatial,
}: {
  contract: ForecastMapContract
  metadata: OverviewMetadata
  filters: OverviewFilters
  mode: PredictiveMode
  selectedId: string | null
  onSelect: (id: string) => void
  spatialState: SpatialLoadState
  retrySpatial: () => void
}) {
  const rows = useMemo(
    () => aggregateForecastPrecincts(contract, metadata, filters),
    [contract, metadata, filters],
  )
  const selected = rows.find((row) => row.id === selectedId) ?? rows[0] ?? null
  const total = rows.reduce((sum, row) => sum + row.predictedCount, 0)
  const spatialResolution = useMemo(
    () => resolveSpatialReference(spatialState, contract),
    [contract, spatialState],
  )
  return <section className="map-operational forecast-operational" aria-labelledby="map-operational-title">
    <div className="map-operational__heading"><div><h2 id="map-operational-title">{mode==='forecast'?'Forecast':'Expected change'}</h2><p>Week of {formatDate(contract.dimensions.forecastWeeks[0])} · {formatInteger(rows.length)} precincts · {mode==='forecast'?`${formatPredictiveValue(total)} expected aggregate reported events`:'compared with the prior-only historical baseline'}</p></div></div>
    {rows.length===0&&<div className="map-empty-notice" role="status"><Crosshair aria-hidden="true" size={18}/><div><strong>No forecast rows match these filters</strong><span>Adjust the categorical filters or reset the view.</span></div></div>}
    <div className="map-workspace">
      <PredictiveMapCanvas resolution={spatialResolution} rows={rows} mode={mode} selectedId={selected?.id??null} onSelect={onSelect} onRetry={retrySpatial}/>
      <div className="map-side-stack"><ForecastDetail row={selected} contract={contract}/><section className="hotspot-register" aria-labelledby="forecast-register-title"><div className="hotspot-register__heading"><h3 id="forecast-register-title">{mode==='forecast'?'Precinct forecast list':'Precinct expected-change list'}</h3><span aria-live="polite">{formatInteger(rows.length)} results</span></div><ol className="hotspot-register__list">{rows.map(row=>{
        const selectedRow=row.id===selected?.id
        const missingBaseline=row.baselineRows<row.totalRows
        const label=mode==='forecast'
          ? `Select precinct ${row.precinct}, ${formatPredictiveValue(row.predictedCount)} expected aggregate reported events${row.predictedCount===0?', valid zero forecast':''}`
          : `Select precinct ${row.precinct}, ${missingBaseline?'expected change unavailable':`${row.direction} baseline${row.expectedChangeCount===null?'':`, ${signed(row.expectedChangeCount)}`}`}`
        return <li key={row.id}><button type="button" className={selectedRow?'is-selected':undefined} aria-pressed={selectedRow} aria-label={label} onClick={()=>onSelect(row.id)}><span className="hotspot-register__rank">P{row.precinct}</span><span className="hotspot-register__identity"><strong>{row.borough} · Precinct {row.precinct}</strong><small>{mode==='forecast'?`${formatPredictiveValue(row.predictedCount)} expected aggregate reported events${row.predictedCount===0?' · valid zero':''}`:missingBaseline?`Change unavailable · ${row.baselineRows===0?'baseline missing':'partial baseline'}`:row.expectedChangeCount===null?'Change unavailable':`${row.direction} baseline · ${signed(row.expectedChangeCount)}`}</small></span><span className={`forecast-direction ${mode==='forecast'?'forecast-direction--volume':`forecast-direction--${row.direction.replace(' ','-')}`}`}>{mode==='forecast'?(row.predictedCount===0?'zero':'volume'):row.direction}</span></button></li>
      })}</ol></section></div>
    </div>
  </section>
}

function PredictiveState({ state, metadata, filters, retry, mode, selectedId, onSelect, spatialState, retrySpatial }: { state:ForecastLoadState; metadata:OverviewMetadata; filters:OverviewFilters; retry:()=>void; mode:PredictiveMode; selectedId:string|null; onSelect:(id:string)=>void; spatialState:SpatialLoadState; retrySpatial:()=>void }) {
  if(state.status==='loading') return <LoadingMapState/>
  if(state.status==='error') return <section className="map-state-panel map-state-panel--error" role="alert"><AlertTriangle aria-hidden="true" size={26}/><div><h2>Forecast unavailable</h2><p>The Forecast Map artifact could not be loaded or validated.</p><button type="button" onClick={retry}><RefreshCw aria-hidden="true" size={15}/>Retry</button></div></section>
  const c=state.contract, compatibility=forecastCompatibility(c,metadata,filters)
  if(c.forecast.status!=='available') return <section className={`map-state-panel map-state-panel--${c.forecast.status}`} role="status"><ShieldAlert aria-hidden="true" size={26}/><div><h2>{c.forecast.status==='missing'?'No forecast artifact':c.forecast.status==='invalid'?'Forecast artifact invalid':'Forecast artifact stale'}</h2><p>No forecast values are shown.</p></div></section>
  if(compatibility!=='compatible') return <section className="map-state-panel map-state-panel--historical" role="status"><Info aria-hidden="true" size={26}/><div><h2>{compatibility==='unsupported-date'?'Forecast unavailable for this historical selection':'Overview and Forecast dates do not align'}</h2><p>{compatibility==='forecast-older'?'Overview is newer than the Forecast observation horizon.':compatibility==='forecast-newer'?'Forecast is newer than Overview.':compatibility==='overview-older'?'Overview does not reach the Forecast observation horizon.':'The fixed next-week forecast is shown only when the selected range includes the latest complete source week.'}</p></div></section>
  if(c.forecast.isEmpty) return <section className="map-state-panel" role="status"><Info aria-hidden="true" size={26}/><div><h2>Forecast available but empty</h2><p>The valid artifact contains no forecast rows; this is not a zero forecast.</p></div></section>
  return <PredictiveWorkspace contract={c} metadata={metadata} filters={filters} mode={mode} selectedId={selectedId} onSelect={onSelect} spatialState={spatialState} retrySpatial={retrySpatial}/>
}

export default function MapView({
  metadata,
  filters,
  onFilters,
  onReset,
  mapLoader = loadMap,
  forecastMapLoader = loadForecastMap,
  precinctSpatialReferenceLoader = loadPrecinctSpatialReference,
}: MapViewProps) {
  const [loadKey, setLoadKey] = useState(0)
  const [state, setState] = useState<MapLoadState>({ status: 'loading' })
  const [layer, setLayer] = useState<HotspotLayer>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [mode, setMode] = useState<AnalyticalMode>('hotspots')
  const [forecastKey, setForecastKey] = useState(0)
  const [forecastState, setForecastState] = useState<ForecastLoadState>({status:'loading'})
  const [spatialRequested, setSpatialRequested] = useState(false)
  const [spatialKey, setSpatialKey] = useState(0)
  const [spatialState, setSpatialState] = useState<SpatialLoadState>({status:'idle'})

  useEffect(() => {
    let active = true
    mapLoader()
      .then((contract) => {
        if (active) setState({ status: 'ready', contract })
      })
      .catch(() => {
        if (active) setState({ status: 'error' })
      })
    return () => {
      active = false
    }
  }, [loadKey, mapLoader])

  useEffect(()=>{let active=true; forecastMapLoader().then(contract=>{if(active)setForecastState({status:'ready',contract})}).catch(()=>{if(active)setForecastState({status:'error'})});return()=>{active=false}},[forecastKey,forecastMapLoader])

  useEffect(() => {
    if (!spatialRequested) return
    let active = true
    precinctSpatialReferenceLoader()
      .then((contract) => {
        if (active) setSpatialState({ status: 'ready', contract })
      })
      .catch((error: unknown) => {
        if (!active) return
        setSpatialState({
          status: 'error',
          code:
            error instanceof PrecinctSpatialReferenceError
              ? error.code
              : 'network',
        })
      })
    return () => {
      active = false
    }
  }, [precinctSpatialReferenceLoader, spatialKey, spatialRequested])

  const retry = () => {
    setState({ status: 'loading' })
    setLoadKey((value) => value + 1)
  }
  const reset = () => {
    setLayer('all')
    setSelectedId(null)
    onReset()
  }
  const retrySpatial = () => {
    setSpatialRequested(true)
    setSpatialState({ status: 'loading' })
    setSpatialKey((value) => value + 1)
  }
  const showsCurrentSnapshot =
    filters.endWeek >= metadata.dataRange.latestCompleteWeek
  const overviewEndDate = metadata.dataRange.safeEventEndDate

  return (
    <main id="main-content" className="main-content map-view">
      <FilterToolbar
        metadata={metadata}
        filters={filters}
        onChange={onFilters}
        onReset={reset}
      />

      <div className="map-mode-control" role="group" aria-label="Map analytical mode">
        {([['hotspots','Hotspots'],['forecast','Forecast'],['change','Expected change']] as const).map(([value,label])=><button key={value} type="button" aria-pressed={mode===value} className={mode===value?'is-active':undefined} onClick={()=>{setMode(value);setSelectedId(null);if(value!=='hotspots'){if(!spatialRequested)setSpatialState({status:'loading'});setSpatialRequested(true)}}}>{label}</button>)}
      </div>

      {mode!=='hotspots' ? <PredictiveState state={forecastState} metadata={metadata} filters={filters} mode={mode} selectedId={selectedId} onSelect={setSelectedId} retry={()=>{setForecastState({status:'loading'});setForecastKey(v=>v+1)}} spatialState={spatialState} retrySpatial={retrySpatial}/> : state.status === 'loading' ? (
        <LoadingMapState />
      ) : state.status === 'error' ? (
        <ErrorMapState retry={retry} />
      ) : state.contract.dataRange.safeEventEndDate !== overviewEndDate ? (
        <ContractMismatchState
          mapEndDate={state.contract.dataRange.safeEventEndDate}
          overviewEndDate={overviewEndDate}
          retry={retry}
        />
      ) : state.contract.hotspots.status !== 'available' ? (
        <SourceState
          status={state.contract.hotspots.status}
          onRetry={retry}
        />
      ) : !showsCurrentSnapshot ? (
        <HistoricalState filters={filters} metadata={metadata} contract={state.contract} />
      ) : (
        <OperationalMap
          contract={state.contract}
          metadata={metadata}
          filters={filters}
          layer={layer}
          selectedId={selectedId}
          onLayer={setLayer}
          onSelect={setSelectedId}
        />
      )}

    </main>
  )
}

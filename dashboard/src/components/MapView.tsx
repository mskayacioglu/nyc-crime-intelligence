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
import { loadMap } from '../data/loadMap'
import type {
  HotspotLayer,
  MapDataContract,
  MapHotspot,
  MapHotspotStatus,
  MapLoader,
} from '../types/map'
import type { OverviewFilters, OverviewMetadata } from '../types/overview'
import { formatDate, formatDecimal, formatInteger } from '../utils/format'
import { FilterToolbar } from './FilterToolbar'
import { HotspotMap } from './HotspotMap'

export interface MapViewProps {
  metadata: OverviewMetadata
  filters: OverviewFilters
  onFilters: (filters: OverviewFilters) => void
  onReset: () => void
  mapLoader?: MapLoader
}

type MapLoadState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; contract: MapDataContract }

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

export default function MapView({
  metadata,
  filters,
  onFilters,
  onReset,
  mapLoader = loadMap,
}: MapViewProps) {
  const [loadKey, setLoadKey] = useState(0)
  const [state, setState] = useState<MapLoadState>({ status: 'loading' })
  const [layer, setLayer] = useState<HotspotLayer>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

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

  const retry = () => {
    setState({ status: 'loading' })
    setLoadKey((value) => value + 1)
  }
  const reset = () => {
    setLayer('all')
    setSelectedId(null)
    onReset()
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

      {state.status === 'loading' ? (
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

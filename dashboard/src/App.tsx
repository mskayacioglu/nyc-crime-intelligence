import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Crosshair,
  Database,
  Landmark,
  LayoutDashboard,
  Map as MapIcon,
  Minus,
  RefreshCw,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { aggregateObserved, aggregateSignals, defaultFilters } from './data/aggregateOverview'
import { loadOverview } from './data/loadOverview'
import { AttentionTable } from './components/AttentionTable'
import { FilterToolbar } from './components/FilterToolbar'
import { MetricCard, type MetricTone } from './components/MetricCard'
import { ErrorState, LoadingState } from './components/PageState'
import { SystemContext } from './components/SystemContext'
import type {
  OverviewBundle,
  OverviewFilters,
  OverviewLoader,
  OverviewMetadata,
  SignalView,
} from './types/overview'
import type { MapLoader } from './types/map'
import type { ForecastMapLoader } from './types/forecastMap'
import type { PrecinctSpatialReferenceLoader } from './types/precinctSpatialReference'
import {
  formatDate,
  formatDecimal,
  formatInteger,
  formatShortDate,
} from './utils/format'

const OverviewCharts = lazy(() => import('./components/OverviewCharts'))
const MapView = lazy(() => import('./components/MapView'))
const AnomaliesView = lazy(() => import('./components/AnomaliesView'))

interface AppProps {
  loader?: OverviewLoader
  mapLoader?: MapLoader
  forecastMapLoader?: ForecastMapLoader
  precinctSpatialReferenceLoader?: PrecinctSpatialReferenceLoader
}

type ApplicationView = 'overview' | 'map' | 'anomalies'

type LoadState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; bundle: OverviewBundle }

function AppNavigation({
  view,
  onView,
}: {
  view: ApplicationView
  onView: (view: ApplicationView) => void
}) {
  return (
    <nav className="view-navigation" aria-label="Dashboard views">
      <button
        type="button"
        className="view-navigation__item"
        aria-current={view === 'overview' ? 'page' : undefined}
        onClick={() => onView('overview')}
      >
        <LayoutDashboard aria-hidden="true" size={15} />
        Overview
      </button>
      <button
        type="button"
        className="view-navigation__item"
        aria-current={view === 'map' ? 'page' : undefined}
        onClick={() => onView('map')}
      >
        <MapIcon aria-hidden="true" size={15} />
        Map &amp; hotspots
      </button>
      <button
        type="button"
        className="view-navigation__item"
        aria-current={view === 'anomalies' ? 'page' : undefined}
        onClick={() => onView('anomalies')}
      >
        <AlertTriangle aria-hidden="true" size={15} />
        Anomalies
      </button>
      <span className="responsible-boundary">
        <ShieldAlert aria-hidden="true" size={14} />
        Area-level patterns only · not individual risk or enforcement guidance
      </span>
    </nav>
  )
}

function MapModuleLoading() {
  return (
    <main id="main-content" className="main-content" aria-busy="true">
      <div className="state-banner" role="status">
        <MapIcon aria-hidden="true" size={18} />
        <div>
          <strong>Opening hotspots</strong>
          <span>Preparing the map.</span>
        </div>
      </div>
      <div className="skeleton-block map-module-loading" aria-hidden="true" />
    </main>
  )
}

function AnomaliesModuleLoading() {
  return (
    <main id="main-content" className="main-content" aria-busy="true">
      <div className="state-banner" role="status">
        <AlertTriangle aria-hidden="true" size={18} />
        <div>
          <strong>Opening anomalies</strong>
          <span>Preparing observed aggregate signals.</span>
        </div>
      </div>
      <div className="skeleton-block anomalies-module-loading" aria-hidden="true" />
    </main>
  )
}

function skipLinkLabel(view: ApplicationView): string {
  if (view === 'overview') return 'Overview'
  if (view === 'map') return 'Map and hotspots'
  return 'Anomalies'
}

function AppHeader({
  metadata,
  state,
  onReload,
}: {
  metadata?: OverviewMetadata
  state: LoadState['status']
  onReload: () => void
}) {
  const isPartial = metadata?.dataRange.latestWeekIsPartial ?? false
  return (
    <header className="application-header">
      <div className="application-header__texture" aria-hidden="true" />
      <div className="application-header__inner">
        <div className="identity-block">
          <span className="identity-mark" aria-hidden="true">
            <Landmark size={21} />
          </span>
          <div>
            <h1>NYC Crime Intelligence</h1>
          </div>
        </div>
        <div className="header-status">
          <div
            className={`freshness-status freshness-status--${state}${isPartial ? ' freshness-status--partial' : ''}`}
          >
            {state === 'ready' ? (
              isPartial ? <AlertTriangle aria-hidden="true" size={15} /> : <CheckCircle2 aria-hidden="true" size={15} />
            ) : state === 'error' ? (
              <ShieldAlert aria-hidden="true" size={15} />
            ) : (
              <Activity aria-hidden="true" size={15} />
            )}
            <div>
              <span>
                {state === 'ready'
                  ? 'Data through'
                  : state === 'error'
                    ? 'Data unavailable'
                    : 'Connecting'}
              </span>
              <strong className="freshness-full">
                {metadata
                  ? `${formatDate(metadata.dataRange.safeEventEndDate)}${isPartial ? ' · partial week' : ''}`
                  : 'Pending'}
              </strong>
              <time
                className="freshness-mobile"
                dateTime={metadata?.dataRange.safeEventEndDate}
              >
                {metadata
                  ? `${metadata.dataRange.safeEventEndDate}${isPartial ? ' · partial' : ''}`
                  : 'Pending'}
              </time>
            </div>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onReload}
            aria-label="Reload dashboard data"
            data-tooltip="Reload data"
          >
            <RefreshCw aria-hidden="true" size={16} />
          </button>
        </div>
      </div>
    </header>
  )
}

function comparisonPresentation(comparison: ReturnType<typeof aggregateObserved>['comparison']) {
  if (!comparison) {
    return {
      value: 'Not available',
      detail: 'Select two complete weeks',
      tone: 'neutral' as MetricTone,
      Icon: Minus,
    }
  }
  const change = comparison.percentChange
  if (change === null) {
    return {
      value: 'No prior base',
      detail: `${comparison.windowWeeks}-week windows`,
      tone: 'neutral' as MetricTone,
      Icon: Minus,
    }
  }
  const increased = change > 0
  const decreased = change < 0
  return {
    value: `${change > 0 ? '+' : ''}${formatDecimal(change)}%`,
    detail: `${comparison.windowWeeks} weeks vs prior ${comparison.windowWeeks} · ${increased ? 'up' : decreased ? 'down' : 'flat'}`,
    tone: increased ? ('warning' as MetricTone) : ('analytical' as MetricTone),
    Icon: increased ? TrendingUp : decreased ? TrendingDown : Minus,
  }
}

function signalMetricDetail(signals: SignalView): {
  hotspot: string
  anomaly: string
  forecast: string
} {
  const hotspot = !signals.hotspots.available
    ? 'Unavailable'
    : !signals.hotspots.currentWindow
      ? 'Unavailable for historical dates'
      : `${signals.hotspots.critical} critical · ${signals.hotspots.high} high${signals.hotspots.scanDate ? ` · ${formatShortDate(signals.hotspots.scanDate)}` : ''}`

  const anomaly = !signals.anomalies.available
    ? 'Unavailable'
    : `${signals.anomalies.critical} critical · ${signals.anomalies.high} high`
  const forecast = !signals.forecast.currentWindow
    ? 'Unavailable for historical dates'
    : !signals.forecast.available
      ? 'Estimate unavailable'
      : `${signals.forecast.forecastWeek ? formatShortDate(signals.forecast.forecastWeek) : 'Next week'} · point estimate · no interval`
  return { hotspot, anomaly, forecast }
}

function severityTone({
  available,
  currentWindow = true,
  total,
  critical,
}: {
  available: boolean
  currentWindow?: boolean
  total: number
  critical: number
}): MetricTone {
  if (!available || !currentWindow || total === 0) return 'neutral'
  return critical > 0 ? 'critical' : 'warning'
}

function ReadyOverview({
  bundle,
  filters,
  onFilters,
  onReset,
}: {
  bundle: OverviewBundle
  filters: OverviewFilters
  onFilters: (filters: OverviewFilters) => void
  onReset: () => void
}) {
  const observed = useMemo(
    () => aggregateObserved(bundle.metadata, bundle.cube, filters),
    [bundle, filters],
  )
  const signals = useMemo(
    () => aggregateSignals(bundle.metadata, filters),
    [bundle.metadata, filters],
  )
  const comparison = comparisonPresentation(observed.comparison)
  const signalDetails = signalMetricDetail(signals)
  const hotspotValue = !signals.hotspots.available || !signals.hotspots.currentWindow
    ? 'Not shown'
    : formatInteger(signals.hotspots.total)
  const anomalyValue = !signals.anomalies.available
    ? 'Unavailable'
    : formatInteger(signals.anomalies.total)
  const forecastValue = signals.forecast.available && signals.forecast.predictedTotal !== null
    ? formatDecimal(signals.forecast.predictedTotal)
    : 'Not shown'
  const hotspotTone = severityTone(signals.hotspots)
  const anomalyTone = severityTone(signals.anomalies)
  const forecastTone: MetricTone =
    signals.forecast.available &&
    signals.forecast.currentWindow &&
    signals.forecast.predictedTotal !== null
      ? 'analytical'
      : 'neutral'

  return (
    <main id="main-content" className="main-content">
      <FilterToolbar
        metadata={bundle.metadata}
        filters={filters}
        onChange={onFilters}
        onReset={onReset}
      />

      {bundle.metadata.dataRange.latestWeekIsPartial && (
        <div className="quality-notice" role="note">
          <AlertTriangle aria-hidden="true" size={17} />
          <p>
            <strong>Latest week is partial.</strong> Comparisons end{' '}
            {formatDate(bundle.metadata.dataRange.latestCompleteWeek)}.
          </p>
        </div>
      )}

      {observed.isEmpty && (
        <div className="empty-notice" role="status">
          <BarChart3 aria-hidden="true" size={18} />
          <div>
            <strong>No results</strong>
            <span>Adjust the filters or reset the view.</span>
          </div>
        </div>
      )}

      <section className="metrics-grid" aria-label="Overview metrics" aria-live="polite">
        <MetricCard
          label="Reported events"
          value={formatInteger(observed.selectedTotal)}
          detail={`${formatDate(filters.startWeek)} — ${formatDate(filters.endWeek)}`}
          icon={Database}
          tone="neutral"
          testId="selected-total"
        />
        <MetricCard
          label="Recent change"
          value={comparison.value}
          detail={comparison.detail}
          icon={comparison.Icon}
          tone={comparison.tone}
          testId="recent-change"
        />
        <MetricCard
          label="Hotspots"
          value={hotspotValue}
          detail={signalDetails.hotspot}
          icon={Crosshair}
          tone={hotspotTone}
          testId="hotspot-summary"
        />
        <MetricCard
          label="Anomalies"
          value={anomalyValue}
          detail={signalDetails.anomaly}
          icon={AlertTriangle}
          tone={anomalyTone}
          testId="anomaly-summary"
        />
        <MetricCard
          label="Next-week estimate"
          value={forecastValue}
          detail={signalDetails.forecast}
          icon={Activity}
          tone={forecastTone}
          testId="forecast-summary"
        />
      </section>

      <Suspense
        fallback={<div className="skeleton-block charts-loading" role="status">Preparing charts…</div>}
      >
        <OverviewCharts view={observed} />
      </Suspense>

      <AttentionTable rows={signals.attention} />
      <SystemContext metadata={bundle.metadata} />
    </main>
  )
}

export default function App({ loader = loadOverview, mapLoader, forecastMapLoader, precinctSpatialReferenceLoader }: AppProps) {
  const [loadKey, setLoadKey] = useState(0)
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [filters, setFilters] = useState<OverviewFilters | null>(null)
  const [view, setView] = useState<ApplicationView>('overview')

  useEffect(() => {
    let active = true
    loader()
      .then((bundle) => {
        if (!active) return
        setFilters(defaultFilters(bundle.metadata))
        setState({ status: 'ready', bundle })
      })
      .catch(() => {
        if (active) setState({ status: 'error' })
      })
    return () => {
      active = false
    }
  }, [loader, loadKey])

  const reload = () => {
    setState({ status: 'loading' })
    setLoadKey((value) => value + 1)
  }
  const metadata = state.status === 'ready' ? state.bundle.metadata : undefined

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to {skipLinkLabel(view)}
      </a>
      <AppHeader metadata={metadata} state={state.status} onReload={reload} />
      <AppNavigation view={view} onView={setView} />
      {state.status === 'loading' ? (
        <LoadingState />
      ) : state.status === 'error' ? (
        <ErrorState retry={reload} />
      ) : filters ? (
        view === 'overview' ? (
          <ReadyOverview
            bundle={state.bundle}
            filters={filters}
            onFilters={setFilters}
            onReset={() => setFilters(defaultFilters(state.bundle.metadata))}
          />
        ) : view === 'map' ? (
          <Suspense fallback={<MapModuleLoading />}>
            <MapView
              metadata={state.bundle.metadata}
              filters={filters}
              onFilters={setFilters}
              onReset={() => setFilters(defaultFilters(state.bundle.metadata))}
              mapLoader={mapLoader}
              forecastMapLoader={forecastMapLoader}
              precinctSpatialReferenceLoader={precinctSpatialReferenceLoader}
            />
          </Suspense>
        ) : (
          <Suspense fallback={<AnomaliesModuleLoading />}>
            <AnomaliesView
              metadata={state.bundle.metadata}
              filters={filters}
              onFilters={setFilters}
              onReset={() => setFilters(defaultFilters(state.bundle.metadata))}
            />
          </Suspense>
        )
      ) : null}
    </div>
  )
}

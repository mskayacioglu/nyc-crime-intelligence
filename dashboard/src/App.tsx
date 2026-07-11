import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Crosshair,
  Database,
  Info,
  Landmark,
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
import type {
  OverviewBundle,
  OverviewFilters,
  OverviewLoader,
  OverviewMetadata,
  SignalView,
} from './types/overview'
import {
  formatDate,
  formatDecimal,
  formatInteger,
  formatShortDate,
} from './utils/format'

const OverviewCharts = lazy(() => import('./components/OverviewCharts'))

interface AppProps {
  loader?: OverviewLoader
}

type LoadState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; bundle: OverviewBundle }

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
            <p>Citywide aggregate operations</p>
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
                  ? 'Latest available data'
                  : state === 'error'
                    ? 'Data connection unavailable'
                    : 'Opening aggregate data'}
              </span>
              <strong>
                {metadata
                  ? `${formatDate(metadata.dataRange.safeEventEndDate)}${isPartial ? ' · partial week' : ''}`
                  : 'Status pending'}
              </strong>
            </div>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onReload}
            aria-label="Reload dashboard data"
            data-tooltip="Reload aggregate data"
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
      detail: 'Select at least two complete weeks',
      tone: 'neutral' as MetricTone,
      Icon: Minus,
    }
  }
  const change = comparison.percentChange
  if (change === null) {
    return {
      value: 'No prior base',
      detail: `${comparison.windowWeeks}-week observed windows`,
      tone: 'neutral' as MetricTone,
      Icon: Minus,
    }
  }
  const increased = change > 0
  const decreased = change < 0
  return {
    value: `${change > 0 ? '+' : ''}${formatDecimal(change)}%`,
    detail: `${comparison.windowWeeks} complete weeks vs prior ${comparison.windowWeeks} · ${increased ? 'increase' : decreased ? 'decrease' : 'no change'}`,
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
    ? signals.hotspots.reason ?? 'Optional hotspot output is unavailable'
    : !signals.hotspots.currentWindow
      ? 'Fixed current snapshot hidden for a historical date selection'
      : `${signals.hotspots.critical} critical · ${signals.hotspots.high} high${signals.hotspots.scanDate ? ` · scan ${signals.hotspots.scanDate}` : ''}${signals.hotspots.snapshotAgeDays === null ? '' : signals.hotspots.snapshotAgeDays === 0 ? ' · aligned to latest data date' : ` · ${signals.hotspots.snapshotAgeDays} data-day${signals.hotspots.snapshotAgeDays === 1 ? '' : 's'} behind latest event date`}`

  const anomaly = !signals.anomalies.available
    ? signals.anomalies.reason ?? 'Optional anomaly output is unavailable'
    : `${signals.anomalies.critical} critical · ${signals.anomalies.high} high in selected weeks`

  const errors = [
    signals.forecast.mae === null ? null : `MAE ${formatDecimal(signals.forecast.mae)}`,
    signals.forecast.rmse === null ? null : `RMSE ${formatDecimal(signals.forecast.rmse)}`,
    signals.forecast.weightedMae === null
      ? null
      : `weighted MAE ${formatDecimal(signals.forecast.weightedMae)}`,
    signals.forecast.coveragePct === null
      ? null
      : `${formatDecimal(signals.forecast.coveragePct)}% coverage`,
  ].filter(Boolean)
  const forecast = !signals.forecast.currentWindow
    ? 'Future horizon hidden for a historical date selection'
    : !signals.forecast.available
      ? signals.forecast.reason ?? 'Forecast or historical error context is unavailable'
      : `Future week ${signals.forecast.forecastWeek ?? 'not reported'} · ${signals.forecast.errorScope ?? 'overall historical backtest'}${
          signals.forecast.errorUnit ? ' · per segment-week' : ''
        }: ${errors.join(' · ')} · ${signals.forecast.errorFilterSemantics ?? 'Historical errors are not recomputed for active filters.'} · ${
          signals.forecast.limitations[0] ?? 'No uncertainty interval is supplied.'
        }`
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

const ANALYTICAL_ARTIFACTS = [
  { key: 'anomalyMetrics', label: 'Anomaly metrics' },
  { key: 'hotspotMetrics', label: 'Hotspot metrics' },
  { key: 'mlMetrics', label: 'ML forecast metrics' },
  { key: 'mlManifest', label: 'ML forecast manifest' },
  { key: 'baselineManifest', label: 'Baseline forecast manifest' },
] as const

function recordValue(record: unknown, key: string): string | null {
  if (!record || typeof record !== 'object') return null
  const value = (record as Record<string, unknown>)[key]
  return typeof value === 'string' || typeof value === 'number'
    ? String(value)
    : null
}

function statusLabel(status: string): string {
  const normalized = status.replaceAll('_', ' ')
  return normalized.charAt(0).toUpperCase() + normalized.slice(1)
}

function compactTimestamp(timestamp: string): string {
  return timestamp
    .replace('T', ' ')
    .replace(/\.\d+(?=Z$|[+-]\d{2}:\d{2}$)/, '')
}

function OverviewContext({ metadata }: { metadata: OverviewMetadata }) {
  const versions = Object.entries(metadata.versions).filter(
    ([key, value]) => key !== 'dashboardContract' && typeof value === 'object',
  )
  const availableVersions = versions.filter(
    ([, value]) => typeof value === 'object' && value.status === 'available',
  ).length
  const modelManifest = metadata.versions.mlManifest
  const modelVersion =
    modelManifest && typeof modelManifest === 'object'
      ? modelManifest.modelVersion ?? modelManifest.artifactVersion
      : null

  return (
    <section className="context-section" aria-labelledby="context-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Provenance and controls</p>
          <h2 id="context-title">Analytical context</h2>
          <p>Coverage, quality, version, and responsible-use information.</p>
        </div>
        <Info aria-hidden="true" size={18} />
      </div>
      <dl className="context-grid">
        <div>
          <dt>Covered event dates</dt>
          <dd>
            {formatDate(metadata.dataRange.safeEventStartDate)} —{' '}
            {formatDate(metadata.dataRange.safeEventEndDate)}
          </dd>
        </div>
        <div>
          <dt>Aggregate-safe records</dt>
          <dd>{formatInteger(metadata.dataQuality.aggregateSafeEventCount)}</dd>
          <small>{formatInteger(metadata.dataQuality.excludedEventCount)} excluded by cleaning contract</small>
        </div>
        <div>
          <dt>Output versions</dt>
          <dd>Overview contract v{metadata.versions.dashboardContract}</dd>
          <small>{availableVersions}/{versions.length} analytical version records available</small>
        </div>
        <div>
          <dt>Forecast artifact</dt>
          <dd>{modelVersion === null ? 'Not available' : `Model version ${String(modelVersion)}`}</dd>
          <small>Model estimate; no uncertainty interval is supplied</small>
        </div>
      </dl>
      <section
        className="artifact-provenance"
        aria-labelledby="artifact-provenance-title"
      >
        <div className="artifact-provenance__heading">
          <div>
            <p className="section-kicker">Analytical artifacts</p>
            <h3 id="artifact-provenance-title">Artifact provenance</h3>
          </div>
          <span>{availableVersions}/{ANALYTICAL_ARTIFACTS.length} available</span>
        </div>
        <ul className="artifact-provenance__list">
          {ANALYTICAL_ARTIFACTS.map(({ key, label }) => {
            const record = metadata.versions[key]
            const status = recordValue(record, 'status') ?? 'not supplied'
            const phase = recordValue(record, 'phase')
            const modelName = recordValue(record, 'modelName')
            const modelVersion = recordValue(record, 'modelVersion')
            const artifactVersion = recordValue(record, 'artifactVersion')
            const generatedAtUtc = recordValue(record, 'generatedAtUtc')
            const sourceFile = recordValue(record, 'sourceFile')
            const versionDetail = [
              phase,
              modelName ? `Model ${modelName}` : null,
              modelVersion
                ? `model v${modelVersion}`
                : artifactVersion
                  ? `artifact v${artifactVersion}`
                  : null,
            ].filter(Boolean)

            return (
              <li key={key}>
                <div className="artifact-provenance__item-heading">
                  <div>
                    <strong>{label}</strong>
                    <code>{key}</code>
                  </div>
                  <span
                    className={`artifact-status${status === 'available' ? ' artifact-status--available' : ''}`}
                  >
                    {statusLabel(status)}
                  </span>
                </div>
                <p className="artifact-provenance__version">
                  {versionDetail.length > 0
                    ? versionDetail.join(' · ')
                    : 'No phase or version metadata reported'}
                </p>
                <p className="artifact-provenance__meta">
                  {generatedAtUtc ? (
                    <span>
                      Generated{' '}
                      <time dateTime={generatedAtUtc}>
                        {compactTimestamp(generatedAtUtc)}
                      </time>
                    </span>
                  ) : (
                    <span>Generation time not reported</span>
                  )}
                  {sourceFile && <span>Source {sourceFile}</span>}
                </p>
              </li>
            )
          })}
        </ul>
      </section>
      <div className="responsible-use">
        <ShieldAlert aria-hidden="true" size={19} />
        <div>
          <h3>Responsible-use boundary</h3>
          <p>
            Aggregate trend intelligence only. No complaint-level records, suspect or
            victim demographics, person-level scores, patrol directives, or enforcement
            recommendations are included.
          </p>
          <ul>
            {metadata.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
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

      <section className="scope-strip" aria-label="Current analytical scope">
        <div>
          <span>Selected observed period</span>
          <strong>{formatDate(filters.startWeek)} — {formatDate(filters.endWeek)}</strong>
        </div>
        <div>
          <span>Latest complete week</span>
          <strong>{formatDate(bundle.metadata.dataRange.latestCompleteWeek)}</strong>
        </div>
        <div>
          <span>Count definition</span>
          <strong>Aggregate reported complaint events</strong>
        </div>
      </section>

      {bundle.metadata.dataRange.latestWeekIsPartial && (
        <div className="quality-notice" role="note">
          <AlertTriangle aria-hidden="true" size={17} />
          <p>
            <strong>Latest week is incomplete.</strong> It is available for freshness,
            but default recent-period comparisons stop at{' '}
            {formatDate(bundle.metadata.dataRange.latestCompleteWeek)}. This data-quality
            state is separate from crime-signal severity.
          </p>
        </div>
      )}

      {observed.isEmpty && (
        <div className="empty-notice" role="status">
          <BarChart3 aria-hidden="true" size={18} />
          <div>
            <strong>No aggregate records match these filters</strong>
            <span>Reset filters, choose another category, or expand the week range.</span>
          </div>
        </div>
      )}

      <section className="metrics-grid" aria-label="Overview metrics" aria-live="polite">
        <MetricCard
          label="Selected aggregate events"
          value={formatInteger(observed.selectedTotal)}
          detail={`${formatShortDate(filters.startWeek)} — ${formatShortDate(filters.endWeek)} · observed`}
          icon={Database}
          tone="neutral"
          testId="selected-total"
        />
        <MetricCard
          label="Recent-period change"
          value={comparison.value}
          detail={comparison.detail}
          icon={comparison.Icon}
          tone={comparison.tone}
          testId="recent-change"
        />
        <MetricCard
          label="Current hotspot snapshot"
          value={hotspotValue}
          detail={signalDetails.hotspot}
          icon={Crosshair}
          tone={hotspotTone}
          testId="hotspot-summary"
        />
        <MetricCard
          label="High-severity anomalies"
          value={anomalyValue}
          detail={signalDetails.anomaly}
          icon={AlertTriangle}
          tone={anomalyTone}
          testId="anomaly-summary"
        />
        <MetricCard
          label="Future forecast horizon"
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

      <div className="signal-semantics" role="note">
        <Info aria-hidden="true" size={17} />
        <p>
          <strong>Measure boundaries:</strong> observed counts are reported events;
          the gray trend line is a prior-only historical baseline; anomalies are
          unusual aggregate deviations; hotspots are a fixed current concentration
          snapshot; forecasts are future model estimates. Forecast totals follow
          compatible filters, while displayed error figures remain overall historical
          backtest context and are not recomputed for active filters.
        </p>
      </div>

      <AttentionTable rows={signals.attention} />
      <OverviewContext metadata={bundle.metadata} />

      <footer className="application-footer">
        <span>NYC Crime Intelligence · {bundle.metadata.application.phase}</span>
        <span>
          Data-date basis {formatDate(bundle.metadata.dataRange.safeEventEndDate)} ·
          contract {bundle.metadata.schemaVersion}
        </span>
      </footer>
    </main>
  )
}

export default function App({ loader = loadOverview }: AppProps) {
  const [loadKey, setLoadKey] = useState(0)
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [filters, setFilters] = useState<OverviewFilters | null>(null)

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
      <a className="skip-link" href="#main-content">Skip to Overview</a>
      <AppHeader metadata={metadata} state={state.status} onReload={reload} />
      {state.status === 'loading' ? (
        <LoadingState />
      ) : state.status === 'error' ? (
        <ErrorState retry={reload} />
      ) : filters ? (
        <ReadyOverview
          bundle={state.bundle}
          filters={filters}
          onFilters={setFilters}
          onReset={() => setFilters(defaultFilters(state.bundle.metadata))}
        />
      ) : null}
    </div>
  )
}

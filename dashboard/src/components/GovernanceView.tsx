import {
  AlertTriangle,
  CalendarRange,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Database,
  FileClock,
  Info,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  GovernanceContractError,
  decodeGovernanceForecast,
  decodeGovernanceMap,
  decodeGovernanceOverview,
  decodeGovernanceSpatial,
  governanceFailure,
} from '../data/decodeGovernance'
import { loadForecastMap } from '../data/loadForecastMap'
import { loadMap } from '../data/loadMap'
import { loadPrecinctSpatialReference } from '../data/loadPrecinctSpatialReference'
import type { ForecastMapContract, ForecastMapLoader } from '../types/forecastMap'
import type {
  GovernanceOverviewProjection,
  GovernanceReadinessStatus,
  GovernanceSourceResult,
} from '../types/governance'
import type { MapDataContract, MapLoader } from '../types/map'
import type { OverviewMetadata, SourceIssueCounts } from '../types/overview'
import type {
  PrecinctSpatialReferenceContract,
  PrecinctSpatialReferenceLoader,
} from '../types/precinctSpatialReference'
import { formatDate, formatDecimal, formatInteger } from '../utils/format'

interface GovernanceViewProps {
  metadata: OverviewMetadata
  mapLoader?: MapLoader
  forecastMapLoader?: ForecastMapLoader
  precinctSpatialReferenceLoader?: PrecinctSpatialReferenceLoader
}

type ArtifactState =
  | { status: 'loading' }
  | {
      status: 'ready'
      checkedAtUtc: string
      map: GovernanceSourceResult<MapDataContract>
      forecast: GovernanceSourceResult<ForecastMapContract>
      spatial: GovernanceSourceResult<PrecinctSpatialReferenceContract>
    }

interface ReadinessItem {
  id: string
  name: string
  status: GovernanceReadinessStatus
  description: string
  reason: string
}

const SOURCE_ISSUES: Array<{
  key: keyof Omit<
    SourceIssueCounts,
    | 'rowsWithAnyIssue'
    | 'rowsWithMultipleIssues'
    | 'maximumIssuesPerRow'
    | 'populationCount'
    | 'categoriesOverlap'
    | 'countsAreNonAdditive'
  >
  label: string
}> = [
  { key: 'missingOffense', label: 'Missing offense' },
  { key: 'missingBorough', label: 'Missing borough' },
  { key: 'missingPrecinct', label: 'Missing precinct' },
  { key: 'missingInvalidComplaintStartDate', label: 'Missing or invalid start date' },
  { key: 'implausiblyOldComplaintStartDate', label: 'Implausibly old start date' },
  { key: 'futureComplaintStartDate', label: 'Future start date' },
  { key: 'futureComplaintEndDate', label: 'Future end date' },
  { key: 'complaintEndBeforeStart', label: 'End date before start date' },
  { key: 'reportDateBeforeComplaintStart', label: 'Report date before start date' },
  { key: 'missingCoordinates', label: 'Missing coordinates' },
  { key: 'zeroCoordinates', label: 'Zero coordinates' },
  { key: 'coordinatesOutsideBroadNycBounds', label: 'Coordinates outside broad NYC bounds' },
  { key: 'invalidLawCategory', label: 'Invalid law category' },
]

const STATUS_LABEL: Record<GovernanceReadinessStatus, string> = {
  available: 'Available',
  partial: 'Partial',
  empty: 'Available · empty',
  missing: 'Missing',
  invalid: 'Invalid',
  stale: 'Stale',
  incompatible: 'Incompatible',
  unavailable: 'Unavailable',
}

function result<T>(operation: () => T, source: 'map' | 'forecast' | 'spatial'): GovernanceSourceResult<T> {
  try {
    return { status: 'ready', value: operation() }
  } catch (error) {
    return { status: 'error', failure: governanceFailure(error, source) }
  }
}

function artifactStatus(
  status: string,
  isEmpty: boolean,
): GovernanceReadinessStatus {
  if (status === 'available') return isEmpty ? 'empty' : 'available'
  if (
    status === 'missing' ||
    status === 'invalid' ||
    status === 'stale' ||
    status === 'incompatible'
  ) {
    return status
  }
  return 'unavailable'
}

function sourceFailureItem(
  id: string,
  name: string,
  description: string,
  resultValue: GovernanceSourceResult<unknown>,
): ReadinessItem | null {
  if (resultValue.status === 'ready') return null
  return {
    id,
    name,
    description,
    status: resultValue.failure.status,
    reason: resultValue.failure.reason,
  }
}

function readinessItems(
  core: GovernanceOverviewProjection,
  state: Extract<ArtifactState, { status: 'ready' }>,
): ReadinessItem[] {
  const mapFailure = sourceFailureItem(
    'hotspots',
    'Hotspots',
    'Retrospective aggregate concentration snapshot.',
    state.map,
  )
  const forecastFailure = sourceFailureItem(
    'forecast',
    'Forecast',
    'Fixed-horizon aggregate point estimates.',
    state.forecast,
  )
  const spatialFailure = sourceFailureItem(
    'spatial',
    'Precinct boundaries',
    'Official aggregate-only spatial reference.',
    state.spatial,
  )

  const hotspots: ReadinessItem = mapFailure ?? (() => {
    const contract = (state.map as Extract<typeof state.map, { status: 'ready' }>).value
    const status = artifactStatus(
      contract.hotspots.status,
      contract.hotspots.status === 'available' && contract.hotspots.rows.length === 0,
    )
    return {
      id: 'hotspots',
      name: 'Hotspots',
      description: 'Retrospective aggregate concentration snapshot.',
      status,
      reason:
        status === 'available'
          ? `${formatInteger(contract.hotspots.rows.length)} aggregate rows scored through ${formatDate(contract.hotspots.summary.scoringEndDate!)}; freshness is measured against the data horizon, not the viewer clock.`
          : status === 'empty'
            ? 'The valid hotspot artifact contains no rows; this is an empty result, not a zero signal.'
            : `The hotspot artifact is ${STATUS_LABEL[status].toLocaleLowerCase('en-US')}; no rows are treated as zero or available.`,
    }
  })()

  const anomalyStatus = core.anomalies.status === 'available'
    ? core.anomalies.isEmpty
      ? 'empty'
      : 'available'
    : core.anomalies.status
  const anomalies: ReadinessItem = {
    id: 'anomalies',
    name: 'Anomalies',
    description: 'Already-observed weekly aggregate deviations.',
    status: anomalyStatus,
    reason:
      core.anomalies.status === 'available'
        ? core.anomalies.isEmpty
          ? 'The valid anomaly source has no high or critical rows; this is not a zero anomaly.'
          : `${formatInteger(core.anomalies.sourceRowCount)} high or critical rows scored through ${formatDate(core.anomalies.scoringEndWeek)}.`
        : `The anomaly source is ${STATUS_LABEL[anomalyStatus].toLocaleLowerCase('en-US')}; no unavailable row is presented as an analytical signal.`,
  }

  let forecast: ReadinessItem
  let expectedChange: ReadinessItem
  if (forecastFailure) {
    forecast = forecastFailure
    expectedChange = {
      ...forecastFailure,
      id: 'expected-change',
      name: 'Expected Change',
      description: 'Model estimate minus the documented prior-only baseline.',
    }
  } else {
    const contract = (state.forecast as Extract<typeof state.forecast, { status: 'ready' }>).value
    const status = artifactStatus(contract.forecast.status, contract.forecast.isEmpty)
    forecast = {
      id: 'forecast',
      name: 'Forecast',
      description: 'Fixed-horizon aggregate point estimates.',
      status,
      reason:
        status === 'available'
          ? `${formatInteger(contract.forecast.summary.rowCount)} rows included in the committed browser-safe artifact for the fixed week of ${formatDate(contract.dimensions.forecastWeeks[0])}; not a live or rolling operational forecast.`
          : status === 'empty'
            ? 'The valid forecast artifact is empty; no total is inferred as zero.'
            : `The forecast artifact is ${STATUS_LABEL[status].toLocaleLowerCase('en-US')}; no prediction value is shown.`,
    }
    const changeAvailability = contract.availability.expectedChangeCount
    const changeStatus: GovernanceReadinessStatus =
      status !== 'available'
        ? status
        : changeAvailability === 'available'
          ? 'available'
          : changeAvailability === 'partial'
            ? 'partial'
            : changeAvailability === 'missing' ||
                changeAvailability === 'invalid' ||
                changeAvailability === 'stale'
              ? changeAvailability
              : 'unavailable'
    const summary = contract.baseline.summary
    expectedChange = {
      id: 'expected-change',
      name: 'Expected Change',
      description: 'Model estimate minus the documented prior-only baseline.',
      status: changeStatus,
      reason:
        changeStatus === 'available' || changeStatus === 'partial'
          ? `${formatInteger(summary.expectedChangeCountAvailableRowCount)} of ${formatInteger(summary.publishedRowCount)} included rows have a count change; ${formatInteger(summary.expectedChangePctAvailableRowCount)} have a percentage change. ${formatInteger(summary.zeroBaselineRowCount)} baselines are valid zero values, so their percentage change remains unavailable.`
          : changeStatus === 'empty'
            ? 'The valid forecast artifact contains no rows, so Expected Change is empty rather than zero or unavailable.'
            : 'Expected Change is unavailable because its validated baseline or forecast context is unavailable; missing history is not converted to zero.',
    }
  }

  const spatial: ReadinessItem = spatialFailure ?? (() => {
    const contract = (state.spatial as Extract<typeof state.spatial, { status: 'ready' }>).value
    return {
      id: 'spatial',
      name: 'Precinct boundaries',
      description: 'Official aggregate-only spatial reference.',
      status: 'available',
      reason: `${formatInteger(contract.coverage.featureCount)} complete precinct features; source retrieved ${contract.provenance.retrieval.retrievedAtUtc}. The documented quarterly-source TTL was checked against the viewer clock.`,
    }
  })()

  return [hotspots, anomalies, forecast, expectedChange, spatial]
}

function StatusLabel({ status }: { status: GovernanceReadinessStatus }) {
  const Icon = status === 'available'
    ? CheckCircle2
    : status === 'partial' || status === 'stale'
      ? AlertTriangle
      : ShieldAlert
  return (
    <span className={`governance-status governance-status--${status}`}>
      <Icon aria-hidden="true" size={15} />
      {STATUS_LABEL[status]}
    </span>
  )
}

function GovernanceInvalidState({ status }: { status: 'invalid' | 'incompatible' }) {
  const incompatible = status === 'incompatible'
  const reason = incompatible
    ? 'do not agree with the supported Governance contract.'
    : 'did not pass strict validation.'
  return (
    <main id="main-content" className="main-content governance-view">
      <section className="governance-state governance-state--invalid" role="alert">
        <ShieldAlert aria-hidden="true" size={28} />
        <div>
          <h2>Governance metadata is {incompatible ? 'incompatible' : 'invalid'}</h2>
          <p>
            The committed browser-safe coverage, quality, identity, or responsible-use fields {reason}{' '}
            No malformed value is presented as zero or available. Reload dashboard data
            to retry.
          </p>
        </div>
      </section>
    </main>
  )
}

function CoverageSection({ core }: { core: GovernanceOverviewProjection }) {
  return (
    <section className="governance-panel" aria-labelledby="governance-coverage-title">
      <div className="governance-panel__heading">
        <CalendarRange aria-hidden="true" size={19} />
        <div>
          <p className="section-kicker">Committed browser-safe observation scope</p>
          <h3 id="governance-coverage-title">Data coverage</h3>
        </div>
      </div>
      <dl className="governance-fact-grid governance-fact-grid--coverage">
        <div>
          <dt>Event-date coverage</dt>
          <dd>{formatDate(core.eventStartDate)} — {formatDate(core.eventEndDate)}</dd>
          <small>Dates of aggregate-safe reported complaint events</small>
        </div>
        <div>
          <dt>Weekly bucket range</dt>
          <dd>{formatDate(core.firstWeek)} — {formatDate(core.lastWeek)}</dd>
          <small>Monday bucket boundaries</small>
        </div>
        <div>
          <dt>Latest complete week</dt>
          <dd>{formatDate(core.latestCompleteWeek)}</dd>
          <small>Used for default comparisons</small>
        </div>
        <div>
          <dt>Latest observed week</dt>
          <dd>{formatDate(core.lastWeek)}</dd>
          <small>{core.latestWeekIsPartial ? 'Partial' : 'Complete'} weekly bucket</small>
        </div>
        <div>
          <dt>Source rows</dt>
          <dd>{formatInteger(core.sourceRowCount)}</dd>
          <small>All cleaned source rows evaluated</small>
        </div>
        <div>
          <dt>Included aggregate-safe rows</dt>
          <dd>{formatInteger(core.aggregateSafeEventCount)}</dd>
          <small>Included in committed browser-safe aggregate counts</small>
        </div>
        <div>
          <dt>Excluded rows</dt>
          <dd>{formatInteger(core.excludedEventCount)}</dd>
          <small>Excluded by aggregate eligibility checks</small>
        </div>
      </dl>
      <div className="governance-note" role="note">
        <Info aria-hidden="true" size={17} />
        <p>
          The first weekly bucket begins {formatDate(core.firstWeek)} because weeks use
          Monday boundaries; the first covered event is {formatDate(core.eventStartDate)}.
          The earlier bucket date does not claim an earlier event.
        </p>
      </div>
      {core.latestWeekIsPartial && (
        <div className="governance-warning" role="note">
          <AlertTriangle aria-hidden="true" size={17} />
          <p>
            <strong>Partial latest week.</strong> The week beginning {formatDate(core.lastWeek)}{' '}
            is incomplete and must not be compared directly with complete weeks.
            The latest complete bucket begins {formatDate(core.latestCompleteWeek)}.
          </p>
        </div>
      )}
    </section>
  )
}

function QualitySection({ core }: { core: GovernanceOverviewProjection }) {
  const issues = core.sourceIssueCounts
  const unknown = core.aggregateSafeUnknownCounts
  return (
    <section className="governance-panel" aria-labelledby="governance-quality-title">
      <div className="governance-panel__heading">
        <Database aria-hidden="true" size={19} />
        <div>
          <p className="section-kicker">Distinct populations and warnings</p>
          <h3 id="governance-quality-title">Data quality and missing data</h3>
        </div>
      </div>
      <h4>Source-level issue flags</h4>
      <dl className="governance-quality-grid">
        {SOURCE_ISSUES.map(({ key, label }) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{formatInteger(issues[key])}</dd>
          </div>
        ))}
      </dl>
      <div className="governance-warning" role="note">
        <AlertTriangle aria-hidden="true" size={17} />
        <p>
          <strong>Issue categories overlap and are not additive.</strong>{' '}
          {formatInteger(issues.rowsWithAnyIssue)} source rows have at least one listed
          flag; {formatInteger(issues.rowsWithMultipleIssues)} have more than one, with at
          most {formatInteger(issues.maximumIssuesPerRow)} flags on one row. These issue
          counts are not the excluded-row count.
        </p>
      </div>

      <h4>Aggregate-safe values retained as UNKNOWN</h4>
      <dl className="governance-fact-grid governance-fact-grid--unknown">
        <div><dt>Borough</dt><dd>{formatInteger(unknown.borough)}</dd></div>
        <div><dt>Precinct</dt><dd>{formatInteger(unknown.precinct)}</dd></div>
        <div><dt>Offense</dt><dd>{formatInteger(unknown.offense)}</dd></div>
        <div><dt>Law category</dt><dd>{formatInteger(unknown.lawCategory)}</dd></div>
      </dl>
      <p className="governance-explanation">
        These counts use the included aggregate-safe population, not the full source
        population above. Missing borough, precinct, or offense can be preserved as the
        literal aggregate label UNKNOWN. UNKNOWN does not mean the row was excluded, and a
        verified zero—such as the current law-category count—remains zero rather than
        “unavailable.”
      </p>
    </section>
  )
}

function ModelSection({ state }: { state: ArtifactState }) {
  if (state.status === 'loading') {
    return (
      <section className="governance-panel governance-panel--loading" aria-busy="true">
        <div className="governance-loading">
          <Clock3 aria-hidden="true" size={18} />
          <div><strong>Checking model lifecycle</strong><span>Validating the committed Forecast contract.</span></div>
        </div>
      </section>
    )
  }
  if (state.forecast.status === 'error') {
    return (
      <section className="governance-panel" aria-labelledby="governance-model-title">
        <div className="governance-panel__heading">
          <FileClock aria-hidden="true" size={19} />
          <h3 id="governance-model-title">Model identity and lifecycle</h3>
        </div>
        <div className="governance-inline-state" role="status">
          <StatusLabel status={state.forecast.failure.status} />
          <p>{state.forecast.failure.reason} Model dates and metrics are withheld.</p>
        </div>
      </section>
    )
  }
  const contract = state.forecast.value
  const model = contract.model
  if (model.status !== 'available') {
    return (
      <section className="governance-panel" aria-labelledby="governance-model-title">
        <div className="governance-panel__heading">
          <FileClock aria-hidden="true" size={19} />
          <h3 id="governance-model-title">Model identity and lifecycle</h3>
        </div>
        <div className="governance-inline-state" role="status">
          <StatusLabel status={model.status} />
          <p>{model.reason} No identity, timestamp, or metric is inferred.</p>
        </div>
      </section>
    )
  }
  const error = model.historicalError
  return (
    <section className="governance-panel" aria-labelledby="governance-model-title">
      <div className="governance-panel__heading">
        <FileClock aria-hidden="true" size={19} />
        <div>
          <p className="section-kicker">Fixed retrospective artifact context</p>
          <h3 id="governance-model-title">Model identity and lifecycle</h3>
        </div>
      </div>
      <dl className="governance-fact-grid governance-fact-grid--model">
        <div>
          <dt>Model</dt>
          <dd>DuckDB lag ensemble regressor</dd>
          <small className="governance-long-value">Contract identity: {model.name}</small>
        </div>
        <div><dt>Model version</dt><dd>{model.version}</dd></div>
        <div><dt>Artifact version</dt><dd>{model.artifactVersion}</dd></div>
        <div>
          <dt>Training-data window</dt>
          <dd>{formatDate(model.trainingStartWeek!)} — {formatDate(model.trainingThroughWeek!)}</dd>
          <small>Historical weekly inputs used by the artifact</small>
        </div>
        <div>
          <dt>Training data through</dt>
          <dd>{formatDate(model.trainingThroughWeek!)}</dd>
          <small>A data horizon, not a training-completion time</small>
        </div>
        <div>
          <dt>Independent last-training time</dt>
          <dd>Not independently recorded</dd>
          <small>{model.independentTrainingTime.reason}</small>
        </div>
        <div>
          <dt>Model artifact generated</dt>
          <dd className="governance-long-value">
            <time dateTime={model.artifactGeneratedAtUtc!}>{model.artifactGeneratedAtUtc}</time>
          </dd>
          <small>Artifact construction timestamp; not relabeled as “last trained”</small>
        </div>
        <div>
          <dt>Fixed forecast horizon</dt>
          <dd>Week of {formatDate(model.forecastWeek!)}</dd>
          <small>Repository/demo horizon, not a live current forecast</small>
        </div>
      </dl>

      <h4>Overall historical validation context</h4>
      {error.status === 'available' ? (
        <>
          <dl className="governance-validation-grid">
            <div><dt>MAE</dt><dd>{formatDecimal(error.mae!)}</dd></div>
            <div><dt>RMSE</dt><dd>{formatDecimal(error.rmse!)}</dd></div>
            <div><dt>Weighted MAE</dt><dd>{error.weightedMae === null ? 'Unavailable' : formatDecimal(error.weightedMae!)}</dd></div>
            <div><dt>Prediction coverage</dt><dd>{formatDecimal(error.predictionCoveragePct!)}%</dd></div>
          </dl>
          <p className="governance-explanation">
            These metrics cover {formatInteger(error.backtestRowCount!)} historical
            segment-weeks from {formatDate(error.backtestStartWeek!)} through
            {` ${formatDate(error.backtestEndWeek!)}`}. They are overall backtest context,
            not filter-specific errors, guarantees, or uncertainty intervals.
          </p>
        </>
      ) : (
        <div className="governance-inline-state" role="status">
          <StatusLabel status={error.status} />
          <p>Historical validation context is unavailable; no missing metric is displayed as zero.</p>
        </div>
      )}
      <div className="governance-warning" role="note">
        <AlertTriangle aria-hidden="true" size={17} />
        <p>
          Forecasts are point estimates only. No confidence or prediction interval is
          available, and the fixed historical/demo horizon must not be described as live,
          current, real-time, or operational guidance.
        </p>
      </div>
    </section>
  )
}

function ReadinessSection({
  core,
  state,
  onRetry,
}: {
  core: GovernanceOverviewProjection
  state: ArtifactState
  onRetry: () => void
}) {
  if (state.status === 'loading') {
    return (
      <section className="governance-panel governance-panel--loading" aria-busy="true">
        <div className="governance-loading" role="status">
          <Clock3 aria-hidden="true" size={18} />
          <div><strong>Checking analytical readiness</strong><span>Validating committed artifact status and alignment.</span></div>
        </div>
      </section>
    )
  }
  const items = readinessItems(core, state)
  const hasLoadFailure = state.map.status === 'error' || state.forecast.status === 'error' || state.spatial.status === 'error'
  return (
    <section className="governance-panel" aria-labelledby="governance-readiness-title">
      <div className="governance-panel__heading">
        <ShieldCheck aria-hidden="true" size={19} />
        <div>
          <p className="section-kicker">No generic health score</p>
          <h3 id="governance-readiness-title">Artifact and signal readiness</h3>
        </div>
      </div>
      <ul className="governance-readiness-list">
        {items.map((item) => (
          <li key={item.id}>
            <div className="governance-readiness-list__heading">
              <div><strong>{item.name}</strong><span>{item.description}</span></div>
              <StatusLabel status={item.status} />
            </div>
            <p>{item.reason}</p>
          </li>
        ))}
      </ul>
      <p className="governance-explanation">
        Hotspots describe retrospective concentration, Anomalies describe observed
        deviations, Forecast contains fixed-horizon point estimates, and Expected Change
        compares those estimates with a prior-only baseline. Availability or analytical
        priority is not a policing priority.
      </p>
      {hasLoadFailure && (
        <button type="button" className="governance-retry" onClick={onRetry}>
          <RefreshCw aria-hidden="true" size={15} />
          Retry artifact checks
        </button>
      )}
    </section>
  )
}

function ResponsibleUseSection() {
  return (
    <section className="governance-panel" aria-labelledby="governance-use-title">
      <div className="governance-panel__heading">
        <ShieldAlert aria-hidden="true" size={19} />
        <div>
          <p className="section-kicker">Decision-support boundaries</p>
          <h3 id="governance-use-title">Responsible use and limitations</h3>
        </div>
      </div>
      <div className="governance-limitations">
        <section aria-labelledby="governance-data-limits">
          <h4 id="governance-data-limits">Reported data is not causal truth</h4>
          <ul>
            <li>Counts describe reported complaint events; they do not establish causes or the full incidence of harm.</li>
            <li>Reporting delays, revisions, under-reporting, and classification or policy changes can affect aggregates.</li>
            <li>The latest partial week is not directly comparable with complete weeks.</li>
          </ul>
        </section>
        <section aria-labelledby="governance-model-limits">
          <h4 id="governance-model-limits">Model context is limited</h4>
          <ul>
            <li>The forecast is a fixed historical/repository demo horizon, not real-time operational guidance.</li>
            <li>Forecasts are point estimates without prediction intervals.</li>
            <li>Overall historical validation errors are context, not filter-specific guarantees.</li>
            <li>The model does not account for every holiday, exogenous event, reporting delay, or spatial spillover.</li>
            <li>No formal drift monitor, model-age threshold, or general retraining cadence is currently established.</li>
          </ul>
        </section>
        <section aria-labelledby="governance-action-limits">
          <h4 id="governance-action-limits">No person-level or enforcement use</h4>
          <ul>
            <li>Analysis is aggregate-only and uses no demographics or person-level scoring.</li>
            <li>No individual risk labels are produced.</li>
            <li>No patrol, enforcement, deployment, intervention, or operational allocation recommendation is produced.</li>
            <li>Signal status, severity, or analytical priority must not be framed as policing priority.</li>
          </ul>
        </section>
      </div>
    </section>
  )
}

function ProvenanceDisclosure({
  core,
  state,
}: {
  core: GovernanceOverviewProjection
  state: ArtifactState
}) {
  const forecast = state.status === 'ready' && state.forecast.status === 'ready'
    ? state.forecast.value
    : null
  const spatial = state.status === 'ready' && state.spatial.status === 'ready'
    ? state.spatial.value
    : null
  const checkedAtUtc = state.status === 'ready' ? state.checkedAtUtc : null
  return (
    <details className="governance-provenance">
      <summary>
        <span><Info aria-hidden="true" size={16} /><strong>Safe provenance and timestamp glossary</strong></span>
        <ChevronDown aria-hidden="true" size={16} />
      </summary>
      <div className="governance-provenance__body">
        <dl className="governance-provenance-grid">
          <div>
            <dt>Contract data-derived timestamp</dt>
            <dd><time dateTime={core.contractGeneratedAtUtc}>{core.contractGeneratedAtUtc}</time></dd>
            <small>Maximum aggregate-safe event date at midnight UTC; not build time</small>
          </div>
          <div>
            <dt>Model artifact generated</dt>
            <dd>{forecast?.model.artifactGeneratedAtUtc ?? 'Unavailable'}</dd>
            <small>Artifact construction; not an independent training-completion time</small>
          </div>
          <div>
            <dt>Spatial source retrieved</dt>
            <dd>{spatial?.provenance.retrieval.retrievedAtUtc ?? 'Unavailable'}</dd>
            <small>{spatial ? `${spatial.provenance.dataset.publisher}, edition ${spatial.provenance.dataset.edition}` : 'Optional source unavailable'}</small>
          </div>
          <div>
            <dt>Spatial source portal update</dt>
            <dd>{spatial?.provenance.retrieval.portalRowsUpdatedAtUtc ?? 'Unavailable'}</dd>
            <small>Starts the documented 120-day quarterly-source freshness window</small>
          </div>
          <div>
            <dt>Viewer check time</dt>
            <dd>{checkedAtUtc ?? 'Pending'}</dd>
            <small>Current viewer clock used only for the documented spatial TTL; never a data timestamp</small>
          </div>
          <div>
            <dt>Model identifier</dt>
            <dd>{forecast?.model.name ?? 'Unavailable'}</dd>
            <small>Allowlisted model identity; no raw manifest is exposed</small>
          </div>
        </dl>
      </div>
    </details>
  )
}

export default function GovernanceView({
  metadata,
  mapLoader = loadMap,
  forecastMapLoader = loadForecastMap,
  precinctSpatialReferenceLoader = loadPrecinctSpatialReference,
}: GovernanceViewProps) {
  const [loadKey, setLoadKey] = useState(0)
  const [artifacts, setArtifacts] = useState<ArtifactState>({ status: 'loading' })
  const core = useMemo(() => {
    try {
      return { status: 'ready' as const, value: decodeGovernanceOverview(metadata) }
    } catch (error) {
      return {
        status: 'error' as const,
        failureStatus:
          error instanceof GovernanceContractError ? error.status : ('invalid' as const),
      }
    }
  }, [metadata])

  useEffect(() => {
    if (core.status !== 'ready') return
    let active = true
    const checkedAt = new Date()
    Promise.allSettled([
      mapLoader(),
      forecastMapLoader(),
      precinctSpatialReferenceLoader(),
    ]).then(([mapSettled, forecastSettled, spatialSettled]) => {
      if (!active) return
      const mapResult: GovernanceSourceResult<MapDataContract> =
        mapSettled.status === 'fulfilled'
          ? result(() => decodeGovernanceMap(core.value, mapSettled.value), 'map')
          : { status: 'error', failure: governanceFailure(mapSettled.reason, 'map') }
      const forecastResult: GovernanceSourceResult<ForecastMapContract> =
        forecastSettled.status === 'fulfilled'
          ? result(() => decodeGovernanceForecast(core.value, forecastSettled.value), 'forecast')
          : { status: 'error', failure: governanceFailure(forecastSettled.reason, 'forecast') }
      const reconciledForecast = forecastResult.status === 'ready' ? forecastResult.value : null
      const spatialResult: GovernanceSourceResult<PrecinctSpatialReferenceContract> =
        spatialSettled.status === 'fulfilled'
          ? result(
              () => decodeGovernanceSpatial(reconciledForecast, spatialSettled.value, checkedAt),
              'spatial',
            )
          : { status: 'error', failure: governanceFailure(spatialSettled.reason, 'spatial') }
      setArtifacts({
        status: 'ready',
        checkedAtUtc: checkedAt.toISOString(),
        map: mapResult,
        forecast: forecastResult,
        spatial: spatialResult,
      })
    })
    return () => {
      active = false
    }
  }, [core, forecastMapLoader, loadKey, mapLoader, precinctSpatialReferenceLoader])

  if (core.status === 'error') {
    return <GovernanceInvalidState status={core.failureStatus} />
  }

  return (
    <main id="main-content" className="main-content governance-view">
      <section className="governance-introduction" aria-labelledby="governance-title">
        <div>
          <p className="section-kicker">Committed artifact accountability</p>
          <h2 id="governance-title">Governance</h2>
          <p>
            Coverage, data-quality warnings, model lifecycle, analytical readiness, and
            responsible-use limits for the committed browser-safe aggregate artifacts.
          </p>
        </div>
        <div className="governance-scope" role="note">
          <ShieldCheck aria-hidden="true" size={18} />
          <p>
            <strong>Dataset- and model-wide scope.</strong> These values describe the
            underlying committed browser-safe artifacts, not the current borough, precinct, offense,
            law-category, or date-filtered slice. Your global filters are preserved while
            this view is open.
          </p>
        </div>
      </section>

      <CoverageSection core={core.value} />
      <QualitySection core={core.value} />
      <ModelSection state={artifacts} />
      <ReadinessSection
        core={core.value}
        state={artifacts}
        onRetry={() => {
          setArtifacts({ status: 'loading' })
          setLoadKey((value) => value + 1)
        }}
      />
      <ResponsibleUseSection />
      <ProvenanceDisclosure core={core.value} state={artifacts} />
    </main>
  )
}

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import forecastArtifact from '../../public/data/forecast-map.json'
import mapArtifact from '../../public/data/map.json'
import overviewArtifact from '../../public/data/overview.json'
import spatialArtifact from '../../public/data/precinct-spatial-reference.json'
import { PrecinctSpatialReferenceError } from '../data/loadPrecinctSpatialReference'
import type { ForecastMapContract } from '../types/forecastMap'
import type { MapDataContract } from '../types/map'
import type { OverviewMetadata } from '../types/overview'
import type { PrecinctSpatialReferenceContract } from '../types/precinctSpatialReference'
import GovernanceView from './GovernanceView'

type GovernanceProps = ComponentProps<typeof GovernanceView>
type UnknownObject = Record<string, unknown>

function object(value: unknown): UnknownObject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Test fixture section is not an object.')
  }
  return value as UnknownObject
}

const metadata = (): OverviewMetadata =>
  structuredClone(overviewArtifact) as unknown as OverviewMetadata
const mapContract = (): MapDataContract =>
  structuredClone(mapArtifact) as unknown as MapDataContract
const forecastContract = (): ForecastMapContract =>
  structuredClone(forecastArtifact) as unknown as ForecastMapContract
const spatialContract = (): PrecinctSpatialReferenceContract =>
  structuredClone(spatialArtifact) as unknown as PrecinctSpatialReferenceContract

function renderGovernance(overrides: Partial<GovernanceProps> = {}) {
  const props: GovernanceProps = {
    metadata: metadata(),
    mapLoader: async () => mapContract(),
    forecastMapLoader: async () => forecastContract(),
    precinctSpatialReferenceLoader: async () => spatialContract(),
    ...overrides,
  }
  return render(<GovernanceView {...props} />)
}

function readinessItem(name: string): HTMLElement {
  const heading = screen.getByText(name, { selector: 'strong' })
  const item = heading.closest('li')
  if (!item) throw new Error(`Readiness item ${name} is missing.`)
  return item
}

function staleMap(): MapDataContract {
  const value = mapContract() as unknown as UnknownObject
  const hotspots = object(value.hotspots)
  hotspots.status = 'stale'
  hotspots.reason = 'The aggregate snapshot is behind its documented data horizon.'
  hotspots.rows = []
  const summary = object(hotspots.summary)
  Object.assign(summary, {
    rowCount: 0,
    scoringEndDate: null,
    snapshotAgeDays: null,
    recentWindowDays: null,
    baselineWindowDays: null,
    gridSizeDegrees: null,
    counts: { byGrain: [0, 0], bySeverity: [0, 0, 0, 0] },
  })
  return value as unknown as MapDataContract
}

function availableEmptyForecast(): ForecastMapContract {
  const value = forecastContract() as unknown as UnknownObject
  object(value.dataRange).supportedForecastWeeks = []
  const dimensions = object(value.dimensions)
  for (const key of ['forecastWeeks', 'boroughs', 'precincts', 'offenseTypes', 'lawCategories']) {
    dimensions[key] = []
  }
  object(object(value.filterIndex).precinctsByBorough).rows = []
  const forecast = object(value.forecast)
  forecast.rows = []
  forecast.isEmpty = true
  Object.assign(object(forecast.summary), {
    rowCount: 0,
    sourceRowCount: 0,
    sourceSegmentCount: 8466,
    modelSegmentCoveragePct: 0,
    withheldRowCount: 0,
    sourcePredictedTotal: null,
    predictedTotal: null,
    withheldPredictedTotal: null,
    rowCoveragePct: null,
    predictedVolumeCoveragePct: null,
    publishedPrecinctCount: 0,
    publishedBoroughCount: 0,
    unknownOffenseRowCount: 0,
    countsByBorough: [],
    zeroPredictionRowCount: 0,
    withheldReasonCounts: { boroughMismatch: 0, unmappableLocation: 0 },
  })
  const baseline = object(value.baseline)
  baseline.valueAvailability = 'unavailable'
  Object.assign(object(baseline.summary), {
    publishedRowCount: 0,
    baselineAvailableRowCount: 0,
    baselineUnavailableRowCount: 0,
    expectedChangeCountAvailableRowCount: 0,
    expectedChangePctAvailableRowCount: 0,
    zeroBaselineRowCount: 0,
  })
  Object.assign(object(value.availability), {
    forecastPointEstimates: 'empty',
    historicalBaseline: 'unavailable',
    expectedChangeCount: 'unavailable',
    expectedChangePct: 'unavailable',
  })
  return value as unknown as ForecastMapContract
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(new Date('2026-07-17T12:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('Governance view', () => {
  it('renders complete non-chart coverage, quality, lifecycle, and readiness context', async () => {
    renderGovernance()

    expect(
      screen.getByRole('heading', { name: 'Governance' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.getByText(/dataset- and model-wide scope/i).closest('[role="note"]')).toHaveTextContent(
      /not the current borough, precinct, offense, law-category, or date-filtered slice/i,
    )

    const coverage = screen
      .getByRole('heading', { name: 'Data coverage' })
      .closest('section')
    expect(coverage).not.toBeNull()
    expect(within(coverage!).getByText('Jan 1, 2006 — Dec 31, 2025')).toBeInTheDocument()
    expect(within(coverage!).getByText('Dec 26, 2005 — Dec 29, 2025')).toBeInTheDocument()
    expect(within(coverage!).getByText('10,071,507')).toBeInTheDocument()
    expect(within(coverage!).getByText('10,049,687')).toBeInTheDocument()
    expect(within(coverage!).getByText('21,820')).toBeInTheDocument()
    expect(within(coverage!).getByText(/partial latest week/i).closest('[role="note"]')).toHaveTextContent(
      /must not be compared directly with complete weeks/i,
    )
    expect(coverage).toHaveTextContent(/monday boundaries/i)
    expect(coverage).toHaveTextContent(/does not claim an earlier event/i)

    const quality = screen
      .getByRole('heading', { name: 'Data quality and missing data' })
      .closest('section')
    expect(quality).not.toBeNull()
    expect(within(quality!).getByText('18,907')).toBeInTheDocument()
    expect(within(quality!).getByText('10,078')).toBeInTheDocument()
    expect(within(quality!).getByText('771')).toBeInTheDocument()
    expect(within(quality!).getByText('18,847')).toBeInTheDocument()
    expect(within(quality!).getByText('10,065')).toBeInTheDocument()
    expect(within(quality!).getByText('713')).toBeInTheDocument()
    expect(quality).toHaveTextContent(/issue categories overlap and are not additive/i)
    expect(quality).toHaveTextContent(/issue counts are not the excluded-row count/i)
    expect(quality).toHaveTextContent(/unknown does not mean the row was excluded/i)
    expect(quality).toHaveTextContent(/verified zero.*remains zero rather than.*unavailable/i)

    await screen.findByText('Not independently recorded')
    const lifecycle = screen
      .getByRole('heading', { name: 'Model identity and lifecycle' })
      .closest('section')
    expect(lifecycle).not.toBeNull()
    expect(lifecycle).toHaveTextContent('DuckDB lag ensemble regressor')
    expect(lifecycle).toHaveTextContent('duckdb_lag_ensemble_regressor')
    expect(lifecycle).toHaveTextContent(/model version\s*1/i)
    expect(lifecycle).toHaveTextContent(/artifact version\s*1/i)
    expect(lifecycle).toHaveTextContent(/dec 26, 2005 — dec 29, 2025/i)
    expect(lifecycle).toHaveTextContent('2026-07-05T12:40:05.068774+00:00')
    expect(lifecycle).toHaveTextContent(/week of jan 5, 2026/i)
    expect(lifecycle).toHaveTextContent(/not a training-completion time/i)
    expect(lifecycle).toHaveTextContent(/overall backtest context, not filter-specific/i)
    expect(lifecycle).toHaveTextContent(/point estimates only/i)
    expect(lifecycle).toHaveTextContent(/no confidence or prediction interval/i)
    expect(lifecycle).toHaveTextContent(/fixed historical\/demo horizon/i)

    expect(within(readinessItem('Hotspots')).getByText('Available')).toBeInTheDocument()
    expect(readinessItem('Hotspots')).toHaveTextContent('396 aggregate rows')
    expect(within(readinessItem('Anomalies')).getByText('Available')).toBeInTheDocument()
    expect(readinessItem('Anomalies')).toHaveTextContent('10,378 high or critical rows')
    expect(within(readinessItem('Forecast')).getByText('Available')).toBeInTheDocument()
    expect(readinessItem('Forecast')).toHaveTextContent(/not a live or rolling operational forecast/i)
    expect(within(readinessItem('Expected Change')).getByText('Partial')).toBeInTheDocument()
    expect(readinessItem('Expected Change')).toHaveTextContent(
      /3,051 baselines are valid zero values, so their percentage change remains unavailable/i,
    )
    expect(within(readinessItem('Precinct boundaries')).getByText('Available')).toBeInTheDocument()
  })

  it('states the complete responsible-use boundary without framing signals as policing priority', async () => {
    renderGovernance()
    await screen.findByText('Not independently recorded')

    const limits = screen
      .getByRole('heading', { name: 'Responsible use and limitations' })
      .closest('section')
    expect(limits).not.toBeNull()
    expect(limits).toHaveTextContent(/reported complaint events.*do not establish causes/i)
    expect(limits).toHaveTextContent(/reporting delays, revisions, under-reporting/i)
    expect(limits).toHaveTextContent(/fixed historical\/repository demo horizon/i)
    expect(limits).toHaveTextContent(/point estimates without prediction intervals/i)
    expect(limits).toHaveTextContent(/not filter-specific guarantees/i)
    expect(limits).toHaveTextContent(/holiday, exogenous event, reporting delay, or spatial spillover/i)
    expect(limits).toHaveTextContent(/no formal drift monitor, model-age threshold, or general retraining cadence/i)
    expect(limits).toHaveTextContent(/aggregate-only and uses no demographics or person-level scoring/i)
    expect(limits).toHaveTextContent(/no individual risk labels/i)
    expect(limits).toHaveTextContent(/no patrol, enforcement, deployment, intervention/i)
    expect(limits).toHaveTextContent(/must not be framed as policing priority/i)
  })

  it('uses a native collapsed disclosure and exposes only allowlisted provenance', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderGovernance()
    await screen.findByText('Not independently recorded')

    const summaryText = screen.getByText('Safe provenance and timestamp glossary')
    const summary = summaryText.closest('summary')
    const disclosure = summaryText.closest('details')
    expect(summary).not.toBeNull()
    expect(disclosure).not.toBeNull()
    expect(disclosure).not.toHaveAttribute('open')

    await user.click(summary!)

    expect(disclosure).toHaveAttribute('open')
    summary!.focus()
    expect(summary).toHaveFocus()
    expect(disclosure).toHaveTextContent(/contract data-derived timestamp/i)
    expect(disclosure).toHaveTextContent('2025-12-31T00:00:00Z')
    expect(disclosure).toHaveTextContent(/artifact construction; not an independent training-completion time/i)
    expect(disclosure).toHaveTextContent(/current viewer clock used only for the documented spatial ttl/i)
    expect(disclosure).not.toHaveTextContent(/\/Users\/|\/home\/|complaints_clean\.parquet/i)
  })

  it('shows honest loading, sanitized failure, and native retry recovery states', async () => {
    const never = new Promise<MapDataContract>(() => undefined)
    const loading = renderGovernance({ mapLoader: () => never })

    expect(screen.getByText('Checking model lifecycle')).toBeInTheDocument()
    expect(screen.getByText('Checking analytical readiness')).toBeInTheDocument()
    expect(screen.getByText('Checking model lifecycle').closest('[aria-busy="true"]')).not.toBeNull()
    expect(screen.getByText('Checking analytical readiness').closest('[role="status"]')).not.toBeNull()
    expect(screen.getAllByRole('status')).toHaveLength(1)
    loading.unmount()

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    const mapLoader = vi
      .fn<() => Promise<MapDataContract>>()
      .mockRejectedValueOnce(
        new Error('/Users/example/private/map.json returned token=secret'),
      )
      .mockResolvedValue(mapContract())
    renderGovernance({ mapLoader })

    const retry = await screen.findByRole('button', {
      name: 'Retry artifact checks',
    })
    expect(within(readinessItem('Hotspots')).getByText('Unavailable')).toBeInTheDocument()
    expect(readinessItem('Hotspots')).toHaveTextContent(
      /could not be loaded or validated/i,
    )
    expect(document.body).not.toHaveTextContent(/Users|token=secret|private\/map\.json/i)

    await user.click(retry)

    await waitFor(() => expect(mapLoader).toHaveBeenCalledTimes(2))
    await waitFor(() =>
      expect(within(readinessItem('Hotspots')).getByText('Available')).toBeInTheDocument(),
    )
    expect(screen.queryByRole('button', { name: 'Retry artifact checks' })).not.toBeInTheDocument()
  })

  it('keeps available, missing, invalid, stale, and incompatible signals distinct', async () => {
    const value = metadata() as unknown as UnknownObject
    object(object(value.signals).anomalies).status = 'invalid'
    object(object(value.signals).anomalies).reason =
      'The anomaly artifact failed its strict validation.'
    object(object(value.signals).anomalies).rows = []
    const overviewHotspots = object(object(value.signals).hotspots)
    overviewHotspots.status = 'stale'
    overviewHotspots.reason =
      'The hotspot snapshot is behind its documented data horizon.'
    overviewHotspots.rows = []
    const forecast = forecastContract() as unknown as UnknownObject
    object(forecast.model).artifactGeneratedAtUtc = '2026-07-05T12:41:05+00:00'

    renderGovernance({
      metadata: value as unknown as OverviewMetadata,
      mapLoader: async () => staleMap(),
      forecastMapLoader: async () => forecast as unknown as ForecastMapContract,
      precinctSpatialReferenceLoader: async () => {
        throw new PrecinctSpatialReferenceError(
          'missing-artifact',
          '/Users/example/private/spatial.json is missing',
        )
      },
    })

    await screen.findByRole('button', { name: 'Retry artifact checks' })
    expect(within(readinessItem('Hotspots')).getByText('Stale')).toBeInTheDocument()
    expect(within(readinessItem('Anomalies')).getByText('Invalid')).toBeInTheDocument()
    expect(within(readinessItem('Forecast')).getByText('Incompatible')).toBeInTheDocument()
    expect(within(readinessItem('Expected Change')).getByText('Incompatible')).toBeInTheDocument()
    expect(within(readinessItem('Precinct boundaries')).getByText('Missing')).toBeInTheDocument()
    expect(document.body).not.toHaveTextContent(/Users|private\/spatial\.json/i)
  })

  it('keeps an available-empty Forecast and Expected Change distinct from unavailable', async () => {
    renderGovernance({ forecastMapLoader: async () => availableEmptyForecast() })

    await screen.findByText('Not independently recorded')
    expect(within(readinessItem('Forecast')).getByText('Available · empty')).toBeInTheDocument()
    expect(readinessItem('Forecast')).toHaveTextContent(/no total is inferred as zero/i)
    expect(within(readinessItem('Expected Change')).getByText('Available · empty')).toBeInTheDocument()
    expect(readinessItem('Expected Change')).toHaveTextContent(
      /empty rather than zero or unavailable/i,
    )
  })

  it('fails closed before loading artifacts when responsible-use metadata is unsafe', () => {
    const value = metadata() as unknown as UnknownObject
    object(value.ethics).patrolRecommendations = true
    const mapLoader = vi.fn(async () => mapContract())
    const forecastMapLoader = vi.fn(async () => forecastContract())
    const precinctSpatialReferenceLoader = vi.fn(async () => spatialContract())

    renderGovernance({
      metadata: value as unknown as OverviewMetadata,
      mapLoader,
      forecastMapLoader,
      precinctSpatialReferenceLoader,
    })

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Governance metadata is incompatible',
    )
    expect(screen.getByRole('alert')).toHaveTextContent(
      /no malformed value is presented as zero or available/i,
    )
    expect(mapLoader).not.toHaveBeenCalled()
    expect(forecastMapLoader).not.toHaveBeenCalled()
    expect(precinctSpatialReferenceLoader).not.toHaveBeenCalled()
  })

  it('labels malformed core Governance counts as invalid', () => {
    const value = metadata() as unknown as UnknownObject
    object(object(value.dataQuality).sourceIssueCounts).missingOffense = -1
    const mapLoader = vi.fn(async () => mapContract())

    renderGovernance({
      metadata: value as unknown as OverviewMetadata,
      mapLoader,
    })

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Governance metadata is invalid',
    )
    expect(screen.getByRole('alert')).toHaveTextContent(
      /did not pass strict validation/i,
    )
    expect(mapLoader).not.toHaveBeenCalled()
  })
})

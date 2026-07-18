import { decodeAnomalies } from './decodeAnomalies'
import { decodeForecastMap } from './loadForecastMap'
import { assertMapContract } from './loadMap'
import {
  assertPrecinctSpatialReferenceFresh,
  decodePrecinctSpatialReference,
  PrecinctSpatialReferenceError,
  reconcilePrecinctSpatialReference,
} from './loadPrecinctSpatialReference'
import type { ForecastMapContract } from '../types/forecastMap'
import type {
  GovernanceFailureStatus,
  GovernanceOverviewProjection,
  GovernanceReadinessStatus,
  GovernanceSourceFailure,
} from '../types/governance'
import type { MapDataContract } from '../types/map'
import type { OverviewMetadata, VersionRecord } from '../types/overview'
import type { PrecinctSpatialReferenceContract } from '../types/precinctSpatialReference'

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/
const UTC_TIMESTAMP =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)$/
const MODEL_ARTIFACT_TYPE = 'weekly_forecast_ml_model'
const MODEL_NAME = 'duckdb_lag_ensemble_regressor'
const INDEPENDENT_TRAINING_REASON =
  'No independent training-completion timestamp is recorded.'
const SIGNAL_STATUSES = new Set<GovernanceReadinessStatus>([
  'available',
  'missing',
  'invalid',
  'stale',
  'incompatible',
  'unavailable',
])
const SOURCE_ISSUE_COUNT_KEYS = [
  'complaintEndBeforeStart',
  'coordinatesOutsideBroadNycBounds',
  'futureComplaintEndDate',
  'futureComplaintStartDate',
  'implausiblyOldComplaintStartDate',
  'invalidLawCategory',
  'maximumIssuesPerRow',
  'missingBorough',
  'missingCoordinates',
  'missingInvalidComplaintStartDate',
  'missingOffense',
  'missingPrecinct',
  'reportDateBeforeComplaintStart',
  'rowsWithAnyIssue',
  'rowsWithMultipleIssues',
  'zeroCoordinates',
] as const
const SOURCE_ISSUE_KEYS = [
  ...SOURCE_ISSUE_COUNT_KEYS,
  'categoriesOverlap',
  'countsAreNonAdditive',
  'populationCount',
] as const
const UNKNOWN_COUNT_KEYS = ['borough', 'lawCategory', 'offense', 'precinct'] as const
const UNKNOWN_KEYS = [
  ...UNKNOWN_COUNT_KEYS,
  'categoriesOverlap',
  'populationCount',
  'valuesRetained',
] as const
const FORBIDDEN_LOCAL_PATH =
  /(?:\/(?:Users|home|root|content|private\/tmp|private\/var)\/|[A-Za-z]:\\)/i

type UnknownRecord = Record<string, unknown>

export class GovernanceContractError extends Error {
  readonly status: GovernanceFailureStatus

  constructor(status: GovernanceFailureStatus, message: string) {
    super(message)
    this.name = 'GovernanceContractError'
    this.status = status
  }
}

function record(value: unknown, label: string): UnknownRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new GovernanceContractError('invalid', `${label} is missing or malformed.`)
  }
  return value as UnknownRecord
}

function exactKeys(value: UnknownRecord, expected: readonly string[], label: string): void {
  const actual = Object.keys(value).sort()
  const wanted = [...expected].sort()
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) {
    throw new GovernanceContractError('incompatible', `${label} has an unsupported schema.`)
  }
}

function nonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value) && value >= 0
}

function finiteNonNegative(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
}

function isoDate(value: unknown): value is string {
  if (typeof value !== 'string' || !ISO_DATE.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value
}

function utcTimestamp(value: unknown): value is string {
  if (typeof value !== 'string' || value.length > 80 || !UTC_TIMESTAMP.test(value)) {
    return false
  }
  const parsed = new Date(value)
  return (
    !Number.isNaN(parsed.valueOf()) &&
    isoDate(value.slice(0, 10)) &&
    parsed.toISOString().slice(0, 19) === value.slice(0, 19) &&
    parsed.getUTCFullYear() >= 2000
  )
}

function monday(value: string): boolean {
  return new Date(`${value}T00:00:00Z`).getUTCDay() === 1
}

function addDays(value: string, days: number): string {
  const parsed = new Date(`${value}T00:00:00Z`)
  parsed.setUTCDate(parsed.getUTCDate() + days)
  return parsed.toISOString().slice(0, 10)
}

function safeText(value: unknown, label: string): string {
  if (
    typeof value !== 'string' ||
    value.length === 0 ||
    value.length > 2_000 ||
    value !== value.trim() ||
    FORBIDDEN_LOCAL_PATH.test(value) ||
    [...value].some((character) => character.charCodeAt(0) < 32)
  ) {
    throw new GovernanceContractError('invalid', `${label} is unsafe.`)
  }
  return value
}

function safeSourceFile(value: unknown, label: string): string {
  const text = safeText(value, label)
  if (text.includes('/') || text.includes('\\') || text === '.' || text === '..') {
    throw new GovernanceContractError('invalid', `${label} must be a safe filename.`)
  }
  return text
}

function signalStatus(value: unknown, label: string): GovernanceReadinessStatus {
  const signal = record(value, `${label} signal`)
  const status = signal.status
  if (!SIGNAL_STATUSES.has(status as GovernanceReadinessStatus)) {
    throw new GovernanceContractError('incompatible', `${label} status is unsupported.`)
  }
  safeSourceFile(signal.sourceFile, `${label} source`)
  if (status !== 'available') {
    if (signal.reason !== undefined) safeText(signal.reason, `${label} unavailable reason`)
    if (status !== 'missing' && signal.reason === undefined) {
      throw new GovernanceContractError('invalid', `${label} unavailable reason is missing.`)
    }
    if (!Array.isArray(signal.rows) || signal.rows.length > 0) {
      throw new GovernanceContractError('invalid', `${label} unavailable state contains rows.`)
    }
    return status as GovernanceReadinessStatus
  }
  if (!Array.isArray(signal.rows)) {
    throw new GovernanceContractError('invalid', `${label} available rows are missing.`)
  }
  if (signal.reason !== undefined) {
    throw new GovernanceContractError('invalid', `${label} available state has a reason.`)
  }
  return signal.rows.length === 0 ? 'empty' : 'available'
}

function versionRecord(value: unknown): VersionRecord {
  return record(value, 'ML manifest version') as VersionRecord
}

function parseModelManifest(value: unknown): GovernanceOverviewProjection['modelManifest'] {
  const manifest = versionRecord(value)
  const status = manifest.status
  if (!SIGNAL_STATUSES.has(status as GovernanceReadinessStatus)) {
    throw new GovernanceContractError('incompatible', 'ML manifest status is unsupported.')
  }
  safeSourceFile(manifest.sourceFile, 'ML manifest source')
  if (status !== 'available') {
    if (manifest.reason !== undefined) safeText(manifest.reason, 'ML manifest reason')
    if (status !== 'missing' && manifest.reason === undefined) {
      throw new GovernanceContractError('invalid', 'ML manifest unavailable reason is missing.')
    }
    return {
      status: status as GovernanceReadinessStatus,
      artifactType: null,
      artifactVersion: null,
      modelName: null,
      modelVersion: null,
      forecastWeek: null,
      generatedAtUtc: null,
    }
  }
  if (
    manifest.artifactType !== MODEL_ARTIFACT_TYPE ||
    manifest.artifactVersion !== 1 ||
    manifest.modelName !== MODEL_NAME ||
    manifest.modelVersion !== 1 ||
    !isoDate(manifest.forecastWeek) ||
    !monday(manifest.forecastWeek) ||
    !utcTimestamp(manifest.generatedAtUtc)
  ) {
    throw new GovernanceContractError('incompatible', 'ML manifest identity or lifecycle metadata is invalid.')
  }
  if (manifest.reason !== undefined || !String(manifest.generatedAtUtc).endsWith('+00:00')) {
    throw new GovernanceContractError('incompatible', 'ML manifest lifecycle state is contradictory.')
  }
  return {
    status: 'available',
    artifactType: manifest.artifactType,
    artifactVersion: manifest.artifactVersion,
    modelName: manifest.modelName,
    modelVersion: manifest.modelVersion,
    forecastWeek: manifest.forecastWeek,
    generatedAtUtc: manifest.generatedAtUtc,
  }
}

function assertOverviewEthics(value: unknown): void {
  const ethics = record(value, 'Overview responsible-use contract')
  exactKeys(
    ethics,
    [
      'aggregateTrendIntelligenceOnly',
      'demographicAttributesIncluded',
      'enforcementRecommendations',
      'eventRecordsIncluded',
      'patrolRecommendations',
      'personLevelScoring',
    ],
    'Overview responsible-use contract',
  )
  if (
    ethics.aggregateTrendIntelligenceOnly !== true ||
    ethics.demographicAttributesIncluded !== false ||
    ethics.enforcementRecommendations !== false ||
    ethics.eventRecordsIncluded !== false ||
    ethics.patrolRecommendations !== false ||
    ethics.personLevelScoring !== false
  ) {
    throw new GovernanceContractError('incompatible', 'Overview responsible-use flags fail closed.')
  }
}

export function decodeGovernanceOverview(value: unknown): GovernanceOverviewProjection {
  const metadata = record(value, 'Overview governance source')
  const application = record(metadata.application, 'Overview application')
  if (
    metadata.schemaVersion !== '1.0.0' ||
    application.name !== 'NYC Crime Intelligence' ||
    application.phase !== 'Phase 7A' ||
    application.view !== 'Overview' ||
    !utcTimestamp(metadata.generatedAtUtc)
  ) {
    throw new GovernanceContractError('incompatible', 'Overview identity or generated timestamp is invalid.')
  }

  const range = record(metadata.dataRange, 'Overview data range')
  const dates = [
    range.safeEventStartDate,
    range.safeEventEndDate,
    range.firstWeek,
    range.lastWeek,
    range.latestCompleteWeek,
    range.defaultStartWeek,
    range.defaultEndWeek,
  ]
  if (
    !dates.every(isoDate) ||
    !monday(range.firstWeek as string) ||
    !monday(range.lastWeek as string) ||
    !monday(range.latestCompleteWeek as string) ||
    !monday(range.defaultStartWeek as string) ||
    !monday(range.defaultEndWeek as string) ||
    (range.safeEventStartDate as string) > (range.safeEventEndDate as string) ||
    (range.firstWeek as string) > (range.lastWeek as string) ||
    (range.defaultStartWeek as string) > (range.defaultEndWeek as string) ||
    (range.defaultStartWeek as string) < (range.firstWeek as string) ||
    (range.defaultEndWeek as string) > (range.latestCompleteWeek as string) ||
    typeof range.latestWeekIsPartial !== 'boolean'
  ) {
    throw new GovernanceContractError('invalid', 'Overview coverage ranges are invalid or reversed.')
  }
  const expectedPartial =
    addDays(range.lastWeek as string, 6) > (range.safeEventEndDate as string)
  const expectedComplete = expectedPartial
    ? addDays(range.lastWeek as string, -7)
    : range.lastWeek
  if (
    range.latestWeekIsPartial !== expectedPartial ||
    range.latestCompleteWeek !== expectedComplete ||
    range.defaultEndWeek !== range.latestCompleteWeek ||
    (range.firstWeek as string) > (range.safeEventStartDate as string) ||
    addDays(range.firstWeek as string, 6) < (range.safeEventStartDate as string) ||
    (range.lastWeek as string) > (range.safeEventEndDate as string) ||
    addDays(range.lastWeek as string, 6) < (range.safeEventEndDate as string) ||
    metadata.generatedAtUtc !== `${String(range.safeEventEndDate)}T00:00:00Z`
  ) {
    throw new GovernanceContractError('incompatible', 'Overview coverage fields do not reconcile.')
  }

  const quality = record(metadata.dataQuality, 'Overview data quality')
  const sourceRowCount = quality.cleanSourceRowCount
  const aggregateSafeEventCount = quality.aggregateSafeEventCount
  const excludedEventCount = quality.excludedEventCount
  if (
    !nonNegativeInteger(sourceRowCount) ||
    !nonNegativeInteger(aggregateSafeEventCount) ||
    !nonNegativeInteger(excludedEventCount) ||
    sourceRowCount - aggregateSafeEventCount !== excludedEventCount ||
    quality.countsReconciled !== true
  ) {
    throw new GovernanceContractError('invalid', 'Overview population counts do not reconcile.')
  }
  const observed = record(metadata.observed, 'Overview observed metadata')
  if (
    observed.safeEventCount !== aggregateSafeEventCount ||
    observed.weeklyAggregateCount !== aggregateSafeEventCount
  ) {
    throw new GovernanceContractError('invalid', 'Overview observed counts do not reconcile.')
  }

  const sourceIssues = record(quality.sourceIssueCounts, 'Source issue counts')
  exactKeys(sourceIssues, SOURCE_ISSUE_KEYS, 'Source issue counts')
  for (const key of SOURCE_ISSUE_COUNT_KEYS) {
    if (!nonNegativeInteger(sourceIssues[key]) || sourceIssues[key] > sourceRowCount) {
      throw new GovernanceContractError('invalid', `Source issue count ${key} is invalid.`)
    }
  }
  const individualIssueSum = SOURCE_ISSUE_COUNT_KEYS
    .filter((key) => !['rowsWithAnyIssue', 'rowsWithMultipleIssues', 'maximumIssuesPerRow'].includes(key))
    .reduce((sum, key) => sum + (sourceIssues[key] as number), 0)
  if (
    (sourceIssues.rowsWithMultipleIssues as number) > (sourceIssues.rowsWithAnyIssue as number) ||
    (sourceIssues.maximumIssuesPerRow as number) > 13 ||
    ((sourceIssues.rowsWithAnyIssue as number) === 0) !==
      ((sourceIssues.maximumIssuesPerRow as number) === 0) ||
    ((sourceIssues.rowsWithMultipleIssues as number) === 0) !==
      ((sourceIssues.maximumIssuesPerRow as number) <= 1) ||
    individualIssueSum < (sourceIssues.rowsWithAnyIssue as number) ||
    ((sourceIssues.rowsWithMultipleIssues as number) > 0 &&
      individualIssueSum <= (sourceIssues.rowsWithAnyIssue as number)) ||
    sourceIssues.populationCount !== sourceRowCount ||
    sourceIssues.categoriesOverlap !== true ||
    sourceIssues.countsAreNonAdditive !== true
  ) {
    throw new GovernanceContractError('invalid', 'Source issue overlap counts do not reconcile.')
  }

  const unknownCounts = record(quality.aggregateSafeUnknownCounts, 'Aggregate-safe UNKNOWN counts')
  exactKeys(unknownCounts, UNKNOWN_KEYS, 'Aggregate-safe UNKNOWN counts')
  for (const key of UNKNOWN_COUNT_KEYS) {
    if (!nonNegativeInteger(unknownCounts[key]) || unknownCounts[key] > aggregateSafeEventCount) {
      throw new GovernanceContractError('invalid', `Aggregate-safe UNKNOWN count ${key} is invalid.`)
    }
  }
  if (
    unknownCounts.populationCount !== aggregateSafeEventCount ||
    unknownCounts.valuesRetained !== true ||
    unknownCounts.categoriesOverlap !== true
  ) {
    throw new GovernanceContractError('incompatible', 'Aggregate-safe UNKNOWN semantics are unsafe.')
  }
  assertOverviewEthics(metadata.ethics)
  if (
    !Array.isArray(metadata.limitations) ||
    metadata.limitations.length < 5 ||
    !metadata.limitations.every((item) => {
      try {
        safeText(item, 'Overview limitation')
        return true
      } catch {
        return false
      }
    })
  ) {
    throw new GovernanceContractError('invalid', 'Overview limitations are missing or unsafe.')
  }

  const signals = record(metadata.signals, 'Overview signals')
  const versions = record(metadata.versions, 'Overview versions')
  const anomalies = decodeAnomalies(value)
  return {
    metadata: value as OverviewMetadata,
    contractGeneratedAtUtc: metadata.generatedAtUtc as string,
    eventStartDate: range.safeEventStartDate as string,
    eventEndDate: range.safeEventEndDate as string,
    firstWeek: range.firstWeek as string,
    lastWeek: range.lastWeek as string,
    latestCompleteWeek: range.latestCompleteWeek as string,
    latestWeekIsPartial: range.latestWeekIsPartial as boolean,
    sourceRowCount,
    aggregateSafeEventCount,
    excludedEventCount,
    sourceIssueCounts: sourceIssues as unknown as GovernanceOverviewProjection['sourceIssueCounts'],
    aggregateSafeUnknownCounts:
      unknownCounts as unknown as GovernanceOverviewProjection['aggregateSafeUnknownCounts'],
    anomalies,
    overviewForecastStatus: signalStatus(signals.forecast, 'Forecast'),
    overviewHotspotStatus: signalStatus(signals.hotspots, 'Hotspot'),
    modelManifest: parseModelManifest(versions.mlManifest),
  }
}

export function decodeGovernanceMap(
  overview: GovernanceOverviewProjection,
  value: unknown,
): MapDataContract {
  try {
    assertMapContract(value)
  } catch {
    throw new GovernanceContractError('invalid', 'Map contract validation failed.')
  }
  const contract = value
  if (
    contract.schemaVersion !== '1.0.0' ||
    contract.application.name !== 'NYC Crime Intelligence' ||
    contract.application.phase !== 'Phase 7B' ||
    contract.application.view !== 'Map and Hotspot View' ||
    !utcTimestamp(contract.generatedAtUtc)
  ) {
    throw new GovernanceContractError('incompatible', 'Map identity or generated timestamp is incompatible.')
  }
  if (
    contract.dataRange.safeEventStartDate !== overview.eventStartDate ||
    contract.dataRange.safeEventEndDate !== overview.eventEndDate ||
    contract.dataRange.sourceEventCount !== overview.sourceRowCount ||
    contract.dataRange.aggregateSafeEventCount !== overview.aggregateSafeEventCount ||
    contract.dataRange.excludedEventCount !== overview.excludedEventCount ||
    contract.generatedAtUtc !== overview.contractGeneratedAtUtc
  ) {
    throw new GovernanceContractError('incompatible', 'Map and Overview coverage do not reconcile.')
  }
  const overviewHotspotStatus =
    overview.overviewHotspotStatus === 'empty'
      ? 'available'
      : overview.overviewHotspotStatus
  if (contract.hotspots.status !== overviewHotspotStatus) {
    throw new GovernanceContractError('incompatible', 'Map and Overview hotspot status do not reconcile.')
  }
  if (contract.hotspots.status === 'available') {
    const overviewSignal = record(
      overview.metadata.signals.hotspots,
      'Overview hotspot signal',
    )
    const overviewSummary = record(overviewSignal.summary, 'Overview hotspot summary')
    const counts = record(contract.hotspots.summary.counts, 'Map hotspot summary counts')
    const bySeverity = counts.bySeverity
    const criticalIndex = contract.dimensions.severities.indexOf('critical')
    const highIndex = contract.dimensions.severities.indexOf('high')
    if (
      !Array.isArray(bySeverity) ||
      criticalIndex < 0 ||
      highIndex < 0 ||
      overviewSummary.criticalCount !== bySeverity[criticalIndex] ||
      overviewSummary.highCount !== bySeverity[highIndex] ||
      overviewSummary.rowCount !==
        (bySeverity[criticalIndex] as number) + (bySeverity[highIndex] as number)
    ) {
      throw new GovernanceContractError('incompatible', 'Map and Overview hotspot counts do not reconcile.')
    }
  }
  safeSourceFile(contract.hotspots.sourceFile, 'Map hotspot source')
  if (contract.hotspots.reason !== undefined) {
    safeText(contract.hotspots.reason, 'Map hotspot reason')
  }
  contract.limitations.forEach((item) => safeText(item, 'Map limitation'))
  return contract
}

function overallForecastError(overview: GovernanceOverviewProjection): UnknownRecord | null {
  const forecast = record(overview.metadata.signals.forecast, 'Overview Forecast signal')
  if (forecast.status !== 'available') return null
  const summary = record(forecast.summary, 'Overview Forecast summary')
  return record(summary.historicalError, 'Overview Forecast historical error')
}

export function decodeGovernanceForecast(
  overview: GovernanceOverviewProjection,
  value: unknown,
): ForecastMapContract {
  let contract: ForecastMapContract
  try {
    contract = decodeForecastMap(value)
  } catch {
    throw new GovernanceContractError('invalid', 'Forecast contract validation failed.')
  }
  if (
    contract.generatedAtUtc !== overview.contractGeneratedAtUtc ||
    contract.dataRange.safeEventStartDate !== overview.eventStartDate ||
    contract.dataRange.safeEventEndDate !== overview.eventEndDate ||
    contract.dataRange.firstObservedWeek !== overview.firstWeek ||
    contract.dataRange.latestObservedWeek !== overview.lastWeek ||
    contract.dataRange.latestCompleteWeek !== overview.latestCompleteWeek ||
    contract.dataRange.latestWeekIsPartial !== overview.latestWeekIsPartial
  ) {
    throw new GovernanceContractError('incompatible', 'Forecast and Overview coverage do not reconcile.')
  }

  const model = contract.model
  safeSourceFile(contract.forecast.sourceFile, 'Forecast source')
  safeSourceFile(contract.baseline.sourceFile, 'Baseline source')
  safeSourceFile(contract.baseline.manifestSourceFile, 'Baseline manifest source')
  safeSourceFile(model.sourceFile, 'Model source')
  safeSourceFile(model.historicalError.sourceFile, 'Historical-error source')
  contract.limitations.forEach((item) => safeText(item, 'Forecast limitation'))
  if (model.reason !== undefined) safeText(model.reason, 'Model unavailable reason')
  if (model.historicalError.reason !== undefined) {
    safeText(model.historicalError.reason, 'Historical-error unavailable reason')
  }
  if (model.status === 'available') {
    const manifest = overview.modelManifest
    const historical = model.historicalError
    const overviewHistorical = overallForecastError(overview)
    if (
      manifest.status !== 'available' ||
      model.artifactType !== manifest.artifactType ||
      model.artifactVersion !== manifest.artifactVersion ||
      model.name !== manifest.modelName ||
      model.version !== manifest.modelVersion ||
      model.forecastWeek !== manifest.forecastWeek ||
      model.artifactGeneratedAtUtc !== manifest.generatedAtUtc ||
      model.trainingStartWeek !== overview.firstWeek ||
      model.trainingThroughWeek !== overview.lastWeek ||
      model.forecastWeek !== addDays(overview.lastWeek, 7) ||
      model.independentTrainingTime.status !== 'unavailable' ||
      model.independentTrainingTime.timestamp !== null ||
      model.independentTrainingTime.reason !== INDEPENDENT_TRAINING_REASON ||
      model.pointEstimatesOnly !== true ||
      model.predictionIntervalsAvailable !== false
    ) {
      throw new GovernanceContractError('incompatible', 'Forecast model lifecycle does not reconcile with Overview.')
    }
    if (!utcTimestamp(model.artifactGeneratedAtUtc)) {
      throw new GovernanceContractError('invalid', 'Forecast artifact timestamp is invalid.')
    }
    if (historical.status === 'available') {
      if (
        !overviewHistorical ||
        overviewHistorical.status !== 'available' ||
        historical.mae !== overviewHistorical.mae ||
        historical.rmse !== overviewHistorical.rmse ||
        historical.weightedMae !== overviewHistorical.weightedMae ||
        historical.predictionCoveragePct !== overviewHistorical.predictionCoveragePct ||
        historical.backtestEndWeek !== overview.latestCompleteWeek
      ) {
        throw new GovernanceContractError(
          'incompatible',
          'Forecast historical validation does not reconcile with Overview.',
        )
      }
      if (
        !finiteNonNegative(historical.mae) ||
        !finiteNonNegative(historical.rmse) ||
        (historical.weightedMae !== null && !finiteNonNegative(historical.weightedMae)) ||
        !finiteNonNegative(historical.predictionCoveragePct) ||
        historical.predictionCoveragePct > 100 ||
        !nonNegativeInteger(historical.backtestRowCount)
      ) {
        throw new GovernanceContractError('invalid', 'Forecast historical validation context is invalid.')
      }
    }
  } else {
    const manifestStatus = overview.modelManifest.status
    const statusReconciles =
      model.status === manifestStatus ||
      (model.status === 'stale' && manifestStatus === 'available')
    if (!statusReconciles) {
      throw new GovernanceContractError(
        'incompatible',
        'Forecast and Overview model availability do not reconcile.',
      )
    }
  }
  const semantics = record(contract.forecastSemantics, 'Forecast semantics')
  if (
    semantics.observationHorizon !==
      'The forecast is next-week only relative to the fixed repository source horizon, not relative to the current wall clock.' ||
    semantics.horizon !== 'one-next-week' ||
    semantics.weekStartDay !== 'Monday' ||
    contract.availability.predictionIntervals !== 'unavailable'
  ) {
    throw new GovernanceContractError('incompatible', 'Forecast fixed-horizon semantics are incompatible.')
  }
  return contract
}

export function decodeGovernanceSpatial(
  forecast: ForecastMapContract | null,
  value: unknown,
  checkedAt: Date,
): PrecinctSpatialReferenceContract {
  if (Number.isNaN(checkedAt.valueOf())) {
    throw new GovernanceContractError('invalid', 'Viewer freshness-check time is invalid.')
  }
  const contract = assertPrecinctSpatialReferenceFresh(
    decodePrecinctSpatialReference(value),
    checkedAt,
  )
  if (forecast?.forecast.status === 'available' && !forecast.forecast.isEmpty) {
    reconcilePrecinctSpatialReference(contract, forecast)
  }
  return contract
}

export function governanceFailure(error: unknown, source: 'map' | 'forecast' | 'spatial'): GovernanceSourceFailure {
  if (error instanceof GovernanceContractError) {
    return {
      status: error.status,
      reason: `The ${source} contract did not reconcile with the committed browser-safe Governance scope.`,
    }
  }
  if (error instanceof PrecinctSpatialReferenceError) {
    const status: GovernanceReadinessStatus =
      error.code === 'stale'
        ? 'stale'
        : error.code === 'missing-artifact'
          ? 'missing'
          : ['forecast-incompatible', 'location-key-mismatch', 'incompatible-identity', 'unsupported-version'].includes(error.code)
            ? 'incompatible'
            : error.code === 'network'
              ? 'unavailable'
              : 'invalid'
    return {
      status,
      reason: `The ${source} contract is ${status}; no unavailable values are converted to zero.`,
    }
  }
  return {
    status: 'unavailable',
    reason: `The ${source} contract could not be loaded or validated.`,
  }
}

export { INDEPENDENT_TRAINING_REASON }

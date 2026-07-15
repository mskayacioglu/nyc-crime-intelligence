import {
  ANOMALY_ROW_COLUMNS,
  type AnomaliesContract,
  type AnomalyExpectedSource,
  type AnomalyPriorityLabel,
  type AnomalyRecord,
  type AnomalyReferenceLabel,
  type AnomalySeverity,
  type AnomalyStatus,
  type AnomalySummary,
  type AnomalyUnavailableStatus,
} from '../types/anomalies'

const OVERVIEW_SCHEMA_VERSION = '1.0.0'
const OVERVIEW_APPLICATION = {
  name: 'NYC Crime Intelligence',
  phase: 'Phase 7A',
  view: 'Overview',
} as const
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/
const KNOWN_STATUSES = new Set<AnomalyStatus>([
  'available',
  'missing',
  'invalid',
  'stale',
  'incompatible',
])
const EXPECTED_SOURCES = new Set<AnomalyExpectedSource>([
  'ml_prediction',
  'rolling_13_week_mean',
])
const SEVERITIES = new Set<AnomalySeverity>(['critical', 'high'])
const SUMMARY_COLUMNS = [
  'criticalCount',
  'highCount',
  'isEmpty',
  'rowCount',
  'scoringEndWeek',
]
// The builder publishes each numeric field independently at four decimal places.
// One ten-thousandth is therefore the strictest safe reconciliation tolerance for
// the browser contract.
const RECONCILIATION_TOLERANCE = 0.0001

type FailureStatus = 'invalid' | 'incompatible'

interface AnomalyDimensions {
  weeks: string[]
  boroughs: string[]
  precincts: string[]
  offenseTypes: string[]
  lawCategories: string[]
  severities: string[]
  anomalyExpectedSources: string[]
}

class DecodeFailure extends Error {
  status: FailureStatus

  constructor(status: FailureStatus, message: string) {
    super(message)
    this.status = status
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)

const isNonNegativeInteger = (value: unknown): value is number =>
  isFiniteNumber(value) && Number.isInteger(value) && value >= 0

function isIsoDate(value: unknown): value is string {
  if (typeof value !== 'string' || !ISO_DATE.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value
}

function isMonday(value: string): boolean {
  return new Date(`${value}T00:00:00Z`).getUTCDay() === 1
}

function requiredLabels(value: unknown, name: string): string[] {
  if (
    !Array.isArray(value) ||
    !value.every((item) => typeof item === 'string' && item.length > 0) ||
    new Set(value).size !== value.length
  ) {
    throw new DecodeFailure(
      'incompatible',
      `The anomaly ${name} dimension must be unique and non-empty-valued.`,
    )
  }
  return value
}

function parseDimensions(value: unknown): AnomalyDimensions {
  if (!isRecord(value)) {
    throw new DecodeFailure('incompatible', 'The anomaly dimensions are missing.')
  }
  const dimensions = {
    weeks: requiredLabels(value.weeks, 'weeks'),
    boroughs: requiredLabels(value.boroughs, 'boroughs'),
    precincts: requiredLabels(value.precincts, 'precincts'),
    offenseTypes: requiredLabels(value.offenseTypes, 'offense types'),
    lawCategories: requiredLabels(value.lawCategories, 'law categories'),
    severities: requiredLabels(value.severities, 'severities'),
    anomalyExpectedSources: requiredLabels(
      value.anomalyExpectedSources,
      'expectation sources',
    ),
  }
  if (
    !dimensions.weeks.every(isIsoDate) ||
    dimensions.weeks.some(
      (week, index) => index > 0 && week <= dimensions.weeks[index - 1],
    )
  ) {
    throw new DecodeFailure('incompatible', 'The anomaly week dimension is invalid.')
  }
  return dimensions
}

function validIndex(value: unknown, labels: string[]): value is number {
  return isNonNegativeInteger(value) && value < labels.length
}

function compareText(left: string, right: string): number {
  if (left < right) return -1
  return left > right ? 1 : 0
}

export function compareAnomalyRecords(
  left: AnomalyRecord,
  right: AnomalyRecord,
): number {
  const severityOrder: Record<AnomalySeverity, number> = { critical: 0, high: 1 }
  return (
    severityOrder[left.severity] - severityOrder[right.severity] ||
    right.score - left.score ||
    compareText(right.week, left.week) ||
    compareText(left.borough, right.borough) ||
    compareText(left.precinct, right.precinct) ||
    compareText(left.offenseType, right.offenseType) ||
    compareText(left.lawCategory, right.lawCategory) ||
    right.actualCount - left.actualCount ||
    right.expectedCount - left.expectedCount ||
    compareText(left.expectedSource, right.expectedSource) ||
    right.residualCount - left.residualCount
  )
}

function referenceLabel(source: AnomalyExpectedSource): AnomalyReferenceLabel {
  return source === 'ml_prediction'
    ? 'Historical backtest estimate'
    : 'Prior 13-week average'
}

function priorityLabel(severity: AnomalySeverity): AnomalyPriorityLabel {
  return severity === 'critical'
    ? 'Critical signal priority'
    : 'High signal priority'
}

function logicalId(values: string[]): string {
  return `anomaly:${values.map((value) => encodeURIComponent(value)).join('|')}`
}

function decodeRow(
  value: unknown,
  rowIndex: number,
  dimensions: AnomalyDimensions,
  latestCompleteWeek: string,
): AnomalyRecord {
  if (!Array.isArray(value) || value.length !== ANOMALY_ROW_COLUMNS.length) {
    throw new DecodeFailure(
      'incompatible',
      `Anomaly row ${rowIndex + 1} does not have the required width.`,
    )
  }
  const [
    weekIndex,
    boroughIndex,
    precinctIndex,
    offenseTypeIndex,
    lawCategoryIndex,
    actualCount,
    expectedCount,
    residualCount,
    score,
    severityIndex,
    expectedSourceIndex,
  ] = value
  if (
    !validIndex(weekIndex, dimensions.weeks) ||
    !validIndex(boroughIndex, dimensions.boroughs) ||
    !validIndex(precinctIndex, dimensions.precincts) ||
    !validIndex(offenseTypeIndex, dimensions.offenseTypes) ||
    !validIndex(lawCategoryIndex, dimensions.lawCategories) ||
    !validIndex(severityIndex, dimensions.severities) ||
    !validIndex(expectedSourceIndex, dimensions.anomalyExpectedSources)
  ) {
    throw new DecodeFailure(
      'invalid',
      `Anomaly row ${rowIndex + 1} contains an invalid dimension index.`,
    )
  }

  const week = dimensions.weeks[weekIndex]
  const severity = dimensions.severities[severityIndex]
  const expectedSource = dimensions.anomalyExpectedSources[expectedSourceIndex]
  if (!isMonday(week) || week > latestCompleteWeek) {
    throw new DecodeFailure(
      'invalid',
      `Anomaly row ${rowIndex + 1} is not a complete Monday-starting week.`,
    )
  }
  if (!SEVERITIES.has(severity as AnomalySeverity)) {
    throw new DecodeFailure(
      'invalid',
      `Anomaly row ${rowIndex + 1} has an unsupported severity.`,
    )
  }
  if (!EXPECTED_SOURCES.has(expectedSource as AnomalyExpectedSource)) {
    throw new DecodeFailure(
      'invalid',
      `Anomaly row ${rowIndex + 1} has an unsupported expectation source.`,
    )
  }
  if (!isNonNegativeInteger(actualCount)) {
    throw new DecodeFailure(
      'invalid',
      `Anomaly row ${rowIndex + 1} has an invalid observed aggregate count.`,
    )
  }
  if (!isFiniteNumber(expectedCount) || expectedCount < 0) {
    throw new DecodeFailure(
      'invalid',
      `Anomaly row ${rowIndex + 1} has an invalid expected aggregate count.`,
    )
  }
  if (!isFiniteNumber(residualCount) || residualCount <= 0) {
    throw new DecodeFailure(
      'invalid',
      `Anomaly row ${rowIndex + 1} must have a positive deviation.`,
    )
  }
  if (
    Math.abs(actualCount - expectedCount - residualCount) >
    RECONCILIATION_TOLERANCE
  ) {
    throw new DecodeFailure(
      'invalid',
      `Anomaly row ${rowIndex + 1} does not reconcile observed and expected counts.`,
    )
  }
  if (!isFiniteNumber(score) || score < 0) {
    throw new DecodeFailure(
      'invalid',
      `Anomaly row ${rowIndex + 1} has an invalid anomaly score.`,
    )
  }

  const typedSeverity = severity as AnomalySeverity
  const typedSource = expectedSource as AnomalyExpectedSource
  const borough = dimensions.boroughs[boroughIndex]
  const precinct = dimensions.precincts[precinctIndex]
  const offenseType = dimensions.offenseTypes[offenseTypeIndex]
  const lawCategory = dimensions.lawCategories[lawCategoryIndex]
  return {
    id: logicalId([week, borough, precinct, offenseType, lawCategory]),
    sourceRank: rowIndex + 1,
    weekIndex,
    boroughIndex,
    precinctIndex,
    offenseTypeIndex,
    lawCategoryIndex,
    week,
    borough,
    precinct,
    offenseType,
    lawCategory,
    actualCount,
    expectedCount,
    residualCount,
    signedDeviation: residualCount,
    signedDeviationLabel: `+${String(residualCount)}`,
    deviationPct: expectedCount === 0 ? null : (residualCount / expectedCount) * 100,
    score,
    severity: typedSeverity,
    priorityLabel: priorityLabel(typedSeverity),
    expectedSource: typedSource,
    referenceLabel: referenceLabel(typedSource),
    direction: 'above',
    directionLabel: 'Above expectation',
  }
}

function parseSummary(
  value: unknown,
  rows: AnomalyRecord[],
  latestCompleteWeek: string,
): AnomalySummary {
  if (
    !isRecord(value) ||
    JSON.stringify(Object.keys(value).sort()) !== JSON.stringify(SUMMARY_COLUMNS)
  ) {
    throw new DecodeFailure('invalid', 'The anomaly summary schema is invalid.')
  }
  const { rowCount, highCount, criticalCount, isEmpty, scoringEndWeek } = value
  if (
    !isNonNegativeInteger(rowCount) ||
    !isNonNegativeInteger(highCount) ||
    !isNonNegativeInteger(criticalCount) ||
    typeof isEmpty !== 'boolean' ||
    !isIsoDate(scoringEndWeek) ||
    !isMonday(scoringEndWeek)
  ) {
    throw new DecodeFailure('invalid', 'The anomaly summary counts are invalid.')
  }
  const actualHigh = rows.filter((row) => row.severity === 'high').length
  const actualCritical = rows.length - actualHigh
  if (
    rowCount !== rows.length ||
    highCount !== actualHigh ||
    criticalCount !== actualCritical ||
    highCount + criticalCount !== rowCount ||
    isEmpty !== (rows.length === 0)
  ) {
    throw new DecodeFailure(
      'invalid',
      'The anomaly summary does not reconcile with its rows.',
    )
  }
  if (scoringEndWeek !== latestCompleteWeek) {
    throw new DecodeFailure(
      'invalid',
      'The anomaly scoring horizon does not match the latest complete week.',
    )
  }
  return {
    rowCount,
    highCount,
    criticalCount,
    isEmpty,
    scoringEndWeek,
  }
}

function unavailable(
  status: AnomalyUnavailableStatus,
  reason: unknown,
  sourceFile: unknown,
): AnomaliesContract {
  const fallback = {
    missing: 'The aggregate anomaly source is missing.',
    invalid: 'The aggregate anomaly source is invalid.',
    stale: 'The aggregate anomaly source is stale.',
    incompatible: 'The aggregate anomaly contract is incompatible.',
  }[status]
  return {
    status,
    sourceFile:
      typeof sourceFile === 'string' && sourceFile.length > 0 ? sourceFile : null,
    reason: typeof reason === 'string' && reason.length > 0 ? reason : fallback,
  }
}

function assertOverviewIdentity(value: Record<string, unknown>): void {
  if (value.schemaVersion !== OVERVIEW_SCHEMA_VERSION) {
    throw new DecodeFailure(
      'incompatible',
      'The Overview schema version is not supported by the anomaly experience.',
    )
  }
  if (!isRecord(value.application)) {
    throw new DecodeFailure('incompatible', 'The Overview application identity is missing.')
  }
  if (
    value.application.name !== OVERVIEW_APPLICATION.name ||
    value.application.phase !== OVERVIEW_APPLICATION.phase ||
    value.application.view !== OVERVIEW_APPLICATION.view
  ) {
    throw new DecodeFailure(
      'incompatible',
      'The Overview application identity is incompatible with the anomaly experience.',
    )
  }
  if (
    !isRecord(value.versions) ||
    value.versions.dashboardContract !== OVERVIEW_SCHEMA_VERSION
  ) {
    throw new DecodeFailure(
      'incompatible',
      'The Overview dashboard contract version is incompatible.',
    )
  }
  if (!isRecord(value.ethics)) {
    throw new DecodeFailure(
      'incompatible',
      'The Overview responsible-use contract is missing.',
    )
  }
  const ethics = value.ethics
  if (
    ethics.aggregateTrendIntelligenceOnly !== true ||
    ethics.demographicAttributesIncluded !== false ||
    ethics.enforcementRecommendations !== false ||
    ethics.eventRecordsIncluded !== false ||
    ethics.patrolRecommendations !== false ||
    ethics.personLevelScoring !== false
  ) {
    throw new DecodeFailure(
      'incompatible',
      'The Overview responsible-use contract is incompatible.',
    )
  }
}

export function decodeAnomalies(value: unknown): AnomaliesContract {
  let sourceFile: unknown
  try {
    if (!isRecord(value)) {
      throw new DecodeFailure('incompatible', 'The Overview response is not an object.')
    }
    assertOverviewIdentity(value)
    if (!isRecord(value.signals) || !isRecord(value.signals.anomalies)) {
      throw new DecodeFailure('incompatible', 'The Overview anomaly signal is missing.')
    }
    const signal = value.signals.anomalies
    sourceFile = signal.sourceFile
    const declaredStatus = signal.status
    if (
      typeof declaredStatus !== 'string' ||
      !KNOWN_STATUSES.has(declaredStatus as AnomalyStatus)
    ) {
      return unavailable(
        'incompatible',
        'The Overview anomaly status is unknown.',
        sourceFile,
      )
    }
    if (declaredStatus !== 'available') {
      if (
        signal.rows !== undefined &&
        (!Array.isArray(signal.rows) || signal.rows.length > 0)
      ) {
        return unavailable(
          'invalid',
          'An unavailable anomaly contract cannot contain rows.',
          sourceFile,
        )
      }
      return unavailable(
        declaredStatus as AnomalyUnavailableStatus,
        signal.reason,
        sourceFile,
      )
    }
    if (typeof sourceFile !== 'string' || sourceFile.length === 0) {
      throw new DecodeFailure('invalid', 'The available anomaly source file is missing.')
    }
    if (
      !Array.isArray(signal.rowColumns) ||
      signal.rowColumns.length !== ANOMALY_ROW_COLUMNS.length ||
      !signal.rowColumns.every(
        (column, index) => column === ANOMALY_ROW_COLUMNS[index],
      )
    ) {
      throw new DecodeFailure(
        'incompatible',
        'The Overview anomaly row columns are incompatible.',
      )
    }
    if (!Array.isArray(signal.rows)) {
      throw new DecodeFailure('invalid', 'The Overview anomaly rows are missing.')
    }
    if (!isRecord(value.dataRange)) {
      throw new DecodeFailure('incompatible', 'The Overview anomaly date range is missing.')
    }
    const latestCompleteWeek = value.dataRange.latestCompleteWeek
    if (!isIsoDate(latestCompleteWeek) || !isMonday(latestCompleteWeek)) {
      throw new DecodeFailure(
        'incompatible',
        'The Overview latest complete week is incompatible.',
      )
    }
    const dimensions = parseDimensions(value.dimensions)
    const rows = signal.rows.map((row, index) =>
      decodeRow(row, index, dimensions, latestCompleteWeek),
    )
    const ids = new Set<string>()
    for (let index = 0; index < rows.length; index += 1) {
      const row = rows[index]
      if (ids.has(row.id)) {
        throw new DecodeFailure(
          'invalid',
          `Anomaly row ${index + 1} duplicates a logical identity.`,
        )
      }
      ids.add(row.id)
      if (index > 0 && compareAnomalyRecords(rows[index - 1], row) > 0) {
        throw new DecodeFailure(
          'invalid',
          `Anomaly row ${index + 1} is outside the deterministic source order.`,
        )
      }
    }
    const summary = parseSummary(signal.summary, rows, latestCompleteWeek)
    return {
      status: 'available',
      sourceFile,
      rows,
      isEmpty: rows.length === 0,
      sourceRowCount: rows.length,
      scoringEndWeek: summary.scoringEndWeek,
      summary,
    }
  } catch (error) {
    if (error instanceof DecodeFailure) {
      return unavailable(error.status, error.message, sourceFile)
    }
    return unavailable(
      'invalid',
      'The aggregate anomaly source could not be decoded safely.',
      sourceFile,
    )
  }
}

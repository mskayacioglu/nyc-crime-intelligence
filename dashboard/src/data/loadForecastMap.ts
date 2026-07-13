import {
  FORECAST_MAP_ROW_COLUMNS,
  type ForecastMapContract,
  type ForecastMapRow,
  type ForecastMapStatus,
} from '../types/forecastMap'

const PATH = '/data/forecast-map.json'
const DATE = /^\d{4}-\d{2}-\d{2}$/
const UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/
const PRECINCT = /^[1-9]\d{0,2}$/
const FORBIDDEN = /(complaint.?id|cmplnt|victim|suspect|race|sex|age.?group|exact.?address|latitude|longitude|person.?score|patrol.?priority|enforcement.?target)/i
const STATUSES = new Set<ForecastMapStatus>(['available', 'missing', 'invalid', 'stale'])
const PROVENANCE_KEYS = [
  'baselineManifest',
  'baselinePredictions',
  'mlManifest',
  'mlMetrics',
  'mlPredictions',
  'overview',
  'weeklyAggregate',
]

const record = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)
const finite = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)
const integer = (value: unknown): value is number =>
  finite(value) && Number.isInteger(value) && value >= 0
const close = (left: number, right: number, tolerance: number) =>
  Math.abs(left - right) <= tolerance

function exactKeys(value: Record<string, unknown>, expected: string[], label: string): void {
  if (JSON.stringify(Object.keys(value).sort()) !== JSON.stringify([...expected].sort())) {
    throw new Error(`Forecast Map ${label} schema is invalid.`)
  }
}

function isoDate(value: unknown): value is string {
  if (typeof value !== 'string' || !DATE.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value
}

function addDays(value: string, days: number): string {
  return new Date(Date.parse(`${value}T00:00:00Z`) + days * 86_400_000)
    .toISOString()
    .slice(0, 10)
}

function labels(value: unknown, name: string): string[] {
  if (
    !Array.isArray(value) ||
    !value.every((item) => typeof item === 'string' && item.length > 0) ||
    new Set(value).size !== value.length ||
    value.some((item, index) => index > 0 && item <= value[index - 1])
  ) {
    throw new Error(`Forecast Map ${name} labels must be sorted and unique.`)
  }
  return value
}

function expectedAvailability(available: number, total: number): 'available' | 'partial' | 'unavailable' {
  if (total === 0 || available === 0) return 'unavailable'
  return available === total ? 'available' : 'partial'
}

function assertSafeFlags(value: Record<string, unknown>): void {
  const privacy = value.privacy
  const ethics = value.ethics
  if (!record(privacy) || !record(ethics)) {
    throw new Error('Forecast Map privacy or responsible-use flags are missing.')
  }
  exactKeys(
    privacy,
    [
      'aggregateOnly',
      'complaintIdentifiersIncluded',
      'demographicAttributesIncluded',
      'eventLevelCoordinatesIncluded',
      'eventRecordsIncluded',
      'exactAddressesIncluded',
      'namesIncluded',
      'sourceRowIdentifiersIncluded',
    ],
    'privacy',
  )
  exactKeys(
    ethics,
    [
      'aggregateReportedEventVolumeOnly',
      'enforcementRecommendations',
      'individualBehaviorPrediction',
      'patrolRecommendations',
      'personLevelScoring',
      'specificIncidentLocationPrediction',
    ],
    'responsible-use',
  )
  if (
    privacy.aggregateOnly !== true ||
    privacy.complaintIdentifiersIncluded !== false ||
    privacy.demographicAttributesIncluded !== false ||
    privacy.eventLevelCoordinatesIncluded !== false ||
    privacy.eventRecordsIncluded !== false ||
    privacy.exactAddressesIncluded !== false ||
    privacy.namesIncluded !== false ||
    privacy.sourceRowIdentifiersIncluded !== false ||
    ethics.aggregateReportedEventVolumeOnly !== true ||
    ethics.enforcementRecommendations !== false ||
    ethics.individualBehaviorPrediction !== false ||
    ethics.patrolRecommendations !== false ||
    ethics.personLevelScoring !== false ||
    ethics.specificIncidentLocationPrediction !== false
  ) {
    throw new Error('Forecast Map privacy or responsible-use flags are incompatible.')
  }

  const keys: string[] = []
  const walk = (candidate: unknown): void => {
    if (Array.isArray(candidate)) candidate.forEach(walk)
    else if (record(candidate)) {
      Object.entries(candidate).forEach(([key, child]) => {
        keys.push(key)
        walk(child)
      })
    }
  }
  walk(
    Object.fromEntries(
      Object.entries(value).filter(([key]) => key !== 'privacy' && key !== 'ethics'),
    ),
  )
  if (keys.some((key) => FORBIDDEN.test(key))) {
    throw new Error('Forecast Map contains a forbidden field.')
  }
}

function assertProvenance(value: unknown): void {
  if (!record(value)) throw new Error('Forecast Map provenance is invalid.')
  exactKeys(value, PROVENANCE_KEYS, 'provenance')
  for (const entry of Object.values(value)) {
    if (!record(entry)) throw new Error('Forecast Map provenance entry is invalid.')
    exactKeys(entry, ['publishedUse', 'sourceFile', 'status'], 'provenance entry')
    if (
      !STATUSES.has(entry.status as ForecastMapStatus) ||
      typeof entry.sourceFile !== 'string' ||
      !entry.sourceFile ||
      entry.sourceFile.includes('/') ||
      entry.sourceFile.includes('\\') ||
      typeof entry.publishedUse !== 'string' ||
      !entry.publishedUse
    ) {
      throw new Error('Forecast Map provenance entry is invalid.')
    }
  }
}

export function decodeForecastMap(value: unknown): ForecastMapContract {
  if (!record(value)) throw new Error('Forecast Map response is not an object.')
  exactKeys(
    value,
    [
      'application',
      'availability',
      'baseline',
      'dataRange',
      'dimensions',
      'ethics',
      'filterIndex',
      'forecast',
      'forecastSemantics',
      'generatedAtUtc',
      'limitations',
      'locationKeySemantics',
      'methodology',
      'model',
      'privacy',
      'provenance',
      'schemaVersion',
    ],
    'top-level',
  )
  if (value.schemaVersion !== '1.0.0' || !UTC.test(String(value.generatedAtUtc))) {
    throw new Error('Forecast Map identity or schema is incompatible.')
  }
  const application = value.application
  const range = value.dataRange
  const dimensions = value.dimensions
  const forecast = value.forecast
  if (!record(application) || !record(range) || !record(dimensions) || !record(forecast)) {
    throw new Error('Forecast Map required sections are invalid.')
  }
  exactKeys(application, ['name', 'phase', 'view'], 'application')
  if (
    application.name !== 'NYC Crime Intelligence' ||
    application.phase !== 'Phase 7C.1' ||
    application.view !== 'Forecast Map Data Contract'
  ) {
    throw new Error('Forecast Map application identity is incompatible.')
  }

  exactKeys(
    range,
    [
      'firstObservedWeek',
      'latestCompleteWeek',
      'latestObservedWeek',
      'latestWeekIsPartial',
      'safeEventEndDate',
      'safeEventStartDate',
      'supportedForecastWeeks',
    ],
    'date range',
  )
  const rangeDates = [
    range.safeEventStartDate,
    range.safeEventEndDate,
    range.firstObservedWeek,
    range.latestObservedWeek,
    range.latestCompleteWeek,
  ]
  if (
    !rangeDates.every(isoDate) ||
    typeof range.latestWeekIsPartial !== 'boolean' ||
    !Array.isArray(range.supportedForecastWeeks) ||
    !range.supportedForecastWeeks.every(isoDate) ||
    range.supportedForecastWeeks.length > 1
  ) {
    throw new Error('Forecast Map date range is invalid.')
  }
  const safeStart = range.safeEventStartDate as string
  const safeEnd = range.safeEventEndDate as string
  const firstWeek = range.firstObservedWeek as string
  const latestWeek = range.latestObservedWeek as string
  const latestComplete = range.latestCompleteWeek as string
  const expectedPartial = addDays(latestWeek, 6) > safeEnd
  if (
    safeStart > safeEnd ||
    firstWeek > latestComplete ||
    latestComplete > latestWeek ||
    range.latestWeekIsPartial !== expectedPartial ||
    latestComplete !== (expectedPartial ? addDays(latestWeek, -7) : latestWeek) ||
    String(value.generatedAtUtc).slice(0, 10) !== safeEnd
  ) {
    throw new Error('Forecast Map date range is inconsistent.')
  }

  exactKeys(
    dimensions,
    ['boroughs', 'forecastWeeks', 'lawCategories', 'offenseTypes', 'precincts'],
    'dimensions',
  )
  const weeks = labels(dimensions.forecastWeeks, 'forecastWeeks')
  const boroughs = labels(dimensions.boroughs, 'boroughs')
  const precincts = labels(dimensions.precincts, 'precincts')
  const offenses = labels(dimensions.offenseTypes, 'offenseTypes')
  const laws = labels(dimensions.lawCategories, 'lawCategories')
  if (precincts.some((label) => !PRECINCT.test(label))) {
    throw new Error('Forecast Map precinct labels are unsafe.')
  }

  const status = forecast.status
  if (!STATUSES.has(status as ForecastMapStatus)) {
    throw new Error('Forecast Map forecast status is invalid.')
  }
  const forecastKeys = [
    'isEmpty',
    'rowColumns',
    'rows',
    'sourceFile',
    'status',
    'summary',
    ...(status === 'available' ? [] : ['reason']),
  ]
  exactKeys(forecast, forecastKeys, 'forecast')
  if (
    typeof forecast.sourceFile !== 'string' ||
    !forecast.sourceFile ||
    typeof forecast.isEmpty !== 'boolean' ||
    JSON.stringify(forecast.rowColumns) !== JSON.stringify(FORECAST_MAP_ROW_COLUMNS) ||
    !Array.isArray(forecast.rows) ||
    !record(forecast.summary)
  ) {
    throw new Error('Forecast Map forecast section is invalid.')
  }
  const rows = forecast.rows
  if (
    status !== 'available' &&
    (typeof forecast.reason !== 'string' || !forecast.reason || rows.length > 0 || forecast.isEmpty)
  ) {
    throw new Error('Unavailable Forecast Map cannot expose rows.')
  }
  if (status === 'available' && forecast.isEmpty !== (rows.length === 0)) {
    throw new Error('Forecast Map empty state is inconsistent.')
  }
  const hasRows = status === 'available' && rows.length > 0
  if (hasRows) {
    if (
      weeks.length !== 1 ||
      boroughs.length === 0 ||
      precincts.length === 0 ||
      offenses.length === 0 ||
      laws.length === 0 ||
      JSON.stringify(range.supportedForecastWeeks) !== JSON.stringify(weeks) ||
      weeks[0] !== addDays(latestWeek, 7) ||
      String(value.generatedAtUtc).slice(0, 10) > weeks[0]
    ) {
      throw new Error('Forecast Map horizon is incompatible.')
    }
  } else if (
    weeks.length ||
    boroughs.length ||
    precincts.length ||
    offenses.length ||
    laws.length ||
    range.supportedForecastWeeks.length
  ) {
    throw new Error('Unavailable or empty Forecast Map exposes dimensions.')
  }

  const filterIndex = value.filterIndex
  if (!record(filterIndex) || !record(filterIndex.precinctsByBorough)) {
    throw new Error('Forecast Map filter index is invalid.')
  }
  exactKeys(filterIndex, ['precinctsByBorough'], 'filter index')
  const precinctIndex = filterIndex.precinctsByBorough
  exactKeys(precinctIndex, ['rowColumns', 'rows', 'semantics'], 'precinct filter index')
  if (
    JSON.stringify(precinctIndex.rowColumns) !==
      JSON.stringify(['boroughIndex', 'precinctIndexes']) ||
    !Array.isArray(precinctIndex.rows) ||
    typeof precinctIndex.semantics !== 'string'
  ) {
    throw new Error('Forecast Map filter index is invalid.')
  }
  const precinctBorough = new Map<number, number>()
  let priorBorough = -1
  for (const row of precinctIndex.rows) {
    if (
      !Array.isArray(row) ||
      row.length !== 2 ||
      !integer(row[0]) ||
      row[0] >= boroughs.length ||
      row[0] <= priorBorough ||
      !Array.isArray(row[1]) ||
      !row[1].every((item) => integer(item) && item < precincts.length) ||
      new Set(row[1]).size !== row[1].length ||
      row[1].some((item, index) => index > 0 && item <= row[1][index - 1])
    ) {
      throw new Error('Forecast Map filter index is invalid.')
    }
    priorBorough = row[0]
    for (const item of row[1]) {
      if (precinctBorough.has(item)) {
        throw new Error('Forecast Map precinct has multiple boroughs.')
      }
      precinctBorough.set(item, row[0])
    }
  }
  if (precinctBorough.size !== precincts.length) {
    throw new Error('Forecast Map precinct index is incomplete.')
  }

  const methodology = value.methodology
  if (!record(methodology) || methodology.arithmeticTolerance !== 0.000001 || methodology.numericRoundingDigits !== 6) {
    throw new Error('Forecast Map arithmetic contract is invalid.')
  }
  const tolerance = methodology.arithmeticTolerance
  const logical = new Set<string>()
  let previous = ''
  let total = 0
  let zero = 0
  let baselineAvailable = 0
  let changeAvailable = 0
  let pctAvailable = 0
  let zeroBaseline = 0
  let unknownOffense = 0
  const byBorough = Array(boroughs.length).fill(0) as number[]
  const rowPairs = new Set<string>()
  for (let index = 0; index < rows.length; index += 1) {
    const raw = rows[index]
    if (!Array.isArray(raw) || raw.length !== FORECAST_MAP_ROW_COLUMNS.length) {
      throw new Error(`Forecast Map row ${index + 1} has invalid width.`)
    }
    const [wi, bi, pi, oi, li, predicted, baseline, change, pct, key] = raw as ForecastMapRow
    if (
      ![wi, bi, pi, oi, li].every(integer) ||
      wi >= weeks.length ||
      bi >= boroughs.length ||
      pi >= precincts.length ||
      oi >= offenses.length ||
      li >= laws.length ||
      !finite(predicted) ||
      predicted < 0 ||
      (baseline !== null && (!finite(baseline) || baseline < 0)) ||
      (change !== null && !finite(change)) ||
      (pct !== null && !finite(pct)) ||
      key !== `nypd-precinct:${precincts[pi]}` ||
      precinctBorough.get(pi) !== bi
    ) {
      throw new Error(`Forecast Map row ${index + 1} contains an invalid value.`)
    }
    const logicalKey = [wi, bi, pi, oi, li]
      .map((item) => String(item).padStart(6, '0'))
      .join('|')
    if (logical.has(logicalKey) || (previous && logicalKey <= previous)) {
      throw new Error('Forecast Map rows are duplicate or unstably ordered.')
    }
    logical.add(logicalKey)
    previous = logicalKey
    rowPairs.add(`${bi}|${pi}`)
    if (
      baseline === null
        ? change !== null || pct !== null
        : change === null ||
          !close(change, predicted - baseline, tolerance) ||
          (baseline === 0
            ? pct !== null
            : pct === null || !close(pct, (change / baseline) * 100, tolerance))
    ) {
      throw new Error('Forecast Map baseline/change arithmetic is invalid.')
    }
    total += predicted
    byBorough[bi] += 1
    if (predicted === 0) zero += 1
    if (baseline !== null) {
      baselineAvailable += 1
      changeAvailable += 1
      if (baseline === 0) zeroBaseline += 1
    }
    if (pct !== null) pctAvailable += 1
    if (offenses[oi].toLocaleUpperCase('en-US') === 'UNKNOWN') unknownOffense += 1
  }
  if (
    new Set([...precinctBorough.entries()].map(([pi, bi]) => `${bi}|${pi}`)).size !==
      rowPairs.size ||
    [...rowPairs].some((pair) => ![...precinctBorough.entries()].some(([pi, bi]) => pair === `${bi}|${pi}`))
  ) {
    throw new Error('Forecast Map rows and precinct index do not reconcile.')
  }

  const summary = forecast.summary
  exactKeys(
    summary,
    [
      'countsByBorough',
      'modelSegmentCoveragePct',
      'predictedTotal',
      'predictedVolumeCoveragePct',
      'publishedBoroughCount',
      'publishedPrecinctCount',
      'rowCount',
      'rowCoveragePct',
      'sourcePredictedTotal',
      'sourceRowCount',
      'sourceSegmentCount',
      'unknownOffenseRowCount',
      'withheldPredictedTotal',
      'withheldReasonCounts',
      'withheldRowCount',
      'zeroPredictionRowCount',
    ],
    'summary',
  )
  if (
    !integer(summary.rowCount) ||
    summary.rowCount !== rows.length ||
    !integer(summary.publishedBoroughCount) ||
    summary.publishedBoroughCount !== boroughs.length ||
    !integer(summary.publishedPrecinctCount) ||
    summary.publishedPrecinctCount !== precincts.length ||
    !integer(summary.zeroPredictionRowCount) ||
    summary.zeroPredictionRowCount !== zero ||
    !integer(summary.unknownOffenseRowCount) ||
    summary.unknownOffenseRowCount !== unknownOffense ||
    JSON.stringify(summary.countsByBorough) !== JSON.stringify(byBorough) ||
    !record(summary.withheldReasonCounts) ||
    !integer(summary.withheldReasonCounts.boroughMismatch) ||
    !integer(summary.withheldReasonCounts.unmappableLocation)
  ) {
    throw new Error('Forecast Map summary does not reconcile.')
  }
  if (status === 'available') {
    if (
      !integer(summary.sourceRowCount) ||
      !integer(summary.sourceSegmentCount) ||
      !integer(summary.withheldRowCount) ||
      summary.sourceRowCount !== rows.length + summary.withheldRowCount ||
      summary.withheldRowCount !==
        summary.withheldReasonCounts.boroughMismatch +
          summary.withheldReasonCounts.unmappableLocation ||
      (summary.sourceSegmentCount > 0 &&
        (!finite(summary.modelSegmentCoveragePct) ||
          !close(
            summary.modelSegmentCoveragePct,
            (summary.sourceRowCount / summary.sourceSegmentCount) * 100,
            tolerance,
          )))
    ) {
      throw new Error('Forecast Map source coverage does not reconcile.')
    }
    if (rows.length > 0) {
      if (
        summary.sourceRowCount !== summary.sourceSegmentCount ||
        !finite(summary.predictedTotal) ||
        !finite(summary.sourcePredictedTotal) ||
        !finite(summary.withheldPredictedTotal) ||
        !finite(summary.rowCoveragePct) ||
        !finite(summary.predictedVolumeCoveragePct) ||
        !close(summary.predictedTotal, total, tolerance) ||
        !close(
          summary.sourcePredictedTotal,
          summary.predictedTotal + summary.withheldPredictedTotal,
          tolerance,
        ) ||
        !close(
          summary.rowCoveragePct,
          (summary.rowCount / summary.sourceRowCount) * 100,
          tolerance,
        ) ||
        !close(
          summary.predictedVolumeCoveragePct,
          (summary.predictedTotal / summary.sourcePredictedTotal) * 100,
          tolerance,
        )
      ) {
        throw new Error('Forecast Map numeric summary does not reconcile.')
      }
    } else if (
      summary.predictedTotal !== null ||
      summary.sourcePredictedTotal !== null ||
      summary.withheldPredictedTotal !== null ||
      summary.rowCoveragePct !== null ||
      summary.predictedVolumeCoveragePct !== null
    ) {
      throw new Error('Available-empty Forecast Map publishes numeric totals.')
    }
  } else if (
    summary.sourceRowCount !== null ||
    summary.sourceSegmentCount !== null ||
    summary.withheldRowCount !== null ||
    summary.modelSegmentCoveragePct !== null ||
    summary.predictedTotal !== null ||
    summary.sourcePredictedTotal !== null ||
    summary.withheldPredictedTotal !== null ||
    summary.rowCoveragePct !== null ||
    summary.predictedVolumeCoveragePct !== null
  ) {
    throw new Error('Unavailable Forecast Map publishes source totals.')
  }

  const baseline = value.baseline
  if (!record(baseline) || !record(baseline.summary)) {
    throw new Error('Forecast Map baseline context is invalid.')
  }
  const baselineStatus = baseline.status as ForecastMapStatus
  if (!STATUSES.has(baselineStatus)) {
    throw new Error('Forecast Map baseline status is invalid.')
  }
  exactKeys(
    baseline,
    [
      'manifestSourceFile',
      'method',
      'priorOnly',
      'requiredPriorWeeks',
      ...(baselineStatus === 'available' ? [] : ['reason']),
      'semantics',
      'sourceFile',
      'status',
      'summary',
      'valueAvailability',
      'zeroFillRule',
    ],
    'baseline',
  )
  exactKeys(
    baseline.summary,
    [
      'baselineAvailableRowCount',
      'baselineUnavailableRowCount',
      'expectedChangeCountAvailableRowCount',
      'expectedChangePctAvailableRowCount',
      'publishedRowCount',
      'zeroBaselineRowCount',
    ],
    'baseline summary',
  )
  if (
    baseline.summary.publishedRowCount !== rows.length ||
    baseline.summary.baselineAvailableRowCount !== baselineAvailable ||
    baseline.summary.baselineUnavailableRowCount !== rows.length - baselineAvailable ||
    baseline.summary.expectedChangeCountAvailableRowCount !== changeAvailable ||
    baseline.summary.expectedChangePctAvailableRowCount !== pctAvailable ||
    baseline.summary.zeroBaselineRowCount !== zeroBaseline ||
    baseline.valueAvailability !== expectedAvailability(baselineAvailable, rows.length) ||
    typeof baseline.sourceFile !== 'string' ||
    typeof baseline.manifestSourceFile !== 'string'
  ) {
    throw new Error('Forecast Map baseline summary does not reconcile.')
  }
  if (baselineStatus === 'available') {
    if (
      typeof baseline.method !== 'string' ||
      !baseline.method ||
      baseline.priorOnly !== true ||
      !integer(baseline.requiredPriorWeeks) ||
      baseline.requiredPriorWeeks < 1 ||
      typeof baseline.semantics !== 'string' ||
      typeof baseline.zeroFillRule !== 'string'
    ) {
      throw new Error('Available Forecast Map baseline metadata is incomplete.')
    }
  } else if (
    typeof baseline.reason !== 'string' ||
    !baseline.reason ||
    baseline.method !== null ||
    baseline.priorOnly !== null ||
    baseline.requiredPriorWeeks !== null ||
    baseline.semantics !== null ||
    baseline.zeroFillRule !== null ||
    baselineAvailable > 0
  ) {
    throw new Error('Unavailable Forecast Map baseline is inconsistent.')
  }

  const availability = value.availability
  if (!record(availability)) throw new Error('Forecast Map availability is invalid.')
  exactKeys(
    availability,
    [
      'expectedChangeCount',
      'expectedChangePct',
      'forecastPointEstimates',
      'historicalBaseline',
      'precinctSpatialReference',
      'predictionIntervals',
    ],
    'availability',
  )
  const expectedForecastAvailability =
    status === 'available' ? (rows.length ? 'available' : 'empty') : status
  if (
    availability.forecastPointEstimates !== expectedForecastAvailability ||
    availability.historicalBaseline !== expectedAvailability(baselineAvailable, rows.length) ||
    availability.expectedChangeCount !== expectedAvailability(changeAvailable, rows.length) ||
    availability.expectedChangePct !== expectedAvailability(pctAvailable, rows.length) ||
    availability.predictionIntervals !== 'unavailable' ||
    availability.precinctSpatialReference !== 'location-key-only'
  ) {
    throw new Error('Forecast Map availability does not reconcile.')
  }

  const model = value.model
  if (!record(model) || !record(model.historicalError)) {
    throw new Error('Forecast Map model context is invalid.')
  }
  const modelStatus = model.status as ForecastMapStatus
  if (!STATUSES.has(modelStatus)) throw new Error('Forecast Map model status is invalid.')
  exactKeys(
    model,
    [
      'artifactType',
      'artifactVersion',
      'forecastWeek',
      'historicalError',
      'leakageControlsVerified',
      'name',
      'pointEstimatesOnly',
      'predictionIntervalsAvailable',
      ...(modelStatus === 'available' ? [] : ['reason']),
      'sourceFile',
      'status',
      'trainingStartWeek',
      'trainingThroughWeek',
      'version',
    ],
    'model',
  )
  if (
    typeof model.sourceFile !== 'string' ||
    model.pointEstimatesOnly !== true ||
    model.predictionIntervalsAvailable !== false ||
    typeof model.leakageControlsVerified !== 'boolean'
  ) {
    throw new Error('Forecast Map model flags are invalid.')
  }
  if (modelStatus === 'available') {
    if (
      model.artifactType !== 'weekly_forecast_ml_model' ||
      model.artifactVersion !== 1 ||
      typeof model.name !== 'string' ||
      !integer(model.version) ||
      model.version < 1 ||
      !isoDate(model.forecastWeek) ||
      !isoDate(model.trainingStartWeek) ||
      !isoDate(model.trainingThroughWeek) ||
      model.trainingThroughWeek !== latestWeek ||
      model.leakageControlsVerified !== true ||
      (hasRows && model.forecastWeek !== weeks[0])
    ) {
      throw new Error('Available Forecast Map model metadata is invalid.')
    }
  } else if (
    typeof model.reason !== 'string' ||
    !model.reason ||
    model.artifactType !== null ||
    model.artifactVersion !== null ||
    model.name !== null ||
    model.version !== null ||
    model.forecastWeek !== null ||
    model.trainingStartWeek !== null ||
    model.trainingThroughWeek !== null ||
    model.leakageControlsVerified !== false ||
    hasRows
  ) {
    throw new Error('Unavailable Forecast Map model metadata is inconsistent.')
  }
  const historical = model.historicalError
  if (!['available', 'missing', 'invalid'].includes(String(historical.status))) {
    throw new Error('Forecast Map historical-error status is invalid.')
  }
  if (historical.status === 'available') {
    exactKeys(
      historical,
      [
        'backtestEndWeek',
        'backtestRowCount',
        'backtestStartWeek',
        'filterSemantics',
        'mae',
        'predictionCoveragePct',
        'rmse',
        'scope',
        'sourceFile',
        'status',
        'unit',
        'weightedMae',
      ],
      'historical error',
    )
    if (
      !finite(historical.mae) ||
      historical.mae < 0 ||
      !finite(historical.rmse) ||
      historical.rmse < 0 ||
      (historical.weightedMae !== null &&
        (!finite(historical.weightedMae) || historical.weightedMae < 0)) ||
      !finite(historical.predictionCoveragePct) ||
      historical.predictionCoveragePct < 0 ||
      historical.predictionCoveragePct > 100 ||
      !integer(historical.backtestRowCount) ||
      !isoDate(historical.backtestStartWeek) ||
      !isoDate(historical.backtestEndWeek) ||
      historical.backtestEndWeek !== latestComplete ||
      typeof historical.sourceFile !== 'string' ||
      typeof historical.unit !== 'string' ||
      typeof historical.scope !== 'string' ||
      typeof historical.filterSemantics !== 'string'
    ) {
      throw new Error('Forecast Map historical-error context is invalid.')
    }
  } else {
    exactKeys(historical, ['reason', 'sourceFile', 'status'], 'historical error')
    if (
      typeof historical.reason !== 'string' ||
      !historical.reason ||
      typeof historical.sourceFile !== 'string'
    ) {
      throw new Error('Unavailable Forecast Map historical-error context is invalid.')
    }
  }

  const location = value.locationKeySemantics
  if (!record(location)) throw new Error('Forecast Map spatial-reference contract is invalid.')
  exactKeys(
    location,
    [
      'coordinatesIncluded',
      'coverage',
      'geometryIncluded',
      'scheme',
      'spatialReferenceAvailable',
      'stableJoinKeyOnly',
    ],
    'location-key semantics',
  )
  if (
    location.coordinatesIncluded !== false ||
    location.geometryIncluded !== false ||
    location.spatialReferenceAvailable !== false ||
    location.stableJoinKeyOnly !== true ||
    location.scheme !== 'nypd-precinct:<source precinct label>' ||
    typeof location.coverage !== 'string'
  ) {
    throw new Error('Forecast Map spatial-reference contract is invalid.')
  }
  if (!Array.isArray(value.limitations) || !value.limitations.every((item) => typeof item === 'string')) {
    throw new Error('Forecast Map limitations are invalid.')
  }
  assertProvenance(value.provenance)
  assertSafeFlags(value)
  return value as unknown as ForecastMapContract
}

export async function loadForecastMap(): Promise<ForecastMapContract> {
  const response = await fetch(PATH, { cache: 'no-cache' })
  if (!response.ok) throw new Error('Forecast Map data could not be loaded.')
  return decodeForecastMap(await response.json())
}

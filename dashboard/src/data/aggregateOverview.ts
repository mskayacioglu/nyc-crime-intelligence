import type {
  AttentionRow,
  IndexedRow,
  ObservedCube,
  ObservedView,
  OverviewFilters,
  OverviewMetadata,
  RankedValue,
  SignalContract,
  SignalView,
} from '../types/overview'

const BASELINE_WEEKS = 8
const COMPARISON_WEEKS = 4

function lowerBound(values: ArrayLike<number>, target: number): number {
  let low = 0
  let high = values.length
  while (low < high) {
    const middle = (low + high) >>> 1
    if (values[middle] < target) low = middle + 1
    else high = middle
  }
  return low
}

function upperBound(values: ArrayLike<number>, target: number): number {
  let low = 0
  let high = values.length
  while (low < high) {
    const middle = (low + high) >>> 1
    if (values[middle] <= target) low = middle + 1
    else high = middle
  }
  return low
}

function firstWeekAtOrAfter(weeks: string[], date: string): number {
  let low = 0
  let high = weeks.length
  while (low < high) {
    const middle = (low + high) >>> 1
    if (weeks[middle] < date) low = middle + 1
    else high = middle
  }
  return Math.min(low, weeks.length - 1)
}

function lastWeekAtOrBefore(weeks: string[], date: string): number {
  let low = 0
  let high = weeks.length
  while (low < high) {
    const middle = (low + high) >>> 1
    if (weeks[middle] <= date) low = middle + 1
    else high = middle
  }
  return Math.max(0, low - 1)
}

export function defaultFilters(metadata: OverviewMetadata): OverviewFilters {
  return {
    startWeek: metadata.dataRange.defaultStartWeek,
    endWeek: metadata.dataRange.defaultEndWeek,
    boroughIndex: null,
    precinctIndex: null,
    offenseIndex: null,
    lawIndex: null,
  }
}

export function precinctOptions(
  metadata: OverviewMetadata,
  boroughIndex: number | null,
): number[] {
  if (boroughIndex === null) {
    return metadata.dimensions.precincts.map((_, index) => index)
  }
  const mapping = metadata.filterIndex.precinctsByBorough.rows.find(
    ([index]) => index === boroughIndex,
  )
  return mapping ? [...mapping[1]] : []
}

function matchesFilters(
  row: number,
  cube: ObservedCube,
  filters: OverviewFilters,
): boolean {
  return (
    (filters.boroughIndex === null ||
      cube.boroughs[row] === filters.boroughIndex) &&
    (filters.precinctIndex === null ||
      cube.precincts[row] === filters.precinctIndex) &&
    (filters.offenseIndex === null ||
      cube.offenses[row] === filters.offenseIndex) &&
    (filters.lawIndex === null || cube.laws[row] === filters.lawIndex)
  )
}

function ranked(values: Float64Array, labels: string[], limit?: number): RankedValue[] {
  const result = Array.from(values, (value, index) => ({
    label: labels[index],
    value,
    index,
  }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label))
  return limit === undefined ? result : result.slice(0, limit)
}

export function aggregateObserved(
  metadata: OverviewMetadata,
  cube: ObservedCube,
  filters: OverviewFilters,
): ObservedView {
  const { weeks } = metadata.dimensions
  const startWeekIndex = firstWeekAtOrAfter(weeks, filters.startWeek)
  const endWeekIndex = lastWeekAtOrBefore(weeks, filters.endWeek)
  if (startWeekIndex > endWeekIndex) {
    return {
      selectedTotal: 0,
      weekly: [],
      boroughs: [],
      offenses: [],
      laws: [],
      comparison: null,
      isEmpty: true,
    }
  }

  const baselineStartIndex = Math.max(0, startWeekIndex - BASELINE_WEEKS)
  const offsets = cube.weekRowOffsets
  const canUseOffsets =
    offsets !== undefined && endWeekIndex + 1 < offsets.length
  const rowStart = canUseOffsets
    ? offsets[baselineStartIndex]
    : lowerBound(cube.weeks, baselineStartIndex)
  const rowEnd = canUseOffsets
    ? offsets[endWeekIndex + 1]
    : upperBound(cube.weeks, endWeekIndex)
  const weeklyCounts = new Float64Array(endWeekIndex - baselineStartIndex + 1)
  const boroughCounts = new Float64Array(metadata.dimensions.boroughs.length)
  const offenseCounts = new Float64Array(metadata.dimensions.offenseTypes.length)
  const lawCounts = new Float64Array(metadata.dimensions.lawCategories.length)
  let selectedTotal = 0

  for (let row = rowStart; row < rowEnd; row += 1) {
    if (!matchesFilters(row, cube, filters)) continue
    const count = cube.counts[row]
    const weekIndex = cube.weeks[row]
    weeklyCounts[weekIndex - baselineStartIndex] += count

    if (weekIndex < startWeekIndex) continue
    selectedTotal += count
    boroughCounts[cube.boroughs[row]] += count
    offenseCounts[cube.offenses[row]] += count
    lawCounts[cube.laws[row]] += count
  }

  const latestCompleteIndex = weeks.indexOf(metadata.dataRange.latestCompleteWeek)
  const weekly = []
  for (let weekIndex = startWeekIndex; weekIndex <= endWeekIndex; weekIndex += 1) {
    const localIndex = weekIndex - baselineStartIndex
    let baseline: number | null = null
    if (localIndex >= BASELINE_WEEKS) {
      let priorTotal = 0
      for (let prior = localIndex - BASELINE_WEEKS; prior < localIndex; prior += 1) {
        priorTotal += weeklyCounts[prior]
      }
      baseline = Math.round((priorTotal / BASELINE_WEEKS) * 10) / 10
    }
    weekly.push({
      week: weeks[weekIndex],
      count: weeklyCounts[localIndex],
      baseline,
      isPartial: latestCompleteIndex >= 0 && weekIndex > latestCompleteIndex,
    })
  }

  const completePoints = weekly.filter((point) => !point.isPartial)
  const comparisonWindow = Math.min(
    COMPARISON_WEEKS,
    Math.floor(completePoints.length / 2),
  )
  let comparison = null
  if (comparisonWindow > 0) {
    const recent = completePoints.slice(-comparisonWindow)
    const prior = completePoints.slice(-comparisonWindow * 2, -comparisonWindow)
    const recentCount = recent.reduce((sum, point) => sum + point.count, 0)
    const priorCount = prior.reduce((sum, point) => sum + point.count, 0)
    comparison = {
      recentCount,
      priorCount,
      percentChange:
        priorCount === 0
          ? null
          : Math.round(((recentCount - priorCount) / priorCount) * 1000) / 10,
      windowWeeks: comparisonWindow,
      recentStart: recent[0].week,
      recentEnd: recent.at(-1)?.week ?? recent[0].week,
      priorStart: prior[0].week,
      priorEnd: prior.at(-1)?.week ?? prior[0].week,
    }
  }

  return {
    selectedTotal,
    weekly,
    boroughs: ranked(boroughCounts, metadata.dimensions.boroughs),
    offenses: ranked(offenseCounts, metadata.dimensions.offenseTypes, 8),
    laws: ranked(lawCounts, metadata.dimensions.lawCategories),
    comparison,
    isEmpty: selectedTotal === 0,
  }
}

function columnIndex(contract: SignalContract, name: string): number {
  return contract.rowColumns?.indexOf(name) ?? -1
}

function numberField(
  row: IndexedRow,
  contract: SignalContract,
  name: string,
): number | null {
  const index = columnIndex(contract, name)
  const value = index >= 0 ? row[index] : null
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function stringField(
  row: IndexedRow,
  contract: SignalContract,
  name: string,
): string | null {
  const index = columnIndex(contract, name)
  const value = index >= 0 ? row[index] : null
  return typeof value === 'string' ? value : null
}

function signalMatches(
  row: IndexedRow,
  contract: SignalContract,
  filters: OverviewFilters,
): boolean {
  const pairs: Array<[string, number | null]> = [
    ['boroughIndex', filters.boroughIndex],
    ['precinctIndex', filters.precinctIndex],
    ['offenseTypeIndex', filters.offenseIndex],
    ['lawCategoryIndex', filters.lawIndex],
  ]
  return pairs.every(([column, selected]) => {
    if (selected === null) return true
    return numberField(row, contract, column) === selected
  })
}

function signalAvailable(contract: SignalContract): boolean {
  return contract.status === 'available' && Array.isArray(contract.rows)
}

function severityFor(
  metadata: OverviewMetadata,
  contract: SignalContract,
  row: IndexedRow,
): string {
  const index = numberField(row, contract, 'severityIndex')
  return index === null ? 'unknown' : (metadata.dimensions.severities[index] ?? 'unknown')
}

function areaFor(
  metadata: OverviewMetadata,
  contract: SignalContract,
  row: IndexedRow,
): string {
  const boroughIndex = numberField(row, contract, 'boroughIndex')
  const precinctIndex = numberField(row, contract, 'precinctIndex')
  const borough = boroughIndex === null ? 'CITYWIDE' : metadata.dimensions.boroughs[boroughIndex]
  const precinct =
    precinctIndex === null ? null : metadata.dimensions.precincts[precinctIndex]
  return precinct ? `${borough} · PCT ${precinct}` : borough
}

function dimensionLabel(
  values: string[],
  contract: SignalContract,
  row: IndexedRow,
  column: string,
): string {
  const index = numberField(row, contract, column)
  return index === null ? 'ALL' : (values[index] ?? 'UNKNOWN')
}

function forecastSummaryError(contract: SignalContract): {
  available: boolean
  mae: number | null
  rmse: number | null
  weightedMae: number | null
  coveragePct: number | null
  unit: string | null
  scope: string | null
  filterSemantics: string | null
  reason: string | null
  limitations: string[]
} {
  const historicalError = contract.summary?.historicalError
  const error =
    historicalError && typeof historicalError === 'object'
      ? (historicalError as Record<string, unknown>)
      : null
  const summaryLimitations = contract.summary?.limitations
  const unit = error?.unit
  const scope = error?.scope
  const filterSemantics = error?.filterSemantics
  const reason = error?.reason
  const numeric = (key: string): number | null => {
    const value = error?.[key]
    return typeof value === 'number' && Number.isFinite(value) ? value : null
  }
  return {
    available: error?.status === 'available',
    mae: numeric('mae'),
    rmse: numeric('rmse'),
    weightedMae: numeric('weightedMae'),
    coveragePct: numeric('predictionCoveragePct'),
    unit: typeof unit === 'string' ? unit : null,
    scope: typeof scope === 'string' ? scope : null,
    filterSemantics: typeof filterSemantics === 'string' ? filterSemantics : null,
    reason: typeof reason === 'string' ? reason : null,
    limitations: Array.isArray(summaryLimitations)
      ? summaryLimitations.filter((value): value is string => typeof value === 'string')
      : [],
  }
}

function summaryString(contract: SignalContract, key: string): string | null {
  const value = contract.summary?.[key]
  return typeof value === 'string' ? value : null
}

function summaryNumber(contract: SignalContract, key: string): number | null {
  const value = contract.summary?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function signalRowsAreValid(contract: SignalContract, fields: string[]): boolean {
  return (
    signalAvailable(contract) &&
    (contract.rows ?? []).every((row) =>
      fields.every((field) => numberField(row, contract, field) !== null),
    )
  )
}

export function aggregateSignals(
  metadata: OverviewMetadata,
  filters: OverviewFilters,
): SignalView {
  const { hotspots, anomalies, forecast } = metadata.signals
  const weeks = metadata.dimensions.weeks
  const startIndex = firstWeekAtOrAfter(weeks, filters.startWeek)
  const endIndex = lastWeekAtOrBefore(weeks, filters.endWeek)
  const completeIndex = weeks.indexOf(metadata.dataRange.latestCompleteWeek)
  const currentWindow = completeIndex >= 0 && endIndex >= completeIndex
  const hotspotSourceValid = signalRowsAreValid(hotspots, [
    'recentCount',
    'expectedRecentCount',
    'liftPct',
    'score',
  ])
  const anomalySourceValid = signalRowsAreValid(anomalies, [
    'actualCount',
    'expectedCount',
    'residualCount',
    'score',
  ])
  const forecastSourceValid = signalRowsAreValid(forecast, ['predictedCount'])

  const hotspotRows = hotspotSourceValid && currentWindow
    ? (hotspots.rows ?? []).filter((row) => signalMatches(row, hotspots, filters))
    : []
  const anomalyRows = anomalySourceValid
    ? (anomalies.rows ?? []).filter((row) => {
        const week = numberField(row, anomalies, 'weekIndex')
        return (
          week !== null &&
          week >= startIndex &&
          week <= endIndex &&
          signalMatches(row, anomalies, filters)
        )
      })
    : []
  const forecastRows = forecastSourceValid && currentWindow
    ? (forecast.rows ?? []).filter((row) => signalMatches(row, forecast, filters))
    : []

  const hotspotCritical = hotspotRows.filter(
    (row) => severityFor(metadata, hotspots, row) === 'critical',
  ).length
  const anomalyCritical = anomalyRows.filter(
    (row) => severityFor(metadata, anomalies, row) === 'critical',
  ).length

  const attention: AttentionRow[] = []
  hotspotRows.forEach((row, index) => {
    const recentCount = numberField(row, hotspots, 'recentCount')
    const expectedRecentCount = numberField(row, hotspots, 'expectedRecentCount')
    const score = numberField(row, hotspots, 'score')
    if (recentCount === null || expectedRecentCount === null || score === null) return
    const locationLabel = stringField(row, hotspots, 'locationLabel')
    const area = areaFor(metadata, hotspots, row)
    attention.push({
      id: `hotspot-${index}-${score}`,
      kind: 'Hotspot',
      severity: severityFor(metadata, hotspots, row),
      period: stringField(row, hotspots, 'scoringEndDate') ?? 'Latest scan',
      area: locationLabel ? `${area} · ${locationLabel}` : area,
      offense: dimensionLabel(
        metadata.dimensions.offenseTypes,
        hotspots,
        row,
        'offenseTypeIndex',
      ),
      law: dimensionLabel(
        metadata.dimensions.lawCategories,
        hotspots,
        row,
        'lawCategoryIndex',
      ),
      observedLabel: 'Recent count',
      observedValue: recentCount,
      referenceLabel: 'Expected recent count',
      referenceValue: expectedRecentCount,
      score,
    })
  })
  anomalyRows.forEach((row, index) => {
    const weekIndex = numberField(row, anomalies, 'weekIndex')
    const actualCount = numberField(row, anomalies, 'actualCount')
    const expectedCount = numberField(row, anomalies, 'expectedCount')
    const score = numberField(row, anomalies, 'score')
    if (
      weekIndex === null ||
      actualCount === null ||
      expectedCount === null ||
      score === null
    ) return
    const expectedSourceIndex = numberField(row, anomalies, 'expectedSourceIndex')
    const expectedSource =
      expectedSourceIndex === null
        ? 'historical expectation'
        : (metadata.dimensions.anomalyExpectedSources[expectedSourceIndex] ??
          'historical expectation')
    const referenceLabel =
      expectedSource === 'ml_prediction'
        ? 'Model estimate'
        : expectedSource === 'rolling_13_week_mean'
          ? '13-week average'
          : 'Historical expectation'
    attention.push({
      id: `anomaly-${index}-${weekIndex}`,
      kind: 'Anomaly',
      severity: severityFor(metadata, anomalies, row),
      period: weeks[weekIndex] ?? 'Unknown week',
      area: areaFor(metadata, anomalies, row),
      offense: dimensionLabel(
        metadata.dimensions.offenseTypes,
        anomalies,
        row,
        'offenseTypeIndex',
      ),
      law: dimensionLabel(
        metadata.dimensions.lawCategories,
        anomalies,
        row,
        'lawCategoryIndex',
      ),
      observedLabel: 'Observed',
      observedValue: actualCount,
      referenceLabel,
      referenceValue: expectedCount,
      score,
    })
  })
  attention.sort((a, b) => {
    const severityOrder = { critical: 0, high: 1, unknown: 2 }
    return (
      (severityOrder[a.severity as keyof typeof severityOrder] ?? 3) -
        (severityOrder[b.severity as keyof typeof severityOrder] ?? 3) ||
      b.score - a.score ||
      a.kind.localeCompare(b.kind) ||
      b.period.localeCompare(a.period) ||
      a.id.localeCompare(b.id)
    )
  })

  const summaryError = forecastSummaryError(forecast)
  const mae = summaryError.mae
  const rmse = summaryError.rmse
  const weightedMae = summaryError.weightedMae
  const coveragePct = summaryError.coveragePct
  const hasHistoricalError =
    summaryError.available && mae !== null && rmse !== null
  const predictedTotal = forecastRows.reduce(
    (sum, row) => sum + (numberField(row, forecast, 'predictedCount') as number),
    0,
  )
  const firstForecast = forecastRows[0]
  const forecastWeekIndex = firstForecast
    ? numberField(firstForecast, forecast, 'weekIndex')
    : null
  const modelIndex = firstForecast
    ? numberField(firstForecast, forecast, 'modelNameIndex')
    : null

  return {
    hotspots: {
      available: hotspotSourceValid,
      currentWindow,
      total: hotspotRows.length,
      critical: hotspotCritical,
      high: hotspotRows.length - hotspotCritical,
      scanDate:
        summaryString(hotspots, 'snapshotDate') ??
        (hotspotRows.length > 0
          ? stringField(hotspotRows[0], hotspots, 'scoringEndDate')
          : null),
      snapshotAgeDays: summaryNumber(hotspots, 'snapshotAgeDays'),
      reason:
        hotspots.reason ??
        (signalAvailable(hotspots) && !hotspotSourceValid
          ? 'Hotspot contract contains invalid required numeric values.'
          : undefined),
    },
    anomalies: {
      available: anomalySourceValid,
      total: anomalyRows.length,
      critical: anomalyCritical,
      high: anomalyRows.length - anomalyCritical,
      reason:
        anomalies.reason ??
        (signalAvailable(anomalies) && !anomalySourceValid
          ? 'Anomaly contract contains invalid required numeric values.'
          : undefined),
    },
    forecast: {
      available:
        forecastSourceValid &&
        currentWindow &&
        forecastRows.length > 0 &&
        hasHistoricalError,
      currentWindow,
      predictedTotal:
        forecastRows.length > 0 ? Math.round(predictedTotal * 10) / 10 : null,
      forecastWeek:
        forecastWeekIndex === null ? null : (weeks[forecastWeekIndex] ?? null),
      modelName:
        modelIndex === null ? null : (metadata.dimensions.modelNames[modelIndex] ?? null),
      mae,
      rmse,
      weightedMae,
      coveragePct,
      errorUnit: summaryError.unit,
      errorScope: summaryError.scope,
      errorFilterSemantics: summaryError.filterSemantics,
      limitations: summaryError.limitations,
      reason:
        forecast.reason ??
        (signalAvailable(forecast) && !forecastSourceValid
          ? 'Forecast contract contains invalid required numeric values.'
          : summaryError.reason) ??
        (!hasHistoricalError
          ? 'Historical error metrics are unavailable; no forecast total is presented.'
          : undefined),
    },
    attention: attention.slice(0, 10),
  }
}

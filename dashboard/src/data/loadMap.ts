import {
  MAP_HOTSPOT_ROW_COLUMNS,
  type MapDataContract,
  type MapDimensions,
  type MapHotspotRow,
  type MapLoader,
} from '../types/map'

const DEFAULT_MAP_PATH = '/data/map.json'
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isNonNegativeInteger(value: unknown): value is number {
  return isFiniteNumber(value) && Number.isInteger(value) && value >= 0
}

function isIsoDate(value: unknown): value is string {
  if (typeof value !== 'string' || !ISO_DATE.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value
}

function dateDifferenceDays(startDate: string, endDate: string): number {
  const start = Date.parse(`${startDate}T00:00:00Z`)
  const end = Date.parse(`${endDate}T00:00:00Z`)
  return Math.round((end - start) / 86_400_000)
}

function stringArray(value: unknown, name: string): string[] {
  if (
    !Array.isArray(value) ||
    !value.every((item) => typeof item === 'string' && item.length > 0)
  ) {
    throw new Error(`The Map ${name} dimension is invalid.`)
  }
  if (new Set(value).size !== value.length) {
    throw new Error(`The Map ${name} dimension contains duplicates.`)
  }
  return value
}

function parseDimensions(value: unknown): MapDimensions {
  if (!isRecord(value)) {
    throw new Error('The Map dimensions are missing.')
  }
  return {
    hotspotGrains: stringArray(value.hotspotGrains, 'hotspotGrains'),
    boroughs: stringArray(value.boroughs, 'boroughs'),
    precincts: stringArray(value.precincts, 'precincts'),
    offenseTypes: stringArray(value.offenseTypes, 'offenseTypes'),
    lawCategories: stringArray(value.lawCategories, 'lawCategories'),
    severities: stringArray(value.severities, 'severities'),
  }
}

function validIndex(value: unknown, dimension: string[]): value is number {
  return isNonNegativeInteger(value) && value < dimension.length
}

function nullableFinite(value: unknown): value is number | null {
  return value === null || isFiniteNumber(value)
}

function assertRow(
  value: unknown,
  dimensions: MapDimensions,
  rowNumber: number,
): asserts value is MapHotspotRow {
  if (!Array.isArray(value) || value.length !== MAP_HOTSPOT_ROW_COLUMNS.length) {
    throw new Error(`Map hotspot row ${rowNumber} does not match the contract.`)
  }

  const [
    rank,
    grainIndex,
    boroughIndex,
    precinctIndex,
    offenseTypeIndex,
    lawCategoryIndex,
    latitude,
    longitude,
    locationLabel,
    recentCount,
    expectedRecentCount,
    liftPct,
    score,
    severityIndex,
    coordinateCoveragePct,
  ] = value

  const valid =
    isFiniteNumber(rank) &&
    Number.isInteger(rank) &&
    rank > 0 &&
    validIndex(grainIndex, dimensions.hotspotGrains) &&
    validIndex(boroughIndex, dimensions.boroughs) &&
    (precinctIndex === null || validIndex(precinctIndex, dimensions.precincts)) &&
    validIndex(offenseTypeIndex, dimensions.offenseTypes) &&
    validIndex(lawCategoryIndex, dimensions.lawCategories) &&
    isFiniteNumber(latitude) &&
    latitude >= -90 &&
    latitude <= 90 &&
    isFiniteNumber(longitude) &&
    longitude >= -180 &&
    longitude <= 180 &&
    typeof locationLabel === 'string' &&
    locationLabel.length > 0 &&
    isNonNegativeInteger(recentCount) &&
    nullableFinite(expectedRecentCount) &&
    (expectedRecentCount === null || expectedRecentCount >= 0) &&
    nullableFinite(liftPct) &&
    isFiniteNumber(score) &&
    score >= 0 &&
    score <= 100 &&
    validIndex(severityIndex, dimensions.severities) &&
    isFiniteNumber(coordinateCoveragePct) &&
    coordinateCoveragePct >= 0 &&
    coordinateCoveragePct <= 100

  if (!valid) {
    throw new Error(`Map hotspot row ${rowNumber} contains an invalid value.`)
  }

  const grain = dimensions.hotspotGrains[grainIndex].toLocaleLowerCase('en-US')
  if (
    (grain === 'grid' && precinctIndex !== null) ||
    (grain === 'precinct' && precinctIndex === null) ||
    (grain !== 'grid' && grain !== 'precinct')
  ) {
    throw new Error(`Map hotspot row ${rowNumber} has invalid grain semantics.`)
  }
}

function assertRowsAreUnique(rows: MapHotspotRow[]): void {
  const ranks = new Set<number>()
  const logicalKeys = new Set<string>()
  rows.forEach((row, index) => {
    const rank = row[0]
    const logicalKey = JSON.stringify([
      row[1],
      row[2],
      row[3],
      row[4],
      row[5],
      row[6],
      row[7],
    ])
    if (ranks.has(rank) || logicalKeys.has(logicalKey)) {
      throw new Error(`Map hotspot row ${index + 1} duplicates a logical key.`)
    }
    ranks.add(rank)
    logicalKeys.add(logicalKey)
  })
}

function assertSummary(value: unknown, rowCount: number): void {
  if (!isRecord(value)) {
    throw new Error('The Map hotspot summary is missing.')
  }
  const nullableNonNegativeInteger = (candidate: unknown) =>
    candidate === null || isNonNegativeInteger(candidate)
  const nullablePositiveInteger = (candidate: unknown) =>
    candidate === null || (isNonNegativeInteger(candidate) && candidate > 0)
  const valid =
    value.rowCount === rowCount &&
    (value.scoringEndDate === null || isIsoDate(value.scoringEndDate)) &&
    nullableNonNegativeInteger(value.snapshotAgeDays) &&
    value.currentMaxAgeDays === 1 &&
    nullablePositiveInteger(value.recentWindowDays) &&
    nullablePositiveInteger(value.baselineWindowDays) &&
    (value.gridSizeDegrees === null ||
      (isFiniteNumber(value.gridSizeDegrees) && value.gridSizeDegrees > 0)) &&
    isRecord(value.counts)

  if (!valid) {
    throw new Error('The Map hotspot summary is invalid.')
  }
}

function assertFilterIndex(value: unknown, dimensions: MapDimensions): void {
  if (!isRecord(value) || !isRecord(value.precinctsByBorough)) {
    throw new Error('The Map filter index is missing.')
  }
  const index = value.precinctsByBorough
  if (
    !Array.isArray(index.rowColumns) ||
    index.rowColumns.length !== 2 ||
    index.rowColumns[0] !== 'boroughIndex' ||
    index.rowColumns[1] !== 'precinctIndexes' ||
    typeof index.semantics !== 'string' ||
    !Array.isArray(index.rows)
  ) {
    throw new Error('The Map filter index is invalid.')
  }
  const boroughs = new Set<number>()
  for (const row of index.rows) {
    if (
      !Array.isArray(row) ||
      row.length !== 2 ||
      !validIndex(row[0], dimensions.boroughs) ||
      !Array.isArray(row[1]) ||
      !row[1].every((value) => validIndex(value, dimensions.precincts)) ||
      new Set(row[1]).size !== row[1].length ||
      boroughs.has(row[0])
    ) {
      throw new Error('The Map filter index is invalid.')
    }
    boroughs.add(row[0])
  }
}

function assertEthics(value: unknown): void {
  if (!isRecord(value)) {
    throw new Error('The Map responsible-use contract is missing.')
  }
  const privacySafe =
    value.aggregateTrendIntelligenceOnly === true &&
    value.demographicAttributesIncluded === false &&
    value.enforcementRecommendations === false &&
    value.eventRecordsIncluded === false &&
    value.patrolRecommendations === false &&
    value.personLevelScoring === false
  if (!privacySafe) {
    throw new Error('The Map responsible-use contract is incompatible.')
  }
}

function assertMapContract(value: unknown): asserts value is MapDataContract {
  if (!isRecord(value)) {
    throw new Error('The Map response is not a JSON object.')
  }
  if (
    typeof value.schemaVersion !== 'string' ||
    typeof value.generatedAtUtc !== 'string' ||
    !isRecord(value.application) ||
    value.application.name !== 'NYC Crime Intelligence' ||
    typeof value.application.phase !== 'string' ||
    typeof value.application.view !== 'string' ||
    !isRecord(value.dataRange) ||
    !isIsoDate(value.dataRange.safeEventStartDate) ||
    !isIsoDate(value.dataRange.safeEventEndDate) ||
    !isNonNegativeInteger(value.dataRange.aggregateSafeEventCount) ||
    !isNonNegativeInteger(value.dataRange.sourceEventCount) ||
    !isNonNegativeInteger(value.dataRange.excludedEventCount) ||
    value.dataRange.sourceEventCount - value.dataRange.excludedEventCount !==
      value.dataRange.aggregateSafeEventCount ||
    typeof value.dataRange.unit !== 'string' ||
    !isRecord(value.methodology) ||
    !isRecord(value.provenance) ||
    !isRecord(value.filterSemantics) ||
    !isRecord(value.coordinateSemantics) ||
    !isRecord(value.dateSemantics) ||
    !isRecord(value.grainSemantics) ||
    !Array.isArray(value.limitations) ||
    !value.limitations.every((item) => typeof item === 'string')
  ) {
    throw new Error('The Map contract is incomplete or incompatible.')
  }

  const dimensions = parseDimensions(value.dimensions)
  assertFilterIndex(value.filterIndex, dimensions)
  if (!isRecord(value.hotspots)) {
    throw new Error('The Map hotspot contract is missing.')
  }
  const hotspot = value.hotspots
  if (
    !['available', 'missing', 'invalid', 'stale'].includes(String(hotspot.status)) ||
    typeof hotspot.sourceFile !== 'string' ||
    (hotspot.reason !== undefined && typeof hotspot.reason !== 'string') ||
    !Array.isArray(hotspot.rowColumns) ||
    hotspot.rowColumns.length !== MAP_HOTSPOT_ROW_COLUMNS.length ||
    !hotspot.rowColumns.every(
      (column, index) => column === MAP_HOTSPOT_ROW_COLUMNS[index],
    ) ||
    !Array.isArray(hotspot.rows)
  ) {
    throw new Error('The Map hotspot contract is incomplete or incompatible.')
  }

  if (hotspot.status !== 'available' && typeof hotspot.reason !== 'string') {
    throw new Error('A non-available Map hotspot contract requires a reason.')
  }

  hotspot.rows.forEach((row, index) => assertRow(row, dimensions, index + 1))
  if (hotspot.status !== 'available' && hotspot.rows.length > 0) {
    throw new Error('A non-available Map hotspot contract cannot expose rows.')
  }
  assertRowsAreUnique(hotspot.rows as MapHotspotRow[])
  assertSummary(hotspot.summary, hotspot.rows.length)
  const summary = hotspot.summary as Record<string, unknown>
  if (hotspot.status === 'available' && hotspot.rows.length > 0) {
    if (
      !isIsoDate(summary.scoringEndDate) ||
      summary.scoringEndDate > value.dataRange.safeEventEndDate
    ) {
      throw new Error('An available Map hotspot snapshot has an invalid scoring date.')
    }
    if (
      !isNonNegativeInteger(summary.snapshotAgeDays) ||
      summary.snapshotAgeDays > 1
    ) {
      throw new Error('An available Map hotspot snapshot exceeds the freshness limit.')
    }
    if (
      summary.snapshotAgeDays !==
      dateDifferenceDays(
        summary.scoringEndDate as string,
        value.dataRange.safeEventEndDate,
      )
    ) {
      throw new Error('The Map hotspot snapshot age is inconsistent with its dates.')
    }
  }
  assertEthics(value.ethics)
}

async function fetchOk(path: string): Promise<Response> {
  const response = await fetch(path, { cache: 'no-cache' })
  if (!response.ok) {
    throw new Error(`Map data could not be loaded (${response.status}).`)
  }
  return response
}

export const loadMap: MapLoader = async () => {
  const response = await fetchOk(DEFAULT_MAP_PATH)
  const value: unknown = await response.json()
  assertMapContract(value)
  return value
}

export { assertMapContract }

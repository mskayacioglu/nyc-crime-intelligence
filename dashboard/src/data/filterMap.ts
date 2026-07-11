import type {
  HotspotLayer,
  MapDataContract,
  MapFilterResult,
  MapHotspot,
  MapHotspotRow,
} from '../types/map'
import type { OverviewFilters, OverviewMetadata } from '../types/overview'

function normalizedLabel(value: string): string {
  return value.trim().toLocaleUpperCase('en-US')
}

function dimensionLabel(values: string[], index: number): string {
  return values[index] ?? 'UNKNOWN'
}

function resolveRow(
  row: MapHotspotRow,
  contract: MapDataContract,
): MapHotspot {
  return {
    id: `hotspot-${row[0]}`,
    rank: row[0],
    grain: dimensionLabel(contract.dimensions.hotspotGrains, row[1]),
    borough: dimensionLabel(contract.dimensions.boroughs, row[2]),
    precinct:
      row[3] === null
        ? null
        : dimensionLabel(contract.dimensions.precincts, row[3]),
    offenseType: dimensionLabel(contract.dimensions.offenseTypes, row[4]),
    lawCategory: dimensionLabel(contract.dimensions.lawCategories, row[5]),
    latitude: row[6],
    longitude: row[7],
    locationLabel: row[8],
    recentCount: row[9],
    expectedRecentCount: row[10],
    liftPct: row[11],
    score: row[12],
    severity: dimensionLabel(contract.dimensions.severities, row[13]),
    coordinateCoveragePct: row[14],
  }
}

function matchesSelectedLabel(
  value: string | null,
  overviewValues: string[],
  selectedIndex: number | null,
): boolean {
  if (selectedIndex === null) return true
  const selected = overviewValues[selectedIndex]
  return (
    selected !== undefined &&
    value !== null &&
    normalizedLabel(value) === normalizedLabel(selected)
  )
}

function matchesNonPrecinctFilters(
  row: MapHotspot,
  metadata: OverviewMetadata,
  filters: OverviewFilters,
): boolean {
  return (
    matchesSelectedLabel(
      row.borough,
      metadata.dimensions.boroughs,
      filters.boroughIndex,
    ) &&
    matchesSelectedLabel(
      row.offenseType,
      metadata.dimensions.offenseTypes,
      filters.offenseIndex,
    ) &&
    matchesSelectedLabel(
      row.lawCategory,
      metadata.dimensions.lawCategories,
      filters.lawIndex,
    )
  )
}

function isGrain(row: MapHotspot, grain: Exclude<HotspotLayer, 'all'>): boolean {
  return normalizedLabel(row.grain) === normalizedLabel(grain)
}

export function filterMapHotspots(
  contract: MapDataContract,
  metadata: OverviewMetadata,
  filters: OverviewFilters,
  layer: HotspotLayer,
): MapFilterResult {
  const decoded = contract.hotspots.rows.map((row) => resolveRow(row, contract))
  const nonPrecinctRows = decoded.filter((row) =>
    matchesNonPrecinctFilters(row, metadata, filters),
  )
  const gridExcludedByPrecinct =
    filters.precinctIndex !== null &&
    nonPrecinctRows.some((row) => isGrain(row, 'grid'))
  const scopeRows = nonPrecinctRows.filter((row) =>
    matchesSelectedLabel(
      row.precinct,
      metadata.dimensions.precincts,
      filters.precinctIndex,
    ),
  )
  const layerCounts: Record<HotspotLayer, number> = {
    all: scopeRows.length,
    grid: scopeRows.filter((row) => isGrain(row, 'grid')).length,
    precinct: scopeRows.filter((row) => isGrain(row, 'precinct')).length,
  }
  const rows =
    layer === 'all'
      ? scopeRows
      : scopeRows.filter((row) => isGrain(row, layer))

  return { rows, scopeRows, layerCounts, gridExcludedByPrecinct }
}

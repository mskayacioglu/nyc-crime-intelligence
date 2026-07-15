import type {
  AnomaliesContract,
  AnomalyRecord,
  FilteredAnomalies,
} from '../types/anomalies'
import type { OverviewFilters } from '../types/overview'

export function filterAnomalyRows(
  rows: AnomalyRecord[],
  filters: OverviewFilters,
): AnomalyRecord[] {
  return rows.filter(
    (row) =>
      row.week >= filters.startWeek &&
      row.week <= filters.endWeek &&
      (filters.boroughIndex === null || row.boroughIndex === filters.boroughIndex) &&
      (filters.precinctIndex === null || row.precinctIndex === filters.precinctIndex) &&
      (filters.offenseIndex === null || row.offenseTypeIndex === filters.offenseIndex) &&
      (filters.lawIndex === null || row.lawCategoryIndex === filters.lawIndex),
  )
}

export function filterAnomalies(
  contract: AnomaliesContract,
  filters: OverviewFilters,
): FilteredAnomalies {
  if (contract.status !== 'available') {
    return {
      rows: [],
      sourceRowCount: 0,
      isFilteredEmpty: false,
      filters,
    }
  }
  const rows = filterAnomalyRows(contract.rows, filters)
  return {
    rows,
    sourceRowCount: contract.sourceRowCount,
    isFilteredEmpty: !contract.isEmpty && rows.length === 0,
    filters,
  }
}

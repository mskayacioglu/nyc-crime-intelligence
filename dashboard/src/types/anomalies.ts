import type { OverviewFilters } from './overview'

export const ANOMALY_ROW_COLUMNS = [
  'weekIndex',
  'boroughIndex',
  'precinctIndex',
  'offenseTypeIndex',
  'lawCategoryIndex',
  'actualCount',
  'expectedCount',
  'residualCount',
  'score',
  'severityIndex',
  'expectedSourceIndex',
] as const

export type AnomalyStatus =
  | 'available'
  | 'missing'
  | 'invalid'
  | 'stale'
  | 'incompatible'

export type AnomalyUnavailableStatus = Exclude<AnomalyStatus, 'available'>
export type AnomalySeverity = 'critical' | 'high'
export type AnomalyExpectedSource =
  | 'ml_prediction'
  | 'rolling_13_week_mean'
export type AnomalyReferenceLabel =
  | 'Historical backtest estimate'
  | 'Prior 13-week average'
export type AnomalyPriorityLabel =
  | 'Critical signal priority'
  | 'High signal priority'

export interface AnomalyRecord {
  id: string
  sourceRank: number
  weekIndex: number
  boroughIndex: number
  precinctIndex: number
  offenseTypeIndex: number
  lawCategoryIndex: number
  week: string
  borough: string
  precinct: string
  offenseType: string
  lawCategory: string
  actualCount: number
  expectedCount: number
  residualCount: number
  signedDeviation: number
  signedDeviationLabel: string
  deviationPct: number | null
  score: number
  severity: AnomalySeverity
  priorityLabel: AnomalyPriorityLabel
  expectedSource: AnomalyExpectedSource
  referenceLabel: AnomalyReferenceLabel
  direction: 'above'
  directionLabel: 'Above expectation'
}

export interface AnomalySummary {
  rowCount: number
  highCount: number
  criticalCount: number
  isEmpty: boolean
  scoringEndWeek: string
}

export interface AvailableAnomaliesContract {
  status: 'available'
  sourceFile: string
  rows: AnomalyRecord[]
  isEmpty: boolean
  sourceRowCount: number
  scoringEndWeek: string
  summary: AnomalySummary
}

export interface UnavailableAnomaliesContract {
  status: AnomalyUnavailableStatus
  sourceFile: string | null
  reason: string
}

export type AnomaliesContract =
  | AvailableAnomaliesContract
  | UnavailableAnomaliesContract

export interface FilteredAnomalies {
  rows: AnomalyRecord[]
  sourceRowCount: number
  isFilteredEmpty: boolean
  filters: OverviewFilters
}

export const FORECAST_MAP_ROW_COLUMNS = [
  'forecastWeekIndex', 'boroughIndex', 'precinctIndex', 'offenseTypeIndex',
  'lawCategoryIndex', 'predictedCount', 'historicalBaseline',
  'expectedChangeCount', 'expectedChangePct', 'precinctLocationKey',
] as const

export type ForecastMapStatus = 'available' | 'missing' | 'invalid' | 'stale'
export type Availability =
  | 'available'
  | 'partial'
  | 'unavailable'
  | 'empty'
  | 'missing'
  | 'invalid'
  | 'stale'
  | 'location-key-only'
export type ForecastMapRow = [number, number, number, number, number, number, number | null, number | null, number | null, string]

export interface ForecastMapContract {
  schemaVersion: '1.0.0'
  generatedAtUtc: string
  application: { name: 'NYC Crime Intelligence'; phase: 'Phase 7C.1'; view: 'Forecast Map Data Contract' }
  dataRange: {
    safeEventStartDate: string; safeEventEndDate: string; firstObservedWeek: string
    latestObservedWeek: string; latestCompleteWeek: string; latestWeekIsPartial: boolean
    supportedForecastWeeks: string[]
  }
  dimensions: { forecastWeeks: string[]; boroughs: string[]; precincts: string[]; offenseTypes: string[]; lawCategories: string[] }
  filterIndex: { precinctsByBorough: { rowColumns: string[]; rows: Array<[number, number[]]>; semantics: string } }
  forecast: {
    status: ForecastMapStatus; sourceFile: string; reason?: string; isEmpty: boolean
    rowColumns: string[]; rows: ForecastMapRow[]
    summary: {
      rowCount: number; sourceRowCount: number | null; sourceSegmentCount: number | null; withheldRowCount: number | null
      predictedTotal: number | null; sourcePredictedTotal: number | null; withheldPredictedTotal: number | null
      rowCoveragePct: number | null; predictedVolumeCoveragePct: number | null; modelSegmentCoveragePct: number | null
      publishedBoroughCount: number; publishedPrecinctCount: number; zeroPredictionRowCount: number
      unknownOffenseRowCount: number; countsByBorough: number[]
      withheldReasonCounts: { boroughMismatch: number; unmappableLocation: number }
    }
  }
  availability: Record<string, Availability>
  model: {
    status: ForecastMapStatus
    reason?: string
    artifactType: 'weekly_forecast_ml_model' | null
    artifactVersion: 1 | null
    name: string | null
    version: number | null
    forecastWeek: string | null
    trainingStartWeek: string | null
    trainingThroughWeek: string | null
    leakageControlsVerified: boolean
    pointEstimatesOnly: true
    predictionIntervalsAvailable: false
    historicalError: {
      status: 'available' | 'missing' | 'invalid'
      reason?: string
      mae?: number
      rmse?: number
      weightedMae?: number | null
      predictionCoveragePct?: number
      backtestRowCount?: number
      backtestStartWeek?: string
      backtestEndWeek?: string
      unit?: string
      scope?: string
      filterSemantics?: string
      sourceFile: string
    }
    sourceFile: string
  }
  baseline: {
    status: ForecastMapStatus
    reason?: string
    method: string | null
    priorOnly: true | null
    requiredPriorWeeks: number | null
    semantics: string | null
    valueAvailability: 'available' | 'partial' | 'unavailable'
    zeroFillRule: string | null
    summary: { publishedRowCount: number; baselineAvailableRowCount: number; baselineUnavailableRowCount: number; expectedChangeCountAvailableRowCount: number; expectedChangePctAvailableRowCount: number; zeroBaselineRowCount: number }
    sourceFile: string
    manifestSourceFile: string
  }
  methodology: { arithmeticTolerance: number; numericRoundingDigits: number; [key: string]: unknown }
  locationKeySemantics: { coordinatesIncluded: false; geometryIncluded: false; spatialReferenceAvailable: false; stableJoinKeyOnly: true; scheme: string; coverage: string }
  forecastSemantics: Record<string, unknown>
  privacy: { aggregateOnly: true; complaintIdentifiersIncluded: false; demographicAttributesIncluded: false; eventLevelCoordinatesIncluded: false; eventRecordsIncluded: false; exactAddressesIncluded: false; namesIncluded: false; sourceRowIdentifiersIncluded: false }
  ethics: { aggregateReportedEventVolumeOnly: true; enforcementRecommendations: false; individualBehaviorPrediction: false; patrolRecommendations: false; personLevelScoring: false; specificIncidentLocationPrediction: false }
  limitations: string[]
  provenance: Record<string, unknown>
}

export type ForecastMapLoader = () => Promise<ForecastMapContract>
export type PredictiveMode = 'forecast' | 'change'
export interface PrecinctForecast {
  id: string; borough: string; precinct: string; forecastWeek: string; predictedCount: number
  historicalBaseline: number | null; expectedChangeCount: number | null; expectedChangePct: number | null
  baselineRows: number; totalRows: number; direction: 'above' | 'below' | 'approximately equal' | 'unavailable'
}

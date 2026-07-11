export type CubeArrayType = 'uint8' | 'uint16' | 'uint32'

export interface CubeColumnSpec {
  type: CubeArrayType
  length: number
  offsetBytes: number
  byteLength: number
  dimension?: keyof OverviewDimensions
  observedWeekCount?: number
  semantics?: string
}

export interface OverviewCubeContract {
  encoding: 'columnar-arrays-v1'
  compression: 'gzip'
  byteOrder: 'little-endian'
  path: string
  rowCount: number
  observedWeekCount?: number
  columnOrder: string[]
  columns: Record<string, CubeColumnSpec>
  compressedByteLength?: number
  compressedBytes?: number
  uncompressedByteLength?: number
  uncompressedBytes?: number
}

export interface OverviewDimensions {
  weeks: string[]
  boroughs: string[]
  precincts: string[]
  offenseTypes: string[]
  lawCategories: string[]
  severities: string[]
  hotspotGrains: string[]
  anomalyExpectedSources: string[]
  modelNames: string[]
}

export type IndexedRow = Array<number | string | null>

export type HotspotRow = [
  grainIndex: number,
  boroughIndex: number,
  precinctIndex: number | null,
  offenseTypeIndex: number,
  lawCategoryIndex: number,
  scoringEndDate: string,
  locationLabel: string | null,
  recentCount: number,
  expectedRecentCount: number,
  liftPct: number,
  score: number,
  severityIndex: number,
]

export type AnomalyRow = [
  weekIndex: number,
  boroughIndex: number,
  precinctIndex: number,
  offenseTypeIndex: number,
  lawCategoryIndex: number,
  actualCount: number,
  expectedCount: number,
  residualCount: number,
  score: number,
  severityIndex: number,
  expectedSourceIndex: number,
]

export type ForecastRow = [
  weekIndex: number,
  boroughIndex: number,
  precinctIndex: number,
  offenseTypeIndex: number,
  lawCategoryIndex: number,
  predictedCount: number,
  modelNameIndex: number,
]

export interface SignalContract<Row extends IndexedRow = IndexedRow> {
  status: string
  sourceFile?: string
  reason?: string
  rowColumns?: string[]
  rows?: Row[]
  summary?: Record<string, unknown>
}

export interface VersionRecord {
  status?: string
  sourceFile?: string
  generatedAtUtc?: string
  phase?: string
  [key: string]: unknown
}

export interface OverviewMetadata {
  schemaVersion: string
  generatedAtUtc: string
  application: {
    name: string
    phase: string
    view: string
  }
  cube: OverviewCubeContract
  dataRange: {
    safeEventStartDate: string
    safeEventEndDate: string
    firstWeek: string
    lastWeek: string
    latestCompleteWeek: string
    latestWeekIsPartial: boolean
    defaultStartWeek: string
    defaultEndWeek: string
  }
  dimensions: OverviewDimensions
  filterIndex: {
    precinctsByBorough: {
      rowColumns: string[]
      rows: Array<[number, number[]]>
      knownPrecinctPolicy?: string
      unknownPrecinctPolicy?: string
    }
  }
  dataQuality: {
    aggregateSafeEventCount: number
    excludedEventCount: number
    cleanSourceRowCount: number
    countsReconciled: boolean
    dateBasis: string
    [key: string]: unknown
  }
  observed: {
    unit: string
    comparisonSemantics: string
    dateFilterSemantics: string
    latestWeekNote: string
    safeEventCount: number
    [key: string]: unknown
  }
  signals: {
    hotspots: SignalContract<HotspotRow>
    anomalies: SignalContract<AnomalyRow>
    forecast: SignalContract<ForecastRow>
  }
  versions: {
    dashboardContract: string
    [key: string]: string | VersionRecord
  }
  ethics: {
    aggregateTrendIntelligenceOnly: boolean
    demographicAttributesIncluded: boolean
    enforcementRecommendations: boolean
    eventRecordsIncluded: boolean
    patrolRecommendations: boolean
    personLevelScoring: boolean
  }
  limitations: string[]
}

export interface ObservedCube {
  counts: Uint32Array
  weeks: Uint16Array
  boroughs: Uint8Array
  precincts: Uint8Array
  offenses: Uint8Array
  laws: Uint8Array
  weekRowOffsets?: Uint32Array
}

export interface OverviewBundle {
  metadata: OverviewMetadata
  cube: ObservedCube
}

export interface OverviewFilters {
  startWeek: string
  endWeek: string
  boroughIndex: number | null
  precinctIndex: number | null
  offenseIndex: number | null
  lawIndex: number | null
}

export interface TimePoint {
  week: string
  count: number
  baseline: number | null
  isPartial: boolean
}

export interface RankedValue {
  label: string
  value: number
  index: number
}

export interface PeriodComparison {
  recentCount: number
  priorCount: number
  percentChange: number | null
  windowWeeks: number
  recentStart: string
  recentEnd: string
  priorStart: string
  priorEnd: string
}

export interface ObservedView {
  selectedTotal: number
  weekly: TimePoint[]
  boroughs: RankedValue[]
  offenses: RankedValue[]
  laws: RankedValue[]
  comparison: PeriodComparison | null
  isEmpty: boolean
}

export interface AttentionRow {
  id: string
  kind: 'Hotspot' | 'Anomaly'
  severity: string
  period: string
  area: string
  offense: string
  law: string
  observedLabel: string
  observedValue: number
  referenceLabel: string
  referenceValue: number
  score: number
}

export interface SignalView {
  hotspots: {
    available: boolean
    currentWindow: boolean
    total: number
    critical: number
    high: number
    scanDate: string | null
    snapshotAgeDays: number | null
    reason?: string
  }
  anomalies: {
    available: boolean
    total: number
    critical: number
    high: number
    reason?: string
  }
  forecast: {
    available: boolean
    currentWindow: boolean
    predictedTotal: number | null
    forecastWeek: string | null
    modelName: string | null
    mae: number | null
    rmse: number | null
    weightedMae: number | null
    coveragePct: number | null
    errorUnit: string | null
    errorScope: string | null
    errorFilterSemantics: string | null
    limitations: string[]
    reason?: string
  }
  attention: AttentionRow[]
}

export type OverviewLoader = () => Promise<OverviewBundle>

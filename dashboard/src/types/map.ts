export const MAP_HOTSPOT_ROW_COLUMNS = [
  'rank',
  'grainIndex',
  'boroughIndex',
  'precinctIndex',
  'offenseTypeIndex',
  'lawCategoryIndex',
  'latitude',
  'longitude',
  'locationLabel',
  'recentCount',
  'expectedRecentCount',
  'liftPct',
  'score',
  'severityIndex',
  'coordinateCoveragePct',
] as const

export type MapHotspotStatus = 'available' | 'missing' | 'invalid' | 'stale'

export type MapHotspotRow = [
  rank: number,
  grainIndex: number,
  boroughIndex: number,
  precinctIndex: number | null,
  offenseTypeIndex: number,
  lawCategoryIndex: number,
  latitude: number,
  longitude: number,
  locationLabel: string,
  recentCount: number,
  expectedRecentCount: number | null,
  liftPct: number | null,
  score: number,
  severityIndex: number,
  coordinateCoveragePct: number,
]

export interface MapDimensions {
  hotspotGrains: string[]
  boroughs: string[]
  precincts: string[]
  offenseTypes: string[]
  lawCategories: string[]
  severities: string[]
}

export interface MapHotspotSummary {
  rowCount: number
  scoringEndDate: string | null
  snapshotAgeDays: number | null
  currentMaxAgeDays: 1
  recentWindowDays: number | null
  baselineWindowDays: number | null
  gridSizeDegrees: number | null
  counts: Record<string, unknown>
}

export interface MapHotspotContract {
  status: MapHotspotStatus
  sourceFile: string
  reason?: string
  rowColumns: string[]
  rows: MapHotspotRow[]
  summary: MapHotspotSummary
}

export interface MapApplicationContract {
  name: string
  phase: string
  view: string
}

export interface MapDataRangeContract {
  safeEventStartDate: string
  safeEventEndDate: string
  aggregateSafeEventCount: number
  sourceEventCount: number
  excludedEventCount: number
  unit: string
}

export interface MapFilterIndexContract {
  precinctsByBorough: {
    rowColumns: string[]
    rows: Array<[boroughIndex: number, precinctIndexes: number[]]>
    semantics: string
  }
}

export interface MapEthicsContract {
  aggregateTrendIntelligenceOnly: boolean
  demographicAttributesIncluded: boolean
  enforcementRecommendations: boolean
  eventRecordsIncluded: boolean
  patrolRecommendations: boolean
  personLevelScoring: boolean
}

export interface MapDataContract {
  schemaVersion: string
  generatedAtUtc: string
  application: MapApplicationContract
  dataRange: MapDataRangeContract
  dimensions: MapDimensions
  filterIndex: MapFilterIndexContract
  hotspots: MapHotspotContract
  methodology: Record<string, unknown>
  provenance: Record<string, unknown>
  filterSemantics: Record<string, unknown>
  coordinateSemantics: Record<string, unknown>
  dateSemantics: Record<string, unknown>
  grainSemantics: Record<string, unknown>
  ethics: MapEthicsContract
  limitations: string[]
}

export type MapLoader = () => Promise<MapDataContract>

export type HotspotLayer = 'all' | 'grid' | 'precinct'

export interface MapHotspot {
  id: string
  rank: number
  grain: string
  borough: string
  precinct: string | null
  offenseType: string
  lawCategory: string
  latitude: number
  longitude: number
  locationLabel: string
  recentCount: number
  expectedRecentCount: number | null
  liftPct: number | null
  score: number
  severity: string
  coordinateCoveragePct: number
}

export interface MapFilterResult {
  rows: MapHotspot[]
  scopeRows: MapHotspot[]
  layerCounts: Record<HotspotLayer, number>
  gridExcludedByPrecinct: boolean
}

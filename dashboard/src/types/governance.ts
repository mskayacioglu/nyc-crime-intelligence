import type { AnomaliesContract } from './anomalies'
import type { ForecastMapContract } from './forecastMap'
import type { MapDataContract } from './map'
import type {
  AggregateSafeUnknownCounts,
  OverviewMetadata,
  SourceIssueCounts,
} from './overview'
import type { PrecinctSpatialReferenceContract } from './precinctSpatialReference'

export type GovernanceFailureStatus = 'invalid' | 'incompatible'

export type GovernanceReadinessStatus =
  | 'available'
  | 'partial'
  | 'empty'
  | 'missing'
  | 'invalid'
  | 'stale'
  | 'incompatible'
  | 'unavailable'

export interface GovernanceOverviewProjection {
  metadata: OverviewMetadata
  contractGeneratedAtUtc: string
  eventStartDate: string
  eventEndDate: string
  firstWeek: string
  lastWeek: string
  latestCompleteWeek: string
  latestWeekIsPartial: boolean
  sourceRowCount: number
  aggregateSafeEventCount: number
  excludedEventCount: number
  sourceIssueCounts: SourceIssueCounts
  aggregateSafeUnknownCounts: AggregateSafeUnknownCounts
  anomalies: AnomaliesContract
  overviewForecastStatus: GovernanceReadinessStatus
  overviewHotspotStatus: GovernanceReadinessStatus
  modelManifest: {
    status: GovernanceReadinessStatus
    artifactType: string | null
    artifactVersion: number | null
    modelName: string | null
    modelVersion: number | null
    forecastWeek: string | null
    generatedAtUtc: string | null
  }
}

export interface GovernanceArtifactProjection {
  map: MapDataContract
  forecast: ForecastMapContract
  spatial: PrecinctSpatialReferenceContract
  checkedAtUtc: string
}

export interface GovernanceSourceFailure {
  status: GovernanceReadinessStatus
  reason: string
}

export type GovernanceSourceResult<T> =
  | { status: 'ready'; value: T }
  | { status: 'error'; failure: GovernanceSourceFailure }

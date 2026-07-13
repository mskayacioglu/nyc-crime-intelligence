import type { PrecinctForecast, PredictiveMode } from '../types/forecastMap'
import type {
  PrecinctSpatialFeature,
  PrecinctSpatialReferenceContract,
} from '../types/precinctSpatialReference'

const predictiveValueFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 6,
})

export const PREDICTIVE_SCALE_PERCENTILE = 0.95
export const EXPECTED_CHANGE_TOLERANCE = 0.000001

export type ForecastVolumeLevel =
  | 'zero'
  | 'positive-1'
  | 'positive-2'
  | 'positive-3'
  | 'positive-4'
export type ExpectedChangeDirection =
  | 'above'
  | 'below'
  | 'approximately equal'
  | 'unavailable'
export type ExpectedChangeIntensity = 0 | 1 | 2 | 3
export type BaselineCoverage = 'complete' | 'partial' | 'missing' | 'unavailable'

export interface ForecastVolumeScale {
  percentile: typeof PREDICTIVE_SCALE_PERCENTILE
  maximum: number
  /** Exact upper bounds for the four positive-volume color steps. Zero is separate. */
  thresholds: readonly [number, number, number, number]
}

export interface ExpectedChangeScale {
  percentile: typeof PREDICTIVE_SCALE_PERCENTILE
  tolerance: typeof EXPECTED_CHANGE_TOLERANCE
  magnitudeMaximum: number
  /** Exact upper magnitude bounds for the three non-neutral color steps. */
  magnitudeThresholds: readonly [number, number, number]
  domain: readonly [number, number]
}

export interface MatchedPrecinctForecast {
  row: PrecinctForecast
  feature: PrecinctSpatialFeature
}

export function formatPredictiveValue(value: number): string {
  if (!Number.isFinite(value)) {
    throw new RangeError('Predictive display values must be finite.')
  }
  const normalized = Math.abs(value) < 0.0000005 ? 0 : value
  return predictiveValueFormatter.format(normalized)
}

function requireFiniteNonnegative(value: number, label: string): number {
  if (!Number.isFinite(value) || value < 0) {
    throw new RangeError(`${label} must be a finite nonnegative number.`)
  }
  return value
}

function percentile(values: readonly number[], quantile: number): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((left, right) => left - right)
  const position = (sorted.length - 1) * quantile
  const lowerIndex = Math.floor(position)
  const upperIndex = Math.ceil(position)
  const lower = sorted[lowerIndex]
  const upper = sorted[upperIndex]
  if (lowerIndex === upperIndex) return lower
  return lower + (upper - lower) * (position - lowerIndex)
}

/**
 * Uses the linearly interpolated 95th percentile of positive filtered values.
 * Values above the cap remain exact in text and share the darkest map step.
 */
export function createForecastVolumeScale(
  rows: readonly PrecinctForecast[],
): ForecastVolumeScale {
  const positiveValues = rows
    .map((row) => requireFiniteNonnegative(row.predictedCount, 'predictedCount'))
    .filter((value) => value > 0)
  const maximum = percentile(positiveValues, PREDICTIVE_SCALE_PERCENTILE)
  return {
    percentile: PREDICTIVE_SCALE_PERCENTILE,
    maximum,
    thresholds: [maximum / 4, maximum / 2, (maximum * 3) / 4, maximum],
  }
}

export function forecastVolumeLevel(
  value: number,
  scale: ForecastVolumeScale,
): ForecastVolumeLevel {
  requireFiniteNonnegative(value, 'predictedCount')
  if (value === 0) return 'zero'
  if (scale.maximum <= 0 || value <= scale.thresholds[0]) return 'positive-1'
  if (value <= scale.thresholds[1]) return 'positive-2'
  if (value <= scale.thresholds[2]) return 'positive-3'
  return 'positive-4'
}

export function baselineCoverage(row: PrecinctForecast): BaselineCoverage {
  if (
    !Number.isInteger(row.totalRows) ||
    !Number.isInteger(row.baselineRows) ||
    row.totalRows < 0 ||
    row.baselineRows < 0 ||
    row.baselineRows > row.totalRows
  ) {
    throw new RangeError('Baseline row counts are invalid.')
  }
  if (row.totalRows === 0) return 'unavailable'
  if (row.baselineRows === 0) return 'missing'
  if (row.baselineRows < row.totalRows) return 'partial'
  return row.expectedChangeCount === null ? 'unavailable' : 'complete'
}

export function expectedChangeDirection(
  row: PrecinctForecast,
): ExpectedChangeDirection {
  if (baselineCoverage(row) !== 'complete' || row.expectedChangeCount === null) {
    return 'unavailable'
  }
  if (!Number.isFinite(row.expectedChangeCount)) {
    throw new RangeError('expectedChangeCount must be finite when available.')
  }
  if (Math.abs(row.expectedChangeCount) <= EXPECTED_CHANGE_TOLERANCE) {
    return 'approximately equal'
  }
  return row.expectedChangeCount > 0 ? 'above' : 'below'
}

/**
 * Uses a symmetric domain around zero, capped at the linearly interpolated
 * 95th percentile of complete, non-neutral absolute changes.
 */
export function createExpectedChangeScale(
  rows: readonly PrecinctForecast[],
): ExpectedChangeScale {
  const magnitudes = rows.flatMap((row) => {
    if (baselineCoverage(row) !== 'complete' || row.expectedChangeCount === null) {
      return []
    }
    if (!Number.isFinite(row.expectedChangeCount)) {
      throw new RangeError('expectedChangeCount must be finite when available.')
    }
    const magnitude = Math.abs(row.expectedChangeCount)
    return magnitude > EXPECTED_CHANGE_TOLERANCE ? [magnitude] : []
  })
  const magnitudeMaximum = percentile(magnitudes, PREDICTIVE_SCALE_PERCENTILE)
  return {
    percentile: PREDICTIVE_SCALE_PERCENTILE,
    tolerance: EXPECTED_CHANGE_TOLERANCE,
    magnitudeMaximum,
    magnitudeThresholds: [
      magnitudeMaximum / 3,
      (magnitudeMaximum * 2) / 3,
      magnitudeMaximum,
    ],
    domain: [-magnitudeMaximum, magnitudeMaximum],
  }
}

export function expectedChangeIntensity(
  row: PrecinctForecast,
  scale: ExpectedChangeScale,
): ExpectedChangeIntensity {
  const direction = expectedChangeDirection(row)
  if (direction === 'unavailable' || direction === 'approximately equal') return 0
  const magnitude = Math.abs(row.expectedChangeCount as number)
  if (scale.magnitudeMaximum <= 0 || magnitude <= scale.magnitudeThresholds[0]) {
    return 1
  }
  if (magnitude <= scale.magnitudeThresholds[1]) return 2
  return 3
}

export function matchPrecinctForecastFeatures(
  spatial: PrecinctSpatialReferenceContract,
  rows: readonly PrecinctForecast[],
): MatchedPrecinctForecast[] {
  const featuresByKey = new Map(
    spatial.features.map((feature) => [feature.properties.locationKey, feature]),
  )
  return rows.flatMap((row) => {
    const feature = featuresByKey.get(row.id)
    return feature ? [{ row, feature }] : []
  })
}

function signed(value: number): string {
  return `${value > 0 ? '+' : ''}${formatPredictiveValue(value)}`
}

export function precinctMapTooltipText(
  row: PrecinctForecast,
  mode: PredictiveMode,
): string {
  const identity = `${row.borough} · Precinct ${row.precinct}`
  if (mode === 'forecast') {
    const zero = row.predictedCount === 0 ? ' · valid zero forecast' : ''
    return `${identity} · ${formatPredictiveValue(row.predictedCount)} expected aggregate reported events${zero}`
  }

  const coverage = baselineCoverage(row)
  if (coverage === 'partial') {
    return `${identity} · expected change unavailable · partial baseline coverage (${row.baselineRows} of ${row.totalRows} contributing rows)`
  }
  if (coverage === 'missing') {
    return `${identity} · expected change unavailable · baseline missing (0 of ${row.totalRows} contributing rows)`
  }
  if (coverage === 'unavailable' || row.expectedChangeCount === null) {
    return `${identity} · expected change unavailable · baseline coverage unavailable`
  }

  return `${identity} · ${expectedChangeDirection(row)} historical baseline · ${signed(row.expectedChangeCount)} expected aggregate reported events`
}

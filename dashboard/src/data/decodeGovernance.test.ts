import { describe, expect, it } from 'vitest'
import forecastArtifact from '../../public/data/forecast-map.json'
import mapArtifact from '../../public/data/map.json'
import overviewArtifact from '../../public/data/overview.json'
import spatialArtifact from '../../public/data/precinct-spatial-reference.json'
import { PrecinctSpatialReferenceError } from './loadPrecinctSpatialReference'
import {
  decodeGovernanceForecast,
  decodeGovernanceMap,
  decodeGovernanceOverview,
  decodeGovernanceSpatial,
  governanceFailure,
  GovernanceContractError,
  INDEPENDENT_TRAINING_REASON,
} from './decodeGovernance'

type UnknownObject = Record<string, unknown>

const overviewCopy = (): UnknownObject =>
  structuredClone(overviewArtifact) as unknown as UnknownObject
const mapCopy = (): UnknownObject =>
  structuredClone(mapArtifact) as unknown as UnknownObject
const forecastCopy = (): UnknownObject =>
  structuredClone(forecastArtifact) as unknown as UnknownObject
const spatialCopy = (): UnknownObject =>
  structuredClone(spatialArtifact) as unknown as UnknownObject

function object(value: unknown): UnknownObject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Test fixture section is not an object.')
  }
  return value as UnknownObject
}

function expectGovernanceError(
  action: () => unknown,
  status: 'invalid' | 'incompatible',
): void {
  try {
    action()
    throw new Error('Expected Governance validation to fail.')
  } catch (error) {
    expect(error).toBeInstanceOf(GovernanceContractError)
    expect(error).toMatchObject({ status })
  }
}

describe('Governance strict aggregate projection', () => {
  it('reconciles the real published artifacts and preserves each lifecycle timestamp', () => {
    const overview = decodeGovernanceOverview(overviewCopy())
    const map = decodeGovernanceMap(overview, mapCopy())
    const forecast = decodeGovernanceForecast(overview, forecastCopy())
    const spatial = decodeGovernanceSpatial(
      forecast,
      spatialCopy(),
      new Date('2026-07-17T12:00:00Z'),
    )

    expect(overview).toMatchObject({
      eventStartDate: '2006-01-01',
      eventEndDate: '2025-12-31',
      firstWeek: '2005-12-26',
      lastWeek: '2025-12-29',
      latestCompleteWeek: '2025-12-22',
      latestWeekIsPartial: true,
      sourceRowCount: 10_071_507,
      aggregateSafeEventCount: 10_049_687,
      excludedEventCount: 21_820,
    })
    expect(overview.sourceIssueCounts).toMatchObject({
      missingInvalidComplaintStartDate: 655,
      missingBorough: 10_078,
      missingPrecinct: 771,
      missingOffense: 18_907,
      missingCoordinates: 479,
      zeroCoordinates: 25,
      coordinatesOutsideBroadNycBounds: 33,
      rowsWithAnyIssue: 52_050,
      rowsWithMultipleIssues: 605,
      maximumIssuesPerRow: 3,
    })
    expect(overview.aggregateSafeUnknownCounts).toMatchObject({
      borough: 10_065,
      precinct: 713,
      offense: 18_847,
      lawCategory: 0,
    })
    expect(map.hotspots.rows).toHaveLength(396)
    expect(forecast.model).toMatchObject({
      status: 'available',
      artifactType: 'weekly_forecast_ml_model',
      artifactVersion: 1,
      artifactGeneratedAtUtc: '2026-07-05T12:40:05.068774+00:00',
      name: 'duckdb_lag_ensemble_regressor',
      version: 1,
      trainingStartWeek: '2005-12-26',
      trainingThroughWeek: '2025-12-29',
      forecastWeek: '2026-01-05',
      independentTrainingTime: {
        status: 'unavailable',
        timestamp: null,
        reason: INDEPENDENT_TRAINING_REASON,
      },
      pointEstimatesOnly: true,
      predictionIntervalsAvailable: false,
    })
    expect(forecast.model.historicalError).toMatchObject({
      status: 'available',
      mae: 0.4894,
      rmse: 1.3943,
      weightedMae: 3.6555,
      predictionCoveragePct: 100,
      backtestRowCount: 437_144,
      backtestEndWeek: '2025-12-22',
    })
    expect(spatial.coverage).toMatchObject({ complete: true, featureCount: 78 })
  })

  it.each([
    ['unsupported identity', (value: UnknownObject) => {
      object(value.application).view = 'Governance'
    }, 'incompatible'],
    ['non-UTC generated timestamp', (value: UnknownObject) => {
      value.generatedAtUtc = '2025-12-31T00:00:00'
    }, 'incompatible'],
    ['non-midnight generated timestamp', (value: UnknownObject) => {
      value.generatedAtUtc = '2025-12-31T12:00:00Z'
    }, 'incompatible'],
    ['malformed event date', (value: UnknownObject) => {
      object(value.dataRange).safeEventStartDate = '2006-13-01'
    }, 'invalid'],
    ['non-Monday weekly boundary', (value: UnknownObject) => {
      object(value.dataRange).firstWeek = '2005-12-27'
    }, 'invalid'],
    ['reversed event range', (value: UnknownObject) => {
      object(value.dataRange).safeEventStartDate = '2026-01-01'
    }, 'invalid'],
    ['contradictory partial-week range', (value: UnknownObject) => {
      object(value.dataRange).latestCompleteWeek = '2025-12-29'
    }, 'incompatible'],
    ['false partial-week declaration', (value: UnknownObject) => {
      Object.assign(object(value.dataRange), {
        latestWeekIsPartial: false,
        latestCompleteWeek: '2025-12-29',
        defaultEndWeek: '2025-12-29',
      })
    }, 'incompatible'],
    ['unsupported model version', (value: UnknownObject) => {
      object(object(value.versions).mlManifest).modelVersion = 2
    }, 'incompatible'],
    ['negative issue count', (value: UnknownObject) => {
      object(object(value.dataQuality).sourceIssueCounts).missingOffense = -1
    }, 'invalid'],
    ['non-finite issue count', (value: UnknownObject) => {
      object(object(value.dataQuality).sourceIssueCounts).missingOffense = Number.NaN
    }, 'invalid'],
    ['contradictory population total', (value: UnknownObject) => {
      object(value.dataQuality).excludedEventCount = 21_821
    }, 'invalid'],
    ['unsafe overlap semantics', (value: UnknownObject) => {
      object(object(value.dataQuality).sourceIssueCounts).categoriesOverlap = false
    }, 'invalid'],
    ['contradictory maximum issue overlap', (value: UnknownObject) => {
      object(object(value.dataQuality).sourceIssueCounts).maximumIssuesPerRow = 1
    }, 'invalid'],
    ['unsafe retained-UNKNOWN semantics', (value: UnknownObject) => {
      object(object(value.dataQuality).aggregateSafeUnknownCounts).valuesRetained = false
    }, 'incompatible'],
    ['extra quality field', (value: UnknownObject) => {
      object(object(value.dataQuality).sourceIssueCounts).unreviewed = 0
    }, 'incompatible'],
    ['unsafe responsible-use flag', (value: UnknownObject) => {
      object(value.ethics).personLevelScoring = true
    }, 'incompatible'],
    ['absolute source path', (value: UnknownObject) => {
      object(object(value.versions).mlManifest).sourceFile =
        '/Users/example/private/model_manifest.json'
    }, 'invalid'],
    ['available signal with a reason', (value: UnknownObject) => {
      object(object(value.signals).hotspots).reason = 'Contradictory reason.'
    }, 'invalid'],
    ['available manifest with a reason', (value: UnknownObject) => {
      object(object(value.versions).mlManifest).reason = 'Contradictory reason.'
    }, 'incompatible'],
  ] as const)('rejects %s without projecting misleading values', (_name, mutate, status) => {
    const value = overviewCopy()
    mutate(value)
    expectGovernanceError(
      () => decodeGovernanceOverview(value),
      status as 'invalid' | 'incompatible',
    )
  })

  it('preserves valid zero counts while keeping UNKNOWN distinct from exclusions', () => {
    const result = decodeGovernanceOverview(overviewCopy())

    expect(result.sourceIssueCounts.futureComplaintStartDate).toBe(0)
    expect(result.sourceIssueCounts.invalidLawCategory).toBe(0)
    expect(result.aggregateSafeUnknownCounts.lawCategory).toBe(0)
    expect(result.aggregateSafeUnknownCounts.offense).toBe(18_847)
    expect(result.aggregateSafeUnknownCounts.offense).not.toBe(
      result.excludedEventCount,
    )
  })

  it('rejects map coverage that disagrees with the Overview contract', () => {
    const overview = decodeGovernanceOverview(overviewCopy())
    const map = mapCopy()
    object(map.dataRange).aggregateSafeEventCount = 10_049_686
    object(map.dataRange).sourceEventCount = 10_071_506

    expectGovernanceError(
      () => decodeGovernanceMap(overview, map),
      'incompatible',
    )
  })

  it('rejects Map hotspot readiness that disagrees with Overview', () => {
    const overview = decodeGovernanceOverview(overviewCopy())
    const map = mapCopy()
    const hotspots = object(map.hotspots)
    hotspots.status = 'stale'
    hotspots.reason = 'The hotspot snapshot is stale.'
    hotspots.rows = []
    Object.assign(object(hotspots.summary), {
      rowCount: 0,
      scoringEndDate: null,
      snapshotAgeDays: null,
      recentWindowDays: null,
      baselineWindowDays: null,
      gridSizeDegrees: null,
      counts: { byGrain: [0, 0], bySeverity: [0, 0, 0, 0] },
    })

    expectGovernanceError(() => decodeGovernanceMap(overview, map), 'incompatible')
  })

  it.each([
    ['artifact timestamp', (value: UnknownObject) => {
      object(value.model).artifactGeneratedAtUtc = '2026-07-05T12:41:05+00:00'
    }],
    ['training-through date', (value: UnknownObject) => {
      object(value.model).trainingThroughWeek = '2025-12-22'
    }],
    ['forecast horizon', (value: UnknownObject) => {
      object(value.model).forecastWeek = '2026-01-12'
    }],
    ['model identity', (value: UnknownObject) => {
      object(value.model).name = 'unreviewed_model'
    }],
    ['model version', (value: UnknownObject) => {
      object(value.model).version = 2
    }],
    ['independent training timestamp', (value: UnknownObject) => {
      object(value.model).independentTrainingTime = {
        status: 'available',
        timestamp: '2026-07-05T12:40:05+00:00',
        reason: 'Inferred from artifact generation.',
      }
    }],
    ['fixed-horizon wording', (value: UnknownObject) => {
      object(value.forecastSemantics).observationHorizon =
        'This is a live forecast relative to the viewer clock.'
    }],
  ])('rejects incompatible Forecast %s lifecycle fields', (_name, mutate) => {
    const overview = decodeGovernanceOverview(overviewCopy())
    const value = forecastCopy()
    mutate(value)

    expect(() => decodeGovernanceForecast(overview, value)).toThrow()
  })

  it.each([
    ['negative validation metric', -0.1],
    ['non-finite validation metric', Number.POSITIVE_INFINITY],
  ])('rejects a %s instead of coercing it to zero', (_name, metric) => {
    const overview = decodeGovernanceOverview(overviewCopy())
    const value = forecastCopy()
    object(object(value.model).historicalError).mae = metric

    expect(() => decodeGovernanceForecast(overview, value)).toThrow()
  })

  it('preserves valid model lifecycle data when optional historical metrics are invalid', () => {
    const overview = decodeGovernanceOverview(overviewCopy())
    const value = forecastCopy()
    object(value.model).historicalError = {
      status: 'invalid',
      sourceFile: 'ml_metrics.json',
      reason: 'Historical metrics failed their strict alignment check.',
    }

    const forecast = decodeGovernanceForecast(overview, value)
    expect(forecast.model.status).toBe('available')
    expect(forecast.model.artifactGeneratedAtUtc).toBe(
      '2026-07-05T12:40:05.068774+00:00',
    )
    expect(forecast.model.historicalError.status).toBe('invalid')
  })

  it('applies only the documented spatial TTL and rejects an invalid viewer clock', () => {
    const forecast = decodeGovernanceForecast(
      decodeGovernanceOverview(overviewCopy()),
      forecastCopy(),
    )

    expect(() =>
      decodeGovernanceSpatial(
        forecast,
        spatialCopy(),
        new Date('2026-09-23T19:46:58.001Z'),
      ),
    ).toThrow(PrecinctSpatialReferenceError)
    expectGovernanceError(
      () => decodeGovernanceSpatial(forecast, spatialCopy(), new Date('invalid')),
      'invalid',
    )
  })
})

describe('Governance failure sanitization', () => {
  it.each([
    ['missing-artifact', 'missing'],
    ['network', 'unavailable'],
    ['stale', 'stale'],
    ['unsupported-version', 'incompatible'],
    ['invalid-contract', 'invalid'],
  ] as const)('maps spatial %s to the textual %s status', (code, status) => {
    const failure = governanceFailure(
      new PrecinctSpatialReferenceError(
        code,
        '/Users/example/private/precinct-spatial-reference.json failed',
      ),
      'spatial',
    )

    expect(failure).toMatchObject({ status })
    expect(failure.reason).not.toMatch(/Users|private|precinct-spatial-reference\.json/i)
    expect(failure.reason).toMatch(/no unavailable values are converted to zero/i)
  })

  it('never leaks arbitrary network or local-path details', () => {
    const failure = governanceFailure(
      new Error('/Users/example/private/source.json returned token=secret'),
      'forecast',
    )

    expect(failure).toEqual({
      status: 'unavailable',
      reason: 'The forecast contract could not be loaded or validated.',
    })
  })
})

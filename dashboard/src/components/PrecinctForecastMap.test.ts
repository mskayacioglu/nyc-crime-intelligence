import { describe, expect, it } from 'vitest'
import type { PrecinctForecast } from '../types/forecastMap'
import type { PrecinctSpatialReferenceContract } from '../types/precinctSpatialReference'
import {
  baselineCoverage,
  createExpectedChangeScale,
  createForecastVolumeScale,
  expectedChangeDirection,
  expectedChangeIntensity,
  formatPredictiveValue,
  forecastVolumeLevel,
  matchPrecinctForecastFeatures,
  precinctMapTooltipText,
} from './precinctForecastScale'

function forecastRow(
  id: string,
  overrides: Partial<PrecinctForecast> = {},
): PrecinctForecast {
  return {
    id,
    borough: 'MANHATTAN',
    precinct: id.split(':')[1] ?? '1',
    forecastWeek: '2026-01-05',
    predictedCount: 10,
    historicalBaseline: 8,
    expectedChangeCount: 2,
    expectedChangePct: 25,
    baselineRows: 4,
    totalRows: 4,
    direction: 'above',
    ...overrides,
  }
}

function spatialContract(...keys: string[]): PrecinctSpatialReferenceContract {
  return {
    type: 'FeatureCollection',
    schemaVersion: '1.0.0',
    generatedAtUtc: '2025-12-31T00:00:00Z',
    application: {
      name: 'NYC Crime Intelligence',
      phase: 'Phase 7C.3',
      view: 'Precinct Spatial Reference',
    },
    provenance: {},
    coordinateReference: {},
    locationKeySemantics: {},
    compatibility: {},
    processing: {},
    coverage: {},
    privacy: {},
    responsibleUse: {},
    limitations: [],
    features: keys.map((locationKey, index) => ({
      type: 'Feature',
      properties: {
        locationKey,
        precinctLabel: locationKey.split(':')[1] ?? String(index + 1),
      },
      geometry: {
        type: 'MultiPolygon',
        coordinates: [
          [
            [
              [-74 + index * 0.01, 40.7],
              [-73.99 + index * 0.01, 40.7],
              [-73.99 + index * 0.01, 40.71],
              [-74 + index * 0.01, 40.7],
            ],
          ],
        ],
      },
    })),
  } as unknown as PrecinctSpatialReferenceContract
}

describe('Forecast precinct volume scale', () => {
  it('caps the sequential domain at a deterministic positive-value p95', () => {
    const rows = Array.from({ length: 20 }, (_, index) =>
      forecastRow(`nypd-precinct:${index + 1}`, {
        predictedCount: index + 1,
      }),
    )
    rows.push(forecastRow('nypd-precinct:99', { predictedCount: 1000 }))

    const scale = createForecastVolumeScale(rows)

    expect(scale.maximum).toBe(20)
    expect(scale.thresholds).toEqual([5, 10, 15, 20])
    expect(forecastVolumeLevel(0, scale)).toBe('zero')
    expect(forecastVolumeLevel(5, scale)).toBe('positive-1')
    expect(forecastVolumeLevel(10, scale)).toBe('positive-2')
    expect(forecastVolumeLevel(15, scale)).toBe('positive-3')
    expect(forecastVolumeLevel(20, scale)).toBe('positive-4')
    expect(forecastVolumeLevel(1000, scale)).toBe('positive-4')
  })

  it('keeps an exact zero explicit and rejects invalid volume', () => {
    const zero = forecastRow('nypd-precinct:1', { predictedCount: 0 })
    const scale = createForecastVolumeScale([zero])

    expect(scale.maximum).toBe(0)
    expect(forecastVolumeLevel(0, scale)).toBe('zero')
    expect(precinctMapTooltipText(zero, 'forecast')).toContain(
      '0.0 expected aggregate reported events · valid zero forecast',
    )
    expect(() =>
      createForecastVolumeScale([
        forecastRow('nypd-precinct:2', { predictedCount: -1 }),
      ]),
    ).toThrow(/finite nonnegative/)
  })

  it('preserves small positive values instead of formatting them as zero', () => {
    const small = forecastRow('nypd-precinct:66', {
      predictedCount: 0.00102,
      historicalBaseline: 0,
      expectedChangeCount: 0.00102,
      expectedChangePct: null,
    })

    expect(formatPredictiveValue(0)).toBe('0.0')
    expect(formatPredictiveValue(0.00102)).toBe('0.00102')
    expect(formatPredictiveValue(0.000001)).toBe('0.000001')
    expect(precinctMapTooltipText(small, 'forecast')).toContain(
      '0.00102 expected aggregate reported events',
    )
    expect(precinctMapTooltipText(small, 'forecast')).not.toContain(
      '0.0 expected',
    )
    expect(precinctMapTooltipText(small, 'change')).toContain(
      '+0.00102 expected aggregate reported events',
    )
  })
})

describe('Expected change precinct scale', () => {
  it('uses a symmetric robust magnitude and the six-decimal neutral tolerance', () => {
    const rows = Array.from({ length: 20 }, (_, index) =>
      forecastRow(`nypd-precinct:${index + 1}`, {
        expectedChangeCount: (index % 2 === 0 ? -1 : 1) * (index + 1),
      }),
    )
    rows.push(
      forecastRow('nypd-precinct:99', { expectedChangeCount: 1000 }),
    )
    const scale = createExpectedChangeScale(rows)

    expect(scale.magnitudeMaximum).toBe(20)
    expect(scale.domain).toEqual([-20, 20])
    expect(scale.magnitudeThresholds).toEqual([
      20 / 3,
      40 / 3,
      20,
    ])
    expect(
      expectedChangeDirection(
        forecastRow('nypd-precinct:1', { expectedChangeCount: 0.000001 }),
      ),
    ).toBe('approximately equal')
    expect(
      expectedChangeDirection(
        forecastRow('nypd-precinct:2', { expectedChangeCount: -0.000001 }),
      ),
    ).toBe('approximately equal')
    expect(
      expectedChangeDirection(
        forecastRow('nypd-precinct:3', { expectedChangeCount: 0.000002 }),
      ),
    ).toBe('above')
    expect(
      expectedChangeIntensity(
        forecastRow('nypd-precinct:4', { expectedChangeCount: -20 }),
        scale,
      ),
    ).toBe(3)
  })

  it('distinguishes partial and missing baselines without treating either as zero', () => {
    const partial = forecastRow('nypd-precinct:1', {
      baselineRows: 2,
      totalRows: 4,
      historicalBaseline: null,
      expectedChangeCount: null,
      expectedChangePct: null,
      direction: 'unavailable',
    })
    const missing = forecastRow('nypd-precinct:2', {
      baselineRows: 0,
      totalRows: 4,
      historicalBaseline: null,
      expectedChangeCount: null,
      expectedChangePct: null,
      direction: 'unavailable',
    })

    expect(baselineCoverage(partial)).toBe('partial')
    expect(baselineCoverage(missing)).toBe('missing')
    expect(expectedChangeDirection(partial)).toBe('unavailable')
    expect(expectedChangeDirection(missing)).toBe('unavailable')
    expect(createExpectedChangeScale([partial, missing]).domain).toEqual([-0, 0])
    expect(precinctMapTooltipText(partial, 'change')).toContain(
      'partial baseline coverage (2 of 4 contributing rows)',
    )
    expect(precinctMapTooltipText(missing, 'change')).toContain(
      'baseline missing (0 of 4 contributing rows)',
    )
    expect(precinctMapTooltipText(partial, 'change')).not.toContain('+0.0')
    expect(precinctMapTooltipText(missing, 'change')).not.toContain('+0.0')
  })
})

describe('Forecast-to-spatial matching', () => {
  it('keeps filtered row order and renders only exact matching location keys', () => {
    const rows = [
      forecastRow('nypd-precinct:2'),
      forecastRow('nypd-precinct:1'),
      forecastRow('nypd-precinct:999'),
    ]
    const matched = matchPrecinctForecastFeatures(
      spatialContract('nypd-precinct:1', 'nypd-precinct:2'),
      rows,
    )

    expect(matched.map(({ row }) => row.id)).toEqual([
      'nypd-precinct:2',
      'nypd-precinct:1',
    ])
    expect(matched.map(({ feature }) => feature.properties.locationKey)).toEqual([
      'nypd-precinct:2',
      'nypd-precinct:1',
    ])
  })
})

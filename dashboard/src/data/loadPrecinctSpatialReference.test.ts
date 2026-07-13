import { afterEach, describe, expect, it, vi } from 'vitest'
import forecastArtifact from '../../public/data/forecast-map.json'
import spatialArtifact from '../../public/data/precinct-spatial-reference.json'
import type { ForecastMapContract } from '../types/forecastMap'
import type { PrecinctSpatialReferenceContract } from '../types/precinctSpatialReference'
import { decodeForecastMap } from './loadForecastMap'
import {
  assertPrecinctSpatialReferenceFresh,
  decodePrecinctSpatialReference,
  loadPrecinctSpatialReference,
  PrecinctSpatialReferenceError,
  reconcilePrecinctSpatialReference,
  type PrecinctSpatialReferenceErrorCode,
} from './loadPrecinctSpatialReference'

type UnknownObject = Record<string, unknown>

const spatialCopy = (): UnknownObject =>
  structuredClone(spatialArtifact) as unknown as UnknownObject

function object(value: unknown): UnknownObject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Test fixture section is not an object.')
  }
  return value as UnknownObject
}

function features(value: UnknownObject): UnknownObject[] {
  return value.features as unknown as UnknownObject[]
}

function properties(feature: UnknownObject): UnknownObject {
  return object(feature.properties)
}

function geometry(feature: UnknownObject): UnknownObject {
  return object(feature.geometry)
}

function firstRing(value: UnknownObject): number[][] {
  const coordinates = geometry(features(value)[0]).coordinates as number[][][][]
  return coordinates[0][0]
}

function expectCode(
  action: () => unknown,
  code: PrecinctSpatialReferenceErrorCode,
): void {
  try {
    action()
    throw new Error('Expected the spatial-reference operation to fail.')
  } catch (error) {
    expect(error).toBeInstanceOf(PrecinctSpatialReferenceError)
    expect(error).toMatchObject({ code })
  }
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('Precinct spatial-reference runtime contract', () => {
  it('loads the real authoritative artifact with exact complete geometry coverage', () => {
    const first = decodePrecinctSpatialReference(spatialCopy())
    const second = decodePrecinctSpatialReference(spatialCopy())

    expect(first).toEqual(second)
    expect(first.features).toHaveLength(78)
    expect(first.coverage).toEqual({
      complete: true,
      duplicateLocationKeyCount: 0,
      expectedFeatureCount: 78,
      featureCount: 78,
      forecastLocationKeyCount: 78,
      missingForecastLocationKeys: [],
      polygonCount: 235,
      positionCount: 98060,
      ringCount: 236,
      unexpectedSpatialLocationKeys: [],
    })
    expect(first.coordinateReference.bounds).toEqual({
      maxLatitude: 40.91553278,
      maxLongitude: -73.70000906,
      minLatitude: 40.49613399,
      minLongitude: -74.25559136,
    })
    expect(first.provenance.retrieval.sha256).toBe(
      '5210830afa9d0875b7a7c769edfc4d2ebe984a9ab1e36f3b7fad8508828172aa',
    )
    expect(first.processing.simplificationApplied).toBe(false)
  })

  it('fetches the fixed path without cache and does not mutate the response', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-12T20:00:00Z'))
    const source = spatialCopy()
    const before = JSON.stringify(source)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => source,
      }),
    )

    const result = await loadPrecinctSpatialReference()

    expect(fetch).toHaveBeenCalledWith('/data/precinct-spatial-reference.json', {
      cache: 'no-cache',
    })
    expect(result.features).toHaveLength(78)
    expect(JSON.stringify(source)).toBe(before)
  })

  it('keeps the quarterly source current only through its explicit refresh window', () => {
    const contract = decodePrecinctSpatialReference(spatialCopy())

    expect(
      assertPrecinctSpatialReferenceFresh(
        contract,
        new Date('2026-09-23T19:46:58Z'),
      ),
    ).toBe(contract)
    expectCode(
      () =>
        assertPrecinctSpatialReferenceFresh(
          contract,
          new Date('2026-09-23T19:46:58.001Z'),
        ),
      'stale',
    )
  })

  it('distinguishes missing, network, and malformed-JSON failures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 404 }),
    )
    await expect(loadPrecinctSpatialReference()).rejects.toMatchObject({
      code: 'missing-artifact',
    })

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    await expect(loadPrecinctSpatialReference()).rejects.toMatchObject({
      code: 'network',
    })

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError('bad JSON')
        },
      }),
    )
    await expect(loadPrecinctSpatialReference()).rejects.toMatchObject({
      code: 'malformed-json',
    })
  })

  it('rejects unsupported versions, identities, and extra unsafe fields', () => {
    const unsupported = spatialCopy()
    unsupported.schemaVersion = '2.0.0'
    expectCode(
      () => decodePrecinctSpatialReference(unsupported),
      'unsupported-version',
    )

    const identity = spatialCopy()
    object(identity.application).phase = 'Phase 7C.2'
    expectCode(
      () => decodePrecinctSpatialReference(identity),
      'incompatible-identity',
    )

    const unsafe = spatialCopy()
    properties(features(unsafe)[0]).complaintId = 'private'
    expectCode(() => decodePrecinctSpatialReference(unsafe), 'invalid-contract')
  })

  it('rejects malformed, non-finite, imprecise, out-of-bounds, and open geometry', () => {
    const wrongType = spatialCopy()
    geometry(features(wrongType)[0]).type = 'Polygon'
    expectCode(() => decodePrecinctSpatialReference(wrongType), 'invalid-geometry')

    const nonFinite = spatialCopy()
    firstRing(nonFinite)[0][0] = Number.NaN
    expectCode(() => decodePrecinctSpatialReference(nonFinite), 'invalid-geometry')

    const imprecise = spatialCopy()
    firstRing(imprecise)[0][0] += 0.000000001
    expectCode(() => decodePrecinctSpatialReference(imprecise), 'invalid-geometry')

    const outsideNyc = spatialCopy()
    firstRing(outsideNyc)[0][0] = 40.7
    expectCode(() => decodePrecinctSpatialReference(outsideNyc), 'invalid-geometry')

    const open = spatialCopy()
    const ring = firstRing(open)
    ring[ring.length - 1] = [ring[0][0] + 0.00000001, ring[0][1]]
    expectCode(() => decodePrecinctSpatialReference(open), 'invalid-geometry')

    const degenerate = spatialCopy()
    const degenerateRing = firstRing(degenerate)
    const first = [...degenerateRing[0]]
    const second = [...degenerateRing[1]]
    degenerateRing.splice(0, degenerateRing.length, first, second, second, first)
    expectCode(() => decodePrecinctSpatialReference(degenerate), 'invalid-geometry')

    const zeroArea = spatialCopy()
    const zeroAreaRing = firstRing(zeroArea)
    zeroAreaRing.splice(
      0,
      zeroAreaRing.length,
      [-74, 40.7],
      [-73.99, 40.71],
      [-73.98, 40.72],
      [-74, 40.7],
    )
    expectCode(() => decodePrecinctSpatialReference(zeroArea), 'invalid-geometry')
  })

  it('rejects duplicate identities, unstable order, and incomplete feature coverage', () => {
    const duplicate = spatialCopy()
    features(duplicate)[1] = structuredClone(features(duplicate)[0])
    expectCode(
      () => decodePrecinctSpatialReference(duplicate),
      'duplicate-location-key',
    )

    const unordered = spatialCopy()
    ;[features(unordered)[0], features(unordered)[1]] = [
      features(unordered)[1],
      features(unordered)[0],
    ]
    expectCode(
      () => decodePrecinctSpatialReference(unordered),
      'unstable-feature-order',
    )

    const incomplete = spatialCopy()
    features(incomplete).pop()
    expectCode(
      () => decodePrecinctSpatialReference(incomplete),
      'incomplete-coverage',
    )
  })

  it('rejects changed geometry counts and declared coordinate bounds', () => {
    const counts = spatialCopy()
    object(counts.coverage).polygonCount = 236
    expectCode(() => decodePrecinctSpatialReference(counts), 'invalid-contract')

    const bounds = spatialCopy()
    object(object(bounds.coordinateReference).bounds).minLongitude = -74.25559135
    expectCode(
      () => decodePrecinctSpatialReference(bounds),
      'invalid-coordinate-reference',
    )
  })

  it('rejects provenance, public-use, processing, privacy, and responsible-use drift', () => {
    const checksum = spatialCopy()
    object(object(checksum.provenance).retrieval).sha256 = '0'.repeat(64)
    expectCode(
      () => decodePrecinctSpatialReference(checksum),
      'invalid-provenance',
    )

    const publicUse = spatialCopy()
    object(object(publicUse.provenance).publicUse).namedLicense = 'MIT'
    expectCode(
      () => decodePrecinctSpatialReference(publicUse),
      'invalid-provenance',
    )

    const processing = spatialCopy()
    object(processing.processing).simplificationApplied = true
    expectCode(() => decodePrecinctSpatialReference(processing), 'invalid-contract')

    const privacy = spatialCopy()
    object(privacy.privacy).eventLevelCoordinatesIncluded = true
    expectCode(() => decodePrecinctSpatialReference(privacy), 'invalid-contract')

    const responsibleUse = spatialCopy()
    object(responsibleUse.responsibleUse).patrolRecommendations = true
    expectCode(
      () => decodePrecinctSpatialReference(responsibleUse),
      'invalid-contract',
    )
  })
})

describe('Forecast and spatial-reference reconciliation', () => {
  const forecast = (): ForecastMapContract =>
    decodeForecastMap(structuredClone(forecastArtifact))
  const spatial = (): PrecinctSpatialReferenceContract =>
    decodePrecinctSpatialReference(spatialCopy())

  it('reconciles the real artifacts to the same exact 78-key universe', () => {
    const spatialContract = spatial()
    expect(
      reconcilePrecinctSpatialReference(spatialContract, forecast()),
    ).toBe(spatialContract)
  })

  it('reports incomplete and mismatched spatial key sets separately', () => {
    const incomplete = structuredClone(spatial())
    incomplete.features.pop()
    expectCode(
      () => reconcilePrecinctSpatialReference(incomplete, forecast()),
      'incomplete-coverage',
    )

    const mismatch = structuredClone(spatial())
    const finalFeature = mismatch.features[mismatch.features.length - 1]
    finalFeature.properties.precinctLabel = '999'
    finalFeature.properties.locationKey = 'nypd-precinct:999'
    expectCode(
      () => reconcilePrecinctSpatialReference(mismatch, forecast()),
      'location-key-mismatch',
    )
  })

  it('rejects unsupported Forecast identity, key scheme, and row coverage', () => {
    const unsupported = structuredClone(forecast()) as unknown as UnknownObject
    unsupported.schemaVersion = '2.0.0'
    expectCode(
      () =>
        reconcilePrecinctSpatialReference(
          spatial(),
          unsupported as unknown as ForecastMapContract,
        ),
      'forecast-incompatible',
    )

    const scheme = structuredClone(forecast())
    scheme.locationKeySemantics.scheme = 'other:<label>'
    expectCode(
      () => reconcilePrecinctSpatialReference(spatial(), scheme),
      'forecast-incompatible',
    )

    const rows = structuredClone(forecast())
    rows.forecast.rows = rows.forecast.rows.filter(
      (row) => row[9] !== 'nypd-precinct:116',
    )
    expectCode(
      () => reconcilePrecinctSpatialReference(spatial(), rows),
      'forecast-incompatible',
    )
  })
})

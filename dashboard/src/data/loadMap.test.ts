import { afterEach, describe, expect, it, vi } from 'vitest'
import generatedMap from '../../public/data/map.json'
import { mapFixture } from '../test/mapFixture'
import type { MapDataContract, MapHotspotRow } from '../types/map'
import { loadMap } from './loadMap'

function respondWith(contract: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(contract), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
}

function cloneFixture(): MapDataContract {
  return structuredClone(mapFixture())
}

afterEach(() => vi.unstubAllGlobals())

describe('Map contract loader', () => {
  it('accepts the generated browser artifact', async () => {
    respondWith(generatedMap)

    const result = await loadMap()

    expect(result.hotspots.status).toBe('available')
    expect(result.hotspots.rows).toHaveLength(396)
    expect(result.hotspots.summary.scoringEndDate).toBe('2025-12-30')
  })

  it('loads the exact compact aggregate contract without transforming values', async () => {
    const contract = cloneFixture()
    respondWith(contract)

    const result = await loadMap()

    expect(fetch).toHaveBeenCalledWith('/data/map.json', { cache: 'no-cache' })
    expect(result).toEqual(contract)
    expect(result.hotspots.rows).toHaveLength(5)
  })

  it('rejects changed row columns and non-finite numeric encodings', async () => {
    const changedColumns = cloneFixture()
    changedColumns.hotspots.rowColumns[0] = 'complaintId'
    respondWith(changedColumns)
    await expect(loadMap()).rejects.toThrow('incomplete or incompatible')

    const invalidNumeric = cloneFixture()
    invalidNumeric.hotspots.rows[0][12] = Number.NaN
    respondWith(invalidNumeric)
    await expect(loadMap()).rejects.toThrow('invalid value')
  })

  it('rejects duplicate ranks or logical hotspot keys', async () => {
    const contract = cloneFixture()
    const duplicate = [...contract.hotspots.rows[0]] as MapHotspotRow
    duplicate[0] = 99
    contract.hotspots.rows.push(duplicate)
    contract.hotspots.summary.rowCount += 1
    respondWith(contract)

    await expect(loadMap()).rejects.toThrow('duplicates a logical key')
  })

  it('rejects available snapshots that are future-dated or beyond the freshness limit', async () => {
    const future = cloneFixture()
    future.hotspots.summary.scoringEndDate = '2025-03-11'
    respondWith(future)
    await expect(loadMap()).rejects.toThrow('invalid scoring date')

    const staleAsAvailable = cloneFixture()
    staleAsAvailable.hotspots.summary.snapshotAgeDays = 2
    respondWith(staleAsAvailable)
    await expect(loadMap()).rejects.toThrow('exceeds the freshness limit')
  })

  it('rejects a declared snapshot age that contradicts the contract dates', async () => {
    const contract = cloneFixture()
    contract.hotspots.summary.scoringEndDate = '2025-03-09'
    contract.hotspots.summary.snapshotAgeDays = 0
    respondWith(contract)

    await expect(loadMap()).rejects.toThrow('age is inconsistent with its dates')
  })

  it('rejects grid and precinct rows that violate grain semantics', async () => {
    const gridWithPrecinct = cloneFixture()
    gridWithPrecinct.hotspots.rows[0][3] = 0
    respondWith(gridWithPrecinct)
    await expect(loadMap()).rejects.toThrow('invalid grain semantics')

    const precinctWithoutPrecinct = cloneFixture()
    precinctWithoutPrecinct.hotspots.rows[1][3] = null
    respondWith(precinctWithoutPrecinct)
    await expect(loadMap()).rejects.toThrow('invalid grain semantics')
  })

  it('requires non-available statuses to carry a reason and zero rows', async () => {
    const rowsOnMissing = cloneFixture()
    rowsOnMissing.hotspots.status = 'missing'
    rowsOnMissing.hotspots.reason = 'Source missing.'
    respondWith(rowsOnMissing)
    await expect(loadMap()).rejects.toThrow('cannot expose rows')

    const missingReason = mapFixture({ status: 'stale' })
    delete missingReason.hotspots.reason
    respondWith(missingReason)
    await expect(loadMap()).rejects.toThrow('requires a reason')
  })

  it('rejects responsible-use flags that would permit unsafe browser data', async () => {
    const contract = cloneFixture()
    contract.ethics.eventRecordsIncluded = true
    respondWith(contract)

    await expect(loadMap()).rejects.toThrow('responsible-use contract is incompatible')
  })
})

import { describe, expect, it } from 'vitest'
import { overviewFixture } from '../test/fixture'
import type { AnomalyRow, OverviewFilters, OverviewMetadata } from '../types/overview'
import { decodeAnomalies } from './decodeAnomalies'
import { filterAnomalies, filterAnomalyRows } from './filterAnomalies'

function validOverview(): OverviewMetadata {
  const metadata = structuredClone(overviewFixture().metadata)
  metadata.signals.anomalies.summary = {
    rowCount: 2,
    highCount: 1,
    criticalCount: 1,
    isEmpty: false,
    scoringEndWeek: '2025-03-03',
  }
  return metadata
}

const allFilters: OverviewFilters = {
  startWeek: '2025-01-06',
  endWeek: '2025-03-03',
  boroughIndex: null,
  precinctIndex: null,
  offenseIndex: null,
  lawIndex: null,
}

describe('anomaly filtering', () => {
  it('applies inclusive dates and all four indexed shared dimensions', () => {
    const contract = decodeAnomalies(validOverview())
    expect(contract.status).toBe('available')
    if (contract.status !== 'available') return

    expect(filterAnomalyRows(contract.rows, allFilters)).toHaveLength(2)
    expect(
      filterAnomalyRows(contract.rows, {
        ...allFilters,
        startWeek: '2025-03-03',
        endWeek: '2025-03-03',
      }).map((row) => row.sourceRank),
    ).toEqual([1])
    expect(
      filterAnomalyRows(contract.rows, { ...allFilters, boroughIndex: 1 }).map(
        (row) => row.sourceRank,
      ),
    ).toEqual([2])
    expect(
      filterAnomalyRows(contract.rows, { ...allFilters, precinctIndex: 0 }).map(
        (row) => row.sourceRank,
      ),
    ).toEqual([1])
    expect(
      filterAnomalyRows(contract.rows, { ...allFilters, offenseIndex: 1 }).map(
        (row) => row.sourceRank,
      ),
    ).toEqual([2])
    expect(
      filterAnomalyRows(contract.rows, { ...allFilters, lawIndex: 0 }).map(
        (row) => row.sourceRank,
      ),
    ).toEqual([1])
  })

  it('preserves deterministic source order under filtering', () => {
    const contract = decodeAnomalies(validOverview())
    expect(contract.status).toBe('available')
    if (contract.status !== 'available') return

    const filtered = filterAnomalies(contract, allFilters)

    expect(filtered.rows.map((row) => row.id)).toEqual(
      contract.rows.map((row) => row.id),
    )
    expect(filtered.sourceRowCount).toBe(2)
    expect(filtered.isFilteredEmpty).toBe(false)
  })

  it('distinguishes a declared empty source from a filtered-empty result', () => {
    const emptyMetadata = validOverview()
    emptyMetadata.signals.anomalies.rows = []
    emptyMetadata.signals.anomalies.summary = {
      rowCount: 0,
      highCount: 0,
      criticalCount: 0,
      isEmpty: true,
      scoringEndWeek: '2025-03-03',
    }
    const empty = decodeAnomalies(emptyMetadata)
    expect(empty.status).toBe('available')
    if (empty.status !== 'available') return
    expect(empty.isEmpty).toBe(true)
    expect(filterAnomalies(empty, allFilters)).toMatchObject({
      rows: [],
      sourceRowCount: 0,
      isFilteredEmpty: false,
    })

    const populated = decodeAnomalies(validOverview())
    expect(populated.status).toBe('available')
    if (populated.status !== 'available') return
    expect(
      filterAnomalies(populated, {
        ...allFilters,
        startWeek: '2000-01-03',
        endWeek: '2000-01-03',
      }),
    ).toMatchObject({
      rows: [],
      sourceRowCount: 2,
      isFilteredEmpty: true,
    })
  })

  it('does not expose rows from an unavailable source', () => {
    const metadata = validOverview()
    metadata.signals.anomalies.status = 'stale'
    metadata.signals.anomalies.reason = 'The source is stale.'
    metadata.signals.anomalies.rows = [
      [...(metadata.signals.anomalies.rows as AnomalyRow[])[0]],
    ]
    const contract = decodeAnomalies(metadata)

    expect(filterAnomalies(contract, allFilters)).toMatchObject({
      rows: [],
      sourceRowCount: 0,
      isFilteredEmpty: false,
    })
  })

  it('honors simultaneous borough and precinct constraints', () => {
    const contract = decodeAnomalies(validOverview())
    expect(contract.status).toBe('available')
    if (contract.status !== 'available') return

    expect(
      filterAnomalies(contract, {
        ...allFilters,
        boroughIndex: 0,
        precinctIndex: 1,
      }),
    ).toMatchObject({ rows: [], isFilteredEmpty: true })
    expect(
      filterAnomalies(contract, {
        ...allFilters,
        boroughIndex: 0,
        precinctIndex: 0,
      }).rows.map((row) => row.sourceRank),
    ).toEqual([1])
  })
})

import { describe, expect, it, vi } from 'vitest'
import artifact from '../../public/data/forecast-map.json'
import { aggregateForecastPrecincts } from './filterForecastMap'
import { decodeForecastMap, loadForecastMap } from './loadForecastMap'
import type { OverviewMetadata } from '../types/overview'

const copy = () => structuredClone(artifact) as unknown

describe('Forecast Map runtime contract', () => {
  it('loads the real generated artifact deterministically with one next-week horizon', () => {
    const first=decodeForecastMap(copy()), second=decodeForecastMap(copy())
    expect(first).toEqual(second)
    expect(first.forecast.rows).toHaveLength(5852)
    expect(first.dimensions.forecastWeeks).toEqual(['2026-01-05'])
    expect(first.locationKeySemantics.spatialReferenceAvailable).toBe(false)
  })

  it('fetches the fixed path without cache and does not mutate the source', async () => {
    const source=copy(), before=JSON.stringify(source)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true,json:async()=>source}))
    await expect(loadForecastMap()).resolves.toBeDefined()
    expect(fetch).toHaveBeenCalledWith('/data/forecast-map.json',{cache:'no-cache'})
    expect(JSON.stringify(source)).toBe(before)
  })

  it.each([
    ['row width', (v: Record<string, unknown>) => { (v.forecast as {rows:unknown[][]}).rows[0].pop() }],
    ['duplicate key', (v: Record<string, unknown>) => { const rows=(v.forecast as {rows:unknown[][]}).rows; rows[1]=[...rows[0]] }],
    ['negative value', (v: Record<string, unknown>) => { (v.forecast as {rows:unknown[][]}).rows[0][5]=-1 }],
    ['unsafe privacy', (v: Record<string, unknown>) => { (v.privacy as Record<string,unknown>).aggregateOnly=false }],
    ['zero baseline percentage', (v: Record<string, unknown>) => { const row=(v.forecast as {rows:unknown[][]}).rows.find(r=>r[6]===0)!; row[8]=0 }],
  ])('rejects malformed %s contracts', (_name, mutate) => {
    const value=copy() as Record<string,unknown>; mutate(value)
    expect(()=>decodeForecastMap(value)).toThrow()
  })

  it('distinguishes a valid zero estimate and preserves partial baseline aggregation', () => {
    const contract=decodeForecastMap(copy())
    const metadata={dimensions:{boroughs:contract.dimensions.boroughs,precincts:contract.dimensions.precincts,offenseTypes:contract.dimensions.offenseTypes,lawCategories:contract.dimensions.lawCategories}} as OverviewMetadata
    const rows=aggregateForecastPrecincts(contract,metadata,{startWeek:'2025-12-22',endWeek:'2025-12-22',boroughIndex:null,precinctIndex:null,offenseIndex:null,lawIndex:null})
    expect(rows).toHaveLength(78)
    expect(rows.reduce((sum,row)=>sum+row.predictedCount,0)).toBeCloseTo(contract.forecast.summary.predictedTotal!,6)
    expect(rows.some(row=>row.baselineRows<row.totalRows)).toBe(true)
    expect(contract.forecast.rows.some(row=>row[5]===0)).toBe(true)
  })
})

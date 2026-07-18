import { describe, expect, it, vi } from 'vitest'
import artifact from '../../public/data/forecast-map.json'
import { aggregateForecastPrecincts } from './filterForecastMap'
import { decodeForecastMap, loadForecastMap } from './loadForecastMap'
import type { OverviewMetadata } from '../types/overview'

const copy = () => structuredClone(artifact) as unknown
const localFixtureRoot = '/' + 'Users/example/private/'

function makeAvailableEmpty(): Record<string, unknown> {
  const value=copy() as Record<string,unknown>
  const range=value.dataRange as Record<string,unknown>
  const dimensions=value.dimensions as Record<string,unknown>
  const filterIndex=(value.filterIndex as {precinctsByBorough:Record<string,unknown>}).precinctsByBorough
  const forecast=value.forecast as Record<string,unknown>
  const summary=forecast.summary as Record<string,unknown>
  const baseline=value.baseline as Record<string,unknown>
  const baselineSummary=baseline.summary as Record<string,unknown>
  const availability=value.availability as Record<string,unknown>
  range.supportedForecastWeeks=[]
  for(const key of ['forecastWeeks','boroughs','precincts','offenseTypes','lawCategories']) dimensions[key]=[]
  filterIndex.rows=[]
  forecast.rows=[]
  forecast.isEmpty=true
  Object.assign(summary,{
    rowCount:0,sourceRowCount:0,sourceSegmentCount:8466,modelSegmentCoveragePct:0,
    withheldRowCount:0,sourcePredictedTotal:null,predictedTotal:null,
    withheldPredictedTotal:null,rowCoveragePct:null,predictedVolumeCoveragePct:null,
    publishedPrecinctCount:0,publishedBoroughCount:0,unknownOffenseRowCount:0,
    countsByBorough:[],zeroPredictionRowCount:0,
    withheldReasonCounts:{boroughMismatch:0,unmappableLocation:0},
  })
  Object.assign(baselineSummary,{
    publishedRowCount:0,baselineAvailableRowCount:0,baselineUnavailableRowCount:0,
    expectedChangeCountAvailableRowCount:0,expectedChangePctAvailableRowCount:0,
    zeroBaselineRowCount:0,
  })
  baseline.valueAvailability='unavailable'
  Object.assign(availability,{
    forecastPointEstimates:'empty',historicalBaseline:'unavailable',
    expectedChangeCount:'unavailable',expectedChangePct:'unavailable',
  })
  return value
}

describe('Forecast Map runtime contract', () => {
  it('loads the real generated artifact deterministically with one next-week horizon', () => {
    const first=decodeForecastMap(copy()), second=decodeForecastMap(copy())
    expect(first).toEqual(second)
    expect(first.forecast.rows).toHaveLength(5852)
    expect(first.dimensions.forecastWeeks).toEqual(['2026-01-05'])
    expect(first.locationKeySemantics.spatialReferenceAvailable).toBe(false)
    expect(first.model.artifactGeneratedAtUtc).toBe('2026-07-05T12:40:05.068774+00:00')
    expect(first.model.independentTrainingTime).toEqual({
      status: 'unavailable',
      timestamp: null,
      reason: 'No independent training-completion timestamp is recorded.',
    })
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
    ['malformed artifact timestamp', (v: Record<string, unknown>) => { (v.model as Record<string,unknown>).artifactGeneratedAtUtc='2026-02-30T12:40:05+00:00' }],
    ['inferred training timestamp', (v: Record<string, unknown>) => { ((v.model as Record<string,unknown>).independentTrainingTime as Record<string,unknown>).timestamp='2026-07-05T12:40:05Z' }],
    ['contradictory training status', (v: Record<string, unknown>) => { ((v.model as Record<string,unknown>).independentTrainingTime as Record<string,unknown>).status='available' }],
    ['absolute forecast source path', (v: Record<string, unknown>) => { (v.forecast as Record<string,unknown>).sourceFile=localFixtureRoot+'forecast.parquet' }],
    ['absolute baseline source path', (v: Record<string, unknown>) => { (v.baseline as Record<string,unknown>).sourceFile=localFixtureRoot+'baseline.parquet' }],
    ['absolute baseline manifest path', (v: Record<string, unknown>) => { (v.baseline as Record<string,unknown>).manifestSourceFile=localFixtureRoot+'manifest.json' }],
    ['absolute historical source path', (v: Record<string, unknown>) => { ((v.model as Record<string,unknown>).historicalError as Record<string,unknown>).sourceFile=localFixtureRoot+'metrics.json' }],
    ['zero backtest rows', (v: Record<string, unknown>) => { ((v.model as Record<string,unknown>).historicalError as Record<string,unknown>).backtestRowCount=0 }],
    ['reversed backtest range', (v: Record<string, unknown>) => { const h=(v.model as {historicalError:Record<string,unknown>}).historicalError; h.backtestStartWeek='2025-12-22'; h.backtestEndWeek='2024-12-30' }],
    ['noncanonical artifact timestamp', (v: Record<string, unknown>) => { (v.model as Record<string,unknown>).artifactGeneratedAtUtc='2026-07-05T12:40:05.068774Z' }],
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

  it('accepts a strictly declared available-empty state without converting it to zero', () => {
    const contract=decodeForecastMap(makeAvailableEmpty())
    expect(contract.forecast.status).toBe('available')
    expect(contract.forecast.isEmpty).toBe(true)
    expect(contract.forecast.rows).toEqual([])
    expect(contract.forecast.summary.predictedTotal).toBeNull()
    expect(contract.availability.forecastPointEstimates).toBe('empty')
  })

  it('accepts strict missing and stale states with withheld dimensions and totals', () => {
    const missing=makeAvailableEmpty()
    const missingForecast=missing.forecast as Record<string,unknown>
    const missingSummary=missingForecast.summary as Record<string,unknown>
    const missingBaseline=missing.baseline as Record<string,unknown>
    const missingAvailability=missing.availability as Record<string,unknown>
    missingForecast.status='missing'; missingForecast.isEmpty=false
    missingForecast.reason='Forecast prediction artifact is missing.'
    Object.assign(missingSummary,{
      sourceRowCount:null,sourceSegmentCount:null,modelSegmentCoveragePct:null,
      withheldRowCount:null,
    })
    Object.assign(missingBaseline,{
      status:'invalid',reason:'Baseline values cannot align to a missing forecast.',
      method:null,semantics:null,requiredPriorWeeks:null,priorOnly:null,zeroFillRule:null,
    })
    missingAvailability.forecastPointEstimates='missing'
    const missingContract=decodeForecastMap(missing)
    expect(missingContract.forecast.status).toBe('missing')

    const stale=structuredClone(missing) as Record<string,unknown>
    const staleForecast=stale.forecast as Record<string,unknown>
    const staleAvailability=stale.availability as Record<string,unknown>
    staleForecast.status='stale'; staleForecast.reason='Forecast is behind observations.'
    staleAvailability.forecastPointEstimates='stale'
    stale.model={
      status:'stale',sourceFile:'model_manifest.json',reason:'Model is behind observations.',
      artifactType:null,artifactVersion:null,artifactGeneratedAtUtc:null,
      independentTrainingTime:{
        status:'unavailable',timestamp:null,
        reason:'No independent training-completion timestamp is recorded.',
      },
      name:null,version:null,forecastWeek:null,
      trainingStartWeek:null,trainingThroughWeek:null,leakageControlsVerified:false,
      pointEstimatesOnly:true,predictionIntervalsAvailable:false,
      historicalError:{status:'invalid',sourceFile:'ml_metrics.json',reason:'Historical context cannot align.'},
    }
    const staleContract=decodeForecastMap(stale)
    expect(staleContract.forecast.status).toBe('stale')
    expect(staleContract.forecast.summary.predictedTotal).toBeNull()
  })

  it('preserves point estimates when optional baseline or historical error context is invalid', () => {
    const value=copy() as Record<string,unknown>
    const forecast=value.forecast as {rows:unknown[][]}
    forecast.rows.forEach(row=>{row[6]=null;row[7]=null;row[8]=null})
    const baseline=value.baseline as Record<string,unknown>
    const baselineSummary=baseline.summary as Record<string,unknown>
    Object.assign(baseline,{
      status:'invalid',reason:'Fixture baseline is invalid.',method:null,semantics:null,
      requiredPriorWeeks:null,priorOnly:null,zeroFillRule:null,valueAvailability:'unavailable',
    })
    Object.assign(baselineSummary,{
      baselineAvailableRowCount:0,
      baselineUnavailableRowCount:forecast.rows.length,
      expectedChangeCountAvailableRowCount:0,
      expectedChangePctAvailableRowCount:0,
      zeroBaselineRowCount:0,
    })
    Object.assign(value.availability as Record<string,unknown>,{
      historicalBaseline:'unavailable',expectedChangeCount:'unavailable',
      expectedChangePct:'unavailable',
    })
    const model=value.model as Record<string,unknown>
    model.historicalError={
      status:'invalid',sourceFile:'ml_metrics.json',reason:'Fixture metrics are invalid.',
    }
    const contract=decodeForecastMap(value)
    expect(contract.forecast.status).toBe('available')
    expect(contract.forecast.rows.length).toBeGreaterThan(0)
    expect(contract.baseline.status).toBe('invalid')
    expect(contract.model.historicalError.status).toBe('invalid')
  })
})

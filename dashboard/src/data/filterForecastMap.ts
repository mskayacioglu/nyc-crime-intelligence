import type { ForecastMapContract, PrecinctForecast } from '../types/forecastMap'
import type { OverviewFilters, OverviewMetadata } from '../types/overview'

const same = (a: string, b: string) => a.trim().toLocaleLowerCase('en-US') === b.trim().toLocaleLowerCase('en-US')
const overviewLabel = (values: string[], index: number | null) => index === null ? null : values[index]

export function aggregateForecastPrecincts(contract: ForecastMapContract, metadata: OverviewMetadata, filters: OverviewFilters): PrecinctForecast[] {
  const borough = overviewLabel(metadata.dimensions.boroughs, filters.boroughIndex)
  const precinct = overviewLabel(metadata.dimensions.precincts, filters.precinctIndex)
  const offense = overviewLabel(metadata.dimensions.offenseTypes, filters.offenseIndex)
  const law = overviewLabel(metadata.dimensions.lawCategories, filters.lawIndex)
  const groups = new Map<string, { borough: string; precinct: string; predicted: number; baseline: number; baselineRows: number; totalRows: number }>()
  for (const row of contract.forecast.rows) {
    const b=contract.dimensions.boroughs[row[1]], p=contract.dimensions.precincts[row[2]], o=contract.dimensions.offenseTypes[row[3]], l=contract.dimensions.lawCategories[row[4]]
    if ((borough&&!same(b,borough)) || (precinct&&!same(p,precinct)) || (offense&&!same(o,offense)) || (law&&!same(l,law))) continue
    const current=groups.get(row[9]) ?? {borough:b,precinct:p,predicted:0,baseline:0,baselineRows:0,totalRows:0}
    current.predicted+=row[5]; current.totalRows++
    if(row[6]!==null){current.baseline+=row[6];current.baselineRows++}
    groups.set(row[9],current)
  }
  return [...groups.entries()].map(([id,g])=>{
    const complete=g.baselineRows===g.totalRows
    const baseline=complete ? g.baseline : null
    const change=baseline===null ? null : g.predicted-baseline
    const pct=baseline!==null&&baseline>0 ? change!/baseline*100 : null
    const direction: PrecinctForecast['direction']=change===null ? 'unavailable' : Math.abs(change)<=0.000001 ? 'approximately equal' : change>0 ? 'above' : 'below'
    return {id,borough:g.borough,precinct:g.precinct,forecastWeek:contract.dimensions.forecastWeeks[0],predictedCount:g.predicted,historicalBaseline:baseline,expectedChangeCount:change,expectedChangePct:pct,baselineRows:g.baselineRows,totalRows:g.totalRows,direction}
  }).sort((a,b)=>b.predictedCount-a.predictedCount || a.precinct.localeCompare(b.precinct, 'en-US', {numeric:true}))
}

export type ForecastCompatibility = 'compatible'|'unsupported-date'|'overview-older'|'forecast-older'|'forecast-newer'
export function forecastCompatibility(contract: ForecastMapContract, metadata: OverviewMetadata, filters: OverviewFilters): ForecastCompatibility {
  if (metadata.dataRange.safeEventEndDate < contract.dataRange.safeEventEndDate) return 'forecast-newer'
  if (metadata.dataRange.safeEventEndDate > contract.dataRange.safeEventEndDate) return 'forecast-older'
  if (metadata.dataRange.lastWeek < contract.dataRange.latestObservedWeek) return 'overview-older'
  if (metadata.dataRange.lastWeek > contract.dataRange.latestObservedWeek) return 'forecast-older'
  return filters.endWeek >= metadata.dataRange.latestCompleteWeek ? 'compatible' : 'unsupported-date'
}

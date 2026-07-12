import { FORECAST_MAP_ROW_COLUMNS, type ForecastMapContract, type ForecastMapRow } from '../types/forecastMap'

const PATH = '/data/forecast-map.json'
const DATE = /^\d{4}-\d{2}-\d{2}$/
const UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/
const FORBIDDEN = /(complaint.?id|cmplnt|victim|suspect|race|sex|age.?group|exact.?address|latitude|longitude|person.?score|patrol.?priority|enforcement.?target)/i

const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const integer = (v: unknown): v is number => finite(v) && Number.isInteger(v) && v >= 0
const isoDate = (v: unknown): v is string => typeof v === 'string' && DATE.test(v) && new Date(`${v}T00:00:00Z`).toISOString().slice(0, 10) === v
const addDays = (date: string, days: number) => new Date(Date.parse(`${date}T00:00:00Z`) + days * 86400000).toISOString().slice(0, 10)
const close = (a: number, b: number, tolerance: number) => Math.abs(a - b) <= tolerance

function labels(v: unknown, name: string, nonempty = true): string[] {
  if (!Array.isArray(v) || (nonempty && !v.length) || !v.every(x => typeof x === 'string' && x.length > 0)) throw new Error(`Forecast Map ${name} labels are invalid.`)
  if (new Set(v).size !== v.length || v.some((x, i) => i > 0 && x <= v[i - 1])) throw new Error(`Forecast Map ${name} labels must be sorted and unique.`)
  return v
}

function assertSafeFlags(v: Record<string, unknown>) {
  const privacy = v.privacy as Record<string, unknown>
  const ethics = v.ethics as Record<string, unknown>
  if (!record(privacy) || privacy.aggregateOnly !== true || privacy.complaintIdentifiersIncluded !== false || privacy.demographicAttributesIncluded !== false || privacy.eventLevelCoordinatesIncluded !== false || privacy.eventRecordsIncluded !== false || privacy.exactAddressesIncluded !== false || privacy.namesIncluded !== false || privacy.sourceRowIdentifiersIncluded !== false || !record(ethics) || ethics.aggregateReportedEventVolumeOnly !== true || ethics.enforcementRecommendations !== false || ethics.individualBehaviorPrediction !== false || ethics.patrolRecommendations !== false || ethics.personLevelScoring !== false || ethics.specificIncidentLocationPrediction !== false) throw new Error('Forecast Map privacy or responsible-use flags are incompatible.')
  const keys: string[] = []
  const walk = (x: unknown) => { if (Array.isArray(x)) x.forEach(walk); else if (record(x)) Object.entries(x).forEach(([k, child]) => { keys.push(k); walk(child) }) }
  walk(Object.fromEntries(Object.entries(v).filter(([key]) => key !== 'privacy' && key !== 'ethics')))
  if (keys.some(k => FORBIDDEN.test(k))) throw new Error('Forecast Map contains a forbidden field.')
}

export function decodeForecastMap(v: unknown): ForecastMapContract {
  if (!record(v)) throw new Error('Forecast Map response is not an object.')
  const exactTop = ['application','availability','baseline','dataRange','dimensions','ethics','filterIndex','forecast','forecastSemantics','generatedAtUtc','limitations','locationKeySemantics','methodology','model','privacy','provenance','schemaVersion']
  if (JSON.stringify(Object.keys(v).sort()) !== JSON.stringify(exactTop) || v.schemaVersion !== '1.0.0' || !UTC.test(String(v.generatedAtUtc))) throw new Error('Forecast Map identity or schema is incompatible.')
  const app = v.application; const rangeUnknown = v.dataRange; const dimsUnknown = v.dimensions; const forecastUnknown = v.forecast
  if (!record(app) || app.name !== 'NYC Crime Intelligence' || app.phase !== 'Phase 7C.1' || app.view !== 'Forecast Map Data Contract' || !record(rangeUnknown) || !record(dimsUnknown) || !record(forecastUnknown)) throw new Error('Forecast Map required sections are invalid.')
  const candidate = v as unknown as ForecastMapContract
  const range=candidate.dataRange, dims=candidate.dimensions, forecast=candidate.forecast
  if (![range.safeEventStartDate,range.safeEventEndDate,range.firstObservedWeek,range.latestObservedWeek,range.latestCompleteWeek].every(isoDate) || range.latestWeekIsPartial !== true || !Array.isArray(range.supportedForecastWeeks) || range.supportedForecastWeeks.length !== 1 || !isoDate(range.supportedForecastWeeks[0])) throw new Error('Forecast Map date range is invalid.')
  const weeks = labels(dims.forecastWeeks, 'forecastWeeks'); const boroughs = labels(dims.boroughs, 'boroughs'); const precincts = labels(dims.precincts, 'precincts'); const offenses = labels(dims.offenseTypes, 'offenseTypes'); const laws = labels(dims.lawCategories, 'lawCategories')
  const week = weeks[0]
  if (weeks.length !== 1 || week !== range.supportedForecastWeeks[0] || week <= range.latestObservedWeek || week !== addDays(range.latestObservedWeek as string, 7) || String(v.generatedAtUtc).slice(0,10) !== range.safeEventEndDate) throw new Error('Forecast Map horizon or generation date is incompatible.')
  const index = v.filterIndex
  if (!record(index) || !record(index.precinctsByBorough) || JSON.stringify(index.precinctsByBorough.rowColumns) !== JSON.stringify(['boroughIndex','precinctIndexes']) || !Array.isArray(index.precinctsByBorough.rows)) throw new Error('Forecast Map filter index is invalid.')
  const precinctBorough = new Map<number, number>()
  for (const row of index.precinctsByBorough.rows) { if (!Array.isArray(row) || row.length !== 2 || !integer(row[0]) || row[0] >= boroughs.length || !Array.isArray(row[1]) || !row[1].every(p => integer(p) && p < precincts.length) || new Set(row[1]).size !== row[1].length) throw new Error('Forecast Map filter index is invalid.'); for (const p of row[1]) { if (precinctBorough.has(p)) throw new Error('Forecast Map precinct has multiple boroughs.'); precinctBorough.set(p, row[0]) } }
  if (precinctBorough.size !== precincts.length) throw new Error('Forecast Map precinct index is incomplete.')
  if (!['available','missing','invalid','stale'].includes(String(forecast.status)) || typeof forecast.sourceFile !== 'string' || typeof forecast.isEmpty !== 'boolean' || JSON.stringify(forecast.rowColumns) !== JSON.stringify(FORECAST_MAP_ROW_COLUMNS) || !Array.isArray(forecast.rows) || !record(forecast.summary)) throw new Error('Forecast Map forecast section is invalid.')
  if (forecast.status !== 'available' && (typeof forecast.reason !== 'string' || forecast.rows.length || forecast.isEmpty)) throw new Error('Unavailable Forecast Map cannot expose rows.')
  if (forecast.status === 'available' && forecast.isEmpty !== (forecast.rows.length === 0)) throw new Error('Forecast Map empty state is inconsistent.')
  const tolerance = record(v.methodology) && finite(v.methodology.arithmeticTolerance) ? v.methodology.arithmeticTolerance : NaN
  if (tolerance !== 0.000001) throw new Error('Forecast Map arithmetic tolerance is invalid.')
  const logical = new Set<string>(); let previous = ''; let total = 0; let zero = 0; let baseAvailable = 0; let pctAvailable = 0; const byBorough = Array(boroughs.length).fill(0)
  for (let i=0;i<forecast.rows.length;i++) {
    const raw=forecast.rows[i] as unknown
    if (!Array.isArray(raw) || raw.length !== 10) throw new Error(`Forecast Map row ${i+1} has invalid width.`)
    const [wi,bi,pi,oi,li,pred,base,change,pct,key] = raw as ForecastMapRow
    if (![wi,bi,pi,oi,li].every(integer) || wi >= weeks.length || bi >= boroughs.length || pi >= precincts.length || oi >= offenses.length || li >= laws.length || !finite(pred) || pred < 0 || (base !== null && (!finite(base) || base < 0)) || (change !== null && !finite(change)) || (pct !== null && !finite(pct)) || typeof key !== 'string' || key !== `nypd-precinct:${precincts[pi]}` || precinctBorough.get(pi) !== bi) throw new Error(`Forecast Map row ${i+1} contains an invalid value.`)
    const lk=[wi,bi,pi,oi,li].map(value=>String(value).padStart(6,'0')).join('|')
    if(logical.has(lk) || (previous && lk <= previous)) throw new Error('Forecast Map rows are duplicate or unstably ordered.')
    logical.add(lk); previous=lk
    if(base===null ? change!==null || pct!==null : change===null || !close(change,pred-base,tolerance) || (base===0 ? pct!==null : pct===null || !close(pct,change/base*100,tolerance))) throw new Error('Forecast Map baseline/change arithmetic is invalid.')
    total += pred; byBorough[bi]++; if(pred===0) zero++; if(base!==null) baseAvailable++; if(pct!==null) pctAvailable++
  }
  const s=forecast.summary
  const numericSummary = finite(s.predictedTotal) && finite(s.sourcePredictedTotal) && finite(s.withheldPredictedTotal) && finite(s.rowCoveragePct) && finite(s.predictedVolumeCoveragePct)
  if (s.rowCount!==forecast.rows.length || s.sourceRowCount!==s.sourceSegmentCount || s.sourceRowCount!==s.rowCount+s.withheldRowCount || s.withheldRowCount!==s.withheldReasonCounts.boroughMismatch+s.withheldReasonCounts.unmappableLocation || s.publishedBoroughCount!==boroughs.length || s.publishedPrecinctCount!==precincts.length || s.zeroPredictionRowCount!==zero || JSON.stringify(s.countsByBorough)!==JSON.stringify(byBorough) || (forecast.rows.length ? !numericSummary || !close(s.predictedTotal!,total,tolerance) || !close(s.sourcePredictedTotal!,s.predictedTotal!+s.withheldPredictedTotal!,tolerance) || !close(s.rowCoveragePct!,s.rowCount/s.sourceRowCount*100,tolerance) || !close(s.predictedVolumeCoveragePct!,s.predictedTotal!/s.sourcePredictedTotal!*100,tolerance) : s.predictedTotal!==null)) throw new Error('Forecast Map summary does not reconcile.')
  const baseline=candidate.baseline; const model=candidate.model
  if (!record(baseline) || !record(baseline.summary) || baseline.priorOnly!==true || baseline.summary.publishedRowCount!==forecast.rows.length || baseline.summary.baselineAvailableRowCount!==baseAvailable || baseline.summary.baselineUnavailableRowCount!==forecast.rows.length-baseAvailable || baseline.summary.expectedChangeCountAvailableRowCount!==baseAvailable || baseline.summary.expectedChangePctAvailableRowCount!==pctAvailable || !record(model) || model.status!=='available' || model.artifactType!=='weekly_forecast_ml_model' || model.artifactVersion!==1 || model.forecastWeek!==week || model.trainingThroughWeek!==range.latestObservedWeek || model.pointEstimatesOnly!==true || model.predictionIntervalsAvailable!==false || model.leakageControlsVerified!==true || !record(model.historicalError) || model.historicalError.status!=='available' || !finite(model.historicalError.mae) || !finite(model.historicalError.rmse) || !finite(model.historicalError.predictionCoveragePct) || !finite(model.historicalError.backtestRowCount) || model.historicalError.backtestEndWeek!==range.latestCompleteWeek) throw new Error('Forecast Map model, error, or baseline context is invalid.')
  const loc=candidate.locationKeySemantics
  if (!record(loc) || loc.coordinatesIncluded!==false || loc.geometryIncluded!==false || loc.spatialReferenceAvailable!==false || loc.stableJoinKeyOnly!==true || loc.scheme!=='nypd-precinct:<source precinct label>') throw new Error('Forecast Map spatial-reference contract is invalid.')
  assertSafeFlags(v)
  return candidate
}

export async function loadForecastMap(): Promise<ForecastMapContract> {
  const response = await fetch(PATH, { cache: 'no-cache' })
  if (!response.ok) throw new Error('Forecast Map data could not be loaded.')
  return decodeForecastMap(await response.json())
}

import { describe, expect, it } from 'vitest'
import generatedOverview from '../../public/data/overview.json'
import { overviewFixture } from '../test/fixture'
import type { AnomalyRow, OverviewMetadata } from '../types/overview'
import { decodeAnomalies } from './decodeAnomalies'
import { filterAnomalies } from './filterAnomalies'

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

function availableRows(metadata: OverviewMetadata): AnomalyRow[] {
  return metadata.signals.anomalies.rows as AnomalyRow[]
}

describe('Overview anomaly decoder', () => {
  it('accepts the authoritative generated artifact and its default selection', () => {
    const contract = decodeAnomalies(generatedOverview)

    expect(contract.status).toBe('available')
    if (contract.status !== 'available') return
    expect(contract.sourceFile).toBe('anomalies.parquet')
    expect(contract.rows).toHaveLength(10_378)
    expect(contract.summary).toEqual({
      rowCount: 10_378,
      highCount: 7_301,
      criticalCount: 3_077,
      isEmpty: false,
      scoringEndWeek: '2025-12-22',
    })
    expect(contract.scoringEndWeek).toBe('2025-12-22')
    expect(contract.rows[0]).toMatchObject({
      week: '2020-06-01',
      borough: 'BRONX',
      precinct: '46',
      offenseType: 'BURGLARY',
      lawCategory: 'FELONY',
      actualCount: 118,
      expectedCount: 4,
      residualCount: 114,
      score: 53.603,
      severity: 'critical',
      expectedSource: 'rolling_13_week_mean',
      referenceLabel: 'Prior 13-week average',
      directionLabel: 'Above expectation',
    })

    const filtered = filterAnomalies(contract, {
      startWeek: generatedOverview.dataRange.defaultStartWeek,
      endWeek: generatedOverview.dataRange.defaultEndWeek,
      boroughIndex: null,
      precinctIndex: null,
      offenseIndex: null,
      lawIndex: null,
    })
    expect(filtered.rows).toHaveLength(645)
    expect(filtered.rows[0]).toMatchObject({
      week: '2025-06-09',
      borough: 'MANHATTAN',
      precinct: '5',
      offenseType: 'OFFENSES AGAINST PUBLIC ADMINI',
      lawCategory: 'MISDEMEANOR',
      actualCount: 31,
      expectedCount: 3.0625,
      residualCount: 27.9375,
      score: 11.8988,
      severity: 'critical',
      expectedSource: 'ml_prediction',
    })
  })

  it('derives stable tuple identities and explicit analytical labels', () => {
    const contract = decodeAnomalies(validOverview())

    expect(contract.status).toBe('available')
    if (contract.status !== 'available') return
    expect(contract.rows[0]).toMatchObject({
      id: 'anomaly:2025-03-03|BRONX|1|GRAND%20LARCENY|FELONY',
      sourceRank: 1,
      signedDeviation: 6.5,
      signedDeviationLabel: '+6.5',
      direction: 'above',
      directionLabel: 'Above expectation',
      referenceLabel: 'Prior 13-week average',
      priorityLabel: 'Critical signal priority',
    })
    expect(contract.rows[1]).toMatchObject({
      referenceLabel: 'Historical backtest estimate',
      priorityLabel: 'High signal priority',
    })
    expect(contract.rows[0].deviationPct).toBeCloseTo(56.521739)
  })

  it('preserves a valid zero expectation without inventing a percentage', () => {
    const metadata = validOverview()
    const first = availableRows(metadata)[0]
    first[6] = 0
    first[7] = first[5]

    const contract = decodeAnomalies(metadata)

    expect(contract.status).toBe('available')
    if (contract.status !== 'available') return
    expect(contract.rows[0].expectedCount).toBe(0)
    expect(contract.rows[0].residualCount).toBe(18)
    expect(contract.rows[0].deviationPct).toBeNull()
    expect(contract.rows[0].signedDeviationLabel).toBe('+18')
  })

  it('treats an unavailable expectation as invalid rather than converting it to zero', () => {
    const metadata = validOverview()
    const first = availableRows(metadata)[0] as unknown[]
    first[6] = null

    expect(decodeAnomalies(metadata)).toMatchObject({
      status: 'invalid',
      reason: 'Anomaly row 1 has an invalid expected aggregate count.',
    })
  })

  it.each([
    ['missing', 'Source was not published.'],
    ['invalid', 'Source validation failed.'],
    ['stale', 'Source is older than this snapshot.'],
    ['incompatible', 'Source schema is unsupported.'],
  ] as const)('preserves a declared %s unavailable state', (status, reason) => {
    const metadata = validOverview()
    metadata.signals.anomalies.status = status
    metadata.signals.anomalies.reason = reason
    metadata.signals.anomalies.rows = []

    const contract = decodeAnomalies(metadata)

    expect(contract).toEqual({
      status,
      sourceFile: 'anomalies.parquet',
      reason,
    })
  })

  it('rejects hidden rows on a declared unavailable signal', () => {
    const metadata = validOverview()
    metadata.signals.anomalies.status = 'stale'
    metadata.signals.anomalies.reason = 'Source is stale.'

    expect(decodeAnomalies(metadata)).toEqual({
      status: 'invalid',
      sourceFile: 'anomalies.parquet',
      reason: 'An unavailable anomaly contract cannot contain rows.',
    })
  })

  it('maps unknown statuses to incompatible without throwing', () => {
    const metadata = validOverview()
    metadata.signals.anomalies.status = 'available-later'

    expect(decodeAnomalies(metadata)).toEqual({
      status: 'incompatible',
      sourceFile: 'anomalies.parquet',
      reason: 'The Overview anomaly status is unknown.',
    })
    expect(decodeAnomalies(null).status).toBe('incompatible')
  })

  it('requires the exact row columns and width', () => {
    const changedColumns = validOverview()
    changedColumns.signals.anomalies.rowColumns![0] = 'complaintId'
    expect(decodeAnomalies(changedColumns)).toMatchObject({
      status: 'incompatible',
      reason: 'The Overview anomaly row columns are incompatible.',
    })

    const changedWidth = validOverview()
    availableRows(changedWidth)[0].pop()
    expect(decodeAnomalies(changedWidth)).toMatchObject({
      status: 'incompatible',
      reason: 'Anomaly row 1 does not have the required width.',
    })
  })

  it.each([
    ['fractional week index', 0, 0.5],
    ['out-of-range borough index', 1, 99],
    ['negative precinct index', 2, -1],
    ['out-of-range offense index', 3, 99],
    ['out-of-range law index', 4, 99],
    ['out-of-range severity index', 9, 99],
    ['out-of-range expectation-source index', 10, 99],
  ] as const)('rejects an invalid %s', (_label, column, value) => {
    const metadata = validOverview()
    availableRows(metadata)[0][column] = value

    expect(decodeAnomalies(metadata)).toMatchObject({
      status: 'invalid',
      reason: 'Anomaly row 1 contains an invalid dimension index.',
    })
  })

  it('rejects non-Monday and post-complete anomaly periods', () => {
    const nonMonday = validOverview()
    nonMonday.dimensions.weeks[8] = '2025-03-04'
    expect(decodeAnomalies(nonMonday)).toMatchObject({
      status: 'invalid',
      reason: 'Anomaly row 1 is not a complete Monday-starting week.',
    })

    const postComplete = validOverview()
    availableRows(postComplete)[0][0] = 9
    expect(decodeAnomalies(postComplete)).toMatchObject({
      status: 'invalid',
      reason: 'Anomaly row 1 is not a complete Monday-starting week.',
    })
  })

  it.each([
    ['fractional actual', 5, 1.5, 'invalid observed aggregate count'],
    ['negative actual', 5, -1, 'invalid observed aggregate count'],
    ['non-finite actual', 5, Number.NaN, 'invalid observed aggregate count'],
    ['negative expectation', 6, -1, 'invalid expected aggregate count'],
    ['non-finite expectation', 6, Number.POSITIVE_INFINITY, 'invalid expected aggregate count'],
    ['zero residual', 7, 0, 'must have a positive deviation'],
    ['negative residual', 7, -1, 'must have a positive deviation'],
    ['non-finite residual', 7, Number.NaN, 'must have a positive deviation'],
    ['negative score', 8, -1, 'invalid anomaly score'],
    ['non-finite score', 8, Number.POSITIVE_INFINITY, 'invalid anomaly score'],
  ] as const)('fails closed for %s', (_label, column, value, message) => {
    const metadata = validOverview()
    availableRows(metadata)[0][column] = value

    const contract = decodeAnomalies(metadata)
    expect(contract.status).toBe('invalid')
    if (contract.status === 'available') return
    expect(contract.reason).toContain(message)
  })

  it('enforces residual reconciliation at the four-decimal publication precision', () => {
    const withinTolerance = validOverview()
    availableRows(withinTolerance)[0][7] += 0.00009
    expect(decodeAnomalies(withinTolerance).status).toBe('available')

    const outsideTolerance = validOverview()
    availableRows(outsideTolerance)[0][7] += 0.00011
    expect(decodeAnomalies(outsideTolerance)).toMatchObject({
      status: 'invalid',
      reason: 'Anomaly row 1 does not reconcile observed and expected counts.',
    })
  })

  it('allows only documented severity and expectation-source labels', () => {
    const severity = validOverview()
    severity.dimensions.severities[0] = 'urgent'
    expect(decodeAnomalies(severity)).toMatchObject({
      status: 'invalid',
      reason: 'Anomaly row 1 has an unsupported severity.',
    })

    const expectation = validOverview()
    expectation.dimensions.anomalyExpectedSources[1] = 'future_forecast'
    expect(decodeAnomalies(expectation)).toMatchObject({
      status: 'invalid',
      reason: 'Anomaly row 1 has an unsupported expectation source.',
    })
  })

  it('rejects duplicate logical identities and out-of-order rows', () => {
    const duplicate = validOverview()
    const duplicateRow = [...availableRows(duplicate)[0]] as AnomalyRow
    availableRows(duplicate).push(duplicateRow)
    duplicate.signals.anomalies.summary = {
      rowCount: 3,
      highCount: 1,
      criticalCount: 2,
      isEmpty: false,
      scoringEndWeek: '2025-03-03',
    }
    expect(decodeAnomalies(duplicate)).toMatchObject({
      status: 'invalid',
      reason: 'Anomaly row 3 duplicates a logical identity.',
    })

    const outOfOrder = validOverview()
    availableRows(outOfOrder).reverse()
    expect(decodeAnomalies(outOfOrder)).toMatchObject({
      status: 'invalid',
      reason: 'Anomaly row 2 is outside the deterministic source order.',
    })
  })

  it('requires an exact, fully reconciled summary', () => {
    const mismatch = validOverview()
    mismatch.signals.anomalies.summary = {
      rowCount: 2,
      highCount: 2,
      criticalCount: 0,
      isEmpty: false,
      scoringEndWeek: '2025-03-03',
    }
    expect(decodeAnomalies(mismatch)).toMatchObject({
      status: 'invalid',
      reason: 'The anomaly summary does not reconcile with its rows.',
    })

    const extra = validOverview()
    extra.signals.anomalies.summary = {
      rowCount: 2,
      highCount: 1,
      criticalCount: 1,
      isEmpty: false,
      lowCount: 0,
      scoringEndWeek: '2025-03-03',
    }
    expect(decodeAnomalies(extra)).toMatchObject({
      status: 'invalid',
      reason: 'The anomaly summary schema is invalid.',
    })

    const emptyFlag = validOverview()
    const emptySummary = emptyFlag.signals.anomalies.summary as Record<string, unknown>
    emptySummary.isEmpty = true
    expect(decodeAnomalies(emptyFlag)).toMatchObject({
      status: 'invalid',
      reason: 'The anomaly summary does not reconcile with its rows.',
    })

    const horizon = validOverview()
    const horizonSummary = horizon.signals.anomalies.summary as Record<string, unknown>
    horizonSummary.scoringEndWeek = '2025-02-24'
    expect(decodeAnomalies(horizon)).toMatchObject({
      status: 'invalid',
      reason: 'The anomaly scoring horizon does not match the latest complete week.',
    })
  })

  it('fails closed on incompatible schema, application, or responsible-use flags', () => {
    const schema = validOverview()
    schema.schemaVersion = '2.0.0'
    expect(decodeAnomalies(schema).status).toBe('incompatible')

    const application = validOverview()
    application.application.view = 'Forecast'
    expect(decodeAnomalies(application).status).toBe('incompatible')

    const version = validOverview()
    version.versions.dashboardContract = '0.9.0'
    expect(decodeAnomalies(version).status).toBe('incompatible')

    const ethics = validOverview()
    ethics.ethics.personLevelScoring = true
    expect(decodeAnomalies(ethics)).toMatchObject({
      status: 'incompatible',
      reason: 'The Overview responsible-use contract is incompatible.',
    })
  })
})

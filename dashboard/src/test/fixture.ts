import type {
  AnomalyRow,
  ForecastRow,
  HotspotRow,
  OverviewBundle,
  OverviewMetadata,
} from '../types/overview'

const weeks = [
  '2025-01-06',
  '2025-01-13',
  '2025-01-20',
  '2025-01-27',
  '2025-02-03',
  '2025-02-10',
  '2025-02-17',
  '2025-02-24',
  '2025-03-03',
  '2025-03-10',
  '2025-03-17',
]

export function overviewFixture({ optional = true } = {}): OverviewBundle {
  const counts: number[] = []
  const weekIndexes: number[] = []
  const boroughs: number[] = []
  const precincts: number[] = []
  const offenses: number[] = []
  const laws: number[] = []

  for (let weekIndex = 0; weekIndex <= 9; weekIndex += 1) {
    counts.push(10 + weekIndex, 5)
    weekIndexes.push(weekIndex, weekIndex)
    boroughs.push(0, 1)
    precincts.push(0, 1)
    offenses.push(0, 1)
    laws.push(0, 1)
  }

  const hotspotRows: HotspotRow[] = [
    [0, 0, null, 0, 0, '2025-03-10', 'GRID 40.845, -73.905', 30, 10.91, 175, 92, 0],
    [1, 1, 1, 1, 1, '2025-03-10', null, 12, 6.49, 85, 71, 1],
  ]
  const anomalyRows: AnomalyRow[] = [
    [8, 0, 0, 0, 0, 18, 11.5, 6.5, 4.2, 0, 1],
    [7, 1, 1, 1, 1, 5, 2, 3, 3.1, 1, 0],
  ]
  const forecastRows: ForecastRow[] = [
    [10, 0, 0, 0, 0, 12.5, 0],
    [10, 1, 1, 1, 1, 5.5, 0],
  ]

  const metadata: OverviewMetadata = {
    schemaVersion: '1.0.0',
    generatedAtUtc: '2025-03-10T00:00:00Z',
    application: {
      name: 'NYC Crime Intelligence',
      phase: 'Phase 7A',
      view: 'Overview',
    },
    cube: {
      encoding: 'columnar-arrays-v1',
      compression: 'gzip',
      byteOrder: 'little-endian',
      path: '/data/overview-cube.bin.gz',
      rowCount: counts.length,
      columnOrder: ['counts', 'weeks', 'boroughs', 'precincts', 'offenses', 'laws'],
      columns: {
        counts: { type: 'uint32', length: counts.length, offsetBytes: 0, byteLength: counts.length * 4 },
        weeks: { type: 'uint16', length: counts.length, offsetBytes: counts.length * 4, byteLength: counts.length * 2 },
        boroughs: { type: 'uint8', length: counts.length, offsetBytes: counts.length * 6, byteLength: counts.length },
        precincts: { type: 'uint8', length: counts.length, offsetBytes: counts.length * 7, byteLength: counts.length },
        offenses: { type: 'uint8', length: counts.length, offsetBytes: counts.length * 8, byteLength: counts.length },
        laws: { type: 'uint8', length: counts.length, offsetBytes: counts.length * 9, byteLength: counts.length },
      },
    },
    dataRange: {
      safeEventStartDate: '2025-01-06',
      safeEventEndDate: '2025-03-10',
      firstWeek: '2025-01-06',
      lastWeek: '2025-03-10',
      latestCompleteWeek: '2025-03-03',
      latestWeekIsPartial: true,
      defaultStartWeek: '2025-01-06',
      defaultEndWeek: '2025-03-03',
    },
    dimensions: {
      weeks,
      boroughs: ['BRONX', 'BROOKLYN'],
      precincts: ['1', '2', 'UNKNOWN'],
      offenseTypes: ['GRAND LARCENY', 'ROBBERY', 'NO OBSERVED RECORDS'],
      lawCategories: ['FELONY', 'MISDEMEANOR', 'VIOLATION'],
      severities: ['critical', 'high'],
      hotspotGrains: ['grid', 'precinct'],
      anomalyExpectedSources: ['ml_prediction', 'rolling_13_week_mean'],
      modelNames: ['fixture_forecast'],
    },
    filterIndex: {
      precinctsByBorough: {
        rowColumns: ['boroughIndex', 'precinctIndexes'],
        rows: [[0, [0, 2]], [1, [1, 2]]],
      },
    },
    dataQuality: {
      aggregateSafeEventCount: counts.reduce((sum, value) => sum + value, 0),
      excludedEventCount: 3,
      cleanSourceRowCount: counts.reduce((sum, value) => sum + value, 0) + 3,
      countsReconciled: true,
      dateBasis: 'Fixture maximum aggregate-safe event date.',
      sourceIssueCounts: {
        populationCount: counts.reduce((sum, value) => sum + value, 0) + 3,
        missingInvalidComplaintStartDate: 1,
        implausiblyOldComplaintStartDate: 1,
        futureComplaintStartDate: 0,
        futureComplaintEndDate: 0,
        complaintEndBeforeStart: 0,
        reportDateBeforeComplaintStart: 0,
        missingBorough: 1,
        missingPrecinct: 0,
        missingOffense: 0,
        missingCoordinates: 0,
        zeroCoordinates: 0,
        coordinatesOutsideBroadNycBounds: 0,
        invalidLawCategory: 0,
        rowsWithAnyIssue: 3,
        rowsWithMultipleIssues: 0,
        maximumIssuesPerRow: 1,
        categoriesOverlap: true,
        countsAreNonAdditive: true,
      },
      aggregateSafeUnknownCounts: {
        populationCount: counts.reduce((sum, value) => sum + value, 0),
        borough: 0,
        precinct: 0,
        offense: 0,
        lawCategory: 0,
        valuesRetained: true,
        categoriesOverlap: true,
      },
    },
    observed: {
      unit: 'reported aggregate complaint events',
      comparisonSemantics: 'Equal complete-week windows.',
      dateFilterSemantics: 'Inclusive Monday week starts.',
      latestWeekNote: 'Latest week is partial.',
      safeEventCount: counts.reduce((sum, value) => sum + value, 0),
    },
    signals: {
      hotspots: optional
        ? {
            status: 'available',
            sourceFile: 'hotspots.parquet',
            rowColumns: ['grainIndex', 'boroughIndex', 'precinctIndex', 'offenseTypeIndex', 'lawCategoryIndex', 'scoringEndDate', 'locationLabel', 'recentCount', 'expectedRecentCount', 'liftPct', 'score', 'severityIndex'],
            rows: hotspotRows,
            summary: { snapshotDate: '2025-03-10', snapshotAgeDays: 0 },
          }
        : { status: 'unavailable', reason: 'Hotspot output was not supplied.' },
      anomalies: optional
        ? {
            status: 'available',
            sourceFile: 'anomalies.parquet',
            rowColumns: ['weekIndex', 'boroughIndex', 'precinctIndex', 'offenseTypeIndex', 'lawCategoryIndex', 'actualCount', 'expectedCount', 'residualCount', 'score', 'severityIndex', 'expectedSourceIndex'],
            rows: anomalyRows,
          }
        : { status: 'unavailable', reason: 'Anomaly output was not supplied.' },
      forecast: optional
        ? {
            status: 'available',
            sourceFile: 'ml_predictions.parquet',
            rowColumns: ['weekIndex', 'boroughIndex', 'precinctIndex', 'offenseTypeIndex', 'lawCategoryIndex', 'predictedCount', 'modelNameIndex'],
            rows: forecastRows,
            summary: {
              historicalError: {
                status: 'available',
                mae: 0.5,
                rmse: 1.4,
                weightedMae: 3.7,
                predictionCoveragePct: 100,
                unit: 'reported events per segment-week',
                scope: 'overall model backtest across all segments',
                filterSemantics: 'Historical errors are not recomputed for active dashboard filters.',
              },
              limitations: ['No uncertainty interval is available.'],
            },
          }
        : { status: 'unavailable', reason: 'Forecast output was not supplied.' },
    },
    versions: {
      dashboardContract: '1.0.0',
      mlManifest: {
        status: optional ? 'available' : 'unavailable',
        modelVersion: 1,
        sourceFile: 'model_manifest.json',
      },
      mlMetrics: {
        status: optional ? 'available' : 'unavailable',
        backtestMae: 0.5,
        backtestRmse: 1.4,
        backtestWeightedMae: 3.7,
        sourceFile: 'ml_metrics.json',
      },
    },
    ethics: {
      aggregateTrendIntelligenceOnly: true,
      demographicAttributesIncluded: false,
      enforcementRecommendations: false,
      eventRecordsIncluded: false,
      patrolRecommendations: false,
      personLevelScoring: false,
    },
    limitations: [
      'Counts describe reported aggregate complaint events and do not explain causality.',
      'Outputs are decision-support context and are not grounds for enforcement action.',
    ],
  }

  return {
    metadata,
    cube: {
      counts: Uint32Array.from(counts),
      weeks: Uint16Array.from(weekIndexes),
      boroughs: Uint8Array.from(boroughs),
      precincts: Uint8Array.from(precincts),
      offenses: Uint8Array.from(offenses),
      laws: Uint8Array.from(laws),
    },
  }
}

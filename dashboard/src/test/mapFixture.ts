import type {
  MapDataContract,
  MapHotspotRow,
  MapHotspotStatus,
} from '../types/map'

const AVAILABLE_ROWS: MapHotspotRow[] = [
  [
    1,
    0,
    1,
    null,
    1,
    1,
    40.845,
    -73.905,
    'Grid 40.845, -73.905',
    30,
    10.91,
    175,
    92,
    3,
    98.5,
  ],
  [
    2,
    1,
    0,
    0,
    0,
    0,
    40.6812,
    -73.9461,
    'Brooklyn · Precinct 2 aggregate centroid',
    22,
    12.4,
    77.4,
    78,
    2,
    96,
  ],
  [
    3,
    0,
    0,
    null,
    0,
    0,
    40.695,
    -73.975,
    'Grid 40.695, -73.975',
    14,
    10.2,
    37.3,
    61,
    1,
    100,
  ],
  [
    4,
    1,
    1,
    1,
    1,
    1,
    40.822,
    -73.91,
    'Bronx · Precinct 1 aggregate centroid',
    12,
    8,
    50,
    67,
    2,
    94,
  ],
  [
    5,
    1,
    1,
    1,
    0,
    0,
    40.824,
    -73.912,
    'Bronx · Precinct 1 robbery centroid',
    7,
    6.5,
    7.7,
    42,
    0,
    91,
  ],
]

interface MapFixtureOptions {
  status?: MapHotspotStatus
  empty?: boolean
}

export function mapFixture({
  status = 'available',
  empty = false,
}: MapFixtureOptions = {}): MapDataContract {
  const rows = status === 'available' && !empty ? AVAILABLE_ROWS.map((row) => [...row] as MapHotspotRow) : []
  return {
    schemaVersion: '1.0.0',
    generatedAtUtc: '2025-03-10T12:00:00Z',
    application: {
      name: 'NYC Crime Intelligence',
      phase: 'Phase 7B',
      view: 'Map and Hotspot View',
    },
    dataRange: {
      safeEventStartDate: '2025-01-06',
      safeEventEndDate: '2025-03-10',
      aggregateSafeEventCount: 171,
      sourceEventCount: 174,
      excludedEventCount: 3,
      unit: 'reported aggregate complaint events',
    },
    dimensions: {
      hotspotGrains: ['grid', 'precinct'],
      boroughs: ['BROOKLYN', 'BRONX'],
      precincts: ['2', '1', 'UNKNOWN'],
      offenseTypes: ['ROBBERY', 'GRAND LARCENY'],
      lawCategories: ['MISDEMEANOR', 'FELONY'],
      severities: ['low', 'medium', 'high', 'critical'],
    },
    filterIndex: {
      precinctsByBorough: {
        rowColumns: ['boroughIndex', 'precinctIndexes'],
        rows: [[0, [0]], [1, [1]]],
        semantics: 'Fixture snapshot precinct index.',
      },
    },
    hotspots: {
      status,
      sourceFile: 'hotspots.parquet',
      ...(status === 'available'
        ? {}
        : { reason: `Fixture hotspot source is ${status}.` }),
      rowColumns: [
        'rank',
        'grainIndex',
        'boroughIndex',
        'precinctIndex',
        'offenseTypeIndex',
        'lawCategoryIndex',
        'latitude',
        'longitude',
        'locationLabel',
        'recentCount',
        'expectedRecentCount',
        'liftPct',
        'score',
        'severityIndex',
        'coordinateCoveragePct',
      ],
      rows,
      summary: {
        rowCount: rows.length,
        scoringEndDate: rows.length > 0 ? '2025-03-10' : null,
        snapshotAgeDays: rows.length > 0 ? 0 : null,
        currentMaxAgeDays: 1,
        recentWindowDays: rows.length > 0 ? 30 : null,
        baselineWindowDays: rows.length > 0 ? 365 : null,
        gridSizeDegrees: rows.length > 0 ? 0.01 : null,
        counts: {
          byGrain: rows.length > 0 ? [2, 3] : [0, 0],
          bySeverity: rows.length > 0 ? [1, 1, 2, 1] : [0, 0, 0, 0],
        },
      },
    },
    methodology: {
      expectedRecentCountDefinition:
        'Expected count is the historical baseline normalized to the recent window.',
    },
    provenance: {
      hotspots: { status, sourceFile: 'hotspots.parquet' },
    },
    filterSemantics: {
      precinct: 'Grid rows have no precinct assignment.',
    },
    coordinateSemantics: {
      gridCoordinates: 'Grid coordinates are deterministic aggregate cell centers.',
      precinctCoordinates:
        'Precinct coordinates are aggregate centroids, not official boundary centers.',
    },
    dateSemantics: {
      mode: 'fixed-current-snapshot',
      historicalSelectionBehavior:
        'The fixed snapshot is withheld when the selection ends before the latest complete week.',
    },
    grainSemantics: {
      grid: 'Aggregate grid cell.',
      precinct: 'Aggregate precinct centroid.',
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
      'Hotspots describe aggregate concentration, not individual behavior.',
      'Signals do not justify patrol or enforcement action.',
    ],
  }
}

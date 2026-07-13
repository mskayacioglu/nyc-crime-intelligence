import type { ForecastMapContract } from '../types/forecastMap'
import type {
  PrecinctSpatialFeature,
  PrecinctSpatialGeometry,
  PrecinctSpatialReferenceContract,
  PrecinctSpatialReferenceLoader,
} from '../types/precinctSpatialReference'

const PATH = '/data/precinct-spatial-reference.json'
const SCHEMA_VERSION = '1.0.0'
const SPATIAL_FRESHNESS_DAYS = 120
const SPATIAL_FRESHNESS_LIMITATION =
  'Because the official source is quarterly, the browser treats this spatial artifact as stale 120 calendar days after the recorded portalRowsUpdatedAtUtc timestamp unless a reviewed newer edition is vendored.'
const LOCATION_KEY_SCHEME = 'nypd-precinct:<source precinct label>'
const EXPECTED_PRECINCT_COUNT = 78
const UTC_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/
const PRECINCT_LABEL = /^[1-9]\d{0,2}$/
const NYC_LONGITUDE_MIN = -74.3
const NYC_LONGITUDE_MAX = -73.65
const NYC_LATITUDE_MIN = 40.45
const NYC_LATITUDE_MAX = 40.95
const SOURCE_BYTE_SIZE = 3_842_773
const SOURCE_SHA256 = '5210830afa9d0875b7a7c769edfc4d2ebe984a9ab1e36f3b7fad8508828172aa'
const PROVENANCE_BYTE_SIZE = 2_676
const PROVENANCE_SHA256 = '48c20488e785dbfff204803d86f78d86dfb9e7513372cee51a830135864e385f'
const SHA256 = /^[0-9a-f]{64}$/
const RETRIEVAL_URL =
  'https://data.cityofnewyork.us/api/geospatial/y76i-bdw7?method=export&format=GeoJSON'
const DATASET_PAGE_URL =
  'https://data.cityofnewyork.us/City-Government/Police-Precincts/y76i-bdw7'
const PUBLISHER_PAGE_URL =
  'https://www.nyc.gov/content/planning/pages/resources/datasets/police-precincts'
const METADATA_API_URL = 'https://data.cityofnewyork.us/api/views/y76i-bdw7'
const METADATA_PDF_URL =
  'https://s-media.nyc.gov/agencies/dcp/assets/files/pdf/data-tools/bytes/nypp_metadata.pdf'
const TERMS_URL = 'https://opendata.cityofnewyork.us/overview/'
const FAQ_URL = 'https://opendata.cityofnewyork.us/faq/'
const TECHNICAL_STANDARDS_URL =
  'https://opendata.cityofnewyork.us/wp-content/uploads/NYC_OpenData_TechnicalStandardsManual.pdf'
const CONVERSION =
  'NYC Open Data supplied the GeoJSON export in WGS84 longitude/latitude; repository processing performs no reprojection.'
const LOCATION_MAPPING =
  'Exact string mapping from the authoritative precinct property; no precinct is remapped, merged, dropped, or invented.'
const CANONICAL_JSON =
  'UTF-8, recursively sorted object keys, compact separators, finite JSON numbers, one trailing newline.'
const GENERATION_TIMESTAMP_POLICY =
  'generatedAtUtc equals the reviewed source retrieval timestamp; the wall clock is never read.'

const TOP_LEVEL_KEYS = [
  'application',
  'compatibility',
  'coordinateReference',
  'coverage',
  'features',
  'generatedAtUtc',
  'limitations',
  'locationKeySemantics',
  'privacy',
  'processing',
  'provenance',
  'responsibleUse',
  'schemaVersion',
  'type',
] as const

export type PrecinctSpatialReferenceErrorCode =
  | 'missing-artifact'
  | 'network'
  | 'stale'
  | 'malformed-json'
  | 'unsupported-version'
  | 'incompatible-identity'
  | 'invalid-provenance'
  | 'invalid-coordinate-reference'
  | 'invalid-contract'
  | 'invalid-geometry'
  | 'duplicate-location-key'
  | 'unstable-feature-order'
  | 'incomplete-coverage'
  | 'location-key-mismatch'
  | 'forecast-incompatible'

export class PrecinctSpatialReferenceError extends Error {
  readonly code: PrecinctSpatialReferenceErrorCode

  constructor(code: PrecinctSpatialReferenceErrorCode, message: string) {
    super(message)
    this.name = 'PrecinctSpatialReferenceError'
    this.code = code
  }
}

interface GeometryStats {
  polygonCount: number
  ringCount: number
  coordinateCount: number
  bounds: [number, number, number, number]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function sortedKeys(value: Record<string, unknown>): string[] {
  return Object.keys(value).sort()
}

function exactObject(
  value: unknown,
  expectedKeys: readonly string[],
  label: string,
  code: PrecinctSpatialReferenceErrorCode = 'invalid-contract',
): Record<string, unknown> {
  if (
    !isRecord(value) ||
    JSON.stringify(sortedKeys(value)) !== JSON.stringify([...expectedKeys].sort())
  ) {
    throw new PrecinctSpatialReferenceError(
      code,
      `${label} does not match the supported schema.`,
    )
  }
  return value
}

function finiteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function nonEmptyText(value: unknown, maximumLength = 2_000): value is string {
  return (
    typeof value === 'string' &&
    value.length > 0 &&
    value === value.trim() &&
    value.length <= maximumLength &&
    ![...value].some((character) => character.charCodeAt(0) < 32)
  )
}

function exactStringArray(value: unknown, expected: readonly string[]): boolean {
  return (
    Array.isArray(value) &&
    value.length === expected.length &&
    value.every((item, index) => item === expected[index])
  )
}

function canonicalEightDecimal(value: number): boolean {
  return Math.round(value * 100_000_000) / 100_000_000 === value
}

function validUtcTimestamp(value: unknown): value is string {
  if (typeof value !== 'string' || !UTC_TIMESTAMP.test(value)) return false
  const parsed = new Date(value)
  return (
    !Number.isNaN(parsed.valueOf()) &&
    parsed.toISOString().replace('.000Z', 'Z') === value
  )
}

function statsAccumulator(): GeometryStats {
  return {
    polygonCount: 0,
    ringCount: 0,
    coordinateCount: 0,
    bounds: [Infinity, Infinity, -Infinity, -Infinity],
  }
}

function validateGeometry(
  value: unknown,
  featureIndex: number,
  stats: GeometryStats,
): asserts value is PrecinctSpatialGeometry {
  const geometry = exactObject(
    value,
    ['coordinates', 'type'],
    `Spatial feature ${featureIndex + 1} geometry`,
    'invalid-geometry',
  )
  if (geometry.type !== 'MultiPolygon' || !Array.isArray(geometry.coordinates)) {
    throw new PrecinctSpatialReferenceError(
      'invalid-geometry',
      `Spatial feature ${featureIndex + 1} must contain a MultiPolygon.`,
    )
  }
  if (geometry.coordinates.length === 0) {
    throw new PrecinctSpatialReferenceError(
      'invalid-geometry',
      `Spatial feature ${featureIndex + 1} has no polygons.`,
    )
  }

  for (const [polygonIndex, polygon] of geometry.coordinates.entries()) {
    if (!Array.isArray(polygon) || polygon.length === 0) {
      throw new PrecinctSpatialReferenceError(
        'invalid-geometry',
        `Spatial feature ${featureIndex + 1} polygon ${polygonIndex + 1} has no rings.`,
      )
    }
    stats.polygonCount += 1

    for (const [ringIndex, ring] of polygon.entries()) {
      if (!Array.isArray(ring) || ring.length < 4) {
        throw new PrecinctSpatialReferenceError(
          'invalid-geometry',
          `Spatial feature ${featureIndex + 1} ring ${ringIndex + 1} is too short.`,
        )
      }
      stats.ringCount += 1
      const distinct = new Set<string>()
      const scaledPositions: Array<[bigint, bigint]> = []

      for (const [positionIndex, position] of ring.entries()) {
        if (
          !Array.isArray(position) ||
          position.length !== 2 ||
          !finiteNumber(position[0]) ||
          !finiteNumber(position[1])
        ) {
          throw new PrecinctSpatialReferenceError(
            'invalid-geometry',
            `Spatial feature ${featureIndex + 1} position ${positionIndex + 1} is invalid.`,
          )
        }
        const [longitude, latitude] = position
        if (
          !canonicalEightDecimal(longitude) ||
          !canonicalEightDecimal(latitude) ||
          longitude < NYC_LONGITUDE_MIN ||
          longitude > NYC_LONGITUDE_MAX ||
          latitude < NYC_LATITUDE_MIN ||
          latitude > NYC_LATITUDE_MAX
        ) {
          throw new PrecinctSpatialReferenceError(
            'invalid-geometry',
            `Spatial feature ${featureIndex + 1} contains an imprecise or implausible coordinate.`,
          )
        }
        stats.coordinateCount += 1
        stats.bounds[0] = Math.min(stats.bounds[0], longitude)
        stats.bounds[1] = Math.min(stats.bounds[1], latitude)
        stats.bounds[2] = Math.max(stats.bounds[2], longitude)
        stats.bounds[3] = Math.max(stats.bounds[3], latitude)
        scaledPositions.push([
          BigInt(Math.round(longitude * 100_000_000)),
          BigInt(Math.round(latitude * 100_000_000)),
        ])
        if (positionIndex < ring.length - 1) {
          distinct.add(`${longitude},${latitude}`)
        }
      }

      const first = ring[0]
      const last = ring[ring.length - 1]
      if (
        first[0] !== last[0] ||
        first[1] !== last[1] ||
        distinct.size < 3
      ) {
        throw new PrecinctSpatialReferenceError(
          'invalid-geometry',
          `Spatial feature ${featureIndex + 1} ring ${ringIndex + 1} is not closed and valid.`,
        )
      }
      const [originLongitude, originLatitude] = scaledPositions[0]
      let doubleArea = 0n
      for (let index = 0; index < scaledPositions.length - 1; index += 1) {
        const [longitude, latitude] = scaledPositions[index]
        const [nextLongitude, nextLatitude] = scaledPositions[index + 1]
        doubleArea +=
          (longitude - originLongitude) * (nextLatitude - originLatitude) -
          (nextLongitude - originLongitude) * (latitude - originLatitude)
      }
      if (doubleArea === 0n) {
        throw new PrecinctSpatialReferenceError(
          'invalid-geometry',
          `Spatial feature ${featureIndex + 1} ring ${ringIndex + 1} has zero area.`,
        )
      }
    }
  }
}

function validateFeatures(
  value: unknown,
): { features: PrecinctSpatialFeature[]; stats: GeometryStats } {
  if (!Array.isArray(value)) {
    throw new PrecinctSpatialReferenceError(
      'invalid-contract',
      'Spatial features must be an array.',
    )
  }
  if (value.length !== EXPECTED_PRECINCT_COUNT) {
    throw new PrecinctSpatialReferenceError(
      'incomplete-coverage',
      `Spatial reference must contain exactly ${EXPECTED_PRECINCT_COUNT} precincts.`,
    )
  }

  const stats = statsAccumulator()
  const locationKeys = new Set<string>()
  const precinctLabels = new Set<string>()
  let previousLocationKey: string | null = null

  value.forEach((candidate, featureIndex) => {
    const feature = exactObject(
      candidate,
      ['geometry', 'properties', 'type'],
      `Spatial feature ${featureIndex + 1}`,
    )
    const properties = exactObject(
      feature.properties,
      ['locationKey', 'precinctLabel'],
      `Spatial feature ${featureIndex + 1} properties`,
    )
    if (
      feature.type !== 'Feature' ||
      typeof properties.precinctLabel !== 'string' ||
      !PRECINCT_LABEL.test(properties.precinctLabel) ||
      properties.locationKey !== `nypd-precinct:${properties.precinctLabel}`
    ) {
      throw new PrecinctSpatialReferenceError(
        'invalid-contract',
        `Spatial feature ${featureIndex + 1} has an invalid precinct identity.`,
      )
    }
    const locationKey = properties.locationKey
    if (locationKeys.has(locationKey) || precinctLabels.has(properties.precinctLabel)) {
      throw new PrecinctSpatialReferenceError(
        'duplicate-location-key',
        `Spatial feature ${featureIndex + 1} duplicates a precinct identity.`,
      )
    }
    if (previousLocationKey !== null && locationKey <= previousLocationKey) {
      throw new PrecinctSpatialReferenceError(
        'unstable-feature-order',
        'Spatial features are not in strict lexical location-key order.',
      )
    }
    locationKeys.add(locationKey)
    precinctLabels.add(properties.precinctLabel)
    previousLocationKey = locationKey
    validateGeometry(feature.geometry, featureIndex, stats)
  })

  return { features: value as PrecinctSpatialFeature[], stats }
}

function validateMetadataSections(
  contract: Record<string, unknown>,
  stats: GeometryStats,
): void {
  if (
    stats.polygonCount <= 0 ||
    stats.ringCount <= 0 ||
    stats.coordinateCount <= 0 ||
    stats.bounds.some((value) => !Number.isFinite(value))
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-geometry',
      'Spatial geometry summary is empty or invalid.',
    )
  }

  const provenance = exactObject(
    contract.provenance,
    ['dataset', 'publicUse', 'provenanceRecord', 'retrieval', 'sourceSchema'],
    'Spatial provenance',
    'invalid-provenance',
  )
  const dataset = exactObject(
    provenance.dataset,
    [
      'dataDate',
      'datasetId',
      'datasetPageUrl',
      'edition',
      'metadataApiUrl',
      'metadataPdfUrl',
      'publisher',
      'publisherPageUrl',
      'title',
      'updateFrequency',
    ],
    'Spatial provenance dataset',
    'invalid-provenance',
  )
  if (
    dataset.title !== 'Police Precincts' ||
    dataset.datasetId !== 'y76i-bdw7' ||
    dataset.edition !== '26B' ||
    dataset.publisher !== 'New York City Department of City Planning (DCP)' ||
    dataset.updateFrequency !== 'Quarterly' ||
    dataset.dataDate !== '2026-05' ||
    dataset.datasetPageUrl !== DATASET_PAGE_URL ||
    dataset.publisherPageUrl !== PUBLISHER_PAGE_URL ||
    dataset.metadataApiUrl !== METADATA_API_URL ||
    dataset.metadataPdfUrl !== METADATA_PDF_URL
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-provenance',
      'Spatial dataset identity, release, publisher, or official URLs are invalid.',
    )
  }

  const retrieval = exactObject(
    provenance.retrieval,
    [
      'byteSize',
      'mediaType',
      'originalFilename',
      'portalRowsUpdatedAtUtc',
      'repeatDownloadByteIdentical',
      'retrievalUrl',
      'retrievedAtUtc',
      'sha256',
      'vendoredFilename',
    ],
    'Spatial provenance retrieval',
    'invalid-provenance',
  )
  if (
    retrieval.retrievalUrl !== RETRIEVAL_URL ||
    !validUtcTimestamp(retrieval.retrievedAtUtc) ||
    !validUtcTimestamp(retrieval.portalRowsUpdatedAtUtc) ||
    retrieval.retrievedAtUtc !== contract.generatedAtUtc ||
    Date.parse(retrieval.portalRowsUpdatedAtUtc) > Date.parse(retrieval.retrievedAtUtc) ||
    retrieval.originalFilename !== 'Police Precincts.geojson' ||
    retrieval.vendoredFilename !== 'police_precincts_y76i-bdw7_26b.geojson' ||
    retrieval.mediaType !== 'application/vnd.geo+json' ||
    retrieval.byteSize !== SOURCE_BYTE_SIZE ||
    retrieval.sha256 !== SOURCE_SHA256 ||
    !SHA256.test(String(retrieval.sha256)) ||
    retrieval.repeatDownloadByteIdentical !== true
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-provenance',
      'Spatial retrieval metadata or source checksum is invalid.',
    )
  }

  const sourceSchema = exactObject(
    provenance.sourceSchema,
    [
      'conversion',
      'exportAxisOrder',
      'exportCoordinateReference',
      'featureCount',
      'geometryType',
      'nativeCoordinateReference',
      'nativeCoordinateReferenceName',
      'propertyFields',
      'rootType',
    ],
    'Spatial provenance source schema',
    'invalid-provenance',
  )
  if (
    sourceSchema.rootType !== 'FeatureCollection' ||
    sourceSchema.featureCount !== EXPECTED_PRECINCT_COUNT ||
    sourceSchema.geometryType !== 'MultiPolygon' ||
    !exactStringArray(sourceSchema.propertyFields, [
      'precinct',
      'shape_area',
      'shape_leng',
    ]) ||
    sourceSchema.nativeCoordinateReference !== 'EPSG:2263' ||
    sourceSchema.nativeCoordinateReferenceName !==
      'NAD83 / New York Long Island (US survey feet)' ||
    sourceSchema.exportCoordinateReference !== 'OGC:CRS84' ||
    sourceSchema.exportAxisOrder !== 'longitude, latitude' ||
    sourceSchema.conversion !== CONVERSION
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-provenance',
      'Spatial source schema or source coordinate-reference metadata is invalid.',
    )
  }

  const publicUse = exactObject(
    provenance.publicUse,
    [
      'assessment',
      'faqUrl',
      'namedLicense',
      'summary',
      'technicalStandardsUrl',
      'termsUrl',
    ],
    'Spatial provenance public-use assessment',
    'invalid-provenance',
  )
  const publicUseSummary =
    typeof publicUse.summary === 'string' ? publicUse.summary.toLowerCase() : ''
  if (
    publicUse.namedLicense !== null ||
    publicUse.assessment !== 'license-compatible public data' ||
    publicUse.termsUrl !== TERMS_URL ||
    publicUse.faqUrl !== FAQ_URL ||
    publicUse.technicalStandardsUrl !== TECHNICAL_STANDARDS_URL ||
    !nonEmptyText(publicUse.summary) ||
    !publicUseSummary.includes('no use restrictions') ||
    !publicUseSummary.includes('freely available')
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-provenance',
      'Spatial public-use assessment is absent or unsupported.',
    )
  }

  const provenanceRecord = exactObject(
    provenance.provenanceRecord,
    ['byteSize', 'filename', 'sha256'],
    'Spatial provenance record',
    'invalid-provenance',
  )
  if (
    provenanceRecord.filename !==
      'police_precincts_y76i-bdw7_26b.provenance.json' ||
    provenanceRecord.byteSize !== PROVENANCE_BYTE_SIZE ||
    provenanceRecord.sha256 !== PROVENANCE_SHA256 ||
    !SHA256.test(String(provenanceRecord.sha256))
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-provenance',
      'Spatial provenance-record checksum is invalid.',
    )
  }

  const coordinateReference = exactObject(
    contract.coordinateReference,
    [
      'bounds',
      'conversion',
      'officialGeoJsonExport',
      'publishedCoordinateOrder',
      'repositoryReprojectionApplied',
      'sourceNative',
    ],
    'Spatial coordinate reference',
    'invalid-coordinate-reference',
  )
  const sourceNative = exactObject(
    coordinateReference.sourceNative,
    ['identifier', 'name'],
    'Spatial native coordinate reference',
    'invalid-coordinate-reference',
  )
  const officialExport = exactObject(
    coordinateReference.officialGeoJsonExport,
    ['axisOrder', 'identifier'],
    'Spatial export coordinate reference',
    'invalid-coordinate-reference',
  )
  const bounds = exactObject(
    coordinateReference.bounds,
    ['maxLatitude', 'maxLongitude', 'minLatitude', 'minLongitude'],
    'Spatial coordinate bounds',
    'invalid-coordinate-reference',
  )
  const declaredBounds = [
    bounds.minLongitude,
    bounds.minLatitude,
    bounds.maxLongitude,
    bounds.maxLatitude,
  ]
  if (
    sourceNative.identifier !== 'EPSG:2263' ||
    sourceNative.name !== 'NAD83 / New York Long Island (US survey feet)' ||
    officialExport.identifier !== 'OGC:CRS84' ||
    officialExport.axisOrder !== 'longitude, latitude' ||
    coordinateReference.publishedCoordinateOrder !== 'longitude, latitude' ||
    coordinateReference.repositoryReprojectionApplied !== false ||
    coordinateReference.conversion !== CONVERSION ||
    !declaredBounds.every(
      (value) => finiteNumber(value) && canonicalEightDecimal(value),
    ) ||
    declaredBounds.some((value, index) => value !== stats.bounds[index])
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-coordinate-reference',
      'Spatial coordinate-reference identity, conversion, or bounds are invalid.',
    )
  }

  const location = exactObject(
    contract.locationKeySemantics,
    [
      'mapping',
      'publishedJoinField',
      'publishedLabelField',
      'scheme',
      'sourceIdentifierField',
    ],
    'Spatial location-key semantics',
  )
  if (
    location.scheme !== LOCATION_KEY_SCHEME ||
    location.sourceIdentifierField !== 'precinct' ||
    location.publishedLabelField !== 'properties.precinctLabel' ||
    location.publishedJoinField !== 'properties.locationKey' ||
    location.mapping !== LOCATION_MAPPING
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-contract',
      'Spatial location-key semantics are incompatible.',
    )
  }

  const compatibility = exactObject(
    contract.compatibility,
    [
      'forecastLocationKeyCount',
      'forecastMapSchemaVersion',
      'forecastMapView',
      'locationKeyScheme',
      'reconciliation',
    ],
    'Spatial Forecast compatibility',
  )
  if (
    compatibility.forecastMapSchemaVersion !== '1.0.0' ||
    compatibility.forecastMapView !== 'Forecast Map Data Contract' ||
    compatibility.locationKeyScheme !== LOCATION_KEY_SCHEME ||
    compatibility.forecastLocationKeyCount !== EXPECTED_PRECINCT_COUNT ||
    compatibility.reconciliation !== 'exact'
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-contract',
      'Spatial Forecast compatibility metadata is invalid.',
    )
  }

  const processing = exactObject(
    contract.processing,
    [
      'canonicalJson',
      'coordinateRoundingDigits',
      'featureOrdering',
      'generationTimestampPolicy',
      'publishedPositionCount',
      'simplificationAlgorithm',
      'simplificationApplied',
      'simplificationTolerance',
      'sourcePositionCount',
      'vertexRemovalApplied',
    ],
    'Spatial processing metadata',
  )
  if (
    processing.coordinateRoundingDigits !== 8 ||
    processing.simplificationApplied !== false ||
    processing.simplificationAlgorithm !== null ||
    processing.simplificationTolerance !== null ||
    processing.vertexRemovalApplied !== false ||
    processing.sourcePositionCount !== stats.coordinateCount ||
    processing.publishedPositionCount !== stats.coordinateCount ||
    processing.featureOrdering !== 'Lexical ascending locationKey.' ||
    processing.canonicalJson !== CANONICAL_JSON ||
    processing.generationTimestampPolicy !== GENERATION_TIMESTAMP_POLICY
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-contract',
      'Spatial processing, precision, or simplification metadata is invalid.',
    )
  }

  const coverage = exactObject(
    contract.coverage,
    [
      'complete',
      'duplicateLocationKeyCount',
      'expectedFeatureCount',
      'featureCount',
      'forecastLocationKeyCount',
      'missingForecastLocationKeys',
      'polygonCount',
      'positionCount',
      'ringCount',
      'unexpectedSpatialLocationKeys',
    ],
    'Spatial coverage',
  )
  if (
    coverage.expectedFeatureCount !== EXPECTED_PRECINCT_COUNT ||
    coverage.featureCount !== EXPECTED_PRECINCT_COUNT ||
    coverage.forecastLocationKeyCount !== EXPECTED_PRECINCT_COUNT ||
    coverage.polygonCount !== stats.polygonCount ||
    coverage.ringCount !== stats.ringCount ||
    coverage.positionCount !== stats.coordinateCount ||
    !exactStringArray(coverage.missingForecastLocationKeys, []) ||
    !exactStringArray(coverage.unexpectedSpatialLocationKeys, []) ||
    coverage.duplicateLocationKeyCount !== 0 ||
    coverage.complete !== true
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-contract',
      'Spatial feature and geometry coverage does not reconcile.',
    )
  }

  const privacy = exactObject(
    contract.privacy,
    [
      'administrativeBoundaryGeometryOnly',
      'aggregatePublicVisualizationSuitable',
      'complaintOrEventRecordsIncluded',
      'demographicAttributesIncluded',
      'eventLevelCoordinatesIncluded',
      'inferredCentroidsIncluded',
      'personOrAddressRecordsIncluded',
      'sourceShapeMetricsIncluded',
    ],
    'Spatial privacy flags',
  )
  if (
    privacy.administrativeBoundaryGeometryOnly !== true ||
    privacy.aggregatePublicVisualizationSuitable !== true ||
    privacy.complaintOrEventRecordsIncluded !== false ||
    privacy.personOrAddressRecordsIncluded !== false ||
    privacy.demographicAttributesIncluded !== false ||
    privacy.eventLevelCoordinatesIncluded !== false ||
    privacy.inferredCentroidsIncluded !== false ||
    privacy.sourceShapeMetricsIncluded !== false
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-contract',
      'Spatial privacy flags are absent or unsafe.',
    )
  }

  const responsibleUse = exactObject(
    contract.responsibleUse,
    [
      'aggregatePrecinctVisualizationOnly',
      'enforcementRecommendations',
      'patrolRecommendations',
      'personLevelScoring',
      'riskOrDangerClassification',
      'specificIncidentLocationPrediction',
    ],
    'Spatial responsible-use flags',
  )
  if (
    responsibleUse.aggregatePrecinctVisualizationOnly !== true ||
    responsibleUse.specificIncidentLocationPrediction !== false ||
    responsibleUse.personLevelScoring !== false ||
    responsibleUse.patrolRecommendations !== false ||
    responsibleUse.enforcementRecommendations !== false ||
    responsibleUse.riskOrDangerClassification !== false
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-contract',
      'Spatial responsible-use flags are absent or unsafe.',
    )
  }
}

export function decodePrecinctSpatialReference(
  value: unknown,
): PrecinctSpatialReferenceContract {
  const contract = exactObject(value, TOP_LEVEL_KEYS, 'Spatial reference')
  if (contract.schemaVersion !== SCHEMA_VERSION) {
    throw new PrecinctSpatialReferenceError(
      'unsupported-version',
      'Spatial reference schema version is unsupported.',
    )
  }
  if (contract.type !== 'FeatureCollection' || !validUtcTimestamp(contract.generatedAtUtc)) {
    throw new PrecinctSpatialReferenceError(
      'invalid-contract',
      'Spatial reference type or deterministic timestamp is invalid.',
    )
  }
  const application = exactObject(
    contract.application,
    ['name', 'phase', 'view'],
    'Spatial reference application',
    'incompatible-identity',
  )
  if (
    application.name !== 'NYC Crime Intelligence' ||
    application.phase !== 'Phase 7C.3' ||
    application.view !== 'Precinct Spatial Reference'
  ) {
    throw new PrecinctSpatialReferenceError(
      'incompatible-identity',
      'Spatial reference application identity is incompatible.',
    )
  }
  if (
    !Array.isArray(contract.limitations) ||
    contract.limitations.length < 4 ||
    !contract.limitations.every((item) => nonEmptyText(item)) ||
    new Set(contract.limitations).size !== contract.limitations.length ||
    !contract.limitations.includes(SPATIAL_FRESHNESS_LIMITATION)
  ) {
    throw new PrecinctSpatialReferenceError(
      'invalid-contract',
      'Spatial reference limitations are invalid.',
    )
  }

  const { stats } = validateFeatures(contract.features)
  validateMetadataSections(contract, stats)
  return value as PrecinctSpatialReferenceContract
}

export function assertPrecinctSpatialReferenceFresh(
  contract: PrecinctSpatialReferenceContract,
  now: Date = new Date(),
): PrecinctSpatialReferenceContract {
  const portalUpdatedAt = Date.parse(
    contract.provenance.retrieval.portalRowsUpdatedAtUtc,
  )
  const currentTime = now.getTime()
  if (!Number.isFinite(portalUpdatedAt) || !Number.isFinite(currentTime)) {
    throw new PrecinctSpatialReferenceError(
      'invalid-provenance',
      'Spatial reference freshness metadata is invalid.',
    )
  }
  const staleAfter =
    portalUpdatedAt + SPATIAL_FRESHNESS_DAYS * 24 * 60 * 60 * 1_000
  if (currentTime > staleAfter) {
    throw new PrecinctSpatialReferenceError(
      'stale',
      'The reviewed official precinct boundary edition is past its refresh window.',
    )
  }
  return contract
}

function spatialLocationKeyScheme(contract: PrecinctSpatialReferenceContract): unknown {
  return contract.locationKeySemantics.scheme
}

export function reconcilePrecinctSpatialReference(
  spatial: PrecinctSpatialReferenceContract,
  forecast: ForecastMapContract,
): PrecinctSpatialReferenceContract {
  if (
    forecast.schemaVersion !== '1.0.0' ||
    forecast.application.name !== 'NYC Crime Intelligence' ||
    forecast.application.phase !== 'Phase 7C.1' ||
    forecast.application.view !== 'Forecast Map Data Contract' ||
    forecast.forecast.status !== 'available' ||
    forecast.forecast.isEmpty ||
    forecast.locationKeySemantics.scheme !== LOCATION_KEY_SCHEME ||
    spatialLocationKeyScheme(spatial) !== LOCATION_KEY_SCHEME
  ) {
    throw new PrecinctSpatialReferenceError(
      'forecast-incompatible',
      'Forecast and spatial-reference identities or location-key schemes are incompatible.',
    )
  }

  const expectedKeys = forecast.dimensions.precincts.map(
    (label) => `nypd-precinct:${label}`,
  )
  if (
    expectedKeys.length !== EXPECTED_PRECINCT_COUNT ||
    new Set(expectedKeys).size !== expectedKeys.length ||
    expectedKeys.some(
      (key, index) =>
        !PRECINCT_LABEL.test(forecast.dimensions.precincts[index]) ||
        (index > 0 && key <= expectedKeys[index - 1]),
    )
  ) {
    throw new PrecinctSpatialReferenceError(
      'forecast-incompatible',
      'Forecast precinct dimensions are not a supported stable key universe.',
    )
  }

  const rowKeys = new Set(forecast.forecast.rows.map((row) => row[9]))
  if (
    rowKeys.size !== expectedKeys.length ||
    expectedKeys.some((key) => !rowKeys.has(key))
  ) {
    throw new PrecinctSpatialReferenceError(
      'forecast-incompatible',
      'Forecast rows do not reconcile to their declared precinct dimensions.',
    )
  }

  const actualKeys = new Set(
    spatial.features.map((feature) => feature.properties.locationKey),
  )
  const missing = expectedKeys.filter((key) => !actualKeys.has(key))
  const unexpected = [...actualKeys].filter((key) => !rowKeys.has(key))
  if (missing.length > 0 && unexpected.length === 0) {
    throw new PrecinctSpatialReferenceError(
      'incomplete-coverage',
      `Spatial reference is missing ${missing.length} Forecast precinct key(s).`,
    )
  }
  if (missing.length > 0 || unexpected.length > 0) {
    throw new PrecinctSpatialReferenceError(
      'location-key-mismatch',
      'Spatial reference and Forecast precinct keys do not match exactly.',
    )
  }
  return spatial
}

export const loadPrecinctSpatialReference: PrecinctSpatialReferenceLoader = async () => {
  let response: Response
  try {
    response = await fetch(PATH, { cache: 'no-cache' })
  } catch {
    throw new PrecinctSpatialReferenceError(
      'network',
      'Precinct spatial-reference data could not be loaded.',
    )
  }
  if (!response.ok) {
    throw new PrecinctSpatialReferenceError(
      response.status === 404 ? 'missing-artifact' : 'network',
      response.status === 404
        ? 'Precinct spatial-reference artifact is missing.'
        : 'Precinct spatial-reference data could not be loaded.',
    )
  }

  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new PrecinctSpatialReferenceError(
      'malformed-json',
      'Precinct spatial-reference response is not valid JSON.',
    )
  }
  return assertPrecinctSpatialReferenceFresh(
    decodePrecinctSpatialReference(value),
  )
}

export {
  EXPECTED_PRECINCT_COUNT,
  LOCATION_KEY_SCHEME,
  SPATIAL_FRESHNESS_DAYS,
}

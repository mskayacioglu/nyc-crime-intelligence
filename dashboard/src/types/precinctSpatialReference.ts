export type PrecinctSpatialPosition = [longitude: number, latitude: number]
export type PrecinctSpatialLinearRing = PrecinctSpatialPosition[]
export type PrecinctSpatialPolygonCoordinates = PrecinctSpatialLinearRing[]
export type PrecinctSpatialMultiPolygonCoordinates =
  PrecinctSpatialPolygonCoordinates[]

export interface PrecinctSpatialGeometry {
  type: 'MultiPolygon'
  coordinates: PrecinctSpatialMultiPolygonCoordinates
}

export interface PrecinctSpatialFeature {
  type: 'Feature'
  properties: {
    precinctLabel: string
    locationKey: string
  }
  geometry: PrecinctSpatialGeometry
}

export interface PrecinctSpatialDatasetProvenance {
  title: 'Police Precincts'
  datasetId: 'y76i-bdw7'
  edition: '26B'
  publisher: 'New York City Department of City Planning (DCP)'
  updateFrequency: 'Quarterly'
  dataDate: '2026-05'
  datasetPageUrl: string
  publisherPageUrl: string
  metadataApiUrl: string
  metadataPdfUrl: string
}

export interface PrecinctSpatialRetrievalProvenance {
  retrievalUrl: string
  retrievedAtUtc: string
  portalRowsUpdatedAtUtc: string
  originalFilename: 'Police Precincts.geojson'
  vendoredFilename: 'police_precincts_y76i-bdw7_26b.geojson'
  mediaType: 'application/vnd.geo+json'
  byteSize: number
  sha256: string
  repeatDownloadByteIdentical: true
}

export interface PrecinctSpatialSourceSchema {
  rootType: 'FeatureCollection'
  featureCount: 78
  geometryType: 'MultiPolygon'
  propertyFields: ['precinct', 'shape_area', 'shape_leng']
  nativeCoordinateReference: 'EPSG:2263'
  nativeCoordinateReferenceName: 'NAD83 / New York Long Island (US survey feet)'
  exportCoordinateReference: 'OGC:CRS84'
  exportAxisOrder: 'longitude, latitude'
  conversion: string
}

export interface PrecinctSpatialPublicUse {
  namedLicense: null
  assessment: 'license-compatible public data'
  termsUrl: string
  faqUrl: string
  technicalStandardsUrl: string
  summary: string
}

export interface PrecinctSpatialProvenance {
  dataset: PrecinctSpatialDatasetProvenance
  retrieval: PrecinctSpatialRetrievalProvenance
  sourceSchema: PrecinctSpatialSourceSchema
  publicUse: PrecinctSpatialPublicUse
  provenanceRecord: {
    filename: 'police_precincts_y76i-bdw7_26b.provenance.json'
    byteSize: number
    sha256: string
  }
}

export interface PrecinctSpatialCoordinateReference {
  sourceNative: {
    identifier: 'EPSG:2263'
    name: 'NAD83 / New York Long Island (US survey feet)'
  }
  officialGeoJsonExport: {
    identifier: 'OGC:CRS84'
    axisOrder: 'longitude, latitude'
  }
  publishedCoordinateOrder: 'longitude, latitude'
  repositoryReprojectionApplied: false
  conversion: string
  bounds: {
    minLongitude: number
    minLatitude: number
    maxLongitude: number
    maxLatitude: number
  }
}

export interface PrecinctSpatialCoverage {
  expectedFeatureCount: 78
  featureCount: 78
  forecastLocationKeyCount: 78
  polygonCount: number
  ringCount: number
  positionCount: number
  missingForecastLocationKeys: []
  unexpectedSpatialLocationKeys: []
  duplicateLocationKeyCount: 0
  complete: true
}

export interface PrecinctSpatialReferenceContract {
  type: 'FeatureCollection'
  schemaVersion: '1.0.0'
  generatedAtUtc: string
  application: {
    name: 'NYC Crime Intelligence'
    phase: 'Phase 7C.3'
    view: 'Precinct Spatial Reference'
  }
  provenance: PrecinctSpatialProvenance
  coordinateReference: PrecinctSpatialCoordinateReference
  locationKeySemantics: {
    scheme: 'nypd-precinct:<source precinct label>'
    sourceIdentifierField: 'precinct'
    publishedLabelField: 'properties.precinctLabel'
    publishedJoinField: 'properties.locationKey'
    mapping: string
  }
  compatibility: {
    forecastMapSchemaVersion: '1.0.0'
    forecastMapView: 'Forecast Map Data Contract'
    locationKeyScheme: 'nypd-precinct:<source precinct label>'
    forecastLocationKeyCount: 78
    reconciliation: 'exact'
  }
  processing: {
    coordinateRoundingDigits: 8
    simplificationApplied: false
    simplificationAlgorithm: null
    simplificationTolerance: null
    vertexRemovalApplied: false
    sourcePositionCount: number
    publishedPositionCount: number
    featureOrdering: 'Lexical ascending locationKey.'
    canonicalJson: string
    generationTimestampPolicy: string
  }
  coverage: PrecinctSpatialCoverage
  privacy: {
    administrativeBoundaryGeometryOnly: true
    aggregatePublicVisualizationSuitable: true
    complaintOrEventRecordsIncluded: false
    personOrAddressRecordsIncluded: false
    demographicAttributesIncluded: false
    eventLevelCoordinatesIncluded: false
    inferredCentroidsIncluded: false
    sourceShapeMetricsIncluded: false
  }
  responsibleUse: {
    aggregatePrecinctVisualizationOnly: true
    specificIncidentLocationPrediction: false
    personLevelScoring: false
    patrolRecommendations: false
    enforcementRecommendations: false
    riskOrDangerClassification: false
  }
  limitations: string[]
  features: PrecinctSpatialFeature[]
}

export type PrecinctSpatialReferenceLoader =
  () => Promise<PrecinctSpatialReferenceContract>

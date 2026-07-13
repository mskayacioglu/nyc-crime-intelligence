import { act, render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PrecinctForecast } from '../types/forecastMap'
import type { PrecinctSpatialReferenceContract } from '../types/precinctSpatialReference'
import { PrecinctForecastMap } from './PrecinctForecastMap'

const leaflet = vi.hoisted(() => {
  type EventHandler = () => void
  const tileHandlers = new Map<string, EventHandler>()
  const geoJsonLayers: Array<{
    events: Map<string, EventHandler>
    bindTooltip: ReturnType<typeof vi.fn>
    setStyle: ReturnType<typeof vi.fn>
    bringToFront: ReturnType<typeof vi.fn>
  }> = []
  const mapInstance = {
    setView: vi.fn(),
    fitBounds: vi.fn(),
    invalidateSize: vi.fn(),
    remove: vi.fn(),
  }
  mapInstance.setView.mockReturnValue(mapInstance)

  const tileLayer = {
    on: vi.fn((event: string, handler: EventHandler) => {
      tileHandlers.set(event, handler)
      return tileLayer
    }),
    addTo: vi.fn(() => tileLayer),
    off: vi.fn(),
  }
  const layerGroup = {
    addTo: vi.fn(() => layerGroup),
    clearLayers: vi.fn(),
  }
  const map = vi.fn(() => mapInstance)
  const makeTileLayer = vi.fn(() => tileLayer)
  const makeLayerGroup = vi.fn(() => layerGroup)
  const geoJSON = vi.fn(() => {
    const events = new Map<string, EventHandler>()
    const layer = {
      events,
      bindTooltip: vi.fn(),
      on: vi.fn((event: string, handler: EventHandler) => {
        events.set(event, handler)
        return layer
      }),
      addTo: vi.fn(() => layer),
      getBounds: vi.fn(() => ({ mockBounds: true })),
      setStyle: vi.fn(),
      bringToFront: vi.fn(),
    }
    geoJsonLayers.push(layer)
    return layer
  })
  const latLngBounds = vi.fn(() => {
    let valid = false
    return {
      extend: vi.fn(() => {
        valid = true
      }),
      isValid: vi.fn(() => valid),
    }
  })
  const zoomControl = {
    addTo: vi.fn(() => zoomControl),
    getContainer: vi.fn(() => {
      const container = document.createElement('div')
      const zoomIn = document.createElement('a')
      const zoomOut = document.createElement('a')
      zoomIn.className = 'leaflet-control-zoom-in'
      zoomOut.className = 'leaflet-control-zoom-out'
      container.append(zoomIn, zoomOut)
      return container
    }),
  }
  const zoom = vi.fn(() => zoomControl)

  return {
    geoJSON,
    geoJsonLayers,
    latLngBounds,
    layerGroup,
    makeLayerGroup,
    makeTileLayer,
    map,
    mapInstance,
    tileHandlers,
    tileLayer,
    zoom,
    zoomControl,
    reset() {
      vi.clearAllMocks()
      geoJsonLayers.length = 0
      tileHandlers.clear()
      mapInstance.setView.mockReturnValue(mapInstance)
      tileLayer.on.mockImplementation((event: string, handler: EventHandler) => {
        tileHandlers.set(event, handler)
        return tileLayer
      })
      tileLayer.addTo.mockReturnValue(tileLayer)
      layerGroup.addTo.mockReturnValue(layerGroup)
      map.mockReturnValue(mapInstance)
      makeTileLayer.mockReturnValue(tileLayer)
      makeLayerGroup.mockReturnValue(layerGroup)
      zoom.mockReturnValue(zoomControl)
      zoomControl.addTo.mockReturnValue(zoomControl)
    },
  }
})

vi.mock('leaflet', () => ({
  default: {
    map: leaflet.map,
    tileLayer: leaflet.makeTileLayer,
    control: { zoom: leaflet.zoom },
    layerGroup: leaflet.makeLayerGroup,
    geoJSON: leaflet.geoJSON,
    latLngBounds: leaflet.latLngBounds,
  },
}))

function row(
  precinct: string,
  overrides: Partial<PrecinctForecast> = {},
): PrecinctForecast {
  return {
    id: `nypd-precinct:${precinct}`,
    borough: 'MANHATTAN',
    precinct,
    forecastWeek: '2026-01-05',
    predictedCount: 10,
    historicalBaseline: 8,
    expectedChangeCount: 2,
    expectedChangePct: 25,
    baselineRows: 4,
    totalRows: 4,
    direction: 'above',
    ...overrides,
  }
}

function spatial(...precincts: string[]): PrecinctSpatialReferenceContract {
  return {
    type: 'FeatureCollection',
    schemaVersion: '1.0.0',
    generatedAtUtc: '2025-12-31T00:00:00Z',
    application: {
      name: 'NYC Crime Intelligence',
      phase: 'Phase 7C.3',
      view: 'Precinct Spatial Reference',
    },
    provenance: {},
    coordinateReference: {},
    locationKeySemantics: {},
    compatibility: {},
    processing: {},
    coverage: {},
    privacy: {},
    responsibleUse: {},
    limitations: [],
    features: precincts.map((precinct, index) => ({
      type: 'Feature',
      properties: {
        precinctLabel: precinct,
        locationKey: `nypd-precinct:${precinct}`,
      },
      geometry: {
        type: 'MultiPolygon',
        coordinates: [
          [
            [
              [-74 + index * 0.01, 40.7],
              [-73.99 + index * 0.01, 40.7],
              [-73.99 + index * 0.01, 40.71],
              [-74 + index * 0.01, 40.7],
            ],
          ],
        ],
      },
    })),
  } as unknown as PrecinctSpatialReferenceContract
}

describe('PrecinctForecastMap Leaflet lifecycle', () => {
  beforeEach(() => leaflet.reset())

  it('selects polygons, detects tile failure, and only refits for a changed key set', () => {
    const onSelect = vi.fn()
    const onTileStatus = vi.fn()
    const rows = [row('1'), row('2')]
    const contract = spatial('1', '2')
    const { container, rerender } = render(
      <PrecinctForecastMap
        spatial={contract}
        rows={rows}
        mode="forecast"
        selectedId={null}
        onSelect={onSelect}
        descriptionId="forecast-map-description"
        onTileStatus={onTileStatus}
      />,
    )

    expect(container.querySelector('[role="region"]')).toHaveAttribute(
      'data-feature-count',
      '2',
    )
    expect(leaflet.geoJSON).toHaveBeenCalledTimes(2)
    expect(leaflet.mapInstance.fitBounds).toHaveBeenCalledTimes(1)
    expect(onTileStatus).toHaveBeenCalledWith('loading')

    act(() => leaflet.geoJsonLayers[1].events.get('click')?.())
    expect(onSelect).toHaveBeenCalledWith('nypd-precinct:2')

    rerender(
      <PrecinctForecastMap
        spatial={contract}
        rows={rows}
        mode="forecast"
        selectedId="nypd-precinct:2"
        onSelect={onSelect}
        descriptionId="forecast-map-description"
        onTileStatus={onTileStatus}
      />,
    )
    expect(leaflet.geoJSON).toHaveBeenCalledTimes(2)
    expect(leaflet.mapInstance.fitBounds).toHaveBeenCalledTimes(1)
    expect(leaflet.geoJsonLayers[1].setStyle).toHaveBeenCalled()
    expect(leaflet.geoJsonLayers[1].bringToFront).toHaveBeenCalled()

    act(() => leaflet.tileHandlers.get('tileerror')?.())
    expect(onTileStatus).toHaveBeenLastCalledWith('error')
    expect(leaflet.geoJsonLayers).toHaveLength(2)

    rerender(
      <PrecinctForecastMap
        spatial={contract}
        rows={[rows[0]]}
        mode="forecast"
        selectedId={null}
        onSelect={onSelect}
        descriptionId="forecast-map-description"
        onTileStatus={onTileStatus}
      />,
    )
    expect(leaflet.mapInstance.fitBounds).toHaveBeenCalledTimes(2)

    rerender(
      <PrecinctForecastMap
        spatial={contract}
        rows={[]}
        mode="forecast"
        selectedId={null}
        onSelect={onSelect}
        descriptionId="forecast-map-description"
        onTileStatus={onTileStatus}
      />,
    )
    expect(leaflet.mapInstance.setView).toHaveBeenCalledTimes(2)
  })

  it('gives partial and missing baselines different non-color path semantics', () => {
    render(
      <PrecinctForecastMap
        spatial={spatial('1', '2')}
        rows={[
          row('1', {
            historicalBaseline: null,
            expectedChangeCount: null,
            expectedChangePct: null,
            baselineRows: 2,
            direction: 'unavailable',
          }),
          row('2', {
            historicalBaseline: null,
            expectedChangeCount: null,
            expectedChangePct: null,
            baselineRows: 0,
            direction: 'unavailable',
          }),
        ]}
        mode="change"
        selectedId={null}
        onSelect={() => undefined}
        descriptionId="change-map-description"
      />,
    )

    const geoJsonCalls = leaflet.geoJSON.mock.calls as unknown as Array<
      [unknown, { style: Record<string, unknown> }]
    >
    const partialStyle = geoJsonCalls[0]![1].style
    const missingStyle = geoJsonCalls[1]![1].style
    expect(partialStyle).toMatchObject({ dashArray: '8 5', fillOpacity: 0.2 })
    expect(missingStyle).toMatchObject({ dashArray: '2 5', fillOpacity: 0.1 })
  })
})

import L from 'leaflet'
import { useEffect, useMemo, useRef } from 'react'
import 'leaflet/dist/leaflet.css'
import type { PrecinctForecast, PredictiveMode } from '../types/forecastMap'
import type { PrecinctSpatialReferenceContract } from '../types/precinctSpatialReference'
import {
  baselineCoverage,
  createExpectedChangeScale,
  createForecastVolumeScale,
  expectedChangeDirection,
  expectedChangeIntensity,
  forecastVolumeLevel,
  matchPrecinctForecastFeatures,
  precinctMapTooltipText,
} from './precinctForecastScale'
import type {
  BaselineCoverage,
  ExpectedChangeScale,
  ForecastVolumeLevel,
  ForecastVolumeScale,
} from './precinctForecastScale'

const NYC_CENTER: L.LatLngExpression = [40.7128, -74.006]
const DEFAULT_ZOOM = 10

export type PredictiveTileStatus = 'loading' | 'available' | 'error'

export interface PrecinctForecastMapProps {
  spatial: PrecinctSpatialReferenceContract
  rows: PrecinctForecast[]
  mode: PredictiveMode
  selectedId: string | null
  onSelect: (id: string) => void
  descriptionId: string
  onTileStatus?: (status: PredictiveTileStatus) => void
}

interface RenderedPrecinct {
  layer: L.GeoJSON
  baseStyle: L.PathOptions
}

function cssToken(element: HTMLElement, name: string, fallback: string): string {
  const value = getComputedStyle(element).getPropertyValue(name).trim()
  return value || fallback
}

const FORECAST_COLORS: Record<ForecastVolumeLevel, [string, string]> = {
  zero: ['--map-forecast-volume-zero', '#4b5960'],
  'positive-1': ['--map-forecast-volume-1', '#9ac7ce'],
  'positive-2': ['--map-forecast-volume-2', '#68aab5'],
  'positive-3': ['--map-forecast-volume-3', '#388896'],
  'positive-4': ['--map-forecast-volume-4', '#155b69'],
}

function forecastStyle(
  row: PrecinctForecast,
  scale: ForecastVolumeScale,
  container: HTMLElement,
): L.PathOptions {
  const level = forecastVolumeLevel(row.predictedCount, scale)
  const [token, fallback] = FORECAST_COLORS[level]
  const fillColor = cssToken(container, token, fallback)
  return {
    color: cssToken(container, '--map-predictive-boundary', '#d1dadd'),
    fillColor,
    fillOpacity: level === 'zero' ? 0.34 : 0.68,
    lineCap: 'round',
    lineJoin: 'round',
    opacity: 0.88,
    weight: level === 'zero' ? 1.8 : 1.35,
  }
}

function unavailableChangeStyle(
  coverage: Exclude<BaselineCoverage, 'complete'>,
  container: HTMLElement,
): L.PathOptions {
  if (coverage === 'partial') {
    const color = cssToken(container, '--map-change-partial', '#bca66f')
    return {
      color,
      dashArray: '8 5',
      fillColor: color,
      fillOpacity: 0.2,
      opacity: 1,
      weight: 2.1,
    }
  }
  const color = cssToken(container, '--map-change-unavailable', '#747f85')
  return {
    color,
    dashArray: coverage === 'missing' ? '2 5' : '1 6',
    fillColor: color,
    fillOpacity: coverage === 'missing' ? 0.1 : 0.06,
    opacity: 0.95,
    weight: 2,
  }
}

function changeStyle(
  row: PrecinctForecast,
  scale: ExpectedChangeScale,
  container: HTMLElement,
): L.PathOptions {
  const coverage = baselineCoverage(row)
  if (coverage !== 'complete') return unavailableChangeStyle(coverage, container)

  const direction = expectedChangeDirection(row)
  if (direction === 'unavailable') {
    return unavailableChangeStyle('unavailable', container)
  }
  if (direction === 'approximately equal') {
    const neutral = cssToken(container, '--map-change-equal', '#818c91')
    return {
      color: cssToken(container, '--map-predictive-boundary', '#d1dadd'),
      fillColor: neutral,
      fillOpacity: 0.45,
      opacity: 0.9,
      weight: 1.5,
    }
  }

  const intensity = expectedChangeIntensity(row, scale)
  const token = `--map-change-${direction}-${intensity}`
  const fallbacks =
    direction === 'above'
      ? ['#d1ad70', '#b98a4d', '#8f6434']
      : ['#6596b5', '#397497', '#1d536f']
  const fillColor = cssToken(container, token, fallbacks[intensity - 1])
  return {
    color: cssToken(container, '--map-predictive-boundary', '#d1dadd'),
    fillColor,
    fillOpacity: 0.68,
    opacity: 0.9,
    weight: 1.45,
  }
}

function selectedStyle(
  baseStyle: L.PathOptions,
  container: HTMLElement,
): L.PathOptions {
  return {
    ...baseStyle,
    color: cssToken(container, '--map-selected-outline', '#eef0ed'),
    fillOpacity: Math.min(0.82, (baseStyle.fillOpacity ?? 0.5) + 0.1),
    opacity: 1,
    weight: Math.max(3.5, baseStyle.weight ?? 0),
  }
}

function tooltipContent(row: PrecinctForecast, mode: PredictiveMode): HTMLElement {
  const content = document.createElement('span')
  content.textContent = precinctMapTooltipText(row, mode)
  return content
}

export function PrecinctForecastMap({
  spatial,
  rows,
  mode,
  selectedId,
  onSelect,
  descriptionId,
  onTileStatus,
}: PrecinctForecastMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const precinctLayerRef = useRef<L.LayerGroup | null>(null)
  const renderedRef = useRef<Map<string, RenderedPrecinct>>(new Map())
  const selectedIdRef = useRef(selectedId)
  const onSelectRef = useRef(onSelect)
  const onTileStatusRef = useRef(onTileStatus)
  const tileStatusRef = useRef<PredictiveTileStatus | null>(null)
  const lastFitKeyRef = useRef<string | null>(null)

  const matched = useMemo(
    () => matchPrecinctForecastFeatures(spatial, rows),
    [rows, spatial],
  )

  useEffect(() => {
    selectedIdRef.current = selectedId
    onSelectRef.current = onSelect
    onTileStatusRef.current = onTileStatus
  }, [onSelect, onTileStatus, selectedId])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const rendered = renderedRef.current

    const map = L.map(container, {
      attributionControl: true,
      keyboard: true,
      preferCanvas: true,
      scrollWheelZoom: false,
      zoomControl: false,
    }).setView(NYC_CENTER, DEFAULT_ZOOM)

    const reportTileStatus = (status: PredictiveTileStatus) => {
      if (tileStatusRef.current === status) return
      tileStatusRef.current = status
      onTileStatusRef.current?.(status)
    }
    reportTileStatus('loading')
    let tileFailed = false
    const tiles = L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
      {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        maxZoom: 19,
        subdomains: 'abcd',
        updateWhenIdle: true,
      },
    )
      .on('tileload', () => {
        if (!tileFailed) reportTileStatus('available')
      })
      .on('tileerror', () => {
        tileFailed = true
        reportTileStatus('error')
      })
      .addTo(map)

    const zoom = L.control.zoom({ position: 'topright' }).addTo(map)
    const zoomContainer = zoom.getContainer()
    zoomContainer
      ?.querySelector<HTMLElement>('.leaflet-control-zoom-in')
      ?.setAttribute(
        'aria-label',
        'Zoom in predictive precinct map',
      )
    zoomContainer
      ?.querySelector<HTMLElement>('.leaflet-control-zoom-out')
      ?.setAttribute(
        'aria-label',
        'Zoom out predictive precinct map',
      )

    const precinctLayer = L.layerGroup().addTo(map)
    mapRef.current = map
    precinctLayerRef.current = precinctLayer

    const resizeObserver =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => map.invalidateSize({ pan: false }))
    resizeObserver?.observe(container)

    return () => {
      resizeObserver?.disconnect()
      tiles.off()
      map.remove()
      mapRef.current = null
      precinctLayerRef.current = null
      rendered.clear()
      lastFitKeyRef.current = null
    }
    // Mode changes restyle the existing map in the rendering effect; they do
    // not rebuild the Leaflet instance or move its viewport.
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const precinctLayer = precinctLayerRef.current
    const container = containerRef.current
    if (!map || !precinctLayer || !container) return

    precinctLayer.clearLayers()
    renderedRef.current.clear()
    const forecastScale = createForecastVolumeScale(rows)
    const expectedChangeScale = createExpectedChangeScale(rows)
    const bounds = L.latLngBounds([])

    matched.forEach(({ row, feature }) => {
      const baseStyle =
        mode === 'forecast'
          ? forecastStyle(row, forecastScale, container)
          : changeStyle(row, expectedChangeScale, container)
      const layer = L.geoJSON(feature, {
        style: row.id === selectedIdRef.current
          ? selectedStyle(baseStyle, container)
          : baseStyle,
      })
      layer.bindTooltip(tooltipContent(row, mode), {
        direction: 'top',
        sticky: true,
      })
      layer.on('click', () => onSelectRef.current(row.id))
      layer.addTo(precinctLayer)
      renderedRef.current.set(row.id, { layer, baseStyle })
      bounds.extend(layer.getBounds())
    })

    const fitKey = matched
      .map(({ row }) => row.id)
      .sort((left, right) => left.localeCompare(right, 'en-US', { numeric: true }))
      .join('\u0000')
    if (fitKey !== lastFitKeyRef.current) {
      if (bounds.isValid()) {
        map.fitBounds(bounds, {
          animate: false,
          maxZoom: 13,
          padding: [24, 24],
        })
      } else {
        map.setView(NYC_CENTER, DEFAULT_ZOOM, { animate: false })
      }
      lastFitKeyRef.current = fitKey
    }
  }, [matched, mode, rows])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    renderedRef.current.forEach(({ layer, baseStyle }, id) => {
      const selected = id === selectedId
      layer.setStyle(selected ? selectedStyle(baseStyle, container) : baseStyle)
      if (selected) layer.bringToFront()
    })
  }, [selectedId])

  return (
    <div
      ref={containerRef}
      className="hotspot-map precinct-forecast-map"
      role="region"
      aria-label={
        mode === 'forecast'
          ? 'NYPD precinct forecast map'
          : 'NYPD precinct expected change map'
      }
      aria-describedby={descriptionId}
      data-feature-count={matched.length}
      data-mode={mode}
      title="Pan and zoom verified precinct boundaries. Use the precinct list for keyboard selection and complete values."
    />
  )
}

import L from 'leaflet'
import { useEffect, useRef } from 'react'
import 'leaflet/dist/leaflet.css'
import type { MapHotspot } from '../types/map'

const NYC_CENTER: L.LatLngExpression = [40.7128, -74.006]
const DEFAULT_ZOOM = 10

interface HotspotMapProps {
  hotspots: MapHotspot[]
  selectedId: string | null
  onSelect: (id: string) => void
  gridSizeDegrees: number | null
  descriptionId: string
}

function cssToken(element: HTMLElement, name: string, fallback: string): string {
  const value = getComputedStyle(element).getPropertyValue(name).trim()
  return value || fallback
}

function severityColor(element: HTMLElement, severity: string): string {
  const normalized = severity.trim().toLocaleLowerCase('en-US')
  if (normalized === 'critical') {
    return cssToken(element, '--map-severity-critical', '#c56868')
  }
  if (normalized === 'high') {
    return cssToken(element, '--map-severity-high', '#d1a35e')
  }
  if (normalized === 'medium') {
    return cssToken(element, '--map-severity-medium', '#75b1ba')
  }
  if (normalized === 'low') {
    return cssToken(element, '--map-severity-low', '#7b888f')
  }
  return cssToken(element, '--analytical-signal', '#75b1ba')
}

function tooltipContent(hotspot: MapHotspot): HTMLElement {
  const content = document.createElement('span')
  content.textContent = `${hotspot.locationLabel} · ${hotspot.offenseType} · ${hotspot.severity} severity`
  return content
}

function pathForHotspot(
  hotspot: MapHotspot,
  container: HTMLElement,
  selected: boolean,
  gridSizeDegrees: number | null,
): L.Path {
  const color = severityColor(container, hotspot.severity)
  const selectedColor = cssToken(container, '--map-selected-outline', '#eef0ed')
  const normalizedGrain = hotspot.grain.trim().toLocaleLowerCase('en-US')
  const pathOptions: L.PathOptions = {
    color: selected ? selectedColor : color,
    fillColor: color,
    fillOpacity: selected ? 0.78 : 0.52,
    opacity: 1,
    weight: selected ? 3 : 1.5,
  }

  if (normalizedGrain === 'grid' && gridSizeDegrees !== null) {
    const halfSize = gridSizeDegrees / 2
    return L.rectangle(
      [
        [hotspot.latitude - halfSize, hotspot.longitude - halfSize],
        [hotspot.latitude + halfSize, hotspot.longitude + halfSize],
      ],
      pathOptions,
    )
  }

  return L.circleMarker([hotspot.latitude, hotspot.longitude], {
    ...pathOptions,
    radius: normalizedGrain === 'precinct' ? (selected ? 10 : 8) : selected ? 8 : 6,
  })
}

export function HotspotMap({
  hotspots,
  selectedId,
  onSelect,
  gridSizeDegrees,
  descriptionId,
}: HotspotMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const signalLayerRef = useRef<L.LayerGroup | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const map = L.map(container, {
      attributionControl: true,
      keyboard: true,
      preferCanvas: true,
      scrollWheelZoom: false,
      zoomControl: false,
    }).setView(NYC_CENTER, DEFAULT_ZOOM)
    L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
      {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        maxZoom: 19,
        subdomains: 'abcd',
        updateWhenIdle: true,
      },
    ).addTo(map)
    const zoom = L.control.zoom({ position: 'topright' }).addTo(map)
    const zoomContainer = zoom.getContainer()
    zoomContainer
      ?.querySelector<HTMLElement>('.leaflet-control-zoom-in')
      ?.setAttribute('aria-label', 'Zoom in hotspot map')
    zoomContainer
      ?.querySelector<HTMLElement>('.leaflet-control-zoom-out')
      ?.setAttribute('aria-label', 'Zoom out hotspot map')

    const signalLayer = L.layerGroup().addTo(map)
    mapRef.current = map
    signalLayerRef.current = signalLayer

    const resizeObserver =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => map.invalidateSize({ pan: false }))
    resizeObserver?.observe(container)

    return () => {
      resizeObserver?.disconnect()
      map.remove()
      mapRef.current = null
      signalLayerRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const signalLayer = signalLayerRef.current
    const container = containerRef.current
    if (!map || !signalLayer || !container) return

    signalLayer.clearLayers()
    const bounds = L.latLngBounds([])
    hotspots.forEach((hotspot) => {
      const path = pathForHotspot(
        hotspot,
        container,
        hotspot.id === selectedId,
        gridSizeDegrees,
      )
      path.bindTooltip(tooltipContent(hotspot), {
        direction: 'top',
        sticky: true,
      })
      path.on('click', () => onSelect(hotspot.id))
      path.addTo(signalLayer)
      bounds.extend([hotspot.latitude, hotspot.longitude])
    })

    if (bounds.isValid()) {
      map.fitBounds(bounds, {
        animate: false,
        maxZoom: 13,
        padding: [24, 24],
      })
    } else {
      map.setView(NYC_CENTER, DEFAULT_ZOOM, { animate: false })
    }
  }, [gridSizeDegrees, hotspots, onSelect, selectedId])

  return (
    <div
      ref={containerRef}
      className="hotspot-map"
      role="region"
      aria-label="NYC hotspot map"
      aria-describedby={descriptionId}
      title="Pan and zoom the map. Use the hotspot list for keyboard navigation."
    />
  )
}

import { describe, expect, it } from 'vitest'
import appCss from './app.css?raw'
import tokensCss from './tokens.css?raw'

function mediaBlock(start: string, end: string): string {
  const startIndex = appCss.indexOf(start)
  const endIndex = appCss.indexOf(end, startIndex + start.length)
  return appCss.slice(startIndex, endIndex)
}

describe('Map responsive layout contract', () => {
  it('keeps the dark city basemap legible beneath hotspot signals', () => {
    const tileFilter = tokensCss.match(
      /--map-tile-filter:\s*saturate\([^)]+\)\s*brightness\(([^)]+)\)\s*contrast\([^)]+\);/,
    )

    expect(appCss).toMatch(
      /\.hotspot-map \.leaflet-tile-pane\s*{[^}]*filter:\s*var\(--map-tile-filter\);/s,
    )
    expect(tileFilter).not.toBeNull()
    expect(Number(tileFilter?.[1])).toBeGreaterThanOrEqual(1)
  })

  it('stacks the bounded map workspace before the mobile breakpoint', () => {
    const tablet = mediaBlock(
      '@media (max-width: 900px)',
      '@media (max-width: 660px)',
    )

    expect(tablet).toMatch(
      /\.map-workspace\s*{[^}]*height:\s*auto;[^}]*grid-template-columns:\s*1fr;/s,
    )
    expect(tablet).toMatch(
      /\.map-side-stack\s*{[^}]*grid-template-columns:\s*repeat\(2,/s,
    )
  })

  it('uses one-column controls, map, detail, and register on mobile', () => {
    const mobile = mediaBlock(
      '@media (max-width: 660px)',
      '@media (max-width: 390px)',
    )

    expect(mobile).toMatch(/\.map-layer-control\s*{[^}]*width:\s*100%;/s)
    expect(mobile).toMatch(
      /\.map-side-stack\s*{[^}]*grid-template-columns:\s*1fr;/s,
    )
    expect(mobile).toMatch(/\.hotspot-map\s*{[^}]*min-height:\s*390px;/s)
  })

  it('uses a single metric column at the verified narrow mobile width', () => {
    const narrowMobile = mediaBlock(
      '@media (max-width: 390px)',
      '@media (prefers-reduced-motion: reduce)',
    )

    expect(narrowMobile).toMatch(
      /\.metrics-grid\s*{[^}]*grid-template-columns:\s*1fr;/s,
    )
    expect(narrowMobile).toMatch(
      /\.freshness-status\s*{[^}]*display:\s*flex;/s,
    )
    expect(narrowMobile).toMatch(
      /\.freshness-status \.freshness-mobile\s*{[^}]*display:\s*block\s*!important;/s,
    )
  })

  it('keeps categorical scope visible when mobile filters are collapsed', () => {
    const mobile = mediaBlock(
      '@media (max-width: 660px)',
      '@media (max-width: 390px)',
    )

    expect(mobile).toMatch(
      /\.filter-toolbar__body\[data-expanded='false'\]\s*{[^}]*display:\s*none;/s,
    )
    expect(mobile).toMatch(
      /\.filter-active-scope\s*{[^}]*display:\s*block;/s,
    )
  })

  it('uses comfortable filter, layer, reload, and disclosure targets at tablet sizes', () => {
    expect(appCss).toMatch(/\.icon-button\s*{[^}]*width:\s*44px;[^}]*height:\s*44px;/s)
    expect(appCss).toMatch(
      /\.filter-field input,\s*\.filter-field select\s*{[^}]*min-height:\s*44px;/s,
    )
    expect(appCss).toMatch(
      /\.map-layer-control button\s*{[^}]*min-height:\s*44px;/s,
    )
    expect(appCss).toMatch(
      /\.data-context > summary\s*{[^}]*min-height:\s*44px;/s,
    )
    expect(appCss).toMatch(
      /\.map-mode-control button\s*{[^}]*min-height:\s*44px;/s,
    )
    expect(appCss).toMatch(
      /\.forecast-canvas-neutral button\s*{[^}]*min-height:\s*44px;/s,
    )
  })

  it('keeps the predictive legend, polygon canvas, and missing-baseline key responsive', () => {
    expect(appCss).toMatch(
      /\.predictive-map-panel\s*{[^}]*grid-template-rows:\s*auto minmax\(0, 1fr\);/s,
    )
    expect(appCss).toMatch(
      /\.predictive-map-legend\s*{[^}]*flex-wrap:\s*wrap;/s,
    )
    expect(appCss).toMatch(
      /\.change-swatch--unavailable\s*{[^}]*border:\s*2px dashed/s,
    )
    expect(appCss).toMatch(
      /\.precinct-forecast-map\s*{[^}]*min-height:\s*460px;/s,
    )
  })

  it('provides a solid surface fallback before enhancing supported glass', () => {
    expect(appCss).toMatch(
      /\.filter-toolbar,\s*\.analysis-panel,[\s\S]*?background:\s*var\(--surface-panel\);/,
    )
    expect(appCss).toContain(
      '@supports ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px)))',
    )
    expect(appCss).toMatch(
      /@supports[\s\S]*?backdrop-filter:\s*blur\(var\(--glass-blur\)\)/,
    )
    expect(appCss).toMatch(
      /\.system-context:not\(\[open\]\)\s*>\s*\.system-context__body\s*{[^}]*display:\s*none;/s,
    )
    expect(appCss).toMatch(
      /\.data-context:not\(\[open\]\)\s*>\s*\.data-context__body\s*{[^}]*display:\s*none;/s,
    )
  })

  it('removes depth motion and skeleton animation when reduced motion is requested', () => {
    const reducedMotion = mediaBlock(
      '@media (prefers-reduced-motion: reduce)',
      '@media print',
    )

    expect(reducedMotion).toMatch(
      /\.analysis-panel:hover,\s*\.metric-card:hover\s*{[^}]*transform:\s*none;/s,
    )
    expect(reducedMotion).toMatch(
      /\.skeleton-block::after\s*{[^}]*animation:\s*none\s*!important;/s,
    )
  })
})

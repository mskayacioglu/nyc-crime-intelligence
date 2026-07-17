import { describe, expect, it } from 'vitest'
import appCss from './app.css?raw'

describe('Governance responsive and interaction layout contract', () => {
  it('bounds every long-value surface and prevents page-level horizontal overflow', () => {
    expect(appCss).toMatch(
      /\.app-shell\s*{[^}]*overflow-x:\s*clip;/s,
    )
    expect(appCss).toMatch(
      /\.governance-view\s*{[^}]*min-width:\s*0;/s,
    )
    expect(appCss).toMatch(
      /\.governance-introduction,\s*\.governance-panel,\s*\.governance-provenance,\s*\.governance-state\s*{[^}]*min-width:\s*0;/s,
    )
    expect(appCss).toMatch(
      /\.governance-fact-grid > div,[\s\S]*?\.governance-provenance-grid > div\s*{[^}]*min-width:\s*0;[^}]*overflow-wrap:\s*anywhere;/,
    )
    expect(appCss).toMatch(
      /\.governance-long-value,\s*\.governance-long-value time\s*{[^}]*white-space:\s*normal;[^}]*overflow-wrap:\s*anywhere;[^}]*word-break:\s*break-word;/s,
    )
    expect(appCss).toMatch(
      /\.governance-readiness-list__heading > div\s*{[^}]*min-width:\s*0;/s,
    )
  })

  it('uses deliberate desktop, tablet, and mobile information grids', () => {
    expect(appCss).toMatch(
      /\.governance-introduction\s*{[^}]*grid-template-columns:\s*minmax\(0, 0\.9fr\) minmax\(320px, 1\.1fr\);/s,
    )
    expect(appCss).toMatch(
      /\.governance-fact-grid\s*{[^}]*grid-template-columns:\s*repeat\(4, minmax\(0, 1fr\)\);/s,
    )
    expect(appCss).toMatch(
      /\.governance-fact-grid--model\s*{[^}]*grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\);/s,
    )
    expect(appCss).toMatch(
      /\.governance-quality-grid\s*{[^}]*grid-template-columns:\s*repeat\(5, minmax\(0, 1fr\)\);/s,
    )
    expect(appCss).toMatch(
      /\.governance-limitations\s*{[^}]*grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\);/s,
    )
    expect(appCss).toMatch(
      /@media \(max-width: 900px\)[\s\S]*?\.governance-introduction\s*{[^}]*grid-template-columns:\s*1fr;[\s\S]*?\.governance-fact-grid,[\s\S]*?\.governance-provenance-grid\s*{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\);[\s\S]*?\.governance-limitations\s*{[^}]*grid-template-columns:\s*1fr;/,
    )
    expect(appCss).toMatch(
      /@media \(max-width: 660px\)[\s\S]*?\.governance-fact-grid,[\s\S]*?\.governance-provenance-grid\s*{[^}]*grid-template-columns:\s*1fr;/,
    )
  })

  it('keeps all Governance and navigation native controls at least 44 pixels', () => {
    expect(appCss).toMatch(
      /\.governance-retry\s*{[^}]*min-height:\s*44px;/s,
    )
    expect(appCss).toMatch(
      /\.governance-provenance > summary\s*{[^}]*min-height:\s*44px;/s,
    )
    expect(appCss).toMatch(
      /button:focus-visible,\s*input:focus-visible,\s*select:focus-visible,\s*summary:focus-visible,[\s\S]*?outline:\s*2px solid var\(--focus-ring\);/,
    )
    expect(appCss).toMatch(
      /\.view-navigation__item\s*{[^}]*min-height:\s*44px;/s,
    )
    expect(appCss).toMatch(
      /@media \(max-width: 660px\)[\s\S]*?\.governance-provenance > summary\s*{[^}]*min-height:\s*52px;/,
    )
  })

  it('lays out four navigation items as a readable mobile two-by-two grid', () => {
    expect(appCss).toMatch(
      /@media \(max-width: 660px\)[\s\S]*?\.view-navigation\s*{[^}]*display:\s*grid;[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\);/,
    )
    expect(appCss).toMatch(
      /@media \(max-width: 660px\)[\s\S]*?\.view-navigation__item\s*{[^}]*width:\s*100%;[^}]*min-width:\s*0;[^}]*min-height:\s*44px;/,
    )
    expect(appCss).toMatch(
      /@media \(max-width: 660px\)[\s\S]*?\.responsible-boundary\s*{[^}]*grid-column:\s*1 \/ -1;/,
    )
  })
})

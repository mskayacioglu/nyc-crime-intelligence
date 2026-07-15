import { describe, expect, it } from 'vitest'
import appCss from './app.css?raw'

describe('Anomalies responsive layout contract', () => {
  it('keeps overflow inside a bounded, keyboard-accessible register', () => {
    expect(appCss).toMatch(
      /\.anomalies-view,\s*\.anomaly-introduction,[\s\S]*?min-width:\s*0;/,
    )
    expect(appCss).toMatch(
      /\.anomaly-register\s*{[^}]*overflow:\s*hidden;/s,
    )
    expect(appCss).toMatch(
      /\.anomaly-register__list\s*{[^}]*overflow-y:\s*auto;/s,
    )
  })

  it('uses a two-pane desktop workspace and stacks it at tablet width', () => {
    expect(appCss).toMatch(
      /\.anomaly-workspace\s*{[^}]*grid-template-columns:\s*minmax\(0, 1\.45fr\) minmax\(320px, 0\.68fr\);/s,
    )
    expect(appCss).toMatch(
      /@media \(max-width: 900px\)[\s\S]*?\.anomaly-introduction,\s*\.anomaly-workspace\s*{[^}]*grid-template-columns:\s*1fr;/,
    )
  })

  it('keeps native row and disclosure targets at least 44 pixels', () => {
    expect(appCss).toMatch(
      /\.anomaly-register__list button\s*{[^}]*min-height:\s*72px;/s,
    )
    expect(appCss).toMatch(
      /\.anomaly-methodology > summary\s*{[^}]*min-height:\s*44px;/s,
    )
    expect(appCss).toMatch(
      /\.anomaly-register__list button:focus-visible\s*{[^}]*outline-offset:\s*-3px;/s,
    )
  })

  it('uses mobile-safe navigation, list cards, and detail metrics', () => {
    expect(appCss).toMatch(
      /@media \(max-width: 660px\)[\s\S]*?\.view-navigation__item\s*{[^}]*min-width:\s*0;/,
    )
    expect(appCss).toMatch(
      /@media \(max-width: 660px\)[\s\S]*?\.anomaly-register__list button\s*{[^}]*min-height:\s*92px;/,
    )
    expect(appCss).toMatch(
      /@media \(max-width: 390px\)[\s\S]*?\.anomaly-detail__metrics\s*{[^}]*grid-template-columns:\s*1fr;/,
    )
  })
})

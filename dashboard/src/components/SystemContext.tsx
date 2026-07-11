import { ChevronDown, Info } from 'lucide-react'
import type { OverviewMetadata } from '../types/overview'
import { formatDate, formatInteger } from '../utils/format'

export function SystemContext({ metadata }: { metadata: OverviewMetadata }) {
  return (
    <details className="system-context" data-testid="system-context">
      <summary>
        <span className="system-context__identity">
          <Info aria-hidden="true" size={17} />
          <span>
            <strong>About the data</strong>
            <small>Coverage, interpretation, and limitations</small>
          </span>
        </span>
        <ChevronDown className="system-context__chevron" aria-hidden="true" size={17} />
      </summary>

      <div className="system-context__body">
        <section aria-labelledby="system-context-title">
          <h2 id="system-context-title" className="visually-hidden">
            About the data
          </h2>
          <dl className="context-grid">
            <div>
              <dt>Coverage</dt>
              <dd>
                {formatDate(metadata.dataRange.safeEventStartDate)} —{' '}
                {formatDate(metadata.dataRange.safeEventEndDate)}
              </dd>
              <small>Reported complaint events</small>
            </div>
            <div>
              <dt>Included records</dt>
              <dd>{formatInteger(metadata.dataQuality.aggregateSafeEventCount)}</dd>
              <small>
                {formatInteger(metadata.dataQuality.excludedEventCount)} excluded by quality checks
              </small>
            </div>
            <div>
              <dt>Forecast</dt>
              <dd>Point estimate</dd>
              <small>No prediction interval is available</small>
            </div>
          </dl>

          <section className="context-limitations" aria-labelledby="context-limitations-title">
            <h3 id="context-limitations-title">How to read these results</h3>
            <ul>
              <li>Reported counts can change with reporting, classification, and revisions.</li>
              <li>Hotspots and anomalies describe unusual patterns, not causes.</li>
              <li>Forecast error is measured citywide and is not recalculated for active filters.</li>
            </ul>
          </section>
        </section>
      </div>
    </details>
  )
}

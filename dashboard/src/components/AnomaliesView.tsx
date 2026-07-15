import {
  AlertTriangle,
  Info,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { decodeAnomalies } from '../data/decodeAnomalies'
import { filterAnomalies } from '../data/filterAnomalies'
import type { AnomalyRecord, AnomalyUnavailableStatus } from '../types/anomalies'
import type { OverviewFilters, OverviewMetadata } from '../types/overview'
import { displayDimension, formatDate, formatDecimal, formatInteger } from '../utils/format'
import { FilterToolbar } from './FilterToolbar'

interface AnomaliesViewProps {
  metadata: OverviewMetadata
  filters: OverviewFilters
  onFilters: (filters: OverviewFilters) => void
  onReset: () => void
}

const preciseFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 4,
})

function precise(value: number): string {
  return preciseFormatter.format(value)
}

function signed(value: number): string {
  return `${value >= 0 ? '+' : ''}${precise(value)}`
}

function areaLabel(row: AnomalyRecord): string {
  return `${displayDimension(row.borough)} · Precinct ${displayDimension(row.precinct)}`
}

function priorityBadge(row: AnomalyRecord) {
  return (
    <span className={`anomaly-priority anomaly-priority--${row.severity}`}>
      <AlertTriangle aria-hidden="true" size={12} />
      {row.priorityLabel}
    </span>
  )
}

function AnomalyDetail({ row }: { row: AnomalyRecord }) {
  const zeroReference = row.expectedCount === 0
  const referenceExplanation =
    row.expectedSource === 'ml_prediction'
      ? 'This is the leakage-safe model estimate for the already-observed historical week, not a future forecast.'
      : 'This average uses the prior 13 weeks only and excludes the observed target week.'

  return (
    <aside
      className="anomaly-detail"
      aria-labelledby="anomaly-detail-title"
      aria-live="polite"
    >
      <div className="anomaly-detail__heading">
        <div>
          <h3 id="anomaly-detail-title">Week of {formatDate(row.week)}</h3>
          <p>Selected observed aggregate signal</p>
        </div>
        {priorityBadge(row)}
      </div>
      <div className="anomaly-detail__body">
        <p className="anomaly-detail__scope">
          <strong>{areaLabel(row)}</strong>
          <br />
          {displayDimension(row.offenseType)} · {displayDimension(row.lawCategory)}
        </p>
        <dl className="anomaly-detail__metrics">
          <div>
            <dt>Observed aggregate</dt>
            <dd>{formatInteger(row.actualCount)}</dd>
          </div>
          <div>
            <dt>{row.referenceLabel}</dt>
            <dd>
              {precise(row.expectedCount)}
              {zeroReference ? ' · valid zero' : ''}
            </dd>
          </div>
          <div>
            <dt>Signed deviation</dt>
            <dd>{signed(row.residualCount)}</dd>
          </div>
          <div>
            <dt>Relative deviation</dt>
            <dd>
              {row.deviationPct === null
                ? 'Unavailable · zero reference'
                : `+${formatDecimal(row.deviationPct)}%`}
            </dd>
          </div>
          <div>
            <dt>Anomaly score</dt>
            <dd>{precise(row.score)}</dd>
          </div>
          <div>
            <dt>Analytical priority</dt>
            <dd>{row.priorityLabel}</dd>
          </div>
        </dl>
        <p className="anomaly-detail__direction">
          <TrendingUp aria-hidden="true" size={16} />
          <span>
            <strong>{row.directionLabel}</strong> · {signed(row.residualCount)} aggregate
            reported events
          </span>
        </p>
        <p className="anomaly-detail__interpretation">{referenceExplanation}</p>
        <p className="anomaly-detail__interpretation">
          Signal priority ranks analytical deviation strength. It is not offense
          seriousness, a policing priority, or a recommendation for patrol or enforcement.
        </p>
      </div>
    </aside>
  )
}

function AnomalyRegister({
  rows,
  selectedId,
  onSelect,
}: {
  rows: AnomalyRecord[]
  selectedId: string
  onSelect: (id: string) => void
}) {
  return (
    <section className="anomaly-register" aria-labelledby="anomaly-register-title">
      <div className="anomaly-register__heading">
        <div>
          <h3 id="anomaly-register-title">Observed anomaly list</h3>
          <p>Critical first, then score, date, and stable aggregate identity.</p>
        </div>
        <span className="anomaly-register__count" aria-live="polite">
          {formatInteger(rows.length)} results
        </span>
      </div>
      <ol className="anomaly-register__list" aria-label="High and critical anomaly results">
        {rows.map((row, index) => {
          const selected = row.id === selectedId
          const label = [
            `Select anomaly ${index + 1}`,
            `week of ${formatDate(row.week)}`,
            areaLabel(row),
            displayDimension(row.offenseType),
            displayDimension(row.lawCategory),
            row.priorityLabel,
            `${signed(row.residualCount)} above expectation`,
          ].join(', ')
          return (
            <li key={row.id}>
              <button
                type="button"
                className={selected ? 'is-selected' : undefined}
                aria-pressed={selected}
                aria-label={label}
                onClick={() => onSelect(row.id)}
              >
                <span className="anomaly-register__rank">#{index + 1}</span>
                <span className="anomaly-register__identity">
                  <strong>
                    {formatDate(row.week)} · {areaLabel(row)}
                  </strong>
                  <small>
                    {displayDimension(row.offenseType)} · {displayDimension(row.lawCategory)}
                  </small>
                </span>
                <span className="anomaly-register__deviation">
                  {signed(row.residualCount)} · score {precise(row.score)}
                </span>
                {priorityBadge(row)}
              </button>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

function statusContent(status: AnomalyUnavailableStatus): {
  title: string
  message: string
} {
  if (status === 'missing') {
    return {
      title: 'Anomaly data is missing',
      message:
        'The authoritative aggregate anomaly artifact or its required methodology metadata is not present. No anomaly values are shown.',
    }
  }
  if (status === 'stale') {
    return {
      title: 'Anomaly data is stale',
      message:
        'The documented anomaly scoring horizon is behind the validated Overview horizon. Refresh the analytical artifacts before using this view.',
    }
  }
  if (status === 'incompatible') {
    return {
      title: 'Anomaly data is incompatible',
      message:
        'The anomaly contract does not align with this dashboard or its observation horizon. No rows are displayed.',
    }
  }
  return {
    title: 'Anomaly data is invalid',
    message:
      'The anomaly artifact or its methodology metadata did not pass validation. No invalid values are converted to zero.',
  }
}

function MethodologyDisclosure() {
  return (
    <details className="anomaly-methodology">
      <summary>
        <Info aria-hidden="true" size={16} />
        <strong>How to interpret anomaly ranking and priority</strong>
      </summary>
      <div className="anomaly-methodology__body">
        <p>
          Anomalies are already-observed weekly aggregate increases. They are distinct
          from Hotspots, which describe recent concentration, and Forecast / Expected
          change, which are future model estimates.
        </p>
        <ul>
          <li>
            The selected reference is a leakage-safe historical-week model estimate when
            available; otherwise it is the mean of the prior 13 weeks.
          </li>
          <li>
            The established candidate gate requires sufficient prior history and volume,
            at least four observed events, and at least three events above expectation.
          </li>
          <li>
            This view intentionally publishes only high and critical signals. It ranks
            critical before high, then by anomaly score, newest week, and stable aggregate
            identity.
          </li>
          <li>
            Score is composite signal strength, not a probability or event count. Severity
            also uses the documented residual, volume, and standardized-deviation gates.
          </li>
        </ul>
        <p>
          Reporting delays, classification changes, data revisions, and unmodeled events
          can affect these signals. They do not explain cause and do not justify patrol,
          enforcement, or person-level action.
        </p>
      </div>
    </details>
  )
}

export default function AnomaliesView({
  metadata,
  filters,
  onFilters,
  onReset,
}: AnomaliesViewProps) {
  const contract = useMemo(() => decodeAnomalies(metadata), [metadata])
  const filtered = useMemo(
    () => filterAnomalies(contract, filters),
    [contract, filters],
  )
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected =
    contract.status === 'available'
      ? filtered.rows.find((row) => row.id === selectedId) ?? filtered.rows[0] ?? null
      : null
  const effectiveSelectedId = selected?.id ?? null

  const criticalCount = filtered.rows.filter(
    (row) => row.severity === 'critical',
  ).length
  const highCount = filtered.rows.length - criticalCount
  const changeFilters = (nextFilters: OverviewFilters) => {
    if (
      selectedId !== null &&
      !filterAnomalies(contract, nextFilters).rows.some((row) => row.id === selectedId)
    ) {
      setSelectedId(null)
    }
    onFilters(nextFilters)
  }
  const reset = () => {
    setSelectedId(null)
    onReset()
  }

  return (
    <main id="main-content" className="main-content anomalies-view">
      <FilterToolbar
        metadata={metadata}
        filters={filters}
        onChange={changeFilters}
        onReset={reset}
      />

      <section className="anomaly-introduction" aria-labelledby="anomalies-title">
        <div className="anomaly-introduction__copy">
          <p className="section-kicker">Observed weekly deviations</p>
          <h2 id="anomalies-title">Anomalies</h2>
          <p>
            High and critical aggregate increases already observed in reported complaint
            data, compared with the documented historical-week expectation. These are not
            Hotspots, future forecasts, or predictions of individual behavior.
          </p>
        </div>
        <div className="anomaly-summary-grid" aria-label="Filtered anomaly counts" aria-live="polite">
          <div className="anomaly-summary-card">
            <span>Results</span>
            <strong>{contract.status === 'available' ? formatInteger(filtered.rows.length) : '—'}</strong>
          </div>
          <div className="anomaly-summary-card anomaly-summary-card--critical">
            <span>Critical</span>
            <strong>{contract.status === 'available' ? formatInteger(criticalCount) : '—'}</strong>
          </div>
          <div className="anomaly-summary-card anomaly-summary-card--high">
            <span>High</span>
            <strong>{contract.status === 'available' ? formatInteger(highCount) : '—'}</strong>
          </div>
        </div>
      </section>

      {contract.status !== 'available' ? (
        <section
          className={`anomaly-state anomaly-state--${contract.status}`}
          role={contract.status === 'invalid' || contract.status === 'incompatible' ? 'alert' : 'status'}
        >
          <ShieldAlert aria-hidden="true" size={28} />
          <div>
            <h2>{statusContent(contract.status).title}</h2>
            <p>{statusContent(contract.status).message}</p>
          </div>
        </section>
      ) : contract.isEmpty ? (
        <section className="anomaly-empty" role="status">
          <Info aria-hidden="true" size={28} />
          <div>
            <h3>Anomaly source is available but empty</h3>
            <p>
              The valid artifact contains no high or critical rows. This is an empty
              analytical result, not a zero-valued anomaly.
            </p>
          </div>
        </section>
      ) : filtered.isFilteredEmpty ? (
        <section className="anomaly-empty" role="status">
          <Info aria-hidden="true" size={28} />
          <div>
            <h3>No anomalies match the active filters</h3>
            <p>Adjust the date or category filters, or reset the view.</p>
          </div>
        </section>
      ) : selected && effectiveSelectedId ? (
        <div className="anomaly-workspace">
          <AnomalyRegister
            rows={filtered.rows}
            selectedId={effectiveSelectedId}
            onSelect={setSelectedId}
          />
          <AnomalyDetail row={selected} />
        </div>
      ) : null}

      <MethodologyDisclosure />
    </main>
  )
}

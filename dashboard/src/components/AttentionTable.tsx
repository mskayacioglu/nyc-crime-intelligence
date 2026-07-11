import { AlertTriangle, Crosshair } from 'lucide-react'
import type { AttentionRow } from '../types/overview'
import { formatDecimal, formatInteger } from '../utils/format'

export function AttentionTable({ rows }: { rows: AttentionRow[] }) {
  return (
    <section className="analysis-panel attention-panel" aria-labelledby="attention-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Aggregate signals</p>
          <h2 id="attention-title">Attention queue</h2>
          <p>
            Highest-severity aggregate anomalies and current hotspot signals.
          </p>
        </div>
        <Crosshair aria-hidden="true" size={18} />
      </div>
      {rows.length === 0 ? (
        <div className="panel-empty panel-empty--compact">
          <AlertTriangle aria-hidden="true" size={18} />
          <div>
            <strong>No compatible attention signals</strong>
            <p>
              No high or critical hotspot or anomaly rows match this filter context.
            </p>
          </div>
        </div>
      ) : (
        <div className="table-scroll" tabIndex={0} aria-label="Scrollable attention table">
          <table className="attention-table">
            <thead>
              <tr>
                <th scope="col">Severity</th>
                <th scope="col">Signal</th>
                <th scope="col">Period</th>
                <th scope="col">Area</th>
                <th scope="col">Offense / law</th>
                <th scope="col" className="numeric-cell">Observed</th>
                <th scope="col" className="numeric-cell">Reference</th>
                <th scope="col" className="numeric-cell">Score</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <span className={`severity severity--${row.severity}`}>
                      {row.severity}
                    </span>
                  </td>
                  <td>{row.kind}</td>
                  <td>{row.period}</td>
                  <td title={row.area}>{row.area}</td>
                  <td title={`${row.offense} · ${row.law}`}>
                    <span className="table-primary">{row.offense}</span>
                    <span className="table-secondary">{row.law}</span>
                  </td>
                  <td className="numeric-cell">
                    <span className="table-primary">{formatInteger(row.observedValue)}</span>
                    <span className="table-secondary">{row.observedLabel}</span>
                  </td>
                  <td className="numeric-cell">
                    <span className="table-primary">{formatDecimal(row.referenceValue)}</span>
                    <span className="table-secondary">{row.referenceLabel}</span>
                  </td>
                  <td className="numeric-cell">{formatDecimal(row.score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="panel-footnote">
        Signals identify aggregate conditions for review. They do not establish
        causality or justify person-level or enforcement action.
      </p>
    </section>
  )
}

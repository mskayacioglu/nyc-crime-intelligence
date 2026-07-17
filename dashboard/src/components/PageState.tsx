import { AlertCircle, Database, RefreshCw } from 'lucide-react'

function StateSkeleton() {
  return (
    <div className="dashboard-skeleton" aria-hidden="true">
      <div className="skeleton-block skeleton-filter" />
      <div className="skeleton-metrics">
        {Array.from({ length: 5 }, (_, index) => (
          <div className="skeleton-block skeleton-metric" key={index} />
        ))}
      </div>
      <div className="skeleton-grid">
        <div className="skeleton-block skeleton-chart skeleton-chart--wide" />
        <div className="skeleton-block skeleton-chart" />
        <div className="skeleton-block skeleton-chart" />
        <div className="skeleton-block skeleton-chart" />
      </div>
    </div>
  )
}

export function LoadingState() {
  return (
    <main id="main-content" className="main-content" aria-busy="true">
      <div className="state-banner" role="status">
        <Database aria-hidden="true" size={18} />
        <div>
          <strong>Loading overview</strong>
          <span>Preparing the current view.</span>
        </div>
      </div>
      <StateSkeleton />
    </main>
  )
}

export function ErrorState({ retry }: { retry: () => void }) {
  return (
    <main id="main-content" className="main-content">
      <section className="error-panel" role="alert">
        <AlertCircle aria-hidden="true" size={28} />
        <div>
          <h2>Data unavailable</h2>
          <p>
            The required core Overview metadata or aggregate cube is missing,
            inaccessible, or invalid. Try loading the dashboard again.
          </p>
          <button type="button" onClick={retry}>
            <RefreshCw aria-hidden="true" size={15} />
            Retry
          </button>
        </div>
      </section>
    </main>
  )
}

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { overviewFixture } from './test/fixture'

vi.mock('./components/MapView', () => ({
  default: () => (
    <main id="main-content">
      <h2>Map and Hotspot View</h2>
    </main>
  ),
}))

vi.mock('./components/AnomaliesView', () => ({
  default: ({ filters }: { filters: { boroughIndex: number | null } }) => (
    <main id="main-content">
      <h2>Anomalies View</h2>
      <p data-testid="anomaly-shared-borough">
        {filters.boroughIndex === null ? 'all' : filters.boroughIndex}
      </p>
    </main>
  ),
}))

describe('Dashboard view navigation', () => {
  it('opens the Map from Overview and returns without changing the default screen', async () => {
    const user = userEvent.setup()
    render(<App loader={async () => overviewFixture()} />)

    expect(await screen.findByTestId('selected-total')).toHaveTextContent('171')
    expect(
      screen.getByRole('button', { name: 'Overview' }),
    ).toHaveAttribute('aria-current', 'page')

    await user.click(screen.getByRole('button', { name: 'Map & hotspots' }))
    expect(
      await screen.findByRole('heading', { name: 'Map and Hotspot View' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Map & hotspots' }),
    ).toHaveAttribute('aria-current', 'page')

    await user.click(screen.getByRole('button', { name: 'Overview' }))
    expect(await screen.findByTestId('selected-total')).toHaveTextContent('171')
  })

  it('opens the lazy Anomalies view with the shared filter scope', async () => {
    const user = userEvent.setup()
    render(<App loader={async () => overviewFixture()} />)
    await screen.findByTestId('selected-total')

    await user.selectOptions(screen.getByLabelText('Borough'), '0')
    await user.click(screen.getByRole('button', { name: 'Anomalies' }))

    expect(
      await screen.findByRole('heading', { name: 'Anomalies View' }),
    ).toBeInTheDocument()
    expect(screen.getByTestId('anomaly-shared-borough')).toHaveTextContent('0')
    expect(screen.getByRole('button', { name: 'Anomalies' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByRole('link', { name: 'Skip to Anomalies' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Overview' }))
    expect(screen.getByLabelText('Borough')).toHaveValue('0')
  })
})

describe('Overview application states', () => {
  it('preserves the dashboard frame while aggregate data is loading', () => {
    const loader = () => new Promise<never>(() => undefined)
    render(<App loader={loader} />)

    expect(screen.getByRole('status')).toHaveTextContent('Loading overview')
    expect(document.querySelectorAll('.skeleton-metric')).toHaveLength(5)
  })

  it('shows an actionable error without exposing an internal error', async () => {
    const loader = vi.fn().mockRejectedValue(new Error('secret stack detail'))
    const user = userEvent.setup()
    render(<App loader={loader} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Data unavailable')
    expect(screen.queryByText(/secret stack detail/i)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(loader).toHaveBeenCalledTimes(2))
  })

  it('degrades safely when optional analytical outputs are absent', async () => {
    render(<App loader={async () => overviewFixture({ optional: false })} />)

    expect(await screen.findByTestId('selected-total')).toHaveTextContent('171')
    expect(screen.getByTestId('hotspot-summary')).toHaveTextContent('Not shown')
    expect(screen.getByTestId('anomaly-summary')).toHaveTextContent('Unavailable')
    expect(screen.getByTestId('forecast-summary')).toHaveTextContent('Not shown')
    expect(screen.getByTestId('hotspot-summary')).toHaveClass('metric-card--neutral')
    expect(screen.getByTestId('anomaly-summary')).toHaveClass('metric-card--neutral')
    expect(screen.getByTestId('forecast-summary')).toHaveClass('metric-card--neutral')
    expect(screen.getByText('No priority signals')).toBeInTheDocument()
  })
})

describe('Overview global filtering', () => {
  it('constrains precinct choices to the selected borough and clears an invalid precinct', async () => {
    const user = userEvent.setup()
    render(<App loader={async () => overviewFixture()} />)
    await screen.findByTestId('selected-total')

    const precinct = screen.getByLabelText('Precinct')
    await user.selectOptions(
      precinct,
      within(precinct).getByRole('option', { name: '2' }),
    )
    expect(precinct).toHaveValue('1')

    await user.selectOptions(screen.getByLabelText('Borough'), '0')
    expect(precinct).toHaveValue('')
    const options = within(precinct).getAllByRole('option').map((option) => option.textContent)
    expect(options).toContain('1')
    expect(options).not.toContain('2')
  })

  it('keeps observed totals internally consistent and reset restores the default scope', async () => {
    const user = userEvent.setup()
    render(<App loader={async () => overviewFixture()} />)
    const total = await screen.findByTestId('selected-total')
    expect(total).toHaveTextContent('171')

    await user.selectOptions(screen.getByLabelText('Borough'), '0')
    expect(total).toHaveTextContent('126')
    expect(screen.getByTestId('borough-chart')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Reset' }))
    expect(total).toHaveTextContent('171')
    expect(screen.getByLabelText('Borough')).toHaveValue('')
  })

  it('keeps a valid deterministic date window when a required date is cleared', async () => {
    const user = userEvent.setup()
    render(<App loader={async () => overviewFixture()} />)
    await screen.findByTestId('selected-total')

    const startWeek = screen.getByLabelText('Start week')
    const initialStart = (startWeek as HTMLInputElement).value
    await user.clear(startWeek)

    expect(startWeek).toHaveValue(initialStart)
    expect(screen.getByTestId('selected-total')).toHaveTextContent('171')
  })

  it('rejects off-dimension dates and accepts an observed Monday week', async () => {
    render(<App loader={async () => overviewFixture()} />)
    await screen.findByTestId('selected-total')

    const startWeek = screen.getByLabelText('Start week')
    const endWeek = screen.getByLabelText('End week')
    fireEvent.input(startWeek, { target: { value: '2025-01-07' } })
    expect(startWeek).toHaveValue('2025-01-06')

    fireEvent.input(endWeek, { target: { value: '2025-03-17' } })
    expect(endWeek).toHaveValue('2025-03-03')

    fireEvent.input(startWeek, { target: { value: '2025-01-13' } })
    expect(startWeek).toHaveValue('2025-01-13')
    expect(screen.getByTestId('selected-total')).toHaveTextContent('156')
  })

  it('exposes the mobile filter disclosure state to assistive technology', async () => {
    const user = userEvent.setup()
    render(<App loader={async () => overviewFixture()} />)
    await screen.findByTestId('selected-total')

    const disclosure = screen.getByRole('button', { name: 'Show filters' })
    const controls = document.getElementById('filter-controls')
    const activeScope = document.querySelector('.filter-active-scope')
    expect(disclosure).toHaveAttribute('aria-expanded', 'false')
    expect(disclosure).toHaveAttribute('aria-controls', 'filter-controls')
    expect(controls).toHaveAttribute('data-expanded', 'false')
    expect(activeScope).toHaveTextContent(
      'Active scope · All boroughs · All precincts · All offenses · All law categories',
    )

    await user.click(disclosure)
    expect(screen.getByRole('button', { name: 'Hide filters' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(controls).toHaveAttribute('data-expanded', 'true')
  })

  it('identifies an explicit empty result without collapsing the controls', async () => {
    const user = userEvent.setup()
    render(<App loader={async () => overviewFixture()} />)
    await screen.findByTestId('selected-total')

    await user.selectOptions(screen.getByLabelText('Offense type'), '2')
    expect(screen.getByText('No results')).toBeInTheDocument()
    expect(screen.getByTestId('selected-total')).toHaveTextContent('0')
    expect(screen.getByLabelText('Offense type')).toHaveValue('2')
  })
})

describe('Overview data context', () => {
  it('keeps product context concise and excludes development metadata', async () => {
    const user = userEvent.setup()
    const bundle = overviewFixture()
    bundle.metadata.versions = {
      ...bundle.metadata.versions,
      anomalyMetrics: {
        status: 'available',
        phase: 'Phase 6A - Anomaly Detection Layer',
        generatedAtUtc: '2025-03-10T08:30:00Z',
        sourceFile: 'anomaly_metrics.json',
      },
      hotspotMetrics: {
        status: 'available',
        phase: 'Phase 6B - Aggregate Hotspot Detection Layer',
        generatedAtUtc: '2025-03-10T09:00:00Z',
        sourceFile: 'hotspot_metrics.json',
      },
      baselineManifest: {
        status: 'available',
        phase: 'Phase 4 - Baseline Forecast Model',
        artifactVersion: 2,
        generatedAtUtc: '2025-03-09T07:00:00Z',
        sourceFile: 'model_manifest.json',
      },
      mlManifest: {
        status: 'available',
        phase: 'Phase 5 - ML Forecast Model',
        modelName: 'fixture_forecast',
        modelVersion: 1,
        generatedAtUtc: '2025-03-10T10:00:00Z',
        sourceFile: 'model_manifest.json',
      },
    }

    render(<App loader={async () => bundle} />)
    await screen.findByTestId('selected-total')

    const systemContext = screen.getByTestId('system-context')
    expect(systemContext).not.toHaveAttribute('open')
    expect(screen.getAllByText(/area-level patterns only/i)).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Reload dashboard data' })).toBeInTheDocument()

    await user.click(within(systemContext).getByText('About the data', { selector: 'strong' }))
    expect(systemContext).toHaveAttribute('open')

    expect(within(systemContext).getByText('Coverage')).toBeInTheDocument()
    expect(within(systemContext).getByText('Included records')).toBeInTheDocument()
    expect(within(systemContext).getByText('Point estimate')).toBeInTheDocument()
    expect(
      within(systemContext).getByRole('heading', { name: 'How to read these results' }),
    ).toBeInTheDocument()
    expect(systemContext).not.toHaveTextContent(
      /phase \d|contract v|artifact|manifest|\.json|\.parquet|sources ready|generated/i,
    )
  })
})

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { overviewFixture } from './test/fixture'

describe('Overview application states', () => {
  it('preserves the dashboard frame while aggregate data is loading', () => {
    const loader = () => new Promise<never>(() => undefined)
    render(<App loader={loader} />)

    expect(screen.getByRole('status')).toHaveTextContent('Loading aggregate intelligence')
    expect(document.querySelectorAll('.skeleton-metric')).toHaveLength(5)
  })

  it('shows an actionable error without exposing an internal error', async () => {
    const loader = vi.fn().mockRejectedValue(new Error('secret stack detail'))
    const user = userEvent.setup()
    render(<App loader={loader} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Aggregate data could not be opened')
    expect(screen.queryByText(/secret stack detail/i)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry data load' }))
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
    expect(screen.getByText('No compatible attention signals')).toBeInTheDocument()
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
    expect(disclosure).toHaveAttribute('aria-expanded', 'false')
    expect(disclosure).toHaveAttribute('aria-controls', 'filter-controls')
    expect(controls).toHaveAttribute('data-expanded', 'false')

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
    expect(screen.getByText('No aggregate records match these filters')).toBeInTheDocument()
    expect(screen.getByTestId('selected-total')).toHaveTextContent('0')
    expect(screen.getByLabelText('Offense type')).toHaveValue('2')
  })
})

describe('Overview analytical provenance', () => {
  it('lists artifact status, phase or version, and generation time when supplied', async () => {
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

    const provenance = screen.getByRole('region', { name: 'Artifact provenance' })
    expect(within(provenance).getByText('Anomaly metrics')).toBeInTheDocument()
    expect(within(provenance).getByText('Hotspot metrics')).toBeInTheDocument()
    expect(within(provenance).getByText('ML forecast metrics')).toBeInTheDocument()
    expect(within(provenance).getByText('ML forecast manifest')).toBeInTheDocument()
    expect(within(provenance).getByText('Baseline forecast manifest')).toBeInTheDocument()
    expect(within(provenance).getByText(/Model fixture_forecast · model v1/)).toBeInTheDocument()
    expect(within(provenance).getByText(/Phase 4 - Baseline Forecast Model · artifact v2/)).toBeInTheDocument()
    expect(within(provenance).getByText('2025-03-10 08:30:00Z')).toBeInTheDocument()
    expect(within(provenance).getAllByText('Available')).toHaveLength(5)
  })
})

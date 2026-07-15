import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { defaultFilters } from '../data/aggregateOverview'
import { overviewFixture } from '../test/fixture'
import type { OverviewFilters, OverviewMetadata } from '../types/overview'
import AnomaliesView from './AnomaliesView'

function metadataFixture(): OverviewMetadata {
  const metadata = overviewFixture().metadata
  metadata.signals.anomalies.summary = {
    rowCount: 2,
    highCount: 1,
    criticalCount: 1,
    isEmpty: false,
    scoringEndWeek: metadata.dataRange.latestCompleteWeek,
  }
  return metadata
}

function Harness({ metadata = metadataFixture() }: { metadata?: OverviewMetadata }) {
  const [filters, setFilters] = useState<OverviewFilters>(defaultFilters(metadata))
  return (
    <AnomaliesView
      metadata={metadata}
      filters={filters}
      onFilters={setFilters}
      onReset={() => setFilters(defaultFilters(metadata))}
    />
  )
}

describe('Anomalies view', () => {
  it('selects the deterministic first signal and synchronizes list and detail', () => {
    render(<Harness />)

    const buttons = screen.getAllByRole('button', { name: /select anomaly/i })
    expect(buttons).toHaveLength(2)
    expect(buttons[0]).toHaveAttribute('aria-pressed', 'true')
    expect(buttons[1]).toHaveAttribute('aria-pressed', 'false')
    expect(buttons[0]).toHaveAccessibleName(/grand larceny, felony, critical signal priority/i)

    const detail = screen.getByRole('complementary', { name: /week of mar 3, 2025/i })
    expect(detail).toHaveTextContent('BRONX · Precinct 1')
    expect(detail).toHaveTextContent('GRAND LARCENY · FELONY')
    expect(detail).toHaveTextContent('Prior 13-week average')
    expect(detail).toHaveTextContent('11.5')
    expect(detail).toHaveTextContent('+6.5 aggregate reported events')
    expect(detail).toHaveTextContent('Critical signal priority')
  })

  it('uses native Enter and Space activation while retaining visible button focus', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const buttons = screen.getAllByRole('button', { name: /select anomaly/i })

    buttons[1].focus()
    await user.keyboard('{Enter}')
    expect(buttons[1]).toHaveFocus()
    expect(buttons[1]).toHaveAttribute('aria-pressed', 'true')
    expect(
      screen.getByRole('complementary', { name: /week of feb 24, 2025/i }),
    ).toHaveTextContent('Historical backtest estimate')

    buttons[0].focus()
    await user.keyboard(' ')
    expect(buttons[0]).toHaveFocus()
    expect(buttons[0]).toHaveAttribute('aria-pressed', 'true')
    expect(
      screen.getByRole('complementary', { name: /week of mar 3, 2025/i }),
    ).toBeInTheDocument()
  })

  it('applies categorical filters, borough constraints, and Reset consistently', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    const precinct = screen.getByLabelText('Precinct')
    await user.selectOptions(
      precinct,
      within(precinct).getByRole('option', { name: '2' }),
    )
    expect(precinct).toHaveValue('1')

    await user.selectOptions(screen.getByLabelText('Borough'), '0')
    expect(precinct).toHaveValue('')
    expect(screen.getAllByRole('button', { name: /select anomaly/i })).toHaveLength(1)
    expect(screen.getByText('1 results')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Reset' }))
    expect(screen.getByLabelText('Borough')).toHaveValue('')
    expect(screen.getAllByRole('button', { name: /select anomaly/i })).toHaveLength(2)
  })

  it('distinguishes a source-empty result from a filtered-empty result', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<Harness />)

    await user.selectOptions(screen.getByLabelText('Offense type'), '2')
    expect(screen.getByRole('status')).toHaveTextContent(
      'No anomalies match the active filters',
    )

    unmount()
    const metadata = metadataFixture()
    metadata.signals.anomalies.rows = []
    metadata.signals.anomalies.summary = {
      rowCount: 0,
      highCount: 0,
      criticalCount: 0,
      isEmpty: true,
      scoringEndWeek: metadata.dataRange.latestCompleteWeek,
    }
    render(<Harness metadata={metadata} />)
    expect(screen.getByRole('status')).toHaveTextContent(
      'Anomaly source is available but empty',
    )
    expect(screen.queryByRole('button', { name: /select anomaly/i })).not.toBeInTheDocument()
  })

  it.each([
    ['missing', 'Anomaly data is missing'],
    ['invalid', 'Anomaly data is invalid'],
    ['stale', 'Anomaly data is stale'],
    ['incompatible', 'Anomaly data is incompatible'],
  ] as const)('renders the declared %s state without anomaly values', (status, title) => {
    const metadata = metadataFixture()
    metadata.signals.anomalies = {
      status,
      sourceFile: 'anomalies.parquet',
      reason: 'Internal test detail that is not rendered.',
      rows: [],
    }
    render(<Harness metadata={metadata} />)

    expect(screen.getByText(title)).toBeInTheDocument()
    expect(screen.queryByText(/internal test detail/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /select anomaly/i })).not.toBeInTheDocument()
  })

  it('preserves a valid zero reference and withholds only the undefined percentage', () => {
    const metadata = metadataFixture()
    const rows = metadata.signals.anomalies.rows
    if (!rows) throw new Error('Fixture anomaly rows are missing.')
    rows[0] = [8, 0, 0, 0, 0, 18, 0, 18, 4.2, 0, 1]

    render(<Harness metadata={metadata} />)
    const detail = screen.getByRole('complementary', { name: /week of mar 3, 2025/i })
    expect(detail).toHaveTextContent('0 · valid zero')
    expect(detail).toHaveTextContent('Unavailable · zero reference')
    expect(detail).toHaveTextContent('+18 aggregate reported events')
  })

  it('explains ranking, source precedence, and responsible-use boundaries', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const disclosure = screen.getByText(
      'How to interpret anomaly ranking and priority',
    )
    await user.click(disclosure)

    const details = disclosure.closest('details')
    expect(details).toHaveAttribute('open')
    expect(details).toHaveTextContent('already-observed weekly aggregate increases')
    expect(details).toHaveTextContent('critical before high')
    expect(details).toHaveTextContent('not a probability or event count')
    expect(details).toHaveTextContent('do not justify patrol, enforcement')
  })

  it('keeps a selected native button focused after its state rerender', async () => {
    const user = userEvent.setup()
    const onFilters = vi.fn()
    const metadata = metadataFixture()
    const filters = defaultFilters(metadata)
    render(
      <AnomaliesView
        metadata={metadata}
        filters={filters}
        onFilters={onFilters}
        onReset={vi.fn()}
      />,
    )
    const second = screen.getAllByRole('button', { name: /select anomaly/i })[1]
    second.focus()
    await user.keyboard('{Enter}')
    expect(second).toHaveFocus()
    expect(second).toHaveAttribute('aria-pressed', 'true')
    expect(within(second).getByText('High signal priority')).toBeInTheDocument()
  })
})

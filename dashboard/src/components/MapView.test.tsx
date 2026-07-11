import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { defaultFilters } from '../data/aggregateOverview'
import type { MapDataContract, MapHotspot, MapLoader } from '../types/map'
import type { OverviewFilters } from '../types/overview'
import { mapFixture } from '../test/mapFixture'
import { overviewFixture } from '../test/fixture'
import MapView from './MapView'

vi.mock('./HotspotMap', () => ({
  HotspotMap: ({
    hotspots,
    selectedId,
    onSelect,
  }: {
    hotspots: MapHotspot[]
    selectedId: string | null
    onSelect: (id: string) => void
  }) => (
    <div data-testid="hotspot-map" data-count={hotspots.length}>
      <span>Mock aggregate map with {hotspots.length} signals</span>
      {hotspots.map((hotspot) => (
        <button
          key={hotspot.id}
          type="button"
          aria-label={`Mock map marker ${hotspot.rank}`}
          aria-pressed={hotspot.id === selectedId}
          onClick={() => onSelect(hotspot.id)}
        >
          {hotspot.locationLabel}
        </button>
      ))}
    </div>
  ),
}))

function MapHarness({
  contract = mapFixture(),
  loader,
  initialFilters,
}: {
  contract?: MapDataContract
  loader?: MapLoader
  initialFilters?: OverviewFilters
}) {
  const metadata = overviewFixture().metadata
  const defaults = defaultFilters(metadata)
  const [filters, setFilters] = useState(initialFilters ?? defaults)
  return (
    <MapView
      metadata={metadata}
      filters={filters}
      onFilters={setFilters}
      onReset={() => setFilters(defaults)}
      mapLoader={loader ?? (async () => contract)}
    />
  )
}

describe('Map data states', () => {
  it('keeps global filters available while the compact Map contract is loading', () => {
    const loader = () => new Promise<MapDataContract>(() => undefined)
    render(<MapHarness loader={loader} />)

    expect(screen.getByRole('status')).toHaveTextContent(
      'Loading hotspots',
    )
    expect(screen.getByLabelText('Borough')).toBeInTheDocument()
    expect(screen.queryByTestId('hotspot-map')).not.toBeInTheDocument()
  })

  it('shows a safe error and retries without exposing response details', async () => {
    const loader = vi.fn().mockRejectedValue(new Error('private path detail'))
    const user = userEvent.setup()
    render(<MapHarness loader={loader} />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Map unavailable')
    expect(alert).not.toHaveTextContent('private path detail')
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(loader).toHaveBeenCalledTimes(2))
  })

  it.each([
    ['missing', 'No hotspot data'],
    ['invalid', 'Hotspot data unavailable'],
    ['stale', 'Hotspot data out of date'],
  ] as const)('renders the %s source as a neutral non-map state', async (status, title) => {
    render(<MapHarness contract={mapFixture({ status })} />)

    expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument()
    expect(screen.queryByText(`Fixture hotspot source is ${status}.`)).not.toBeInTheDocument()
    expect(screen.queryByTestId('hotspot-map')).not.toBeInTheDocument()
  })

  it('distinguishes an available empty snapshot from a missing input', async () => {
    render(<MapHarness contract={mapFixture({ empty: true })} />)

    expect(
      await screen.findByText(
        'No hotspots available',
      ),
    ).toBeInTheDocument()
    expect(screen.getByTestId('hotspot-map')).toHaveAttribute('data-count', '0')
    expect(screen.getByText('No hotspot selected')).toBeInTheDocument()
  })

  it('withholds the fixed current snapshot from a historical end week', async () => {
    const metadata = overviewFixture().metadata
    const filters = {
      ...defaultFilters(metadata),
      endWeek: '2025-02-24',
    }
    render(<MapHarness initialFilters={filters} />)

    expect(
      await screen.findByRole('heading', {
        name: 'Historical hotspots unavailable',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText(/set it to .* or later/i)).toBeInTheDocument()
    expect(screen.queryByTestId('hotspot-map')).not.toBeInTheDocument()
  })

  it('withholds a Map contract built from a different safe event date', async () => {
    const contract = mapFixture()
    contract.dataRange.safeEventEndDate = '2025-03-03'
    render(<MapHarness contract={contract} />)

    expect(
      await screen.findByRole('heading', { name: 'Map temporarily unavailable' }),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('hotspot-map')).not.toBeInTheDocument()
  })
})

describe('Map filtering and selection', () => {
  it('matches global filter labels even when Map dimension indexes differ', async () => {
    const user = userEvent.setup()
    render(<MapHarness />)
    const map = await screen.findByTestId('hotspot-map')
    expect(map).toHaveAttribute('data-count', '5')

    await user.selectOptions(screen.getByLabelText('Borough'), '0')
    expect(map).toHaveAttribute('data-count', '3')

    await user.selectOptions(screen.getByLabelText('Offense type'), '0')
    expect(map).toHaveAttribute('data-count', '2')

    await user.selectOptions(screen.getByLabelText('Law category'), '0')
    expect(map).toHaveAttribute('data-count', '2')
  })

  it('keeps the borough-to-precinct constraint and clears an incompatible precinct', async () => {
    const user = userEvent.setup()
    render(<MapHarness />)
    await screen.findByTestId('hotspot-map')

    const precinct = screen.getByLabelText('Precinct')
    await user.selectOptions(
      precinct,
      within(precinct).getByRole('option', { name: '2' }),
    )
    expect(precinct).toHaveValue('1')

    await user.selectOptions(screen.getByLabelText('Borough'), '0')
    expect(precinct).toHaveValue('')
    expect(within(precinct).queryByRole('option', { name: '2' })).not.toBeInTheDocument()
  })

  it('omits unassigned grid rows under a precinct filter and explains the rule', async () => {
    const user = userEvent.setup()
    render(<MapHarness />)
    const map = await screen.findByTestId('hotspot-map')

    await user.selectOptions(screen.getByLabelText('Borough'), '0')
    await user.selectOptions(screen.getByLabelText('Precinct'), '0')
    expect(map).toHaveAttribute('data-count', '2')
    expect(screen.getByRole('note')).toHaveTextContent(
      'Grid cells are unavailable',
    )

    await user.click(screen.getByRole('button', { name: 'Show grid cells' }))
    expect(map).toHaveAttribute('data-count', '0')
    expect(screen.getByText('No hotspots match these filters')).toBeInTheDocument()

    await user.click(
      screen.getByRole('button', { name: 'Show precinct markers' }),
    )
    expect(map).toHaveAttribute('data-count', '2')
  })

  it('supports marker and keyboard-register selection with a complete detail panel', async () => {
    const user = userEvent.setup()
    render(<MapHarness />)
    await screen.findByTestId('hotspot-map')

    await user.click(screen.getByRole('button', { name: 'Mock map marker 2' }))
    let detail = screen.getByRole('complementary', {
      name: 'Brooklyn · Precinct 2 aggregate centroid',
    })
    expect(within(detail).getByText('22')).toBeInTheDocument()
    expect(within(detail).getByText('12.4')).toBeInTheDocument()
    expect(within(detail).getByText('+77.4%')).toBeInTheDocument()
    expect(within(detail).getByText('78.0')).toBeInTheDocument()
    expect(within(detail).getByText('high')).toBeInTheDocument()

    const dataContext = within(detail).getByText('About hotspots').closest('details')
    expect(dataContext).not.toHaveAttribute('open')
    await user.click(within(detail).getByText('About hotspots'))
    expect(dataContext).toHaveAttribute('open')
    expect(within(detail).getByText(/prior 365 days/i)).toBeInTheDocument()
    expect(detail).not.toHaveTextContent(/\.parquet|source file|contract|artifact/i)

    const registerButton = screen.getByRole('button', {
      name: /select rank 4 precinct hotspot/i,
    })
    registerButton.focus()
    await user.keyboard('{Enter}')
    expect(registerButton).toHaveAttribute('aria-pressed', 'true')
    detail = screen.getByRole('complementary', {
      name: 'Bronx · Precinct 1 aggregate centroid',
    })
    expect(within(detail).getByText('12')).toBeInTheDocument()
  })

  it('reset restores the global scope, all-grain layer, and first detail', async () => {
    const user = userEvent.setup()
    render(<MapHarness />)
    const map = await screen.findByTestId('hotspot-map')

    await user.selectOptions(screen.getByLabelText('Borough'), '0')
    await user.click(screen.getByRole('button', { name: 'Show grid cells' }))
    expect(map).toHaveAttribute('data-count', '1')

    await user.click(screen.getByRole('button', { name: 'Reset' }))
    expect(screen.getByLabelText('Borough')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Show all hotspot layers' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(map).toHaveAttribute('data-count', '5')
    expect(
      screen.getByRole('complementary', { name: 'Grid 40.845, -73.905' }),
    ).toBeInTheDocument()
  })
})

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { defaultFilters } from '../data/aggregateOverview'
import type { MapDataContract, MapHotspot, MapLoader } from '../types/map'
import type { OverviewFilters } from '../types/overview'
import { mapFixture } from '../test/mapFixture'
import { overviewFixture } from '../test/fixture'
import MapView from './MapView'
import forecastArtifact from '../../public/data/forecast-map.json'
import spatialArtifact from '../../public/data/precinct-spatial-reference.json'
import overviewMetadataArtifact from '../../public/data/overview.json'
import { decodeForecastMap } from '../data/loadForecastMap'
import {
  decodePrecinctSpatialReference,
  PrecinctSpatialReferenceError,
} from '../data/loadPrecinctSpatialReference'
import type { OverviewMetadata } from '../types/overview'

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

vi.mock('./PrecinctForecastMap', () => ({
  PrecinctForecastMap: ({
    rows,
    selectedId,
    onSelect,
    mode,
    onTileStatus,
  }: {
    rows: Array<{ id: string; precinct: string }>
    selectedId: string | null
    onSelect: (id: string) => void
    mode: string
    onTileStatus?: (status: 'error') => void
  }) => (
    <div data-testid="predictive-map" data-count={rows.length} data-mode={mode}>
      {rows.map((row) => (
        <button
          key={row.id}
          type="button"
          aria-label={`Mock forecast polygon precinct ${row.precinct}`}
          aria-pressed={row.id === selectedId}
          onClick={() => onSelect(row.id)}
        >
          Precinct {row.precinct}
        </button>
      ))}
      <button type="button" onClick={() => onTileStatus?.('error')}>
        Simulate predictive tile failure
      </button>
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

describe('Predictive Map modes', () => {
  function PredictiveHarness({
    spatialLoader = async () =>
      decodePrecinctSpatialReference(structuredClone(spatialArtifact)),
    forecastLoader = async () => decodeForecastMap(structuredClone(forecastArtifact)),
  }: {
    spatialLoader?: () => Promise<ReturnType<typeof decodePrecinctSpatialReference>>
    forecastLoader?: () => Promise<ReturnType<typeof decodeForecastMap>>
  } = {}) {
    const metadata=overviewMetadataArtifact as unknown as OverviewMetadata
    const defaults=defaultFilters(metadata)
    const [filters,setFilters]=useState(defaults)
    return <MapView metadata={metadata} filters={filters} onFilters={setFilters} onReset={()=>setFilters(defaults)} mapLoader={async()=>mapFixture()} forecastMapLoader={forecastLoader} precinctSpatialReferenceLoader={spatialLoader}/>
  }

  function selectedPrecinct(button: HTMLElement): string {
    const match = button.getAttribute('aria-label')?.match(/^Select precinct ([^,]+),/)
    if (!match) throw new Error('Predictive list button is missing its precinct label.')
    return match[1]
  }

  function expectSynchronizedSelection(button: HTMLElement) {
    const precinct = selectedPrecinct(button)
    expect(button).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('complementary')).toHaveTextContent(`Precinct ${precinct}`)
    expect(
      within(screen.getByTestId('predictive-map')).getByRole('button', {
        name: `Mock forecast polygon precinct ${precinct}`,
      }),
    ).toHaveAttribute('aria-pressed', 'true')
  }

  it('renders verified polygons and keeps polygon, keyboard list, and detail selection synchronized', async () => {
    const user=userEvent.setup()
    render(<PredictiveHarness/>)
    await user.click(screen.getByRole('button',{name:'Forecast'}))
    const map=await screen.findByTestId('predictive-map')
    expect(map).toHaveAttribute('data-count','78')
    expect(screen.getByRole('group',{name:'Forecast aggregate-volume scale'})).toHaveTextContent(/95th-percentile cap/i)
    expect(screen.getByRole('heading',{name:'Precinct forecast list'})).toBeInTheDocument()
    const buttons=screen.getAllByRole('button',{name:/select precinct/i})
    expect(buttons).toHaveLength(78)
    buttons[1].focus(); await user.keyboard('{Enter}')
    expect(buttons[1]).toHaveAttribute('aria-pressed','true')
    expect(screen.getByRole('complementary')).toHaveTextContent(/Expected aggregate reported-event volume/i)
    expect(screen.getByRole('complementary')).toHaveTextContent(/No prediction interval is available/i)

    await user.click(screen.getByRole('button',{name:'Mock forecast polygon precinct 1'}))
    expect(screen.getByRole('button',{name:/Select precinct 1,/i})).toHaveAttribute('aria-pressed','true')
    expect(screen.getByRole('complementary')).toHaveTextContent('Precinct 1')
  })

  it('retains native focus through Enter, Tab, and Space selection in both predictive modes', async () => {
    const user = userEvent.setup()
    render(<PredictiveHarness />)

    await user.click(screen.getByRole('button', { name: 'Forecast' }))
    await screen.findByTestId('predictive-map')
    const forecastButtons = screen.getAllByRole('button', { name: /select precinct/i })
    const forecastEnter = forecastButtons[1]
    const forecastSpace = forecastButtons[2]

    forecastEnter.focus()
    await user.keyboard('{Enter}')
    expect(forecastEnter).toHaveFocus()
    expectSynchronizedSelection(forecastEnter)

    await user.tab()
    expect(forecastSpace).toHaveFocus()
    await user.keyboard(' ')
    expect(forecastSpace).toHaveFocus()
    expect(forecastEnter).toHaveAttribute('aria-pressed', 'false')
    expectSynchronizedSelection(forecastSpace)

    await user.click(screen.getByRole('button', { name: 'Expected change' }))
    expect(
      await screen.findByRole('heading', { name: 'Expected change' }),
    ).toBeInTheDocument()
    const changeButtons = screen.getAllByRole('button', { name: /select precinct/i })
    const changeEnter = changeButtons[3]
    const changeSpace = changeButtons[4]

    changeEnter.focus()
    await user.keyboard('{Enter}')
    expect(changeEnter).toHaveFocus()
    expectSynchronizedSelection(changeEnter)

    await user.tab()
    expect(changeSpace).toHaveFocus()
    await user.keyboard(' ')
    expect(changeSpace).toHaveFocus()
    expect(changeEnter).toHaveAttribute('aria-pressed', 'false')
    expectSynchronizedSelection(changeSpace)
  })

  it('keeps filtered polygon counts exact and distinguishes a filter-empty result', async () => {
    const user = userEvent.setup()
    render(<PredictiveHarness />)
    await user.click(screen.getByRole('button', { name: 'Forecast' }))

    await user.selectOptions(screen.getByLabelText('Borough'), 'BRONX')
    await waitFor(() => {
      expect(screen.getByTestId('predictive-map')).toHaveAttribute(
        'data-count',
        '12',
      )
    })
    expect(screen.getAllByRole('button', { name: /select precinct/i })).toHaveLength(
      12,
    )

    await user.selectOptions(screen.getByLabelText('Borough'), 'MANHATTAN')
    await user.selectOptions(screen.getByLabelText('Offense type'), 'ABORTION')
    await waitFor(() => {
      expect(screen.getByTestId('predictive-map')).toHaveAttribute(
        'data-count',
        '0',
      )
    })
    expect(
      screen.getByText('No forecast rows match these filters'),
    ).toBeInTheDocument()
    expect(screen.getByRole('complementary')).toHaveTextContent(
      'No precinct selected',
    )
    expect(screen.queryByRole('button', { name: /select precinct/i })).not.toBeInTheDocument()
  })

  it('keeps a real small positive forecast distinct from valid zero in both predictive modes', async () => {
    const user = userEvent.setup()
    render(<PredictiveHarness />)
    await user.click(screen.getByRole('button', { name: 'Forecast' }))

    await user.selectOptions(screen.getByLabelText('Borough'), 'BROOKLYN')
    await user.selectOptions(screen.getByLabelText('Precinct'), '66')
    await user.selectOptions(
      screen.getByLabelText('Offense type'),
      'UNLAWFUL POSS. WEAP. ON SCHOOL',
    )
    await user.selectOptions(screen.getByLabelText('Law category'), 'VIOLATION')

    expect(
      await screen.findByRole('button', {
        name: 'Select precinct 66, 0.00102 expected aggregate reported events',
      }),
    ).toBeInTheDocument()
    const forecastLegend = screen.getByRole('group', {
      name: 'Forecast aggregate-volume scale',
    })
    expect(forecastLegend).toHaveTextContent('>0–0.000255')
    expect(forecastLegend).toHaveTextContent('0.00102')
    expect(screen.getByRole('complementary')).toHaveTextContent('0.00102')
    expect(screen.getByRole('complementary')).not.toHaveTextContent(
      /Forecast\s+0\.0(?:\D|$)/,
    )

    await user.click(screen.getByRole('button', { name: 'Expected change' }))
    expect(
      screen.getByRole('button', {
        name: 'Select precinct 66, above baseline, +0.00102',
      }),
    ).toBeInTheDocument()
    expect(screen.getByRole('complementary')).toHaveTextContent(
      'above · +0.00102',
    )
  })

  it('shows signed direction text in Expected change mode and preserves Hotspots', async () => {
    const user=userEvent.setup()
    render(<PredictiveHarness/>)
    await user.click(screen.getByRole('button',{name:'Expected change'}))
    expect(await screen.findByRole('heading',{name:'Expected change'})).toBeInTheDocument()
    expect(screen.getAllByText(/above|below|approximately equal/i).length).toBeGreaterThan(0)
    const legend=screen.getByRole('group',{name:'Expected-change direction and magnitude scale'})
    expect(legend).toHaveTextContent('Below baseline')
    expect(legend).toHaveTextContent('Above baseline')
    expect(legend).toHaveTextContent('Baseline unavailable or partial')
    await user.click(screen.getByRole('button',{name:'Hotspots'}))
    expect(screen.getByRole('button',{name:'Hotspots'})).toHaveAttribute('aria-pressed','true')
  })

  it('keeps polygons and the complete non-map path usable when raster tiles fail', async () => {
    const user=userEvent.setup()
    render(<PredictiveHarness/>)
    await user.click(screen.getByRole('button',{name:'Forecast'}))
    await screen.findByTestId('predictive-map')
    await user.click(screen.getByRole('button',{name:'Simulate predictive tile failure'}))
    expect(screen.getByRole('status')).toHaveTextContent('Base map tiles are unavailable')
    expect(screen.getByTestId('predictive-map')).toHaveAttribute('data-count','78')
    expect(screen.getAllByRole('button',{name:/select precinct/i})).toHaveLength(78)
  })

  it.each([
    ['missing-artifact','Precinct geography unavailable'],
    ['network','Precinct geography could not load'],
    ['stale','Precinct geography out of date'],
    ['invalid-contract','Precinct geography invalid'],
    ['incomplete-coverage','Precinct geography incomplete'],
    ['location-key-mismatch','Precinct geography key mismatch'],
  ] as const)('keeps list/detail available for the %s spatial state', async (code,title) => {
    const user=userEvent.setup()
    const spatialLoader=async()=>{
      throw new PrecinctSpatialReferenceError(code,'fixture spatial state')
    }
    render(<PredictiveHarness spatialLoader={spatialLoader}/>)
    await user.click(screen.getByRole('button',{name:'Forecast'}))
    expect(await screen.findByRole('heading',{name:title})).toBeInTheDocument()
    expect(screen.getAllByRole('button',{name:/select precinct/i})).toHaveLength(78)
    expect(screen.getByRole('complementary')).toHaveTextContent(/Expected aggregate reported-event volume/i)
    expect(screen.queryByTestId('predictive-map')).not.toBeInTheDocument()
    if (code === 'incomplete-coverage') {
      expect(screen.getByRole('status')).toHaveTextContent(
        'every precinct included in the Forecast contract',
      )
      expect(screen.getByRole('status')).not.toHaveTextContent(/\bpublished\b/i)
    }
  })

  it('does not reuse the fixed forecast for an unsupported historical range', async () => {
    const user=userEvent.setup()
    render(<PredictiveHarness/>)
    fireEvent.input(screen.getByLabelText('End week'),{target:{value:'2025-12-15'}})
    await user.click(screen.getByRole('button',{name:'Forecast'}))
    expect(await screen.findByRole('heading',{name:'Forecast unavailable for this historical selection'})).toBeInTheDocument()
  })

  it.each([
    ['missing','No forecast artifact'],
    ['invalid','Forecast artifact invalid'],
    ['stale','Forecast artifact stale'],
  ] as const)('renders a distinct %s Forecast artifact state', async (status,title) => {
    const contract=decodeForecastMap(structuredClone(forecastArtifact))
    contract.forecast.status=status
    contract.forecast.reason=`Fixture ${status} forecast.`
    contract.forecast.isEmpty=false
    const user=userEvent.setup()
    render(<PredictiveHarness forecastLoader={async()=>contract}/>)
    await user.click(screen.getByRole('button',{name:'Forecast'}))
    expect(await screen.findByRole('heading',{name:title})).toBeInTheDocument()
    expect(screen.queryByTestId('predictive-map')).not.toBeInTheDocument()
  })

  it('keeps available-empty Forecast distinct from a valid zero', async () => {
    const contract=decodeForecastMap(structuredClone(forecastArtifact))
    contract.forecast.rows=[]
    contract.forecast.isEmpty=true
    const user=userEvent.setup()
    render(<PredictiveHarness forecastLoader={async()=>contract}/>)
    await user.click(screen.getByRole('button',{name:'Forecast'}))
    expect(await screen.findByRole('heading',{name:'Forecast available but empty'})).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('not a zero forecast')
  })

  it.each([
    ['forecast-newer','Forecast is newer than Overview.'],
    ['forecast-older','Overview is newer than the Forecast observation horizon.'],
    ['overview-older','Overview does not reach the Forecast observation horizon.'],
  ] as const)('keeps the %s date mismatch explicit', async (kind,copy) => {
    const contract=decodeForecastMap(structuredClone(forecastArtifact))
    if(kind==='forecast-newer') contract.dataRange.safeEventEndDate='2026-01-01'
    if(kind==='forecast-older') contract.dataRange.safeEventEndDate='2025-12-30'
    if(kind==='overview-older') contract.dataRange.latestObservedWeek='2026-01-05'
    const user=userEvent.setup()
    render(<PredictiveHarness forecastLoader={async()=>contract}/>)
    await user.click(screen.getByRole('button',{name:'Forecast'}))
    expect(await screen.findByRole('heading',{name:'Overview and Forecast dates do not align'})).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(copy)
  })
})

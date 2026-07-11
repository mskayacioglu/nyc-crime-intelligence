import { ChevronDown, ListFilter, RotateCcw } from 'lucide-react'
import { useMemo, useState } from 'react'
import { precinctOptions } from '../data/aggregateOverview'
import type { OverviewFilters, OverviewMetadata } from '../types/overview'
import { displayDimension } from '../utils/format'

interface FilterToolbarProps {
  metadata: OverviewMetadata
  filters: OverviewFilters
  onChange: (filters: OverviewFilters) => void
  onReset: () => void
}

function SelectField({
  id,
  label,
  value,
  options,
  allLabel,
  disabled,
  onChange,
}: {
  id: string
  label: string
  value: number | null
  options: Array<{ index: number; label: string }>
  allLabel: string
  disabled?: boolean
  onChange: (index: number | null) => void
}) {
  return (
    <label className="filter-field" htmlFor={id}>
      <span>{label}</span>
      <select
        id={id}
        value={value ?? ''}
        disabled={disabled}
        onChange={(event) =>
          onChange(event.target.value === '' ? null : Number(event.target.value))
        }
      >
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option.index} value={option.index}>
            {displayDimension(option.label)}
          </option>
        ))}
      </select>
    </label>
  )
}

export function FilterToolbar({
  metadata,
  filters,
  onChange,
  onReset,
}: FilterToolbarProps) {
  const [expanded, setExpanded] = useState(false)
  const dimensions = metadata.dimensions
  const allowedPrecincts = useMemo(
    () => precinctOptions(metadata, filters.boroughIndex),
    [metadata, filters.boroughIndex],
  )
  const observedWeeks = useMemo(
    () =>
      new Set(
        dimensions.weeks.filter(
          (week) => week <= metadata.dataRange.lastWeek,
        ),
      ),
    [dimensions.weeks, metadata.dataRange.lastWeek],
  )

  const dimensionOptions = (values: string[]) =>
    values.map((label, index) => ({ index, label }))
  const activeScope = [
    filters.boroughIndex === null
      ? 'All boroughs'
      : displayDimension(dimensions.boroughs[filters.boroughIndex]),
    filters.precinctIndex === null
      ? 'All precincts'
      : `Precinct ${displayDimension(dimensions.precincts[filters.precinctIndex])}`,
    filters.offenseIndex === null
      ? 'All offenses'
      : displayDimension(dimensions.offenseTypes[filters.offenseIndex]),
    filters.lawIndex === null
      ? 'All law categories'
      : displayDimension(dimensions.lawCategories[filters.lawIndex]),
  ]

  return (
    <section className="filter-toolbar" aria-labelledby="filter-heading">
      <div className="filter-toolbar__heading">
        <div>
          <h2 id="filter-heading">
            <ListFilter aria-hidden="true" size={16} />
            Filters
          </h2>
        </div>
        <div className="filter-toolbar__actions">
          <button
            className="filter-collapse"
            type="button"
            aria-expanded={expanded}
            aria-controls="filter-controls"
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? 'Hide filters' : 'Show filters'}
            <ChevronDown aria-hidden="true" size={15} />
          </button>
          <button className="reset-button" type="button" onClick={onReset}>
            <RotateCcw aria-hidden="true" size={15} />
            Reset
          </button>
        </div>
      </div>
      <div
        id="filter-controls"
        className="filter-toolbar__body"
        data-expanded={expanded}
      >
        <label className="filter-field" htmlFor="start-week">
          <span>Start week</span>
          <input
            id="start-week"
            type="date"
            min={metadata.dataRange.firstWeek}
            max={filters.endWeek}
            step={7}
            required
            value={filters.startWeek}
            onInput={(event) => {
              const value = event.currentTarget.value
              if (
                observedWeeks.has(value) &&
                value >= metadata.dataRange.firstWeek &&
                value <= filters.endWeek
              ) {
                onChange({ ...filters, startWeek: value })
              }
            }}
          />
        </label>
        <label className="filter-field" htmlFor="end-week">
          <span>End week</span>
          <input
            id="end-week"
            type="date"
            min={filters.startWeek}
            max={metadata.dataRange.lastWeek}
            step={7}
            required
            value={filters.endWeek}
            onInput={(event) => {
              const value = event.currentTarget.value
              if (
                observedWeeks.has(value) &&
                value >= filters.startWeek &&
                value <= metadata.dataRange.lastWeek
              ) {
                onChange({ ...filters, endWeek: value })
              }
            }}
          />
        </label>
        <SelectField
          id="borough"
          label="Borough"
          allLabel="All boroughs"
          value={filters.boroughIndex}
          options={dimensionOptions(dimensions.boroughs)}
          onChange={(boroughIndex) => {
            const nextAllowed = precinctOptions(metadata, boroughIndex)
            const precinctIndex =
              filters.precinctIndex !== null &&
              nextAllowed.includes(filters.precinctIndex)
                ? filters.precinctIndex
                : null
            onChange({ ...filters, boroughIndex, precinctIndex })
          }}
        />
        <SelectField
          id="precinct"
          label="Precinct"
          allLabel={
            filters.boroughIndex === null ? 'All precincts' : 'All in borough'
          }
          value={filters.precinctIndex}
          options={allowedPrecincts.map((index) => ({
            index,
            label: dimensions.precincts[index],
          }))}
          disabled={filters.boroughIndex !== null && allowedPrecincts.length === 0}
          onChange={(precinctIndex) => onChange({ ...filters, precinctIndex })}
        />
        <SelectField
          id="offense"
          label="Offense type"
          allLabel="All offense types"
          value={filters.offenseIndex}
          options={dimensionOptions(dimensions.offenseTypes)}
          onChange={(offenseIndex) => onChange({ ...filters, offenseIndex })}
        />
        <SelectField
          id="law-category"
          label="Law category"
          allLabel="All law categories"
          value={filters.lawIndex}
          options={dimensionOptions(dimensions.lawCategories)}
          onChange={(lawIndex) => onChange({ ...filters, lawIndex })}
        />
      </div>
      <div className="filter-toolbar__meta">
        <p className="filter-semantics">
          Weeks begin Monday.
        </p>
        <p className="filter-active-scope" aria-live="polite">
          <strong>Active scope</strong> · {activeScope.join(' · ')}
        </p>
      </div>
    </section>
  )
}

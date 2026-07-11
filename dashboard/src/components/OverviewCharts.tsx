import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ObservedView, RankedValue } from '../types/overview'
import {
  displayDimension,
  formatCompact,
  formatInteger,
  formatShortDate,
} from '../utils/format'

interface TooltipEntry {
  color?: string
  name?: string
  value?: number | string
}

function ChartTooltip({
  active,
  label,
  payload,
}: {
  active?: boolean
  label?: number | string
  payload?: TooltipEntry[]
}) {
  if (!active || !payload?.length) return null
  const labelText = typeof label === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(label)
    ? formatShortDate(label)
    : label
  return (
    <div className="chart-tooltip">
      {labelText !== undefined && <strong>{labelText}</strong>}
      {payload.map((entry, index) => (
        <span key={`${entry.name ?? 'value'}-${index}`}>
          <i style={{ backgroundColor: entry.color }} aria-hidden="true" />
          {entry.name}: {formatInteger(Number(entry.value ?? 0))}
        </span>
      ))}
    </div>
  )
}

function EmptyChart({ message }: { message: string }) {
  return (
    <div className="panel-empty">
      <strong>No data</strong>
      <p>{message}</p>
    </div>
  )
}

function PanelHeading({
  id,
  title,
  meta,
}: {
  id: string
  title: string
  meta?: string
}) {
  return (
    <div className="panel-heading">
      <div>
        <h2 id={id}>{title}</h2>
      </div>
      {meta && <span className="panel-meta">{meta}</span>}
    </div>
  )
}

function WeeklyTrend({ view }: { view: ObservedView }) {
  return (
    <section className="analysis-panel trend-panel" aria-labelledby="trend-title">
      <div className="panel-heading">
        <div>
          <h2 id="trend-title">Weekly volume</h2>
        </div>
        <div className="chart-legend" aria-label="Chart legend">
          <span><i className="legend-observed" />Observed</span>
          <span><i className="legend-baseline" />8-week baseline</span>
        </div>
      </div>
      {view.isEmpty ? (
        <EmptyChart message="Change the filters or expand the selected week range." />
      ) : (
        <div className="chart chart--trend" data-testid="weekly-trend-chart">
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <ComposedChart
              data={view.weekly}
              margin={{ top: 14, right: 18, bottom: 6, left: 4 }}
              accessibilityLayer
            >
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis
                dataKey="week"
                minTickGap={48}
                tickFormatter={formatShortDate}
                tickLine={false}
                axisLine={{ stroke: 'var(--chart-axis)' }}
              />
              <YAxis
                width={48}
                tickFormatter={formatCompact}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: 'var(--chart-cursor)' }} />
              <Line
                type="monotone"
                dataKey="baseline"
                name="8-week baseline"
                stroke="var(--chart-baseline)"
                strokeWidth={1.5}
                strokeDasharray="5 5"
                dot={false}
                activeDot={false}
                isAnimationActive={false}
                connectNulls={false}
              />
              <Line
                type="monotone"
                dataKey="count"
                name="Observed events"
                stroke="var(--chart-observed)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 3, fill: 'var(--chart-observed)' }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}

function BoroughComparison({ values }: { values: RankedValue[] }) {
  return (
    <section className="analysis-panel borough-panel" aria-labelledby="borough-title">
      <PanelHeading
        id="borough-title"
        title="Borough volume"
      />
      {values.length === 0 ? (
        <EmptyChart message="No borough totals match the active filters." />
      ) : (
        <div className="chart chart--standard" data-testid="borough-chart">
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <BarChart data={values} margin={{ top: 12, right: 12, bottom: 28, left: 0 }} accessibilityLayer>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis
                dataKey="label"
                tickFormatter={(value: string) => value === 'STATEN ISLAND' ? 'S.I.' : value.slice(0, 8)}
                interval={0}
                tickLine={false}
                axisLine={{ stroke: 'var(--chart-axis)' }}
              />
              <YAxis width={44} tickFormatter={formatCompact} tickLine={false} axisLine={false} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--chart-hover)' }} />
              <Bar dataKey="value" name="Observed events" fill="var(--chart-observed)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}

function OffenseRanking({ values }: { values: RankedValue[] }) {
  const displayValues = values.map((value) => ({
    ...value,
    displayLabel: displayDimension(value.label),
  }))
  return (
    <section className="analysis-panel offense-panel" aria-labelledby="offense-title">
      <PanelHeading
        id="offense-title"
        title="Top offenses"
      />
      {values.length === 0 ? (
        <EmptyChart message="No offense totals match the active filters." />
      ) : (
        <div className="chart chart--standard" data-testid="offense-chart">
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <BarChart data={displayValues} layout="vertical" margin={{ top: 10, right: 24, bottom: 4, left: 8 }} accessibilityLayer>
              <CartesianGrid horizontal={false} stroke="var(--chart-grid)" />
              <XAxis type="number" tickFormatter={formatCompact} tickLine={false} axisLine={{ stroke: 'var(--chart-axis)' }} />
              <YAxis
                type="category"
                dataKey="displayLabel"
                width={156}
                tickFormatter={(value: string) => value.length > 23 ? `${value.slice(0, 21)}…` : value}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--chart-hover)' }} />
              <Bar dataKey="value" name="Observed events" fill="var(--chart-secondary)" radius={[0, 2, 2, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}

const lawColors = [
  'var(--chart-law-felony)',
  'var(--chart-law-misdemeanor)',
  'var(--chart-law-violation)',
]

function LawDistribution({ values }: { values: RankedValue[] }) {
  return (
    <section className="analysis-panel law-panel" aria-labelledby="law-title">
      <PanelHeading
        id="law-title"
        title="Law categories"
      />
      {values.length === 0 ? (
        <EmptyChart message="No law-category totals match the active filters." />
      ) : (
        <div className="law-layout">
          <div className="chart chart--law" data-testid="law-chart">
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <PieChart accessibilityLayer>
                <Tooltip content={<ChartTooltip />} />
                <Pie
                  data={values}
                  dataKey="value"
                  nameKey="label"
                  innerRadius="58%"
                  outerRadius="82%"
                  paddingAngle={1}
                  stroke="var(--surface-panel)"
                  strokeWidth={2}
                  isAnimationActive={false}
                >
                  {values.map((value) => (
                    <Cell key={value.index} fill={lawColors[value.index] ?? 'var(--chart-secondary)'} />
                  ))}
                </Pie>
                <Legend content={() => null} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="law-legend">
            {values.map((value) => (
              <li key={value.index}>
                <i style={{ backgroundColor: lawColors[value.index] }} aria-hidden="true" />
                <span>{value.label}</span>
                <strong>{formatInteger(value.value)}</strong>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

export default function OverviewCharts({ view }: { view: ObservedView }) {
  return (
    <div className="dashboard-grid">
      <WeeklyTrend view={view} />
      <BoroughComparison values={view.boroughs} />
      <OffenseRanking values={view.offenses} />
      <LawDistribution values={view.laws} />
    </div>
  )
}

import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

export type MetricTone = 'neutral' | 'analytical' | 'warning' | 'critical'

interface MetricCardProps {
  label: string
  value: ReactNode
  detail: ReactNode
  icon: LucideIcon
  tone?: MetricTone
  testId?: string
}

export function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
  tone = 'neutral',
  testId,
}: MetricCardProps) {
  return (
    <article className={`metric-card metric-card--${tone}`} data-testid={testId}>
      <div className="metric-card__heading">
        <span>{label}</span>
        <Icon aria-hidden="true" size={17} />
      </div>
      <div className="metric-card__value">{value}</div>
      <div className="metric-card__detail">{detail}</div>
    </article>
  )
}

const integerFormatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const decimalFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})
const compactFormatter = new Intl.NumberFormat('en-US', {
  notation: 'compact',
  maximumFractionDigits: 1,
})
const dateFormatter = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  timeZone: 'UTC',
})
const shortDateFormatter = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  timeZone: 'UTC',
})

export function formatInteger(value: number): string {
  return integerFormatter.format(value)
}

export function formatDecimal(value: number): string {
  return decimalFormatter.format(value)
}

export function formatCompact(value: number): string {
  return compactFormatter.format(value)
}

function isoDate(value: string): Date {
  return new Date(`${value}T00:00:00Z`)
}

export function formatDate(value: string): string {
  return dateFormatter.format(isoDate(value))
}

export function formatShortDate(value: string): string {
  return shortDateFormatter.format(isoDate(value))
}

export function displayDimension(value: string): string {
  if (value === 'UNKNOWN') return 'Unknown / not reported'
  return value
}

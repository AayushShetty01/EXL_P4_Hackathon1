/* Formats percentages, metrics, and elapsed time consistently. */
/** Formats a nullable value as a percentage. */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  return value == null ? '—' : `${(value * 100).toFixed(digits)}%`
}

/** Formats a metric and uses scientific notation for very small differences. */
export function formatMetric(value: number | null | undefined, digits = 3): string {
  if (value == null || !Number.isFinite(value)) return '—'
  if (value !== 0 && Math.abs(value) < 0.0001) return value.toExponential(2)
  return value.toFixed(digits)
}

/** Formats an integer using the browser's locale conventions. */
export function formatCount(value: number | null | undefined): string {
  return value == null ? '—' : new Intl.NumberFormat().format(value)
}

/** Formats seconds as a readable duration. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  if (seconds < 60) return `${seconds.toFixed(1)} sec`
  return `${(seconds / 60).toFixed(1)} min`
}

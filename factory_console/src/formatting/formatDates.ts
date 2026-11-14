/* Formats UTC dates and timestamps for readable audit and inventory views. */
/** Formats a date-only value without shifting its calendar day. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return 'Not recorded'
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`)
  return Number.isNaN(date.valueOf())
    ? 'Invalid date'
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' }).format(date)
}

/** Formats an ISO timestamp in the browser's local timezone. */
export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return 'Not recorded'
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? 'Invalid timestamp'
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(date)
}

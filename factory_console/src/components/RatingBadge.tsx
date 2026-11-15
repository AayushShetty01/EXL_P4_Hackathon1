/* Displays a validation rating with its matching icon and label. */
import type { Rating } from '../api/types'
import { statusPresentation } from '../formatting/statusStyles'

/** Shows a rating or an accessible empty state when none exists. */
export function RatingBadge({ rating }: { rating: Rating | null }) {
  if (!rating) return <span className="text-sm text-slate-500">Not rated</span>
  const { label, className, Icon } = statusPresentation(rating)
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}>
      <Icon size={14} aria-hidden="true" />
      {label}
    </span>
  )
}

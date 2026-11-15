/* Displays the model's assigned materiality tier. */
import type { Tier } from '../api/types'
import { NOT_DISCOVERED } from '../formatting/statusStyles'

/** Shows a model tier using a consistent visual badge. */
export function TierBadge({ tier }: { tier: Tier | null }) {
  if (!tier) return <span className="text-sm text-slate-500">{NOT_DISCOVERED}</span>
  const color =
    tier === 'Tier 1'
      ? 'border-violet-200 bg-violet-50 text-violet-800'
      : tier === 'Tier 2'
        ? 'border-blue-200 bg-blue-50 text-blue-800'
        : 'border-slate-200 bg-slate-100 text-slate-700'
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${color}`}>
      {tier}
    </span>
  )
}

/* Gives unavailable or not-yet-produced data a clear explanation. */
import { Inbox } from 'lucide-react'
import type { ReactNode } from 'react'

/** Shows an informative empty state with an optional action. */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
      <Inbox size={24} className="text-slate-400" aria-hidden="true" />
      <h3 className="mt-3 font-semibold text-slate-800">{title}</h3>
      <p className="mt-1 max-w-md text-sm text-slate-500">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

/* Renders a headline metric with an icon and optional context. */
import type { ReactNode } from 'react'

/** Shows one metric value, label, and supporting text. */
export function MetricCard({
  label,
  value,
  description,
  icon,
}: {
  label: string
  value: string
  description?: string
  icon: ReactNode
}) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-slate-600">{label}</p>
        <span className="rounded-lg bg-teal-50 p-2 text-teal-800" aria-hidden="true">
          {icon}
        </span>
      </div>
      <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
      {description && <p className="mt-1 text-xs text-slate-500">{description}</p>}
    </article>
  )
}

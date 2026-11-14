/* Presents mapped model-risk principles and evidence coverage. */
import { useState } from 'react'
import { useCompliance } from '../api/hooks'
import type { Evidence } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { EvidenceDrawer } from '../components/EvidenceDrawer'

/** Shows the compliance mapping and evidence status for each expectation. */
export function ComplianceTab({ modelId }: { modelId: string }) {
  const query = useCompliance(modelId)
  const [evidence, setEvidence] = useState<Evidence | null>(null)

  if (query.isLoading) return <p className="py-8 text-sm text-slate-500" role="status">Loading compliance mapping…</p>
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />
  if (!query.data) {
    return <EmptyState title="Compliance mapping not available" description="No principle mapping is available for this model in the current data source." />
  }

  const { coverage, principles, disclaimer } = query.data
  const total = coverage.met + coverage.partial + coverage.not_met + coverage.out_of_scope

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
        <p className="font-semibold">Scope note</p>
        <p className="mt-1">{disclaimer}</p>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Summary label="Expectations mapped" value={String(total)} />
        <Summary label="Met" value={String(coverage.met)} />
        <Summary label="Partial" value={String(coverage.partial)} />
        <Summary label="Not met" value={String(coverage.not_met)} />
        <Summary label="Out of scope" value={String(coverage.out_of_scope)} />
      </section>

      <div className="space-y-4">
        {principles.map((principle) => (
          <section key={principle.principle} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <header className="border-b border-slate-200 px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-teal-800">{principle.principle}</p>
              <h3 className="mt-1 font-semibold text-slate-900">{principle.title}</h3>
            </header>
            <ul className="divide-y divide-slate-100">
              {principle.items.map((item) => {
                const evidencePath = item.evidence_path
                return (
                  <li key={item.id} className="flex flex-wrap items-start justify-between gap-3 px-5 py-4">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-800">{item.expectation}</p>
                      {item.note && <p className="mt-1 text-sm text-slate-600">{item.note}</p>}
                      {evidencePath ? (
                        <button
                          type="button"
                          className="mt-2 break-all text-left text-xs font-semibold text-teal-800 hover:underline"
                          onClick={() => setEvidence({ file: evidencePath, start_line: 1, end_line: 1, quote: `Compliance evidence for ${item.id}.` })}
                        >
                          Evidence: {evidencePath}
                        </button>
                      ) : <p className="mt-2 text-xs text-slate-500">No evidence artifact linked.</p>}
                    </div>
                    <StatusBadge status={item.status} />
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </div>
      <EvidenceDrawer evidence={evidence} onClose={() => setEvidence(null)} />
    </div>
  )
}

function Summary({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><p className="text-xs text-slate-500">{label}</p><p className="mt-2 text-2xl font-semibold text-slate-950">{value}</p></div>
}

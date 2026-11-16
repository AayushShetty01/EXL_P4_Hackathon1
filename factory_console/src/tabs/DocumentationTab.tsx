/* Presents generated documentation, claim grounding, and detected drift. */
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { useDocumentation } from '../api/hooks'
import type { Evidence } from '../api/types'
import { formatDate } from '../formatting/formatDates'
import { formatPercent } from '../formatting/formatNumbers'
import { StatusBadge } from '../components/StatusBadge'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'
import { EvidenceDrawer } from '../components/EvidenceDrawer'

/** Shows the evidence-grounded model document and its drift comparison. */
export function DocumentationTab({ modelId }: { modelId: string }) {
  const query = useDocumentation(modelId)
  const [evidence, setEvidence] = useState<Evidence | null>(null)

  if (query.isLoading) return <Loading label="documentation" />
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />
  if (!query.data) {
    return <EmptyState title="Documentation not available" description="No generated documentation is available for this model in the current data source." />
  }

  const documentation = query.data

  return (
    <div className="space-y-6">
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard label="Groundedness" value={formatPercent(documentation.groundedness.score)} />
        <SummaryCard label="Verified claims" value={`${documentation.groundedness.claims_verified} / ${documentation.groundedness.claims_total}`} />
        <SummaryCard label="Unverified claims" value={String(documentation.groundedness.claims_unverified)} />
        <SummaryCard label="SME input needed" value={String(documentation.groundedness.claims_sme_input_needed)} />
      </section>

      <div className="flex flex-wrap justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 text-sm">
        <p><span className="text-slate-500">Generated:</span> {formatDate(documentation.generated_at)}</p>
        <p><span className="text-slate-500">Generator:</span> {documentation.generated_by_model}</p>
        <p className="break-all"><span className="text-slate-500">Artifact:</span> {documentation.markdown_path}</p>
      </div>

      <section className="space-y-4">
        <h3 className="text-lg font-semibold text-slate-900">Documentation and cited claims</h3>
        {documentation.sections.map((section) => (
          <article key={section.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h4 className="font-semibold text-slate-900">{section.title}</h4>
            <div className="prose prose-sm mt-3 max-w-none text-slate-700">
              <ReactMarkdown>{section.markdown}</ReactMarkdown>
            </div>
            {section.claims.length > 0 && (
              <ul className="mt-4 space-y-3 border-t border-slate-100 pt-4">
                {section.claims.map((claim) => (
                  <li key={claim.id} className="rounded-lg bg-slate-50 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-medium text-slate-800">{claim.id}: {claim.text}</p>
                      <StatusBadge status={claim.status} />
                    </div>
                    {claim.evidence.length > 0 ? (
                      <ul className="mt-2 space-y-1">
                        {claim.evidence.map((item, index) => (
                          <li key={`${claim.id}-${item.file}-${item.start_line}-${index}`}>
                            <EvidenceButton evidence={item} onClick={setEvidence} />
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 text-xs text-amber-800">No source citation is available for this claim.</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </article>
        ))}
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-5 py-4">
          <h3 className="font-semibold text-slate-900">Documentation drift</h3>
          <p className="mt-1 text-sm text-slate-500">Differences between the legacy document and source code require human review.</p>
        </div>
        {documentation.doc_drift.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-[760px] w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="px-5 py-3">Severity / topic</th>
                  <th scope="col" className="px-5 py-3">Legacy document</th>
                  <th scope="col" className="px-5 py-3">Source code</th>
                  <th scope="col" className="px-5 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {documentation.doc_drift.map((item) => (
                  <tr key={item.id} className="align-top">
                    <th scope="row" className="px-5 py-4 font-medium text-slate-900">
                      <StatusBadge status={item.severity} />
                      <p className="mt-2">{item.topic}</p>
                    </th>
                    <td className="px-5 py-4 text-slate-700">
                      <p>{item.legacy_doc_says}</p>
                      <EvidenceButton evidence={item.legacy_evidence} onClick={setEvidence} />
                    </td>
                    <td className="px-5 py-4 text-slate-700">
                      <p>{item.code_says}</p>
                      <EvidenceButton evidence={item.code_evidence} onClick={setEvidence} />
                    </td>
                    <td className="px-5 py-4"><StatusBadge status={item.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No drift items" description="No documentation differences were returned." />
        )}
      </section>
      <EvidenceDrawer evidence={evidence} onClose={() => setEvidence(null)} />
    </div>
  )
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-950">{value}</p>
    </div>
  )
}

function EvidenceButton({ evidence, onClick }: { evidence: Evidence | null; onClick: (evidence: Evidence) => void }) {
  if (!evidence) return <p className="mt-2 text-xs text-slate-500">No evidence cited</p>
  return (
    <button
      type="button"
      className="mt-2 block break-all text-left text-xs font-semibold text-teal-800 hover:underline"
      onClick={() => onClick(evidence)}
    >
      {evidence.file}:{evidence.start_line}–{evidence.end_line}
    </button>
  )
}

function Loading({ label }: { label: string }) {
  return <p className="py-8 text-sm text-slate-500" role="status">Loading {label}…</p>
}

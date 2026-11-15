/* Loads and displays cited source lines in a side drawer. */
import { lazy, Suspense } from 'react'
import { X } from 'lucide-react'
import { useFile } from '../api/hooks'
import type { Evidence } from '../api/types'
import { ErrorState } from './ErrorState'
import { EmptyState } from './EmptyState'

const CodeViewer = lazy(() => import('./CodeViewer').then((module) => ({ default: module.CodeViewer })))

/** Shows the file and highlighted lines supporting a claim or field. */
export function EvidenceDrawer({
  evidence,
  onClose,
}: {
  evidence: Evidence | null
  onClose: () => void
}) {
  const fileQuery = useFile(evidence?.file ?? null)

  if (!evidence) return null

  return (
    <div className="fixed inset-0 z-40 bg-slate-950/30" role="presentation" onMouseDown={onClose}>
      <aside
        className="absolute inset-y-0 right-0 flex w-full max-w-3xl flex-col bg-white shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-drawer-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-teal-800">Cited evidence</p>
            <h2 id="evidence-drawer-title" className="mt-1 truncate text-lg font-semibold text-slate-950">{evidence.file}</h2>
            <p className="mt-2 text-sm text-slate-600">Lines {evidence.start_line}–{evidence.end_line}</p>
          </div>
          <button type="button" className="rounded-md p-2 text-slate-500 hover:bg-slate-100" onClick={onClose} aria-label="Close evidence">
            <X size={20} />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-5">
          <blockquote className="mb-4 border-l-4 border-teal-700 bg-teal-50 px-4 py-3 text-sm text-teal-950">
            {evidence.quote}
          </blockquote>
          {fileQuery.isLoading ? (
            <p className="py-8 text-sm text-slate-500" role="status">Loading cited source…</p>
          ) : fileQuery.error ? (
            <ErrorState error={fileQuery.error} retry={() => void fileQuery.refetch()} />
          ) : fileQuery.data ? (
            <Suspense fallback={<p className="py-8 text-sm text-slate-500" role="status">Loading source viewer…</p>}>
              <CodeViewer
                file={fileQuery.data}
                highlightStart={evidence.start_line}
                highlightEnd={evidence.end_line}
              />
            </Suspense>
          ) : (
            <EmptyState
              title="Evidence file is unavailable"
              description="The API or snapshot does not contain this cited file."
            />
          )}
        </div>
      </aside>
    </div>
  )
}

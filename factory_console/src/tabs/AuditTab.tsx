/* Presents model audit events and the service-reported chain validation state. */
import { useAudit } from '../api/hooks'
import { formatTimestamp } from '../formatting/formatDates'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'

/** Lists model-scoped events with actor, action, detail, and hash linkage. */
export function AuditTab({ modelId }: { modelId: string }) {
  const query = useAudit(modelId)

  if (query.isLoading) return <p className="py-8 text-sm text-slate-500" role="status">Loading audit events…</p>
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />
  if (!query.data) {
    return <EmptyState title="Audit events not available" description="No audit log is available for this model in the current data source." />
  }

  const { chain_valid: chainValid, events } = query.data

  return (
    <div className="space-y-5">
      <section className={`rounded-xl border p-5 ${chainValid ? 'border-emerald-200 bg-emerald-50' : 'border-rose-300 bg-rose-50'}`}>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Audit hash chain</p>
        <h3 className={`mt-1 text-lg font-semibold ${chainValid ? 'text-emerald-950' : 'text-rose-950'}`}>
          {chainValid ? 'Chain reported valid' : 'Chain validation failed'}
        </h3>
        <p className="mt-1 text-sm text-slate-700">
          This status is supplied by the API or fixture; the console does not independently recompute event hashes.
        </p>
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-5 py-4">
          <h3 className="font-semibold text-slate-900">Audit events</h3>
          <p className="mt-1 text-sm text-slate-500">{events.length} events for {modelId}</p>
        </div>
        {events.length ? (
          <ol className="divide-y divide-slate-100">
            {events.map((event) => (
              <li key={`${event.seq}-${event.hash}`} className="px-5 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-slate-900">#{event.seq} · {event.action.replaceAll('_', ' ')}</p>
                    <p className="mt-1 text-sm text-slate-600">{event.actor} ({event.actor_type}) · {formatTimestamp(event.ts)}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {event.stage ? `Stage: ${event.stage}` : 'No stage'}{event.run_id ? ` · Run: ${event.run_id}` : ''}
                    </p>
                  </div>
                  <pre className="max-w-full overflow-x-auto rounded-md bg-slate-50 p-3 text-xs text-slate-700">{JSON.stringify(event.detail, null, 2)}</pre>
                </div>
                <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
                  <div className="min-w-0"><dt className="text-slate-500">Previous hash</dt><dd className="mt-1 break-all font-mono text-slate-700">{event.prev_hash}</dd></div>
                  <div className="min-w-0"><dt className="text-slate-500">Event hash</dt><dd className="mt-1 break-all font-mono text-slate-700">{event.hash}</dd></div>
                </dl>
              </li>
            ))}
          </ol>
        ) : <EmptyState title="No audit events" description="No events were recorded for this model." />}
      </section>
    </div>
  )
}

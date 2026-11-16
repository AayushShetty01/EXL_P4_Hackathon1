/* Presents monitoring batches, thresholds, alerts, and revalidation triggers. */
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ReactNode } from 'react'
import { useMonitoring } from '../api/hooks'
import { formatMetric, formatPercent } from '../formatting/formatNumbers'
import { RatingBadge } from '../components/RatingBadge'
import { StatusBadge } from '../components/StatusBadge'
import { ChartCard } from '../components/ChartCard'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { formatResultError } from '../formatting/statusStyles'

/** Shows simulated or recorded drift and its revalidation decision. */
export function MonitoringTab({ modelId }: { modelId: string }) {
  const query = useMonitoring(modelId)

  if (query.isLoading) return <p className="py-8 text-sm text-slate-500" role="status">Loading monitoring results…</p>
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />
  if (!query.data) {
    return <EmptyState title="Monitoring results not available" description="No monitoring batches are available for this model in the current data source." />
  }

  const result = query.data

  return (
    <div className="space-y-6">
      <section className={`rounded-xl border p-5 ${result.revalidation_triggered ? 'border-rose-300 bg-rose-50' : 'border-slate-200 bg-white'}`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Monitoring status</p>
            <h3 className="mt-1 text-lg font-semibold text-slate-950">
              {result.revalidation_triggered ? 'Revalidation required' : 'No revalidation trigger'}
            </h3>
            <p className="mt-1 text-sm text-slate-700">
              {result.trigger_reason ?? 'No trigger reason was recorded.'}
            </p>
          </div>
          <div className="flex items-center gap-2"><StatusBadge status={result.status} />{result.simulated && <StatusBadge status="SIMULATED" />}</div>
        </div>
      </section>

      {result.error && <p className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900" role="alert">{formatResultError(result.error)}</p>}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Summary label="Reference sample" value={result.reference_sample} />
        <Summary label="Batches monitored" value={String(result.batches.length)} />
        <Summary label="Alerts raised" value={String(result.alerts.length)} />
        <Summary label="Revalidation trigger" value={result.revalidation_triggered ? 'Yes' : 'No'} />
      </section>

      <ChartCard title="Population stability over time" description={`Green below ${formatMetric(result.thresholds_used.psi_green)} · amber below ${formatMetric(result.thresholds_used.psi_amber)}`} height={300}>
        {result.batches.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={result.batches} margin={{ top: 10, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="batch" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line type="monotone" dataKey="psi_score" name="Score PSI" stroke="#287e83" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="max_csi.csi" name="Max feature CSI" stroke="#d47b24" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        ) : <EmptyState title="No monitoring batches" description="No batch values were returned." />}
      </ChartCard>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-5 py-4">
          <h3 className="font-semibold text-slate-900">Monitoring batches</h3>
          <p className="mt-1 text-sm text-slate-500">Reference: {result.reference_sample} · Outcome measures are shown only when available.</p>
        </div>
        {result.batches.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-[900px] w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>{['Batch', 'N', 'PSI', 'Max CSI', 'AUC', 'Default rate', 'Mean PD', 'Alert'].map((heading) => <th key={heading} scope="col" className="px-4 py-3">{heading}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {result.batches.map((batch) => (
                  <tr key={batch.batch}>
                    <th scope="row" className="px-4 py-3 font-medium text-slate-800">{batch.batch}</th>
                    <td className="px-4 py-3">{batch.n.toLocaleString()}</td>
                    <td className="px-4 py-3">{formatMetric(batch.psi_score)}</td>
                    <td className="px-4 py-3">{batch.max_csi ? `${batch.max_csi.feature}: ${formatMetric(batch.max_csi.csi)}` : 'None'}</td>
                    <td className="px-4 py-3">{formatMetric(batch.auc)}</td>
                    <td className="px-4 py-3">{formatPercent(batch.observed_default_rate)}</td>
                    <td className="px-4 py-3">{formatPercent(batch.mean_pd)}</td>
                    <td className="px-4 py-3"><RatingBadge rating={batch.alert} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <EmptyState title="No monitoring batches" description="No batch values were returned." />}
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <Panel title="Alerts">
          {result.alerts.length ? (
            <ul className="space-y-3">
              {result.alerts.map((alert, index) => (
                <li key={`${alert.batch}-${alert.rule}-${index}`} className="flex flex-wrap items-start justify-between gap-3 rounded-lg bg-slate-50 p-3">
                  <div><p className="font-semibold text-slate-800">{alert.batch} · {alert.rule}</p><p className="mt-1 text-sm text-slate-600">Observed value: {formatMetric(alert.value)}</p></div>
                  <RatingBadge rating={alert.level} />
                </li>
              ))}
            </ul>
          ) : <EmptyState title="No alerts" description="No monitoring alerts were returned." />}
        </Panel>
        <Panel title="Trigger thresholds">
          <dl className="space-y-3 text-sm">
            <Threshold name="PSI green threshold" value={result.thresholds_used.psi_green} />
            <Threshold name="PSI amber threshold" value={result.thresholds_used.psi_amber} />
            <Threshold name="AUC drop trigger" value={result.thresholds_used.auc_drop_trigger} />
          </dl>
          <p className="mt-4 break-all text-xs text-slate-500">Result artifact: {result.result_path}</p>
        </Panel>
      </section>
    </div>
  )
}

function Summary({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><p className="text-xs text-slate-500">{label}</p><p className="mt-2 text-xl font-semibold text-slate-950">{value}</p></div>
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><h3 className="mb-4 font-semibold text-slate-900">{title}</h3>{children}</section>
}

function Threshold({ name, value }: { name: string; value: number }) {
  return <div className="flex justify-between gap-3 border-b border-slate-100 pb-2"><dt className="text-slate-600">{name}</dt><dd className="font-medium text-slate-900">{formatMetric(value)}</dd></div>
}

/* Shows factory-wide metrics, estate composition, and pipeline progress. */
import {
  Archive,
  CheckCircle2,
  Clock3,
  FileCheck2,
  FileText,
  Fingerprint,
  RefreshCw,
  ScanSearch,
  ShieldAlert,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Link } from 'react-router-dom'
import { apiMode } from '../api/client'
import { useFactoryMetrics, useModels, useScanEstate } from '../api/hooks'
import { ChartCard } from '../components/ChartCard'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { MetricCard } from '../components/MetricCard'
import { StatusBadge } from '../components/StatusBadge'
import { formatCount, formatMetric } from '../formatting/formatNumbers'
import type { ModelSummary } from '../api/types'

const stages = ['discover', 'document', 'redevelop', 'validate', 'monitor'] as const

/** Renders the dashboard and refreshes the inventory through factory_core. */
export function DashboardPage() {
  const modelsQuery = useModels()
  const metricsQuery = useFactoryMetrics()
  const scanMutation = useScanEstate()
  const models = modelsQuery.data ?? []
  const metrics = metricsQuery.data
  const isLoading = modelsQuery.isLoading || metricsQuery.isLoading
  const error = modelsQuery.error ?? metricsQuery.error

  if (isLoading) {
    return <p className="p-8 text-sm text-slate-500" role="status">Loading factory dashboard…</p>
  }
  if (error) {
    return <ErrorState error={error} retry={() => void Promise.all([modelsQuery.refetch(), metricsQuery.refetch()])} />
  }
  if (!metrics || models.length === 0) {
    return (
      <EmptyState
        title="No factory data available"
        description="Scan the estate to load model inventory and factory metrics."
        action={<ScanEstateButton disabled={apiMode === 'snapshot'} onClick={() => scanMutation.mutate()} />}
      />
    )
  }

  const tierData = Object.entries(metrics.by_tier).map(([name, count]) => ({ name, count }))
  const languageData = Object.entries(metrics.by_language).map(([name, count]) => ({ name, count }))
  const findingTotal = Object.values(metrics.open_findings).reduce((sum, count) => sum + count, 0)
  const baseline = metrics.manual_baseline_weeks_per_validation

  return (
    <div className="space-y-7">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-teal-800">Portfolio overview</p>
          <h2 className="mt-1 text-2xl font-semibold text-slate-950">Factory dashboard</h2>
          <p className="mt-1 text-sm text-slate-600">Model inventory, evidence progress, and review workload.</p>
        </div>
        <div className="flex items-center gap-3">
          {scanMutation.error && <span className="max-w-xs text-sm text-rose-700">{scanMutation.error.message}</span>}
          <ScanEstateButton
            disabled={apiMode === 'snapshot' || scanMutation.isPending}
            onClick={() => scanMutation.mutate()}
            busy={scanMutation.isPending}
          />
        </div>
      </header>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Factory headline metrics">
        <MetricCard label="Models in inventory" value={formatCount(metrics.models_total)} icon={<Archive size={18} />} />
        <MetricCard label="Documents outdated at discovery" value={formatCount(metrics.docs_outdated_at_discovery)} icon={<FileText size={18} />} />
        <MetricCard label="Documents regenerated" value={formatCount(metrics.docs_generated)} icon={<FileCheck2 size={18} />} />
        <MetricCard label="Parity certificates" value={formatCount(metrics.parity_certificates_issued)} icon={<Fingerprint size={18} />} />
        <MetricCard label="Validations completed" value={formatCount(metrics.validations_completed)} icon={<CheckCircle2 size={18} />} />
        <MetricCard
          label="Open findings"
          value={formatCount(findingTotal)}
          description={`High ${metrics.open_findings.HIGH} · Medium ${metrics.open_findings.MEDIUM} · Low ${metrics.open_findings.LOW}`}
          icon={<ShieldAlert size={18} />}
        />
        <MetricCard label="Revalidation triggers" value={formatCount(metrics.revalidation_triggers)} icon={<RefreshCw size={18} />} />
        <MetricCard label="Average groundedness" value={formatMetric(metrics.avg_groundedness * 100, 1) + '%'} icon={<CheckCircle2 size={18} />} />
      </section>

      <section className="grid gap-4 lg:grid-cols-[1fr_1.7fr]">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <Clock3 size={18} className="text-teal-800" aria-hidden="true" />
            <h3 className="font-semibold text-slate-900">Time per model</h3>
          </div>
          <div className="mt-5 grid grid-cols-2 gap-4">
            <TimeValue label="Average agent time" value={`${formatMetric(metrics.avg_agent_minutes_per_model, 1)} min`} />
            <TimeValue label="Human review logged" value={`${formatMetric(metrics.human_review_minutes_logged, 1)} min`} />
            <TimeValue label="Manual validation baseline" value={`${baseline[0]}–${baseline[1]} weeks`} />
          </div>
          <p className="mt-4 text-xs text-slate-500">Baseline from the challenge brief. Factory preparation does not replace human review and sign-off.</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <ChartCard title="Models by tier" height={230}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={tierData} margin={{ top: 8, right: 12, bottom: 4, left: -18 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#287e83" radius={[5, 5, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
          <ChartCard title="Models by language" height={230}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={languageData} margin={{ top: 8, right: 12, bottom: 4, left: -18 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#426796" radius={[5, 5, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <h3 className="font-semibold text-slate-900">Pipeline board</h3>
            <p className="mt-1 text-xs text-slate-500">Select a model to open its passport and review gates.</p>
          </div>
          <Link className="text-sm font-semibold text-teal-800 hover:underline" to="/models">View inventory</Link>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[900px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="px-5 py-3">Model</th>
                {stages.map((stage) => <th scope="col" key={stage} className="px-3 py-3 capitalize">{stage}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {models.map((model) => <PipelineRow key={model.model_id} model={model} />)}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

/** Shows the inventory scan action with its loading state. */
function ScanEstateButton({
  onClick,
  disabled,
  busy = false,
}: {
  onClick: () => void
  disabled: boolean
  busy?: boolean
}) {
  return (
    <button
      type="button"
      className="inline-flex items-center gap-2 rounded-lg bg-teal-800 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-900 disabled:cursor-not-allowed disabled:opacity-50"
      onClick={onClick}
      disabled={disabled}
    >
      <ScanSearch size={16} aria-hidden="true" />
      {busy ? 'Scanning…' : 'Scan estate'}
    </button>
  )
}

/** Renders one compact time metric. */
function TimeValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 font-semibold text-slate-900">{value}</p>
    </div>
  )
}

/** Renders a model row and its five stage statuses. */
function PipelineRow({ model }: { model: ModelSummary }) {
  return (
    <tr className="hover:bg-slate-50">
      <th scope="row" className="px-5 py-3 font-medium">
        <Link to={`/models/${model.model_id}`} className="text-slate-900 hover:text-teal-800">
          <span className="block text-xs text-slate-500">{model.model_id}</span>
          <span>{model.model_name}</span>
        </Link>
      </th>
      {stages.map((stage) => (
        <td className="px-3 py-3" key={stage}>
          <StatusBadge status={model.pipeline_status[stage]} />
        </td>
      ))}
    </tr>
  )
}

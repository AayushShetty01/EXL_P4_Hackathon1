/* Loads a model's inventory and renders its passport workspace. */
import { lazy, Suspense } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useModels, useModel, useRun, useStartRun } from '../api/hooks'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { RatingBadge } from '../components/RatingBadge'
import { TierBadge } from '../components/TierBadge'
import { PassportTab } from '../tabs/PassportTab'

const AuditTab = lazy(() => import('../tabs/AuditTab').then((module) => ({ default: module.AuditTab })))
const ComplianceTab = lazy(() => import('../tabs/ComplianceTab').then((module) => ({ default: module.ComplianceTab })))
const DocumentationTab = lazy(() => import('../tabs/DocumentationTab').then((module) => ({ default: module.DocumentationTab })))
const MonitoringTab = lazy(() => import('../tabs/MonitoringTab').then((module) => ({ default: module.MonitoringTab })))
const RedevelopmentTab = lazy(() => import('../tabs/RedevelopmentTab').then((module) => ({ default: module.RedevelopmentTab })))
const ValidationTab = lazy(() => import('../tabs/ValidationTab').then((module) => ({ default: module.ValidationTab })))

const modelTabs = [
  { id: 'passport', label: 'Passport' },
  { id: 'documentation', label: 'Documentation' },
  { id: 'redevelopment', label: 'Redevelopment' },
  { id: 'validation', label: 'Validation' },
  { id: 'monitoring', label: 'Monitoring' },
  { id: 'compliance', label: 'Compliance' },
  { id: 'audit', label: 'Audit' },
] as const

/** Shows the selected model header and its evidence workspaces. */
export function ModelDetailPage() {
  const { modelId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab')
  const activeTab = modelTabs.find((tab) => tab.id === requestedTab)?.id ?? 'passport'
  const modelQuery = useModel(modelId)
  const modelsQuery = useModels()
  const modelSummary = modelsQuery.data?.find((item) => item.model_id === modelId)
  const runQuery = useRun(
    modelId,
    activeTab === 'passport' ? modelSummary?.active_run_id ?? null : null,
  )
  const startMutation = useStartRun()

  if (modelQuery.isLoading || modelsQuery.isLoading) {
    return <p className="p-8 text-sm text-slate-500" role="status">Loading model passport…</p>
  }
  if (modelQuery.error || modelsQuery.error) {
    return <ErrorState error={modelQuery.error ?? modelsQuery.error} retry={() => {
      void modelQuery.refetch()
      void modelsQuery.refetch()
    }} />
  }
  if (activeTab === 'passport' && runQuery.error) {
    return <ErrorState error={runQuery.error} retry={() => void runQuery.refetch()} />
  }
  if (!modelQuery.data || !modelSummary) {
    return (
      <EmptyState
        title="Model not found"
        description={`No inventory record is available for ${modelId || 'this model'}.`}
        action={<Link className="font-semibold text-teal-800 hover:underline" to="/models">Return to inventory</Link>}
      />
    )
  }

  /** Starts a review-gated run through all applicable stages. */
  function startModelRun() {
    startMutation.mutate({
      modelId,
      request: {
        stages: ['discover', 'document', 'redevelop', 'validate', 'monitor'],
        auto_approve: false,
      },
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/models" className="text-sm font-medium text-teal-800 hover:underline">← Model inventory</Link>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <h2 className="text-2xl font-semibold text-slate-950">{modelQuery.data.model_name}</h2>
            <TierBadge tier={modelQuery.data.tiering.tier} />
            <RatingBadge rating={modelSummary.overall_rating} />
          </div>
          <p className="mt-2 text-sm text-slate-600">
            {modelQuery.data.model_id} · {modelQuery.data.language} · {modelQuery.data.model_owner}
          </p>
        </div>
      </div>

      <div className="overflow-x-auto border-b border-slate-200">
        <nav className="flex min-w-max gap-5" aria-label="Model workspaces">
          {modelTabs.map((tab) => (
            <Link
              key={tab.id}
              to={`?tab=${tab.id}`}
              aria-current={activeTab === tab.id ? 'page' : undefined}
              className={`border-b-2 px-1 pb-3 text-sm font-semibold ${
                activeTab === tab.id
                  ? 'border-teal-800 text-teal-900'
                  : 'border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-800'
              }`}
            >
              {tab.label}
            </Link>
          ))}
        </nav>
      </div>

      <Suspense fallback={<p className="py-8 text-sm text-slate-500" role="status">Loading workspace…</p>}>
        {activeTab === 'passport' && (
          <PassportTab
            model={modelQuery.data}
            run={runQuery.data ?? null}
            runLoading={runQuery.isLoading}
            onStartRun={startModelRun}
            startPending={startMutation.isPending}
            startError={startMutation.error?.message ?? null}
          />
        )}
        {activeTab === 'documentation' && <DocumentationTab modelId={modelId} />}
        {activeTab === 'redevelopment' && <RedevelopmentTab modelId={modelId} />}
        {activeTab === 'validation' && <ValidationTab modelId={modelId} />}
        {activeTab === 'monitoring' && <MonitoringTab modelId={modelId} />}
        {activeTab === 'compliance' && <ComplianceTab modelId={modelId} />}
        {activeTab === 'audit' && <AuditTab modelId={modelId} />}
      </Suspense>
    </div>
  )
}

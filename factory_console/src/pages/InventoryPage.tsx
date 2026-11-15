/* Lists and filters model inventory records and pipeline progress. */
import { useMemo, useState } from 'react'
import { AlertCircle, ArrowDown, ArrowUp, Search } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useModels } from '../api/hooks'
import type { ModelSummary } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { RatingBadge } from '../components/RatingBadge'
import { StatusBadge } from '../components/StatusBadge'
import { TierBadge } from '../components/TierBadge'
import { formatDate } from '../formatting/formatDates'
import { NOT_DISCOVERED } from '../formatting/statusStyles'

type SortKey = 'model_id' | 'model_name' | 'tier'

/** Displays sortable, searchable inventory rows. */
export function InventoryPage() {
  const modelsQuery = useModels()
  const [filter, setFilter] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('model_id')
  const [ascending, setAscending] = useState(true)

  const models = useMemo(() => {
    const search = filter.trim().toLowerCase()
    return [...(modelsQuery.data ?? [])]
      .filter((model) =>
        [model.model_id, model.model_name, model.model_type, model.language, model.business_line]
          .some((value) => (value ?? '').toLowerCase().includes(search)),
      )
      .sort((left, right) => {
        const [first, second] = [left[sortKey], right[sortKey]]
        if (first === second) return 0
        if (first == null) return 1 // models without a value sort last in both directions
        if (second == null) return -1
        return first.localeCompare(second) * (ascending ? 1 : -1)
      })
  }, [ascending, filter, modelsQuery.data, sortKey])

  if (modelsQuery.isLoading) {
    return <p className="p-8 text-sm text-slate-500" role="status">Loading model inventory…</p>
  }
  if (modelsQuery.error) {
    return <ErrorState error={modelsQuery.error} retry={() => void modelsQuery.refetch()} />
  }
  if (!modelsQuery.data?.length) {
    return <EmptyState title="Inventory is empty" description="Scan the estate to register model records." />
  }

  /** Selects a column and toggles its ordering on repeated clicks. */
  function chooseSort(key: SortKey) {
    if (sortKey === key) setAscending(!ascending)
    else {
      setSortKey(key)
      setAscending(true)
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-teal-800">Model estate</p>
          <h2 className="mt-1 text-2xl font-semibold text-slate-950">Inventory</h2>
          <p className="mt-1 text-sm text-slate-600">{models.length} of {modelsQuery.data.length} models</p>
        </div>
        <label className="relative block w-full sm:max-w-sm">
          <Search size={17} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <span className="sr-only">Filter models</span>
          <input
            type="search"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter by model, ID, type, or line"
            className="w-full rounded-lg border border-slate-300 bg-white py-2.5 pl-10 pr-3 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
          />
        </label>
      </header>

      {!models.length ? (
        <EmptyState title="No matching models" description="Try a different search term." />
      ) : (
        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-[1250px] w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <SortableHeader label="Model ID" sortKey="model_id" activeKey={sortKey} ascending={ascending} onSort={chooseSort} />
                  <SortableHeader label="Name" sortKey="model_name" activeKey={sortKey} ascending={ascending} onSort={chooseSort} />
                  <th scope="col" className="px-4 py-3">Type</th>
                  <th scope="col" className="px-4 py-3">Language</th>
                  <SortableHeader label="Tier" sortKey="tier" activeKey={sortKey} ascending={ascending} onSort={chooseSort} />
                  <th scope="col" className="px-4 py-3">Documentation</th>
                  <th scope="col" className="px-4 py-3">Last validated</th>
                  <th scope="col" className="px-4 py-3">Rating</th>
                  <th scope="col" className="px-4 py-3">Pipeline progress</th>
                  <th scope="col" className="px-4 py-3">Revalidation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {models.map((model) => <InventoryRow key={model.model_id} model={model} />)}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}

/** Renders a sortable table heading with its current direction. */
function SortableHeader({
  label,
  sortKey,
  activeKey,
  ascending,
  onSort,
}: {
  label: string
  sortKey: SortKey
  activeKey: SortKey
  ascending: boolean
  onSort: (key: SortKey) => void
}) {
  const active = sortKey === activeKey
  const Icon = ascending ? ArrowUp : ArrowDown
  return (
    <th scope="col" className="px-4 py-3">
      <button
        type="button"
        className="inline-flex items-center gap-1 font-semibold uppercase tracking-wide hover:text-teal-800"
        aria-sort={active ? (ascending ? 'ascending' : 'descending') : 'none'}
        onClick={() => onSort(sortKey)}
      >
        {label}
        {active && <Icon size={13} aria-hidden="true" />}
      </button>
    </th>
  )
}

/** Renders one searchable inventory record. */
function InventoryRow({ model }: { model: ModelSummary }) {
  const completed = Object.values(model.pipeline_status).filter(
    (status) => status === 'APPROVED' || status === 'SKIPPED',
  ).length
  return (
    <tr className="align-middle hover:bg-slate-50">
      <td className="px-4 py-4 font-mono text-xs text-slate-600">
        <Link to={`/models/${model.model_id}`} className="font-semibold text-teal-800 hover:underline">{model.model_id}</Link>
      </td>
      <td className="max-w-64 px-4 py-4">
        <Link to={`/models/${model.model_id}`} className="font-semibold text-slate-900 hover:text-teal-800">{model.model_name ?? model.model_id}</Link>
        <span className="mt-1 block text-xs text-slate-500">{model.business_line}</span>
      </td>
      <td className="px-4 py-4 text-slate-700">{model.model_type?.replaceAll('_', ' ') ?? NOT_DISCOVERED}</td>
      <td className="px-4 py-4 text-slate-700">{model.language}</td>
      <td className="px-4 py-4"><TierBadge tier={model.tier} /></td>
      <td className="px-4 py-4">{model.doc_status ? <StatusBadge status={model.doc_status} /> : <span className="text-sm text-slate-500">{NOT_DISCOVERED}</span>}</td>
      <td className="px-4 py-4 text-slate-600">{formatDate(model.last_validated)}</td>
      <td className="px-4 py-4"><RatingBadge rating={model.overall_rating} /></td>
      <td className="px-4 py-4">
        <div className="flex items-center gap-2">
          <div className="h-2 w-20 overflow-hidden rounded-full bg-slate-100" aria-label={`${completed} of 5 stages complete`}>
            <div className="h-full rounded-full bg-teal-700" style={{ width: `${(completed / 5) * 100}%` }} />
          </div>
          <span className="text-xs text-slate-600">{completed}/5</span>
        </div>
      </td>
      <td className="px-4 py-4">
        {model.revalidation_required ? (
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-rose-800"><AlertCircle size={14} />Required</span>
        ) : <span className="text-xs text-slate-500">No trigger</span>}
      </td>
    </tr>
  )
}

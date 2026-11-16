/* Presents code translation iterations, line mappings, and parity evidence. */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useRedevelopment } from '../api/hooks'
import type { Evidence, RedevelopResult } from '../api/types'
import { formatDuration, formatMetric, formatPercent } from '../formatting/formatNumbers'
import { StatusBadge } from '../components/StatusBadge'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'
import { EvidenceDrawer } from '../components/EvidenceDrawer'
import { formatResultError } from '../formatting/statusStyles'

/** Shows the generated implementation and parity certificate details. */
export function RedevelopmentTab({ modelId }: { modelId: string }) {
  const query = useRedevelopment(modelId)
  const [evidence, setEvidence] = useState<Evidence | null>(null)

  if (query.isLoading) return <p className="py-8 text-sm text-slate-500" role="status">Loading redevelopment evidence…</p>
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />
  if (!query.data) {
    return <EmptyState title="Redevelopment evidence not available" description="No code translation or parity result is available for this model in the current data source." />
  }

  const result = query.data
  const parity = result.parity

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Translation</p>
          <h3 className="mt-1 text-lg font-semibold text-slate-950">{result.source_language} → {result.target_language}</h3>
          <p className="mt-1 text-sm text-slate-600">Run {result.run_id} · {formatDuration(result.duration_seconds)}</p>
        </div>
        <StatusBadge status={result.status} />
      </section>

      {result.error && <p className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900" role="alert">{formatResultError(result.error)}</p>}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Summary label="Parity certificate" value={certificateLabel(result.status)} />
        <Summary label="Records compared" value={parity ? parity.records_compared.toLocaleString() : 'None'} />
        <Summary label="Unit tests" value={result.unit_tests ? `${result.unit_tests.passed} / ${result.unit_tests.total} passed` : 'No unit test result'} />
        <Summary label="Iterations" value={String(result.iterations.length)} />
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <Panel title="Parity levels">
          {parity ? (<>
          <p className="mb-3 text-sm text-slate-600">
            Tolerances: PD {formatMetric(parity.tolerance_pd, 6)} · coefficient {formatMetric(parity.tolerance_coef, 6)}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr><th className="py-2 pr-3">Level</th><th className="py-2 pr-3">Status</th><th className="py-2 pr-3">Max diff</th><th className="py-2">Match rate</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {parity.levels.map((level) => (
                  <tr key={level.level} className="align-top">
                    <th scope="row" className="py-3 pr-3 font-medium text-slate-800">
                      {level.level}<p className="mt-1 text-xs font-normal text-slate-500">{level.detail}</p>
                    </th>
                    <td className="py-3 pr-3"><StatusBadge status={level.status} /></td>
                    <td className="py-3 pr-3">{formatMetric(level.max_abs_diff)}</td>
                    <td className="py-3">{formatPercent(level.match_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>) : <p className="text-sm text-slate-500">No parity result</p>}
        </Panel>
        <Panel title="Translation iterations">
          <ol className="space-y-3">
            {result.iterations.map((iteration) => (
              <li key={iteration.iteration} className="rounded-lg bg-slate-50 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold text-slate-800">Iteration {iteration.iteration}</p>
                  <StatusBadge status={iteration.parity_passed ? 'PASSED' : 'FAILED'} />
                </div>
                <p className="mt-2 text-sm text-slate-600">
                  {iteration.unit_tests_passed} tests passed · {iteration.unit_tests_failed} failed · max PD difference {formatMetric(iteration.max_abs_diff_pd)}
                </p>
                {iteration.diagnosis && <p className="mt-2 text-sm text-slate-700"><strong>Diagnosis:</strong> {iteration.diagnosis}</p>}
                {iteration.fix_applied && <p className="mt-1 text-sm text-slate-700"><strong>Fix:</strong> {iteration.fix_applied}</p>}
              </li>
            ))}
          </ol>
        </Panel>
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <Panel title="Generated files">
          {result.generated_files.length ? (
            <ul className="space-y-2">
              {result.generated_files.map((file) => (
                <li key={file.path} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 p-3">
                  <button
                    type="button"
                    className="break-all text-left text-sm font-semibold text-teal-800 hover:underline"
                    onClick={() => setEvidence({ file: file.path, start_line: 1, end_line: 1, quote: `Generated ${file.kind} artifact.` })}
                  >
                    {file.path}
                  </button>
                  <StatusBadge status={file.kind} />
                </li>
              ))}
            </ul>
          ) : <EmptyState title="No generated files" description="No output artifacts were returned." />}
        </Panel>
        <Panel title="Source-to-target line mapping">
          {result.line_mapping.length ? (
            <ul className="space-y-3">
              {result.line_mapping.map((mapping, index) => (
                <li key={`${mapping.legacy_file}-${mapping.legacy_start}-${index}`} className="rounded-lg bg-slate-50 p-3">
                  <button
                    type="button"
                    className="break-all text-left text-sm font-semibold text-teal-800 hover:underline"
                    onClick={() => setEvidence({
                      file: mapping.python_file,
                      start_line: mapping.python_start,
                      end_line: mapping.python_end,
                      quote: mapping.note,
                    })}
                  >
                    {mapping.legacy_file}:{mapping.legacy_start}–{mapping.legacy_end} → {mapping.python_file}:{mapping.python_start}–{mapping.python_end}
                  </button>
                  <p className="mt-1 text-xs text-slate-600">{mapping.note}</p>
                </li>
              ))}
            </ul>
          ) : <EmptyState title="No line mappings" description="No source-to-target mapping was returned." />}
        </Panel>
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <Panel title="Compatibility checks">
          {result.pitfalls_checked.length
            ? <div className="flex flex-wrap gap-2">{result.pitfalls_checked.map((item) => <StatusBadge key={item} status={item} />)}</div>
            : <p className="text-sm text-slate-500">No compatibility checks were recorded.</p>}
        </Panel>
        <Panel title="Certificate hashes">
          {parity ? (<>
          <dl className="space-y-2 text-xs">
            {Object.entries(parity.hashes).map(([label, hash]) => (
              <div key={label} className="grid gap-1 sm:grid-cols-[minmax(130px,0.6fr)_1fr]">
                <dt className="font-medium text-slate-600">{label.replaceAll('_', ' ')}</dt>
                <dd className="break-all font-mono text-slate-800">{hash ?? 'Not available'}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 break-all text-xs text-slate-500">Certificate: {parity.certificate_md_path ?? 'Not written'}</p>
          {parity.mismatch_sample_path && (
            <p className="mt-1 break-all text-xs text-rose-800">Mismatch sample: {parity.mismatch_sample_path}</p>
          )}
          </>) : <p className="text-sm text-slate-500">No parity result</p>}
        </Panel>
      </section>
      <EvidenceDrawer evidence={evidence} onClose={() => setEvidence(null)} />
    </div>
  )
}

/** Certificate outcome from the rebuild status; only a real comparison is called passed or failed. */
function certificateLabel(status: RedevelopResult['status']) {
  if (status === 'PARITY_PASSED') return 'Passed'
  if (status === 'PARITY_FAILED') return 'Failed'
  if (status === 'TRANSLATED_NO_GOLDEN') return 'Not checked: no legacy outputs'
  return 'No parity result'
}

function Summary({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><p className="text-xs text-slate-500">{label}</p><p className="mt-2 text-xl font-semibold text-slate-950">{value}</p></div>
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><h3 className="mb-4 font-semibold text-slate-900">{title}</h3>{children}</section>
}

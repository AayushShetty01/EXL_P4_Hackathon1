/* Presents quantitative validation results, fairness, findings, and narrative. */
import type { ReactNode } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { artifactUrl } from '../api/client'
import { useValidation } from '../api/hooks'
import type { Rating, ValidationSeriesPoint } from '../api/types'
import { formatMetric, formatPercent } from '../formatting/formatNumbers'
import { RatingBadge } from '../components/RatingBadge'
import { StatusBadge } from '../components/StatusBadge'
import { ChartCard } from '../components/ChartCard'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { formatResultError } from '../formatting/statusStyles'

/** Shows the validation scorecard, charts, fairness, and human-readable report. */
export function ValidationTab({ modelId }: { modelId: string }) {
  const query = useValidation(modelId)

  if (query.isLoading) return <p className="py-8 text-sm text-slate-500" role="status">Loading validation results…</p>
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />
  if (!query.data) {
    return <EmptyState title="Validation results not available" description="No validation result is available for this model in the current data source." />
  }

  const { result, narrative, number_grounding, report, validator_agent_model } = query.data
  const sections = result.sections

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Independent validation</p>
          <p className="mt-1 text-sm text-slate-600">Run {result.run_id} · Development n={result.sample_sizes.dev.toLocaleString()} · Holdout n={result.sample_sizes.oot.toLocaleString()}</p>
          <p className="mt-1 text-xs text-slate-500">Validator: {validator_agent_model}</p>
        </div>
        <div className="flex items-center gap-3"><StatusBadge status={result.status} /><RatingBadge rating={result.overall_rating} /></div>
      </section>
      {result.error && <p className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900" role="alert">{formatResultError(result.error)}</p>}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <RatingCard label="Overall" rating={result.overall_rating} />
        <RatingCard label="Data quality" rating={sections.data_quality.rating} />
        <RatingCard label="Discrimination" rating={sections.discrimination.rating} />
        <RatingCard label="Calibration" rating={sections.calibration.rating} />
        <RatingCard label="Stability" rating={sections.stability.rating} />
        <RatingCard label="Backtest" rating={sections.backtest.rating} />
        <RatingCard label="Fairness" rating={sections.fairness.rating} />
        {sections.sensitivity && <RatingCard label="Sensitivity" rating={sections.sensitivity.rating} />}
        {sections.benchmark && <RatingCard label="Benchmark" rating={sections.benchmark.rating} />}
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <Panel title="Data quality">
          <div className="mb-3 grid grid-cols-2 gap-3 text-sm">
            <p>Development target rate <strong>{formatPercent(sections.data_quality.target_rate.dev)}</strong></p>
            <p>Holdout target rate <strong>{formatPercent(sections.data_quality.target_rate.oot)}</strong></p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500"><tr><th className="py-2">Check</th><th className="py-2">Value</th><th className="py-2">Threshold</th><th className="py-2">Result</th></tr></thead>
              <tbody className="divide-y divide-slate-100">{sections.data_quality.checks.map((check) => (
                <tr key={check.check}><th scope="row" className="py-2 font-medium text-slate-800">{check.check.replaceAll('_', ' ')}</th><td className="py-2">{formatMetric(check.value)}</td><td className="py-2">{formatMetric(check.threshold)}</td><td className="py-2"><StatusBadge status={check.passed ? 'PASSED' : 'FAILED'} /></td></tr>
              ))}</tbody>
            </table>
          </div>
        </Panel>
        <Panel title="Discrimination and calibration">
          <div className="grid gap-4 sm:grid-cols-2">
            <MetricGroup title="Holdout discrimination" rows={[
              ['AUC', formatMetric(sections.discrimination.oot.auc)],
              ['Gini', formatMetric(sections.discrimination.oot.gini)],
              ['KS', formatMetric(sections.discrimination.oot.ks)],
              ['Gini relative drop', formatPercent(sections.discrimination.gini_relative_drop)],
            ]} />
            <MetricGroup title="Holdout calibration" rows={[
              ['Brier score', formatMetric(sections.calibration.oot.brier)],
              ['Mean predicted PD', formatPercent(sections.calibration.oot.mean_predicted_pd)],
              ['Observed default rate', formatPercent(sections.calibration.oot.observed_default_rate)],
              ['Observed / expected', formatMetric(sections.calibration.oot.observed_over_expected)],
              ['Hosmer–Lemeshow p', formatMetric(sections.calibration.oot.hosmer_lemeshow_p)],
            ]} />
          </div>
          <h4 className="mb-2 mt-5 text-sm font-semibold text-slate-800">Calibration by decile</h4>
          <SimpleTable
            headings={['Decile', 'N', 'Mean PD', 'Observed rate']}
            rows={sections.calibration.decile_table.map((row) => [String(row.decile), row.n.toLocaleString(), formatPercent(row.mean_pd), formatPercent(row.observed_rate)])}
          />
        </Panel>
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <Panel title="Stability">
          <p className="mb-3 text-sm text-slate-700">Portfolio PSI <strong>{formatMetric(sections.stability.psi_score)}</strong></p>
          <SimpleTable
            headings={['Feature', 'CSI', 'Rating']}
            rows={sections.stability.csi.map((row) => [row.feature, formatMetric(row.csi), row.rating])}
          />
        </Panel>
        <Panel title="Backtest by band">
          <SimpleTable
            headings={['Band', 'PD range', 'N', 'Mean PD', 'Observed', 'p-value', 'Rating']}
            rows={sections.backtest.bands.map((row) => [
              row.band,
              `${formatPercent(row.pd_min)}–${formatPercent(row.pd_max)}`,
              row.n.toLocaleString(),
              formatPercent(row.mean_pd),
              formatPercent(row.observed_rate),
              formatMetric(row.binomial_p),
              row.light,
            ])}
          />
        </Panel>
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <Panel title="Fairness analysis">
          <p className="mb-4 text-sm text-slate-600">Favourable outcome: <strong>{sections.fairness.favourable_outcome}</strong></p>
          <div className="space-y-5">
            {sections.fairness.by_attribute.map((attribute) => (
              <div key={attribute.attribute}>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h4 className="font-semibold text-slate-800">{attribute.attribute}</h4>
                  <RatingBadge rating={attribute.rating} />
                </div>
                <SimpleTable
                  headings={['Group', 'N', 'Approval', 'Good approval', 'Bad approval', 'Default', 'Mean PD']}
                  rows={attribute.groups.map((group) => [
                    group.group,
                    group.n.toLocaleString(),
                    formatPercent(group.approval_rate),
                    formatPercent(group.approval_rate_good_customers),
                    formatPercent(group.approval_rate_bad_customers),
                    formatPercent(group.observed_default_rate),
                    formatPercent(group.mean_pd),
                  ])}
                />
                <p className="mt-2 text-xs text-slate-600">
                  Demographic parity ratio {formatMetric(attribute.demographic_parity_ratio)} ·
                  Equal opportunity diff {formatMetric(attribute.equal_opportunity_diff)} ·
                  Equalized odds diff {formatMetric(attribute.equalized_odds_diff)}
                </p>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Sensitivity and benchmark">
          {sections.sensitivity ? (
            <div className="mb-5">
              <div className="mb-2 flex items-center justify-between"><h4 className="font-semibold text-slate-800">Sensitivity</h4><RatingBadge rating={sections.sensitivity.rating} /></div>
              <SimpleTable
                headings={['Feature', 'Shock', 'Mean PD change', 'Decision flip']}
                rows={sections.sensitivity.shocks.map((row) => [row.feature, row.shock, formatPercent(row.mean_pd_change), formatPercent(row.decision_flip_rate)])}
              />
            </div>
          ) : <p className="mb-4 text-sm text-slate-500">Sensitivity analysis was not returned.</p>}
          {sections.benchmark ? (
            <>
              <div className="mb-2 flex items-center justify-between"><h4 className="font-semibold text-slate-800">Challenger benchmark</h4><RatingBadge rating={sections.benchmark.rating} /></div>
              <MetricGroup title={sections.benchmark.challenger} rows={[
                ['Champion holdout AUC', formatMetric(sections.benchmark.champion_auc_oot)],
                ['Challenger holdout AUC', formatMetric(sections.benchmark.challenger_auc_oot)],
                ['AUC uplift', formatMetric(sections.benchmark.auc_uplift)],
              ]} />
            </>
          ) : <p className="text-sm text-slate-500">Benchmark comparison was not returned.</p>}
        </Panel>
      </section>

      <section className="space-y-4">
        <h3 className="text-lg font-semibold text-slate-900">Validation charts</h3>
        <div className="grid gap-4 xl:grid-cols-2">
          {result.charts.map((chart) => (
            <ValidationChart
              key={chart.id}
              chartId={chart.id}
              title={chart.title}
              path={chart.path}
              points={result.series[chart.id] ?? []}
            />
          ))}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <Panel title="Findings">
          {result.findings.length ? (
            <ol className="space-y-3">
              {result.findings.map((finding) => (
                <li key={finding.id} className="rounded-lg border border-slate-100 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold text-slate-900">{finding.title}</h4><StatusBadge status={finding.severity} /></div>
                  <p className="mt-2 text-sm text-slate-700">{finding.detail}</p>
                  <p className="mt-2 text-xs text-slate-600">Evidence: {finding.evidence.metric} = {String(finding.evidence.value)} · threshold: {finding.evidence.threshold}</p>
                  <p className="mt-2 text-sm text-teal-900"><strong>Recommendation:</strong> {finding.recommendation}</p>
                </li>
              ))}
            </ol>
          ) : <EmptyState title="No findings returned" description="No validation findings were recorded." />}
        </Panel>
        <Panel title="Grounded narrative">
          <p className="mb-3 text-sm text-slate-600">
            Number grounding {formatPercent(number_grounding.score)} · {number_grounding.numbers_verified} / {number_grounding.numbers_in_narrative} values verified
          </p>
          <NarrativeSection title="Executive summary" text={narrative.executive_summary} />
          <NarrativeSection title="Conceptual soundness" text={narrative.conceptual_soundness} />
          <NarrativeSection title="Findings commentary" text={narrative.findings_commentary} />
          <NarrativeSection title="Conclusion" text={narrative.conclusion} />
          {narrative.unverified_numbers.length > 0 && <p className="mt-3 text-sm text-amber-900">Unverified numbers: {narrative.unverified_numbers.join(', ')}</p>}
          <div className="mt-4 flex flex-wrap gap-3 text-sm">
            {report.html_path && <ArtifactLink path={report.html_path} label="HTML report" />}
            {report.docx_path && <ArtifactLink path={report.docx_path} label="DOCX report" />}
          </div>
        </Panel>
      </section>
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
        Thresholds used: {Object.entries(result.thresholds_used).map(([name, value]) => `${name} ${formatMetric(value)}`).join(' · ')}
      </div>
    </div>
  )
}

function ValidationChart({ chartId, title, path, points }: { chartId: string; title: string; path: string; points: ValidationSeriesPoint[] }) {
  const xKey = chartId === 'roc_oot' ? 'fpr' : chartId === 'calibration_oot' ? 'decile' : 'bin'
  const lines = chartId === 'roc_oot'
    ? [{ key: 'tpr', color: '#287e83' }]
    : chartId === 'calibration_oot'
      ? [{ key: 'mean_pd', color: '#287e83' }, { key: 'observed_rate', color: '#d47b24' }]
      : [{ key: 'dev_share', color: '#426796' }, { key: 'oot_share', color: '#d47b24' }]
  const url = artifactUrl(path)

  return (
    <ChartCard title={title} description={path} height={260}>
      {points.length ? (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 10, right: 12, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            {lines.map((line) => <Line key={line.key} type="monotone" dataKey={line.key} stroke={line.color} strokeWidth={2} dot={{ r: 3 }} />)}
          </LineChart>
        </ResponsiveContainer>
      ) : <EmptyState title="Chart data unavailable" description="No series values were returned for this chart." />}
      {url && <a className="mt-2 inline-block text-xs font-semibold text-teal-800 hover:underline" href={url}>Open chart artifact</a>}
    </ChartCard>
  )
}

function RatingCard({ label, rating }: { label: string; rating: Rating }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><p className="mb-2 text-xs text-slate-500">{label}</p><RatingBadge rating={rating} /></div>
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><h3 className="mb-4 font-semibold text-slate-900">{title}</h3>{children}</section>
}

function MetricGroup({ title, rows }: { title: string; rows: Array<[string, string]> }) {
  return <div><h4 className="mb-2 text-sm font-semibold text-slate-800">{title}</h4><dl className="space-y-2">{rows.map(([label, value]) => <div key={label} className="flex justify-between gap-3 border-b border-slate-100 pb-2 text-sm"><dt className="text-slate-600">{label}</dt><dd className="font-medium text-slate-900">{value}</dd></div>)}</dl></div>
}

function SimpleTable({ headings, rows }: { headings: string[]; rows: string[][] }) {
  if (!rows.length) return <p className="text-sm text-slate-500">No data was returned.</p>
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-xs">
        <thead className="bg-slate-50 text-slate-500"><tr>{headings.map((heading) => <th key={heading} scope="col" className="whitespace-nowrap px-2 py-2 font-semibold">{heading}</th>)}</tr></thead>
        <tbody className="divide-y divide-slate-100">{rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex} className="whitespace-nowrap px-2 py-2 text-slate-700">{cell}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}

function NarrativeSection({ title, text }: { title: string; text: string }) {
  return <div className="mb-3"><h4 className="text-sm font-semibold text-slate-800">{title}</h4><p className="mt-1 text-sm leading-6 text-slate-700">{text}</p></div>
}

function ArtifactLink({ path, label }: { path: string; label: string }) {
  const url = artifactUrl(path)
  return url
    ? <a href={url} className="font-semibold text-teal-800 hover:underline">{label}</a>
    : <span className="text-xs text-slate-500">{label}: {path} (artifact link unavailable in mock mode)</span>
}

/* Captures a human decision for the stage awaiting review. */
import { useEffect, useState } from 'react'
import { Check, X } from 'lucide-react'
import { ApiError, apiMode } from '../api/client'
import { useGateDecision } from '../api/hooks'
import type { StageName } from '../api/types'
import { useReviewerIdentity } from './ReviewerProvider'

const reviewGuidance: Record<StageName, string> = {
  discover: 'Check the inventory record and the assigned tier.',
  document: 'Review cited claims, unverified statements, and document drift.',
  redevelop: 'Review the code translation, test results, and parity certificate.',
  validate: 'Review independent metrics, fairness results, and findings.',
  monitor: 'Review simulated drift alerts and the revalidation decision.',
}

/** Renders an approval panel for the active human gate. */
export function GateReviewPanel({ runId, stage }: { runId: string; stage: StageName }) {
  const { identity } = useReviewerIdentity()
  const decisionMutation = useGateDecision()
  const [comment, setComment] = useState('')

  useEffect(() => {
    decisionMutation.reset()
    setComment('')
  }, [decisionMutation.reset, identity.reviewer, identity.role, runId, stage])

  /** Sends the selected human decision and optional review note. */
  function decide(decision: 'approve' | 'reject') {
    decisionMutation.mutate({
      runId,
      stage,
      decision: {
        decision,
        reviewer: identity.reviewer,
        role: identity.role,
        comment: comment.trim(),
      },
    })
  }

  const errorMessage =
    decisionMutation.error instanceof ApiError &&
    decisionMutation.error.code === 'INDEPENDENCE_VIOLATION'
      ? 'The reviewer who approved redevelopment cannot approve validation.'
      : decisionMutation.error?.message

  return (
    <section className="rounded-xl border border-teal-200 bg-teal-50 p-5" aria-labelledby="gate-review-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-teal-900">Human review required</p>
          <h3 id="gate-review-heading" className="mt-1 text-lg font-semibold text-slate-950">
            {stage[0].toUpperCase() + stage.slice(1)} gate
          </h3>
          <p className="mt-1 text-sm text-slate-700">{reviewGuidance[stage]}</p>
        </div>
        <p className="rounded-md bg-white px-3 py-2 text-xs text-slate-700">
          Reviewing as <strong>{identity.reviewer}</strong> · {identity.role}
        </p>
      </div>
      <label className="mt-4 block text-sm font-medium text-slate-700" htmlFor="gate-review-comment">
        Review comment
      </label>
      <textarea
        id="gate-review-comment"
        rows={3}
        value={comment}
        onChange={(event) => setComment(event.target.value)}
        className="mt-1 w-full resize-y rounded-lg border border-slate-300 bg-white p-3 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
        placeholder="Record the reason for your decision"
      />
      {errorMessage && (
        <p className="mt-3 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm font-medium text-rose-900" role="alert">
          {errorMessage}
        </p>
      )}
      {apiMode === 'snapshot' && (
        <p className="mt-3 text-sm text-amber-900">Recorded runs are read-only in snapshot mode.</p>
      )}
      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          disabled={apiMode === 'snapshot' || decisionMutation.isPending}
          onClick={() => decide('approve')}
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-800 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-900 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Check size={16} aria-hidden="true" />
          {decisionMutation.isPending ? 'Saving…' : 'Approve'}
        </button>
        <button
          type="button"
          disabled={apiMode === 'snapshot' || decisionMutation.isPending}
          onClick={() => decide('reject')}
          className="inline-flex items-center gap-2 rounded-lg border border-rose-300 bg-white px-4 py-2.5 text-sm font-semibold text-rose-800 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <X size={16} aria-hidden="true" />
          Reject
        </button>
      </div>
    </section>
  )
}

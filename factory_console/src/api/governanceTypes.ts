/* Defines compliance, audit, factory metric, and file response types. */
import type {
  FindingSeverity,
  ModelLanguage,
  StageName,
  Tier,
} from './contractEnums'
import type { ModelSummary } from './modelTypes'

export interface ComplianceItem {
  id: string
  expectation: string
  status: 'MET' | 'PARTIAL' | 'NOT_MET' | 'OUT_OF_SCOPE'
  evidence_path: string | null
  note: string | null
}

export interface Compliance {
  model_id: string
  disclaimer: string
  principles: Array<{ principle: string; title: string; items: ComplianceItem[] }>
  coverage: { met: number; partial: number; not_met: number; out_of_scope: number }
}

export interface AuditEvent {
  seq: number
  ts: string
  model_id: string
  run_id: string | null
  stage: StageName | null
  actor_type: 'agent' | 'human' | 'system'
  actor: string
  action:
    | 'stage_started'
    | 'stage_completed'
    | 'stage_failed'
    | 'stage_skipped'
    | 'llm_call'
    | 'tool_call'
    | 'service_call'
    | 'artifact_written'
    | 'gate_decision'
    | 'revalidation_triggered'
  detail: Record<string, unknown>
  prev_hash: string
  hash: string
}

export interface Audit {
  chain_valid: boolean
  events: AuditEvent[]
}

export interface FactoryMetrics {
  models_total: number
  by_tier: Record<Tier, number>
  by_language: Record<ModelLanguage, number>
  docs_outdated_at_discovery: number
  docs_generated: number
  avg_groundedness: number
  parity_certificates_issued: number
  validations_completed: number
  open_findings: Record<FindingSeverity, number>
  revalidation_triggers: number
  avg_agent_minutes_per_model: number
  human_review_minutes_logged: number
  manual_baseline_weeks_per_validation: [number, number]
}

export interface FileView {
  path: string
  language: string
  lines: number
  content: string
}

export interface ModelsResponse {
  models: ModelSummary[]
}

export interface ScanEstateResponse {
  models_found: string[]
}

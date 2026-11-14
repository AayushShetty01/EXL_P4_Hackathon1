/* Defines run, stage, and human gate request and response types. */
import type {
  ReviewDecision,
  ReviewerRole,
  RunStatus,
  StageName,
  StageStatus,
} from './contractEnums'

export interface GateDecision {
  decision: ReviewDecision
  reviewer: string
  role: ReviewerRole
  comment: string
  decided_at: string
  review_seconds: number | null
}

export interface GateDecisionRequest {
  decision: ReviewDecision
  reviewer: string
  role: ReviewerRole
  comment: string
}

export interface StageRun {
  stage: StageName
  status: StageStatus
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  summary: string | null
  skip_reason: string | null
  error: string | null
  gate: GateDecision | null
}

export interface Run {
  run_id: string
  model_id: string
  status: RunStatus
  current_stage: StageName | null
  auto_approve: boolean
  stages: StageRun[]
  started_at: string
  finished_at: string | null
  total_agent_seconds: number
  total_review_seconds: number
}

export interface RunStartRequest {
  stages: StageName[]
  auto_approve: boolean
}

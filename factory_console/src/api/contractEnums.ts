/* Defines the shared literal values used by ModelPassport contracts. */
export type ModelType = 'credit_pd' | 'fraud' | 'pricing' | 'other'
export type ModelLanguage = 'SAS' | 'R' | 'Python'
export type Tier = 'Tier 1' | 'Tier 2' | 'Tier 3'
export type DocumentStatus = 'MISSING' | 'OUTDATED' | 'CURRENT'
export type Rating = 'GREEN' | 'AMBER' | 'RED'
export type FindingSeverity = 'HIGH' | 'MEDIUM' | 'LOW'
export type ReviewerRole = 'developer' | 'validator' | 'owner'
export type StageName = 'discover' | 'document' | 'redevelop' | 'validate' | 'monitor'
export type StageStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'AWAITING_REVIEW'
  | 'APPROVED'
  | 'REJECTED'
  | 'FAILED'
  | 'SKIPPED'
export type RunStatus = 'RUNNING' | 'AWAITING_REVIEW' | 'COMPLETED' | 'REJECTED' | 'FAILED'
export type ReviewDecision = 'approve' | 'reject'

export interface PipelineStatus {
  discover: StageStatus
  document: StageStatus
  redevelop: StageStatus
  validate: StageStatus
  monitor: StageStatus
}

/** Error field of a service result: absent, a plain message, or a code with a message. */
export type ResultError = string | { code: string; message: string } | null

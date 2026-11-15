/* Defines model inventory records and evidence file references. */
import type {
  DocumentStatus,
  ModelLanguage,
  ModelType,
  PipelineStatus,
  Rating,
  Tier,
} from './contractEnums'

export interface SourceFile {
  path: string
  kind: string
  lines: number
  sha256: string
}

export interface Evidence {
  file: string
  start_line: number
  end_line: number
  quote: string
}

export interface InventoryFieldEvidence extends Evidence {
  status: 'VERIFIED' | 'UNVERIFIED'
}

export interface InputVariable {
  name: string
  description: string | null
  transformation: string | null
}

export interface Tiering {
  tier: Tier
  materiality_score: number
  complexity_score: number
  rationale: string[]
}

export interface InventoryRecord {
  model_id: string
  model_name: string | null
  purpose: string | null
  business_line: string | null
  model_owner: string | null
  language: ModelLanguage
  algorithm: string | null
  target_variable: string | null
  input_variables: InputVariable[]
  outputs: string[]
  upstream_dependencies: string[]
  downstream_uses: string[]
  exposure_gbp_m: number | null
  regulatory_use: string | null
  customer_facing: boolean | null
  tiering: Tiering | null
  doc_status: DocumentStatus | null
  doc_last_updated: string | null
  last_code_change: string | null
  last_validated: string | null
  next_validation_due: string | null
  source_files: SourceFile[]
  field_evidence: Record<string, InventoryFieldEvidence>
  open_questions: string[]
  pipeline_status: PipelineStatus
  revalidation_required: boolean
  created_at: string
  updated_at: string
}

export interface ModelSummary {
  model_id: string
  model_name: string | null
  model_type: ModelType | null
  language: ModelLanguage
  algorithm: string | null
  business_line: string | null
  tier: Tier | null
  doc_status: DocumentStatus | null
  last_validated: string | null
  pipeline_status: PipelineStatus
  overall_rating: Rating | null
  revalidation_required: boolean
  active_run_id: string | null
}

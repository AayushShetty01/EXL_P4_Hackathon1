/* Defines evidence-cited documentation and document drift records. */
import type { FindingSeverity } from './contractEnums'
import type { Evidence } from './modelTypes'

export interface Claim {
  id: string
  text: string
  status: 'VERIFIED' | 'UNVERIFIED' | 'SME_INPUT_NEEDED'
  evidence: Evidence[]
}

export interface DocumentationSection {
  id: string
  title: string
  markdown: string
  claims: Claim[]
}

export interface DocDriftItem {
  id: string
  severity: FindingSeverity
  topic: string
  legacy_doc_says: string
  code_says: string
  legacy_evidence: Evidence | null
  code_evidence: Evidence | null
  status: 'VERIFIED' | 'UNVERIFIED'
}

export interface Documentation {
  model_id: string
  generated_at: string
  generated_by_model: string
  groundedness: {
    claims_total: number
    claims_verified: number
    claims_unverified: number
    claims_sme_input_needed: number
    score: number
  }
  sections: DocumentationSection[]
  doc_drift: DocDriftItem[]
  markdown_path: string
}

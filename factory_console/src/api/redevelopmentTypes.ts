/* Defines rebuild outputs, code mappings, and parity certificate types. */
import type { ModelLanguage } from './contractEnums'

export interface RedevelopmentIteration {
  iteration: number
  unit_tests_passed: number
  unit_tests_failed: number
  parity_passed: boolean
  max_abs_diff_pd: number | null
  diagnosis: string | null
  fix_applied: string | null
}

export interface GeneratedFile {
  path: string
  kind: string
}

export interface LineMapping {
  legacy_file: string
  legacy_start: number
  legacy_end: number
  python_file: string
  python_start: number
  python_end: number
  note: string
}

export interface ParityLevel {
  level: string
  status: 'PASSED' | 'FAILED' | 'NOT_APPLICABLE'
  max_abs_diff: number | null
  mismatched_records: number | null
  match_rate: number | null
  psi: number | null
  detail: string
}

export interface ParityResult {
  passed: boolean
  records_compared: number
  tolerance_pd: number
  tolerance_coef: number
  levels: ParityLevel[]
  hashes: {
    legacy_code_sha256: string
    python_code_sha256: string
    input_data_sha256: string
    golden_output_sha256: string
  }
  certificate_md_path: string
  certificate_json_path: string
  mismatch_sample_path: string | null
}

export interface RedevelopResult {
  model_id: string
  run_id: string
  status: 'PARITY_PASSED' | 'PARITY_FAILED' | 'TRANSLATED_NO_GOLDEN' | 'ERROR'
  source_language: ModelLanguage
  target_language: 'Python'
  iterations: RedevelopmentIteration[]
  generated_files: GeneratedFile[]
  line_mapping: LineMapping[]
  unit_tests: { total: number; passed: number; failed: number }
  parity: ParityResult
  pitfalls_checked: string[]
  mlflow: Record<string, string> | null
  llm_trace: Array<Record<string, string | number | boolean>>
  duration_seconds: number
  error: string | null
}

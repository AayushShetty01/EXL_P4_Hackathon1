/* Defines deterministic validation metrics, findings, and report types. */
import type { FindingSeverity, Rating, ResultError } from './contractEnums'

export interface ValidationCheck {
  check: string
  value: number
  threshold: number
  passed: boolean
}

export interface DiscriminationMetrics {
  auc: number
  gini: number
  ks: number
}

export interface CalibrationMetrics {
  brier: number
  mean_predicted_pd: number
  observed_default_rate: number
  observed_over_expected: number
  hosmer_lemeshow_stat: number
  hosmer_lemeshow_p: number
}

export interface DecileMetric {
  decile: number
  n: number
  mean_pd: number
  observed_rate: number
}

export interface FairnessGroup {
  group: string
  n: number
  approval_rate: number
  approval_rate_good_customers: number | null
  approval_rate_bad_customers: number | null
  observed_default_rate: number
  mean_pd: number
}

export interface FairnessAttribute {
  attribute: string
  groups: FairnessGroup[]
  demographic_parity_ratio: number | null
  equal_opportunity_diff: number | null
  equalized_odds_diff: number | null
  rating: Rating
}

export interface Finding {
  id: string
  section: string
  severity: FindingSeverity
  title: string
  detail: string
  evidence: { metric: string; value: number | string; threshold: string }
  recommendation: string
}

export interface ValidationSeriesPoint {
  [key: string]: string | number
}

export interface ValidationResult {
  model_id: string
  run_id: string
  status: 'COMPLETED' | 'ERROR'
  overall_rating: Rating
  sample_sizes: { dev: number; oot: number }
  sections: {
    data_quality: {
      rating: Rating
      checks: ValidationCheck[]
      target_rate: { dev: number; oot: number }
    }
    discrimination: {
      rating: Rating
      dev: DiscriminationMetrics
      oot: DiscriminationMetrics
      gini_relative_drop: number
    }
    calibration: {
      rating: Rating
      oot: CalibrationMetrics
      decile_table: DecileMetric[]
    }
    stability: {
      rating: Rating
      psi_score: number
      csi: Array<{ feature: string; csi: number; rating: Rating }>
    }
    backtest: {
      rating: Rating
      bands: Array<{
        band: string
        pd_min: number
        pd_max: number
        n: number
        mean_pd: number
        observed_rate: number
        binomial_p: number
        light: Rating
      }>
    }
    fairness: {
      rating: Rating
      favourable_outcome: string
      by_attribute: FairnessAttribute[]
    }
    sensitivity: {
      rating: Rating
      shocks: Array<{
        feature: string
        shock: string
        mean_pd_change: number
        decision_flip_rate: number
      }>
    } | null
    benchmark: {
      rating: Rating
      challenger: string
      champion_auc_oot: number
      challenger_auc_oot: number
      auc_uplift: number
    } | null
  }
  findings: Finding[]
  charts: Array<{ id: string; title: string; path: string }>
  series: Record<string, ValidationSeriesPoint[]>
  thresholds_used: Record<string, number>
  result_path: string
  duration_seconds: number
  error: ResultError
}

export interface ValidationView {
  model_id: string
  result: ValidationResult
  narrative: {
    executive_summary: string
    conceptual_soundness: string
    findings_commentary: string
    conclusion: string
    unverified_numbers: string[]
  }
  number_grounding: { numbers_in_narrative: number; numbers_verified: number; score: number }
  validator_agent_model: string
  report: { html_path: string | null; docx_path: string | null }
}

/* Defines monitoring batch results, alerts, and revalidation triggers. */
import type { Rating, ResultError } from './contractEnums'

export interface MonitoringBatch {
  batch: string
  n: number
  psi_score: number
  max_csi: { feature: string; csi: number }
  auc: number | null
  observed_default_rate: number | null
  mean_pd: number
  alert: Rating
}

export interface MonitoringResult {
  model_id: string
  status: 'COMPLETED' | 'ERROR'
  simulated: boolean
  reference_sample: string
  batches: MonitoringBatch[]
  alerts: Array<{ batch: string; level: Rating; rule: string; value: number }>
  revalidation_triggered: boolean
  trigger_reason: string | null
  thresholds_used: { psi_green: number; psi_amber: number; auc_drop_trigger: number }
  result_path: string
  error: ResultError
}

/* Exposes the contract endpoints for mock, live, and snapshot modes. */
import {
  apiBaseUrl,
  apiMode,
  ApiError,
  requestJson,
} from './apiTransport'
import {
  mockGetAudit,
  mockGetCompliance,
  mockGetDocumentation,
  mockGetFactoryMetrics,
  mockGetFile,
  mockGetModel,
  mockGetModels,
  mockGetMonitoring,
  mockGetRedevelopment,
  mockGetRun,
  mockGetValidation,
  mockPostGateDecision,
  mockScanEstate,
  mockStartRun,
} from './mockClient'
import type {
  Audit,
  Compliance,
  Documentation,
  FactoryMetrics,
  FileView,
  GateDecisionRequest,
  InventoryRecord,
  ModelSummary,
  MonitoringResult,
  ModelsResponse,
  RedevelopResult,
  Run,
  RunStartRequest,
  ScanEstateResponse,
  StageName,
  ValidationView,
} from './types'

export { apiMode, ApiError }
export type { ApiMode } from './apiTransport'

/** Reads the model list in the currently selected data mode. */
export async function getModels(): Promise<ModelSummary[]> {
  if (apiMode === 'mock') return mockGetModels()
  const response = await requestJson<ModelsResponse>(
    apiMode === 'snapshot' ? 'models.json' : '/api/models',
  )
  return response?.models ?? []
}

/** Scans the model estate through the factory_core endpoint. */
export async function scanEstate(): Promise<ScanEstateResponse> {
  if (apiMode === 'mock') return mockScanEstate()
  if (apiMode === 'snapshot') {
    throw new ApiError('Estate scanning is disabled in snapshot mode.', 405, 'READ_ONLY')
  }
  const response = await requestJson<ScanEstateResponse>('/api/estate/scan', {
    method: 'POST',
  })
  if (!response) {
    throw new ApiError('Estate scan returned no response.', 502)
  }
  return response
}

/** Reads the inventory record for one model. */
export async function getModel(modelId: string): Promise<InventoryRecord | null> {
  if (apiMode === 'mock') return mockGetModel(modelId)
  const path =
    apiMode === 'snapshot'
      ? `models/${encodeURIComponent(modelId)}.json`
      : `/api/models/${encodeURIComponent(modelId)}`
  return requestJson<InventoryRecord>(path)
}

/** Starts a run and returns its identifier. */
export async function startRun(
  modelId: string,
  request: RunStartRequest,
): Promise<{ run_id: string }> {
  if (apiMode === 'mock') return mockStartRun(modelId, request)
  if (apiMode === 'snapshot') {
    throw new ApiError('Starting a run is disabled in snapshot mode.', 405, 'READ_ONLY')
  }
  const response = await requestJson<{ run_id: string }>(
    `/api/models/${encodeURIComponent(modelId)}/runs`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    },
  )
  if (!response) {
    throw new ApiError('Starting the run returned no response.', 502)
  }
  return response
}

/** Reads one run and its stage state. */
export async function getRun(runId: string): Promise<Run | null> {
  if (apiMode === 'mock') return mockGetRun(runId)
  const path =
    apiMode === 'snapshot'
      ? `runs/${encodeURIComponent(runId)}.json`
      : `/api/runs/${encodeURIComponent(runId)}`
  return requestJson<Run>(path)
}

/** Records a gate decision and returns the updated run. */
export async function postGateDecision(
  runId: string,
  stage: StageName,
  decision: GateDecisionRequest,
): Promise<Run> {
  if (apiMode === 'mock') return mockPostGateDecision(runId, stage, decision)
  if (apiMode === 'snapshot') {
    throw new ApiError('Gate decisions are disabled in snapshot mode.', 405, 'READ_ONLY')
  }
  const response = await requestJson<Run>(
    `/api/runs/${encodeURIComponent(runId)}/gates/${stage}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(decision),
    },
  )
  if (!response) {
    throw new ApiError('Recording the gate decision returned no response.', 502)
  }
  return response
}

/** Reads the generated documentation for one model when it exists. */
export async function getDocumentation(modelId: string): Promise<Documentation | null> {
  if (apiMode === 'mock') return mockGetDocumentation(modelId)
  return requestJson<Documentation>(
    apiMode === 'snapshot'
      ? `models/${encodeURIComponent(modelId)}/documentation.json`
      : `/api/models/${encodeURIComponent(modelId)}/documentation`,
  )
}

/** Reads the redevelopment result for one model when it exists. */
export async function getRedevelopment(modelId: string): Promise<RedevelopResult | null> {
  if (apiMode === 'mock') return mockGetRedevelopment(modelId)
  return requestJson<RedevelopResult>(
    apiMode === 'snapshot'
      ? `models/${encodeURIComponent(modelId)}/redevelopment.json`
      : `/api/models/${encodeURIComponent(modelId)}/redevelopment`,
  )
}

/** Reads the validation result and narrative for one model. */
export async function getValidation(modelId: string): Promise<ValidationView | null> {
  if (apiMode === 'mock') return mockGetValidation(modelId)
  return requestJson<ValidationView>(
    apiMode === 'snapshot'
      ? `models/${encodeURIComponent(modelId)}/validation.json`
      : `/api/models/${encodeURIComponent(modelId)}/validation`,
  )
}

/** Reads the monitoring result for one model when it exists. */
export async function getMonitoring(modelId: string): Promise<MonitoringResult | null> {
  if (apiMode === 'mock') return mockGetMonitoring(modelId)
  return requestJson<MonitoringResult>(
    apiMode === 'snapshot'
      ? `models/${encodeURIComponent(modelId)}/monitoring.json`
      : `/api/models/${encodeURIComponent(modelId)}/monitoring`,
  )
}

/** Reads the compliance matrix for one model when it exists. */
export async function getCompliance(modelId: string): Promise<Compliance | null> {
  if (apiMode === 'mock') return mockGetCompliance(modelId)
  return requestJson<Compliance>(
    apiMode === 'snapshot'
      ? `models/${encodeURIComponent(modelId)}/compliance.json`
      : `/api/models/${encodeURIComponent(modelId)}/compliance`,
  )
}

/** Reads audit events and optionally filters them by model. */
export async function getAudit(modelId?: string): Promise<Audit | null> {
  if (apiMode === 'mock') return mockGetAudit(modelId)
  const path =
    apiMode === 'snapshot'
      ? 'audit.json'
      : `/api/audit${modelId ? `?model_id=${encodeURIComponent(modelId)}` : ''}`
  const response = await requestJson<Audit>(path)
  if (apiMode === 'snapshot' && modelId && response) {
    return {
      chain_valid: response.chain_valid,
      events: response.events.filter((event) => event.model_id === modelId),
    }
  }
  return response
}

/** Reads factory-wide dashboard metrics. */
export async function getFactoryMetrics(): Promise<FactoryMetrics | null> {
  if (apiMode === 'mock') return mockGetFactoryMetrics()
  return requestJson<FactoryMetrics>(
    apiMode === 'snapshot' ? 'metrics.json' : '/api/metrics/factory',
  )
}

/** Reads one text file through the factory_core file API or mock fixture. */
export async function getFile(path: string): Promise<FileView | null> {
  if (apiMode === 'mock') return mockGetFile(path)
  const requestPath =
    apiMode === 'snapshot'
      ? `files/${path.replaceAll('/', '__')}.json`
      : `/api/files?path=${encodeURIComponent(path)}`
  return requestJson<FileView>(requestPath)
}

/** Builds the mode-specific URL for a stored binary artifact. */
export function artifactUrl(path: string): string | null {
  if (apiMode === 'mock') return null
  if (apiMode === 'snapshot') {
    const artifactPath = path.startsWith('artifacts/') ? path.slice('artifacts/'.length) : path
    return `/snapshot/artifacts/${artifactPath
      .split('/')
      .map(encodeURIComponent)
      .join('/')}`
  }
  return `${apiBaseUrl}/api/artifacts/${path
    .split('/')
    .map(encodeURIComponent)
    .join('/')}`
}

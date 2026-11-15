/* Implements stateful sample responses for offline mock mode. */
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
  StageRun,
  StageStatus,
  ValidationView,
} from './types'
import { ApiError, mockDelay } from './apiTransport'
import modelsFixture from '../mocks/models.json'
import metricsFixture from '../mocks/metrics.json'
import auditFixture from '../mocks/audit.json'
import modelM001Fixture from '../mocks/model-M001.json'
import modelM002Fixture from '../mocks/model-M002.json'
import modelM003Fixture from '../mocks/model-M003.json'
import modelM004Fixture from '../mocks/model-M004.json'
import documentationFixture from '../mocks/documentation-M001.json'
import redevelopmentFixture from '../mocks/redevelopment-M001.json'
import redevelopmentM002Fixture from '../mocks/redevelopment-M002.json'
import validationFixture from '../mocks/validation-M001.json'
import monitoringFixture from '../mocks/monitoring-M001.json'
import complianceFixture from '../mocks/compliance-M001.json'
import filesFixture from '../mocks/files.json'

const mockModels = (modelsFixture as ModelsResponse).models
const mockInventory: Record<string, InventoryRecord> = {
  M001: modelM001Fixture as InventoryRecord,
  M002: modelM002Fixture as InventoryRecord,
  M003: modelM003Fixture as InventoryRecord,
  M004: modelM004Fixture as InventoryRecord,
}
const mockRedevelopment: Record<string, RedevelopResult> = {
  M001: redevelopmentFixture as RedevelopResult,
  M002: redevelopmentM002Fixture as RedevelopResult,
}
const mockRuns: Record<string, Run> = {}
const mockAudit = auditFixture as Audit

/** Returns the sample model list. */
export async function mockGetModels(): Promise<ModelSummary[]> {
  await mockDelay()
  return structuredClone(mockModels)
}

/** Returns model identifiers found in the mock estate. */
export async function mockScanEstate(): Promise<ScanEstateResponse> {
  await mockDelay()
  return { models_found: mockModels.map((model) => model.model_id) }
}

/** Returns a copy of one sample inventory record. */
export async function mockGetModel(modelId: string): Promise<InventoryRecord | null> {
  await mockDelay()
  const inventory = mockInventory[modelId]
  return inventory ? structuredClone(inventory) : null
}

/** Starts an in-memory run that pauses at each applicable review gate. */
export async function mockStartRun(
  modelId: string,
  request: RunStartRequest,
): Promise<{ run_id: string }> {
  await mockDelay()
  const inventory = mockInventory[modelId]
  if (!inventory) {
    throw new ApiError(`Model ${modelId} was not found.`, 404, 'NOT_FOUND')
  }

  const existingRun = Object.values(mockRuns).find(
    (run) => run.model_id === modelId && !['COMPLETED', 'REJECTED', 'FAILED'].includes(run.status),
  )
  if (existingRun) {
    return { run_id: existingRun.run_id }
  }

  const runId = `run_${modelId}_demo`
  const now = new Date().toISOString()
  const applicableStages = request.stages.filter((stage) => {
    if (stage === 'redevelop' && inventory.language === 'Python') return false
    if (modelId === 'M004' && stage === 'redevelop') return false
    if ((stage === 'validate' || stage === 'monitor') && modelId === 'M004') return false
    return true
  })
  const stages: StageRun[] = request.stages.map((stage) => {
    const skipped = !applicableStages.includes(stage)
    const current = !skipped && stage === applicableStages[0]
    const status: StageStatus = skipped
      ? 'SKIPPED'
      : current
        ? 'AWAITING_REVIEW'
        : 'PENDING'
    return {
      stage,
      status,
      started_at: current ? now : null,
      finished_at: current ? now : null,
      duration_seconds: current ? 0 : null,
      summary: current ? 'Illustrative mock stage is ready for human review.' : null,
      skip_reason: skipped ? 'This stage does not apply to the sample model.' : null,
      error: null,
      gate: null,
    }
  })
  const currentStage = applicableStages[0] ?? null
  const run: Run = {
    run_id: runId,
    model_id: modelId,
    status: currentStage ? 'AWAITING_REVIEW' : 'COMPLETED',
    current_stage: currentStage,
    auto_approve: request.auto_approve,
    stages,
    started_at: now,
    finished_at: currentStage ? null : now,
    total_agent_seconds: 0,
    total_review_seconds: 0,
  }
  mockRuns[runId] = run
  updateMockPipeline(modelId, stages)
  return { run_id: runId }
}

/** Returns a copy of a run stored in memory. */
export async function mockGetRun(runId: string): Promise<Run | null> {
  await mockDelay()
  const run = mockRuns[runId]
  return run ? structuredClone(run) : null
}

/** Applies a mock decision and advances the run to its next review gate. */
export async function mockPostGateDecision(
  runId: string,
  stage: StageName,
  decision: GateDecisionRequest,
): Promise<Run> {
  await mockDelay()
  const run = mockRuns[runId]
  if (!run) {
    throw new ApiError(`Run ${runId} was not found.`, 404, 'NOT_FOUND')
  }
  const currentStage = run.stages.find((item) => item.stage === stage)
  if (!currentStage || currentStage.status !== 'AWAITING_REVIEW') {
    throw new ApiError(`Stage ${stage} is not waiting for review.`, 409, 'INVALID_STAGE')
  }
  if (stage === 'validate' && decision.decision === 'approve') {
    const redevelopmentReviewer = run.stages.find((item) => item.stage === 'redevelop')?.gate?.reviewer
    if (redevelopmentReviewer === decision.reviewer) {
      throw new ApiError(
        'The reviewer who approved redevelopment cannot approve validation.',
        409,
        'INDEPENDENCE_VIOLATION',
      )
    }
  }

  const now = new Date().toISOString()
  currentStage.status = decision.decision === 'approve' ? 'APPROVED' : 'REJECTED'
  currentStage.gate = {
    ...decision,
    decided_at: now,
    review_seconds: 0,
  }
  if (decision.decision === 'reject') {
    run.status = 'REJECTED'
    run.current_stage = null
    run.finished_at = now
  } else {
    const nextStage = run.stages.find((item) => item.status === 'PENDING')
    if (nextStage) {
      nextStage.status = 'AWAITING_REVIEW'
      nextStage.started_at = now
      nextStage.finished_at = now
      nextStage.duration_seconds = 0
      nextStage.summary = 'Illustrative mock stage is ready for human review.'
      run.status = 'AWAITING_REVIEW'
      run.current_stage = nextStage.stage
    } else {
      run.status = 'COMPLETED'
      run.current_stage = null
      run.finished_at = now
    }
  }
  run.total_review_seconds = run.stages.reduce(
    (total, item) => total + (item.gate?.review_seconds ?? 0),
    0,
  )
  updateMockPipeline(run.model_id, run.stages)
  appendMockAuditEvent(run, stage, decision, now)
  return structuredClone(run)
}

/** Updates sample stage statuses after a mock workflow transition. */
function updateMockPipeline(modelId: string, stages: StageRun[]) {
  const summary = mockModels.find((model) => model.model_id === modelId)
  const inventory = mockInventory[modelId]
  if (!summary || !inventory) return
  for (const { stage, status } of stages) {
    summary.pipeline_status[stage] = status
    inventory.pipeline_status[stage] = status
  }
  summary.active_run_id =
    mockRuns[`run_${modelId}_demo`]?.status === 'AWAITING_REVIEW' ? `run_${modelId}_demo` : null
}

/** Adds a clearly marked example approval to the in-memory mock audit. */
function appendMockAuditEvent(
  run: Run,
  stage: StageName,
  decision: GateDecisionRequest,
  timestamp: string,
) {
  const previousEvent = mockAudit.events.at(-1)
  const sequence = (previousEvent?.seq ?? 0) + 1
  mockAudit.events.push({
    seq: sequence,
    ts: timestamp,
    model_id: run.model_id,
    run_id: run.run_id,
    stage,
    actor_type: 'human',
    actor: decision.reviewer,
    action: 'gate_decision',
    detail: {
      decision: decision.decision,
      role: decision.role,
      comment: decision.comment,
      sample: true,
    },
    prev_hash: previousEvent?.hash ?? 'sample-hash-root',
    hash: `sample-hash-${sequence}`,
  })
}

/** Returns sample documentation for the hero model. */
export async function mockGetDocumentation(modelId: string): Promise<Documentation | null> {
  await mockDelay()
  return modelId === 'M001' ? structuredClone(documentationFixture as Documentation) : null
}

/** Returns sample redevelopment results: M001 without legacy outputs, M002 stopped with an error. */
export async function mockGetRedevelopment(modelId: string): Promise<RedevelopResult | null> {
  await mockDelay()
  const result = mockRedevelopment[modelId]
  return result ? structuredClone(result) : null
}

/** Returns sample validation metrics and narrative for the hero model. */
export async function mockGetValidation(modelId: string): Promise<ValidationView | null> {
  await mockDelay()
  return modelId === 'M001' ? structuredClone(validationFixture as ValidationView) : null
}

/** Returns sample monitoring results for the hero model. */
export async function mockGetMonitoring(modelId: string): Promise<MonitoringResult | null> {
  await mockDelay()
  return modelId === 'M001' ? structuredClone(monitoringFixture as MonitoringResult) : null
}

/** Returns the sample compliance matrix for the hero model. */
export async function mockGetCompliance(modelId: string): Promise<Compliance | null> {
  await mockDelay()
  return modelId === 'M001' ? structuredClone(complianceFixture as Compliance) : null
}

/** Returns sample audit events, optionally filtered by model. */
export async function mockGetAudit(modelId?: string): Promise<Audit> {
  await mockDelay()
  const audit = structuredClone(mockAudit)
  return modelId
    ? { chain_valid: audit.chain_valid, events: audit.events.filter((event) => event.model_id === modelId) }
    : audit
}

/** Returns the sample factory metrics. */
export async function mockGetFactoryMetrics(): Promise<FactoryMetrics> {
  await mockDelay()
  return structuredClone(metricsFixture as FactoryMetrics)
}

/** Returns one sample text file by repository-relative path. */
export async function mockGetFile(path: string): Promise<FileView | null> {
  await mockDelay()
  const fileMap = filesFixture as Record<string, FileView>
  return fileMap[path] ? structuredClone(fileMap[path]) : null
}

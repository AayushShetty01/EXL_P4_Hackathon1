/* Exposes typed TanStack Query hooks for factory_console screens. */
import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getAudit,
  getCompliance,
  getDocumentation,
  getFactoryMetrics,
  getFile,
  getModel,
  getModels,
  getMonitoring,
  getRedevelopment,
  getRun,
  getValidation,
  postGateDecision,
  scanEstate,
  startRun,
} from './client'
import type { GateDecisionRequest, RunStartRequest, StageName } from './types'

export const queryKeys = {
  models: ['models'] as const,
  model: (modelId: string) => ['model', modelId] as const,
  run: (runId: string) => ['run', runId] as const,
  documentation: (modelId: string) => ['documentation', modelId] as const,
  redevelopment: (modelId: string) => ['redevelopment', modelId] as const,
  validation: (modelId: string) => ['validation', modelId] as const,
  monitoring: (modelId: string) => ['monitoring', modelId] as const,
  compliance: (modelId: string) => ['compliance', modelId] as const,
  audit: (modelId?: string) => ['audit', modelId ?? 'all'] as const,
  metrics: ['factory-metrics'] as const,
  file: (path: string) => ['file', path] as const,
}

/** Loads model inventory summaries. */
export function useModels() {
  return useQuery({ queryKey: queryKeys.models, queryFn: getModels })
}

/** Loads one model inventory record. */
export function useModel(modelId: string) {
  return useQuery({
    queryKey: queryKeys.model(modelId),
    queryFn: () => getModel(modelId),
    enabled: Boolean(modelId),
  })
}

/** Loads one run and polls while its pipeline is running. */
export function useRun(modelId: string, runId: string | null) {
  const queryClient = useQueryClient()
  const lastRefreshedStage = useRef<string | null>(null)
  const query = useQuery({
    queryKey: queryKeys.run(runId ?? ''),
    queryFn: () => getRun(runId ?? ''),
    enabled: Boolean(runId),
    refetchInterval: (currentQuery) =>
      currentQuery.state.data?.status === 'RUNNING' ? 2000 : false,
  })

  useEffect(() => {
    const run = query.data
    if (!run || run.status !== 'AWAITING_REVIEW' || !run.current_stage) {
      lastRefreshedStage.current = null
      return
    }

    const stageKey = `${run.run_id}:${run.current_stage}`
    if (lastRefreshedStage.current === stageKey) return
    lastRefreshedStage.current = stageKey
    void queryClient.invalidateQueries({
      queryKey: outputQueryKey(modelId, run.current_stage),
    })
  }, [modelId, query.data, queryClient])

  return query
}

/** Loads documentation when available. */
export function useDocumentation(modelId: string) {
  return useQuery({
    queryKey: queryKeys.documentation(modelId),
    queryFn: () => getDocumentation(modelId),
    enabled: Boolean(modelId),
  })
}

/** Loads redevelopment evidence when available. */
export function useRedevelopment(modelId: string) {
  return useQuery({
    queryKey: queryKeys.redevelopment(modelId),
    queryFn: () => getRedevelopment(modelId),
    enabled: Boolean(modelId),
  })
}

/** Loads validation metrics and narrative when available. */
export function useValidation(modelId: string) {
  return useQuery({
    queryKey: queryKeys.validation(modelId),
    queryFn: () => getValidation(modelId),
    enabled: Boolean(modelId),
  })
}

/** Loads monitoring results when available. */
export function useMonitoring(modelId: string) {
  return useQuery({
    queryKey: queryKeys.monitoring(modelId),
    queryFn: () => getMonitoring(modelId),
    enabled: Boolean(modelId),
  })
}

/** Loads the compliance matrix when available. */
export function useCompliance(modelId: string) {
  return useQuery({
    queryKey: queryKeys.compliance(modelId),
    queryFn: () => getCompliance(modelId),
    enabled: Boolean(modelId),
  })
}

/** Loads audit events for one model or for the whole estate. */
export function useAudit(modelId?: string) {
  return useQuery({
    queryKey: queryKeys.audit(modelId),
    queryFn: () => getAudit(modelId),
  })
}

/** Loads factory-wide dashboard metrics. */
export function useFactoryMetrics() {
  return useQuery({ queryKey: queryKeys.metrics, queryFn: getFactoryMetrics })
}

/** Loads one source or artifact text file. */
export function useFile(path: string | null) {
  return useQuery({
    queryKey: queryKeys.file(path ?? ''),
    queryFn: () => getFile(path ?? ''),
    enabled: Boolean(path),
  })
}

/** Starts a run and refreshes the affected model data. */
export function useStartRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ modelId, request }: { modelId: string; request: RunStartRequest }) =>
      startRun(modelId, request),
    onSuccess: async (_result, { modelId }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.models }),
        queryClient.invalidateQueries({ queryKey: queryKeys.model(modelId) }),
      ])
    },
  })
}

/** Submits a gate decision and refreshes run and model queries. */
export function useGateDecision() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      runId,
      stage,
      decision,
    }: {
      runId: string
      stage: StageName
      decision: GateDecisionRequest
    }) => postGateDecision(runId, stage, decision),
    onSuccess: async (run) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.run(run.run_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.models }),
        queryClient.invalidateQueries({ queryKey: queryKeys.model(run.model_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.audit() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.audit(run.model_id) }),
      ])
    },
  })
}

/** Scans the estate and refreshes inventory after success. */
export function useScanEstate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: scanEstate,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.models }),
        queryClient.invalidateQueries({ queryKey: queryKeys.metrics }),
      ])
    },
  })
}

/** Maps an awaiting stage to its result query for review-time refreshes. */
function outputQueryKey(modelId: string, stage: StageName) {
  switch (stage) {
    case 'discover':
      return queryKeys.model(modelId)
    case 'document':
      return queryKeys.documentation(modelId)
    case 'redevelop':
      return queryKeys.redevelopment(modelId)
    case 'validate':
      return queryKeys.validation(modelId)
    case 'monitor':
      return queryKeys.monitoring(modelId)
  }
}

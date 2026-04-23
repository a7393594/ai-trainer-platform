/**
 * Pipeline Studio — API Client
 */
import type {
  CaseSummary,
  LabBatchRerunResponse,
  LabOverrides,
  LabRerunResponse,
  LabSourceType,
  PipelineComparison,
  PipelineRunDetail,
  RunDetailResponse,
  RunListResponse,
} from './types'

const AI_ENGINE_URL = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

async function request<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${AI_ENGINE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `API Error: ${res.status}`)
  }
  return res.json()
}

// ============================================================================
// Live Mode (MVP)
// ============================================================================

export async function listPipelineRuns(
  projectId: string,
  opts: { limit?: number; mode?: 'live' | 'lab'; cursor?: string } = {}
): Promise<RunListResponse> {
  const params = new URLSearchParams()
  if (opts.limit) params.set('limit', String(opts.limit))
  if (opts.mode) params.set('mode', opts.mode)
  if (opts.cursor) params.set('cursor', opts.cursor)
  const qs = params.toString()
  return request<RunListResponse>(
    `/api/v1/pipeline/runs/by-project/${projectId}${qs ? `?${qs}` : ''}`
  )
}

export async function getPipelineRunDetail(runId: string): Promise<RunDetailResponse> {
  return request<RunDetailResponse>(`/api/v1/pipeline/runs/detail/${runId}`)
}

/** 依 message_id 查對應的 pipeline run（history 頁面用）。404 時回傳 null。*/
export async function getPipelineRunByMessage(
  messageId: string
): Promise<RunDetailResponse | null> {
  try {
    return await request<RunDetailResponse>(
      `/api/v1/pipeline/runs/by-message/${messageId}`
    )
  } catch (err) {
    if (err instanceof Error && err.message.includes('404')) return null
    if (err instanceof Error && err.message.includes('No pipeline run')) return null
    throw err
  }
}

// ============================================================================
// Lab Mode (v1)
// ============================================================================

export async function forkToLab(
  projectId: string,
  seedRunId: string
): Promise<{ run: PipelineRunDetail }> {
  return request<{ run: PipelineRunDetail }>('/api/v1/pipeline/runs/lab', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, seed_run_id: seedRunId }),
  })
}

export async function compareNode(
  runId: string,
  nodeId: string,
  models: string[],
  promptOverride?: Array<{ role: string; content: string }>
): Promise<{ comparisons: PipelineComparison[] }> {
  return request<{ comparisons: PipelineComparison[] }>(
    `/api/v1/pipeline/runs/${runId}/nodes/${nodeId}/compare`,
    {
      method: 'POST',
      body: JSON.stringify({ models, prompt_override: promptOverride }),
    }
  )
}

export async function rerunNode(
  runId: string,
  nodeId: string,
  opts: {
    modelOverride?: string
    promptOverride?: Array<{ role: string; content: string }>
    /** Batch 4A: extended config overrides */
    temperatureOverride?: number
    maxTokensOverride?: number
    toolIds?: string[]
    presetName?: string
  }
): Promise<{ comparison: PipelineComparison }> {
  return request<{ comparison: PipelineComparison }>(
    `/api/v1/pipeline/runs/${runId}/nodes/${nodeId}/rerun`,
    {
      method: 'POST',
      body: JSON.stringify({
        model_override: opts.modelOverride,
        prompt_override: opts.promptOverride,
        temperature_override: opts.temperatureOverride,
        max_tokens_override: opts.maxTokensOverride,
        tool_ids: opts.toolIds,
        preset_name: opts.presetName,
      }),
    }
  )
}

// ============================================================================
// Batch 4A: Rerun Presets
// ============================================================================

export interface RerunPreset {
  id: string
  project_id: string
  node_type: string
  name: string
  description?: string | null
  model?: string | null
  system_prompt?: string | null
  temperature?: number | null
  max_tokens?: number | null
  tool_ids?: string[] | null
  created_at: string
}

export async function listPresets(projectId: string, nodeType?: string): Promise<{ presets: RerunPreset[] }> {
  const qs = new URLSearchParams({ project_id: projectId })
  if (nodeType) qs.set('node_type', nodeType)
  return request<{ presets: RerunPreset[] }>(`/api/v1/pipeline/presets?${qs.toString()}`)
}

export async function createPreset(data: {
  project_id: string
  node_type: string
  name: string
  description?: string
  model?: string
  system_prompt?: string
  temperature?: number
  max_tokens?: number
  tool_ids?: string[]
}): Promise<{ preset: RerunPreset }> {
  return request<{ preset: RerunPreset }>('/api/v1/pipeline/presets', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function deletePreset(presetId: string): Promise<{ deleted: string }> {
  return request<{ deleted: string }>(`/api/v1/pipeline/presets/${presetId}`, {
    method: 'DELETE',
  })
}

// ============================================================================
// Batch 4B: Pipeline Config (per-project per-node defaults)
// ============================================================================

export interface NodeConfig {
  model?: string
  temperature?: number
  max_tokens?: number
  tool_ids?: string[]
  system_prompt_prefix?: string
  notes?: string
}

export interface PipelineConfig {
  project_id: string
  node_configs: Record<string, NodeConfig>
  updated_at?: string
  updated_by?: string | null
}

export async function getPipelineConfig(projectId: string): Promise<{ config: PipelineConfig }> {
  return request<{ config: PipelineConfig }>(`/api/v1/pipeline/config/${projectId}`)
}

export async function savePipelineConfig(projectId: string, nodeConfigs: Record<string, NodeConfig>): Promise<{ config: PipelineConfig }> {
  return request<{ config: PipelineConfig }>('/api/v1/pipeline/config', {
    method: 'PUT',
    body: JSON.stringify({ project_id: projectId, node_configs: nodeConfigs }),
  })
}

// ============================================================================
// Batch 4C/D/E/F: DAG + Node Types + A/B Compare
// ============================================================================

export interface NodeType {
  id: string
  type_key: string
  name: string
  description?: string
  category: string
  icon?: string
  schema?: { fields?: string[] }
  is_builtin: boolean
}

export interface DAGNode {
  id: string
  type_key: string
  label: string
  config: Record<string, unknown>
  position?: { x: number; y: number }
}

export interface DAGEdge {
  from: string
  to: string
}

export interface PipelineDAG {
  id: string
  project_id: string
  name: string
  version: number
  is_active: boolean
  nodes: DAGNode[]
  edges: DAGEdge[]
  description?: string
  created_at: string
  updated_at?: string
}

export async function listNodeTypes(): Promise<{ node_types: NodeType[] }> {
  return request<{ node_types: NodeType[] }>('/api/v1/pipeline/node-types')
}

export async function getActiveDag(projectId: string): Promise<{ dag: PipelineDAG }> {
  return request<{ dag: PipelineDAG }>(`/api/v1/pipeline/dag/${projectId}`)
}

export async function listDags(projectId: string): Promise<{ dags: PipelineDAG[] }> {
  return request<{ dags: PipelineDAG[] }>(`/api/v1/pipeline/dags/${projectId}`)
}

export async function createDag(data: {
  project_id: string
  name: string
  nodes: DAGNode[]
  edges: DAGEdge[]
  description?: string
  activate?: boolean
}): Promise<{ dag: PipelineDAG }> {
  return request<{ dag: PipelineDAG }>('/api/v1/pipeline/dag', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateDag(dagId: string, patch: {
  nodes?: DAGNode[]
  edges?: DAGEdge[]
  name?: string
  description?: string
}): Promise<{ dag: PipelineDAG }> {
  return request<{ dag: PipelineDAG }>(`/api/v1/pipeline/dag/${dagId}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  })
}

export async function activateDag(dagId: string): Promise<{ dag: PipelineDAG }> {
  return request<{ dag: PipelineDAG }>(`/api/v1/pipeline/dag/${dagId}/activate`, {
    method: 'POST',
  })
}

export async function deleteDag(dagId: string): Promise<{ deleted: string }> {
  return request<{ deleted: string }>(`/api/v1/pipeline/dag/${dagId}`, {
    method: 'DELETE',
  })
}

export interface ABCompareResult {
  dag_a: { id: string; name: string; version: number }
  dag_b: { id: string; name: string; version: number }
  results: Array<{
    input: string
    a: { output: string; model: string; tokens_in: number; tokens_out: number; latency_ms: number; error?: string | null }
    b: { output: string; model: string; tokens_in: number; tokens_out: number; latency_ms: number; error?: string | null }
  }>
}

export async function compareDags(dagAId: string, dagBId: string, testInputs: string[]): Promise<ABCompareResult> {
  return request<ABCompareResult>('/api/v1/pipeline/dag/compare', {
    method: 'POST',
    body: JSON.stringify({
      dag_a_id: dagAId,
      dag_b_id: dagBId,
      test_inputs: testInputs,
    }),
  })
}

export async function selectComparison(
  runId: string,
  nodeId: string,
  comparisonId: string
): Promise<{ comparison: PipelineComparison }> {
  return request<{ comparison: PipelineComparison }>(
    `/api/v1/pipeline/runs/${runId}/nodes/${nodeId}/select`,
    {
      method: 'POST',
      body: JSON.stringify({ comparison_id: comparisonId }),
    }
  )
}

export async function saveComparisonAsPrompt(
  comparisonId: string,
  changeNotes?: string
): Promise<{ prompt_version: { id: string; version: number; content: string } | null }> {
  return request<{
    prompt_version: { id: string; version: number; content: string } | null
  }>(`/api/v1/pipeline/comparisons/${comparisonId}/save-as-prompt`, {
    method: 'POST',
    body: JSON.stringify({ change_notes: changeNotes }),
  })
}

// ============================================================================
// Models (dynamic availability detection)
// ============================================================================

export interface ModelInfo {
  id: string
  label: string
  provider: string
  available: boolean
  cost: string
  notes: string
}

export async function listAvailableModels(): Promise<ModelInfo[]> {
  const res = await request<{ models: ModelInfo[] }>('/api/v1/models')
  return res.models.filter((m) => m.available)
}

// ============================================================================
// v2: auto-scoring, save as test case, delete
// ============================================================================

export async function scoreComparison(
  comparisonId: string,
  opts: { judgeModel?: string; principles?: string; forceRescore?: boolean } = {}
): Promise<{ comparison: PipelineComparison; cached: boolean }> {
  return request<{ comparison: PipelineComparison; cached: boolean }>(
    `/api/v1/pipeline/comparisons/${comparisonId}/score`,
    {
      method: 'POST',
      body: JSON.stringify({
        judge_model: opts.judgeModel,
        principles: opts.principles,
        force_rescore: opts.forceRescore,
      }),
    }
  )
}

export async function saveComparisonAsTestCase(
  comparisonId: string,
  opts: { category?: string; tags?: string[] } = {}
): Promise<{
  test_case: { id: string; input_text: string; expected_output: string } | null
}> {
  return request<{
    test_case: { id: string; input_text: string; expected_output: string } | null
  }>(`/api/v1/pipeline/comparisons/${comparisonId}/save-as-test-case`, {
    method: 'POST',
    body: JSON.stringify({ category: opts.category, tags: opts.tags }),
  })
}

export async function deletePipelineRun(
  runId: string
): Promise<{ deleted: string }> {
  return request<{ deleted: string }>(`/api/v1/pipeline/runs/${runId}`, {
    method: 'DELETE',
  })
}

// ============================================================================
// Experiment Studio (Lab)
// ============================================================================

export async function listCases(
  projectId: string,
  opts: { sourceType?: LabSourceType; limit?: number } = {}
): Promise<{ items: CaseSummary[] }> {
  const params = new URLSearchParams()
  if (opts.sourceType) params.set('source_type', opts.sourceType)
  if (opts.limit) params.set('limit', String(opts.limit))
  const qs = params.toString()
  return request<{ items: CaseSummary[] }>(
    `/api/v1/lab/cases/by-project/${projectId}${qs ? `?${qs}` : ''}`
  )
}

export async function labRerun(body: {
  source_type: LabSourceType
  source_id: string
  input?: string
  overrides?: LabOverrides
  lab_run_id?: string
}): Promise<LabRerunResponse> {
  return request<LabRerunResponse>('/api/v1/lab/rerun', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function labBatchRerun(body: {
  source_type: LabSourceType
  source_id: string
  inputs: string[]
  overrides?: LabOverrides
  lab_run_id?: string
}): Promise<LabBatchRerunResponse> {
  return request<LabBatchRerunResponse>('/api/v1/lab/batch-rerun', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function saveLabOverrides(
  labRunId: string,
  body: { overrides?: LabOverrides; demo_inputs?: string[] }
): Promise<{ run: unknown }> {
  return request<{ run: unknown }>(`/api/v1/lab/runs/${labRunId}/overrides`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

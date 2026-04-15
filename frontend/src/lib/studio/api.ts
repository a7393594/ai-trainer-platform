/**
 * Pipeline Studio — API Client
 */
import type {
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
  }
): Promise<{ comparison: PipelineComparison }> {
  return request<{ comparison: PipelineComparison }>(
    `/api/v1/pipeline/runs/${runId}/nodes/${nodeId}/rerun`,
    {
      method: 'POST',
      body: JSON.stringify({
        model_override: opts.modelOverride,
        prompt_override: opts.promptOverride,
      }),
    }
  )
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

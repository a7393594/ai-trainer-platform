/**
 * Pipeline Studio — TypeScript 型別定義
 * 對應 ai-engine/app/core/pipeline/tracer.py 的 NodeSpan / PipelineRun 序列化格式。
 */

export type NodeType = 'input' | 'process' | 'model' | 'parallel' | 'tool' | 'output'

export type NodeStatus = 'running' | 'ok' | 'error'

export interface NodeSpan {
  id: string
  type: NodeType
  label: string
  parent_id: string | null
  started_at_ms: number
  finished_at_ms: number | null
  latency_ms: number
  status: NodeStatus
  model: string | null
  tokens_in: number
  tokens_out: number
  cost_usd: number
  input_ref: unknown
  output_ref: unknown
  metadata: Record<string, unknown>
  error: string | null
}

export interface NodeEdge {
  from: string
  to: string
}

export interface NodesJson {
  nodes: NodeSpan[]
  edges: NodeEdge[]
}

export interface PipelineRunSummary {
  id: string
  project_id: string
  session_id: string | null
  message_id: string | null
  mode: 'live' | 'lab'
  input_text: string
  total_cost_usd: number
  total_duration_ms: number
  status: 'running' | 'completed' | 'failed'
  parent_run_id: string | null
  created_at: string
}

export interface PipelineRunDetail extends PipelineRunSummary {
  nodes_json: NodesJson
  triggered_by: string | null
}

export interface PipelineComparison {
  id: string
  pipeline_run_id: string
  node_id: string
  model: string
  input_prompt: string
  output_text: string
  input_tokens: number
  output_tokens: number
  cost_usd: number
  latency_ms: number
  score: number | null
  score_reason: string | null
  score_model: string | null
  is_selected: boolean
  prompt_version_id: string | null
  created_at: string
}

export interface RunDetailResponse {
  run: PipelineRunDetail
  comparisons_by_node: Record<string, PipelineComparison[]>
}

export interface RunListResponse {
  runs: PipelineRunSummary[]
  next_cursor: string | null
}

import type {
  AnalyticsSummary,
  RulingResult,
  RulingHistory,
  RuleItem,
  RuleSource,
  ModelInfo,
  SystemConfig,
} from '@/types/referee';

// 共用 AI Trainer 的後端(同一個 :8000 server,referee 端點在 /api/v1/referee/ prefix)
const API_BASE = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000';

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

export function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  return request<AnalyticsSummary>('/api/v1/referee/analytics/summary');
}

export function submitRuling(
  dispute: string,
  gameContext: Record<string, unknown>,
  options?: { force_dual_model?: boolean; force_triple_model?: boolean }
): Promise<RulingResult> {
  return request<RulingResult>('/api/v1/referee/ruling', {
    method: 'POST',
    body: JSON.stringify({
      dispute,
      game_context: gameContext,
      ...options,
    }),
  });
}

export function getRulingHistory(limit?: number): Promise<RulingHistory[]> {
  const params = limit ? `?limit=${limit}` : '';
  return request<RulingHistory[]>(`/api/v1/referee/ruling/history${params}`);
}

export function getRulingDetail(id: string): Promise<RulingResult> {
  return request<RulingResult>(`/api/v1/referee/ruling/${id}`);
}

export function searchRules(query: string, topK?: number): Promise<RuleItem[]> {
  const params = new URLSearchParams({ query });
  if (topK) params.set('top_k', String(topK));
  return request<RuleItem[]>(`/api/v1/referee/rules/search?${params}`);
}

export function listRuleSources(): Promise<RuleSource[]> {
  return request<RuleSource[]>('/api/v1/referee/rules/sources');
}

export function listRules(sourceId?: string, topic?: string): Promise<RuleItem[]> {
  const params = new URLSearchParams();
  if (sourceId) params.set('source_id', sourceId);
  if (topic) params.set('topic', topic);
  const qs = params.toString();
  return request<RuleItem[]>(`/api/v1/referee/rules/list${qs ? `?${qs}` : ''}`);
}

export function getConfig(): Promise<SystemConfig> {
  return request<SystemConfig>('/api/v1/referee/config');
}

export function updateConfig(data: Partial<SystemConfig>): Promise<SystemConfig> {
  return request<SystemConfig>('/api/v1/referee/config', {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export function listModels(): Promise<ModelInfo[]> {
  return request<ModelInfo[]>('/api/v1/referee/models');
}

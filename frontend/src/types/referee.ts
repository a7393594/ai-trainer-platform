export interface ConfidenceData {
  verbalized: number;
  consistency_score: number;
  cross_model_agreement: number;
  calibrated_final: number;
  routing_mode: string;
}

export interface VotingResult {
  agreement: boolean;
  primary?: { model: string; decision: string; cost_usd: number };
  secondary?: { model: string; decision: string; cost_usd: number };
  tertiary?: { model: string; decision: string; cost_usd: number };
}

export interface RulingResult {
  ruling_id: string;
  decision: string;
  applicable_rules: string[];
  reasoning: string;
  subsequent_steps: string[];
  confidence: ConfidenceData;
  voting?: VotingResult;
  rules_retrieved: Array<{
    rule_code: string;
    title: string;
    score: number;
    full_text?: string;
    topic?: string;
  }>;
  model_used: string;
  latency_ms: number;
  total_cost_usd: number;
  audit_log?: Record<string, unknown>;
  created_at?: string;
}

export interface RulingHistory {
  id: string;
  ruling_id?: string;
  dispute_preview?: string;
  final_decision?: string;
  decision_preview?: string;
  applicable_rules?: string[];
  effective_rule?: string;
  confidence: number | ConfidenceData;
  routing_mode?: string;
  model_used?: string;
  total_cost_usd?: number;
  latency_ms?: number;
  created_at?: string;
}

export interface AnalyticsSummary {
  total_rulings: number;
  avg_confidence: number;
  total_cost_usd: number;
  avg_latency_ms: number;
  mode_distribution: Record<string, number>;
  confidence_buckets: Record<string, number>;
  model_usage: Record<string, number>;
  recent_rulings: RulingHistory[];
  rules_count?: number;
}

export interface RuleItem {
  rule_code: string;
  title: string;
  full_text: string;
  topic: string;
  source_id: string;
  requires_judgment: boolean;
  tags?: string[];
}

export interface RuleSource {
  source_id: string;
  name: string;
  rule_count: number;
  description?: string;
}

export interface ModelInfo {
  model_id: string;
  provider: string;
  display_name: string;
  available: boolean;
  cost_per_1k_input?: number;
  cost_per_1k_output?: number;
}

export interface SystemConfig {
  primary_model: string;
  backup_model: string;
  triage_model: string;
  auto_decide_threshold: number;
  human_confirm_threshold: number;
  enable_dual_model: boolean;
  enable_triple_model: boolean;
  consistency_samples: number;
  temperature: number;
}

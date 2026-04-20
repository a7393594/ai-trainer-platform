-- ============================================
-- AI Trainer Platform — Supabase Migration
-- 完整 Schema + RLS 安全策略
-- ============================================

-- 啟用必要的擴充
CREATE EXTENSION IF NOT EXISTS "pgcrypto";    -- UUID 產生
CREATE EXTENSION IF NOT EXISTS "vector";       -- pgvector（capability_rules 的 trigger_embedding）

-- ============================================
-- 基礎層：租戶 & 使用者
-- ============================================

CREATE TABLE tenants (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  plan          TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'pro', 'enterprise')),
  settings      JSONB NOT NULL DEFAULT '{}',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  auth_user_id  UUID UNIQUE,                -- 對應 Supabase Auth 的 user id
  email         TEXT NOT NULL,
  display_name  TEXT,
  role          TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin', 'trainer', 'viewer')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_auth ON users(auth_user_id);

-- ============================================
-- 專案層
-- ============================================

CREATE TABLE projects (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  description     TEXT,
  domain_template TEXT,
  status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'training', 'active', 'archived')),
  settings        JSONB NOT NULL DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_tenant ON projects(tenant_id);

-- ============================================
-- 訓練對話層
-- ============================================

CREATE TABLE training_sessions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id       UUID NOT NULL REFERENCES users(id),
  session_type  TEXT NOT NULL DEFAULT 'freeform' CHECK (session_type IN ('onboarding', 'freeform', 'capability')),
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at      TIMESTAMPTZ
);

CREATE INDEX idx_sessions_project ON training_sessions(project_id);

CREATE TABLE training_messages (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id    UUID NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
  role          TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content       TEXT NOT NULL,
  metadata      JSONB NOT NULL DEFAULT '{}',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_messages_session ON training_messages(session_id);
CREATE INDEX idx_messages_created ON training_messages(created_at);

CREATE TABLE feedbacks (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id      UUID NOT NULL REFERENCES training_messages(id) ON DELETE CASCADE,
  rating          TEXT NOT NULL CHECK (rating IN ('correct', 'partial', 'wrong')),
  correction_text TEXT,
  created_by      UUID REFERENCES users(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_feedbacks_message ON feedbacks(message_id);

-- ============================================
-- Prompt 層
-- ============================================

CREATE TABLE prompt_versions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  content       TEXT NOT NULL,
  version       INT NOT NULL,
  is_active     BOOLEAN NOT NULL DEFAULT false,
  eval_score    FLOAT,
  change_notes  TEXT,
  created_by    UUID REFERENCES users(id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_prompts_project ON prompt_versions(project_id);
CREATE UNIQUE INDEX idx_prompts_active ON prompt_versions(project_id) WHERE is_active = true;

-- ============================================
-- 知識庫層
-- ============================================

CREATE TABLE knowledge_docs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title         TEXT NOT NULL,
  source_type   TEXT NOT NULL CHECK (source_type IN ('upload', 'url', 'auto_extract')),
  raw_content   TEXT,
  file_path     TEXT,
  chunk_count   INT NOT NULL DEFAULT 0,
  status        TEXT NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'ready', 'error')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_docs_project ON knowledge_docs(project_id);

CREATE TABLE knowledge_chunks (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id          UUID NOT NULL REFERENCES knowledge_docs(id) ON DELETE CASCADE,
  content         TEXT NOT NULL,
  qdrant_point_id TEXT NOT NULL,
  chunk_index     INT NOT NULL DEFAULT 0,
  metadata        JSONB NOT NULL DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chunks_doc ON knowledge_chunks(doc_id);

-- ============================================
-- 評估層
-- ============================================

CREATE TABLE eval_test_cases (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  input_text      TEXT NOT NULL,
  expected_output TEXT NOT NULL,
  category        TEXT,
  is_active       BOOLEAN NOT NULL DEFAULT true,
  created_by      UUID REFERENCES users(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_testcases_project ON eval_test_cases(project_id);

CREATE TABLE eval_runs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  prompt_version_id UUID REFERENCES prompt_versions(id),
  model_used        TEXT,
  total_score       FLOAT,
  passed_count      INT NOT NULL DEFAULT 0,
  failed_count      INT NOT NULL DEFAULT 0,
  run_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_runs_project ON eval_runs(project_id);

CREATE TABLE eval_results (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id          UUID NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
  test_case_id    UUID NOT NULL REFERENCES eval_test_cases(id),
  actual_output   TEXT NOT NULL,
  score           FLOAT,
  passed          BOOLEAN,
  details         JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_results_run ON eval_results(run_id);

-- ============================================
-- Fine-tune 層
-- ============================================

CREATE TABLE finetune_jobs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  provider            TEXT NOT NULL,
  model_base          TEXT NOT NULL,
  training_data_count INT NOT NULL DEFAULT 0,
  status              TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  result_model_id     TEXT,
  error_message       TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at        TIMESTAMPTZ
);

CREATE INDEX idx_finetune_project ON finetune_jobs(project_id);

-- ============================================
-- LLM 設定層
-- ============================================

CREATE TABLE llm_configs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  provider            TEXT NOT NULL,
  model               TEXT NOT NULL,
  api_key_encrypted   TEXT NOT NULL,
  is_default          BOOLEAN NOT NULL DEFAULT false,
  cost_per_1k_tokens  FLOAT,
  settings            JSONB NOT NULL DEFAULT '{}',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_llm_tenant ON llm_configs(tenant_id);

-- ============================================
-- Agent 能力層
-- ============================================

CREATE TABLE widget_templates (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  widget_type   TEXT NOT NULL CHECK (widget_type IN (
    'single_select', 'multi_select', 'rank', 'confirm',
    'form', 'card_carousel', 'date_picker', 'slider'
  )),
  config_json   JSONB NOT NULL,
  created_by    UUID REFERENCES users(id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_widgets_project ON widget_templates(project_id);

CREATE TABLE tools (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  description   TEXT,
  tool_type     TEXT NOT NULL CHECK (tool_type IN ('api_call', 'db_query', 'webhook', 'internal_fn', 'mcp_server')),
  config_json   JSONB NOT NULL,
  auth_config   JSONB NOT NULL DEFAULT '{}',
  permissions   TEXT[] NOT NULL DEFAULT '{}',
  rate_limit    TEXT,
  is_active     BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tools_tenant ON tools(tenant_id);

CREATE TABLE capability_rules (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  trigger_description   TEXT NOT NULL,
  trigger_embedding     vector(1536),
  action_type           TEXT NOT NULL CHECK (action_type IN ('widget', 'tool_call', 'workflow', 'composite')),
  action_config         JSONB NOT NULL,
  priority              INT NOT NULL DEFAULT 0,
  is_active             BOOLEAN NOT NULL DEFAULT true,
  eval_score            FLOAT,
  created_by            UUID REFERENCES users(id),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_caps_project ON capability_rules(project_id);

CREATE TABLE workflows (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name                  TEXT NOT NULL,
  trigger_description   TEXT NOT NULL,
  steps_json            JSONB NOT NULL,
  is_active             BOOLEAN NOT NULL DEFAULT true,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_workflows_project ON workflows(project_id);

CREATE TABLE workflow_runs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id   UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  session_id    UUID REFERENCES training_sessions(id),
  user_id       UUID NOT NULL REFERENCES users(id),
  current_step  TEXT,
  status        TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'waiting_input')),
  context_json  JSONB NOT NULL DEFAULT '{}',
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at  TIMESTAMPTZ
);

CREATE INDEX idx_wfruns_workflow ON workflow_runs(workflow_id);

CREATE TABLE audit_logs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id       UUID REFERENCES users(id),
  action_type   TEXT NOT NULL,
  tool_id       UUID REFERENCES tools(id),
  request_data  JSONB,
  response_data JSONB,
  status        TEXT CHECK (status IN ('success', 'error', 'dry_run')),
  duration_ms   INT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_tenant ON audit_logs(tenant_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at);

-- ============================================
-- RLS（行級安全策略）
-- 確保每個租戶只能存取自己的資料
-- ============================================

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedbacks ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompt_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_docs ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE eval_test_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE eval_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE eval_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE finetune_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE widget_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE tools ENABLE ROW LEVEL SECURITY;
ALTER TABLE capability_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- 輔助函數：取得當前使用者的 tenant_id
CREATE OR REPLACE FUNCTION get_user_tenant_id()
RETURNS UUID AS $$
  SELECT tenant_id FROM users WHERE auth_user_id = auth.uid() LIMIT 1;
$$ LANGUAGE sql SECURITY DEFINER;

-- 租戶只能看到自己
CREATE POLICY tenant_isolation ON tenants
  FOR ALL USING (id = get_user_tenant_id());

-- 使用者只能看到同租戶的人
CREATE POLICY user_tenant_isolation ON users
  FOR ALL USING (tenant_id = get_user_tenant_id());

-- 專案：同租戶
CREATE POLICY project_tenant_isolation ON projects
  FOR ALL USING (tenant_id = get_user_tenant_id());

-- 以下表透過 project → tenant 鏈結
CREATE POLICY session_isolation ON training_sessions
  FOR ALL USING (project_id IN (SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()));

CREATE POLICY message_isolation ON training_messages
  FOR ALL USING (session_id IN (
    SELECT id FROM training_sessions WHERE project_id IN (
      SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()
    )
  ));

CREATE POLICY feedback_isolation ON feedbacks
  FOR ALL USING (message_id IN (
    SELECT id FROM training_messages WHERE session_id IN (
      SELECT id FROM training_sessions WHERE project_id IN (
        SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()
      )
    )
  ));

CREATE POLICY prompt_isolation ON prompt_versions
  FOR ALL USING (project_id IN (SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()));

CREATE POLICY doc_isolation ON knowledge_docs
  FOR ALL USING (project_id IN (SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()));

CREATE POLICY chunk_isolation ON knowledge_chunks
  FOR ALL USING (doc_id IN (
    SELECT id FROM knowledge_docs WHERE project_id IN (
      SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()
    )
  ));

CREATE POLICY testcase_isolation ON eval_test_cases
  FOR ALL USING (project_id IN (SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()));

CREATE POLICY run_isolation ON eval_runs
  FOR ALL USING (project_id IN (SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()));

CREATE POLICY result_isolation ON eval_results
  FOR ALL USING (run_id IN (
    SELECT id FROM eval_runs WHERE project_id IN (
      SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()
    )
  ));

CREATE POLICY finetune_isolation ON finetune_jobs
  FOR ALL USING (project_id IN (SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()));

CREATE POLICY llm_isolation ON llm_configs
  FOR ALL USING (tenant_id = get_user_tenant_id());

CREATE POLICY widget_isolation ON widget_templates
  FOR ALL USING (project_id IN (SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()));

CREATE POLICY tool_isolation ON tools
  FOR ALL USING (tenant_id = get_user_tenant_id());

CREATE POLICY cap_isolation ON capability_rules
  FOR ALL USING (project_id IN (SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()));

CREATE POLICY workflow_isolation ON workflows
  FOR ALL USING (project_id IN (SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()));

CREATE POLICY wfrun_isolation ON workflow_runs
  FOR ALL USING (workflow_id IN (
    SELECT id FROM workflows WHERE project_id IN (
      SELECT id FROM projects WHERE tenant_id = get_user_tenant_id()
    )
  ));

CREATE POLICY audit_isolation ON audit_logs
  FOR ALL USING (tenant_id = get_user_tenant_id());

-- ============================================
-- updated_at 自動更新觸發器
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER projects_updated_at
  BEFORE UPDATE ON projects
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ============================================================================
-- Pipeline Studio v2.2 (Phase 7 add-on)
-- ============================================================================
-- Note: runtime code uses the `ait_` prefix for all tables. These two new
-- tables follow that convention even though the earlier tables in this file
-- were historically defined without the prefix.
-- ============================================================================

-- Pipeline run = one trace of a chat turn going through the orchestrator.
-- nodes_json holds the full {nodes, edges} graph rendered by the frontend.
CREATE TABLE IF NOT EXISTS ait_pipeline_runs (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id         UUID NOT NULL,
  session_id         UUID,
  message_id         UUID,
  mode               TEXT NOT NULL DEFAULT 'live' CHECK (mode IN ('live','lab')),
  input_text         TEXT NOT NULL,
  nodes_json         JSONB NOT NULL,
  total_cost_usd     NUMERIC(14,8) NOT NULL DEFAULT 0,
  total_duration_ms  INTEGER NOT NULL DEFAULT 0,
  parent_run_id      UUID,
  triggered_by       UUID,
  status             TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('running','completed','failed')),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_project
  ON ait_pipeline_runs(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_session
  ON ait_pipeline_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_message
  ON ait_pipeline_runs(message_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_parent
  ON ait_pipeline_runs(parent_run_id);

-- Per-node multi-model comparison candidates (Lab Mode v1)
CREATE TABLE IF NOT EXISTS ait_pipeline_node_comparisons (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_run_id    UUID NOT NULL REFERENCES ait_pipeline_runs(id) ON DELETE CASCADE,
  node_id            TEXT NOT NULL,
  model              TEXT NOT NULL,
  input_prompt       TEXT NOT NULL,
  output_text        TEXT NOT NULL,
  input_tokens       INTEGER NOT NULL DEFAULT 0,
  output_tokens      INTEGER NOT NULL DEFAULT 0,
  cost_usd           NUMERIC(14,8) NOT NULL DEFAULT 0,
  latency_ms         INTEGER NOT NULL DEFAULT 0,
  score              INTEGER,
  score_reason       TEXT,
  score_model        TEXT,
  is_selected        BOOLEAN NOT NULL DEFAULT false,
  prompt_version_id  UUID,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_cmp_run
  ON ait_pipeline_node_comparisons(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_cmp_node
  ON ait_pipeline_node_comparisons(pipeline_run_id, node_id);
-- At most one selected candidate per (run, node)
CREATE UNIQUE INDEX IF NOT EXISTS idx_pipeline_cmp_selected
  ON ait_pipeline_node_comparisons(pipeline_run_id, node_id)
  WHERE is_selected = true;

-- RLS (service_role bypasses these; scoped policies added when dashboard
-- migrates to user-scoped tokens, matching the pattern used for other ait_ tables)
ALTER TABLE ait_pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ait_pipeline_node_comparisons ENABLE ROW LEVEL SECURITY;

-- ================================================================
-- Experiment Studio (Lab) — metadata bag for lab runs
-- Stores {source_type, source_id, overrides:{...}, demo_inputs:[...]}
-- Additive only; safe to re-run.
-- ================================================================
ALTER TABLE ait_pipeline_runs
  ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_metadata_source
  ON ait_pipeline_runs((metadata->>'source_type'));

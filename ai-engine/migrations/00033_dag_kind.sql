-- Migration: V4 DAG retirement — 加 dag_kind 區分 lab / workflow / retired_chat
-- Created: 2026-04-29 (V4 chat engine refactor)
--
-- 背景:V4 起 chat 流量改走 app/core/chat/engine.py,DAG executor 不再服務 chat。
--      但 DAG 物件本體保留(觀察用 + Pipeline Studio playground + workflow 觸發)。
-- 此 migration 加 dag_kind 欄位區分三種用途:
--   - lab:           Pipeline Studio playground 手動編輯的 DAG(預設值)
--   - workflow:      由 chat engine 的 start_workflow tool 觸發的 DAG
--   - retired_chat:  舊 V3 chat 路徑的 DAG 物件,唯讀觀察用,執行會被 guard 擋掉

-- 1. 加欄位(預設 'lab' — 新建 DAG 預設視為 Pipeline Studio playground)
ALTER TABLE ait_pipeline_dags
ADD COLUMN IF NOT EXISTS dag_kind TEXT NOT NULL DEFAULT 'lab';

-- 2. 加 CHECK constraint(只允許三種值)
ALTER TABLE ait_pipeline_dags
DROP CONSTRAINT IF EXISTS ait_pipeline_dags_dag_kind_check;

ALTER TABLE ait_pipeline_dags
ADD CONSTRAINT ait_pipeline_dags_dag_kind_check
CHECK (dag_kind IN ('lab', 'workflow', 'retired_chat'));

-- 3. 把現有的 chat DAG 標記為 retired_chat
-- 判斷依據:
--   (a) name 含 "chat" 或 "default"(chat_adapter._seed_default_dag 用的命名)
--   (b) nodes 含 id="n_triage"(_seed_default_dag 種出來的標記節點)
UPDATE ait_pipeline_dags
SET dag_kind = 'retired_chat'
WHERE
  (name ILIKE '%chat%' OR name ILIKE '%default%')
  OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(nodes) AS node
    WHERE node->>'id' = 'n_triage'
  );

-- 4. 索引(之後 query workflow / lab DAG 用)
CREATE INDEX IF NOT EXISTS idx_ait_pipeline_dags_dag_kind
  ON ait_pipeline_dags(dag_kind);

-- 5. 增加 column comment
COMMENT ON COLUMN ait_pipeline_dags.dag_kind IS
  'V4: lab=Pipeline Studio playground, workflow=tool-triggered, retired_chat=legacy V3 chat path observe-only';

# 願景 vs 現況差距分析

> **最後更新：2026-04-23**
> 對照 vision-operation-flow.md 的每一步，標記現有實作的完成度。
> 本文件歷史：初版（Phase 1-6 完成時寫）標記為 ~85% 完成；本次更新反映到 Experiment Studio + Pipeline Studio + Method A 統一架構 + Poker Coach 6 Phase 全完成之後的實況。

---

## 11 步驟對照（更新版）

| 步驟 | 願景描述 | 現況（2026-04-23）|
|------|---------|------|
| **1. 建立專案** | | |
| → 新建專案 | 輸入名稱 + 領域 | ✅ |
| → Onboarding 問答 | 5-8 題互動引導 | ✅ OnboardingManager |
| → 自動產出 Prompt | 根據回答生成 | ✅ |
| → **自動產出關鍵問題** | 10-20 個測試題 | ✅ 已補（`onboarding_auto_testcases` 測試覆蓋） |
| **2. 模型比較** | | |
| → 列出可用模型 + 價格 | 含價格/速度標籤 | ✅ 37-model registry |
| → 勾選多個模型 | checkbox 選擇 | ✅ Comparison create tab |
| → 批次執行 | N × M | ✅ comparison_engine |
| → 並排面板 | | ✅ grid per question |
| → 延遲 + 成本顯示 | | ✅ |
| → 評估矩陣 | 正確率×成本×延遲 | ✅ model_stats |
| **3. 人工評審** | | |
| → 標記 ✅/⚠️/❌ | 每個回答 | ✅ 三級（含 partial） |
| → 排名投票 | 第 1, 2, 3 | ✅ voted_rank |
| → AI 輔助評審 | 自動打分 | ✅ 已補（`eval_ai_review` 測試覆蓋；`/eval` 頁面有「全部評分」按鈕） |
| → 推薦最佳模型 | 綜合指數排名 | 🟡 矩陣完整，自動推薦演算法仍手動 |
| **4. 概念差分析** | | |
| → 自動找出弱點 | | ✅ analyze_gaps |
| → 弱點聚類 | 分類標籤 | ✅ 已補（`eval_gap_clustering` LLM 分類 + remediation 建議） |
| → 三路補齊按鈕 | RAG / Prompt / Eval | ✅ remediate endpoint |
| **5. 初步打磨** | | |
| → RAG 補齊 | | ✅ +URL ingestion |
| → Prompt 修正 | | ✅ |
| → Eval 監控 | | ✅ |
| → **打磨前後對比** | 自動重跑比分 | ✅ 已補（`eval_before_after` — `POST /eval/before-after/{project_id}`） |
| **6. 對話訓練** | | |
| → 對話介面 | | ✅ SSE streaming |
| → 回饋 👍⚠️👎 | | ✅ |
| → 互動 Widget | | ✅ 8 種 widget |
| → 附加圖片 / 手牌 | | ✅ AttachmentPicker / HandRecordPicker |
| → 工具自動調用 | | ✅ |
| **7. 自動優化** | | |
| → 負面回饋分析 | 3+ 筆觸發 | ✅ PromptOptimizer |
| → 產出建議 | | ✅ |
| → 審核 + 新版本 | | ✅（Prompts 新增「編輯（建立新版本）」modal） |
| → 自動評估 + 回歸偵測 | | ✅ |
| → 分數趨勢圖 | | ✅ SVG |
| **8. 工具串接** | | |
| → 註冊工具 | | ✅ 5 種 executor（api_call / db_query / webhook / internal_fn / mcp_server） |
| → 測試工具 | dry-run | ✅ |
| → AI 自動使用 | | ✅ |
| **9. 外部串接** | | |
| → Embed Token | iframe 嵌入 | ✅ postMessage bridge |
| → API Key | `sk_live_` | ✅ |
| → 使用量記錄 | | ✅ by_tool_name（`tool_stats` 已補） |
| **10. 觀察優化** | | |
| → 對話量 / 回饋分佈 / 工具頻率 / 成本 | | ✅ `/analytics` 全覆蓋 + CSV 匯出 |
| → 評估分數趨勢 | | ✅ |
| **11. 微調** | | |
| → 數據預覽 + 多格式匯出 | | ✅ OpenAI / Anthropic / Generic |
| → 建立訓練任務 | | ✅ job CRUD + poll |
| → **實際執行微調** | 呼叫 provider API | 🟡 skeleton 有，真送 OpenAI/Anthropic Fine-tune API 未驗證 |
| → **切換到新模型** | 自動替換 | ✅ 已補（`finetune_auto_switch`，poll 成功後更新 project.default_model） |

---

## 11 步驟完成度彙總

| 完成度 | 步驟數 | 說明 |
|---|---|---|
| ✅ 完全覆蓋 | 10 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 |
| 🟡 部分覆蓋 | 1 | 11（實際送 provider fine-tune 待驗證） |
| ❌ 完全缺失 | 0 | — |

**完成度估計：~97%**（vs 舊版估計 85-90%）。

---

## 超出原 vision 的新功能（計畫外新增）

以下均不在 `vision-operation-flow.md` 中，實作後已在線上：

### Agent 可觀測性
- **Pipeline Studio v2.2** (`/studio`)：AI 處理管線 8 節點視覺化 + Lab Mode fork 實驗 + 節點級 compare/rerun
- **Experiment Studio** (`/lab`)：4 來源統一 case browser（Pipeline / Workflow / Chat / Comparison）+ editable rerun + save-as-prompt / save-as-test-case
- **Langfuse trace** 整合（`/observability/trace/{project_id}`）
- **Context compression metrics** + **Session summarizer**（長對話自動摘要）

### 治理四件套
- **`/audit`** — tenant 級審計日誌瀏覽器（action / tool / status 篩選 + 展開 request/response）
- **`/budget`** — 月度預算 + 告警 webhook（Slack / Email / Generic 通知器）
- **`/handoff`** — Hand-off to human 工單系統（urgency 分級 + 客服接管）
- **`/quality`** — 負面回饋比率告警（wrong_high / negative_high 分級）

### Workflow 進階
- **Workflow Template Library**（4 個內建：support_escalation / refund_request / knowledge_fallback / nps_survey）
- **Workflow 分支 / 迴圈 / 並行**（if / parallel / loop 步驟類型 + safe eval）
- **capability → workflow auto-run**（capability_rules.action_type 支援 `handoff` + `workflow.auto`）
- **Workflow run trace viewer**

### RAG / 知識
- **URL 知識擷取**（非只 PDF/DOCX/TXT/CSV，可直接貼 URL）
- **Qdrant dual-write**（pgvector 主 + Qdrant 並行；per-project collection `ait_kb_{project_id}`）
- **Intent semantic match**（capability_rules.trigger_embedding cosine 比對，hybrid 模式）

### 商業 / 認證
- **Plan Limits**（free / pro / enterprise 各級限額）
- **Stripe billing skeleton**
- **SSO 登入**
- **A/B Test 頁面**（variant 編輯器 + 權重 + 即時 correct_rate + 以此結束 conclude）

### Poker 專屬（超出原 phase-7 撲克 demo 規模）
- **Poker Coach 6 Phase 全完成**（18 DB 表 + 14 後端模組 + 7 前端頁）
- **FSRS-4.5 間隔重複** 排程器
- **6 對手原型** LLM roleplay
- **Screenshot OCR**（Claude vision 牌桌解析）
- **Session Reports** 自動總結卡

### Method A 統一架構
- 單一 `ait_projects` + `project_type` enum + `domain_config` JSONB 驅動全部 UI / nav / API
- Referee 功能已併入（不再是獨立 repo），透過 project_type=referee 啟用
- 3 projects 同時運作：Poker Coach（trainer）、Customer Support AI（trainer）、Poker Referee AI（referee）

---

## 計畫內仍未完成

| 項目 | 位置 | 影響 |
|---|---|---|
| 實際送 Provider Fine-tune API | spec-v2 Phase 6 | `/finetune` 管線完整，但真呼叫 OpenAI/Anthropic 尚未驗證 |
| Capacitor + PWA 打包 | spec-v2 Phase 7 | 行動端體驗未閉環 |
| Landing Page | spec-v2 Phase 8 | 公開流量入口缺 |
| GTO Solver 實際接入 | Poker 領域 | 目前 LLM approx MVP，精度受限 |
| Knowledge 版本控制 | spec-v2 Phase 2 | 編輯是覆寫 |
| 從對話自動抽取知識候選 | spec-v2 Phase 2 | 需手動上傳 |
| 自動推薦最佳模型演算法 | vision 步驟 3 | 矩陣完整，但推薦 logic 尚未自動 |

---

## 跟 PokerVerse 生態的整合（新增章節）

本平台是 PokerVerse 生態的 AI 引擎，被 **C-end AI Coach** 透過 proxy 整合使用。整合點：

- **Proxy 層** 在 `pokerverse/b-end/c-end/src/app/api/ai-coach/`（feature branch `feature/tournament-lifecycle-batch2-5` 上）
- **user_id 映射** — C-end 的 `auth.uid()` → `ait_users.id`
- **Widget 標記** — `<!--WIDGET:...-->` 標記被 C-end 解析為互動按鈕
- **SSE 協議** — 對話串流透過 proxy 轉發
- **Onboarding / 儀表板 / 覆盤 / 複習 / 模擬** 六大模組走這條路線

詳見 `integration-c-end.md`（新建）。

---

## 結論

相較於初版，**11 個步驟中原本 3 個 P0/5 個 P1/2 個 P2 缺口，現在剩下 1 個 🟡（實際送 fine-tune）**。核心訓練循環已完全閉合；後續差距集中在**部署打磨**（PWA / Landing）與**生態整合**（真實 GTO Solver / Provider Fine-tune 執行）。

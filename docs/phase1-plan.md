# Phase 1：訓練對話 MVP — 詳細實作計畫

> **目標：** 完成核心對話迴圈 — 使用者能與 AI 對話、AI 能回覆、使用者能打分修正
> **前置條件：** Phase 0 骨架已建立、Supabase 專案已開通、至少一個 LLM API Key 可用
> **預估時間：** 3-4 週（無時間壓力，做對優先）

---

## 開工前的環境準備清單

```bash
# 1. Supabase 專案開通
#    → https://supabase.com/dashboard 建立新專案
#    → 取得 URL + anon key + service role key
#    → 在 SQL Editor 裡執行 supabase-migration.sql 建表

# 2. Qdrant Cloud 開通（或 Docker 本地跑）
#    → https://cloud.qdrant.io 免費方案
#    → 取得 URL + API Key
#    → 或本地：docker compose up qdrant -d

# 3. LLM API Key
#    → 至少準備一個：Anthropic 或 OpenAI
#    → 填入 ai-engine/.env

# 4. 安裝依賴
cd frontend && npm install
cd ../ai-engine && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt

# 5. 啟動
cd ai-engine && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

---

## Task 拆解（按開發順序）

---

### Week 1：打通核心管線

---

#### Task 1.1：Supabase 真實連線 + CRUD 工具函數
**新建：** `ai-engine/app/db/crud.py`

```
要做的事：
1. 建立通用 CRUD 工具函數：
   - create_tenant(name) → tenant
   - create_user(tenant_id, email, role) → user
   - create_project(tenant_id, name, domain_template) → project
   - create_session(project_id, user_id, session_type) → session
   - save_message(session_id, role, content, metadata) → message
   - get_session_messages(session_id) → list[message]
   - save_feedback(message_id, rating, correction_text) → feedback
   - get_active_prompt(project_id) → prompt_version
   - create_prompt_version(project_id, content, created_by) → prompt_version

2. 建立 seed 腳本 ai-engine/scripts/seed.py：
   - 一個 demo tenant（正義企業社）
   - 一個 demo user（admin 角色）
   - 一個 demo project（撲克 AI 教練）
   - 一個初始 prompt_version（is_active=true）

驗收標準：
 ✓ 跑 seed 腳本後，Supabase Dashboard 表裡有資料
 ✓ 所有 CRUD 函數可以正常讀寫
 ✓ 用 service_role key 繞過 RLS
```

---

#### Task 1.2：Agent Orchestrator 接上真實 DB
**修改：** `ai-engine/app/core/orchestrator/agent.py`

```
要做的事：
1. _create_session() → 真正寫入 training_sessions 表
2. _load_history() → 真正從 training_messages 表讀取
3. _save_message() → 真正寫入 training_messages 表
4. _load_active_prompt() → 從 prompt_versions 讀取 is_active=true 的版本
5. 加上 tenant_id / user_id 的驗證邏輯

驗收標準：
 ✓ POST /api/v1/chat 送訊息後，DB 裡有完整對話紀錄
 ✓ 重新打開同一個 session_id，歷史訊息正確載入
 ✓ 不同 tenant 的資料互相看不到
```

---

#### Task 1.3：前端 ↔ 後端完整串通
**修改：** `frontend/src/lib/ai-engine.ts` + `ChatInterface.tsx`

```
要做的事：
1. 確認 CORS 設定正確（Next.js dev server → FastAPI）
2. 測試完整流程：打字 → 送出 → 等待 → AI 回覆顯示
3. 處理錯誤狀態：
   - 後端斷線 → 「AI 引擎無法連線，請檢查後端是否啟動」
   - API Key 無效 → 「LLM 金鑰無效，請到設定頁更新」
   - 超時 → 「回覆超時，請重試」
4. 加上 streaming 支援（可選，先用非串流也行）

驗收標準：
 ✓ 能在瀏覽器裡跟 AI 正常對話
 ✓ 錯誤時顯示友善的中文錯誤訊息
 ✓ 載入中有動畫（已有 bouncing dots）
```

---

### Week 2：Onboarding Interview（引導式建立基線）

---

#### Task 2.1：領域模板系統
**新建：** `ai-engine/app/core/prompt/templates.py`

```
要做的事：
1. 定義領域模板的資料格式（JSON Schema）：
   {
     "id": "poker",
     "name": "撲克 AI 教練",
     "description": "訓練一個能回答撲克策略問題的 AI",
     "onboarding_questions": [
       {
         "id": "q1_level",
         "question": "你的俱樂部主要打什麼級別？",
         "widget_type": "single_select",
         "options": [
           {"id": "low", "label": "低級別 (1/2, 2/5)"},
           {"id": "mid", "label": "中級別 (5/10, 10/20)"},
           {"id": "high", "label": "高級別 (25/50+)"},
           {"id": "mixed", "label": "混合級別"}
         ],
         "required": true
       },
       {
         "id": "q2_table_type",
         "question": "常見的桌型是？",
         "widget_type": "multi_select",
         "options": [
           {"id": "6max", "label": "6人桌"},
           {"id": "9max", "label": "9人桌"},
           {"id": "heads_up", "label": "單挑"}
         ]
       },
       {
         "id": "q3_experience",
         "question": "你的成員平均打牌經驗大約多久？",
         "widget_type": "single_select",
         "options": [
           {"id": "beginner", "label": "新手 (<1年)"},
           {"id": "intermediate", "label": "有經驗 (1-3年)"},
           {"id": "advanced", "label": "老手 (3年+)"},
           {"id": "mixed", "label": "混合程度"}
         ]
       },
       {
         "id": "q4_tone",
         "question": "你希望 AI 教練的語氣風格？",
         "widget_type": "single_select",
         "options": [
           {"id": "professional", "label": "專業嚴謹"},
           {"id": "friendly", "label": "輕鬆友善"},
           {"id": "humorous", "label": "幽默風趣"},
           {"id": "coach", "label": "教練式（會挑戰你）"}
         ]
       },
       {
         "id": "q5_topics",
         "question": "最常被會員問到的問題類型？",
         "widget_type": "multi_select",
         "options": [
           {"id": "preflop", "label": "翻牌前策略"},
           {"id": "postflop", "label": "翻牌後打法"},
           {"id": "position", "label": "位置觀念"},
           {"id": "bankroll", "label": "籌碼管理"},
           {"id": "tournament", "label": "錦標賽策略"},
           {"id": "mental", "label": "心態管理"}
         ]
       },
       {
         "id": "q6_format",
         "question": "你偏好的回答格式？",
         "widget_type": "single_select",
         "options": [
           {"id": "concise", "label": "簡潔扼要（3-5句）"},
           {"id": "detailed", "label": "詳細解說（含分析過程）"},
           {"id": "example", "label": "舉例為主（用實際牌局說明）"}
         ]
       },
       {
         "id": "q7_language",
         "question": "回答語言？",
         "widget_type": "single_select",
         "options": [
           {"id": "zh_tw", "label": "繁體中文"},
           {"id": "zh_cn", "label": "簡體中文"},
           {"id": "en", "label": "English"},
           {"id": "mixed", "label": "中英混用（術語用英文）"}
         ]
       },
       {
         "id": "q8_rules",
         "question": "有什麼 AI 不該做的事嗎？",
         "widget_type": "form",
         "config": {
           "fields": [
             {"name": "dont_do", "label": "AI 不該做的事", "type": "text",
              "placeholder": "例如：不要推薦線上賭博平台"}
           ]
         }
       }
     ],
     "base_system_prompt_template": "你是 {{project_name}} 的 AI 撲克教練..."
   }

2. 建立一個通用模板（不綁定領域）：
   - 問：你想讓 AI 做什麼？
   - 問：目標受眾是誰？
   - 問：回答風格偏好？
   - 問：有什麼限制？

3. 模板存放方式：先用 JSON 檔案，之後可搬到 DB

驗收標準：
 ✓ 載入模板時能取得完整問題列表
 ✓ 撲克模板至少 8 個問題
 ✓ 通用模板至少 5 個問題
```

---

#### Task 2.2：Onboarding 對話流程引擎
**新建：** `ai-engine/app/core/orchestrator/onboarding.py`

```
要做的事：
1. OnboardingManager 類別：
   - start(project_id) → 載入模板 → 回傳第一個問題（含 Widget 定義）
   - handle_answer(session_id, question_id, answer) → 儲存答案 → 回傳下一題
   - get_progress(session_id) → { current: 3, total: 8 }
   - complete(session_id) → 彙整所有答案 → 用 LLM 產出初始 System Prompt
   
2. 答案儲存：
   - 存在 training_messages 裡（metadata 帶 question_id + answer）
   - 同時在 session metadata 裡追蹤進度

3. Prompt 產出邏輯：
   - 把所有 Q&A 彙整成文字
   - 餵給 LLM：「根據以下資訊，產出一份 System Prompt...」
   - 存入 prompt_versions（version=1, is_active=true）

驗收標準：
 ✓ 新 onboarding session 會從第一題開始
 ✓ 每個答案都正確儲存
 ✓ 完成後自動產出合理的 System Prompt
 ✓ Prompt 被設為 active 版本
```

---

#### Task 2.3：Agent Orchestrator 整合 Onboarding
**修改：** `ai-engine/app/core/orchestrator/agent.py` + `api/v1/__init__.py`

```
要做的事：
1. 新增 session_type 判斷：
   - 如果 session_type == 'onboarding' → 走 OnboardingManager
   - 否則走一般對話
   
2. 新增 API 端點：
   - POST /api/v1/onboarding/start → 開始 Onboarding
   - POST /api/v1/onboarding/answer → 回答問題
   - GET  /api/v1/onboarding/progress/{session_id} → 查進度

3. ChatResponse 的 widgets 欄位帶上 Onboarding 的問題元件

驗收標準：
 ✓ 前端選「引導式建立基線」→ 後端回傳第一個問題 + Widget
 ✓ 使用者回答 → 後端回傳下一題
 ✓ 最後一題回答完 → 後端回傳「基線建立完成」+ Prompt 摘要
```

---

#### Task 2.4：前端 Onboarding UI
**修改：** `ChatInterface.tsx` + `chat/page.tsx`

```
要做的事：
1. 頂部的「會話模式」下拉選「引導式建立基線」→ 呼叫 start 端點
2. 進度條元件：顯示「第 3/8 題」
3. 完成畫面：
   - 顯示「✅ 基線建立完成！」
   - 顯示產出的 Prompt 摘要（可展開看完整版）
   - 「開始自由訓練」按鈕
4. 自動切換到 freeform 模式

驗收標準：
 ✓ 完整 Onboarding 流程體驗流暢
 ✓ 進度條正確更新
 ✓ 完成後無縫切換到自由訓練
```

---

### Week 3：回饋系統 + Prompt 自動優化建議

---

#### Task 3.1：回饋 API 完善
**修改：** `ai-engine/app/api/v1/__init__.py`

```
要做的事：
1. POST /api/v1/feedback → 真正寫入 feedbacks 表
2. 驗證 message_id 存在且屬於請求者的 tenant
3. GET /api/v1/feedback/stats/{project_id} → 回饋統計
   - 總回饋數、各評級數量、近 7 天趨勢

驗收標準：
 ✓ 回饋正確寫入 DB
 ✓ 統計端點回傳正確數字
```

---

#### Task 3.2：前端 FeedbackBar 完善
**修改：** `FeedbackBar.tsx` + `ChatInterface.tsx`

```
要做的事：
1. ChatInterface 傳真實 message_id 給 FeedbackBar
   - 需要後端回傳 message_id（修改 ChatResponse 加上 message_id）
2. 提交成功的視覺回饋（勾勾動畫 or 背景變色）
3. 一則訊息只能打分一次（用 state 追蹤已打分的 message_id）
4. 修正輸入框：按 Enter 送出、Shift+Enter 換行

驗收標準：
 ✓ 打分送出後有明確視覺確認
 ✓ 不能重複打分
 ✓ 修正文字操作流暢
```

---

#### Task 3.3：Prompt 自動優化建議引擎
**新建：** `ai-engine/app/core/prompt/optimizer.py`

```
要做的事：
1. PromptOptimizer 類別：

   analyze_and_suggest(project_id):
     a. 從 feedbacks 表撈最近的回饋（rating != 'correct'）
     b. 關聯回原始 message 取得上下文
     c. 載入當前 active prompt
     d. 用 LLM 分析：
        System: 你是一個 Prompt 優化專家。分析以下回饋和當前 Prompt，
                產出具體的修改建議。回傳 JSON 格式。
        User: 當前 Prompt: {prompt}
              使用者不滿意的回答：{feedbacks_with_context}
     e. 解析 LLM 回覆為結構化建議

   apply_suggestion(project_id, suggestion_id):
     a. 讀取當前 prompt + 建議內容
     b. 用 LLM 合併產出新 prompt
     c. 建立新的 prompt_version（version +1）
     d. 不自動設為 active（需要通過測試才 activate）
        → Phase 1 先簡化：直接設為 active

2. 建議資料結構：
   {
     "id": "uuid",
     "project_id": "...",
     "based_on_feedback_count": 5,
     "changes": [
       {
         "type": "modify",      // 'modify' | 'add' | 'remove'
         "section": "語氣風格",
         "reason": "3 位使用者反映回答太生硬",
         "before": "...",       // modify 時有
         "after": "...",        // modify/add 時有
       }
     ],
     "status": "pending",       // 'pending' | 'applied' | 'rejected'
     "created_at": "..."
   }

3. 新增 API：
   - GET  /api/v1/prompt/suggestions/{project_id} → 取得待審建議列表
   - POST /api/v1/prompt/suggestions/{project_id}/generate → 手動觸發產出建議
   - POST /api/v1/prompt/suggestions/{suggestion_id}/apply → 套用建議
   - POST /api/v1/prompt/suggestions/{suggestion_id}/reject → 拒絕建議

4. 新增 DB 表（或用 JSONB 欄位存在 prompt_versions 的 metadata 裡）：
   - 建議先存在記憶體 / 簡單的 JSONB 欄位
   - Phase 4 再做正式的 suggestions 表

驗收標準：
 ✓ 累積 5+ 筆「部分正確」或「錯誤」回饋後，能產出合理建議
 ✓ 建議內容是中文，非技術人員看得懂
 ✓ 套用後新版 Prompt 確實有改善
```

---

#### Task 3.4：前端 Prompt 建議審核面板
**新建：** `frontend/src/components/chat/PromptSuggestion.tsx`

```
要做的事：
1. 在對話頁面加一個「💡 Prompt 優化建議」觸發按鈕
   - 有新建議時顯示紅點通知
2. 點開後顯示建議面板：
   - 列出每條變更（改了什麼 / 為什麼 / 改前改後）
   - 用綠色底色標示新增、紅色底色標示刪除、黃色標示修改
3. 底部兩個按鈕：「✓ 套用此建議」「✗ 忽略」
4. 套用後顯示：「已更新到 v{N}，對話已使用新版 Prompt」

驗收標準：
 ✓ 建議面板 UI 清楚易讀
 ✓ 變更差異（diff）用顏色區分
 ✓ 套用 / 忽略操作流暢
 ✓ 套用後下一則對話立即使用新 Prompt
```

---

### Week 4：整合測試 + 修正

---

#### Task 4.1：端到端完整流程測試

```
測試劇本（手動走一遍）：

1. 開啟 http://localhost:3000
2. 選「引導式建立基線」
3. 回答 8 個 Onboarding 問題（用撲克模板）
4. 確認基線 Prompt 產出（到 Supabase 查 prompt_versions）
5. 切換到「自由訓練」
6. 跟 AI 對話 10 輪，涵蓋：
   - 翻牌前策略問題
   - 位置觀念問題
   - 籌碼管理問題
   - 故意問一個超出範圍的問題
7. 對 5 則 AI 回覆打分：
   - 2 則標「正確」
   - 2 則標「部分正確」+ 寫修正
   - 1 則標「錯誤」+ 寫修正
8. 點「💡 Prompt 優化建議」→ 觸發產出
9. 檢查建議內容是否合理
10. 套用建議
11. 再對話 5 輪，確認改善

每一步檢查：
 ✓ 前端 UI 正常
 ✓ 後端 API 回覆正確
 ✓ DB 資料正確
 ✓ 對話歷史載入正確
```

---

#### Task 4.2：錯誤處理加固

```
測試清單：
 □ LLM API Key 故意填錯 → 前端顯示友善錯誤
 □ 送 10000+ 字元的超長訊息 → 正常處理或提示過長
 □ 快速連按送出 5 次 → 不會重複建立 session
 □ 後端沒啟動時前端操作 → 顯示「無法連線」
 □ Supabase 斷線 → 有重試機制或友善提示
 □ 空白訊息 → 前端攔截，不送出
 □ Session ID 亂填 → 後端回 404
 □ 切換模型後對話 → 回覆正常
```

---

#### Task 4.3：程式碼品質

```
要做的事：
 □ Python 端：跑 mypy 型別檢查，確保無 error
 □ Python 端：跑 ruff 格式化
 □ TypeScript 端：跑 tsc --noEmit 確保無型別錯誤
 □ 前端：跑 next lint
 □ 刪除所有 console.log / print debug 輸出
 □ 確保所有 TODO 都標記了對應的 Phase
 □ 更新 README.md 的啟動指令
```

---

## Phase 1 完成後 → Phase 2 準備

Phase 1 做完後，你手上會有：
- 一個能對話的 AI Agent 原型
- 完整的 Onboarding 流程
- 回饋 → Prompt 優化的閉環

**Phase 2（RAG 知識庫）的入口點：**
- `agent.py` 裡的 `_search_knowledge()` 目前回傳 None
- 只要接上 Qdrant + Embedding，RAG 就能跑
- 知識庫的文件上傳 UI 已有 placeholder 頁面

---

## 給 Claude Code 的開發指令範本

```
你現在要開發 AI Trainer Platform 的 Phase 1。

專案結構在 /path/to/ai-trainer-platform
規格書在 docs/spec-v2.md
Phase 1 計畫在 docs/phase1-plan.md

當前要做的 Task 是：Task X.X（標題）

請按照 phase1-plan.md 裡描述的要求實作，
完成後列出驗收標準的逐項確認結果。

技術要求：
- Python 用 type hints
- TypeScript 用 strict mode
- 錯誤處理要完整
- 中文註解
- 不要產出沒在計畫裡的功能
```

---

*Phase 1 詳細實作計畫 v1.0 | 產出日期：2026-04-01*

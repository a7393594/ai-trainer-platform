# Phase 1 實作計畫 — 訓練對話 MVP

> **目標：** 完成核心訓練對話循環，使用者可以跟 AI 對話、AI 能回覆（含互動元件）、使用者能打分回饋
> **前置完成：** Phase 0 骨架已建好，Supabase / Qdrant / LLM 連線就緒
> **預估時間：** 3-4 週（Solo + Claude Code）

---

## 開工前 Checklist

在進入 Phase 1 之前，確認 Phase 0 地基已通：

```
□ Supabase 專案已建立，migration.sql 已執行
□ Qdrant Cloud 已開通（或本地 Docker 跑起來）
□ 至少一個 LLM API Key 已設定（Claude 或 GPT）
□ `uvicorn app.main:app --reload` 可啟動，/health 回 200
□ `npm run dev` 前端可啟動，看到 Dashboard 側邊欄
□ 前端能成功呼叫後端 /health 端點（CORS 沒擋）
```

---

## 任務拆分（按實作順序）

### Week 1：後端 — 對話核心 + 資料存取

---

#### Task 1.1：Supabase CRUD 服務層
**檔案：** `ai-engine/app/db/crud.py`（新增）
**做什麼：** 封裝所有 Supabase 表的基本讀寫操作

```python
# 需要實作的函數：

# 專案
async def get_project(project_id: str) -> dict
async def list_projects(tenant_id: str) -> list[dict]

# 訓練會話
async def create_session(project_id: str, user_id: str, session_type: str) -> dict
async def get_session(session_id: str) -> dict

# 訓練訊息
async def create_message(session_id: str, role: str, content: str, metadata: dict) -> dict
async def list_messages(session_id: str, limit: int = 50) -> list[dict]

# 回饋
async def create_feedback(message_id: str, rating: str, correction: str = None) -> dict

# Prompt 版本
async def get_active_prompt(project_id: str) -> str | None
async def create_prompt_version(project_id: str, content: str, created_by: str) -> dict
```

**驗收標準：**
- 每個函數都能正確讀寫 Supabase
- 寫一個簡單的 pytest 測試確認連線正常

---

#### Task 1.2：接通 Agent Orchestrator 的資料存取
**檔案：** `ai-engine/app/core/orchestrator/agent.py`（修改）
**做什麼：** 把 Phase 0 的 placeholder 方法接上真實的 Supabase CRUD

```python
# 把這些 TODO 方法接上 crud.py：
_create_session()    → crud.create_session()
_load_history()      → crud.list_messages()
_save_message()      → crud.create_message()
_load_active_prompt() → crud.get_active_prompt()
```

**驗收標準：**
- POST /api/v1/chat 能存訊息到 Supabase
- 對話歷史能正確載入（第二則訊息能看到第一則的上下文）

---

#### Task 1.3：Feedback 端點實作
**檔案：** `ai-engine/app/api/v1/__init__.py`（修改）
**做什麼：** 把 /feedback 端點接上 Supabase

```python
@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    # 1. 存入 feedbacks 表
    # 2. 如果 rating == 'wrong' 且有 correction_text：
    #    → 產生一條「Prompt 修改建議」（Phase 1 先存到 DB，Phase 4 才自動優化）
    # 3. 回傳確認
```

**驗收標準：**
- 打分 + 修正文字能存到 feedbacks 表
- 能查詢某個 session 的所有回饋

---

#### Task 1.4：Onboarding Interview — AI 主動提問流程
**檔案：** `ai-engine/app/core/orchestrator/onboarding.py`（新增）
**做什麼：** 實作「AI 第一次主動問 10-15 個問題建立基線」的邏輯

```python
class OnboardingEngine:
    """
    引導式建立基線

    流程：
    1. 載入領域模板的問題集（例如撲克模板有 12 個問題）
    2. 按順序問使用者
    3. 把回答整理成初始 System Prompt
    4. 存為第一個 prompt_version
    """

    # 撲克領域模板範例問題：
    POKER_TEMPLATE = [
        {
            "question": "你的俱樂部主要打什麼類型的牌局？",
            "widget": {
                "widget_type": "multi_select",
                "options": [
                    {"id": "nlh", "label": "無限注德州撲克 (NLH)"},
                    {"id": "plo", "label": "底池限注奧馬哈 (PLO)"},
                    {"id": "mixed", "label": "混合賽"},
                    {"id": "tourney", "label": "錦標賽"},
                    {"id": "sng", "label": "SNG（坐滿即打）"},
                ]
            }
        },
        {
            "question": "成員的整體程度？",
            "widget": {
                "widget_type": "single_select",
                "options": [
                    {"id": "beginner", "label": "大多數是新手"},
                    {"id": "intermediate", "label": "中級為主"},
                    {"id": "advanced", "label": "進階玩家居多"},
                    {"id": "mixed", "label": "混合程度"},
                ]
            }
        },
        {
            "question": "你的俱樂部常見的盲注級別是？",
            "widget": {
                "widget_type": "multi_select",
                "options": [
                    {"id": "micro", "label": "微額 (1/2, 2/5)"},
                    {"id": "low", "label": "低額 (5/10, 10/20)"},
                    {"id": "mid", "label": "中額 (25/50, 50/100)"},
                    {"id": "high", "label": "高額 (100/200+)"},
                ]
            }
        },
        {
            "question": "最常見的爭議或問題是什麼？",
            "type": "free_text"  # 這題不用元件，讓使用者自由打
        },
        {
            "question": "你希望 AI 助手的語氣和風格是？",
            "widget": {
                "widget_type": "single_select",
                "options": [
                    {"id": "professional", "label": "專業正式"},
                    {"id": "friendly", "label": "友善親切"},
                    {"id": "coach", "label": "教練風格（直接點出問題）"},
                    {"id": "casual", "label": "輕鬆隨意"},
                ]
            }
        },
        # ... 繼續到 10-15 題
    ]

    async def get_next_question(self, session_id: str) -> dict:
        """根據已回答的題數，回傳下一題"""
        ...

    async def process_answer(self, session_id: str, answer: dict) -> dict:
        """處理使用者的回答，決定繼續問下一題還是完成"""
        ...

    async def generate_baseline_prompt(self, session_id: str) -> str:
        """把所有回答彙整成初始 System Prompt"""
        ...
```

**驗收標準：**
- 新會話選「引導式建立基線」模式，AI 會依序問問題
- 每個問題搭配正確的互動元件
- 所有問題回答完後，自動產生第一版 System Prompt 並存入 prompt_versions

---

### Week 2：前端 — 對話 UI + 元件互動

---

#### Task 2.1：ChatInterface 接通真實 API
**檔案：** `frontend/src/components/chat/ChatInterface.tsx`（修改）
**做什麼：** 確保前端 → 後端的完整對話流程跑通

```
測試流程：
1. 使用者打字送出 → POST /api/v1/chat
2. AI 回覆文字 → 顯示在對話框
3. AI 回覆帶元件 → WidgetRenderer 渲染
4. 使用者操作元件 → POST /api/v1/chat/widget-response
5. AI 根據元件結果繼續回覆
```

**驗收標準：**
- 文字對話來回正常
- 互動元件能渲染 + 回傳結果
- 對話歷史保持上下文（AI 記得前面說了什麼）

---

#### Task 2.2：Session 管理 UI
**檔案：** `frontend/src/components/chat/SessionSidebar.tsx`（新增）
**做什麼：** 對話左側的會話清單

```
功能：
- 列出所有訓練會話（從 training_sessions 查詢）
- 點選切換會話
- 「新建會話」按鈕，可選模式（自由訓練 / 引導式基線 / 定義能力）
- 顯示會話類型標籤（onboarding / freeform / capability）
```

**驗收標準：**
- 能建立新會話
- 能切換舊會話，載入歷史訊息
- 會話類型正確標記

---

#### Task 2.3：FeedbackBar 完善 + 回饋統計
**檔案：** `frontend/src/components/chat/FeedbackBar.tsx`（修改）
**做什麼：** 

```
加強：
- 打分後視覺回饋（顏色變化、icon）
- 修正框支援 Markdown
- 頂部顯示本次會話的回饋統計：✓12 / △3 / ✗1
```

---

#### Task 2.4：Onboarding 模式的前端整合
**做什麼：** 當使用者選「引導式建立基線」時，前端進入特殊模式

```
差異：
- 頂部顯示進度條（已回答 3/12 題）
- 每題 AI 提問自動帶互動元件
- 最後一題完成後，顯示「基線已建立！」的摘要卡片
- 摘要卡片顯示 AI 根據回答生成的 System Prompt 預覽
- 使用者可以「確認上線」或「手動修改」
```

---

### Week 3：Prompt 自動優化建議 + 打磨

---

#### Task 3.1：Prompt 修改建議產生器
**檔案：** `ai-engine/app/core/prompt/optimizer.py`（新增）
**做什麼：** 根據使用者回饋，自動產出 Prompt 修改建議

```python
class PromptOptimizer:
    """
    根據「部分正確」和「錯誤」的回饋，
    讓 LLM 分析哪裡出了問題，建議怎麼修改 System Prompt

    注意：Phase 1 只「建議」，不自動套用。需要人工確認。
    """

    async def analyze_feedback_batch(self, project_id: str) -> list[dict]:
        """
        收集最近 N 則負面回饋，分析模式：
        1. 取得所有 rating != 'correct' 的回饋
        2. 取得對應的 AI 輸出和使用者修正
        3. 送給 LLM 分析：「根據這些錯誤，System Prompt 該怎麼改？」
        4. 回傳建議列表
        """
        ...

    async def generate_improved_prompt(
        self, current_prompt: str, suggestions: list[dict]
    ) -> str:
        """根據建議產生改良版 Prompt"""
        ...
```

**驗收標準：**
- 累積 5+ 則負面回饋後，系統能產出具體的 Prompt 修改建議
- 建議顯示在 Dashboard 上（簡單的通知卡片）
- 使用者可以一鍵套用建議（存為新的 prompt_version）

---

#### Task 3.2：Prompt 版本對比 UI（簡易版）
**檔案：** `frontend/src/app/(dashboard)/prompts/page.tsx`（修改）
**做什麼：** 把 placeholder 替換成真實的 Prompt 管理介面

```
功能（Phase 1 簡易版）：
- 列出所有 prompt_versions
- 查看每個版本的完整內容
- 標記哪個版本是 active
- 一鍵切換 active 版本
- 顯示每個版本的 eval_score（Phase 4 才有值，現在先空著）
```

---

#### Task 3.3：對話品質保底 — 串流回覆
**檔案：** 前後端都需要改
**做什麼：** 把 LLM 回覆從「一次全吐」改成「逐字串流」

```
後端：
- LLM Router 加 stream=True 參數
- 新端點 /api/v1/chat/stream 用 Server-Sent Events (SSE)

前端：
- ChatInterface 支援 SSE 讀取
- 逐字顯示 AI 回覆（打字機效果）
```

**為什麼 Phase 1 就要做：**
沒有串流的話，長回覆使用者要等 5-10 秒看到空白，體驗很差。

---

#### Task 3.4：整合測試 + Bug 修復
**做什麼：** 跑完整個 Phase 1 流程確認沒有斷裂

```
完整測試路徑：
1. 開新專案 → 進入 Onboarding → AI 問完 12 題 → 生成基線 Prompt ✓
2. 切到自由訓練 → 跟 AI 對話 → AI 正確使用剛建立的基線 ✓
3. 對某則回覆打「錯誤」+ 寫修正 → 回饋存入 DB ✓
4. 累積 5 則負面回饋 → 系統產出 Prompt 修改建議 ✓
5. 套用建議 → 新版 Prompt 生效 → 之後的回覆有改善 ✓
6. 切回舊會話 → 歷史訊息完整載入 ✓
7. 串流回覆 → 打字機效果正常 ✓
```

---

## Phase 1 完成後的系統狀態

```
✅ 能建立專案
✅ 能跑 Onboarding 建立基線（含互動元件）
✅ 能自由對話訓練（串流回覆）
✅ 能打分回饋（正確/部分正確/錯誤+修正）
✅ 能根據回饋產出 Prompt 修改建議
✅ 能管理 Prompt 版本
✅ 對話歷史完整保存（為未來 Fine-tune 累積資料）

⬜ RAG 知識庫（Phase 2）
⬜ Agent 能力——互動元件 + 工具呼叫 由訓練者定義（Phase 3）
⬜ 評估引擎——自動跑分（Phase 4）
⬜ 工作流引擎（Phase 5）
⬜ Fine-tune 管線（Phase 6）
```

---

## Claude Code 開發提示

每個 Task 可以直接丟給 Claude Code 當一個獨立指令：

```bash
# 範例：開發 Task 1.1
claude "請在 ai-engine/app/db/ 建立 crud.py，
封裝 Supabase 的 CRUD 操作，包含：
projects / training_sessions / training_messages / feedbacks / prompt_versions
每個表都要有 create / get / list 函數。
使用 app/db/supabase.py 的 get_supabase() 取得連線。
參考 app/models/schemas.py 的型別定義。"
```

```bash
# 範例：開發 Task 1.4
claude "請建立 ai-engine/app/core/orchestrator/onboarding.py，
實作 OnboardingEngine 類別。
功能是：AI 按順序問使用者 10-15 個問題，每題可帶互動元件，
問完後自動彙整成 System Prompt 存入 prompt_versions。
先做撲克領域的模板。
參考 docs/spec-v2.md 第三節 Module 1 和 Module 10 的規格。"
```

---

## 下一步：Phase 2 預告

Phase 1 完成後進入 Phase 2（RAG 知識庫），核心是：
- 文件上傳 → 自動切塊 → Embedding → 存入 Qdrant
- 對話時自動搜尋相關知識注入 LLM 上下文
- 從對話自動抽取知識候選

這會讓 AI 從「只看 Prompt 規則回答」升級到「查資料再回答」。

---

*Phase 1 計畫版本：v1.0 | 產出日期：2026-04-01*

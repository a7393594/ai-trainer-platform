# AI Trainer Platform — 完整系統規格書 v2.0

> **專案代號：** AI Trainer（暫定）
> **定位：** 讓企業內部員工（非技術人員）透過對話，訓練出能互動、能操作、能精準回答的 AI Agent
> **第一個 Demo：** 撲克領域（接入 PokerVerse 生態）
> **開發模式：** Solo Founder + Claude Code 全棧開發
> **部署模式：** SaaS 多租戶，未來開放自架
> **目標平台：** Web (PWA) + iOS + Android（透過 Capacitor）

---

## 一、核心概念

### 這個系統在做什麼？（一句話）

一個「對話式 AI Agent 訓練工作台」——使用者跟系統對話，系統自動把對話內容轉化為 AI 的規則、知識、操作能力和微調資料，經過審核測試後，產出一個能對話、能互動、能操作外部系統的領域專用 AI Agent。

### 與一般 AI 工具的差異

```
一般 AI Chatbot：使用者問 → AI 回答文字 → 結束

本平台訓練出的 AI Agent：
  使用者問 → AI 判斷意圖 →
    ├─ 回文字（一般回答）
    ├─ 丟互動元件（讓使用者選、排序、填表單、確認）
    ├─ 呼叫外部 API（查資料、寫入資料、觸發流程）
    └─ 組合以上（查 API → 用結果生成選項 → 等使用者選 → 再呼叫另一個 API）
```

### 核心循環（Training Loop）

```
┌──────────────────────────────────────────────────────────────┐
│                      TRAINING LOOP                            │
│                                                               │
│  ① AI 提問引導         使用者進入時，AI 主動問一輪問題         │
│       ↓                建立領域基線（Baseline）                │
│                                                               │
│  ② 使用者回饋          使用者可打分、補充、修正 AI 輸出        │
│       ↓                也可定義「什麼時候該跳選項/呼叫 API」    │
│                                                               │
│  ③ 自動產出修正         系統將回饋轉化為四層修正：              │
│       │                  - Prompt 規則更新                     │
│       │                  - RAG 知識庫新增/修正                  │
│       │                  - 能力規則新增（互動元件 + 工具呼叫）   │
│       │                  - Fine-tune 訓練資料累積               │
│       ↓                                                       │
│  ④ 審核閘門            早期：人工審核每次修正                   │
│       │                中期：AI 自動評分＋人類抽檢               │
│       │                後期：全自動（累積足夠黃金標準後）         │
│       ↓                                                       │
│  ⑤ 測試驗證            用測試案例集驗證修正後是否變好            │
│       │                 通過 → 套用修正                        │
│       │                 未通過 → 回滾 + 標記失敗原因             │
│       ↓                                                       │
│  ⑥ 回到 ①             持續迭代，精度越來越高                   │
└──────────────────────────────────────────────────────────────┘
```

---

## 二、系統架構

### 完整分層圖

```
┌───────────────────────────────────────────────────────┐
│              CLIENT LAYER（用戶端）                     │
│  Web App (PWA) ──── iOS / Android (Capacitor)         │
│  React + Next.js                                      │
│  ┌──────────────────────────────────────────────┐     │
│  │  Widget Renderer（元件渲染器）                  │     │
│  │  負責渲染 AI 回傳的互動元件：                    │     │
│  │  單選 / 多選 / 排序 / 表單 / 確認 / 滑桿 / 日期  │     │
│  └──────────────────────────────────────────────┘     │
└────────────────────────┬──────────────────────────────┘
                         │ HTTPS / WebSocket
┌────────────────────────▼──────────────────────────────┐
│              API GATEWAY（API 閘道）                    │
│  Next.js API Routes                                   │
│  認證 / 限流 / 路由 / WebSocket 管理                    │
└────────────┬──────────────────────┬───────────────────┘
             │                      │
┌────────────▼──────────┐  ┌────────▼──────────────────────────┐
│   BIZ LAYER            │  │   AI ENGINE（AI 引擎）              │
│   業務邏輯層            │  │   Python FastAPI 微服務             │
│   Supabase             │  │                                    │
│   - Auth 認證           │  │  ┌──────────────────────────────┐ │
│   - PostgreSQL         │  │  │  Agent Orchestrator           │ │
│   - Realtime           │  │  │  （代理調度器）                 │ │
│   - Storage            │  │  │  接收輸入 → 意圖分類 →          │ │
│                        │  │  │  分派到對應能力                 │ │
│                        │  │  └──┬────────┬────────┬──────────┘ │
│                        │  │     │        │        │            │
│                        │  │  ┌──▼─────┐┌─▼──────┐┌▼─────────┐ │
│                        │  │  │Widget  ││Tool    ││Workflow  │ │
│                        │  │  │Engine  ││Registry││Engine    │ │
│                        │  │  │互動元件 ││工具註冊 ││工作流引擎 │ │
│                        │  │  │引擎    ││中心    ││          │ │
│                        │  │  └────────┘└────────┘└──────────┘ │
│                        │  │                                    │
│                        │  │  ┌──────────────────────────────┐ │
│                        │  │  │  LLM Router（多模型切換器）    │ │
│                        │  │  │  LiteLLM 統一介面             │ │
│                        │  │  │  Claude / GPT / Llama /       │ │
│                        │  │  │  Gemini / Mistral ...         │ │
│                        │  │  └──────────────────────────────┘ │
│                        │  │  ┌──────────────────────────────┐ │
│                        │  │  │  RAG Pipeline（知識檢索管線）  │ │
│                        │  │  │  Embedding → 向量搜尋          │ │
│                        │  │  │  → 上下文注入                  │ │
│                        │  │  └──────────────────────────────┘ │
│                        │  │  ┌──────────────────────────────┐ │
│                        │  │  │  Prompt Manager（提示詞管理）  │ │
│                        │  │  │  版本控制 / A-B 測試           │ │
│                        │  │  └──────────────────────────────┘ │
│                        │  │  ┌──────────────────────────────┐ │
│                        │  │  │  Eval Engine（評估引擎）       │ │
│                        │  │  │  測試案例 → 自動跑分           │ │
│                        │  │  │  → 回歸測試 → 分數趨勢         │ │
│                        │  │  └──────────────────────────────┘ │
│                        │  │  ┌──────────────────────────────┐ │
│                        │  │  │  Fine-tune Pipeline           │ │
│                        │  │  │  （微調訓練管線）              │ │
│                        │  │  │  資料清洗 → 格式轉換           │ │
│                        │  │  │  → 送出訓練 → 部署新模型       │ │
│                        │  │  └──────────────────────────────┘ │
│                        │  │  ┌──────────────────────────────┐ │
│                        │  │  │  Capability Trainer           │ │
│                        │  │  │  （能力訓練器）                │ │
│                        │  │  │  對話式定義互動 + 操作規則     │ │
│                        │  │  └──────────────────────────────┘ │
└────────────────────────┘  └──────────────────────────────────┘
                                          │
                    ┌─────────────────────┼─────────────────┐
                    ▼                     ▼                 ▼
              ┌──────────┐         ┌──────────┐      ┌────────────┐
              │ Supabase │         │ Qdrant   │      │ Supabase   │
              │ Postgres │         │ (向量DB)  │      │ Storage    │
              │ 業務資料  │         │ 語意搜尋  │      │ 文件/檔案   │
              └──────────┘         └──────────┘      └────────────┘
```

### 架構決策理由

| 決策 | 理由 |
|------|------|
| **前端 Next.js + Capacitor** | 一套程式碼 → Web PWA + iOS + Android，Solo 開發最省力 |
| **前端內建 Widget Renderer** | AI 回傳的互動元件需要前端即時渲染，獨立元件系統方便擴充 |
| **AI 引擎用 Python (FastAPI)** | Fine-tune、RAG、Embedding 的工具鏈 90% 是 Python 生態（LlamaIndex、Hugging Face） |
| **Agent Orchestrator 獨立層** | 意圖分類 + 能力分派是 Agent 的核心，獨立出來方便測試和擴展 |
| **業務層用 Supabase** | Auth / DB / Realtime / Storage 一站搞定 |
| **向量 DB 用 Qdrant** | 開源可自架（未來 on-premise 需求）、metadata 過濾（多租戶必須）、比 Pinecone 便宜 |
| **LLM Router 用 LiteLLM** | 不綁死任何一家，一個 API 呼叫 100+ 模型，內建成本追蹤 |

---

## 三、完整模組清單 & 功能規格

### Module 1：Training Conversation（訓練對話模組）

**功能：** 使用者與 AI 的對話介面，AI 負責引導使用者把領域知識和操作規則「倒出來」

| 子功能 | 說明 |
|--------|------|
| **Onboarding Interview** | AI 第一次主動問 10-15 個問題，建立領域基線。問題由「領域模板」驅動 |
| **Free-form Training** | 基線建立後，使用者可自由輸入：貼資料、寫規則、給範例、指出錯誤 |
| **Feedback Widget** | 每次 AI 輸出旁有「正確 / 部分正確 / 錯誤」按鈕 + 自由文字修正框 |
| **Conversation History** | 所有訓練對話完整保存，作為未來 Fine-tune 的原始資料 |

---

### Module 2：Knowledge Manager（知識管理模組）

**功能：** 管理 RAG 知識庫的內容

| 子功能 | 說明 |
|--------|------|
| **Document Upload** | 支援上傳 PDF / DOCX / TXT / CSV / 網頁連結，自動切塊（Chunking）+ 向量化 |
| **Knowledge Browser** | 可視化瀏覽知識庫內容，支援搜尋、刪除、編輯 |
| **Auto-extract** | 從訓練對話中自動抽取知識點，建議加入知識庫（需使用者確認） |
| **Version Control** | 知識庫有版本紀錄，可回滾到任何歷史版本 |

---

### Module 3：Prompt Studio（提示詞工作室）

**功能：** 管理系統提示詞（System Prompt），也就是「AI 的行為規則」

| 子功能 | 說明 |
|--------|------|
| **Visual Editor** | 非技術人員也能用的規則編輯器，用選項 + 填空取代手寫 prompt |
| **Version Diff** | 每次修改都有版本紀錄，可看差異對比 |
| **A/B Testing** | 同時跑兩個版本的 prompt，看哪個評分更高 |
| **Auto-optimize** | 根據使用者回饋，AI 自動建議 prompt 修改（需人工確認） |

---

### Module 4：Eval Engine（評估引擎）

**功能：** 判定 AI 修改後到底變好還是變差

| 子功能 | 說明 |
|--------|------|
| **Test Case Manager** | 管理「標準問答對」（黃金標準），早期由人工建立 |
| **Auto-run** | 每次修改後自動跑全部測試案例，產出分數報告 |
| **Regression Alert** | 新版本在某些案例退步時，自動警告並阻止上線 |
| **Scoring Dashboard** | 儀表板顯示分數趨勢、各類別表現、問題熱區 |
| **Phase Transition** | 測試案例數 > 閾值（如 200 組）且人工一致率 > 90% 時，自動啟用全自動審核 |

---

### Module 5：LLM Router（多模型切換器）

**功能：** 統一介面呼叫任何 LLM，使用者可自由切換和新增

| 子功能 | 說明 |
|--------|------|
| **Provider Config** | 管理各 LLM 供應商的 API Key、設定 |
| **Model Registry** | 登記可用模型清單，包含成本 / 速度 / 能力標籤 |
| **Smart Routing** | 可設規則：簡單問題走便宜模型、複雜問題走強模型 |
| **Cost Tracker** | 追蹤每個租戶的 API 呼叫成本 |

---

### Module 6：Fine-tune Pipeline（微調管線）

**功能：** 把累積的訓練對話資料轉成 Fine-tune 訓練資料，送出訓練

| 子功能 | 說明 |
|--------|------|
| **Data Curator** | 自動從已標記為「正確」的對話中抽取訓練資料對 |
| **Format Converter** | 轉成各 LLM 要求的格式（OpenAI JSONL / Anthropic 格式等） |
| **Training Trigger** | 累積到一定量時提醒使用者，一鍵送出訓練 |
| **Model Swap** | 訓練完成後，新模型自動進入 A/B 測試，確認比舊版好才切換 |

---

### Module 7：Widget Engine（互動元件引擎）

**功能：** AI 輸出時可嵌入互動元件，使用者操作後結果回傳給 AI 繼續處理

#### 支援的元件類型

| 元件 | 用途 | 回傳資料格式 |
|------|------|-------------|
| **single_select** | 單選（選一個） | `{ selected: "option_id" }` |
| **multi_select** | 多選（選多個） | `{ selected: ["id1", "id2"] }` |
| **rank** | 排序 / 拖拉排列優先順序 | `{ ranked: ["id3", "id1", "id2"] }` |
| **confirm** | 確認 / 取消（二元操作） | `{ confirmed: true/false }` |
| **form** | 迷你表單（多欄位填寫） | `{ fields: { name: "...", amount: 100 } }` |
| **card_carousel** | 卡片輪播展示（含圖片、標題、描述） | `{ selected_card: "card_id" }` |
| **date_picker** | 日期 / 時間選擇 | `{ datetime: "2026-04-01T14:00" }` |
| **slider** | 數值滑桿 | `{ value: 75 }` |

#### 元件定義格式（AI 輸出時使用）

```json
{
  "type": "widget",
  "widget_type": "single_select",
  "question": "你想分析哪種牌局？",
  "options": [
    { "id": "cash", "label": "現金桌", "description": "固定籌碼，隨時可走" },
    { "id": "tourney", "label": "錦標賽", "description": "淘汰制，盲注遞增" },
    { "id": "sng", "label": "SNG", "description": "坐滿即打的小型錦標賽" }
  ],
  "allow_skip": false
}
```

#### 訓練方式（非技術人員怎麼教 AI 何時用元件）

```
訓練者：「當玩家問翻牌該怎麼打的時候，先讓他選他的位置，
         選項有：UTG、MP、CO、BTN、SB、BB」

→ 系統自動轉成規則：
{
  "trigger": "翻牌策略相關問題",
  "action": "show_widget",
  "widget": {
    "type": "single_select",
    "question": "你在什麼位置？",
    "options": ["UTG", "MP", "CO", "BTN", "SB", "BB"]
  },
  "then": "用選擇的位置 + 原始問題重新生成回答"
}
```

---

### Module 8：Tool Registry（工具註冊中心）

**功能：** 管理 AI 可以呼叫的外部 API 和內部函數

#### 工具類型

| 類型 | 說明 | 範例 |
|------|------|------|
| **api_call** | 呼叫外部 REST API | 查 PokerVerse 玩家數據、查天氣、查匯率 |
| **db_query** | 查詢租戶自己的 Supabase 資料 | 查會員資料、查訂單紀錄 |
| **webhook** | 觸發外部流程 | 發通知、建立工單、寄 Email |
| **internal_fn** | 平台內建函數 | 計算機率、格式轉換、產生圖表 |
| **mcp_server** | 連接 MCP 協議的服務 | Google Calendar、Gmail、Slack |

#### 工具定義格式

```json
{
  "tool_id": "pokerverse_get_player_stats",
  "name": "查詢玩家數據",
  "description": "從 PokerVerse 取得指定玩家的歷史戰績",
  "type": "api_call",
  "config": {
    "method": "GET",
    "url": "https://api.pokerverse.app/v1/players/{player_id}/stats",
    "headers": {
      "Authorization": "Bearer {{tenant.api_keys.pokerverse}}"
    },
    "params_schema": {
      "player_id": { "type": "string", "required": true },
      "date_range": { "type": "string", "enum": ["7d", "30d", "90d", "all"] }
    }
  },
  "response_mapping": {
    "summary": "{{hands_played}} 手牌，勝率 {{win_rate}}%，VPIP {{vpip}}%"
  },
  "permissions": ["trainer", "admin"],
  "rate_limit": "60/min"
}
```

#### 訓練方式（非技術人員怎麼教 AI 何時用工具）

```
訓練者：「當有人問某個玩家最近打得怎樣，就去 PokerVerse 查他的數據，
         然後用白話告訴他重點數字」

→ 系統引導：
  AI：「好的，我需要確認幾件事：」
  AI：[顯示表單元件]
      - 要查詢的 API 端點 URL？（或從已註冊工具中選）
      - 需要哪些參數？（玩家 ID？時間範圍？）
      - 查到結果後，要特別強調哪些數據？

→ 最終轉成結構化規則並存入 Tool Binding（工具綁定）
```

---

### Module 9：Workflow Engine（工作流引擎）

**功能：** 多步驟流程串接——AI 可以依序執行多個動作

#### 工作流定義範例

```yaml
workflow: "新玩家入會流程"
trigger: "使用者表達想加入俱樂部"
steps:
  - id: ask_info
    action: show_widget
    widget:
      type: form
      fields:
        - { name: "nickname", label: "撲克暱稱", type: "text" }
        - { name: "experience", label: "打牌經驗", type: "single_select",
            options: ["新手", "中級", "進階", "職業"] }
        - { name: "preferred_game", label: "偏好牌型", type: "multi_select",
            options: ["NLH", "PLO", "混合賽"] }

  - id: create_player
    action: api_call
    tool: "pokerverse_create_player"
    params:
      nickname: "{{steps.ask_info.result.nickname}}"
      level: "{{steps.ask_info.result.experience}}"
    on_error: "跟使用者說註冊暫時有問題，稍後再試"

  - id: welcome
    action: respond
    message: "歡迎 {{steps.ask_info.result.nickname}}！已幫你建立帳號。"
    follow_up:
      action: show_widget
      widget:
        type: single_select
        question: "想先做什麼？"
        options: ["看今日賽事", "找牌桌", "學習基礎策略"]
```

#### 視覺化工作流編輯器（給非技術人員用）

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐
│  觸發條件 │───→│ 問使用者  │───→│ 呼叫 API │───→│  回覆   │
│ 「想入會」│    │ [表單]    │    │ 建帳號   │    │ 歡迎詞  │
└─────────┘    └──────────┘    └──────────┘    └─────────┘
                                    │
                                    ▼ 失敗時
                               ┌──────────┐
                               │ 錯誤處理  │
                               │ 通知使用者 │
                               └──────────┘
```

---

### Module 10：Capability Trainer（能力訓練器）

**功能：** 整個系統的靈魂——讓訓練者用「說的」來定義 AI 的互動能力和操作能力

#### 訓練流程

```
┌──────────────────────────────────────────────────────┐
│              CAPABILITY TRAINING FLOW                 │
│                                                       │
│  ① 訓練者描述情境                                      │
│     「當客戶問退款的時候...」                            │
│          ↓                                            │
│  ② AI 追問細節                                        │
│     「要先確認訂單編號嗎？」                             │
│     「確認後要自動發起退款還是通知主管？」                  │
│          ↓                                            │
│  ③ AI 產出結構化規則草稿                                │
│     觸發條件 + 要用的元件 + 要呼叫的工具 + 回覆模板       │
│          ↓                                            │
│  ④ 訓練者預覽 & 模擬測試                                │
│     AI 模擬一個使用者，走一遍整個流程                     │
│          ↓                                            │
│  ⑤ 確認上線 or 修改                                    │
│     通過 → 加入 Active Rules                           │
│     不通過 → 回到 ①                                    │
└──────────────────────────────────────────────────────┘
```

---

### Module 11：Agent Orchestrator（代理調度器）

**功能：** AI Agent 運行時的「大腦」，負責判斷每次使用者輸入該觸發什麼

#### 執行流程（Runtime）

```
使用者輸入
    ↓
┌──────────────────────────────────┐
│  Intent Classifier（意圖分類器）   │
│  判斷這句話要觸發什麼              │
│  1. 比對 capability_rules        │
│  2. 檢查進行中的 workflow         │
│  3. 都不匹配 → 一般對話           │
└──────┬──────────┬────────┬───────┘
       │          │        │
  匹配規則    進行中流程   一般對話
       ↓          ↓        ↓
  執行 Action   繼續下一步  LLM 回覆
  (元件/API/    (帶入上下文) (Prompt +
   工作流)                   RAG)
       ↓          ↓        ↓
  ┌────────────────────────────────┐
  │   Response Composer（回覆組合器）│
  │   組合最終回覆：                 │
  │   文字 + 元件 + API 結果        │
  └────────────────────────────────┘
       ↓
  回傳給前端渲染
```

---

### Module 12：Multi-tenant & Auth（多租戶 & 認證）

**功能：** SaaS 多租戶隔離

| 子功能 | 說明 |
|--------|------|
| **Tenant Isolation** | 每個企業的資料完全隔離（DB row-level + 向量 DB namespace） |
| **Role System** | Admin（管理員）/ Trainer（訓練者）/ Viewer（只看結果） |
| **Auth** | Supabase Auth，支援 Email + Google + SSO |

---

## 四、技術選型總表

| 層級 | 技術 | 選擇理由 |
|------|------|----------|
| **前端框架** | Next.js 14+ (App Router) | SSR + API Routes 一體化 |
| **UI 庫** | shadcn/ui + Tailwind | 開發速度快、可客製 |
| **手機 App** | Capacitor | Web → Native，一套程式碼三平台 |
| **業務後端** | Supabase (PostgreSQL) | Auth / DB / Realtime / Storage 全家桶 |
| **AI 引擎** | Python FastAPI | 獨立微服務，AI 生態工具鏈完整 |
| **LLM 統一介面** | LiteLLM | 一個 API 呼叫 100+ 模型，含成本追蹤 |
| **RAG 框架** | LlamaIndex | 比 LangChain 更專注在 RAG，文件切塊策略成熟 |
| **向量資料庫** | Qdrant | 開源可自架、metadata 過濾強、支援多租戶 namespace |
| **Embedding 模型** | OpenAI text-embedding-3-small（初期）→ 開源模型（後期） | 初期求穩，後期降成本 |
| **Fine-tune** | 各 LLM 供應商原生 API | OpenAI / Anthropic / Together AI 等 |
| **部署** | Vercel (前端) + Railway 或 Fly.io (Python) + Qdrant Cloud | Solo 開發最省運維 |
| **監控** | Sentry + LangFuse | LangFuse 專門追蹤 LLM 呼叫品質 |

---

## 五、資料庫 Schema（完整版）

```sql
-- ============================================
-- 基礎層：租戶 & 使用者
-- ============================================

-- 租戶（每個企業就是一個租戶）
CREATE TABLE tenants (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  plan          TEXT DEFAULT 'free',        -- 'free' | 'pro' | 'enterprise'
  settings      JSONB DEFAULT '{}',
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- 使用者
CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID REFERENCES tenants(id) NOT NULL,
  email         TEXT NOT NULL,
  role          TEXT DEFAULT 'viewer',      -- 'admin' | 'trainer' | 'viewer'
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- 專案層：AI 專案
-- ============================================

-- AI 專案（一個租戶可以訓練多個不同用途的 AI）
CREATE TABLE projects (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID REFERENCES tenants(id) NOT NULL,
  name            TEXT NOT NULL,
  domain_template TEXT,                     -- 領域模板 ID（撲克、客服、醫療...）
  status          TEXT DEFAULT 'draft',     -- 'draft' | 'training' | 'active' | 'archived'
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- 訓練對話層
-- ============================================

-- 訓練會話
CREATE TABLE training_sessions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID REFERENCES projects(id) NOT NULL,
  user_id       UUID REFERENCES users(id) NOT NULL,
  session_type  TEXT DEFAULT 'freeform',    -- 'onboarding' | 'freeform' | 'capability'
  started_at    TIMESTAMPTZ DEFAULT now(),
  ended_at      TIMESTAMPTZ
);

-- 訓練訊息
CREATE TABLE training_messages (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id    UUID REFERENCES training_sessions(id) NOT NULL,
  role          TEXT NOT NULL,              -- 'user' | 'assistant' | 'system'
  content       TEXT NOT NULL,
  metadata      JSONB DEFAULT '{}',         -- 含元件回傳結果、工具呼叫紀錄等
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- 使用者回饋
CREATE TABLE feedbacks (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id      UUID REFERENCES training_messages(id) NOT NULL,
  rating          TEXT NOT NULL,            -- 'correct' | 'partial' | 'wrong'
  correction_text TEXT,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- Prompt 層
-- ============================================

-- Prompt 版本
CREATE TABLE prompt_versions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID REFERENCES projects(id) NOT NULL,
  content       TEXT NOT NULL,
  version       INT NOT NULL,
  is_active     BOOLEAN DEFAULT false,
  eval_score    FLOAT,
  created_by    UUID REFERENCES users(id),
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- 知識庫層
-- ============================================

-- 知識庫文件
CREATE TABLE knowledge_docs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID REFERENCES projects(id) NOT NULL,
  title         TEXT NOT NULL,
  source_type   TEXT NOT NULL,              -- 'upload' | 'url' | 'auto_extract'
  raw_content   TEXT,
  chunk_count   INT DEFAULT 0,
  status        TEXT DEFAULT 'processing',  -- 'processing' | 'ready' | 'error'
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- 知識庫切塊（對應向量 DB 的 ID）
CREATE TABLE knowledge_chunks (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id          UUID REFERENCES knowledge_docs(id) NOT NULL,
  content         TEXT NOT NULL,
  qdrant_point_id TEXT NOT NULL,            -- Qdrant 向量 DB 中的 Point ID
  metadata        JSONB DEFAULT '{}',
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- 評估層
-- ============================================

-- 測試案例（黃金標準）
CREATE TABLE eval_test_cases (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID REFERENCES projects(id) NOT NULL,
  input_text      TEXT NOT NULL,
  expected_output TEXT NOT NULL,
  category        TEXT,                     -- 用來分群看表現
  created_by      UUID REFERENCES users(id),
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- 評估執行
CREATE TABLE eval_runs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        UUID REFERENCES projects(id) NOT NULL,
  prompt_version_id UUID REFERENCES prompt_versions(id),
  total_score       FLOAT,
  passed_count      INT DEFAULT 0,
  failed_count      INT DEFAULT 0,
  run_at            TIMESTAMPTZ DEFAULT now()
);

-- 評估結果明細
CREATE TABLE eval_results (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id          UUID REFERENCES eval_runs(id) NOT NULL,
  test_case_id    UUID REFERENCES eval_test_cases(id) NOT NULL,
  actual_output   TEXT NOT NULL,
  score           FLOAT,
  passed          BOOLEAN,
  details         JSONB DEFAULT '{}'
);

-- ============================================
-- Fine-tune 層
-- ============================================

-- Fine-tune 任務
CREATE TABLE finetune_jobs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          UUID REFERENCES projects(id) NOT NULL,
  provider            TEXT NOT NULL,         -- 'openai' | 'anthropic' | 'together'
  model_base          TEXT NOT NULL,         -- 基底模型名稱
  training_data_count INT DEFAULT 0,
  status              TEXT DEFAULT 'pending', -- 'pending' | 'running' | 'completed' | 'failed'
  result_model_id     TEXT,                  -- 訓練完成後的模型 ID
  created_at          TIMESTAMPTZ DEFAULT now(),
  completed_at        TIMESTAMPTZ
);

-- ============================================
-- LLM 設定層
-- ============================================

-- LLM 供應商設定
CREATE TABLE llm_configs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID REFERENCES tenants(id) NOT NULL,
  provider            TEXT NOT NULL,         -- 'openai' | 'anthropic' | 'google' | ...
  model               TEXT NOT NULL,
  api_key_encrypted   TEXT NOT NULL,         -- AES-256 加密
  is_default          BOOLEAN DEFAULT false,
  cost_per_1k_tokens  FLOAT,
  created_at          TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- Agent 能力層（新增）
-- ============================================

-- 互動元件模板
CREATE TABLE widget_templates (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID REFERENCES projects(id) NOT NULL,
  name          TEXT NOT NULL,
  widget_type   TEXT NOT NULL,              -- 'single_select' | 'multi_select' | 'form' | ...
  config_json   JSONB NOT NULL,             -- 元件設定（選項、樣式等）
  created_by    UUID REFERENCES users(id),
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- 工具註冊
CREATE TABLE tools (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID REFERENCES tenants(id) NOT NULL,
  name          TEXT NOT NULL,
  description   TEXT,
  tool_type     TEXT NOT NULL,              -- 'api_call' | 'db_query' | 'webhook' | 'internal_fn' | 'mcp_server'
  config_json   JSONB NOT NULL,             -- API URL、參數定義、回應映射
  auth_config   JSONB DEFAULT '{}',         -- 認證設定（API Key、OAuth 等）
  permissions   TEXT[] DEFAULT '{}',        -- 誰可以觸發
  rate_limit    TEXT,                       -- 例如 '60/min'
  is_active     BOOLEAN DEFAULT true,
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- 能力規則（訓練者教出來的「什麼時候做什麼」）
CREATE TABLE capability_rules (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            UUID REFERENCES projects(id) NOT NULL,
  trigger_description   TEXT NOT NULL,       -- 人話描述的觸發條件
  trigger_embedding     VECTOR(1536),        -- 觸發條件的向量（語意比對用，存在 Supabase pgvector）
  action_type           TEXT NOT NULL,       -- 'widget' | 'tool_call' | 'workflow' | 'composite'
  action_config         JSONB NOT NULL,      -- 對應的動作設定
  priority              INT DEFAULT 0,       -- 優先順序（數字越大越優先）
  is_active             BOOLEAN DEFAULT true,
  eval_score            FLOAT,               -- 這條規則的測試分數
  created_by            UUID REFERENCES users(id),
  created_at            TIMESTAMPTZ DEFAULT now()
);

-- 工作流定義
CREATE TABLE workflows (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            UUID REFERENCES projects(id) NOT NULL,
  name                  TEXT NOT NULL,
  trigger_description   TEXT NOT NULL,
  steps_json            JSONB NOT NULL,      -- 工作流步驟定義
  is_active             BOOLEAN DEFAULT true,
  created_at            TIMESTAMPTZ DEFAULT now()
);

-- 工作流執行紀錄
CREATE TABLE workflow_runs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id   UUID REFERENCES workflows(id) NOT NULL,
  session_id    UUID REFERENCES training_sessions(id),
  user_id       UUID REFERENCES users(id) NOT NULL,
  current_step  TEXT,
  status        TEXT DEFAULT 'running',     -- 'running' | 'completed' | 'failed' | 'waiting_input'
  context_json  JSONB DEFAULT '{}',         -- 執行過程中的變數和狀態
  started_at    TIMESTAMPTZ DEFAULT now(),
  completed_at  TIMESTAMPTZ
);

-- 審計日誌（所有工具呼叫紀錄）
CREATE TABLE audit_logs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID REFERENCES tenants(id) NOT NULL,
  user_id       UUID REFERENCES users(id),
  action_type   TEXT NOT NULL,              -- 'tool_call' | 'workflow_step' | 'widget_response' | ...
  tool_id       UUID REFERENCES tools(id),
  request_data  JSONB,
  response_data JSONB,
  status        TEXT,                       -- 'success' | 'error' | 'dry_run'
  created_at    TIMESTAMPTZ DEFAULT now()
);
```

---

## 六、安全機制

| 機制 | 說明 |
|------|------|
| **API Key 加密** | 租戶的第三方 API Key 用 AES-256 加密存放，不會明文暴露 |
| **權限隔離** | 每個工具設定誰能觸發（admin / trainer / end-user） |
| **執行沙盒** | API 呼叫透過後端 Proxy 發出，前端不直接接觸外部 API |
| **速率限制** | 每個工具有獨立的速率限制，防止濫用 |
| **審計日誌** | 所有工具呼叫都記錄：誰觸發、什麼時候、送了什麼參數、回了什麼 |
| **Dry Run 模式** | 工具在測試階段可以「假執行」，不真的呼叫外部 API |
| **敏感操作確認** | 涉及寫入/刪除/付款的操作，強制顯示 confirm 元件讓使用者確認 |
| **RLS（行級安全）** | Supabase Row-Level Security，租戶只能看到自己的資料 |
| **Tenant Namespace** | Qdrant 向量 DB 用 namespace 隔離各租戶的知識庫 |

---

## 七、撲克 Demo 完整應用對照表

| 通用模組 | 撲克場景對應 |
|----------|-------------|
| Onboarding Interview | 「你的俱樂部打什麼級別？常見桌型？成員程度？」 |
| Knowledge Upload | 上傳 GTO 策略文件、俱樂部規章、常見爭議判例 |
| Prompt Rules | 「當玩家問翻牌策略時，先問持牌範圍再給建議」 |
| Test Cases | 100 組「玩家問題 → 教練標準回答」 |
| Fine-tune | 用累積的高品質對話訓練出「PokerVerse AI 教練 v1」 |
| 最終產品 | 嵌入 PokerVerse App 的 AI 教練功能 |

### Agent 場景對照

| 場景 | 互動元件 | 工具呼叫 | 工作流 |
|------|---------|---------|--------|
| 「這手牌該怎麼打？」 | 選位置 → 選持牌 → 選牌面 | 呼叫 GTO solver API | — |
| 「幫我報名今晚錦標賽」 | 確認賽事 → 確認付款 | 查賽事 → 建報名 | 完整報名流程 |
| 「我最近戰績如何？」 | — | 查詢玩家數據 API | — |
| 「推薦適合的牌桌」 | 選偏好（級別/人數/牌型） | 查可用牌桌 → 過濾 | — |
| 「新人想入會」 | 填資料表單 → 選方案 → 確認 | 建帳號 + 扣款 + 通知 | 完整入會流程 |

---

## 八、開發階段規劃（完整版）

### Phase 0：地基（2-3 週）
- [ ] 專案初始化：Next.js + Supabase + FastAPI 骨架
- [ ] Supabase Schema 建立 + RLS（行級安全策略）
- [ ] Qdrant Cloud 開通 + 基礎連線
- [ ] LiteLLM 整合 + 至少接通 Claude + GPT
- [ ] 基礎 Auth + 多租戶骨架

### Phase 1：訓練對話 MVP（3-4 週）
- [ ] Onboarding Interview 流程（AI 主動提問 → 建立基線）
- [ ] 自由對話訓練介面
- [ ] Feedback Widget（打分 + 修正）
- [ ] 對話歷史儲存
- [ ] 從對話自動產出 Prompt 修改建議

### Phase 2：RAG 知識庫（2-3 週）
- [ ] 文件上傳 + 自動切塊 + 向量化
- [ ] 知識庫瀏覽器（搜尋 / 刪除 / 編輯）
- [ ] RAG 查詢整合進對話流程
- [ ] 從對話自動抽取知識候選

### Phase 3：Agent Toolkit — 互動元件 & 工具（3-4 週）
- [ ] Widget Engine — 前端元件渲染系統 + 結果回傳機制
- [ ] Widget 元件庫：single_select / multi_select / form / confirm / rank / slider / date_picker / card_carousel
- [ ] Tool Registry — 工具 CRUD + API 連接器 + Dry Run 模式
- [ ] Capability Rules — 規則儲存 + 語意比對觸發
- [ ] Capability Trainer — 對話式定義規則的訓練介面
- [ ] Agent Orchestrator — 意圖分類 + 能力分派 + 回覆組合

### Phase 4：Prompt Studio + 評估引擎（3-4 週）
- [ ] Prompt 視覺化編輯器
- [ ] 版本控制 + Diff 對比
- [ ] 測試案例管理 CRUD（含 Agent 行為測試）
- [ ] 自動跑分 + 回歸測試
- [ ] 評分儀表板

### Phase 5：Workflow Engine（2-3 週）
- [ ] 工作流定義格式 + 執行引擎
- [ ] 視覺化工作流編輯器（拖拉式）
- [ ] 工作流執行紀錄 + Debug 工具
- [ ] MCP Server 整合（選用）

### Phase 6：Fine-tune 管線（2-3 週）
- [ ] 訓練資料自動抽取 + 清洗
- [ ] 格式轉換器（JSONL 等）
- [ ] 一鍵送出訓練 + 狀態追蹤
- [ ] 新舊模型 A/B 測試

### Phase 7：撲克 Demo + 打磨（2-3 週）
- [ ] 撲克領域模板（Onboarding 問題集 + 預設知識 + 預設工具）
- [ ] 連接 PokerVerse 展示
- [ ] PWA 封裝 + Capacitor 打包測試
- [ ] 效能優化 + 錯誤處理

### Phase 8：上線準備（2 週）
- [ ] 計費系統串接（Stripe）
- [ ] Landing Page
- [ ] 文件 / 使用者引導
- [ ] 監控 + 告警設定

### 預估總時程：20-27 週（無時間壓力，做對比較重要）

---

## 九、成本估算（月費）

| 項目 | 預估月費 (USD) | 備註 |
|------|---------------|------|
| Vercel Pro | $20 | 前端部署 |
| Railway / Fly.io | $10-30 | Python 微服務 |
| Supabase Pro | $25 | 業務 DB |
| Qdrant Cloud | $25-65 | 向量 DB（依資料量） |
| LLM API 費用 | $50-500+ | 依用量，初期低 |
| LangFuse | $0 (自架) 或 $59 | LLM 監控 |
| **合計（初期）** | **$130-200/月** | 不含 LLM API 大量使用 |

---

## 十、風險與對策

| 風險 | 影響 | 對策 |
|------|------|------|
| 非技術使用者不知道怎麼「教」AI | 產品無法被使用 | Onboarding Interview 做好引導 + 領域模板預設 80% 問題 |
| AI 自動修改 prompt 後品質下降 | 信任崩塌 | 評估引擎 + 回歸測試 + 回滾機制三重保險 |
| Fine-tune 資料量不夠 | 微調效果差 | 先用 Prompt + RAG 撐住，Fine-tune 作為進階功能 |
| Solo 開發戰線太長 | 進度失控 | 嚴格 Phase 切割，每個 Phase 獨立可交付 |
| LLM API 成本失控 | 虧錢 | Smart Routing + 成本追蹤 + 用量限制 |
| Agent 工具呼叫出錯造成資料損壞 | 使用者資料受損 | Dry Run 模式 + 敏感操作確認 + 審計日誌 + 回滾 |
| 能力規則衝突（多條規則同時匹配） | AI 行為不可預測 | Priority 排序 + 衝突偵測 + 測試覆蓋 |

---

## 十一、命名建議

| 候選名 | 概念 |
|--------|------|
| **TrainMyAI** | 直白，使用者秒懂 |
| **Forge AI** | 鍛造你的 AI，有「打磨」的意象 |
| **MoldAI** | 塑造 AI，像陶藝一樣 |
| **AI Dojo** | AI 道場，訓練的場所 |
| **NeuralForge** | 神經鍛造，技術感較重 |

---

## 十二、名詞對照表（白話解釋）

| 術語 | 白話 |
|------|------|
| **LLM (Large Language Model)** | 大型語言模型，就是 ChatGPT / Claude 這類 AI |
| **Prompt** | 提示詞，給 AI 的指令和規則 |
| **RAG (Retrieval-Augmented Generation)** | 先查資料再回答，讓 AI 回答時有參考依據 |
| **Fine-tune** | 微調，用特定資料重新訓練模型，讓它在某個領域更準 |
| **Embedding** | 把文字轉成一串數字（向量），方便電腦比較語意相似度 |
| **向量資料庫 (Vector DB)** | 專門存放和搜尋這些「數字化的文字」的資料庫 |
| **Agent** | 代理人，不只會說話，還能操作工具、呼叫 API 的 AI |
| **Widget** | 互動元件，像按鈕、選單、表單這類可點擊操作的介面組件 |
| **Workflow** | 工作流，把多個步驟串成一個自動化流程 |
| **MCP (Model Context Protocol)** | 模型上下文協議，讓 AI 標準化地連接外部服務 |
| **Namespace** | 命名空間，用來隔離不同租戶資料的技術手段 |
| **RLS (Row-Level Security)** | 行級安全，資料庫層面確保每個租戶只能看到自己的資料 |
| **A/B Testing** | 同時跑兩個版本，看哪個表現更好 |
| **Regression Test** | 回歸測試，確保改了新東西之後舊功能沒壞掉 |
| **Dry Run** | 假執行，走一遍流程但不真的操作，用來測試 |
| **SSO (Single Sign-On)** | 單一登入，用一組帳號就能登入多個系統 |
| **Webhook** | 鉤子，當事件發生時自動通知另一個系統 |
| **PWA (Progressive Web App)** | 漸進式網頁應用，網頁做得像 App 一樣可以裝在手機桌面 |
| **Capacitor** | 一個工具，把網頁包成 iOS / Android 原生 App |
| **LiteLLM** | 一個開源工具，用同一個介面呼叫各家 AI 模型 |
| **LlamaIndex** | 一個 Python 框架，專門處理 RAG 的資料切塊和檢索 |
| **LangFuse** | 一個監控工具，追蹤 AI 每次呼叫的品質和成本 |
| **Qdrant** | 一個開源向量資料庫，存放和搜尋語意化的資料 |

---

*文件版本：v2.0 完整合併版 | 產出日期：2026-04-01 | 作者：Claude × Allen*

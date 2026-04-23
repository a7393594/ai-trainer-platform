# C-end AI Coach 整合規格

> **建立：2026-04-23**
> 這份文件記錄 PokerVerse C-end 透過 proxy 整合 ai-trainer-platform 的技術介面，目的是在兩邊之間建立 single source of truth。
>
> **現況：整合工作在 `PokerVerse.git` 的 `feature/tournament-lifecycle-batch2-5` 分支，尚未合入 main**。該分支領先 main 518 commits，最新 10 個 commits 都是 `c-end/ai-coach` 相關的修復與強化。

---

## 整合架構

```
PokerVerse 玩家
    ↓ (Next.js 16 PWA)
pokerverse/b-end/c-end/
    ├── src/app/ai-coach/               ← C-end AI Coach UI（Onboarding / 儀表板 / 覆盤 / 複習 / 模擬）
    └── src/app/api/ai-coach/           ← Proxy layer
            ↓ (HTTPS / SSE)
ai-trainer-platform/
    └── ai-engine (FastAPI, port 8000)  ← 真實 AI 引擎
            ↓
        Supabase (cbezdrfehpxqyxwbsehj)
            └── ait_* tables            ← Trainer 側資料（獨立於 company_id）
```

---

## 整合點

### 1. 用戶映射（critical）

PokerVerse 的 `auth.uid()`（Supabase auth）**不等於** `ait_users.id`。

- **Proxy 層負責映射**：收到 C-end 請求 → 以 `auth.uid()` 查詢 `ait_users` → 取 `ait_users.id` 作為 AI 引擎請求的 `user_id`。
- **若 `ait_users` 中無此用戶**：proxy 應自動建立（或返回 401，由 C-end 引導走 onboarding）。
- **Bug 史**：`fix(c-end/ai-coach): 修復 user_id 映射 — auth.uid() → ait_users.id`（commit `98889931`）。

### 2. Onboarding（可跳過）

- C-end 的 onboarding 走 ai-trainer-platform 的 `/api/v1/onboarding/*` 端點。
- Proxy 容錯：onboarding 步驟允許跳過（不阻塞正式對話）。
- 相關 commit：`7af7ac33 fix(c-end/ai-coach): proxy auth 檢查 + onboarding 可跳過 + 錯誤容錯`。

### 3. 對話 SSE 串流

- C-end 呼叫 proxy → proxy 轉呼叫 `POST /api/v1/chat/stream`（ai-trainer-platform）
- Proxy 必須原樣 pass-through `text/event-stream`（不能改編碼或 buffer）。
- **安全 JSON 解析**：proxy 錯誤處理改用 `safeJson` 避免非 JSON 回應解析失敗（commit `f920e5d9`）。

### 4. Widget 標記協議

AI 引擎回覆中嵌入 `<!--WIDGET:{json}-->` 標記，C-end 解析為互動按鈕。

- **範例**：`<!--WIDGET:{"type":"multi_select","options":[...]}-->`
- **解析位置**：C-end 的對話渲染元件（`fix(c-end/ai-coach): 解析 <!--WIDGET:--> 標記為互動按鈕`，commit `163ac26a`）
- **互動優化**：支援 `multi-select` + 「其他」選項 + 舊輪 disable（commit `b15bec90`）。

### 5. Markdown 渲染

C-end 端需支援 AI 回覆的 Markdown：標題 / 粗體 / 清單 / 表格（commit `e287c73d`）。

### 6. 歷史對話

- C-end 的歷史對話 GET handler 必須用 `ait_users.id` 作 trainer ID 查詢（commit `f33a40ee`）。
- RLS policy 必須對 trainer ID 而非 auth.uid() 放行。

### 7. 附件

- 手牌附件：C-end 透過 HandRecordPicker 選取，附在 message.attachments。
- Proxy 把附件原樣轉給 AI 引擎。
- 相關 commit：`def65a0a fix(c-end/ai-coach): 恢復手牌附件 + 修復 sidebar 標題溢出`。

---

## 建議對外 API 合約（proxy ↔ ai-trainer-platform）

為避免未來 proxy 層耦合在私有 endpoint，建議統一走 Public API（`sk_live_` key + `/api/v1/public/*`），但目前**未實行**。現況是 proxy 走內部 endpoint + `auth_bypass` header。

| 合約項目 | 現況 | 建議 |
|---|---|---|
| 認證 | proxy 層自帶 service role | 改走 Integrations 管理頁發的 `sk_live_` key |
| 用戶識別 | proxy 映射 `auth.uid() → ait_users.id` | 映射邏輯改由 AI 引擎端處理（`/api/v1/users/resolve`） |
| Rate limit | 未套用 | 套用 ai-trainer-platform 的 plan_limits |
| 觀測 | 無統一 trace_id | 統一傳 `X-Request-Id` 讓 Langfuse 可貫穿 |

---

## 既知風險 / 待釐清

1. **未合入 main 的分支長度** — `feature/tournament-lifecycle-batch2-5` 有 518 個 commits，C-end AI Coach 僅其中 10 個。合 main 時是否 cherry-pick 還是整條進？
2. **資料所有權** — `ait_` 表存的用戶訓練資料所有權屬於 PokerVerse 還是 ai-trainer-platform？若未來拆為獨立 SaaS，遷移方案？
3. **Feature flag** — AI Coach 是所有 C-end 玩家都能用，還是特定 tier？目前 c-end 本地 `domain_config.features` 未見 gating。
4. **成本歸屬** — C-end AI Coach 的 LLM 成本算在哪個 `tenant_id`？是 PokerVerse 統一一個還是每 company 獨立？
5. **觀察：C-end 最新 `feat(c-end/ai-coach): 完整訓練系統 — Onboarding + 儀表板 + 數據 + 覆盤 + 複習 + 模擬` (commit `0ba1b04b`)** — 這條告訴我們 C-end 實作了六大模組（前端），但對應 ai-trainer-platform 的哪些 API 是否都已支援，需要 audit。

---

## 對齊的下一步

- [ ] 把 `feature/tournament-lifecycle-batch2-5` 裡關於 c-end/ai-coach 的改動開 PR 合 main（或列 cherry-pick 清單）
- [ ] 在 ai-trainer-platform 的 `app/api/v1/` 下加 `public/` 前綴版本，讓 C-end proxy 改走 public key
- [ ] 在 `pokerverse/openspec/specs/` 新增 `ai-coach` spec（呼應 ai-repair 的規格層級）
- [ ] 此檔案持續追蹤 integration 介面變更

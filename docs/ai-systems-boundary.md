# AI 系統邊界與生態文件對齊

> **建立：2026-04-23**
> 這份文件釐清 FORGE X / PokerVerse 生態中**三條 AI 系統線**的邊界、對接點，以及各規劃文件的現況與不一致記錄。
>
> 動機：先前盤點發現「ai-repair」已實作但 ai-trainer-platform 的文件從未提及，兩者可能功能重疊。這份文件是 single source of truth。

---

## 生態中的 AI 三條線

```
 ┌─────────────────────────────────────────────────────────────┐
 │                     FORGE X / 正義撲克                       │
 │                                                             │
 │  ┌────────────────────┐      ┌───────────────────────┐      │
 │  │  PokerVerse B-end  │      │  ai-trainer-platform  │      │
 │  │  （俱樂部後台）     │      │  （AI Agent 平台）    │      │
 │  │                    │      │                       │      │
 │  │  ┌──────────────┐  │      │  ┌──────────────────┐ │      │
 │  │  │ AI Repair    │◀─┼──────┼──│ （無關聯）       │ │      │
 │  │  │ （內部維運）  │  │      │  │                  │ │      │
 │  │  └──────────────┘  │      │  └──────────────────┘ │      │
 │  └────────────────────┘      │                       │      │
 │                              │                       │      │
 │  ┌────────────────────┐      │                       │      │
 │  │  PokerVerse C-end  │      │                       │      │
 │  │  （玩家 PWA）      │      │                       │      │
 │  │                    │      │                       │      │
 │  │  ┌──────────────┐  │ SSE  │  ┌──────────────────┐ │      │
 │  │  │ AI Coach UI  │──┼──────┼─▶│ AI 引擎 + RAG +  │ │      │
 │  │  │              │  │ Proxy│  │ Tools + Widget   │ │      │
 │  │  └──────────────┘  │      │  └──────────────────┘ │      │
 │  └────────────────────┘      └───────────────────────┘      │
 └─────────────────────────────────────────────────────────────┘
```

---

## 三條線的角色定義

### 線 1：ai-trainer-platform（AI Agent 訓練工作台）

- **身份**：獨立 SaaS / 產品（repo: `a7393594/ai-trainer-platform`，Vercel 獨立部署）
- **使命**：讓非技術人員用對話訓練領域 AI Agent（Prompt / RAG / Tool / Widget / Workflow / Eval / Fine-tune）
- **資料模型**：
  - 表前綴 `ait_`（與 PokerVerse `company_id` 體系完全隔離）
  - 多租戶：`ait_tenants` / `ait_users` / `ait_projects`
  - 不認識 `company_id` 也不需要
- **Project types**：`trainer`（通用） / `referee`（仲裁） / `poker_coach`（trainer + poker domain）
- **對外介面**：
  - Public API（`sk_live_*` key）
  - Embed widget（postMessage bridge + embed token）
- **目前被使用**：PokerVerse C-end AI Coach（走 proxy）

### 線 2：PokerVerse B-end AI Repair（內部維運工具）

- **身份**：PokerVerse B-end 的一個 tab（admin-panel 24 模組之一）
- **使命**：讓俱樂部管理員用自然語言描述系統問題，Claude API 診斷 + 產出 SQL 預覽 + 人工確認執行
- **資料模型**：直接操作 PokerVerse 的 company schema（~50 張業務表）
- **安全機制**（來自 `openspec/specs/ai-repair/spec.md`）：
  - AI 僅回傳建議 + SQL 預覽，不自動執行
  - 高風險操作（DELETE / ALTER）強制人工二次確認
  - 交易隔離 + 自動回滾
  - 執行前自動備份
  - 所有操作記錄 + Hash 鏈防竄改
- **狀態**：STATUS.md 標記為已完成

### 線 3：PokerVerse C-end AI Coach（玩家入口）

- **身份**：PokerVerse C-end（Next.js 16 PWA）的一個模組
- **使命**：讓玩家用對話式介面接受撲克教練輔導（Onboarding / 儀表板 / 覆盤 / 複習 / 模擬）
- **實作方式**：**Thin client + proxy 到 ai-trainer-platform**
- **整合規格**：見 `integration-c-end.md`
- **狀態**：
  - 在 b-end repo 的 `feature/tournament-lifecycle-batch2-5` 分支
  - 領先 main 518 commits（整條分支含賽事生命週期 + AI Coach）
  - 最新 10 個 commits 都是 ai-coach 修復與強化
  - **尚未合入 main**

---

## 邊界原則（避免重疊）

| 邊界 | Line 1 (AI Trainer) | Line 2 (AI Repair) | Line 3 (AI Coach) |
|---|---|---|---|
| **操作對象** | `ait_*` 表 + project 資料 | PokerVerse 業務表 + schema | `ait_*` 透過 Line 1 |
| **用戶** | 訓練者 / 產品經理 | 俱樂部管理員 | 撲克玩家 |
| **授權層級** | 各 tenant 獨立 | 公司 admin | 玩家身份 |
| **風險分類** | 低（對話 / 知識修改） | **極高**（真實業務資料 + schema） | 低（僅對 `ait_*` 讀寫） |
| **是否執行 SQL** | ❌ 不會 | ✅ 會（人工確認） | ❌ 不會 |
| **是否有 LLM 呼叫** | ✅ 大量 | ✅ Claude API | ✅ 透過 Line 1 |
| **觀測平台** | Langfuse | PokerVerse 內建 audit_log | Langfuse（經 Line 1） |

**原則**：三條線**永遠不共用資料庫 schema**。Line 1 的 `ait_*` 與 Line 2 的 company schema 是兩套 Supabase schema 或 namespace，Line 3 是純前端 + proxy，不直接碰資料庫。

---

## 生態規劃文件清單（補充 ai-trainer-platform/docs/ 之外）

| 位置 | 文件 | 涵蓋 |
|---|---|---|
| `pokerverse/openspec/project.md` | 專案總覽 | PokerVerse 平台整體（B / C / D 端） |
| `pokerverse/openspec/STATUS.md` | 進度狀態 | 21 模組完成清單 |
| `pokerverse/openspec/STANDARDS.md` | 技術標準 | 多租戶 / 聚合欄位 / RLS / i18n / 法務 |
| `pokerverse/openspec/WORKFLOW.md` | 開發流程 | MCP 工具同步 / BDD / audit_log |
| `pokerverse/openspec/config.yaml` | Config | openspec 配置 |
| `pokerverse/openspec/specs/ai-repair/spec.md` | AI Repair 規格 | 見上文 Line 2 |
| `pokerverse/openspec/specs/c-end/spec.md` | C-end 規格 | Next.js 16 + PWA + AI Coach 規劃 |
| `pokerverse/openspec/specs/{16 個其他}/spec.md` | 業務 spec | tournament / registration / ... |
| `pokerverse/openspec/changes/2026-03-c-end-tech-stack.md` | 技術棧決策 | React Native → Next.js 16 改動說明 |
| `pokerverse/openspec/changes/2026-03-mcp-server.md` | MCP Server 規劃 | DB 操作同步至 MCP |
| `PokerVerse_專案總覽報告.docx` | 2026-03-21 進度報告 | 雙軌過渡（Glide → Next.js），B-end 19 模組 |
| `參考資料/20250712營運手冊 -_ PV.pdf` | 現行營運手冊 | 舊版（Glide）營運流程參考 |

---

## 已知文件不一致

本區記錄各規劃文件之間的差異，供後續統一時參考。

### 1. B-end 模組數：19 vs 21

- **docx（2026-03-21）**：寫「19 個 B-end 模組完成，計畫中 9 個」。
- **`openspec/STATUS.md`**：寫 21 個模組完成（多了 **知識庫**、**AI 修復**）。
- **原因**：docx 報告時間早於 ai-repair + 知識庫完工。
- **建議**：以 STATUS.md 為準，docx 僅作時間點快照保留。

### 2. C-end 技術棧：React Native vs Next.js 16 + PWA

- **舊 spec**：React Native（iOS + Android + Web）
- **新 spec（`c-end/spec.md` + `changes/2026-03-c-end-tech-stack.md`）**：Next.js 16 + PWA
- **原因**：2026-03 的 change proposal 切換。
- **建議**：以新 spec 為準，舊 spec 片段若仍殘留於 docx / 其他文件請略過。

### 3. ai-trainer-platform 未出現在 PokerVerse 生態文件

- **現況**：`openspec/project.md` / `STATUS.md` 都沒寫 AI Coach 用的是哪個引擎。
- **後果**：新人看 PokerVerse 文件不會知道 AI Coach 的後端是 ai-trainer-platform。
- **建議**：在 `openspec/specs/c-end/spec.md` 的「AI 教練」段落加一條註解：「AI 引擎由 ai-trainer-platform 提供，整合規格見 ai-trainer-platform/docs/integration-c-end.md」。

### 4. `vision-vs-reality.md`（本 repo）長期未更新

- **舊版**：Phase 1-6 完成時寫，估 85-90% 完成。
- **新版（2026-04-23）**：97% 完成（大多數缺口已補）。
- **建議**：設自動化規則或每季 review 一次。

### 5. poker-referee-ai 是遺留 repo

- **現況**：`a7393594/poker-referee-ai` 還在 GitHub（`4b4f51f`）
- **功能已搬遷**：合併進 ai-trainer-platform 以 `project_type=referee` 啟用
- **建議**：在該 repo 建立 `README.md` 明確標示 archive + 轉移目的地

### 6. `vision-operation-flow.md` 是產品 vision，不是實作 spec

- **定位**：從使用者角度描述「應該有什麼」。
- **注意**：不要把 `vision-operation-flow.md` 誤作 spec 看待；實作對照要看 `spec-v2.md` + 本 `vision-vs-reality.md`。

---

## 生態層級的下一步

- [ ] 在 `pokerverse/openspec/specs/c-end/spec.md` 加 AI Coach → ai-trainer-platform 的引用
- [ ] 考慮在 `pokerverse/openspec/specs/` 新增 `ai-coach` spec（與 ai-repair 同級）
- [ ] 定期（每月？）review 本檔案 + `integration-c-end.md` + `vision-vs-reality.md`
- [ ] 把 PokerVerse 生態的所有 Claude 相關功能集中到一份「AI 平台藍圖」文件（可在本 repo 下 `ecosystem.md`）

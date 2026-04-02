# AI Trainer Platform

> 對話式 AI Agent 訓練工作台 — 讓任何人透過對話訓練出能互動、能操作的 AI Agent

## 專案結構

```
ai-trainer-platform/
├── frontend/          # Next.js 前端（Web + PWA + Capacitor）
│   ├── src/
│   │   ├── app/       # Next.js App Router 頁面
│   │   ├── components/# React 元件
│   │   │   ├── chat/  # 對話介面相關
│   │   │   ├── widgets/# AI 互動元件（選項、表單、確認...）
│   │   │   └── ui/    # shadcn/ui 基礎元件
│   │   ├── lib/       # 工具函數、API client
│   │   └── types/     # TypeScript 型別定義
│   └── package.json
│
├── ai-engine/         # Python FastAPI AI 引擎
│   ├── app/
│   │   ├── api/       # API 路由
│   │   ├── core/      # 核心邏輯
│   │   │   ├── orchestrator/  # Agent 調度器
│   │   │   ├── llm_router/    # 多模型切換
│   │   │   ├── rag/           # RAG 管線
│   │   │   ├── prompt/        # Prompt 管理
│   │   │   ├── eval/          # 評估引擎
│   │   │   ├── finetune/      # Fine-tune 管線
│   │   │   ├── widgets/       # 互動元件定義
│   │   │   ├── tools/         # 工具註冊 & 執行
│   │   │   └── workflows/     # 工作流引擎
│   │   ├── db/        # 資料庫連線
│   │   └── models/    # Pydantic 資料模型
│   ├── requirements.txt
│   └── Dockerfile
│
├── docs/              # 規格文件
├── docker-compose.yml # 本地開發環境
└── README.md
```

## 快速開始

### 前置需求
- Node.js 20+
- Python 3.11+
- Docker（可選，用於本地 Qdrant）

### 1. 前端

```bash
cd frontend
npm install
cp .env.example .env.local
# 填入 Supabase URL / Key
npm run dev
```

### 2. AI 引擎

```bash
cd ai-engine
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 填入 API Keys
uvicorn app.main:app --reload --port 8000
```

### 3. 本地 Qdrant（Docker）

```bash
docker compose up qdrant -d
```

## 技術棧

| 層級 | 技術 |
|------|------|
| 前端 | Next.js 14 + React + shadcn/ui + Tailwind |
| 手機 | Capacitor (PWA → iOS/Android) |
| AI 引擎 | Python FastAPI |
| 業務 DB | Supabase (PostgreSQL) |
| 向量 DB | Qdrant |
| LLM | LiteLLM（多模型切換） |
| RAG | LlamaIndex |
| 監控 | Sentry + LangFuse |

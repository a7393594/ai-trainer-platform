'use client'

import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'

export type Locale = 'zh-TW' | 'en'

const translations: Record<Locale, Record<string, string>> = {
  'zh-TW': {
    // ====== Nav ======
    'nav.chat': '訓練對話',
    'nav.knowledge': '知識庫',
    'nav.prompts': '提示詞工作室',
    'nav.eval': '評估引擎',
    'nav.tools': '工具管理',
    'nav.workflows': '工作流',
    'nav.settings': '設定',
    'nav.integrations': '整合管理',
    'nav.signOut': '登出',

    // ====== Login ======
    'login.title': 'AI Trainer',
    'login.signIn': '登入你的工作區',
    'login.signUp': '建立帳號',
    'login.google': '使用 Google 繼續',
    'login.or': '或',
    'login.email': '電子郵件',
    'login.password': '密碼',
    'login.signInBtn': '登入',
    'login.signUpBtn': '註冊',
    'login.noAccount': '還沒有帳號？',
    'login.hasAccount': '已有帳號？',
    'login.loading': '載入中...',
    'login.checkEmail': '請查看你的信箱驗證連結',

    // ====== Landing ======
    'landing.badge': '對話式 AI Agent 訓練平台',
    'landing.heroTitle1': '訓練你的 AI Agent',
    'landing.heroTitle2': '透過對話',
    'landing.heroDesc': '非技術人員也能透過自然對話，訓練出能聊天、操作元件、呼叫 API、執行多步驟工作流的領域專用 AI Agent。',
    'landing.start': '開始訓練',
    'landing.viewSettings': '查看設定',
    'landing.openDashboard': '進入主控台',
    'landing.everything': '完整功能',
    'landing.feat.chat': '訓練對話',
    'landing.feat.chatDesc': '支援串流的對話介面，透過即時回饋教會你的 AI。',
    'landing.feat.knowledge': '知識庫',
    'landing.feat.knowledgeDesc': '上傳文件啟用 RAG 回覆，自動切塊與向量搜尋。',
    'landing.feat.prompts': '提示詞工作室',
    'landing.feat.promptsDesc': '版本控制的系統提示詞，根據回饋自動產出優化建議。',
    'landing.feat.eval': '評估引擎',
    'landing.feat.evalDesc': '建立測試案例，用 LLM 評分自動跑分。',
    'landing.feat.tools': '工具註冊',
    'landing.feat.toolsDesc': '註冊外部 API、Webhook 和 MCP 服務給 AI 使用。',
    'landing.feat.workflows': '工作流',
    'landing.feat.workflowsDesc': '建立帶分支邏輯和錯誤處理的多步驟自動化流程。',
    'landing.loop': '訓練迴圈',
    'landing.step1': '引導式訪談',
    'landing.step1Desc': 'AI 提問建立你的領域基線',
    'landing.step2': '自由訓練',
    'landing.step2Desc': '自由對話 — 貼資料、寫規則、給範例',
    'landing.step3': '回饋打分',
    'landing.step3Desc': '對 AI 回覆評分：正確、部分正確、錯誤，加修正',
    'landing.step4': '自動優化',
    'landing.step4Desc': '系統根據回饋產出提示詞改善建議',
    'landing.step5': '評估測試',
    'landing.step5Desc': '跑測試案例驗證改善，含回歸檢測',
    'landing.step6': '持續迭代',
    'landing.step6Desc': '每個循環讓你的 AI 更聰明',
    'landing.builtWith': '技術棧',

    // ====== Chat ======
    'chat.title': '訓練對話',
    'chat.empty': '開始對話來訓練你的 AI',
    'chat.emptyHint': '在下方輸入訊息或選擇引導模式',
    'chat.placeholder': '輸入訊息...',
    'chat.placeholderOnboard': '請用上方元件回答...',
    'chat.send': '送出',
    'chat.sessions': '會話',
    'chat.newSession': '+ 新增',
    'chat.freeTraining': '自由訓練',
    'chat.guidedSetup': '引導式建立',
    'chat.promptOpt': 'Prompt 優化',
    'chat.connecting': '連線中...',
    'chat.cantConnect': '無法連線到 AI 引擎',
    'chat.startBackend': '請啟動後端：',

    // ====== Feedback ======
    'feedback.correct': '✓ 正確',
    'feedback.partial': '△ 部分正確',
    'feedback.wrong': '✗ 錯誤',
    'feedback.submitted': '已回饋',
    'feedback.correction': '正確的回答應該是...',
    'feedback.submit': '送出修正',

    // ====== Knowledge ======
    'knowledge.title': '知識庫',
    'knowledge.desc': '上傳文件啟用 RAG 回覆',
    'knowledge.upload': '上傳文件',
    'knowledge.docTitle': '文件標題',
    'knowledge.content': '貼上文件內容...',
    'knowledge.cancel': '取消',
    'knowledge.uploading': '上傳中...',
    'knowledge.delete': '刪除',
    'knowledge.empty': '尚無文件。上傳一個開始使用。',
    'knowledge.chunks': '區塊',
    'knowledge.view': '查看',
    'knowledge.edit': '編輯',
    'knowledge.save': '儲存',
    'knowledge.editTitle': '編輯文件',
    'knowledge.viewContent': '文件內容',
    'knowledge.chunkList': '切塊列表',
    'knowledge.saving': '儲存中...',
    'knowledge.close': '關閉',

    // ====== Prompts ======
    'prompts.title': '提示詞工作室',
    'prompts.desc': 'System Prompt 版本控制',
    'prompts.active': '使用中',
    'prompts.setActive': '設為使用中',
    'prompts.empty': '尚無提示詞版本。開始 Onboarding 產出第一個。',

    // ====== Eval ======
    'eval.title': '評估引擎',
    'eval.desc': '測試案例與自動化評估',
    'eval.testCases': '測試案例',
    'eval.runHistory': '執行歷史',
    'eval.addCase': '+ 新增測試案例',
    'eval.input': '輸入（問題）',
    'eval.expected': '預期輸出',
    'eval.category': '分類（選填）',
    'eval.save': '儲存',
    'eval.del': '刪除',
    'eval.runEval': '執行評估',
    'eval.running': '評估中...',
    'eval.passed': '通過',
    'eval.failed': '未通過',
    'eval.emptyCase': '尚無測試案例。新增一些來開始評估。',
    'eval.emptyRun': '尚無評估記錄。',
    'eval.score': '分數',

    // ====== Tools ======
    'tools.title': '工具管理',
    'tools.desc': '註冊與管理 AI Agent 的外部工具',
    'tools.register': '註冊工具',
    'tools.name': '工具名稱',
    'tools.description': '描述',
    'tools.test': '測試',
    'tools.empty': '尚無工具。新增一個來擴展 AI 的能力。',

    // ====== Workflows ======
    'workflows.title': '工作流',
    'workflows.desc': '建立多步驟自動化流程',
    'workflows.create': '建立工作流',
    'workflows.wfName': '工作流名稱',
    'workflows.trigger': '觸發條件（例如：當使用者要報名時）',
    'workflows.steps': '步驟',
    'workflows.empty': '尚無工作流。建立一個來自動化多步驟流程。',

    // ====== Settings ======
    'settings.title': '設定',
    'settings.desc': '專案設定與管理',
    'settings.projectInfo': '專案資訊',
    'settings.name': '名稱',
    'settings.projectId': '專案 ID',
    'settings.tenantId': '租戶 ID',
    'settings.domain': '領域',
    'settings.llmModels': '可用 LLM 模型',
    'settings.apiKeys': 'API 金鑰',
    'settings.connected': '已連接',
    'settings.notConfigured': '未設定',
    'settings.finetune': '微調資料',
    'settings.trainingPairs': '訓練對',
    'settings.totalFeedbacks': '總回饋數',
    'settings.status': '狀態',
    'settings.ready': '就緒',
    'settings.needMore': '需要更多',
    'settings.export': '匯出訓練資料 (JSONL)',
    'settings.language': '語言',

    // ====== Integrations ======
    'integrations.title': '整合管理',
    'integrations.desc': '為外部頁面嵌入與 API 呼叫產生 Embed Token',
    'integrations.create': '建立 Embed Token',
    'integrations.name': '名稱',
    'integrations.namePlaceholder': '例如：PokerVerse 生產環境',
    'integrations.allowedOrigins': '允許的來源（逗號分隔，留空=允許所有）',
    'integrations.originsPlaceholder': 'https://example.com, *.pokerverse.com',
    'integrations.scopes': '權限範圍',
    'integrations.scope.chat': '對話',
    'integrations.scope.widget': '互動元件',
    'integrations.scope.history': '讀取歷史',
    'integrations.createBtn': '建立',
    'integrations.tokenCreated': 'Token 已建立',
    'integrations.tokenWarning': '這個 token 只會顯示一次，請立即複製保存！',
    'integrations.copyToken': '複製 Token',
    'integrations.copySnippet': '複製 iframe 嵌入碼',
    'integrations.copied': '已複製！',
    'integrations.snippetTitle': 'iframe 嵌入碼',
    'integrations.revoke': '撤銷',
    'integrations.revokeConfirm': '確定要撤銷這個 token？撤銷後無法復原。',
    'integrations.empty': '尚無 Embed Token。建立一個開始將 AI 嵌入外部頁面。',
    'integrations.lastUsed': '最後使用',
    'integrations.never': '從未使用',
    'integrations.origins': '允許來源',
    'integrations.allOrigins': '所有來源',
    'integrations.done': '完成',
    'integrations.close': '關閉',
    'integrations.primaryProject': '主要 AI 模型',
    'integrations.additionalProjects': '額外授權的 AI 模型',
    'integrations.additionalProjectsHint': '勾選後，此 token 可在 embed 介面切換使用這些 project',
    'integrations.accessibleProjects': '可存取 project',

    // ====== Prompt Suggestion ======
    'suggestion.title': 'Prompt 優化建議',
    'suggestion.generate': '產出建議',
    'suggestion.analyzing': '分析中...',
    'suggestion.apply': '套用',
    'suggestion.dismiss': '忽略',
    'suggestion.empty': '尚無待審建議。點擊產出來分析回饋。',
    'suggestion.loading': '載入中...',
    'suggestion.basedOn': '依據 {count} 筆回饋',

    // ====== Common ======
    'common.cancel': '取消',
    'common.loading': '載入中...',
    'common.justNow': '剛剛',
    'common.mAgo': '{n}分鐘前',
    'common.hAgo': '{n}小時前',
    'common.dAgo': '{n}天前',
  },
  'en': {
    // ====== Nav ======
    'nav.chat': 'Training Chat',
    'nav.knowledge': 'Knowledge',
    'nav.prompts': 'Prompt Studio',
    'nav.eval': 'Eval Engine',
    'nav.tools': 'Tools',
    'nav.workflows': 'Workflows',
    'nav.settings': 'Settings',
    'nav.integrations': 'Integrations',
    'nav.signOut': 'Sign Out',

    // ====== Login ======
    'login.title': 'AI Trainer',
    'login.signIn': 'Sign in to your workspace',
    'login.signUp': 'Create your account',
    'login.google': 'Continue with Google',
    'login.or': 'or',
    'login.email': 'Email',
    'login.password': 'Password',
    'login.signInBtn': 'Sign In',
    'login.signUpBtn': 'Sign Up',
    'login.noAccount': "Don't have an account?",
    'login.hasAccount': 'Already have an account?',
    'login.loading': 'Loading...',
    'login.checkEmail': 'Check your email for verification link',

    // ====== Landing ======
    'landing.badge': 'Conversational AI Agent Training Platform',
    'landing.heroTitle1': 'Train Your AI Agent',
    'landing.heroTitle2': 'Through Conversation',
    'landing.heroDesc': 'Non-technical users can train domain-specific AI agents that can chat, interact with widgets, call APIs, and execute multi-step workflows — all through natural conversation.',
    'landing.start': 'Start Training',
    'landing.viewSettings': 'View Settings',
    'landing.openDashboard': 'Open Dashboard',
    'landing.everything': 'Everything You Need',
    'landing.feat.chat': 'Training Chat',
    'landing.feat.chatDesc': 'Conversational interface with streaming responses. Teach your AI through dialogue with instant feedback.',
    'landing.feat.knowledge': 'Knowledge Base',
    'landing.feat.knowledgeDesc': 'Upload documents for RAG-powered responses. Automatic chunking and vector search.',
    'landing.feat.prompts': 'Prompt Studio',
    'landing.feat.promptsDesc': 'Version-controlled system prompts with auto-optimization suggestions based on user feedback.',
    'landing.feat.eval': 'Eval Engine',
    'landing.feat.evalDesc': 'Create test cases and run automated evaluations with LLM-powered scoring.',
    'landing.feat.tools': 'Tool Registry',
    'landing.feat.toolsDesc': 'Register external APIs, webhooks, and MCP servers for your agent to use.',
    'landing.feat.workflows': 'Workflows',
    'landing.feat.workflowsDesc': 'Build multi-step automated processes with branching logic and error handling.',
    'landing.loop': 'The Training Loop',
    'landing.step1': 'Guided Interview',
    'landing.step1Desc': 'AI asks questions to establish your domain baseline',
    'landing.step2': 'Free Training',
    'landing.step2Desc': 'Chat freely — paste data, write rules, give examples',
    'landing.step3': 'Feedback & Scoring',
    'landing.step3Desc': 'Rate AI responses as correct, partial, or wrong with corrections',
    'landing.step4': 'Auto-Optimize',
    'landing.step4Desc': 'System generates prompt improvement suggestions from feedback',
    'landing.step5': 'Evaluate & Test',
    'landing.step5Desc': 'Run test cases to verify improvements with regression detection',
    'landing.step6': 'Iterate',
    'landing.step6Desc': 'Continuous improvement — each cycle makes your AI smarter',
    'landing.builtWith': 'Built With',

    // ====== Chat ======
    'chat.title': 'Training Chat',
    'chat.empty': 'Start a conversation to train your AI',
    'chat.emptyHint': 'Type a message below or select guided mode',
    'chat.placeholder': 'Type a message...',
    'chat.placeholderOnboard': 'Use the widget above to answer...',
    'chat.send': 'Send',
    'chat.sessions': 'Sessions',
    'chat.newSession': '+ New',
    'chat.freeTraining': 'Free Training',
    'chat.guidedSetup': 'Guided Setup',
    'chat.promptOpt': 'Prompt Opt.',
    'chat.connecting': 'Connecting...',
    'chat.cantConnect': 'Cannot connect to AI Engine',
    'chat.startBackend': 'Start backend:',

    // ====== Feedback ======
    'feedback.correct': '✓ Correct',
    'feedback.partial': '△ Partial',
    'feedback.wrong': '✗ Wrong',
    'feedback.submitted': 'Feedback sent',
    'feedback.correction': 'The correct answer should be...',
    'feedback.submit': 'Submit Correction',

    // ====== Knowledge ======
    'knowledge.title': 'Knowledge Base',
    'knowledge.desc': 'Upload documents for RAG-powered responses',
    'knowledge.upload': 'Upload Document',
    'knowledge.docTitle': 'Document title',
    'knowledge.content': 'Paste document content here...',
    'knowledge.cancel': 'Cancel',
    'knowledge.uploading': 'Uploading...',
    'knowledge.delete': 'Delete',
    'knowledge.empty': 'No documents yet. Upload one to get started.',
    'knowledge.chunks': 'chunks',
    'knowledge.view': 'View',
    'knowledge.edit': 'Edit',
    'knowledge.save': 'Save',
    'knowledge.editTitle': 'Edit Document',
    'knowledge.viewContent': 'Document Content',
    'knowledge.chunkList': 'Chunks',
    'knowledge.saving': 'Saving...',
    'knowledge.close': 'Close',

    // ====== Prompts ======
    'prompts.title': 'Prompt Studio',
    'prompts.desc': 'System Prompt version control',
    'prompts.active': 'Active',
    'prompts.setActive': 'Set as Active',
    'prompts.empty': 'No prompt versions yet. Start an onboarding session to generate the first one.',

    // ====== Eval ======
    'eval.title': 'Eval Engine',
    'eval.desc': 'Test cases and automated evaluation',
    'eval.testCases': 'Test Cases',
    'eval.runHistory': 'Run History',
    'eval.addCase': '+ Add Test Case',
    'eval.input': 'Input (question)',
    'eval.expected': 'Expected output',
    'eval.category': 'Category (optional)',
    'eval.save': 'Save',
    'eval.del': 'Delete',
    'eval.runEval': 'Run Evaluation',
    'eval.running': 'Running...',
    'eval.passed': 'passed',
    'eval.failed': 'failed',
    'eval.emptyCase': 'No test cases. Add some to start evaluating.',
    'eval.emptyRun': 'No evaluation runs yet.',
    'eval.score': 'Score',

    // ====== Tools ======
    'tools.title': 'Tool Registry',
    'tools.desc': 'Register and manage external tools for your AI agent',
    'tools.register': 'Register Tool',
    'tools.name': 'Tool name',
    'tools.description': 'Description',
    'tools.test': 'Test',
    'tools.empty': 'No tools registered. Add one to extend your AI\'s capabilities.',

    // ====== Workflows ======
    'workflows.title': 'Workflows',
    'workflows.desc': 'Create multi-step automated processes',
    'workflows.create': 'Create Workflow',
    'workflows.wfName': 'Workflow name',
    'workflows.trigger': 'Trigger description (e.g., When user wants to register)',
    'workflows.steps': 'Steps',
    'workflows.empty': 'No workflows yet. Create one to automate multi-step processes.',

    // ====== Settings ======
    'settings.title': 'Settings',
    'settings.desc': 'Project configuration and management',
    'settings.projectInfo': 'Project Info',
    'settings.name': 'Name',
    'settings.projectId': 'Project ID',
    'settings.tenantId': 'Tenant ID',
    'settings.domain': 'Domain',
    'settings.llmModels': 'Available LLM Models',
    'settings.apiKeys': 'API Keys',
    'settings.connected': 'Connected',
    'settings.notConfigured': 'Not configured',
    'settings.finetune': 'Fine-tune Data',
    'settings.trainingPairs': 'Training Pairs',
    'settings.totalFeedbacks': 'Total Feedbacks',
    'settings.status': 'Status',
    'settings.ready': 'Ready',
    'settings.needMore': 'Need More',
    'settings.export': 'Export Training Data (JSONL)',
    'settings.language': 'Language',

    // ====== Integrations ======
    'integrations.title': 'Integrations',
    'integrations.desc': 'Generate Embed Tokens for embedding on external sites or calling via API',
    'integrations.create': 'Create Embed Token',
    'integrations.name': 'Name',
    'integrations.namePlaceholder': 'e.g. PokerVerse Production',
    'integrations.allowedOrigins': 'Allowed origins (comma-separated, empty = allow all)',
    'integrations.originsPlaceholder': 'https://example.com, *.pokerverse.com',
    'integrations.scopes': 'Scopes',
    'integrations.scope.chat': 'Chat',
    'integrations.scope.widget': 'Widgets',
    'integrations.scope.history': 'Read history',
    'integrations.createBtn': 'Create',
    'integrations.tokenCreated': 'Token Created',
    'integrations.tokenWarning': 'This token will only be shown once. Copy it now!',
    'integrations.copyToken': 'Copy Token',
    'integrations.copySnippet': 'Copy iframe snippet',
    'integrations.copied': 'Copied!',
    'integrations.snippetTitle': 'iframe Embed Code',
    'integrations.revoke': 'Revoke',
    'integrations.revokeConfirm': 'Revoke this token? This cannot be undone.',
    'integrations.empty': 'No embed tokens yet. Create one to start embedding your AI.',
    'integrations.lastUsed': 'Last used',
    'integrations.never': 'Never',
    'integrations.origins': 'Allowed origins',
    'integrations.allOrigins': 'All origins',
    'integrations.done': 'Done',
    'integrations.close': 'Close',
    'integrations.primaryProject': 'Primary AI model',
    'integrations.additionalProjects': 'Additional authorized AI models',
    'integrations.additionalProjectsHint': 'Checked projects can be switched to inside the embed UI',
    'integrations.accessibleProjects': 'Accessible projects',

    // ====== Prompt Suggestion ======
    'suggestion.title': 'Prompt Optimization',
    'suggestion.generate': 'Generate Suggestions',
    'suggestion.analyzing': 'Analyzing...',
    'suggestion.apply': 'Apply',
    'suggestion.dismiss': 'Dismiss',
    'suggestion.empty': 'No pending suggestions. Click generate to analyze feedback.',
    'suggestion.loading': 'Loading...',
    'suggestion.basedOn': 'Based on {count} feedbacks',

    // ====== Common ======
    'common.cancel': 'Cancel',
    'common.loading': 'Loading...',
    'common.justNow': 'just now',
    'common.mAgo': '{n}m ago',
    'common.hAgo': '{n}h ago',
    'common.dAgo': '{n}d ago',
  },
}

interface I18nContext {
  locale: Locale
  setLocale: (l: Locale) => void
  t: (key: string, params?: Record<string, string | number>) => string
}

const I18nCtx = createContext<I18nContext>({
  locale: 'zh-TW',
  setLocale: () => {},
  t: (key) => key,
})

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>('zh-TW')

  useEffect(() => {
    const saved = localStorage.getItem('ait-locale') as Locale | null
    if (saved && (saved === 'zh-TW' || saved === 'en')) {
      setLocaleState(saved)
    }
  }, [])

  const setLocale = (l: Locale) => {
    setLocaleState(l)
    localStorage.setItem('ait-locale', l)
  }

  const t = (key: string, params?: Record<string, string | number>): string => {
    let text = translations[locale]?.[key] || translations['en']?.[key] || key
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        text = text.replace(`{${k}}`, String(v))
      })
    }
    return text
  }

  return (
    <I18nCtx.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nCtx.Provider>
  )
}

export function useI18n() {
  return useContext(I18nCtx)
}

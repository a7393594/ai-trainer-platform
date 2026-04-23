'use client'

/**
 * /pipeline-config — 專案級每節點預設配置
 *
 * 把硬編碼的 orchestrator 流程視覺化為節點列表。
 * 每個節點可調整：model / temperature / max_tokens / tools / prompt prefix。
 * 儲存後套用到這個專案所有未來的 chat 呼叫。
 */

import { useEffect, useState } from 'react'
import { useProject } from '@/lib/project-context'
import { getPipelineConfig, savePipelineConfig, type NodeConfig } from '@/lib/studio/api'
import { listTools } from '@/lib/ai-engine'
import { ModelSelector } from '@/components/shared/ModelSelector'

// The hardcoded pipeline structure (matches orchestrator flow)
// Only nodes with `configurable: true` get an edit panel
interface NodeDef {
  label: string
  title: string
  description: string
  icon: string
  type: 'input' | 'process' | 'model' | 'parallel' | 'output'
  configurable: boolean
  configFields?: Array<'model' | 'temperature' | 'max_tokens' | 'tools' | 'system_prompt_prefix' | 'notes'>
}

const PIPELINE_NODES: NodeDef[] = [
  {
    label: 'user_input',
    title: '使用者輸入',
    description: '接收玩家訊息',
    icon: '📥',
    type: 'input',
    configurable: false,
  },
  {
    label: 'context_loader',
    title: '載入歷史',
    description: '從 session 讀取對話紀錄',
    icon: '⚙️',
    type: 'process',
    configurable: false,
  },
  {
    label: 'triage',
    title: '意圖分類',
    description: '判斷訊息類型（一般對話 / capability rule / workflow）',
    icon: '⚙️',
    type: 'process',
    configurable: false,
  },
  {
    label: 'prompt_compose',
    title: 'Prompt 組裝',
    description: 'System prompt + RAG + 歷史 + 當前訊息',
    icon: '⚙️',
    type: 'process',
    configurable: true,
    configFields: ['system_prompt_prefix', 'notes'],
  },
  {
    label: 'main_model',
    title: '主模型呼叫',
    description: '實際呼叫 LLM 產生回應（可選用工具、可串流）',
    icon: '🧠',
    type: 'model',
    configurable: true,
    configFields: ['model', 'temperature', 'max_tokens', 'tools', 'notes'],
  },
  {
    label: 'tool_iterations',
    title: '工具呼叫迴圈',
    description: '最多 5 輪；限制哪些工具可被使用',
    icon: '🔧',
    type: 'parallel',
    configurable: true,
    configFields: ['tools', 'notes'],
  },
  {
    label: 'widget_parse',
    title: 'Widget 解析',
    description: '從回應末尾 <!--WIDGET:--> 抽出互動元件',
    icon: '⚙️',
    type: 'process',
    configurable: false,
  },
  {
    label: 'output',
    title: '最終輸出',
    description: '寫入 ait_training_messages 並回傳給前端',
    icon: '📤',
    type: 'output',
    configurable: false,
  },
]

interface Tool {
  id: string
  name: string
  description?: string
}

export default function PipelineConfigPage() {
  const { currentProject } = useProject()
  const projectId = currentProject?.project_id
  const tenantId = currentProject?.tenant_id

  const [nodeConfigs, setNodeConfigs] = useState<Record<string, NodeConfig>>({})
  const [originalConfigs, setOriginalConfigs] = useState<Record<string, NodeConfig>>({})
  const [tools, setTools] = useState<Tool[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>('main_model')

  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    getPipelineConfig(projectId)
      .then((r) => {
        const cfgs = r.config.node_configs || {}
        setNodeConfigs(cfgs)
        setOriginalConfigs(JSON.parse(JSON.stringify(cfgs)))
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [projectId])

  useEffect(() => {
    if (!tenantId) return
    listTools(tenantId)
      .then((r: unknown) => {
        const data = (r as { tools?: Tool[] })?.tools || []
        setTools(data)
      })
      .catch(() => setTools([]))
  }, [tenantId])

  const dirty = JSON.stringify(nodeConfigs) !== JSON.stringify(originalConfigs)

  const updateNodeConfig = (label: string, patch: Partial<NodeConfig>) => {
    setNodeConfigs((prev) => {
      const current = prev[label] || {}
      const merged = { ...current, ...patch }
      // Remove undefined/empty so we don't persist noise
      const cleaned: NodeConfig = {}
      if (merged.model) cleaned.model = merged.model
      if (merged.temperature != null) cleaned.temperature = merged.temperature
      if (merged.max_tokens != null) cleaned.max_tokens = merged.max_tokens
      if (merged.tool_ids && merged.tool_ids.length > 0) cleaned.tool_ids = merged.tool_ids
      if (merged.system_prompt_prefix) cleaned.system_prompt_prefix = merged.system_prompt_prefix
      if (merged.notes) cleaned.notes = merged.notes
      return { ...prev, [label]: cleaned }
    })
  }

  const resetNodeConfig = (label: string) => {
    setNodeConfigs((prev) => {
      const next = { ...prev }
      delete next[label]
      return next
    })
  }

  const handleSave = async () => {
    if (!projectId) return
    setSaving(true)
    setNotice(null)
    try {
      const res = await savePipelineConfig(projectId, nodeConfigs)
      setOriginalConfigs(JSON.parse(JSON.stringify(res.config.node_configs)))
      setNotice('已儲存，新設定將套用到下次對話')
    } catch (e) {
      setNotice(e instanceof Error ? e.message : '儲存失敗')
    }
    setSaving(false)
    setTimeout(() => setNotice(null), 4000)
  }

  const handleRevert = () => {
    setNodeConfigs(JSON.parse(JSON.stringify(originalConfigs)))
  }

  if (!projectId) {
    return <div className="p-6 text-sm text-zinc-500">尚未選擇專案</div>
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-900">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto bg-zinc-900 p-6">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">Pipeline 配置</h1>
            <p className="text-xs text-zinc-500 mt-1">
              調整此專案的 AI 流程節點預設參數。儲存後套用到所有後續對話（不影響歷史）。
            </p>
          </div>
          <div className="flex items-center gap-2">
            {dirty && (
              <button
                onClick={handleRevert}
                className="rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200"
              >
                還原
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={!dirty || saving}
              className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
            >
              {saving ? '儲存中...' : '儲存並套用'}
            </button>
          </div>
        </div>

        {notice && (
          <div className="mb-3 rounded border border-blue-500/40 bg-blue-900/20 px-3 py-2 text-xs text-blue-300">
            {notice}
          </div>
        )}

        {/* Node cards */}
        <div className="space-y-2">
          {PIPELINE_NODES.map((node, idx) => {
            const cfg = nodeConfigs[node.label] || {}
            const hasCustom = Object.keys(cfg).length > 0
            const isExpanded = expanded === node.label

            return (
              <div
                key={node.label}
                className={`rounded-lg border transition-colors ${
                  hasCustom ? 'border-blue-500/50 bg-blue-500/5' : 'border-zinc-700 bg-zinc-800/40'
                }`}
              >
                <button
                  onClick={() => setExpanded(isExpanded ? null : node.label)}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left"
                >
                  <span className="text-zinc-500 text-xs font-mono w-6">#{idx + 1}</span>
                  <span className="text-lg">{node.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-zinc-200">{node.title}</span>
                      <span className="text-[10px] uppercase text-zinc-600 bg-zinc-800 rounded px-1.5 py-0.5">
                        {node.type}
                      </span>
                      {hasCustom && (
                        <span className="text-[10px] text-blue-400 bg-blue-500/10 rounded px-1.5 py-0.5">
                          已自訂
                        </span>
                      )}
                      {!node.configurable && (
                        <span className="text-[10px] text-zinc-600">（無可調參數）</span>
                      )}
                    </div>
                    <p className="text-xs text-zinc-500 mt-0.5">{node.description}</p>
                  </div>
                  {node.configurable && (
                    <span className="text-zinc-600 text-xs">{isExpanded ? '▼' : '▶'}</span>
                  )}
                </button>

                {isExpanded && node.configurable && (
                  <div className="border-t border-zinc-800 px-4 py-3 space-y-3">
                    {hasCustom && (
                      <div className="flex justify-end">
                        <button
                          onClick={() => resetNodeConfig(node.label)}
                          className="text-[10px] text-zinc-500 hover:text-red-400"
                        >
                          清除此節點所有自訂
                        </button>
                      </div>
                    )}

                    {node.configFields?.includes('model') && (
                      <div>
                        <label className="text-[10px] uppercase text-zinc-500 block mb-1">模型</label>
                        <ModelSelector
                          value={cfg.model || ''}
                          onChange={(v) => updateNodeConfig(node.label, { model: v })}
                          projectDefault={currentProject?.default_model}
                          showWarning
                          className="w-full"
                        />
                        <p className="text-[10px] text-zinc-600 mt-1">
                          未設定時使用專案預設（{currentProject?.default_model || 'claude-sonnet-4-20250514'}）
                        </p>
                      </div>
                    )}

                    {node.configFields?.includes('temperature') && (
                      <div>
                        <label className="flex items-center justify-between mb-1">
                          <span className="text-[10px] uppercase text-zinc-500">Temperature</span>
                          <span className="text-[10px] font-mono text-zinc-400">
                            {cfg.temperature != null ? cfg.temperature.toFixed(2) : '預設 (0.70)'}
                          </span>
                        </label>
                        <input
                          type="range"
                          min="0"
                          max="2"
                          step="0.05"
                          value={cfg.temperature ?? 0.7}
                          onChange={(e) =>
                            updateNodeConfig(node.label, { temperature: parseFloat(e.target.value) })
                          }
                          className="w-full accent-blue-500"
                        />
                        <div className="flex justify-between text-[9px] text-zinc-600">
                          <span>0 · 確定性</span>
                          <span>1 · 平衡</span>
                          <span>2 · 創造性</span>
                        </div>
                        {cfg.temperature != null && (
                          <button
                            onClick={() => updateNodeConfig(node.label, { temperature: undefined })}
                            className="mt-1 text-[10px] text-zinc-500 hover:text-zinc-300"
                          >
                            重設為預設
                          </button>
                        )}
                      </div>
                    )}

                    {node.configFields?.includes('max_tokens') && (
                      <div>
                        <label className="flex items-center justify-between mb-1">
                          <span className="text-[10px] uppercase text-zinc-500">Max Tokens</span>
                          <span className="text-[10px] font-mono text-zinc-400">
                            {cfg.max_tokens ?? '預設 (2000)'}
                          </span>
                        </label>
                        <input
                          type="number"
                          min="256"
                          max="32000"
                          step="256"
                          value={cfg.max_tokens ?? ''}
                          placeholder="2000"
                          onChange={(e) => {
                            const v = e.target.value ? parseInt(e.target.value, 10) : undefined
                            updateNodeConfig(node.label, { max_tokens: v })
                          }}
                          className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
                        />
                      </div>
                    )}

                    {node.configFields?.includes('tools') && (
                      <div>
                        <label className="block mb-1">
                          <span className="text-[10px] uppercase text-zinc-500">可用工具白名單</span>
                          <span className="ml-1 text-[9px] text-zinc-600">
                            （{(cfg.tool_ids || []).length} / {tools.length} 選中；未設定 = 全部工具皆可用）
                          </span>
                        </label>
                        {tools.length === 0 ? (
                          <p className="text-[10px] text-zinc-600">此 tenant 尚無註冊工具</p>
                        ) : (
                          <div className="max-h-32 overflow-y-auto space-y-0.5 rounded border border-zinc-800 bg-zinc-900 p-1">
                            {tools.map((t) => {
                              const selected = (cfg.tool_ids || []).includes(t.id)
                              return (
                                <button
                                  key={t.id}
                                  onClick={() => {
                                    const cur = new Set(cfg.tool_ids || [])
                                    if (cur.has(t.id)) cur.delete(t.id)
                                    else cur.add(t.id)
                                    updateNodeConfig(node.label, {
                                      tool_ids: cur.size === 0 ? undefined : Array.from(cur),
                                    })
                                  }}
                                  className={`w-full text-left px-2 py-1 rounded text-[10px] flex items-center gap-1.5 ${
                                    selected ? 'bg-blue-500/20 text-blue-300' : 'text-zinc-400 hover:bg-zinc-800'
                                  }`}
                                >
                                  <span
                                    className={`w-3 h-3 rounded border flex items-center justify-center text-[8px] ${
                                      selected ? 'bg-blue-500 border-blue-500 text-white' : 'border-zinc-600'
                                    }`}
                                  >
                                    {selected && '✓'}
                                  </span>
                                  <span className="font-mono">{t.name}</span>
                                  {t.description && (
                                    <span className="text-zinc-600 truncate flex-1">— {t.description}</span>
                                  )}
                                </button>
                              )
                            })}
                          </div>
                        )}
                      </div>
                    )}

                    {node.configFields?.includes('system_prompt_prefix') && (
                      <div>
                        <label className="text-[10px] uppercase text-zinc-500 block mb-1">
                          System Prompt 前綴（選填）
                        </label>
                        <textarea
                          value={cfg.system_prompt_prefix || ''}
                          onChange={(e) =>
                            updateNodeConfig(node.label, { system_prompt_prefix: e.target.value })
                          }
                          rows={3}
                          placeholder="會插入到 active prompt 之前..."
                          className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500 resize-y"
                        />
                      </div>
                    )}

                    {node.configFields?.includes('notes') && (
                      <div>
                        <label className="text-[10px] uppercase text-zinc-500 block mb-1">備註</label>
                        <input
                          type="text"
                          value={cfg.notes || ''}
                          onChange={(e) => updateNodeConfig(node.label, { notes: e.target.value })}
                          placeholder="這個節點的特殊用途..."
                          className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
                        />
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        <div className="mt-6 rounded border border-zinc-800 bg-zinc-950/50 p-3">
          <p className="text-[10px] text-zinc-500">
            <strong className="text-zinc-400">說明：</strong>
            此頁面的流程是目前硬編碼的 orchestrator 架構。完整拖拉式 DAG 編輯器（增減節點、改變連線）為後續規劃。
            目前提供的是每個現有節點的「參數覆寫」能力，儲存後會立即套用到下一次對話。
          </p>
        </div>
      </div>
    </div>
  )
}

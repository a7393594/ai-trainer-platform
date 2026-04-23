'use client'

import { useEffect, useMemo, useState } from 'react'
import type { NodeSpan, PipelineComparison } from '@/lib/studio/types'
import { formatCost, formatDuration } from '@/lib/studio/graph'
import {
  listAvailableModels, rerunNode, type ModelInfo,
  listPresets, createPreset, deletePreset, type RerunPreset,
} from '@/lib/studio/api'
import { listTools } from '@/lib/ai-engine'
import { useProject } from '@/lib/project-context'

interface PromptEditorProps {
  runId: string
  span: NodeSpan
  onComparisonCreated: (cmp: PipelineComparison) => void
}

interface Message {
  role: string
  content: string
}

interface Tool {
  id: string
  name: string
  description?: string
  tool_type?: string
}

export default function PromptEditor({ runId, span, onComparisonCreated }: PromptEditorProps) {
  const { currentProject } = useProject()
  const projectId = currentProject?.project_id
  const tenantId = currentProject?.tenant_id

  // Messages
  const original = useMemo<Message[]>(() => {
    if (!Array.isArray(span.input_ref)) return []
    return (span.input_ref as Message[]).map((m) => ({
      role: m.role || 'user',
      content: typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
    }))
  }, [span.input_ref])

  const [messages, setMessages] = useState<Message[]>(original)
  const [model, setModel] = useState(span.model || 'claude-sonnet-4-20250514')
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<PipelineComparison | null>(null)

  // Batch 4A: extended config
  const [temperature, setTemperature] = useState(0.7)
  const [maxTokens, setMaxTokens] = useState(2000)
  const [tools, setTools] = useState<Tool[]>([])
  const [selectedToolIds, setSelectedToolIds] = useState<Set<string>>(new Set())
  const [showAdvanced, setShowAdvanced] = useState(false)

  // Presets
  const [presets, setPresets] = useState<RerunPreset[]>([])
  const [showSavePreset, setShowSavePreset] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [presetDesc, setPresetDesc] = useState('')

  useEffect(() => {
    listAvailableModels().then(setAvailableModels).catch(() => {})
  }, [])

  useEffect(() => {
    if (!tenantId) return
    listTools(tenantId)
      .then((r: unknown) => {
        const data = (r as { tools?: Tool[] })?.tools || []
        setTools(data)
      })
      .catch(() => setTools([]))
  }, [tenantId])

  useEffect(() => {
    if (!projectId) return
    listPresets(projectId, 'model')
      .then((r) => setPresets(r.presets))
      .catch(() => setPresets([]))
  }, [projectId])

  // Reset when span changes
  useEffect(() => {
    setMessages(original)
    setModel(span.model || 'claude-sonnet-4-20250514')
    setLastResult(null)
    setError(null)
    setTemperature(0.7)
    setMaxTokens(2000)
    setSelectedToolIds(new Set())
  }, [original, span])

  const dirty = useMemo(
    () =>
      messages.length !== original.length ||
      messages.some((m, i) => m.content !== original[i]?.content) ||
      model !== (span.model || 'claude-sonnet-4-20250514') ||
      temperature !== 0.7 ||
      maxTokens !== 2000 ||
      selectedToolIds.size > 0,
    [messages, original, model, span.model, temperature, maxTokens, selectedToolIds]
  )

  const updateContent = (idx: number, content: string) => {
    setMessages((prev) => prev.map((m, i) => (i === idx ? { ...m, content } : m)))
  }

  const reset = () => {
    setMessages(original)
    setModel(span.model || 'claude-sonnet-4-20250514')
    setTemperature(0.7)
    setMaxTokens(2000)
    setSelectedToolIds(new Set())
  }

  const applyPreset = (preset: RerunPreset) => {
    if (preset.model) setModel(preset.model)
    if (preset.temperature != null) setTemperature(preset.temperature)
    if (preset.max_tokens != null) setMaxTokens(preset.max_tokens)
    if (preset.tool_ids) setSelectedToolIds(new Set(preset.tool_ids))
    // Apply system_prompt override if preset has one
    if (preset.system_prompt) {
      setMessages((prev) => {
        const next = [...prev]
        const sysIdx = next.findIndex((m) => m.role === 'system')
        if (sysIdx >= 0) next[sysIdx] = { ...next[sysIdx], content: preset.system_prompt! }
        else next.unshift({ role: 'system', content: preset.system_prompt! })
        return next
      })
    }
    setShowAdvanced(true)
  }

  const handleSavePreset = async () => {
    if (!projectId || !presetName.trim()) return
    try {
      const systemMsg = messages.find((m) => m.role === 'system')
      const res = await createPreset({
        project_id: projectId,
        node_type: 'model',
        name: presetName.trim(),
        description: presetDesc.trim() || undefined,
        model,
        system_prompt: systemMsg?.content,
        temperature,
        max_tokens: maxTokens,
        tool_ids: Array.from(selectedToolIds),
      })
      setPresets((p) => [res.preset, ...p])
      setShowSavePreset(false)
      setPresetName('')
      setPresetDesc('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleDeletePreset = async (id: string) => {
    if (!confirm('確定要刪除此 preset？')) return
    try {
      await deletePreset(id)
      setPresets((p) => p.filter((x) => x.id !== id))
    } catch { /* ignore */ }
  }

  const handleRerun = async () => {
    setRunning(true)
    setError(null)
    try {
      const res = await rerunNode(runId, span.id, {
        modelOverride: model,
        promptOverride: messages,
        temperatureOverride: temperature !== 0.7 ? temperature : undefined,
        maxTokensOverride: maxTokens !== 2000 ? maxTokens : undefined,
        toolIds: selectedToolIds.size > 0 ? Array.from(selectedToolIds) : undefined,
      })
      setLastResult(res.comparison)
      onComparisonCreated(res.comparison)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  const toggleTool = (id: string) => {
    setSelectedToolIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  if (original.length === 0) {
    return (
      <p className="text-[11px] text-zinc-500">
        此節點沒有可編輯的 messages（input_ref 不是 messages 列表）
      </p>
    )
  }

  return (
    <div className="space-y-3">
      {/* Preset bar */}
      {presets.length > 0 && (
        <div className="rounded border border-zinc-800 bg-zinc-900/60 p-2">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] uppercase text-zinc-500">已儲存配置</span>
            <button
              onClick={() => setShowSavePreset((s) => !s)}
              className="text-[10px] text-blue-400 hover:underline"
            >
              + 儲存當前
            </button>
          </div>
          <div className="flex flex-wrap gap-1">
            {presets.map((p) => (
              <div
                key={p.id}
                className="flex items-center gap-1 rounded bg-zinc-800 px-2 py-0.5 group"
                title={p.description || ''}
              >
                <button
                  onClick={() => applyPreset(p)}
                  className="text-[10px] text-zinc-300 hover:text-zinc-100"
                >
                  {p.name}
                </button>
                <button
                  onClick={() => handleDeletePreset(p.id)}
                  className="text-[10px] text-zinc-600 hover:text-red-400 opacity-0 group-hover:opacity-100"
                  title="刪除"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {presets.length === 0 && (
        <button
          onClick={() => setShowSavePreset((s) => !s)}
          className="text-[10px] text-zinc-500 hover:text-blue-400"
        >
          + 儲存當前配置為 preset
        </button>
      )}

      {showSavePreset && (
        <div className="rounded border border-blue-500/40 bg-blue-950/20 p-3 space-y-2">
          <input
            type="text"
            value={presetName}
            onChange={(e) => setPresetName(e.target.value)}
            placeholder="Preset 名稱（例如：保守 GTO 分析）"
            className="w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
          />
          <input
            type="text"
            value={presetDesc}
            onChange={(e) => setPresetDesc(e.target.value)}
            placeholder="說明（選填）"
            className="w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
          />
          <div className="flex gap-2">
            <button
              onClick={handleSavePreset}
              disabled={!presetName.trim()}
              className="flex-1 rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
            >
              儲存
            </button>
            <button
              onClick={() => { setShowSavePreset(false); setPresetName(''); setPresetDesc('') }}
              className="rounded border border-zinc-700 px-3 py-1 text-xs text-zinc-400"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* Model + action bar */}
      <div className="rounded border border-zinc-800 bg-zinc-900/60 p-3">
        <label className="mb-1 block text-[10px] uppercase text-zinc-500">模型</label>
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className="w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-200 outline-none focus:border-blue-500"
        >
          {availableModels.length > 0 ? (
            availableModels.map((m) => (
              <option key={m.id} value={m.id} disabled={m.available === false}>
                {m.label} ({m.provider}) {m.cost ? `· ${m.cost}` : ''} {m.available === false ? ' — 未配置' : ''}
              </option>
            ))
          ) : (
            <option value={model}>{model.replace(/-\d{8}$/, '')}</option>
          )}
        </select>

        {/* Advanced toggle */}
        <button
          onClick={() => setShowAdvanced((s) => !s)}
          className="mt-2 text-[10px] text-zinc-500 hover:text-zinc-300"
        >
          {showAdvanced ? '▼' : '▶'} 進階配置
          {(temperature !== 0.7 || maxTokens !== 2000 || selectedToolIds.size > 0) && (
            <span className="ml-1 text-yellow-400">●</span>
          )}
        </button>

        {showAdvanced && (
          <div className="mt-2 space-y-2 border-t border-zinc-800 pt-2">
            {/* Temperature */}
            <div>
              <label className="flex items-center justify-between mb-0.5">
                <span className="text-[10px] uppercase text-zinc-500">Temperature</span>
                <span className="text-[10px] font-mono text-zinc-400">{temperature.toFixed(2)}</span>
              </label>
              <input
                type="range"
                min="0"
                max="2"
                step="0.05"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full accent-blue-500"
              />
              <div className="flex justify-between text-[9px] text-zinc-600">
                <span>0 · 確定性</span>
                <span>1 · 平衡</span>
                <span>2 · 創造性</span>
              </div>
            </div>

            {/* Max tokens */}
            <div>
              <label className="flex items-center justify-between mb-0.5">
                <span className="text-[10px] uppercase text-zinc-500">Max Tokens</span>
                <span className="text-[10px] font-mono text-zinc-400">{maxTokens}</span>
              </label>
              <input
                type="number"
                min="256"
                max="32000"
                step="256"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value, 10) || 2000)}
                className="w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-200 outline-none focus:border-blue-500"
              />
            </div>

            {/* Tools whitelist */}
            {tools.length > 0 && (
              <div>
                <label className="block mb-0.5">
                  <span className="text-[10px] uppercase text-zinc-500">可用工具</span>
                  <span className="ml-1 text-[9px] text-zinc-600">
                    （{selectedToolIds.size} / {tools.length} 選中；不選 = 不提供工具）
                  </span>
                </label>
                <div className="max-h-32 overflow-y-auto space-y-0.5 rounded border border-zinc-800 bg-zinc-950 p-1">
                  {tools.map((t) => {
                    const selected = selectedToolIds.has(t.id)
                    return (
                      <button
                        key={t.id}
                        onClick={() => toggleTool(t.id)}
                        className={`w-full text-left px-2 py-1 rounded text-[10px] flex items-center gap-1.5 ${
                          selected ? 'bg-blue-500/20 text-blue-300' : 'text-zinc-400 hover:bg-zinc-800'
                        }`}
                      >
                        <span className={`w-3 h-3 rounded border flex items-center justify-center text-[8px] ${
                          selected ? 'bg-blue-500 border-blue-500 text-white' : 'border-zinc-600'
                        }`}>
                          {selected && '✓'}
                        </span>
                        <span className="font-mono">{t.name}</span>
                        {t.description && <span className="text-zinc-600 truncate flex-1">— {t.description}</span>}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
            {tools.length === 0 && tenantId && (
              <p className="text-[10px] text-zinc-600">此 tenant 尚無註冊工具</p>
            )}
          </div>
        )}

        <div className="mt-2 flex items-center gap-2">
          <button
            onClick={handleRerun}
            disabled={running}
            className="flex-1 rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500"
          >
            {running ? '重跑中…' : dirty ? '用修改後配置重跑' : '重跑此節點'}
          </button>
          {dirty && (
            <button
              onClick={reset}
              className="rounded border border-zinc-700 px-2 py-1.5 text-[11px] text-zinc-400 hover:text-zinc-200"
            >
              還原
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-500/60 bg-red-950/40 p-2 text-[11px] text-red-300">
          {error}
        </div>
      )}

      {lastResult && (
        <div className="rounded border border-emerald-500/60 bg-emerald-950/30 p-3">
          <div className="mb-1 flex items-center justify-between text-[10px] text-emerald-300">
            <span>新結果（{lastResult.model.replace(/-\d{8}$/, '')}）</span>
            <span>
              {formatDuration(lastResult.latency_ms)} / {formatCost(lastResult.cost_usd)}
            </span>
          </div>
          <pre className="max-h-36 overflow-auto whitespace-pre-wrap rounded bg-zinc-950/80 p-2 font-mono text-[11px] text-emerald-100">
            {lastResult.output_text}
          </pre>
        </div>
      )}

      {/* Messages editor */}
      <div className="space-y-2">
        {messages.map((m, i) => {
          const changed = m.content !== original[i]?.content
          return (
            <div
              key={i}
              className={`rounded border p-2 ${
                changed ? 'border-amber-500/60 bg-amber-950/20' : 'border-zinc-800 bg-zinc-900/60'
              }`}
            >
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[10px] uppercase text-zinc-500">{m.role}</span>
                {changed && <span className="text-[10px] text-amber-400">已修改</span>}
              </div>
              <textarea
                value={m.content}
                onChange={(e) => updateContent(i, e.target.value)}
                rows={Math.min(Math.max(m.content.split('\n').length, 3), 12)}
                className="w-full resize-y rounded border border-zinc-800 bg-zinc-950 px-2 py-1 font-mono text-[11px] leading-relaxed text-zinc-100 outline-none focus:border-blue-500"
                readOnly={m.role === 'user' && i === messages.length - 1}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}

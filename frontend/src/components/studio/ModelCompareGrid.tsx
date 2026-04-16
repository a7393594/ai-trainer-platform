'use client'

import { useEffect, useState } from 'react'
import type { PipelineComparison } from '@/lib/studio/types'
import { formatCost, formatDuration } from '@/lib/studio/graph'
import {
  compareNode,
  listAvailableModels,
  saveComparisonAsPrompt,
  saveComparisonAsTestCase,
  scoreComparison,
  selectComparison,
  type ModelInfo,
} from '@/lib/studio/api'

interface ModelCompareGridProps {
  runId: string
  nodeId: string
  currentModel: string | null
  initialComparisons: PipelineComparison[]
  onComparisonsChange: (rows: PipelineComparison[]) => void
}

export default function ModelCompareGrid({
  runId,
  nodeId,
  currentModel,
  initialComparisons,
  onComparisonsChange,
}: ModelCompareGridProps) {
  const [comparisons, setComparisons] = useState<PipelineComparison[]>(initialComparisons)
  const [candidateModels, setCandidateModels] = useState<ModelInfo[]>([])
  const [selectedModels, setSelectedModels] = useState<string[]>(() =>
    currentModel ? [currentModel] : []
  )

  // 從 API 動態載入可用模型
  useEffect(() => {
    listAvailableModels()
      .then((models) => {
        setCandidateModels(models)
        // 如果 currentModel 不在可用列表裡,清掉預選
        if (currentModel && !models.some((m) => m.id === currentModel)) {
          setSelectedModels([])
        }
      })
      .catch(() => {
        // fallback: 只放 anthropic 系列
        setCandidateModels([
          { id: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4', provider: 'anthropic', available: true, cost: '$3.0/15.0', notes: '' },
          { id: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5', provider: 'anthropic', available: true, cost: '$0.8/4.0', notes: '' },
        ])
      })
  }, [])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [scoringIds, setScoringIds] = useState<Set<string>>(new Set())
  const [savingTestCaseIds, setSavingTestCaseIds] = useState<Set<string>>(
    new Set()
  )

  const toggleModel = (model: string) => {
    setSelectedModels((prev) =>
      prev.includes(model)
        ? prev.filter((m) => m !== model)
        : prev.length >= 4
        ? prev
        : [...prev, model]
    )
  }

  const handleRunCompare = async () => {
    if (selectedModels.length === 0) {
      setError('至少選 1 個模型')
      return
    }
    setRunning(true)
    setError(null)
    try {
      const res = await compareNode(runId, nodeId, selectedModels)
      const merged = [...comparisons, ...res.comparisons]
      setComparisons(merged)
      onComparisonsChange(merged)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  const handleSelect = async (cmpId: string) => {
    try {
      await selectComparison(runId, nodeId, cmpId)
      const updated = comparisons.map((c) => ({
        ...c,
        is_selected: c.id === cmpId,
      }))
      setComparisons(updated)
      onComparisonsChange(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleSaveAsPrompt = async (cmpId: string) => {
    setSavingId(cmpId)
    setSaveMessage(null)
    try {
      const res = await saveComparisonAsPrompt(cmpId)
      if (res.prompt_version) {
        setSaveMessage(
          `已儲存為 Prompt v${
            (res.prompt_version as { version?: number }).version ?? '?'
          }`
        )
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingId(null)
    }
  }

  const handleScoreOne = async (cmpId: string) => {
    setScoringIds((prev) => new Set(prev).add(cmpId))
    try {
      const res = await scoreComparison(cmpId)
      const updated = comparisons.map((c) =>
        c.id === cmpId ? res.comparison : c
      )
      setComparisons(updated)
      onComparisonsChange(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setScoringIds((prev) => {
        const next = new Set(prev)
        next.delete(cmpId)
        return next
      })
    }
  }

  const handleScoreAll = async () => {
    const unscored = comparisons.filter((c) => c.score === null)
    if (unscored.length === 0) return
    const marker = new Set(scoringIds)
    unscored.forEach((c) => marker.add(c.id))
    setScoringIds(marker)
    try {
      const updated = [...comparisons]
      for (const c of unscored) {
        const res = await scoreComparison(c.id)
        const idx = updated.findIndex((x) => x.id === c.id)
        if (idx >= 0) updated[idx] = res.comparison
        setComparisons([...updated])
      }
      onComparisonsChange(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setScoringIds(new Set())
    }
  }

  const handleSaveAsTestCase = async (cmpId: string) => {
    setSavingTestCaseIds((prev) => new Set(prev).add(cmpId))
    setSaveMessage(null)
    try {
      const res = await saveComparisonAsTestCase(cmpId, {
        category: 'from_pipeline_studio',
      })
      if (res.test_case) {
        setSaveMessage(`已存為 Eval test case(${res.test_case.id.slice(0, 8)}…)`)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingTestCaseIds((prev) => {
        const next = new Set(prev)
        next.delete(cmpId)
        return next
      })
    }
  }

  const unscoredCount = comparisons.filter((c) => c.score === null).length

  return (
    <div className="space-y-3">
      {/* 模型選擇 + 執行 */}
      <div className="rounded border border-zinc-800 bg-zinc-900/60 p-3">
        <div className="mb-2 text-[11px] uppercase text-zinc-500">
          選擇模型(最多 4 個)
        </div>
        <div className="flex flex-wrap gap-2">
          {candidateModels.length === 0 && (
            <span className="text-[10px] text-zinc-500">載入模型中...</span>
          )}
          {candidateModels.map((m) => {
            const checked = selectedModels.includes(m.id)
            return (
              <button
                key={m.id}
                onClick={() => toggleModel(m.id)}
                title={m.notes || m.id}
                className={`rounded border px-2 py-1 text-[11px] transition-colors ${
                  checked
                    ? 'border-blue-500 bg-blue-950/50 text-blue-200'
                    : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {m.label} <span className="text-[9px] opacity-60">{m.cost}</span>
              </button>
            )
          })}
        </div>
        <button
          onClick={handleRunCompare}
          disabled={running || selectedModels.length === 0}
          className="mt-2 w-full rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500"
        >
          {running
            ? `跑 ${selectedModels.length} 個模型中…`
            : `並行執行 ${selectedModels.length} 個模型`}
        </button>
      </div>

      {error && (
        <div className="rounded border border-red-500/60 bg-red-950/40 p-2 text-[11px] text-red-300">
          {error}
        </div>
      )}
      {saveMessage && (
        <div className="rounded border border-emerald-500/60 bg-emerald-950/40 p-2 text-[11px] text-emerald-300">
          {saveMessage}
        </div>
      )}

      {/* Score all + 候選清單 */}
      {comparisons.length === 0 ? (
        <p className="py-4 text-center text-[11px] text-zinc-500">
          尚未有比較結果。選模型後按「並行執行」。
        </p>
      ) : (
        <>
          {unscoredCount > 0 && (
            <div className="flex items-center justify-between rounded border border-zinc-800 bg-zinc-900/40 px-3 py-2">
              <span className="text-[11px] text-zinc-400">
                {unscoredCount} 個候選尚未評分
              </span>
              <button
                onClick={handleScoreAll}
                disabled={scoringIds.size > 0}
                className="rounded border border-amber-500/60 bg-amber-950/40 px-2 py-1 text-[10px] text-amber-300 hover:bg-amber-900/60 disabled:opacity-50"
              >
                {scoringIds.size > 0 ? '評分中…' : '🧑‍⚖️ 全部評分'}
              </button>
            </div>
          )}

          <div className="space-y-2">
            {comparisons.map((c) => {
              const scoring = scoringIds.has(c.id)
              const savingTC = savingTestCaseIds.has(c.id)
              return (
                <div
                  key={c.id}
                  className={`rounded border p-3 transition-colors ${
                    c.is_selected
                      ? 'border-blue-500/80 bg-blue-950/30'
                      : 'border-zinc-800 bg-zinc-900/40'
                  }`}
                >
                  <div className="mb-1 flex items-center justify-between">
                    <span className="font-mono text-[11px] text-violet-300">
                      {c.model.replace(/-\d{8}$/, '')}
                    </span>
                    <div className="flex items-center gap-2 text-[10px] text-zinc-400">
                      <span>{formatDuration(c.latency_ms)}</span>
                      <span>{formatCost(c.cost_usd)}</span>
                      <span>
                        {c.input_tokens}→{c.output_tokens}
                      </span>
                    </div>
                  </div>

                  {/* Score badge row */}
                  <div className="mb-2 flex items-center gap-2">
                    {c.score !== null ? (
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-mono ${
                          c.score >= 70
                            ? 'bg-emerald-900/60 text-emerald-200'
                            : c.score >= 40
                            ? 'bg-amber-900/60 text-amber-200'
                            : 'bg-red-900/60 text-red-200'
                        }`}
                        title={c.score_reason || ''}
                      >
                        📊 {c.score}/100
                      </span>
                    ) : (
                      <button
                        onClick={() => handleScoreOne(c.id)}
                        disabled={scoring}
                        className="rounded border border-zinc-700 px-1.5 py-0.5 text-[10px] text-zinc-400 hover:bg-zinc-800 disabled:opacity-50"
                      >
                        {scoring ? '評分中…' : '📊 評分'}
                      </button>
                    )}
                    {c.score !== null && c.score_reason && (
                      <span className="truncate text-[10px] italic text-zinc-500">
                        {c.score_reason}
                      </span>
                    )}
                  </div>

                  <pre className="mb-2 max-h-36 overflow-auto whitespace-pre-wrap rounded bg-zinc-950/70 p-2 font-mono text-[11px] text-zinc-200">
                    {c.output_text || '(empty)'}
                  </pre>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => handleSelect(c.id)}
                      disabled={c.is_selected}
                      className={`rounded px-2 py-1 text-[10px] transition-colors ${
                        c.is_selected
                          ? 'cursor-default bg-blue-600 text-white'
                          : 'border border-zinc-700 text-zinc-300 hover:bg-zinc-800'
                      }`}
                    >
                      {c.is_selected ? '✓ 已選用' : '選用'}
                    </button>
                    <button
                      onClick={() => handleSaveAsPrompt(c.id)}
                      disabled={savingId === c.id}
                      className="rounded border border-zinc-700 px-2 py-1 text-[10px] text-zinc-300 hover:bg-zinc-800 disabled:text-zinc-600"
                    >
                      {savingId === c.id ? '儲存中…' : '存為 Prompt'}
                    </button>
                    <button
                      onClick={() => handleSaveAsTestCase(c.id)}
                      disabled={savingTC}
                      className="rounded border border-zinc-700 px-2 py-1 text-[10px] text-zinc-300 hover:bg-zinc-800 disabled:text-zinc-600"
                    >
                      {savingTC ? '儲存中…' : '存為 Test Case'}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

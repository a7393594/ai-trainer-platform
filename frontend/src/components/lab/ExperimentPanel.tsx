'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  labBatchRerun,
  labRerun,
  listAvailableModels,
  saveLabOverrides,
  type ModelInfo,
} from '@/lib/studio/api'
import { useLabStore } from '@/lib/studio/labStore'
import KnowledgeOverridePanel from './KnowledgeOverridePanel'
import ToolsBundlePicker from './ToolsBundlePicker'
import WorkflowStepEditor from './WorkflowStepEditor'
import DemoInputsEditor from './DemoInputsEditor'
import ResultsMatrix from './ResultsMatrix'

type Tab = 'inputs' | 'prompt' | 'tools' | 'knowledge' | 'workflow' | 'results'

interface Props {
  projectId: string
}

export default function ExperimentPanel({ projectId }: Props) {
  const selectedCase = useLabStore((s) => s.selectedCase)
  const labRunId = useLabStore((s) => s.labRunId)
  const setLabRunId = useLabStore((s) => s.setLabRunId)
  const overrides = useLabStore((s) => s.overrides)
  const setOverrides = useLabStore((s) => s.setOverrides)
  const demoInputs = useLabStore((s) => s.demoInputs)
  const history = useLabStore((s) => s.history)
  const appendHistory = useLabStore((s) => s.appendHistory)

  const isWorkflow = selectedCase?.source_type === 'workflow'

  const tabs = useMemo<Array<{ value: Tab; label: string }>>(() => {
    const base: Array<{ value: Tab; label: string }> = [
      { value: 'inputs', label: '輸入' },
      { value: 'prompt', label: 'Prompt' },
      { value: 'tools', label: '工具' },
      { value: 'knowledge', label: '知識庫' },
    ]
    if (isWorkflow) base.push({ value: 'workflow', label: 'Workflow' })
    base.push({ value: 'results', label: `結果 (${history.length})` })
    return base
  }, [isWorkflow, history.length])

  const [tab, setTab] = useState<Tab>('inputs')
  const [models, setModels] = useState<ModelInfo[]>([])
  const [singleInput, setSingleInput] = useState('')
  const [running, setRunning] = useState(false)
  const [batchRunning, setBatchRunning] = useState(false)
  const [savingBundle, setSavingBundle] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listAvailableModels()
      .then(setModels)
      .catch(() => setModels([]))
  }, [])

  const canRun = !!selectedCase
  const effectiveInput = singleInput.trim()

  const handleRun = async () => {
    if (!selectedCase) return
    setRunning(true)
    setError(null)
    try {
      const res = await labRerun({
        source_type: selectedCase.source_type,
        source_id: selectedCase.id,
        input: effectiveInput || undefined,
        overrides,
        lab_run_id: labRunId || undefined,
      })
      setLabRunId(res.lab_run_id)
      appendHistory({
        input: effectiveInput || selectedCase.title,
        result: res.result,
      })
      setTab('results')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  const handleBatchRun = async () => {
    if (!selectedCase || demoInputs.length === 0) return
    setBatchRunning(true)
    setError(null)
    try {
      const res = await labBatchRerun({
        source_type: selectedCase.source_type,
        source_id: selectedCase.id,
        inputs: demoInputs,
        overrides,
        lab_run_id: labRunId || undefined,
      })
      setLabRunId(res.lab_run_id)
      res.results.forEach((r, i) => {
        appendHistory({ input: demoInputs[i], result: r })
      })
      setTab('results')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBatchRunning(false)
    }
  }

  const handleSaveBundle = async () => {
    if (!labRunId) {
      setError('尚未建立 lab run — 先跑一次再保存')
      return
    }
    setSavingBundle(true)
    setError(null)
    try {
      await saveLabOverrides(labRunId, { overrides, demo_inputs: demoInputs })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingBundle(false)
    }
  }

  if (!selectedCase) {
    return (
      <aside className="flex h-full w-[400px] flex-shrink-0 flex-col items-center justify-center border-l border-zinc-800 bg-zinc-950/60 p-6 text-center text-xs text-zinc-500">
        <p>← 左側挑一個過往案例,在這裡編輯 prompt / tools / 知識庫後重跑</p>
      </aside>
    )
  }

  return (
    <aside className="flex h-full w-[420px] flex-shrink-0 flex-col border-l border-zinc-800 bg-zinc-950/60">
      <div className="border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-zinc-100">實驗設定</h3>
          <button
            onClick={handleSaveBundle}
            disabled={savingBundle || !labRunId}
            className="rounded border border-zinc-700 px-2 py-1 text-[10px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
            title={labRunId ? '將 overrides 存入此 lab run' : '尚未建立 lab run'}
          >
            {savingBundle ? '儲存中…' : '💾 保存設定'}
          </button>
        </div>
        <p className="mt-1 truncate text-[10px] text-zinc-500">
          {selectedCase.source_type}#{selectedCase.id.slice(0, 8)} · {selectedCase.title}
        </p>
      </div>

      <div className="flex overflow-x-auto border-b border-zinc-800 px-2">
        {tabs.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={`whitespace-nowrap border-b-2 px-3 py-2 text-[11px] transition-colors ${
              tab === t.value
                ? 'border-blue-500 text-blue-300'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4 text-xs text-zinc-200">
        {tab === 'inputs' && (
          <div className="space-y-3">
            <label className="block text-[11px] text-zinc-400">
              單一問題（留空則用案例原始 input）
            </label>
            <textarea
              value={singleInput}
              onChange={(e) => setSingleInput(e.target.value)}
              rows={6}
              placeholder={selectedCase.title}
              className="w-full rounded border border-zinc-700 bg-zinc-900 p-2 text-xs text-zinc-100 placeholder-zinc-500 focus:border-blue-500 focus:outline-none"
            />
            <div className="border-t border-zinc-800 pt-3">
              <label className="mb-1 block text-[11px] text-zinc-400">
                批次示範問題（可加多組輸入並行跑）
              </label>
              <DemoInputsEditor />
            </div>
          </div>
        )}

        {tab === 'prompt' && (
          <div className="space-y-3">
            <label className="block text-[11px] text-zinc-400">
              System prompt 覆寫（留空則用專案 active prompt）
            </label>
            <textarea
              value={overrides.prompt_override || ''}
              onChange={(e) =>
                setOverrides({ prompt_override: e.target.value || undefined })
              }
              rows={10}
              placeholder="You are a helpful assistant..."
              className="w-full rounded border border-zinc-700 bg-zinc-900 p-2 text-xs text-zinc-100 placeholder-zinc-500 focus:border-blue-500 focus:outline-none"
            />
            <label className="mt-3 block text-[11px] text-zinc-400">
              Model 覆寫
            </label>
            <select
              value={overrides.model_override || ''}
              onChange={(e) =>
                setOverrides({ model_override: e.target.value || undefined })
              }
              className="w-full rounded border border-zinc-700 bg-zinc-900 p-2 text-xs text-zinc-100 focus:border-blue-500 focus:outline-none"
            >
              <option value="">（沿用專案預設）</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label} ({m.provider})
                </option>
              ))}
            </select>
          </div>
        )}

        {tab === 'tools' && <ToolsBundlePicker projectId={projectId} />}

        {tab === 'knowledge' && <KnowledgeOverridePanel projectId={projectId} />}

        {tab === 'workflow' && isWorkflow && (
          <WorkflowStepEditor sourceId={selectedCase.id} />
        )}

        {tab === 'results' && <ResultsMatrix />}
      </div>

      {error && (
        <div className="border-t border-red-500/40 bg-red-950/30 px-4 py-2 text-[11px] text-red-300">
          {error}
        </div>
      )}

      <div className="flex gap-2 border-t border-zinc-800 bg-zinc-950 p-3">
        <button
          onClick={handleRun}
          disabled={running || !canRun}
          className="flex-1 rounded bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40"
        >
          {running ? '執行中…' : '▶ Run'}
        </button>
        <button
          onClick={handleBatchRun}
          disabled={batchRunning || demoInputs.length === 0 || !canRun}
          className="flex-1 rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
          title={demoInputs.length ? `並行跑 ${demoInputs.length} 組示範問題` : '先在「輸入」頁加示範問題'}
        >
          {batchRunning
            ? '批次執行中…'
            : `⚡ Batch Run (${demoInputs.length})`}
        </button>
      </div>
    </aside>
  )
}

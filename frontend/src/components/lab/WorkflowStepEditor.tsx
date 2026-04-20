'use client'

import { useEffect, useState } from 'react'
import { useLabStore } from '@/lib/studio/labStore'

const AI_ENGINE_URL =
  process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

interface Props {
  sourceId: string // workflow_run_id
}

interface WorkflowRunRow {
  id: string
  workflow_id: string
  context_json?: Record<string, unknown> | null
}

/**
 * Minimal JSON editor for workflow steps_override. For MVP we expose the raw
 * JSON array of step objects — engine already supports if/parallel/loop types.
 * A visual tree editor can be layered on later without changing the store
 * contract (stores as list[dict]).
 */
export default function WorkflowStepEditor({ sourceId }: Props) {
  const overrides = useLabStore((s) => s.overrides)
  const setOverrides = useLabStore((s) => s.setOverrides)

  const [raw, setRaw] = useState<string>('')
  const [loadedOriginal, setLoadedOriginal] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [parseErr, setParseErr] = useState<string | null>(null)

  // Load original workflow steps once for reference / starter
  useEffect(() => {
    if (loadedOriginal) return
    const load = async () => {
      try {
        const runRes = await fetch(
          `${AI_ENGINE_URL}/api/v1/workflows/runs/${sourceId}`
        )
        if (!runRes.ok) throw new Error(`run fetch ${runRes.status}`)
        const run: WorkflowRunRow = await runRes.json()
        const wfRes = await fetch(
          `${AI_ENGINE_URL}/api/v1/workflows/detail/${run.workflow_id}`
        )
        if (!wfRes.ok) throw new Error(`wf fetch ${wfRes.status}`)
        const wfData = await wfRes.json()
        const steps = wfData.workflow?.steps_json ?? wfData.steps_json ?? []
        setRaw(JSON.stringify(steps, null, 2))
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoadedOriginal(true)
      }
    }
    load()
  }, [sourceId, loadedOriginal])

  // Keep store in sync with parseable JSON
  useEffect(() => {
    if (!raw.trim()) {
      setParseErr(null)
      if (overrides.workflow_steps_override) {
        setOverrides({ workflow_steps_override: undefined })
      }
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) {
        setParseErr('steps 必須是 array')
        return
      }
      setParseErr(null)
      setOverrides({ workflow_steps_override: parsed })
    } catch (e) {
      setParseErr(e instanceof Error ? e.message : String(e))
    }
  }, [raw, setOverrides])
  // eslint-disable-next-line react-hooks/exhaustive-deps — overrides.workflow_steps_override read only for clearing

  return (
    <div className="space-y-2">
      <p className="text-[11px] text-zinc-400">
        編輯下方 JSON 可覆寫此 workflow rerun 時的 steps。支援 if / parallel / loop 類型（engine 原生）。留空則沿用原 workflow 定義。
      </p>
      {error && <p className="text-[10px] text-red-400">載入原始 steps 失敗: {error}</p>}
      {parseErr && <p className="text-[10px] text-amber-400">JSON 錯誤: {parseErr}</p>}
      <textarea
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        rows={18}
        className="w-full rounded border border-zinc-700 bg-zinc-900 p-2 font-mono text-[11px] text-zinc-100 focus:border-blue-500 focus:outline-none"
        spellCheck={false}
      />
      <div className="flex gap-2">
        <button
          onClick={() => setRaw('')}
          className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-[10px] text-zinc-300 hover:bg-zinc-800"
        >
          清除（回到原始 workflow）
        </button>
      </div>
    </div>
  )
}

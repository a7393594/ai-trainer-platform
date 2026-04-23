'use client'

/**
 * /dag-compare — A/B 並排測試兩個 DAG
 *
 * 選 DAG A + DAG B + 輸入 N 個測試 prompt，並排跑出結果比較：
 * - 每個 input 顯示 A / B 兩側回應
 * - tokens、latency、成本、模型
 * - 手動標記「A 比較好」/「B 比較好」/「平手」
 */

import { useEffect, useState } from 'react'
import { useProject } from '@/lib/project-context'
import { listDags, compareDags, type PipelineDAG, type ABCompareResult } from '@/lib/studio/api'

type Verdict = 'a' | 'b' | 'tie' | null

export default function DAGComparePage() {
  const { currentProject } = useProject()
  const projectId = currentProject?.project_id

  const [dags, setDags] = useState<PipelineDAG[]>([])
  const [dagAId, setDagAId] = useState<string>('')
  const [dagBId, setDagBId] = useState<string>('')
  const [testInputs, setTestInputs] = useState<string>('翻前 BTN 拿 AKs 該加注還是 limp？\nK72 rainbow flop 我有 AK，對手 check，我該 c-bet 嗎？')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<ABCompareResult | null>(null)
  const [verdicts, setVerdicts] = useState<Record<number, Verdict>>({})
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId) return
    listDags(projectId).then((r) => {
      setDags(r.dags || [])
      if (r.dags && r.dags.length >= 2) {
        setDagAId(r.dags[0].id)
        setDagBId(r.dags[1].id)
      } else if (r.dags?.[0]) {
        setDagAId(r.dags[0].id)
      }
    }).catch(() => {})
  }, [projectId])

  const handleRun = async () => {
    if (!dagAId || !dagBId) { setError('請選擇兩個 DAG'); return }
    if (dagAId === dagBId) { setError('DAG A 與 B 不能相同'); return }
    const inputs = testInputs.split('\n').map((s) => s.trim()).filter(Boolean)
    if (inputs.length === 0) { setError('請輸入至少一個測試 prompt'); return }
    setRunning(true)
    setError(null)
    setVerdicts({})
    try {
      const res = await compareDags(dagAId, dagBId, inputs)
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : '執行失敗')
    }
    setRunning(false)
  }

  const verdictSummary = () => {
    const counts = { a: 0, b: 0, tie: 0, unjudged: 0 }
    if (!result) return counts
    for (let i = 0; i < result.results.length; i++) {
      const v = verdicts[i]
      if (v === 'a') counts.a++
      else if (v === 'b') counts.b++
      else if (v === 'tie') counts.tie++
      else counts.unjudged++
    }
    return counts
  }

  if (!projectId) {
    return <div className="p-6 text-sm text-zinc-500">尚未選擇專案</div>
  }

  if (dags.length < 2) {
    return (
      <div className="p-6">
        <p className="text-sm text-zinc-400">此專案需要至少 2 個 DAG 版本才能比較。</p>
        <p className="text-xs text-zinc-500 mt-2">
          請到 <a href="/dag-editor" className="text-blue-400 hover:underline">DAG 編輯器</a> 建立新版本。
        </p>
      </div>
    )
  }

  const summary = verdictSummary()

  return (
    <div className="h-full overflow-y-auto bg-zinc-900 p-4">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">DAG A/B 比較</h1>
        <p className="text-xs text-zinc-500 mb-4">
          用同一批 input 並排跑兩個 DAG，手動評比哪個表現較好。
        </p>

        {/* Control panel */}
        <div className="rounded border border-zinc-700 bg-zinc-800/40 p-4 mb-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] uppercase text-zinc-500 mb-1">DAG A</label>
              <select
                value={dagAId}
                onChange={(e) => setDagAId(e.target.value)}
                className="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-200"
              >
                {dags.map((d) => (
                  <option key={d.id} value={d.id}>v{d.version} · {d.name} {d.is_active ? '✓' : ''}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[10px] uppercase text-zinc-500 mb-1">DAG B</label>
              <select
                value={dagBId}
                onChange={(e) => setDagBId(e.target.value)}
                className="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-200"
              >
                {dags.map((d) => (
                  <option key={d.id} value={d.id}>v{d.version} · {d.name} {d.is_active ? '✓' : ''}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-[10px] uppercase text-zinc-500 mb-1">
              測試 Input（每行一筆）
            </label>
            <textarea
              value={testInputs}
              onChange={(e) => setTestInputs(e.target.value)}
              rows={4}
              className="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-blue-500 font-mono"
            />
            <p className="text-[10px] text-zinc-500 mt-1">
              {testInputs.split('\n').filter((s) => s.trim()).length} 筆輸入
            </p>
          </div>

          {error && <p className="text-xs text-red-400">{error}</p>}

          <button
            onClick={handleRun}
            disabled={running}
            className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {running ? `執行中... (${testInputs.split('\n').filter((s) => s.trim()).length} 筆 × 2 模型)` : '▶ 開始比較'}
          </button>
        </div>

        {/* Results */}
        {result && (
          <div className="space-y-3">
            {/* Summary */}
            <div className="rounded border border-zinc-700 bg-zinc-800/40 p-3 flex items-center gap-4 flex-wrap">
              <span className="text-xs text-zinc-400">評比結果：</span>
              <span className="text-xs">
                <span className="text-blue-400 font-semibold">A 勝 {summary.a}</span>
                <span className="text-zinc-500"> / </span>
                <span className="text-emerald-400 font-semibold">B 勝 {summary.b}</span>
                <span className="text-zinc-500"> / </span>
                <span className="text-zinc-400">平手 {summary.tie}</span>
                {summary.unjudged > 0 && (
                  <>
                    <span className="text-zinc-500"> / </span>
                    <span className="text-zinc-500">未評 {summary.unjudged}</span>
                  </>
                )}
              </span>
              <div className="flex-1" />
              <span className="text-[10px] text-zinc-500">
                A: v{result.dag_a.version} ({result.dag_a.name}) · B: v{result.dag_b.version} ({result.dag_b.name})
              </span>
            </div>

            {/* Per-input rows */}
            {result.results.map((row, i) => (
              <div key={i} className="rounded border border-zinc-700 bg-zinc-800/40 p-3">
                <div className="mb-2 flex items-start gap-2">
                  <span className="text-[10px] text-zinc-500 shrink-0 mt-0.5">Input #{i + 1}</span>
                  <p className="text-xs text-zinc-300 flex-1 font-mono">{row.input}</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {/* A side */}
                  <div className={`rounded border p-2 ${verdicts[i] === 'a' ? 'border-blue-500 bg-blue-500/10' : 'border-zinc-700 bg-zinc-900/50'}`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] uppercase text-blue-400">A</span>
                      <span className="text-[9px] text-zinc-500 font-mono">{row.a.model}</span>
                    </div>
                    {row.a.error ? (
                      <p className="text-[10px] text-red-400">Error: {row.a.error}</p>
                    ) : (
                      <pre className="text-[11px] text-zinc-200 whitespace-pre-wrap max-h-48 overflow-y-auto">{row.a.output}</pre>
                    )}
                    <div className="mt-1 flex gap-3 text-[9px] text-zinc-500">
                      <span>in: {row.a.tokens_in}</span>
                      <span>out: {row.a.tokens_out}</span>
                      <span>{row.a.latency_ms}ms</span>
                    </div>
                  </div>

                  {/* B side */}
                  <div className={`rounded border p-2 ${verdicts[i] === 'b' ? 'border-emerald-500 bg-emerald-500/10' : 'border-zinc-700 bg-zinc-900/50'}`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] uppercase text-emerald-400">B</span>
                      <span className="text-[9px] text-zinc-500 font-mono">{row.b.model}</span>
                    </div>
                    {row.b.error ? (
                      <p className="text-[10px] text-red-400">Error: {row.b.error}</p>
                    ) : (
                      <pre className="text-[11px] text-zinc-200 whitespace-pre-wrap max-h-48 overflow-y-auto">{row.b.output}</pre>
                    )}
                    <div className="mt-1 flex gap-3 text-[9px] text-zinc-500">
                      <span>in: {row.b.tokens_in}</span>
                      <span>out: {row.b.tokens_out}</span>
                      <span>{row.b.latency_ms}ms</span>
                    </div>
                  </div>
                </div>

                {/* Verdict buttons */}
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() => setVerdicts((v) => ({ ...v, [i]: 'a' }))}
                    className={`flex-1 rounded px-3 py-1 text-xs ${
                      verdicts[i] === 'a' ? 'bg-blue-600 text-white' : 'border border-zinc-700 text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    A 較好
                  </button>
                  <button
                    onClick={() => setVerdicts((v) => ({ ...v, [i]: 'tie' }))}
                    className={`flex-1 rounded px-3 py-1 text-xs ${
                      verdicts[i] === 'tie' ? 'bg-zinc-600 text-white' : 'border border-zinc-700 text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    平手
                  </button>
                  <button
                    onClick={() => setVerdicts((v) => ({ ...v, [i]: 'b' }))}
                    className={`flex-1 rounded px-3 py-1 text-xs ${
                      verdicts[i] === 'b' ? 'bg-emerald-600 text-white' : 'border border-zinc-700 text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    B 較好
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

'use client'

import { useEffect, useState } from 'react'
import { useProject } from '@/lib/project-context'
import { listDags, compareDags, type PipelineDAG, type ABCompareResult, type ABTraceEntry, type ABSideResult } from '@/lib/studio/api'

type Verdict = 'a' | 'b' | 'tie' | null

// ── Model pricing (USD per 1M tokens) ──────────────────────────────────────
const MODEL_PRICING: Record<string, { in: number; out: number }> = {
  'claude-haiku-4-5-20251001': { in: 0.25, out: 1.25 },
  'claude-haiku-4-5': { in: 0.25, out: 1.25 },
  'claude-haiku-3-5': { in: 0.8, out: 4.0 },
  'claude-sonnet-4-20250514': { in: 3.0, out: 15.0 },
  'claude-sonnet-4-6': { in: 3.0, out: 15.0 },
  'claude-sonnet-3-7': { in: 3.0, out: 15.0 },
  'claude-opus-4-7': { in: 15.0, out: 75.0 },
  'gpt-4o': { in: 2.5, out: 10.0 },
  'gpt-4o-mini': { in: 0.15, out: 0.6 },
  'gemini-1.5-pro': { in: 1.25, out: 5.0 },
  'gemini-1.5-flash': { in: 0.075, out: 0.3 },
}

function calcCost(model: string, tokensIn: number, tokensOut: number): number {
  const key = Object.keys(MODEL_PRICING).find((k) => model.includes(k)) ?? ''
  const p = MODEL_PRICING[key]
  if (!p) return 0
  return (tokensIn * p.in + tokensOut * p.out) / 1_000_000
}

// ── Status badge ───────────────────────────────────────────────────────────
function StatusBadge({ status }: { status: string }) {
  if (status === 'ok') return <span className="text-[9px] rounded px-1 bg-emerald-900/60 text-emerald-400">ok</span>
  if (status === 'skipped') return <span className="text-[9px] rounded px-1 bg-zinc-800 text-zinc-500">skip</span>
  return <span className="text-[9px] rounded px-1 bg-red-900/60 text-red-400">err</span>
}

// ── Trace panel ───────────────────────────────────────────────────────────
function TracePanel({ trace }: { trace: ABTraceEntry[] }) {
  const [open, setOpen] = useState(false)
  if (!trace || trace.length === 0) return null
  const totalMs = trace.reduce((s, t) => s + (t.latency_ms || 0), 0)
  return (
    <div className="mt-2 border border-zinc-700/60 rounded">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-2 py-1 text-[10px] text-zinc-400 hover:text-zinc-200"
      >
        <span>{open ? '▾' : '▸'} 執行過程 ({trace.length} 個節點)</span>
        <span className="text-zinc-500">{totalMs}ms 總計</span>
      </button>
      {open && (
        <div className="border-t border-zinc-700/60 px-2 py-1 space-y-0.5 max-h-64 overflow-y-auto">
          {trace.map((t, i) => (
            <div key={i} className="flex items-start gap-2 py-0.5">
              <StatusBadge status={t.status} />
              <span className="text-[10px] text-zinc-400 shrink-0 w-28 truncate" title={t.label}>{t.label || t.type_key}</span>
              <span className="text-[10px] text-zinc-300 flex-1 min-w-0 truncate" title={t.summary}>{t.summary}</span>
              <span className="text-[9px] text-zinc-500 shrink-0">
                {t.latency_ms > 0 ? `${t.latency_ms}ms` : '—'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Side panel (A or B) ───────────────────────────────────────────────────
function SidePanel({
  side,
  data,
  highlighted,
}: {
  side: 'A' | 'B'
  data: ABSideResult
  highlighted: boolean
}) {
  const cost = calcCost(data.model, data.tokens_in, data.tokens_out)
  const borderCls = highlighted
    ? side === 'A' ? 'border-blue-500 bg-blue-500/10' : 'border-emerald-500 bg-emerald-500/10'
    : 'border-zinc-700 bg-zinc-900/50'
  const labelCls = side === 'A' ? 'text-blue-400' : 'text-emerald-400'

  return (
    <div className={`rounded border p-2 flex flex-col gap-1 ${borderCls}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className={`text-[10px] uppercase font-semibold ${labelCls}`}>{side}</span>
        <span className="text-[9px] text-zinc-500 font-mono truncate max-w-[160px]" title={data.model}>{data.model}</span>
      </div>

      {/* Output */}
      {data.error ? (
        <p className="text-[10px] text-red-400">Error: {data.error}</p>
      ) : (
        <pre className="text-[11px] text-zinc-200 whitespace-pre-wrap max-h-48 overflow-y-auto">{data.output}</pre>
      )}

      {/* Stats row */}
      <div className="flex items-center gap-3 flex-wrap mt-1">
        <span className="text-[9px] text-zinc-500">in: {data.tokens_in.toLocaleString()}</span>
        <span className="text-[9px] text-zinc-500">out: {data.tokens_out.toLocaleString()}</span>
        <span className="text-[9px] text-zinc-500">{data.latency_ms}ms</span>
        {cost > 0 && (
          <span className="text-[9px] font-mono text-amber-400 ml-auto">
            ${cost < 0.0001 ? cost.toExponential(2) : cost.toFixed(4)}
          </span>
        )}
      </div>

      {/* Trace */}
      <TracePanel trace={data.trace || []} />
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────
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
            {/* Summary bar */}
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
              {/* Aggregate cost */}
              {result.results.length > 0 && (() => {
                const totalA = result.results.reduce((s, r) => s + calcCost(r.a.model, r.a.tokens_in, r.a.tokens_out), 0)
                const totalB = result.results.reduce((s, r) => s + calcCost(r.b.model, r.b.tokens_in, r.b.tokens_out), 0)
                if (totalA === 0 && totalB === 0) return null
                return (
                  <span className="text-[10px] text-zinc-400">
                    總成本 A: <span className="text-amber-400">${totalA.toFixed(4)}</span>
                    {' / '}B: <span className="text-amber-400">${totalB.toFixed(4)}</span>
                  </span>
                )
              })()}
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
                  <SidePanel side="A" data={row.a} highlighted={verdicts[i] === 'a'} />
                  <SidePanel side="B" data={row.b} highlighted={verdicts[i] === 'b'} />
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

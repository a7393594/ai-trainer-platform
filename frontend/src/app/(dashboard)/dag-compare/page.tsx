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

// ── Node type metadata: 用途 + 作動方式 ────────────────────────────────────
interface NodeInfo { purpose: string; behavior: string; fieldHints?: Record<string, string> }
const NODE_TYPE_INFO: Record<string, NodeInfo> = {
  user_input: {
    purpose: '接收使用者訊息，把原始 input 放入執行上下文。',
    behavior: '從請求參數讀 user_message，長度、字數就在此紀錄。後續所有節點都從 ctx.user_message 取用。',
  },
  load_history: {
    purpose: '從資料庫載入歷史對話訊息，組成上下文一部分。',
    behavior: '預設從 session_id 往前抓最近 20 則訊息；測試模式（DAG 測試）會跳過不連資料庫。',
  },
  triage: {
    purpose: '意圖分類（關鍵字規則版），判斷使用者訊息屬於一般對話、capability rule、或進行中 workflow。',
    behavior: '用固定關鍵字 + 正則掃 user_message，比對 project 的 capability rules；設定在 ctx.intent_type / ctx.intent_rule。',
  },
  triage_llm: {
    purpose: '意圖分類（LLM 版），用便宜模型判斷該不該走某個 capability rule。',
    behavior: '列出所有 project capability rules 給分類器，要求輸出 `{"type":"general"}` 或 `{"type":"capability_rule","rule_index":N}`。失敗降級到 keyword 分類。',
    fieldHints: {
      intent_type: '最終分類結果：general / capability_rule / active_workflow',
      matched: '若為 capability_rule，對應的規則描述',
      action_type: 'capability_rule 的處理動作（tool_call / workflow / handoff / widget）',
      model_used: '實際用的分類模型',
    },
  },
  capability_tool_call: {
    purpose: 'Capability rule 走 tool_call 動作 — 直接呼叫預設工具組。',
    behavior: 'condition 要求 intent_type=capability_rule AND action_type=tool_call 才執行；跳過就是條件不符。',
  },
  capability_workflow: {
    purpose: 'Capability rule 走 workflow 動作 — 啟動一個 workflow 模板。',
    behavior: 'condition 要求 action_type=workflow；啟動後 ctx.intent_type 會變成 active_workflow。',
  },
  capability_handoff: {
    purpose: 'Capability rule 走 handoff 動作 — 轉交給真人或特定 agent。',
    behavior: 'condition 要求 action_type=handoff；寫入 handoff 訊息到輸出。',
  },
  capability_widget: {
    purpose: 'Capability rule 走 widget 動作 — 回傳預定義 widget + 可選的 LLM 文字回覆。',
    behavior: 'condition 要求 action_type=widget。',
  },
  workflow_continue: {
    purpose: '若目前 session 正在跑 workflow，繼續下一步。',
    behavior: 'condition 要求 intent_type=active_workflow 才執行。',
  },
  load_knowledge: {
    purpose: 'RAG 檢索 — 找與 user_message 相關的知識片段。',
    behavior: '優先走 Qdrant 向量搜尋，失敗 fallback 到 pgvector 再 fallback 到 keyword；結果寫到 ctx.rag_context。',
    fieldHints: {
      chunk_count: '取回的片段數量',
      total_chars: 'RAG 內容字數',
      rag_preview: '前 1000 字預覽（完整內容會帶進 prompt）',
      query: '實際做搜尋的查詢字串',
    },
  },
  compose_prompt: {
    purpose: '把 system prompt 前綴 + project active prompt + WIDGET_INSTRUCTION 組合；組完後連同 RAG、history、user message 形成 ctx.messages。',
    behavior: '讀 active prompt（A/B 變體感知）；若 config.system_prompt_prefix 有值會插在最前面。',
    fieldHints: {
      message_count: '最終訊息陣列長度（system + rag + history + user）',
      system_prompt_length: 'system prompt 字數',
      system_prompt_preview: 'system prompt 前 1500 字',
      has_rag: '是否有 RAG 內容',
      has_prefix: '是否設了 prefix',
      history_count: '歷史訊息數',
      user_message: '原始使用者問題',
    },
  },
  call_model: {
    purpose: '主模型呼叫 — 執行 tool_loop 或 plan_and_execute（若啟用）。',
    behavior: 'planning_mode=false 時走傳統迴圈：模型決定呼叫工具、執行、回塞結果、再問。最多 max_iterations 輪。若耗盡仍無文字 → 三層合成（L1 tool_choice=none / L2 乾淨上下文 / L3 工具結果純文字）。planning_mode=true 時改用 planner 一次列全部 tool、平行執行、合成。',
    fieldHints: {
      model: '主模型（tool_loop 用）',
      synthesis_model: '合成階段用的模型（可與主模型不同，例如 Haiku）',
      planner_model: 'planning_mode 下的規劃模型',
      planning_mode: '啟用 plan-and-execute 架構（省 ~80% 成本）',
      max_iterations: 'tool_loop 最多迭代次數（達到後進入合成）',
      iterations: '實際跑的 iteration 次數',
      tool_calls_total: '執行的 tool_call 總數',
      synthesis_layer: '實際觸發的合成層（L1/L2/L3 或空 = 模型自然返回文字）',
      iteration_details: '每輪詳細：phase / tokens / latency / finish_reason',
    },
  },
  execute_tools: {
    purpose: '顯示 call_model 節點內已執行的工具結果（不另外執行工具）。',
    behavior: '讀 ctx.tool_results 彙整；實際執行是在 call_model 裡同步發生。',
    fieldHints: {
      iterations: 'call_model 走了幾輪',
      total_calls: '工具呼叫總數',
      results: '每次呼叫的 params / result / status 完整紀錄',
    },
  },
  parse_widget: {
    purpose: '從主模型回應抽取 widget 標記，分離出純文字答覆。',
    behavior: '正則找 `<!--WIDGET:{json}-->`，JSON 放 ctx.widgets，剩下 text 放 ctx.clean_text。',
    fieldHints: {
      widget_count: '抽出的 widget 數量',
      clean_length: '移掉 widget 標記後的文字字數',
      raw_length: '原始 llm_response_text 字數',
      clean_preview: 'clean_text 前 500 字',
    },
  },
  guardrail: {
    purpose: '禁用詞檢查；觸發後可選擇警告、阻擋、或重試。',
    behavior: '對 ctx.llm_response_text 做不分大小寫的子字串比對；action=block 時覆寫回應為固定字串。',
  },
  retry: {
    purpose: '標記前一節點若失敗要重試（MVP 尚未接入實際重試邏輯）。',
    behavior: 'config 讀 max_retries / backoff_ms，但目前 DAG executor 未支援真正重試。',
  },
  output: {
    purpose: '組最終輸出；生產模式會寫 ait_training_messages。',
    behavior: 'final_text = ctx.clean_text || ctx.llm_response_text。metadata 帶 widgets / tool_results。測試模式不落庫。',
    fieldHints: {
      final_text_length: '輸出字數',
      final_text_preview: '前 1000 字預覽',
      widget_count: 'metadata 裡的 widget 數',
      total_tokens_in: '整條 pipeline 累積輸入 tokens',
      total_tokens_out: '整條 pipeline 累積輸出 tokens',
      tool_call_count: '整條 pipeline 的工具呼叫數',
      assistant_message_id: '若有落庫，對應的 message id',
    },
  },
}

function NodeTypeInfoBlock({ typeKey }: { typeKey: string }) {
  const info = NODE_TYPE_INFO[typeKey]
  if (!info) return null
  return (
    <div className="mb-2 p-2 rounded bg-blue-950/20 border border-blue-900/40 space-y-1">
      <div>
        <span className="text-[9px] uppercase text-blue-400 font-semibold">用途</span>
        <p className="text-[10px] text-zinc-300 leading-relaxed">{info.purpose}</p>
      </div>
      <div>
        <span className="text-[9px] uppercase text-blue-400 font-semibold">作動方式</span>
        <p className="text-[10px] text-zinc-300 leading-relaxed">{info.behavior}</p>
      </div>
    </div>
  )
}

// ── Per-node detail view ──────────────────────────────────────────────────
function IterationTable({ iters }: { iters: Array<Record<string, unknown>> }) {
  return (
    <div className="mt-1 overflow-x-auto">
      <table className="text-[9px] w-full border-collapse">
        <thead>
          <tr className="text-zinc-500 border-b border-zinc-700/60">
            <th className="text-left px-1 py-0.5">#</th>
            <th className="text-left px-1 py-0.5">phase</th>
            <th className="text-right px-1 py-0.5">in</th>
            <th className="text-right px-1 py-0.5">out</th>
            <th className="text-right px-1 py-0.5">ms</th>
            <th className="text-left px-1 py-0.5">finish</th>
            <th className="text-left px-1 py-0.5">tools/text</th>
          </tr>
        </thead>
        <tbody>
          {iters.map((it, i) => {
            const tools = (it.tool_calls as Array<{ name: string; arguments?: string }> | undefined) || []
            const preview = (it.text_preview as string | undefined) || ''
            const toolsDisplay = tools.length > 0
              ? tools.map((t) => t.name).join(', ')
              : preview.slice(0, 80) + (preview.length > 80 ? '…' : '')
            return (
              <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                <td className="px-1 py-0.5 text-zinc-400">{String(it.iter)}</td>
                <td className="px-1 py-0.5 font-mono text-zinc-300">{String(it.phase)}</td>
                <td className="px-1 py-0.5 text-right text-zinc-400">{String(it.tokens_in || 0)}</td>
                <td className="px-1 py-0.5 text-right text-zinc-400">{String(it.tokens_out || 0)}</td>
                <td className="px-1 py-0.5 text-right text-zinc-500">{String(it.latency_ms || 0)}</td>
                <td className="px-1 py-0.5 text-zinc-500">{String(it.finish_reason || '')}</td>
                <td className="px-1 py-0.5 text-zinc-300 truncate max-w-[180px]" title={toolsDisplay}>{toolsDisplay}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ToolResultList({ results }: { results: Array<Record<string, unknown>> }) {
  return (
    <div className="mt-1 space-y-1">
      {results.map((tr, i) => (
        <div key={i} className="border border-zinc-700/40 rounded px-1 py-0.5 bg-zinc-950/40">
          <div className="flex items-center gap-2">
            <span className={`text-[9px] rounded px-1 ${tr.status === 'ok' ? 'bg-emerald-900/60 text-emerald-400' : 'bg-red-900/60 text-red-400'}`}>
              {String(tr.status)}
            </span>
            <span className="text-[10px] font-mono text-zinc-200">{String(tr.name)}</span>
            <span className="text-[9px] text-zinc-500">iter {String(tr.iteration)}</span>
          </div>
          <details className="mt-0.5">
            <summary className="text-[9px] text-zinc-500 cursor-pointer">params / result</summary>
            <pre className="text-[9px] text-zinc-400 whitespace-pre-wrap mt-0.5">
              params: {JSON.stringify(tr.params, null, 2)}
              {'\n'}result: {JSON.stringify(tr.result, null, 2).slice(0, 1200)}
            </pre>
          </details>
        </div>
      ))}
    </div>
  )
}

function FieldLabel({ fieldKey, hints }: { fieldKey: string; hints?: Record<string, string> }) {
  const hint = hints?.[fieldKey]
  return (
    <span className="text-[9px] text-zinc-500" title={hint || fieldKey}>
      {fieldKey}
      {hint && <span className="ml-1 text-zinc-600">— {hint}</span>}
      ：
    </span>
  )
}

function NodeDetail({ output, typeKey }: { output: Record<string, unknown>; typeKey?: string }) {
  const info = typeKey ? NODE_TYPE_INFO[typeKey] : undefined
  const fieldHints = info?.fieldHints
  if (!output || Object.keys(output).length === 0) {
    return (
      <div>
        {typeKey && <NodeTypeInfoBlock typeKey={typeKey} />}
        <div className="text-[9px] text-zinc-500 italic">此節點未輸出執行資料（可能被 skip 或是純中繼）。</div>
      </div>
    )
  }
  const entries = Object.entries(output)
  return (
    <div>
      {typeKey && <NodeTypeInfoBlock typeKey={typeKey} />}
      <div className="mb-1">
        <span className="text-[9px] uppercase text-emerald-400 font-semibold">目前執行內容</span>
      </div>
      <div className="space-y-1 text-[10px]">
      {entries.map(([key, value]) => {
        // Special renderings
        if (key === 'iteration_details' && Array.isArray(value)) {
          return (
            <div key={key}>
              <FieldLabel fieldKey={key} hints={fieldHints} />
              <IterationTable iters={value as Array<Record<string, unknown>>} />
            </div>
          )
        }
        if (key === 'results' && Array.isArray(value)) {
          return (
            <div key={key}>
              <FieldLabel fieldKey={key} hints={fieldHints} />
              <ToolResultList results={value as Array<Record<string, unknown>>} />
            </div>
          )
        }
        // Long string → pre-wrap
        if (typeof value === 'string' && value.length > 80) {
          return (
            <div key={key}>
              <FieldLabel fieldKey={key} hints={fieldHints} />
              <pre className="text-[10px] text-zinc-300 whitespace-pre-wrap bg-zinc-950/40 border border-zinc-700/40 rounded p-1 max-h-40 overflow-y-auto">{value}</pre>
            </div>
          )
        }
        // Objects/arrays → json
        if (typeof value === 'object' && value !== null) {
          return (
            <div key={key}>
              <FieldLabel fieldKey={key} hints={fieldHints} />
              <pre className="text-[9px] text-zinc-400 whitespace-pre-wrap bg-zinc-950/40 border border-zinc-700/40 rounded p-1 max-h-40 overflow-y-auto">{JSON.stringify(value, null, 2)}</pre>
            </div>
          )
        }
        // Scalar → inline
        return (
          <div key={key} className="flex gap-2 items-baseline">
            <FieldLabel fieldKey={key} hints={fieldHints} />
            <span className="text-[10px] text-zinc-300 break-all">{String(value)}</span>
          </div>
        )
      })}
      </div>
    </div>
  )
}

function TraceRow({ t, index }: { t: ABTraceEntry; index: number }) {
  const [open, setOpen] = useState(false)
  // Even nodes without output have a type_key description worth showing
  const hasContent = !!((t.output && Object.keys(t.output).length > 0) || (t.type_key && NODE_TYPE_INFO[t.type_key]))
  return (
    <div className="border-b border-zinc-800/50 last:border-b-0">
      <button
        onClick={() => hasContent && setOpen((v) => !v)}
        className={`w-full flex items-start gap-2 py-1 px-1 text-left ${hasContent ? 'hover:bg-zinc-800/30 cursor-pointer' : 'cursor-default'}`}
      >
        <span className="text-[9px] text-zinc-600 w-4 shrink-0">{hasContent ? (open ? '▾' : '▸') : ' '}</span>
        <span className="text-[9px] text-zinc-600 w-5 shrink-0">{index + 1}</span>
        <StatusBadge status={t.status} />
        <span className="text-[10px] text-zinc-400 shrink-0 w-28 truncate" title={t.label}>{t.label || t.type_key}</span>
        <span className="text-[10px] text-zinc-300 flex-1 min-w-0 truncate" title={t.summary}>{t.summary}</span>
        <span className="text-[9px] text-zinc-500 shrink-0">
          {t.latency_ms > 0 ? `${t.latency_ms}ms` : '—'}
        </span>
      </button>
      {open && (
        <div className="pl-6 pr-2 pb-2 pt-1 bg-zinc-950/30 border-t border-zinc-800/50">
          <NodeDetail output={(t.output as Record<string, unknown>) || {}} typeKey={t.type_key} />
        </div>
      )}
    </div>
  )
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
        <span className="text-zinc-500">{totalMs}ms 總計 · 點節點看明細</span>
      </button>
      {open && (
        <div className="border-t border-zinc-700/60 max-h-[480px] overflow-y-auto">
          {trace.map((t, i) => (
            <TraceRow key={i} t={t} index={i} />
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

'use client'

/**
 * VariablePicker — DAG editor 變數選擇器
 *
 * 點按鈕 → 下拉列出當前節點上游所有可引用變數 → 選一個 → 自動把
 * `{{node_id.field}}` 插入到關聯的 textarea/input 游標位置（或 onPick 收到）。
 *
 * 不要求使用者記住 `{{}}` 語法，視覺看到的是「上游節點 → 欄位」清單。
 */

import { useEffect, useMemo, useRef, useState } from 'react'

/** 每種節點 type_key 的 output 欄位清單。新增節點類型時記得補。 */
export const NODE_OUTPUT_SHAPES: Record<string, { fields: string[]; note?: string }> = {
  user_input: { fields: ['message'] },
  load_history: { fields: ['messages', 'count'], note: 'messages: list of {role, content}' },
  load_knowledge: { fields: ['chunks', 'count'], note: 'chunks: list of {text, score}' },
  model_call: {
    fields: ['text', 'json', 'model', 'tokens_in', 'tokens_out', 'cost_usd', 'iterations'],
    note: 'json 模式可加 .field 子路徑，例 {{n.json.intent}}',
  },
  branch: {
    fields: ['matched', 'lhs', 'rhs', 'route_taken'],
    note: 'matched: true/false; route_taken: "true"|"false"',
  },
  execute_tools: { fields: ['results'] },
  triage: { fields: ['intent_type', 'matched', 'action_type'] },
  triage_llm: { fields: ['intent_type', 'rule_index'] },
  analyze_intent: { fields: ['actions', 'warnings', 'knowledge_points', 'response_styles'] },
  capability_tool_call: { fields: ['tool_id', 'invoked'] },
  capability_workflow: { fields: ['workflow_id', 'started'] },
  capability_handoff: { fields: ['handoff'] },
  capability_widget: { fields: ['widget_id'] },
  workflow_continue: { fields: ['workflow_status'] },
  parse_widget: { fields: ['widgets'] },
  guardrail: { fields: ['triggered', 'reason'] },
  retry: { fields: ['attempts'] },
}

/** 一個上游節點的描述（給 picker 用）。 */
export interface UpstreamNode {
  id: string
  label?: string
  type_key: string
}

interface VariablePickerProps {
  /** 上游可參考的節點清單（已過濾過：只列真正能讀到 output 的祖先） */
  upstream: UpstreamNode[]
  /** 使用者選了某變數 ref 後，會收到字串如 "n_classifier.json.intent" */
  onPick: (varRef: string) => void
  /** 顯示在按鈕上的文字（預設「+ 插入變數」） */
  buttonLabel?: string
  /** 緊湊樣式（用在 input 旁邊時） */
  compact?: boolean
}

export function VariablePicker({ upstream, onPick, buttonLabel = '+ 插入變數', compact = false }: VariablePickerProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const items = useMemo(() => {
    const lo = search.toLowerCase()
    const out: Array<{ nodeId: string; nodeLabel: string; nodeType: string; field: string; ref: string; note?: string }> = []
    for (const node of upstream) {
      const shape = NODE_OUTPUT_SHAPES[node.type_key] ?? { fields: [], note: undefined }
      for (const field of shape.fields) {
        const ref = `${node.id}.${field}`
        const display = `${node.label || node.id} → ${field}`
        if (!lo || ref.toLowerCase().includes(lo) || display.toLowerCase().includes(lo)) {
          out.push({ nodeId: node.id, nodeLabel: node.label || node.id, nodeType: node.type_key, field, ref, note: shape.note })
        }
      }
    }
    // Always offer raw node refs (for whole-output insertion / json mode)
    for (const node of upstream) {
      const ref = node.id
      if (!lo || ref.toLowerCase().includes(lo) || (node.label || '').toLowerCase().includes(lo)) {
        out.unshift({ nodeId: node.id, nodeLabel: node.label || node.id, nodeType: node.type_key, field: '(整個 output)', ref })
      }
    }
    return out
  }, [upstream, search])

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`rounded ${compact ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-1 text-[11px]'} bg-zinc-800 text-zinc-300 hover:bg-zinc-700 border border-zinc-700`}
        title="從上游節點挑變數插入"
      >
        {buttonLabel}
      </button>

      {open && (
        <div className="absolute z-50 left-0 mt-1 w-[280px] max-h-[360px] overflow-hidden rounded border border-zinc-700 bg-zinc-900 shadow-xl flex flex-col">
          <div className="p-1.5 border-b border-zinc-800 sticky top-0 bg-zinc-900">
            <input
              type="text"
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜尋節點或欄位..."
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-[11px] text-zinc-200 outline-none focus:border-blue-500"
            />
          </div>
          <div className="overflow-y-auto flex-1">
            {upstream.length === 0 && (
              <p className="text-[10px] text-zinc-500 text-center py-4">此節點沒有上游</p>
            )}
            {upstream.length > 0 && items.length === 0 && (
              <p className="text-[10px] text-zinc-500 text-center py-4">沒符合搜尋</p>
            )}
            {items.map((it, i) => (
              <button
                key={`${it.ref}-${i}`}
                type="button"
                onClick={() => {
                  onPick(it.ref)
                  setOpen(false)
                  setSearch('')
                }}
                className="w-full text-left px-3 py-1.5 text-xs hover:bg-zinc-800 border-b border-zinc-800/50 last:border-0"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-zinc-200 truncate">{it.nodeLabel}</span>
                  <span className="text-[9px] text-zinc-500 font-mono shrink-0">{it.nodeType}</span>
                </div>
                <div className="flex items-center justify-between gap-2 mt-0.5">
                  <span className="text-[10px] text-blue-300 font-mono">{it.field}</span>
                  <span className="text-[9px] text-zinc-600 font-mono shrink-0">{`{{${it.ref}}}`}</span>
                </div>
                {it.note && it.field === '(整個 output)' && (
                  <p className="text-[9px] text-zinc-600 mt-0.5">{it.note}</p>
                )}
              </button>
            ))}
          </div>
          <div className="p-1.5 border-t border-zinc-800 text-[9px] text-zinc-600 bg-zinc-900/50">
            點選 → 自動插入 <code className="text-zinc-500">{`{{node.field}}`}</code>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * 把 textarea/input 當前游標位置插入文字。若元素沒 ref / 焦點不在輸入框，append 到結尾。
 * 回傳「插入後的完整字串」與「新游標位置」，呼叫端用來更新 state。
 */
export function insertAtCursor(
  el: HTMLTextAreaElement | HTMLInputElement | null,
  current: string,
  insert: string,
): { next: string; cursor: number } {
  if (!el) {
    return { next: (current || '') + insert, cursor: (current || '').length + insert.length }
  }
  const start = el.selectionStart ?? current.length
  const end = el.selectionEnd ?? current.length
  const next = (current || '').slice(0, start) + insert + (current || '').slice(end)
  return { next, cursor: start + insert.length }
}

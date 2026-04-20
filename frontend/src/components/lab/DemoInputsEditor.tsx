'use client'

import { useState } from 'react'
import { useLabStore } from '@/lib/studio/labStore'

export default function DemoInputsEditor() {
  const demoInputs = useLabStore((s) => s.demoInputs)
  const addDemoInput = useLabStore((s) => s.addDemoInput)
  const removeDemoInput = useLabStore((s) => s.removeDemoInput)

  const [draft, setDraft] = useState('')

  const handleAdd = () => {
    const v = draft.trim()
    if (!v) return
    if (demoInputs.length >= 20) return
    addDemoInput(v)
    setDraft('')
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              handleAdd()
            }
          }}
          placeholder="新增一組示範問題…"
          className="flex-1 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 placeholder-zinc-500 focus:border-blue-500 focus:outline-none"
        />
        <button
          onClick={handleAdd}
          disabled={!draft.trim() || demoInputs.length >= 20}
          className="rounded bg-zinc-800 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-40"
        >
          + 加入
        </button>
      </div>
      {demoInputs.length >= 20 && (
        <p className="text-[10px] text-amber-400">最多 20 組（避免 API 爆量）</p>
      )}
      {demoInputs.length === 0 ? (
        <p className="text-[10px] text-zinc-500">
          加入多組問題後按右下方「Batch Run」可同時跑所有問題
        </p>
      ) : (
        <ul className="space-y-1">
          {demoInputs.map((inp, i) => (
            <li
              key={i}
              className="flex items-start justify-between gap-2 rounded border border-zinc-800 bg-zinc-900/60 p-2"
            >
              <span className="flex-1 break-words text-[11px] text-zinc-200">
                <span className="mr-1 text-[10px] text-zinc-500">#{i + 1}</span>
                {inp}
              </span>
              <button
                onClick={() => removeDemoInput(i)}
                className="text-[10px] text-red-400 hover:text-red-300"
                title="移除"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

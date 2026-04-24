'use client'

/**
 * PromptPicker — 從提示詞工作室挑一個 slot / version 綁到 node config
 *
 * 綁定模式（預設「釘版本」— 未來該 slot 升版不影響本節點）：
 *   - pin: 存 { slot_ref: 'mode_coach', version_ref_id: 'uuid' }
 *   - follow: 存 { slot_ref: 'mode_coach' }（追 active）
 *
 * 儲存欄位由呼叫方指定（field_ref / field_ref_version 兩個欄位名稱）。
 */

import { useEffect, useState } from 'react'
import {
  getPromptLibrary, listSlotVersions,
  type PromptSlotInfo,
} from '@/lib/ai-engine'
import { useProject } from '@/lib/project-context'

interface PromptPickerProps {
  open: boolean
  onClose: () => void
  /** 目前綁定的 slot ref（若有）*/
  currentRef?: string
  /** 目前綁定的 version id（若有，代表釘版本）*/
  currentVersionId?: string
  /** 使用者送出後呼叫 — 若 versionId 存在代表釘版本，否則追 active */
  onPick: (slot: string, versionId?: string) => void
}

export function PromptPicker({ open, onClose, currentRef, currentVersionId, onPick }: PromptPickerProps) {
  const { currentProject } = useProject()
  const projectId = currentProject?.project_id
  const [slots, setSlots] = useState<PromptSlotInfo[]>([])
  const [selectedSlot, setSelectedSlot] = useState<string | null>(currentRef || null)
  const [slotVersions, setSlotVersions] = useState<PromptSlotInfo[]>([])
  const [mode, setMode] = useState<'pin' | 'follow'>(currentVersionId ? 'pin' : 'pin')
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(currentVersionId || null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !projectId) return
    setLoading(true)
    getPromptLibrary(projectId)
      .then((r) => setSlots(r.slots))
      .finally(() => setLoading(false))
  }, [open, projectId])

  useEffect(() => {
    if (!selectedSlot || !projectId) { setSlotVersions([]); return }
    listSlotVersions(projectId, selectedSlot)
      .then((r) => {
        setSlotVersions(r.versions)
        // 預設選 active 版本
        const active = r.versions.find(v => v.is_active)
        if (active && !selectedVersionId) setSelectedVersionId(active.id)
      })
  }, [selectedSlot, projectId])

  if (!open) return null

  const selectedInfo = slots.find(s => s.slot === selectedSlot)
  const selectedVersion = slotVersions.find(v => v.id === selectedVersionId)

  const handlePick = () => {
    if (!selectedSlot) return
    if (mode === 'pin' && selectedVersionId) {
      onPick(selectedSlot, selectedVersionId)
    } else {
      onPick(selectedSlot)
    }
    onClose()
  }

  // Group by category
  const grouped: Record<string, PromptSlotInfo[]> = {}
  for (const s of slots) {
    const cat = s.category || 'custom'
    ;(grouped[cat] = grouped[cat] || []).push(s)
  }
  const categoryOrder = ['system', 'persona', 'custom']

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-lg w-full max-w-3xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 py-3 border-b border-zinc-700 flex items-center justify-between">
          <h3 className="text-sm font-medium text-zinc-200">📚 從提示詞工作室挑一個</h3>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200">✕</button>
        </div>

        <div className="flex-1 flex min-h-0">
          {/* Slot list */}
          <div className="w-56 border-r border-zinc-800 overflow-y-auto flex-shrink-0">
            {loading ? (
              <div className="p-3 text-xs text-zinc-500">載入中…</div>
            ) : (
              categoryOrder.map((cat) => {
                const list = grouped[cat]
                if (!list?.length) return null
                return (
                  <div key={cat} className="py-2">
                    <div className="px-3 py-1 text-[9px] uppercase text-zinc-500 font-semibold">
                      {cat === 'system' ? '系統核心' : cat === 'persona' ? '人格模式' : '自訂'}
                    </div>
                    {list.map((s) => {
                      const active = s.slot === selectedSlot
                      return (
                        <button
                          key={s.slot}
                          onClick={() => { setSelectedSlot(s.slot); setSelectedVersionId(null) }}
                          className={`w-full flex items-center gap-2 px-3 py-2 text-left text-xs ${
                            active
                              ? 'bg-blue-600/20 border-l-2 border-blue-500 text-blue-200'
                              : 'border-l-2 border-transparent text-zinc-300 hover:bg-zinc-800/60'
                          }`}
                        >
                          <span className="text-base shrink-0">{s.icon || '📝'}</span>
                          <div className="flex-1 min-w-0">
                            <div className="font-medium truncate">{s.title || s.slot}</div>
                            <div className="text-[9px] text-zinc-500 truncate">{s.slot}</div>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                )
              })
            )}
          </div>

          {/* Detail + version picker */}
          <div className="flex-1 overflow-y-auto p-4">
            {!selectedInfo ? (
              <div className="text-xs text-zinc-500">← 選一個 slot</div>
            ) : (
              <>
                <div className="flex items-start gap-2 mb-3">
                  <span className="text-2xl">{selectedInfo.icon || '📝'}</span>
                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-medium text-zinc-200">{selectedInfo.title || selectedInfo.slot}</h4>
                    <p className="text-[10px] text-zinc-500">{selectedInfo.description}</p>
                    <p className="text-[9px] text-zinc-600 font-mono">{selectedInfo.slot}</p>
                  </div>
                </div>

                {/* Binding mode */}
                <div className="mb-3 space-y-1 p-2 rounded border border-zinc-700 bg-zinc-800/40">
                  <div className="text-[10px] uppercase text-zinc-500 mb-1">綁定模式</div>
                  <label className="flex items-start gap-2 text-xs cursor-pointer">
                    <input type="radio" checked={mode === 'pin'} onChange={() => setMode('pin')} className="mt-0.5" />
                    <div>
                      <div className="text-zinc-200">📌 釘版本（推薦）</div>
                      <div className="text-[10px] text-zinc-500">未來此 slot 新增版本不會影響本節點 — 確保一致性</div>
                    </div>
                  </label>
                  <label className="flex items-start gap-2 text-xs cursor-pointer">
                    <input type="radio" checked={mode === 'follow'} onChange={() => setMode('follow')} className="mt-0.5" />
                    <div>
                      <div className="text-zinc-200">🔄 追 active</div>
                      <div className="text-[10px] text-zinc-500">永遠用該 slot 目前 active 的版本 — 改了全部節點跟著變</div>
                    </div>
                  </label>
                </div>

                {/* Version select (only for pin mode) */}
                {mode === 'pin' && (
                  <div className="mb-3">
                    <label className="text-[10px] uppercase text-zinc-500 block mb-1">選版本</label>
                    <select
                      value={selectedVersionId || ''}
                      onChange={(e) => setSelectedVersionId(e.target.value)}
                      className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-200 outline-none focus:border-blue-500"
                    >
                      {slotVersions.map((v) => (
                        <option key={v.id} value={v.id}>
                          v{v.version}{v.is_active ? ' (active)' : ''} · {new Date(v.created_at).toLocaleDateString()} · {v.change_notes?.slice(0, 40) || '-'}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Preview */}
                <div>
                  <div className="text-[10px] uppercase text-zinc-500 mb-1">預覽</div>
                  <pre className="whitespace-pre-wrap text-[10px] text-zinc-300 bg-zinc-950 border border-zinc-700 rounded p-2 max-h-64 overflow-y-auto leading-relaxed">
                    {mode === 'pin' ? (selectedVersion?.content || '（選版本看預覽）') : selectedInfo.content}
                  </pre>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="px-4 py-3 border-t border-zinc-700 flex justify-end gap-2">
          <button onClick={onClose} className="rounded bg-zinc-700 px-4 py-1.5 text-xs text-zinc-200 hover:bg-zinc-600">
            取消
          </button>
          <button
            onClick={handlePick}
            disabled={!selectedSlot || (mode === 'pin' && !selectedVersionId)}
            className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
          >
            使用這個
          </button>
        </div>
      </div>
    </div>
  )
}

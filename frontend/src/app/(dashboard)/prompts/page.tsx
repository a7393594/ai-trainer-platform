'use client'

/**
 * 提示詞工作室（多 slot 版）
 *
 * 左側顯示所有 slot 的卡片（base / analyze_intent / mode_* / 自訂）。
 * 點卡片進入該 slot 的詳細面板：目前 active 內容 + 版本歷史 + 編輯 / 建新版本。
 */

import { useEffect, useState, useCallback } from 'react'
import {
  getPromptLibrary, listSlotVersions, activatePromptVersion,
  createPromptVersion,
  type PromptSlotInfo,
} from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'
import { useProject } from '@/lib/project-context'

type ModalMode =
  | { type: 'create'; slot: string; slotInfo: PromptSlotInfo }
  | { type: 'create-custom' }
  | null

const SLOT_CATEGORY_LABEL: Record<string, string> = {
  system: '系統核心',
  persona: '人格模式',
  custom: '自訂',
}

export default function PromptsPage() {
  const [library, setLibrary] = useState<PromptSlotInfo[]>([])
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null)
  const [slotVersions, setSlotVersions] = useState<PromptSlotInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [modal, setModal] = useState<ModalMode>(null)
  const { t } = useI18n()
  const { currentProject } = useProject()
  const projectId = currentProject?.project_id || null

  const refreshLibrary = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const r = await getPromptLibrary(projectId)
      setLibrary(r.slots)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  const refreshSlotVersions = useCallback(async (slot: string) => {
    if (!projectId) return
    setVersionsLoading(true)
    try {
      const r = await listSlotVersions(projectId, slot)
      setSlotVersions(r.versions)
    } finally {
      setVersionsLoading(false)
    }
  }, [projectId])

  useEffect(() => { refreshLibrary() }, [refreshLibrary])
  useEffect(() => {
    if (selectedSlot) refreshSlotVersions(selectedSlot)
  }, [selectedSlot, refreshSlotVersions])

  const selectedInfo = library.find((s) => s.slot === selectedSlot)

  const handleActivate = async (versionId: string) => {
    if (!projectId || !selectedSlot) return
    await activatePromptVersion(projectId, versionId)
    await refreshSlotVersions(selectedSlot)
    await refreshLibrary()
  }

  const handleCreateVersion = async (data: {
    content: string
    change_notes?: string
    activate?: boolean
  }) => {
    if (!projectId || !selectedSlot || !selectedInfo) return
    await createPromptVersion(projectId, {
      ...data,
      slot: selectedSlot,
      title: selectedInfo.title,
      description: selectedInfo.description,
      icon: selectedInfo.icon,
      category: selectedInfo.category,
    })
    setModal(null)
    await refreshSlotVersions(selectedSlot)
    await refreshLibrary()
  }

  const handleCreateCustomSlot = async (data: {
    slot: string
    content: string
    title: string
    description?: string
    icon?: string
  }) => {
    if (!projectId) return
    // 強制 slot 前綴 custom_
    const slotKey = data.slot.startsWith('custom_') ? data.slot : `custom_${data.slot}`
    await createPromptVersion(projectId, {
      content: data.content,
      slot: slotKey,
      title: data.title,
      description: data.description,
      icon: data.icon || '💡',
      category: 'custom',
      activate: true,
      change_notes: '自訂 slot 初始版本',
    })
    setModal(null)
    await refreshLibrary()
    setSelectedSlot(slotKey)
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-900">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
      </div>
    )
  }

  // Group by category for display
  const grouped: Record<string, PromptSlotInfo[]> = {}
  for (const s of library) {
    const cat = s.category || 'custom'
    ;(grouped[cat] = grouped[cat] || []).push(s)
  }

  return (
    <div className="h-full bg-zinc-900 flex overflow-hidden">
      {/* Left: slot list */}
      <aside className="w-80 border-r border-zinc-800 overflow-y-auto flex-shrink-0">
        <div className="p-4 border-b border-zinc-800 flex items-center justify-between">
          <div>
            <h1 className="text-sm font-medium text-zinc-200">{t('prompts.title')}</h1>
            <p className="text-[10px] text-zinc-500 mt-0.5">每個 slot 獨立版本歷史</p>
          </div>
          <button
            onClick={() => setModal({ type: 'create-custom' })}
            className="rounded bg-zinc-700 px-2 py-1 text-[10px] text-zinc-200 hover:bg-zinc-600"
          >
            + 自訂
          </button>
        </div>

        {['system', 'persona', 'custom'].map((cat) => {
          const slots = grouped[cat]
          if (!slots?.length) return null
          return (
            <div key={cat} className="py-2">
              <div className="px-4 py-1 text-[9px] uppercase text-zinc-500 font-semibold">
                {SLOT_CATEGORY_LABEL[cat] || cat}
              </div>
              {slots.map((s) => {
                const active = s.slot === selectedSlot
                return (
                  <button
                    key={s.slot}
                    onClick={() => setSelectedSlot(s.slot)}
                    className={`w-full flex items-center gap-2 px-4 py-2 text-left text-xs transition-colors ${
                      active
                        ? 'bg-blue-600/20 border-l-2 border-blue-500 text-blue-200'
                        : 'border-l-2 border-transparent text-zinc-300 hover:bg-zinc-800/60'
                    }`}
                  >
                    <span className="text-base shrink-0">{s.icon || '📝'}</span>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{s.title || s.slot}</div>
                      <div className="text-[9px] text-zinc-500 font-mono truncate">
                        {s.slot} · v{s.version} · {s.total_versions} 版
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )
        })}
      </aside>

      {/* Right: slot detail */}
      <main className="flex-1 overflow-y-auto">
        {!selectedInfo ? (
          <div className="h-full flex items-center justify-center text-zinc-500 text-sm">
            ← 從左側選一個 slot 開始編輯
          </div>
        ) : (
          <div className="max-w-3xl mx-auto p-6">
            {/* Header */}
            <div className="flex items-start gap-3 mb-4">
              <span className="text-3xl shrink-0">{selectedInfo.icon || '📝'}</span>
              <div className="flex-1 min-w-0">
                <h2 className="text-lg font-medium text-zinc-200">
                  {selectedInfo.title || selectedInfo.slot}
                </h2>
                <p className="text-xs text-zinc-500 mt-0.5">{selectedInfo.description}</p>
                <p className="text-[10px] text-zinc-600 font-mono mt-1">
                  slot: <span className="text-zinc-400">{selectedInfo.slot}</span>
                  {' · '}active v{selectedInfo.version}
                  {' · '}共 {selectedInfo.total_versions} 版
                </p>
              </div>
              <button
                onClick={() => setModal({ type: 'create', slot: selectedInfo.slot, slotInfo: selectedInfo })}
                className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 shrink-0"
              >
                + 建立新版本
              </button>
            </div>

            {/* Active content */}
            <div className="rounded border border-blue-500/30 bg-blue-500/5 p-3 mb-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] uppercase text-blue-400 font-semibold">目前 active</span>
                <span className="text-[10px] text-zinc-500">
                  v{selectedInfo.version} · {new Date(selectedInfo.created_at).toLocaleString('zh-TW')}
                </span>
              </div>
              <pre className="whitespace-pre-wrap text-xs text-zinc-200 font-mono leading-relaxed max-h-96 overflow-y-auto">
                {selectedInfo.content}
              </pre>
              {selectedInfo.change_notes && (
                <p className="text-[10px] text-zinc-500 mt-2 italic">
                  備註：{selectedInfo.change_notes}
                </p>
              )}
            </div>

            {/* Version history */}
            <div>
              <h3 className="text-xs font-medium text-zinc-300 mb-2">版本歷史</h3>
              {versionsLoading ? (
                <div className="text-[10px] text-zinc-500">載入中…</div>
              ) : (
                <div className="space-y-1">
                  {slotVersions.map((v) => (
                    <div
                      key={v.id}
                      className={`rounded border px-3 py-2 text-xs ${
                        v.is_active
                          ? 'border-blue-500/40 bg-blue-500/5'
                          : 'border-zinc-700 bg-zinc-800/40'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="font-mono text-zinc-300">v{v.version}</span>
                          {v.is_active && (
                            <span className="rounded bg-green-500/20 px-1.5 py-0.5 text-[9px] text-green-400">
                              active
                            </span>
                          )}
                          <span className="text-[10px] text-zinc-500 truncate">
                            {v.change_notes || '(無變更備註)'}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-[10px] text-zinc-600">
                            {new Date(v.created_at).toLocaleString('zh-TW', {
                              month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
                            })}
                          </span>
                          {!v.is_active && (
                            <button
                              onClick={() => handleActivate(v.id)}
                              className="text-[10px] text-blue-400 hover:text-blue-300"
                            >
                              切此版本
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Modal: 建立新版本 */}
      {modal?.type === 'create' && (
        <CreateVersionModal
          slotInfo={modal.slotInfo}
          onSubmit={handleCreateVersion}
          onClose={() => setModal(null)}
        />
      )}

      {/* Modal: 建立自訂 slot */}
      {modal?.type === 'create-custom' && (
        <CreateCustomSlotModal
          onSubmit={handleCreateCustomSlot}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}

function CreateVersionModal({
  slotInfo,
  onSubmit,
  onClose,
}: {
  slotInfo: PromptSlotInfo
  onSubmit: (data: { content: string; change_notes?: string; activate?: boolean }) => Promise<void>
  onClose: () => void
}) {
  const [content, setContent] = useState(slotInfo.content)
  const [notes, setNotes] = useState('')
  const [activate, setActivate] = useState(true)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    try {
      await onSubmit({ content, change_notes: notes, activate })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-zinc-900 border border-zinc-700 rounded-lg w-full max-w-3xl max-h-[90vh] flex flex-col">
        <div className="px-4 py-3 border-b border-zinc-700 flex items-center justify-between">
          <h3 className="text-sm font-medium text-zinc-200">
            {slotInfo.icon} 建立 {slotInfo.title || slotInfo.slot} 新版本
          </h3>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          <div>
            <label className="text-[10px] uppercase text-zinc-500 block mb-1">內容</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={16}
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 font-mono leading-relaxed outline-none focus:border-blue-500 resize-y"
            />
            <p className="text-[10px] text-zinc-600 mt-1">字數：{content.length}</p>
          </div>
          <div>
            <label className="text-[10px] uppercase text-zinc-500 block mb-1">變更備註（建議）</label>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="這次改了什麼？為什麼改？"
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-blue-500"
            />
          </div>
          <label className="flex items-center gap-2 text-xs text-zinc-300">
            <input
              type="checkbox"
              checked={activate}
              onChange={(e) => setActivate(e.target.checked)}
            />
            同時啟用為 active（其他版本自動停用）
          </label>
        </div>
        <div className="px-4 py-3 border-t border-zinc-700 flex justify-end gap-2">
          <button onClick={onClose} className="rounded bg-zinc-700 px-4 py-1.5 text-xs text-zinc-200 hover:bg-zinc-600">
            取消
          </button>
          <button
            onClick={save}
            disabled={saving || !content.trim()}
            className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {saving ? '儲存中…' : '建立新版本'}
          </button>
        </div>
      </div>
    </div>
  )
}

function CreateCustomSlotModal({
  onSubmit,
  onClose,
}: {
  onSubmit: (data: { slot: string; content: string; title: string; description?: string; icon?: string }) => Promise<void>
  onClose: () => void
}) {
  const [slot, setSlot] = useState('')
  const [title, setTitle] = useState('')
  const [icon, setIcon] = useState('💡')
  const [description, setDescription] = useState('')
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)

  const slotKey = slot.trim().replace(/^custom_/, '')
  const canSubmit = slotKey.length > 0 && title.trim().length > 0 && content.trim().length > 0 && !saving

  const save = async () => {
    setSaving(true)
    try {
      await onSubmit({ slot: slotKey, title: title.trim(), description, icon, content })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-zinc-900 border border-zinc-700 rounded-lg w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="px-4 py-3 border-b border-zinc-700 flex items-center justify-between">
          <h3 className="text-sm font-medium text-zinc-200">建立自訂 slot</h3>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-[10px] uppercase text-zinc-500 block mb-1">slot 識別名</label>
              <div className="flex">
                <span className="rounded-l border border-r-0 border-zinc-700 bg-zinc-800 px-2 py-2 text-xs text-zinc-500 font-mono">custom_</span>
                <input
                  value={slot}
                  onChange={(e) => setSlot(e.target.value.replace(/[^a-z0-9_]/gi, '_').toLowerCase())}
                  placeholder="beginner_coach"
                  className="flex-1 rounded-r border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 font-mono outline-none focus:border-blue-500"
                />
              </div>
            </div>
            <div className="w-20">
              <label className="text-[10px] uppercase text-zinc-500 block mb-1">icon</label>
              <input
                value={icon}
                onChange={(e) => setIcon(e.target.value)}
                maxLength={2}
                className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-2 text-lg text-center outline-none focus:border-blue-500"
              />
            </div>
          </div>
          <div>
            <label className="text-[10px] uppercase text-zinc-500 block mb-1">顯示名稱</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="新手友善教練"
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase text-zinc-500 block mb-1">描述</label>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="用途說明"
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase text-zinc-500 block mb-1">prompt 內容</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={10}
              placeholder="你是一個..."
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 font-mono outline-none focus:border-blue-500 resize-y"
            />
          </div>
        </div>
        <div className="px-4 py-3 border-t border-zinc-700 flex justify-end gap-2">
          <button onClick={onClose} className="rounded bg-zinc-700 px-4 py-1.5 text-xs text-zinc-200 hover:bg-zinc-600">
            取消
          </button>
          <button
            onClick={save}
            disabled={!canSubmit}
            className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {saving ? '建立中…' : '建立 + 啟用'}
          </button>
        </div>
      </div>
    </div>
  )
}

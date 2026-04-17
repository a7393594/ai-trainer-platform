'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

export default function PokerUploadPage() {
  const [projectId, setProjectId] = useState('')
  const [userId, setUserId] = useState('')
  const [rawText, setRawText] = useState('')
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')
  const [batches, setBatches] = useState<any[]>([])
  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setProjectId(ctx.project_id)
      setUserId(ctx.user_id)
      loadBatches(ctx.user_id, ctx.project_id)
    })
  }, [])

  const loadBatches = async (uid: string, pid: string) => {
    try {
      const r = await fetch(`${AI}/api/v1/poker/uploads?user_id=${uid}&project_id=${pid}`)
      const d = await r.json()
      setBatches(d.batches || [])
    } catch {}
  }

  const handleUpload = async () => {
    if (!rawText.trim()) return
    setUploading(true)
    setError('')
    setResult(null)
    try {
      const r = await fetch(`${AI}/api/v1/poker/upload/hh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, project_id: projectId, raw_text: rawText, filename: 'paste-upload.txt' }),
      })
      if (!r.ok) {
        const err = await r.text()
        throw new Error(err)
      }
      const data = await r.json()
      setResult(data)
      setRawText('')
      loadBatches(userId, projectId)
    } catch (e: any) {
      setError(e.message || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const statusBadge: Record<string, string> = {
    completed: 'bg-emerald-500/20 text-emerald-400',
    processing: 'bg-amber-500/20 text-amber-400',
    error: 'bg-red-500/20 text-red-400',
  }

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">{t('nav.poker.upload')}</h1>
        <p className="text-xs text-zinc-500 mb-6">貼上 PokerStars 或 GGPoker 的手牌歷史文字</p>

        {/* Upload Area */}
        <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 mb-6">
          <textarea
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder="PokerStars Hand #156632473469: Hold'em No Limit ($0.05/$0.10 USD) - 2016/07/30 18:48:33 ET&#10;Table 'Aludra IV' 6-max Seat #1 is the button&#10;..."
            rows={12}
            className="w-full rounded border border-zinc-600 bg-zinc-900 px-3 py-2 text-xs text-zinc-200 font-mono outline-none focus:border-blue-500 mb-3"
          />
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-zinc-500">
              {rawText.length > 0 ? `${rawText.length.toLocaleString()} 字元` : '支援 PokerStars / GGPoker 格式'}
            </span>
            <button
              onClick={handleUpload}
              disabled={uploading || !rawText.trim()}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500 disabled:opacity-50"
            >
              {uploading ? '解析中...' : '上傳並解析'}
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-500/50 bg-red-950/30 p-3 mb-4 text-sm text-red-300">{error}</div>
        )}

        {/* Result */}
        {result && (
          <div className="rounded-lg border border-emerald-500/50 bg-emerald-950/20 p-4 mb-6">
            <h3 className="text-sm font-medium text-emerald-300 mb-2">上傳成功</h3>
            <div className="grid grid-cols-4 gap-3 text-center">
              <div>
                <div className="text-lg font-bold text-zinc-200">{result.total_hands}</div>
                <div className="text-[10px] text-zinc-500">總手數</div>
              </div>
              <div>
                <div className="text-lg font-bold text-emerald-400">{result.inserted}</div>
                <div className="text-[10px] text-zinc-500">新增</div>
              </div>
              <div>
                <div className="text-lg font-bold text-amber-400">{result.failed}</div>
                <div className="text-[10px] text-zinc-500">重複/失敗</div>
              </div>
              <div>
                <div className="text-lg font-bold text-blue-400">{result.stats_preview?.vpip ?? '-'}%</div>
                <div className="text-[10px] text-zinc-500">VPIP</div>
              </div>
            </div>
          </div>
        )}

        {/* Upload History */}
        <h2 className="text-sm font-medium text-zinc-300 mb-3">上傳紀錄</h2>
        <div className="space-y-2">
          {batches.map((b) => (
            <div key={b.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50 px-4 py-3 flex items-center justify-between">
              <div>
                <p className="text-sm text-zinc-200">{b.filename}</p>
                <p className="text-[10px] text-zinc-500">
                  {b.parsed_hands} 手 / {b.source} / {new Date(b.created_at).toLocaleString()}
                </p>
              </div>
              <span className={`rounded px-2 py-0.5 text-[10px] ${statusBadge[b.status] || ''}`}>
                {b.status}
              </span>
            </div>
          ))}
          {batches.length === 0 && <p className="text-sm text-zinc-500 text-center py-8">尚無上傳紀錄</p>}
        </div>
      </div>
    </div>
  )
}

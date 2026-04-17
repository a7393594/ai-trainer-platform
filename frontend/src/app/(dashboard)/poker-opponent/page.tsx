'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

const archetypeEmojis: Record<string, string> = {
  tag: '🎯', lag: '🔥', tp: '🐢', lp: '🐟', maniac: '💥', nit: '🪨',
}
const archetypeColors: Record<string, string> = {
  tag: 'border-blue-500/40', lag: 'border-red-500/40', tp: 'border-zinc-500/40',
  lp: 'border-emerald-500/40', maniac: 'border-amber-500/40', nit: 'border-violet-500/40',
}

interface ActionResult { action: string; amount?: number; reasoning: string; archetype_name: string }

export default function OpponentSimPage() {
  const { t } = useI18n()
  const [archetypes, setArchetypes] = useState<any[]>([])
  const [selected, setSelected] = useState('')
  const [potSize, setPotSize] = useState('10')
  const [board, setBoard] = useState('')
  const [street, setStreet] = useState('flop')
  const [actionTo, setActionTo] = useState('check or bet')
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState<ActionResult[]>([])

  useEffect(() => {
    fetch(`${AI}/api/v1/poker/opponent/archetypes`).then(r => r.json()).then(d => {
      setArchetypes(d.archetypes || [])
      if (d.archetypes?.length) setSelected(d.archetypes[0].id)
    }).catch(() => {})
  }, [])

  const simulate = async () => {
    if (!selected) return
    setLoading(true)
    try {
      const r = await fetch(`${AI}/api/v1/poker/opponent/simulate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ archetype: selected, game_state: { pot_size: potSize, board: board.split(' ').filter(Boolean), street, action_to: actionTo } }),
      })
      const result = await r.json()
      setHistory(prev => [result, ...prev])
    } catch {}
    setLoading(false)
  }

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-y-auto">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">{t('nav.poker.opponent')}</h1>
        <p className="text-xs text-zinc-500 mb-6">選擇對手類型，模擬真實牌桌互動</p>

        {/* Archetype Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
          {archetypes.map((a) => (
            <button
              key={a.id}
              onClick={() => setSelected(a.id)}
              className={`rounded-lg border p-3 text-left transition-all ${selected === a.id ? `${archetypeColors[a.id] || 'border-blue-500/40'} bg-zinc-800` : 'border-zinc-700 bg-zinc-800/30 hover:border-zinc-600'}`}
            >
              <div className="text-lg mb-1">{archetypeEmojis[a.id] || '🃏'}</div>
              <div className="text-xs font-medium text-zinc-200 truncate">{a.name}</div>
              <div className="text-[10px] text-zinc-500 mt-1">VPIP {a.stats?.vpip}% PFR {a.stats?.pfr}%</div>
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Game State Input */}
          <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
            <h2 className="text-sm font-medium text-zinc-300 mb-3">遊戲狀態</h2>
            <div className="space-y-3">
              <div>
                <label className="text-[10px] text-zinc-500 mb-1 block">底池 (bb)</label>
                <input value={potSize} onChange={e => setPotSize(e.target.value)} type="number" className="w-full rounded border border-zinc-600 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-blue-500" />
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 mb-1 block">公共牌（空格分隔，如 Ah Kd 3c）</label>
                <input value={board} onChange={e => setBoard(e.target.value)} placeholder="Ah Kd 3c" className="w-full rounded border border-zinc-600 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-blue-500" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-zinc-500 mb-1 block">街</label>
                  <select value={street} onChange={e => setStreet(e.target.value)} className="w-full rounded border border-zinc-600 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none">
                    <option value="preflop">Preflop</option>
                    <option value="flop">Flop</option>
                    <option value="turn">Turn</option>
                    <option value="river">River</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 mb-1 block">需要動作</label>
                  <input value={actionTo} onChange={e => setActionTo(e.target.value)} className="w-full rounded border border-zinc-600 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-blue-500" />
                </div>
              </div>
              <button onClick={simulate} disabled={loading || !selected} className="w-full rounded bg-blue-600 px-4 py-2.5 text-sm text-white hover:bg-blue-500 disabled:opacity-50">
                {loading ? '思考中...' : '模擬對手動作'}
              </button>
            </div>
          </div>

          {/* Action History */}
          <div className="space-y-3">
            <h2 className="text-sm font-medium text-zinc-300">對手回應</h2>
            {history.length === 0 && <p className="text-xs text-zinc-500 py-8 text-center">選擇對手並設定牌面，開始模擬</p>}
            {history.map((h, i) => (
              <div key={i} className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-medium text-violet-300">{h.archetype_name}</span>
                  <span className={`rounded px-2 py-0.5 text-xs font-bold ${h.action === 'fold' ? 'text-red-400 bg-red-950/50' : h.action === 'raise' || h.action === 'bet' ? 'text-amber-400 bg-amber-950/50' : 'text-emerald-400 bg-emerald-950/50'}`}>
                    {h.action}{h.amount ? ` ${h.amount}bb` : ''}
                  </span>
                </div>
                <p className="text-xs text-zinc-400">{h.reasoning}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

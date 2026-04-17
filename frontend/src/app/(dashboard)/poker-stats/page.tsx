'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

// GTO reference ranges for 6-max 100bb
const GTO_REF: Record<string, { min: number; max: number; label: string }> = {
  vpip: { min: 22, max: 27, label: 'VPIP' },
  pfr: { min: 19, max: 25, label: 'PFR' },
  three_bet: { min: 7, max: 11, label: '3-Bet%' },
  fold_to_three_bet: { min: 50, max: 58, label: 'Fold to 3-Bet' },
  cbet_flop: { min: 55, max: 75, label: 'C-Bet Flop' },
  wtsd: { min: 25, max: 28, label: 'WTSD%' },
  won_at_sd: { min: 50, max: 54, label: 'W$SD%' },
  af: { min: 2.5, max: 3.5, label: 'AF' },
  wwsf: { min: 46, max: 52, label: 'WWSF%' },
  steal_pct: { min: 35, max: 50, label: 'Steal%' },
}

function StatBadge({ stat, value }: { stat: string; value: number }) {
  const ref = GTO_REF[stat]
  if (!ref) return null
  const isLow = value < ref.min
  const isHigh = value > ref.max
  const color = isLow ? 'text-red-400' : isHigh ? 'text-amber-400' : 'text-emerald-400'
  const indicator = isLow ? '偏低' : isHigh ? '偏高' : 'GTO 範圍'
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3">
      <div className="text-[10px] text-zinc-500 mb-1">{ref.label}</div>
      <div className={`text-xl font-bold font-mono ${color}`}>
        {stat === 'af' ? value.toFixed(2) : `${value.toFixed(1)}%`}
      </div>
      <div className="text-[10px] text-zinc-600 mt-0.5">
        {indicator} (GTO: {stat === 'af' ? `${ref.min}-${ref.max}` : `${ref.min}-${ref.max}%`})
      </div>
    </div>
  )
}

function PositionRow({ pos, data }: { pos: string; data: any }) {
  const vpipColor = data.vpip > 35 ? 'text-red-400' : data.vpip > 27 ? 'text-amber-400' : 'text-emerald-400'
  const pfrColor = data.pfr > 25 ? 'text-amber-400' : data.pfr < 15 ? 'text-red-400' : 'text-emerald-400'
  const bbColor = data.bb_per_100 > 0 ? 'text-emerald-400' : data.bb_per_100 < -5 ? 'text-red-400' : 'text-amber-400'
  return (
    <tr className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
      <td className="px-3 py-2 text-sm font-medium text-zinc-200">{pos}</td>
      <td className="px-3 py-2 text-sm text-zinc-400">{data.hands}</td>
      <td className={`px-3 py-2 text-sm font-mono ${vpipColor}`}>{data.vpip.toFixed(1)}%</td>
      <td className={`px-3 py-2 text-sm font-mono ${pfrColor}`}>{data.pfr.toFixed(1)}%</td>
      <td className={`px-3 py-2 text-sm font-mono ${bbColor}`}>{data.bb_per_100.toFixed(1)}</td>
    </tr>
  )
}

export default function PokerStatsPage() {
  const [userId, setUserId] = useState('')
  const [projectId, setProjectId] = useState('')
  const [stats, setStats] = useState<any>(null)
  const [byPosition, setByPosition] = useState<any>({})
  const [sampleSize, setSampleSize] = useState(0)
  const [loading, setLoading] = useState(true)
  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setUserId(ctx.user_id)
      setProjectId(ctx.project_id)
      loadStats(ctx.user_id, ctx.project_id)
    }).catch(() => setLoading(false))
  }, [])

  const loadStats = async (uid: string, pid: string) => {
    try {
      const r = await fetch(`${AI}/api/v1/poker/stats?user_id=${uid}&project_id=${pid}`)
      const d = await r.json()
      setStats(d.stats)
      setByPosition(d.by_position || d.stats?.by_position || {})
      setSampleSize(d.sample_size || d.stats?.sample_size || 0)
    } catch {}
    setLoading(false)
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-900">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="h-full bg-zinc-900 p-6 flex items-center justify-center">
        <div className="text-center">
          <p className="text-zinc-400 text-sm mb-2">尚無統計資料</p>
          <p className="text-zinc-500 text-xs">請先到「手牌上傳」頁面上傳 PokerStars 或 GGPoker 手牌歷史</p>
        </div>
      </div>
    )
  }

  const positionOrder = ['UTG', 'UTG1', 'MP', 'HJ', 'CO', 'BTN', 'SB', 'BB']
  const positions = positionOrder.filter(p => byPosition[p])

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-y-auto">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">{t('nav.poker.stats')}</h1>
            <p className="text-xs text-zinc-500">樣本數：{sampleSize.toLocaleString()} 手</p>
          </div>
          <div className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5">
            <span className={`text-sm font-bold font-mono ${stats.bb_per_100 > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {stats.bb_per_100 > 0 ? '+' : ''}{stats.bb_per_100?.toFixed(2)} bb/100
            </span>
          </div>
        </div>

        {/* Sample size warning */}
        {sampleSize < 1000 && (
          <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-950/20 px-4 py-2 text-xs text-amber-300">
            樣本數 &lt; 1,000 手，統計數據可能不穩定。建議累積至少 5,000 手以獲得可靠��據。
          </div>
        )}

        {/* Core Stats Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-8">
          {Object.entries(GTO_REF).map(([key]) => {
            const val = stats[key]
            return val != null ? <StatBadge key={key} stat={key} value={val} /> : null
          })}
        </div>

        {/* Position Breakdown */}
        {positions.length > 0 && (
          <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 overflow-hidden mb-8">
            <div className="px-4 py-3 border-b border-zinc-700">
              <h2 className="text-sm font-medium text-zinc-300">���置分佈</h2>
            </div>
            <table className="w-full">
              <thead>
                <tr className="text-left text-[10px] font-medium uppercase tracking-wider text-zinc-500">
                  <th className="px-3 py-2">位置</th>
                  <th className="px-3 py-2">手數</th>
                  <th className="px-3 py-2">VPIP</th>
                  <th className="px-3 py-2">PFR</th>
                  <th className="px-3 py-2">bb/100</th>
                </tr>
              </thead>
              <tbody>
                {positions.map(pos => (
                  <PositionRow key={pos} pos={pos} data={byPosition[pos]} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* VPIP-PFR Gap */}
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <h2 className="text-sm font-medium text-zinc-300 mb-3">關鍵指標分析</h2>
          <div className="space-y-2 text-xs text-zinc-400">
            {stats.vpip - stats.pfr > 5 && (
              <div className="flex items-start gap-2">
                <span className="text-red-400 mt-0.5">!</span>
                <span>VPIP-PFR Gap = {(stats.vpip - stats.pfr).toFixed(1)}%（偏高，建議減少 limp，改為 open raise 進入底池）</span>
              </div>
            )}
            {stats.fold_to_three_bet > 65 && (
              <div className="flex items-start gap-2">
                <span className="text-red-400 mt-0.5">!</span>
                <span>Fold to 3-Bet = {stats.fold_to_three_bet.toFixed(1)}%（過高，對手可以用很寬的 3-bet 範圍剝削你）</span>
              </div>
            )}
            {stats.three_bet < 5 && sampleSize > 500 && (
              <div className="flex items-start gap-2">
                <span className="text-amber-400 mt-0.5">!</span>
                <span>3-Bet% = {stats.three_bet.toFixed(1)}%（偏低，尤其 BB vs BTN 應提升到 10%+）</span>
              </div>
            )}
            {stats.vpip >= 22 && stats.vpip <= 27 && stats.pfr >= 19 && stats.pfr <= 25 && (
              <div className="flex items-start gap-2">
                <span className="text-emerald-400 mt-0.5">OK</span>
                <span>VPIP/PFR �� GTO 範圍內，翻前整體穩定</span>
              </div>
            )}
          </div>
        </div>

        {/* Leak Severity Ranking (分析) */}
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4 mt-6">
          <h2 className="text-sm font-medium text-zinc-300 mb-3">Leak 嚴重度排名</h2>
          <div className="space-y-2">
            {(() => {
              const leaks: { name: string; delta: number; severity: string }[] = []
              for (const [key, ref] of Object.entries(GTO_REF)) {
                const val = stats[key]
                if (val == null) continue
                const delta = val < ref.min ? ref.min - val : val > ref.max ? val - ref.max : 0
                if (delta > 2) leaks.push({ name: ref.label, delta: Math.round(delta * 10) / 10, severity: delta > 10 ? 'critical' : delta > 5 ? 'major' : 'moderate' })
              }
              leaks.sort((a, b) => b.delta - a.delta)
              if (leaks.length === 0) return <p className="text-xs text-emerald-400">所有指標均在 GTO 範圍內</p>
              return leaks.map((l, i) => (
                <div key={i} className="flex items-center justify-between rounded border border-zinc-700 px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${l.severity === 'critical' ? 'text-red-400 border-red-500/40 bg-red-950/50' : l.severity === 'major' ? 'text-amber-400 border-amber-500/40 bg-amber-950/50' : 'text-yellow-400 border-yellow-500/40 bg-yellow-950/50'}`}>{l.severity}</span>
                    <span className="text-xs text-zinc-200">{l.name}</span>
                  </div>
                  <span className="text-xs font-mono text-red-400">偏差 {l.delta}%</span>
                </div>
              ))
            })()}
          </div>
        </div>

        {/* VPIP-PFR Gap Visual (觀察) */}
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4 mt-4">
          <h2 className="text-sm font-medium text-zinc-300 mb-3">翻前風格雷達</h2>
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-[10px] text-zinc-500 mb-1">緊度 (Tightness)</div>
              <div className="text-lg font-bold font-mono text-blue-400">{(100 - stats.vpip).toFixed(0)}%</div>
              <div className="text-[10px] text-zinc-600">{stats.vpip < 22 ? '偏緊' : stats.vpip > 28 ? '偏鬆' : '適中'}</div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500 mb-1">侵略性 (Aggression)</div>
              <div className="text-lg font-bold font-mono text-amber-400">{stats.af?.toFixed(1)}</div>
              <div className="text-[10px] text-zinc-600">{stats.af < 2 ? '被動' : stats.af > 4 ? '超攻' : '均衡'}</div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500 mb-1">VPIP-PFR Gap</div>
              <div className={`text-lg font-bold font-mono ${stats.vpip - stats.pfr > 5 ? 'text-red-400' : 'text-emerald-400'}`}>
                {(stats.vpip - stats.pfr).toFixed(1)}%
              </div>
              <div className="text-[10px] text-zinc-600">{stats.vpip - stats.pfr > 5 ? 'Limp 過多' : '健康'}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

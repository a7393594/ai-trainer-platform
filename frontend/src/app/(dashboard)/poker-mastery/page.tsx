'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

const categoryLabels: Record<string, string> = {
  preflop: '翻前', postflop: '翻後', tournament: '錦標賽', mental: '心理', bankroll: '資金', advanced: '進階',
}
const categoryColors: Record<string, string> = {
  preflop: 'border-blue-500/40', postflop: 'border-emerald-500/40', tournament: 'border-violet-500/40',
  mental: 'border-amber-500/40', bankroll: 'border-cyan-500/40', advanced: 'border-red-500/40',
}

function masteryColor(level: number): string {
  if (level >= 0.7) return 'bg-emerald-500'
  if (level >= 0.3) return 'bg-amber-500'
  return 'bg-red-500'
}

export default function PokerMasteryPage() {
  const [userId, setUserId] = useState('')
  const [projectId, setProjectId] = useState('')
  const [mastery, setMastery] = useState<any[]>([])
  const [plan, setPlan] = useState<any>(null)
  const [due, setDue] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setUserId(ctx.user_id)
      setProjectId(ctx.project_id)
      Promise.all([
        fetch(`${AI}/api/v1/poker/mastery?user_id=${ctx.user_id}&project_id=${ctx.project_id}`).then(r => r.json()),
        fetch(`${AI}/api/v1/poker/learning-plan?user_id=${ctx.user_id}&project_id=${ctx.project_id}`).then(r => r.json()),
        fetch(`${AI}/api/v1/poker/due-reviews?user_id=${ctx.user_id}&project_id=${ctx.project_id}`).then(r => r.json()),
      ]).then(([m, p, d]) => {
        setMastery(m.mastery || [])
        setPlan(p)
        setDue(d.due || [])
      }).catch(() => {}).finally(() => setLoading(false))
    }).catch(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-900">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
      </div>
    )
  }

  // Group mastery by category
  const byCategory: Record<string, any[]> = {}
  for (const m of mastery) {
    const cat = m.category || 'other'
    if (!byCategory[cat]) byCategory[cat] = []
    byCategory[cat].push(m)
  }

  const categoryOrder = ['preflop', 'postflop', 'tournament', 'mental', 'bankroll', 'advanced']

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-y-auto">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">概念掌握度</h1>
        <p className="text-xs text-zinc-500 mb-6">
          {plan?.stats ? `${plan.stats.mastered}/${plan.stats.total_concepts} 概念已掌握 | ${plan.stats.due_review} 待複習` : '追蹤 30 個核心知識組件的學習進度'}
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Learning Plan */}
          <div className="lg:col-span-1 space-y-4">
            {/* Learning Plan */}
            {plan?.items?.length > 0 && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
                <h2 className="text-sm font-medium text-zinc-200 mb-3">今日學習計畫</h2>
                <p className="text-[10px] text-zinc-500 mb-3">預估 {plan.total_estimated_minutes} 分鐘</p>
                <div className="space-y-2">
                  {plan.items.map((item: any, i: number) => (
                    <div key={i} className="flex items-center gap-2 rounded border border-zinc-700 px-3 py-2">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                        item.type === 'weakness' ? 'bg-red-900/30 text-red-400' :
                        item.type === 'new' ? 'bg-blue-900/30 text-blue-400' :
                        'bg-amber-900/30 text-amber-400'
                      }`}>
                        {item.type === 'weakness' ? '弱點' : item.type === 'new' ? '新' : '複習'}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-zinc-200 truncate">{item.concept_name}</p>
                        <p className="text-[10px] text-zinc-500">{item.reason}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Due Reviews */}
            {due.length > 0 && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-950/10 p-4">
                <h2 className="text-sm font-medium text-amber-300 mb-2">
                  待複習 ({due.length})
                </h2>
                <div className="space-y-1">
                  {due.slice(0, 8).map((d: any, i: number) => (
                    <div key={i} className="text-xs text-zinc-400 flex items-center justify-between">
                      <span>{d.concept_name || d.concept_code}</span>
                      <span className="text-[10px] text-zinc-500">{(d.mastery_level * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right: Concept Tree */}
          <div className="lg:col-span-2 space-y-4">
            {categoryOrder.filter(cat => byCategory[cat]).map(cat => (
              <div key={cat} className={`rounded-lg border ${categoryColors[cat] || 'border-zinc-700'} bg-zinc-800/50 p-4`}>
                <h2 className="text-sm font-medium text-zinc-200 mb-3">
                  {categoryLabels[cat] || cat}
                  <span className="ml-2 text-[10px] text-zinc-500">
                    ({byCategory[cat].filter(m => m.mastery_level >= 0.7).length}/{byCategory[cat].length} 掌握)
                  </span>
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {byCategory[cat].sort((a: any, b: any) => a.difficulty - b.difficulty).map((m: any) => (
                    <div key={m.concept_code} className="flex items-center gap-3 rounded border border-zinc-700/50 px-3 py-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-zinc-200 truncate">{m.concept_name}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <div className="flex-1 h-1.5 rounded-full bg-zinc-800">
                            <div
                              className={`h-1.5 rounded-full ${masteryColor(m.mastery_level)} transition-all`}
                              style={{ width: `${m.mastery_level * 100}%` }}
                            />
                          </div>
                          <span className="text-[10px] text-zinc-500 w-8 text-right">
                            {(m.mastery_level * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                      <div className="text-[10px] text-zinc-600">
                        {m.exposure_count || 0}x
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

'use client'

import { useEffect, useState } from 'react'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

interface ProfileData {
  profile: {
    level: string
    level_confidence: number
    scaffolding_stage: string
    game_types: string[]
    weaknesses: string[]
    strengths: string[]
    total_concepts_mastered: number
    xp_total: number
    current_streak_days: number
  } | null
  mastery_summary: { concept_name: string; category: string; mastery_level: number }[]
}

const levelLabels: Record<string, string> = {
  L0: '完全新手', L1: '新手', L2: '中階', L3: '進階', L4: '半職業', L5: '職業',
}
const levelColors: Record<string, string> = {
  L0: 'bg-zinc-600', L1: 'bg-blue-600', L2: 'bg-emerald-600',
  L3: 'bg-violet-600', L4: 'bg-amber-600', L5: 'bg-red-600',
}
const stageLabels: Record<string, string> = {
  modeling: '完整示範', guided: '引導練習', prompting: '提示引導', sparring: '對等切磋',
}

export function StudentProfilePanel({ userId, projectId }: { userId: string; projectId: string }) {
  const [data, setData] = useState<ProfileData | null>(null)
  const [loading, setLoading] = useState(true)
  const { t } = useI18n()

  useEffect(() => {
    if (!userId || !projectId) return
    fetch(`${AI}/api/v1/poker/profile?user_id=${userId}&project_id=${projectId}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [userId, projectId])

  if (loading) {
    return (
      <div className="p-3 text-center">
        <div className="h-3 w-3 mx-auto animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
      </div>
    )
  }

  const p = data?.profile
  if (!p) {
    return (
      <div className="p-3 text-xs text-zinc-500 text-center">
        完成 Onboarding 後顯示學生檔案
      </div>
    )
  }

  const level = p.level || 'L1'
  const masteryByCategory = (data?.mastery_summary || []).reduce<Record<string, { total: number; sum: number; weak: string[] }>>((acc, m) => {
    const cat = m.category || 'other'
    if (!acc[cat]) acc[cat] = { total: 0, sum: 0, weak: [] }
    acc[cat].total++
    acc[cat].sum += m.mastery_level
    if (m.mastery_level < 0.3) acc[cat].weak.push(m.concept_name)
    return acc
  }, {})

  return (
    <div className="space-y-3 p-3">
      {/* Level Badge */}
      <div className="flex items-center gap-2">
        <span className={`rounded px-2 py-1 text-xs font-bold text-white ${levelColors[level] || 'bg-zinc-600'}`}>
          {level}
        </span>
        <span className="text-xs text-zinc-300">{levelLabels[level] || level}</span>
        <span className="text-[10px] text-zinc-500">({(p.level_confidence * 100).toFixed(0)}%)</span>
      </div>

      {/* Scaffolding Stage */}
      <div className="rounded border border-zinc-700 bg-zinc-800/50 px-3 py-2">
        <div className="text-[10px] text-zinc-500 mb-0.5">教學模式</div>
        <div className="text-xs text-zinc-200">{stageLabels[p.scaffolding_stage] || p.scaffolding_stage}</div>
      </div>

      {/* Weaknesses */}
      {p.weaknesses?.length > 0 && (
        <div>
          <div className="text-[10px] text-zinc-500 mb-1">弱點</div>
          <div className="flex flex-wrap gap-1">
            {p.weaknesses.slice(0, 4).map((w, i) => (
              <span key={i} className="rounded bg-red-900/30 px-1.5 py-0.5 text-[10px] text-red-300 border border-red-500/30">{w}</span>
            ))}
          </div>
        </div>
      )}

      {/* Mastery Overview */}
      {Object.keys(masteryByCategory).length > 0 && (
        <div>
          <div className="text-[10px] text-zinc-500 mb-1.5">概念掌握</div>
          <div className="space-y-1.5">
            {Object.entries(masteryByCategory).map(([cat, info]) => {
              const avg = info.sum / Math.max(info.total, 1)
              return (
                <div key={cat}>
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-[10px] text-zinc-400">{cat}</span>
                    <span className="text-[10px] text-zinc-500">{(avg * 100).toFixed(0)}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-zinc-800">
                    <div
                      className={`h-1.5 rounded-full transition-all ${
                        avg >= 0.7 ? 'bg-emerald-500' : avg >= 0.3 ? 'bg-amber-500' : 'bg-red-500'
                      }`}
                      style={{ width: `${avg * 100}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 gap-2 text-center">
        <div className="rounded border border-zinc-700 bg-zinc-800/50 px-2 py-1.5">
          <div className="text-xs font-bold text-blue-400">{p.xp_total}</div>
          <div className="text-[10px] text-zinc-500">XP</div>
        </div>
        <div className="rounded border border-zinc-700 bg-zinc-800/50 px-2 py-1.5">
          <div className="text-xs font-bold text-amber-400">{p.current_streak_days}</div>
          <div className="text-[10px] text-zinc-500">Streak</div>
        </div>
      </div>
    </div>
  )
}

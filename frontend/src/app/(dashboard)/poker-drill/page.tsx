'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

const gradeLabels = [
  { grade: 1, label: '忘了', color: 'bg-red-600 hover:bg-red-500', key: 'Again' },
  { grade: 2, label: '困難', color: 'bg-amber-600 hover:bg-amber-500', key: 'Hard' },
  { grade: 3, label: '良好', color: 'bg-blue-600 hover:bg-blue-500', key: 'Good' },
  { grade: 4, label: '輕鬆', color: 'bg-emerald-600 hover:bg-emerald-500', key: 'Easy' },
]

const difficultyStars = (d: number) => '★'.repeat(d) + '☆'.repeat(5 - d)

export default function DrillPage() {
  const { t } = useI18n()
  const [userId, setUserId] = useState('')
  const [projectId, setProjectId] = useState('')
  const [dueItems, setDueItems] = useState<any[]>([])
  const [currentIdx, setCurrentIdx] = useState(0)
  const [showAnswer, setShowAnswer] = useState(false)
  const [completed, setCompleted] = useState(0)
  const [loading, setLoading] = useState(true)
  const [planStats, setPlanStats] = useState<any>(null)

  useEffect(() => {
    getDemoContext().then(async (ctx) => {
      setUserId(ctx.user_id)
      setProjectId(ctx.project_id)
      // Load due reviews + learning plan
      const [dueRes, planRes] = await Promise.all([
        fetch(`${AI}/api/v1/poker/due-reviews?user_id=${ctx.user_id}&project_id=${ctx.project_id}`).then(r => r.json()),
        fetch(`${AI}/api/v1/poker/learning-plan?user_id=${ctx.user_id}&project_id=${ctx.project_id}`).then(r => r.json()),
      ])
      // Combine: due items first, then plan items
      const items = [
        ...(dueRes.due || []).map((d: any) => ({ ...d, drill_type: 'review' })),
        ...(planRes.items || []).filter((i: any) => i.type !== 'review').map((i: any) => ({ ...i, drill_type: i.type, concept_name: i.concept_name, concept_code: i.concept_code })),
      ]
      setDueItems(items)
      setPlanStats(planRes.stats)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const current = dueItems[currentIdx]

  const handleGrade = async (grade: number) => {
    if (!current) return
    const conceptId = current.concept_id || current.id
    if (conceptId) {
      try {
        await fetch(`${AI}/api/v1/poker/mastery/review`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId, concept_id: conceptId, grade }),
        })
      } catch {}
    }
    setCompleted(c => c + 1)
    setShowAnswer(false)
    setCurrentIdx(i => i + 1)
  }

  if (loading) {
    return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>
  }

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-y-auto">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">{t('nav.poker.drill')}</h1>
            <p className="text-xs text-zinc-500">{dueItems.length} 個概念待練習</p>
          </div>
          {planStats && (
            <div className="flex items-center gap-3 text-[10px] text-zinc-500">
              <span>掌握 {planStats.mastered}/{planStats.total_concepts}</span>
              <span>待複習 {planStats.due_review}</span>
            </div>
          )}
        </div>

        {/* Progress */}
        <div className="mb-6">
          <div className="flex items-center justify-between text-[10px] text-zinc-500 mb-1">
            <span>進度</span>
            <span>{completed}/{dueItems.length}</span>
          </div>
          <div className="h-2 rounded-full bg-zinc-800">
            <div className="h-2 rounded-full bg-blue-600 transition-all" style={{ width: `${(completed / Math.max(dueItems.length, 1)) * 100}%` }} />
          </div>
        </div>

        {/* Current Card */}
        {current ? (
          <div className="rounded-xl border border-zinc-700 bg-zinc-800/50 p-6 mb-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] px-2 py-0.5 rounded border ${current.drill_type === 'review' ? 'text-amber-400 border-amber-500/40 bg-amber-950/50' : current.drill_type === 'weakness' ? 'text-red-400 border-red-500/40 bg-red-950/50' : 'text-blue-400 border-blue-500/40 bg-blue-950/50'}`}>
                  {current.drill_type === 'review' ? '複習' : current.drill_type === 'weakness' ? '弱點' : '新概念'}
                </span>
                <span className="text-xs text-zinc-400">{current.category}</span>
              </div>
              <span className="text-[10px] text-amber-400">{difficultyStars(current.difficulty || 1)}</span>
            </div>

            {/* Concept Name */}
            <h2 className="text-xl font-bold text-zinc-100 mb-2">{current.concept_name || current.concept_code}</h2>

            {/* Mastery */}
            {current.mastery_level != null && (
              <div className="flex items-center gap-2 mb-4">
                <div className="flex-1 h-1.5 rounded-full bg-zinc-800">
                  <div className={`h-1.5 rounded-full ${current.mastery_level >= 0.7 ? 'bg-emerald-500' : current.mastery_level >= 0.3 ? 'bg-amber-500' : 'bg-red-500'}`} style={{ width: `${current.mastery_level * 100}%` }} />
                </div>
                <span className="text-[10px] text-zinc-500">{(current.mastery_level * 100).toFixed(0)}%</span>
              </div>
            )}

            {/* Question Area */}
            {!showAnswer ? (
              <div className="text-center py-8">
                <p className="text-sm text-zinc-400 mb-4">你能解釋「{current.concept_name || current.concept_code}」嗎？</p>
                <p className="text-xs text-zinc-500 mb-6">{current.reason || '思考這個概念的核心要點'}</p>
                <button onClick={() => setShowAnswer(true)} className="rounded bg-zinc-700 px-6 py-2.5 text-sm text-zinc-200 hover:bg-zinc-600">顯示答案</button>
              </div>
            ) : (
              <div>
                <div className="bg-zinc-900 rounded-lg p-4 mb-4">
                  <p className="text-xs text-zinc-300 whitespace-pre-wrap">
                    {current.description || `這是 ${current.category} 類別的概念，難度 ${current.difficulty || 1}/5。`}
                  </p>
                </div>

                {/* Grade Buttons */}
                <div className="grid grid-cols-4 gap-2">
                  {gradeLabels.map(g => (
                    <button key={g.grade} onClick={() => handleGrade(g.grade)} className={`rounded px-3 py-2.5 text-sm text-white ${g.color}`}>
                      <div className="font-medium">{g.label}</div>
                      <div className="text-[10px] opacity-70">{g.key}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-16 rounded-xl border border-dashed border-zinc-700">
            <div className="text-3xl mb-3">🎉</div>
            <p className="text-zinc-300 text-sm mb-1">
              {completed > 0 ? `完成 ${completed} 個概念練習！` : '目前沒有待練習的概念'}
            </p>
            <p className="text-zinc-500 text-xs">
              {completed > 0 ? '繼續保持，明天再來' : '先上傳手牌或進行對話來觸發概念學習'}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

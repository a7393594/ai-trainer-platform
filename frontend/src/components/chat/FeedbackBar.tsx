'use client'

/**
 * FeedbackBar — AI 輸出回饋列
 * 每則 AI 訊息下方顯示：✓ 正確 / △ 部分正確 / ✗ 錯誤 + 修正輸入框
 */

import { useState } from 'react'
import type { Rating } from '@/types'

interface FeedbackBarProps {
  messageId: string
  onFeedback: (messageId: string, rating: Rating, correction?: string) => void
}

export function FeedbackBar({ messageId, onFeedback }: FeedbackBarProps) {
  const [rating, setRating] = useState<Rating | null>(null)
  const [showCorrection, setShowCorrection] = useState(false)
  const [correction, setCorrection] = useState('')

  const handleRate = (r: Rating) => {
    setRating(r)
    if (r === 'wrong' || r === 'partial') {
      setShowCorrection(true)
    } else {
      onFeedback(messageId, r)
    }
  }

  const handleSubmitCorrection = () => {
    if (rating) {
      onFeedback(messageId, rating, correction)
      setShowCorrection(false)
    }
  }

  if (rating && !showCorrection) {
    return (
      <div className="mt-2 text-xs text-zinc-500">
        已回饋：{rating === 'correct' ? '✓ 正確' : rating === 'partial' ? '△ 部分正確' : '✗ 錯誤'}
      </div>
    )
  }

  return (
    <div className="mt-2 border-t border-zinc-700 pt-2">
      {!rating && (
        <div className="flex gap-2">
          <button
            onClick={() => handleRate('correct')}
            className="rounded px-2 py-1 text-xs text-green-400 hover:bg-green-400/10 transition-colors"
          >
            ✓ 正確
          </button>
          <button
            onClick={() => handleRate('partial')}
            className="rounded px-2 py-1 text-xs text-yellow-400 hover:bg-yellow-400/10 transition-colors"
          >
            △ 部分正確
          </button>
          <button
            onClick={() => handleRate('wrong')}
            className="rounded px-2 py-1 text-xs text-red-400 hover:bg-red-400/10 transition-colors"
          >
            ✗ 錯誤
          </button>
        </div>
      )}

      {showCorrection && (
        <div className="mt-2 flex flex-col gap-2">
          <textarea
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            placeholder="正確的回答應該是..."
            className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-blue-500 placeholder:text-zinc-500"
            rows={2}
          />
          <button
            onClick={handleSubmitCorrection}
            className="self-end rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-500"
          >
            送出修正
          </button>
        </div>
      )}
    </div>
  )
}

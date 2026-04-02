'use client'

interface OnboardingProgressProps {
  current: number
  total: number
}

export function OnboardingProgress({ current, total }: OnboardingProgressProps) {
  const pct = Math.round((current / total) * 100)

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-zinc-800/50 border-b border-zinc-700">
      <span className="text-xs text-zinc-400 whitespace-nowrap">
        第 {current} / {total} 題
      </span>
      <div className="flex-1 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-500 rounded-full transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-zinc-500">{pct}%</span>
    </div>
  )
}

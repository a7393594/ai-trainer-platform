'use client'

import Link from 'next/link'

interface Step {
  label: string
  href: string
  done?: boolean
}

interface EmptyStateProps {
  icon: string
  title: string
  description: string
  steps?: Step[]
  action?: { label: string; href: string }
}

/**
 * Guided empty state component.
 * Shows when a page has no data, with next-step suggestions.
 */
export function EmptyState({ icon, title, description, steps, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
      <div className="text-4xl">{icon}</div>
      <div>
        <h3 className="text-sm font-medium text-zinc-200 mb-1">{title}</h3>
        <p className="text-xs text-zinc-500 max-w-md">{description}</p>
      </div>

      {steps && steps.length > 0 && (
        <div className="mt-2 space-y-1.5 w-full max-w-sm">
          {steps.map((step, i) => (
            <Link key={i} href={step.href}
              className={`flex items-center gap-3 rounded-lg px-4 py-2.5 text-left transition-colors ${
                step.done
                  ? 'bg-zinc-800/30 text-zinc-500'
                  : 'bg-zinc-800 text-zinc-200 hover:bg-zinc-700 border border-zinc-700'
              }`}>
              <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] ${
                step.done ? 'bg-green-500/20 text-green-400' : 'bg-blue-500/20 text-blue-400'
              }`}>
                {step.done ? '✓' : i + 1}
              </span>
              <span className={`text-xs ${step.done ? 'line-through' : ''}`}>{step.label}</span>
            </Link>
          ))}
        </div>
      )}

      {action && (
        <Link href={action.href} className="rounded-lg bg-blue-600 px-5 py-2 text-sm text-white hover:bg-blue-500 mt-2">
          {action.label}
        </Link>
      )}
    </div>
  )
}

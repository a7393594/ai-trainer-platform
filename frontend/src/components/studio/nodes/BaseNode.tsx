'use client'

import { Handle, Position } from '@xyflow/react'
import type { ReactNode } from 'react'
import type { NodeSpan } from '@/lib/studio/types'
import { formatCost, formatDuration } from '@/lib/studio/graph'

interface BaseNodeProps {
  span: NodeSpan
  icon: string
  accent: string          // Tailwind class e.g. 'border-blue-500/60 bg-blue-950/40'
  showHandles?: boolean
  children?: ReactNode
}

/**
 * 所有 studio 節點共用的外殼 —— 固定尺寸、圖示、狀態色、成本/延遲 chip。
 */
export default function BaseNode({
  span,
  icon,
  accent,
  showHandles = true,
  children,
}: BaseNodeProps) {
  const statusColor =
    span.status === 'error'
      ? 'border-red-500/80 bg-red-950/30'
      : span.status === 'running'
      ? 'border-amber-500/60 bg-amber-950/20'
      : accent

  return (
    <div
      className={`w-[220px] rounded-xl border-2 px-3 py-2.5 text-xs shadow-lg backdrop-blur ${statusColor}`}
    >
      {showHandles && (
        <Handle
          type="target"
          position={Position.Top}
          className="!h-2 !w-2 !bg-zinc-400"
        />
      )}

      <div className="flex items-center gap-2">
        <span className="text-lg leading-none">{icon}</span>
        <span className="truncate font-medium text-zinc-100">{span.label}</span>
      </div>

      {children}

      <div className="mt-2 flex items-center justify-between text-[10px] text-zinc-400">
        <span>{formatDuration(span.latency_ms)}</span>
        <span>{formatCost(span.cost_usd)}</span>
      </div>

      {showHandles && (
        <Handle
          type="source"
          position={Position.Bottom}
          className="!h-2 !w-2 !bg-zinc-400"
        />
      )}
    </div>
  )
}

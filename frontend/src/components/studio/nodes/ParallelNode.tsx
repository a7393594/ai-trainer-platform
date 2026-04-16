'use client'

import type { NodeProps } from '@xyflow/react'
import BaseNode from './BaseNode'
import type { StudioNodeData } from '@/lib/studio/graph'

export default function ParallelNode({ data }: NodeProps) {
  const span = (data as StudioNodeData).span
  const output = span.output_ref as { tool_count?: number } | null
  return (
    <BaseNode
      span={span}
      icon="⚡"
      accent="border-amber-500/70 bg-amber-950/40"
      showHandles
    >
      {typeof output?.tool_count === 'number' && (
        <p className="mt-1 text-[11px] text-amber-200">
          {output.tool_count} parallel tool call(s)
        </p>
      )}
    </BaseNode>
  )
}

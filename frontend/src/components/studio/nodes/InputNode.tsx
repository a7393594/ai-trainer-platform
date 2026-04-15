'use client'

import type { NodeProps } from '@xyflow/react'
import BaseNode from './BaseNode'
import type { StudioNodeData } from '@/lib/studio/graph'

export default function InputNode({ data }: NodeProps) {
  const span = (data as StudioNodeData).span
  const input = span.input_ref as { message?: string } | null
  return (
    <BaseNode
      span={span}
      icon="📥"
      accent="border-sky-500/60 bg-sky-950/40"
      showHandles
    >
      {input?.message && (
        <p className="mt-1.5 line-clamp-2 text-[11px] text-zinc-300">
          {input.message}
        </p>
      )}
    </BaseNode>
  )
}

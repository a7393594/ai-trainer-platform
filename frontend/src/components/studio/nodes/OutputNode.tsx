'use client'

import type { NodeProps } from '@xyflow/react'
import BaseNode from './BaseNode'
import type { StudioNodeData } from '@/lib/studio/graph'

export default function OutputNode({ data }: NodeProps) {
  const span = (data as StudioNodeData).span
  const output = span.output_ref as { content_preview?: string } | null
  return (
    <BaseNode
      span={span}
      icon="📤"
      accent="border-emerald-500/70 bg-emerald-950/40"
      showHandles
    >
      {output?.content_preview && (
        <p className="mt-1.5 line-clamp-2 text-[11px] text-emerald-200">
          {output.content_preview}
        </p>
      )}
    </BaseNode>
  )
}

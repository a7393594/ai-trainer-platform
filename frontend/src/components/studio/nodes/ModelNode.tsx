'use client'

import type { NodeProps } from '@xyflow/react'
import BaseNode from './BaseNode'
import type { StudioNodeData } from '@/lib/studio/graph'

export default function ModelNode({ data }: NodeProps) {
  const span = (data as StudioNodeData).span
  const iterCount = (span.metadata as Record<string, unknown>)?.tool_call_count as number | undefined
  return (
    <BaseNode
      span={span}
      icon="🤖"
      accent="border-violet-500/70 bg-violet-950/40"
      showHandles
    >
      {span.model && (
        <div className="mt-1 flex items-center gap-1">
          <span className="truncate rounded bg-violet-900/60 px-1.5 py-0.5 text-[10px] text-violet-200">
            {span.model.replace(/-\d{8}$/, '')}
          </span>
          {typeof iterCount === 'number' && iterCount > 0 && (
            <span className="rounded bg-amber-900/60 px-1.5 py-0.5 text-[10px] text-amber-200">
              +{iterCount} tool
            </span>
          )}
        </div>
      )}
      <div className="mt-1 text-[10px] text-zinc-400">
        {span.tokens_in} → {span.tokens_out} tokens
      </div>
    </BaseNode>
  )
}

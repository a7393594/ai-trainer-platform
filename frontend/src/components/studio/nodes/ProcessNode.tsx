'use client'

import type { NodeProps } from '@xyflow/react'
import BaseNode from './BaseNode'
import type { StudioNodeData } from '@/lib/studio/graph'

export default function ProcessNode({ data }: NodeProps) {
  const span = (data as StudioNodeData).span
  return (
    <BaseNode
      span={span}
      icon="⚙️"
      accent="border-zinc-600/60 bg-zinc-900/60"
      showHandles
    />
  )
}

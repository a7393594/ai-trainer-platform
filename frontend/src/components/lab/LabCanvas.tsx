'use client'

import PipelineCanvas from '@/components/studio/PipelineCanvas'
import type {
  LabSourceType,
  NodeSpan,
  PipelineRunDetail,
} from '@/lib/studio/types'

interface Props {
  sourceType: LabSourceType
  pipelineDetail: PipelineRunDetail | null
  loading: boolean
  error: string | null
  selectedNodeId: string | null
  onSelectNode: (span: NodeSpan | null) => void
}

export default function LabCanvas({
  sourceType,
  pipelineDetail,
  loading,
  error,
  selectedNodeId,
  onSelectNode,
}: Props) {
  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-zinc-500">
        <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
        載入中…
      </div>
    )
  }
  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-red-400">
        {error}
      </div>
    )
  }

  if (sourceType === 'pipeline') {
    return (
      <div className="relative flex-1">
        <PipelineCanvas
          nodesJson={pipelineDetail?.nodes_json ?? null}
          selectedNodeId={selectedNodeId}
          onSelectNode={onSelectNode}
        />
      </div>
    )
  }

  // workflow / session / comparison — lightweight placeholder canvas
  const hint =
    sourceType === 'workflow'
      ? '點右側「Workflow」頁可編輯 steps_json 後重跑'
      : sourceType === 'session'
        ? '這是對話案例 — 於右側調整 prompt / 工具 / 知識後點 Run 即可重現'
        : '這是多模型比較案例 — 於右側調整後點 Run 再比一次'

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6">
        <p className="mb-2 text-sm text-zinc-200">
          {sourceType === 'workflow'
            ? '🔄 Workflow 案例'
            : sourceType === 'session'
              ? '💬 對話案例'
              : '⚖️ 比較案例'}
        </p>
        <p className="max-w-sm text-xs text-zinc-500">{hint}</p>
      </div>
    </div>
  )
}

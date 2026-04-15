'use client'

import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { getDemoContext } from '@/lib/ai-engine'
import {
  deletePipelineRun,
  forkToLab,
  getPipelineRunDetail,
  listPipelineRuns,
} from '@/lib/studio/api'
import type {
  NodeSpan,
  PipelineComparison,
  PipelineRunDetail,
  PipelineRunSummary,
} from '@/lib/studio/types'
import CostDashboard from '@/components/studio/CostDashboard'
import PipelineCanvas from '@/components/studio/PipelineCanvas'
import NodeInspector from '@/components/studio/NodeInspector'
import RunList from '@/components/studio/RunList'
import type { DemoContext } from '@/types'

export default function StudioPage() {
  const { user } = useAuth()
  const [context, setContext] = useState<DemoContext | null>(null)
  const [ctxError, setCtxError] = useState<string | null>(null)

  const [runs, setRuns] = useState<PipelineRunSummary[]>([])
  const [listLoading, setListLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)

  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [runDetail, setRunDetail] = useState<PipelineRunDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  const [comparisonsByNode, setComparisonsByNode] = useState<
    Record<string, PipelineComparison[]>
  >({})

  const [selectedSpan, setSelectedSpan] = useState<NodeSpan | null>(null)
  const [forking, setForking] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // 1. 載入 project context
  useEffect(() => {
    getDemoContext(user?.email || undefined)
      .then(setContext)
      .catch((err) => setCtxError(err.message))
  }, [user])

  // 2. 載入 runs 列表
  const fetchRuns = useCallback(async () => {
    if (!context) return
    setListLoading(true)
    setListError(null)
    try {
      const res = await listPipelineRuns(context.project_id, { limit: 50 })
      setRuns(res.runs)
      // 預設選第一筆
      if (res.runs.length > 0 && !selectedRunId) {
        setSelectedRunId(res.runs[0].id)
      }
    } catch (err) {
      setListError(err instanceof Error ? err.message : String(err))
    } finally {
      setListLoading(false)
    }
  }, [context, selectedRunId])

  useEffect(() => {
    fetchRuns()
  }, [fetchRuns])

  // 3. 載入選中 run 的詳細 + comparisons
  useEffect(() => {
    if (!selectedRunId) {
      setRunDetail(null)
      setComparisonsByNode({})
      return
    }
    setDetailLoading(true)
    setDetailError(null)
    setSelectedSpan(null)
    getPipelineRunDetail(selectedRunId)
      .then((res) => {
        setRunDetail(res.run)
        setComparisonsByNode(res.comparisons_by_node || {})
      })
      .catch((err) =>
        setDetailError(err instanceof Error ? err.message : String(err))
      )
      .finally(() => setDetailLoading(false))
  }, [selectedRunId])

  // Fork 當前 run 成 Lab run
  const handleForkToLab = useCallback(async () => {
    if (!runDetail || !context) return
    setForking(true)
    try {
      const res = await forkToLab(context.project_id, runDetail.id)
      // 重新抓列表並切到新的 lab run
      await fetchRuns()
      setSelectedRunId(res.run.id)
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : String(err))
    } finally {
      setForking(false)
    }
  }, [runDetail, context, fetchRuns])

  // 刪除當前 lab run
  const handleDeleteLabRun = useCallback(async () => {
    if (!runDetail || runDetail.mode !== 'lab') return
    if (!confirm('確定刪除這個 Lab run?此動作無法復原。')) return
    setDeleting(true)
    try {
      await deletePipelineRun(runDetail.id)
      // 切換到另一個 run(或清空)
      setSelectedRunId(null)
      setRunDetail(null)
      setSelectedSpan(null)
      await fetchRuns()
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : String(err))
    } finally {
      setDeleting(false)
    }
  }, [runDetail, fetchRuns])

  // 當前節點的 comparisons
  const currentComparisons = selectedSpan
    ? comparisonsByNode[selectedSpan.id] || []
    : []

  const setCurrentComparisons = useCallback(
    (rows: PipelineComparison[]) => {
      if (!selectedSpan) return
      setComparisonsByNode((prev) => ({ ...prev, [selectedSpan.id]: rows }))
    },
    [selectedSpan]
  )

  if (ctxError) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-900">
        <div className="rounded-lg border border-red-800 bg-red-900/20 p-6 text-center">
          <p className="text-sm text-red-400">無法連接後端</p>
          <p className="mt-1 text-xs text-zinc-500">{ctxError}</p>
          <p className="mt-3 text-xs text-zinc-400">
            請確認 ait-backend 已啟動(port 8000)
          </p>
        </div>
      </div>
    )
  }

  if (!context) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-900">
        <div className="flex items-center gap-2 text-zinc-400">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
          <span className="text-sm">載入中…</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-zinc-900">
      <CostDashboard
        run={runDetail}
        canForkToLab={!!runDetail && runDetail.mode === 'live'}
        forking={forking}
        onForkToLab={handleForkToLab}
        onDeleteLabRun={handleDeleteLabRun}
        deleting={deleting}
      />

      <div className="flex flex-1 overflow-hidden">
        <RunList
          runs={runs}
          selectedId={selectedRunId}
          loading={listLoading}
          error={listError}
          onSelect={setSelectedRunId}
          onRefresh={fetchRuns}
        />

        <main className="relative flex min-h-0 flex-1">
          {detailLoading ? (
            <div className="flex flex-1 items-center justify-center text-sm text-zinc-500">
              <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
              載入 run 詳細…
            </div>
          ) : detailError ? (
            <div className="flex flex-1 items-center justify-center text-sm text-red-400">
              {detailError}
            </div>
          ) : (
            <div className="flex-1">
              <PipelineCanvas
                nodesJson={runDetail?.nodes_json ?? null}
                selectedNodeId={selectedSpan?.id ?? null}
                onSelectNode={setSelectedSpan}
              />
            </div>
          )}
        </main>

        <NodeInspector
          span={selectedSpan}
          runId={runDetail?.id ?? null}
          runMode={runDetail?.mode ?? null}
          comparisons={currentComparisons}
          onComparisonsChange={setCurrentComparisons}
          onClose={() => setSelectedSpan(null)}
        />
      </div>
    </div>
  )
}

'use client'

import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  type Node,
  type NodeMouseHandler,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import InputNode from './nodes/InputNode'
import ProcessNode from './nodes/ProcessNode'
import ModelNode from './nodes/ModelNode'
import ParallelNode from './nodes/ParallelNode'
import OutputNode from './nodes/OutputNode'
import { layoutPipeline, type StudioNodeData } from '@/lib/studio/graph'
import type { NodeSpan, NodesJson } from '@/lib/studio/types'

const nodeTypes = {
  inputNode: InputNode,
  processNode: ProcessNode,
  modelNode: ModelNode,
  parallelNode: ParallelNode,
  outputNode: OutputNode,
}

interface PipelineCanvasProps {
  nodesJson: NodesJson | null
  selectedNodeId: string | null
  onSelectNode: (span: NodeSpan | null) => void
}

export default function PipelineCanvas({
  nodesJson,
  selectedNodeId,
  onSelectNode,
}: PipelineCanvasProps) {
  const { nodes, edges } = useMemo(() => {
    if (!nodesJson) return { nodes: [], edges: [] }
    return layoutPipeline(nodesJson)
  }, [nodesJson])

  const styledNodes = useMemo(
    () =>
      nodes.map((n) => ({
        ...n,
        className: n.id === selectedNodeId ? 'ring-2 ring-blue-400 rounded-xl' : '',
      })),
    [nodes, selectedNodeId]
  )

  const handleNodeClick: NodeMouseHandler = (_evt, node) => {
    const data = (node as Node<StudioNodeData>).data
    onSelectNode(data.span)
  }

  const handlePaneClick = () => onSelectNode(null)

  // 延遲渲染 React Flow 直到父容器有非零尺寸,避免 React Flow 回報
  // "parent container needs width and height" warning。
  const wrapperRef = useRef<HTMLDivElement>(null)
  const [hasSize, setHasSize] = useState(false)
  useLayoutEffect(() => {
    const el = wrapperRef.current
    if (!el) return
    const check = () => {
      const rect = el.getBoundingClientRect()
      if (rect.width > 0 && rect.height > 0) {
        setHasSize(true)
      }
    }
    check()
    const ro = new ResizeObserver(check)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  if (!nodesJson || !nodesJson.nodes.length) {
    return (
      <div className="absolute inset-0 flex items-center justify-center text-sm text-zinc-500">
        尚未選取 pipeline run,從左側列表挑一筆
      </div>
    )
  }

  return (
    <div ref={wrapperRef} className="absolute inset-0">
      {hasSize && (
        <ReactFlowProvider>
          <ReactFlow
            nodes={styledNodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.25 }}
            proOptions={{ hideAttribution: true }}
            onNodeClick={handleNodeClick}
            onPaneClick={handlePaneClick}
            nodesDraggable={false}
            panOnDrag
            zoomOnScroll
          >
            <Background color="#3f3f46" gap={20} />
            <Controls
              className="!bg-zinc-900/80 !border-zinc-700 [&_button]:!bg-zinc-800 [&_button]:!border-zinc-700 [&_button]:!text-zinc-200"
              showInteractive={false}
            />
          </ReactFlow>
        </ReactFlowProvider>
      )}
    </div>
  )
}

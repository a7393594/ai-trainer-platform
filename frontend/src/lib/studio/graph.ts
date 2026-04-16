/**
 * Pipeline Studio — Graph 轉換工具
 * 把後端傳來的 nodes_json 轉成 React Flow 可用的 {nodes, edges}
 * 並做自動 layout(垂直鏈式,支援 parallel 並排)。
 */
import type { Edge, Node } from '@xyflow/react'
import type { NodeSpan, NodesJson } from './types'

const NODE_WIDTH = 220
const NODE_HEIGHT = 96
const V_GAP = 48
const H_GAP = 32

export interface StudioNodeData extends Record<string, unknown> {
  span: NodeSpan
}

export interface LayoutResult {
  nodes: Node<StudioNodeData>[]
  edges: Edge[]
}

/**
 * 垂直鏈式 layout:
 * - 按 started_at_ms 排序
 * - 有 parent_id 的節點水平排在 parent 旁邊(parallel 子節點)
 * - 其他節點依序垂直往下排
 */
export function layoutPipeline(nodesJson: NodesJson): LayoutResult {
  const spans = [...(nodesJson?.nodes ?? [])].sort(
    (a, b) => a.started_at_ms - b.started_at_ms
  )
  const edgesIn = nodesJson?.edges ?? []

  // 分出根層節點(parent_id 為 null)和子節點
  const rootSpans = spans.filter((s) => !s.parent_id)
  const childByParent: Record<string, NodeSpan[]> = {}
  spans
    .filter((s) => s.parent_id)
    .forEach((s) => {
      const key = s.parent_id as string
      if (!childByParent[key]) childByParent[key] = []
      childByParent[key].push(s)
    })

  const positioned: Node<StudioNodeData>[] = []
  let y = 0
  for (const span of rootSpans) {
    positioned.push({
      id: span.id,
      type: reactFlowTypeFor(span.type),
      position: { x: 0, y },
      data: { span },
      draggable: false,
    })
    // 把這個 root 的子節點水平排到右邊
    const children = childByParent[span.id] || []
    children.forEach((c, i) => {
      positioned.push({
        id: c.id,
        type: reactFlowTypeFor(c.type),
        position: {
          x: NODE_WIDTH + H_GAP + (NODE_WIDTH + H_GAP) * i,
          y,
        },
        data: { span: c },
        draggable: false,
      })
    })
    y += NODE_HEIGHT + V_GAP
  }

  // 產生 edges
  const edges: Edge[] = []
  // 1. 後端傳來的顯式 edges
  edgesIn.forEach((e, i) => {
    edges.push({
      id: `e-${i}`,
      source: e.from,
      target: e.to,
      animated: false,
      style: { stroke: '#3b82f6', strokeWidth: 2 },
    })
  })
  // 2. 顯式 edges 沒涵蓋到的 root 鏈條,用隱式順序連起來
  const edgeSet = new Set(edges.map((e) => `${e.source}->${e.target}`))
  for (let i = 0; i < rootSpans.length - 1; i++) {
    const a = rootSpans[i]
    const b = rootSpans[i + 1]
    const key = `${a.id}->${b.id}`
    if (!edgeSet.has(key)) {
      edges.push({
        id: `chain-${i}`,
        source: a.id,
        target: b.id,
        style: { stroke: '#52525b', strokeWidth: 2, strokeDasharray: '4 4' },
      })
    }
  }

  return { nodes: positioned, edges }
}

function reactFlowTypeFor(spanType: NodeSpan['type']): string {
  switch (spanType) {
    case 'input':
      return 'inputNode'
    case 'process':
      return 'processNode'
    case 'model':
      return 'modelNode'
    case 'parallel':
      return 'parallelNode'
    case 'tool':
      return 'processNode'
    case 'output':
      return 'outputNode'
    default:
      return 'processNode'
  }
}

export function formatCost(usd: number): string {
  if (usd < 0.0001) return '$<0.0001'
  if (usd < 0.01) return `$${usd.toFixed(5)}`
  return `$${usd.toFixed(4)}`
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

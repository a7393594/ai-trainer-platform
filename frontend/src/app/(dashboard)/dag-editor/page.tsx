'use client'

/**
 * /dag-editor — 視覺化 DAG 編輯器
 *
 * 使用 @xyflow/react 讓使用者：
 * - 看到當前 DAG 的節點與連線
 * - 拖拉節點移動位置
 * - 從左側 palette 拖入新節點類型
 * - 連接/斷開節點
 * - 儲存為新版本
 * - 切換 active DAG
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Background, Controls, ReactFlow, ReactFlowProvider,
  addEdge, applyEdgeChanges, applyNodeChanges,
  type Node, type Edge, type Connection, type NodeChange, type EdgeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useProject } from '@/lib/project-context'
import {
  getActiveDag, listDags, listNodeTypes, createDag, updateDag, activateDag, deleteDag,
  type PipelineDAG, type NodeType, type DAGNode, type DAGEdge,
} from '@/lib/studio/api'

interface XYNodeData extends Record<string, unknown> {
  label: string
  icon?: string
  typeKey: string
  category?: string
}

export default function DAGEditorPage() {
  const { currentProject } = useProject()
  const projectId = currentProject?.project_id

  const [allDags, setAllDags] = useState<PipelineDAG[]>([])
  const [currentDag, setCurrentDag] = useState<PipelineDAG | null>(null)
  const [nodeTypes, setNodeTypes] = useState<NodeType[]>([])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [nodes, setNodes] = useState<Node<XYNodeData>[]>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  // Load DAGs and node types on mount
  useEffect(() => {
    if (!projectId) return
    Promise.all([
      listDags(projectId),
      listNodeTypes(),
      getActiveDag(projectId).catch(() => null),
    ]).then(([dagsRes, typesRes, activeRes]) => {
      setAllDags(dagsRes.dags || [])
      setNodeTypes(typesRes.node_types || [])
      if (activeRes?.dag) {
        loadDag(activeRes.dag)
      } else if (dagsRes.dags?.[0]) {
        loadDag(dagsRes.dags[0])
      }
    }).catch(() => {})
  }, [projectId])

  const loadDag = (dag: PipelineDAG) => {
    setCurrentDag(dag)
    const xyNodes: Node<XYNodeData>[] = (dag.nodes || []).map((n, idx) => ({
      id: n.id,
      type: 'default',
      position: n.position || { x: idx * 180, y: 0 },
      data: {
        label: n.label,
        icon: nodeTypes.find((t) => t.type_key === n.type_key)?.icon || '⚙️',
        typeKey: n.type_key,
        category: nodeTypes.find((t) => t.type_key === n.type_key)?.category,
      },
      style: {
        background: '#18181b',
        color: '#e4e4e7',
        border: '2px solid #52525b',
        borderRadius: 8,
        padding: 8,
        fontSize: 11,
      },
    }))
    const xyEdges: Edge[] = (dag.edges || []).map((e, idx) => ({
      id: `e-${idx}`,
      source: e.from,
      target: e.to,
      animated: true,
      style: { stroke: '#52525b' },
    }))
    setNodes(xyNodes)
    setEdges(xyEdges)
    setDirty(false)
  }

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((nds) => applyNodeChanges(changes, nds) as Node<XYNodeData>[])
    setDirty(true)
  }, [])

  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    setEdges((eds) => applyEdgeChanges(changes, eds))
    setDirty(true)
  }, [])

  const onConnect = useCallback((conn: Connection) => {
    setEdges((eds) => addEdge({ ...conn, animated: true, style: { stroke: '#52525b' } }, eds))
    setDirty(true)
  }, [])

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const typeKey = e.dataTransfer.getData('application/node-type')
    if (!typeKey) return
    const type = nodeTypes.find((t) => t.type_key === typeKey)
    if (!type) return

    // Rough drop position
    const bounds = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const position = {
      x: e.clientX - bounds.left,
      y: e.clientY - bounds.top,
    }

    const newId = `n${Date.now()}`
    const newNode: Node<XYNodeData> = {
      id: newId,
      type: 'default',
      position,
      data: {
        label: type.name,
        icon: type.icon,
        typeKey: type.type_key,
        category: type.category,
      },
      style: {
        background: '#18181b',
        color: '#e4e4e7',
        border: '2px solid #3b82f6',
        borderRadius: 8,
        padding: 8,
        fontSize: 11,
      },
    }
    setNodes((nds) => [...nds, newNode])
    setDirty(true)
  }, [nodeTypes])

  // Group node types by category for palette
  const typesByCat = useMemo(() => {
    const g: Record<string, NodeType[]> = {}
    for (const t of nodeTypes) {
      const cat = t.category || 'other'
      ;(g[cat] ||= []).push(t)
    }
    return g
  }, [nodeTypes])

  const handleSaveAsNew = async () => {
    if (!projectId || !currentDag) return
    setSaving(true)
    setNotice(null)
    try {
      // Serialize xy nodes/edges back to DAG format
      const dagNodes: DAGNode[] = nodes.map((n) => {
        const original = currentDag.nodes.find((on) => on.id === n.id)
        return {
          id: n.id,
          type_key: (n.data as XYNodeData).typeKey,
          label: (n.data as XYNodeData).label,
          config: original?.config || {},
          position: n.position,
        }
      })
      const dagEdges: DAGEdge[] = edges.map((e) => ({ from: e.source, to: e.target }))

      const res = await createDag({
        project_id: projectId,
        name: `${currentDag.name} v${currentDag.version + 1}`,
        nodes: dagNodes,
        edges: dagEdges,
        description: 'Edited in DAG editor',
        activate: false,
      })
      setNotice(`已儲存為 v${res.dag.version}（未啟用）`)
      const updated = await listDags(projectId)
      setAllDags(updated.dags || [])
      loadDag(res.dag)
    } catch (e) {
      setNotice(e instanceof Error ? e.message : '儲存失敗')
    }
    setSaving(false)
    setTimeout(() => setNotice(null), 4000)
  }

  const handleSaveOverwrite = async () => {
    if (!currentDag) return
    setSaving(true)
    setNotice(null)
    try {
      const dagNodes: DAGNode[] = nodes.map((n) => {
        const original = currentDag.nodes.find((on) => on.id === n.id)
        return {
          id: n.id,
          type_key: (n.data as XYNodeData).typeKey,
          label: (n.data as XYNodeData).label,
          config: original?.config || {},
          position: n.position,
        }
      })
      const dagEdges: DAGEdge[] = edges.map((e) => ({ from: e.source, to: e.target }))
      const res = await updateDag(currentDag.id, { nodes: dagNodes, edges: dagEdges })
      setCurrentDag(res.dag)
      setDirty(false)
      setNotice('已儲存')
    } catch (e) {
      setNotice(e instanceof Error ? e.message : '儲存失敗')
    }
    setSaving(false)
    setTimeout(() => setNotice(null), 4000)
  }

  const handleActivate = async () => {
    if (!currentDag || !projectId) return
    try {
      await activateDag(currentDag.id)
      const updated = await listDags(projectId)
      setAllDags(updated.dags || [])
      setCurrentDag({ ...currentDag, is_active: true })
      setNotice('已啟用')
    } catch (e) {
      setNotice(e instanceof Error ? e.message : '啟用失敗')
    }
    setTimeout(() => setNotice(null), 4000)
  }

  const handleDelete = async () => {
    if (!currentDag || !projectId) return
    if (currentDag.is_active) { setNotice('無法刪除 active 版本，請先啟用其他版本'); setTimeout(() => setNotice(null), 4000); return }
    if (!confirm(`確定要刪除 ${currentDag.name}？`)) return
    try {
      await deleteDag(currentDag.id)
      const updated = await listDags(projectId)
      setAllDags(updated.dags || [])
      if (updated.dags?.[0]) loadDag(updated.dags[0])
    } catch (e) {
      setNotice(e instanceof Error ? e.message : '刪除失敗')
    }
  }

  const handleSelectedNodeDelete = () => {
    if (!selectedNodeId) return
    setNodes((nds) => nds.filter((n) => n.id !== selectedNodeId))
    setEdges((eds) => eds.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId))
    setSelectedNodeId(null)
    setDirty(true)
  }

  if (!projectId) {
    return <div className="p-6 text-sm text-zinc-500">尚未選擇專案</div>
  }

  return (
    <div className="h-full flex flex-col bg-zinc-900">
      {/* Header */}
      <div className="border-b border-zinc-800 px-4 py-2.5 flex items-center gap-3 flex-wrap">
        <select
          value={currentDag?.id || ''}
          onChange={(e) => {
            const found = allDags.find((d) => d.id === e.target.value)
            if (found) loadDag(found)
          }}
          className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200"
        >
          {allDags.map((d) => (
            <option key={d.id} value={d.id}>
              v{d.version} · {d.name} {d.is_active ? '（啟用中）' : ''}
            </option>
          ))}
        </select>

        {dirty && <span className="text-[10px] text-yellow-400">● 未儲存變更</span>}

        <div className="flex-1" />

        {selectedNodeId && (
          <button onClick={handleSelectedNodeDelete} className="rounded bg-red-600 px-3 py-1.5 text-xs text-white hover:bg-red-500">
            刪除選取節點
          </button>
        )}

        <button
          onClick={handleSaveOverwrite}
          disabled={!dirty || saving || !currentDag}
          className="rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
        >
          {saving ? '儲存中...' : '覆蓋此版本'}
        </button>
        <button
          onClick={handleSaveAsNew}
          disabled={!dirty || saving || !currentDag}
          className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
        >
          儲存為新版本
        </button>
        {currentDag && !currentDag.is_active && (
          <button onClick={handleActivate} className="rounded bg-green-600 px-3 py-1.5 text-xs text-white hover:bg-green-500">
            啟用此版本
          </button>
        )}
        {currentDag && (
          <button onClick={handleDelete} className="text-xs text-zinc-500 hover:text-red-400">
            刪除
          </button>
        )}
      </div>

      {notice && (
        <div className="border-b border-blue-500/30 bg-blue-900/20 px-4 py-2 text-xs text-blue-300">{notice}</div>
      )}

      <div className="flex-1 flex overflow-hidden">
        {/* Node palette (left) */}
        <aside className="w-48 border-r border-zinc-800 bg-zinc-950 overflow-y-auto p-3">
          <p className="text-[10px] uppercase text-zinc-500 mb-2">節點類型</p>
          <p className="text-[9px] text-zinc-600 mb-3">拖拉到畫布新增</p>
          {Object.entries(typesByCat).map(([cat, types]) => (
            <div key={cat} className="mb-3">
              <p className="text-[9px] uppercase text-zinc-500 mb-1">{cat}</p>
              <div className="space-y-1">
                {types.map((t) => (
                  <div
                    key={t.type_key}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData('application/node-type', t.type_key)
                      e.dataTransfer.effectAllowed = 'move'
                    }}
                    className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 cursor-grab hover:border-blue-500 flex items-center gap-1.5"
                    title={t.description}
                  >
                    <span>{t.icon || '⚙️'}</span>
                    <span className="text-[11px] text-zinc-200">{t.name}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </aside>

        {/* Canvas */}
        <div className="flex-1 relative" onDrop={onDrop} onDragOver={onDragOver}>
          <ReactFlowProvider>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={(_, n) => setSelectedNodeId(n.id)}
              onPaneClick={() => setSelectedNodeId(null)}
              fitView
              className="bg-zinc-950"
            >
              <Background color="#27272a" gap={16} />
              <Controls className="!bg-zinc-900 !border-zinc-700" />
            </ReactFlow>
          </ReactFlowProvider>
        </div>

        {/* Info (right) */}
        <aside className="w-64 border-l border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-400 overflow-y-auto">
          <p className="text-[10px] uppercase text-zinc-500 mb-2">使用說明</p>
          <ul className="space-y-1 list-disc pl-4 text-[11px]">
            <li>從左側拖節點到畫布</li>
            <li>拖節點右下方的小圓點連線</li>
            <li>點節點可選取，按「刪除選取節點」移除</li>
            <li>修改後可「覆蓋此版本」或「儲存為新版本」</li>
            <li>新版本預設不啟用，需點「啟用此版本」才會生效</li>
          </ul>
          <p className="text-[10px] uppercase text-zinc-500 mt-4 mb-2">A/B 測試</p>
          <p className="text-[11px]">
            建立新版本後可到 <a href="/dag-compare" className="text-blue-400 hover:underline">DAG 比較</a> 頁面
            用同一批 input 並排測試兩個版本。
          </p>
          {currentDag && (
            <>
              <p className="text-[10px] uppercase text-zinc-500 mt-4 mb-2">當前 DAG</p>
              <dl className="text-[11px] space-y-0.5">
                <div className="flex justify-between"><dt className="text-zinc-500">版本</dt><dd>v{currentDag.version}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">節點數</dt><dd>{nodes.length}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">連線數</dt><dd>{edges.length}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">狀態</dt><dd>{currentDag.is_active ? '啟用中' : '草稿'}</dd></div>
              </dl>
            </>
          )}
        </aside>
      </div>
    </div>
  )
}

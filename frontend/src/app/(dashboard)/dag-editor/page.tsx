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
  testDag,
  type PipelineDAG, type NodeType, type DAGNode, type DAGEdge, type DAGTestResult,
} from '@/lib/studio/api'
import { listTools } from '@/lib/ai-engine'
import { ModelSelector } from '@/components/shared/ModelSelector'

interface XYNodeData extends Record<string, unknown> {
  label: string
  icon?: string
  typeKey: string
  category?: string
}

interface Tool {
  id: string
  name: string
  description?: string
}

export default function DAGEditorPage() {
  const { currentProject } = useProject()
  const projectId = currentProject?.project_id
  const tenantId = currentProject?.tenant_id

  const [allDags, setAllDags] = useState<PipelineDAG[]>([])
  const [currentDag, setCurrentDag] = useState<PipelineDAG | null>(null)
  const [nodeTypes, setNodeTypes] = useState<NodeType[]>([])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [nodes, setNodes] = useState<Node<XYNodeData>[]>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const [nodeConfigs, setNodeConfigs] = useState<Record<string, Record<string, unknown>>>({})
  const [tools, setTools] = useState<Tool[]>([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  // Test DAG state
  const [testModalOpen, setTestModalOpen] = useState(false)
  const [testInput, setTestInput] = useState('K-7-2 flop，我有 AK，對手 check，該怎麼打？')
  const [testRunning, setTestRunning] = useState(false)
  const [testResult, setTestResult] = useState<DAGTestResult | null>(null)
  const [testError, setTestError] = useState<string | null>(null)

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
    // Seed per-node configs from DAG
    const configs: Record<string, Record<string, unknown>> = {}
    for (const n of dag.nodes || []) {
      configs[n.id] = { ...(n.config || {}) }
    }
    setNodeConfigs(configs)
    setNodes(xyNodes)
    setEdges(xyEdges)
    setDirty(false)
    setSelectedNodeId(null)
  }

  useEffect(() => {
    if (!tenantId) return
    listTools(tenantId)
      .then((r: unknown) => setTools(((r as { tools?: Tool[] })?.tools) || []))
      .catch(() => setTools([]))
  }, [tenantId])

  const updateNodeConfig = (nodeId: string, patch: Record<string, unknown>) => {
    setNodeConfigs((prev) => {
      const current = prev[nodeId] || {}
      const merged = { ...current, ...patch }
      // Prune undefined/empty
      const cleaned: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(merged)) {
        if (v === undefined || v === null || v === '') continue
        if (Array.isArray(v) && v.length === 0) continue
        cleaned[k] = v
      }
      return { ...prev, [nodeId]: cleaned }
    })
    setDirty(true)
  }

  const selectedNode = selectedNodeId ? nodes.find((n) => n.id === selectedNodeId) : null
  const selectedNodeType = selectedNode
    ? nodeTypes.find((t) => t.type_key === (selectedNode.data as XYNodeData).typeKey)
    : null

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
    setNodeConfigs((prev) => ({ ...prev, [newId]: {} }))
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
        return {
          id: n.id,
          type_key: (n.data as XYNodeData).typeKey,
          label: (n.data as XYNodeData).label,
          config: nodeConfigs[n.id] || {},
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
        return {
          id: n.id,
          type_key: (n.data as XYNodeData).typeKey,
          label: (n.data as XYNodeData).label,
          config: nodeConfigs[n.id] || {},
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

  const handleTestDag = async () => {
    if (!currentDag) return
    setTestRunning(true)
    setTestError(null)
    setTestResult(null)
    try {
      // If dirty, warn user first
      if (dirty) {
        if (!confirm('當前變更尚未儲存，測試會使用已儲存的版本。是否繼續？')) {
          setTestRunning(false)
          return
        }
      }
      const res = await testDag(currentDag.id, testInput)
      setTestResult(res)
    } catch (e) {
      setTestError(e instanceof Error ? e.message : '測試失敗')
    }
    setTestRunning(false)
  }

  const handleSelectedNodeDelete = () => {
    if (!selectedNodeId) return
    setNodes((nds) => nds.filter((n) => n.id !== selectedNodeId))
    setEdges((eds) => eds.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId))
    setNodeConfigs((prev) => {
      const next = { ...prev }
      delete next[selectedNodeId]
      return next
    })
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
        <button
          onClick={() => setTestModalOpen(true)}
          disabled={!currentDag}
          className="rounded bg-purple-600 px-3 py-1.5 text-xs text-white hover:bg-purple-500 disabled:opacity-50"
          title="用測試 input 跑此 DAG，看每個節點結果"
        >
          ▶ 測試此 DAG
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

        {/* Info / Config (right) */}
        <aside className="w-80 border-l border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-400 overflow-y-auto">
          {selectedNode && selectedNodeType ? (
            <NodeConfigPanel
              node={selectedNode}
              nodeType={selectedNodeType}
              config={nodeConfigs[selectedNode.id] || {}}
              projectDefaultModel={currentProject?.default_model}
              tools={tools}
              onChange={(patch) => updateNodeConfig(selectedNode.id, patch)}
              onLabelChange={(newLabel) => {
                setNodes((nds) => nds.map((n) =>
                  n.id === selectedNode.id
                    ? { ...n, data: { ...(n.data as XYNodeData), label: newLabel } }
                    : n
                ))
                setDirty(true)
              }}
            />
          ) : (
            <>
              <p className="text-[10px] uppercase text-zinc-500 mb-2">使用說明</p>
              <ul className="space-y-1 list-disc pl-4 text-[11px]">
                <li>從左側拖節點到畫布</li>
                <li>拖節點右下方的小圓點連線</li>
                <li>點節點打開右側配置面板</li>
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
            </>
          )}
        </aside>
      </div>

      {/* Test DAG Modal */}
      {testModalOpen && currentDag && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-3xl max-h-[90vh] flex flex-col rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl">
            <div className="flex items-center justify-between border-b border-zinc-700 px-4 py-3">
              <h2 className="text-sm font-medium text-zinc-200">
                測試 DAG：v{currentDag.version} · {currentDag.name}
              </h2>
              <button onClick={() => { setTestModalOpen(false); setTestResult(null); setTestError(null) }} className="text-zinc-500 hover:text-zinc-200">✕</button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              <div>
                <label className="text-[10px] uppercase text-zinc-500 block mb-1">測試 Input</label>
                <textarea
                  value={testInput}
                  onChange={(e) => setTestInput(e.target.value)}
                  rows={3}
                  className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-blue-500"
                />
              </div>
              <button
                onClick={handleTestDag}
                disabled={testRunning || !testInput.trim()}
                className="w-full rounded bg-purple-600 px-3 py-2 text-xs text-white hover:bg-purple-500 disabled:opacity-50"
              >
                {testRunning ? '執行中…' : '▶ 執行'}
              </button>

              {testError && (
                <div className="rounded border border-red-500/50 bg-red-950/30 px-3 py-2 text-xs text-red-300">
                  {testError}
                </div>
              )}

              {testResult && (
                <div className="space-y-3">
                  {/* Summary */}
                  <div className="rounded border border-zinc-700 bg-zinc-800/50 p-3 space-y-1">
                    <div className="flex items-center justify-between text-[10px] text-zinc-400">
                      <span>總覽</span>
                      <span className="font-mono">
                        {testResult.trace.length} 節點 · {testResult.trace.reduce((a, b) => a + (b.latency_ms || 0), 0)}ms · tokens {testResult.total_tokens_in}→{testResult.total_tokens_out}
                      </span>
                    </div>
                    {testResult.guardrail_triggered && (
                      <p className="text-[11px] text-yellow-400">🛡️ Guardrail 觸發</p>
                    )}
                  </div>

                  {/* Final output */}
                  <div>
                    <p className="text-[10px] uppercase text-zinc-500 mb-1">最終輸出</p>
                    <pre className="whitespace-pre-wrap rounded bg-zinc-950 border border-zinc-800 px-3 py-2 text-xs text-emerald-200 max-h-60 overflow-y-auto">
                      {testResult.final_text || '(空)'}
                    </pre>
                    {testResult.widgets.length > 0 && (
                      <p className="text-[10px] text-zinc-500 mt-1">
                        解析出 {testResult.widgets.length} 個 widget
                      </p>
                    )}
                  </div>

                  {/* Trace */}
                  <div>
                    <p className="text-[10px] uppercase text-zinc-500 mb-1">執行 trace</p>
                    <div className="space-y-1">
                      {testResult.trace.map((t, i) => (
                        <div
                          key={`${t.node_id}-${i}`}
                          className={`rounded border px-2 py-1.5 text-[11px] ${
                            t.status === 'error'
                              ? 'border-red-500/50 bg-red-950/20'
                              : t.status === 'skipped'
                              ? 'border-zinc-800 bg-zinc-900/40 opacity-60'
                              : 'border-zinc-700 bg-zinc-800/40'
                          }`}
                        >
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-zinc-500 text-[10px]">#{i + 1}</span>
                            <span className="text-zinc-200 font-medium">{t.label}</span>
                            <span className="text-[9px] text-zinc-600 font-mono">({t.type_key})</span>
                            <div className="flex-1" />
                            <span className={`text-[9px] ${
                              t.status === 'ok' ? 'text-green-400' : t.status === 'error' ? 'text-red-400' : 'text-zinc-500'
                            }`}>
                              {t.status}
                            </span>
                            {t.latency_ms != null && (
                              <span className="text-[9px] text-zinc-500 font-mono">{t.latency_ms}ms</span>
                            )}
                          </div>
                          {t.summary && <p className="text-[10px] text-zinc-400 mt-0.5">{t.summary}</p>}
                          {t.error && <p className="text-[10px] text-red-400 mt-0.5">Error: {t.error}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}


// ============================================================================
// Node Config Panel — dynamic form based on node type's schema.fields
// ============================================================================

interface NodeConfigPanelProps {
  node: Node<XYNodeData>
  nodeType: NodeType
  config: Record<string, unknown>
  projectDefaultModel?: string
  tools: Tool[]
  onChange: (patch: Record<string, unknown>) => void
  onLabelChange: (newLabel: string) => void
}

function NodeConfigPanel({ node, nodeType, config, projectDefaultModel, tools, onChange, onLabelChange }: NodeConfigPanelProps) {
  const fields = nodeType.schema?.fields || []
  const hasCustom = Object.keys(config).length > 0

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="border-b border-zinc-800 pb-2">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xl">{nodeType.icon}</span>
          <div className="flex-1 min-w-0">
            <p className="text-[10px] uppercase text-zinc-500">{nodeType.category} · {nodeType.type_key}</p>
            <p className="text-sm text-zinc-200 font-medium truncate">{nodeType.name}</p>
          </div>
          {hasCustom && <span className="text-[9px] text-blue-400 bg-blue-500/10 rounded px-1.5 py-0.5">已自訂</span>}
        </div>
        {nodeType.description && (
          <p className="text-[10px] text-zinc-500 mt-1">{nodeType.description}</p>
        )}
      </div>

      {/* Label (always editable) */}
      <div>
        <label className="text-[10px] uppercase text-zinc-500 block mb-1">節點名稱（顯示用）</label>
        <input
          type="text"
          value={(node.data as XYNodeData).label}
          onChange={(e) => onLabelChange(e.target.value)}
          className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
        />
      </div>

      {fields.length === 0 && (
        <p className="text-[11px] text-zinc-500 italic">此節點類型沒有可調參數。</p>
      )}

      {/* Dynamic fields */}
      {fields.includes('model') && (
        <div>
          <label className="text-[10px] uppercase text-zinc-500 block mb-1">模型</label>
          <ModelSelector
            value={(config.model as string) || ''}
            onChange={(v) => onChange({ model: v })}
            projectDefault={projectDefaultModel}
            showWarning
            className="w-full"
          />
          {!config.model && (
            <p className="text-[10px] text-zinc-600 mt-1">未設定時使用專案預設（{projectDefaultModel || '...'}）</p>
          )}
        </div>
      )}

      {fields.includes('temperature') && (
        <div>
          <label className="flex items-center justify-between mb-1">
            <span className="text-[10px] uppercase text-zinc-500">Temperature</span>
            <span className="text-[10px] font-mono text-zinc-400">
              {config.temperature != null ? Number(config.temperature).toFixed(2) : '預設 (0.70)'}
            </span>
          </label>
          <input
            type="range"
            min="0" max="2" step="0.05"
            value={Number(config.temperature ?? 0.7)}
            onChange={(e) => onChange({ temperature: parseFloat(e.target.value) })}
            className="w-full accent-blue-500"
          />
          <div className="flex justify-between text-[9px] text-zinc-600">
            <span>0 · 確定</span><span>1 · 平衡</span><span>2 · 創造</span>
          </div>
          {config.temperature != null && (
            <button onClick={() => onChange({ temperature: undefined })} className="mt-1 text-[10px] text-zinc-500 hover:text-zinc-300">
              重設為預設
            </button>
          )}
        </div>
      )}

      {fields.includes('max_tokens') && (
        <div>
          <label className="flex items-center justify-between mb-1">
            <span className="text-[10px] uppercase text-zinc-500">Max Tokens</span>
            <span className="text-[10px] font-mono text-zinc-400">{String(config.max_tokens ?? '預設 (2000)')}</span>
          </label>
          <input
            type="number"
            min="256" max="32000" step="256"
            value={(config.max_tokens as number) ?? ''}
            placeholder="2000"
            onChange={(e) => onChange({ max_tokens: e.target.value ? parseInt(e.target.value, 10) : undefined })}
            className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
          />
        </div>
      )}

      {fields.includes('tool_ids') && (
        <div>
          <label className="block mb-1">
            <span className="text-[10px] uppercase text-zinc-500">可用工具白名單</span>
            <span className="ml-1 text-[9px] text-zinc-600">
              （{((config.tool_ids as string[]) || []).length} / {tools.length}；未選 = 不給工具）
            </span>
          </label>
          {tools.length === 0 ? (
            <p className="text-[10px] text-zinc-600">此 tenant 尚無註冊工具</p>
          ) : (
            <div className="max-h-32 overflow-y-auto space-y-0.5 rounded border border-zinc-800 bg-zinc-900 p-1">
              {tools.map((t) => {
                const selected = ((config.tool_ids as string[]) || []).includes(t.id)
                return (
                  <button
                    key={t.id}
                    onClick={() => {
                      const cur = new Set((config.tool_ids as string[]) || [])
                      if (cur.has(t.id)) cur.delete(t.id)
                      else cur.add(t.id)
                      onChange({ tool_ids: cur.size === 0 ? undefined : Array.from(cur) })
                    }}
                    className={`w-full text-left px-2 py-1 rounded text-[10px] flex items-center gap-1.5 ${
                      selected ? 'bg-blue-500/20 text-blue-300' : 'text-zinc-400 hover:bg-zinc-800'
                    }`}
                  >
                    <span className={`w-3 h-3 rounded border flex items-center justify-center text-[8px] ${
                      selected ? 'bg-blue-500 border-blue-500 text-white' : 'border-zinc-600'
                    }`}>{selected && '✓'}</span>
                    <span className="font-mono">{t.name}</span>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}

      {fields.includes('system_prompt_prefix') && (
        <div>
          <label className="text-[10px] uppercase text-zinc-500 block mb-1">System Prompt 前綴</label>
          <textarea
            value={(config.system_prompt_prefix as string) || ''}
            onChange={(e) => onChange({ system_prompt_prefix: e.target.value })}
            rows={4}
            placeholder="會插入到 active prompt 之前..."
            className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500 resize-y"
          />
        </div>
      )}

      {fields.includes('rag_limit') && (
        <div>
          <label className="flex items-center justify-between mb-1">
            <span className="text-[10px] uppercase text-zinc-500">RAG 取回數量</span>
            <span className="text-[10px] font-mono text-zinc-400">{String(config.rag_limit ?? '預設 (5)')}</span>
          </label>
          <input
            type="number"
            min="0" max="20" step="1"
            value={(config.rag_limit as number) ?? ''}
            placeholder="5"
            onChange={(e) => onChange({ rag_limit: e.target.value ? parseInt(e.target.value, 10) : undefined })}
            className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
          />
          <p className="text-[10px] text-zinc-600 mt-1">0 = 關閉 RAG</p>
        </div>
      )}

      {fields.includes('max_iterations') && (
        <div>
          <label className="flex items-center justify-between mb-1">
            <span className="text-[10px] uppercase text-zinc-500">最大迭代次數</span>
            <span className="text-[10px] font-mono text-zinc-400">{String(config.max_iterations ?? '預設 (5)')}</span>
          </label>
          <input
            type="number"
            min="1" max="10" step="1"
            value={(config.max_iterations as number) ?? ''}
            placeholder="5"
            onChange={(e) => onChange({ max_iterations: e.target.value ? parseInt(e.target.value, 10) : undefined })}
            className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
          />
        </div>
      )}

      {fields.includes('forbidden_patterns') && (
        <div>
          <label className="text-[10px] uppercase text-zinc-500 block mb-1">禁用關鍵字（每行一個）</label>
          <textarea
            value={((config.forbidden_patterns as string[]) || []).join('\n')}
            onChange={(e) => {
              const arr = e.target.value.split('\n').map((s) => s.trim()).filter(Boolean)
              onChange({ forbidden_patterns: arr.length > 0 ? arr : undefined })
            }}
            rows={4}
            placeholder="例如：仇恨言論"
            className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500 resize-y font-mono"
          />
        </div>
      )}

      {fields.includes('action') && (
        <div>
          <label className="text-[10px] uppercase text-zinc-500 block mb-1">偵測後行動</label>
          <select
            value={(config.action as string) || 'warn'}
            onChange={(e) => onChange({ action: e.target.value })}
            className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200"
          >
            <option value="warn">警告並繼續</option>
            <option value="block">阻擋回應</option>
            <option value="retry">要求重新生成</option>
          </select>
        </div>
      )}

      {fields.includes('max_retries') && (
        <div>
          <label className="flex items-center justify-between mb-1">
            <span className="text-[10px] uppercase text-zinc-500">最多重試次數</span>
            <span className="text-[10px] font-mono text-zinc-400">{String(config.max_retries ?? '預設 (3)')}</span>
          </label>
          <input
            type="number"
            min="1" max="5" step="1"
            value={(config.max_retries as number) ?? ''}
            placeholder="3"
            onChange={(e) => onChange({ max_retries: e.target.value ? parseInt(e.target.value, 10) : undefined })}
            className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
          />
        </div>
      )}

      {fields.includes('backoff_ms') && (
        <div>
          <label className="flex items-center justify-between mb-1">
            <span className="text-[10px] uppercase text-zinc-500">重試間隔 (ms)</span>
            <span className="text-[10px] font-mono text-zinc-400">{String(config.backoff_ms ?? '預設 (1000)')}</span>
          </label>
          <input
            type="number"
            min="100" max="10000" step="100"
            value={(config.backoff_ms as number) ?? ''}
            placeholder="1000"
            onChange={(e) => onChange({ backoff_ms: e.target.value ? parseInt(e.target.value, 10) : undefined })}
            className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
          />
        </div>
      )}

      {hasCustom && (
        <div className="border-t border-zinc-800 pt-2">
          <button
            onClick={() => {
              for (const k of Object.keys(config)) onChange({ [k]: undefined })
            }}
            className="text-[10px] text-zinc-500 hover:text-red-400"
          >
            清除此節點所有自訂
          </button>
        </div>
      )}
    </div>
  )
}

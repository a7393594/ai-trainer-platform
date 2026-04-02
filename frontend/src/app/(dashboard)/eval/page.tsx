'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

export default function EvalPage() {
  const [projectId, setProjectId] = useState('')
  const [tab, setTab] = useState<'cases' | 'runs'>('cases')
  const [cases, setCases] = useState<any[]>([])
  const [runs, setRuns] = useState<any[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [input, setInput] = useState('')
  const [expected, setExpected] = useState('')
  const [category, setCategory] = useState('')
  const [running, setRunning] = useState(false)
  const [expandedRun, setExpandedRun] = useState<string | null>(null)
  const [runDetails, setRunDetails] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setProjectId(ctx.project_id)
      loadCases(ctx.project_id)
      loadRuns(ctx.project_id)
    }).catch(() => setLoading(false))
  }, [])

  const loadCases = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/eval/test-cases/${pid}`)
    const d = await r.json()
    setCases(d.test_cases || [])
    setLoading(false)
  }
  const loadRuns = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/eval/runs/${pid}`)
    const d = await r.json()
    setRuns(d.runs || [])
  }

  const handleAddCase = async () => {
    if (!input.trim() || !expected.trim()) return
    await fetch(`${AI}/api/v1/eval/test-cases`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, input_text: input, expected_output: expected, category: category || null }),
    })
    setInput(''); setExpected(''); setCategory(''); setShowAdd(false)
    loadCases(projectId)
  }

  const handleDeleteCase = async (id: string) => {
    await fetch(`${AI}/api/v1/eval/test-cases/${id}`, { method: 'DELETE' })
    loadCases(projectId)
  }

  const handleRunEval = async () => {
    setRunning(true)
    await fetch(`${AI}/api/v1/eval/run/${projectId}`, { method: 'POST' })
    await loadRuns(projectId)
    setRunning(false)
  }

  const handleExpandRun = async (runId: string) => {
    if (expandedRun === runId) { setExpandedRun(null); return }
    const r = await fetch(`${AI}/api/v1/eval/runs/${runId}/details`)
    setRunDetails(await r.json())
    setExpandedRun(runId)
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">Eval Engine</h1>
        <p className="text-xs text-zinc-500 mb-4">Test cases and automated evaluation</p>

        {/* Tabs */}
        <div className="flex gap-1 mb-4">
          {(['cases', 'runs'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)} className={`px-4 py-1.5 rounded text-xs ${tab === t ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'}`}>
              {t === 'cases' ? 'Test Cases' : 'Run History'}
            </button>
          ))}
        </div>

        {tab === 'cases' && (
          <>
            <div className="flex justify-end mb-3">
              <button onClick={() => setShowAdd(true)} className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500">+ Add Test Case</button>
            </div>
            {showAdd && (
              <div className="mb-4 rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
                <textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder="Input (question)" rows={2} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <textarea value={expected} onChange={(e) => setExpected(e.target.value)} placeholder="Expected output" rows={3} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Category (optional)" className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <div className="flex gap-2 justify-end">
                  <button onClick={() => setShowAdd(false)} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300">Cancel</button>
                  <button onClick={handleAddCase} disabled={!input.trim() || !expected.trim()} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white disabled:opacity-50">Save</button>
                </div>
              </div>
            )}
            <div className="space-y-2">
              {cases.map((tc) => (
                <div key={tc.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3">
                  <div className="flex justify-between items-start">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-zinc-400 mb-1">Input:</p>
                      <p className="text-sm text-zinc-200 truncate">{tc.input_text}</p>
                      <p className="text-xs text-zinc-400 mt-2 mb-1">Expected:</p>
                      <p className="text-xs text-zinc-300 truncate">{tc.expected_output}</p>
                    </div>
                    <div className="flex items-center gap-2 ml-3">
                      {tc.category && <span className="rounded bg-purple-500/20 px-1.5 py-0.5 text-[10px] text-purple-400">{tc.category}</span>}
                      <button onClick={() => handleDeleteCase(tc.id)} className="text-xs text-red-400 hover:text-red-300">Del</button>
                    </div>
                  </div>
                </div>
              ))}
              {cases.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">No test cases. Add some to start evaluating.</p>}
            </div>
          </>
        )}

        {tab === 'runs' && (
          <>
            <div className="flex justify-end mb-3">
              <button onClick={handleRunEval} disabled={running || cases.length === 0} className="rounded bg-green-600 px-4 py-1.5 text-xs text-white hover:bg-green-500 disabled:opacity-50">
                {running ? 'Running...' : 'Run Evaluation'}
              </button>
            </div>
            <div className="space-y-2">
              {runs.map((run) => (
                <div key={run.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50">
                  <button onClick={() => handleExpandRun(run.id)} className="w-full text-left px-4 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-zinc-400">{new Date(run.run_at).toLocaleString('zh-TW')}</span>
                      <span className="text-sm font-mono text-zinc-200">{Math.round(run.total_score)}%</span>
                      <div className="w-24 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${run.total_score >= 70 ? 'bg-green-500' : run.total_score >= 40 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${run.total_score}%` }} />
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-green-400">{run.passed_count} passed</span>
                      <span className="text-xs text-red-400">{run.failed_count} failed</span>
                      <span className="text-zinc-600">{expandedRun === run.id ? '[-]' : '[+]'}</span>
                    </div>
                  </button>
                  {expandedRun === run.id && runDetails && (
                    <div className="border-t border-zinc-700 px-4 py-3 space-y-2">
                      {runDetails.results?.map((r: any, i: number) => (
                        <div key={i} className={`rounded p-2 text-xs border-l-2 ${r.passed ? 'border-green-500 bg-green-500/5' : 'border-red-500 bg-red-500/5'}`}>
                          <p className="text-zinc-300"><strong>Score:</strong> {r.score} | {r.passed ? 'PASS' : 'FAIL'}</p>
                          <p className="text-zinc-400 mt-1 truncate">Q: {r.actual_output?.slice(0, 100)}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {runs.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">No evaluation runs yet.</p>}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

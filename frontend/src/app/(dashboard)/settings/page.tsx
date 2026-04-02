'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

export default function SettingsPage() {
  const [context, setContext] = useState<any>(null)
  const [models, setModels] = useState<any[]>([])
  const [ftStats, setFtStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getDemoContext().then(async (ctx) => {
      setContext(ctx)
      const mr = await fetch(`${AI}/api/v1/models`)
      setModels((await mr.json()).models || [])
      try {
        const fr = await fetch(`${AI}/api/v1/finetune/stats/${ctx.project_id}`)
        setFtStats(await fr.json())
      } catch {}
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const handleExport = async () => {
    if (!context) return
    const r = await fetch(`${AI}/api/v1/finetune/export/${context.project_id}`, { method: 'POST' })
    const d = await r.json()
    // Download as file
    const blob = new Blob([d.jsonl || ''], { type: 'application/jsonl' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'training_data.jsonl'
    a.click()
    URL.revokeObjectURL(url)
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-lg font-medium text-zinc-200 mb-1">Settings</h1>
          <p className="text-xs text-zinc-500">Project configuration and management</p>
        </div>

        {/* Project Info */}
        <section className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <h2 className="text-sm font-medium text-zinc-200 mb-3">Project Info</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><span className="text-zinc-400">Name:</span> <span className="text-zinc-200 ml-2">{context?.project_name}</span></div>
            <div><span className="text-zinc-400">Project ID:</span> <span className="text-zinc-500 ml-2 font-mono text-xs">{context?.project_id?.slice(0, 12)}...</span></div>
            <div><span className="text-zinc-400">Tenant ID:</span> <span className="text-zinc-500 ml-2 font-mono text-xs">{context?.tenant_id?.slice(0, 12)}...</span></div>
            <div><span className="text-zinc-400">Domain:</span> <span className="text-zinc-200 ml-2">Poker</span></div>
          </div>
        </section>

        {/* LLM Models */}
        <section className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <h2 className="text-sm font-medium text-zinc-200 mb-3">Available LLM Models</h2>
          <div className="space-y-1">
            {models.map((m) => (
              <div key={m.id} className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-zinc-700/50">
                <span className="text-sm text-zinc-200">{m.label}</span>
                <span className="text-xs text-zinc-500 font-mono">{m.provider}</span>
              </div>
            ))}
          </div>
        </section>

        {/* API Keys */}
        <section className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <h2 className="text-sm font-medium text-zinc-200 mb-3">API Keys</h2>
          <div className="space-y-2">
            <div className="flex items-center justify-between py-1.5">
              <span className="text-sm text-zinc-300">Anthropic</span>
              <span className="rounded bg-green-500/20 px-2 py-0.5 text-[10px] text-green-400">Connected</span>
            </div>
            <div className="flex items-center justify-between py-1.5">
              <span className="text-sm text-zinc-300">Google (Gemini)</span>
              <span className="rounded bg-green-500/20 px-2 py-0.5 text-[10px] text-green-400">Connected</span>
            </div>
            <div className="flex items-center justify-between py-1.5">
              <span className="text-sm text-zinc-300">OpenAI</span>
              <span className="rounded bg-zinc-700 px-2 py-0.5 text-[10px] text-zinc-400">Not configured</span>
            </div>
          </div>
        </section>

        {/* Fine-tune */}
        <section className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <h2 className="text-sm font-medium text-zinc-200 mb-3">Fine-tune Data</h2>
          {ftStats ? (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded bg-zinc-900 p-3 text-center">
                  <p className="text-2xl font-bold text-zinc-200">{ftStats.total_training_pairs}</p>
                  <p className="text-xs text-zinc-500">Training Pairs</p>
                </div>
                <div className="rounded bg-zinc-900 p-3 text-center">
                  <p className="text-2xl font-bold text-zinc-200">{ftStats.feedback_stats?.total || 0}</p>
                  <p className="text-xs text-zinc-500">Total Feedbacks</p>
                </div>
                <div className="rounded bg-zinc-900 p-3 text-center">
                  <p className={`text-2xl font-bold ${ftStats.ready_for_training ? 'text-green-400' : 'text-yellow-400'}`}>
                    {ftStats.ready_for_training ? 'Ready' : 'Need More'}
                  </p>
                  <p className="text-xs text-zinc-500">Status (min {ftStats.min_recommended})</p>
                </div>
              </div>
              <button onClick={handleExport} className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500">
                Export Training Data (JSONL)
              </button>
            </div>
          ) : (
            <p className="text-xs text-zinc-500">No fine-tune data available yet.</p>
          )}
        </section>
      </div>
    </div>
  )
}

'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

interface EmbedToken {
  id: string
  tenant_id: string
  project_id: string
  token_prefix: string
  name: string
  allowed_origins: string[]
  scopes: string[]
  expires_at: string | null
  revoked_at: string | null
  last_used_at: string | null
  created_at: string
}

interface CreatedTokenResponse {
  id: string
  token: string  // plain, shown once
  token_prefix: string
  name: string
  project_id: string
  allowed_origins: string[]
  scopes: string[]
  created_at: string
}

const FRONTEND_URL =
  typeof window !== 'undefined' ? window.location.origin : 'https://frontend-gray-three-14.vercel.app'

export default function IntegrationsPage() {
  const { t } = useI18n()
  const [tokens, setTokens] = useState<EmbedToken[]>([])
  const [projectId, setProjectId] = useState<string>('')
  const [projectName, setProjectName] = useState<string>('')
  const [loading, setLoading] = useState(true)

  // Create form state
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [origins, setOrigins] = useState('')
  const [scopeChat, setScopeChat] = useState(true)
  const [scopeWidget, setScopeWidget] = useState(true)
  const [scopeHistory, setScopeHistory] = useState(false)
  const [creating, setCreating] = useState(false)

  // Post-creation modal
  const [createdToken, setCreatedToken] = useState<CreatedTokenResponse | null>(null)
  const [copiedField, setCopiedField] = useState<string | null>(null)

  useEffect(() => {
    getDemoContext()
      .then((ctx) => {
        setProjectId(ctx.project_id)
        setProjectName(ctx.project_name)
        return loadTokens(ctx.project_id)
      })
      .catch(() => setLoading(false))
  }, [])

  const loadTokens = async (pid: string) => {
    try {
      const r = await fetch(`${AI}/api/v1/embed-tokens?project_id=${pid}`)
      const d = await r.json()
      setTokens(d.tokens || [])
    } catch {}
    setLoading(false)
  }

  const handleCreate = async () => {
    if (!name.trim() || !projectId) return
    setCreating(true)
    try {
      const scopes: string[] = []
      if (scopeChat) scopes.push('chat')
      if (scopeWidget) scopes.push('widget')
      if (scopeHistory) scopes.push('history')

      const allowedOrigins = origins
        .split(',')
        .map((o) => o.trim())
        .filter(Boolean)

      const r = await fetch(`${AI}/api/v1/embed-tokens`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          name: name.trim(),
          allowed_origins: allowedOrigins,
          scopes,
        }),
      })
      if (!r.ok) throw new Error(await r.text())
      const data: CreatedTokenResponse = await r.json()
      setCreatedToken(data)
      setShowCreate(false)
      setName('')
      setOrigins('')
      await loadTokens(projectId)
    } catch (e) {
      alert('Failed to create token: ' + (e as Error).message)
    }
    setCreating(false)
  }

  const handleRevoke = async (tokenId: string) => {
    try {
      await fetch(`${AI}/api/v1/embed-tokens/${tokenId}`, { method: 'DELETE' })
    } catch {}
    await loadTokens(projectId)
  }

  const copyToClipboard = async (text: string, field: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedField(field)
      setTimeout(() => setCopiedField(null), 2000)
    } catch {}
  }

  const buildIframeSnippet = (token: string, pid: string) => {
    return `<iframe
  src="${FRONTEND_URL}/embed/chat/${pid}?token=${token}&theme=dark&lang=zh-TW"
  width="400"
  height="600"
  style="border:0; border-radius:12px"
  allow="clipboard-write"
></iframe>`
  }

  const formatDate = (iso: string | null) => {
    if (!iso) return t('integrations.never')
    return new Date(iso).toLocaleString()
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-900">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
      </div>
    )
  }

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">{t('integrations.title')}</h1>
            <p className="text-xs text-zinc-500 mt-1">{t('integrations.desc')}</p>
            <p className="text-xs text-zinc-600 mt-1">{projectName}</p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500"
          >
            + {t('integrations.create')}
          </button>
        </div>

        {/* Create Form */}
        {showCreate && (
          <div className="mb-6 rounded-lg border border-zinc-700 bg-zinc-800 p-5">
            <h3 className="text-sm font-medium text-zinc-200 mb-4">{t('integrations.create')}</h3>

            <label className="block text-xs text-zinc-400 mb-1">{t('integrations.name')}</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('integrations.namePlaceholder')}
              className="w-full mb-4 rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-blue-500"
            />

            <label className="block text-xs text-zinc-400 mb-1">{t('integrations.allowedOrigins')}</label>
            <input
              value={origins}
              onChange={(e) => setOrigins(e.target.value)}
              placeholder={t('integrations.originsPlaceholder')}
              className="w-full mb-4 rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-blue-500"
            />

            <label className="block text-xs text-zinc-400 mb-2">{t('integrations.scopes')}</label>
            <div className="flex gap-4 mb-4 text-sm">
              <label className="flex items-center gap-2 text-zinc-300">
                <input type="checkbox" checked={scopeChat} onChange={(e) => setScopeChat(e.target.checked)} />
                {t('integrations.scope.chat')}
              </label>
              <label className="flex items-center gap-2 text-zinc-300">
                <input type="checkbox" checked={scopeWidget} onChange={(e) => setScopeWidget(e.target.checked)} />
                {t('integrations.scope.widget')}
              </label>
              <label className="flex items-center gap-2 text-zinc-300">
                <input type="checkbox" checked={scopeHistory} onChange={(e) => setScopeHistory(e.target.checked)} />
                {t('integrations.scope.history')}
              </label>
            </div>

            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowCreate(false)}
                className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={handleCreate}
                disabled={creating || !name.trim()}
                className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {creating ? '...' : t('integrations.createBtn')}
              </button>
            </div>
          </div>
        )}

        {/* Token List */}
        <div className="space-y-2">
          {tokens.map((tok) => (
            <div key={tok.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-zinc-200">{tok.name}</p>
                    <code className="text-[10px] text-zinc-500 bg-zinc-900 px-1.5 py-0.5 rounded">
                      {tok.token_prefix}
                    </code>
                  </div>
                  <div className="flex items-center gap-4 mt-2 text-[11px] text-zinc-500">
                    <span>
                      {t('integrations.origins')}:{' '}
                      {tok.allowed_origins.length === 0
                        ? t('integrations.allOrigins')
                        : tok.allowed_origins.join(', ')}
                    </span>
                    <span>
                      {t('integrations.lastUsed')}: {formatDate(tok.last_used_at)}
                    </span>
                    <span>{tok.scopes.join(', ')}</span>
                  </div>
                </div>
                <button
                  onClick={() => handleRevoke(tok.id)}
                  className="text-xs text-red-400 hover:text-red-300"
                >
                  {t('integrations.revoke')}
                </button>
              </div>
            </div>
          ))}
          {tokens.length === 0 && (
            <p className="text-sm text-zinc-500 text-center py-12">{t('integrations.empty')}</p>
          )}
        </div>

        {/* Post-Creation Modal */}
        {createdToken && (
          <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
            <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-medium text-zinc-100">{t('integrations.tokenCreated')}</h3>
                <button
                  onClick={() => setCreatedToken(null)}
                  className="text-zinc-500 hover:text-zinc-300 text-lg"
                >
                  ×
                </button>
              </div>

              <div className="rounded-lg bg-yellow-500/10 border border-yellow-500/30 p-3 mb-4">
                <p className="text-xs text-yellow-400">⚠️ {t('integrations.tokenWarning')}</p>
              </div>

              <label className="block text-xs text-zinc-400 mb-2">Token</label>
              <div className="flex gap-2 mb-4">
                <code className="flex-1 bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-xs text-zinc-300 break-all font-mono">
                  {createdToken.token}
                </code>
                <button
                  onClick={() => copyToClipboard(createdToken.token, 'token')}
                  className="rounded bg-blue-600 px-3 py-2 text-xs text-white hover:bg-blue-500 whitespace-nowrap"
                >
                  {copiedField === 'token' ? t('integrations.copied') : t('integrations.copyToken')}
                </button>
              </div>

              <label className="block text-xs text-zinc-400 mb-2">{t('integrations.snippetTitle')}</label>
              <div className="mb-4">
                <pre className="bg-zinc-950 border border-zinc-700 rounded p-3 text-xs text-zinc-300 overflow-x-auto mb-2">
                  <code>{buildIframeSnippet(createdToken.token, createdToken.project_id)}</code>
                </pre>
                <button
                  onClick={() =>
                    copyToClipboard(
                      buildIframeSnippet(createdToken.token, createdToken.project_id),
                      'snippet'
                    )
                  }
                  className="rounded bg-blue-600 px-3 py-2 text-xs text-white hover:bg-blue-500"
                >
                  {copiedField === 'snippet' ? t('integrations.copied') : t('integrations.copySnippet')}
                </button>
              </div>

              <div className="flex justify-end pt-3 border-t border-zinc-800">
                <button
                  onClick={() => setCreatedToken(null)}
                  className="rounded bg-zinc-700 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-600"
                >
                  {t('integrations.done')}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

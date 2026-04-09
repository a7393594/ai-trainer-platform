/**
 * Embed API Client — called from /embed/* pages.
 * Auth via X-Embed-Token header.
 */

const AI_ENGINE_URL = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

export interface EmbedChatRequest {
  message: string
  session_id?: string
  external_user_id?: string
  project_id?: string
}

export interface EmbedProject {
  id: string
  name: string
  description: string | null
  is_primary: boolean
}

export interface EmbedSession {
  id: string
  session_type: string | null
  started_at: string
  ended_at: string | null
}

export interface EmbedStreamCallbacks {
  onChunk: (content: string) => void
  onDone: (sessionId: string, messageId: string) => void
  onError?: (error: string) => void
}

/**
 * Stream a chat message using SSE.
 */
export async function sendEmbedMessageStream(
  req: EmbedChatRequest,
  token: string,
  callbacks: EmbedStreamCallbacks,
): Promise<void> {
  const res = await fetch(`${AI_ENGINE_URL}/embed/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Embed-Token': token,
    },
    body: JSON.stringify(req),
  })

  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    callbacks.onError?.(err.detail || `API Error: ${res.status}`)
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let sessionId = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    const text = decoder.decode(value, { stream: true })
    const lines = text.split('\n')
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.session_id) sessionId = data.session_id
        if (data.content) callbacks.onChunk(data.content)
        if (data.done) callbacks.onDone(sessionId, data.message_id)
        if (data.error) callbacks.onError?.(data.error)
      } catch {}
    }
  }
}

/**
 * Non-streaming chat.
 */
export async function sendEmbedMessage(
  req: EmbedChatRequest,
  token: string,
): Promise<any> {
  const res = await fetch(`${AI_ENGINE_URL}/embed/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Embed-Token': token,
    },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `API Error: ${res.status}`)
  }
  return res.json()
}

/**
 * Get session history.
 */
export async function getEmbedSessionHistory(
  sessionId: string,
  token: string,
): Promise<{ session_id: string; project_id?: string; messages: any[] }> {
  const res = await fetch(`${AI_ENGINE_URL}/embed/session/${sessionId}/history`, {
    headers: { 'X-Embed-Token': token },
  })
  if (!res.ok) throw new Error(`Failed: ${res.status}`)
  return res.json()
}

/**
 * List projects this embed token can access. Ordered with primary first.
 */
export async function listEmbedProjects(token: string): Promise<EmbedProject[]> {
  const res = await fetch(`${AI_ENGINE_URL}/embed/projects`, {
    headers: { 'X-Embed-Token': token },
  })
  if (!res.ok) throw new Error(`Failed to list projects: ${res.status}`)
  const data = await res.json()
  return data.projects || []
}

/**
 * List sessions for a project filtered by external user.
 */
export async function listEmbedSessions(
  token: string,
  projectId: string,
  externalUserId: string,
  limit = 50,
): Promise<EmbedSession[]> {
  const url = new URL(`${AI_ENGINE_URL}/embed/sessions`)
  url.searchParams.set('project_id', projectId)
  url.searchParams.set('external_user_id', externalUserId)
  url.searchParams.set('limit', String(limit))
  const res = await fetch(url.toString(), {
    headers: { 'X-Embed-Token': token },
  })
  if (!res.ok) throw new Error(`Failed to list sessions: ${res.status}`)
  const data = await res.json()
  return data.sessions || []
}

/**
 * Create a new session explicitly.
 */
export async function createEmbedSession(
  token: string,
  projectId: string,
  externalUserId: string,
): Promise<{ session_id: string; project_id: string; started_at: string }> {
  const res = await fetch(`${AI_ENGINE_URL}/embed/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Embed-Token': token,
    },
    body: JSON.stringify({
      project_id: projectId,
      external_user_id: externalUserId,
      session_type: 'freeform',
    }),
  })
  if (!res.ok) throw new Error(`Failed to create session: ${res.status}`)
  return res.json()
}

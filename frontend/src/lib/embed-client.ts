/**
 * Embed API Client — called from /embed/* pages.
 * Auth via X-Embed-Token header.
 */

const AI_ENGINE_URL = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

export interface EmbedChatRequest {
  message: string
  session_id?: string
  external_user_id?: string
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
): Promise<{ session_id: string; messages: any[] }> {
  const res = await fetch(`${AI_ENGINE_URL}/embed/session/${sessionId}/history`, {
    headers: { 'X-Embed-Token': token },
  })
  if (!res.ok) throw new Error(`Failed: ${res.status}`)
  return res.json()
}

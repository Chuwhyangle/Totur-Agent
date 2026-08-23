/**
 * @typedef {Object} TutorSource
 * @property {string} id
 * @property {string} title
 * @property {string} url
 * @property {string | null | undefined} domain
 */

/**
 * @typedef {Object} TutorReply
 * @property {string} answer Markdown 正文
 * @property {TutorSource[] | undefined} sources 历史回复可能省略该字段
 */

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL
export const API_BASE_URL = configuredApiBaseUrl ?? (
  import.meta.env.PROD ? '' : 'http://127.0.0.1:8001'
)
const CHAT_URL = `${API_BASE_URL}/chat`
const CHAT_STREAM_URL = `${API_BASE_URL}/chat/stream`
const INTERVIEW_JDS_URL = `${API_BASE_URL}/interview-jds`
const MODELS_URL = `${API_BASE_URL}/models`
const PERSONAS_URL = `${API_BASE_URL}/personas`
const SESSIONS_URL = `${API_BASE_URL}/sessions`
const JOURNAL_URL = `${API_BASE_URL}/api/journal`

export class TutorApiError extends Error {
  constructor(message, { status = null, detail = null, responseBody = null, debug = null, cause = null } = {}) {
    super(message, cause ? { cause } : undefined)
    this.name = 'TutorApiError'
    this.status = status
    this.detail = detail
    this.responseBody = responseBody
    this.debug = debug
    this.isNetworkError = status == null && cause?.name !== 'AbortError'
    this.isAbortError = cause?.name === 'AbortError'
  }
}

function now() {
  return typeof performance !== 'undefined' ? performance.now() : Date.now()
}

async function readJsonSafely(response) {
  if (response.status === 204) return null

  try {
    return await response.json()
  } catch {
    return null
  }
}

function createHttpError(message, response, responseBody, debug) {
  return new TutorApiError(`${message}: ${response.status}`, {
    status: response.status,
    detail: responseBody?.detail ?? null,
    responseBody,
    debug,
  })
}

async function requestJson(url, options = {}, errorMessage = 'API request failed') {
  const startedAt = now()
  const { debugRequestBody, ...fetchOptions } = options
  let response

  try {
    response = await fetch(url, fetchOptions)
  } catch (cause) {
    const debug = {
      url,
      method: fetchOptions.method ?? 'GET',
      requestBody: debugRequestBody,
      status: null,
      durationMs: Math.round(now() - startedAt),
      error: cause instanceof Error ? cause.message : String(cause),
    }
    throw new TutorApiError(errorMessage, { debug, cause })
  }

  const responseBody = await readJsonSafely(response)
  const debug = {
    url,
    method: fetchOptions.method ?? 'GET',
    requestBody: debugRequestBody,
    responseBody,
    status: response.status,
    durationMs: Math.round(now() - startedAt),
  }

  if (!response.ok) {
    throw createHttpError(errorMessage, response, responseBody, debug)
  }

  return { data: responseBody, debug }
}

function buildConversationsUrl(userId, limit) {
  const safeUserId = encodeURIComponent(userId)
  const searchParams = new URLSearchParams({ limit: String(limit) })
  return `${API_BASE_URL}/conversations/${safeUserId}?${searchParams.toString()}`
}

function buildSessionsUrl(userId, limit) {
  const searchParams = new URLSearchParams({ user_id: userId, limit: String(limit) })
  return `${SESSIONS_URL}?${searchParams.toString()}`
}

function buildSessionConversationsUrl(sessionId, limit) {
  const searchParams = new URLSearchParams({ limit: String(limit) })
  return `${SESSIONS_URL}/${sessionId}/conversations?${searchParams.toString()}`
}

function buildInterviewJDsUrl(userId, limit) {
  const searchParams = new URLSearchParams({ user_id: userId, limit: String(limit) })
  return `${INTERVIEW_JDS_URL}?${searchParams.toString()}`
}

function buildAttachmentsUrl(sessionId, userId) {
  const searchParams = new URLSearchParams({ user_id: userId })
  return `${SESSIONS_URL}/${sessionId}/attachments?${searchParams.toString()}`
}

function buildAttachmentUrl(sessionId, attachmentId, userId) {
  const searchParams = new URLSearchParams({ user_id: userId })
  return `${SESSIONS_URL}/${sessionId}/attachments/${encodeURIComponent(attachmentId)}?${searchParams.toString()}`
}

function buildAttachmentRetryUrl(sessionId, attachmentId, userId) {
  const searchParams = new URLSearchParams({ user_id: userId })
  return `${SESSIONS_URL}/${sessionId}/attachments/${encodeURIComponent(attachmentId)}/retry?${searchParams.toString()}`
}

export async function getHealth(options = {}) {
  const { data } = await requestJson(
    `${API_BASE_URL}/health`,
    { signal: options.signal },
    'Health check failed',
  )
  return data
}

export function postChat(requestBody, options = {}) {
  return requestJson(CHAT_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
    debugRequestBody: requestBody,
    signal: options.signal,
  }, 'Chat request failed')
}

/**
 * Post a chat request and stream the response via SSE.
 * @param {Object} requestBody - The chat request body
 * @param {Object} callbacks - Event callbacks
 * @param {function} callbacks.onToken - Called for each token: (text) => void
 * @param {function} callbacks.onToolCall - Called when a tool starts: (tool, args) => void
 * @param {function} callbacks.onToolResult - Called when a tool finishes: (tool, result) => void
 * @param {function} callbacks.onDone - Called when complete: (data) => void
 * @param {function} callbacks.onError - Called on error: (message) => void
 * @param {Object} options - Options like signal
 * @returns {Promise<void>}
 */
export async function postChatStream(requestBody, callbacks, options = {}) {
  const { onToken, onToolCall, onToolResult, onDone, onError } = callbacks
  const { signal } = options

  let response
  try {
    response = await fetch(CHAT_STREAM_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
      signal,
    })
  } catch (cause) {
    if (cause?.name === 'AbortError') return
    onError?.(cause?.message ?? 'Network request failed')
    throw new TutorApiError('Chat stream request failed', { debug: { url: CHAT_STREAM_URL, method: 'POST' }, cause })
  }

  if (!response.ok) {
    const errorBody = await readJsonSafely(response)
    const message = errorBody?.detail ?? `HTTP ${response.status}`
    onError?.(message)
    throw createHttpError('Chat stream request failed', response, errorBody, {
      url: CHAT_STREAM_URL,
      method: 'POST',
      status: response.status,
    })
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent = null
  let terminalEventReceived = false

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // Parse SSE events from buffer
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // Keep incomplete line in buffer

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const dataStr = line.slice(6)
          try {
            const data = JSON.parse(dataStr)
            if (currentEvent === 'token') {
              onToken?.(data.text ?? '')
            } else if (currentEvent === 'tool_call') {
              onToolCall?.(data.tool, data.args)
            } else if (currentEvent === 'tool_result') {
              onToolResult?.(data.tool, data.result)
            } else if (currentEvent === 'done') {
              terminalEventReceived = true
              onDone?.(data)
              return
            } else if (currentEvent === 'error') {
              const message = data.message ?? 'Unknown error'
              onError?.(message)
              throw new TutorApiError('Chat stream failed', {
                detail: data,
                debug: { url: CHAT_STREAM_URL, method: 'POST' },
              })
            }
          } catch (cause) {
            if (cause instanceof TutorApiError) throw cause
            // Ignore malformed JSON
          }
          currentEvent = null
      }
    }
    }
    if (!terminalEventReceived) {
      const message = 'Chat stream ended unexpectedly'
      onError?.(message)
      throw new TutorApiError(message, { debug: { url: CHAT_STREAM_URL, method: 'POST' } })
    }
  } catch (cause) {
    if (cause?.name === 'AbortError') return
    if (cause instanceof TutorApiError) throw cause
    onError?.(cause?.message ?? 'Stream read failed')
  }
}

export function getPersonas(options = {}) {
  return requestJson(PERSONAS_URL, { signal: options.signal }, 'Persona list request failed')
}

export function getModels(options = {}) {
  return requestJson(MODELS_URL, { signal: options.signal }, 'Model list request failed')
}

export function createSession(requestBody, options = {}) {
  return requestJson(SESSIONS_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
    debugRequestBody: requestBody,
    signal: options.signal,
  }, 'Create session failed')
}

export function createInterviewJD(requestBody, options = {}) {
  return requestJson(INTERVIEW_JDS_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
    debugRequestBody: requestBody,
    signal: options.signal,
  }, 'Create interview JD failed')
}

export function getInterviewJDs(userId, limit = 20, options = {}) {
  const url = buildInterviewJDsUrl(userId, limit)
  return requestJson(url, { signal: options.signal }, 'Interview JD list request failed')
}

export function getSessions(userId, limit = 50, options = {}) {
  const url = buildSessionsUrl(userId, limit)
  return requestJson(url, { signal: options.signal }, 'Session list request failed')
}

export function getSessionConversations(sessionId, limit = 50, options = {}) {
  const url = buildSessionConversationsUrl(sessionId, limit)
  return requestJson(url, { signal: options.signal }, 'Session conversations request failed')
}

export function getConversations(userId, limit = 20, options = {}) {
  const url = buildConversationsUrl(userId, limit)
  return requestJson(url, { signal: options.signal }, 'Conversation history request failed')
}

export function uploadAttachment(sessionId, userId, file, options = {}) {
  const formData = new FormData()
  formData.append('user_id', userId)
  formData.append('file', file)

  return requestJson(`${SESSIONS_URL}/${sessionId}/attachments`, {
    method: 'POST',
    body: formData,
    debugRequestBody: {
      user_id: userId,
      file: {
        name: file?.name ?? '',
        size: file?.size ?? 0,
        type: file?.type ?? '',
      },
    },
    signal: options.signal,
  }, 'Attachment upload failed')
}

export function getAttachments(sessionId, userId, options = {}) {
  const url = buildAttachmentsUrl(sessionId, userId)
  return requestJson(url, { signal: options.signal }, 'Attachment list request failed')
}

export function getAttachment(sessionId, attachmentId, userId, options = {}) {
  const url = buildAttachmentUrl(sessionId, attachmentId, userId)
  return requestJson(url, { signal: options.signal }, 'Attachment request failed')
}

export function retryAttachment(sessionId, attachmentId, userId, options = {}) {
  const url = buildAttachmentRetryUrl(sessionId, attachmentId, userId)
  return requestJson(url, {
    method: 'POST',
    signal: options.signal,
  }, 'Attachment retry failed')
}

export function deleteAttachment(sessionId, attachmentId, userId, options = {}) {
  const url = buildAttachmentUrl(sessionId, attachmentId, userId)
  return requestJson(url, {
    method: 'DELETE',
    signal: options.signal,
  }, 'Attachment delete failed')
}

// Journal API functions

export function getJournalEntries(params = {}, options = {}) {
  const searchParams = new URLSearchParams()
  if (params.date) searchParams.set('date', params.date)
  if (params.tag) searchParams.set('tag', params.tag)
  if (params.limit) searchParams.set('limit', String(params.limit))
  const url = `${JOURNAL_URL}/entries${searchParams.toString() ? '?' + searchParams.toString() : ''}`
  return requestJson(url, { signal: options.signal }, 'Get journal entries failed')
}

export function getJournalEntry(entryId, options = {}) {
  return requestJson(`${JOURNAL_URL}/entries/${entryId}`, { signal: options.signal }, 'Get journal entry failed')
}

export function createJournalEntry(requestBody, options = {}) {
  return requestJson(`${JOURNAL_URL}/entries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
    debugRequestBody: requestBody,
    signal: options.signal,
  }, 'Create journal entry failed')
}

export function updateJournalEntry(entryId, requestBody, options = {}) {
  return requestJson(`${JOURNAL_URL}/entries/${entryId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
    debugRequestBody: requestBody,
    signal: options.signal,
  }, 'Update journal entry failed')
}

export function deleteJournalEntry(entryId, options = {}) {
  return requestJson(`${JOURNAL_URL}/entries/${entryId}`, {
    method: 'DELETE',
    signal: options.signal,
  }, 'Delete journal entry failed')
}


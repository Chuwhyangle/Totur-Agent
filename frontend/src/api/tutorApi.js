/**
 * @typedef {Object} TutorSource
 * @property {string} id
 * @property {string} title
 * @property {string} url
 * @property {string | null | undefined} domain
 */

/**
 * @typedef {Object} TutorReply
 * @property {string} answer
 * @property {string} next_task
 * @property {string} exercise
 * @property {string[]} checkpoints
 * @property {TutorSource[] | undefined} sources Legacy replies may omit this field.
 */

const API_BASE_URL = 'http://127.0.0.1:8001'
const CHAT_URL = `${API_BASE_URL}/chat`
const INTERVIEW_JDS_URL = `${API_BASE_URL}/interview-jds`
const PERSONAS_URL = `${API_BASE_URL}/personas`
const SESSIONS_URL = `${API_BASE_URL}/sessions`

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

export function getPersonas(options = {}) {
  return requestJson(PERSONAS_URL, { signal: options.signal }, 'Persona list request failed')
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

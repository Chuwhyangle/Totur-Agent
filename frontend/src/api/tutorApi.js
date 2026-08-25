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
  import.meta.env.PROD ? '' : 'http://127.0.0.1:8002'
)
const CHAT_URL = `${API_BASE_URL}/chat`
const CHAT_STREAM_URL = `${API_BASE_URL}/chat/stream`
const INTERVIEW_JDS_URL = `${API_BASE_URL}/interview-jds`
const MODELS_URL = `${API_BASE_URL}/models`
const PERSONAS_URL = `${API_BASE_URL}/personas`
const SESSIONS_URL = `${API_BASE_URL}/sessions`
const JOURNAL_URL = `${API_BASE_URL}/api/journal`
const WORKSPACES_URL = `${API_BASE_URL}/workspaces`
const LEARNING_PROGRESS_URL = `${API_BASE_URL}/learning-progress`
const KNOWLEDGE_DOCUMENTS_URL = `${API_BASE_URL}/knowledge/documents`
const GITHUB_MCP_STATUS_URL = `${API_BASE_URL}/mcp/github/status`

export class TutorApiError extends Error {
  constructor(message, { status = null, detail = null, responseBody = null, debug = null, cause = null } = {}) {
    super(message, cause ? { cause } : undefined)
    this.name = 'TutorApiError'
    this.status = status
    this.detail = detail
    this.responseBody = responseBody
    this.debug = debug
    this.isNetworkError =
      Boolean(cause) &&
      status == null &&
      cause?.name !== 'AbortError'
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
  const { debugRequestBody, responseType = 'json', ...fetchOptions } = options
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

  const responseBody = responseType === 'text'
    ? await (response.text ? response.text() : readJsonSafely(response))
    : await readJsonSafely(response)
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

function buildWorkspaceQuery(userId, limit) {
  return new URLSearchParams({ user_id: userId, limit: String(limit) })
}

function buildWorkspaceResourceUrl(workspaceId, resource, userId, limit) {
  const searchParams = buildWorkspaceQuery(userId, limit)
  return `${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/${resource}?${searchParams.toString()}`
}

export async function getHealth(options = {}) {
  const { data } = await requestJson(
    `${API_BASE_URL}/health`,
    { signal: options.signal },
    'Health check failed',
  )
  return data
}

export function getGitHubMcpStatus(options = {}) {
  return requestJson(
    GITHUB_MCP_STATUS_URL,
    { signal: options.signal },
    'GitHub MCP status request failed',
  )
}

export function getLearningProgress(userId, subject = 'sql', options = {}) {
  const searchParams = new URLSearchParams({ user_id: userId, subject })
  return requestJson(`${LEARNING_PROGRESS_URL}?${searchParams.toString()}`, {
    signal: options.signal,
  }, 'Learning progress request failed')
}

export function saveLearningProgress(requestBody, options = {}) {
  return requestJson(LEARNING_PROGRESS_URL, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
    debugRequestBody: requestBody,
    signal: options.signal,
  }, 'Save learning progress failed')
}

export function deleteLearningProgress(progressId, userId, subject = 'sql', options = {}) {
  const searchParams = new URLSearchParams({ user_id: userId, subject })
  return requestJson(`${LEARNING_PROGRESS_URL}/${encodeURIComponent(progressId)}?${searchParams.toString()}`, {
    method: 'DELETE',
    signal: options.signal,
  }, 'Delete learning progress failed')
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
 * @param {function} callbacks.onThinking - Called for each model reasoning summary chunk: (text) => void
 * @param {function} callbacks.onToken - Called for each token: (text) => void
 * @param {function} callbacks.onToolCall - Called when a tool starts: (tool, args) => void
 * @param {function} callbacks.onToolResult - Called when a tool finishes: (tool, result) => void
 * @param {function} callbacks.onDone - Called when complete: (data) => void
 * @param {function} callbacks.onError - Called on error: (message) => void
 * @param {Object} options - Options like signal
 * @returns {Promise<void>}
 */
export async function postChatStream(requestBody, callbacks, options = {}) {
  const { onThinking, onToken, onToolCall, onToolResult, onDone, onError } = callbacks
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
    const message = cause?.message ?? 'Network request failed'
    const debug = {
      url: CHAT_STREAM_URL,
      method: 'POST',
      requestBody,
      status: null,
      error: message,
    }
    onError?.(message)
    throw new TutorApiError(message, { debug, cause })
  }

  if (!response.ok) {
    const errorBody = await readJsonSafely(response)
    const message = errorBody?.detail?.message
      ?? errorBody?.detail
      ?? errorBody?.message
      ?? `HTTP ${response.status}`
    const debug = {
      url: CHAT_STREAM_URL,
      method: 'POST',
      requestBody,
      status: response.status,
      error: message,
      responseBody: errorBody,
    }
    onError?.(message)
    throw createHttpError('Chat stream request failed', response, errorBody, debug)
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
            if (currentEvent === 'thinking') {
              onThinking?.(data.text ?? '')
            } else if (currentEvent === 'token') {
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
              const message = data.message ?? data.error ?? '流式请求失败'
              onError?.(message)
              throw new TutorApiError('Chat stream failed', {
                status: response.status,
                detail: data,
                responseBody: data,
                debug: {
                  url: CHAT_STREAM_URL,
                  method: 'POST',
                  requestBody,
                  status: response.status,
                  error: message,
                  responseBody: data,
                },
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
      throw new TutorApiError(message, {
        status: response.status,
        debug: {
          url: CHAT_STREAM_URL,
          method: 'POST',
          requestBody,
          status: response.status,
          error: message,
        },
      })
    }
  } catch (cause) {
    if (cause?.name === 'AbortError') return
    if (cause instanceof TutorApiError) throw cause
    const message = cause?.message ?? 'Stream read failed'
    onError?.(message)
    throw new TutorApiError(message, {
      status: response.status,
      debug: {
        url: CHAT_STREAM_URL,
        method: 'POST',
        requestBody,
        status: response.status,
        error: message,
      },
      cause,
    })
  }
}

export function getPersonas(options = {}) {
  const query = options.userId ? `?user_id=${encodeURIComponent(options.userId)}` : ''
  return requestJson(`${PERSONAS_URL}${query}`, { signal: options.signal }, 'Persona list request failed')
}

export function createCustomPersona(requestBody, options = {}) {
  return requestJson(`${PERSONAS_URL}/custom`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestBody),
    debugRequestBody: requestBody, signal: options.signal,
  }, 'Create Persona failed')
}

export function updateCustomPersona(personaId, requestBody, options = {}) {
  return requestJson(`${PERSONAS_URL}/custom/${encodeURIComponent(personaId)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestBody),
    debugRequestBody: requestBody, signal: options.signal,
  }, 'Update Persona failed')
}

export function disableCustomPersona(personaId, userId, options = {}) {
  return requestJson(`${PERSONAS_URL}/custom/${encodeURIComponent(personaId)}?user_id=${encodeURIComponent(userId)}`, {
    method: 'DELETE', signal: options.signal,
  }, 'Disable Persona failed')
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

export function createWorkspace(requestBody, options = {}) {
  return requestJson(WORKSPACES_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
    debugRequestBody: requestBody,
    signal: options.signal,
  }, 'Create Workspace failed')
}

export function getWorkspaces(userId, limit = 50, options = {}) {
  const searchParams = buildWorkspaceQuery(userId, limit)
  return requestJson(`${WORKSPACES_URL}?${searchParams.toString()}`, { signal: options.signal }, 'Workspace list request failed')
}

export function getWorkspace(workspaceId, userId, options = {}) {
  const searchParams = new URLSearchParams({ user_id: userId })
  return requestJson(`${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}?${searchParams.toString()}`, { signal: options.signal }, 'Workspace request failed')
}

function updateWorkspace(workspaceId, action, userId, options = {}) {
  const searchParams = new URLSearchParams({ user_id: userId })
  return requestJson(`${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/${action}?${searchParams.toString()}`, {
    method: 'POST',
    signal: options.signal,
  }, `Workspace ${action} failed`)
}

export function archiveWorkspace(workspaceId, userId, options = {}) {
  return updateWorkspace(workspaceId, 'archive', userId, options)
}

export function restoreWorkspace(workspaceId, userId, options = {}) {
  return updateWorkspace(workspaceId, 'restore', userId, options)
}

export function getWorkspaceAgentInstructions(workspaceId, userId, options = {}) {
  return requestJson(`${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/agent-instructions?user_id=${encodeURIComponent(userId)}`, { signal: options.signal }, 'Workspace instructions request failed')
}

export function saveWorkspaceAgentInstructions(workspaceId, requestBody, options = {}) {
  return requestJson(`${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/agent-instructions`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestBody),
    debugRequestBody: requestBody, signal: options.signal,
  }, 'Save Workspace instructions failed')
}

export function clearWorkspaceAgentInstructions(workspaceId, userId, options = {}) {
  return requestJson(`${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/agent-instructions?user_id=${encodeURIComponent(userId)}`, {
    method: 'DELETE', signal: options.signal,
  }, 'Clear Workspace instructions failed')
}

export function uploadWorkspaceAsset(workspaceId, userId, file, options = {}) {
  const formData = new FormData()
  formData.append('user_id', userId)
  formData.append('file', file)
  return requestJson(`${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/assets?user_id=${encodeURIComponent(userId)}`, {
    method: 'POST',
    body: formData,
    signal: options.signal,
  }, 'Workspace Asset upload failed')
}

export function getKnowledgeDocuments(userId, options = {}) {
  const params = new URLSearchParams({ user_id: userId, limit: String(options.limit ?? 100) })
  if (options.status) params.set('status', options.status)
  return requestJson(`${KNOWLEDGE_DOCUMENTS_URL}?${params.toString()}`, { signal: options.signal }, 'Knowledge document list request failed')
}

export function uploadKnowledgeDocument(userId, file, options = {}) {
  const formData = new FormData()
  formData.append('user_id', userId)
  formData.append('file', file)
  return requestJson(KNOWLEDGE_DOCUMENTS_URL, { method: 'POST', body: formData, signal: options.signal }, 'Knowledge document upload failed')
}

export function retryKnowledgeDocument(documentId, userId, options = {}) {
  return requestJson(`${KNOWLEDGE_DOCUMENTS_URL}/${encodeURIComponent(documentId)}/retry?user_id=${encodeURIComponent(userId)}`, { method: 'POST', signal: options.signal }, 'Knowledge document retry failed')
}

export function deleteKnowledgeDocument(documentId, userId, options = {}) {
  return requestJson(`${KNOWLEDGE_DOCUMENTS_URL}/${encodeURIComponent(documentId)}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE', signal: options.signal }, 'Knowledge document delete failed')
}

export function getWorkspaceAssets(workspaceId, userId, options = {}) {
  const url = buildWorkspaceResourceUrl(workspaceId, 'assets', userId, options.limit ?? 100)
  return requestJson(url, { signal: options.signal }, 'Workspace Asset list request failed')
}

export function retryWorkspaceAsset(workspaceId, assetId, userId, options = {}) {
  const searchParams = new URLSearchParams({ user_id: userId })
  return requestJson(`${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/assets/${encodeURIComponent(assetId)}/retry?${searchParams.toString()}`, {
    method: 'POST',
    signal: options.signal,
  }, 'Workspace Asset retry failed')
}

export function deleteWorkspaceAsset(workspaceId, assetId, userId, options = {}) {
  const searchParams = new URLSearchParams({ user_id: userId })
  return requestJson(`${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/assets/${encodeURIComponent(assetId)}?${searchParams.toString()}`, {
    method: 'DELETE',
    signal: options.signal,
  }, 'Workspace Asset delete failed')
}

export function getWorkspaceAssetDownloadUrl(workspaceId, assetId, userId) {
  const searchParams = new URLSearchParams({ user_id: userId })
  return `${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/assets/${encodeURIComponent(assetId)}/download?${searchParams.toString()}`
}

export function getWorkspaceTasks(workspaceId, userId, options = {}) {
  return requestJson(buildWorkspaceResourceUrl(workspaceId, 'tasks', userId, options.limit ?? 50), { signal: options.signal }, 'Workspace Task list request failed')
}

export function getWorkspaceTask(workspaceId, taskId, userId, options = {}) {
  const searchParams = new URLSearchParams({ user_id: userId })
  return requestJson(`${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/tasks/${encodeURIComponent(taskId)}?${searchParams.toString()}`, { signal: options.signal }, 'Workspace Task request failed')
}

export function getWorkspaceArtifacts(workspaceId, userId, options = {}) {
  const searchParams = buildWorkspaceQuery(userId, options.limit ?? 50)
  if (options.includeVersions) searchParams.set('include_versions', 'true')
  return requestJson(`${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/artifacts?${searchParams.toString()}`, { signal: options.signal }, 'Workspace Artifact list request failed')
}

export function getWorkspaceArtifact(workspaceId, artifactId, userId, options = {}) {
  const searchParams = new URLSearchParams({ user_id: userId })
  return requestJson(`${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/artifacts/${encodeURIComponent(artifactId)}?${searchParams.toString()}`, { signal: options.signal }, 'Workspace Artifact request failed')
}

export function getWorkspaceArtifactContent(workspaceId, artifactId, userId, options = {}) {
  const searchParams = new URLSearchParams({ user_id: userId })
  return requestJson(`${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/artifacts/${encodeURIComponent(artifactId)}/content?${searchParams.toString()}`, { signal: options.signal, responseType: 'text' }, 'Workspace Artifact content request failed')
}

export function getWorkspaceArtifactDownloadUrl(workspaceId, artifactId, userId) {
  const searchParams = new URLSearchParams({ user_id: userId })
  return `${WORKSPACES_URL}/${encodeURIComponent(workspaceId)}/artifacts/${encodeURIComponent(artifactId)}/download?${searchParams.toString()}`
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


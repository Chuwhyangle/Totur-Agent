const API_BASE_URL = 'http://127.0.0.1:8001'
const CHAT_URL = `${API_BASE_URL}/chat`
const INTERVIEW_JDS_URL = `${API_BASE_URL}/interview-jds`
const PERSONAS_URL = `${API_BASE_URL}/personas`
const SESSIONS_URL = `${API_BASE_URL}/sessions`

// getHealth 负责请求后端健康检查接口，确认 API 是否在线。
export async function getHealth() {
  const response = await fetch(`${API_BASE_URL}/health`)

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`)
  }

  return response.json()
}

async function readJsonSafely(response) {
  try {
    return await response.json()
  } catch {
    return null
  }
}

function buildConversationsUrl(userId, limit) {
  const safeUserId = encodeURIComponent(userId)
  const searchParams = new URLSearchParams({ limit: String(limit) })

  return `${API_BASE_URL}/conversations/${safeUserId}?${searchParams.toString()}`
}

function buildSessionsUrl(userId, limit) {
  const searchParams = new URLSearchParams({
    user_id: userId,
    limit: String(limit),
  })

  return `${SESSIONS_URL}?${searchParams.toString()}`
}

function buildSessionConversationsUrl(sessionId, limit) {
  const searchParams = new URLSearchParams({ limit: String(limit) })

  return `${SESSIONS_URL}/${sessionId}/conversations?${searchParams.toString()}`
}

function buildInterviewJDsUrl(userId, limit) {
  const searchParams = new URLSearchParams({
    user_id: userId,
    limit: String(limit),
  })

  return `${INTERVIEW_JDS_URL}?${searchParams.toString()}`
}

// postChat 负责把用户消息发送给后端 /chat，并保留调试信息。
export async function postChat(requestBody) {
  const startedAt = performance.now()
  const response = await fetch(CHAT_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestBody),
  })
  const responseBody = await readJsonSafely(response)
  const durationMs = Math.round(performance.now() - startedAt)
  const debug = {
    url: CHAT_URL,
    method: 'POST',
    requestBody,
    responseBody,
    status: response.status,
    durationMs,
  }

  if (!response.ok) {
    const error = new Error(`Chat request failed: ${response.status}`)
    error.debug = debug
    throw error
  }

  return {
    data: responseBody,
    debug,
  }
}

// getPersonas 负责读取后端当前可用的人设列表。
export async function getPersonas() {
  const startedAt = performance.now()
  const response = await fetch(PERSONAS_URL)
  const responseBody = await readJsonSafely(response)
  const durationMs = Math.round(performance.now() - startedAt)
  const debug = {
    url: PERSONAS_URL,
    method: 'GET',
    responseBody,
    status: response.status,
    durationMs,
  }

  if (!response.ok) {
    const error = new Error(`Persona list request failed: ${response.status}`)
    error.debug = debug
    throw error
  }

  return {
    data: responseBody,
    debug,
  }
}

// createSession 负责创建一个新的聊天会话窗口。
export async function createSession(requestBody) {
  const startedAt = performance.now()
  const response = await fetch(SESSIONS_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestBody),
  })
  const responseBody = await readJsonSafely(response)
  const durationMs = Math.round(performance.now() - startedAt)
  const debug = {
    url: SESSIONS_URL,
    method: 'POST',
    requestBody,
    responseBody,
    status: response.status,
    durationMs,
  }

  if (!response.ok) {
    const error = new Error(`Create session failed: ${response.status}`)
    error.debug = debug
    throw error
  }

  return {
    data: responseBody,
    debug,
  }
}

// createInterviewJD 负责保存用户整理出来的目标岗位 JD。
export async function createInterviewJD(requestBody) {
  const startedAt = performance.now()
  const response = await fetch(INTERVIEW_JDS_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestBody),
  })
  const responseBody = await readJsonSafely(response)
  const durationMs = Math.round(performance.now() - startedAt)
  const debug = {
    url: INTERVIEW_JDS_URL,
    method: 'POST',
    requestBody,
    responseBody,
    status: response.status,
    durationMs,
  }

  if (!response.ok) {
    const error = new Error(`Create interview JD failed: ${response.status}`)
    error.debug = debug
    throw error
  }

  return {
    data: responseBody,
    debug,
  }
}

// getInterviewJDs 负责按 user_id 读取用户保存过的目标岗位 JD。
export async function getInterviewJDs(userId, limit = 20) {
  const url = buildInterviewJDsUrl(userId, limit)
  const startedAt = performance.now()
  const response = await fetch(url)
  const responseBody = await readJsonSafely(response)
  const durationMs = Math.round(performance.now() - startedAt)
  const debug = {
    url,
    method: 'GET',
    responseBody,
    status: response.status,
    durationMs,
  }

  if (!response.ok) {
    const error = new Error(`Interview JD list request failed: ${response.status}`)
    error.debug = debug
    throw error
  }

  return {
    data: responseBody,
    debug,
  }
}

// getSessions 负责按 user_id 查询这个用户的会话列表。
export async function getSessions(userId, limit = 50) {
  const url = buildSessionsUrl(userId, limit)
  const startedAt = performance.now()
  const response = await fetch(url)
  const responseBody = await readJsonSafely(response)
  const durationMs = Math.round(performance.now() - startedAt)
  const debug = {
    url,
    method: 'GET',
    responseBody,
    status: response.status,
    durationMs,
  }

  if (!response.ok) {
    const error = new Error(`Session list request failed: ${response.status}`)
    error.debug = debug
    throw error
  }

  return {
    data: responseBody,
    debug,
  }
}

// getSessionConversations 负责查询某个会话窗口里的历史消息。
export async function getSessionConversations(sessionId, limit = 50) {
  const url = buildSessionConversationsUrl(sessionId, limit)
  const startedAt = performance.now()
  const response = await fetch(url)
  const responseBody = await readJsonSafely(response)
  const durationMs = Math.round(performance.now() - startedAt)
  const debug = {
    url,
    method: 'GET',
    responseBody,
    status: response.status,
    durationMs,
  }

  if (!response.ok) {
    const error = new Error(`Session conversations request failed: ${response.status}`)
    error.debug = debug
    throw error
  }

  return {
    data: responseBody,
    debug,
  }
}

// getConversations 负责按 user_id 查询最近几条历史对话。
export async function getConversations(userId, limit = 20) {
  const url = buildConversationsUrl(userId, limit)
  const startedAt = performance.now()
  const response = await fetch(url)
  const responseBody = await readJsonSafely(response)
  const durationMs = Math.round(performance.now() - startedAt)
  const debug = {
    url,
    method: 'GET',
    responseBody,
    status: response.status,
    durationMs,
  }

  if (!response.ok) {
    const error = new Error(`Conversation history request failed: ${response.status}`)
    error.debug = debug
    throw error
  }

  return {
    data: responseBody,
    debug,
  }
}

const API_BASE_URL = 'http://127.0.0.1:8001'
const CHAT_URL = `${API_BASE_URL}/chat`

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

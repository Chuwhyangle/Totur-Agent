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

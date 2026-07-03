import { useEffect, useState } from 'react'

import { getConversations, getHealth, postChat } from './api/tutorApi.js'
import ApiStatus from './components/ApiStatus.jsx'
import ChatInput from './components/ChatInput.jsx'
import ChatMessage from './components/ChatMessage.jsx'
import ConversationHistory from './components/ConversationHistory.jsx'
import UserIdInput from './components/UserIdInput.jsx'

function createErrorReply() {
  return {
    answer: '这次请求后端失败了，但页面没有崩溃。',
    next_task: '先确认后端是否运行在 http://127.0.0.1:8001。',
    exercise: '点击顶部刷新按钮，观察 API 状态是否在线。',
    checkpoints: ['用户消息已经保留', '错误被显示在聊天区', '调试详情里可以查看失败信息'],
  }
}

// App 是当前前端页面的主组件，负责组合组件和管理页面状态。
function App() {
  const [apiStatus, setApiStatus] = useState('checking')
  const [userId, setUserId] = useState('demo-user')
  const [draftMessage, setDraftMessage] = useState('')
  // 聊天消息从空数组开始，页面启动时不再显示固定示例回复。
  const [messages, setMessages] = useState([])
  const [isSending, setIsSending] = useState(false)
  const [historyItems, setHistoryItems] = useState([])
  const [historyStatus, setHistoryStatus] = useState('idle')
  const [historyLimit, setHistoryLimit] = useState(5)
  const [historyDebug, setHistoryDebug] = useState(null)

  const canSend = draftMessage.trim().length > 0 && userId.trim().length > 0 && !isSending

  function handleUserIdChange(nextUserId) {
    // 切换用户时清空页面本地状态，避免把不同 user_id 的对话混在一起看。
    setUserId(nextUserId)
    setMessages([])
    setHistoryItems([])
    setHistoryStatus('idle')
    setHistoryDebug(null)
  }

  function handleHistoryLimitChange(nextLimit) {
    const numberLimit = Number(nextLimit)

    if (Number.isNaN(numberLimit)) {
      return
    }

    setHistoryLimit(Math.min(100, Math.max(1, numberLimit)))
  }

  async function loadConversationHistory({ silent = false } = {}) {
    const trimmedUserId = userId.trim()

    if (!trimmedUserId) {
      setHistoryItems([])
      setHistoryStatus('error')
      setHistoryDebug({
        error: 'user_id 不能为空',
      })
      return
    }

    if (!silent) {
      setHistoryStatus('loading')
    }

    try {
      const { data, debug } = await getConversations(trimmedUserId, historyLimit)

      setHistoryItems(Array.isArray(data?.items) ? data.items : [])
      setHistoryDebug(debug)
      setHistoryStatus('success')
      setApiStatus('online')
    } catch (error) {
      setHistoryItems([])
      setHistoryDebug(error.debug ?? { error: error.message })
      setHistoryStatus('error')
      setApiStatus('offline')
    }
  }

  async function handleSendMessage(event) {
    event.preventDefault()

    const trimmedMessage = draftMessage.trim()
    const trimmedUserId = userId.trim()
    if (!trimmedMessage || !trimmedUserId || isSending) {
      return
    }

    const requestBody = {
      // 后端第一阶段短期记忆按 user_id 查询历史，所以这里发送去空格后的值。
      user_id: trimmedUserId,
      message: trimmedMessage,
    }
    const userMessage = {
      id: `message-user-${Date.now()}`,
      role: 'user',
      text: trimmedMessage,
    }

    setMessages((currentMessages) => [...currentMessages, userMessage])
    setDraftMessage('')
    setIsSending(true)

    try {
      const { data, debug } = await postChat(requestBody)
      const assistantMessage = {
        id: `message-assistant-${Date.now()}`,
        role: 'assistant',
        reply: data?.reply,
        debug,
      }

      setMessages((currentMessages) => [...currentMessages, assistantMessage])
      setApiStatus('online')

      // 每次成功发送后刷新历史，方便立刻验证本轮对话已经保存。
      void loadConversationHistory({ silent: true })
    } catch (error) {
      const errorMessage = {
        id: `message-error-${Date.now()}`,
        role: 'assistant',
        reply: createErrorReply(),
        debug: error.debug ?? {
          url: 'http://127.0.0.1:8001/chat',
          method: 'POST',
          requestBody,
          error: error.message,
        },
      }

      setMessages((currentMessages) => [...currentMessages, errorMessage])
      setApiStatus('offline')
    } finally {
      setIsSending(false)
    }
  }

  async function checkApiHealth() {
    setApiStatus('checking')

    try {
      await getHealth()
      setApiStatus('online')
    } catch {
      setApiStatus('offline')
    }
  }

  useEffect(() => {
    checkApiHealth()
  }, [])

  return (
    <main className="app-shell">
      {/* 顶部区域：显示标题、API 状态、刷新按钮和当前 user_id。 */}
      <header className="app-header">
        <div>
          <p className="app-kicker">Tutor Agent</p>
          <h1>学习对话工作台</h1>
        </div>
        <div className="header-controls">
          <ApiStatus status={apiStatus} />
          {/* 刷新按钮会重新请求 GET /health，手动更新 API 状态。 */}
          <button
            className="refresh-button"
            type="button"
            disabled={apiStatus === 'checking'}
            onClick={checkApiHealth}
          >
            刷新
          </button>
          <UserIdInput userId={userId} onUserIdChange={handleUserIdChange} />
        </div>
      </header>

      <div className="workspace-layout">
        <ConversationHistory
          userId={userId}
          items={historyItems}
          status={historyStatus}
          limit={historyLimit}
          onLimitChange={handleHistoryLimitChange}
          onRefresh={loadConversationHistory}
          debug={historyDebug}
        />

        {/* 聊天区域：发送消息后，用户消息和真实后端回复都会加入 messages。 */}
        <section className="chat-surface" aria-label="聊天工作区">
          <div className="thread-preview">
            {messages.map((message) => (
              <ChatMessage
                key={message.id}
                role={message.role}
                text={message.text}
                reply={message.reply}
                debug={message.debug}
              />
            ))}
          </div>
          <ChatInput
            message={draftMessage}
            onMessageChange={setDraftMessage}
            onSubmit={handleSendMessage}
            disabled={!canSend}
            isSending={isSending}
          />
        </section>
      </div>
    </main>
  )
}

export default App

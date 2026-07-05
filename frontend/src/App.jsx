import { useCallback, useEffect, useState } from 'react'

import {
  createInterviewJD,
  createSession,
  getHealth,
  getInterviewJDs,
  getSessionConversations,
  getSessions,
  postChat,
} from './api/tutorApi.js'
import ApiStatus from './components/ApiStatus.jsx'
import ChatInput from './components/ChatInput.jsx'
import ChatMessage from './components/ChatMessage.jsx'
import InterviewJDPanel from './components/InterviewJDPanel.jsx'
import SessionSidebar from './components/SessionSidebar.jsx'
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
  const [sessions, setSessions] = useState([])
  const [sessionsStatus, setSessionsStatus] = useState('idle')
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [activeSessionStatus, setActiveSessionStatus] = useState('idle')
  const [isCreatingSession, setIsCreatingSession] = useState(false)
  const [interviewJDs, setInterviewJDs] = useState([])
  const [interviewJDsStatus, setInterviewJDsStatus] = useState('idle')
  const [isSavingInterviewJD, setIsSavingInterviewJD] = useState(false)

  const canSend = draftMessage.trim().length > 0 && userId.trim().length > 0 && !isSending

  function handleUserIdChange(nextUserId) {
    // 切换用户时清空页面本地状态，避免把不同 user_id 的对话混在一起看。
    setUserId(nextUserId)
    setMessages([])
    setSessions([])
    setSessionsStatus('idle')
    setActiveSessionId(null)
    setActiveSessionStatus('idle')
    setInterviewJDs([])
    setInterviewJDsStatus('idle')
  }

  function buildMessagesFromHistoryItems(items) {
    // 后端历史是最新在前，聊天窗口显示时要改成旧到新。
    return [...items].reverse().flatMap((item) => [
      {
        id: `history-user-${item.id}`,
        role: 'user',
        text: item.message,
      },
      {
        id: `history-assistant-${item.id}`,
        role: 'assistant',
        reply: item.reply,
      },
    ])
  }

  function upsertSession(nextSession) {
    setSessions((currentSessions) => {
      const withoutCurrent = currentSessions.filter(
        (session) => session.id !== nextSession.id,
      )

      return [nextSession, ...withoutCurrent]
    })
  }

  const loadSessions = useCallback(async ({ silent = false } = {}) => {
    const trimmedUserId = userId.trim()
    if (!trimmedUserId) {
      setSessions([])
      setSessionsStatus('error')
      return []
    }

    if (!silent) {
      setSessionsStatus('loading')
    }

    try {
      const { data } = await getSessions(trimmedUserId)
      const nextSessions = Array.isArray(data?.items) ? data.items : []

      setSessions(nextSessions)
      setSessionsStatus('success')
      setApiStatus('online')

      return nextSessions
    } catch {
      setSessions([])
      setSessionsStatus('error')
      setApiStatus('offline')

      return []
    }
  }, [userId])

  const loadInterviewJDs = useCallback(async ({ silent = false } = {}) => {
    const trimmedUserId = userId.trim()
    if (!trimmedUserId) {
      setInterviewJDs([])
      setInterviewJDsStatus('error')
      return []
    }

    if (!silent) {
      setInterviewJDsStatus('loading')
    }

    try {
      const { data } = await getInterviewJDs(trimmedUserId)
      const nextJDs = Array.isArray(data?.items) ? data.items : []

      setInterviewJDs(nextJDs)
      setInterviewJDsStatus('success')
      setApiStatus('online')

      return nextJDs
    } catch {
      setInterviewJDs([])
      setInterviewJDsStatus('error')
      setApiStatus('offline')

      return []
    }
  }, [userId])

  async function handleSaveInterviewJD(requestBody) {
    if (isSavingInterviewJD) {
      return null
    }

    setIsSavingInterviewJD(true)

    try {
      const { data } = await createInterviewJD(requestBody)

      setInterviewJDs((currentJDs) => [data, ...currentJDs])
      setInterviewJDsStatus('success')
      setApiStatus('online')

      return data
    } catch {
      setInterviewJDsStatus('error')
      setApiStatus('offline')

      return null
    } finally {
      setIsSavingInterviewJD(false)
    }
  }

  async function loadSessionMessages(session) {
    setActiveSessionId(session.id)
    setActiveSessionStatus('loading')
    setMessages([])

    try {
      const { data } = await getSessionConversations(session.id)
      const items = Array.isArray(data?.items) ? data.items : []

      setMessages(buildMessagesFromHistoryItems(items))
      setActiveSessionStatus('success')
      setApiStatus('online')
    } catch {
      setMessages([])
      setActiveSessionStatus('error')
      setApiStatus('offline')
    }
  }

  async function handleCreateSession() {
    const trimmedUserId = userId.trim()
    if (!trimmedUserId || isCreatingSession) {
      return null
    }

    setIsCreatingSession(true)

    try {
      // 不传 title，让后端在第一条消息后用用户问题生成标题。
      const { data } = await createSession({ user_id: trimmedUserId })

      upsertSession(data)
      setSessionsStatus('success')
      setActiveSessionId(data.id)
      setActiveSessionStatus('success')
      setMessages([])
      setApiStatus('online')

      return data
    } catch {
      setSessionsStatus('error')
      setApiStatus('offline')

      return null
    } finally {
      setIsCreatingSession(false)
    }
  }

  async function ensureActiveSession() {
    const currentSession = sessions.find((session) => session.id === activeSessionId)
    if (currentSession) {
      return currentSession
    }

    return handleCreateSession()
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
      session_id: activeSessionId,
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
      const activeSession = await ensureActiveSession()

      if (!activeSession) {
        throw new Error('没有可用的会话')
      }

      const chatRequestBody = {
        ...requestBody,
        session_id: activeSession.id,
      }
      const { data, debug } = await postChat(chatRequestBody)
      const assistantMessage = {
        id: `message-assistant-${Date.now()}`,
        role: 'assistant',
        reply: data?.reply,
        debug,
      }

      setMessages((currentMessages) => [...currentMessages, assistantMessage])
      setActiveSessionId(data?.session_id ?? activeSession.id)
      setActiveSessionStatus('success')
      setApiStatus('online')

      // 每次成功发送后刷新会话列表，拿到最新标题和 updated_at。
      void loadSessions({ silent: true })
    } catch (error) {
      const errorMessage = {
        id: `message-error-${Date.now()}`,
        role: 'assistant',
        reply: createErrorReply(),
        debug: error.debug ?? {
          url: 'http://127.0.0.1:8001/chat',
          method: 'POST',
          requestBody: {
            ...requestBody,
            session_id: activeSessionId,
          },
          error: error.message,
        },
      }

      setMessages((currentMessages) => [...currentMessages, errorMessage])
      setApiStatus('offline')
    } finally {
      setIsSending(false)
    }
  }

  const checkApiHealth = useCallback(async () => {
    setApiStatus('checking')

    try {
      await getHealth()
      setApiStatus('online')
    } catch {
      setApiStatus('offline')
    }
  }, [])

  useEffect(() => {
    checkApiHealth()
    void loadSessions()
    void loadInterviewJDs()
  }, [checkApiHealth, loadSessions, loadInterviewJDs])

  const chatEmptyText = (() => {
    if (activeSessionStatus === 'loading') {
      return '正在读取这个会话的历史消息...'
    }

    if (activeSessionStatus === 'error') {
      return '这个会话读取失败，请确认后端是否在线。'
    }

    if (!activeSessionId) {
      return '选择左侧会话，或点击“新建会话”开始新的学习窗口。'
    }

    if (messages.length === 0) {
      return '这个会话还没有消息，发送第一条问题后会自动保存。'
    }

    return ''
  })()

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
        <SessionSidebar
          userId={userId}
          sessions={sessions}
          activeSessionId={activeSessionId}
          status={sessionsStatus}
          isCreating={isCreatingSession}
          onCreateSession={handleCreateSession}
          onRefreshSessions={loadSessions}
          onSelectSession={loadSessionMessages}
        />

        {/* 聊天区域：发送消息后，用户消息和真实后端回复都会加入 messages。 */}
        <section className="chat-surface" aria-label="聊天工作区">
          <div className="thread-preview">
            {chatEmptyText ? <p className="chat-empty">{chatEmptyText}</p> : null}
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

        <InterviewJDPanel
          userId={userId}
          items={interviewJDs}
          status={interviewJDsStatus}
          isSaving={isSavingInterviewJD}
          onRefresh={loadInterviewJDs}
          onSave={handleSaveInterviewJD}
        />
      </div>
    </main>
  )
}

export default App

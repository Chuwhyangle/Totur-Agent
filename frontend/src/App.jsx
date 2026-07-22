import { useCallback, useEffect, useRef, useState } from 'react'

import {
  createInterviewJD,
  createSession,
  getHealth,
  getInterviewJDs,
  getPersonas,
  getSessionConversations,
  getSessions,
  postChat,
} from './api/tutorApi.js'
import ApiStatus from './components/ApiStatus.jsx'
import ChatInput from './components/ChatInput.jsx'
import ChatMessage from './components/ChatMessage.jsx'
import InterviewJDPanel from './components/InterviewJDPanel.jsx'
import Icon from './components/Icon.jsx'
import PersonaSelector from './components/PersonaSelector.jsx'
import SessionSidebar from './components/SessionSidebar.jsx'
import UserIdInput from './components/UserIdInput.jsx'

const DEFAULT_PERSONA_ID = 'tutor'
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
  const [forceWebSearch, setForceWebSearch] = useState(false)
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
  const [personas, setPersonas] = useState([])
  const [personasStatus, setPersonasStatus] = useState('idle')
  const [selectedPersonaId, setSelectedPersonaId] = useState(DEFAULT_PERSONA_ID)
  const [isTargetPanelOpen, setIsTargetPanelOpen] = useState(false)
  const [theme, setTheme] = useState(() => localStorage.getItem('tutor-theme') ?? 'light')
  const threadRef = useRef(null)

  const canSend = draftMessage.trim().length > 0 && userId.trim().length > 0 && !isSending
  const loadPersonas = useCallback(async () => {
    setPersonasStatus('loading')

    try {
      const { data } = await getPersonas()
      const nextPersonas = Array.isArray(data) ? data : []

      setPersonas(nextPersonas)
      setPersonasStatus('success')
      setApiStatus('online')
      setSelectedPersonaId((currentPersonaId) => {
        const stillAvailable = nextPersonas.some(
          (persona) => persona.persona_id === currentPersonaId,
        )

        return stillAvailable
          ? currentPersonaId
          : nextPersonas[0]?.persona_id ?? DEFAULT_PERSONA_ID
      })

      return nextPersonas
    } catch {
      setPersonas([])
      setPersonasStatus('error')
      setApiStatus('offline')

      return []
    }
  }, [])

  function handlePersonaChange(nextPersonaId) {
    // v0.3 起人设绑定在会话上；切换人设会退出当前会话，下一次发送时创建新会话。
    setSelectedPersonaId(nextPersonaId)
    setActiveSessionId(null)
    setActiveSessionStatus('idle')
    setMessages([])
  }

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
    setSelectedPersonaId(session.persona_id ?? DEFAULT_PERSONA_ID)
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
      const { data } = await createSession({
        user_id: trimmedUserId,
        persona_id: selectedPersonaId,
      })

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
      persona_id: selectedPersonaId,
      message: trimmedMessage,
      force_web_search: forceWebSearch,
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
    void loadPersonas()
    void loadSessions()
    void loadInterviewJDs()
  }, [checkApiHealth, loadPersonas, loadSessions, loadInterviewJDs])
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.classList.toggle('dark', theme === 'dark')
    document.documentElement.style.colorScheme = theme
    localStorage.setItem('tutor-theme', theme)
  }, [theme])

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, isSending])

  const activeSession = sessions.find((session) => session.id === activeSessionId)
  const quickPrompts = [
    { title: '制定学习计划', text: '根据我的目标，为我制定一份循序渐进的学习计划。', icon: 'target' },
    { title: '拆解一个概念', text: '请用清晰、可记忆的方式解释一个我正在学习的概念。', icon: 'sparkles' },
    { title: '模拟面试练习', text: '请围绕我的目标岗位，开始一轮循序渐进的模拟面试。', icon: 'message' },
  ]

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-block">
          <span className="brand-mark"><Icon name="sparkles" size={18} strokeWidth={1.6} /></span>
          <div><strong>Tutor Agent</strong><span>专注学习 · 清晰推进</span></div>
        </div>
        <div className="header-center">
          <span className="active-session-title">{activeSession?.title || '未命名会话'}</span>
          <ApiStatus status={apiStatus} />
        </div>
        <div className="header-controls">
          <PersonaSelector personas={personas} selectedPersonaId={selectedPersonaId} status={personasStatus} onPersonaChange={handlePersonaChange} />
          <button className="header-action-button" type="button" onClick={() => setIsTargetPanelOpen(true)}>
            <Icon name="target" size={17} /><span>学习目标</span>
          </button>
          <button className="theme-button" type="button" onClick={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')} aria-label="切换明暗主题">
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={18} />
          </button>
        </div>
      </header>

      <div className="workspace-layout">
        <SessionSidebar
          userId={userId}
          sessions={sessions}
          personas={personas}
          activeSessionId={activeSessionId}
          status={sessionsStatus}
          isCreating={isCreatingSession}
          onCreateSession={handleCreateSession}
          onRefreshSessions={loadSessions}
          onSelectSession={loadSessionMessages}
        />

        <section className="chat-surface" aria-label="聊天工作区">
          <div className="mobile-chat-toolbar">
            <UserIdInput userId={userId} onUserIdChange={handleUserIdChange} />
          </div>
          <div className="thread-preview" ref={threadRef}>
            {messages.length === 0 && activeSessionStatus !== 'loading' ? (
              <div className="welcome-state">
                <div className="welcome-orb"><Icon name="sparkles" size={26} strokeWidth={1.5} /></div>
                <p className="welcome-kicker">专注 · 清晰 · 推进</p>
                <h1>从今天开始，学得更清楚一点</h1>
                <p className="welcome-description">拆解概念、规划路径、围绕目标岗位练习与复盘。保持节奏，不必一次学完。</p>
                <div className="quick-prompt-grid">
                  {quickPrompts.map((prompt) => (
                    <button key={prompt.title} type="button" onClick={() => setDraftMessage(prompt.text)}>
                      <span><Icon name={prompt.icon} size={18} /></span>
                      <strong>{prompt.title}</strong>
                      <small>{prompt.text}</small>
                    </button>
                  ))}
                </div>
                {activeSessionStatus === 'error' ? <p className="inline-error">历史消息读取失败，但你仍可开始新对话。</p> : null}
              </div>
            ) : null}
            {activeSessionStatus === 'loading' ? <div className="thread-loading"><span /><span /><span /><p>正在整理学习记录…</p></div> : null}
            {messages.map((message) => (
              <ChatMessage key={message.id} role={message.role} text={message.text} reply={message.reply} debug={message.debug} />
            ))}
            {isSending ? (
              <div className="message-row assistant-row typing-row">
                <div className="message-avatar assistant-avatar"><Icon name="sparkles" size={17} /></div>
                <div className="typing-indicator"><span /><span /><span /></div>
              </div>
            ) : null}
          </div>
          <ChatInput
            message={draftMessage}
            onMessageChange={setDraftMessage}
            onSubmit={handleSendMessage}
            disabled={!canSend}
            isSending={isSending}
            webSearchEnabled={forceWebSearch}
            onWebSearchEnabledChange={setForceWebSearch}
          />
        </section>
      </div>

      <div className="desktop-user-control"><UserIdInput userId={userId} onUserIdChange={handleUserIdChange} /></div>
      <InterviewJDPanel
        userId={userId}
        items={interviewJDs}
        status={interviewJDsStatus}
        isSaving={isSavingInterviewJD}
        onRefresh={loadInterviewJDs}
        onSave={handleSaveInterviewJD}
        isOpen={isTargetPanelOpen}
        onClose={() => setIsTargetPanelOpen(false)}
      />
    </main>
  )
}

export default App

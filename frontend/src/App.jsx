import { useCallback, useEffect, useRef, useState } from 'react'

import {
  createInterviewJD,
  createSession,
  deleteAttachment,
  getAttachments,
  getHealth,
  getInterviewJDs,
  getModels,
  getPersonas,
  getSessionConversations,
  getSessions,
  postChat,
  postChatStream,
  retryAttachment,
  uploadAttachment,
  API_BASE_URL,
} from './api/tutorApi.js'
import ApiStatus from './components/ApiStatus.jsx'
import AttachmentPanel from './components/AttachmentPanel.jsx'
import ChatInput from './components/ChatInput.jsx'
import ChatMessage from './components/ChatMessage.jsx'
import InterviewJDPanel from './components/InterviewJDPanel.jsx'
import Icon from './components/Icon.jsx'
import ModelSelector from './components/ModelSelector.jsx'
import PersonaSelector from './components/PersonaSelector.jsx'
import SessionSidebar from './components/SessionSidebar.jsx'
import UserIdInput from './components/UserIdInput.jsx'
import { useAttachmentPolling } from './hooks/useAttachmentPolling.js'
import {
  addSelectedAttachmentId,
  attachmentErrorCode,
  attachmentErrorMessage,
  getAttachmentSendBlockReason,
  getInitialSelectedAttachmentIds,
  getSendableAttachmentIds,
  isAttachmentPending,
  reconcileSelectedAttachmentIds,
  shouldMarkApiOffline,
  validatePdfFile,
} from './utils/attachments.js'

const DEFAULT_PERSONA_ID = 'tutor'
const ATTACHMENT_ERRORS_REQUIRING_REFRESH = new Set([
  'attachment_index_missing',
  'attachment_not_found',
  'attachment_not_ready',
  'attachment_processing_failed',
])

const RAG_MODE_REQUEST_FIELDS = {
  off: { rag_enabled: false, force_rag: false },
  auto: { rag_enabled: true, force_rag: false },
  force: { rag_enabled: true, force_rag: true },
}

const WEB_SEARCH_MODE_REQUEST_FIELDS = {
  off: { web_search_enabled: false, force_web_search: false },
  auto: { web_search_enabled: true, force_web_search: false },
  force: { web_search_enabled: true, force_web_search: true },
}

function createErrorReply(error) {
  const errorCode = attachmentErrorCode(error)
  if (errorCode) {
    const answer = errorCode === 'attachment_no_relevant_evidence'
      ? '在所选附件中没有检索到与当前问题足够相关的内容。你可以换一种问法，或取消附件后继续普通提问。'
      : attachmentErrorMessage(error)
    return {
      answer,
      next_task: '检查附件状态，或调整当前选择后重试。',
      exercise: '尝试换一种更具体的问法。',
      checkpoints: ['附件仍只属于当前会话', '业务错误不会被误判为服务离线'],
    }
  }

  return {
    answer: '这次请求后端失败了，但页面没有崩溃。',
    next_task: `先确认后端是否运行在 ${API_BASE_URL}。`,
    exercise: '观察顶部 API 状态，并在服务恢复后重试。',
    checkpoints: ['用户消息已经保留', '错误被显示在聊天区', '调试详情里可以查看失败信息'],
  }
}

function createProtocolErrorReply() {
  return {
    answer: '后端流式响应缺少正式回复数据（done 事件没有 reply 字段）。',
    next_task: '检查 /chat/stream 的 done 事件结构，确认 reply 字段存在。',
    exercise: '展开调试详情，观察收到的 done 数据。',
    checkpoints: ['临时流式文本不会被包装成成功回复'],
  }
}

function buildAttachmentScopeKey(userId, personaId, sessionId) {
  return `${userId.trim()}::${personaId ?? ''}::${sessionId ?? 'none'}`
}

function upsertAttachment(items, nextAttachment) {
  const withoutCurrent = items.filter((attachment) => attachment.id !== nextAttachment.id)
  return [{ ...nextAttachment, clientAdded: true }, ...withoutCurrent]
}

function mergeListedAttachments(currentItems, listedItems) {
  const listedIds = new Set(listedItems.map((attachment) => attachment.id))
  const localItems = currentItems.filter(
    (attachment) => attachment.clientAdded && !listedIds.has(attachment.id),
  )
  return [...listedItems, ...localItems]
}

function App() {
  const [apiStatus, setApiStatus] = useState('checking')
  const [userId, setUserId] = useState('demo-user')
  const [draftMessage, setDraftMessage] = useState('')
  const [webSearchMode, setWebSearchMode] = useState('auto')
  const [ragMode, setRagMode] = useState('auto')
  const [messages, setMessages] = useState([])
  const [isSending, setIsSending] = useState(false)
  const [streamingEnabled, setStreamingEnabled] = useState(() => localStorage.getItem('tutor-streaming') !== 'false')
  const [streamingMessage, setStreamingMessage] = useState(null) // In-progress streaming message
  const [streamingTool, setStreamingTool] = useState(null) // Currently running tool
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
  const [models, setModels] = useState([])
  const [modelsStatus, setModelsStatus] = useState('idle')
  const [selectedModelId, setSelectedModelId] = useState(() => localStorage.getItem('tutor-model') ?? null)
  const [isTargetPanelOpen, setIsTargetPanelOpen] = useState(false)
  const [theme, setTheme] = useState(() => localStorage.getItem('tutor-theme') ?? 'light')
  const [attachments, setAttachments] = useState([])
  const [attachmentStatus, setAttachmentStatus] = useState('idle')
  const [selectedAttachmentIds, setSelectedAttachmentIds] = useState([])
  const [attachmentError, setAttachmentError] = useState('')
  const [attachmentActionStates, setAttachmentActionStates] = useState({})
  const [attachmentActionErrors, setAttachmentActionErrors] = useState({})
  const [isUploadingAttachment, setIsUploadingAttachment] = useState(false)
  const threadRef = useRef(null)
  const attachmentScopeKeyRef = useRef('')
  const attachmentListRequestIdRef = useRef(0)
  const attachmentSelectionTouchedRef = useRef(false)
  const sessionMessageRequestIdRef = useRef(0)
  const sessionCreateRequestIdRef = useRef(0)
  const streamAbortControllerRef = useRef(null)

  const attachmentSendBlockReason = getAttachmentSendBlockReason(
    attachments,
    selectedAttachmentIds,
  )
  const canSend = draftMessage.trim().length > 0
    && userId.trim().length > 0
    && !isSending
    && !attachmentSendBlockReason

  function updateApiStatusAfterError(error) {
    setApiStatus(shouldMarkApiOffline(error) ? 'offline' : 'online')
  }

  function activateAttachmentScope(
    nextSessionId,
    nextUserId,
    nextPersonaId,
    { preserveSessionCreation = false } = {},
  ) {
    const nextScopeKey = buildAttachmentScopeKey(nextUserId, nextPersonaId, nextSessionId)
    if (!preserveSessionCreation) {
      sessionCreateRequestIdRef.current += 1
      setIsCreatingSession(false)
    }
    attachmentScopeKeyRef.current = nextScopeKey
    attachmentListRequestIdRef.current += 1
    attachmentSelectionTouchedRef.current = false
    setAttachments([])
    setSelectedAttachmentIds([])
    setAttachmentStatus(nextSessionId ? 'loading' : 'idle')
    setAttachmentError('')
    setAttachmentActionStates({})
    setAttachmentActionErrors({})
    return nextScopeKey
  }

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
    } catch (error) {
      setPersonas([])
      setPersonasStatus('error')
      updateApiStatusAfterError(error)
      return []
    }
  }, [])

  const loadModels = useCallback(async () => {
    setModelsStatus('loading')
    try {
      const { data } = await getModels()
      const nextModels = Array.isArray(data) ? data : []
      setModels(nextModels)
      setModelsStatus('success')
      setApiStatus('online')
      setSelectedModelId((currentModelId) => {
        const stillAvailable = nextModels.some((model) => model.model_id === currentModelId)
        return stillAvailable ? currentModelId : (nextModels[0]?.model_id ?? null)
      })
      return nextModels
    } catch (error) {
      setModels([])
      setModelsStatus('error')
      updateApiStatusAfterError(error)
      return []
    }
  }, [])

  function handlePersonaChange(nextPersonaId) {
    sessionMessageRequestIdRef.current += 1
    activateAttachmentScope(null, userId, nextPersonaId)
    setSelectedPersonaId(nextPersonaId)
    setActiveSessionId(null)
    setActiveSessionStatus('idle')
    setMessages([])
  }

  function handleUserIdChange(nextUserId) {
    sessionMessageRequestIdRef.current += 1
    activateAttachmentScope(null, nextUserId, selectedPersonaId)
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
    return [...items].reverse().flatMap((item) => [
      { id: `history-user-${item.id}`, role: 'user', text: item.message },
      { id: `history-assistant-${item.id}`, role: 'assistant', reply: item.reply },
    ])
  }

  function upsertSession(nextSession) {
    setSessions((currentSessions) => {
      const withoutCurrent = currentSessions.filter((session) => session.id !== nextSession.id)
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
    if (!silent) setSessionsStatus('loading')

    try {
      const { data } = await getSessions(trimmedUserId)
      const nextSessions = Array.isArray(data?.items) ? data.items : []
      setSessions(nextSessions)
      setSessionsStatus('success')
      setApiStatus('online')
      return nextSessions
    } catch (error) {
      setSessions([])
      setSessionsStatus('error')
      updateApiStatusAfterError(error)
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
    if (!silent) setInterviewJDsStatus('loading')

    try {
      const { data } = await getInterviewJDs(trimmedUserId)
      const nextJDs = Array.isArray(data?.items) ? data.items : []
      setInterviewJDs(nextJDs)
      setInterviewJDsStatus('success')
      setApiStatus('online')
      return nextJDs
    } catch (error) {
      setInterviewJDs([])
      setInterviewJDsStatus('error')
      updateApiStatusAfterError(error)
      return []
    }
  }, [userId])

  async function handleSaveInterviewJD(requestBody) {
    if (isSavingInterviewJD) return null
    setIsSavingInterviewJD(true)

    try {
      const { data } = await createInterviewJD(requestBody)
      setInterviewJDs((currentJDs) => [data, ...currentJDs])
      setInterviewJDsStatus('success')
      setApiStatus('online')
      return data
    } catch (error) {
      setInterviewJDsStatus('error')
      updateApiStatusAfterError(error)
      return null
    } finally {
      setIsSavingInterviewJD(false)
    }
  }

  async function loadSessionMessages(session) {
    const requestId = sessionMessageRequestIdRef.current + 1
    sessionMessageRequestIdRef.current = requestId
    activateAttachmentScope(session.id, userId, session.persona_id ?? DEFAULT_PERSONA_ID)
    setActiveSessionId(session.id)
    setSelectedPersonaId(session.persona_id ?? DEFAULT_PERSONA_ID)
    setActiveSessionStatus('loading')
    setMessages([])

    try {
      const { data } = await getSessionConversations(session.id)
      if (requestId !== sessionMessageRequestIdRef.current) return
      const items = Array.isArray(data?.items) ? data.items : []
      setMessages(buildMessagesFromHistoryItems(items))
      setActiveSessionStatus('success')
      setApiStatus('online')
    } catch (error) {
      if (requestId !== sessionMessageRequestIdRef.current || error?.isAbortError) return
      setMessages([])
      setActiveSessionStatus('error')
      updateApiStatusAfterError(error)
    }
  }

  async function handleCreateSession() {
    const trimmedUserId = userId.trim()
    if (!trimmedUserId || isCreatingSession) return null

    const requestId = sessionCreateRequestIdRef.current + 1
    sessionCreateRequestIdRef.current = requestId
    setIsCreatingSession(true)

    try {
      const { data } = await createSession({
        user_id: trimmedUserId,
        persona_id: selectedPersonaId,
      })
      if (requestId !== sessionCreateRequestIdRef.current) return null

      upsertSession(data)
      setSessionsStatus('success')
      activateAttachmentScope(data.id, trimmedUserId, selectedPersonaId, {
        preserveSessionCreation: true,
      })
      setActiveSessionId(data.id)
      setActiveSessionStatus('success')
      setMessages([])
      setApiStatus('online')
      return data
    } catch (error) {
      if (requestId !== sessionCreateRequestIdRef.current || error?.isAbortError) return null
      setSessionsStatus('error')
      updateApiStatusAfterError(error)
      return null
    } finally {
      if (requestId === sessionCreateRequestIdRef.current) setIsCreatingSession(false)
    }
  }

  async function ensureActiveSession() {
    const currentSession = sessions.find((session) => session.id === activeSessionId)
    return currentSession ?? handleCreateSession()
  }

  const refreshAttachments = useCallback(async ({ signal, initial = false } = {}) => {
    const trimmedUserId = userId.trim()
    const sessionId = activeSessionId
    if (!trimmedUserId || !sessionId) return []

    const scopeKey = buildAttachmentScopeKey(trimmedUserId, selectedPersonaId, sessionId)
    const requestId = attachmentListRequestIdRef.current + 1
    attachmentListRequestIdRef.current = requestId
    if (initial) setAttachmentStatus('loading')

    try {
      const { data } = await getAttachments(sessionId, trimmedUserId, { signal })
      if (
        scopeKey !== attachmentScopeKeyRef.current
        || requestId !== attachmentListRequestIdRef.current
      ) return []

      const listedItems = Array.isArray(data?.items) ? data.items : []
      setAttachments((currentItems) => {
        const nextItems = mergeListedAttachments(currentItems, listedItems)
        setSelectedAttachmentIds((currentIds) => {
          if (initial && !attachmentSelectionTouchedRef.current) {
            return getInitialSelectedAttachmentIds(nextItems)
          }
          return reconcileSelectedAttachmentIds(currentIds, nextItems)
        })
        return nextItems
      })
      setAttachmentStatus('success')
      setAttachmentError('')
      setApiStatus('online')
      return listedItems
    } catch (error) {
      if (
        error?.isAbortError
        || scopeKey !== attachmentScopeKeyRef.current
        || requestId !== attachmentListRequestIdRef.current
      ) return []
      setAttachmentStatus('error')
      setAttachmentError(attachmentErrorMessage(error, '附件列表读取失败，请稍后重试。'))
      updateApiStatusAfterError(error)
      return []
    }
  }, [activeSessionId, selectedPersonaId, userId])

  useEffect(() => {
    const scopeKey = buildAttachmentScopeKey(userId, selectedPersonaId, activeSessionId)
    if (attachmentScopeKeyRef.current !== scopeKey) {
      activateAttachmentScope(activeSessionId, userId, selectedPersonaId)
    }
    if (!activeSessionId || !userId.trim()) return undefined

    const controller = new AbortController()
    void refreshAttachments({ signal: controller.signal, initial: true })
    return () => controller.abort()
  }, [activeSessionId, refreshAttachments, selectedPersonaId, userId])

  const hasPendingAttachments = attachments.some(
    (attachment) => isAttachmentPending(attachment.status),
  )
  useAttachmentPolling({
    enabled: Boolean(activeSessionId && hasPendingAttachments),
    poll: refreshAttachments,
    scopeKey: attachmentScopeKeyRef.current,
  })

  async function handleUploadAttachment(file) {
    if (isUploadingAttachment) return
    const validationMessage = validatePdfFile(file)
    if (validationMessage) {
      setAttachmentError(validationMessage)
      return
    }

    const trimmedUserId = userId.trim()
    const personaId = selectedPersonaId
    if (!trimmedUserId) {
      setAttachmentError('请先填写用户 ID。')
      return
    }

    const initialScopeKey = attachmentScopeKeyRef.current
    let operationScopeKey = initialScopeKey
    setIsUploadingAttachment(true)
    setAttachmentError('')

    try {
      const session = await ensureActiveSession()
      if (!session) {
        if (initialScopeKey !== attachmentScopeKeyRef.current) return
        throw new Error('没有可用的会话')
      }

      operationScopeKey = buildAttachmentScopeKey(trimmedUserId, personaId, session.id)
      if (operationScopeKey !== attachmentScopeKeyRef.current) return
      attachmentListRequestIdRef.current += 1

      const { data } = await uploadAttachment(session.id, trimmedUserId, file)
      if (operationScopeKey !== attachmentScopeKeyRef.current) return

      attachmentSelectionTouchedRef.current = true
      setAttachments((currentItems) => upsertAttachment(currentItems, data))
      setSelectedAttachmentIds((currentIds) => addSelectedAttachmentId(currentIds, data.id))
      setAttachmentStatus('success')
      setAttachmentError('')
      setApiStatus('online')
    } catch (error) {
      if (error?.isAbortError || operationScopeKey !== attachmentScopeKeyRef.current) return
      setAttachmentError(attachmentErrorMessage(error, 'PDF 上传失败，请稍后重试。'))
      updateApiStatusAfterError(error)
    } finally {
      setIsUploadingAttachment(false)
    }
  }

  function handleToggleAttachment(attachmentId) {
    attachmentSelectionTouchedRef.current = true
    setAttachmentError('')
    setSelectedAttachmentIds((currentIds) => {
      if (currentIds.includes(attachmentId)) {
        return currentIds.filter((currentId) => currentId !== attachmentId)
      }
      if (currentIds.length >= 5) {
        setAttachmentError('每次最多选择 5 个附件。')
        return currentIds
      }
      return [...currentIds, attachmentId]
    })
  }

  async function handleRetryAttachment(attachmentId) {
    const trimmedUserId = userId.trim()
    const sessionId = activeSessionId
    const scopeKey = buildAttachmentScopeKey(trimmedUserId, selectedPersonaId, sessionId)
    if (!trimmedUserId || !sessionId || scopeKey !== attachmentScopeKeyRef.current) return

    attachmentListRequestIdRef.current += 1
    setAttachmentActionStates((current) => ({ ...current, [attachmentId]: 'retrying' }))
    setAttachmentActionErrors((current) => ({ ...current, [attachmentId]: '' }))

    try {
      const { data } = await retryAttachment(sessionId, attachmentId, trimmedUserId)
      if (scopeKey !== attachmentScopeKeyRef.current) return
      setAttachments((currentItems) => currentItems.map(
        (attachment) => attachment.id === attachmentId ? data : attachment,
      ))
      setAttachmentStatus('success')
      setAttachmentError('')
      setApiStatus('online')
    } catch (error) {
      if (scopeKey !== attachmentScopeKeyRef.current || error?.isAbortError) return
      setAttachmentActionErrors((current) => ({
        ...current,
        [attachmentId]: attachmentErrorMessage(error, '附件重试失败，请稍后再试。'),
      }))
      updateApiStatusAfterError(error)
    } finally {
      if (scopeKey === attachmentScopeKeyRef.current) {
        setAttachmentActionStates((current) => ({ ...current, [attachmentId]: '' }))
      }
    }
  }

  async function handleDeleteAttachment(attachmentId) {
    const trimmedUserId = userId.trim()
    const sessionId = activeSessionId
    const scopeKey = buildAttachmentScopeKey(trimmedUserId, selectedPersonaId, sessionId)
    if (!trimmedUserId || !sessionId || scopeKey !== attachmentScopeKeyRef.current) return

    attachmentListRequestIdRef.current += 1
    setAttachmentActionStates((current) => ({ ...current, [attachmentId]: 'deleting' }))
    setAttachmentActionErrors((current) => ({ ...current, [attachmentId]: '' }))

    try {
      await deleteAttachment(sessionId, attachmentId, trimmedUserId)
      if (scopeKey !== attachmentScopeKeyRef.current) return
      attachmentListRequestIdRef.current += 1
      setAttachments((currentItems) => currentItems.filter(
        (attachment) => attachment.id !== attachmentId,
      ))
      setSelectedAttachmentIds((currentIds) => currentIds.filter(
        (currentId) => currentId !== attachmentId,
      ))
      setAttachmentStatus('success')
      setAttachmentError('')
      setApiStatus('online')
    } catch (error) {
      if (scopeKey !== attachmentScopeKeyRef.current || error?.isAbortError) return
      setAttachmentActionErrors((current) => ({
        ...current,
        [attachmentId]: attachmentErrorMessage(error, '附件删除失败，请稍后再试。'),
      }))
      updateApiStatusAfterError(error)
    } finally {
      if (scopeKey === attachmentScopeKeyRef.current) {
        setAttachmentActionStates((current) => ({ ...current, [attachmentId]: '' }))
      }
    }
  }

  async function handleSendMessage(event) {
    event.preventDefault()

    const trimmedMessage = draftMessage.trim()
    const trimmedUserId = userId.trim()
    if (!trimmedMessage || !trimmedUserId || isSending) return
    if (attachmentSendBlockReason) {
      setAttachmentError(attachmentSendBlockReason)
      return
    }

    const attachmentIds = getSendableAttachmentIds(attachments, selectedAttachmentIds)
    const ragModeForRequest = ragMode
    const webSearchModeForRequest = webSearchMode
    const baseRequestBody = {
      user_id: trimmedUserId,
      session_id: activeSessionId,
      persona_id: selectedPersonaId,
      message: trimmedMessage,
      model_id: selectedModelId ?? undefined,
      ...WEB_SEARCH_MODE_REQUEST_FIELDS[webSearchModeForRequest],
      ...RAG_MODE_REQUEST_FIELDS[ragModeForRequest],
      attachment_ids: attachmentIds,
    }
    const userMessage = {
      id: `message-user-${Date.now()}`,
      role: 'user',
      text: trimmedMessage,
    }

    let chatScopeKey = attachmentScopeKeyRef.current
    setMessages((currentMessages) => [...currentMessages, userMessage])
    setDraftMessage('')
    setIsSending(true)
    setStreamingMessage(null)
    const streamAbortController = streamingEnabled ? new AbortController() : null
    streamAbortControllerRef.current = streamAbortController

    setStreamingTool(null)

    try {
      const activeSession = await ensureActiveSession()
      if (!activeSession) throw new Error('没有可用的会话')

      const chatRequestBody = { ...baseRequestBody, session_id: activeSession.id }
      chatScopeKey = buildAttachmentScopeKey(
        trimmedUserId,
        selectedPersonaId,
        activeSession.id,
      )
      // “本轮强制使用”只对本次成功发出的请求生效，发出后自动回到自动判断。
      if (ragModeForRequest === 'force') setRagMode('auto')
      if (webSearchModeForRequest === 'force') setWebSearchMode('auto')

      if (streamingEnabled) {
        // Streaming mode
        const messageId = `message-assistant-${Date.now()}`
        let accumulatedText = ''
        let finalData = null

        // 流开始时就创建 assistant 流式消息区域：
        // 即使工具调用先于第一个 token 到达，也能立即显示工具状态。
        setStreamingMessage({
          id: messageId,
          role: 'assistant',
          text: '',
          isStreaming: true,
        })

        await postChatStream(
          chatRequestBody,
          {
            onToken: (text) => {
              // token 按到达顺序持续追加；工具调用只更新工具状态，不清空正文。
              accumulatedText += text
              setStreamingMessage({
                id: messageId,
                role: 'assistant',
                text: accumulatedText,
                isStreaming: true,
              })
            },
            onToolCall: (tool, args) => {
              setStreamingTool({ tool, args, status: 'running' })
            },
            onToolResult: () => {
              setStreamingTool(null)
            },
            onDone: (data) => {
              finalData = data
            },
            onError: (message) => {
              console.error('Stream error:', message)
            },
          },
          { signal: streamAbortController.signal },
        )


        if (chatScopeKey !== attachmentScopeKeyRef.current) return

        if (streamAbortController.signal.aborted) return

        // Finalize the streaming message.
        // done.reply 是最终回复的唯一数据源；临时流式文本只用于预览。
        const streamDebug = {
          url: `${API_BASE_URL}/chat/stream`,
          method: 'POST',
          requestBody: chatRequestBody,
          responseBody: {
            session_id: finalData?.session_id ?? activeSession.id,
            done: finalData ?? null,
          },
        }
        const assistantMessage = finalData?.reply
          ? {
              id: messageId,
              role: 'assistant',
              reply: finalData.reply,
              debug: streamDebug,
            }
          : {
              id: messageId,
              role: 'assistant',
              reply: createProtocolErrorReply(),
              debug: streamDebug,
            }
        setMessages((currentMessages) => [...currentMessages, assistantMessage])
        setStreamingMessage(null)
        setStreamingTool(null)
        setActiveSessionId(finalData?.session_id ?? activeSession.id)
        setActiveSessionStatus('success')
        setApiStatus('online')
        void loadSessions({ silent: true })
      } else {
        // Non-streaming mode (fallback)
        const { data, debug } = await postChat(chatRequestBody)
        if (chatScopeKey !== attachmentScopeKeyRef.current) return

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
        void loadSessions({ silent: true })
      }
    } catch (error) {
      if (chatScopeKey !== attachmentScopeKeyRef.current || error?.isAbortError) return

      const errorMessage = {
        id: `message-error-${Date.now()}`,
        role: 'assistant',
        reply: createErrorReply(error),
        debug: error.debug ?? {
          url: `${API_BASE_URL}/${streamingEnabled ? 'chat/stream' : 'chat'}`,
          method: 'POST',
          requestBody: baseRequestBody,
          error: error.message,
        },
      }
      setMessages((currentMessages) => [...currentMessages, errorMessage])
      setStreamingMessage(null)
      setStreamingTool(null)
      updateApiStatusAfterError(error)
      if (ATTACHMENT_ERRORS_REQUIRING_REFRESH.has(attachmentErrorCode(error))) {
        await refreshAttachments()
      }
    } finally {
      if (streamAbortControllerRef.current === streamAbortController) {
        streamAbortControllerRef.current = null
        setIsSending(false)
      }
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
    void loadModels()
    void loadSessions()
    void loadInterviewJDs()
  }, [checkApiHealth, loadPersonas, loadModels, loadSessions, loadInterviewJDs])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.classList.toggle('dark', theme === 'dark')
    document.documentElement.style.colorScheme = theme
    localStorage.setItem('tutor-theme', theme)
  }, [theme])

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, isSending, streamingMessage])

  function handleStreamingToggle() {
    const next = !streamingEnabled
    setStreamingEnabled(next)
    localStorage.setItem('tutor-streaming', String(next))
  }

  function handleModelChange(nextModelId) {
    setSelectedModelId(nextModelId)
    localStorage.setItem('tutor-model', nextModelId)
  }

  function handleStopStreaming() {
    streamAbortControllerRef.current?.abort()
    setStreamingMessage(null)
    setStreamingTool(null)
    setIsSending(false)
  }

  const activeSession = sessions.find((session) => session.id === activeSessionId)
  const quickPrompts = [
    { title: '制定学习计划', text: '根据我的目标，为我制定一份循序渐进的学习计划。', icon: 'target' },
    { title: '拆解一个概念', text: '请用清晰、可记忆的方式解释一个我正在学习的概念。', icon: 'sparkles' },
    { title: '模拟面试练习', text: '请围绕我的目标岗位，开始一轮循序渐进的模拟面试。', icon: 'message' },
  ]

  const attachmentPanel = (
    <AttachmentPanel
      attachments={attachments}
      selectedAttachmentIds={selectedAttachmentIds}
      status={attachmentStatus}
      error={attachmentError}
      actionErrors={attachmentActionErrors}
      actionStates={attachmentActionStates}
      sendBlockReason={attachmentSendBlockReason}
      disabled={isSending || isUploadingAttachment || !userId.trim()}
      onUpload={handleUploadAttachment}
      onToggle={handleToggleAttachment}
      onRetry={handleRetryAttachment}
      onDelete={handleDeleteAttachment}
    />
  )

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
          <ModelSelector models={models} selectedModelId={selectedModelId} status={modelsStatus} onModelChange={handleModelChange} />
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
            {isSending && streamingMessage ? (
              <ChatMessage
                key={streamingMessage.id}
                role="assistant"
                text={streamingMessage.text}
                isStreaming={streamingMessage.isStreaming}
                streamingTool={streamingTool}
              />
            ) : null}
            {isSending && !streamingMessage ? (
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
            webSearchMode={webSearchMode}
            onWebSearchModeChange={setWebSearchMode}
            ragMode={ragMode}
            onRagModeChange={setRagMode}
            streamingEnabled={streamingEnabled}
            onStreamingEnabledChange={handleStreamingToggle}
            onStopStreaming={streamingEnabled ? handleStopStreaming : undefined}
            attachmentPanel={attachmentPanel}
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

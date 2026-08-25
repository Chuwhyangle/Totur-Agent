import { useCallback, useEffect, useRef, useState } from 'react'

import {
  createInterviewJD,
  createCustomPersona,
  createSession,
  createWorkspace,
  deleteAttachment,
  deleteWorkspaceAsset,
  getAttachments,
  getHealth,
  getInterviewJDs,
  getModels,
  getPersonas,
  updateCustomPersona,
  disableCustomPersona,
  getSessionConversations,
  getSessions,
  getWorkspaceArtifactContent,
  getWorkspaceArtifactDownloadUrl,
  getWorkspaceArtifacts,
  getWorkspaceAssetDownloadUrl,
  getWorkspaceAssets,
  getWorkspaceTasks,
  getWorkspaceAgentInstructions,
  getWorkspaces,
  postChat,
  postChatStream,
  retryAttachment,
  retryWorkspaceAsset,
  uploadAttachment,
  uploadWorkspaceAsset,
  archiveWorkspace,
  restoreWorkspace,
  saveWorkspaceAgentInstructions,
  clearWorkspaceAgentInstructions,
  API_BASE_URL,
} from './api/tutorApi.js'
import ApiStatus from './components/ApiStatus.jsx'
import ChatInput from './components/ChatInput.jsx'
import ChatMessage from './components/ChatMessage.jsx'
import InterviewJDPanel from './components/InterviewJDPanel.jsx'
import Icon from './components/Icon.jsx'
import ModelSelector from './components/ModelSelector.jsx'
import PersonaSelector from './components/PersonaSelector.jsx'
import PersonaManager from './components/PersonaManager.jsx'
import SessionSidebar from './components/SessionSidebar.jsx'
import WorkspacePanel from './components/workspaces/WorkspacePanel.jsx'
import KnowledgeLibrary from './components/KnowledgeLibrary.jsx'
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
  validateAttachmentFile,
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
  documents: { rag_enabled: true, force_rag: true, rag_scope: 'user_documents' },
}

const WEB_SEARCH_MODE_REQUEST_FIELDS = {
  off: { web_search_enabled: false, force_web_search: false },
  auto: { web_search_enabled: true, force_web_search: false },
  force: { web_search_enabled: true, force_web_search: true },
}

function monotonicNow() {
  return typeof performance !== 'undefined' ? performance.now() : Date.now()
}

function getErrorDisplayMessage(error) {
  if (typeof error?.detail?.message === 'string') {
    return error.detail.message
  }

  if (typeof error?.detail === 'string') {
    return error.detail
  }

  if (typeof error?.responseBody?.detail?.message === 'string') {
    return error.responseBody.detail.message
  }

  if (typeof error?.responseBody?.detail === 'string') {
    return error.responseBody.detail
  }

  if (typeof error?.responseBody?.message === 'string') {
    return error.responseBody.message
  }

  if (typeof error?.message === 'string' && error.message.trim()) {
    return error.message
  }

  if (typeof error?.detail?.error === 'string') {
    return `请求失败：${error.detail.error}`
  }

  return '请求失败，请稍后重试。'
}

function createErrorReply(error) {
  return {
    answer: getErrorDisplayMessage(error),
    sources: [],
  }
}

function createProtocolErrorReply() {
  const answer = '后端流式响应缺少正式回复数据（done 事件没有 reply 字段）。请检查 /chat/stream 的 done 事件结构，或展开调试详情观察收到的 done 数据。'
  return { answer, sources: [] }
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
  const [sessionCreateError, setSessionCreateError] = useState('')
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [activeSessionStatus, setActiveSessionStatus] = useState('idle')
  const [isCreatingSession, setIsCreatingSession] = useState(false)
  const [interviewJDs, setInterviewJDs] = useState([])
  const [interviewJDsStatus, setInterviewJDsStatus] = useState('idle')
  const [isSavingInterviewJD, setIsSavingInterviewJD] = useState(false)
  const [personas, setPersonas] = useState([])
  const [personasStatus, setPersonasStatus] = useState('idle')
  const [selectedPersonaId, setSelectedPersonaId] = useState(DEFAULT_PERSONA_ID)
  const [personaManagerOpen, setPersonaManagerOpen] = useState(false)
  const [models, setModels] = useState([])
  const [modelsStatus, setModelsStatus] = useState('idle')
  const [selectedModelId, setSelectedModelId] = useState(() => localStorage.getItem('tutor-model') ?? null)
  const [isTargetPanelOpen, setIsTargetPanelOpen] = useState(false)
  const [knowledgeLibraryOpen, setKnowledgeLibraryOpen] = useState(false)
  const [theme, setTheme] = useState(() => localStorage.getItem('tutor-theme') ?? 'light')
  const [attachments, setAttachments] = useState([])
  const [attachmentStatus, setAttachmentStatus] = useState('idle')
  const [selectedAttachmentIds, setSelectedAttachmentIds] = useState([])
  const [attachmentError, setAttachmentError] = useState('')
  const [composerNotice, setComposerNotice] = useState('')
  const [attachmentActionStates, setAttachmentActionStates] = useState({})
  const [attachmentActionErrors, setAttachmentActionErrors] = useState({})
  const [isUploadingAttachment, setIsUploadingAttachment] = useState(false)
  const [workspaceFeatureStatus, setWorkspaceFeatureStatus] = useState('idle')
  const [workspaces, setWorkspaces] = useState([])
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState(null)
  const [workspacePanelOpen, setWorkspacePanelOpen] = useState(false)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => localStorage.getItem('tutor-sidebar-collapsed') === 'true')
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false)
  const [workspaceInstructions, setWorkspaceInstructions] = useState({ content: '', version: 0 })
  const [workspaceAssets, setWorkspaceAssets] = useState([])
  const [workspaceAssetsStatus, setWorkspaceAssetsStatus] = useState('idle')
  const [workspaceAssetsError, setWorkspaceAssetsError] = useState('')
  const [workspaceAssetActionStates, setWorkspaceAssetActionStates] = useState({})
  const [workspaceTasks, setWorkspaceTasks] = useState([])
  const [workspaceTasksStatus, setWorkspaceTasksStatus] = useState('idle')
  const [workspaceTasksError, setWorkspaceTasksError] = useState('')
  const [workspaceArtifacts, setWorkspaceArtifacts] = useState([])
  const [workspaceArtifactsStatus, setWorkspaceArtifactsStatus] = useState('idle')
  const [workspaceArtifactsError, setWorkspaceArtifactsError] = useState('')
  const [selectedArtifact, setSelectedArtifact] = useState(null)
  const [artifactContent, setArtifactContent] = useState('')
  const [artifactContentLoading, setArtifactContentLoading] = useState(false)
  const threadRef = useRef(null)
  const attachmentScopeKeyRef = useRef('')
  const attachmentListRequestIdRef = useRef(0)
  const attachmentSelectionTouchedRef = useRef(false)
  const sessionMessageRequestIdRef = useRef(0)
  const sessionCreateRequestIdRef = useRef(0)
  const streamAbortControllerRef = useRef(null)
  const workspaceRequestIdRef = useRef(0)

  const activeSession = sessions.find((session) => session.id === activeSessionId)
  const activeSessionWorkspace = workspaces.find((workspace) => workspace.id === activeSession?.workspace_id)
  const attachmentSendBlockReason = getAttachmentSendBlockReason(
    attachments,
    selectedAttachmentIds,
  )
  const canSend = draftMessage.trim().length > 0
    && userId.trim().length > 0
    && !isSending
    && activeSessionStatus !== 'loading'
    && !attachmentSendBlockReason
    && activeSessionWorkspace?.status !== 'ARCHIVED'

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
      const { data } = await getPersonas({ userId: userId.trim() })
      const nextPersonas = Array.isArray(data) ? data : []
      setPersonas(nextPersonas)
      setPersonasStatus('success')
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
      return []
    }
  }, [userId])

  async function handleCreatePersona(payload) {
    const { data } = await createCustomPersona(payload)
    setPersonas((current) => [...current, data])
    setSelectedPersonaId(data.persona_id)
  }

  async function handleUpdatePersona(personaId, payload) {
    const { data } = await updateCustomPersona(personaId, payload)
    setPersonas((current) => current.map((item) => item.persona_id === personaId ? data : item))
  }

  async function handleDisablePersona(personaId) {
    await disableCustomPersona(personaId, userId.trim())
    setPersonas((current) => current.filter((item) => item.persona_id !== personaId))
    setSelectedPersonaId((current) => current === personaId ? DEFAULT_PERSONA_ID : current)
  }

  const loadModels = useCallback(async () => {
    setModelsStatus('loading')
    try {
      const { data } = await getModels()
      const nextModels = Array.isArray(data) ? data : []
      setModels(nextModels)
      setModelsStatus('success')
      setSelectedModelId((currentModelId) => {
        const stillAvailable = nextModels.some((model) => model.model_id === currentModelId)
        return stillAvailable ? currentModelId : (nextModels[0]?.model_id ?? null)
      })
      return nextModels
    } catch {
      setModels([])
      setModelsStatus('error')
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
    setSelectedWorkspaceId(null)
  }

  function handleUserIdChange(nextUserId) {
    sessionMessageRequestIdRef.current += 1
    activateAttachmentScope(null, nextUserId, selectedPersonaId)
    setUserId(nextUserId)
    setMessages([])
    setSessions([])
    setSessionsStatus('idle')
    setSessionCreateError('')
    setActiveSessionId(null)
    setActiveSessionStatus('idle')
    setInterviewJDs([])
    setInterviewJDsStatus('idle')
    workspaceRequestIdRef.current += 1
    setWorkspaces([])
    setSelectedWorkspaceId(null)
    setWorkspaceAssets([])
    setWorkspaceTasks([])
    setWorkspaceArtifacts([])
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
      setSessionCreateError('请先填写用户 ID。')
      return []
    }
    if (!silent) {
      setSessionsStatus('loading')
      setSessionCreateError('')
    }

    try {
      const { data } = await getSessions(trimmedUserId)
      const nextSessions = Array.isArray(data?.items) ? data.items : []
      setSessions(nextSessions)
      setSessionsStatus('success')
      setSessionCreateError('')
      return nextSessions
    } catch {
      setSessions([])
      setSessionsStatus('error')
      return []
    }
  }, [userId])

  const loadWorkspaces = useCallback(async ({ silent = false } = {}) => {
    const trimmedUserId = userId.trim()
    if (!trimmedUserId) {
      setWorkspaces([])
      setWorkspaceFeatureStatus('idle')
      return []
    }
    if (!silent) setWorkspaceFeatureStatus('loading')
    try {
      const { data } = await getWorkspaces(trimmedUserId)
      const nextWorkspaces = Array.isArray(data?.items) ? data.items : []
      setWorkspaces(nextWorkspaces)
      setWorkspaceFeatureStatus('available')
      setSelectedWorkspaceId((currentId) => currentId && nextWorkspaces.some((item) => item.id === currentId) ? currentId : null)
      return nextWorkspaces
    } catch {
      setWorkspaces([])
      setSelectedWorkspaceId(null)
      setWorkspaceFeatureStatus('error')
      return []
    }
  }, [userId])

  const loadWorkspaceAssets = useCallback(async ({ signal, workspaceId = selectedWorkspaceId } = {}) => {
    const trimmedUserId = userId.trim()
    if (!trimmedUserId || !workspaceId) return []
    const requestId = workspaceRequestIdRef.current
    if (workspaceAssets.length === 0) setWorkspaceAssetsStatus('loading')
    try {
      const { data } = await getWorkspaceAssets(workspaceId, trimmedUserId, { signal })
      if (requestId !== workspaceRequestIdRef.current) return []
      const items = Array.isArray(data?.items) ? data.items : []
      setWorkspaceAssets(items)
      setWorkspaceAssetsStatus('success')
      setWorkspaceAssetsError('')
      return items
    } catch (error) {
      if (error?.isAbortError || requestId !== workspaceRequestIdRef.current) return []
      setWorkspaceAssetsStatus('error')
      setWorkspaceAssetsError(error?.detail?.message ?? error?.message ?? 'Workspace Asset 读取失败。')
      return []
    }
  }, [selectedWorkspaceId, userId, workspaceAssets.length])

  async function loadWorkspaceData(workspaceId = selectedWorkspaceId) {
    const trimmedUserId = userId.trim()
    if (!trimmedUserId || !workspaceId) return
    const requestId = workspaceRequestIdRef.current
    setWorkspaceTasksStatus('loading')
    setWorkspaceArtifactsStatus('loading')
    try {
      const [taskResult, artifactResult] = await Promise.all([
        getWorkspaceTasks(workspaceId, trimmedUserId),
        getWorkspaceArtifacts(workspaceId, trimmedUserId),
      ])
      if (requestId !== workspaceRequestIdRef.current) return
      setWorkspaceTasks(Array.isArray(taskResult.data?.items) ? taskResult.data.items : [])
      setWorkspaceArtifacts(Array.isArray(artifactResult.data?.items) ? artifactResult.data.items : [])
      setWorkspaceTasksStatus('success')
      setWorkspaceArtifactsStatus('success')
      setWorkspaceTasksError('')
      setWorkspaceArtifactsError('')
    } catch (error) {
      if (requestId !== workspaceRequestIdRef.current) return
      setWorkspaceTasksStatus('error')
      setWorkspaceArtifactsStatus('error')
      const message = error?.detail?.message ?? error?.message ?? 'Workspace 记录读取失败。'
      setWorkspaceTasksError(message)
      setWorkspaceArtifactsError(message)
    }
  }

  async function loadWorkspaceInstructions(workspaceId) {
    const trimmedUserId = userId.trim()
    if (!trimmedUserId || !workspaceId) return
    try {
      const { data } = await getWorkspaceAgentInstructions(workspaceId, trimmedUserId)
      setWorkspaceInstructions({ content: data?.content ?? '', version: data?.version ?? 0 })
    } catch { setWorkspaceInstructions({ content: '', version: 0 }) }
  }

  async function saveWorkspaceInstructions(content) {
    const { data } = await saveWorkspaceAgentInstructions(selectedWorkspaceId, { user_id: userId.trim(), content })
    setWorkspaceInstructions({ content: data?.content ?? '', version: data?.version ?? 0 })
  }

  async function clearWorkspaceInstructions() {
    const { data } = await clearWorkspaceAgentInstructions(selectedWorkspaceId, userId.trim())
    setWorkspaceInstructions({ content: data?.content ?? '', version: data?.version ?? 0 })
  }

  async function selectWorkspace(workspaceId) {
    workspaceRequestIdRef.current += 1
    setSelectedWorkspaceId(workspaceId)
    void loadWorkspaceInstructions(workspaceId)
    setSelectedArtifact(null)
    setArtifactContent('')
    setWorkspaceAssets([])
    setWorkspaceAssetsStatus('loading')
    setWorkspaceTasks([])
    setWorkspaceArtifacts([])
    void loadWorkspaceAssets({ workspaceId })
    void loadWorkspaceData(workspaceId)
  }

  async function handleCreateWorkspace({ name, description }) {
    try {
      const { data } = await createWorkspace({ user_id: userId.trim(), name, description })
      setWorkspaces((current) => [data, ...current])
      setWorkspaceFeatureStatus('available')
      await selectWorkspace(data.id)
    } catch {
      setWorkspaceFeatureStatus('error')
    }
  }

  async function handleWorkspaceLifecycle(workspaceId, action) {
    if (!userId.trim()) return
    try {
      const request = action === 'archive' ? archiveWorkspace : restoreWorkspace
      const { data } = await request(workspaceId, userId.trim())
      setWorkspaces((current) => current.map((item) => item.id === data.id ? data : item))
    } catch {
      setWorkspaceFeatureStatus('error')
    }
  }

  async function handleUploadWorkspaceAsset(file) {
    const workspace = workspaces.find((item) => item.id === selectedWorkspaceId)
    if (!workspace || workspace.status === 'ARCHIVED') return
    try {
      const { data } = await uploadWorkspaceAsset(selectedWorkspaceId, userId.trim(), file)
      const nextAsset = data?.asset ?? data
      setWorkspaceAssets((current) => [nextAsset, ...current.filter((item) => item.id !== nextAsset.id)])
      setWorkspaceAssetsStatus('success')
      void loadWorkspaceAssets({ workspaceId: selectedWorkspaceId })
    } catch (error) {
      setWorkspaceAssetsError(error?.detail?.message ?? error?.message ?? 'Workspace Asset 上传失败。')
      setWorkspaceAssetsStatus('error')
    }
  }

  async function handleWorkspaceAssetAction(asset, action) {
    if (!selectedWorkspaceId || !userId.trim()) return
    setWorkspaceAssetActionStates((current) => ({ ...current, [asset.id]: action }))
    try {
      if (action === 'download') {
        window.open(getWorkspaceAssetDownloadUrl(selectedWorkspaceId, asset.id, userId.trim()), '_blank', 'noopener,noreferrer')
      } else {
        const request = action === 'retry' ? retryWorkspaceAsset : deleteWorkspaceAsset
        const { data } = await request(selectedWorkspaceId, asset.id, userId.trim())
        if (action === 'delete') setWorkspaceAssets((current) => current.filter((item) => item.id !== asset.id))
        else setWorkspaceAssets((current) => current.map((item) => item.id === asset.id ? data : item))
      }
    } catch (error) {
      setWorkspaceAssetsError(error?.detail?.message ?? error?.message ?? `Asset ${action} 失败。`)
    } finally {
      setWorkspaceAssetActionStates((current) => ({ ...current, [asset.id]: '' }))
    }
  }

  async function handleSelectArtifact(artifact) {
    if (!selectedWorkspaceId || !userId.trim()) return
    setSelectedArtifact(artifact)
    setArtifactContentLoading(true)
    try {
      const { data } = await getWorkspaceArtifactContent(selectedWorkspaceId, artifact.id, userId.trim())
      setArtifactContent(typeof data === 'string' ? data : '')
    } catch {
      setArtifactContent('无法读取 Artifact 内容。')
    } finally {
      setArtifactContentLoading(false)
    }
  }

  function handleDownloadArtifact(artifact) {
    if (!selectedWorkspaceId) return
    window.open(getWorkspaceArtifactDownloadUrl(selectedWorkspaceId, artifact.id, userId.trim()), '_blank', 'noopener,noreferrer')
  }

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
      return nextJDs
    } catch {
      setInterviewJDs([])
      setInterviewJDsStatus('error')
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
      return data
    } catch {
      setInterviewJDsStatus('error')
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
    workspaceRequestIdRef.current += 1
      if (session.workspace_id) {
        setSelectedWorkspaceId(session.workspace_id)
        void loadWorkspaceInstructions(session.workspace_id)
      setWorkspaceAssets([])
      setWorkspaceTasks([])
      setWorkspaceArtifacts([])
      void loadWorkspaceAssets({ workspaceId: session.workspace_id })
      void loadWorkspaceData(session.workspace_id)
    } else {
      setSelectedWorkspaceId(null)
      setWorkspaceAssets([])
      setWorkspaceTasks([])
      setWorkspaceArtifacts([])
    }

    try {
      const { data } = await getSessionConversations(session.id)
      if (requestId !== sessionMessageRequestIdRef.current) return
      const items = Array.isArray(data?.items) ? data.items : []
      setMessages(buildMessagesFromHistoryItems(items))
      setActiveSessionStatus('success')
    } catch (error) {
      if (requestId !== sessionMessageRequestIdRef.current || error?.isAbortError) return
      setMessages([])
      setActiveSessionStatus('error')
    }
  }

  async function handleCreateSession(workspaceIdInput = null) {
    const workspaceId = typeof workspaceIdInput === 'string' && workspaceIdInput.trim()
      ? workspaceIdInput
      : null
    const trimmedUserId = userId.trim()
    if (!trimmedUserId || isCreatingSession) return null

    const requestId = sessionCreateRequestIdRef.current + 1
    sessionCreateRequestIdRef.current = requestId
    setIsCreatingSession(true)
    setSessionCreateError('')

    try {
      const { data } = await createSession({
        user_id: trimmedUserId,
        persona_id: selectedPersonaId,
        ...(workspaceId ? { workspace_id: workspaceId } : {}),
      })
      if (requestId !== sessionCreateRequestIdRef.current) return null

      upsertSession(data)
      setSessionsStatus('success')
      setSessionCreateError('')
      activateAttachmentScope(data.id, trimmedUserId, selectedPersonaId, {
        preserveSessionCreation: true,
      })
      setActiveSessionId(data.id)
      setActiveSessionStatus('success')
      setMessages([])
      setSelectedWorkspaceId(data.workspace_id ?? null)
      if (data.workspace_id) {
        void loadWorkspaceInstructions(data.workspace_id)
        workspaceRequestIdRef.current += 1
        setWorkspaceAssets([])
        setWorkspaceTasks([])
        setWorkspaceArtifacts([])
        void loadWorkspaceAssets({ workspaceId: data.workspace_id })
        void loadWorkspaceData(data.workspace_id)
      }
      return data
    } catch (error) {
      if (requestId !== sessionCreateRequestIdRef.current || error?.isAbortError) return null
      console.error('createSession failed', error)
      setSessionsStatus('error')
      setSessionCreateError(
        error?.status
          ? `创建会话失败（HTTP ${error.status}）：${error?.detail?.error ?? error.message}`
          : `创建会话失败：${error.message}`,
      )
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
      return listedItems
    } catch (error) {
      if (
        error?.isAbortError
        || scopeKey !== attachmentScopeKeyRef.current
        || requestId !== attachmentListRequestIdRef.current
      ) return []
      setAttachmentStatus('error')
      setAttachmentError(attachmentErrorMessage(error, '附件列表读取失败，请稍后重试。'))
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
  const hasPendingWorkspaceAssets = workspaceAssets.some((asset) => ['STAGING', 'PROCESSING'].includes(asset.status))
  useAttachmentPolling({
    enabled: Boolean(selectedWorkspaceId && hasPendingWorkspaceAssets),
    poll: loadWorkspaceAssets,
    intervalMs: 1800,
    scopeKey: selectedWorkspaceId ?? '',
  })

  async function handleUploadAttachment(file) {
    if (isUploadingAttachment) return
    const validationMessage = validateAttachmentFile(file)
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
    } catch (error) {
      if (error?.isAbortError || operationScopeKey !== attachmentScopeKeyRef.current) return
      setAttachmentError(attachmentErrorMessage(error, '附件上传失败，请稍后重试。'))
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
    } catch (error) {
      if (scopeKey !== attachmentScopeKeyRef.current || error?.isAbortError) return
      setAttachmentActionErrors((current) => ({
        ...current,
        [attachmentId]: attachmentErrorMessage(error, '附件重试失败，请稍后再试。'),
      }))
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
    } catch (error) {
      if (scopeKey !== attachmentScopeKeyRef.current || error?.isAbortError) return
      setAttachmentActionErrors((current) => ({
        ...current,
        [attachmentId]: attachmentErrorMessage(error, '附件删除失败，请稍后再试。'),
      }))
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
    if (!trimmedMessage) return
    if (!trimmedUserId) {
      setComposerNotice('用户 ID 为空，请先填写。')
      return
    }
    if (isSending) {
      setComposerNotice('正在生成中，请等待当前回复完成。')
      return
    }
    if (activeSessionStatus === 'loading') {
      setComposerNotice('正在加载历史消息，请稍候。')
      return
    }
    setComposerNotice('')
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
    if (ragModeForRequest === 'documents') {
      baseRequestBody.web_search_enabled = false
      baseRequestBody.force_web_search = false
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

    let accumulatedText = ''
    let accumulatedThinking = ''

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
      if (ragModeForRequest === 'force' || ragModeForRequest === 'documents') setRagMode('auto')
      if (webSearchModeForRequest === 'force') setWebSearchMode('auto')

      if (streamingEnabled) {
        // Streaming mode
        const messageId = `message-assistant-${Date.now()}`
        const requestStartedAt = monotonicNow()
        let firstTokenLatencyMs = null
        let finalData = null

        // 流开始时就创建 assistant 流式消息区域：
        // 即使工具调用先于第一个 token 到达，也能立即显示工具状态。
        setStreamingMessage({
          id: messageId,
          role: 'assistant',
          text: '',
          thinking: '',
          metrics: null,
          isStreaming: true,
        })

        await postChatStream(
          chatRequestBody,
          {
            onThinking: (text) => {
              accumulatedThinking += text
              setStreamingMessage({
                id: messageId,
                role: 'assistant',
                text: accumulatedText,
                thinking: accumulatedThinking,
                metrics: {
                  firstTokenLatencyMs,
                  completionElapsedMs: Math.round(monotonicNow() - requestStartedAt),
                  tokenCount: null,
                },
                isStreaming: true,
              })
            },
            onToken: (text) => {
              // token 按到达顺序持续追加；工具调用只更新工具状态，不清空正文。
              if (firstTokenLatencyMs === null) {
                firstTokenLatencyMs = Math.round(monotonicNow() - requestStartedAt)
              }
              accumulatedText += text
              setStreamingMessage({
                id: messageId,
                role: 'assistant',
                text: accumulatedText,
                thinking: accumulatedThinking,
                metrics: {
                  firstTokenLatencyMs,
                  completionElapsedMs: Math.round(monotonicNow() - requestStartedAt),
                  tokenCount: null,
                },
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
        const usage = finalData?.usage ?? {}
        const tokenCount = Number.isFinite(usage.total_tokens)
          ? usage.total_tokens
          : Number.isFinite(usage.completion_tokens)
            ? usage.completion_tokens
            : null
        const responseMetrics = {
          firstTokenLatencyMs,
          completionElapsedMs: Math.round(monotonicNow() - requestStartedAt),
          tokenCount,
        }
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
              thinking: accumulatedThinking,
              metrics: responseMetrics,
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
        void loadSessions({ silent: true })
        if (activeSession.workspace_id) void loadWorkspaceData(activeSession.workspace_id)
      } else {
        // Non-streaming mode (fallback)
        const requestStartedAt = monotonicNow()
        const { data, debug } = await postChat(chatRequestBody)
        if (chatScopeKey !== attachmentScopeKeyRef.current) return

        const assistantMessage = {
          id: `message-assistant-${Date.now()}`,
          role: 'assistant',
          reply: data?.reply,
          metrics: {
            firstTokenLatencyMs: null,
            completionElapsedMs: Math.round(monotonicNow() - requestStartedAt),
            tokenCount: Number.isFinite(data?.usage?.total_tokens)
              ? data.usage.total_tokens
              : Number.isFinite(data?.usage?.completion_tokens)
                ? data.usage.completion_tokens
                : null,
          },
          debug,
        }
        setMessages((currentMessages) => [...currentMessages, assistantMessage])
        setActiveSessionId(data?.session_id ?? activeSession.id)
        setActiveSessionStatus('success')
        void loadSessions({ silent: true })
        if (activeSession.workspace_id) void loadWorkspaceData(activeSession.workspace_id)
      }
    } catch (error) {
      if (chatScopeKey !== attachmentScopeKeyRef.current || error?.isAbortError) return

      const errorMessage = {
        id: `message-error-${Date.now()}`,
        role: 'assistant',
        reply: createErrorReply(error),
        debug: {
          url: `${API_BASE_URL}/${streamingEnabled ? 'chat/stream' : 'chat'}`,
          method: 'POST',
          requestBody: baseRequestBody,
          ...error.debug,
          status: error.status ?? error.debug?.status ?? null,
          error: error.message,
          detail: error.detail,
          responseBody:
            error.responseBody
            ?? error.debug?.responseBody
            ?? null,
        },
      }
      const partialMessage = streamingEnabled && accumulatedText
        ? {
            id: `message-partial-${Date.now()}`,
            role: 'assistant',
            reply: { answer: accumulatedText, sources: [] },
          }
        : null
      setMessages((currentMessages) => [
        ...currentMessages,
        ...(partialMessage ? [partialMessage] : []),
        errorMessage,
      ])
      setStreamingMessage(null)
      setStreamingTool(null)
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
    void loadWorkspaces()
    void loadInterviewJDs()
  }, [checkApiHealth, loadPersonas, loadModels, loadSessions, loadWorkspaces, loadInterviewJDs])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.classList.toggle('dark', theme === 'dark')
    document.documentElement.style.colorScheme = theme
    localStorage.setItem('tutor-theme', theme)
  }, [theme])

  useEffect(() => {
    localStorage.setItem('tutor-sidebar-collapsed', String(isSidebarCollapsed))
  }, [isSidebarCollapsed])

  useEffect(() => {
    function handleEscape(event) {
      if (event.key === 'Escape') setIsMobileSidebarOpen(false)
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [])

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

  const quickPrompts = [
    { title: '制定学习计划', text: '根据我的目标，为我制定一份循序渐进的学习计划。', icon: 'target' },
    { title: '拆解一个概念', text: '请用清晰、可记忆的方式解释一个我正在学习的概念。', icon: 'sparkles' },
    { title: '模拟面试练习', text: '请围绕我的目标岗位，开始一轮循序渐进的模拟面试。', icon: 'message' },
  ]

  const attachmentProps = {
    attachments,
    selectedAttachmentIds,
    status: attachmentStatus,
    error: attachmentError,
    actionErrors: attachmentActionErrors,
    actionStates: attachmentActionStates,
    sendBlockReason: attachmentSendBlockReason,
    disabled: isSending || isUploadingAttachment || !userId.trim(),
    onUpload: handleUploadAttachment,
    onToggle: handleToggleAttachment,
    onRetry: handleRetryAttachment,
    onDelete: handleDeleteAttachment,
  }

  return (
    <main className={`app-shell${isSidebarCollapsed ? ' sidebar-collapsed' : ''}`}>
      <header className="app-header">
        <div className="header-leading">
          <button className="icon-button menu-button" type="button" onClick={() => setIsMobileSidebarOpen(true)} aria-label="打开会话侧栏" title="打开会话侧栏"><Icon name="menu" size={19} /></button>
          {isSidebarCollapsed ? <button className="icon-button sidebar-expand-button" type="button" onClick={() => setIsSidebarCollapsed(false)} aria-label="展开会话侧栏" title="展开会话侧栏"><Icon name="panel" size={18} /></button> : null}
          <span className="active-session-title">{activeSession?.title || '未命名会话'}</span>
        </div>
        <div className="header-center">
          <ApiStatus status={apiStatus} onRefresh={checkApiHealth} />
        </div>
        <div className="header-controls">
          <ModelSelector models={models} selectedModelId={selectedModelId} status={modelsStatus} onModelChange={handleModelChange} />
          <PersonaSelector
            personas={personas}
            selectedPersonaId={selectedPersonaId}
            status={personasStatus}
            onPersonaChange={(nextPersonaId) => {
              if (nextPersonaId === '__manage_custom__') {
                setPersonaManagerOpen(true)
                return
              }
              handlePersonaChange(nextPersonaId)
            }}
          />
          <button className="persona-manager-trigger" type="button" onClick={() => setPersonaManagerOpen(true)} aria-label="管理 Persona" title="管理 Persona"><Icon name="user" size={16} /></button>
          <button className="header-action-button" type="button" onClick={() => setIsTargetPanelOpen(true)}>
            <Icon name="target" size={17} /><span>学习目标</span>
          </button>
          <button className="header-action-button" type="button" onClick={() => setKnowledgeLibraryOpen(true)}>
            <Icon name="file" size={17} /><span>文档库</span>
          </button>
          <button className="theme-button" type="button" onClick={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')} aria-label="切换明暗主题">
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={18} />
          </button>
        </div>
      </header>

      <div className="workspace-layout">
        {isMobileSidebarOpen ? <button className="drawer-scrim sidebar-scrim" type="button" aria-label="关闭会话侧栏" onClick={() => setIsMobileSidebarOpen(false)} /> : null}
        <SessionSidebar
          userId={userId}
          sessions={sessions}
          personas={personas}
          workspaces={workspaces}
          selectedWorkspaceId={selectedWorkspaceId}
          activeSessionId={activeSessionId}
          status={sessionsStatus}
          sessionCreateError={sessionCreateError}
          isCreating={isCreatingSession}
          isSidebarCollapsed={isSidebarCollapsed}
          isMobileOpen={isMobileSidebarOpen}
          onToggleCollapsed={() => setIsSidebarCollapsed((value) => !value)}
          onCreateSession={handleCreateSession}
          onRefreshSessions={loadSessions}
          onSelectSession={loadSessionMessages}
          onSelectWorkspace={selectWorkspace}
          onCreateWorkspace={() => setWorkspacePanelOpen(true)}
          onArchiveWorkspace={(workspaceId) => handleWorkspaceLifecycle(workspaceId, 'archive')}
          onRestoreWorkspace={(workspaceId) => handleWorkspaceLifecycle(workspaceId, 'restore')}
          onOpenWorkspaceDetail={(workspaceId) => { void selectWorkspace(workspaceId); setWorkspacePanelOpen(true) }}
          onUserIdChange={handleUserIdChange}
        />

        <section className="chat-surface" aria-label="聊天工作区">
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
              <ChatMessage key={message.id} role={message.role} text={message.text} reply={message.reply} thinking={message.thinking} metrics={message.metrics} debug={message.debug} />
            ))}
            {isSending && streamingMessage ? (
              <ChatMessage
                key={streamingMessage.id}
                role="assistant"
                text={streamingMessage.text}
                thinking={streamingMessage.thinking}
                metrics={streamingMessage.metrics}
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
            attachmentProps={attachmentProps}
            notice={composerNotice}
          />
        </section>
      </div>

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
      {personaManagerOpen ? <PersonaManager userId={userId.trim()} personas={personas} onCreate={handleCreatePersona} onUpdate={handleUpdatePersona} onDisable={handleDisablePersona} onClose={() => setPersonaManagerOpen(false)} /> : null}
      {knowledgeLibraryOpen ? <KnowledgeLibrary userId={userId} onClose={() => setKnowledgeLibraryOpen(false)} /> : null}
      <WorkspacePanel
        open={workspacePanelOpen}
        featureStatus={workspaceFeatureStatus}
        userId={userId}
        workspaces={workspaces}
        selectedWorkspaceId={selectedWorkspaceId}
        selectedWorkspace={workspaces.find((workspace) => workspace.id === selectedWorkspaceId)}
        workspaceInstructions={workspaceInstructions}
        onSaveInstructions={saveWorkspaceInstructions}
        onClearInstructions={clearWorkspaceInstructions}
        assets={workspaceAssets}
        assetsStatus={workspaceAssetsStatus}
        assetsError={workspaceAssetsError}
        assetActionStates={workspaceAssetActionStates}
        tasks={workspaceTasks}
        tasksStatus={workspaceTasksStatus}
        tasksError={workspaceTasksError}
        artifacts={workspaceArtifacts}
        artifactsStatus={workspaceArtifactsStatus}
        artifactsError={workspaceArtifactsError}
        selectedArtifact={selectedArtifact}
        artifactContent={artifactContent}
        artifactContentLoading={artifactContentLoading}
        onClose={() => setWorkspacePanelOpen(false)}
        onSelectWorkspace={selectWorkspace}
        onCreateWorkspace={handleCreateWorkspace}
        onArchiveWorkspace={(workspaceId) => handleWorkspaceLifecycle(workspaceId, 'archive')}
        onRestoreWorkspace={(workspaceId) => handleWorkspaceLifecycle(workspaceId, 'restore')}
        onCreateSession={(workspaceId) => { setWorkspacePanelOpen(false); void handleCreateSession(workspaceId) }}
        onUploadAsset={handleUploadWorkspaceAsset}
        onRetryAsset={(asset) => handleWorkspaceAssetAction(asset, 'retry')}
        onDeleteAsset={(asset) => handleWorkspaceAssetAction(asset, 'delete')}
        onDownloadAsset={(asset) => handleWorkspaceAssetAction(asset, 'download')}
        onSelectArtifact={handleSelectArtifact}
        onCloseArtifact={() => { setSelectedArtifact(null); setArtifactContent('') }}
        onDownloadArtifact={handleDownloadArtifact}
      />
    </main>
  )
}

export default App

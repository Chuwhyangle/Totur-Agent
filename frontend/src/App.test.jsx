import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  API_BASE_URL: 'http://127.0.0.1:8001',
  createInterviewJD: vi.fn(),
  createSession: vi.fn(),
  deleteAttachment: vi.fn(),
  getAttachments: vi.fn(),
  getHealth: vi.fn(),
  getInterviewJDs: vi.fn(),
  getPersonas: vi.fn(),
  getSessionConversations: vi.fn(),
  getSessions: vi.fn(),
  getWorkspaces: vi.fn(),
  getWorkspaceAssets: vi.fn(),
  getWorkspaceTasks: vi.fn(),
  getWorkspaceArtifacts: vi.fn(),
  postChat: vi.fn(),
  postChatStream: vi.fn(),
  retryAttachment: vi.fn(),
  uploadAttachment: vi.fn(),
}))

vi.mock('./api/tutorApi.js', () => api)

import App from './App.jsx'

const sessions = [
  {
    id: 'session-1',
    title: 'Session One',
    persona_id: 'tutor',
    updated_at: '2026-07-26T00:00:00Z',
  },
  {
    id: 'session-2',
    title: 'Session Two',
    persona_id: 'tutor',
    updated_at: '2026-07-26T00:00:00Z',
  },
]

const readyAttachment = (id, filename) => ({
  id,
  original_filename: filename,
  mime_type: 'application/pdf',
  size_bytes: 2048,
  status: 'READY',
  created_at: '2026-07-26T00:00:00Z',
  expires_at: '2026-07-27T00:00:00Z',
  error_code: null,
  user_safe_message: null,
})

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function mockAppBootstrap() {
  api.getHealth.mockResolvedValue({ status: 'ok' })
  api.getPersonas.mockResolvedValue({
    data: [
      { persona_id: 'tutor', name: 'Tutor' },
      { persona_id: 'reviewer', name: 'Reviewer' },
    ],
  })
  api.getSessions.mockResolvedValue({ data: { items: sessions } })
  api.getWorkspaces.mockResolvedValue({ data: { items: [] } })
  api.getInterviewJDs.mockResolvedValue({ data: { items: [] } })
  api.getSessionConversations.mockResolvedValue({ data: { items: [] } })
  api.createSession.mockResolvedValue({ data: sessions[0] })
  api.postChat.mockResolvedValue({
    data: {
      session_id: 'session-1',
      reply: {
        answer: 'done',
        sources: [],
      },
    },
    debug: {},
  })
}

async function openSession(user, title = 'Session One') {
  await user.click(await screen.findByText(title))
}

describe('App attachment scope and sending', () => {
  beforeEach(() => {
    Object.values(api).forEach((mock) => typeof mock === 'function' && mock.mockReset())
    localStorage.clear()
    localStorage.setItem('tutor-streaming', 'false')
    mockAppBootstrap()
  })

  it('does not let an old session attachment response overwrite the current session', async () => {
    const user = userEvent.setup()
    const firstList = deferred()
    api.getAttachments.mockImplementation((sessionId) => {
      if (sessionId === 'session-1') return firstList.promise
      return Promise.resolve({ data: { items: [readyAttachment('second', 'second.pdf')] } })
    })

    render(<App />)
    await openSession(user, 'Session One')
    await waitFor(() => expect(api.getAttachments).toHaveBeenCalledWith(
      'session-1',
      'demo-user',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))

    await openSession(user, 'Session Two')
    expect(await screen.findByText('second.pdf')).not.toBeNull()

    await act(async () => {
      firstList.resolve({ data: { items: [readyAttachment('first', 'first.pdf')] } })
      await firstList.promise
    })

    expect(screen.queryByText('first.pdf')).toBeNull()
    expect(screen.getByText('second.pdf')).not.toBeNull()
  })

  it('keeps the first message when session history finishes after sending', async () => {
    const user = userEvent.setup()
    const history = deferred()
    api.getSessionConversations.mockReturnValue(history.promise)
    api.getAttachments.mockResolvedValue({ data: { items: [] } })

    render(<App />)
    await openSession(user)
    await user.type(
      screen.getByPlaceholderText('写下你的问题，或让导师帮你拆解下一步…'),
      'first question',
    )
    expect(screen.getByRole('button', { name: '发送消息' }).disabled).toBe(true)

    await act(async () => {
      history.resolve({ data: { items: [] } })
      await history.promise
    })

    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.postChat).toHaveBeenCalledTimes(1))

    expect(screen.getByText('first question')).not.toBeNull()
  })

  it('clears attachment state and ignores stale responses after persona changes', async () => {
    const user = userEvent.setup()
    const attachmentList = deferred()
    api.getAttachments.mockReturnValue(attachmentList.promise)

    render(<App />)
    await openSession(user)
    await waitFor(() => expect(api.getAttachments).toHaveBeenCalledTimes(1))

    await user.selectOptions(screen.getByLabelText('人设'), 'reviewer')
    await act(async () => {
      attachmentList.resolve({ data: { items: [readyAttachment('old', 'old-persona.pdf')] } })
      await attachmentList.promise
    })

    expect(screen.queryByText('old-persona.pdf')).toBeNull()
  })

  it('clears attachment state and ignores stale responses after user changes', async () => {
    const user = userEvent.setup()
    const attachmentList = deferred()
    api.getAttachments.mockReturnValue(attachmentList.promise)

    render(<App />)
    await openSession(user)
    await waitFor(() => expect(api.getAttachments).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getAllByLabelText('user_id')[0], {
      target: { value: 'another-user' },
    })
    await act(async () => {
      attachmentList.resolve({ data: { items: [readyAttachment('old-user', 'old-user.pdf')] } })
      await attachmentList.promise
    })

    expect(screen.queryByText('old-user.pdf')).toBeNull()
  })

  it('auto-selects ready attachments and sends their ids in chat', async () => {
    const user = userEvent.setup()
    api.getAttachments.mockResolvedValue({
      data: { items: [readyAttachment('attachment-1', 'resume.pdf')] },
    })

    render(<App />)
    await openSession(user)
    expect(await screen.findByText('resume.pdf')).not.toBeNull()
    expect(screen.getByRole('checkbox', { name: '选择附件 resume.pdf' }).checked).toBe(true)

    await user.type(
      screen.getByPlaceholderText('写下你的问题，或让导师帮你拆解下一步…'),
      '总结附件',
    )
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.postChat).toHaveBeenCalledTimes(1))
    expect(api.postChat.mock.calls[0][0]).toMatchObject({
      user_id: 'demo-user',
      session_id: 'session-1',
      persona_id: 'tutor',
      message: '总结附件',
      force_web_search: false,
      attachment_ids: ['attachment-1'],
    })
  })

  it('refreshes a missing attachment index and blocks another send', async () => {
    const user = userEvent.setup()
    const attachment = readyAttachment('attachment-1', 'resume.pdf')
    api.getAttachments
      .mockResolvedValueOnce({ data: { items: [attachment] } })
      .mockResolvedValueOnce({
        data: {
          items: [{
            ...attachment,
            status: 'FAILED',
            error_code: 'ATTACHMENT_INDEX_MISSING',
            user_safe_message: '附件索引缺失，请重试处理。',
          }],
        },
      })
    api.postChat.mockRejectedValue({
      status: 409,
      detail: { error: 'attachment_index_missing' },
      isNetworkError: false,
      message: 'attachment index missing',
    })

    render(<App />)
    await openSession(user)
    expect(await screen.findByText('resume.pdf')).not.toBeNull()

    const input = screen.getByPlaceholderText('写下你的问题，或让导师帮你拆解下一步…')
    await user.type(input, '总结附件')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.getAttachments).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('处理失败')).not.toBeNull()
    expect(screen.getByText('附件索引缺失，请重试处理。')).not.toBeNull()
    expect(screen.getByRole('button', { name: '重试附件 resume.pdf' })).not.toBeNull()
    expect(screen.getByRole('status').textContent).toContain('所选附件处理失败')

    await user.type(input, '再次发送')
    expect(screen.getByRole('button', { name: '发送消息' }).disabled).toBe(true)
    await user.click(screen.getByRole('button', { name: '发送消息' }))
    expect(api.postChat).toHaveBeenCalledTimes(1)
  })

  it('keeps send disabled when a selected attachment is still pending', async () => {
    const user = userEvent.setup()
    api.getAttachments.mockResolvedValue({
      data: {
        items: [{
          ...readyAttachment('attachment-1', 'processing.pdf'),
          status: 'PARSING',
        }],
      },
    })

    render(<App />)
    await openSession(user)
    const checkbox = await screen.findByRole('checkbox', { name: '选择附件 processing.pdf' })
    await user.click(checkbox)
    await user.type(
      screen.getByPlaceholderText('写下你的问题，或让导师帮你拆解下一步…'),
      '现在发送',
    )

    expect(screen.getByRole('button', { name: '发送消息' }).disabled).toBe(true)
    expect(screen.getByRole('status').textContent).toContain('附件仍在处理中')
    expect(api.postChat).not.toHaveBeenCalled()
  })
})



describe('App RAG three-state control', () => {
  beforeEach(() => {
    Object.values(api).forEach((mock) => typeof mock === 'function' && mock.mockReset())
    localStorage.clear()
    localStorage.setItem('tutor-streaming', 'false')
    mockAppBootstrap()
  })

  const ragButton = () => screen.getByRole('button', { name: /RAG 检索/ })
  const webSearchButton = () => screen.getByRole('button', { name: /联网搜索/ })
  const input = () => screen.getByPlaceholderText('写下你的问题，或让导师帮你拆解下一步…')

  it('defaults to auto mode', async () => {
    render(<App />)
    expect(ragButton().getAttribute('aria-label')).toBe('RAG 检索：自动判断')
    expect(webSearchButton().getAttribute('aria-label')).toBe('联网搜索：自动判断')
  })

  it('cycles auto -> force -> off -> auto', async () => {
    const user = userEvent.setup()
    render(<App />)
    const button = ragButton()

    await user.click(button)
    expect(button.getAttribute('aria-label')).toBe('RAG 检索：本轮强制使用')
    await user.click(button)
    expect(button.getAttribute('aria-label')).toBe('RAG 检索：强制关闭')
    await user.click(button)
    expect(button.getAttribute('aria-label')).toBe('RAG 检索：自动判断')
  })

  it('cycles the web search button through the same three states', async () => {
    const user = userEvent.setup()
    render(<App />)
    const button = webSearchButton()

    await user.click(button)
    expect(button.getAttribute('aria-label')).toBe('联网搜索：本轮强制使用')
    await user.click(button)
    expect(button.getAttribute('aria-label')).toBe('联网搜索：强制关闭')
    await user.click(button)
    expect(button.getAttribute('aria-label')).toBe('联网搜索：自动判断')
  })

  it('sends force mode fields in a non-streaming request', async () => {
    const user = userEvent.setup()
    render(<App />)
    await openSession(user)
    await user.click(ragButton())
    await user.type(input(), 'FastAPI 依赖注入')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.postChat).toHaveBeenCalledTimes(1))
    expect(api.postChat.mock.calls[0][0]).toMatchObject({
      rag_enabled: true,
      force_rag: true,
      web_search_enabled: true,
      force_web_search: false,
    })
  })

  it('sends web search force mode fields in a non-streaming request', async () => {
    const user = userEvent.setup()
    render(<App />)
    await openSession(user)
    await user.click(webSearchButton())
    await user.type(input(), 'FastAPI 最新版本')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.postChat).toHaveBeenCalledTimes(1))
    expect(api.postChat.mock.calls[0][0]).toMatchObject({
      web_search_enabled: true,
      force_web_search: true,
    })
  })

  it('sends web search off mode fields in a non-streaming request', async () => {
    const user = userEvent.setup()
    render(<App />)
    await openSession(user)
    const button = webSearchButton()
    await user.click(button)
    await user.click(button)
    await user.type(input(), 'plain question')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.postChat).toHaveBeenCalledTimes(1))
    expect(api.postChat.mock.calls[0][0]).toMatchObject({
      web_search_enabled: false,
      force_web_search: false,
    })
  })

  it('sends off mode fields in a non-streaming request', async () => {
    const user = userEvent.setup()
    render(<App />)
    await openSession(user)
    const button = ragButton()
    await user.click(button)
    await user.click(button)
    await user.type(input(), 'plain question')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.postChat).toHaveBeenCalledTimes(1))
    expect(api.postChat.mock.calls[0][0]).toMatchObject({
      rag_enabled: false,
      force_rag: false,
    })
  })

  it('sends auto mode fields in a non-streaming request by default', async () => {
    const user = userEvent.setup()
    render(<App />)
    await openSession(user)
    await user.type(input(), 'auto question')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.postChat).toHaveBeenCalledTimes(1))
    expect(api.postChat.mock.calls[0][0]).toMatchObject({
      rag_enabled: true,
      force_rag: false,
    })
  })

  it('sends the same rag fields in a streaming request', async () => {
    const user = userEvent.setup()
    localStorage.setItem('tutor-streaming', 'true')
    api.postChatStream.mockImplementation(async (_request, callbacks) => {
      callbacks.onDone({ session_id: 'session-1' })
    })
    render(<App />)
    await openSession(user)
    await user.click(ragButton())
    await user.type(input(), 'stream force question')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.postChatStream).toHaveBeenCalledTimes(1))
    expect(api.postChatStream.mock.calls[0][0]).toMatchObject({
      rag_enabled: true,
      force_rag: true,
    })
  })

  it('resets force mode back to auto after the request is dispatched', async () => {
    const user = userEvent.setup()
    render(<App />)
    await openSession(user)
    await user.click(ragButton())
    await user.click(webSearchButton())
    await user.type(input(), 'one shot')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.postChat).toHaveBeenCalledTimes(1))
    expect(ragButton().getAttribute('aria-label')).toBe('RAG 检索：自动判断')
    expect(webSearchButton().getAttribute('aria-label')).toBe('联网搜索：自动判断')
  })

  it('keeps force mode when the request is not dispatched', async () => {
    const user = userEvent.setup()
    api.getSessions.mockResolvedValue({ data: { items: [] } })
    api.createSession.mockRejectedValue(new Error('create session failed'))
    render(<App />)
    await user.click(ragButton())
    await user.type(input(), 'will not send')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.createSession).toHaveBeenCalled())
    expect(api.postChat).not.toHaveBeenCalled()
    expect(ragButton().getAttribute('aria-label')).toBe('RAG 检索：本轮强制使用')
  })

  it('disables the rag button while sending', async () => {
    const user = userEvent.setup()
    const pending = deferred()
    api.postChat.mockReturnValue(pending.promise)
    render(<App />)
    await openSession(user)
    await user.type(input(), 'slow question')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.postChat).toHaveBeenCalled())
    expect(ragButton().disabled).toBe(true)
    pending.resolve({ data: { session_id: 'session-1', reply: { answer: 'ok' } } })
  })
})


describe('App SSE sending', () => {
  beforeEach(() => {
    Object.values(api).forEach((mock) => typeof mock === 'function' && mock.mockReset())
    localStorage.clear()
    localStorage.setItem('tutor-streaming', 'true')
    mockAppBootstrap()
  })

  it('uses done.reply as the final source of truth and clears sending state on done', async () => {
    const user = userEvent.setup()
    api.getAttachments.mockResolvedValue({ data: { items: [] } })
    api.postChatStream.mockImplementation(async (_request, callbacks) => {
      callbacks.onToken('Hello ')
      callbacks.onToken('world')
      callbacks.onDone({
        session_id: 'session-1',
        reply: {
          answer: '最终回复',
          sources: [],
        },
      })
    })

    render(<App />)
    await openSession(user)
    await user.type(screen.getByPlaceholderText('写下你的问题，或让导师帮你拆解下一步…'), 'stream this')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    expect(await screen.findByText('最终回复')).not.toBeNull()
    expect(screen.queryByText('Hello world')).toBeNull()
    expect(api.postChatStream).toHaveBeenCalledTimes(1)
    expect(api.postChat).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.getByRole('button', { name: '流式' }).disabled).toBe(false))
  })

  it('shows the tool status even when a tool call arrives before the first token', async () => {
    const user = userEvent.setup()
    const streamGate = deferred()
    api.getAttachments.mockResolvedValue({ data: { items: [] } })
    api.postChatStream.mockImplementation(async (_request, callbacks) => {
      callbacks.onToolCall('web_search', { query: 'FastAPI' })
      await streamGate.promise
      callbacks.onToolResult('web_search', { ok: true })
      callbacks.onToken('最终正文')
      callbacks.onDone({
        session_id: 'session-1',
        reply: { answer: '最终正文', sources: [] },
      })
    })

    render(<App />)
    await openSession(user)
    await user.type(document.querySelector('.chat-input'), 'search this')
    await user.click(document.querySelector('.send-button'))

    // 首个 token 未到时，工具状态已可见（不再只有加载动画）
    expect(await screen.findByText(/正在调用 web_search/)).not.toBeNull()

    await act(async () => {
      streamGate.resolve()
      await streamGate.promise
    })

    expect(await screen.findByText('最终正文')).not.toBeNull()
  })

  it('keeps text accumulated before a tool call and continues appending after it', async () => {
    const user = userEvent.setup()
    const streamGate = deferred()
    api.getAttachments.mockResolvedValue({ data: { items: [] } })
    api.postChatStream.mockImplementation(async (_request, callbacks) => {
      callbacks.onToken('# 步骤\n')
      callbacks.onToken('- 第一点\n')
      callbacks.onToolCall('search_learning_notes', { query: 'x' })
      await streamGate.promise
      callbacks.onToolResult('search_learning_notes', { ok: true })
      callbacks.onToken('## 结论\n')
      callbacks.onDone({
        session_id: 'session-1',
        reply: { answer: '## 最终答案\n\n来自 done.reply', sources: [] },
      })
    })

    render(<App />)
    await openSession(user)
    await user.type(document.querySelector('.chat-input'), 'stream this')
    await user.click(document.querySelector('.send-button'))

    // 工具调用期间：工具状态显示，工具调用前累积的正文不被清空，标题仍然成立
    expect(await screen.findByText(/正在调用 search_learning_notes/)).not.toBeNull()
    expect(screen.getByRole('heading', { name: '步骤' })).not.toBeNull()
    expect(screen.getByText('第一点')).not.toBeNull()

    await act(async () => {
      streamGate.resolve()
      await streamGate.promise
    })

    // 完成后以 done.reply 为准，流式预览被替换
    expect(await screen.findByRole('heading', { name: '最终答案' })).not.toBeNull()
    expect(screen.getByText('来自 done.reply')).not.toBeNull()
    expect(screen.queryByRole('heading', { name: '步骤' })).toBeNull()
    expect(screen.queryByText(/正在调用 search_learning_notes/)).toBeNull()
  })

  it('treats a done event without reply as a protocol error instead of promoting partial text', async () => {
    const user = userEvent.setup()
    api.getAttachments.mockResolvedValue({ data: { items: [] } })
    api.postChatStream.mockImplementation(async (_request, callbacks) => {
      callbacks.onToken('partial preview')
      callbacks.onDone({ session_id: 'session-1' })
    })

    render(<App />)
    await openSession(user)
    await user.type(document.querySelector('.chat-input'), 'stream this')
    await user.click(document.querySelector('.send-button'))

    expect(await screen.findByText(/缺少正式回复数据/)).not.toBeNull()
    expect(screen.queryByText('partial preview')).toBeNull()
    await waitFor(() => expect(screen.getByRole('button', { name: '流式' }).disabled).toBe(false))
  })

  it('clears sending state after a stream error callback', async () => {
    const user = userEvent.setup()
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    api.getAttachments.mockResolvedValue({ data: { items: [] } })
    api.postChatStream.mockImplementation(async (_request, callbacks) => {
      callbacks.onError('generation failed')
    })

    render(<App />)
    await openSession(user)
    await user.type(screen.getByPlaceholderText('写下你的问题，或让导师帮你拆解下一步…'), 'fail stream')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(screen.getByRole('button', { name: '流式' }).disabled).toBe(false))
    expect(consoleError).toHaveBeenCalledWith('Stream error:', 'generation failed')
    consoleError.mockRestore()
  })

  it('does not promote partial stream text to a successful reply after rejection', async () => {
    const user = userEvent.setup()
    api.getAttachments.mockResolvedValue({ data: { items: [] } })
    api.postChatStream.mockImplementation(async (_request, callbacks) => {
      callbacks.onToken('partial answer')
      throw new Error('stream failed')
    })

    render(<App />)
    await openSession(user)
    await user.type(document.querySelector('.chat-input'), 'fail stream')
    await user.click(document.querySelector('.send-button'))

    await waitFor(() => expect(document.querySelector('.streaming-toggle').disabled).toBe(false))
    expect(screen.getByText('partial answer')).not.toBeNull()
    expect(screen.getByText('stream failed')).not.toBeNull()
    expect(screen.queryByText('这次请求后端失败了，但页面没有崩溃')).toBeNull()
    expect(screen.getByText('API 在线')).not.toBeNull()
  })

  it('shows the real stream error and preserves complete debug details', async () => {
    const user = userEvent.setup()
    api.getAttachments.mockResolvedValue({ data: { items: [] } })
    api.postChatStream.mockImplementation(async (_request, callbacks) => {
      callbacks.onToken('partial answer')
      throw {
        message: 'Chat stream failed',
        status: 200,
        detail: {
          error: 'conversation_persistence_failed',
          message: '回答已生成，但对话保存失败。',
          debug_message: 'RuntimeError: database is locked',
        },
        responseBody: {
          error: 'conversation_persistence_failed',
          message: '回答已生成，但对话保存失败。',
        },
        debug: { error: '回答已生成，但对话保存失败。' },
      }
    })

    render(<App />)
    await openSession(user)
    await user.type(document.querySelector('.chat-input'), 'save this')
    await user.click(document.querySelector('.send-button'))

    expect(await screen.findByText('回答已生成，但对话保存失败。')).not.toBeNull()
    expect(screen.getByText('partial answer')).not.toBeNull()
    expect(screen.queryByText(/排查建议/)).toBeNull()
    await user.click(screen.getByText('调试详情'))
    expect(screen.getByText(/"status": 200/)).not.toBeNull()
    expect(screen.getByText(/"conversation_persistence_failed"/)).not.toBeNull()
    expect(screen.getByText(/"responseBody"/)).not.toBeNull()
    expect(screen.getByText('API 在线')).not.toBeNull()
  })

  it('keeps internal stream errors out of the visible reply', async () => {
    const user = userEvent.setup()
    api.getAttachments.mockResolvedValue({ data: { items: [] } })
    api.postChatStream.mockRejectedValue({
      message: '流式响应处理失败，请重试。',
      status: 200,
      detail: {
        error: 'stream_internal_error',
        stage: 'stream',
        message: '流式响应处理失败，请重试。',
        debug_message: 'ValueError: Token was created in a different Context',
      },
      responseBody: {
        error: 'stream_internal_error',
        message: '流式响应处理失败，请重试。',
        debug_message: 'ValueError: Token was created in a different Context',
      },
    })

    render(<App />)
    await openSession(user)
    await user.type(document.querySelector('.chat-input'), 'internal failure')
    await user.click(document.querySelector('.send-button'))

    expect(await screen.findByText('流式响应处理失败，请重试。')).not.toBeNull()
    const debugDetails = document.querySelector('.debug-details')
    expect(debugDetails.open).toBe(false)
    await user.click(screen.getByText('调试详情'))
    expect(screen.getByText(/Token was created in a different Context/)).not.toBeNull()
    expect(screen.getByText('API 在线')).not.toBeNull()
  })

  it('keeps the API status unchanged after a chat HTTP error', async () => {
    const user = userEvent.setup()
    localStorage.setItem('tutor-streaming', 'false')
    api.getAttachments.mockResolvedValue({ data: { items: [] } })
    api.postChat.mockRejectedValue({
      message: 'Chat request failed: 422',
      status: 422,
      detail: { message: '请求参数无效' },
      responseBody: { detail: { message: '请求参数无效' } },
    })

    render(<App />)
    await openSession(user)
    await user.type(document.querySelector('.chat-input'), 'invalid request')
    await user.click(document.querySelector('.send-button'))

    expect(await screen.findByText('请求参数无效')).not.toBeNull()
    expect(screen.getByText('API 在线')).not.toBeNull()
  })

  it('refreshes API status only through the health check', async () => {
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(api.getHealth).toHaveBeenCalledTimes(1))
    api.getHealth.mockRejectedValueOnce(new Error('health unavailable'))
    await user.click(screen.getByRole('button', { name: '刷新 API 状态' }))

    expect(await screen.findByText('API 离线')).not.toBeNull()
    expect(api.getHealth).toHaveBeenCalledTimes(2)
  })

  it('aborts an active stream and removes transient output when stopped', async () => {
    const user = userEvent.setup()
    const streamFinished = deferred()
    api.getAttachments.mockResolvedValue({ data: { items: [] } })
    api.postChatStream.mockImplementation(async (_request, callbacks, options) => {
      callbacks.onToken('partial answer')
      options.signal.addEventListener('abort', () => {
        queueMicrotask(() => {
          callbacks.onToken('late token')
          streamFinished.resolve()
        })
      })
      await streamFinished.promise
    })

    render(<App />)
    await openSession(user)
    await user.type(document.querySelector('.chat-input'), 'stop stream')
    await user.click(document.querySelector('.send-button'))

    await waitFor(() => expect(api.postChatStream).toHaveBeenCalledWith(
      expect.any(Object),
      expect.any(Object),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    expect(await screen.findByText('partial answer')).not.toBeNull()

    await user.click(document.querySelector('.send-button[type="button"]'))

    await waitFor(() => expect(screen.queryByText('partial answer')).toBeNull())
    expect(screen.queryByText('late token')).toBeNull()
    expect(api.postChatStream.mock.calls[0][2].signal.aborted).toBe(true)
    expect(document.querySelector('.send-button[type="button"]')).toBeNull()
    await waitFor(() => expect(document.querySelector('.streaming-toggle').disabled).toBe(false))
  })

  it('uses ordinary chat when the streaming toggle is off', async () => {
    const user = userEvent.setup()
    localStorage.setItem('tutor-streaming', 'false')
    api.getAttachments.mockResolvedValue({ data: { items: [] } })

    render(<App />)
    await openSession(user)
    await user.type(screen.getByPlaceholderText('写下你的问题，或让导师帮你拆解下一步…'), 'normal chat')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.postChat).toHaveBeenCalledTimes(1))
    expect(api.postChatStream).not.toHaveBeenCalled()
  })
})

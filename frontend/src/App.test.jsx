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
  api.getInterviewJDs.mockResolvedValue({ data: { items: [] } })
  api.getSessionConversations.mockResolvedValue({ data: { items: [] } })
  api.createSession.mockResolvedValue({ data: sessions[0] })
  api.postChat.mockResolvedValue({
    data: {
      session_id: 'session-1',
      reply: {
        answer: 'done',
        next_task: 'next',
        exercise: 'exercise',
        checkpoints: [],
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

  it('clears attachment state and ignores stale responses after persona changes', async () => {
    const user = userEvent.setup()
    const attachmentList = deferred()
    api.getAttachments.mockReturnValue(attachmentList.promise)

    render(<App />)
    await openSession(user)
    await waitFor(() => expect(api.getAttachments).toHaveBeenCalledTimes(1))

    await user.selectOptions(screen.getByRole('combobox'), 'reviewer')
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
  const input = () => screen.getByPlaceholderText('写下你的问题，或让导师帮你拆解下一步…')

  it('defaults to auto mode', async () => {
    render(<App />)
    expect(ragButton().getAttribute('aria-label')).toBe('RAG 检索：自动判断')
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
    await user.type(input(), 'one shot')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => expect(api.postChat).toHaveBeenCalledTimes(1))
    expect(ragButton().getAttribute('aria-label')).toBe('RAG 检索：自动判断')
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

  it('accumulates stream tokens into a displayable assistant reply and clears sending state on done', async () => {
    const user = userEvent.setup()
    api.getAttachments.mockResolvedValue({ data: { items: [] } })
    api.postChatStream.mockImplementation(async (_request, callbacks) => {
      callbacks.onToken('Hello ')
      callbacks.onToken('world')
      callbacks.onDone({ session_id: 'session-1' })
    })

    render(<App />)
    await openSession(user)
    await user.type(screen.getByPlaceholderText('写下你的问题，或让导师帮你拆解下一步…'), 'stream this')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    expect(await screen.findByText('Hello world')).not.toBeNull()
    expect(api.postChatStream).toHaveBeenCalledTimes(1)
    expect(api.postChat).not.toHaveBeenCalled()
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
    expect(screen.queryByText('partial answer')).toBeNull()
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

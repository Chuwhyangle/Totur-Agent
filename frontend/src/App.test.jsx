import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
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
    Object.values(api).forEach((mock) => mock.mockReset())
    localStorage.clear()
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


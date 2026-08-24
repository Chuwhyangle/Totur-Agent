import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  API_BASE_URL,
  TutorApiError,
  deleteAttachment,
  getAttachments,
  getWorkspaceArtifactContent,
  getWorkspaceAssetDownloadUrl,
  getWorkspaceAssets,
  getWorkspaceTasks,
  getWorkspaces,
  createWorkspace,
  uploadWorkspaceAsset,
  retryWorkspaceAsset,
  deleteWorkspaceAsset,
  postChat,
  postChatStream,
  retryAttachment,
  uploadAttachment,
} from './tutorApi.js'

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(body),
  }
}

describe('tutorApi attachment API', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uploads PDF with FormData without forcing multipart Content-Type', async () => {
    fetch.mockResolvedValue(jsonResponse({ id: 'attachment-1', status: 'UPLOADED' }, 201))
    const file = new File(['pdf'], 'resume.pdf', { type: 'application/pdf' })

    const result = await uploadAttachment('session-1', 'user one', file)

    expect(result.data.id).toBe('attachment-1')
    expect(fetch).toHaveBeenCalledTimes(1)
    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe(`${API_BASE_URL}/sessions/session-1/attachments`)
    expect(options.method).toBe('POST')
    expect(options.headers).toBeUndefined()
    expect(options.debugRequestBody).toBeUndefined()
    expect(options.body).toBeInstanceOf(FormData)
    expect(options.body.get('user_id')).toBe('user one')
    expect(options.body.get('file')).toBe(file)
  })

  it('uses the expected list, retry, and delete routes', async () => {
    fetch
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
      .mockResolvedValueOnce(jsonResponse({ id: 'attachment/1', status: 'PARSING' }))
      .mockResolvedValueOnce({ ok: true, status: 204, json: vi.fn() })

    await getAttachments('session-1', 'user one')
    await retryAttachment('session-1', 'attachment/1', 'user one')
    await deleteAttachment('session-1', 'attachment/1', 'user one')

    expect(fetch.mock.calls[0][0]).toBe(
      `${API_BASE_URL}/sessions/session-1/attachments?user_id=user+one`,
    )
    expect(fetch.mock.calls[1][0]).toBe(
      `${API_BASE_URL}/sessions/session-1/attachments/attachment%2F1/retry?user_id=user+one`,
    )
    expect(fetch.mock.calls[1][1].method).toBe('POST')
    expect(fetch.mock.calls[2][0]).toBe(
      `${API_BASE_URL}/sessions/session-1/attachments/attachment%2F1?user_id=user+one`,
    )
    expect(fetch.mock.calls[2][1].method).toBe('DELETE')
  })

  it('preserves business error details without treating HTTP 4xx as offline', async () => {
    const responseBody = {
      detail: {
        error: 'attachment_not_ready',
        message: 'not ready',
      },
    }
    fetch.mockResolvedValue(jsonResponse(responseBody, 409))

    let caught
    try {
      await retryAttachment('session-1', 'attachment-1', 'user-1')
    } catch (error) {
      caught = error
    }

    expect(caught).toBeInstanceOf(TutorApiError)
    expect(caught).toMatchObject({
      status: 409,
      detail: responseBody.detail,
      responseBody,
      isNetworkError: false,
      isAbortError: false,
    })
    expect(caught.debug).toMatchObject({
      method: 'POST',
      status: 409,
      responseBody,
    })
  })

  it('sends attachment_ids in the chat JSON body', async () => {
    fetch.mockResolvedValue(jsonResponse({ reply: { answer: 'ok' } }))
    const requestBody = {
      user_id: 'user-1',
      session_id: 'session-1',
      persona_id: 'tutor',
      message: '总结附件',
      force_web_search: false,
      attachment_ids: ['attachment-1'],
    }

    await postChat(requestBody)

    const [, options] = fetch.mock.calls[0]
    expect(options.headers).toEqual({ 'Content-Type': 'application/json' })
    expect(JSON.parse(options.body)).toEqual(requestBody)
  })
})

describe('tutorApi Workspace API', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses Workspace lifecycle and list URLs with the user query', async () => {
    fetch.mockResolvedValue(jsonResponse({ items: [] }))
    await getWorkspaces('user one')
    expect(fetch.mock.calls[0][0]).toBe(`${API_BASE_URL}/workspaces?user_id=user+one&limit=50`)

    fetch.mockResolvedValue(jsonResponse({ id: 'w1' }, 201))
    await createWorkspace({ user_id: 'user one', name: 'Project' })
    expect(fetch.mock.calls[1][0]).toBe(`${API_BASE_URL}/workspaces`)
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ user_id: 'user one', name: 'Project' })
  })

  it('supports Asset, Task, and Markdown content endpoints', async () => {
    fetch.mockResolvedValueOnce(jsonResponse({ asset: { id: 'a1' } }, 202))
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
      .mockResolvedValueOnce(jsonResponse({ id: 'a1', status: 'PROCESSING' }, 202))
      .mockResolvedValueOnce(jsonResponse({ id: 'a1', status: 'DELETED' }))
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
      .mockResolvedValueOnce({ ok: true, status: 200, text: vi.fn().mockResolvedValue('# report') })

    await uploadWorkspaceAsset('w/1', 'user one', new File(['notes'], 'notes.md', { type: 'text/markdown' }))
    await getWorkspaceAssets('w/1', 'user one')
    await retryWorkspaceAsset('w/1', 'a/1', 'user one')
    await deleteWorkspaceAsset('w/1', 'a/1', 'user one')
    await getWorkspaceTasks('w/1', 'user one')
    await getWorkspaceArtifactContent('w/1', 'art/1', 'user one')

    expect(fetch.mock.calls[0][0]).toContain('/workspaces/w%2F1/assets?user_id=user%20one')
    expect(fetch.mock.calls[2][1].method).toBe('POST')
    expect(fetch.mock.calls[3][1].method).toBe('DELETE')
    expect(fetch.mock.calls[5][0]).toContain('/workspaces/w%2F1/artifacts/art%2F1/content')
    expect(getWorkspaceAssetDownloadUrl('w/1', 'a/1', 'user one')).toContain('/workspaces/w%2F1/assets/a%2F1/download')
  })
})


describe('tutorApi SSE API', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function streamResponse(chunks) {
    const encoder = new TextEncoder()
    const reads = chunks.map((chunk) => ({ done: false, value: encoder.encode(chunk) }))
    reads.push({ done: true, value: undefined })
    return {
      ok: true,
      status: 200,
      body: {
        getReader: () => ({ read: vi.fn().mockImplementation(() => Promise.resolve(reads.shift())) }),
      },
    }
  }

  it('forwards rag fields verbatim in chat and stream bodies', async () => {
    fetch.mockResolvedValue(jsonResponse({ reply: { answer: 'ok' } }))
    const chatBody = {
      user_id: 'user-1',
      message: 'q',
      rag_enabled: true,
      force_rag: true,
    }
    await postChat(chatBody)
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(chatBody)

    const streamBody = {
      user_id: 'user-1',
      message: 'q',
      rag_enabled: false,
      force_rag: false,
    }
    fetch.mockResolvedValue(streamResponse([
      'event: done\ndata: {"session_id":"session-1"}\n\n',
    ]))
    await postChatStream(streamBody, { onDone: vi.fn() })
    expect(fetch).toHaveBeenLastCalledWith(
      `${API_BASE_URL}/chat/stream`,
      expect.objectContaining({ body: JSON.stringify(streamBody) }),
    )
  })

  it('posts JSON to the stream URL and dispatches token, tool, and done events', async () => {
    fetch.mockResolvedValue(streamResponse([
      'event: token\ndata: {"text":"Hello "}\n\n'
      + 'event: tool_call\ndata: {"tool":"search","args":{"q":"SSE"}}\n\n'
      + 'event: tool_result\ndata: {"tool":"search","result":{"ok":true}}\n\n'
      + 'event: token\ndata: {"text":"world"}\n\n'
      + 'event: done\ndata: {"session_id":"session-1","reply":{"answer":"Hello world"}}\n\n',
    ]))
    const callbacks = {
      onToken: vi.fn(),
      onToolCall: vi.fn(),
      onToolResult: vi.fn(),
      onDone: vi.fn(),
      onError: vi.fn(),
    }
    const body = { user_id: 'user-1', message: 'hello' }

    await postChatStream(body, callbacks)

    expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/chat/stream`, expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }))
    expect(callbacks.onToken.mock.calls).toEqual([['Hello '], ['world']])
    expect(callbacks.onToolCall).toHaveBeenCalledWith('search', { q: 'SSE' })
    expect(callbacks.onToolResult).toHaveBeenCalledWith('search', { ok: true })
    expect(callbacks.onDone).toHaveBeenCalledWith({
      session_id: 'session-1',
      reply: { answer: 'Hello world' },
    })
    expect(callbacks.onError).not.toHaveBeenCalled()
  })

  it('keeps an SSE frame buffered when its event and data arrive in separate chunks', async () => {
    fetch.mockResolvedValue(streamResponse([
      'event: token\r\n',
      'data: {"text":"split frame"}\r\n\r\n'
        + 'event: done\r\ndata: {"session_id":"session-1"}\r\n\r\n',
    ]))
    const callbacks = { onToken: vi.fn(), onDone: vi.fn(), onError: vi.fn() }

    await postChatStream({ user_id: 'user-1', message: 'hello' }, callbacks)

    expect(callbacks.onToken).toHaveBeenCalledWith('split frame')
    expect(callbacks.onDone).toHaveBeenCalledWith({ session_id: 'session-1' })
    expect(callbacks.onError).not.toHaveBeenCalled()
  })

  it('rejects an EOF without a terminal SSE event', async () => {
    fetch.mockResolvedValue(streamResponse([
      'event: token\ndata: {"text":"partial"}\n\n',
    ]))
    const callbacks = { onToken: vi.fn(), onError: vi.fn() }

    await expect(postChatStream({ user_id: 'user-1', message: 'hello' }, callbacks))
      .rejects.toMatchObject({ name: 'TutorApiError', message: 'Chat stream ended unexpectedly' })

    expect(callbacks.onToken).toHaveBeenCalledWith('partial')
    expect(callbacks.onError).toHaveBeenCalledWith('Chat stream ended unexpectedly')
  })
  it('dispatches a well-formed SSE error event', async () => {
    fetch.mockResolvedValue(streamResponse([
      'event: error\ndata: {"message":"generation failed"}\n\n',
    ]))
    const onError = vi.fn()

    await expect(postChatStream({ user_id: 'user-1', message: 'hello' }, { onError }))
      .rejects.toMatchObject({ name: 'TutorApiError', message: 'Chat stream failed' })

    expect(onError).toHaveBeenCalledWith('generation failed')
  })
})


describe('tutorApi SSE cancellation', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('treats an aborted request as cancellation instead of an error', async () => {
    const abortError = new Error('aborted')
    abortError.name = 'AbortError'
    fetch.mockRejectedValue(abortError)
    const onError = vi.fn()

    await expect(postChatStream(
      { user_id: 'user-1', message: 'cancel' },
      { onError },
      { signal: new AbortController().signal },
    )).resolves.toBeUndefined()

    expect(onError).not.toHaveBeenCalled()
  })
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  TutorApiError,
  deleteAttachment,
  getAttachments,
  postChat,
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
    expect(url).toBe('http://127.0.0.1:8001/sessions/session-1/attachments')
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
      'http://127.0.0.1:8001/sessions/session-1/attachments?user_id=user+one',
    )
    expect(fetch.mock.calls[1][0]).toBe(
      'http://127.0.0.1:8001/sessions/session-1/attachments/attachment%2F1/retry?user_id=user+one',
    )
    expect(fetch.mock.calls[1][1].method).toBe('POST')
    expect(fetch.mock.calls[2][0]).toBe(
      'http://127.0.0.1:8001/sessions/session-1/attachments/attachment%2F1?user_id=user+one',
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

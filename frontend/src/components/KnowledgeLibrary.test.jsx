import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import KnowledgeLibrary from './KnowledgeLibrary.jsx'
import * as api from '../api/tutorApi.js'

vi.mock('../api/tutorApi.js', async () => {
  const actual = await vi.importActual('../api/tutorApi.js')
  return { ...actual, getKnowledgeDocuments: vi.fn(), uploadKnowledgeDocument: vi.fn(), deleteKnowledgeDocument: vi.fn(), retryKnowledgeDocument: vi.fn() }
})

describe('KnowledgeLibrary', () => {
  beforeEach(() => { vi.clearAllMocks(); api.getKnowledgeDocuments.mockResolvedValue({ data: { items: [] } }) })

  it('uploads and refreshes the list', async () => {
    const user = userEvent.setup()
    api.uploadKnowledgeDocument.mockResolvedValue({ data: { duplicate: false } })
    const { container } = render(<KnowledgeLibrary userId="alice" onClose={() => {}} />)
    await waitFor(() => expect(api.getKnowledgeDocuments).toHaveBeenCalled())
    await user.upload(container.querySelector('input[type="file"]'), new File(['body'], 'notes.md', { type: 'text/markdown' }))
    await waitFor(() => expect(api.uploadKnowledgeDocument).toHaveBeenCalled())
  })

  it('shows an in-progress state while a document upload is pending', async () => {
    const user = userEvent.setup()
    let resolveUpload
    api.uploadKnowledgeDocument.mockReturnValue(new Promise((resolve) => { resolveUpload = resolve }))
    const { container } = render(<KnowledgeLibrary userId="alice" onClose={() => {}} />)
    await waitFor(() => expect(api.getKnowledgeDocuments).toHaveBeenCalled())

    await user.upload(container.querySelector('input[type="file"]'), new File(['pdf'], 'guide.pdf', { type: 'application/pdf' }))
    expect(screen.getByRole('status').textContent).toContain('正在上传并处理文档')
    expect(screen.getByRole('button', { name: '处理中…' }).disabled).toBe(true)

    resolveUpload({ data: { duplicate: false } })
    await waitFor(() => expect(api.getKnowledgeDocuments).toHaveBeenCalledTimes(2))
  })

  it('closes from the close button and Escape key', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<KnowledgeLibrary userId="alice" onClose={onClose} />)
    await waitFor(() => expect(api.getKnowledgeDocuments).toHaveBeenCalled())

    await user.click(screen.getByRole('dialog').querySelector('button[aria-label="关闭文档库"]'))
    expect(onClose).toHaveBeenCalledTimes(1)
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('explains when the running backend has no knowledge document routes', async () => {
    api.getKnowledgeDocuments.mockRejectedValue({ status: 404, message: 'request failed' })
    render(<KnowledgeLibrary userId="alice" onClose={() => {}} />)

    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('请重启后端服务'))
  })

  it('rejects unsupported extensions locally', async () => {
    const { container } = render(<KnowledgeLibrary userId="alice" onClose={() => {}} />)
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(['body'], 'notes.txt', { type: 'text/plain' })], value: '' } })
    await waitFor(() => expect(screen.getByText('只支持 PDF、Markdown 文件')).toBeTruthy())
    expect(api.uploadKnowledgeDocument).not.toHaveBeenCalled()
    expect(screen.getByText('只支持 PDF、Markdown 文件')).toBeTruthy()
  })
})

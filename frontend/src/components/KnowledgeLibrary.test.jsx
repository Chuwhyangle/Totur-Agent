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

  it('rejects unsupported extensions locally', async () => {
    const { container } = render(<KnowledgeLibrary userId="alice" onClose={() => {}} />)
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(['body'], 'notes.txt', { type: 'text/plain' })], value: '' } })
    await waitFor(() => expect(screen.getByText('只支持 PDF、Markdown 文件')).toBeTruthy())
    expect(api.uploadKnowledgeDocument).not.toHaveBeenCalled()
    expect(screen.getByText('只支持 PDF、Markdown 文件')).toBeTruthy()
  })
})

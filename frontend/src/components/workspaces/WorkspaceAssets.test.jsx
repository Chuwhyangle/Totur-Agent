import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import WorkspaceAssets from './WorkspaceAssets.jsx'

describe('WorkspaceAssets', () => {
  it('separates Workspace files and disables writes when archived', async () => {
    const user = userEvent.setup()
    const onUpload = vi.fn()
    render(<WorkspaceAssets assets={[{ id: 'a1', original_filename: 'notes.md', media_type: 'text/markdown', size_bytes: 10, status: 'READY' }]} disabled onUpload={onUpload} />)

    expect(screen.getByText('notes.md')).toBeTruthy()
    expect(screen.getByRole('button', { name: '下载 notes.md' }).disabled).toBe(true)
    const input = document.querySelector('input[type="file"]')
    await user.upload(input, new File(['# notes'], 'new.md', { type: 'text/markdown' }))
    expect(onUpload).not.toHaveBeenCalled()
  })
})

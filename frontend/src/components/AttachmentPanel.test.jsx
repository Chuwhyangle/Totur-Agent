import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import AttachmentPanel from './AttachmentPanel.jsx'

const attachments = [
  {
    id: 'ready-1',
    original_filename: 'resume.pdf',
    size_bytes: 2048,
    status: 'READY',
  },
  {
    id: 'failed-1',
    original_filename: 'broken.pdf',
    size_bytes: 1024,
    status: 'FAILED',
    user_safe_message: 'PDF 无法解析。',
  },
]

describe('AttachmentPanel', () => {
  it('supports selecting, retrying, deleting, and uploading a PDF', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()
    const onRetry = vi.fn()
    const onDelete = vi.fn()
    const onUpload = vi.fn().mockResolvedValue(undefined)
    const { container } = render(
      <AttachmentPanel
        attachments={attachments}
        selectedAttachmentIds={['ready-1']}
        status="success"
        onToggle={onToggle}
        onRetry={onRetry}
        onDelete={onDelete}
        onUpload={onUpload}
      />,
    )

    await user.click(screen.getByRole('checkbox', { name: '选择附件 broken.pdf' }))
    await user.click(screen.getByRole('button', { name: '重试附件 broken.pdf' }))
    await user.click(screen.getByRole('button', { name: '删除附件 resume.pdf' }))
    const file = new File(['pdf'], 'new.pdf', { type: 'application/pdf' })
    await user.upload(container.querySelector('input[type="file"]'), file)

    expect(onToggle).toHaveBeenCalledWith('failed-1')
    expect(onRetry).toHaveBeenCalledWith('failed-1')
    expect(onDelete).toHaveBeenCalledWith('ready-1')
    expect(onUpload).toHaveBeenCalledWith(file)
    expect(screen.getByText('PDF 无法解析。')).not.toBeNull()
  })

  it('shows send blocking and action errors in Chinese', () => {
    render(
      <AttachmentPanel
        attachments={attachments}
        selectedAttachmentIds={['failed-1']}
        status="success"
        sendBlockReason="所选附件处理失败，请重试、删除或取消选择。"
        actionErrors={{ 'failed-1': '附件重试失败，请稍后再试。' }}
      />,
    )

    expect(screen.getByRole('status').textContent).toContain('处理失败')
    expect(screen.getByText('附件重试失败，请稍后再试。')).not.toBeNull()
  })
})

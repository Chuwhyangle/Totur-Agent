import { describe, expect, it } from 'vitest'

import {
  addSelectedAttachmentId,
  attachmentErrorMessage,
  getAttachmentSendBlockReason,
  getInitialSelectedAttachmentIds,
  getSendableAttachmentIds,
  reconcileSelectedAttachmentIds,
  shouldMarkApiOffline,
  validateAttachmentFile,
} from './attachments.js'

const attachment = (id, status) => ({ id, status })

describe('attachment state helpers', () => {
  it('auto-selects only READY/PARTIAL attachments and caps selection at five', () => {
    const items = [
      attachment('pending', 'PARSING'),
      attachment('ready-1', 'READY'),
      attachment('partial', 'PARTIAL'),
      attachment('ready-2', 'READY'),
      attachment('ready-3', 'READY'),
      attachment('ready-4', 'READY'),
      attachment('ready-5', 'READY'),
    ]

    expect(getInitialSelectedAttachmentIds(items)).toEqual([
      'ready-1',
      'partial',
      'ready-2',
      'ready-3',
      'ready-4',
    ])
  })

  it('removes stale attachment ids when the active scope list changes', () => {
    expect(reconcileSelectedAttachmentIds(
      ['old-session', 'shared', 'missing'],
      [attachment('shared', 'READY'), attachment('new-session', 'READY')],
    )).toEqual(['shared'])
  })

  it('blocks pending and failed selections from sending', () => {
    expect(getAttachmentSendBlockReason(
      [attachment('a1', 'PARSING')],
      ['a1'],
    )).toContain('处理中')
    expect(getAttachmentSendBlockReason(
      [attachment('a1', 'FAILED')],
      ['a1'],
    )).toContain('处理失败')
    expect(getAttachmentSendBlockReason(
      [attachment('a1', 'READY')],
      ['a1'],
    )).toBe('')
  })

  it('sends only selected usable attachments and never more than five', () => {
    const items = [
      attachment('ready-1', 'READY'),
      attachment('partial', 'PARTIAL'),
      attachment('failed', 'FAILED'),
      attachment('pending', 'INDEXING'),
      attachment('ready-2', 'READY'),
      attachment('ready-3', 'READY'),
      attachment('ready-4', 'READY'),
      attachment('ready-5', 'READY'),
    ]

    expect(getSendableAttachmentIds(items, items.map((item) => item.id))).toEqual([
      'ready-1',
      'partial',
      'ready-2',
      'ready-3',
      'ready-4',
    ])
  })

  it('deduplicates added ids, validates attachments, and maps safe Chinese errors', () => {
    expect(addSelectedAttachmentId(['a1'], 'a1')).toEqual(['a1'])
    expect(validateAttachmentFile(new File(['x'], 'note.txt', { type: 'text/plain' }))).toBe('')
    expect(validateAttachmentFile(new File(['x'], 'note.exe', { type: 'application/octet-stream' }))).toContain('不支持')
    expect(attachmentErrorMessage({ detail: { error: 'attachment_too_large' } })).toBe(
      '文件超过大小限制。',
    )
    expect(shouldMarkApiOffline({ status: 409, isNetworkError: false })).toBe(false)
    expect(shouldMarkApiOffline({ status: null, isNetworkError: true })).toBe(true)
  })
})

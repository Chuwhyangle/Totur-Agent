import { useRef } from 'react'

import Icon from './Icon.jsx'
import {
  attachmentStatusLabel,
  formatAttachmentSize,
} from '../utils/attachments.js'

function AttachmentPanel({
  attachments = [],
  selectedAttachmentIds = [],
  status = 'idle',
  error = '',
  actionErrors = {},
  actionStates = {},
  sendBlockReason = '',
  disabled = false,
  onUpload,
  onToggle,
  onRetry,
  onDelete,
}) {
  const fileInputRef = useRef(null)
  const selectedIds = new Set(selectedAttachmentIds)

  async function handleFileChange(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) await onUpload?.(file)
  }

  return (
    <section className="attachment-panel" aria-label="会话附件">
      <div className="attachment-toolbar">
        <button
          className="attachment-upload-button"
          type="button"
          disabled={disabled}
          onClick={() => fileInputRef.current?.click()}
        >
          <Icon name="paperclip" size={14} />
          <span>上传 PDF</span>
        </button>
        <input
          ref={fileInputRef}
          className="attachment-file-input"
          type="file"
          accept="application/pdf,.pdf"
          onChange={handleFileChange}
        />
        <span className="attachment-toolbar-summary">
          {status === 'loading' ? '正在读取附件…' : `已选 ${selectedAttachmentIds.length}/5`}
        </span>
      </div>

      {attachments.length > 0 ? (
        <ul className="attachment-list">
          {attachments.map((attachment) => {
            const isSelected = selectedIds.has(attachment.id)
            const actionState = actionStates[attachment.id]
            const displayStatus = actionState === 'deleting' ? 'DELETING' : attachment.status
            const selectionDisabled = !isSelected && selectedAttachmentIds.length >= 5

            return (
              <li className="attachment-item" key={attachment.id}>
                <label className="attachment-select-control">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    disabled={selectionDisabled || actionState === 'deleting'}
                    onChange={() => onToggle?.(attachment.id)}
                    aria-label={`选择附件 ${attachment.original_filename}`}
                  />
                  <span className="attachment-file-icon"><Icon name="file" size={14} /></span>
                  <span className="attachment-copy">
                    <strong title={attachment.original_filename}>{attachment.original_filename}</strong>
                    <small>{formatAttachmentSize(attachment.size_bytes)}</small>
                  </span>
                </label>
                <span className={`attachment-status attachment-status-${String(displayStatus).toLowerCase()}`}>
                  {attachmentStatusLabel(displayStatus)}
                </span>
                <span className="attachment-actions">
                  {attachment.status === 'FAILED' ? (
                    <button
                      type="button"
                      disabled={Boolean(actionState)}
                      onClick={() => onRetry?.(attachment.id)}
                      aria-label={`重试附件 ${attachment.original_filename}`}
                    >
                      <Icon name="refresh" size={13} />
                      <span>{actionState === 'retrying' ? '重试中' : '重试'}</span>
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={Boolean(actionState)}
                    onClick={() => onDelete?.(attachment.id)}
                    aria-label={`删除附件 ${attachment.original_filename}`}
                  >
                    <Icon name="trash" size={13} />
                    <span>{actionState === 'deleting' ? '删除中' : '删除'}</span>
                  </button>
                </span>
                {attachment.user_safe_message ? (
                  <p className="attachment-item-message">{attachment.user_safe_message}</p>
                ) : null}
                {actionErrors[attachment.id] ? (
                  <p className="attachment-item-message attachment-item-error">{actionErrors[attachment.id]}</p>
                ) : null}
              </li>
            )
          })}
        </ul>
      ) : null}

      {status === 'success' && attachments.length === 0 ? (
        <p className="attachment-empty">可上传包含文本层的 PDF，仅在当前会话中使用。</p>
      ) : null}
      {error ? <p className="attachment-panel-error" role="alert">{error}</p> : null}
      {sendBlockReason ? <p className="attachment-send-block" role="status">{sendBlockReason}</p> : null}
    </section>
  )
}

export default AttachmentPanel

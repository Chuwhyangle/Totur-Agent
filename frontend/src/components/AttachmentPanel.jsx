import { useRef } from 'react'

import Icon from './Icon.jsx'
import { attachmentStatusLabel, formatAttachmentSize, getAttachmentIconName, SUPPORTED_ATTACHMENT_ACCEPT } from '../utils/attachments.js'

function AttachmentList({
  attachments = [],
  selectedAttachmentIds = [],
  actionErrors = {},
  actionStates = {},
  onToggle,
  onRetry,
  onDelete,
}) {
  const selectedIds = new Set(selectedAttachmentIds)
  return attachments.length > 0 ? (
    <ul className="attachment-list">
      {attachments.map((attachment) => {
        const isSelected = selectedIds.has(attachment.id)
        const actionState = actionStates[attachment.id]
        const displayStatus = actionState === 'deleting' ? 'DELETING' : attachment.status
        const selectionDisabled = !isSelected && selectedAttachmentIds.length >= 5
        return (
          <li className="attachment-item" key={attachment.id}>
            <label className="attachment-select-control">
              <input type="checkbox" checked={isSelected} disabled={selectionDisabled || actionState === 'deleting'} onChange={() => onToggle?.(attachment.id)} aria-label={`选择附件 ${attachment.original_filename}`} />
              <span className="attachment-file-icon"><Icon name={getAttachmentIconName(attachment.original_filename)} size={14} /></span>
              <span className="attachment-copy"><strong title={attachment.original_filename}>{attachment.original_filename}</strong><small>{formatAttachmentSize(attachment.size_bytes)}</small></span>
            </label>
            <span className={`attachment-status attachment-status-${String(displayStatus).toLowerCase()}`}><span className="attachment-status-dot" />{attachmentStatusLabel(displayStatus)}</span>
            <span className="attachment-actions">
              {attachment.status === 'FAILED' ? <button type="button" disabled={Boolean(actionState)} onClick={() => onRetry?.(attachment.id)} aria-label={`重试附件 ${attachment.original_filename}`}><Icon name="refresh" size={13} /><span>{actionState === 'retrying' ? '重试中' : '重试'}</span></button> : null}
              <button type="button" disabled={Boolean(actionState)} onClick={() => onDelete?.(attachment.id)} aria-label={`删除附件 ${attachment.original_filename}`}><Icon name="trash" size={13} /><span>{actionState === 'deleting' ? '删除中' : '删除'}</span></button>
            </span>
            {attachment.user_safe_message ? <p className="attachment-item-message">{attachment.user_safe_message}</p> : null}
            {actionErrors[attachment.id] ? <p className="attachment-item-message attachment-item-error">{actionErrors[attachment.id]}</p> : null}
          </li>
        )
      })}
    </ul>
  ) : null
}

export function AttachmentPopover({
  open = true,
  fileInputRef,
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
  onClose,
}) {
  const internalInputRef = useRef(null)
  const inputRef = fileInputRef || internalInputRef
  if (!open) return null

  async function handleFileChange(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) await onUpload?.(file)
  }

  return (
    <section className="attachment-popover" role="dialog" aria-label="附件管理">
      <div className="attachment-popover-header">
        <strong>附件管理</strong>
        {onClose ? <button className="icon-button" type="button" onClick={onClose} aria-label="关闭附件管理"><Icon name="close" size={14} /></button> : null}
      </div>
      <button className="attachment-upload-button" type="button" disabled={disabled} onClick={() => inputRef.current?.click()}><Icon name="plus" size={14} /><span>上传附件</span></button>
      <input ref={inputRef} className="attachment-file-input" type="file" accept={SUPPORTED_ATTACHMENT_ACCEPT} onChange={handleFileChange} />
      <span className="attachment-toolbar-summary">{status === 'loading' ? '正在读取附件…' : `已选 ${selectedAttachmentIds.length}/5`}</span>
      <AttachmentList attachments={attachments} selectedAttachmentIds={selectedAttachmentIds} actionErrors={actionErrors} actionStates={actionStates} onToggle={onToggle} onRetry={onRetry} onDelete={onDelete} />
      {status === 'success' && attachments.length === 0 ? <p className="attachment-empty">可上传 PDF、Office、文本、Markdown、代码、CSV 或 JSON，仅在当前会话中使用。</p> : null}
      {error ? <p className="attachment-panel-error" role="alert">{error}</p> : null}
      {sendBlockReason ? <p className="attachment-send-block" role="status">{sendBlockReason}</p> : null}
    </section>
  )
}

export function AttachmentChips({ attachments = [], onDelete }) {
  if (attachments.length === 0) return null
  return (
    <div className="attachment-chips" aria-label="已选附件">
      {attachments.map((attachment) => {
        const status = String(attachment.status || '').toLowerCase()
        return <span className="attachment-chip" key={attachment.id}><Icon name={getAttachmentIconName(attachment.original_filename)} size={13} /><span className="attachment-chip-name" title={attachment.original_filename}>{attachment.original_filename}</span><span className={`attachment-chip-dot attachment-chip-dot-${status}`} /><span className="attachment-chip-status">{attachmentStatusLabel(attachment.status)}</span><button type="button" aria-label={`删除附件 ${attachment.original_filename}`} title="移除附件" onClick={() => onDelete?.(attachment.id)}><Icon name="close" size={11} /></button></span>
      })}
    </div>
  )
}

// Compatibility wrapper for callers that used the old always-open panel.
function AttachmentPanel(props) {
  return <AttachmentPopover {...props} open />
}

export default AttachmentPanel

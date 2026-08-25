import { useEffect, useRef, useState } from 'react'

import Icon from './Icon.jsx'
import { AttachmentChips, AttachmentPopover } from './AttachmentPanel.jsx'
import { SUPPORTED_ATTACHMENT_ACCEPT, validateAttachmentFile } from '../utils/attachments.js'

const MODE_ORDER = ['auto', 'force', 'off']
const MODE_LABELS = { auto: '自动判断', force: '本轮强制使用', off: '强制关闭', documents: '仅文档库' }

function ModeControl({ kind, mode, onChange, disabled }) {
  const [open, setOpen] = useState(false)
  const isRag = kind === 'RAG 检索'
  const IconName = isRag ? 'file' : 'globe'
  const cycleMode = () => onChange?.(MODE_ORDER[(MODE_ORDER.indexOf(mode) + 1) % MODE_ORDER.length])
  return (
    <span className="mode-control">
      <button className={`web-search-toggle rag-toggle${mode === 'force' ? ' is-active' : ''}${mode === 'off' ? ' is-rag-off' : ''}`} type="button" aria-pressed={mode === 'force'} aria-label={`${kind}：${MODE_LABELS[mode]}`} title={`${kind}：${MODE_LABELS[mode]}`} disabled={disabled} onClick={cycleMode}>
        <Icon name={IconName} size={14} strokeWidth={1.7} /><span>{kind}</span><small>{MODE_LABELS[mode]}</small>
      </button>
      <button className="mode-chevron" type="button" aria-label="模式选项" aria-expanded={open} onClick={() => setOpen((value) => !value)} disabled={disabled}><Icon name="chevron-down" size={12} /></button>
      {open ? <div className="mode-popover" role="radiogroup" aria-label={`${kind}模式`}>
        {MODE_ORDER.map((value) => <button key={value} type="button" role="radio" aria-checked={mode === value} onClick={() => { onChange?.(value); setOpen(false) }}>{MODE_LABELS[value]}</button>)}
        {isRag ? <button type="button" role="radio" aria-checked={mode === 'documents'} onClick={() => { onChange?.('documents'); setOpen(false) }}>{MODE_LABELS.documents}</button> : null}
      </div> : null}
    </span>
  )
}

function ChatInput({
  message,
  onMessageChange,
  onSubmit,
  disabled = false,
  progressUpdateDisabled = false,
  isSending = false,
  webSearchMode = 'auto',
  onWebSearchModeChange,
  ragMode = 'auto',
  onRagModeChange,
  streamingEnabled = true,
  onStreamingEnabledChange,
  attachmentProps = null,
  notice = '',
  onStopStreaming,
  placeholder = '写下你的问题，或让导师帮你拆解下一步…',
}) {
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)
  const composerRef = useRef(null)
  const [attachmentOpen, setAttachmentOpen] = useState(false)
  const [isDragging, setIsDragging] = useState(false)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [message])

  useEffect(() => {
    if (!attachmentOpen) return undefined
    function handlePointerDown(event) {
      if (!composerRef.current?.contains(event.target)) setAttachmentOpen(false)
    }
    function handleEscape(event) {
      if (event.key === 'Escape') setAttachmentOpen(false)
    }
    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleEscape)
    return () => { document.removeEventListener('pointerdown', handlePointerDown); document.removeEventListener('keydown', handleEscape) }
  }, [attachmentOpen])

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (!disabled) event.currentTarget.form?.requestSubmit()
    }
  }

  function handlePaste(event) {
    const files = Array.from(event.clipboardData?.files || [])
    const attachment = files.find((file) => !validateAttachmentFile(file))
    if (attachment) {
      event.preventDefault()
      attachmentProps?.onUpload?.(attachment)
    }
  }

  function handleDrop(event) {
    event.preventDefault()
    setIsDragging(false)
    const attachment = Array.from(event.dataTransfer?.files || []).find((file) => !validateAttachmentFile(file))
    if (attachment) attachmentProps?.onUpload?.(attachment)
  }

  const attachments = attachmentProps?.attachments || []
  const hasAttachments = attachments.length > 0
  return (
    <div ref={composerRef} className={`composer-wrap${isDragging ? ' is-dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); setIsDragging(true) }} onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setIsDragging(false) }} onDrop={handleDrop}>
      {isDragging ? <div className="composer-drop-overlay">松开以上传附件</div> : null}
      <AttachmentChips attachments={attachments} onDelete={attachmentProps?.onDelete} />
      <AttachmentPopover {...attachmentProps} open={attachmentOpen} onClose={() => setAttachmentOpen(false)} />
      <form className="chat-input-form" aria-label="发送消息" onSubmit={onSubmit}>
        <textarea ref={textareaRef} className="chat-input" placeholder={placeholder} rows="1" value={message} onChange={(event) => onMessageChange(event.target.value)} onKeyDown={handleKeyDown} onPaste={handlePaste} />
        <button className="progress-update-button" type="submit" name="action" value="update_progress" disabled={progressUpdateDisabled} title="根据最近的学习情况更新长期进度"><Icon name="check" size={14} /><span>更新进度</span></button>
        {isSending && onStopStreaming ? <button className="send-button" type="button" aria-label="停止生成" title="停止生成" onClick={onStopStreaming}>停止</button> : <button className="send-button" type="submit" disabled={disabled} aria-label="发送消息">{isSending ? <span className="send-loader" /> : <Icon name="send" size={17} strokeWidth={1.7} />}</button>}
      </form>
      <div className="composer-options">
        <span className="attachment-control">
          <button className="web-search-toggle attachment-toggle" type="button" aria-label={hasAttachments ? `附件（已选 ${attachments.length} 个）` : '附件'} aria-haspopup="dialog" aria-expanded={attachmentOpen} title="上传附件（支持 PDF、Word、Excel、PPT、文本、Markdown、代码、CSV、JSON，仅在本次会话有效）" disabled={attachmentProps?.disabled} onClick={() => { if (!hasAttachments) fileInputRef.current?.click(); else setAttachmentOpen((value) => !value) }}><Icon name="paperclip" size={14} /><span>附件</span>{hasAttachments ? <b className="pill-badge">{attachments.length}</b> : null}</button>
          <input ref={fileInputRef} className="attachment-file-input" type="file" accept={SUPPORTED_ATTACHMENT_ACCEPT} onChange={async (event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) await attachmentProps?.onUpload?.(file) }} />
        </span>
        <ModeControl kind="联网搜索" mode={webSearchMode} onChange={onWebSearchModeChange} disabled={isSending} />
        <ModeControl kind="RAG 检索" mode={ragMode} onChange={onRagModeChange} disabled={isSending} />
        {onStreamingEnabledChange ? <button className={`streaming-toggle${streamingEnabled ? ' is-active' : ''}`} type="button" aria-pressed={streamingEnabled} disabled={isSending} onClick={() => onStreamingEnabledChange(!streamingEnabled)} title={streamingEnabled ? '流式输出已开启' : '流式输出已关闭'}><Icon name="sparkles" size={14} strokeWidth={1.7} /><span>流式</span></button> : null}
      </div>
      <p className="composer-hint">Enter 发送 · Shift + Enter 换行 · AI 可能出错，重要信息请再核对</p>
      {notice ? <p className="composer-notice" role="alert">{notice}</p> : null}
    </div>
  )
}

export default ChatInput

import { useEffect, useRef } from 'react'
import Icon from './Icon.jsx'

function ChatInput({
  message,
  onMessageChange,
  onSubmit,
  disabled = false,
  isSending = false,
  webSearchMode = 'auto',
  onWebSearchModeChange,
  ragMode = 'auto',
  onRagModeChange,
  streamingEnabled = true,
  onStreamingEnabledChange,
  attachmentPanel = null,
  onStopStreaming,
  placeholder = '写下你的问题，或让导师帮你拆解下一步…',
}) {
  const textareaRef = useRef(null)

  const RAG_MODE_ORDER = ['auto', 'force', 'off']
  const RAG_MODE_LABELS = {
    auto: '自动判断',
    force: '本轮强制使用',
    off: '强制关闭',
  }

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [message])

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (!disabled) event.currentTarget.form?.requestSubmit()
    }
  }

  function cycleMode(currentMode) {
    const nextIndex = (RAG_MODE_ORDER.indexOf(currentMode) + 1) % RAG_MODE_ORDER.length
    return RAG_MODE_ORDER[nextIndex]
  }

  function handleRagModeClick() {
    onRagModeChange?.(cycleMode(ragMode))
  }

  function handleWebSearchModeClick() {
    onWebSearchModeChange?.(cycleMode(webSearchMode))
  }

  const ragButtonClass = `web-search-toggle rag-toggle${
    ragMode === 'force' ? ' is-active' : ''
  }${ragMode === 'off' ? ' is-rag-off' : ''}`

  const webSearchButtonClass = `web-search-toggle rag-toggle${
    webSearchMode === 'force' ? ' is-active' : ''
  }${webSearchMode === 'off' ? ' is-rag-off' : ''}`

  return (
    <div className="composer-wrap">
      {attachmentPanel}
      <form className="chat-input-form" aria-label="发送消息" onSubmit={onSubmit}>
        <textarea
          ref={textareaRef}
          className="chat-input"
          placeholder={placeholder}
          rows="1"
          value={message}
          onChange={(event) => onMessageChange(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        {isSending && onStopStreaming ? (
          <button className="send-button" type="button" aria-label="停止生成" title="停止生成" onClick={onStopStreaming}>
            停止
          </button>
        ) : (
          <button className="send-button" type="submit" disabled={disabled} aria-label="发送消息">
            {isSending ? <span className="send-loader" /> : <Icon name="send" size={17} strokeWidth={1.7} />}
          </button>
        )}
      </form>
      <div className="composer-options">
        <button
          className={webSearchButtonClass}
          type="button"
          aria-pressed={webSearchMode === 'force'}
          aria-label={`联网搜索：${RAG_MODE_LABELS[webSearchMode]}`}
          title={`联网搜索：${RAG_MODE_LABELS[webSearchMode]}`}
          disabled={isSending}
          onClick={handleWebSearchModeClick}
        >
          <Icon name="globe" size={14} strokeWidth={1.7} />
          <span>联网搜索</span>
          <small>{RAG_MODE_LABELS[webSearchMode]}</small>
        </button>
        <button
          className={ragButtonClass}
          type="button"
          aria-pressed={ragMode === 'force'}
          aria-label={`RAG 检索：${RAG_MODE_LABELS[ragMode]}`}
          title={`RAG 检索：${RAG_MODE_LABELS[ragMode]}`}
          disabled={isSending}
          onClick={handleRagModeClick}
        >
          <Icon name="file" size={14} strokeWidth={1.7} />
          <span>RAG 检索</span>
          <small>{RAG_MODE_LABELS[ragMode]}</small>
        </button>
        {onStreamingEnabledChange ? (
          <button
            className={`streaming-toggle${streamingEnabled ? ' is-active' : ''}`}
            type="button"
            aria-pressed={streamingEnabled}
            disabled={isSending}
            onClick={() => onStreamingEnabledChange(!streamingEnabled)}
            title={streamingEnabled ? '流式输出已开启' : '流式输出已关闭'}
          >
            <Icon name="sparkles" size={14} strokeWidth={1.7} />
            <span>流式</span>
          </button>
        ) : null}
      </div>
      <p className="composer-hint">Enter 发送 · Shift + Enter 换行 · AI 可能出错，重要信息请再核对</p>
    </div>
  )
}

export default ChatInput

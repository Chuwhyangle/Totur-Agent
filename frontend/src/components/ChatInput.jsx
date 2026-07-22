import { useEffect, useRef } from 'react'
import Icon from './Icon.jsx'

function ChatInput({
  message,
  onMessageChange,
  onSubmit,
  disabled = false,
  isSending = false,
  webSearchEnabled = false,
  onWebSearchEnabledChange,
  placeholder = '写下你的问题，或让导师帮你拆解下一步…',
}) {
  const textareaRef = useRef(null)

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

  return (
    <div className="composer-wrap">
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
        <button className="send-button" type="submit" disabled={disabled} aria-label="发送消息">
          {isSending ? <span className="send-loader" /> : <Icon name="send" size={17} strokeWidth={1.7} />}
        </button>
      </form>
      <div className="composer-options">
        <button
          className={`web-search-toggle${webSearchEnabled ? ' is-active' : ''}`}
          type="button"
          aria-pressed={webSearchEnabled}
          disabled={isSending}
          onClick={() => onWebSearchEnabledChange?.(!webSearchEnabled)}
        >
          <Icon name="globe" size={14} strokeWidth={1.7} />
          <span>联网搜索</span>
          <small>{webSearchEnabled ? '本轮强制使用' : '自动判断'}</small>
        </button>
      </div>
      <p className="composer-hint">Enter 发送 · Shift + Enter 换行 · AI 可能出错，重要信息请再核对</p>
    </div>
  )
}

export default ChatInput

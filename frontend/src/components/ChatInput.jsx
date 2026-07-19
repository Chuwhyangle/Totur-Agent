import Icon from './Icon.jsx'

function ChatInput({
  message,
  onMessageChange,
  onSubmit,
  disabled = false,
  isSending = false,
  placeholder = '向 AI 导师提问，或让它为你制定学习计划…',
}) {
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
          className="chat-input"
          placeholder={placeholder}
          rows="1"
          value={message}
          onChange={(event) => onMessageChange(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button className="send-button" type="submit" disabled={disabled} aria-label="发送消息">
          {isSending ? <span className="send-loader" /> : <Icon name="send" size={18} />}
        </button>
      </form>
      <p className="composer-hint">Enter 发送 · Shift + Enter 换行 · AI 可能会犯错，请核对重要信息</p>
    </div>
  )
}

export default ChatInput

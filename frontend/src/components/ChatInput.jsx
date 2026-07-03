// ChatInput 是受控输入区：输入内容和发送动作都交给 App.jsx 处理。
function ChatInput({
  message,
  onMessageChange,
  onSubmit,
  disabled = false,
  isSending = false,
  placeholder = '输入你想学习的问题...',
}) {
  return (
    <form className="chat-input-form" aria-label="发送消息" onSubmit={onSubmit}>
      <textarea
        className="chat-input"
        placeholder={placeholder}
        rows="2"
        value={message}
        onChange={(event) => onMessageChange(event.target.value)}
      />
      <button className="send-button" type="submit" disabled={disabled}>
        {isSending ? '发送中' : '发送'}
      </button>
    </form>
  )
}

export default ChatInput

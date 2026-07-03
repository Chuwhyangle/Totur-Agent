import DebugDetails from './DebugDetails.jsx'

// ChatMessage 负责显示一条聊天消息，用户消息和 AI 消息共用这个组件。
function ChatMessage({ role, text, reply, debug }) {
  const isAssistant = role === 'assistant'
  const author = isAssistant ? 'Tutor Agent' : 'You'
  const messageClassName = isAssistant
    ? 'message assistant-message'
    : 'message user-message'
  const answer = reply?.answer ?? '暂时没有拿到有效回答。'
  const nextTask = reply?.next_task ?? '请稍后重试，或换一个更具体的问题。'
  const exercise = reply?.exercise ?? '用一句话描述你刚才想问的问题。'
  const checkpoints = Array.isArray(reply?.checkpoints)
    ? reply.checkpoints
    : ['前端没有因为响应字段异常而崩溃']

  return (
    <article className={messageClassName}>
      <span className="message-author">{author}</span>

      {reply ? (
        <div className="structured-reply">
          <p>{answer}</p>

          <section className="reply-section">
            <span className="reply-label">下一步</span>
            <p>{nextTask}</p>
          </section>

          <section className="reply-section">
            <span className="reply-label">小练习</span>
            <p>{exercise}</p>
          </section>

          <section className="reply-section">
            <span className="reply-label">检查点</span>
            <ul className="checkpoint-list">
              {checkpoints.map((checkpoint) => (
                <li key={checkpoint}>{checkpoint}</li>
              ))}
            </ul>
          </section>
        </div>
      ) : (
        <p>{text}</p>
      )}

      {debug ? <DebugDetails data={debug} /> : null}
    </article>
  )
}

export default ChatMessage

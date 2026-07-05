import DebugDetails from './DebugDetails.jsx'

function ToolTraceSummary({ trace }) {
  if (!trace?.used || !Array.isArray(trace.calls) || trace.calls.length === 0) {
    return null
  }

  return (
    <details className="tool-trace-summary">
      <summary>工具调用</summary>
      <div className="tool-trace-list">
        {trace.calls.map((call, index) => (
          <section className="tool-trace-item" key={`${call.name}-${index}`}>
            <div className="tool-trace-header">
              <span className="tool-trace-name">{call.name}</span>
              <span className={call.ok ? 'tool-trace-ok' : 'tool-trace-error'}>
                {call.ok ? 'ok' : call.error || 'error'}
              </span>
            </div>
            <p className="tool-trace-line">
              参数：{JSON.stringify(call.arguments ?? {})}
            </p>
            <p className="tool-trace-line">
              结果：{call.returned_count ?? 0} 条
              {Array.isArray(call.top_titles) && call.top_titles.length > 0
                ? ` · ${call.top_titles.join('、')}`
                : ''}
            </p>
          </section>
        ))}
      </div>
    </details>
  )
}

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
  const toolTrace = debug?.responseBody?.tool_trace

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

      <ToolTraceSummary trace={toolTrace} />

      {debug ? <DebugDetails data={debug} /> : null}
    </article>
  )
}

export default ChatMessage

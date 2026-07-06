import DebugDetails from './DebugDetails.jsx'

function joinValues(values) {
  return Array.isArray(values) && values.length > 0 ? values.join('、') : ''
}

function ToolResultPreview({ items, topTitles }) {
  const previewItems = Array.isArray(items) ? items : []

  if (previewItems.length === 0) {
    return Array.isArray(topTitles) && topTitles.length > 0 ? (
      <p className="tool-trace-line">标题：{topTitles.join('、')}</p>
    ) : null
  }

  return (
    <ol className="tool-result-preview-list">
      {previewItems.map((item, index) => {
        const matchedFields = joinValues(item.matched_fields)
        const coreSkills = joinValues(item.core_skills)
        const keywords = joinValues(item.keywords)
        const interviewFocus = joinValues(item.interview_focus)

        return (
          <li className="tool-result-preview-item" key={`${item.title}-${index}`}>
            <div className="tool-result-preview-title">
              <span>{item.title}</span>
              {item.match_score != null ? (
                <span className="tool-result-score">匹配分 {item.match_score}</span>
              ) : null}
            </div>
            {matchedFields ? (
              <p className="tool-trace-line">命中字段：{matchedFields}</p>
            ) : null}
            {coreSkills ? (
              <p className="tool-trace-line">核心技能：{coreSkills}</p>
            ) : null}
            {keywords ? <p className="tool-trace-line">关键词：{keywords}</p> : null}
            {interviewFocus ? (
              <p className="tool-trace-line">面试重点：{interviewFocus}</p>
            ) : null}
            {item.raw_text_excerpt ? (
              <p className="tool-trace-line">片段：{item.raw_text_excerpt}</p>
            ) : null}
          </li>
        )
      })}
    </ol>
  )
}

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
              <div className="tool-trace-title">
                {call.round != null ? (
                  <span className="tool-trace-round">第 {call.round} 轮</span>
                ) : null}
                <span className="tool-trace-name">{call.name}</span>
              </div>
              <span className={call.ok ? 'tool-trace-ok' : 'tool-trace-error'}>
                {call.ok ? 'ok' : call.error || 'error'}
              </span>
            </div>
            <p className="tool-trace-line">
              参数：{JSON.stringify(call.arguments ?? {})}
            </p>
            <p className="tool-trace-line">
              结果：{call.returned_count ?? 0} 条
            </p>
            <ToolResultPreview
              items={call.result_preview}
              topTitles={call.top_titles}
            />
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

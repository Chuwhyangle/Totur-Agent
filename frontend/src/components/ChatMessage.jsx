import DebugDetails from './DebugDetails.jsx'
import Icon from './Icon.jsx'
import SourceCards from './SourceCards.jsx'
import { sourceCardId } from '../utils/sourceLinks.js'

function AnswerWithCitations({ answer, sources }) {
  const sourceIds = new Set(
    (Array.isArray(sources) ? sources : []).map((source) => String(source?.id ?? '')),
  )
  const parts = String(answer).split(/(\[web_\d+\])/g)

  return parts.map((part, index) => {
    const match = /^\[(web_\d+)\]$/.exec(part)
    if (!match || !sourceIds.has(match[1])) return part

    return (
      <a
        className="source-citation"
        href={`#${sourceCardId(match[1])}`}
        key={`${match[1]}-${index}`}
        aria-label={`查看来源 ${match[1]}`}
      >
        {part}
      </a>
    )
  })
}

function joinValues(values) {
  return Array.isArray(values) && values.length > 0 ? values.join('、') : ''
}

function ToolResultPreview({ items, topTitles }) {
  const previewItems = Array.isArray(items) ? items : []
  if (previewItems.length === 0) {
    return Array.isArray(topTitles) && topTitles.length > 0
      ? <p className="tool-trace-line">标题：{topTitles.join('、')}</p>
      : null
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
              {item.match_score != null ? <span className="tool-result-score">匹配 {item.match_score}</span> : null}
            </div>
            {matchedFields ? <p className="tool-trace-line">命中：{matchedFields}</p> : null}
            {coreSkills ? <p className="tool-trace-line">核心技能：{coreSkills}</p> : null}
            {keywords ? <p className="tool-trace-line">关键词：{keywords}</p> : null}
            {interviewFocus ? <p className="tool-trace-line">面试重点：{interviewFocus}</p> : null}
            {item.raw_text_excerpt ? <p className="tool-trace-line">片段：{item.raw_text_excerpt}</p> : null}
          </li>
        )
      })}
    </ol>
  )
}

function ToolTraceSummary({ trace }) {
  if (!trace?.used || !Array.isArray(trace.calls) || trace.calls.length === 0) return null
  return (
    <details className="tool-trace-summary">
      <summary><Icon name="sparkles" size={15} /> 查看工具调用</summary>
      <div className="tool-trace-list">
        {trace.calls.map((call, index) => (
          <section className="tool-trace-item" key={`${call.name}-${index}`}>
            <div className="tool-trace-header">
              <div className="tool-trace-title">
                {call.round != null ? <span className="tool-trace-round">第 {call.round} 轮</span> : null}
                <span className="tool-trace-name">{call.name}</span>
              </div>
              <span className={call.ok ? 'tool-trace-ok' : 'tool-trace-error'}>{call.ok ? '完成' : call.error || '错误'}</span>
            </div>
            <p className="tool-trace-line">参数：{JSON.stringify(call.arguments ?? {})}</p>
            <p className="tool-trace-line">返回：{call.returned_count ?? 0} 条</p>
            <ToolResultPreview items={call.result_preview} topTitles={call.top_titles} />
          </section>
        ))}
      </div>
    </details>
  )
}

function ChatMessage({ role, text, reply, debug }) {
  const isAssistant = role === 'assistant'
  const answer = reply?.answer ?? '暂时没有拿到有效回答。'
  const nextTask = reply?.next_task ?? '请稍后重试，或换一个更具体的问题。'
  const exercise = reply?.exercise ?? '用一句话描述你刚才想问的问题。'
  const checkpoints = Array.isArray(reply?.checkpoints) ? reply.checkpoints : []
  const sources = Array.isArray(reply?.sources) ? reply.sources : []
  const toolTrace = debug?.responseBody?.tool_trace

  return (
    <article className={`message-row ${isAssistant ? 'assistant-row' : 'user-row'}`}>
      <div className={`message-avatar ${isAssistant ? 'assistant-avatar' : 'user-avatar'}`}>
        {isAssistant ? <Icon name="sparkles" size={17} /> : <Icon name="user" size={17} />}
      </div>
      <div className={`message ${isAssistant ? 'assistant-message' : 'user-message'}`}>
        <div className="message-meta">
          <span className="message-author">{isAssistant ? 'AI 导师' : '你'}</span>
          <span className="message-time">刚刚</span>
        </div>
        {reply ? (
          <div className="structured-reply">
            <p className="answer-text"><AnswerWithCitations answer={answer} sources={sources} /></p>
            <div className="reply-grid">
              <section className="reply-section reply-next">
                <span className="reply-icon"><Icon name="chevron" size={15} /></span>
                <div><span className="reply-label">下一步</span><p>{nextTask}</p></div>
              </section>
              <section className="reply-section reply-exercise">
                <span className="reply-icon"><Icon name="target" size={15} /></span>
                <div><span className="reply-label">小练习</span><p>{exercise}</p></div>
              </section>
            </div>
            {checkpoints.length > 0 ? (
              <section className="checkpoint-section">
                <span className="reply-label">完成检查</span>
                <ul className="checkpoint-list">
                  {checkpoints.map((checkpoint) => <li key={checkpoint}><Icon name="check" size={14} />{checkpoint}</li>)}
                </ul>
              </section>
            ) : null}
            <SourceCards sources={sources} />
          </div>
        ) : <p className="user-text">{text}</p>}
        <ToolTraceSummary trace={toolTrace} />
        {debug ? <DebugDetails data={debug} /> : null}
      </div>
    </article>
  )
}

export default ChatMessage

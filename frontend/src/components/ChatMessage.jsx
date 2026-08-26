import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import DebugDetails from './DebugDetails.jsx'
import Icon from './Icon.jsx'
import SourceCards from './SourceCards.jsx'
import { sourceCardId } from '../utils/sourceLinks.js'

function MarkdownAnswer({ answer, sources }) {
  // 把引用标记 [web_N]/[attachment_N]/[note_N]/[jd_N] 转成 markdown 链接，让 ReactMarkdown 渲染成可点击的 a 标签
  const sourceIds = new Set(
    (Array.isArray(sources) ? sources : []).map((source) => String(source?.id ?? '')),
  )
  const md = String(answer).replace(
    /(\[(web|attachment|note|jd)_\d+\])/g,
    (raw) => {
      const citationId = raw.replace(/^\[|\]$/g, '')
      return sourceIds.has(citationId) ? `[${citationId}](#${sourceCardId(citationId)})` : raw
    },
  )

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => {
          const citation = href?.startsWith('#source-')
            ? { className: 'source-citation', 'aria-label': `查看来源 ${href.slice('#source-'.length)}` }
            : {}
          return <a href={href} {...citation}>{children}</a>
        },
      }}
    >
      {md}
    </ReactMarkdown>
  )
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
                {call.name?.startsWith('mcp_github_') ? (
                  <span className="tool-trace-channel">GitHub MCP · 只读</span>
                ) : null}
              </div>
              <span className={call.ok ? 'tool-trace-ok' : 'tool-trace-error'}>{call.ok ? '完成' : call.error || '错误'}</span>
            </div>
            <p className="tool-trace-line">参数：{JSON.stringify(call.arguments ?? {})}</p>
            {call.returned_count != null ? (
              <p className="tool-trace-line">返回：{call.returned_count} 条</p>
            ) : null}
            <ToolResultPreview items={call.result_preview} topTitles={call.top_titles} />
          </section>
        ))}
      </div>
    </details>
  )
}

function ThinkingSummary({ text, isStreaming = false }) {
  const thinking = typeof text === 'string' ? text.trim() : ''
  if (!thinking) return null

  return (
    <details className="thinking-summary">
      <summary>
        <Icon name="sparkles" size={15} />
        {isStreaming ? '思考中' : '思考过程'}
      </summary>
      <div className="thinking-text">{thinking}</div>
    </details>
  )
}

function formatDuration(milliseconds) {
  if (!Number.isFinite(milliseconds)) return ''
  if (milliseconds < 1000) return `${Math.max(0, Math.round(milliseconds))} ms`
  return `${(milliseconds / 1000).toFixed(1)} s`
}

function ResponseMetrics({ metrics }) {
  if (!metrics) return null
  const items = []
  if (Number.isFinite(metrics.firstTokenLatencyMs)) {
    items.push(`首字 ${formatDuration(metrics.firstTokenLatencyMs)}`)
  }
  if (Number.isFinite(metrics.completionElapsedMs)) {
    items.push(`完成 ${formatDuration(metrics.completionElapsedMs)}`)
  }
  if (Number.isFinite(metrics.tokenCount)) {
    items.push(`${metrics.tokenCount} tokens`)
  }
  if (items.length === 0) return null

  return <div className="response-metrics" aria-label="响应指标">{items.join(' · ')}</div>
}

function ChatMessage({ role, text, reply, debug, thinking, metrics, isStreaming, streamingTool }) {
  const isAssistant = role === 'assistant'
  const rawAnswer = reply?.answer ?? text ?? ''
  const answer = rawAnswer !== '' ? rawAnswer : reply ? '暂时没有拿到有效回答。' : ''
  const sources = Array.isArray(reply?.sources) ? reply.sources : []
  const toolTrace = debug?.responseBody?.tool_trace

  // Streaming state: show partial text with cursor
  const showStreaming = isStreaming && !reply

  return (
    <article className={`message-row ${isAssistant ? 'assistant-row' : 'user-row'}`}>
      <div className={`message-avatar ${isAssistant ? 'assistant-avatar' : 'user-avatar'}`}>
        {isAssistant ? <Icon name="sparkles" size={17} /> : <Icon name="user" size={17} />}
      </div>
      <div className={`message ${isAssistant ? 'assistant-message' : 'user-message'}`}>
        <div className="message-meta">
          <span className="message-author">{isAssistant ? '导师' : '你'}</span>
          <span className="message-time">{showStreaming ? '正在输入...' : '刚刚'}</span>
        </div>
        {showStreaming ? (
          <div className="streaming-reply">
            <ThinkingSummary text={thinking} isStreaming />
            {streamingTool ? (
              <div className="streaming-tool-status">
                <span className="streaming-tool-spinner" />
                <span>
                  {streamingTool.tool === 'model'
                    ? '正在生成回答'
                    : `正在调用 ${streamingTool.tool}...`}
                  {Number.isFinite(streamingTool.elapsedMs)
                    ? ` · ${(streamingTool.elapsedMs / 1000).toFixed(1)}s`
                    : ''}
                </span>
              </div>
            ) : null}
            <div className="answer-text streaming-text">
              <MarkdownAnswer answer={answer} sources={sources} />
              <span className="streaming-cursor">▋</span>
            </div>
            <ResponseMetrics metrics={metrics} />
          </div>
        ) : reply ? (
          <div className="structured-reply">
            <ThinkingSummary text={thinking} />
            <div className="answer-text">
              <MarkdownAnswer answer={answer} sources={sources} />
            </div>
            <SourceCards sources={sources} />
            <ResponseMetrics metrics={metrics} />
          </div>
        ) : <p className="user-text">{text}</p>}
        {!showStreaming && toolTrace ? <ToolTraceSummary trace={toolTrace} /> : null}
        {!showStreaming && debug ? <DebugDetails data={debug} /> : null}
        {!showStreaming ? <div className="message-actions" aria-label="消息操作">
          <button type="button" aria-label="复制消息" title="复制" onClick={() => navigator.clipboard?.writeText(rawAnswer)}><Icon name="copy" size={13} /></button>
          {isAssistant ? <button type="button" aria-label="重新生成" title="重新生成"><Icon name="refresh" size={13} /></button> : null}
        </div> : null}
      </div>
    </article>
  )
}

export default ChatMessage

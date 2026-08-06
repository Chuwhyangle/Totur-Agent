import { safeHttpUrl, sourceCardId } from '../utils/sourceLinks.js'

function sourceTitle(source) {
  return typeof source?.title === 'string' && source.title.trim()
    ? source.title.trim()
    : '未命名来源'
}

function sourceDomain(source, safeUrl) {
  if (source?.domain === 'attachment') return '会话附件'
  if (source?.domain === 'knowledge_note') return '本地知识库'
  if (typeof source?.domain === 'string' && source.domain.trim()) return source.domain.trim()
  return safeUrl ? new URL(safeUrl).hostname : '未知来源'
}

function SourceCardContent({ source, safeUrl }) {
  return (
    <>
      <span className="source-card-copy">
        <strong>{sourceTitle(source)}</strong>
        <span>{sourceDomain(source, safeUrl)}</span>
      </span>
      {safeUrl ? <span className="source-card-arrow" aria-hidden="true">↗</span> : null}
    </>
  )
}

function SourceCards({ sources }) {
  const seenIds = new Set()
  const sourceItems = Array.isArray(sources)
    ? sources.filter((source) => {
        if (!source || typeof source !== 'object' || !source.id) return false
        const sourceId = String(source.id)
        if (seenIds.has(sourceId)) return false
        seenIds.add(sourceId)
        return true
      })
    : []

  if (sourceItems.length === 0) return null

  return (
    <section className="source-section" aria-label="参考来源">
      <span className="reply-label">参考来源</span>
      <ul className="source-card-list">
        {sourceItems.map((source) => {
          const safeUrl = ['attachment', 'knowledge_note'].includes(source.domain)
            ? null
            : safeHttpUrl(source.url)
          const content = <SourceCardContent source={source} safeUrl={safeUrl} />

          return (
            <li className="source-card" id={sourceCardId(source.id)} key={String(source.id)}>
              {safeUrl ? (
                <a href={safeUrl} target="_blank" rel="noopener noreferrer">
                  {content}
                </a>
              ) : (
                <div>{content}</div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

export default SourceCards

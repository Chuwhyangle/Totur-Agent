import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

function safeHref(href) {
  if (!href) return null
  return /^(https?:\/\/|mailto:|#|\/)/i.test(href) ? href : null
}

function ArtifactPreview({ artifact, content, loading = false, onClose }) {
  if (!artifact) return null
  return (
    <section className="artifact-preview" aria-label="Artifact 预览">
      <div className="artifact-preview-heading">
        <div><span className="workspace-eyebrow">Markdown Artifact</span><h3>{artifact.title}</h3><small>v{artifact.version_number}</small></div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="关闭 Artifact 预览" title="关闭"><span aria-hidden="true">×</span></button>
      </div>
      {loading ? <p className="workspace-muted">正在读取内容…</p> : (
        <div className="artifact-markdown">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ href, children }) => {
                const nextHref = safeHref(href)
                return nextHref ? <a href={nextHref} target="_blank" rel="noreferrer">{children}</a> : <span>{children}</span>
              },
            }}
          >
            {content || ''}
          </ReactMarkdown>
        </div>
      )}
    </section>
  )
}

export default ArtifactPreview

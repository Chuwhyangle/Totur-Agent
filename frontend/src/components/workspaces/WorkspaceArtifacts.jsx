import Icon from '../Icon.jsx'
import ArtifactPreview from './ArtifactPreview.jsx'

function WorkspaceArtifacts({ artifacts = [], loading = false, error = '', selectedArtifact, content, contentLoading = false, onSelect, onClosePreview, onDownload }) {
  return (
    <section className="workspace-section" aria-label="Workspace Artifacts">
      <div className="workspace-section-heading"><div><span className="workspace-eyebrow">Outputs</span><h2>Artifacts</h2></div></div>
      {loading && artifacts.length === 0 ? <p className="workspace-muted">正在读取 Artifacts…</p> : null}
      {error ? <p className="workspace-error" role="alert">{error}</p> : null}
      {!loading && artifacts.length === 0 && !error ? <p className="workspace-empty">创建 Markdown 报告后会显示在这里。</p> : null}
      {artifacts.length > 0 ? (
        <ul className="workspace-artifact-list">
          {artifacts.map((artifact) => (
            <li key={artifact.id} className={selectedArtifact?.id === artifact.id ? 'workspace-artifact-item workspace-artifact-item-active' : 'workspace-artifact-item'}>
              <button type="button" className="workspace-artifact-select" onClick={() => onSelect?.(artifact)}>
                <span className="workspace-file-icon"><Icon name="file" size={15} /></span>
                <span className="workspace-list-copy"><strong>{artifact.title}</strong><small>v{artifact.version_number} · {artifact.status} · {artifact.sources?.length ?? 0} 个来源</small></span>
              </button>
              <button type="button" className="icon-button" onClick={() => onDownload?.(artifact)} aria-label={`下载 ${artifact.title}`} title="下载"><Icon name="download" size={14} /></button>
            </li>
          ))}
        </ul>
      ) : null}
      <ArtifactPreview artifact={selectedArtifact} content={content} loading={contentLoading} onClose={onClosePreview} />
    </section>
  )
}

export default WorkspaceArtifacts

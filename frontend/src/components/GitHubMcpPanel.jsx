import Icon from './Icon.jsx'

const STATUS_COPY = {
  connected: '已连接',
  degraded: '部分可用',
  unavailable: '暂不可用',
  empty: '未发现工具',
  disabled: '未启用',
  not_configured: '未配置',
  configuration_error: '配置错误',
}

function statusLabel(status) {
  return STATUS_COPY[status] ?? (status === 'loading' ? '读取中' : '等待检查')
}

function statusClass(status) {
  if (status === 'connected') return 'is-connected'
  if (status === 'degraded') return 'is-warning'
  if (status === 'loading') return 'is-loading'
  return 'is-error'
}

export default function GitHubMcpPanel({
  open = false,
  data = null,
  status = 'idle',
  error = '',
  onRefresh,
  onClose,
}) {
  if (!open) return null

  const panelStatus = status === 'loading' ? 'loading' : data?.status ?? status
  const projects = Array.isArray(data?.projects) ? data.projects : []
  const tools = Array.isArray(data?.tools) ? data.tools : []

  return (
    <>
      <button className="drawer-scrim github-mcp-scrim" type="button" aria-label="关闭 GitHub MCP 面板" onClick={onClose} />
      <aside className="github-mcp-panel" role="dialog" aria-modal="true" aria-label="GitHub MCP">
        <header className="github-mcp-header">
          <div className="github-mcp-title-wrap">
            <span className="github-mcp-mark"><Icon name="file-code" size={19} /></span>
            <div>
              <span className="workspace-eyebrow">READ-ONLY TOOL</span>
              <h2>GitHub MCP</h2>
              <p>让 Agent 读取已 Push 的仓库代码。</p>
            </div>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭 GitHub MCP" title="关闭">
            <Icon name="close" size={17} />
          </button>
        </header>

        <section className="github-mcp-status-card" data-status={panelStatus}>
          <div className="github-mcp-status-heading">
            <span className={`github-mcp-status-dot ${statusClass(panelStatus)}`} />
            <strong>{statusLabel(panelStatus)}</strong>
            <button className="icon-button" type="button" onClick={() => onRefresh?.()} disabled={status === 'loading'} aria-label="刷新 GitHub MCP 状态" title="刷新">
              <Icon name="refresh" size={14} />
            </button>
          </div>
          <p>
            {data?.enabled
              ? `${data.server_name || 'GitHub'} · ${data.transport || 'Hosted MCP'} · 只读`
              : '后端未启用 GitHub MCP，聊天 Agent 不会调用远程工具。'}
          </p>
          {error || data?.error ? <small className="github-mcp-error">{error || data.error}</small> : null}
        </section>

        <section className="github-mcp-section">
          <div className="github-mcp-section-heading">
            <div>
              <span className="workspace-eyebrow">PROJECTS</span>
              <h3>挂载项目</h3>
            </div>
            <span className="github-mcp-count">{projects.length}</span>
          </div>
          <p className="github-mcp-muted">这里显示部署明确声明的仓库，不会暴露 PAT 的权限范围。</p>
          {projects.length > 0 ? (
            <ul className="github-mcp-project-list">
              {projects.map((project) => (
                <li key={project.full_name} className="github-mcp-project">
                  <span className="github-mcp-project-icon"><Icon name="file-code" size={16} /></span>
                  <div className="github-mcp-project-copy">
                    <strong>{project.name || project.full_name}</strong>
                    <small>{project.full_name}</small>
                  </div>
                  <a href={project.url} target="_blank" rel="noreferrer" aria-label={`打开 ${project.full_name}`} title="在 GitHub 打开">
                    <Icon name="chevron" size={15} />
                  </a>
                </li>
              ))}
            </ul>
          ) : <p className="github-mcp-empty">暂未声明项目。</p>}
        </section>

        <section className="github-mcp-section">
          <div className="github-mcp-section-heading">
            <div>
              <span className="workspace-eyebrow">TOOLS</span>
              <h3>只读工具</h3>
            </div>
            <span className="github-mcp-count">{data?.tool_count ?? tools.length}</span>
          </div>
          {tools.length > 0 ? (
            <ul className="github-mcp-tool-list">
              {tools.map((tool) => <li key={tool}><Icon name="check" size={13} />{tool.replace(/^mcp_github_/, '')}</li>)}
            </ul>
          ) : <p className="github-mcp-empty">连接成功后会显示可用工具。</p>}
        </section>
      </aside>
    </>
  )
}


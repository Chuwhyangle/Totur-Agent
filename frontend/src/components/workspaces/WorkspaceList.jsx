import Icon from '../Icon.jsx'

function WorkspaceList({
  userId,
  workspaces = [],
  selectedWorkspaceId,
  onSelect,
  onCreate,
  onArchive,
  onRestore,
  disabled = false,
}) {
  return (
    <section className="workspace-section" aria-label="Workspace 列表">
      <div className="workspace-section-heading">
        <div>
          <span className="workspace-eyebrow">Workspace</span>
          <h2>项目空间</h2>
        </div>
        <button className="icon-button" type="button" disabled={disabled || !userId.trim()} onClick={onCreate} aria-label="创建 Workspace" title="创建 Workspace">
          <Icon name="plus" size={16} />
        </button>
      </div>
      {workspaces.length === 0 ? <p className="workspace-empty">还没有 Workspace。</p> : (
        <ul className="workspace-list">
          {workspaces.map((workspace) => {
            const isSelected = workspace.id === selectedWorkspaceId
            const isArchived = workspace.status === 'ARCHIVED'
            return (
              <li key={workspace.id}>
                <div className={isSelected ? 'workspace-list-item workspace-list-item-active' : 'workspace-list-item'}>
                  <button type="button" className="workspace-select-button" onClick={() => onSelect(workspace.id)}>
                    <span className="workspace-status-dot" data-status={workspace.status} />
                    <span className="workspace-list-copy">
                      <strong>{workspace.name}</strong>
                      <small>{isArchived ? '已归档' : workspace.description || '活跃 Workspace'}</small>
                    </span>
                  </button>
                  <button
                    className="icon-button workspace-list-action"
                    type="button"
                    disabled={disabled}
                    onClick={() => (isArchived ? onRestore(workspace.id) : onArchive(workspace.id))}
                    aria-label={isArchived ? `恢复 ${workspace.name}` : `归档 ${workspace.name}`}
                    title={isArchived ? '恢复 Workspace' : '归档 Workspace'}
                  >
                    <Icon name={isArchived ? 'refresh' : 'archive'} size={14} />
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

export default WorkspaceList

import { useState } from 'react'

import Icon from '../Icon.jsx'

function WorkspaceRail({
  workspaces = [],
  selectedWorkspaceId,
  onSelect,
  onCreate,
  onArchive,
  onRestore,
  onOpenDetail,
}) {
  const [menuId, setMenuId] = useState(null)
  const [showAll, setShowAll] = useState(false)
  const visibleWorkspaces = showAll ? workspaces : workspaces.slice(0, 5)

  return (
    <section className="workspace-rail" aria-label="工作区">
      <div className="workspace-rail-heading">
        <span>工作区</span>
        <span className="workspace-rail-actions">
          <button className="icon-button" type="button" onClick={onCreate} aria-label="创建 Workspace" title="新建工作区">
            <Icon name="plus" size={14} />
          </button>
          <button className="icon-button" type="button" onClick={() => setShowAll((value) => !value)} aria-label={showAll ? '收起工作区' : '展开工作区'} title={showAll ? '收起' : '展开'}>
            <Icon name="chevron-down" size={14} className={showAll ? 'is-open' : ''} />
          </button>
        </span>
      </div>
      {visibleWorkspaces.length === 0 ? <p className="workspace-rail-empty">暂无工作区</p> : (
        <ul className="workspace-rail-list">
          {visibleWorkspaces.map((workspace) => {
            const archived = workspace.status === 'ARCHIVED'
            const selected = workspace.id === selectedWorkspaceId
            return (
              <li key={workspace.id} className={`workspace-rail-item${selected ? ' is-selected' : ''}`}>
                <button className="workspace-rail-select" type="button" onClick={() => onSelect?.(workspace.id)} title={workspace.name}>
                  <span className="workspace-status-dot" data-status={workspace.status} />
                  <span className="workspace-rail-name">{workspace.name}</span>
                  <span className="workspace-rail-count">{workspace.session_count ?? 0}</span>
                </button>
                <button className="workspace-rail-menu-button" type="button" onClick={() => setMenuId((current) => current === workspace.id ? null : workspace.id)} aria-label={`${workspace.name} 更多操作`} title="更多操作">
                  <span aria-hidden="true">⋯</span>
                </button>
                {menuId === workspace.id ? (
                  <div className="workspace-rail-popover" role="menu">
                    <button type="button" role="menuitem" onClick={() => { onOpenDetail?.(workspace.id); setMenuId(null) }}>打开工作台</button>
                    <button type="button" role="menuitem" disabled={archived} onClick={() => { onSelect?.(workspace.id); setMenuId(null) }}>在此开始会话</button>
                    <button type="button" role="menuitem" onClick={() => { (archived ? onRestore : onArchive)?.(workspace.id); setMenuId(null) }}>{archived ? '恢复' : '归档'}</button>
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
      {workspaces.length > 5 ? <button className="workspace-rail-more" type="button" onClick={() => setShowAll((value) => !value)}>{showAll ? '收起' : `显示全部 (${workspaces.length})`}</button> : null}
    </section>
  )
}

export default WorkspaceRail

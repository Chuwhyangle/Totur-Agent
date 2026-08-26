import { useMemo, useState } from 'react'

import Icon from './Icon.jsx'
import UserIdInput from './UserIdInput.jsx'
import WorkspaceRail from './workspaces/WorkspaceRail.jsx'

function formatUpdatedAt(updatedAt) {
  const date = new Date(updatedAt)
  if (Number.isNaN(date.getTime())) return updatedAt
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  return new Intl.DateTimeFormat('zh-CN', sameDay
    ? { hour: '2-digit', minute: '2-digit' }
    : { month: 'numeric', day: 'numeric' }
  ).format(date)
}

export function groupSessionsByRecency(sessions = [], now = new Date()) {
  const startToday = new Date(now)
  startToday.setHours(0, 0, 0, 0)
  const startYesterday = new Date(startToday)
  startYesterday.setDate(startYesterday.getDate() - 1)
  const startWeek = new Date(startToday)
  startWeek.setDate(startWeek.getDate() - 7)
  const groups = { 今天: [], 昨天: [], '近 7 天': [], 更早: [] }
  sessions.forEach((session) => {
    const date = new Date(session.updated_at)
    if (Number.isNaN(date.getTime()) || date < startWeek) groups.更早.push(session)
    else if (date >= startToday) groups.今天.push(session)
    else if (date >= startYesterday) groups.昨天.push(session)
    else groups['近 7 天'].push(session)
  })
  return groups
}

function SessionSidebar({
  userId,
  sessions,
  personas = [],
  workspaces = [],
  selectedWorkspaceId,
  activeSessionId,
  status,
  sessionCreateError = '',
  sessionActionId = null,
  isCreating,
  isSidebarCollapsed = false,
  isMobileOpen = false,
  onToggleCollapsed,
  onCreateSession,
  onRefreshSessions,
  onArchiveSession,
  onRestoreSession,
  onDeleteSession,
  onSelectSession,
  onSelectWorkspace,
  onCreateWorkspace,
  onArchiveWorkspace,
  onRestoreWorkspace,
  onOpenWorkspaceDetail,
  onUserIdChange,
}) {
  const [sessionScope, setSessionScope] = useState('workspace')
  const [menuSessionId, setMenuSessionId] = useState(null)
  const isLoading = status === 'loading'
  const workspaceSessions = useMemo(() => {
    if (sessionScope === 'archived') return sessions.filter((session) => Boolean(session.archived_at))

    const activeSessions = sessions.filter((session) => !session.archived_at)
    if (sessionScope === 'all' || !selectedWorkspaceId) return activeSessions
    return activeSessions.filter((session) => session.workspace_id === selectedWorkspaceId)
  }, [sessions, selectedWorkspaceId, sessionScope])
  const groupedSessions = useMemo(() => groupSessionsByRecency(workspaceSessions), [workspaceSessions])
  const workspaceNames = useMemo(() => new Map(workspaces.map((workspace) => [workspace.id, workspace.name])), [workspaces])
  const workspacesWithCounts = useMemo(() => workspaces.map((workspace) => ({
    ...workspace,
    session_count: workspace.session_count ?? sessions.filter((session) => session.workspace_id === workspace.id && !session.archived_at).length,
  })), [sessions, workspaces])

  function handleSessionAction(action, session) {
    setMenuSessionId(null)
    if (action === 'delete' && !window.confirm(`确认永久删除“${session.title || '未命名会话'}”及其聊天记录吗？此操作无法恢复。`)) return

    const handler = action === 'archive'
      ? onArchiveSession
      : action === 'restore'
        ? onRestoreSession
        : onDeleteSession
    void handler?.(session)
  }

  return (
    <aside className={`session-sidebar${isSidebarCollapsed ? ' is-collapsed' : ''}${isMobileOpen ? ' is-mobile-open' : ''}`} aria-label="会话列表">
      <div className="sidebar-brand-row">
        <div className="brand-block">
          <span className="brand-mark"><Icon name="sparkles" size={18} strokeWidth={1.6} /></span>
          <div><strong>Tutor Agent</strong><span>专注学习 · 清晰推进</span></div>
        </div>
        <button className="icon-button sidebar-collapse-button" type="button" onClick={() => onToggleCollapsed()} aria-label={isSidebarCollapsed ? '展开侧栏' : '收起侧栏'} title={isSidebarCollapsed ? '展开侧栏' : '收起侧栏'}>
          <Icon name={isSidebarCollapsed ? 'chevron' : 'chevron-left'} size={15} />
        </button>
      </div>

      <button className="session-primary-button" type="button" disabled={isCreating || !userId.trim()} onClick={() => onCreateSession()} title="开始新对话">
        <Icon name="plus" size={18} />
        <span>{isCreating ? '创建中…' : '开始新对话'}</span>
      </button>

      <WorkspaceRail
        workspaces={workspacesWithCounts}
        selectedWorkspaceId={selectedWorkspaceId}
        onSelect={onSelectWorkspace}
        onCreateSession={onCreateSession}
        onCreate={onCreateWorkspace}
        onArchive={onArchiveWorkspace}
        onRestore={onRestoreWorkspace}
        onOpenDetail={onOpenWorkspaceDetail}
      />

      <div className="session-list-header">
        <span>会话</span>
        <span className="session-header-controls">
          <select value={sessionScope} onChange={(event) => { setSessionScope(event.target.value); setMenuSessionId(null) }} aria-label="会话范围" title="会话范围">
            <option value="workspace">本工作区</option>
            <option value="all">全部</option>
            <option value="archived">已回档</option>
          </select>
          <button className="icon-button" type="button" disabled={isLoading || !userId.trim()} onClick={() => onRefreshSessions()} aria-label="刷新会话" title="刷新会话">
            <Icon name="refresh" size={14} />
          </button>
        </span>
      </div>

      {status === 'idle' ? <p className="session-empty">刷新后可查看历史会话</p> : null}
      {status === 'loading' ? <div className="session-skeletons"><span /><span /><span /></div> : null}
      {status === 'error' ? <p className="session-error"><strong>会话操作失败</strong>{sessionCreateError ? `：${sessionCreateError}` : ''}</p> : null}
      {status === 'success' && workspaceSessions.length === 0 ? <p className="session-empty">{sessionScope === 'archived' ? '还没有回档的会话。' : '还没有会话。从一次清晰的问题开始。'}</p> : null}

      {workspaceSessions.length > 0 ? (
        <div className="session-list">
          {Object.entries(groupedSessions).map(([group, groupSessions]) => groupSessions.length > 0 ? (
            <section key={group} className="session-group" aria-label={group}>
              <h3 className="session-list-header session-group-heading">{group}</h3>
              <ol>
                {groupSessions.map((session) => {
                  const isActive = session.id === activeSessionId
                  const sessionTitle = session.title || '未命名会话'
                  const isActionPending = sessionActionId === session.id
                  return (
                    <li key={session.id}>
                      <div className="session-row">
                        <button className={isActive ? 'session-item session-item-active' : 'session-item'} type="button" onClick={() => onSelectSession(session)} title={sessionTitle}>
                          <span className="session-persona-dot" title={personas.find((item) => item.persona_id === session.persona_id)?.name ?? '默认导师'} />
                          <span className="session-copy">
                            <span className="session-title">{sessionTitle}</span>
                            {sessionScope === 'all' && session.workspace_id ? <span className="session-workspace-name">{workspaceNames.get(session.workspace_id) || '未命名工作区'}</span> : null}
                          </span>
                          <span className="session-meta">{formatUpdatedAt(session.updated_at)}</span>
                        </button>
                        <button className="session-more" type="button" disabled={isActionPending} onClick={() => setMenuSessionId((current) => current === session.id ? null : session.id)} aria-label={`会话操作 ${sessionTitle}`} title="会话操作">⋯</button>
                        {menuSessionId === session.id ? (
                          <div className="session-actions-popover" role="menu">
                            <button type="button" role="menuitem" disabled={isActionPending} onClick={() => handleSessionAction(session.archived_at ? 'restore' : 'archive', session)}>{session.archived_at ? '恢复' : '回档'}</button>
                            <button type="button" role="menuitem" disabled={isActionPending} onClick={() => handleSessionAction('delete', session)}>删除</button>
                          </div>
                        ) : null}
                      </div>
                    </li>
                  )
                })}
              </ol>
            </section>
          ) : null)}
        </div>
      ) : null}

      <div className="sidebar-footer">
        <span className="user-avatar-mini">{(userId || 'U').slice(0, 1).toUpperCase()}</span>
        <span className="sidebar-user-copy"><UserIdInput userId={userId} onUserIdChange={onUserIdChange} /></span>
        <span className="online-dot" />
      </div>
    </aside>
  )
}

export default SessionSidebar

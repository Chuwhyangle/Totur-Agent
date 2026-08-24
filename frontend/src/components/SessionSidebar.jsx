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
  isCreating,
  isSidebarCollapsed = false,
  onToggleCollapsed,
  onCreateSession,
  onRefreshSessions,
  onSelectSession,
  onSelectWorkspace,
  onCreateWorkspace,
  onArchiveWorkspace,
  onRestoreWorkspace,
  onOpenWorkspaceDetail,
  onUserIdChange,
}) {
  const [sessionScope, setSessionScope] = useState('workspace')
  const isLoading = status === 'loading'
  const workspaceSessions = useMemo(() => {
    if (sessionScope === 'all' || !selectedWorkspaceId) return sessions
    return sessions.filter((session) => session.workspace_id === selectedWorkspaceId)
  }, [sessions, selectedWorkspaceId, sessionScope])
  const groupedSessions = useMemo(() => groupSessionsByRecency(workspaceSessions), [workspaceSessions])
  const workspaceNames = useMemo(() => new Map(workspaces.map((workspace) => [workspace.id, workspace.name])), [workspaces])

  return (
    <aside className={`session-sidebar${isSidebarCollapsed ? ' is-collapsed' : ''}`} aria-label="会话列表">
      <div className="sidebar-brand-row">
        <div className="brand-block">
          <span className="brand-mark"><Icon name="sparkles" size={18} strokeWidth={1.6} /></span>
          <div><strong>Tutor Agent</strong><span>专注学习 · 清晰推进</span></div>
        </div>
        <button className="icon-button sidebar-collapse-button" type="button" onClick={onToggleCollapsed} aria-label={isSidebarCollapsed ? '展开侧栏' : '收起侧栏'} title={isSidebarCollapsed ? '展开侧栏' : '收起侧栏'}>
          <Icon name="chevron" size={15} className={isSidebarCollapsed ? 'is-open' : ''} />
        </button>
      </div>

      <button className="session-primary-button" type="button" disabled={isCreating || !userId.trim()} onClick={onCreateSession} title="开始新对话">
        <Icon name="plus" size={18} />
        <span>{isCreating ? '创建中…' : '开始新对话'}</span>
      </button>

      <WorkspaceRail
        workspaces={workspaces}
        selectedWorkspaceId={selectedWorkspaceId}
        onSelect={onSelectWorkspace}
        onCreate={onCreateWorkspace}
        onArchive={onArchiveWorkspace}
        onRestore={onRestoreWorkspace}
        onOpenDetail={onOpenWorkspaceDetail}
      />

      <div className="session-list-header">
        <span>会话</span>
        <span className="session-header-controls">
          <select value={sessionScope} onChange={(event) => setSessionScope(event.target.value)} aria-label="会话范围" title="会话范围">
            <option value="workspace">本工作区</option>
            <option value="all">全部</option>
          </select>
          <button className="icon-button" type="button" disabled={isLoading || !userId.trim()} onClick={onRefreshSessions} aria-label="刷新会话" title="刷新会话">
            <Icon name="refresh" size={14} />
          </button>
        </span>
      </div>

      {status === 'idle' ? <p className="session-empty">刷新后可查看历史会话</p> : null}
      {status === 'loading' ? <div className="session-skeletons"><span /><span /><span /></div> : null}
      {status === 'error' ? <p className="session-error">会话读取失败，请检查服务连接。</p> : null}
      {status === 'success' && workspaceSessions.length === 0 ? <p className="session-empty">还没有会话。从一次清晰的问题开始。</p> : null}

      {workspaceSessions.length > 0 ? (
        <div className="session-list">
          {Object.entries(groupedSessions).map(([group, groupSessions]) => groupSessions.length > 0 ? (
            <section key={group} className="session-group" aria-label={group}>
              <h3 className="session-list-header session-group-heading">{group}</h3>
              <ol>
                {groupSessions.map((session) => {
                  const isActive = session.id === activeSessionId
                  return (
                    <li key={session.id}>
                      <button className={isActive ? 'session-item session-item-active' : 'session-item'} type="button" onClick={() => onSelectSession(session)} title={session.title || '未命名会话'}>
                        <span className="session-persona-dot" title={personas.find((item) => item.persona_id === session.persona_id)?.name ?? '默认导师'} />
                        <span className="session-copy">
                          <span className="session-title">{session.title || '未命名会话'}</span>
                          {sessionScope === 'all' && session.workspace_id ? <span className="session-workspace-name">{workspaceNames.get(session.workspace_id) || '未命名工作区'}</span> : null}
                        </span>
                        <span className="session-meta">{formatUpdatedAt(session.updated_at)}</span>
                        <span className="session-more" aria-hidden="true">⋯</span>
                      </button>
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

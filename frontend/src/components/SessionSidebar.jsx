import Icon from './Icon.jsx'

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

function getPersonaName(personas, personaId) {
  return personas.find((item) => item.persona_id === personaId)?.name ?? '默认导师'
}

function SessionSidebar({
  userId,
  sessions,
  personas = [],
  activeSessionId,
  status,
  isCreating,
  onCreateSession,
  onRefreshSessions,
  onSelectSession,
}) {
  const isLoading = status === 'loading'
  const hasSessions = sessions.length > 0

  return (
    <aside className="session-sidebar" aria-label="会话列表">
      <button
        className="session-primary-button"
        type="button"
        disabled={isCreating || !userId.trim()}
        onClick={onCreateSession}
      >
        <Icon name="plus" size={18} />
        <span>{isCreating ? '创建中…' : '新建学习对话'}</span>
      </button>

      <div className="session-list-header">
        <span>最近对话</span>
        <button className="icon-button" type="button" disabled={isLoading || !userId.trim()} onClick={onRefreshSessions} aria-label="刷新会话">
          <Icon name="refresh" size={16} />
        </button>
      </div>

      {status === 'idle' ? <p className="session-empty">刷新以读取历史会话</p> : null}
      {status === 'loading' ? <div className="session-skeletons"><span /><span /><span /></div> : null}
      {status === 'error' ? <p className="session-error">会话读取失败，请检查服务连接。</p> : null}
      {status === 'success' && !hasSessions ? <p className="session-empty">暂无历史对话，开始一次新的学习吧。</p> : null}

      {hasSessions ? (
        <ol className="session-list">
          {sessions.map((session) => {
            const isActive = session.id === activeSessionId
            return (
              <li key={session.id}>
                <button className={isActive ? 'session-item session-item-active' : 'session-item'} type="button" onClick={() => onSelectSession(session)}>
                  <span className="session-item-icon"><Icon name="message" size={16} /></span>
                  <span className="session-copy">
                    <span className="session-title">{session.title || '新的学习对话'}</span>
                    <span className="session-persona">{getPersonaName(personas, session.persona_id)}</span>
                  </span>
                  <span className="session-meta">{formatUpdatedAt(session.updated_at)}</span>
                </button>
              </li>
            )
          })}
        </ol>
      ) : null}

      <div className="sidebar-footer">
        <span className="user-avatar-mini">{(userId || 'U').slice(0, 1).toUpperCase()}</span>
        <span className="sidebar-user-copy"><strong>{userId || '未设置用户'}</strong><small>学习档案已同步</small></span>
        <span className="online-dot" />
      </div>
    </aside>
  )
}

export default SessionSidebar

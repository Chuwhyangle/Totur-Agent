function formatUpdatedAt(updatedAt) {
  const date = new Date(updatedAt)

  if (Number.isNaN(date.getTime())) {
    return updatedAt
  }

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function getPersonaName(personas, personaId) {
  const persona = personas.find((item) => item.persona_id === personaId)

  return persona?.name ?? personaId ?? '默认导师'
}

// SessionSidebar 负责显示会话列表，并让用户新建或切换会话。
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
      <div className="session-sidebar-header">
        <div>
          <p className="session-kicker">Sessions</p>
          <h2>会话窗口</h2>
        </div>
        <p className="session-user">当前：{userId || '未填写'}</p>
      </div>

      <div className="session-actions">
        <button
          className="session-primary-button"
          type="button"
          disabled={isCreating || !userId.trim()}
          onClick={onCreateSession}
        >
          {isCreating ? '创建中' : '新建会话'}
        </button>
        <button
          className="session-secondary-button"
          type="button"
          disabled={isLoading || !userId.trim()}
          onClick={onRefreshSessions}
        >
          {isLoading ? '读取中' : '刷新'}
        </button>
      </div>

      {status === 'idle' ? (
        <p className="session-empty">点击“刷新”读取会话，或直接新建会话。</p>
      ) : null}

      {status === 'loading' ? (
        <p className="session-empty">正在读取会话列表...</p>
      ) : null}

      {status === 'error' ? (
        <p className="session-error">会话列表读取失败，请确认后端是否在线。</p>
      ) : null}

      {status === 'success' && !hasSessions ? (
        <p className="session-empty">这个 user_id 暂时还没有会话。</p>
      ) : null}

      {hasSessions ? (
        <ol className="session-list">
          {sessions.map((session) => {
            const isActive = session.id === activeSessionId
            const personaName = getPersonaName(personas, session.persona_id)

            return (
              <li key={session.id}>
                <button
                  className={isActive ? 'session-item session-item-active' : 'session-item'}
                  type="button"
                  onClick={() => onSelectSession(session)}
                >
                  <span className="session-title">{session.title}</span>
                  <span className="session-persona">{personaName}</span>
                  <span className="session-meta">
                    #{session.id} · {formatUpdatedAt(session.updated_at)}
                  </span>
                </button>
              </li>
            )
          })}
        </ol>
      ) : null}
    </aside>
  )
}

export default SessionSidebar

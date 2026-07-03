import DebugDetails from './DebugDetails.jsx'

function formatCreatedAt(createdAt) {
  const date = new Date(createdAt)

  if (Number.isNaN(date.getTime())) {
    return createdAt
  }

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

// ConversationHistory 负责显示当前 user_id 的历史对话列表。
function ConversationHistory({
  userId,
  items,
  status,
  limit,
  onLimitChange,
  onRefresh,
  debug,
}) {
  const isLoading = status === 'loading'
  const hasItems = items.length > 0

  return (
    <aside className="history-panel" aria-label="用户历史记录">
      <div className="history-header">
        <div>
          <p className="history-kicker">History</p>
          <h2>历史记录</h2>
        </div>
        <p className="history-user">当前：{userId || '未填写'}</p>
      </div>

      <div className="history-controls">
        <label className="history-limit-field">
          <span>条数</span>
          <input
            type="number"
            min="1"
            max="100"
            value={limit}
            onChange={(event) => onLimitChange(event.target.value)}
            aria-label="历史记录条数"
          />
        </label>
        <button
          className="history-refresh-button"
          type="button"
          disabled={isLoading}
          onClick={() => onRefresh()}
        >
          {isLoading ? '读取中' : '查看历史'}
        </button>
      </div>

      {status === 'idle' ? (
        <p className="history-empty">点击“查看历史”，读取当前用户最近的对话。</p>
      ) : null}

      {status === 'loading' ? (
        <p className="history-empty">正在从后端读取历史记录...</p>
      ) : null}

      {status === 'error' ? (
        <p className="history-error">历史记录读取失败，请确认后端是否在线。</p>
      ) : null}

      {status === 'success' && !hasItems ? (
        <p className="history-empty">这个 user_id 暂时没有历史记录。</p>
      ) : null}

      {hasItems ? (
        <ol className="history-list">
          {items.map((item) => (
            <li className="history-item" key={item.id}>
              <div className="history-item-meta">
                <span>#{item.id}</span>
                <time dateTime={item.created_at}>{formatCreatedAt(item.created_at)}</time>
              </div>
              <p className="history-question">{item.message}</p>
              <p className="history-answer">{item.reply?.answer ?? '没有回答内容'}</p>
            </li>
          ))}
        </ol>
      ) : null}

      {debug ? <DebugDetails title="历史调试详情" data={debug} /> : null}
    </aside>
  )
}

export default ConversationHistory

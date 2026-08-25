import Icon from './Icon.jsx'

const statusText = {
  idle: '前端已启动',
  checking: '连接中',
  online: 'API 在线',
  offline: 'API 离线',
}

// ApiStatus 只负责显示 API 状态，真正的请求逻辑放在 App.jsx。
function ApiStatus({ status = 'idle', onRefresh }) {
  const text = statusText[status] ?? statusText.idle

  return (
    <div className={`api-status api-status-${status}`} aria-label="API 状态">
      <span className="status-dot" />
      <span>{text}</span>
      <button
        className="api-status-refresh"
        type="button"
        aria-label="刷新 API 状态"
        title="刷新 API 状态"
        disabled={status === 'checking'}
        onClick={onRefresh}
      >
        <Icon name="refresh" size={13} />
      </button>
    </div>
  )
}

export default ApiStatus

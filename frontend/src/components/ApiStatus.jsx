const statusText = {
  idle: '前端已启动',
  checking: '连接中',
  online: 'API 在线',
  offline: 'API 离线',
}

// ApiStatus 只负责显示 API 状态，真正的请求逻辑放在 App.jsx。
function ApiStatus({ status = 'idle' }) {
  const text = statusText[status] ?? statusText.idle

  return (
    <div className={`api-status api-status-${status}`} aria-label="API 状态">
      <span className="status-dot" />
      {text}
    </div>
  )
}

export default ApiStatus

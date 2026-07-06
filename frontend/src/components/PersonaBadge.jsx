// PersonaBadge 负责在聊天区顶部展示当前生效的人设。
function PersonaBadge({ persona, status }) {
  const description = status === 'error'
    ? '人设列表读取失败，当前使用默认导师。'
    : persona.description

  return (
    <div className="persona-badge" aria-live="polite">
      <span className="persona-badge-label">当前人设</span>
      <strong className="persona-badge-name">{persona.name}</strong>
      <span className="persona-badge-description">{description}</span>
    </div>
  )
}

export default PersonaBadge

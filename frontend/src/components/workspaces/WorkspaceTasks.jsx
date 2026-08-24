function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function WorkspaceTasks({ tasks = [], loading = false, error = '' }) {
  return (
    <section className="workspace-section" aria-label="Workspace Tasks">
      <div className="workspace-section-heading"><div><span className="workspace-eyebrow">Runs</span><h2>Tasks</h2></div></div>
      {loading && tasks.length === 0 ? <p className="workspace-muted">正在读取 Tasks…</p> : null}
      {error ? <p className="workspace-error" role="alert">{error}</p> : null}
      {!loading && tasks.length === 0 && !error ? <p className="workspace-empty">完成一次 Workspace Agent 操作后会显示 Task。</p> : null}
      {tasks.length > 0 ? (
        <ul className="workspace-task-list">
          {tasks.map((task) => (
            <li className="workspace-task-item" key={task.id}>
              <div className="workspace-task-heading"><strong>{task.goal}</strong><span className={`workspace-status workspace-status-${String(task.status).toLowerCase()}`}>{task.status}</span></div>
              <div className="workspace-task-meta"><span>{formatDate(task.updated_at)}</span><span>{task.steps?.length ?? 0} Steps</span><span>{task.warning_count ?? 0} Warnings</span></div>
              {task.steps?.length ? <div className="workspace-step-list">{task.steps.map((step) => <div key={step.id} className="workspace-step-row"><span>{step.tool_name}</span><span className={`workspace-step-status workspace-step-${String(step.status).toLowerCase()}`}>{step.status}</span>{step.error_code ? <small>{step.error_code}</small> : null}</div>)}</div> : null}
              {task.error_code ? <p className="workspace-item-error">Error: {task.error_code}</p> : null}
              <small className="workspace-trace">Trace ID: {task.trace_id}</small>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}

export default WorkspaceTasks

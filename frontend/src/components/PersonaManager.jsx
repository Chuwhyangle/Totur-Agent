import { useState } from 'react'

import Icon from './Icon.jsx'

const BUILTIN_PERSONA_IDS = new Set(['tutor', 'algorithm_coach', 'interviewer', 'journal'])

function PersonaManager({ userId, personas, onCreate, onUpdate, onDisable, onClose }) {
  const customPersonas = personas.filter((persona) => !BUILTIN_PERSONA_IDS.has(persona.persona_id))
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ name: '', description: '', system_prompt: '' })
  const [error, setError] = useState('')

  function startCreate() {
    setEditing('new')
    setForm({ name: '', description: '', system_prompt: '' })
    setError('')
  }

  function startEdit(persona) {
    setEditing(persona.persona_id)
    setForm({ name: persona.name, description: persona.description, system_prompt: persona.system_prompt || '' })
    setError('')
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    try {
      const payload = { user_id: userId, ...form }
      if (editing === 'new') await onCreate(payload)
      else await onUpdate(editing, payload)
      setEditing(null)
    } catch (cause) {
      setError(cause?.message || '保存失败，请稍后重试。')
    }
  }

  return (
    <>
      <button className="panel-backdrop is-visible" type="button" aria-label="关闭 Persona 管理" onClick={onClose} />
      <aside className="persona-manager-panel" role="dialog" aria-modal="true" aria-label="自定义 Persona">
        <header className="persona-manager-header">
          <div>
            <p className="persona-manager-kicker">Agent Identity</p>
            <h2>{editing ? (editing === 'new' ? '新建 Persona' : '编辑 Persona') : '自定义 Persona'}</h2>
          </div>
          <button className="close-panel-button" type="button" onClick={onClose} aria-label="关闭面板" title="关闭"><Icon name="close" size={17} /></button>
        </header>

        {editing ? (
          <form className="persona-form" onSubmit={submit}>
            <p className="panel-description">定义 Agent 的身份、专长和交流方式。它只影响 Persona，不会改变平台权限。</p>
            <label className="persona-form-field"><span>名称</span><input required maxLength={100} value={form.name} placeholder="例如：后端架构面试官" onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
            <label className="persona-form-field"><span>一句话描述</span><input required maxLength={500} value={form.description} placeholder="例如：追问设计依据与技术取舍" onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
            <label className="persona-form-field"><span>工作提示词</span><textarea required value={form.system_prompt} placeholder="你是谁？擅长什么？应该怎样和用户交流？" onChange={(event) => setForm({ ...form, system_prompt: event.target.value })} rows={10} /></label>
            {error ? <p className="persona-form-error" role="alert">{error}</p> : null}
            <div className="persona-form-actions"><button className="workspace-secondary-button" type="button" onClick={() => setEditing(null)}>返回列表</button><button className="workspace-small-button" type="submit"><Icon name="check" size={14} /> 保存 Persona</button></div>
          </form>
        ) : (
          <>
            <p className="panel-description">把 Agent 的身份和表达方式固定下来，在不同 Workspace 中重复使用。</p>
            <div className="persona-manager-toolbar"><span>{customPersonas.length} 个自定义 Persona</span><button className="workspace-small-button" type="button" onClick={startCreate}><Icon name="plus" size={14} /> 新建</button></div>
            {customPersonas.length > 0 ? (
              <ul className="persona-manager-list">
                {customPersonas.map((persona) => (
                  <li className="persona-manager-item" key={persona.persona_id}>
                    <span className="persona-manager-icon"><Icon name="user" size={16} /></span>
                    <span className="persona-manager-copy"><strong>{persona.name}</strong><small>{persona.description}</small></span>
                    <span className="persona-manager-actions"><button className="icon-button" type="button" onClick={() => startEdit(persona)} aria-label={`编辑 ${persona.name}`} title="编辑"><Icon name="file" size={15} /></button><button className="icon-button persona-disable-button" type="button" onClick={() => onDisable(persona.persona_id)} aria-label={`停用 ${persona.name}`} title="停用"><Icon name="trash" size={15} /></button></span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="persona-manager-empty"><span><Icon name="sparkles" size={19} /></span><strong>还没有自定义 Persona</strong><small>从一个明确的 Agent 身份开始。</small></div>
            )}
          </>
        )}
      </aside>
    </>
  )
}

export default PersonaManager

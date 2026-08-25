import { useEffect, useState } from 'react'

import Icon from './Icon.jsx'

const LEVEL_LABELS = {
  0: '未接触',
  1: '初步理解',
  2: '基础练习',
  3: '基本掌握',
}

const STATUS_LABELS = {
  not_started: '未开始',
  learning: '正在学习',
  needs_practice: '需要巩固',
  mastered: '基本掌握',
}

const EMPTY_FORM = {
  topic: '',
  level: 0,
  status: 'learning',
  evidence: '',
  next_step: '',
}

function LearningProgressPanel({
  open = false,
  userId = '',
  items = [],
  status = 'idle',
  error = '',
  onRefresh,
  onSave,
  onDelete,
  onClose,
}) {
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [formError, setFormError] = useState('')

  useEffect(() => {
    if (!open) return
    setEditingId(null)
    setForm(EMPTY_FORM)
    setFormError('')
  }, [open])

  if (!open) return null

  function startCreate() {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setFormError('')
  }

  function startEdit(item) {
    setEditingId(item.id)
    setForm({
      topic: item.topic,
      level: item.level,
      status: item.status,
      evidence: item.evidence ?? '',
      next_step: item.next_step ?? '',
    })
    setFormError('')
  }

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!form.topic.trim()) {
      setFormError('请填写知识点。')
      return
    }
    setSaving(true)
    setFormError('')
    try {
      await onSave?.({
        ...form,
        topic: form.topic.trim(),
        level: Number(form.level),
        evidence: form.evidence.trim() || null,
        next_step: form.next_step.trim() || null,
      })
      startCreate()
    } catch (saveError) {
      setFormError(saveError?.message || '保存学习进度失败。')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(item) {
    if (!window.confirm(`确认删除“${item.topic}”的学习记录吗？`)) return
    setDeletingId(item.id)
    try {
      await onDelete?.(item)
      if (editingId === item.id) startCreate()
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <>
      <button className="drawer-scrim progress-scrim" type="button" aria-label="关闭学习进度面板" onClick={onClose} />
      <aside className="learning-progress-panel" aria-label="SQL 学习进度面板">
        <header className="learning-progress-header">
          <div>
            <span className="workspace-eyebrow">SQL MEMORY</span>
            <h2>学习进度</h2>
            <p>记录你的掌握情况，帮助 Agent 给出更合适的下一步。</p>
          </div>
          <button className="icon-button" type="button" aria-label="关闭学习进度面板" title="关闭" onClick={onClose}>
            <Icon name="close" size={17} />
          </button>
        </header>

        <div className="learning-progress-toolbar">
          <span>{userId || '未设置用户'} · SQL</span>
          <div>
            <button className="icon-button" type="button" aria-label="刷新学习进度" title="刷新" disabled={status === 'loading'} onClick={() => onRefresh?.()}>
              <Icon name="refresh" size={14} />
            </button>
            <button className="workspace-small-button" type="button" onClick={startCreate}>
              <Icon name="plus" size={14} /> 新增记录
            </button>
          </div>
        </div>

        {error ? <p className="learning-progress-error" role="alert">{error}</p> : null}
        {status === 'loading' ? <p className="learning-progress-empty">正在读取学习记录…</p> : null}
        {status !== 'loading' && items.length === 0 ? (
          <div className="learning-progress-empty">
            <Icon name="target" size={22} />
            <p>还没有 SQL 学习记录。</p>
            <small>可以先手动添加一个知识点，或在聊天中点击“更新进度”。</small>
          </div>
        ) : null}
        {status !== 'loading' && items.length > 0 ? (
          <div className="learning-progress-list">
            {items.map((item) => (
              <article className="learning-progress-card" key={item.id}>
                <div className="learning-progress-card-heading">
                  <div>
                    <strong>{item.topic}</strong>
                    <span className={`learning-progress-status status-${item.status}`}>
                      {STATUS_LABELS[item.status] || item.status}
                    </span>
                  </div>
                  <span className="learning-progress-level">{LEVEL_LABELS[item.level] || `Level ${item.level}`}</span>
                </div>
                {item.evidence ? <p><b>依据：</b>{item.evidence}</p> : null}
                {item.next_step ? <p><b>下一步：</b>{item.next_step}</p> : null}
                <footer>
                  <small>来源：{item.source === 'agent' ? 'Agent' : '手动'} · {formatUpdatedAt(item.updated_at)}</small>
                  <div>
                    <button className="icon-button" type="button" aria-label={`编辑 ${item.topic}`} title="编辑" onClick={() => startEdit(item)}>
                      <Icon name="check" size={14} />
                    </button>
                    <button className="icon-button" type="button" aria-label={`删除 ${item.topic}`} title="删除" disabled={deletingId === item.id} onClick={() => handleDelete(item)}>
                      <Icon name="trash" size={14} />
                    </button>
                  </div>
                </footer>
              </article>
            ))}
          </div>
        ) : null}

        <form className="learning-progress-form" onSubmit={handleSubmit}>
          <div className="learning-progress-form-heading">
            <h3>{editingId === null ? '新增学习记录' : '编辑学习记录'}</h3>
            {editingId !== null ? <button type="button" onClick={startCreate}>取消编辑</button> : null}
          </div>
          <label>
            <span>知识点</span>
            <input value={form.topic} maxLength={120} placeholder="例如：LEFT JOIN" onChange={(event) => updateField('topic', event.target.value)} />
          </label>
          <div className="learning-progress-form-row">
            <label>
              <span>等级</span>
              <select value={form.level} onChange={(event) => updateField('level', event.target.value)}>
                {Object.entries(LEVEL_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>
              <span>状态</span>
              <select value={form.status} onChange={(event) => updateField('status', event.target.value)}>
                {Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
          </div>
          <label>
            <span>学习依据</span>
            <textarea value={form.evidence} maxLength={2000} rows={3} placeholder="我在哪些练习中表现如何？" onChange={(event) => updateField('evidence', event.target.value)} />
          </label>
          <label>
            <span>下一步</span>
            <input value={form.next_step} maxLength={500} placeholder="例如：完成两道多表 JOIN 练习" onChange={(event) => updateField('next_step', event.target.value)} />
          </label>
          {formError ? <p className="learning-progress-form-error" role="alert">{formError}</p> : null}
          <button className="workspace-primary-button" type="submit" disabled={saving || !userId.trim()}>
            <Icon name="check" size={14} /> {saving ? '保存中…' : '保存学习记录'}
          </button>
        </form>
      </aside>
    </>
  )
}

function formatUpdatedAt(value) {
  if (!value) return '刚刚'
  const date = new Date(value.replace(' ', 'T'))
  if (Number.isNaN(date.getTime())) return '刚刚'
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

export default LearningProgressPanel

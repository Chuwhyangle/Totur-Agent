import { useEffect, useState } from 'react'

import Icon from './Icon.jsx'

const aiAgentSample = {
  title: 'AI Agent / LLM 应用开发岗位',
  rawText: `毕业时间：2025年-2026年
基于大语言模型(LLM)开发智能Agent应用，实现自动化任务处理
设计和实现RAG(检索增强生成）系统，提升AI回答的准确性和相关性
使用LangChain、LangGraph等框架构建复杂的AI工作流和多步骤推理链
参与Agent系统的性能评测，建立评估指标和测试体系
优化Agent的推理能力、工具使用能力和多轮对话能力`,
  coreSkills: 'LangChain\nLangGraph\nLLM 应用链路\n多步骤 Agent 工作流',
  preferredSkills: 'RAG\n上下文工程\nAgent 评测',
  keywords: 'LLM\nAgent\nRAG\nLangChain\nFastAPI\nPython',
  interviewFocus: 'Agent 工具调用\nRAG 系统设计\nAgent 评测',
}

const emptyForm = () => ({ title: '', rawText: '', coreSkills: '', preferredSkills: '', keywords: '', interviewFocus: '' })
const splitList = (value) => value.split(/[\n,，]/).map((item) => item.trim()).filter(Boolean)
const formatMetaList = (values) => Array.isArray(values) && values.length > 0 ? values.slice(0, 4).join(' · ') : '暂无技能标签'
const formatFormList = (values) => Array.isArray(values) ? values.join('\n') : ''

function formFromItem(item) {
  return {
    title: item.title ?? '',
    rawText: item.raw_text ?? '',
    coreSkills: formatFormList(item.core_skills),
    preferredSkills: formatFormList(item.preferred_skills),
    keywords: formatFormList(item.keywords),
    interviewFocus: formatFormList(item.interview_focus),
  }
}

function InterviewJDPanel({ userId, items, status, isSaving, onRefresh, onView, onSave, onDelete, isOpen, onClose }) {
  const [form, setForm] = useState(emptyForm())
  const [editingId, setEditingId] = useState(null)
  const [editingItem, setEditingItem] = useState(null)
  const [viewingItem, setViewingItem] = useState(null)
  const [detailLoadingId, setDetailLoadingId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [formError, setFormError] = useState('')
  const trimmedUserId = userId.trim()
  const canSave = trimmedUserId && form.title.trim() && form.rawText.trim() && !isSaving

  useEffect(() => {
    if (!isOpen) return
    setForm(emptyForm())
    setEditingId(null)
    setEditingItem(null)
    setViewingItem(null)
    setFormError('')
  }, [isOpen, trimmedUserId])

  const updateField = (field, value) => setForm((current) => ({ ...current, [field]: value }))

  function startCreate() {
    setEditingId(null)
    setEditingItem(null)
    setViewingItem(null)
    setForm(emptyForm())
    setFormError('')
  }

  function startEdit(item) {
    setEditingId(item.id)
    setEditingItem(item)
    setViewingItem(null)
    setForm(formFromItem(item))
    setFormError('')
  }

  async function handleView(item) {
    setDetailLoadingId(item.id)
    setFormError('')
    try {
      const detail = onView ? await onView(item) : item
      setViewingItem(detail || item)
    } catch (error) {
      setFormError(error?.message || '读取目标岗位详情失败。')
    } finally {
      setDetailLoadingId(null)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!canSave) {
      setFormError('请填写岗位名称和 JD 原文。')
      return
    }

    setFormError('')
    const requestBody = {
      user_id: trimmedUserId,
      title: form.title.trim(),
      role_family: editingItem?.role_family ?? 'ai_agent_engineer',
      seniority: editingItem?.seniority ?? 'graduate',
      target_graduation_years: editingItem?.target_graduation_years ?? ['2025', '2026'],
      raw_text: form.rawText.trim(),
      responsibilities: editingItem?.responsibilities ?? [],
      must_have: editingItem?.must_have ?? [],
      core_skills: splitList(form.coreSkills),
      preferred_skills: splitList(form.preferredSkills),
      bonus_skills: editingItem?.bonus_skills ?? ['FastAPI', 'Docker', 'Git'],
      keywords: splitList(form.keywords),
      interview_focus: splitList(form.interviewFocus),
    }

    try {
      const saved = await onSave?.(requestBody, editingId)
      if (!saved) throw new Error('保存目标岗位失败，请稍后重试。')
      setViewingItem(saved)
      setEditingId(null)
      setEditingItem(null)
      setForm(emptyForm())
    } catch (error) {
      setFormError(error?.message || '保存目标岗位失败，请稍后重试。')
    }
  }

  async function handleDelete(item) {
    if (!window.confirm(`确认删除“${item.title}”吗？删除后无法恢复。`)) return

    setDeletingId(item.id)
    setFormError('')
    try {
      await onDelete?.(item)
      if (editingId === item.id) startCreate()
      if (viewingItem?.id === item.id) setViewingItem(null)
    } catch (error) {
      setFormError(error?.message || '删除目标岗位失败，请稍后重试。')
    } finally {
      setDeletingId(null)
    }
  }

  if (!isOpen) return null

  return (
    <>
      <button className={`panel-backdrop ${isOpen ? 'is-visible' : ''}`} type="button" aria-label="关闭目标岗位面板" onClick={onClose} />
      <aside className={`interview-jd-panel ${isOpen ? 'is-open' : ''}`} aria-label="目标岗位 JD">
        <div className="interview-jd-header">
          <div><p className="interview-jd-kicker">学习目标</p><h2>目标岗位</h2></div>
          <button className="close-panel-button" type="button" onClick={onClose} aria-label="关闭面板">×</button>
        </div>
        <p className="panel-description">保存目标岗位后，导师会围绕能力缺口给出更精准的学习建议与练习。</p>

        <div className="saved-jd-block">
          <div className="saved-jd-title"><span>已保存岗位</span><button type="button" onClick={onRefresh} disabled={status === 'loading'} aria-label="刷新目标岗位"><Icon name="refresh" size={15} /></button></div>
          {status === 'loading' ? <p className="interview-jd-empty">正在读取…</p> : null}
          {status === 'error' ? <p className="interview-jd-error" role="alert">读取失败，请检查服务连接。</p> : null}
          {status === 'success' && items.length === 0 ? <p className="interview-jd-empty">还没有保存目标岗位。</p> : null}
          {items.length > 0 ? (
            <ul className="interview-jd-list">
              {items.map((item) => (
                <li className="interview-jd-item" key={item.id}>
                  <span className="jd-icon"><Icon name="target" size={16} /></span>
                  <span className="interview-jd-item-copy"><strong>{item.title}</strong><small>{formatMetaList(item.keywords)}</small></span>
                  <span className="interview-jd-item-actions">
                    <button className="icon-button" type="button" aria-label={`查看 ${item.title}`} title="查看" disabled={detailLoadingId === item.id} onClick={() => handleView(item)}><Icon name="file-text" size={14} /></button>
                    <button className="icon-button" type="button" aria-label={`编辑 ${item.title}`} title="编辑" onClick={() => startEdit(item)}><Icon name="file" size={14} /></button>
                    <button className="icon-button" type="button" aria-label={`删除 ${item.title}`} title="删除" disabled={deletingId === item.id} onClick={() => handleDelete(item)}><Icon name="trash" size={14} /></button>
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        {viewingItem ? (
          <section className="interview-jd-detail" aria-label={`目标岗位详情 ${viewingItem.title}`}>
            <div className="interview-jd-detail-header">
              <div><span className="interview-jd-detail-kicker">岗位详情</span><h3>{viewingItem.title}</h3></div>
              <button className="workspace-small-button" type="button" onClick={() => startEdit(viewingItem)}><Icon name="file" size={13} /> 编辑</button>
            </div>
            <div className="interview-jd-detail-meta">
              <span>创建于 {formatDate(viewingItem.created_at)}</span>
              <span>更新于 {formatDate(viewingItem.updated_at)}</span>
            </div>
            <div className="interview-jd-detail-section"><strong>JD 原文</strong><p className="interview-jd-raw-text">{viewingItem.raw_text}</p></div>
            {renderDetailLists(viewingItem)}
          </section>
        ) : null}

        {formError ? <p className="interview-jd-form-error" role="alert">{formError}</p> : null}
        <form className="interview-jd-form" onSubmit={handleSubmit}>
          <div className="form-section-title">
            <span>{editingId === null ? '添加新岗位' : '编辑目标岗位'}</span>
            <div className="interview-jd-form-actions">
              {editingId !== null ? <button type="button" onClick={startCreate}>取消编辑</button> : null}
              <button type="button" onClick={() => setForm(aiAgentSample)}>填入示例</button>
            </div>
          </div>
          <label className="interview-jd-field"><span>岗位名称</span><input value={form.title} maxLength={120} onChange={(e) => updateField('title', e.target.value)} placeholder="例如：AI Agent 开发工程师" /></label>
          <label className="interview-jd-field"><span>JD 原文</span><textarea value={form.rawText} onChange={(e) => updateField('rawText', e.target.value)} placeholder="粘贴职位描述和任职要求" rows={6} /></label>
          <details className="advanced-fields">
            <summary>补充结构化信息（可选）</summary>
            <label className="interview-jd-field"><span>核心技能</span><textarea value={form.coreSkills} onChange={(e) => updateField('coreSkills', e.target.value)} placeholder="LangChain、LangGraph" rows={2} /></label>
            <label className="interview-jd-field"><span>优先技能</span><textarea value={form.preferredSkills} onChange={(e) => updateField('preferredSkills', e.target.value)} placeholder="RAG、Agent 评测" rows={2} /></label>
            <label className="interview-jd-field"><span>关键词</span><textarea value={form.keywords} onChange={(e) => updateField('keywords', e.target.value)} placeholder="LLM、Agent、FastAPI" rows={2} /></label>
            <label className="interview-jd-field"><span>面试重点</span><textarea value={form.interviewFocus} onChange={(e) => updateField('interviewFocus', e.target.value)} placeholder="工具调用、系统设计" rows={2} /></label>
          </details>
          <button className="interview-jd-primary-button" type="submit" disabled={!canSave}>{isSaving ? '保存中…' : editingId === null ? '保存目标岗位' : '保存修改'}</button>
        </form>
      </aside>
    </>
  )
}

function renderDetailLists(item) {
  const fields = [
    ['职责', item.responsibilities],
    ['必备技能', item.must_have],
    ['核心技能', item.core_skills],
    ['优先技能', item.preferred_skills],
    ['加分技能', item.bonus_skills],
    ['关键词', item.keywords],
    ['面试重点', item.interview_focus],
  ]

  const visibleFields = fields.filter(([, values]) => Array.isArray(values) && values.length > 0)
  if (visibleFields.length === 0) return null

  return (
    <div className="interview-jd-detail-lists">
      {visibleFields.map(([label, values]) => <div key={label}><strong>{label}</strong><p>{values.join(' · ')}</p></div>)}
    </div>
  )
}

function formatDate(value) {
  if (!value) return '未知'
  const date = new Date(value.replace(' ', 'T'))
  return Number.isNaN(date.getTime()) ? '未知' : date.toLocaleDateString('zh-CN')
}

export default InterviewJDPanel

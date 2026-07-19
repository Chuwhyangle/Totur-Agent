import { useState } from 'react'
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

function InterviewJDPanel({ userId, items, status, isSaving, onRefresh, onSave, isOpen, onClose }) {
  const [form, setForm] = useState(emptyForm())
  const trimmedUserId = userId.trim()
  const canSave = trimmedUserId && form.title.trim() && form.rawText.trim() && !isSaving
  const updateField = (field, value) => setForm((current) => ({ ...current, [field]: value }))

  async function handleSubmit(event) {
    event.preventDefault()
    if (!canSave) return
    const saved = await onSave({
      user_id: trimmedUserId,
      title: form.title.trim(),
      role_family: 'ai_agent_engineer',
      seniority: 'graduate',
      target_graduation_years: ['2025', '2026'],
      raw_text: form.rawText.trim(),
      responsibilities: [], must_have: [],
      core_skills: splitList(form.coreSkills),
      preferred_skills: splitList(form.preferredSkills),
      bonus_skills: ['FastAPI', 'Docker', 'Git'],
      keywords: splitList(form.keywords),
      interview_focus: splitList(form.interviewFocus),
    })
    if (saved) setForm(emptyForm())
  }

  return (
    <>
      <button className={`panel-backdrop ${isOpen ? 'is-visible' : ''}`} type="button" aria-label="关闭目标岗位面板" onClick={onClose} />
      <aside className={`interview-jd-panel ${isOpen ? 'is-open' : ''}`} aria-label="目标岗位 JD">
        <div className="interview-jd-header">
          <div><p className="interview-jd-kicker">学习目标</p><h2>目标岗位 JD</h2></div>
          <button className="close-panel-button" type="button" onClick={onClose} aria-label="关闭面板">×</button>
        </div>
        <p className="panel-description">保存目标岗位后，AI 会围绕能力缺口给出更精准的学习建议。</p>

        <div className="saved-jd-block">
          <div className="saved-jd-title"><span>已保存岗位</span><button type="button" onClick={onRefresh} disabled={status === 'loading'}><Icon name="refresh" size={15} /></button></div>
          {status === 'loading' ? <p className="interview-jd-empty">正在读取…</p> : null}
          {status === 'error' ? <p className="interview-jd-error">读取失败，请检查服务连接。</p> : null}
          {status === 'success' && items.length === 0 ? <p className="interview-jd-empty">还没有保存目标岗位。</p> : null}
          {items.length > 0 ? <ul className="interview-jd-list">{items.map((item) => <li className="interview-jd-item" key={item.id}><span className="jd-icon"><Icon name="target" size={16} /></span><span><strong>{item.title}</strong><small>{formatMetaList(item.keywords)}</small></span></li>)}</ul> : null}
        </div>

        <form className="interview-jd-form" onSubmit={handleSubmit}>
          <div className="form-section-title"><span>添加新岗位</span><button type="button" onClick={() => setForm(aiAgentSample)}>填入示例</button></div>
          <label className="interview-jd-field"><span>岗位名称</span><input value={form.title} onChange={(e) => updateField('title', e.target.value)} placeholder="例如：AI Agent 开发工程师" /></label>
          <label className="interview-jd-field"><span>JD 原文</span><textarea value={form.rawText} onChange={(e) => updateField('rawText', e.target.value)} placeholder="粘贴职位描述和任职要求" rows={6} /></label>
          <details className="advanced-fields">
            <summary>补充结构化信息（可选）</summary>
            <label className="interview-jd-field"><span>核心技能</span><textarea value={form.coreSkills} onChange={(e) => updateField('coreSkills', e.target.value)} placeholder="LangChain、LangGraph" rows={2} /></label>
            <label className="interview-jd-field"><span>优先技能</span><textarea value={form.preferredSkills} onChange={(e) => updateField('preferredSkills', e.target.value)} placeholder="RAG、Agent 评测" rows={2} /></label>
            <label className="interview-jd-field"><span>关键词</span><textarea value={form.keywords} onChange={(e) => updateField('keywords', e.target.value)} placeholder="LLM、Agent、FastAPI" rows={2} /></label>
            <label className="interview-jd-field"><span>面试重点</span><textarea value={form.interviewFocus} onChange={(e) => updateField('interviewFocus', e.target.value)} placeholder="工具调用、系统设计" rows={2} /></label>
          </details>
          <button className="interview-jd-primary-button" type="submit" disabled={!canSave}>{isSaving ? '保存中…' : '保存目标岗位'}</button>
        </form>
      </aside>
    </>
  )
}

export default InterviewJDPanel

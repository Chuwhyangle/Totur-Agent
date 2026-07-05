import { useState } from 'react'

const aiAgentSample = {
  title: 'AI Agent / LLM 应用开发岗位',
  rawText: `毕业时间：2025年-2026年
基于大语言模型(LLM)开发智能Agent应用，实现自动化任务处理
设计和实现RAG(检索增强生成）系统，提升AI回答的准确性和相关性
使用LangChain、LangGraph等框架构建复杂的AI工作流和多步骤推理链
参与Agent系统的性能评测，建立评估指标和测试体系
优化Agent的推理能力、工具使用能力和多轮对话能力
与产品、设计团队协作，将AI能力集成到实际业务场景中
跟踪AI技术发展趋势，探索新技术在Agent开发中的应用
必备技能：Python、数据结构和算法、机器学习基础、数据处理、英语技术文档阅读
核心技术要求：LangChain、LangGraph
优先技能：RAG、Ragflow、上下文工程、Agent评测
技术栈加分项：Transformers、ollama、vllm、FastAPI、Docker、Git、NLP项目、开源项目、技术博客、后端经验`,
  coreSkills: 'LangChain\nLangGraph\nLLM 应用链路\n多步骤 Agent 工作流',
  preferredSkills: 'RAG\nRagflow\n上下文工程\nAgent 评测',
  keywords: 'LLM\nAgent\nRAG\nLangChain\nLangGraph\nFastAPI\nPython',
  interviewFocus: 'Agent 工具调用\nRAG 系统设计\nLangGraph 多步骤工作流\nAgent 评测\nFastAPI 后端落地',
}

function splitList(value) {
  return value
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function emptyForm() {
  return {
    title: '',
    rawText: '',
    coreSkills: '',
    preferredSkills: '',
    keywords: '',
    interviewFocus: '',
  }
}

function formatMetaList(values) {
  if (!Array.isArray(values) || values.length === 0) {
    return '暂无标签'
  }

  return values.slice(0, 4).join(' / ')
}

// InterviewJDPanel 是第一版 JD 表单地基：先保存目标岗位，再让后续工具检索它。
function InterviewJDPanel({
  userId,
  items,
  status,
  isSaving,
  onRefresh,
  onSave,
}) {
  const [form, setForm] = useState(emptyForm())

  const trimmedUserId = userId.trim()
  const canSave =
    trimmedUserId.length > 0 &&
    form.title.trim().length > 0 &&
    form.rawText.trim().length > 0 &&
    !isSaving

  function updateField(field, value) {
    setForm((currentForm) => ({
      ...currentForm,
      [field]: value,
    }))
  }

  function fillSample() {
    setForm(aiAgentSample)
  }

  async function handleSubmit(event) {
    event.preventDefault()

    if (!canSave) {
      return
    }

    const saved = await onSave({
      user_id: trimmedUserId,
      title: form.title.trim(),
      role_family: 'ai_agent_engineer',
      seniority: 'graduate',
      target_graduation_years: ['2025', '2026'],
      raw_text: form.rawText.trim(),
      responsibilities: [],
      must_have: [],
      core_skills: splitList(form.coreSkills),
      preferred_skills: splitList(form.preferredSkills),
      bonus_skills: ['FastAPI', 'Docker', 'Git'],
      keywords: splitList(form.keywords),
      interview_focus: splitList(form.interviewFocus),
    })

    if (saved) {
      setForm(emptyForm())
    }
  }

  return (
    <aside className="interview-jd-panel" aria-label="目标岗位 JD">
      <div className="interview-jd-header">
        <div>
          <p className="interview-jd-kicker">Interview JD</p>
          <h2>目标岗位</h2>
        </div>
        <button
          className="interview-jd-ghost-button"
          type="button"
          onClick={onRefresh}
          disabled={status === 'loading'}
        >
          刷新
        </button>
      </div>

      <form className="interview-jd-form" onSubmit={handleSubmit}>
        <label className="interview-jd-field">
          <span>岗位名称</span>
          <input
            value={form.title}
            onChange={(event) => updateField('title', event.target.value)}
            placeholder="AI Agent / LLM 应用开发岗位"
          />
        </label>

        <label className="interview-jd-field">
          <span>JD 原文</span>
          <textarea
            value={form.rawText}
            onChange={(event) => updateField('rawText', event.target.value)}
            placeholder="粘贴职位描述和任职要求"
            rows={7}
          />
        </label>

        <label className="interview-jd-field">
          <span>核心技能</span>
          <textarea
            value={form.coreSkills}
            onChange={(event) => updateField('coreSkills', event.target.value)}
            placeholder="LangChain&#10;LangGraph"
            rows={3}
          />
        </label>

        <label className="interview-jd-field">
          <span>优先技能</span>
          <textarea
            value={form.preferredSkills}
            onChange={(event) => updateField('preferredSkills', event.target.value)}
            placeholder="RAG&#10;Agent 评测"
            rows={3}
          />
        </label>

        <label className="interview-jd-field">
          <span>关键词</span>
          <textarea
            value={form.keywords}
            onChange={(event) => updateField('keywords', event.target.value)}
            placeholder="LLM&#10;Agent&#10;FastAPI"
            rows={3}
          />
        </label>

        <label className="interview-jd-field">
          <span>面试重点</span>
          <textarea
            value={form.interviewFocus}
            onChange={(event) => updateField('interviewFocus', event.target.value)}
            placeholder="Agent 工具调用&#10;RAG 系统设计"
            rows={3}
          />
        </label>

        <div className="interview-jd-actions">
          <button
            className="interview-jd-secondary-button"
            type="button"
            onClick={fillSample}
          >
            填入 AI Agent JD
          </button>
          <button
            className="interview-jd-primary-button"
            type="submit"
            disabled={!canSave}
          >
            {isSaving ? '保存中' : '保存'}
          </button>
        </div>
      </form>

      <div className="interview-jd-list-block">
        <p className="interview-jd-list-title">已保存</p>
        {status === 'loading' ? (
          <p className="interview-jd-empty">正在读取 JD...</p>
        ) : null}
        {status === 'error' ? (
          <p className="interview-jd-error">JD 读取失败，请确认后端是否在线。</p>
        ) : null}
        {status === 'success' && items.length === 0 ? (
          <p className="interview-jd-empty">还没有保存目标岗位。</p>
        ) : null}
        {items.length > 0 ? (
          <ul className="interview-jd-list">
            {items.map((item) => (
              <li className="interview-jd-item" key={item.id}>
                <span className="interview-jd-item-title">{item.title}</span>
                <span className="interview-jd-item-meta">
                  {formatMetaList(item.keywords)}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </aside>
  )
}

export default InterviewJDPanel

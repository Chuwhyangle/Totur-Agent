import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import InterviewJDPanel from './InterviewJDPanel.jsx'

const item = {
  id: 7,
  user_id: 'alice',
  title: 'AI Agent 工程师',
  role_family: 'ai_agent_engineer',
  seniority: 'graduate',
  target_graduation_years: ['2025', '2026'],
  raw_text: '负责 Agent 应用开发和 RAG 系统设计。',
  responsibilities: [],
  must_have: [],
  core_skills: ['Python', 'FastAPI'],
  preferred_skills: ['RAG'],
  bonus_skills: ['Docker'],
  keywords: ['Agent', 'RAG'],
  interview_focus: ['工具调用'],
  created_at: '2026-08-25T10:00:00Z',
  updated_at: '2026-08-25T10:00:00Z',
}

beforeEach(() => {
  vi.stubGlobal('confirm', vi.fn(() => true))
})

describe('InterviewJDPanel', () => {
  it('loads and displays the full saved JD when viewing it', async () => {
    const user = userEvent.setup()
    const onView = vi.fn().mockResolvedValue(item)
    render(<InterviewJDPanel isOpen userId="alice" items={[item]} status="success" onView={onView} />)

    await user.click(screen.getByRole('button', { name: '查看 AI Agent 工程师' }))

    expect(onView).toHaveBeenCalledWith(item)
    expect(screen.getByText('岗位详情')).not.toBeNull()
    expect(screen.getByText(item.raw_text)).not.toBeNull()
    expect(screen.getByText('Python · FastAPI')).not.toBeNull()
  })

  it('fills the form and saves changes for an existing JD', async () => {
    const user = userEvent.setup()
    const updated = { ...item, title: '高级 AI Agent 工程师' }
    const onSave = vi.fn().mockResolvedValue(updated)
    render(<InterviewJDPanel isOpen userId="alice" items={[item]} status="success" onSave={onSave} />)

    await user.click(screen.getByRole('button', { name: '编辑 AI Agent 工程师' }))
    expect(screen.getByDisplayValue(item.title)).not.toBeNull()
    expect(screen.getByDisplayValue(item.raw_text)).not.toBeNull()

    const titleInput = screen.getByDisplayValue(item.title)
    await user.clear(titleInput)
    await user.type(titleInput, updated.title)
    await user.click(screen.getByRole('button', { name: '保存修改' }))

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      title: updated.title,
      raw_text: item.raw_text,
      responsibilities: item.responsibilities,
      must_have: item.must_have,
      bonus_skills: item.bonus_skills,
    }), item.id)
  })

  it('confirms and deletes a saved JD', async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn().mockResolvedValue(undefined)
    render(<InterviewJDPanel isOpen userId="alice" items={[item]} status="success" onDelete={onDelete} />)

    await user.click(screen.getByRole('button', { name: '删除 AI Agent 工程师' }))

    expect(window.confirm).toHaveBeenCalledWith('确认删除“AI Agent 工程师”吗？删除后无法恢复。')
    expect(onDelete).toHaveBeenCalledWith(item)
  })
})

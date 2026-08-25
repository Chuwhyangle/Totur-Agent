import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LearningProgressPanel from './LearningProgressPanel.jsx'

const item = {
  id: 7,
  user_id: 'alice',
  subject: 'sql',
  topic: 'JOIN',
  level: 1,
  status: 'needs_practice',
  evidence: '容易忘记连接条件',
  next_step: '完成两道 JOIN 练习',
  source: 'agent',
  updated_at: '2026-08-25 12:00:00',
}

beforeEach(() => {
  vi.stubGlobal('confirm', vi.fn(() => true))
})

describe('LearningProgressPanel', () => {
  it('shows saved progress and opens an edit form', async () => {
    const user = userEvent.setup()
    render(<LearningProgressPanel open userId="alice" items={[item]} />)

    expect(screen.getByText('JOIN')).not.toBeNull()
    const card = screen.getByText('JOIN').closest('article')
    expect(within(card).getByText('需要巩固')).not.toBeNull()
    expect(within(card).getByText('容易忘记连接条件')).not.toBeNull()

    await user.click(screen.getByRole('button', { name: '编辑 JOIN' }))
    expect(screen.getByDisplayValue('JOIN')).not.toBeNull()
    expect(screen.getByDisplayValue('容易忘记连接条件')).not.toBeNull()
    expect(screen.getByText('编辑学习记录')).not.toBeNull()
  })

  it('saves a new progress record and deletes an existing record', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn().mockResolvedValue(item)
    const onDelete = vi.fn().mockResolvedValue(undefined)
    render(<LearningProgressPanel open userId="alice" items={[item]} onSave={onSave} onDelete={onDelete} />)

    await user.click(screen.getByRole('button', { name: '新增记录' }))
    await user.type(screen.getByPlaceholderText('例如：LEFT JOIN'), 'GROUP BY')
    await user.type(screen.getByPlaceholderText('我在哪些练习中表现如何？'), '能完成基础分组题')
    await user.click(screen.getByRole('button', { name: '保存学习记录' }))

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      topic: 'GROUP BY',
      level: 0,
      status: 'learning',
      evidence: '能完成基础分组题',
    }))

    await user.click(screen.getByRole('button', { name: '删除 JOIN' }))
    expect(onDelete).toHaveBeenCalledWith(item)
  })
})

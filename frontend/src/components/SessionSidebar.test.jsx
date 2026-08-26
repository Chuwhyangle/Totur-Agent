import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import SessionSidebar from './SessionSidebar.jsx'

const activeSession = {
  id: 1,
  title: '正在学习 FastAPI',
  persona_id: 'tutor',
  updated_at: '2026-07-26T00:00:00Z',
  archived_at: null,
  workspace_id: null,
}

const archivedSession = {
  id: 2,
  title: '已回档的旧会话',
  persona_id: 'tutor',
  updated_at: '2026-07-25T00:00:00Z',
  archived_at: '2026-07-27T00:00:00Z',
  workspace_id: null,
}

function renderSidebar(overrides = {}) {
  return render(
    <SessionSidebar
      userId="alice"
      sessions={[activeSession, archivedSession]}
      personas={[]}
      workspaces={[]}
      status="success"
      isCreating={false}
      onToggleCollapsed={vi.fn()}
      onCreateSession={vi.fn()}
      onRefreshSessions={vi.fn()}
      onSelectSession={vi.fn()}
      onSelectWorkspace={vi.fn()}
      onCreateWorkspace={vi.fn()}
      onUserIdChange={vi.fn()}
      {...overrides}
    />,
  )
}

beforeEach(() => {
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('SessionSidebar session lifecycle actions', () => {
  it('hides archived sessions by default and archives from the session menu', async () => {
    const user = userEvent.setup()
    const onArchiveSession = vi.fn()
    renderSidebar({ onArchiveSession })

    expect(screen.getByText(activeSession.title)).not.toBeNull()
    expect(screen.queryByText(archivedSession.title)).toBeNull()

    await user.click(screen.getByRole('button', { name: `会话操作 ${activeSession.title}` }))
    await user.click(screen.getByRole('menuitem', { name: '回档' }))

    expect(onArchiveSession).toHaveBeenCalledWith(activeSession)
  })

  it('shows archived sessions and restores them or permanently deletes them', async () => {
    const user = userEvent.setup()
    const onRestoreSession = vi.fn()
    const onDeleteSession = vi.fn()
    renderSidebar({ onRestoreSession, onDeleteSession })

    await user.selectOptions(screen.getByLabelText('会话范围'), 'archived')
    expect(screen.getByText(archivedSession.title)).not.toBeNull()
    expect(screen.queryByText(activeSession.title)).toBeNull()

    await user.click(screen.getByRole('button', { name: `会话操作 ${archivedSession.title}` }))
    await user.click(screen.getByRole('menuitem', { name: '恢复' }))
    expect(onRestoreSession).toHaveBeenCalledWith(archivedSession)

    await user.click(screen.getByRole('button', { name: `会话操作 ${archivedSession.title}` }))
    await user.click(screen.getByRole('menuitem', { name: '删除' }))
    expect(window.confirm).toHaveBeenCalledWith(`确认永久删除“${archivedSession.title}”及其聊天记录吗？此操作无法恢复。`)
    expect(onDeleteSession).toHaveBeenCalledWith(archivedSession)
  })
})

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import WorkspaceRail from './WorkspaceRail.jsx'

describe('WorkspaceRail', () => {
  it('starts a session from the workspace action menu', async () => {
    const user = userEvent.setup()
    const onCreateSession = vi.fn()
    const onSelect = vi.fn()

    render(<WorkspaceRail
      workspaces={[{ id: 'w1', name: 'Agent Project', status: 'ACTIVE', session_count: 0 }]}
      selectedWorkspaceId="w1"
      onSelect={onSelect}
      onCreateSession={onCreateSession}
    />)

    await user.click(screen.getByRole('button', { name: 'Agent Project 更多操作' }))
    await user.click(screen.getByRole('menuitem', { name: '在此开始会话' }))

    expect(onCreateSession).toHaveBeenCalledWith('w1')
    expect(onSelect).not.toHaveBeenCalled()
  })
})

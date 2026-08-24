import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import WorkspacePanel from './WorkspacePanel.jsx'

describe('WorkspacePanel', () => {
  it('creates a session from the selected Workspace', async () => {
    const user = userEvent.setup()
    const onCreateSession = vi.fn()
    render(<WorkspacePanel
      open
      featureStatus="available"
      userId="alice"
      workspaces={[{ id: 'w1', name: 'Agent Project', status: 'ACTIVE' }]}
      selectedWorkspaceId="w1"
      selectedWorkspace={{ id: 'w1', name: 'Agent Project', status: 'ACTIVE' }}
      assets={[]}
      tasks={[]}
      artifacts={[]}
      onCreateSession={onCreateSession}
      onSelectWorkspace={vi.fn()}
    />)

    await user.click(screen.getByRole('button', { name: /在此 Workspace 开始会话/ }))
    expect(onCreateSession).toHaveBeenCalledWith('w1')
  })
})

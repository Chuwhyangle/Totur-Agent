import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import WorkspaceArtifacts from './WorkspaceArtifacts.jsx'

describe('WorkspaceArtifacts', () => {
  it('renders Markdown safely and blocks javascript links', () => {
    render(<WorkspaceArtifacts
      artifacts={[{ id: 'art-1', title: 'Report', version_number: 1, status: 'READY', sources: [] }]}
      selectedArtifact={{ id: 'art-1', title: 'Report', version_number: 1 }}
      content={'# Report\n\n[bad](javascript:alert(1))\n\n- item'}
    />)

    expect(screen.getAllByRole('heading', { name: 'Report' }).length).toBe(2)
    expect(screen.getByText('item')).toBeTruthy()
    expect(screen.queryByRole('link')).toBeNull()
  })
})

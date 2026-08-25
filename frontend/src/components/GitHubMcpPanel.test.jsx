import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import GitHubMcpPanel from './GitHubMcpPanel.jsx'

const connectedData = {
  enabled: true,
  status: 'connected',
  server_name: 'github',
  transport: 'streamable-http',
  readonly: true,
  projects: [
    {
      full_name: 'Chuwhyangle/Totur-Agent',
      name: 'Totur-Agent',
      url: 'https://github.com/Chuwhyangle/Totur-Agent',
    },
  ],
  tool_count: 2,
  tools: ['mcp_github_search_code', 'mcp_github_get_file_contents'],
}

describe('GitHubMcpPanel', () => {
  it('shows connection, mounted project, and read-only tools', () => {
    render(<GitHubMcpPanel open data={connectedData} status="ready" onClose={() => {}} />)

    expect(screen.getByRole('dialog', { name: 'GitHub MCP' })).toBeTruthy()
    expect(screen.getByText('已连接')).toBeTruthy()
    expect(screen.getByText('Chuwhyangle/Totur-Agent')).toBeTruthy()
    expect(screen.getByText('search_code')).toBeTruthy()
    expect(screen.getByText('get_file_contents')).toBeTruthy()
    expect(screen.getByText('只读工具')).toBeTruthy()
  })

  it('refreshes and closes the panel', async () => {
    const user = userEvent.setup()
    const onRefresh = vi.fn()
    const onClose = vi.fn()
    render(<GitHubMcpPanel open data={{ ...connectedData, status: 'disabled' }} status="ready" onRefresh={onRefresh} onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: '刷新 GitHub MCP 状态' }))
    await user.click(screen.getByRole('button', { name: '关闭 GitHub MCP' }))

    expect(onRefresh).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('explains when the MCP client is disabled', () => {
    render(<GitHubMcpPanel open data={{ status: 'disabled', enabled: false, projects: [] }} status="ready" onClose={() => {}} />)

    expect(screen.getByText('未启用')).toBeTruthy()
    expect(screen.getByText('后端未启用 GitHub MCP，聊天 Agent 不会调用远程工具。')).toBeTruthy()
  })
})

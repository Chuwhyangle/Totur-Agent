import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import ChatMessage from './ChatMessage.jsx'
import SourceCards from './SourceCards.jsx'

const baseReply = {
  answer: '附件结论 [attachment_1]，网页补充 [web_1]，伪造引用 [attachment_999]。',
  next_task: '继续',
  exercise: '练习',
  checkpoints: [],
  sources: [
    {
      id: 'attachment_1',
      title: 'resume.pdf · 第 2 页',
      url: '',
      domain: 'attachment',
    },
    {
      id: 'web_1',
      title: 'Web source',
      url: 'https://example.com/reference',
      domain: 'example.com',
    },
  ],
}

describe('attachment citations and source cards', () => {
  it('links only citations backed by reply.sources', () => {
    render(<ChatMessage role="assistant" reply={baseReply} />)

    expect(screen.getByRole('link', { name: '查看来源 attachment_1' }).getAttribute('href')).toBe(
      '#source-attachment_1',
    )
    expect(screen.getByRole('link', { name: '查看来源 web_1' }).getAttribute('href')).toBe(
      '#source-web_1',
    )
    expect(screen.queryByRole('link', { name: '查看来源 attachment_999' })).toBeNull()
    expect(screen.getByText(/伪造引用 \[attachment_999\]/)).not.toBeNull()
  })

  it('renders attachment sources without external links and web sources safely', () => {
    render(<SourceCards sources={baseReply.sources} />)

    const attachmentCard = document.getElementById('source-attachment_1')
    const webCard = document.getElementById('source-web_1')
    expect(attachmentCard.querySelector('a')).toBeNull()
    expect(attachmentCard.textContent).toContain('会话附件')
    expect(webCard.querySelector('a').getAttribute('href')).toBe('https://example.com/reference')
  })

  it('does not create links for unsafe source URLs', () => {
    render(<SourceCards sources={[{
      id: 'web_2',
      title: 'Unsafe',
      url: 'javascript:alert(1)',
      domain: '',
    }]} />)

    expect(document.getElementById('source-web_2').querySelector('a')).toBeNull()
  })
})

describe('note citations and knowledge-note source cards', () => {
  const noteReply = {
    answer: '本地笔记引用 [note_1]，伪造的 [note_999] 不应可点击。',
    next_task: 'next',
    exercise: 'exercise',
    checkpoints: [],
    sources: [
      {
        id: 'note_1',
        title: 'docs/backend/fastapi.md · FastAPI 依赖注入',
        url: '',
        domain: 'knowledge_note',
      },
    ],
  }

  it('links only note citations backed by reply.sources', () => {
    render(<ChatMessage role="assistant" reply={noteReply} />)

    expect(screen.getByRole('link', { name: '查看来源 note_1' }).getAttribute('href')).toBe(
      '#source-note_1',
    )
    expect(screen.queryByRole('link', { name: '查看来源 note_999' })).toBeNull()
    expect(screen.getByText(/\[note_999\]/)).not.toBeNull()
  })

  it('renders note cards without external links and labels them as local knowledge base', () => {
    render(<SourceCards sources={noteReply.sources} />)

    const noteCard = document.getElementById('source-note_1')
    expect(noteCard.querySelector('a')).toBeNull()
    expect(noteCard.textContent).toContain('本地知识库')
    expect(noteCard.textContent).toContain('docs/backend/fastapi.md')
    expect(noteCard.textContent).toContain('FastAPI 依赖注入')
  })

  it('renders note, web and attachment cards together', () => {
    render(<SourceCards sources={[
      ...noteReply.sources,
      {
        id: 'web_1',
        title: 'Web source',
        url: 'https://example.com/reference',
        domain: 'example.com',
      },
      {
        id: 'attachment_1',
        title: 'resume.pdf · 第 2 页',
        url: '',
        domain: 'attachment',
      },
    ]} />)

    expect(document.getElementById('source-note_1')).not.toBeNull()
    expect(document.getElementById('source-web_1').querySelector('a').getAttribute('href')).toBe(
      'https://example.com/reference',
    )
    expect(document.getElementById('source-attachment_1').querySelector('a')).toBeNull()
  })
})

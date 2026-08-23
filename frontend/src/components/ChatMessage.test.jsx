import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import ChatMessage from './ChatMessage.jsx'
import SourceCards from './SourceCards.jsx'

const baseReply = {
  answer: '附件结论 [attachment_1]，网页补充 [web_1]，伪造引用 [attachment_999]。',
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

describe('jd citations and jd source cards', () => {
  const jdReply = {
    answer: '岗位匹配 [jd_1]，伪造的 [jd_9] 不应可点击。',
    sources: [
      {
        id: 'jd_1',
        title: '后端开发 JD',
        url: '',
        domain: 'jd',
      },
    ],
  }

  it('links only jd citations backed by reply.sources', () => {
    render(<ChatMessage role="assistant" reply={jdReply} />)

    expect(screen.getByRole('link', { name: '查看来源 jd_1' }).getAttribute('href')).toBe(
      '#source-jd_1',
    )
    expect(screen.queryByRole('link', { name: '查看来源 jd_9' })).toBeNull()
    expect(screen.getByText(/\[jd_9\]/)).not.toBeNull()
  })

  it('renders a card for a jd source without an external link', () => {
    render(<SourceCards sources={jdReply.sources} />)

    const jdCard = document.getElementById('source-jd_1')
    expect(jdCard).not.toBeNull()
    expect(jdCard.querySelector('a')).toBeNull()
    expect(jdCard.textContent).toContain('后端开发 JD')
  })
})

describe('GFM markdown rendering', () => {
  const markdownReply = {
    answer: [
      '## 标题',
      '',
      '正文段落。',
      '',
      '| 列 A | 列 B |',
      '| --- | --- |',
      '| 1 | 2 |',
      '',
      '- [x] 已完成',
      '- [ ] 未完成',
      '',
      '~~删除线~~',
      '',
      '```python',
      'print("hello")',
      '```',
    ].join('\n'),
    sources: [],
  }

  it('renders tables, task lists, strikethrough and fenced code blocks', () => {
    render(<ChatMessage role="assistant" reply={markdownReply} />)

    expect(screen.getByRole('heading', { name: '标题' })).not.toBeNull()
    const table = screen.getByRole('table')
    expect(table).not.toBeNull()
    expect(table.querySelectorAll('th')[0].textContent).toBe('列 A')
    expect(table.textContent).toContain('2')
    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes).toHaveLength(2)
    expect(checkboxes[0].checked).toBe(true)
    expect(checkboxes[1].checked).toBe(false)
    expect(screen.getByText('已完成')).not.toBeNull()
    expect(screen.getByText('未完成')).not.toBeNull()
    expect(screen.getByText('删除线').tagName).toBe('DEL')
    expect(screen.getByText('print("hello")')).not.toBeNull()
  })
})

describe('markdown container structure', () => {
  it('never nests block markdown elements inside a paragraph', () => {
    const streamingText = [
      '# 标题',
      '',
      '- 列表项',
      '',
      '```js',
      'const x = 1',
      '```',
    ].join('\n')
    render(<ChatMessage role="assistant" isStreaming text={streamingText} />)

    const answerText = document.querySelector('.answer-text')
    expect(answerText).not.toBeNull()
    expect(answerText.tagName).toBe('DIV')

    const heading = screen.getByRole('heading', { name: '标题' })
    expect(heading.closest('p')).toBeNull()
    const listItem = screen.getByText('列表项')
    expect(listItem.closest('p')).toBeNull()
    const codeBlock = screen.getByText(/const x = 1/)
    expect(codeBlock.closest('p')).toBeNull()
  })
})

describe('reply contract', () => {
  it('renders only answer and sources, never legacy structured fields', () => {
    render(<ChatMessage role="assistant" reply={{
      answer: '只有正文。',
      next_task: '继续练习',
      exercise: '写一个接口',
      checkpoints: ['能解释路由'],
      sources: [],
    }} />)

    // 新契约：即使旧字段有内容也只渲染 Markdown 正文与来源
    expect(screen.getByText('只有正文。')).not.toBeNull()
    expect(screen.queryByText('下一步')).toBeNull()
    expect(screen.queryByText('继续练习')).toBeNull()
    expect(screen.queryByText('练习')).toBeNull()
    expect(screen.queryByText('检查点')).toBeNull()
    expect(screen.queryByText('能解释路由')).toBeNull()
  })
})

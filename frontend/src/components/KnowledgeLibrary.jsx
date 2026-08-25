import { useCallback, useEffect, useRef, useState } from 'react'

import Icon from './Icon.jsx'
import {
  deleteKnowledgeDocument,
  getKnowledgeDocuments,
  retryKnowledgeDocument,
  uploadKnowledgeDocument,
} from '../api/tutorApi.js'

const ACCEPTED = ['.pdf', '.md', '.markdown']
const TERMINAL = new Set(['READY', 'FAILED', 'DELETED'])

function formatSize(value) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

export default function KnowledgeLibrary({ userId, onClose }) {
  const [documents, setDocuments] = useState([])
  const [status, setStatus] = useState('idle')
  const [notice, setNotice] = useState('')
  const inputRef = useRef(null)

  const refresh = useCallback(async () => {
    if (!userId?.trim()) return
    setStatus('loading')
    try {
      const { data } = await getKnowledgeDocuments(userId.trim())
      setDocuments(data?.items ?? [])
      setStatus('ready')
    } catch (error) {
      setNotice(error.message || '文档列表读取失败')
      setStatus('error')
    }
  }, [userId])

  useEffect(() => { void refresh() }, [refresh])

  useEffect(() => {
    if (!documents.some((item) => !TERMINAL.has(item.status))) return undefined
    const timer = window.setInterval(() => { void refresh() }, 2000)
    return () => window.clearInterval(timer)
  }, [documents, refresh])

  async function handleUpload(file) {
    const extension = `.${file.name.split('.').pop()?.toLowerCase()}`
    if (!ACCEPTED.includes(extension)) { setNotice('只支持 PDF、Markdown 文件'); return }
    if (file.size > 50 * 1024 * 1024) { setNotice('文件不能超过 50MB'); return }
    const sameName = documents.find((item) => item.original_filename === file.name && item.status !== 'DELETED')
    if (sameName && !window.confirm(`文档库中已有同名文件《${file.name}》,继续上传将替换旧版本`)) return
    try {
      const { data } = await uploadKnowledgeDocument(userId.trim(), file)
      setNotice(data?.duplicate ? '该文件已在文档库中' : '文档已加入处理队列')
      await refresh()
    } catch (error) { setNotice(error.message || '上传失败') }
  }

  async function handleDelete(item) {
    if (!window.confirm(`确认删除《${item.original_filename}》?`)) return
    try { await deleteKnowledgeDocument(item.id, userId.trim()); await refresh() } catch (error) { setNotice(error.message || '删除失败') }
  }

  async function handleRetry(item) {
    try { await retryKnowledgeDocument(item.id, userId.trim()); await refresh() } catch (error) { setNotice(error.message || '重试失败') }
  }

  return (
    <div className="workspace-panel-overlay" role="dialog" aria-label="文档库">
      <section className="workspace-panel">
        <div className="workspace-panel-header"><div><span className="workspace-eyebrow">Knowledge</span><h2>文档库</h2></div><button className="icon-button" type="button" onClick={onClose} aria-label="关闭文档库"><Icon name="x" size={18} /></button></div>
        <div className="workspace-section-heading"><span className="workspace-muted">PDF / Markdown · 最大 50MB</span><button className="workspace-small-button" type="button" onClick={() => inputRef.current?.click()}><Icon name="upload" size={14} /> 上传</button><input ref={inputRef} hidden type="file" accept={ACCEPTED.join(',')} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void handleUpload(file) }} /></div>
        {notice ? <p className="workspace-muted" role="status">{notice}</p> : null}
        {status === 'loading' && documents.length === 0 ? <p className="workspace-muted">正在读取文档…</p> : null}
        {documents.length === 0 && status !== 'loading' ? <p className="workspace-empty">还没有上传文档。</p> : null}
        <ul className="workspace-asset-list">{documents.filter((item) => item.status !== 'DELETED').map((item) => <li className="workspace-asset-item" key={item.id}><div className="workspace-asset-main"><span className="workspace-file-icon"><Icon name="file" size={15} /></span><div className="workspace-list-copy"><strong>{item.original_filename}{item.version_no > 1 ? ` v${item.version_no}` : ''}</strong><small>{formatSize(item.size_bytes)} · {item.page_count ?? '-'} 页 · {item.chunk_count ?? '-'} chunks</small></div></div><span className={`workspace-status workspace-status-${String(item.status).toLowerCase()}`}>{item.status}</span><div className="workspace-item-actions">{item.status === 'FAILED' ? <button className="icon-button" type="button" onClick={() => void handleRetry(item)} aria-label={`重试 ${item.original_filename}`} title="重试"><Icon name="refresh" size={14} /></button> : null}<button className="icon-button" type="button" onClick={() => void handleDelete(item)} aria-label={`删除 ${item.original_filename}`} title="删除"><Icon name="trash" size={14} /></button></div>{item.user_safe_message ? <p className="workspace-item-error">{item.user_safe_message}</p> : null}</li>)}</ul>
      </section>
    </div>
  )
}

import { useRef } from 'react'

import Icon from '../Icon.jsx'

const acceptedTypes = '.pdf,.md,.markdown,.txt,.csv,.json,application/pdf,text/markdown,text/plain,text/csv,application/json'

function formatSize(size) {
  if (!Number.isFinite(Number(size))) return '大小未知'
  const bytes = Number(size)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function WorkspaceAssets({
  assets = [],
  loading = false,
  error = '',
  disabled = false,
  actionStates = {},
  onUpload,
  onRetry,
  onDelete,
  onDownload,
}) {
  const inputRef = useRef(null)

  async function handleFileChange(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) await onUpload?.(file)
  }

  return (
    <section className="workspace-section" aria-label="Workspace Assets">
      <div className="workspace-section-heading">
        <div><span className="workspace-eyebrow">Files</span><h2>Workspace Assets</h2></div>
        <button className="workspace-small-button" type="button" disabled={disabled} onClick={() => inputRef.current?.click()}>
          <Icon name="upload" size={14} /> 上传
        </button>
        <input ref={inputRef} className="workspace-file-input" type="file" accept={acceptedTypes} disabled={disabled} onChange={handleFileChange} />
      </div>
      {loading && assets.length === 0 ? <p className="workspace-muted">正在读取 Assets…</p> : null}
      {error ? <p className="workspace-error" role="alert">{error}</p> : null}
      {!loading && assets.length === 0 && !error ? <p className="workspace-empty">上传 PDF、Markdown、TXT、CSV 或 JSON。</p> : null}
      {assets.length > 0 ? (
        <ul className="workspace-asset-list">
          {assets.map((asset) => {
            const actionState = actionStates[asset.id]
            const isProcessing = ['STAGING', 'PROCESSING', 'DELETING'].includes(asset.status)
            return (
              <li key={asset.id} className="workspace-asset-item">
                <div className="workspace-asset-main">
                  <span className="workspace-file-icon"><Icon name="file" size={15} /></span>
                  <div className="workspace-list-copy">
                    <strong title={asset.original_filename}>{asset.original_filename}</strong>
                    <small>{formatSize(asset.size_bytes)} · {asset.media_type}</small>
                  </div>
                </div>
                <span className={`workspace-status workspace-status-${String(asset.status).toLowerCase()}`}>{asset.status}</span>
                <div className="workspace-item-actions">
                  <button type="button" className="icon-button" disabled={disabled || isProcessing || actionState === 'deleting' || asset.status !== 'READY'} onClick={() => onDownload?.(asset)} aria-label={`下载 ${asset.original_filename}`} title="下载">
                    <Icon name="download" size={14} />
                  </button>
                  {asset.status === 'FAILED' ? <button type="button" className="icon-button" disabled={disabled || Boolean(actionState)} onClick={() => onRetry?.(asset)} aria-label={`重试 ${asset.original_filename}`} title="重试"><Icon name="refresh" size={14} /></button> : null}
                  <button type="button" className="icon-button" disabled={disabled || Boolean(actionState) || isProcessing} onClick={() => onDelete?.(asset)} aria-label={`删除 ${asset.original_filename}`} title="删除"><Icon name="trash" size={14} /></button>
                </div>
                {asset.error_message ? <p className="workspace-item-error">{asset.error_message}</p> : null}
              </li>
            )
          })}
        </ul>
      ) : null}
    </section>
  )
}

export default WorkspaceAssets

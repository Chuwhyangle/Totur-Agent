import { useEffect, useRef, useState } from 'react'

import Icon from '../Icon.jsx'
import WorkspaceArtifacts from './WorkspaceArtifacts.jsx'
import WorkspaceAssets from './WorkspaceAssets.jsx'
import WorkspaceList from './WorkspaceList.jsx'
import WorkspaceTasks from './WorkspaceTasks.jsx'

function WorkspacePanel({
  open,
  featureStatus = 'idle',
  userId,
  workspaces,
  selectedWorkspaceId,
  selectedWorkspace,
  workspaceInstructions = { content: '', version: 0 },
  onSaveInstructions,
  onClearInstructions,
  assets,
  assetsStatus,
  assetsError,
  assetActionStates,
  tasks,
  tasksStatus,
  tasksError,
  artifacts,
  artifactsStatus,
  artifactsError,
  selectedArtifact,
  artifactContent,
  artifactContentLoading,
  onClose,
  onSelectWorkspace,
  onCreateWorkspace,
  onArchiveWorkspace,
  onRestoreWorkspace,
  onCreateSession,
  onUploadAsset,
  onRetryAsset,
  onDeleteAsset,
  onDownloadAsset,
  onSelectArtifact,
  onCloseArtifact,
  onDownloadArtifact,
}) {
  const [isCreating, setIsCreating] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [instructionDraft, setInstructionDraft] = useState('')
  const [instructionSaving, setInstructionSaving] = useState(false)
  const closeButtonRef = useRef(null)
  const triggerRef = useRef(null)

  useEffect(() => {
    if (!instructionSaving) setInstructionDraft(workspaceInstructions.content)
  }, [workspaceInstructions.content, instructionSaving])

  useEffect(() => {
    if (!open) return undefined
    triggerRef.current = document.activeElement
    closeButtonRef.current?.focus()
    function handleEscape(event) {
      if (event.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', handleEscape)
    return () => {
      window.removeEventListener('keydown', handleEscape)
      triggerRef.current?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  async function handleCreate(event) {
    event.preventDefault()
    if (!name.trim()) return
    await onCreateWorkspace({ name: name.trim(), description: description.trim() || null })
    setName('')
    setDescription('')
    setIsCreating(false)
  }

  const archived = selectedWorkspace?.status === 'ARCHIVED'

  async function handleSaveInstructions() {
    setInstructionSaving(true)
    try { await onSaveInstructions?.(instructionDraft) } finally { setInstructionSaving(false) }
  }

  return (
    <>
      <button className="drawer-scrim workspace-scrim" type="button" aria-label="关闭 Workspace 工作台" onClick={onClose} />
      <aside className="workspace-panel" aria-label="Workspace 工作台">
      <div className="workspace-panel-header">
        <div><span className="workspace-eyebrow">Workspace</span><h1>项目工作台</h1></div>
        <button ref={closeButtonRef} className="icon-button" type="button" onClick={onClose} aria-label="关闭 Workspace 工作台" title="关闭"><Icon name="close" size={17} /></button>
      </div>
      {featureStatus === 'error' ? <p className="workspace-error" role="alert">Workspace 功能未启用，普通聊天仍可使用。</p> : null}
      {featureStatus === 'loading' ? <p className="workspace-muted">正在读取 Workspace…</p> : null}
      {featureStatus !== 'error' ? <WorkspaceList userId={userId} workspaces={workspaces} selectedWorkspaceId={selectedWorkspaceId} onSelect={onSelectWorkspace} onCreate={() => setIsCreating(true)} onArchive={onArchiveWorkspace} onRestore={onRestoreWorkspace} /> : null}
      {isCreating ? (
        <form className="workspace-create-form" onSubmit={handleCreate}>
          <label>名称<input value={name} onChange={(event) => setName(event.target.value)} autoFocus /></label>
          <label>描述<input value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          <div className="workspace-form-actions"><button type="button" className="workspace-secondary-button" onClick={() => setIsCreating(false)}>取消</button><button type="submit" className="workspace-small-button" disabled={!name.trim()}>创建</button></div>
        </form>
      ) : null}
      {selectedWorkspace ? (
        <>
          <div className="workspace-current-heading"><div><span className="workspace-eyebrow">Current</span><h2>{selectedWorkspace.name}</h2></div><span className={`workspace-status workspace-status-${String(selectedWorkspace.status).toLowerCase()}`}>{selectedWorkspace.status}</span></div>
          {archived ? <div className="workspace-archive-notice"><Icon name="archive" size={15} /><span>Workspace 已归档，请恢复后继续聊天和管理 Assets。</span></div> : null}
          <button className="workspace-primary-button" type="button" disabled={archived} onClick={() => onCreateSession?.(selectedWorkspace.id)}><Icon name="message" size={14} /> 在此 Workspace 开始会话</button>
          <section className="workspace-section" aria-label="AGENT.md 设置">
            <div className="workspace-section-heading"><div><span className="workspace-eyebrow">AGENT.md</span><h2>工作规则</h2></div><small>v{workspaceInstructions.version}</small></div>
            <textarea value={instructionDraft} maxLength={8000} disabled={archived || instructionSaving} onChange={(event) => setInstructionDraft(event.target.value)} placeholder="为当前 Workspace 定义 Agent 的工作流程和输出结构。" rows={8} />
            <div className="workspace-form-actions"><small>{instructionDraft.length}/8000</small><button type="button" className="workspace-secondary-button" disabled={archived || instructionSaving || !instructionDraft} onClick={async () => { setInstructionSaving(true); try { await onClearInstructions?.(); setInstructionDraft('') } finally { setInstructionSaving(false) } }}>清空</button><button type="button" className="workspace-small-button" disabled={archived || instructionSaving} onClick={handleSaveInstructions}>保存</button></div>
          </section>
          <WorkspaceAssets assets={assets} loading={assetsStatus === 'loading'} error={assetsError} disabled={archived} actionStates={assetActionStates} onUpload={onUploadAsset} onRetry={onRetryAsset} onDelete={onDeleteAsset} onDownload={onDownloadAsset} />
          <WorkspaceTasks tasks={tasks} loading={tasksStatus === 'loading'} error={tasksError} />
          <WorkspaceArtifacts artifacts={artifacts} loading={artifactsStatus === 'loading'} error={artifactsError} selectedArtifact={selectedArtifact} content={artifactContent} contentLoading={artifactContentLoading} onSelect={onSelectArtifact} onClosePreview={onCloseArtifact} onDownload={onDownloadArtifact} />
        </>
      ) : <p className="workspace-empty">选择一个 Workspace 查看文件和产出。</p>}
      </aside>
    </>
  )
}

export default WorkspacePanel

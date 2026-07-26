export const ATTACHMENT_STATUS_LABELS = {
  UPLOADED: '等待处理',
  PARSING: '正在解析 PDF',
  INDEXING: '正在建立索引',
  READY: '可用于问答',
  PARTIAL: '部分内容可用',
  FAILED: '处理失败',
  DELETING: '正在删除',
}

const PENDING_STATUSES = new Set(['UPLOADED', 'PARSING', 'INDEXING'])
const USABLE_STATUSES = new Set(['READY', 'PARTIAL'])

const ERROR_MESSAGES = {
  attachment_not_found: '附件不存在、已过期，或不属于当前会话。',
  attachment_not_ready: '附件仍在处理中，请稍后再试。',
  attachment_processing_failed: '附件处理失败，请重试或重新上传。',
  attachment_index_missing: '附件索引缺失，请重新处理。',
  attachment_no_relevant_evidence: '所选附件中没有检索到相关内容。',
  attachment_already_processing: '附件正在处理中，无需重复重试。',
  attachment_retry_not_allowed: '当前附件状态不允许重新处理。',
  attachment_limit_reached: '当前会话附件数量已达到上限。',
  attachment_too_large: 'PDF 文件超过大小限制。',
  unsupported_attachment_type: '当前只支持包含文本层的 PDF 文件。',
  attachment_storage_error: '附件存储失败，请稍后重试。',
  attachment_retrieval_failed: '附件检索暂时失败，请稍后重试。',
}

export function isAttachmentPending(status) {
  return PENDING_STATUSES.has(status)
}

export function isAttachmentUsable(status) {
  return USABLE_STATUSES.has(status)
}

export function attachmentStatusLabel(status) {
  return ATTACHMENT_STATUS_LABELS[status] ?? status ?? '未知状态'
}

export function attachmentErrorCode(error) {
  return typeof error?.detail?.error === 'string' ? error.detail.error : ''
}

export function attachmentErrorMessage(error, fallback = '附件操作失败，请稍后重试。') {
  return ERROR_MESSAGES[attachmentErrorCode(error)] ?? fallback
}

export function shouldMarkApiOffline(error) {
  return Boolean(error?.isNetworkError)
}

export function formatAttachmentSize(sizeBytes) {
  const bytes = Number(sizeBytes)
  if (!Number.isFinite(bytes) || bytes < 0) return '大小未知'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function getInitialSelectedAttachmentIds(attachments) {
  return (Array.isArray(attachments) ? attachments : [])
    .filter((attachment) => isAttachmentUsable(attachment?.status))
    .slice(0, 5)
    .map((attachment) => attachment.id)
}

export function reconcileSelectedAttachmentIds(selectedIds, attachments) {
  const availableIds = new Set(
    (Array.isArray(attachments) ? attachments : []).map((attachment) => attachment?.id),
  )
  return (Array.isArray(selectedIds) ? selectedIds : [])
    .filter((attachmentId) => availableIds.has(attachmentId))
    .slice(0, 5)
}

export function addSelectedAttachmentId(selectedIds, attachmentId) {
  const nextIds = new Set(Array.isArray(selectedIds) ? selectedIds : [])
  nextIds.add(attachmentId)
  return [...nextIds].slice(0, 5)
}

export function getAttachmentSendBlockReason(attachments, selectedIds) {
  const selectedSet = new Set(Array.isArray(selectedIds) ? selectedIds : [])
  const selectedAttachments = (Array.isArray(attachments) ? attachments : [])
    .filter((attachment) => selectedSet.has(attachment?.id))

  if (selectedAttachments.some((attachment) => isAttachmentPending(attachment.status))) {
    return '附件仍在处理中，请等待处理完成后再发送。'
  }
  if (selectedAttachments.some((attachment) => attachment.status === 'FAILED')) {
    return '所选附件处理失败，请重试、删除或取消选择。'
  }
  if (selectedAttachments.some((attachment) => !isAttachmentUsable(attachment.status))) {
    return '所选附件当前不可用于问答，请取消选择后再发送。'
  }
  return ''
}

export function getSendableAttachmentIds(attachments, selectedIds) {
  const selectedSet = new Set(Array.isArray(selectedIds) ? selectedIds : [])
  return (Array.isArray(attachments) ? attachments : [])
    .filter((attachment) => selectedSet.has(attachment?.id) && isAttachmentUsable(attachment.status))
    .slice(0, 5)
    .map((attachment) => attachment.id)
}

export function validatePdfFile(file) {
  if (!file) return '请选择 PDF 文件。'
  const hasPdfExtension = typeof file.name === 'string' && file.name.toLowerCase().endsWith('.pdf')
  const hasPdfMime = file.type === 'application/pdf'
  if (!hasPdfExtension && !hasPdfMime) return '当前只支持 PDF 文件。'
  if (file.size <= 0) return 'PDF 文件为空，请选择有效文件。'
  return ''
}

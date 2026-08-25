export const ATTACHMENT_STATUS_LABELS = {
  UPLOADED: '等待处理',
  PARSING: '正在解析文件',
  INDEXING: '正在建立索引',
  READY: '可用于问答',
  PARTIAL: '部分内容可用',
  FAILED: '处理失败',
  DELETING: '正在删除',
}

export const SUPPORTED_ATTACHMENT_EXTENSIONS = [
  '.pdf', '.docx', '.xlsx', '.pptx', '.txt', '.log', '.md', '.markdown',
  '.csv', '.json', '.html', '.xml', '.py', '.js', '.jsx', '.ts', '.tsx',
  '.java', '.go', '.rs', '.c', '.cpp', '.h', '.cs', '.sql', '.sh', '.yaml',
  '.yml', '.toml', '.ini', '.css',
]

export const SUPPORTED_ATTACHMENT_ACCEPT = SUPPORTED_ATTACHMENT_EXTENSIONS.join(',')

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
  attachment_too_large: '文件超过大小限制。',
  unsupported_attachment_type: '不支持该文件类型。支持：PDF、Word(.docx)、Excel(.xlsx)、PPT(.pptx)、Markdown、文本、代码、CSV、JSON。',
  attachment_legacy_office_format: '不支持旧版 Office 格式，请另存为 .docx、.pptx、.xlsx 或 PDF。',
  attachment_archive_not_supported: '不支持压缩包，请直接上传 PDF、Office 文档或文本文件。',
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

export function validateAttachmentFile(file) {
  if (!file) return '请选择附件文件。'
  const filename = typeof file.name === 'string' ? file.name.toLowerCase() : ''
  if (!SUPPORTED_ATTACHMENT_EXTENSIONS.some((extension) => filename.endsWith(extension))) return '不支持该文件类型。支持 PDF、Word、Excel、PPT、文本、Markdown、代码、CSV、JSON。'
  if (file.size <= 0) return '文件为空，请选择有效文件。'
  return ''
}

export function getAttachmentIconName(filename) {
  const lowerName = typeof filename === 'string' ? filename.toLowerCase() : ''
  if (lowerName.endsWith('.xlsx')) return 'file-sheet'
  if (lowerName.endsWith('.pptx')) return 'file-slides'
  if (['.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.rs', '.c', '.cpp', '.h', '.cs', '.sql', '.sh', '.yaml', '.yml', '.toml', '.ini', '.css', '.xml'].some((extension) => lowerName.endsWith(extension))) return 'file-code'
  if (['.txt', '.log', '.md', '.markdown', '.csv', '.json', '.html', '.docx'].some((extension) => lowerName.endsWith(extension))) return 'file-text'
  return 'file'
}

export const validatePdfFile = validateAttachmentFile

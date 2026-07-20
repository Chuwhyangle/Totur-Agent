export function safeHttpUrl(rawUrl) {
  if (typeof rawUrl !== 'string' || rawUrl.trim().length === 0) return null

  try {
    const parsedUrl = new URL(rawUrl)
    return parsedUrl.protocol === 'https:' ? parsedUrl.toString() : null
  } catch {
    return null
  }
}

export function sourceCardId(sourceId) {
  const safeId = String(sourceId ?? '').replace(/[^a-zA-Z0-9_-]/g, '-')
  return `source-${safeId || 'unknown'}`
}

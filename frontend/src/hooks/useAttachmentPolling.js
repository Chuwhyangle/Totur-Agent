import { useEffect } from 'react'

export function useAttachmentPolling({ enabled, poll, intervalMs = 1500, scopeKey = '' }) {
  useEffect(() => {
    if (!enabled) return undefined

    let cancelled = false
    let timerId = null
    let controller = null

    const schedule = () => {
      if (cancelled) return
      timerId = window.setTimeout(runPoll, intervalMs)
    }

    const runPoll = async () => {
      if (cancelled) return
      controller = new AbortController()
      try {
        await poll({ signal: controller.signal })
      } finally {
        controller = null
        schedule()
      }
    }

    schedule()

    return () => {
      cancelled = true
      if (timerId != null) window.clearTimeout(timerId)
      controller?.abort()
    }
  }, [enabled, intervalMs, poll, scopeKey])
}

import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAttachmentPolling } from './useAttachmentPolling.js'

describe('useAttachmentPolling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('polls while enabled and stops after enabled becomes false', async () => {
    const poll = vi.fn().mockResolvedValue(undefined)
    const { rerender } = renderHook(
      ({ enabled }) => useAttachmentPolling({ enabled, poll, intervalMs: 100, scopeKey: 'scope-1' }),
      { initialProps: { enabled: true } },
    )

    expect(poll).not.toHaveBeenCalled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(poll).toHaveBeenCalledTimes(1)
    expect(poll.mock.calls[0][0].signal).toBeInstanceOf(AbortSignal)

    rerender({ enabled: false })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
    })
    expect(poll).toHaveBeenCalledTimes(1)
  })

  it('aborts an in-flight poll when scope changes', async () => {
    let observedSignal
    const poll = vi.fn(({ signal }) => {
      observedSignal = signal
      return new Promise(() => {})
    })
    const { rerender } = renderHook(
      ({ scopeKey }) => useAttachmentPolling({ enabled: true, poll, intervalMs: 50, scopeKey }),
      { initialProps: { scopeKey: 'scope-1' } },
    )

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })
    expect(observedSignal.aborted).toBe(false)

    rerender({ scopeKey: 'scope-2' })
    expect(observedSignal.aborted).toBe(true)
  })
})

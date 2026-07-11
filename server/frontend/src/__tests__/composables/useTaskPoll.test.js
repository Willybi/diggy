import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../utils/api.js', () => ({
  default: { get: apiGet },
}))

import { useTaskPoll } from '../../composables/useTaskPoll.js'

// Mount a throwaway component whose setup calls useTaskPoll, so onUnmounted
// registers against a real component instance (the composable's contract).
function mountPoll(statusUrlFn, options) {
  let controls
  const wrapper = mount({
    setup() {
      controls = useTaskPoll(statusUrlFn, options)
      return () => null
    },
  })
  return { wrapper, controls }
}

describe('useTaskPoll', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    apiGet.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('polls until the payload is terminal, then stops the timer', async () => {
    apiGet
      .mockResolvedValueOnce({ data: { status: 'running' } })
      .mockResolvedValueOnce({ data: { status: 'done', result: 42 } })

    const onData = vi.fn((data, { stop }) => {
      if (data.status === 'done') stop()
    })
    const { controls } = mountPoll((key) => `/status/${key}`, { intervalMs: 2000, onData })

    controls.start('task-1')
    expect(controls.isActive('task-1')).toBe(true)

    await vi.advanceTimersByTimeAsync(2000) // 1st tick → running
    expect(apiGet).toHaveBeenCalledWith('/status/task-1')
    expect(controls.isActive('task-1')).toBe(true)

    await vi.advanceTimersByTimeAsync(2000) // 2nd tick → done
    expect(onData).toHaveBeenCalledTimes(2)
    expect(controls.isActive('task-1')).toBe(false)

    // No further requests once stopped.
    const callsAfterDone = apiGet.mock.calls.length
    await vi.advanceTimersByTimeAsync(6000)
    expect(apiGet.mock.calls.length).toBe(callsAfterDone)
  })

  it('routes request failures to onError and stops by default', async () => {
    apiGet.mockRejectedValue(new Error('boom'))
    const onError = vi.fn()
    const { controls } = mountPoll(() => '/status', { intervalMs: 1000, onError })

    controls.start()
    await vi.advanceTimersByTimeAsync(1000)

    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error)
    expect(controls.isActive()).toBe(false)
  })

  it('keeps polling through errors when stopOnError is false', async () => {
    apiGet.mockRejectedValue(new Error('flaky'))
    const onError = vi.fn()
    const { controls } = mountPoll(() => '/status', {
      intervalMs: 1000,
      stopOnError: false,
      onError,
    })

    controls.start()
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(1000)

    // Each failing tick notifies onError but the poll survives and keeps going.
    expect(onError).toHaveBeenCalledTimes(2)
    expect(controls.isActive()).toBe(true)
    expect(apiGet.mock.calls.length).toBe(2)
    controls.stop()
  })

  it('fires onMaxAttempts and stops once the cap is exceeded', async () => {
    apiGet.mockResolvedValue({ data: { status: 'running' } })
    const onMaxAttempts = vi.fn()
    const { controls } = mountPoll(() => '/status', {
      intervalMs: 1000,
      maxAttempts: 2,
      onMaxAttempts,
    })

    controls.start()
    await vi.advanceTimersByTimeAsync(1000) // attempt 1 → GET
    await vi.advanceTimersByTimeAsync(1000) // attempt 2 → GET
    expect(apiGet.mock.calls.length).toBe(2)
    expect(onMaxAttempts).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1000) // attempt 3 → over cap, no GET
    expect(apiGet.mock.calls.length).toBe(2)
    expect(onMaxAttempts).toHaveBeenCalledTimes(1)
    expect(controls.isActive()).toBe(false)
  })

  it('stops every timer when the host component unmounts', async () => {
    apiGet.mockResolvedValue({ data: { status: 'running' } })
    const { wrapper, controls } = mountPoll((key) => `/status/${key}`, { intervalMs: 1000 })

    controls.start('a')
    controls.start('b')
    expect(controls.isActive('a')).toBe(true)
    expect(controls.isActive('b')).toBe(true)

    wrapper.unmount()
    expect(controls.isActive('a')).toBe(false)
    expect(controls.isActive('b')).toBe(false)

    const callsBefore = apiGet.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)
    expect(apiGet.mock.calls.length).toBe(callsBefore)
  })

  it('runs concurrent polls independently, stopping one leaves the other alive', async () => {
    apiGet.mockImplementation((url) => {
      // 'a' terminates on its first tick; 'b' keeps running.
      if (url === '/status/a') return Promise.resolve({ data: { status: 'done' } })
      return Promise.resolve({ data: { status: 'running' } })
    })
    const onData = vi.fn((data, { stop }) => {
      if (data.status === 'done') stop()
    })
    const { controls } = mountPoll((key) => `/status/${key}`, { intervalMs: 1000, onData })

    controls.start('a')
    controls.start('b')

    await vi.advanceTimersByTimeAsync(1000) // both tick once; 'a' finishes
    expect(controls.isActive('a')).toBe(false)
    expect(controls.isActive('b')).toBe(true)

    const aCalls = apiGet.mock.calls.filter(([u]) => u === '/status/a').length
    await vi.advanceTimersByTimeAsync(2000) // only 'b' keeps polling
    expect(apiGet.mock.calls.filter(([u]) => u === '/status/a').length).toBe(aCalls)
    expect(apiGet.mock.calls.filter(([u]) => u === '/status/b').length).toBeGreaterThan(1)

    controls.stop('b')
    expect(controls.isActive('b')).toBe(false)
  })
})

import { onUnmounted } from 'vue'
import api from '../utils/api.js'

const DEFAULT_KEY = '__default__'

/**
 * Poll a Celery-style task-status endpoint on an interval until the host
 * component decides it is finished.
 *
 * Centralizes the parts every polling site duplicates — the interval loop, the
 * attempt cap, the network-error catch and the unmount cleanup — while leaving
 * the interpretation of the payload (progress fields, terminal statuses, error
 * messages) to the caller's callbacks.
 *
 * MUST be called synchronously in setup() so its onUnmounted cleanup registers.
 * Timers are keyed, so several polls can run concurrently (e.g. one per playlist
 * in WatchlistView); single-task sites simply omit the key.
 *
 * @param {(key: string) => string} statusUrlFn  builds the status URL for a key
 * @param {object} [options]
 * @param {number} [options.intervalMs=3000]      delay between ticks
 * @param {number|null} [options.maxAttempts=null]  give up after N requests (null = never)
 * @param {boolean} [options.stopOnError=true]     stop the poll when a request throws
 * @param {(data: any, ctx: PollCtx) => void} [options.onData]  called with each response body
 * @param {(err: any, ctx: PollCtx) => void} [options.onError]  called when a request throws
 * @param {(ctx: {key: string, attempt: number}) => void} [options.onMaxAttempts]
 * @returns {{ start: Function, stop: Function, isActive: Function }}
 *
 * @typedef {{ key: string, attempt: number, stop: () => void }} PollCtx
 */
export function useTaskPoll(statusUrlFn, options = {}) {
  const {
    intervalMs = 3000,
    maxAttempts = null,
    stopOnError = true,
    onData,
    onError,
    onMaxAttempts,
  } = options

  // key → { timerId, attempts }
  const timers = new Map()

  function isActive(key = DEFAULT_KEY) {
    return timers.has(key)
  }

  // stop() with no key stops every poll (used by unmount cleanup and single-task sites).
  function stop(key) {
    if (key === undefined) {
      timers.forEach((entry) => clearInterval(entry.timerId))
      timers.clear()
      return
    }
    const entry = timers.get(key)
    if (entry) {
      clearInterval(entry.timerId)
      timers.delete(key)
    }
  }

  function start(key = DEFAULT_KEY) {
    stop(key)
    const entry = { timerId: null, attempts: 0 }
    entry.timerId = setInterval(() => tick(key), intervalMs)
    timers.set(key, entry)
  }

  async function tick(key) {
    const entry = timers.get(key)
    if (!entry) return
    entry.attempts++
    const attempt = entry.attempts
    if (maxAttempts !== null && attempt > maxAttempts) {
      stop(key)
      onMaxAttempts?.({ key, attempt })
      return
    }
    const ctx = { key, attempt, stop: () => stop(key) }
    try {
      const { data } = await api.get(statusUrlFn(key))
      if (!timers.has(key)) return // stopped/unmounted while the request was in flight
      await onData?.(data, ctx)
    } catch (err) {
      if (!timers.has(key)) return
      onError?.(err, ctx)
      if (stopOnError) stop(key)
    }
  }

  onUnmounted(() => stop())

  return { start, stop, isActive }
}

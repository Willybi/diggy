import { describe, it, expect, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createChunkPrefetcher } from '../../utils/prefetch.js'

describe('createChunkPrefetcher (D9.c chunk prefetch)', () => {
  it('does not invoke any loader at construction time', () => {
    const loader = vi.fn(() => Promise.resolve({ default: {} }))
    createChunkPrefetcher(new Map([['/radar', loader]]))
    expect(loader).not.toHaveBeenCalled()
  })

  it('invokes the target route loader once and dedups repeats', async () => {
    const radar = vi.fn(() => Promise.resolve({ default: {} }))
    const explorer = vi.fn(() => Promise.resolve({ default: {} }))
    const prefetch = createChunkPrefetcher(
      new Map([
        ['/radar', radar],
        ['/explorer', explorer],
      ]),
    )

    prefetch('/radar')
    prefetch('/radar')
    prefetch('/radar')
    await flushPromises()

    expect(radar).toHaveBeenCalledTimes(1)
    // Only the hovered route is preloaded — never a burst of the whole nav.
    expect(explorer).not.toHaveBeenCalled()
  })

  it('ignores an unknown path (no loader = no-op, no throw)', async () => {
    const prefetch = createChunkPrefetcher(new Map())
    expect(() => prefetch('/nope')).not.toThrow()
    await flushPromises()
  })

  it('swallows a rejected loader and frees the key for a later retry', async () => {
    const loader = vi
      .fn()
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce({ default: {} })
    const prefetch = createChunkPrefetcher(new Map([['/radar', loader]]))

    // First attempt rejects — must not surface as an unhandled rejection.
    prefetch('/radar')
    await flushPromises()
    expect(loader).toHaveBeenCalledTimes(1)

    // The key was released on failure, so a subsequent hover retries.
    prefetch('/radar')
    await flushPromises()
    expect(loader).toHaveBeenCalledTimes(2)
  })
})

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'

// Capture the guard callback registered at setup so tests can fire "leave".
const { leave } = vi.hoisted(() => ({ leave: { cb: null } }))
vi.mock('vue-router', () => ({
  onBeforeRouteLeave: (cb) => {
    leave.cb = cb
  },
}))

import { useScrollRestore } from '../../composables/useScrollRestore.js'

describe('useScrollRestore', () => {
  beforeEach(() => {
    leave.cb = null
    window.history.replaceState({}, '')
  })

  it('without a snapshot: runs initialFetch only, leaves the scroller alone', async () => {
    const node = { scrollTop: 0 }
    const initialFetch = vi.fn(() => Promise.resolve())
    const hydrate = vi.fn(() => Promise.resolve())
    const { restore } = useScrollRestore({ scroller: ref(node), getCount: () => 0 })

    const restored = await restore({ initialFetch, hydrate })

    expect(restored).toBe(false)
    expect(initialFetch).toHaveBeenCalledTimes(1)
    expect(hydrate).not.toHaveBeenCalled()
    expect(node.scrollTop).toBe(0)
  })

  it('with a snapshot: hydrates the saved count then re-applies the offset', async () => {
    window.history.replaceState({ __diggyScroll: { top: 300, count: 240 } }, '')
    const node = { scrollTop: 0 }
    const initialFetch = vi.fn(() => Promise.resolve())
    const hydrate = vi.fn(() => Promise.resolve())
    const { restore } = useScrollRestore({ scroller: ref(node), getCount: () => 240 })

    const restored = await restore({ initialFetch, hydrate })

    expect(restored).toBe(true)
    expect(hydrate).toHaveBeenCalledWith(240)
    expect(initialFetch).not.toHaveBeenCalled()
    expect(node.scrollTop).toBe(300)
  })

  it('at the top of the list (top 0): treated as a fresh load, no hydrate', async () => {
    window.history.replaceState({ __diggyScroll: { top: 0, count: 240 } }, '')
    const node = { scrollTop: 0 }
    const initialFetch = vi.fn(() => Promise.resolve())
    const hydrate = vi.fn(() => Promise.resolve())
    const { restore } = useScrollRestore({ scroller: ref(node), getCount: () => 240 })

    const restored = await restore({ initialFetch, hydrate })

    expect(restored).toBe(false)
    expect(initialFetch).toHaveBeenCalledTimes(1)
    expect(hydrate).not.toHaveBeenCalled()
  })

  it('snapshot() writes { top, count } into history.state on leave', () => {
    const node = { scrollTop: 540 }
    useScrollRestore({ scroller: ref(node), getCount: () => 120 })

    expect(leave.cb).toBeTypeOf('function')
    leave.cb()

    expect(window.history.state.__diggyScroll).toEqual({ top: 540, count: 120 })
  })
})

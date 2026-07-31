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

const PAGE = 20
const TARGET = 60

// A fake paginated source: initialFetch loads page 1, loadMore appends a page.
function makeSource() {
  const items = ref([])
  const hasMore = ref(false)
  const loadMore = vi.fn(() => {
    const n = items.value.length
    items.value = [...items.value, ...Array.from({ length: PAGE }, (_, i) => n + i)]
    hasMore.value = items.value.length < TARGET
    return Promise.resolve()
  })
  const initialFetch = vi.fn(() => {
    items.value = Array.from({ length: PAGE }, (_, i) => i)
    hasMore.value = true
    return Promise.resolve()
  })
  return { items, hasMore, loadMore, initialFetch }
}

describe('useScrollRestore', () => {
  beforeEach(() => {
    leave.cb = null
    window.history.replaceState({}, '')
  })

  it('without a snapshot: loads page 1 only and does not touch the scroller', async () => {
    const node = { scrollTop: 0 }
    const { items, hasMore, loadMore, initialFetch } = makeSource()
    const { restore } = useScrollRestore({
      scroller: ref(node),
      getCount: () => items.value.length,
      loadMore,
      hasMore,
    })

    const restored = await restore(initialFetch)

    expect(restored).toBe(false)
    expect(initialFetch).toHaveBeenCalledTimes(1)
    expect(loadMore).not.toHaveBeenCalled()
    expect(node.scrollTop).toBe(0)
  })

  it('with a snapshot: reloads pages up to the saved count then re-applies the offset', async () => {
    window.history.replaceState({ __diggyScroll: { top: 300, count: TARGET } }, '')
    const node = { scrollTop: 0 }
    const { items, hasMore, loadMore, initialFetch } = makeSource()
    const { restore } = useScrollRestore({
      scroller: ref(node),
      getCount: () => items.value.length,
      loadMore,
      hasMore,
    })

    const restored = await restore(initialFetch)

    expect(restored).toBe(true)
    // page 1 (20) + two loadMore pages (→ 60) to reach the saved count.
    expect(loadMore).toHaveBeenCalledTimes(2)
    expect(items.value.length).toBe(TARGET)
    expect(node.scrollTop).toBe(300)
  })

  it('stops growing when the source runs dry (fewer rows than the saved count)', async () => {
    window.history.replaceState({ __diggyScroll: { top: 999, count: 200 } }, '')
    const node = { scrollTop: 0 }
    const { items, hasMore, loadMore, initialFetch } = makeSource()
    const { restore } = useScrollRestore({
      scroller: ref(node),
      getCount: () => items.value.length,
      loadMore,
      hasMore,
    })

    await restore(initialFetch)

    // hasMore turns false at 60 → the loop stops there, offset still applied.
    expect(items.value.length).toBe(TARGET)
    expect(node.scrollTop).toBe(999)
  })

  it('snapshot() writes { top, count } into history.state on leave', async () => {
    const node = { scrollTop: 0 }
    const { items, loadMore, hasMore, initialFetch } = makeSource()
    useScrollRestore({
      scroller: ref(node),
      getCount: () => items.value.length,
      loadMore,
      hasMore,
    })
    await initialFetch()
    node.scrollTop = 540

    // Fire the onBeforeRouteLeave guard captured at setup.
    expect(leave.cb).toBeTypeOf('function')
    leave.cb()

    expect(window.history.state.__diggyScroll).toEqual({ top: 540, count: PAGE })
  })
})

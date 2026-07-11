import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../utils/api.js', () => ({
  default: { get: apiGet },
}))

import { usePaginatedList } from '../../composables/usePaginatedList.js'

// Mount a throwaway component whose setup calls usePaginatedList, so the
// useInfiniteScroll onMounted/onUnmounted hooks register against a real
// instance (the composable's contract).
function mountList(opts) {
  let list
  const wrapper = mount({
    setup() {
      list = usePaginatedList(opts)
      return () => null
    },
  })
  return { wrapper, list }
}

const page = (items, total) => ({
  data: { items, total, pillarCounts: { techno: total } },
})

describe('usePaginatedList', () => {
  beforeEach(() => {
    apiGet.mockReset()
    // jsdom has no IntersectionObserver; the sentinel wiring only needs it to exist.
    globalThis.IntersectionObserver = class {
      observe() {}
      disconnect() {}
    }
  })

  afterEach(() => {
    delete globalThis.IntersectionObserver
  })

  it('initial fetch fills state with the expected params', async () => {
    apiGet.mockResolvedValueOnce(page([{ id: 1 }, { id: 2 }], 5))
    const { list } = mountList({
      endpoint: '/api/artists/',
      pageSize: 24,
      sort: () => 'catalog',
      family: () => 'all',
      query: () => '',
    })

    await list.fetch()

    expect(apiGet).toHaveBeenCalledWith('/api/artists/', {
      params: { sort: 'catalog', limit: 24, offset: 0 },
    })
    expect(list.items.value).toEqual([{ id: 1 }, { id: 2 }])
    expect(list.total.value).toBe(5)
    expect(list.familyCounts.value).toEqual({ techno: 5 })
    expect(list.hasMore.value).toBe(true) // 2 < 5
    expect(list.loading.value).toBe(false)
  })

  it('adds family and trimmed q params only when active', async () => {
    apiGet.mockResolvedValueOnce(page([], 0))
    const { list } = mountList({
      endpoint: '/api/genres',
      sort: () => 'tracks',
      family: () => 'techno',
      query: () => '  house  ',
    })

    await list.fetch()

    expect(apiGet).toHaveBeenCalledWith('/api/genres', {
      params: { sort: 'tracks', limit: 24, offset: 0, family: 'techno', q: 'house' },
    })
  })

  it('loadMore appends the next page and advances the offset', async () => {
    apiGet
      .mockResolvedValueOnce(page([{ id: 1 }, { id: 2 }], 4))
      .mockResolvedValueOnce(page([{ id: 3 }, { id: 4 }], 4))
    const { list } = mountList({
      endpoint: '/api/artists/',
      sort: () => 'catalog',
    })

    await list.fetch()
    expect(list.hasMore.value).toBe(true)

    list.loadMore()
    await flushPromises()

    expect(apiGet).toHaveBeenLastCalledWith('/api/artists/', {
      params: { sort: 'catalog', limit: 24, offset: 2 },
    })
    expect(list.items.value).toEqual([{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }])
    expect(list.offset.value).toBe(2)
    expect(list.hasMore.value).toBe(false) // 4 < 4 → false
  })

  it('guards against a double fetch while a load is in flight', async () => {
    let resolveFirst
    apiGet
      .mockImplementationOnce(
        () => new Promise((r) => (resolveFirst = () => r(page([{ id: 1 }], 4)))),
      )
      .mockResolvedValue(page([{ id: 2 }], 4))
    const { list } = mountList({ endpoint: '/api/artists/', sort: () => 'catalog' })

    const first = list.fetch()
    expect(list.loading.value).toBe(true)

    // Sentinel re-fires while loading → must be ignored.
    list.loadMore()
    expect(apiGet).toHaveBeenCalledTimes(1)

    resolveFirst()
    await first
    expect(list.loading.value).toBe(false)
  })

  it('reset replaces items and rewinds the offset to 0', async () => {
    const sort = ref('catalog')
    apiGet
      .mockResolvedValueOnce(page([{ id: 1 }, { id: 2 }], 4))
      .mockResolvedValueOnce(page([{ id: 3 }, { id: 4 }], 4))
      .mockResolvedValueOnce(page([{ id: 9 }], 1))
    const { list } = mountList({ endpoint: '/api/artists/', sort: () => sort.value })

    await list.fetch()
    list.loadMore()
    await flushPromises()
    expect(list.offset.value).toBe(2)

    // Filter change → reset fetch.
    sort.value = 'alpha'
    await list.fetch(true)

    expect(list.offset.value).toBe(0)
    expect(list.items.value).toEqual([{ id: 9 }]) // replaced, not appended
    expect(apiGet).toHaveBeenLastCalledWith('/api/artists/', {
      params: { sort: 'alpha', limit: 24, offset: 0 },
    })
  })

  it('on a reset error empties items; on a loadMore error keeps them', async () => {
    const { list } = mountList({ endpoint: '/api/artists/', sort: () => 'catalog' })

    // Reset error → items cleared.
    apiGet.mockRejectedValueOnce(new Error('boom'))
    await list.fetch(true)
    expect(list.items.value).toEqual([])
    expect(list.loading.value).toBe(false)

    // Successful page, then a failing loadMore → prior items survive.
    apiGet.mockResolvedValueOnce(page([{ id: 1 }, { id: 2 }], 4))
    await list.fetch(true)
    apiGet.mockRejectedValueOnce(new Error('flaky'))
    list.loadMore()
    await flushPromises()

    expect(list.items.value).toEqual([{ id: 1 }, { id: 2 }])
    expect(list.loading.value).toBe(false)
  })
})

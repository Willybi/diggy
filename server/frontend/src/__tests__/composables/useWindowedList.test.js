import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../utils/api.js', () => ({
  default: { get: apiGet },
}))

import { useWindowedList } from '../../composables/useWindowedList.js'

// The page supplies buildParams(skip); the endpoint gets called with it verbatim.
const params = (skip) => ({ skip, limit: 100 })
const page = (items, total) => ({ data: { items, total } })

describe('useWindowedList', () => {
  beforeEach(() => {
    apiGet.mockReset()
  })

  it('initial fetch fills state and calls the endpoint with buildParams(0)', async () => {
    apiGet.mockResolvedValueOnce(page([{ id: 1 }, { id: 2 }], 5))
    const list = useWindowedList({ endpoint: '/api/catalog/', buildParams: params })

    await list.fetch()

    expect(apiGet).toHaveBeenCalledWith('/api/catalog/', { params: { skip: 0, limit: 100 } })
    expect(list.items.value).toEqual([{ id: 1 }, { id: 2 }])
    expect(list.total.value).toBe(5)
    expect(list.hasMore.value).toBe(true) // 2 < 5
    expect(list.loading.value).toBe(false)
  })

  it('loadMore appends the next page at skip = items.length', async () => {
    apiGet
      .mockResolvedValueOnce(page([{ id: 1 }, { id: 2 }], 4))
      .mockResolvedValueOnce(page([{ id: 3 }, { id: 4 }], 4))
    const list = useWindowedList({ endpoint: '/api/catalog/', buildParams: params })

    await list.fetch()
    list.loadMore()
    await flushPromises()

    expect(apiGet).toHaveBeenLastCalledWith('/api/catalog/', { params: { skip: 2, limit: 100 } })
    expect(list.items.value).toEqual([{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }])
    expect(list.hasMore.value).toBe(false) // 4 < 4 → false
  })

  it('reset replaces items instead of appending', async () => {
    apiGet
      .mockResolvedValueOnce(page([{ id: 1 }, { id: 2 }], 4))
      .mockResolvedValueOnce(page([{ id: 9 }], 1))
    const list = useWindowedList({ endpoint: '/api/catalog/', buildParams: params })

    await list.fetch()
    await list.fetch(true)

    expect(list.items.value).toEqual([{ id: 9 }]) // replaced, not appended
    expect(list.total.value).toBe(1)
    expect(list.hasMore.value).toBe(false)
  })

  it('guards loadMore while a load is in flight', async () => {
    let resolveFirst
    apiGet
      .mockImplementationOnce(() => new Promise((r) => (resolveFirst = () => r(page([{ id: 1 }], 4)))))
      .mockResolvedValue(page([{ id: 2 }], 4))
    const list = useWindowedList({ endpoint: '/api/catalog/', buildParams: params })

    const first = list.fetch()
    expect(list.loading.value).toBe(true)

    // Window re-fires loadMore while loading → must be ignored.
    list.loadMore()
    expect(apiGet).toHaveBeenCalledTimes(1)

    resolveFirst()
    await first
    expect(list.loading.value).toBe(false)
  })

  it('drops a stale response when a newer request supersedes it (race)', async () => {
    let resolveOld
    apiGet
      // Old request A: resolves LAST, must be discarded.
      .mockImplementationOnce(() => new Promise((r) => (resolveOld = () => r(page([{ id: 'old' }], 1)))))
      // New request B: resolves first with the winning payload.
      .mockResolvedValueOnce(page([{ id: 'new' }], 1))
    const list = useWindowedList({ endpoint: '/api/catalog/', buildParams: params })

    const a = list.fetch(true) // A in flight
    const b = list.fetch(true) // B supersedes A (token bumped)
    await b
    resolveOld() // A resolves late
    await a

    expect(list.items.value).toEqual([{ id: 'new' }])
    expect(list.loading.value).toBe(false)
  })

  it('on a reset error flags error (total null, not 0); on a loadMore error keeps them', async () => {
    const list = useWindowedList({ endpoint: '/api/catalog/', buildParams: params })

    // Reset error → items cleared, error flagged, total left null (NOT 0, which
    // the page would read as an empty result rather than a failure).
    apiGet.mockRejectedValueOnce(new Error('boom'))
    await list.fetch(true)
    expect(list.items.value).toEqual([])
    expect(list.total.value).toBe(null)
    expect(list.error.value).toBe(true)
    expect(list.loading.value).toBe(false)

    // A successful reset clears the error flag.
    apiGet.mockResolvedValueOnce(page([{ id: 1 }, { id: 2 }], 4))
    await list.fetch(true)
    expect(list.error.value).toBe(false)
    expect(list.total.value).toBe(4)

    // A failing loadMore → prior items survive, error stays clear.
    apiGet.mockRejectedValueOnce(new Error('flaky'))
    list.loadMore()
    await flushPromises()

    expect(list.items.value).toEqual([{ id: 1 }, { id: 2 }])
    expect(list.error.value).toBe(false)
    expect(list.loading.value).toBe(false)
  })
})

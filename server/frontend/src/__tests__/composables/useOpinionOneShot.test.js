import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'

// The composable reaches api + the opinions store directly (like usePaginatedList
// reaches api). Mock both: api.get is asserted, the store is a controllable
// { data, load } stand-in whose `data[kind]` map drives the id resolution.
const { apiGet, opinionsStore } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  opinionsStore: { data: {}, load: vi.fn() },
}))

vi.mock('../../utils/api.js', () => ({ default: { get: apiGet } }))
vi.mock('../../stores/opinions.js', () => ({ useOpinionsStore: () => opinionsStore }))

import { useOpinionOneShot } from '../../composables/useOpinionOneShot.js'

// The trunk refs a host view would hand over (from usePaginatedList).
function makeRefs() {
  return { items: ref([]), total: ref(0), hasMore: ref(false), loading: ref(false) }
}

describe('useOpinionOneShot', () => {
  beforeEach(() => {
    apiGet.mockReset()
    opinionsStore.load.mockReset()
    opinionsStore.data = {}
  })

  it('nominal: resolves the matching ids, fires one fetch, writes the refs', async () => {
    opinionsStore.data = { artist: { 10: 'liked', 11: 'disliked', 12: 'liked' } }
    apiGet.mockResolvedValueOnce({ data: { items: [{ id: 10 }, { id: 12 }], total: 2 } })
    const refs = makeRefs()
    const { run, capped } = useOpinionOneShot({
      endpoint: '/api/artists/',
      kind: 'artist',
      refs,
      buildParams: () => ({ sort: 'alpha', limit: 100, offset: 0 }),
    })

    await run('liked')

    // One shot, ids appended to the base params by the composable.
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet).toHaveBeenCalledWith('/api/artists/', {
      params: { sort: 'alpha', limit: 100, offset: 0, ids: '10,12' },
    })
    expect(refs.items.value).toEqual([{ id: 10 }, { id: 12 }])
    expect(refs.total.value).toBe(2)
    expect(refs.hasMore.value).toBe(false)
    expect(refs.loading.value).toBe(false)
    expect(capped.value).toBe(false)
  })

  it('no matching id: empties the refs without a request', async () => {
    opinionsStore.data = { artist: { 11: 'disliked' } } // nothing liked
    const refs = makeRefs()
    refs.total.value = 5 // stale value that must be cleared
    const { run, capped } = useOpinionOneShot({
      endpoint: '/api/artists/',
      kind: 'artist',
      refs,
      buildParams: () => ({ sort: 'alpha', limit: 100, offset: 0 }),
    })

    await run('liked')

    expect(apiGet).not.toHaveBeenCalled()
    expect(refs.items.value).toEqual([])
    expect(refs.total.value).toBe(0)
    expect(refs.hasMore.value).toBe(false)
    expect(capped.value).toBe(false)
  })

  it('exclude_ids variant: excludes every rated id, sends no ids param', async () => {
    opinionsStore.data = { set: { 1: 'liked', 2: 'disliked', 3: 'liked' } }
    apiGet.mockResolvedValueOnce({ data: { items: [{ id: 9 }], total: 1 } })
    const refs = makeRefs()
    const { run } = useOpinionOneShot({
      endpoint: '/api/sets/',
      kind: 'set',
      refs,
      unratedValue: 'none',
      buildParams: () => ({ sort: '-date', limit: 200, offset: 0 }),
    })

    await run('none')

    expect(apiGet).toHaveBeenCalledTimes(1)
    const [, cfg] = apiGet.mock.calls[0]
    expect(cfg.params.exclude_ids).toBe('1,2,3')
    expect(cfg.params.ids).toBeUndefined()
    expect(refs.items.value).toEqual([{ id: 9 }])
  })

  it('exclude_ids variant with nothing rated: no exclude param (full corpus)', async () => {
    opinionsStore.data = { set: {} }
    apiGet.mockResolvedValueOnce({ data: { items: [{ id: 9 }], total: 1 } })
    const refs = makeRefs()
    const { run } = useOpinionOneShot({
      endpoint: '/api/sets/',
      kind: 'set',
      refs,
      unratedValue: 'none',
      buildParams: () => ({ sort: '-date', limit: 200, offset: 0 }),
    })

    await run('none')

    const [, cfg] = apiGet.mock.calls[0]
    expect(cfg.params.exclude_ids).toBeUndefined()
    expect(cfg.params.ids).toBeUndefined()
  })

  it('cap: flags capped when the true total exceeds the returned page', async () => {
    opinionsStore.data = { set: { 1: 'liked', 2: 'liked' } }
    // The endpoint caps the page at the limit but reports the full match count.
    apiGet.mockResolvedValueOnce({ data: { items: [{ id: 1 }], total: 150 } })
    const refs = makeRefs()
    const { run, capped } = useOpinionOneShot({
      endpoint: '/api/sets/',
      kind: 'set',
      refs,
      buildParams: () => ({ sort: '-date', limit: 200, offset: 0 }),
    })

    await run('liked')

    expect(refs.total.value).toBe(150)
    expect(capped.value).toBe(true)
  })

  it('calls onData with the response for a view-specific field', async () => {
    opinionsStore.data = { artist: { 10: 'liked' } }
    const resp = { items: [{ id: 10 }], total: 1, pillarCounts: { techno: 1 } }
    apiGet.mockResolvedValueOnce({ data: resp })
    const onData = vi.fn()
    const refs = makeRefs()
    const { run } = useOpinionOneShot({
      endpoint: '/api/artists/',
      kind: 'artist',
      refs,
      buildParams: () => ({ sort: 'alpha', limit: 100, offset: 0 }),
      onData,
    })

    await run('liked')

    expect(onData).toHaveBeenCalledWith(resp)
  })

  it('on a request error empties the refs and clears loading', async () => {
    opinionsStore.data = { artist: { 10: 'liked' } }
    apiGet.mockRejectedValueOnce(new Error('boom'))
    const refs = makeRefs()
    refs.total.value = 7
    const { run, capped } = useOpinionOneShot({
      endpoint: '/api/artists/',
      kind: 'artist',
      refs,
      buildParams: () => ({ sort: 'alpha', limit: 100, offset: 0 }),
    })

    await run('liked')

    expect(refs.items.value).toEqual([])
    expect(refs.total.value).toBe(0)
    expect(refs.hasMore.value).toBe(false)
    expect(refs.loading.value).toBe(false)
    expect(capped.value).toBe(false)
  })

  it('toggles the loading ref true during the fetch and false after', async () => {
    opinionsStore.data = { artist: { 10: 'liked' } }
    const refs = makeRefs()
    let loadingDuringFetch = null
    apiGet.mockImplementationOnce(() => {
      loadingDuringFetch = refs.loading.value
      return Promise.resolve({ data: { items: [{ id: 10 }], total: 1 } })
    })
    const { run } = useOpinionOneShot({
      endpoint: '/api/artists/',
      kind: 'artist',
      refs,
      buildParams: () => ({ sort: 'alpha', limit: 100, offset: 0 }),
    })

    await run('liked')

    expect(loadingDuringFetch).toBe(true)
    expect(refs.loading.value).toBe(false)
  })
})

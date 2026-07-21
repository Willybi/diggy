import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { reactive, nextTick } from 'vue'
import {
  useFilterState,
  serializeValue,
  deserializeValue,
} from '../../composables/useFilterState.js'

const criteria = [
  { key: 'q', type: 'text', label: 'Recherche' },
  { key: 'bpm', type: 'range', label: 'BPM', min: 60, max: 200 },
  { key: 'keys', type: 'multi', label: 'Key' },
  {
    key: 'inlib',
    type: 'segment',
    label: 'Bibliothèque',
    options: [
      { value: null, label: 'Tous' },
      { value: 'in', label: 'Dans ma bib' },
    ],
  },
  { key: 'preview', type: 'toggle', label: 'Extrait' },
]

function setup(query = {}, extraCriteria = criteria) {
  const route = reactive({ query })
  const router = { replace: vi.fn() }
  const fs = useFilterState(extraCriteria, { router, route })
  return { route, router, ...fs }
}

describe('useFilterState', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('initialises every criterion to its default when the URL is bare', () => {
    const { state } = setup()
    expect(state).toEqual({
      q: '',
      bpm: [60, 200],
      keys: [],
      inlib: null,
      preview: false,
    })
  })

  it('restores the full state from the query params (shared URL)', () => {
    const { state } = setup({
      q: 'kaskade',
      bpm: '120-133',
      keys: '5A,6A',
      inlib: 'in',
      preview: '1',
    })
    expect(state).toEqual({
      q: 'kaskade',
      bpm: [120, 133],
      keys: ['5A', '6A'],
      inlib: 'in',
      preview: true,
    })
  })

  it('writes non-debounced mutations to the URL immediately (next tick)', async () => {
    const { state, router } = setup()
    state.keys = ['5A', '6A']
    state.preview = true
    await nextTick()
    expect(router.replace).toHaveBeenCalledWith({ query: { keys: '5A,6A', preview: '1' } })
  })

  it('omits default values from the query (absent param = default)', async () => {
    const { state, router } = setup({ keys: '5A' })
    state.keys = []
    await nextTick()
    expect(router.replace).toHaveBeenCalledWith({ query: {} })
  })

  it('debounces text mutations by 250ms', async () => {
    const { state, router } = setup()
    state.q = 'drum'
    await nextTick()
    expect(router.replace).not.toHaveBeenCalled()

    vi.advanceTimersByTime(249)
    expect(router.replace).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(router.replace).toHaveBeenCalledWith({ query: { q: 'drum' } })
  })

  it('debounces range mutations by 250ms', async () => {
    const { state, router } = setup()
    state.bpm = [120, 133]
    await nextTick()
    expect(router.replace).not.toHaveBeenCalled()

    vi.advanceTimersByTime(250)
    expect(router.replace).toHaveBeenCalledWith({ query: { bpm: '120-133' } })
  })

  it('an immediate mutation flushes a pending debounced one in the same write', async () => {
    const { state, router } = setup()
    state.q = 'drum'
    await nextTick()
    state.preview = true
    await nextTick()
    expect(router.replace).toHaveBeenCalledTimes(1)
    expect(router.replace).toHaveBeenCalledWith({ query: { q: 'drum', preview: '1' } })
  })

  it('preserves foreign query params it does not own', async () => {
    const { state, router } = setup({ tab: 'sets' })
    state.keys = ['5A']
    await nextTick()
    expect(router.replace).toHaveBeenCalledWith({ query: { tab: 'sets', keys: '5A' } })
  })

  it('re-applies the URL into the state on route change (back/forward)', async () => {
    const { state, route, router } = setup({ bpm: '120-133' })
    expect(state.bpm).toEqual([120, 133])

    route.query = { bpm: '90-100', keys: '3B' }
    await nextTick()
    expect(state.bpm).toEqual([90, 100])
    expect(state.keys).toEqual(['3B'])

    // The echo serialises back to the exact same query → no write-back.
    vi.advanceTimersByTime(300)
    await nextTick()
    expect(router.replace).not.toHaveBeenCalled()
  })

  it('reset() restores every default and clears the owned params', async () => {
    const { state, reset, router } = setup({
      q: 'kaskade',
      bpm: '120-133',
      keys: '5A',
      preview: '1',
      tab: 'sets',
    })
    reset()
    await nextTick()
    expect(state.bpm).toEqual([60, 200])
    expect(state.q).toBe('')
    expect(router.replace).toHaveBeenLastCalledWith({ query: { tab: 'sets' } })
  })

  it('honours per-criterion custom serializers (artists: ids in URL)', async () => {
    const artistCriterion = {
      key: 'artists',
      type: 'multi',
      label: 'Artiste',
      serialize: (v) => (v.length ? v.map((a) => a.id).join(',') : undefined),
      deserialize: (raw) =>
        raw
          ? String(raw)
              .split(',')
              .map((id) => ({ id: Number(id) }))
          : [],
    }
    const { state, router } = setup({ artists: '4,9' }, [artistCriterion])
    expect(state.artists).toEqual([{ id: 4 }, { id: 9 }])

    state.artists = [{ id: 4, name: 'Kaskade' }]
    await nextTick()
    expect(router.replace).toHaveBeenCalledWith({ query: { artists: '4' } })
  })
})

describe('serializeValue / deserializeValue', () => {
  const range = { type: 'range', min: 60, max: 200 }

  it('range: full range → absent; malformed or inverted raw → default', () => {
    expect(serializeValue(range, [60, 200])).toBeUndefined()
    expect(serializeValue(range, [120, 133])).toBe('120-133')
    expect(deserializeValue(range, 'abc')).toEqual([60, 200])
    expect(deserializeValue(range, '150-100')).toEqual([60, 200])
  })

  it('range: clamps out-of-bounds raw values to the criterion bounds', () => {
    expect(deserializeValue(range, '10-500')).toEqual([60, 200])
  })

  it('segment: unknown raw value falls back to inactive (null)', () => {
    const seg = { type: 'segment', options: [{ value: 'in', label: 'In' }] }
    expect(deserializeValue(seg, 'hack')).toBeNull()
    expect(deserializeValue(seg, 'in')).toBe('in')
  })

  it('toggle: only truthy markers deserialize to true', () => {
    const tgl = { type: 'toggle' }
    expect(deserializeValue(tgl, '1')).toBe(true)
    expect(deserializeValue(tgl, 'true')).toBe(true)
    expect(deserializeValue(tgl, '0')).toBe(false)
  })

  it('text: serialisation trims and empties to absent', () => {
    const txt = { type: 'text' }
    expect(serializeValue(txt, '  drum  ')).toBe('drum')
    expect(serializeValue(txt, '   ')).toBeUndefined()
  })
})

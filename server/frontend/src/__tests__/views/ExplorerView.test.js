import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'
import { reactive } from 'vue'

// Mutable holders shared with the hoisted mocks below. `routeState` is a plain
// container whose `.route`/`.replace` are (re)assigned per test in beforeEach:
// `.route` is a REACTIVE object (so watch(() => route.query) actually fires) and
// `.replace` writes the new query into it — the browser round-trip that lets a
// post-mount filter change drive the refetch watch. Read at useRoute()/replace()
// call time (during mount), never at hoist time, so vue's reactive is available.
const { apiMock, routerPush, routeState, playerMock } = vi.hoisted(() => ({
  apiMock: {
    get: vi.fn(),
    patch: vi.fn(),
  },
  routerPush: vi.fn(),
  routeState: {},
  playerMock: {
    isCurrent: () => false,
    playing: false,
    play: vi.fn(),
  },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

vi.mock('../../stores/audioPlayer', () => ({
  useAudioPlayer: () => playerMock,
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeState.route,
  useRouter: () => ({ push: routerPush, replace: routeState.replace }),
}))

function makeItems() {
  return [
    {
      id: 1,
      title: 'Alpha',
      artist: 'Kaskade',
      artist_id: 10,
      artists: [{ id: 10, name: 'Kaskade' }],
      genres: [
        { name: 'House', pillar: 'house', depth: 0 },
        { name: 'Tech House', pillar: 'house', depth: 1 },
        { name: 'Deep House', pillar: 'house', depth: 1 },
      ],
      style: null,
      bpm: 128.4,
      key: '5A',
      duration_ms: 245000,
      has_artwork: false,
      has_preview: true,
      in_lib: true,
      avis: null,
      trend_rank: 14,
    },
    {
      id: 2,
      title: 'Beta',
      artist: 'Unknown',
      artist_id: null,
      artists: [],
      genres: [],
      style: null,
      bpm: null,
      key: null,
      duration_ms: null,
      has_artwork: false,
      has_preview: false,
      in_lib: false,
      avis: null,
      trend_rank: 120,
    },
  ]
}

// The main list fetch uses URLSearchParams (repeated params); the two head
// counter fetches use plain objects — that difference routes the mock.
let listResponse

function installApiMock() {
  apiMock.get.mockImplementation((url, cfg = {}) => {
    if (url === '/api/catalog/genres') {
      return Promise.resolve({
        data: [{ name: 'House', count: 100, pillar: 'house', depth: 0 }],
      })
    }
    if (url === '/api/artists/') {
      return Promise.resolve({ data: { items: [{ id: 7, name: 'Kaskade', has_artwork: false }] } })
    }
    if (url === '/api/catalog/') {
      const params = cfg.params
      if (params instanceof URLSearchParams) {
        return Promise.resolve({ data: listResponse })
      }
      if (params?.in_lib === true) return Promise.resolve({ data: { total: 56, items: [] } })
      return Promise.resolve({ data: { total: 500, items: [] } })
    }
    return Promise.resolve({ data: {} })
  })
}

function mainListCalls() {
  return apiMock.get.mock.calls.filter(
    ([url, cfg]) => url === '/api/catalog/' && cfg?.params instanceof URLSearchParams,
  )
}

function lastMainParams() {
  const calls = mainListCalls()
  return calls[calls.length - 1][1].params
}

async function mountView(query = {}) {
  routeState.route.path = '/explorer'
  routeState.route.query = query
  const { default: ExplorerView } = await import('../../views/ExplorerView.vue')
  const wrapper = mount(ExplorerView, {
    global: {
      components: { RouterLink: RouterLinkStub },
      stubs: { ImportRekordboxModal: true, ExternalImportModal: true },
    },
  })
  await flushPromises()
  return wrapper
}

describe('ExplorerView', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.patch.mockReset()
    apiMock.patch.mockResolvedValue({ data: {} })
    routerPush.mockReset()
    // Fresh REACTIVE route per test (isolates instances that are never unmounted);
    // router.replace writes the query back into it so the URL→refetch watch fires.
    routeState.route = reactive({ path: '/explorer', query: {} })
    routeState.replace = vi.fn((loc) => {
      routeState.route.query = { ...(loc.query || {}) }
    })
    listResponse = { total: 2, items: makeItems() }
    installApiMock()
  })

  it('initializes state from a filtered URL and fetches with the exact API params', async () => {
    await mountView({
      q: 'daft',
      bpm: '100-140',
      key: ['5A', '6A'],
      genre: 'Tech House',
      artist_id: '7',
      lib: 'in',
      dur: '3-5',
      preview: '1',
      avis: 'liked',
      year: '1990-2005',
      label: 'defected',
      sort: 'bpm',
      order: 'desc',
    })

    const p = lastMainParams()
    expect(p.get('skip')).toBe('0')
    expect(p.get('limit')).toBe('100')
    expect(p.get('search')).toBe('daft')
    expect(p.get('bpm_min')).toBe('100')
    expect(p.get('bpm_max')).toBe('140')
    expect(p.getAll('key')).toEqual(['5A', '6A'])
    expect(p.getAll('genre')).toEqual(['Tech House'])
    expect(p.getAll('artist_id')).toEqual(['7'])
    expect(p.get('in_lib')).toBe('true')
    expect(p.get('duration_min')).toBe('180000')
    expect(p.get('duration_max')).toBe('300000')
    expect(p.get('has_preview')).toBe('true')
    expect(p.get('avis')).toBe('liked')
    expect(p.get('year_min')).toBe('1990')
    expect(p.get('year_max')).toBe('2005')
    expect(p.get('label')).toBe('defected')
    expect(p.get('sort')).toBe('bpm')
    expect(p.get('order')).toBe('desc')
  })

  it('hydrates artist chips from the URL via GET /api/artists/?ids=', async () => {
    const wrapper = await mountView({ artist_id: '7' })
    expect(apiMock.get).toHaveBeenCalledWith('/api/artists/', {
      params: { ids: '7', limit: 100 },
    })
    // The chip shows the hydrated name, not the #id placeholder.
    expect(wrapper.text()).toContain('Kaskade')
  })

  it('maps open-ended duration presets to a single API bound', async () => {
    await mountView({ dur: 'lt3' })
    let p = lastMainParams()
    expect(p.get('duration_max')).toBe('180000')
    expect(p.has('duration_min')).toBe(false)

    await mountView({ dur: 'gt8' })
    p = lastMainParams()
    expect(p.get('duration_min')).toBe('480000')
    expect(p.has('duration_max')).toBe(false)
  })

  it('sends no sort/order params for the default sort (created_at desc backend-side)', async () => {
    await mountView({})
    const p = lastMainParams()
    expect(p.has('sort')).toBe(false)
    expect(p.has('order')).toBe(false)
  })

  it('renders rows: title, #rank badge only when ≤ 50, « +N » styles, — for nulls', async () => {
    const wrapper = await mountView({})
    const rows = wrapper.findAll('.xp-row:not(.xp-row--skel)')
    expect(rows).toHaveLength(2)

    const first = rows[0]
    expect(first.text()).toContain('Alpha')
    expect(first.find('.xp-rank').text()).toBe('#14')
    expect(first.find('.xp-more').text()).toBe('+2')
    expect(first.find('.xp-bpm').text()).toBe('128')
    expect(first.find('.xp-key').text()).toBe('5A')

    const second = rows[1]
    expect(second.find('.xp-rank').exists()).toBe(false)
    // genres empty + style null → em dash, bpm/key null → em dash.
    expect(second.findAll('.xp-null').length).toBeGreaterThanOrEqual(3)
    // No preview → no play button at all.
    expect(second.find('.pbtn').exists()).toBe(false)
  })

  it('patches the avis optimistically and colors the row', async () => {
    const wrapper = await mountView({})
    const firstRow = wrapper.findAll('.xp-row:not(.xp-row--skel)')[0]
    await firstRow.find('.ld-btn.like').trigger('click')
    expect(apiMock.patch).toHaveBeenCalledWith('/api/catalog/1/avis', { avis: 'liked' })
    await flushPromises()
    expect(wrapper.findAll('.xp-row:not(.xp-row--skel)')[0].classes()).toContain('liked')
  })

  it('shows the actionable empty state with removable chips', async () => {
    listResponse = { total: 0, items: [] }
    const wrapper = await mountView({ genre: 'House' })

    const empty = wrapper.find('.xp-empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('Aucun résultat avec ces filtres')
    expect(empty.text()).toContain('Réinitialiser tous les filtres')

    const chip = empty.find('.fchip--empty')
    expect(chip.exists()).toBe(true)
    expect(chip.text()).toContain('House')

    // Removing the chip clears the criterion from the state (chips disappear).
    await chip.trigger('click')
    expect(wrapper.find('.xp-empty .fchip--empty').exists()).toBe(false)
  })

  it('renders the head counter from the base and in-lib totals (fr-FR)', async () => {
    const wrapper = await mountView({})
    expect(wrapper.find('.xp-sub').text()).toBe('500 tracks · 56 dans ma bibliothèque')
  })

  it('refetches with the new params when a filter changes after mount (URL round-trip)', async () => {
    const wrapper = await mountView({})
    const before = mainListCalls().length

    // Click the BPM header → onHeaderSort sets state.sort/order → useFilterState
    // writes the URL via router.replace → the reactive route.query change drives
    // the refetch watch. This whole chain was inert with the old non-reactive mock.
    await wrapper.find('.xp-th--btn.col-bpm').trigger('click')
    await flushPromises()

    expect(mainListCalls().length).toBe(before + 1)
    const p = lastMainParams()
    expect(p.get('sort')).toBe('bpm')
    expect(p.get('order')).toBe('asc')
  })
})

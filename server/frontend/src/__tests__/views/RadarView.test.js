import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'
import { reactive } from 'vue'

// Mutable holders shared with the hoisted mocks below. `routeState.route` is a
// REACTIVE object (so watch(() => route.query) fires) and `.replace` writes the
// new query into it — the URL round-trip that lets a post-mount sort change
// drive the refetch watch. Read at useRoute()/replace() call time (during
// mount), never at hoist time, so vue's reactive is available.
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
      ],
      style: null,
      bpm: 128.4,
      key: '5A',
      has_artwork: false,
      has_preview: true,
      in_lib: true,
      avis: null,
      trend_rank: 14,
      trend_score_10: 9,
      reco_score_10: 7,
      velocity: 2.4,
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
      has_artwork: false,
      has_preview: false,
      in_lib: false,
      avis: null,
      trend_rank: 120,
      trend_score_10: 5,
      reco_score_10: null,
      velocity: null,
    },
  ]
}

// The main feed fetch uses URLSearchParams (repeated params); the head-counter
// fetch uses a plain object ({ limit: 1 }) — that difference routes the mock.
let listResponse
let countsResponse

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
    if (url === '/api/radar/feed') {
      const params = cfg.params
      if (params instanceof URLSearchParams) {
        return Promise.resolve({ data: listResponse })
      }
      // Head counters fetch (plain { limit: 1 }).
      return Promise.resolve({ data: countsResponse })
    }
    return Promise.resolve({ data: {} })
  })
}

function mainListCalls() {
  return apiMock.get.mock.calls.filter(
    ([url, cfg]) => url === '/api/radar/feed' && cfg?.params instanceof URLSearchParams,
  )
}

function lastMainParams() {
  const calls = mainListCalls()
  return calls[calls.length - 1][1].params
}

// toLocaleString('fr-FR') separates thousands with a NARROW NO-BREAK SPACE
// (U+202F), not a plain space — match the real output.
const NNBSP = ' '

async function mountView(query = {}) {
  routeState.route.path = '/radar'
  routeState.route.query = query
  const { default: RadarView } = await import('../../views/RadarView.vue')
  const wrapper = mount(RadarView, {
    global: {
      components: { RouterLink: RouterLinkStub },
    },
  })
  await flushPromises()
  return wrapper
}

describe('RadarView', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.patch.mockReset()
    apiMock.patch.mockResolvedValue({ data: {} })
    routerPush.mockReset()
    // Fresh REACTIVE route per test; router.replace writes the query back into
    // it so the URL→refetch watch fires.
    routeState.route = reactive({ path: '/radar', query: {} })
    routeState.replace = vi.fn((loc) => {
      routeState.route.query = { ...(loc.query || {}) }
    })
    listResponse = { total: 2, trend_count: 1240, reco_count: 100, items: makeItems() }
    countsResponse = { total: 2, trend_count: 1240, reco_count: 100, items: [] }
    installApiMock()
  })

  it('fetches the feed with the exact API params from a filtered URL', async () => {
    await mountView({
      q: 'daft',
      bpm: '100-140',
      key: ['5A', '6A'],
      genre: 'Tech House',
      lib: 'in',
      avis: 'liked',
      year: '1990-2005',
      label: 'defected',
    })

    const p = lastMainParams()
    expect(p.get('skip')).toBe('0')
    expect(p.get('limit')).toBe('100')
    expect(p.get('search')).toBe('daft')
    expect(p.get('bpm_min')).toBe('100')
    expect(p.get('bpm_max')).toBe('140')
    expect(p.getAll('key')).toEqual(['5A', '6A'])
    expect(p.getAll('genre')).toEqual(['Tech House'])
    expect(p.get('in_lib')).toBe('true')
    expect(p.get('avis')).toBe('liked')
    expect(p.get('year_min')).toBe('1990')
    expect(p.get('year_max')).toBe('2005')
    expect(p.get('label')).toBe('defected')
    // Default sort is `tendance` → no sort/order params (back applies its default).
    expect(p.has('sort')).toBe(false)
    expect(p.has('order')).toBe(false)
  })

  it('renders bi-score rows: title, #rank, bpm/key, both score rings + velocity ▲', async () => {
    const wrapper = await mountView({})
    const rows = wrapper.findAll('.rd-row:not(.rd-row--skel)')
    expect(rows).toHaveLength(2)

    const first = rows[0]
    expect(first.text()).toContain('Alpha')
    expect(first.find('.rd-rank').text()).toBe('#14')
    expect(first.find('.rd-bpm').text()).toBe('128')
    expect(first.find('.rd-key').text()).toBe('5A')
    // Both score cells carry a ring; the Tendance note is round(9) = 9.
    expect(first.find('.col-trend .score-ring').exists()).toBe(true)
    expect(first.find('.col-reco .score-ring').exists()).toBe(true)
    expect(first.find('.col-trend .sr-note').text()).toBe('9')
    expect(first.find('.col-reco .sr-note').text()).toBe('7')
    // velocity 2.4 ≥ 1.5 → rising ▲ on the Tendance ring only.
    expect(first.find('.col-trend .rd-velo').exists()).toBe(true)
  })

  it('shows a muted « — » where a score is null (mono-score row), no ring', async () => {
    const wrapper = await mountView({})
    const rows = wrapper.findAll('.rd-row:not(.rd-row--skel)')
    const second = rows[1]

    // Beta has a Tendance score but no Pour toi score.
    expect(second.find('.col-trend .score-ring').exists()).toBe(true)
    expect(second.find('.col-reco .score-ring').exists()).toBe(false)
    const dash = second.find('.col-reco .rd-dash')
    expect(dash.exists()).toBe(true)
    expect(dash.text()).toBe('—')
    expect(dash.attributes('aria-label')).toBe('Pas de score Pour toi')
    // No velocity marker when the row is not rising.
    expect(second.find('.rd-velo').exists()).toBe(false)
  })

  it('highlights the active sort column and toggles order on header clicks', async () => {
    const wrapper = await mountView({})
    // Default: Tendance is the resolved sort → its header/cells are active.
    expect(wrapper.find('.rd-th--score.col-trend').classes()).toContain('is-sorted')
    expect(wrapper.find('.rd-row:not(.rd-row--skel) .col-trend').classes()).toContain('is-active-col')
    expect(wrapper.find('.rd-th--score.col-reco').classes()).not.toContain('is-sorted')

    const before = mainListCalls().length
    // Click « Pour toi » header → sort switches to pour_toi (desc default).
    await wrapper.find('.rd-th--score.col-reco').trigger('click')
    await flushPromises()

    expect(mainListCalls().length).toBe(before + 1)
    let p = lastMainParams()
    expect(p.get('sort')).toBe('pour_toi')
    expect(p.get('order')).toBe('desc')
    // The band moved to the Pour toi column.
    expect(wrapper.find('.rd-th--score.col-reco').classes()).toContain('is-sorted')
    expect(wrapper.find('.rd-row:not(.rd-row--skel) .col-reco').classes()).toContain('is-active-col')

    // Clicking the same header again toggles the order asc.
    await wrapper.find('.rd-th--score.col-reco').trigger('click')
    await flushPromises()
    p = lastMainParams()
    expect(p.get('sort')).toBe('pour_toi')
    expect(p.get('order')).toBe('asc')
  })

  it('renders the bi-score head counter (union bounds, fr-FR)', async () => {
    const wrapper = await mountView({})
    expect(wrapper.find('.rd-sub').text()).toBe(`1${NNBSP}240 tendances · 100 pour toi`)
  })

  it('shows the cold-start invite and « en attente » counter when reco_count is 0', async () => {
    listResponse = {
      total: 2,
      trend_count: 1240,
      reco_count: 0,
      items: makeItems().map((e) => ({ ...e, reco_score_10: null })),
    }
    countsResponse = { total: 2, trend_count: 1240, reco_count: 0, items: [] }
    const wrapper = await mountView({})

    const cold = wrapper.find('.rd-cold')
    expect(cold.exists()).toBe(true)
    expect(cold.text()).toContain('Débloque Pour toi')
    expect(wrapper.find('.rd-sub').text()).toBe(`1${NNBSP}240 tendances · Pour toi en attente de tes likes`)

    // The Pour toi column is entirely « — » (no ring anywhere).
    expect(wrapper.findAll('.col-reco .score-ring')).toHaveLength(0)

    // Dismiss hides the banner.
    await wrapper.find('.rd-cold-x').trigger('click')
    expect(wrapper.find('.rd-cold').exists()).toBe(false)
  })

  it('does not show the cold-start invite when the user has recos', async () => {
    const wrapper = await mountView({})
    expect(wrapper.find('.rd-cold').exists()).toBe(false)
  })

  it('patches the avis optimistically and colors the row', async () => {
    const wrapper = await mountView({})
    const firstRow = wrapper.findAll('.rd-row:not(.rd-row--skel)')[0]
    await firstRow.find('.ld-btn.like').trigger('click')
    expect(apiMock.patch).toHaveBeenCalledWith('/api/catalog/1/avis', { avis: 'liked' })
    await flushPromises()
    expect(wrapper.findAll('.rd-row:not(.rd-row--skel)')[0].classes()).toContain('liked')
  })

  it('shows the actionable empty state with removable chips', async () => {
    listResponse = { total: 0, trend_count: 1240, reco_count: 100, items: [] }
    const wrapper = await mountView({ genre: 'House' })

    const empty = wrapper.find('.rd-empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('Aucun résultat avec ces filtres')

    const chip = empty.find('.fchip--empty')
    expect(chip.exists()).toBe(true)
    expect(chip.text()).toContain('House')

    // Removing the chip clears the criterion from the state (chips disappear).
    await chip.trigger('click')
    expect(wrapper.find('.rd-empty .fchip--empty').exists()).toBe(false)
  })

  it('maps the Récent sort option to sort=recent (not the default)', async () => {
    const wrapper = await mountView({})
    const before = mainListCalls().length
    // Drive the select through the SortSelect <select>.
    await wrapper.find('.rd-sort select').setValue('recent')
    await flushPromises()
    expect(mainListCalls().length).toBe(before + 1)
    const p = lastMainParams()
    expect(p.get('sort')).toBe('recent')
    expect(p.get('order')).toBe('desc')
    // No score column highlighted when sorting by a non-score field.
    expect(wrapper.find('.rd-th--score.col-trend').classes()).not.toContain('is-sorted')
    expect(wrapper.find('.rd-th--score.col-reco').classes()).not.toContain('is-sorted')
  })
})

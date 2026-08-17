import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'
import { nextTick, reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

// Mutable holders shared with the hoisted mocks. `routeState.route` is REACTIVE
// (so watch(() => route.query) fires) and `.replace` writes the new query back
// into it — the browser round-trip that lets a post-mount filter/sort change
// drive the refetch watch, exactly like ExplorerView.test.js.
const { apiMock, routerPush, routeState, playerMock } = vi.hoisted(() => ({
  apiMock: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
  routerPush: vi.fn(),
  routeState: {},
  playerMock: {
    source: null,
    playing: false,
    isCurrent: () => false,
    toggle: vi.fn(),
    play: vi.fn(),
  },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

vi.mock('../../stores/audioPlayer.js', () => ({
  useAudioPlayer: () => playerMock,
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeState.route,
  useRouter: () => ({ push: routerPush, replace: routeState.replace }),
  onBeforeRouteLeave: vi.fn(),
}))

function makeItems() {
  return [
    {
      id: 1,
      title: 'Boiler Room Berlin',
      artists: [
        { id: 10, name: 'Kaskade' },
        { id: 11, name: 'Deadmau5' },
      ],
      top_genres: [
        { name: 'House', pillar: 'house', depth: 0 },
        { name: 'Tech House', pillar: 'house', depth: 1 },
      ],
      played_date: '2026-05-01',
      duration_ms: 3_600_000,
      has_artwork: true,
      total_tracks: 10,
      identified_tracks: 7,
    },
    {
      id: 2,
      title: 'Anonymous Warehouse',
      artists: [],
      top_genres: [],
      played_date: null,
      duration_ms: null,
      has_artwork: false,
      total_tracks: 4,
      identified_tracks: 1,
    },
  ]
}

let opinionsResponse
let listResponse
let detailResponse

function installApiMock() {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/opinions/') return Promise.resolve({ data: opinionsResponse })
    if (url === '/api/catalog/genres') return Promise.resolve({ data: [] })
    if (url === '/api/sets/') return Promise.resolve({ data: listResponse })
    if (url === '/api/sets/search') return Promise.resolve({ data: [] })
    if (url === '/api/sets/1') return Promise.resolve({ data: detailResponse })
    return Promise.resolve({ data: {} })
  })
}

// The real list fetches (initial page / avis one-shot). The head base-count call
// hits the same URL with limit:1 — filter it out so ordering can't confuse us.
function listCalls() {
  return apiMock.get.mock.calls.filter(
    ([url, cfg]) => url === '/api/sets/' && cfg?.params?.limit !== 1,
  )
}
function lastListParams() {
  const calls = listCalls()
  return calls[calls.length - 1][1].params
}

async function openPanel(wrapper) {
  // jsdom width 0 → FilterBar routes the toggle to the inline panel.
  await wrapper.find('.fbar-toggle').trigger('click')
  await flushPromises()
}

function fieldByLabel(wrapper, label) {
  return wrapper.findAll('.flt-field').find((f) => f.find('.flt-label').text() === label)
}

async function clickAvis(wrapper, label) {
  const field = fieldByLabel(wrapper, 'Avis')
  const pill = field.findAll('.seg-pill').find((b) => b.text() === label)
  await pill.trigger('click')
  await flushPromises()
}

async function mountView(query = {}) {
  routeState.route.path = '/sets'
  routeState.route.query = query
  const { default: SetsView } = await import('../../views/SetsView.vue')
  const wrapper = mount(SetsView, {
    global: {
      plugins: [createPinia()],
      components: { RouterLink: RouterLinkStub },
    },
  })
  await flushPromises()
  return wrapper
}

describe('SetsView', () => {
  beforeEach(() => {
    // usePaginatedList instantiates an IntersectionObserver in onMounted — jsdom
    // has none, so provide an inert stub.
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    )
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.patch.mockReset()
    apiMock.patch.mockResolvedValue({ data: {} })
    routerPush.mockReset()
    playerMock.play.mockReset()
    playerMock.toggle.mockReset()
    playerMock.source = null
    playerMock.playing = false
    // Fresh REACTIVE route per test; router.replace writes the query back so the
    // URL→refetch watch fires.
    routeState.route = reactive({ path: '/sets', query: {} })
    routeState.replace = vi.fn((loc) => {
      routeState.route.query = { ...(loc.query || {}) }
    })
    setActivePinia(createPinia())
    opinionsResponse = { set: { 1: 'liked', 2: 'disliked', 3: 'liked' } }
    listResponse = { total: 2, items: makeItems() }
    detailResponse = {
      id: 1,
      title: 'Boiler Room Berlin',
      tracklist: [
        {
          id: 90,
          catalog_id: 500,
          is_id: false,
          has_preview: true,
          catalog_title: 'Opener',
          catalog_artist: 'A1',
          raw_title: 'Opener',
          bpm: 128,
          key: '8A',
        },
        {
          id: 91,
          catalog_id: 501,
          is_id: false,
          has_preview: true,
          catalog_title: 'Peak',
          catalog_artist: 'A2',
          raw_title: 'Peak',
          bpm: 130,
          key: '9A',
        },
        // Unidentified / preview-less rows are dropped from the queue.
        { id: 92, catalog_id: null, is_id: true, has_preview: false, raw_title: 'ID' },
      ],
    }
    installApiMock()
  })

  it('fetches the paginated list with no ids/exclude on mount (all mode, default -date)', async () => {
    await mountView()
    const p = lastListParams()
    expect(p.sort).toBe('-date')
    expect(p.limit).toBe(24)
    expect(p.offset).toBe(0)
    expect(p.ids).toBeUndefined()
    expect(p.exclude_ids).toBeUndefined()
  })

  it('resolves the Aimés avis filter to ids= from the opinions store', async () => {
    const wrapper = await mountView()
    await openPanel(wrapper)
    await clickAvis(wrapper, 'Aimés')

    const p = lastListParams()
    // Only sets opinion-tagged liked → ids 1 and 3, no exclusion.
    expect(p.ids).toBe('1,3')
    expect(p.exclude_ids).toBeUndefined()
    // One shot, not paginated: limit is bumped and the sentinel stays off.
    expect(p.limit).toBe(200)
    expect(wrapper.find('.st-sentinel.on').exists()).toBe(false)
  })

  it('resolves À explorer to exclude_ids= (every rated set, liked ∪ disliked)', async () => {
    const wrapper = await mountView()
    await openPanel(wrapper)
    await clickAvis(wrapper, 'À explorer')

    const p = lastListParams()
    expect(p.exclude_ids).toBe('1,2,3')
    expect(p.ids).toBeUndefined()
  })

  it('shows the avis-empty state (no request) when no set carries the opinion', async () => {
    opinionsResponse = { set: { 2: 'disliked' } } // no liked set
    const wrapper = await mountView()
    await openPanel(wrapper)
    const before = listCalls().length
    await clickAvis(wrapper, 'Aimés')

    // No matching id → the view short-circuits without hitting the list endpoint.
    expect(listCalls().length).toBe(before)
    const empty = wrapper.find('.st-empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('Aucun set liké')
  })

  it('translates a duration preset into duration_min/max params', async () => {
    const wrapper = await mountView()
    await openPanel(wrapper)
    // Durée options: [< 1h, 1–2h, 2–3h, > 3h] → index 1 = the 1h–2h window.
    const field = fieldByLabel(wrapper, 'Durée')
    await field.findAll('.seg-pill')[1].trigger('click')
    await flushPromises()

    const p = lastListParams()
    expect(p.duration_min).toBe(3_600_000)
    expect(p.duration_max).toBe(7_200_000)
  })

  it('renders an enriched row: title, clickable artist links, genre StyleTag, identified-tracks ring', async () => {
    const wrapper = await mountView()
    const rows = wrapper.findAll('.st-row:not(.st-row--skel)')
    expect(rows).toHaveLength(2)

    const first = rows[0]
    expect(first.text()).toContain('Boiler Room Berlin')

    // Artists are individual links to /artist/:id (via ArtistLinks).
    const links = first.findAllComponents(RouterLinkStub)
    const artistLink = links.find((l) => l.props('to') === '/artist/10')
    expect(artistLink).toBeTruthy()
    expect(artistLink.text()).toBe('Kaskade')
    expect(links.some((l) => l.props('to') === '/artist/11')).toBe(true)

    // Genre chip is a StyleTag linking to /style/:name.
    expect(first.find('.style-tag').exists()).toBe(true)
    expect(links.some((l) => l.props('to') === '/style/House')).toBe(true)

    // Tracks column = ScoreRing (pct of identified tracks: 7/10 → 70 %).
    expect(first.find('.col-tracks .score-ring').exists()).toBe(true)
    expect(first.find('.col-tracks .sr-note').text()).toContain('70')

    // Second row has no artists line and no genre chip (both omitted, no dash).
    const second = rows[1]
    expect(second.find('.st-artists').exists()).toBe(false)
    expect(second.find('.style-tag').exists()).toBe(false)
  })

  it('navigates to the set on row click', async () => {
    const wrapper = await mountView()
    await wrapper.find('.st-row:not(.st-row--skel)').trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/set/1')
  })

  it('plays a set in order: fetches its tracklist and queues the playable tracks', async () => {
    const wrapper = await mountView()
    // Play button is the leftmost cell of the row; @click.stop → no navigation.
    await wrapper.find('.st-row:not(.st-row--skel) .pbtn').trigger('click')
    await flushPromises()

    expect(routerPush).not.toHaveBeenCalled()
    expect(playerMock.play).toHaveBeenCalledTimes(1)
    const [firstTrack, source] = playerMock.play.mock.calls[0]
    // First playable track leads the queue.
    expect(firstTrack.catalog_id).toBe(500)
    // The source is a set-tagged list; getItems() returns only playable tracks.
    expect(source.type).toBe('list')
    expect(source.setId).toBe(1)
    expect(source.getItems().map((t) => t.catalog_id)).toEqual([500, 501])
  })

  it('sends the composite sort (-date → -tracks) when a header is clicked', async () => {
    const wrapper = await mountView()
    const before = listCalls().length
    const tracksHeader = wrapper.findAll('.st-th--btn').find((h) => h.text().startsWith('Tracks'))
    await tracksHeader.trigger('click')
    await flushPromises()

    expect(listCalls().length).toBe(before + 1)
    // New column → default descending (leading '-').
    expect(lastListParams().sort).toBe('-tracks')
  })

  it('shows an instant skeleton on mount, replaced by the rows once the list resolves', async () => {
    // Defer the list response so we can observe the pre-resolution state: the
    // skeleton must be on screen BEFORE the fetch settles (D9.b — the perceived
    // delay is what a skeleton kills). loading flips true synchronously inside
    // onMounted's fetch, so one tick paints the ghost rows while the request is
    // still pending.
    let resolveList
    const pending = new Promise((r) => {
      resolveList = r
    })
    apiMock.get.mockImplementation((url, cfg) => {
      // Only the paginated page load (limit 24) is deferred; the head base-count
      // (limit 1) and the genre/opinions calls resolve at once.
      if (url === '/api/sets/' && cfg?.params?.limit !== 1) return pending
      if (url === '/api/opinions/') return Promise.resolve({ data: opinionsResponse })
      if (url === '/api/catalog/genres') return Promise.resolve({ data: [] })
      if (url === '/api/sets/') return Promise.resolve({ data: listResponse })
      return Promise.resolve({ data: {} })
    })

    routeState.route.path = '/sets'
    routeState.route.query = {}
    const { default: SetsView } = await import('../../views/SetsView.vue')
    const wrapper = mount(SetsView, {
      global: {
        plugins: [createPinia()],
        components: { RouterLink: RouterLinkStub },
      },
    })
    await nextTick()

    // Skeleton up, no real rows yet, and the header already shows (not a blank).
    expect(wrapper.findAll('.st-row--skel').length).toBeGreaterThan(0)
    expect(wrapper.findAll('.st-row:not(.st-row--skel)')).toHaveLength(0)
    expect(wrapper.find('.st-thead').exists()).toBe(true)

    // Once the data lands the skeleton is gone and the real rows take over.
    resolveList({ data: listResponse })
    await flushPromises()

    expect(wrapper.find('.st-row--skel').exists()).toBe(false)
    expect(wrapper.findAll('.st-row:not(.st-row--skel)')).toHaveLength(2)
  })
})

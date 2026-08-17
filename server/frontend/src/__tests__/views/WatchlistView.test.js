import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'
import { nextTick, reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

// Mutable holders shared with the hoisted mocks below.
const { apiMock, routerPush, routeState, routerReplace } = vi.hoisted(() => ({
  apiMock: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
  routerPush: vi.fn(),
  routeState: {},
  routerReplace: vi.fn(),
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

vi.mock('vue-router', () => ({
  useRoute: () => routeState.route,
  useRouter: () => ({ push: routerPush, replace: routerReplace }),
  onBeforeRouteLeave: vi.fn(),
}))

// A playlist crawled long ago (out of the 12h cooldown → the Crawl button shows)
// with a recent change (→ a cadence pill), plus a bare/never-crawled playlist.
function makeItems() {
  return [
    {
      id: 1,
      title: 'Defected Radio',
      source: 'deezer',
      owner: 'Defected Records',
      track_count: 120,
      has_artwork: true,
      last_crawled_at: '2020-01-01T00:00:00Z',
      last_changed_at: new Date(Date.now() - 3 * 86400000).toISOString(),
      current_task_id: null,
      followed: true,
      top_genres: [
        { name: 'House', pillar: 'house', depth: 0, pct: 60 },
        { name: 'Tech House', pillar: 'house', depth: 1, pct: 40 },
      ],
      external_id: '111',
    },
    {
      id: 2,
      title: null,
      source: 'tidal',
      owner: null,
      track_count: null,
      has_artwork: false,
      last_crawled_at: null,
      last_changed_at: null,
      current_task_id: null,
      followed: false,
      top_genres: [],
      external_id: 'abc-uuid',
    },
  ]
}

// Opinions returned by GET /api/opinions/ (consumed by the store's load()).
let opinionsResponse
let listResponse

function installApiMock() {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/opinions/') return Promise.resolve({ data: opinionsResponse })
    if (url === '/api/watchlist/browse') return Promise.resolve({ data: listResponse })
    if (typeof url === 'string' && url.endsWith('/crawl-status'))
      return Promise.resolve({ data: { status: null } })
    return Promise.resolve({ data: {} })
  })
}

// Only the browse endpoint, in call order — the opinions/status calls hit other URLs.
function browseCalls() {
  return apiMock.get.mock.calls.filter(([url]) => url === '/api/watchlist/browse')
}
function lastBrowseParams() {
  const calls = browseCalls()
  return calls[calls.length - 1][1].params
}

function clickSeg(wrapper, label) {
  const btn = wrapper.findAll('.filterseg button').find((b) => b.text() === label)
  return btn.trigger('click')
}

async function mountView() {
  const { default: WatchlistView } = await import('../../views/WatchlistView.vue')
  const wrapper = mount(WatchlistView, {
    global: {
      plugins: [createPinia()],
      components: { RouterLink: RouterLinkStub },
    },
  })
  await flushPromises()
  return wrapper
}

describe('WatchlistView', () => {
  beforeEach(() => {
    // useInfiniteScroll (via usePaginatedList) instantiates an IntersectionObserver
    // in onMounted — jsdom has none, so provide an inert stub.
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
    apiMock.post.mockResolvedValue({ data: { id: 5 } })
    apiMock.patch.mockResolvedValue({ data: {} })
    routerPush.mockReset()
    routerReplace.mockReset()
    routeState.route = reactive({ path: '/playlists', query: {} })
    setActivePinia(createPinia())
    opinionsResponse = { playlist: { 1: 'liked', 2: 'disliked', 3: 'liked' } }
    listResponse = { total: 2, items: makeItems() }
    installApiMock()
  })

  it('fetches the browse list with no ids/exclude on mount (all mode, default title asc)', async () => {
    await mountView()
    const p = lastBrowseParams()
    expect(p.sort).toBe('title')
    expect(p.limit).toBe(24)
    expect(p.offset).toBe(0)
    expect(p.ids).toBeUndefined()
    expect(p.exclude_ids).toBeUndefined()
  })

  it('resolves the Liked filter to ids= from the opinions store', async () => {
    const wrapper = await mountView()
    await clickSeg(wrapper, 'Liked')
    await flushPromises()

    const p = lastBrowseParams()
    // Only playlists opinion-tagged liked → ids 1 and 3, no exclusion.
    expect(p.ids).toBe('1,3')
    expect(p.exclude_ids).toBeUndefined()
    // One shot, not paginated: limit is bumped and the sentinel stays off.
    expect(p.limit).toBe(200)
    expect(wrapper.find('.pl-sentinel.on').exists()).toBe(false)
  })

  it('resolves À explorer to exclude_ids= (every rated playlist, liked ∪ disliked)', async () => {
    const wrapper = await mountView()
    await clickSeg(wrapper, 'À explorer')
    await flushPromises()

    const p = lastBrowseParams()
    expect(p.exclude_ids).toBe('1,2,3')
    expect(p.ids).toBeUndefined()
  })

  it('shows the avis-empty state (no request) when no playlist carries the opinion', async () => {
    opinionsResponse = { playlist: { 2: 'disliked' } } // no liked playlist
    const wrapper = await mountView()
    const before = browseCalls().length
    await clickSeg(wrapper, 'Liked')
    await flushPromises()

    // No matching id → the view short-circuits without hitting the browse endpoint.
    expect(browseCalls().length).toBe(before)
    const empty = wrapper.find('.pl-empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('Aucune playlist likée')
  })

  it('renders an enriched row: title, source glyph, genre StyleTag, raw track count, creator', async () => {
    const wrapper = await mountView()
    const rows = wrapper.findAll('.pl-row:not(.pl-row--skel)')
    expect(rows).toHaveLength(2)

    const first = rows[0]
    expect(first.text()).toContain('Defected Radio')

    // Source logo = a non-clickable glyph (PlatformLink variant="glyph").
    expect(first.find('.plink--glyph').exists()).toBe(true)

    // Genre chip is a StyleTag linking to /style/:name.
    expect(first.find('.style-tag').exists()).toBe(true)
    const links = first.findAllComponents(RouterLinkStub)
    expect(links.some((l) => l.props('to') === '/style/House')).toBe(true)

    // Tracks column = a raw number (no ring).
    expect(first.find('.pl-num').text()).toBe('120')
    expect(first.find('.col-tracks .score-ring').exists()).toBe(false)

    // Creator = plain text, no dash.
    expect(first.find('.pl-creator').text()).toBe('Defected Records')

    // Second row: fallback title, no genre chip (omitted, no dash), null track = "—",
    // no creator.
    const second = rows[1]
    expect(second.text()).toContain('abc-uuid')
    expect(second.find('.style-tag').exists()).toBe(false)
    expect(second.find('.pl-null').text()).toBe('—')
    expect(second.find('.pl-creator').exists()).toBe(false)
  })

  it('navigates to the playlist on row click', async () => {
    const wrapper = await mountView()
    await wrapper.find('.pl-row:not(.pl-row--skel)').trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/playlists/1')
  })

  it('sends the composite sort when a header is clicked (Tracks → -tracks, Créateur → creator)', async () => {
    const wrapper = await mountView()
    const before = browseCalls().length

    const tracksHeader = wrapper.findAll('.pl-th--btn').find((h) => h.text().startsWith('Tracks'))
    await tracksHeader.trigger('click')
    await flushPromises()
    expect(browseCalls().length).toBe(before + 1)
    // New magnitude column → default descending (leading '-').
    expect(lastBrowseParams().sort).toBe('-tracks')

    const creatorHeader = wrapper
      .findAll('.pl-th--btn')
      .find((h) => h.text().startsWith('Créateur'))
    await creatorHeader.trigger('click')
    await flushPromises()
    // Alphabetical column → default ascending (no leading '-').
    expect(lastBrowseParams().sort).toBe('creator')
  })

  it('never renders a freshness pill, even when last_changed_at is present', async () => {
    const wrapper = await mountView()
    const rows = wrapper.findAll('.pl-row:not(.pl-row--skel)')
    // Row 1 carries last_changed_at, row 2 is null — neither shows a cadence pill.
    expect(rows[0].find('.pl-cadence').exists()).toBe(false)
    expect(rows[1].find('.pl-cadence').exists()).toBe(false)
    expect(wrapper.find('.pl-cadence').exists()).toBe(false)
  })

  it('triggers a crawl (POST) and surfaces the live "queued" status', async () => {
    const wrapper = await mountView()
    const rows = wrapper.findAll('.pl-row:not(.pl-row--skel)')
    const btn = rows[0].find('.pl-crawl-btn')
    expect(btn.exists()).toBe(true)

    await btn.trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith('/api/watchlist/1/crawl')
    expect(rows[0].find('.pl-live.queued').exists()).toBe(true)
    wrapper.unmount() // clear the keyed poll timer started by triggerCrawl
  })

  it('opens the add modal and rejects an invalid URL without POSTing', async () => {
    const wrapper = await mountView()
    await wrapper.find('.pl-add').trigger('click')
    expect(wrapper.find('.add-overlay').exists()).toBe(true)

    await wrapper.find('#pl-url-input').setValue('not a url')
    await wrapper.find('.pl-url-go').trigger('click')
    await flushPromises()

    expect(apiMock.post).not.toHaveBeenCalled()
    expect(wrapper.find('.pl-form-error').exists()).toBe(true)
    expect(wrapper.find('.add-overlay').exists()).toBe(true)
  })

  it('adds a playlist from a valid URL (POST parsed external_id + source) and closes', async () => {
    apiMock.post.mockResolvedValueOnce({ data: { id: 5 } })
    const wrapper = await mountView()
    await wrapper.find('.pl-add').trigger('click')
    await wrapper.find('#pl-url-input').setValue('https://www.deezer.com/playlist/999')
    await wrapper.find('.pl-url-go').trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith('/api/watchlist/', {
      external_id: '999',
      source: 'deezer',
    })
    expect(wrapper.find('.add-overlay').exists()).toBe(false)
    wrapper.unmount() // clear the poll timer started for the new playlist
  })

  it('surfaces the duplicate (409) error in the add modal', async () => {
    apiMock.post.mockRejectedValueOnce({ response: { status: 409 } })
    const wrapper = await mountView()
    await wrapper.find('.pl-add').trigger('click')
    await wrapper.find('#pl-url-input').setValue('https://www.deezer.com/playlist/999')
    await wrapper.find('.pl-url-go').trigger('click')
    await flushPromises()

    expect(wrapper.find('.pl-form-error').text()).toContain('déjà')
    expect(wrapper.find('.add-overlay').exists()).toBe(true)
  })

  it('shows an instant skeleton on mount, replaced by the rows once the browse list resolves', async () => {
    // Defer the browse response so we can observe the pre-resolution state: the
    // skeleton must be on screen BEFORE the fetch settles (D9.b — the perceived
    // delay is what a skeleton kills). loading flips true synchronously inside
    // onMounted's fetch, so one tick paints the ghost rows while the request is
    // still pending.
    let resolveList
    const pending = new Promise((r) => {
      resolveList = r
    })
    apiMock.get.mockImplementation((url) => {
      if (url === '/api/watchlist/browse') return pending
      if (url === '/api/opinions/') return Promise.resolve({ data: opinionsResponse })
      if (typeof url === 'string' && url.endsWith('/crawl-status'))
        return Promise.resolve({ data: { status: null } })
      return Promise.resolve({ data: {} })
    })

    const { default: WatchlistView } = await import('../../views/WatchlistView.vue')
    const wrapper = mount(WatchlistView, {
      global: {
        plugins: [createPinia()],
        components: { RouterLink: RouterLinkStub },
      },
    })
    await nextTick()

    // Skeleton up, no real rows yet, and the header already shows (not a blank).
    expect(wrapper.findAll('.pl-row--skel').length).toBeGreaterThan(0)
    expect(wrapper.findAll('.pl-row:not(.pl-row--skel)')).toHaveLength(0)
    expect(wrapper.find('.pl-thead').exists()).toBe(true)

    // Once the data lands the skeleton is gone and the real rows take over.
    resolveList({ data: listResponse })
    await flushPromises()

    expect(wrapper.find('.pl-row--skel').exists()).toBe(false)
    expect(wrapper.findAll('.pl-row:not(.pl-row--skel)')).toHaveLength(2)
  })
})

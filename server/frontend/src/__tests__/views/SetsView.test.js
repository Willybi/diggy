import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// Mutable holders shared with the hoisted mocks below.
const { apiMock, routerPush } = vi.hoisted(() => ({
  apiMock: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
  routerPush: vi.fn(),
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
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

// Opinions returned by GET /api/opinions/ (consumed by the store's load()).
let opinionsResponse
let listResponse

function installApiMock() {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/opinions/') return Promise.resolve({ data: opinionsResponse })
    if (url === '/api/sets/') return Promise.resolve({ data: listResponse })
    if (url === '/api/sets/search') return Promise.resolve({ data: [] })
    return Promise.resolve({ data: {} })
  })
}

// Only the list endpoint, in call order — the opinions/search calls hit other URLs.
function setsCalls() {
  return apiMock.get.mock.calls.filter(([url]) => url === '/api/sets/')
}
function lastSetsParams() {
  const calls = setsCalls()
  return calls[calls.length - 1][1].params
}

function clickSeg(wrapper, label) {
  const btn = wrapper.findAll('.filterseg button').find((b) => b.text() === label)
  return btn.trigger('click')
}

async function mountView() {
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
    apiMock.patch.mockResolvedValue({ data: {} })
    routerPush.mockReset()
    setActivePinia(createPinia())
    opinionsResponse = { set: { 1: 'liked', 2: 'disliked', 3: 'liked' } }
    listResponse = { total: 2, items: makeItems() }
    installApiMock()
  })

  it('fetches the paginated list with no ids/exclude on mount (all mode, default -date)', async () => {
    await mountView()
    const p = lastSetsParams()
    expect(p.sort).toBe('-date')
    expect(p.limit).toBe(24)
    expect(p.offset).toBe(0)
    expect(p.ids).toBeUndefined()
    expect(p.exclude_ids).toBeUndefined()
  })

  it('resolves the Liked filter to ids= from the opinions store', async () => {
    const wrapper = await mountView()
    await clickSeg(wrapper, 'Liked')
    await flushPromises()

    const p = lastSetsParams()
    // Only sets opinion-tagged liked → ids 1 and 3, no exclusion.
    expect(p.ids).toBe('1,3')
    expect(p.exclude_ids).toBeUndefined()
    // One shot, not paginated: limit is bumped and the sentinel stays off.
    expect(p.limit).toBe(200)
    expect(wrapper.find('.st-sentinel.on').exists()).toBe(false)
  })

  it('resolves À explorer to exclude_ids= (every rated set, liked ∪ disliked)', async () => {
    const wrapper = await mountView()
    await clickSeg(wrapper, 'À explorer')
    await flushPromises()

    const p = lastSetsParams()
    expect(p.exclude_ids).toBe('1,2,3')
    expect(p.ids).toBeUndefined()
  })

  it('shows the avis-empty state (no request) when no set carries the opinion', async () => {
    opinionsResponse = { set: { 2: 'disliked' } } // no liked set
    const wrapper = await mountView()
    const before = setsCalls().length
    await clickSeg(wrapper, 'Liked')
    await flushPromises()

    // No matching id → the view short-circuits without hitting the list endpoint.
    expect(setsCalls().length).toBe(before)
    const empty = wrapper.find('.st-empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('Aucun set liké')
  })

  it('renders an enriched row: title, clickable artist links, genre StyleTag, pct ScoreRing', async () => {
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

    // Tracks column = pct ScoreRing (7/10 → « 70 % »).
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

  it('sends the composite sort (-date → tracks desc) when a header is clicked', async () => {
    const wrapper = await mountView()
    const before = setsCalls().length
    const tracksHeader = wrapper.findAll('.st-th--btn').find((h) => h.text().startsWith('Tracks'))
    await tracksHeader.trigger('click')
    await flushPromises()

    expect(setsCalls().length).toBe(before + 1)
    // New column → default descending (leading '-').
    expect(lastSetsParams().sort).toBe('-tracks')
  })
})

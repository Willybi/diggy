import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'

// Mutable holders shared with the hoisted mocks below.
const { authState, apiMock } = vi.hoisted(() => ({
  authState: { value: { isAuthenticated: false, user: null } },
  apiMock: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

vi.mock('../../stores/auth.js', () => ({
  useAuthStore: () => authState.value,
}))

vi.mock('../../stores/toast.js', () => ({
  useToast: () => ({ show: vi.fn() }),
}))

vi.mock('../../stores/audioPlayer', () => ({
  useAudioPlayer: () => ({
    track: null,
    playing: false,
    artistPlaying: null,
    play: vi.fn(),
    playRandomArtist: vi.fn(),
  }),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

// A crawled release track: linked to a catalog entry, renders as a track card.
const RELEASE_ITEM = {
  id: 1,
  type: 'release',
  title: 'Song A',
  artist: 'Amelie Lens',
  artist_name: 'Amelie Lens',
  catalog_id: 909,
  has_artwork: true,
  has_preview: true,
  bpm: 138,
  key: '11A',
  release_date: '2026-07-11',
}
// A release we could not crawl: falls back to an external Deezer link.
const RELEASE_LINK_ITEM = {
  id: 3,
  type: 'release',
  title: 'Uncrawled EP',
  artist_name: 'Amelie Lens',
  external_url: 'https://www.deezer.com/album/123',
}
const SET_ITEM = {
  id: 2,
  type: 'set',
  title: 'Awakenings 2026',
  artist_name: 'Amelie Lens',
  set_id: 77,
}
// Two crawled tracks of the SAME release: a followed album is fanned out into
// one artist_activity per track, so they must collapse into a single card.
const ALBUM_TRACK_A = {
  id: 10,
  type: 'release',
  title: 'Track One',
  artist: 'Charlotte de Witte',
  artist_name: 'Charlotte de Witte',
  catalog_id: 501,
  has_artwork: true,
  has_preview: true,
  release_date: '2026-07-12',
  payload: { album_id: '9001', album_title: 'Formula EP' },
}
const ALBUM_TRACK_B = {
  id: 11,
  type: 'release',
  title: 'Track Two',
  artist: 'Charlotte de Witte',
  artist_name: 'Charlotte de Witte',
  catalog_id: 502,
  has_artwork: true,
  has_preview: false,
  release_date: '2026-07-12',
  payload: { album_id: '9001', album_title: 'Formula EP' },
}

function mockApiGet({ activityItems = [], newCount = 0, recoItems = [] } = {}) {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/genres') return Promise.resolve({ data: { items: [] } })
    if (url === '/api/radar/trends') {
      return Promise.resolve({ data: { items: [], family_counts: {} } })
    }
    if (url === '/api/following/activity/new-count') {
      return Promise.resolve({ data: { count: newCount } })
    }
    if (url === '/api/following/activity') {
      return Promise.resolve({ data: { items: activityItems } })
    }
    if (url === '/api/recommendations') {
      return Promise.resolve({ data: { items: recoItems } })
    }
    return Promise.resolve({ data: {} })
  })
}

const RECO_ITEM = {
  id: 42,
  title: 'Strobe',
  artist: 'Deadmau5',
  bpm: 128,
  key: '8A',
  has_artwork: true,
  has_preview: true,
  in_lib: false,
  reco_score: 0.91,
}

async function mountHub() {
  const { default: HubView } = await import('../../views/HubView.vue')
  // vue-router is mocked, so <router-link> never resolves to a component and
  // VTU `stubs` would not apply — register the stub as a global component.
  const wrapper = mount(HubView, {
    global: {
      components: { RouterLink: RouterLinkStub },
      stubs: { SegFilter: true, SourceBadge: true, FamilyChips: true },
    },
  })
  await flushPromises()
  return wrapper
}

describe('HubView followed-artists activity shelf', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.post.mockResolvedValue({ data: {} })
    authState.value = { isAuthenticated: false, user: null }
  })

  it('is not rendered and never hits the network for guests', async () => {
    mockApiGet({ activityItems: [RELEASE_ITEM] })
    const wrapper = await mountHub()
    expect(wrapper.find('.discover--activity').exists()).toBe(false)
    const followingCalls = apiMock.get.mock.calls.filter(([url]) =>
      url.startsWith('/api/following'),
    )
    expect(followingCalls).toHaveLength(0)
  })

  it('is not rendered when the feed is empty', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    mockApiGet({ activityItems: [] })
    const wrapper = await mountHub()
    expect(wrapper.find('.discover--activity').exists()).toBe(false)
    // Nothing displayed → nothing to mark as seen.
    expect(apiMock.post).not.toHaveBeenCalled()
  })

  it('renders a crawled release as a track card and a set as a RouterLink', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    mockApiGet({ activityItems: [RELEASE_ITEM, SET_ITEM] })
    const wrapper = await mountHub()

    const shelf = wrapper.find('.discover--activity')
    expect(shelf.exists()).toBe(true)
    expect(shelf.find('.discover-title').text()).toContain('Nouveautés de tes artistes')

    // Crawled release → clickable track card (div): cover keyed on catalog_id,
    // play button, badge « Nouveauté », relative release age.
    const cards = shelf.findAll('.activity-card')
    const release = cards.find((c) => c.text().includes('Song A'))
    expect(release).toBeTruthy()
    expect(release.element.tagName).toBe('DIV')
    expect(release.find('.ac-badge').text()).toBe('Nouveauté')
    expect(release.find('img').attributes('src')).toBe('/storage/catalog-artworks/909.jpg')
    expect(release.find('.tc-play').exists()).toBe(true)
    expect(release.text()).toContain('Amelie Lens')
    expect(release.text()).toContain('Sorti')

    // Set card → internal RouterLink with badge « Set »
    const setLink = shelf.findComponent(RouterLinkStub)
    expect(setLink.exists()).toBe(true)
    expect(setLink.props('to')).toBe('/set/77')
    expect(setLink.find('.ac-badge').text()).toBe('Set')
    expect(setLink.text()).toContain('Awakenings 2026')
  })

  it('renders an uncrawled release as an external Deezer link', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    mockApiGet({ activityItems: [RELEASE_LINK_ITEM] })
    const wrapper = await mountHub()

    const link = wrapper.find('a.activity-card')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe(RELEASE_LINK_ITEM.external_url)
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toBe('noopener')
    expect(link.find('.ac-badge').text()).toBe('Nouveauté')
    expect(link.text()).toContain('Uncrawled EP')
  })

  it('shows the « N nouvelles » badge while items are not yet marked seen', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    mockApiGet({ activityItems: [RELEASE_ITEM], newCount: 3 })
    // Keep the seen POST pending so the badge stays visible.
    apiMock.post.mockReturnValue(new Promise(() => {}))
    const wrapper = await mountHub()

    const badge = wrapper.find('.ac-new-badge')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('3 nouvelles')
  })

  it('POSTs seen after the feed is displayed and hides the badge', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    mockApiGet({ activityItems: [RELEASE_ITEM], newCount: 3 })
    const wrapper = await mountHub()

    expect(apiMock.post).toHaveBeenCalledTimes(1)
    expect(apiMock.post).toHaveBeenCalledWith('/api/following/activity/seen')
    expect(wrapper.find('.ac-new-badge').exists()).toBe(false)
    // The shelf itself stays visible.
    expect(wrapper.find('.discover--activity').exists()).toBe(true)
  })

  it('keeps the Hub alive when the activity endpoints fail', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    apiMock.get.mockImplementation((url) => {
      if (url.startsWith('/api/following')) return Promise.reject(new Error('boom'))
      return Promise.resolve({ data: { items: [] } })
    })
    const wrapper = await mountHub()
    expect(wrapper.find('.discover--activity').exists()).toBe(false)
    expect(wrapper.find('.searchwrap').exists()).toBe(true)
  })
})

describe('HubView « Pour toi » recommendations shelf', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.post.mockResolvedValue({ data: {} })
    authState.value = { isAuthenticated: false, user: null }
  })

  it('is not rendered and never hits the network for guests', async () => {
    mockApiGet({ recoItems: [RECO_ITEM] })
    const wrapper = await mountHub()
    expect(wrapper.find('.discover--foryou').exists()).toBe(false)
    const recoCalls = apiMock.get.mock.calls.filter(([url]) => url === '/api/recommendations')
    expect(recoCalls).toHaveLength(0)
  })

  it('is not rendered when the feed is empty', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    mockApiGet({ recoItems: [] })
    const wrapper = await mountHub()
    expect(wrapper.find('.discover--foryou').exists()).toBe(false)
  })

  it('renders reco cards when the feed has items', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    mockApiGet({ recoItems: [RECO_ITEM] })
    const wrapper = await mountHub()

    const shelf = wrapper.find('.discover--foryou')
    expect(shelf.exists()).toBe(true)
    expect(shelf.find('.discover-title').text()).toBe('Pour toi')

    const cards = shelf.findAll('.trend-card')
    expect(cards).toHaveLength(1)
    expect(cards[0].text()).toContain('Strobe')
    expect(cards[0].text()).toContain('Deadmau5')
    // Artwork keyed on `id` (not catalog_id).
    expect(shelf.find('.tc-art img').attributes('src')).toBe('/storage/catalog-artworks/42.jpg')
  })

  it('keeps the Hub alive when the recommendations endpoint fails', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    apiMock.get.mockImplementation((url) => {
      if (url === '/api/recommendations') return Promise.reject(new Error('boom'))
      if (url === '/api/following/activity/new-count')
        return Promise.resolve({ data: { count: 0 } })
      return Promise.resolve({ data: { items: [] } })
    })
    const wrapper = await mountHub()
    expect(wrapper.find('.discover--foryou').exists()).toBe(false)
    expect(wrapper.find('.searchwrap').exists()).toBe(true)
  })

  it('shows a skeleton while the recommendations are still loading', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    apiMock.get.mockImplementation((url) => {
      if (url === '/api/recommendations') return new Promise(() => {}) // never resolves
      if (url === '/api/following/activity/new-count')
        return Promise.resolve({ data: { count: 0 } })
      if (url === '/api/following/activity') return Promise.resolve({ data: { items: [] } })
      return Promise.resolve({ data: { items: [], family_counts: {} } })
    })
    const wrapper = await mountHub()
    const shelf = wrapper.find('.discover--foryou')
    expect(shelf.exists()).toBe(true)
    expect(shelf.attributes('aria-busy')).toBe('true')
    expect(shelf.findAll('.trend-card.is-skeleton').length).toBeGreaterThan(0)
    // No real reco cards yet.
    expect(shelf.find('.tc-title').exists()).toBe(false)
  })
})

describe('HubView activity album grouping', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.post.mockResolvedValue({ data: {} })
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
  })

  it('collapses tracks sharing an album_id into one expandable album card', async () => {
    mockApiGet({ activityItems: [ALBUM_TRACK_A, ALBUM_TRACK_B] })
    const wrapper = await mountHub()

    const shelf = wrapper.find('.discover--activity')
    const albumCards = shelf.findAll('.album-card')
    expect(albumCards).toHaveLength(1)
    // One card, not two near-identical track cards.
    expect(shelf.findAll('.activity-card')).toHaveLength(1)

    const card = albumCards[0]
    expect(card.text()).toContain('Formula EP')
    expect(card.text()).toContain('2 titres')
    // Cover keyed on the first artwork-bearing track's catalog_id.
    expect(card.find('.tc-art img').attributes('src')).toBe('/storage/catalog-artworks/501.jpg')

    // Collapsed by default → track titles hidden until expanded.
    expect(card.find('.ac-list').exists()).toBe(false)
    await card.find('.ac-toggle').trigger('click')
    expect(card.find('.ac-list').exists()).toBe(true)
    expect(card.text()).toContain('Track One')
    expect(card.text()).toContain('Track Two')
  })

  it('renders a lone release with an album_id as a single track card (no collapse)', async () => {
    mockApiGet({
      activityItems: [{ ...RELEASE_ITEM, payload: { album_id: '7', album_title: 'Solo' } }],
    })
    const wrapper = await mountHub()

    const shelf = wrapper.find('.discover--activity')
    expect(shelf.find('.album-card').exists()).toBe(false)
    const card = shelf.find('.activity-card')
    expect(card.element.tagName).toBe('DIV')
    expect(card.text()).toContain('Song A')
    expect(card.find('img').attributes('src')).toBe('/storage/catalog-artworks/909.jpg')
  })

  it('dedups a collab track surfaced via two followed artists', async () => {
    // Same catalog_id, no album grouping → shown once (collab dedup preserved).
    const collabA = { ...RELEASE_ITEM, id: 20 }
    const collabB = { ...RELEASE_ITEM, id: 21 }
    mockApiGet({ activityItems: [collabA, collabB] })
    const wrapper = await mountHub()

    const shelf = wrapper.find('.discover--activity')
    expect(shelf.findAll('.activity-card')).toHaveLength(1)
  })
})

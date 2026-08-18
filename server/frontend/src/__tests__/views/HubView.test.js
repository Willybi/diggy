import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'

// Mutable holders shared with the hoisted mocks below.
const { authState, apiMock } = vi.hoisted(() => ({
  authState: { value: { isAuthenticated: false, user: null } },
  apiMock: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

// The section components (lazy-loaded by the Hub) resolve for real in these tests,
// so the store/router mocks must cover them too — they share the same module ids.
vi.mock('../../stores/auth.js', () => ({ useAuthStore: () => authState.value }))
vi.mock('../../stores/toast.js', () => ({ useToast: () => ({ show: vi.fn() }) }))
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
const RECO_ITEM = {
  id: 42,
  title: 'Strobe',
  artist: 'Deadmau5',
  bpm: 128,
  key: '8A',
  has_artwork: true,
  has_preview: true,
  in_lib: false,
}
const TREND_ITEM = {
  catalog_id: 300,
  title: 'La La Land',
  artist: 'Green Velvet',
  has_artwork: true,
  has_preview: true,
  rank: 1,
  bpm: 125,
  key: '4A',
  release_date: '2026-08-01',
}

function mockApiGet({ trendItems = [], activityItems = [], newCount = 0, recoItems = [] } = {}) {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/radar/trends') {
      return Promise.resolve({ data: { items: trendItems, family_counts: {} } })
    }
    if (url === '/api/following/activity/new-count') {
      return Promise.resolve({ data: { count: newCount } })
    }
    if (url === '/api/following/activity') {
      return Promise.resolve({ data: { items: activityItems } })
    }
    if (url === '/api/recommendations/') {
      return Promise.resolve({ data: { items: recoItems } })
    }
    return Promise.resolve({ data: {} })
  })
}

async function mountHub() {
  const { default: HubView } = await import('../../views/HubView.vue')
  const wrapper = mount(HubView, {
    global: {
      // vue-router is mocked, so <RouterLink> (used by the sections) never resolves
      // to a component — register the stub as a global component.
      components: { RouterLink: RouterLinkStub },
      stubs: { SegFilter: true, SourceBadge: true, FamilyChips: true },
    },
  })
  // Wait for the lazy section chunks (defineAsyncComponent) to resolve, then let
  // their onMounted fetches settle and render.
  await vi.dynamicImportSettled()
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('HubView section gating', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.post.mockResolvedValue({ data: {} })
    authState.value = { isAuthenticated: false, user: null }
  })

  it('mounts the trends section for guests but not the auth-only reco/activity sections', async () => {
    mockApiGet({ trendItems: [TREND_ITEM], activityItems: [RELEASE_ITEM], recoItems: [RECO_ITEM] })
    const wrapper = await mountHub()

    // Trends are shown to everyone.
    expect(wrapper.find('.discover').exists()).toBe(true)
    // Auth-only shelves are never mounted for a guest…
    expect(wrapper.find('.discover--foryou').exists()).toBe(false)
    expect(wrapper.find('.discover--activity').exists()).toBe(false)
    // …so their endpoints are never hit.
    const following = apiMock.get.mock.calls.filter(([u]) => u.startsWith('/api/following'))
    const reco = apiMock.get.mock.calls.filter(([u]) => u === '/api/recommendations/')
    expect(following).toHaveLength(0)
    expect(reco).toHaveLength(0)
  })

  it('mounts the reco + activity sections for an authenticated user', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    mockApiGet({ trendItems: [TREND_ITEM], activityItems: [RELEASE_ITEM], recoItems: [RECO_ITEM] })
    const wrapper = await mountHub()

    expect(wrapper.find('.discover--foryou').exists()).toBe(true)
    expect(wrapper.find('.discover--activity').exists()).toBe(true)
    // The section fetches actually fired.
    const reco = apiMock.get.mock.calls.filter(([u]) => u === '/api/recommendations/')
    const activity = apiMock.get.mock.calls.filter(([u]) => u === '/api/following/activity')
    expect(reco.length).toBeGreaterThan(0)
    expect(activity.length).toBeGreaterThan(0)
  })
})

describe('HubView search scope counters', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.post.mockResolvedValue({ data: {} })
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
  })

  it('shows a per-scope count in the dropdown only in search state', async () => {
    apiMock.get.mockImplementation((url) => {
      if (url === '/api/search') {
        return Promise.resolve({
          data: {
            items: [],
            total: 1552,
            totals: { track: 1290, artist: 96, set: 84, album: 12, playlist: 63, genre: 19 },
          },
        })
      }
      if (url === '/api/radar/trends') {
        return Promise.resolve({ data: { items: [], family_counts: {} } })
      }
      if (url === '/api/following/activity/new-count')
        return Promise.resolve({ data: { count: 0 } })
      if (url === '/api/following/activity') return Promise.resolve({ data: { items: [] } })
      if (url === '/api/recommendations/') return Promise.resolve({ data: { items: [] } })
      return Promise.resolve({ data: {} })
    })
    const wrapper = await mountHub()

    // Empty state → no counters in the dropdown.
    expect(wrapper.find('.scope-menu .cnt').exists()).toBe(false)

    // Type a query → debounced search → counters appear (one per scope). The scope
    // dropdown lives in HubView itself (search state stays here after the split).
    await wrapper.find('.search-field input').setValue('house')
    await new Promise((r) => setTimeout(r, 200))
    await flushPromises()

    const counts = wrapper.findAll('.scope-menu .cnt')
    expect(counts).toHaveLength(7) // Tout + 6 types
    // fr-FR grouping inserts thin/no-break spaces (both matched by \s).
    const texts = counts.map((c) => c.text().replace(/\s/g, ''))
    expect(texts[0]).toBe('1552') // « Tout » = sum
    expect(texts[1]).toBe('1290') // Tracks
    expect(texts[2]).toBe('96') // Artistes
  })

  it('keeps the Hub shell alive when a section fetch fails', async () => {
    apiMock.get.mockImplementation((url) => {
      if (url.startsWith('/api/following') || url === '/api/recommendations/') {
        return Promise.reject(new Error('boom'))
      }
      return Promise.resolve({ data: { items: [], family_counts: {} } })
    })
    const wrapper = await mountHub()
    // The search bar (main-chunk shell) is always there regardless of section state.
    expect(wrapper.find('.searchwrap').exists()).toBe(true)
    expect(wrapper.find('.discover--activity').exists()).toBe(false)
    expect(wrapper.find('.discover--foryou').exists()).toBe(false)
  })
})

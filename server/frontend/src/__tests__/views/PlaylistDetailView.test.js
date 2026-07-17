import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'
import TrackCard from '../../components/TrackCard.vue'

// Mutable holders shared with the hoisted mocks below.
const { apiMock, routerPush, playerMock, authMock } = vi.hoisted(() => ({
  apiMock: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
  routerPush: vi.fn(),
  playerMock: {
    isCurrent: () => false,
    playing: false,
    play: vi.fn(),
  },
  authMock: { user: null },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

vi.mock('../../stores/audioPlayer', () => ({
  useAudioPlayer: () => playerMock,
}))

// AdminCard reads the auth store — mock it so is_admin is controllable per test.
vi.mock('../../stores/auth.js', () => ({
  useAuthStore: () => authMock,
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '1' } }),
  useRouter: () => ({ push: routerPush, replace: vi.fn() }),
}))

function makePlaylist(overrides = {}) {
  return {
    id: 1,
    external_id: 'PL123',
    source: 'deezer',
    title: 'Peak Time Techno',
    description: null,
    created_at: '2026-01-01T00:00:00Z',
    last_crawled_at: '2026-07-10T00:00:00Z',
    has_artwork: false,
    track_count: 120,
    owner: 'DJ Someone',
    current_task_id: null,
    followed: false,
    tracks: [],
    top_artists: [],
    top_genres: [],
    ...overrides,
  }
}

function makeTracks(n) {
  return Array.from({ length: n }, (_, i) => ({
    catalog_id: 100 + i,
    title: `Track ${i}`,
    artist: `Artist ${i}`,
    artists: [{ id: 10 + i, name: `Artist ${i}`, has_artwork: false }],
    bpm: 128,
    key: '9A',
    duration_ms: 300000,
    has_artwork: false,
    has_preview: true,
    in_lib: i % 2 === 0,
    // Ascending detected_at → the view must re-order newest first.
    detected_at: `2026-07-${String(10 + i).padStart(2, '0')}T00:00:00Z`,
  }))
}

const globalOpts = {
  global: {
    components: { RouterLink: RouterLinkStub },
    stubs: { StyleTag: true },
  },
}

async function mountView(playlist) {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/watchlist/1') {
      return playlist ? Promise.resolve({ data: playlist }) : Promise.reject(new Error('404'))
    }
    return Promise.resolve({ data: {} })
  })
  const { default: PlaylistDetailView } = await import('../../views/PlaylistDetailView.vue')
  const wrapper = mount(PlaylistDetailView, globalOpts)
  await flushPromises()
  return wrapper
}

describe('PlaylistDetailView', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.delete.mockReset()
    apiMock.post.mockResolvedValue({ data: {} })
    routerPush.mockReset()
    playerMock.playing = false
    authMock.user = null
  })

  // ---- Hero ----

  it('renders the hero title', async () => {
    const wrapper = await mountView(makePlaylist())
    expect(wrapper.find('.hero-title').text()).toBe('Peak Time Techno')
    expect(wrapper.find('.hero-title--id').exists()).toBe(false)
  })

  it('falls back to external_id (mono) when the title is null', async () => {
    const wrapper = await mountView(makePlaylist({ title: null, external_id: 'PL999' }))
    const h1 = wrapper.find('.hero-title')
    expect(h1.text()).toBe('PL999')
    expect(h1.classes()).toContain('hero-title--id')
  })

  it('renders no follow / unfollow button', async () => {
    const wrapper = await mountView(makePlaylist({ followed: true }))
    expect(wrapper.text()).not.toContain('Suivre')
    expect(wrapper.text()).not.toContain('Ne plus suivre')
  })

  it('renders the source PlatformLink with the platform name', async () => {
    const wrapper = await mountView(makePlaylist({ source: 'deezer', external_id: 'PL1' }))
    expect(wrapper.find('.hero-source').exists()).toBe(true)
    expect(wrapper.find('.hero-source-name').text()).toBe('Deezer')
    const link = wrapper.find('.hero-source .plink--btn')
    expect(link.attributes('href')).toBe('https://www.deezer.com/playlist/PL1')
  })

  it('hides the owner when it is redundant with the source', async () => {
    const wrapper = await mountView(makePlaylist({ owner: 'Deezer', source: 'deezer' }))
    expect(wrapper.find('.hero-owner').exists()).toBe(false)
  })

  it('shows the owner when distinct from the source', async () => {
    const wrapper = await mountView(makePlaylist({ owner: 'DJ Someone', source: 'deezer' }))
    expect(wrapper.find('.hero-owner').text()).toBe('DJ Someone')
  })

  // ---- Hero stats (P2) ----

  it('shows « jamais » in --ink-3 when the playlist was never crawled', async () => {
    const wrapper = await mountView(makePlaylist({ last_crawled_at: null }))
    const cells = wrapper.findAll('.stat-cell')
    const crawlCell = cells.find((c) => c.find('.stat-label').text() === 'Dernier crawl')
    expect(crawlCell.find('.stat-val').text()).toBe('jamais')
    expect(crawlCell.find('.stat-val--muted').exists()).toBe(true)
  })

  it('hides the TRACKS cell when track_count is null', async () => {
    const wrapper = await mountView(makePlaylist({ track_count: null }))
    const labels = wrapper.findAll('.stat-label').map((l) => l.text())
    expect(labels).toEqual(['Dernier crawl'])
  })

  it('renders the TRACKS cell with track_count when present', async () => {
    const wrapper = await mountView(makePlaylist({ track_count: 120 }))
    const labels = wrapper.findAll('.stat-label').map((l) => l.text())
    expect(labels).toEqual(['Tracks', 'Dernier crawl'])
    expect(wrapper.findAll('.stat-cell')[0].find('.stat-val').text()).toBe('120')
  })

  // ---- Crawl banner (P4) ----

  it('does not render the crawl banner when no crawl is active', async () => {
    const wrapper = await mountView(makePlaylist({ current_task_id: null }))
    expect(wrapper.find('.crawl-banner').exists()).toBe(false)
  })

  it('renders the running crawl banner once the poll reports it', async () => {
    apiMock.get.mockImplementation((url) => {
      if (url === '/api/watchlist/1') {
        return Promise.resolve({ data: makePlaylist({ current_task_id: 't1' }) })
      }
      if (url.includes('/crawl-status')) return Promise.resolve({ data: { status: 'running' } })
      return Promise.resolve({ data: {} })
    })
    const { default: PlaylistDetailView } = await import('../../views/PlaylistDetailView.vue')
    vi.useFakeTimers()
    try {
      const wrapper = mount(PlaylistDetailView, globalOpts)
      await vi.advanceTimersByTimeAsync(0) // fetchDetail resolves → 'queued', poll starts
      expect(wrapper.find('.crawl-banner.queued').exists()).toBe(true)
      await vi.advanceTimersByTimeAsync(3100) // one poll tick → 'running'
      expect(wrapper.find('.crawl-banner.running').exists()).toBe(true)
      expect(wrapper.find('.crawl-status').text()).toBe('RUNNING')
      wrapper.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  // ---- Description (P5) ----

  it('renders the description only when present', async () => {
    const w1 = await mountView(makePlaylist({ description: 'Best techno' }))
    expect(w1.find('.desc').text()).toBe('Best techno')
    const w2 = await mountView(makePlaylist({ description: null }))
    expect(w2.find('.desc').exists()).toBe(false)
  })

  // ---- « Dans cette playlist » (P6) ----

  it('renders « Dans cette playlist » with top artists and genres', async () => {
    const wrapper = await mountView(
      makePlaylist({
        top_artists: [{ id: 1, name: 'Amelie Lens', has_artwork: false, count: 6 }],
        top_genres: [{ name: 'Techno', pillar: 'techno', depth: 0, pct: 42 }],
      }),
    )
    expect(wrapper.find('.insights').exists()).toBe(true)
    expect(wrapper.findAll('.ins-artist')).toHaveLength(1)
    expect(wrapper.findAll('.ins-genre')).toHaveLength(1)
    // Narrow no-break space (U+202F) before % — French typography (FIX round).
    expect(wrapper.find('.ins-pct').text()).toBe('42 %')
  })

  it('hides « Dans cette playlist » when both top_artists and top_genres are empty', async () => {
    const wrapper = await mountView(makePlaylist({ top_artists: [], top_genres: [] }))
    expect(wrapper.find('.insights').exists()).toBe(false)
  })

  it('shows initials for a top artist without artwork', async () => {
    const wrapper = await mountView(
      makePlaylist({ top_artists: [{ id: 2, name: 'Amelie Lens', has_artwork: false, count: 3 }] }),
    )
    const ph = wrapper.find('.ins-av--ph')
    expect(ph.exists()).toBe(true)
    expect(ph.text()).toBe('AL')
  })

  it('caps top artists at 6 and genres at 5', async () => {
    const artists = Array.from({ length: 9 }, (_, i) => ({
      id: i,
      name: `A${i}`,
      has_artwork: false,
      count: i,
    }))
    const genres = Array.from({ length: 8 }, (_, i) => ({
      name: `G${i}`,
      pillar: 'autres',
      depth: 0,
      pct: i,
    }))
    const wrapper = await mountView(makePlaylist({ top_artists: artists, top_genres: genres }))
    expect(wrapper.findAll('.ins-artist')).toHaveLength(6)
    expect(wrapper.findAll('.ins-genre')).toHaveLength(5)
  })

  // ---- Tracks détectées ----

  it('renders detected tracks as TrackCard (duration + artists + in_lib), newest first, with a counter', async () => {
    const wrapper = await mountView(makePlaylist({ tracks: makeTracks(3), track_count: 120 }))
    const cards = wrapper.findAllComponents(TrackCard)
    expect(cards).toHaveLength(3)
    expect(cards[0].props('showDuration')).toBe(true)
    expect(cards[0].props('showArtist')).toBe(true)
    expect(cards[0].props('track').artists).toHaveLength(1)
    expect(cards[0].props('track')).toHaveProperty('in_lib')
    // catalog_id mapped to id, ordered by detected_at desc (102, 101, 100).
    expect(cards.map((c) => c.props('track').id)).toEqual([102, 101, 100])
    // Counter = number of detected tracks (3), never track_count (120).
    expect(wrapper.find('.sec-count').text()).toContain('3 tracks')
    expect(wrapper.find('.sec-count').text()).not.toContain('120')
  })

  it('renders the never-crawled empty state when there are no detected tracks', async () => {
    const wrapper = await mountView(makePlaylist({ tracks: [], last_crawled_at: null }))
    expect(wrapper.find('.empty-crawl').exists()).toBe(true)
    expect(wrapper.find('.empty-crawl').text()).toContain('Aucune track détectée')
    expect(wrapper.findComponent(TrackCard).exists()).toBe(false)
    // The counter is hidden when the list is empty.
    expect(wrapper.find('.sec-count').exists()).toBe(false)
  })

  // ---- AdminCard ----

  it('shows the AdminCard for an admin on a deezer playlist without artwork', async () => {
    authMock.user = { is_admin: true }
    const wrapper = await mountView(makePlaylist({ has_artwork: false, source: 'deezer' }))
    expect(wrapper.find('.admin-card').exists()).toBe(true)
    expect(wrapper.find('.btn-sync').text()).toContain('Fetch artwork Deezer')
  })

  it('hides the AdminCard for a non-admin', async () => {
    authMock.user = null
    const wrapper = await mountView(makePlaylist({ has_artwork: false, source: 'deezer' }))
    expect(wrapper.find('.admin-card').exists()).toBe(false)
  })

  // ---- States ----

  it('shows the not-found state with a return button to /playlists', async () => {
    const wrapper = await mountView(null)
    expect(wrapper.find('.state--empty').text()).toContain('Playlist introuvable')
    expect(wrapper.findComponent(RouterLinkStub).props('to')).toBe('/playlists')
  })
})

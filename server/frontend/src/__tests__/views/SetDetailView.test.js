import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'
import TrackCard from '../../components/TrackCard.vue'
import SetCard from '../../components/SetCard.vue'
import ScoreRing from '../../components/ScoreRing.vue'
import PlatformLink from '../../components/PlatformLink.vue'

// Mutable holders shared with the hoisted mocks below.
const { apiMock, routerPush, playerMock, authMock } = vi.hoisted(() => ({
  apiMock: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
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

function makeTracklist() {
  return [
    // identified
    {
      id: 100,
      set_id: 1,
      catalog_id: 500,
      position: 1,
      timecode_ms: 65000,
      raw_title: 'Raw A',
      raw_artist: 'Raw Artist A',
      is_id: false,
      catalog_title: 'Track A',
      catalog_artist: 'Artist A',
      catalog_artists: [{ id: 1, name: 'Artist A' }],
      bpm: 140,
      key: '5A',
      duration_ms: 300000,
      has_artwork: true,
      in_lib: true,
      has_preview: true,
    },
    // ID (unidentified marker)
    {
      id: 101,
      set_id: 1,
      catalog_id: null,
      position: 2,
      timecode_ms: 130000,
      raw_title: null,
      raw_artist: null,
      is_id: true,
      catalog_title: null,
      catalog_artist: null,
      catalog_artists: [],
      bpm: null,
      key: null,
      duration_ms: null,
      has_artwork: false,
      in_lib: false,
      has_preview: false,
    },
    // unresolved (read in the source, absent from the catalog)
    {
      id: 102,
      set_id: 1,
      catalog_id: null,
      position: 3,
      timecode_ms: null,
      raw_title: 'Unknown Title',
      raw_artist: 'Unknown Artist',
      is_id: false,
      catalog_title: null,
      catalog_artist: null,
      catalog_artists: [],
      bpm: null,
      key: null,
      duration_ms: null,
      has_artwork: false,
      in_lib: false,
      has_preview: false,
    },
  ]
}

function makeSet(overrides = {}) {
  return {
    id: 1,
    external_id: 'set-1',
    source: 'youtube',
    source_url: 'https://youtube.com/watch?v=abc',
    title: 'Boiler Room: Amelie Lens',
    played_date: '2026-06-01',
    duration_ms: 3_600_000,
    has_artwork: true,
    created_at: '2026-06-02T00:00:00Z',
    last_crawled_at: '2026-06-03T00:00:00Z',
    total_tracks: 26,
    identified_tracks: 18,
    artists: [
      { artist_id: 10, artist_name: 'Amelie Lens', has_artwork: false, role: 'dj', position: 0 },
    ],
    top_genres: [{ name: 'Techno', pillar: 'techno', depth: 0, pct: 60 }],
    tracklist: makeTracklist(),
    ...overrides,
  }
}

function makeSimilar(n) {
  return Array.from({ length: n }, (_, i) => ({
    id: 200 + i,
    title: `Similar ${i}`,
    source: 'youtube',
    played_date: '2026-05-01',
    duration_ms: 3_600_000,
    has_artwork: false,
    total_tracks: 20,
    identified_tracks: 12,
    artists: [`DJ ${i}`],
    score: 1 - i * 0.1,
  }))
}

const globalOpts = {
  global: {
    components: { RouterLink: RouterLinkStub },
    stubs: { StyleTag: true },
  },
}

async function mountView({ set = makeSet(), similar = [], similarError = false } = {}) {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/sets/1') {
      return set ? Promise.resolve({ data: set }) : Promise.reject(new Error('404'))
    }
    if (url === '/api/sets/1/similar') {
      return similarError ? Promise.reject(new Error('500')) : Promise.resolve({ data: similar })
    }
    return Promise.resolve({ data: {} })
  })
  const { default: SetDetailView } = await import('../../views/SetDetailView.vue')
  const wrapper = mount(SetDetailView, globalOpts)
  await flushPromises()
  return wrapper
}

describe('SetDetailView', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.delete.mockReset()
    apiMock.post.mockResolvedValue({ data: {} })
    routerPush.mockReset()
    playerMock.play.mockReset()
    playerMock.playing = false
    authMock.user = null
  })

  // ---- Hero ----

  it('renders the hero title', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('.hero-title').text()).toBe('Boiler Room: Amelie Lens')
  })

  it('renders a single DJ artist without a b2b separator', async () => {
    const wrapper = await mountView()
    expect(wrapper.findAll('.hero-artist-link')).toHaveLength(1)
    expect(wrapper.findAll('.hero-b2b')).toHaveLength(0)
  })

  it('renders a « b2b » separator between two DJ artists (N ≥ 2)', async () => {
    const wrapper = await mountView({
      set: makeSet({
        artists: [
          { artist_id: 10, artist_name: 'Amelie Lens', has_artwork: false, role: 'dj' },
          { artist_id: 11, artist_name: 'Charlotte de Witte', has_artwork: false, role: 'dj' },
        ],
      }),
    })
    expect(wrapper.findAll('.hero-artist-link')).toHaveLength(2)
    const seps = wrapper.findAll('.hero-b2b')
    expect(seps).toHaveLength(1)
    expect(seps[0].text()).toBe('b2b')
  })

  it('omits the artists row when the set has no DJ artist', async () => {
    const wrapper = await mountView({ set: makeSet({ artists: [] }) })
    expect(wrapper.find('.hero-artists').exists()).toBe(false)
  })

  it('renders deduced genres as StyleTag links, and omits the row when empty', async () => {
    const withGenres = await mountView()
    expect(withGenres.findAll('.hero-tags .tag-link')).toHaveLength(1)
    const noGenres = await mountView({ set: makeSet({ top_genres: [] }) })
    expect(noGenres.find('.hero-tags').exists()).toBe(false)
  })

  it('caps deduced genres at 5', async () => {
    const genres = Array.from({ length: 8 }, (_, i) => ({
      name: `G${i}`,
      pillar: 'autres',
      depth: 0,
      pct: i,
    }))
    const wrapper = await mountView({ set: makeSet({ top_genres: genres }) })
    expect(wrapper.findAll('.hero-tags .tag-link')).toHaveLength(5)
  })

  // ---- Hero stats (S3 / S4) ----

  it('renders all four stat labels when duration and date are present', async () => {
    const wrapper = await mountView()
    const labels = wrapper.findAll('.stat-label').map((l) => l.text())
    expect(labels).toEqual(['Durée', 'Date', 'Tracks', 'Identifiées'])
    expect(wrapper.findAll('.stat-cell')[2].find('.stat-val').text()).toBe('26')
  })

  it('masks the Durée and Date cells when their values are null', async () => {
    const wrapper = await mountView({ set: makeSet({ duration_ms: null, played_date: null }) })
    const labels = wrapper.findAll('.stat-label').map((l) => l.text())
    expect(labels).toEqual(['Tracks', 'Identifiées'])
  })

  it('renders the identified ScoreRing in pct mode with the ratio and the fraction', async () => {
    const wrapper = await mountView()
    const ring = wrapper.findComponent(ScoreRing)
    expect(ring.props('mode')).toBe('pct')
    expect(ring.props('size')).toBe('md')
    expect(ring.props('score')).toBeCloseTo(18 / 26)
    expect(wrapper.find('.ident-frac').text()).toBe('18/26')
  })

  it('guards the ratio against a zero total_tracks', async () => {
    const wrapper = await mountView({
      set: makeSet({ total_tracks: 0, identified_tracks: 0, tracklist: [] }),
    })
    expect(wrapper.findComponent(ScoreRing).props('score')).toBe(0)
    expect(wrapper.find('.ident-frac').text()).toBe('0/0')
  })

  // ---- Hero source (S7) ----

  it('renders the source PlatformLink with the platform name and href', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('.hero-source').exists()).toBe(true)
    const link = wrapper.findComponent(PlatformLink)
    expect(link.props('platform')).toBe('youtube')
    expect(link.props('href')).toBe('https://youtube.com/watch?v=abc')
    expect(wrapper.find('.hero-source-name').text()).toBe('YouTube')
  })

  it('maps the back source value « 1001tracklists » to the PlatformLink key « 1001tl »', async () => {
    const wrapper = await mountView({
      set: makeSet({ source: '1001tracklists', source_url: 'https://1001tracklists.com/x' }),
    })
    expect(wrapper.findComponent(PlatformLink).props('platform')).toBe('1001tl')
    expect(wrapper.find('.hero-source-name').text()).toBe('1001Tracklists')
  })

  it('hides the whole source block when source_url is null', async () => {
    const wrapper = await mountView({ set: makeSet({ source_url: null }) })
    expect(wrapper.find('.hero-source').exists()).toBe(false)
    expect(wrapper.findComponent(PlatformLink).exists()).toBe(false)
  })

  // ---- Hero backdrop (S1) ----

  it('renders the blurred backdrop only when the set has artwork', async () => {
    const withArt = await mountView()
    expect(withArt.find('.hero-backdrop').exists()).toBe(true)
    const noArt = await mountView({ set: makeSet({ has_artwork: false }) })
    expect(noArt.find('.hero-backdrop').exists()).toBe(false)
  })

  // ---- Tracklist (S8) ----

  it('renders one TrackCard per tracklist entry with the counter', async () => {
    const wrapper = await mountView()
    expect(wrapper.findAllComponents(TrackCard)).toHaveLength(3)
    const count = wrapper.find('.tracklist .sec-count').text()
    expect(count).toContain('26 tracks')
    expect(count).toContain('18 identifiées')
  })

  it('maps an identified row to the full TrackCard shape (no state)', async () => {
    const wrapper = await mountView()
    const card = wrapper.findAllComponents(TrackCard)[0]
    expect(card.props('state')).toBeUndefined()
    expect(card.props('position')).toBe(1)
    const t = card.props('track')
    expect(t.id).toBe(500)
    expect(t.title).toBe('Track A')
    expect(t.artist).toBe('Artist A')
    expect(t.artists).toEqual([{ id: 1, name: 'Artist A' }])
    expect(t.bpm).toBe(140)
    expect(t.key).toBe('5A')
    expect(t.duration_ms).toBe(300000)
    expect(t.in_lib).toBe(true)
  })

  it('maps an is_id row to state="id"', async () => {
    const wrapper = await mountView()
    expect(wrapper.findAllComponents(TrackCard)[1].props('state')).toBe('id')
  })

  it('maps an unresolved row to state="unresolved" with raw title/artist', async () => {
    const wrapper = await mountView()
    const card = wrapper.findAllComponents(TrackCard)[2]
    expect(card.props('state')).toBe('unresolved')
    expect(card.props('track').title).toBe('Unknown Title')
    expect(card.props('track').artist).toBe('Unknown Artist')
  })

  it('builds a YouTube timecode href but leaves a trackid source non-clickable', async () => {
    const yt = await mountView()
    // 65000 ms → 65s; base url already has a query string → "&t=".
    expect(yt.findAllComponents(TrackCard)[0].props('timecode')).toEqual({
      ms: 65000,
      href: 'https://youtube.com/watch?v=abc&t=65s',
    })
    const tid = await mountView({
      set: makeSet({ source: 'trackid', source_url: 'https://trackid.net/set/1' }),
    })
    const tc = tid.findAllComponents(TrackCard)[0].props('timecode')
    expect(tc.ms).toBe(65000)
    expect(tc.href).toBeUndefined()
  })

  it('builds a timecode href for timecode_ms=0 (0 is a valid cue, not "no cue")', async () => {
    const tracklist = makeTracklist()
    tracklist[0].timecode_ms = 0
    const wrapper = await mountView({ set: makeSet({ tracklist }) })
    const tc = wrapper.findAllComponents(TrackCard)[0].props('timecode')
    expect(tc.ms).toBe(0)
    expect(tc.href).toBe('https://youtube.com/watch?v=abc&t=0s')
  })

  // ---- Tracklist navigation ----

  it('navigates to /catalog/:id on an identified row, and never on an id/unresolved row', async () => {
    const wrapper = await mountView()
    const cards = wrapper.findAllComponents(TrackCard)
    await cards[0].trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/catalog/500')
    routerPush.mockReset()
    await cards[1].trigger('click') // id
    await cards[2].trigger('click') // unresolved
    expect(routerPush).not.toHaveBeenCalled()
  })

  it('plays an identified row through the audioPlayer store', async () => {
    const wrapper = await mountView()
    await wrapper.findAllComponents(TrackCard)[0].vm.$emit('play')
    expect(playerMock.play).toHaveBeenCalledWith({
      id: 500,
      catalog_id: 500,
      title: 'Track A',
      artist: 'Artist A',
      bpm: 140,
      key: '5A',
    })
  })

  // ---- Similar sets (S10) ----

  it('renders the similar sets grid with SetCards and a counter', async () => {
    const wrapper = await mountView({ similar: makeSimilar(4) })
    expect(wrapper.find('.similar').exists()).toBe(true)
    expect(wrapper.findAllComponents(SetCard)).toHaveLength(4)
    expect(wrapper.find('.similar .sec-count').text()).toBe('4 sets')
  })

  it('hides the whole similar section when the endpoint returns an empty list', async () => {
    const wrapper = await mountView({ similar: [] })
    expect(wrapper.find('.similar').exists()).toBe(false)
    expect(wrapper.findComponent(SetCard).exists()).toBe(false)
  })

  it('hides the similar section when the endpoint errors (treated as empty)', async () => {
    const wrapper = await mountView({ similarError: true })
    expect(wrapper.find('.similar').exists()).toBe(false)
  })

  // ---- States ----

  it('shows the loading state before the detail resolves', async () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}))
    const { default: SetDetailView } = await import('../../views/SetDetailView.vue')
    const wrapper = mount(SetDetailView, globalOpts)
    expect(wrapper.find('.state').text()).toContain('Chargement')
  })

  it('shows the not-found state with a return button to /sets', async () => {
    const wrapper = await mountView({ set: null })
    expect(wrapper.find('.state--empty').text()).toContain('Set introuvable')
    expect(wrapper.findComponent(RouterLinkStub).props('to')).toBe('/sets')
  })

  // ---- AdminCard ----

  it('shows the AdminCard for an admin', async () => {
    authMock.user = { is_admin: true }
    const wrapper = await mountView()
    expect(wrapper.find('.admin-card').exists()).toBe(true)
    expect(wrapper.text()).toContain('Amelie Lens')
  })

  it('hides the AdminCard for a non-admin', async () => {
    authMock.user = null
    const wrapper = await mountView()
    expect(wrapper.find('.admin-card').exists()).toBe(false)
  })
})

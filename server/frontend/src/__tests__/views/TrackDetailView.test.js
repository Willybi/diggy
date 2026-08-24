import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'

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
  // The view now reads the auth store to gate AddToCollectionButton (L6);
  // default to authenticated so the button renders as it always did here.
  authMock: { isAuthenticated: true, user: null },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

vi.mock('../../stores/audioPlayer', () => ({
  useAudioPlayer: () => playerMock,
}))

vi.mock('../../stores/auth.js', () => ({
  useAuthStore: () => authMock,
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '1' } }),
  useRouter: () => ({ push: routerPush, replace: vi.fn() }),
}))

function makeTrack(overrides = {}) {
  return {
    id: 1,
    title: 'Strobe',
    artist: 'deadmau5',
    artist_id: 7,
    artists: [{ id: 7, name: 'deadmau5', has_artwork: false }],
    in_lib: true,
    has_artwork: false,
    lib_track_id: null,
    genres: [],
    style: null,
    tags: [],
    bpm: 128,
    key: '9A',
    duration_ms: 634000,
    release_date: '2009-07-07',
    has_preview: true,
    beatport_id: null,
    deezer_id: null,
    label: null,
    isrc: null,
    avis: null,
    rating: 5,
    radar_appearances: [],
    set_appearances: [],
    same_artist_tracks: [],
    ...overrides,
  }
}

function makeSameArtist(n) {
  return Array.from({ length: n }, (_, i) => ({
    id: 100 + i,
    title: `Sibling ${i}`,
    bpm: 126,
    key: '8A',
    has_artwork: false,
    has_preview: true,
    in_lib: false,
  }))
}

function makeSimilar(n) {
  return Array.from({ length: n }, (_, i) => ({
    id: 200 + i,
    title: `Similar ${i}`,
    artist: `Artist ${i}`,
    bpm: 124,
    key: '7A',
    has_artwork: false,
    has_preview: true,
    in_lib: false,
    similarity: { score: 0.87, components: {}, available_features: [] },
  }))
}

// Content neighbours (« Sonne comme ») carry NO similarity/score payload.
function makeContent(n) {
  return Array.from({ length: n }, (_, i) => ({
    id: 300 + i,
    title: `Sounds ${i}`,
    artist: `Artist ${i}`,
    bpm: 122,
    key: '6A',
    has_artwork: false,
    has_preview: true,
    in_lib: false,
  }))
}

async function mountView(track, similar = [], content = []) {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/catalog/1') {
      return track ? Promise.resolve({ data: track }) : Promise.reject(new Error('404'))
    }
    // content-similar shares the `/similar` substring → match it FIRST.
    if (url.includes('/content-similar')) return Promise.resolve({ data: content })
    if (url.includes('/similar')) return Promise.resolve({ data: similar })
    return Promise.resolve({ data: [] })
  })
  const { default: TrackDetailView } = await import('../../views/TrackDetailView.vue')
  const wrapper = mount(TrackDetailView, {
    global: {
      components: { RouterLink: RouterLinkStub },
      stubs: {
        StyleTag: true,
        HeroPlayer: true,
        LikeDislike: true,
        AdminCard: true,
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('TrackDetailView', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.patch.mockReset()
    apiMock.post.mockResolvedValue({ data: {} })
    apiMock.patch.mockResolvedValue({ data: {} })
    routerPush.mockReset()
    playerMock.playing = false
    // Reset the admin flag so the « Sonne comme » gate never leaks across tests.
    authMock.user = null
  })

  it('renders the hero with the 4 musical stats and no rating', async () => {
    const wrapper = await mountView(makeTrack())
    const cells = wrapper.findAll('.stat-cell')
    expect(cells).toHaveLength(4)
    const labels = wrapper.findAll('.stat-label').map((c) => c.text())
    expect(labels).toEqual(['BPM', 'Key', 'Durée', 'Année'])
    // Key is accent-inked
    expect(wrapper.find('.stat-val--key').text()).toBe('9A')
    // Rating is gone from the whole page
    expect(wrapper.find('.star').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Rating')
  })

  it('renders the hero title and one chip per artist', async () => {
    const wrapper = await mountView(
      makeTrack({
        artists: [
          { id: 7, name: 'deadmau5', has_artwork: false },
          { id: 8, name: 'Kaskade', has_artwork: false },
        ],
      }),
    )
    expect(wrapper.find('.hero-title').text()).toBe('Strobe')
    expect(wrapper.findAll('.artist-chip')).toHaveLength(2)
  })

  it("orders Découverte before « Où on l'entend »", async () => {
    const wrapper = await mountView(
      makeTrack({
        same_artist_tracks: makeSameArtist(2),
        set_appearances: [
          { set_id: 3, set_title: 'A Set', timecode_ms: 60000, played_date: '2024-01-01' },
        ],
      }),
      makeSimilar(2),
    )
    const html = wrapper.html()
    expect(html.indexOf('Du même artiste')).toBeGreaterThan(-1)
    expect(html.indexOf('Apparaît dans')).toBeGreaterThan(-1)
    expect(html.indexOf('Du même artiste')).toBeLessThan(html.indexOf('Apparaît dans'))
    expect(html.indexOf('Tracks similaires')).toBeLessThan(html.indexOf('Apparaît dans'))
  })

  it('truncates « Du même artiste » to 6 and toggles with the button', async () => {
    const wrapper = await mountView(makeTrack({ same_artist_tracks: makeSameArtist(8) }))
    // Only one disc-block (no similar), so all track-cards are the same-artist grid.
    expect(wrapper.findAll('.mini-grid .track-card')).toHaveLength(6)
    const more = wrapper.find('.disc-more .btn')
    expect(more.text()).toBe('Afficher plus (2)')
    await more.trigger('click')
    expect(wrapper.findAll('.mini-grid .track-card')).toHaveLength(8)
    expect(wrapper.find('.disc-more .btn').text()).toBe('Afficher moins')
  })

  it('does not render the « Afficher plus » button when 6 or fewer same-artist tracks', async () => {
    const wrapper = await mountView(makeTrack({ same_artist_tracks: makeSameArtist(6) }))
    expect(wrapper.findAll('.mini-grid .track-card')).toHaveLength(6)
    expect(wrapper.find('.disc-more').exists()).toBe(false)
  })

  it('renders similar tracks with a ScoreRing (no "%" text)', async () => {
    const wrapper = await mountView(makeTrack(), makeSimilar(3))
    expect(wrapper.findAll('.score-ring')).toHaveLength(3)
    // round(0.87 * 10) = 9, never the raw percentage
    expect(wrapper.find('.score-ring .sr-note').text()).toBe('9')
    expect(wrapper.text()).not.toContain('87%')
  })

  // Rendered shelf headings only (wrapper.html() also carries the template's
  // « Sonne comme » comment, so assert on real .disc-title text).
  const discTitles = (w) => w.findAll('.disc-title').map((t) => t.text())

  it('renders the « Sonne comme » shelf for an admin, with cards and no ScoreRing', async () => {
    authMock.user = { is_admin: true }
    // No same-artist / no similar → the only mini-grid is the content shelf.
    const wrapper = await mountView(makeTrack(), [], makeContent(3))
    expect(discTitles(wrapper)).toContain('Sonne comme')
    expect(wrapper.findAll('.mini-grid .track-card')).toHaveLength(3)
    // Content neighbours never expose a score.
    expect(wrapper.findAll('.score-ring')).toHaveLength(0)
  })

  it('hides the « Sonne comme » shelf for an admin when there are no content neighbours', async () => {
    authMock.user = { is_admin: true }
    const wrapper = await mountView(makeTrack(), [], [])
    expect(discTitles(wrapper)).not.toContain('Sonne comme')
  })

  it('never renders « Sonne comme » nor calls content-similar for a non-admin', async () => {
    authMock.user = { is_admin: false }
    const wrapper = await mountView(makeTrack(), [], makeContent(3))
    expect(discTitles(wrapper)).not.toContain('Sonne comme')
    const hitContent = apiMock.get.mock.calls.some(([url]) => url.includes('/content-similar'))
    expect(hitContent).toBe(false)
  })

  it('truncates set appearances to 5 with a per-block footer', async () => {
    const sets = Array.from({ length: 7 }, (_, i) => ({
      set_id: i + 1,
      set_title: `Set ${i}`,
      timecode_ms: 60000,
      played_date: '2024-01-01',
    }))
    const wrapper = await mountView(makeTrack({ set_appearances: sets }))
    // One rel-card (sets only).
    expect(wrapper.findAll('.rel-card .rel-row')).toHaveLength(5)
    const more = wrapper.find('.rel-more')
    expect(more.text()).toBe('Afficher plus (2)')
    await more.trigger('click')
    expect(wrapper.findAll('.rel-card .rel-row')).toHaveLength(7)
    expect(wrapper.find('.rel-more').text()).toBe('Afficher moins')
  })

  it('renders a source glyph (PlatformLink) instead of a SourceBadge for playlists', async () => {
    const wrapper = await mountView(
      makeTrack({
        radar_appearances: [
          {
            playlist_id: 5,
            playlist_title: 'Trending Now',
            playlist_source: 'deezer',
            detected_at: '2024-02-02',
          },
        ],
      }),
    )
    expect(wrapper.find('.plink--glyph').exists()).toBe(true)
    // The old text badge must be gone.
    expect(wrapper.find('.src-badge').exists()).toBe(false)
  })

  it('shows the timecode chip on a set appearance', async () => {
    const wrapper = await mountView(
      makeTrack({
        set_appearances: [
          { set_id: 3, set_title: 'A Set', timecode_ms: 3661000, played_date: '2024-01-01' },
        ],
      }),
    )
    expect(wrapper.find('.timecode').text()).toContain('1:01:01')
  })

  it('renders external platform links when ids are present', async () => {
    const wrapper = await mountView(
      makeTrack({ beatport_id: 111, deezer_id: 222, label: 'mau5trap' }),
    )
    const links = wrapper.findAll('.hero-links .plink--btn')
    expect(links).toHaveLength(2)
    expect(wrapper.find('.hero-label-name').text()).toBe('mau5trap')
  })

  it('renders the Beatport embed fallback only without Deezer preview AND with a beatport_id', async () => {
    // Deezer preview present → native player untouched, no iframe (even with a beatport_id)
    let wrapper = await mountView(makeTrack({ beatport_id: 111 }))
    expect(wrapper.find('.bp-embed').exists()).toBe(false)

    // No preview + beatport_id → embed block with its Beatport link
    wrapper = await mountView(makeTrack({ has_preview: false, beatport_id: 111 }))
    const embed = wrapper.find('.bp-embed')
    expect(embed.exists()).toBe(true)
    expect(embed.find('.bp-link').attributes('href')).toBe('https://www.beatport.com/track/-/111')

    // No preview, no beatport_id → no audio block at all
    wrapper = await mountView(makeTrack({ has_preview: false }))
    expect(wrapper.find('.bp-embed').exists()).toBe(false)
  })

  it('shows the not-found state with a return button', async () => {
    const wrapper = await mountView(null)
    expect(wrapper.find('.state--empty').text()).toContain('Track introuvable')
    const back = wrapper.find('.state--empty .btn')
    expect(back.exists()).toBe(true)
    expect(wrapper.findComponent(RouterLinkStub).props('to')).toBe('/explorer')
  })

  it('shows the similar-loading skeleton before similar tracks resolve', async () => {
    // Keep the similar request pending so the skeleton stays visible.
    apiMock.get.mockImplementation((url) => {
      if (url === '/api/catalog/1') return Promise.resolve({ data: makeTrack() })
      if (url.includes('/similar')) return new Promise(() => {})
      return Promise.resolve({ data: [] })
    })
    const { default: TrackDetailView } = await import('../../views/TrackDetailView.vue')
    const wrapper = mount(TrackDetailView, {
      global: {
        components: { RouterLink: RouterLinkStub },
        stubs: { StyleTag: true, HeroPlayer: true, LikeDislike: true, AdminCard: true },
      },
    })
    await flushPromises()
    expect(wrapper.findAll('.sim-skeleton .skel-row')).toHaveLength(4)
  })

  it('shows the « + Nouvelle collection » item in the collection dropdown', async () => {
    const wrapper = await mountView(makeTrack())
    await wrapper.find('.btn-coll').trigger('click')
    await flushPromises()
    const add = wrapper.find('.coll-dd-add')
    expect(add.exists()).toBe(true)
    expect(add.text()).toContain('Nouvelle collection')
  })

  it('creates a collection, adds the current track, then closes the input', async () => {
    apiMock.post.mockImplementation((url) => {
      if (url === '/api/collections/') {
        return Promise.resolve({
          data: {
            id: 42,
            name: 'Peak Time',
            type: 'playlist',
            created_at: '2026-07-17',
            item_count: 0,
          },
        })
      }
      return Promise.resolve({ data: {} })
    })
    const wrapper = await mountView(makeTrack())
    await wrapper.find('.btn-coll').trigger('click')
    await flushPromises()

    // Swap the footer button for the inline input.
    await wrapper.find('.coll-dd-add').trigger('click')
    await flushPromises()
    const input = wrapper.find('.coll-dd-input')
    expect(input.exists()).toBe(true)

    // Type a name and submit with Enter.
    await input.setValue('Peak Time')
    await input.trigger('keydown.enter')
    await flushPromises()

    // Collection created, then the current track (id 1) added to it with the
    // polymorphic payload (C5 v2, extracted into AddToCollectionButton).
    expect(apiMock.post).toHaveBeenCalledWith('/api/collections/', { name: 'Peak Time' })
    expect(apiMock.post).toHaveBeenCalledWith('/api/collections/42/items', {
      item_type: 'track',
      item_id: 1,
      item_name: null,
    })

    // Input closed (footer button back), new collection listed with a ✓.
    expect(wrapper.find('.coll-dd-input').exists()).toBe(false)
    expect(wrapper.find('.coll-dd-add').exists()).toBe(true)
    const added = wrapper.findAll('.coll-dd-item').find((b) => b.text().includes('Peak Time'))
    expect(added).toBeTruthy()
    expect(added.find('.coll-dd-check').exists()).toBe(true)
  })
})

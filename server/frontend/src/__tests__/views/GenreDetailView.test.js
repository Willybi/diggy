import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'

// Mutable holders shared with the hoisted mocks below.
const { apiMock, routerPush, routerReplace, opinionsStore } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
  routerPush: vi.fn(),
  routerReplace: vi.fn(),
  opinionsStore: { get: vi.fn(() => null), set: vi.fn() },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

vi.mock('../../stores/opinions.js', () => ({
  useOpinionsStore: () => opinionsStore,
}))

vi.mock('../../stores/audioPlayer', () => ({
  useAudioPlayer: () => ({
    genrePlaying: null,
    playing: false,
    isCurrent: () => false,
    play: vi.fn(),
    playRandom: vi.fn(),
    close: vi.fn(),
    syncAvis: vi.fn(),
  }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { genre: 'Techno' } }),
  useRouter: () => ({ push: routerPush, replace: routerReplace }),
}))

function makeGenre(overrides = {}) {
  return {
    name: 'Techno',
    pillar: 'techno',
    depth: 0,
    trackCount: 15664,
    artistCount: 1240,
    bpmLo: 120,
    bpmHi: 150,
    inLibCount: 128,
    setCount: 12,
    playlistCount: 3,
    artworks: [],
    artists: [],
    ...overrides,
  }
}

function makeTrack(overrides = {}) {
  return {
    id: 1,
    title: 'Spastik',
    artist: 'Plastikman',
    artists: [{ id: 7, name: 'Plastikman', role: 'main', has_artwork: false }],
    bpm: 132,
    key: '9A',
    durationMs: 372000,
    hasArtwork: false,
    hasPreview: true,
    inLib: true,
    avis: null,
    ...overrides,
  }
}

// TrackCard and LikeDislike stay REAL: the artists[]/flat fallback and the
// end-slot avis are exactly what this page must feed them. AdminCard is
// stubbed (it pulls the auth store); its slot content still renders.
const STUBS = {
  AdminCard: { template: '<div class="admin-stub"><slot /></div>' },
}

let responses

function installApiMock() {
  apiMock.get.mockImplementation((url) => {
    if (url.startsWith('/api/genres/detail/')) return Promise.resolve({ data: responses.detail })
    if (url.startsWith('/api/genres/artists/')) return Promise.resolve({ data: responses.artists })
    if (url.startsWith('/api/genres/sets/')) return Promise.resolve({ data: responses.sets })
    if (url.startsWith('/api/genres/playlists/'))
      return Promise.resolve({ data: responses.playlists })
    if (url.startsWith('/api/genres/tracks/')) return Promise.resolve({ data: responses.tracks })
    if (url.startsWith('/api/genres/neighbors/'))
      return Promise.resolve({ data: responses.neighbors })
    return Promise.resolve({ data: {} })
  })
}

function tracksCalls() {
  return apiMock.get.mock.calls.filter(([url]) => url.startsWith('/api/genres/tracks/'))
}

async function mountView() {
  const { default: GenreDetailView } = await import('../../views/GenreDetailView.vue')
  // vue-router is mocked, so <router-link> never resolves to a component and
  // VTU `stubs` would not apply — register the stub as a global component.
  const wrapper = mount(GenreDetailView, {
    global: {
      components: { RouterLink: RouterLinkStub },
      stubs: STUBS,
    },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  // No IntersectionObserver stub on purpose: the view renders no sentinel
  // (finite tracklist, D8.b) so useInfiniteScroll never instantiates one —
  // jsdom having none would make any sentinel reintroduction fail loudly here.
  apiMock.get.mockReset()
  apiMock.post.mockReset()
  apiMock.patch.mockReset()
  apiMock.patch.mockResolvedValue({ data: {} })
  routerPush.mockReset()
  routerReplace.mockReset()
  opinionsStore.get.mockReset()
  opinionsStore.get.mockReturnValue(null)
  opinionsStore.set.mockReset()
  responses = {
    detail: makeGenre(),
    artists: { items: [], total: 0 },
    sets: { items: [], total: 0 },
    playlists: { items: [], total: 0 },
    tracks: { items: [makeTrack()], total: 1 },
    neighbors: { items: [] },
  }
  installApiMock()
})

describe('GenreDetailView page states', () => {
  it('shows the loading state before the fetch resolves', async () => {
    apiMock.get.mockReturnValue(new Promise(() => {})) // never resolves
    const { default: GenreDetailView } = await import('../../views/GenreDetailView.vue')
    const wrapper = mount(GenreDetailView, {
      global: { components: { RouterLink: RouterLinkStub }, stubs: STUBS },
    })
    expect(wrapper.find('.state').text()).toBe('Chargement…')
  })

  it('shows a not-found state with a return link when the genre fails to load', async () => {
    apiMock.get.mockImplementation((url) => {
      if (url.startsWith('/api/genres/detail/')) return Promise.reject(new Error('404'))
      return Promise.resolve({ data: { items: [], total: 0 } })
    })
    const wrapper = await mountView()
    const empty = wrapper.find('.state--empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('Genre introuvable.')
    expect(wrapper.find('.btn').text()).toBe('Retour aux genres')
  })
})

describe('GenreDetailView hero', () => {
  it('renders the title, the pillar label and the three key stats in the overlay', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('.hero-title').text()).toBe('Techno')
    expect(wrapper.find('.hero-pill').text()).toContain('Techno')
    const values = wrapper.findAll('.hs-v').map((n) => n.text())
    expect(values[0]).toMatch(/^15\s?664$/)
    expect(values[1]).toMatch(/^1\s?240$/)
    expect(values[2]).toBe('120–150')
  })

  it('renders « — » (never « 0–0 ») when the genre has no BPM', async () => {
    responses.detail = makeGenre({ bpmLo: 0, bpmHi: 0 })
    const wrapper = await mountView()
    const values = wrapper.findAll('.hs-v').map((n) => n.text())
    expect(values[2]).toBe('—')
    expect(wrapper.text()).not.toContain('0–0')
  })

  it('omits the avatar cluster (and its « +N ») when there is no avatar', async () => {
    responses.detail = makeGenre({ artists: [], artistCount: 1240 })
    const wrapper = await mountView()
    expect(wrapper.find('.hero-avatars').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('+1')
  })

  it('renders up to 3 avatar links and a « +N » completing artistCount', async () => {
    responses.detail = makeGenre({
      artists: [
        { id: 1, name: 'A', image: '/storage/artist-artworks/1.jpg' },
        { id: 2, name: 'B', image: '/storage/artist-artworks/2.jpg' },
        { id: 3, name: 'C', image: '/storage/artist-artworks/3.jpg' },
      ],
      artistCount: 120,
    })
    const wrapper = await mountView()
    expect(wrapper.findAll('.hero-av')).toHaveLength(3)
    expect(wrapper.find('.hero-av-more').text()).toBe('+117')
  })
})

describe('GenreDetailView structure', () => {
  it('has no « Tout filtrer dans Catalog » button and no StatStrip', async () => {
    const wrapper = await mountView()
    expect(wrapper.text()).not.toContain('Tout filtrer dans Catalog')
    expect(wrapper.find('.stat-strip').exists()).toBe(false)
  })

  it('renders the admin card last, after the tracks section', async () => {
    responses.neighbors = {
      items: [{ name: 'Acid Techno', pillar: 'techno', depth: 1, commonArtists: 42 }],
    }
    const wrapper = await mountView()
    const html = wrapper.html()
    const admin = html.indexOf('admin-stub')
    expect(admin).toBeGreaterThan(html.indexOf('tracks-section'))
    expect(admin).toBeGreaterThan(html.indexOf('neighbor-grid'))
  })

  it('shows the secondary stats line with En bib in positive ink when > 0', async () => {
    const wrapper = await mountView()
    const keys = wrapper.findAll('.ss-k').map((n) => n.text())
    expect(keys).toEqual(['En bib', 'Sets', 'Playlists'])
    expect(wrapper.find('.ss-v--pos').text()).toBe('128')
  })
})

describe('GenreDetailView tracks', () => {
  it('renders TrackCard rows with clickable structured artists', async () => {
    const wrapper = await mountView()
    const row = wrapper.find('.track-card')
    expect(row.exists()).toBe(true)
    expect(row.text()).toContain('Spastik')
    const links = row.findAllComponents(RouterLinkStub)
    const artistLink = links.find((l) => l.props('to') === '/artist/7')
    expect(artistLink).toBeTruthy()
    expect(artistLink.text()).toBe('Plastikman')
  })

  it('falls back to the flat artist string (no link) when artists[] is empty', async () => {
    responses.tracks = {
      items: [makeTrack({ id: 2, artists: [], artist: 'Unknown Crew' })],
      total: 1,
    }
    const wrapper = await mountView()
    const artist = wrapper.find('.tk-artist')
    expect(artist.text()).toBe('Unknown Crew')
    expect(artist.find('.tk-artist-link').exists()).toBe(false)
  })

  it('maps the camelCase payload onto the TrackCard contract (duration shown)', async () => {
    const wrapper = await mountView()
    // durationMs: 372000 → 6:12 through TrackCard's duration column.
    expect(wrapper.find('.tk-dur').text()).toBe('6:12')
  })

  it('shows the full total in the header counter', async () => {
    responses.tracks = { items: [makeTrack()], total: 15664 }
    const wrapper = await mountView()
    expect(wrapper.find('.sec-count').text()).toMatch(/^15\s?664$/)
  })

  it('PATCHes the canonical avis endpoint with a local delta on the row', async () => {
    const wrapper = await mountView()
    await wrapper.find('.track-card .ld-btn.like').trigger('click')
    expect(apiMock.patch).toHaveBeenCalledWith('/api/catalog/1/avis', { avis: 'liked' })
    await flushPromises()
    expect(wrapper.find('.track-card').classes()).toContain('liked')
  })

  it('rolls the row avis back when the PATCH fails', async () => {
    apiMock.patch.mockRejectedValue(new Error('boom'))
    const wrapper = await mountView()
    await wrapper.find('.track-card .ld-btn.like').trigger('click')
    await flushPromises()
    expect(wrapper.find('.track-card').classes()).not.toContain('liked')
  })

  it('shows the search empty state with a working « Réinitialiser », header kept', async () => {
    responses.tracks = { items: [], total: 0 }
    const wrapper = await mountView()
    const empty = wrapper.find('.tracks-empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('Aucune track ne correspond.')
    // Header and its tools stay on screen.
    expect(wrapper.find('.tracks-head').exists()).toBe(true)
    expect(wrapper.find('.sortseg').exists()).toBe(true)

    const before = tracksCalls().length
    await empty.find('.btn--sm').trigger('click')
    await flushPromises()
    const calls = tracksCalls()
    expect(calls.length).toBe(before + 1)
    const params = calls[calls.length - 1][1].params
    expect(params.q).toBeUndefined()
    expect(params.inLib).toBeUndefined()
    expect(params.offset).toBe(0)
  })

  it('refetches with the selected sort and the inLib extra param', async () => {
    const wrapper = await mountView()
    const bpmSeg = wrapper.findAll('.seg').find((b) => b.text() === 'BPM')
    await bpmSeg.trigger('click')
    await flushPromises()
    expect(tracksCalls().at(-1)[1].params.sort).toBe('bpm')

    await wrapper.find('.lib-toggle').trigger('click')
    await flushPromises()
    const params = tracksCalls().at(-1)[1].params
    expect(params.inLib).toBe(1)
  })

  it('refetches page 1 with q when the search input settles (debounce)', async () => {
    const wrapper = await mountView()
    const before = tracksCalls().length
    vi.useFakeTimers()
    await wrapper.find('.tracks-tools .search input').setValue('spastik')
    vi.advanceTimersByTime(300)
    vi.useRealTimers()
    await flushPromises()
    const calls = tracksCalls()
    expect(calls.length).toBe(before + 1)
    const params = calls.at(-1)[1].params
    expect(params.q).toBe('spastik')
    expect(params.offset).toBe(0)
  })

  it('loads a single finite page: no infinite-scroll sentinel in the DOM', async () => {
    responses.tracks = { items: [makeTrack()], total: 15664 }
    const wrapper = await mountView()
    expect(wrapper.find('.tracks-sentinel').exists()).toBe(false)
    const calls = tracksCalls()
    expect(calls.length).toBe(1)
    expect(calls[0][1].params.limit).toBe(50)
    expect(calls[0][1].params.offset).toBe(0)
  })

  it('links « Voir les N autres dans Explorer » (genre-only query) when the page overflows', async () => {
    responses.tracks = { items: [makeTrack()], total: 15664 }
    const wrapper = await mountView()
    const link = wrapper
      .findAllComponents(RouterLinkStub)
      .find((l) => String(l.props('to')).startsWith('/explorer'))
    expect(link).toBeTruthy()
    expect(link.props('to')).toBe('/explorer?genre=Techno')
    expect(link.text()).toMatch(/^Voir les 15\s?663 autres dans Explorer$/)
    expect(link.classes()).toContain('load-more')
  })

  it('hides the Explorer link when the whole tracklist fits on the page', async () => {
    responses.tracks = { items: [makeTrack()], total: 1 }
    const wrapper = await mountView()
    const link = wrapper
      .findAllComponents(RouterLinkStub)
      .find((l) => String(l.props('to')).startsWith('/explorer'))
    expect(link).toBeUndefined()
  })
})

describe('GenreDetailView shelves', () => {
  it('hides the Sets and Playlists sections entirely when empty', async () => {
    const wrapper = await mountView()
    const titles = wrapper.findAll('.rel-title').map((n) => n.text())
    expect(titles).not.toContain('Sets')
    expect(titles).not.toContain('Playlists')
  })

  it('renders the Sets footer « NN % de ce genre » without the colored ring', async () => {
    responses.sets = {
      items: [
        {
          id: 9,
          title: 'Boiler Room',
          playedDate: '2026-01-01',
          hasArtwork: false,
          genreTrackCount: 39,
          totalTracks: 50,
        },
      ],
      total: 1,
    }
    const wrapper = await mountView()
    const foot = wrapper.find('.card-foot--sets')
    expect(foot.exists()).toBe(true)
    expect(foot.find('.cf-pct').text()).toMatch(/^78\s?%$/)
    expect(foot.find('.cf-lbl').text()).toBe('de ce genre')
    expect(wrapper.find('.ring').exists()).toBe(false)
  })

  it('renders the Playlists footer as a source glyph + track count (no text badge)', async () => {
    responses.playlists = {
      items: [
        {
          id: 4,
          title: 'Peak Time',
          source: 'deezer',
          hasArtwork: false,
          owner: 'willi',
          genreTrackCount: 21,
        },
      ],
      total: 1,
    }
    const wrapper = await mountView()
    const foot = wrapper.find('.card-foot--pl')
    expect(foot.exists()).toBe(true)
    expect(foot.find('.plink--glyph').exists()).toBe(true)
    expect(foot.find('.cf-count').text()).toContain('21')
    expect(wrapper.find('.source-badge').exists()).toBe(false)
  })

  it('renders the Artistes cards with « N en bib » only when > 0', async () => {
    responses.artists = {
      items: [
        { id: 1, name: 'Ben Klock', hasArtwork: false, trackCount: 31, inLibCount: 4 },
        { id: 2, name: 'DVS1', hasArtwork: false, trackCount: 18, inLibCount: 0 },
      ],
      total: 2,
    }
    const wrapper = await mountView()
    const libs = wrapper.findAll('.ac-lib')
    expect(libs).toHaveLength(1)
    expect(libs[0].text()).toBe('4 en bib')
  })
})

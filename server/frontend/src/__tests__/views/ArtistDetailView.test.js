import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'

// Mutable holders shared with the hoisted mocks below.
const { authState, apiMock } = vi.hoisted(() => ({
  authState: { value: { isAuthenticated: false, user: null } },
  apiMock: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

vi.mock('../../stores/auth.js', () => ({
  useAuthStore: () => authState.value,
}))

vi.mock('../../stores/audioPlayer', () => ({
  useAudioPlayer: () => ({
    isCurrent: () => false,
    playing: false,
    play: vi.fn(),
    playRandomArtist: vi.fn(),
  }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '42' } }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

function makeArtist(overrides = {}) {
  return {
    id: 42,
    name: 'Amelie Lens',
    has_artwork: false,
    deezer_id: null,
    trackid_id: null,
    following: false,
    genres: [],
    aliases: [],
    catalog_tracks: [],
    sets: [],
    stats: { nb_catalog: 0, nb_lib: 0, nb_sets: 0 },
    ...overrides,
  }
}

// Light stubs — leaf/consumed components are covered by their own suites; here we
// only need to observe what the view feeds them (track count, set mapping, footer,
// platform logos). ExpandableShelf stays real so its default slot renders ShelfCards.
const STUBS = {
  StyleTag: true,
  AdminCard: { template: '<div class="admin-stub"><slot /></div>' },
  TrackCard: {
    props: ['track'],
    template: '<div class="tc-stub">{{ track.title }}</div>',
  },
  SetCard: {
    props: ['set'],
    template:
      '<div class="sc-stub" :data-set-id="set.id">{{ set.title }}<slot name="footer" /></div>',
  },
  PlatformLink: {
    props: ['platform', 'href'],
    template: '<a class="plink-stub" :data-platform="platform" :href="href"></a>',
  },
  ShelfCard: {
    props: ['title'],
    template: '<div class="shelf-stub">{{ title }}</div>',
  },
}

async function mountView(artist, connections = []) {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/artists/42') return Promise.resolve({ data: artist })
    if (url === '/api/artists/42/connections') return Promise.resolve({ data: connections })
    return Promise.resolve({ data: [] })
  })
  const { default: ArtistDetailView } = await import('../../views/ArtistDetailView.vue')
  // vue-router is mocked, so <router-link> never resolves to a component and
  // VTU `stubs` would not apply — register the stub as a global component.
  const wrapper = mount(ArtistDetailView, {
    global: {
      components: { RouterLink: RouterLinkStub },
      stubs: STUBS,
    },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  apiMock.get.mockReset()
  apiMock.post.mockReset()
  apiMock.delete.mockReset()
  apiMock.patch.mockReset()
  apiMock.post.mockResolvedValue({ data: {} })
  apiMock.delete.mockResolvedValue({ data: {} })
  authState.value = { isAuthenticated: false, user: null }
})

describe('ArtistDetailView page states', () => {
  it('shows the loading state before the fetch resolves', async () => {
    apiMock.get.mockReturnValue(new Promise(() => {})) // never resolves
    const { default: ArtistDetailView } = await import('../../views/ArtistDetailView.vue')
    const wrapper = mount(ArtistDetailView, {
      global: { components: { RouterLink: RouterLinkStub }, stubs: STUBS },
    })
    expect(wrapper.find('.state').text()).toBe('Chargement…')
  })

  it('shows a not-found state with a return link when the artist fails to load', async () => {
    apiMock.get.mockImplementation((url) => {
      if (url === '/api/artists/42') return Promise.reject(new Error('404'))
      return Promise.resolve({ data: [] })
    })
    const { default: ArtistDetailView } = await import('../../views/ArtistDetailView.vue')
    const wrapper = mount(ArtistDetailView, {
      global: { components: { RouterLink: RouterLinkStub }, stubs: STUBS },
    })
    await flushPromises()
    const empty = wrapper.find('.state--empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('Artiste introuvable.')
    expect(wrapper.find('.btn').text()).toBe('Retour aux artistes')
  })
})

describe('ArtistDetailView hero', () => {
  it('renders the name on the banner', async () => {
    const wrapper = await mountView(makeArtist({ name: 'Charlotte de Witte' }))
    expect(wrapper.find('.hb-name').text()).toBe('Charlotte de Witte')
  })

  it('renders the 3 folded stats (Catalog · In lib · Sets) and no rating', async () => {
    const wrapper = await mountView(
      makeArtist({ stats: { nb_catalog: 87, nb_lib: 12, nb_sets: 6 } }),
    )
    const labels = wrapper.findAll('.stat-label').map((n) => n.text())
    expect(labels).toEqual(['Catalog', 'In lib', 'Sets'])
    const values = wrapper.findAll('.stat-val').map((n) => n.text())
    expect(values).toEqual(['87', '12', '6'])
    // Rating moy. is removed everywhere on this page.
    expect(wrapper.text()).not.toContain('Rating')
  })

  it('renders a striped placeholder banner (no tiles) when no cover is available', async () => {
    const wrapper = await mountView(makeArtist())
    expect(wrapper.find('.hb-strip').exists()).toBe(true)
    expect(wrapper.findAll('.hb-tile')).toHaveLength(0)
  })

  it('dedupes genres by visible label (StyleTag truncates at « / »)', async () => {
    // « Dance » and « Dance / Pop » both display as « Dance » → a single chip.
    const wrapper = await mountView(
      makeArtist({
        genres: [
          { name: 'Dance', pillar: 'pop', depth: 1 },
          { name: 'Dance / Pop', pillar: 'pop', depth: 2 },
        ],
      }),
    )
    expect(wrapper.findAll('.tag-link')).toHaveLength(1)
  })

  it('cycles the available covers to fill the 12 banner tiles', async () => {
    // 2 covers → 12 tiles cycled (no empty slots).
    const catalog_tracks = [
      { id: 1, title: 'T1', has_artwork: true },
      { id: 2, title: 'T2', has_artwork: true },
      { id: 3, title: 'T3', has_artwork: false },
    ]
    const wrapper = await mountView(makeArtist({ catalog_tracks, stats: { nb_catalog: 3 } }))
    expect(wrapper.find('.hb-strip').exists()).toBe(false)
    expect(wrapper.findAll('.hb-tile')).toHaveLength(12)
  })
})

describe('ArtistDetailView platform logos', () => {
  it('renders no platform logos when both ids are null (and never SoundCloud)', async () => {
    const wrapper = await mountView(makeArtist())
    expect(wrapper.findAll('.plink-stub')).toHaveLength(0)
    expect(wrapper.find('[data-platform="soundcloud"]').exists()).toBe(false)
  })

  it('renders only the Deezer logo when only deezer_id is present', async () => {
    const wrapper = await mountView(makeArtist({ deezer_id: '999' }))
    const links = wrapper.findAll('.plink-stub')
    expect(links).toHaveLength(1)
    expect(links[0].attributes('data-platform')).toBe('deezer')
    expect(links[0].attributes('href')).toContain('deezer.com/artist/999')
  })

  it('renders both logos when both ids are present', async () => {
    const wrapper = await mountView(makeArtist({ deezer_id: '999', trackid_id: 'abc' }))
    const platforms = wrapper.findAll('.plink-stub').map((l) => l.attributes('data-platform'))
    expect(platforms).toEqual(['deezer', 'trackid'])
  })

  it('hides the Deezer logo when deezer_id is the NOT_FOUND sentinel', async () => {
    const wrapper = await mountView(makeArtist({ deezer_id: 'NOT_FOUND' }))
    expect(wrapper.find('[data-platform="deezer"]').exists()).toBe(false)
  })
})

describe('ArtistDetailView dead code removed', () => {
  it('never renders a biography, even when the (legacy) field is present', async () => {
    const wrapper = await mountView(
      makeArtist({
        bio: 'CETTE_BIO_NE_DOIT_PAS_APPARAITRE',
        real_name: 'Real Name',
        country: 'BE',
      }),
    )
    expect(wrapper.text()).not.toContain('CETTE_BIO_NE_DOIT_PAS_APPARAITRE')
    expect(wrapper.text()).not.toContain('Real Name')
    expect(wrapper.find('[data-platform="soundcloud"]').exists()).toBe(false)
  })
})

describe('ArtistDetailView tracks', () => {
  function withTracks(n, nbCatalog = n) {
    const catalog_tracks = Array.from({ length: n }, (_, i) => ({
      id: i + 1,
      title: `Track ${i + 1}`,
      artist: 'A',
      artists: [],
      has_artwork: false,
      has_preview: false,
      in_lib: false,
    }))
    return makeArtist({ catalog_tracks, stats: { nb_catalog: nbCatalog, nb_lib: 0, nb_sets: 0 } })
  }

  it('renders tracks as TrackCard and shows only 10 before expanding', async () => {
    const wrapper = await mountView(withTracks(15))
    expect(wrapper.findAll('.tc-stub')).toHaveLength(10)
    const btn = wrapper.find('.tracks-more button')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toBe('Afficher les 5 autres tracks')
  })

  it('reveals all tracks and drops the button after expanding', async () => {
    const wrapper = await mountView(withTracks(15))
    await wrapper.find('.tracks-more button').trigger('click')
    expect(wrapper.findAll('.tc-stub')).toHaveLength(15)
    expect(wrapper.find('.tracks-more').exists()).toBe(false)
  })

  it('shows no expand button when 10 or fewer tracks are loaded', async () => {
    const wrapper = await mountView(withTracks(8))
    expect(wrapper.findAll('.tc-stub')).toHaveLength(8)
    expect(wrapper.find('.tracks-more').exists()).toBe(false)
  })

  it('notes the extra catalog tracks not carried in the payload', async () => {
    const wrapper = await mountView(withTracks(15, 100))
    const note = wrapper.find('.more-note')
    expect(note.exists()).toBe(true)
    expect(note.text()).toContain('85')
  })
})

describe('ArtistDetailView sets', () => {
  const setsArtist = () =>
    makeArtist({
      sets: [
        {
          set_id: 100,
          title: 'Set A',
          played_date: null,
          role: 'b2b',
          has_artwork: true,
          total_tracks: 10,
          identified_tracks: 7,
          artists: ['DJ X'],
          duration_ms: 3600000,
        },
        {
          set_id: 200,
          title: 'Set B',
          has_artwork: false,
          total_tracks: 0,
          identified_tracks: 0,
          artists: [],
          duration_ms: null,
        },
      ],
      stats: { nb_catalog: 0, nb_lib: 0, nb_sets: 2 },
    })

  it('hides the whole Sets section when there is no set', async () => {
    const wrapper = await mountView(makeArtist())
    expect(wrapper.find('.sets').exists()).toBe(false)
  })

  it('renders a SetCard grid mapping set_id → id, and never shows the import role', async () => {
    const wrapper = await mountView(setsArtist())
    const cards = wrapper.findAll('.sc-stub')
    expect(cards).toHaveLength(2)
    expect(cards.map((c) => c.attributes('data-set-id'))).toEqual(['100', '200'])
    expect(wrapper.text()).not.toContain('b2b')
    expect(wrapper.text()).not.toContain('B2B')
  })

  it('renders the % identifiées footer only for sets with tracks', async () => {
    const wrapper = await mountView(setsArtist())
    const badges = wrapper.findAll('.set-ident-val')
    // Only Set A (7/10) gets a footer; Set B (0 tracks) has none.
    expect(badges).toHaveLength(1)
    expect(badges[0].text()).toContain('70')
    expect(wrapper.findAll('.set-ident-lbl')).toHaveLength(1)
  })
})

describe('ArtistDetailView related artists', () => {
  it('is absent when there are no connections', async () => {
    const wrapper = await mountView(makeArtist())
    expect(wrapper.find('.proches').exists()).toBe(false)
    expect(wrapper.findAll('.shelf-stub')).toHaveLength(0)
  })

  it('renders the related artists as round ShelfCards', async () => {
    const connections = [
      { artist_id: 1, name: 'Farrago', has_artwork: true },
      { artist_id: 2, name: 'Kobosil', has_artwork: false },
    ]
    const wrapper = await mountView(makeArtist(), connections)
    expect(wrapper.find('.proches').exists()).toBe(true)
    const cards = wrapper.findAll('.shelf-stub')
    expect(cards).toHaveLength(2)
    expect(cards.map((c) => c.text())).toEqual(['Farrago', 'Kobosil'])
  })
})

describe('ArtistDetailView aliases', () => {
  it('renders the alias line joined by « · » when present', async () => {
    const wrapper = await mountView(
      makeArtist({ aliases: [{ alias: 'Lenske' }, { alias: 'Renegade' }] }),
    )
    const line = wrapper.find('.aliases')
    expect(line.exists()).toBe(true)
    expect(line.find('.aliases-names').text()).toBe('Lenske · Renegade')
  })

  it('omits the alias line when there is none', async () => {
    const wrapper = await mountView(makeArtist())
    expect(wrapper.find('.aliases').exists()).toBe(false)
  })
})

describe('ArtistDetailView follow button', () => {
  it('is absent for guests', async () => {
    const wrapper = await mountView(makeArtist())
    expect(wrapper.find('.btn-follow').exists()).toBe(false)
  })

  it('shows « Suivre » when the artist is not followed', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    const wrapper = await mountView(makeArtist({ following: false }))
    const btn = wrapper.find('.btn-follow')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toBe('Suivre')
  })

  it('shows « Suivi » when the artist is already followed', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    const wrapper = await mountView(makeArtist({ following: true }))
    expect(wrapper.find('.btn-follow').text()).toBe('Suivi')
  })

  it('POSTs the follow endpoint on click and flips the label', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    const wrapper = await mountView(makeArtist({ following: false }))
    await wrapper.find('.btn-follow').trigger('click')
    await flushPromises()
    expect(apiMock.post).toHaveBeenCalledTimes(1)
    expect(apiMock.post).toHaveBeenCalledWith('/api/artists/42/follow')
    expect(wrapper.find('.btn-follow').text()).toBe('Suivi')
  })

  it('DELETEs the follow endpoint when already following', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    const wrapper = await mountView(makeArtist({ following: true }))
    await wrapper.find('.btn-follow').trigger('click')
    await flushPromises()
    expect(apiMock.delete).toHaveBeenCalledTimes(1)
    expect(apiMock.delete).toHaveBeenCalledWith('/api/artists/42/follow')
    expect(wrapper.find('.btn-follow').text()).toBe('Suivre')
  })

  it('rolls the label back when the API call fails', async () => {
    authState.value = { isAuthenticated: true, user: { username: 'will' } }
    // Deferred rejection so the optimistic state is observable before the API settles.
    let rejectFollow
    apiMock.post.mockReturnValue(
      new Promise((_, reject) => {
        rejectFollow = reject
      }),
    )
    const wrapper = await mountView(makeArtist({ following: false }))
    await wrapper.find('.btn-follow').trigger('click')
    // Optimistic flip is visible while the API is pending…
    expect(wrapper.find('.btn-follow').text()).toBe('Suivi')
    rejectFollow(new Error('boom'))
    await flushPromises()
    // …then rolled back on failure.
    expect(wrapper.find('.btn-follow').text()).toBe('Suivre')
  })
})

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
    soundcloud_id: null,
    trackid_id: null,
    real_name: null,
    country: null,
    bio: null,
    following: false,
    genres: [],
    aliases: [],
    catalog_tracks: [],
    sets: [],
    stats: { nb_catalog: 0, nb_lib: 0, nb_sets: 0, avg_rating: null },
    ...overrides,
  }
}

async function mountView(artist) {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/artists/42') return Promise.resolve({ data: artist })
    return Promise.resolve({ data: [] })
  })
  const { default: ArtistDetailView } = await import('../../views/ArtistDetailView.vue')
  // vue-router is mocked, so <router-link> never resolves to a component and
  // VTU `stubs` would not apply — register the stub as a global component.
  const wrapper = mount(ArtistDetailView, {
    global: {
      components: { RouterLink: RouterLinkStub },
      stubs: {
        StatStrip: true,
        RelBlock: true,
        StyleTag: true,
        ArtistLinks: true,
        AdminCard: true,
        ShelfCard: true,
        ExpandableShelf: true,
        LibDot: true,
        RingPct: true,
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('ArtistDetailView follow button', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.delete.mockReset()
    apiMock.post.mockResolvedValue({ data: {} })
    apiMock.delete.mockResolvedValue({ data: {} })
    authState.value = { isAuthenticated: false, user: null }
  })

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

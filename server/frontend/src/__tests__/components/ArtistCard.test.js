import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, config, RouterLinkStub } from '@vue/test-utils'

// Mutable holders shared with the hoisted mocks below.
const { apiMock, routerPush, opinionState } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), patch: vi.fn() },
  routerPush: vi.fn(),
  opinionState: { value: null },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
}))

vi.mock('../../stores/audioPlayer', () => ({
  useAudioPlayer: () => ({
    artistPlaying: null,
    close: vi.fn(),
    playRandomArtist: vi.fn(),
  }),
}))

vi.mock('../../stores/opinions.js', () => ({
  useOpinionsStore: () => ({
    get: () => opinionState.value,
    set: vi.fn(),
  }),
}))

import ArtistCard from '../../components/ArtistCard.vue'

// The genre tags are wrapped in <RouterLink>; vue-router is mocked, so register
// the stub file-wide (VTU `stubs` are a no-op for an unresolved component — see
// CLAUDE.md pitfall / BottomNav.test.js).
config.global.components = { ...config.global.components, RouterLink: RouterLinkStub }

function makeArtist(overrides = {}) {
  return {
    id: 42,
    name: 'Amelie Lens',
    has_artwork: false,
    nb_catalog: 190,
    nb_lib: 0,
    following: false,
    genres: [{ name: 'Techno', pillar: 'techno', depth: 0 }],
    top_track_artworks: [],
    tracks_with_artwork: 0,
    ...overrides,
  }
}

describe('ArtistCard follow pastille', () => {
  beforeEach(() => {
    apiMock.post.mockReset().mockResolvedValue({})
    apiMock.delete.mockReset().mockResolvedValue({})
    routerPush.mockReset()
    opinionState.value = null
  })

  it('renders the pastille unpressed when the artist is not followed', () => {
    const wrapper = mount(ArtistCard, { props: { artist: makeArtist({ following: false }) } })
    const btn = wrapper.find('.ac-follow')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('aria-pressed')).toBe('false')
    expect(btn.classes()).not.toContain('ac-follow--on')
    expect(btn.attributes('aria-label')).toBe('Suivre Amelie Lens')
  })

  it('renders the pastille pressed when the artist is followed', () => {
    const wrapper = mount(ArtistCard, { props: { artist: makeArtist({ following: true }) } })
    const btn = wrapper.find('.ac-follow')
    expect(btn.attributes('aria-pressed')).toBe('true')
    expect(btn.classes()).toContain('ac-follow--on')
    expect(btn.attributes('aria-label')).toBe('Ne plus suivre Amelie Lens')
  })

  it('POSTs follow on click, flips optimistically, and does not navigate', async () => {
    const wrapper = mount(ArtistCard, { props: { artist: makeArtist({ following: false }) } })
    await wrapper.find('.ac-follow').trigger('click')
    // Optimistic flip is visible before the API settles.
    expect(wrapper.find('.ac-follow').attributes('aria-pressed')).toBe('true')
    await flushPromises()
    expect(apiMock.post).toHaveBeenCalledTimes(1)
    expect(apiMock.post).toHaveBeenCalledWith('/api/artists/42/follow')
    expect(apiMock.delete).not.toHaveBeenCalled()
    // stopPropagation: the card must not navigate.
    expect(routerPush).not.toHaveBeenCalled()
    expect(wrapper.find('.ac-follow').attributes('aria-pressed')).toBe('true')
  })

  it('DELETEs follow on click when already following', async () => {
    const wrapper = mount(ArtistCard, { props: { artist: makeArtist({ following: true }) } })
    await wrapper.find('.ac-follow').trigger('click')
    expect(wrapper.find('.ac-follow').attributes('aria-pressed')).toBe('false')
    await flushPromises()
    expect(apiMock.delete).toHaveBeenCalledTimes(1)
    expect(apiMock.delete).toHaveBeenCalledWith('/api/artists/42/follow')
    expect(apiMock.post).not.toHaveBeenCalled()
    expect(wrapper.find('.ac-follow').attributes('aria-pressed')).toBe('false')
  })

  it('reverts the optimistic flip when the API call fails', async () => {
    // Deferred rejection so the optimistic state is observable before it settles.
    let reject
    apiMock.post.mockReturnValue(
      new Promise((_, r) => {
        reject = r
      }),
    )
    const wrapper = mount(ArtistCard, { props: { artist: makeArtist({ following: false }) } })
    await wrapper.find('.ac-follow').trigger('click')
    expect(wrapper.find('.ac-follow').attributes('aria-pressed')).toBe('true')
    reject(new Error('boom'))
    await flushPromises()
    expect(wrapper.find('.ac-follow').attributes('aria-pressed')).toBe('false')
  })

  it('follows on the follow button without touching the card link', async () => {
    // The card is now a real <a> stretched by NavCover (no JS click/keydown on the
    // card). The follow button is a separate control that .stops its click — it
    // follows and never triggers navigation.
    const wrapper = mount(ArtistCard, { props: { artist: makeArtist({ following: false }) } })
    await wrapper.find('.ac-follow').trigger('click')
    await flushPromises()
    expect(apiMock.post).toHaveBeenCalledWith('/api/artists/42/follow')
    expect(routerPush).not.toHaveBeenCalled()
  })
})

describe('ArtistCard body', () => {
  beforeEach(() => {
    routerPush.mockReset()
    opinionState.value = null
  })

  // The card is now a real stretched <a> (NavCover), not a role="link" div.
  function coverOf(wrapper) {
    return wrapper.findAllComponents(RouterLinkStub).find((l) => l.classes().includes('nav-cover'))
  }

  it('renders a whole-card link to the artist page', () => {
    const wrapper = mount(ArtistCard, { props: { artist: makeArtist() } })
    const cover = coverOf(wrapper)
    expect(cover).toBeTruthy()
    expect(cover.props('to')).toBe('/artist/42')
    expect(cover.attributes('aria-label')).toBe('Amelie Lens')
  })

  it('is a native link, not a role="link"/tabindex div', () => {
    const wrapper = mount(ArtistCard, { props: { artist: makeArtist() } })
    const card = wrapper.find('.artist-card')
    expect(card.attributes('role')).toBeUndefined()
    expect(card.attributes('tabindex')).toBeUndefined()
    // Keyboard reachability now comes from the native <a> rendered by NavCover.
    expect(coverOf(wrapper)).toBeTruthy()
  })

  it('no longer renders the rating or in-lib overlay badges', () => {
    const wrapper = mount(ArtistCard, {
      props: { artist: makeArtist({ avg_rating: 4.2, nb_lib: 5 }) },
    })
    expect(wrapper.find('.ac-rating').exists()).toBe(false)
    expect(wrapper.find('.ac-lib').exists()).toBe(false)
  })

  it('colours the In Lib value when nb_lib > 0 and shows a dash otherwise', () => {
    const withLib = mount(ArtistCard, { props: { artist: makeArtist({ nb_lib: 5 }) } })
    expect(withLib.find('.ac-stat .v-pos').text()).toBe('5')
    expect(withLib.find('.v-empty').exists()).toBe(false)

    const noLib = mount(ArtistCard, { props: { artist: makeArtist({ nb_lib: 0 }) } })
    expect(noLib.find('.ac-stat .v-pos').exists()).toBe(false)
    expect(noLib.find('.v-empty').exists()).toBe(true)
  })

  it('renders genre tags as links to /style/:name', () => {
    const wrapper = mount(ArtistCard, {
      props: { artist: makeArtist({ genres: [{ name: 'Techno', pillar: 'techno', depth: 0 }] }) },
    })
    const links = wrapper.findAllComponents(RouterLinkStub)
    expect(links.map((l) => l.props('to'))).toContain('/style/Techno')
  })

  it('always reserves the tags row so the grid does not dance when genres is empty', () => {
    const wrapper = mount(ArtistCard, { props: { artist: makeArtist({ genres: [] }) } })
    expect(wrapper.find('.ac-genres').exists()).toBe(true)
    // No genre links when genres is empty (the whole-card NavCover link is separate).
    expect(wrapper.findAll('.ac-genre-link')).toHaveLength(0)
  })
})

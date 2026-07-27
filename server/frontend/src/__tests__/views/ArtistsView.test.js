import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// Mutable holders shared with the hoisted mocks below.
const { apiMock } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

// The child ArtistCard pulls in vue-router + stores; the view itself does not.
// Stub it so this suite only exercises the view's head, filters and empty states.
const STUBS = {
  ArtistCard: { props: ['artist'], template: '<div class="ac-stub">{{ artist.name }}</div>' },
}

let opinionsResponse
let listResponse

function installApiMock() {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/opinions/') return Promise.resolve({ data: opinionsResponse })
    if (url === '/api/artists/') return Promise.resolve({ data: listResponse })
    return Promise.resolve({ data: {} })
  })
}

// Only the list endpoint, in call order — opinions hits a different URL.
function artistsCalls() {
  return apiMock.get.mock.calls.filter(([url]) => url === '/api/artists/')
}
function lastArtistsParams() {
  const calls = artistsCalls()
  return calls[calls.length - 1][1].params
}

function clickSeg(wrapper, label) {
  const btn = wrapper.findAll('.filterseg button').find((b) => b.text() === label)
  return btn.trigger('click')
}

async function mountView() {
  const { default: ArtistsView } = await import('../../views/ArtistsView.vue')
  const wrapper = mount(ArtistsView, {
    global: {
      plugins: [createPinia()],
      components: { RouterLink: RouterLinkStub },
      stubs: STUBS,
    },
  })
  await flushPromises()
  return wrapper
}

describe('ArtistsView', () => {
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
    setActivePinia(createPinia())
    opinionsResponse = { artist: {} }
    listResponse = {
      total: 3,
      items: [
        { id: 1, name: 'Amelie Lens', nb_catalog: 190, nb_lib: 0, following: false, genres: [] },
      ],
      pillarCounts: { techno: 3 },
    }
    installApiMock()
  })

  it('fetches the paginated list on mount with the default catalog sort', async () => {
    await mountView()
    const p = lastArtistsParams()
    expect(p.sort).toBe('catalog')
    expect(p.limit).toBe(24)
    expect(p.offset).toBe(0)
    expect(p.followed).toBeUndefined()
    expect(p.no_deezer).toBeUndefined()
  })

  it('offers a « Suivis » segment and no « Rating » segment', async () => {
    const wrapper = await mountView()
    const labels = wrapper.findAll('.filterseg button').map((b) => b.text())
    expect(labels).toContain('Suivis')
    expect(labels).not.toContain('Rating')
  })

  it('sends followed=true with a valid default sort when « Suivis » is selected', async () => {
    const wrapper = await mountView()
    await clickSeg(wrapper, 'Suivis')
    await flushPromises()
    const p = lastArtistsParams()
    expect(p.followed).toBe(true)
    expect(p.sort).toBe('catalog') // « followed » is a filter, not a backend sort
  })

  it('shows the dedicated « Suivis » empty state (icon + invite + reset button) when nobody is followed', async () => {
    const wrapper = await mountView()
    listResponse = { total: 0, items: [], pillarCounts: { techno: 3 } }
    await clickSeg(wrapper, 'Suivis')
    await flushPromises()

    const empty = wrapper.find('.empty-follow')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain("Tu ne suis aucun artiste pour l'instant.")
    expect(empty.find('.ef-icon').exists()).toBe(true)
    // The generic search/filter empty state must NOT be the one rendered here.
    expect(wrapper.find('.empty-search').exists()).toBe(false)
  })

  it('« Voir tout le catalogue » returns to the catalog segment without the followed filter', async () => {
    const wrapper = await mountView()
    listResponse = { total: 0, items: [], pillarCounts: { techno: 3 } }
    await clickSeg(wrapper, 'Suivis')
    await flushPromises()

    listResponse = {
      total: 3,
      items: [{ id: 1, name: 'Amelie Lens', nb_catalog: 190, nb_lib: 0, genres: [] }],
      pillarCounts: { techno: 3 },
    }
    await wrapper.find('.empty-follow .btn').trigger('click')
    await flushPromises()

    const p = lastArtistsParams()
    expect(p.sort).toBe('catalog')
    expect(p.followed).toBeUndefined()
    expect(wrapper.find('.empty-follow').exists()).toBe(false)
  })

  it('adds no_deezer=true for the current sort when the « Sans Deezer » toggle is on', async () => {
    const wrapper = await mountView()
    const toggle = wrapper.find('.no-dz')
    expect(toggle.attributes('aria-checked')).toBe('false')
    await toggle.trigger('click')
    await flushPromises()

    expect(toggle.attributes('aria-checked')).toBe('true')
    const p = lastArtistsParams()
    expect(p.no_deezer).toBe(true)
    expect(p.sort).toBe('catalog')
  })
})

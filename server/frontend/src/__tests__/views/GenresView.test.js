import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

// Mutable holders shared with the hoisted mocks below.
const { apiMock, authStore, routeState, routerReplace } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
  // Minimal auth store stand-in: only `user` is read (admin gate on the strip).
  authStore: { user: null },
  routeState: {},
  routerReplace: vi.fn(),
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))
vi.mock('../../stores/auth.js', () => ({ useAuthStore: () => authStore }))
vi.mock('vue-router', () => ({
  useRoute: () => routeState.route,
  useRouter: () => ({ push: vi.fn(), replace: routerReplace }),
  onBeforeRouteLeave: vi.fn(),
}))

// The child GenreCard pulls in vue-router + stores; the view itself does not.
// Stub it so this suite only exercises the view's head, filters and empty states.
const STUBS = {
  GenreCard: { props: ['genre'], template: '<div class="gc-stub">{{ genre.name }}</div>' },
}

let listResponse

function installApiMock() {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/genres') return Promise.resolve({ data: listResponse })
    if (url === '/api/admin/genres/unclassified-count')
      return Promise.resolve({ data: { count: 0 } })
    return Promise.resolve({ data: {} })
  })
}

// Only the list endpoint, in call order.
function genresCalls() {
  return apiMock.get.mock.calls.filter(([url]) => url === '/api/genres')
}
function lastGenresParams() {
  const calls = genresCalls()
  return calls[calls.length - 1][1].params
}

function clickSeg(wrapper, label) {
  const btn = wrapper.findAll('.filterseg button').find((b) => b.text() === label)
  return btn.trigger('click')
}

async function mountView() {
  const { default: GenresView } = await import('../../views/GenresView.vue')
  const wrapper = mount(GenresView, {
    global: {
      plugins: [createPinia()],
      stubs: STUBS,
    },
  })
  await flushPromises()
  return wrapper
}

describe('GenresView', () => {
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
    routerReplace.mockReset()
    routeState.route = reactive({ path: '/genres', query: {} })
    setActivePinia(createPinia())
    authStore.user = null
    listResponse = {
      total: 1,
      items: [{ name: 'House', pillar: 'house', depth: 0, trackCount: 1180, inLibCount: 79 }],
      pillarCounts: { house: 17 },
    }
    installApiMock()
  })

  it('fetches the paginated list on mount with the default « Tracks » sort', async () => {
    await mountView()
    const p = lastGenresParams()
    expect(p.sort).toBe('tracks')
    expect(p.limit).toBe(24)
    expect(p.offset).toBe(0)
  })

  it('offers an « En bib » sort segment', async () => {
    const wrapper = await mountView()
    const labels = wrapper.findAll('.filterseg button').map((b) => b.text())
    expect(labels).toEqual(['Tracks', 'En bib', 'A–Z', 'Liked', 'Disliked'])
  })

  it('sends sort=lib when the « En bib » segment is selected', async () => {
    const wrapper = await mountView()
    await clickSeg(wrapper, 'En bib')
    await flushPromises()
    expect(lastGenresParams().sort).toBe('lib')
  })

  it('shows the dedicated « Liked » empty state (pastille + invite + reset) when nothing is liked', async () => {
    const wrapper = await mountView()
    await clickSeg(wrapper, 'Liked')
    await flushPromises()

    const empty = wrapper.find('.empty-facet--liked')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain("Aucun genre liké pour l'instant.")
    expect(empty.find('.ef-icon').exists()).toBe(true)
    // The generic search empty state must NOT be the one rendered here.
    expect(wrapper.find('.empty-search').exists()).toBe(false)
  })

  it('counts the shown items (not the server total) in the subtitle on an avis facet', async () => {
    const wrapper = await mountView()
    await clickSeg(wrapper, 'Liked')
    await flushPromises()

    // Nothing is liked: the client-side facet shows 0 cards, and the counter
    // must say so — not the server-page total (1) it used to display.
    // Right member = totalUnfiltered (sum of pillarCounts, here 17).
    expect(wrapper.find('.sub').text()).toBe('0 / 17 genres')
  })

  it('the « Disliked » empty copy names the barred heart, not a thumb', async () => {
    const wrapper = await mountView()
    await clickSeg(wrapper, 'Disliked')
    await flushPromises()

    const empty = wrapper.find('.empty-facet--disliked')
    expect(empty.exists()).toBe(true)
    expect(empty.find('.ef-sub').text()).toContain('cœur barré')
    expect(empty.find('.ef-sub').text()).not.toContain('pouce')
  })

  it('« Voir tous les genres » returns to the Tracks segment', async () => {
    const wrapper = await mountView()
    await clickSeg(wrapper, 'Liked')
    await flushPromises()

    await wrapper.find('.empty-facet--liked .btn').trigger('click')
    await flushPromises()

    expect(lastGenresParams().sort).toBe('tracks')
    expect(wrapper.find('.empty-facet--liked').exists()).toBe(false)
  })

  it('hides the admin strip for a non-admin viewer and shows it for an admin', async () => {
    const guest = await mountView()
    expect(guest.find('.admin-strip').exists()).toBe(false)

    authStore.user = { is_admin: true }
    const admin = await mountView()
    expect(admin.find('.admin-strip').exists()).toBe(true)
  })
})

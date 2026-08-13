import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'

// « Ça sort en ce moment » became a self-contained, lazy-loaded section owning its
// own trend fetch + queue source. Shown to guests and members; the « Voir plus »
// destination and open-track guard adapt to the auth state.
const { authState, apiMock, toastMock } = vi.hoisted(() => ({
  authState: { value: { isAuthenticated: false } },
  apiMock: { get: vi.fn() },
  toastMock: { show: vi.fn() },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))
vi.mock('../../stores/auth', () => ({ useAuthStore: () => authState.value }))
vi.mock('../../stores/toast.js', () => ({ useToast: () => toastMock }))
vi.mock('../../stores/audioPlayer', () => ({
  useAudioPlayer: () => ({ track: null, playing: false, play: vi.fn() }),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

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

function mockTrends({ items = [], familyCounts = {} } = {}) {
  apiMock.get.mockResolvedValue({ data: { items, family_counts: familyCounts } })
}

async function mountSection() {
  const { default: HubTrendsSection } = await import('../../components/hub/HubTrendsSection.vue')
  const wrapper = mount(HubTrendsSection, {
    global: {
      components: { RouterLink: RouterLinkStub },
      stubs: { FamilyChips: true },
    },
  })
  await flushPromises()
  return wrapper
}

describe('HubTrendsSection', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    toastMock.show.mockReset()
    authState.value = { isAuthenticated: false }
  })

  it('fetches trends on mount and renders a card per track', async () => {
    mockTrends({ items: [TREND_ITEM] })
    const wrapper = await mountSection()

    expect(apiMock.get).toHaveBeenCalledWith('/api/radar/trends', { params: { limit: 9 } })
    const shelf = wrapper.find('.discover')
    expect(shelf.exists()).toBe(true)
    expect(shelf.find('.discover-title').text()).toBe('Ça sort en ce moment')

    const cards = shelf.findAll('.dc-card')
    expect(cards).toHaveLength(1)
    expect(cards[0].text()).toContain('La La Land')
    // Trend variant → #rank badge.
    expect(cards[0].find('.dc-badge').text()).toBe('#1')
    expect(cards[0].find('img.aw-img').attributes('src')).toBe('/storage/catalog-artworks/300.jpg')
  })

  it('renders nothing when there are no trends and no family is selected', async () => {
    mockTrends({ items: [] })
    const wrapper = await mountSection()
    expect(wrapper.find('.discover').exists()).toBe(false)
  })

  it('points « Voir plus » to /login for guests', async () => {
    mockTrends({ items: [TREND_ITEM] })
    const wrapper = await mountSection()
    expect(wrapper.findComponent(RouterLinkStub).props('to')).toBe('/login')
  })

  it('points « Voir plus » to /radar for authenticated users', async () => {
    authState.value = { isAuthenticated: true }
    mockTrends({ items: [TREND_ITEM] })
    const wrapper = await mountSection()
    expect(wrapper.findComponent(RouterLinkStub).props('to')).toBe('/radar')
  })

  it('intercepts an open for a guest with a login toast (no navigation)', async () => {
    mockTrends({ items: [TREND_ITEM] })
    const wrapper = await mountSection()
    await wrapper.find('.dc-card').trigger('click')
    expect(toastMock.show).toHaveBeenCalledTimes(1)
    expect(toastMock.show.mock.calls[0][0]).toContain('Connecte-toi')
  })
})

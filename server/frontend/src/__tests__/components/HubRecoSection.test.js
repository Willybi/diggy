import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'

// Ported from HubView.test.js: « Pour toi » became a self-contained, lazy-loaded
// section owning its own fetch. Only mounted for authenticated users (the Hub
// gates it — covered in HubView.test.js), so it carries no guest branches.
const { apiMock } = vi.hoisted(() => ({
  apiMock: { get: vi.fn() },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

vi.mock('../../stores/audioPlayer', () => ({
  useAudioPlayer: () => ({
    track: null,
    playing: false,
    play: vi.fn(),
  }),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

const RECO_ITEM = {
  id: 42,
  title: 'Strobe',
  artist: 'Deadmau5',
  bpm: 128,
  key: '8A',
  has_artwork: true,
  has_preview: true,
  in_lib: false,
  reco_score: 0.91,
}

async function mountSection() {
  const { default: HubRecoSection } = await import('../../components/hub/HubRecoSection.vue')
  const wrapper = mount(HubRecoSection, {
    global: { components: { RouterLink: RouterLinkStub } },
  })
  await flushPromises()
  return wrapper
}

describe('HubRecoSection', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
  })

  it('renders nothing when the feed is empty', async () => {
    apiMock.get.mockResolvedValue({ data: { items: [] } })
    const wrapper = await mountSection()
    expect(wrapper.find('.discover--foryou').exists()).toBe(false)
  })

  it('renders reco cards when the feed has items', async () => {
    apiMock.get.mockResolvedValue({ data: { items: [RECO_ITEM] } })
    const wrapper = await mountSection()

    const shelf = wrapper.find('.discover--foryou')
    expect(shelf.exists()).toBe(true)
    expect(shelf.find('.discover-title').text()).toBe('Pour toi')

    const cards = shelf.findAll('.dc-card')
    expect(cards).toHaveLength(1)
    expect(cards[0].text()).toContain('Strobe')
    expect(cards[0].text()).toContain('Deadmau5')
    // Cover keyed on `id` (not catalog_id).
    expect(shelf.find('img.aw-img').attributes('src')).toBe('/storage/catalog-artworks/42.jpg')
  })

  it('hits /api/recommendations/ with the canonical trailing slash', async () => {
    apiMock.get.mockResolvedValue({ data: { items: [] } })
    await mountSection()
    expect(apiMock.get).toHaveBeenCalledWith('/api/recommendations/', { params: { limit: 9 } })
  })

  it('stays inert (renders nothing) when the recommendations endpoint fails', async () => {
    apiMock.get.mockRejectedValue(new Error('boom'))
    const wrapper = await mountSection()
    expect(wrapper.find('.discover--foryou').exists()).toBe(false)
  })

  it('shows a skeleton while the recommendations are still loading', async () => {
    apiMock.get.mockReturnValue(new Promise(() => {})) // never resolves
    const wrapper = await mountSection()
    const shelf = wrapper.find('.discover--foryou')
    expect(shelf.exists()).toBe(true)
    expect(shelf.attributes('aria-busy')).toBe('true')
    // Skeleton ghosts come from <DiscoveryCard skeleton />.
    expect(shelf.findAll('.dc-card--skeleton').length).toBeGreaterThan(0)
    // No real reco cards / no header yet.
    expect(shelf.find('.discover-head').exists()).toBe(false)
  })
})

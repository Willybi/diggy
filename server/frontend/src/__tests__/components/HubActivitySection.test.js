import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// Ported from HubView.test.js: the followed-artists activity shelf became a
// self-contained, lazy-loaded section that owns its own fetch + seen-marking.
// The Hub only decides WHETHER to mount it (auth gating, covered in HubView.test.js).
const { apiMock } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn() },
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

const RELEASE_ITEM = {
  id: 1,
  type: 'release',
  title: 'Song A',
  artist: 'Amelie Lens',
  artist_name: 'Amelie Lens',
  catalog_id: 909,
  has_artwork: true,
  has_preview: true,
  bpm: 138,
  key: '11A',
  release_date: '2026-07-11',
}
const RELEASE_LINK_ITEM = {
  id: 3,
  type: 'release',
  title: 'Uncrawled EP',
  artist_name: 'Amelie Lens',
  external_url: 'https://www.deezer.com/album/123',
}
const SET_ITEM = {
  id: 2,
  type: 'set',
  title: 'Awakenings 2026',
  artist_name: 'Amelie Lens',
  set_id: 77,
}
const ALBUM_TRACK_A = {
  id: 10,
  type: 'release',
  title: 'Track One',
  artist: 'Charlotte de Witte',
  artist_name: 'Charlotte de Witte',
  catalog_id: 501,
  has_artwork: true,
  has_preview: true,
  release_date: '2026-07-12',
  payload: { album_id: '9001', album_title: 'Formula EP' },
}
const ALBUM_TRACK_B = {
  id: 11,
  type: 'release',
  title: 'Track Two',
  artist: 'Charlotte de Witte',
  artist_name: 'Charlotte de Witte',
  catalog_id: 502,
  has_artwork: true,
  has_preview: false,
  release_date: '2026-07-12',
  payload: { album_id: '9001', album_title: 'Formula EP' },
}

function mockApiGet({ activityItems = [], newCount = 0 } = {}) {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/following/activity/new-count') {
      return Promise.resolve({ data: { count: newCount } })
    }
    if (url === '/api/following/activity') {
      return Promise.resolve({ data: { items: activityItems } })
    }
    return Promise.resolve({ data: {} })
  })
}

async function mountSection() {
  const { default: HubActivitySection } =
    await import('../../components/hub/HubActivitySection.vue')
  const wrapper = mount(HubActivitySection)
  await flushPromises()
  return wrapper
}

describe('HubActivitySection', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.post.mockResolvedValue({ data: {} })
  })

  it('renders nothing when the feed is empty and marks nothing seen', async () => {
    mockApiGet({ activityItems: [] })
    const wrapper = await mountSection()
    expect(wrapper.find('.discover--activity').exists()).toBe(false)
    expect(apiMock.post).not.toHaveBeenCalled()
  })

  it('renders a crawled release as a DiscoveryCard and a set as a « Set » card', async () => {
    mockApiGet({ activityItems: [RELEASE_ITEM, SET_ITEM] })
    const wrapper = await mountSection()

    const shelf = wrapper.find('.discover--activity')
    expect(shelf.exists()).toBe(true)
    expect(shelf.find('.discover-title').text()).toContain('Nouveautés de tes artistes')

    const cards = shelf.findAll('.dc-card')
    const release = cards.find((c) => c.text().includes('Song A'))
    expect(release).toBeTruthy()
    expect(release.element.tagName).toBe('DIV')
    expect(release.find('.dc-badge').text()).toBe('Nouveauté')
    expect(release.find('img.aw-img').attributes('src')).toBe('/storage/catalog-artworks/909.jpg')
    expect(release.find('.dc-play').exists()).toBe(true)
    expect(release.text()).toContain('Amelie Lens')

    const setCard = cards.find((c) => c.text().includes('Awakenings 2026'))
    expect(setCard).toBeTruthy()
    expect(setCard.element.tagName).toBe('DIV')
    expect(setCard.find('.dc-badge').text()).toBe('Set')
    expect(setCard.find('.dc-play').exists()).toBe(false)
  })

  it('renders an uncrawled release as an external Deezer link', async () => {
    mockApiGet({ activityItems: [RELEASE_LINK_ITEM] })
    const wrapper = await mountSection()

    const link = wrapper.find('a.dc-card')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe(RELEASE_LINK_ITEM.external_url)
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toBe('noopener')
    expect(link.find('.dc-badge').text()).toBe('Nouveauté')
    expect(link.text()).toContain('Uncrawled EP')
  })

  it('renders the « Voir plus » as an inert « Bientôt » (no dead link)', async () => {
    mockApiGet({ activityItems: [RELEASE_ITEM] })
    const wrapper = await mountSection()

    const more = wrapper.find('.discover-more')
    expect(more.exists()).toBe(true)
    expect(more.element.tagName).toBe('SPAN')
    expect(more.text()).toBe('Bientôt')
    expect(more.classes()).toContain('is-disabled')
    expect(more.attributes('aria-disabled')).toBe('true')
  })

  it('shows the « N nouvelles » badge while items are not yet marked seen', async () => {
    mockApiGet({ activityItems: [RELEASE_ITEM], newCount: 3 })
    // Keep the seen POST pending so the badge stays visible.
    apiMock.post.mockReturnValue(new Promise(() => {}))
    const wrapper = await mountSection()

    const badge = wrapper.find('.ac-new-badge')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('3 nouvelles')
  })

  it('POSTs seen after the feed is displayed and hides the badge', async () => {
    mockApiGet({ activityItems: [RELEASE_ITEM], newCount: 3 })
    const wrapper = await mountSection()

    expect(apiMock.post).toHaveBeenCalledTimes(1)
    expect(apiMock.post).toHaveBeenCalledWith('/api/following/activity/seen')
    expect(wrapper.find('.ac-new-badge').exists()).toBe(false)
    expect(wrapper.find('.discover--activity').exists()).toBe(true)
  })

  it('stays inert (renders nothing) when the activity endpoints fail', async () => {
    apiMock.get.mockRejectedValue(new Error('boom'))
    const wrapper = await mountSection()
    expect(wrapper.find('.discover--activity').exists()).toBe(false)
  })

  it('collapses tracks sharing an album_id into one expandable album card', async () => {
    mockApiGet({ activityItems: [ALBUM_TRACK_A, ALBUM_TRACK_B] })
    const wrapper = await mountSection()

    const shelf = wrapper.find('.discover--activity')
    const albumCards = shelf.findAll('.album-card')
    expect(albumCards).toHaveLength(1)
    expect(shelf.findAll('.dc-card')).toHaveLength(0)

    const card = albumCards[0]
    expect(card.text()).toContain('Formula EP')
    expect(card.text()).toContain('2 titres')
    expect(card.find('.tc-art img').attributes('src')).toBe('/storage/catalog-artworks/501.jpg')

    expect(card.find('.ac-list').exists()).toBe(false)
    await card.find('.ac-toggle').trigger('click')
    expect(card.find('.ac-list').exists()).toBe(true)
    expect(card.text()).toContain('Track One')
    expect(card.text()).toContain('Track Two')
  })

  it('renders a lone release with an album_id as a single track card (no collapse)', async () => {
    mockApiGet({
      activityItems: [{ ...RELEASE_ITEM, payload: { album_id: '7', album_title: 'Solo' } }],
    })
    const wrapper = await mountSection()

    const shelf = wrapper.find('.discover--activity')
    expect(shelf.find('.album-card').exists()).toBe(false)
    const card = shelf.find('.dc-card')
    expect(card.element.tagName).toBe('DIV')
    expect(card.text()).toContain('Song A')
    expect(card.find('img.aw-img').attributes('src')).toBe('/storage/catalog-artworks/909.jpg')
  })

  it('dedups a collab track surfaced via two followed artists', async () => {
    const collabA = { ...RELEASE_ITEM, id: 20 }
    const collabB = { ...RELEASE_ITEM, id: 21 }
    mockApiGet({ activityItems: [collabA, collabB] })
    const wrapper = await mountSection()

    const shelf = wrapper.find('.discover--activity')
    expect(shelf.findAll('.dc-card')).toHaveLength(1)
  })
})

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'
import TrackCard from '../../components/TrackCard.vue'
import BackButton from '../../components/BackButton.vue'

// Mutable holders shared with the hoisted mocks below.
const { apiMock, routerPush, playerMock } = vi.hoisted(() => ({
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
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

vi.mock('../../stores/audioPlayer', () => ({
  useAudioPlayer: () => playerMock,
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '1' } }),
  useRouter: () => ({ push: routerPush, replace: vi.fn() }),
}))

function makeTracks(n) {
  return Array.from({ length: n }, (_, i) => ({
    id: 100 + i,
    title: `Track ${i}`,
    artist: `Artist ${i}`,
    artists: [{ id: 10 + i, name: `Artist ${i}`, has_artwork: false }],
    bpm: 128,
    key: '9A',
    bpm_source: 'beatport',
    duration_ms: 300000,
    has_artwork: false,
    has_preview: true,
    in_lib: i % 2 === 0,
  }))
}

function makeAlbum(overrides = {}) {
  return {
    id: 1,
    title: 'Peak Time',
    record_type: 'album',
    release_date: '2026-01-15',
    label: 'Drumcode',
    artist: { id: 7, name: 'Adam Beyer', has_artwork: false },
    has_artwork: false,
    total_tracks: 3,
    tracklist: makeTracks(3),
    ...overrides,
  }
}

const globalOpts = {
  global: {
    components: { RouterLink: RouterLinkStub },
  },
}

async function mountView(album) {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/albums/1') {
      return album ? Promise.resolve({ data: album }) : Promise.reject(new Error('404'))
    }
    return Promise.resolve({ data: {} })
  })
  const { default: AlbumView } = await import('../../views/AlbumView.vue')
  const wrapper = mount(AlbumView, globalOpts)
  await flushPromises()
  return wrapper
}

describe('AlbumView', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    routerPush.mockReset()
    playerMock.playing = false
  })

  // ---- Hero ----

  it('renders the hero title and artist link', async () => {
    const wrapper = await mountView(makeAlbum())
    expect(wrapper.find('.hero-title').text()).toBe('Peak Time')
    expect(wrapper.find('.hero-artist-link').text()).toBe('Adam Beyer')
    expect(wrapper.findComponent(RouterLinkStub).props('to')).toBe('/artist/7')
  })

  it('renders the record type, label and tracks stats', async () => {
    const wrapper = await mountView(makeAlbum())
    const labels = wrapper.findAll('.stat-label').map((l) => l.text())
    expect(labels).toEqual(['Type', 'Date', 'Label', 'Tracks'])
    const vals = wrapper.findAll('.stat-val').map((v) => v.text())
    expect(vals[0]).toBe('Album')
    expect(vals[2]).toBe('Drumcode')
    expect(vals[3]).toBe('3')
  })

  it('hides the Type cell when record_type is null and the Label cell when absent', async () => {
    const wrapper = await mountView(makeAlbum({ record_type: null, label: null }))
    const labels = wrapper.findAll('.stat-label').map((l) => l.text())
    expect(labels).toEqual(['Date', 'Tracks'])
  })

  it('hides the artist block when there is no album artist', async () => {
    const wrapper = await mountView(makeAlbum({ artist: null }))
    expect(wrapper.find('.hero-artists').exists()).toBe(false)
  })

  // ---- coverSrc conditioned by has_artwork ----

  it('renders no backdrop and a placeholder cover when has_artwork is false', async () => {
    const wrapper = await mountView(makeAlbum({ has_artwork: false }))
    expect(wrapper.find('.hero-backdrop').exists()).toBe(false)
  })

  it('renders the blurred backdrop from album-artworks when has_artwork is true', async () => {
    const wrapper = await mountView(makeAlbum({ has_artwork: true }))
    const backdrop = wrapper.find('.hero-backdrop img')
    expect(backdrop.exists()).toBe(true)
    expect(backdrop.attributes('src')).toBe('/storage/album-artworks/1.jpg')
  })

  // ---- Tracklist ----

  it('renders the tracklist as TrackCard rows in order with a counter', async () => {
    const wrapper = await mountView(makeAlbum({ tracklist: makeTracks(3), total_tracks: 3 }))
    const cards = wrapper.findAllComponents(TrackCard)
    expect(cards).toHaveLength(3)
    expect(cards[0].props('showDuration')).toBe(true)
    expect(cards[0].props('showArtist')).toBe(true)
    expect(cards[0].props('position')).toBe(1)
    expect(cards.map((c) => c.props('track').id)).toEqual([100, 101, 102])
    expect(wrapper.find('.sec-count').text()).toContain('3 tracks')
  })

  it('navigates to the track detail on a row click', async () => {
    const wrapper = await mountView(makeAlbum({ tracklist: makeTracks(1), total_tracks: 1 }))
    await wrapper.findComponent(TrackCard).trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/catalog/100')
  })

  // ---- States ----

  it('shows the not-found state with a return button falling back to "/"', async () => {
    const wrapper = await mountView(null)
    expect(wrapper.find('.state--empty').text()).toContain('Album introuvable')
    expect(wrapper.findComponent(BackButton).props('fallback')).toBe('/')
  })
})

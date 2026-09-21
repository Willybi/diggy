import { describe, it, expect, vi } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import HubSearchResults from '../../components/hub/HubSearchResults.vue'

// Props-driven display component: HubView owns the search state, this renders the
// rows. Each row is a NavCover-backed real link now (nav-native chantier), so we
// assert the route target per result type.
vi.mock('../../stores/auth', () => ({
  useAuthStore: () => ({ isAuthenticated: true }),
}))
vi.mock('../../stores/audioPlayer', () => ({
  useAudioPlayer: () => ({
    track: null,
    playing: false,
    artistPlaying: null,
    play: vi.fn(),
    playRandomArtist: vi.fn(),
  }),
}))

const ITEMS = [
  { type: 'track', id: 5, title: 'Strobe', artist: 'Deadmau5' },
  { type: 'artist', id: 6, name: 'Deadmau5', track_count: 3 },
  { type: 'set', id: 7, title: 'Awakenings', track_count: 12 },
  { type: 'album', id: 8, title: 'Random Album', artist: 'Someone' },
  { type: 'playlist', id: 9, name: 'My Playlist', track_count: 4 },
  { type: 'genre', name: 'Deep House', track_count: 2, artist_count: 1 },
]

function mountResults(items = ITEMS) {
  return mount(HubSearchResults, {
    props: { items, total: items.length, query: 'x' },
    global: {
      components: { RouterLink: RouterLinkStub },
      // BeatportPlayButton reads the Pinia overlay store at setup → stub it.
      stubs: { BeatportPlayButton: true },
    },
  })
}

describe('HubSearchResults', () => {
  it('renders one navigable row per item with the right internal target', () => {
    const wrapper = mountResults()
    const rows = wrapper.findAll('.rrow')
    expect(rows).toHaveLength(ITEMS.length)

    const targets = rows.map((r) => r.findComponent(RouterLinkStub).props('to'))
    expect(targets).toEqual([
      '/catalog/5',
      '/artist/6',
      '/set/7',
      '/album/8',
      '/playlists/9',
      '/style/Deep%20House',
    ])
  })

  it('keeps the play control clickable above the row link (track)', async () => {
    const wrapper = mountResults([{ type: 'track', id: 5, title: 'Strobe', has_preview: true }])
    const play = wrapper.find('.rart .play')
    expect(play.exists()).toBe(true)
    await play.trigger('click')
    // No throw = the @click.stop play handler fired without navigating.
  })

  // D12: a preview-less track result with a beatport_id gets the shared Beatport
  // overlay button in the artwork spot; a Deezer preview ALWAYS wins over it.
  it('renders the Beatport fallback on a preview-less track with a beatport_id', () => {
    const wrapper = mountResults([
      { type: 'track', id: 5, title: 'Strobe', artist: 'Deadmau5', beatport_id: 321 },
    ])
    expect(wrapper.find('.rart .play').exists()).toBe(false)
    expect(wrapper.find('.rart .bp-play beatport-play-button-stub').exists()).toBe(true)
  })

  it('keeps the Deezer play button (no Beatport) when the preview exists', () => {
    const wrapper = mountResults([
      { type: 'track', id: 5, title: 'Strobe', has_preview: true, beatport_id: 321 },
    ])
    expect(wrapper.find('.rart .play').exists()).toBe(true)
    expect(wrapper.find('beatport-play-button-stub').exists()).toBe(false)
  })

  it('never renders the Beatport fallback on a non-track row', () => {
    const wrapper = mountResults([{ type: 'artist', id: 6, name: 'Deadmau5', beatport_id: 321 }])
    // The artist row keeps its own play affordance and never the Beatport one.
    expect(wrapper.find('.rart .play').exists()).toBe(true)
    expect(wrapper.find('beatport-play-button-stub').exists()).toBe(false)
  })

  it('renders no link for an unknown type', () => {
    const wrapper = mountResults([{ type: 'mystery', id: 1, title: '?' }])
    const row = wrapper.find('.rrow')
    expect(row.exists()).toBe(true)
    expect(row.findComponent(RouterLinkStub).exists()).toBe(false)
    expect(row.find('a.nav-cover').exists()).toBe(false)
  })
})

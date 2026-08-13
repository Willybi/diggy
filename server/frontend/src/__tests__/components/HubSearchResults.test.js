import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import HubSearchResults from '../../components/hub/HubSearchResults.vue'

// The search results list became a lazy-loaded section fed the raw items by
// HubView (which keeps the search state). This section owns the display sort +
// every rendering helper + row navigation/playback.
const { authState, playerMock, toastMock, routerPush } = vi.hoisted(() => ({
  authState: { value: { isAuthenticated: true } },
  playerMock: {
    track: null,
    playing: false,
    artistPlaying: null,
    play: vi.fn(),
    playRandomArtist: vi.fn(),
  },
  toastMock: { show: vi.fn() },
  routerPush: vi.fn(),
}))

vi.mock('../../stores/auth', () => ({ useAuthStore: () => authState.value }))
vi.mock('../../stores/toast.js', () => ({ useToast: () => toastMock }))
vi.mock('../../stores/audioPlayer', () => ({ useAudioPlayer: () => playerMock }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: routerPush }) }))

const TRACK = {
  type: 'track',
  id: 1,
  title: 'Strobe',
  artist: 'Deadmau5',
  bpm: 128,
  key: '8A',
  duration_ms: 634000,
  has_preview: true,
  in_lib: false,
}
const ARTIST = { type: 'artist', id: 5, name: 'Deadmau5', track_count: 12, has_artwork: false }

function mountResults(props = {}) {
  return mount(HubSearchResults, {
    props: { items: [TRACK], total: 1, query: 'strobe', loading: false, ...props },
    global: { stubs: { SegFilter: true, SourceBadge: true } },
  })
}

describe('HubSearchResults', () => {
  beforeEach(() => {
    authState.value = { isAuthenticated: true }
    toastMock.show.mockReset()
    routerPush.mockReset()
    playerMock.play.mockReset()
  })

  it('renders a row per item with its type badge and title', () => {
    const wrapper = mountResults({ items: [TRACK, ARTIST], total: 2 })
    const rows = wrapper.findAll('.rrow')
    expect(rows).toHaveLength(2)
    expect(rows[0].find('.tbadge .lbl').text()).toBe('TRACK')
    expect(rows[0].find('.rtitle').text()).toContain('Strobe')
    expect(rows[1].find('.tbadge .lbl').text()).toBe('ARTISTE')
  })

  it('highlights the query term inside the title', () => {
    const wrapper = mountResults({ items: [TRACK], query: 'stro' })
    expect(wrapper.find('.rtitle').html()).toContain('<mark>')
  })

  it('shows the sort tools for an authenticated user', () => {
    const wrapper = mountResults()
    expect(wrapper.find('.results-tools').exists()).toBe(true)
    expect(wrapper.find('.tools-locked').exists()).toBe(false)
  })

  it('shows a locked-tools hint for a guest', () => {
    authState.value = { isAuthenticated: false }
    const wrapper = mountResults()
    expect(wrapper.find('.tools-locked').exists()).toBe(true)
  })

  it('shows the guest lock row when there are more results than shown', () => {
    authState.value = { isAuthenticated: false }
    const wrapper = mountResults({ items: [TRACK], total: 50 })
    const lock = wrapper.find('.lockrow')
    expect(lock.exists()).toBe(true)
    expect(lock.text()).toContain('49 autres')
  })

  it('renders the empty message when there are no items and not loading', () => {
    const wrapper = mountResults({ items: [], total: 0, loading: false })
    expect(wrapper.find('.r-empty').exists()).toBe(true)
  })

  it('does not render the empty message while a search is loading', () => {
    const wrapper = mountResults({ items: [], total: 0, loading: true })
    expect(wrapper.find('.r-empty').exists()).toBe(false)
  })

  it('navigates on row click for an authenticated user', async () => {
    const wrapper = mountResults({ items: [TRACK] })
    await wrapper.find('.rrow').trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/catalog/1')
  })

  it('intercepts a row click for a guest with a login toast (no navigation)', async () => {
    authState.value = { isAuthenticated: false }
    const wrapper = mountResults({ items: [TRACK] })
    await wrapper.find('.rrow').trigger('click')
    expect(toastMock.show).toHaveBeenCalledTimes(1)
    expect(routerPush).not.toHaveBeenCalled()
  })
})

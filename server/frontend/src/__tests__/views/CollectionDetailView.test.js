import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import CollectionDetailView from '../../views/CollectionDetailView.vue'

// Mutable holders shared with the hoisted mocks below.
const { apiMock, routerPush, playerMock } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), patch: vi.fn() },
  routerPush: vi.fn(),
  playerMock: {
    isCurrent: () => false,
    playing: false,
    play: vi.fn(),
  },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))
vi.mock('../../stores/audioPlayer', () => ({ useAudioPlayer: () => playerMock }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '3' } }),
  useRouter: () => ({ push: routerPush, replace: vi.fn() }),
}))

// A heterogeneous collection: one track + one of every non-track type + a missing item.
function makeCollection() {
  return {
    id: 3,
    name: 'Ma sélection',
    type: 'playlist',
    item_count: 6,
    items: [
      {
        item_type: 'track',
        item_id: 11,
        item_name: null,
        title: 'Strobe',
        subtitle: 'deadmau5',
        has_artwork: true,
        missing: false,
        bpm: 128,
        key: '9A',
        duration_ms: 634000,
        has_preview: true,
      },
      {
        item_type: 'artist',
        item_id: 22,
        item_name: null,
        title: 'Boris Brejcha',
        subtitle: null,
        has_artwork: true,
        missing: false,
      },
      {
        item_type: 'set',
        item_id: 33,
        item_name: null,
        title: 'Awakenings 2024',
        subtitle: 'Awakenings',
        has_artwork: false,
        missing: false,
      },
      {
        item_type: 'genre',
        item_id: null,
        item_name: 'Techno',
        title: 'Techno',
        subtitle: null,
        has_artwork: false,
        missing: false,
      },
      {
        item_type: 'playlist',
        item_id: 44,
        item_name: null,
        title: 'My Radar',
        subtitle: 'someone',
        has_artwork: true,
        missing: false,
      },
      {
        item_type: 'track',
        item_id: 55,
        item_name: 'Deleted track',
        title: null,
        subtitle: null,
        has_artwork: false,
        missing: true,
      },
    ],
  }
}

async function mountView() {
  const wrapper = mount(CollectionDetailView)
  await flushPromises()
  return wrapper
}

describe('CollectionDetailView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.get.mockResolvedValue({ data: makeCollection() })
    apiMock.delete.mockResolvedValue({})
  })

  it('renders one row per heterogeneous item', async () => {
    const wrapper = await mountView()
    expect(wrapper.findAll('.rrow')).toHaveLength(6)
  })

  it('shows track meta only on the (non-missing) track row', async () => {
    const wrapper = await mountView()
    const metas = wrapper.findAll('.rmeta')
    // Only the first track (id 11) is playable/non-missing → 1 meta block.
    expect(metas).toHaveLength(1)
    expect(metas[0].text()).toContain('9A')
  })

  it('navigates to the right route per item type', async () => {
    const wrapper = await mountView()
    const rows = wrapper.findAll('.rrow')
    await rows[0].trigger('click') // track
    expect(routerPush).toHaveBeenLastCalledWith('/catalog/11')
    await rows[1].trigger('click') // artist
    expect(routerPush).toHaveBeenLastCalledWith('/artist/22')
    await rows[2].trigger('click') // set
    expect(routerPush).toHaveBeenLastCalledWith('/set/33')
    await rows[3].trigger('click') // genre → by name
    expect(routerPush).toHaveBeenLastCalledWith('/style/Techno')
    await rows[4].trigger('click') // playlist
    expect(routerPush).toHaveBeenLastCalledWith('/playlists/44')
  })

  it('does not navigate when a missing item row is clicked', async () => {
    const wrapper = await mountView()
    const rows = wrapper.findAll('.rrow')
    await rows[5].trigger('click') // missing track
    expect(routerPush).not.toHaveBeenCalled()
  })

  it('removes a non-track item via the polymorphic route (artist)', async () => {
    const wrapper = await mountView()
    const rows = wrapper.findAll('.rrow')
    await rows[1].find('.rm-btn').trigger('click')
    expect(apiMock.delete).toHaveBeenCalledWith('/api/collections/3/items/artist/22')
    await flushPromises()
    expect(wrapper.findAll('.rrow')).toHaveLength(5)
  })

  it('removes a genre item by item_name query param (null id → placeholder)', async () => {
    const wrapper = await mountView()
    const rows = wrapper.findAll('.rrow')
    await rows[3].find('.rm-btn').trigger('click')
    expect(apiMock.delete).toHaveBeenCalledWith('/api/collections/3/items/genre/0?item_name=Techno')
  })

  it('plays a track and queues ONLY track items', async () => {
    const wrapper = await mountView()
    // The playable track row exposes a .play overlay button.
    const play = wrapper.findAll('.rrow')[0].find('.rart .play')
    expect(play.exists()).toBe(true)
    await play.trigger('click')
    expect(playerMock.play).toHaveBeenCalledTimes(1)
    const [trackArg, sourceArg] = playerMock.play.mock.calls[0]
    expect(trackArg.catalog_id).toBe(11)
    const queued = sourceArg.getItems()
    expect(queued).toHaveLength(1) // the missing track (id 55) is excluded
    expect(queued[0].catalog_id).toBe(11)
  })
})

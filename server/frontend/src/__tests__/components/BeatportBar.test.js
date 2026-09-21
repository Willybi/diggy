import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import BeatportBar from '../../components/BeatportBar.vue'
import { useBeatportBar } from '../../stores/beatportBar.js'
import { useAudioPlayer } from '../../stores/audioPlayer.js'

// The bar WATCHES player.playing (a Deezer play must close it) — the mock is
// REACTIVE so the component watcher actually fires on mutation.
vi.mock('../../stores/audioPlayer.js', async () => {
  const { reactive } = await import('vue')
  const player = reactive({ playing: false, visible: false, toggle: vi.fn() })
  return { useAudioPlayer: () => player }
})

// A recording IntersectionObserver stub: proves the embed renders EAGERLY in
// the bar (no observer created) even when the API exists — in the raw jsdom
// fallback (no IO at all) the eager path would be indistinguishable.
let observers

class ObserverStub {
  constructor() {
    this.disconnected = false
    observers.push(this)
  }
  observe() {}
  disconnect() {
    this.disconnected = true
  }
}

const TRACK = { id: 42, title: 'Higher State', artist: 'Josh Wink', beatport_id: 987 }

describe('BeatportBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    observers = []
    vi.stubGlobal('IntersectionObserver', ObserverStub)
    const player = useAudioPlayer()
    player.playing = false
    player.visible = false
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders nothing while the store is closed', () => {
    const wrapper = mount(BeatportBar)
    expect(wrapper.find('.bp-bar').exists()).toBe(false)
    expect(wrapper.find('iframe').exists()).toBe(false)
  })

  it('opens as a non-modal region with the track meta and the EAGER embed iframe', async () => {
    const wrapper = mount(BeatportBar)
    const store = useBeatportBar()
    store.track = { ...TRACK }
    await nextTick()

    const bar = wrapper.find('.bp-bar')
    expect(bar.exists()).toBe(true)
    // Non-blocking surface: a plain region, NOT a dialog, and NO backdrop
    // (the AddModal chrome is gone — the site stays usable underneath).
    expect(bar.attributes('role')).toBe('region')
    expect(bar.attributes('aria-label')).toBe('Extrait Beatport')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('.add-overlay').exists()).toBe(false)

    expect(wrapper.find('.bpb-title').text()).toBe('Higher State')
    expect(wrapper.find('.bpb-artist').text()).toBe('Josh Wink')

    // Eager embed: the iframe is there immediately, no IntersectionObserver.
    const iframe = wrapper.find('iframe')
    expect(iframe.exists()).toBe(true)
    expect(iframe.attributes('src')).toBe('https://embed.beatport.com/?id=987&type=track')
    expect(observers).toHaveLength(0)
  })

  it('the ✕ button closes the store (bar gone)', async () => {
    const wrapper = mount(BeatportBar)
    const store = useBeatportBar()
    store.track = { ...TRACK }
    await nextTick()

    await wrapper.find('.bpb-close').trigger('click')
    expect(store.track).toBeNull()
    expect(wrapper.find('.bp-bar').exists()).toBe(false)
  })

  it('Escape does NOT close the bar (modal chrome removed — ✕ only)', async () => {
    const wrapper = mount(BeatportBar)
    const store = useBeatportBar()
    store.track = { ...TRACK }
    await nextTick()

    window.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(store.track).not.toBeNull()
    expect(wrapper.find('.bp-bar').exists()).toBe(true)
    wrapper.unmount()
  })

  it('a Deezer play starting (playing false→true) closes the bar', async () => {
    const wrapper = mount(BeatportBar)
    const store = useBeatportBar()
    store.track = { ...TRACK }
    await nextTick()
    expect(wrapper.find('.bp-bar').exists()).toBe(true)

    useAudioPlayer().playing = true
    await nextTick()
    expect(store.track).toBeNull()
    expect(wrapper.find('.bp-bar').exists()).toBe(false)
  })

  it('open() on another track replaces the content (iframe reloads on the new id)', async () => {
    const wrapper = mount(BeatportBar)
    const store = useBeatportBar()
    store.open(TRACK)
    await nextTick()
    expect(wrapper.find('iframe').attributes('src')).toBe(
      'https://embed.beatport.com/?id=987&type=track',
    )

    store.open({ id: 43, title: 'Flash', artist: 'Green Velvet', beatport_id: 654 })
    await nextTick()
    expect(wrapper.find('.bpb-title').text()).toBe('Flash')
    expect(wrapper.find('iframe').attributes('src')).toBe(
      'https://embed.beatport.com/?id=654&type=track',
    )
  })
})

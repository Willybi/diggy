import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import BeatportOverlay from '../../components/BeatportOverlay.vue'
import { useBeatportOverlay } from '../../stores/beatportOverlay.js'

// A recording IntersectionObserver stub: proves the embed renders EAGERLY in
// the modal (no observer created) even when the API exists — in the raw jsdom
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

describe('BeatportOverlay', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    observers = []
    vi.stubGlobal('IntersectionObserver', ObserverStub)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders nothing while the store is closed', () => {
    const wrapper = mount(BeatportOverlay)
    expect(wrapper.find('.add-overlay').exists()).toBe(false)
    expect(wrapper.find('iframe').exists()).toBe(false)
  })

  it('opens with the track meta and the EAGER embed iframe (right id, no observer)', async () => {
    const wrapper = mount(BeatportOverlay)
    const store = useBeatportOverlay()
    store.track = { ...TRACK }
    await nextTick()

    expect(wrapper.find('[role="dialog"]').attributes('aria-label')).toBe('Extrait Beatport')
    expect(wrapper.find('.bpo-title').text()).toBe('Higher State')
    expect(wrapper.find('.bpo-artist').text()).toBe('Josh Wink')

    // Eager embed: the iframe is there immediately, no IntersectionObserver.
    const iframe = wrapper.find('iframe')
    expect(iframe.exists()).toBe(true)
    expect(iframe.attributes('src')).toBe('https://embed.beatport.com/?id=987&type=track')
    expect(observers).toHaveLength(0)
  })

  it('uses the bottom-sheet variant of the modal chrome', async () => {
    const wrapper = mount(BeatportOverlay)
    useBeatportOverlay().track = { ...TRACK }
    await nextTick()
    expect(wrapper.find('.add-overlay').classes()).toContain('add-overlay--sheet')
  })

  it('the ✕ button closes the store (overlay gone)', async () => {
    const wrapper = mount(BeatportOverlay)
    const store = useBeatportOverlay()
    store.track = { ...TRACK }
    await nextTick()

    await wrapper.find('.add-modal-x').trigger('click')
    expect(store.track).toBeNull()
    expect(wrapper.find('.add-overlay').exists()).toBe(false)
  })

  it('a backdrop click closes the store', async () => {
    const wrapper = mount(BeatportOverlay)
    const store = useBeatportOverlay()
    store.track = { ...TRACK }
    await nextTick()

    await wrapper.find('.add-overlay').trigger('click')
    expect(store.track).toBeNull()
  })

  it('Escape closes the store', async () => {
    const wrapper = mount(BeatportOverlay)
    const store = useBeatportOverlay()
    store.track = { ...TRACK }
    await nextTick()

    window.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(store.track).toBeNull()
    wrapper.unmount()
  })
})

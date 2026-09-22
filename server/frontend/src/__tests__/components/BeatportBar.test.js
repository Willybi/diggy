import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount, RouterLinkStub } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import BeatportBar from '../../components/BeatportBar.vue'
import { useBeatportBar } from '../../stores/beatportBar.js'
import { useAudioPlayer } from '../../stores/audioPlayer.js'

// The bar WATCHES player.playing (a Deezer play must close it) and renders the
// resume chip off player.track — the mock is REACTIVE so both actually fire.
vi.mock('../../stores/audioPlayer.js', async () => {
  const { reactive } = await import('vue')
  const player = reactive({ playing: false, visible: false, track: null, toggle: vi.fn() })
  return { useAudioPlayer: () => player }
})

// A recording IntersectionObserver stub: proves the embed renders EAGERLY in
// the card (no observer created) even when the API exists — in the raw jsdom
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

// vue-router is not installed in these mounts: RouterLink must be stubbed via
// global.components (string-name stubs are a no-op for unresolved components).
const mountBar = () =>
  mount(BeatportBar, { global: { components: { RouterLink: RouterLinkStub } } })

describe('BeatportBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    observers = []
    vi.stubGlobal('IntersectionObserver', ObserverStub)
    const player = useAudioPlayer()
    player.playing = false
    player.visible = false
    player.track = null
    player.toggle.mockClear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders nothing while the store is closed', () => {
    const wrapper = mountBar()
    expect(wrapper.find('.bp-card').exists()).toBe(false)
    expect(wrapper.find('iframe').exists()).toBe(false)
  })

  it('opens as a non-modal text-free region with the EAGER embed iframe', async () => {
    const wrapper = mountBar()
    const store = useBeatportBar()
    store.track = { ...TRACK }
    await nextTick()

    const card = wrapper.find('.bp-card')
    expect(card.exists()).toBe(true)
    // Non-blocking surface: a plain region, NOT a dialog, and NO backdrop
    // (the site stays usable underneath).
    expect(card.attributes('role')).toBe('region')
    expect(card.attributes('aria-label')).toBe('Extrait Beatport')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('.add-overlay').exists()).toBe(false)

    // No text chrome: label + title/artist are gone (the iframe carries them),
    // and the embed's own "Voir sur Beatport" link is opted out.
    expect(card.text()).toBe('')
    expect(wrapper.find('a.bp-link').exists()).toBe(false)

    // Eager embed: the iframe is there immediately, no IntersectionObserver.
    const iframe = wrapper.find('iframe')
    expect(iframe.exists()).toBe(true)
    expect(iframe.attributes('src')).toBe('https://embed.beatport.com/?id=987&type=track')
    expect(observers).toHaveLength(0)
  })

  it('the ✕ button closes the store (card gone)', async () => {
    const wrapper = mountBar()
    const store = useBeatportBar()
    store.track = { ...TRACK }
    await nextTick()

    await wrapper.find('.bpc-close').trigger('click')
    expect(store.track).toBeNull()
    expect(wrapper.find('.bp-card').exists()).toBe(false)
  })

  it('Escape does NOT close the card (non-modal — ✕ only)', async () => {
    const wrapper = mountBar()
    const store = useBeatportBar()
    store.track = { ...TRACK }
    await nextTick()

    window.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(store.track).not.toBeNull()
    expect(wrapper.find('.bp-card').exists()).toBe(true)
    wrapper.unmount()
  })

  it('a Deezer play starting (playing false→true) closes the card', async () => {
    const wrapper = mountBar()
    const store = useBeatportBar()
    store.track = { ...TRACK }
    await nextTick()
    expect(wrapper.find('.bp-card').exists()).toBe(true)

    useAudioPlayer().playing = true
    await nextTick()
    expect(store.track).toBeNull()
    expect(wrapper.find('.bp-card').exists()).toBe(false)
  })

  it('open() on another track replaces the content (iframe reloads on the new id)', async () => {
    const wrapper = mountBar()
    const store = useBeatportBar()
    store.open(TRACK)
    await nextTick()
    expect(wrapper.find('iframe').attributes('src')).toBe(
      'https://embed.beatport.com/?id=987&type=track',
    )

    store.open({ id: 43, title: 'Flash', artist: 'Green Velvet', beatport_id: 654 })
    await nextTick()
    expect(wrapper.find('iframe').attributes('src')).toBe(
      'https://embed.beatport.com/?id=654&type=track',
    )
  })

  it('the ↗ ghost is a RouterLink to the track detail page', async () => {
    const wrapper = mountBar()
    const store = useBeatportBar()
    store.track = { ...TRACK }
    await nextTick()

    const link = wrapper.findComponent(RouterLinkStub)
    expect(link.exists()).toBe(true)
    expect(link.props('to')).toBe('/catalog/42')
    expect(link.attributes('aria-label')).toBe('Ouvrir la fiche du son')
  })

  it('renders the resume chip only when a Deezer preview is loaded', async () => {
    const wrapper = mountBar()
    const store = useBeatportBar()
    store.track = { ...TRACK }
    await nextTick()
    expect(wrapper.find('.bpc-resume').exists()).toBe(false)

    useAudioPlayer().track = { catalog_id: 7, title: 'Percolator' }
    await nextTick()
    const chip = wrapper.find('.bpc-resume')
    expect(chip.exists()).toBe(true)
    expect(chip.text()).toContain('Reprendre la preview Deezer')
    expect(chip.text()).toContain('Percolator')
  })

  it('the resume chip closes the card THEN resumes the paused Deezer audio (toggle, not play)', async () => {
    const wrapper = mountBar()
    const store = useBeatportBar()
    const player = useAudioPlayer()
    store.track = { ...TRACK }
    player.track = { catalog_id: 7, title: 'Percolator' }
    await nextTick()

    await wrapper.find('.bpc-resume').trigger('click')
    expect(store.track).toBeNull()
    expect(player.toggle).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.bp-card').exists()).toBe(false)
  })
})

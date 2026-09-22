import { describe, it, expect, beforeEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import App from '../App.vue'
import { useAudioPlayer } from '../stores/audioPlayer.js'
import { useBeatportBar } from '../stores/beatportBar.js'

// SidebarNav pulls useTheme, whose module-level matchMedia crashes jsdom —
// mock the module away (same pattern as a11y.test.js / keepAlive.test.js);
// `stubs` alone would not prevent the import from evaluating.
vi.mock('../components/SidebarNav.vue', () => ({ default: { template: '<div />' } }))

// Focused App-shell suite (D12 v2 "replace" pattern): the Beatport card
// REPLACES the Deezer card — PlayerBar must unmount while beatportBar is
// visible and come back (state untouched in the store) once it closes.
// Everything heavy is stubbed; no auth token in jsdom → guest boot, no network.
const mountApp = () =>
  mount(App, {
    global: {
      // RouterView is an unresolved component here (no router installed):
      // string-name stubs are a no-op for those — register a real stand-in.
      components: { RouterView: { template: '<div />' } },
      stubs: {
        PlayerBar: true,
        BottomNav: true,
        SidebarNav: true,
        ToastNotification: true,
        BeatportBar: true,
      },
    },
  })

describe('App — PlayerBar × BeatportBar cohabitation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('hides PlayerBar while the Beatport card is open, even with a loaded track', () => {
    const player = useAudioPlayer()
    const bar = useBeatportBar()
    player.track = { catalog_id: 7, title: 'Percolator' }
    bar.track = { id: 42, title: 'Higher State', beatport_id: 987 }

    const wrapper = mountApp()
    expect(player.visible).toBe(true)
    expect(wrapper.find('player-bar-stub').exists()).toBe(false)
    expect(wrapper.find('main').classes()).toContain('has-beatport')
  })

  it('re-renders PlayerBar after the Beatport card closes (state preserved)', async () => {
    const player = useAudioPlayer()
    const bar = useBeatportBar()
    player.track = { catalog_id: 7, title: 'Percolator' }
    bar.track = { id: 42, title: 'Higher State', beatport_id: 987 }

    const wrapper = mountApp()
    bar.close()
    await nextTick()
    expect(wrapper.find('player-bar-stub').exists()).toBe(true)
    expect(player.track).toEqual({ catalog_id: 7, title: 'Percolator' })
    expect(wrapper.find('main').classes()).not.toContain('has-beatport')
  })

  it('renders PlayerBar normally when no Beatport card is open', () => {
    const player = useAudioPlayer()
    player.track = { catalog_id: 7, title: 'Percolator' }

    const wrapper = mountApp()
    expect(wrapper.find('player-bar-stub').exists()).toBe(true)
    expect(wrapper.find('main').classes()).toContain('has-player')
  })
})

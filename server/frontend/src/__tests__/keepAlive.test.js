import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { KeepAlive, h } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

// The six listing views cached across navigation (D9.a). Detail pages vary by
// route param and must stay OFF this allowlist.
const CACHED_VIEWS = [
  'ExplorerView',
  'RadarView',
  'ArtistsView',
  'SetsView',
  'WatchlistView',
  'GenresView',
]

// ── App.vue wraps the router view in a bounded <KeepAlive> ─────────────────────

vi.mock('../stores/auth.js', () => ({
  useAuthStore: () => ({ isAuthenticated: false, user: null, refreshUser: vi.fn() }),
}))
vi.mock('../stores/audioPlayer.js', () => ({
  useAudioPlayer: () => ({ visible: false }),
}))
vi.mock('../stores/opinions.js', () => ({
  useOpinionsStore: () => ({ load: vi.fn(), reset: vi.fn() }),
}))
vi.mock('../components/SidebarNav.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../components/PlayerBar.vue', () => ({ default: { template: '<div />' } }))

// A RouterView stub that renders its scoped default slot with a dummy routed
// component, so the <KeepAlive> nested inside actually mounts and is inspectable.
const RouterViewStub = {
  name: 'RouterView',
  setup(_, { slots }) {
    const Dummy = { name: 'ExplorerView', render: () => h('div') }
    return () => (slots.default ? slots.default({ Component: Dummy }) : null)
  },
}

describe('App.vue <KeepAlive> allowlist', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  async function mountApp() {
    const { default: App } = await import('../App.vue')
    return mount(App, {
      global: {
        stubs: {
          RouterView: RouterViewStub,
          SidebarNav: true,
          PlayerBar: true,
          BottomNav: true,
          Transition: true,
          ToastNotification: true,
        },
      },
    })
  }

  it('wraps the router view in a KeepAlive bounded to :max=6', async () => {
    const wrapper = await mountApp()
    const ka = wrapper.findComponent(KeepAlive)
    expect(ka.exists()).toBe(true)
    expect(ka.props('max')).toBe(6)
  })

  it('caches exactly the six listing views (detail pages excluded)', async () => {
    const wrapper = await mountApp()
    const include = wrapper.findComponent(KeepAlive).props('include')
    expect([...include].sort()).toEqual([...CACHED_VIEWS].sort())
  })
})

// ── Each cached view exposes the name KeepAlive :include matches on ────────────
// KeepAlive matches by component name; a name drift would silently disable the
// cache for a view. Assert every allowlisted view declares the expected name.

import ExplorerView from '../views/ExplorerView.vue'
import RadarView from '../views/RadarView.vue'
import ArtistsView from '../views/ArtistsView.vue'
import SetsView from '../views/SetsView.vue'
import WatchlistView from '../views/WatchlistView.vue'
import GenresView from '../views/GenresView.vue'

describe('cached view component names', () => {
  it.each([
    ['ExplorerView', ExplorerView],
    ['RadarView', RadarView],
    ['ArtistsView', ArtistsView],
    ['SetsView', SetsView],
    ['WatchlistView', WatchlistView],
    ['GenresView', GenresView],
  ])('%s declares its name for KeepAlive matching', (name, view) => {
    expect(view.name).toBe(name)
    expect(CACHED_VIEWS).toContain(name)
  })
})

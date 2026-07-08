import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// ── Router: lazy loading ──────────────────────────────────────────────────────

describe('router lazy loading', () => {
  it('HubView is a static import (object component)', async () => {
    const { default: router } = await import('../router.js')
    const routes = router.getRoutes()
    const hubRoute = routes.find((r) => r.path === '/')
    // Static import → component is a plain object with a `setup` or `render`
    expect(typeof hubRoute.components.default).toBe('object')
  })

  it('lazy routes are dynamic imports (functions)', async () => {
    const { default: router } = await import('../router.js')
    const routes = router.getRoutes()

    const lazyPaths = ['/genres', '/catalog', '/sets', '/artists', '/login']
    for (const path of lazyPaths) {
      const route = routes.find((r) => r.path === path)
      if (!route) continue
      // Dynamic import → component is a function that returns a Promise
      expect(typeof route.components.default).toBe('function')
    }
  })
})

// ── LikeDislike: aria-labels ──────────────────────────────────────────────────

vi.mock('../utils/api.js', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    patch: vi.fn(() => Promise.resolve({ data: {} })),
  },
}))

describe('LikeDislike accessibility', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('like button has aria-label', async () => {
    const { default: LikeDislike } = await import('../components/LikeDislike.vue')
    const wrapper = mount(LikeDislike, { props: { modelValue: null } })
    const likeBtn = wrapper.find('.ld-btn.like')
    expect(likeBtn.attributes('aria-label')).toBe('Aimer')
  })

  it('dislike button has aria-label', async () => {
    const { default: LikeDislike } = await import('../components/LikeDislike.vue')
    const wrapper = mount(LikeDislike, { props: { modelValue: null } })
    const dislikeBtn = wrapper.find('.ld-btn.dislike')
    expect(dislikeBtn.attributes('aria-label')).toBe('Ne pas aimer')
  })

  it('like button has aria-pressed=false when not liked', async () => {
    const { default: LikeDislike } = await import('../components/LikeDislike.vue')
    const wrapper = mount(LikeDislike, { props: { modelValue: null } })
    expect(wrapper.find('.ld-btn.like').attributes('aria-pressed')).toBe('false')
  })

  it('like button has aria-pressed=true when liked', async () => {
    const { default: LikeDislike } = await import('../components/LikeDislike.vue')
    const wrapper = mount(LikeDislike, { props: { modelValue: 'liked' } })
    expect(wrapper.find('.ld-btn.like').attributes('aria-pressed')).toBe('true')
  })
})

// ── App.vue: skip link ────────────────────────────────────────────────────────

vi.mock('../stores/auth.js', () => ({
  useAuthStore: () => ({ isAuthenticated: false, user: null }),
}))
vi.mock('../stores/audioPlayer.js', () => ({
  useAudioPlayer: () => ({ visible: false }),
}))
vi.mock('../stores/opinions.js', () => ({
  useOpinionsStore: () => ({ load: vi.fn(), reset: vi.fn() }),
}))
vi.mock('../components/SidebarNav.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../components/PlayerBar.vue', () => ({ default: { template: '<div />' } }))

describe('App.vue skip link', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders a skip link targeting #main-content', async () => {
    const { default: App } = await import('../App.vue')
    const wrapper = mount(App, {
      global: {
        stubs: { RouterView: true, SidebarNav: true, PlayerBar: true, Transition: true, ToastNotification: true },
      },
    })
    const skip = wrapper.find('.skip-link')
    expect(skip.exists()).toBe(true)
    expect(skip.attributes('href')).toBe('#main-content')
  })

  it('main element has id="main-content"', async () => {
    const { default: App } = await import('../App.vue')
    const wrapper = mount(App, {
      global: {
        stubs: { RouterView: true, SidebarNav: true, PlayerBar: true, Transition: true, ToastNotification: true },
      },
    })
    expect(wrapper.find('#main-content').exists()).toBe(true)
  })
})

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'

// Prefetch is exposed by router.js; spy on it so we assert the wiring without
// loading the real router (and without triggering any dynamic import here).
const { prefetchSpy } = vi.hoisted(() => ({ prefetchSpy: vi.fn() }))

vi.mock('../../router.js', () => ({
  default: {},
  prefetchRoute: prefetchSpy,
}))

// vue-router is mocked (BottomNav uses useRoute, SidebarNav uses useRouter), so
// <router-link> never resolves — RouterLinkStub is registered as a global below.
vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/' }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('../../stores/auth.js', () => ({
  useAuthStore: () => ({ isAuthenticated: true, user: { is_admin: false } }),
}))

vi.mock('../../utils/api.js', () => ({
  default: { get: vi.fn().mockResolvedValue({ data: { count: 0 } }) },
}))

vi.mock('../../composables/useTheme.js', () => ({
  useTheme: () => ({ isDark: false, toggle: vi.fn() }),
}))

const globalOpts = { global: { components: { RouterLink: RouterLinkStub } } }

describe('nav chunk prefetch on hover/focus (D9.c)', () => {
  beforeEach(() => {
    prefetchSpy.mockClear()
  })

  it('BottomNav: nothing at mount, hover/focus prefetch the target route once each', async () => {
    const { default: BottomNav } = await import('../../components/BottomNav.vue')
    const wrapper = mount(BottomNav, globalOpts)
    await flushPromises()

    // Mounting must never prefetch — /radar in particular is not touched at boot.
    expect(prefetchSpy).not.toHaveBeenCalled()

    // Order: Hub, Explorer, Radar, … → index 1 is Explorer (/explorer).
    const explorer = wrapper.findAll('button.bottom-nav-item')[1]
    await explorer.trigger('mouseenter')
    expect(prefetchSpy).toHaveBeenCalledTimes(1)
    expect(prefetchSpy).toHaveBeenLastCalledWith('/explorer')

    await explorer.trigger('focus')
    expect(prefetchSpy).toHaveBeenCalledTimes(2)
    expect(prefetchSpy).toHaveBeenLastCalledWith('/explorer')
  })

  it('SidebarNav: nothing at mount, hover/focus prefetch the target route', async () => {
    const { default: SidebarNav } = await import('../../components/SidebarNav.vue')
    const wrapper = mount(SidebarNav, globalOpts)
    await flushPromises()

    expect(prefetchSpy).not.toHaveBeenCalled()

    // First library item is Explorer (/explorer). The footer theme toggle is a
    // <button.nav-item>, so scope the query to the item <span>s.
    const explorer = wrapper.findAll('span.nav-item')[0]
    await explorer.trigger('mouseenter')
    expect(prefetchSpy).toHaveBeenCalledTimes(1)
    expect(prefetchSpy).toHaveBeenLastCalledWith('/explorer')

    await explorer.trigger('focus')
    expect(prefetchSpy).toHaveBeenCalledTimes(2)
    expect(prefetchSpy).toHaveBeenLastCalledWith('/explorer')
  })
})

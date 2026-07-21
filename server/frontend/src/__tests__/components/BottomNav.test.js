import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'

// Mutable holders shared with the hoisted mocks below.
const { authState, apiGet } = vi.hoisted(() => ({
  authState: { value: { isAuthenticated: false, user: null } },
  apiGet: vi.fn(),
}))

vi.mock('../../utils/api.js', () => ({
  default: { get: apiGet },
}))

vi.mock('../../stores/auth.js', () => ({
  useAuthStore: () => authState.value,
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/' }),
}))

async function mountNav() {
  const { default: BottomNav } = await import('../../components/BottomNav.vue')
  // vue-router is mocked, so <router-link> never resolves to a component and
  // VTU `stubs` would not apply — register the stub as a global component.
  const wrapper = mount(BottomNav, {
    global: { components: { RouterLink: RouterLinkStub } },
  })
  await flushPromises()
  return wrapper
}

describe('BottomNav new-count fetch', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiGet.mockResolvedValue({ data: { count: 3 } })
    authState.value = { isAuthenticated: false, user: null }
  })

  it('does not hit the network when the user is not authenticated', async () => {
    authState.value = { isAuthenticated: false, user: null }
    await mountNav()
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('fetches the canonical /api/radar/new-count endpoint when authenticated', async () => {
    authState.value = { isAuthenticated: true, user: { is_admin: false } }
    await mountNav()
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet).toHaveBeenCalledWith('/api/radar/new-count')
  })

  it('renders the five base nav links through the RouterLink stub', async () => {
    authState.value = { isAuthenticated: true, user: { is_admin: false } }
    const wrapper = await mountNav()
    const links = wrapper.findAllComponents(RouterLinkStub)
    expect(links).toHaveLength(5)
    expect(links.map((l) => l.props('to'))).toEqual(['/', '/explorer', '/artists', '/sets', '/genres'])
    expect(wrapper.text()).toContain('Explorer')
  })
})

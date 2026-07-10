import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'

// Mutable holders shared with the hoisted mocks below.
const { routeState, routerReplace, persistMock } = vi.hoisted(() => ({
  routeState: { value: { query: {} } },
  routerReplace: vi.fn(),
  persistMock: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: routerReplace }),
  useRoute: () => routeState.value,
}))

vi.mock('../../stores/auth.js', () => ({
  useAuthStore: () => ({ _persist: persistMock }),
}))

const VALID_PAYLOAD = { token: 'jwt-abc-1', user: { id: 7, email: 'dj@example.com' } }

// Encode a payload the way the backend does: JSON → base64 → base64url
// with the trailing '=' padding stripped.
function setAuthCookie(payload) {
  const b64 = btoa(JSON.stringify(payload))
  // Guard: the stripped base64 must have had padding, otherwise the
  // component's re-padding branch would not really be exercised.
  expect(b64.endsWith('=')).toBe(true)
  const b64url = b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  document.cookie = 'auth_callback=' + b64url
}

async function mountCallback() {
  const { default: LoginCallbackView } = await import('../../views/LoginCallbackView.vue')
  // vue-router is mocked, so <router-link> never resolves to a component and
  // VTU `stubs` would not apply — register the stub as a global component.
  const wrapper = mount(LoginCallbackView, {
    global: { components: { RouterLink: RouterLinkStub } },
  })
  await flushPromises()
  return wrapper
}

describe('LoginCallbackView OAuth callback', () => {
  beforeEach(() => {
    persistMock.mockReset()
    routerReplace.mockReset()
    routeState.value = { query: {} }
    document.cookie = 'auth_callback=; Max-Age=0; Path=/'
  })

  it('persists token and user from a valid cookie then redirects home', async () => {
    setAuthCookie(VALID_PAYLOAD)
    const wrapper = await mountCallback()

    expect(persistMock).toHaveBeenCalledTimes(1)
    expect(persistMock).toHaveBeenCalledWith(VALID_PAYLOAD.token, VALID_PAYLOAD.user)
    expect(routerReplace).toHaveBeenCalledWith('/')
    expect(document.cookie).not.toContain('auth_callback')
    expect(wrapper.find('.callback-error').exists()).toBe(false)
    expect(wrapper.text()).toContain('Connexion en cours')
  })

  it('shows the missing-data error when the cookie is absent', async () => {
    const wrapper = await mountCallback()

    expect(wrapper.text()).toContain('Données de connexion manquantes.')
    expect(persistMock).not.toHaveBeenCalled()
    expect(routerReplace).not.toHaveBeenCalled()

    const retry = wrapper.findComponent(RouterLinkStub)
    expect(retry.exists()).toBe(true)
    expect(retry.props('to')).toBe('/login')
    expect(retry.text()).toBe('Réessayer')
  })

  it('shows the unexpected error when the cookie is not decodable', async () => {
    document.cookie = 'auth_callback=!!!'
    const wrapper = await mountCallback()

    expect(wrapper.text()).toContain('Erreur inattendue lors de la connexion.')
    expect(persistMock).not.toHaveBeenCalled()
    expect(routerReplace).not.toHaveBeenCalled()
  })

  it('shows the Google failure error and returns early when the query has ?error=', async () => {
    routeState.value = { query: { error: 'access_denied' } }
    setAuthCookie(VALID_PAYLOAD)
    const wrapper = await mountCallback()

    expect(wrapper.text()).toContain('La connexion Google a échoué. Veuillez réessayer.')
    expect(persistMock).not.toHaveBeenCalled()
    expect(routerReplace).not.toHaveBeenCalled()
    // Early return happens before cookie handling: the cookie must survive.
    expect(document.cookie).toContain('auth_callback=')
    expect(wrapper.findComponent(RouterLinkStub).props('to')).toBe('/login')
  })
})

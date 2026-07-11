import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../../stores/auth.js'

// Mock localStorage
const storage = {}
const localStorageMock = {
  getItem: vi.fn((key) => storage[key] ?? null),
  setItem: vi.fn((key, val) => {
    storage[key] = String(val)
  }),
  removeItem: vi.fn((key) => {
    delete storage[key]
  }),
}
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

function makeJwt(payload) {
  const header = btoa(JSON.stringify({ alg: 'HS256' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.sig`
}

describe('auth store', () => {
  beforeEach(() => {
    Object.keys(storage).forEach((k) => delete storage[k])
    localStorageMock.getItem.mockClear()
    localStorageMock.setItem.mockClear()
    localStorageMock.removeItem.mockClear()
    setActivePinia(createPinia())
  })

  it('isAuthenticated returns false without token', () => {
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('isAuthenticated returns true with a valid (non-expired) token', () => {
    const token = makeJwt({ exp: Math.floor(Date.now() / 1000) + 3600 })
    storage.diggy_token = token
    storage.diggy_user = JSON.stringify({ email: 'a@b.com' })
    setActivePinia(createPinia())
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(true)
  })

  it('isAuthenticated returns false with an expired token', () => {
    const token = makeJwt({ exp: Math.floor(Date.now() / 1000) - 3600 })
    storage.diggy_token = token
    setActivePinia(createPinia())
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('logout() clears token, user and localStorage', () => {
    const token = makeJwt({ exp: Math.floor(Date.now() / 1000) + 3600 })
    storage.diggy_token = token
    storage.diggy_user = JSON.stringify({ email: 'a@b.com' })
    setActivePinia(createPinia())
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(true)

    auth.logout()
    expect(auth.token).toBeNull()
    expect(auth.user).toBeNull()
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('diggy_token')
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('diggy_user')
  })

  function makeAuthedStore(user = { email: 'a@b.com', is_admin: false }) {
    const token = makeJwt({ exp: Math.floor(Date.now() / 1000) + 3600 })
    storage.diggy_token = token
    storage.diggy_user = JSON.stringify(user)
    setActivePinia(createPinia())
    return { auth: useAuthStore(), token }
  }

  it('refreshUser() refreshes and persists the user (is_admin flip becomes observable)', async () => {
    const { auth, token } = makeAuthedStore({ email: 'a@b.com', is_admin: false })
    expect(auth.user.is_admin).toBe(false)

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ email: 'a@b.com', is_admin: true }),
    })

    await auth.refreshUser()

    expect(globalThis.fetch).toHaveBeenCalledWith('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(auth.user.is_admin).toBe(true)
    expect(storage.diggy_user).toBe(JSON.stringify({ email: 'a@b.com', is_admin: true }))
    // Same token is re-persisted, not dropped.
    expect(auth.token).toBe(token)
  })

  it('refreshUser() logs out when the server rejects the token (401)', async () => {
    const { auth } = makeAuthedStore()
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401 })

    await auth.refreshUser()

    expect(auth.token).toBeNull()
    expect(auth.user).toBeNull()
    expect(storage.diggy_token).toBeUndefined()
    expect(storage.diggy_user).toBeUndefined()
  })

  it('refreshUser() keeps the current user on a network error (no logout)', async () => {
    const { auth, token } = makeAuthedStore()
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('network down'))

    await auth.refreshUser()

    expect(auth.token).toBe(token)
    expect(auth.user).toEqual({ email: 'a@b.com', is_admin: false })
  })

  it('refreshUser() keeps the current user on a 5xx (no logout)', async () => {
    const { auth, token } = makeAuthedStore()
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 503 })

    await auth.refreshUser()

    expect(auth.token).toBe(token)
    expect(auth.user).toEqual({ email: 'a@b.com', is_admin: false })
  })

  it('refreshUser() makes no network call when unauthenticated', async () => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    globalThis.fetch = vi.fn()

    await auth.refreshUser()

    expect(globalThis.fetch).not.toHaveBeenCalled()
  })
})

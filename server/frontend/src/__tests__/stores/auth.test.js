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
})

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Mock router before importing api
vi.mock('../../router', () => ({
  default: { push: vi.fn() },
}))

// We need to re-import fresh for each test suite
import api from '../../utils/api.js'
import { useAuthStore } from '../../stores/auth.js'
import router from '../../router'

// Mock localStorage
const storage = {}
Object.defineProperty(globalThis, 'localStorage', {
  value: {
    getItem: vi.fn((key) => storage[key] ?? null),
    setItem: vi.fn((key, val) => {
      storage[key] = String(val)
    }),
    removeItem: vi.fn((key) => {
      delete storage[key]
    }),
  },
  writable: true,
})

function makeJwt(payload) {
  const header = btoa(JSON.stringify({ alg: 'HS256' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.sig`
}

describe('api interceptors', () => {
  beforeEach(() => {
    Object.keys(storage).forEach((k) => delete storage[k])
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('request interceptor adds Authorization header when token exists', () => {
    const auth = useAuthStore()
    const token = makeJwt({ exp: Math.floor(Date.now() / 1000) + 3600 })
    auth.token = token

    // Simulate running the request interceptor
    const config = { headers: {} }
    const interceptor = api.interceptors.request.handlers[0].fulfilled
    const result = interceptor(config)
    expect(result.headers.Authorization).toBe(`Bearer ${token}`)
  })

  it('request interceptor does not add header when no token', () => {
    const auth = useAuthStore()
    auth.token = null

    const config = { headers: {} }
    const interceptor = api.interceptors.request.handlers[0].fulfilled
    const result = interceptor(config)
    expect(result.headers.Authorization).toBeUndefined()
  })

  it('response interceptor calls logout and redirects on 401', async () => {
    const auth = useAuthStore()
    const token = makeJwt({ exp: Math.floor(Date.now() / 1000) + 3600 })
    auth.token = token

    const error = { response: { status: 401 } }
    const interceptor = api.interceptors.response.handlers[0].rejected

    await expect(interceptor(error)).rejects.toEqual(error)
    expect(auth.token).toBeNull()
    expect(router.push).toHaveBeenCalledWith('/login')
  })
})

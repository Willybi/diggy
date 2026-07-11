import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const API = '/api/auth'

function isTokenExpired(t) {
  try {
    const payload = JSON.parse(atob(t.split('.')[1]))
    return payload.exp * 1000 < Date.now()
  } catch {
    return true
  }
}

export const useAuthStore = defineStore('auth', () => {
  const stored = localStorage.getItem('diggy_token')
  const token = ref(stored && !isTokenExpired(stored) ? stored : null)
  const user = ref(token.value ? JSON.parse(localStorage.getItem('diggy_user') || 'null') : null)

  // Clean up localStorage if token was expired
  if (stored && !token.value) {
    localStorage.removeItem('diggy_token')
    localStorage.removeItem('diggy_user')
  }

  const isAuthenticated = computed(() => !!token.value && !isTokenExpired(token.value))

  function _persist(t, u) {
    token.value = t
    user.value = u
    if (t) {
      localStorage.setItem('diggy_token', t)
      localStorage.setItem('diggy_user', JSON.stringify(u))
    } else {
      localStorage.removeItem('diggy_token')
      localStorage.removeItem('diggy_user')
    }
  }

  async function loginWithGoogle() {
    const res = await fetch(`${API}/google/login`)
    if (!res.ok) throw new Error('Impossible de lancer la connexion Google')
    const { url } = await res.json()
    window.location.href = url
  }

  function logout() {
    _persist(null, null)
  }

  // Re-fetch the persisted user from the server so server-side changes
  // (e.g. is_admin flipped) surface without a re-login. Uses raw fetch like
  // loginWithGoogle: the api wrapper would recurse (it imports this store) and
  // its interceptors would toast on 5xx / redirect on 401 — both unwanted here.
  async function refreshUser() {
    if (!isAuthenticated.value) return
    try {
      const res = await fetch(`${API}/me`, {
        headers: { Authorization: `Bearer ${token.value}` },
      })
      if (res.status === 401) {
        // Token rejected server-side: the persisted session is stale, drop it.
        logout()
        return
      }
      if (!res.ok) return // 5xx or other server hiccup: keep the user, stay silent
      _persist(token.value, await res.json())
    } catch {
      // Network error: a transient outage must never evict the user.
    }
  }

  return { token, user, isAuthenticated, loginWithGoogle, logout, refreshUser, _persist }
})

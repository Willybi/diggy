import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const API = '/api/auth'

function isTokenExpired(t) {
  try {
    const payload = JSON.parse(atob(t.split('.')[1]))
    return payload.exp * 1000 < Date.now()
  } catch { return true }
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

  return { token, user, isAuthenticated, loginWithGoogle, logout }
})

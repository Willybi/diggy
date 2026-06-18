import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const API = '/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('diggy_token') || null)
  const user = ref(JSON.parse(localStorage.getItem('diggy_user') || 'null'))

  const isAuthenticated = computed(() => !!token.value)

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

  async function login(email, password) {
    const res = await fetch(`${API}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Login failed')
    }
    const data = await res.json()
    _persist(data.token, { id: data.user_id, username: data.username, is_admin: data.is_admin ?? false })
    return data
  }

  async function register(email, username, password) {
    const res = await fetch(`${API}/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, username, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Registration failed')
    }
    const data = await res.json()
    _persist(data.token, { id: data.user_id, username: data.username, is_admin: data.is_admin ?? false })
    return data
  }

  function logout() {
    _persist(null, null)
  }

  function authHeaders() {
    return token.value ? { Authorization: `Bearer ${token.value}` } : {}
  }

  return { token, user, isAuthenticated, login, register, logout, authHeaders }
})

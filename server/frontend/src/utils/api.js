import axios from 'axios'
import { useAuthStore } from '../stores/auth.js'
import { useToast } from '../stores/toast.js'
import router from '../router'

const api = axios.create({
  baseURL: '/',
})

// Inject auth token on every request
api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

// Auto-logout on 401, toast on 429 / 5xx / network error
api.interceptors.response.use(undefined, (error) => {
  const status = error.response?.status
  if (status === 401) {
    const auth = useAuthStore()
    if (auth.token) {
      auth.logout()
      router.push('/login')
    }
  } else if (status === 429) {
    const toast = useToast()
    const retry = error.response?.headers?.['retry-after']
    toast.show(
      retry
        ? `Trop de requêtes, réessayez dans ${retry}s.`
        : 'Trop de requêtes, réessayez dans un instant.',
    )
  } else if (!error.response || status >= 500) {
    // Callers can opt out of the auto-toast (e.g. the audio player runs its own
    // transient-503 retry and messages the user itself).
    if (!error.config?.suppressErrorToast) {
      const toast = useToast()
      const msg = error.response?.data?.detail || error.message || 'Erreur réseau'
      toast.show(msg)
    }
  }
  return Promise.reject(error)
})

export default api

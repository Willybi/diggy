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

// Auto-logout on 401, toast on 5xx / network error
api.interceptors.response.use(undefined, (error) => {
  if (error.response?.status === 401) {
    const auth = useAuthStore()
    if (auth.token) {
      auth.logout()
      router.push('/login')
    }
  } else if (!error.response || error.response.status >= 500) {
    const toast = useToast()
    const msg = error.response?.data?.detail || error.message || 'Erreur réseau'
    toast.show(msg)
  }
  return Promise.reject(error)
})

export default api

import axios from 'axios'
import { useAuthStore } from '../stores/auth.js'
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

// Auto-logout on 401
api.interceptors.response.use(undefined, (error) => {
  if (error.response?.status === 401) {
    const auth = useAuthStore()
    if (auth.token) {
      auth.logout()
      router.push('/login')
    }
  }
  return Promise.reject(error)
})

export default api

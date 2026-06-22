import { createApp } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import App from './App.vue'
import router from './router'
import './styles/diggy-tokens.css'

const pinia = createPinia()
const app = createApp(App)
app.use(pinia)
app.use(router)

// Auto-logout on 401 (expired/invalid token)
import { useAuthStore } from './stores/auth.js'
axios.interceptors.response.use(undefined, error => {
  if (error.response?.status === 401) {
    const auth = useAuthStore()
    if (auth.token) {
      auth.logout()
      router.push('/login')
    }
  }
  return Promise.reject(error)
})

app.mount('#app')

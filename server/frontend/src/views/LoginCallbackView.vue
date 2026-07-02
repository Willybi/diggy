<template>
  <div class="callback-page">
    <p v-if="error">{{ error }}</p>
    <p v-else>Connexion en cours...</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const error = ref(null)

onMounted(() => {
  const hash = window.location.hash.substring(1)
  const params = new URLSearchParams(hash)
  const token = params.get('token')
  const user = params.get('user')
  const state = params.get('state')

  const expected = sessionStorage.getItem('oauth_state')
  sessionStorage.removeItem('oauth_state')

  if (!expected || expected !== state) {
    error.value = 'Erreur de securite (state mismatch). Veuillez reessayer.'
    return
  }

  if (!token || !user) {
    error.value = 'Donnees de connexion manquantes.'
    return
  }

  auth._persist(token, JSON.parse(user))
  router.replace('/')
})
</script>

<style scoped>
.callback-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 50vh;
  color: var(--text-primary);
}
</style>

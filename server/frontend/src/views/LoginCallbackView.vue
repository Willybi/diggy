<template>
  <div class="callback-page">
    <template v-if="error">
      <p class="callback-error">{{ error }}</p>
      <router-link to="/login" class="callback-retry">Réessayer</router-link>
    </template>
    <p v-else>Connexion en cours…</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const error = ref(null)

onMounted(() => {
  // Backend error redirect (e.g. Google token exchange failed)
  if (route.query.error) {
    error.value = 'La connexion Google a échoué. Veuillez réessayer.'
    return
  }

  try {
    const hash = window.location.hash.substring(1)
    const params = new URLSearchParams(hash)
    const token = params.get('token')
    const user = params.get('user')
    const state = params.get('state')

    const expected = localStorage.getItem('oauth_state')
    localStorage.removeItem('oauth_state')

    if (!expected || expected !== state) {
      error.value = 'Erreur de sécurité (state mismatch). Veuillez réessayer.'
      return
    }

    if (!token || !user) {
      error.value = 'Données de connexion manquantes.'
      return
    }

    auth._persist(token, JSON.parse(user))
    router.replace('/')
  } catch {
    error.value = 'Erreur inattendue lors de la connexion.'
  }
})
</script>

<style scoped>
.callback-page {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 12px;
  min-height: 50vh;
  color: var(--ink-2);
  font: 400 14px/1.4 var(--font-ui);
}

.callback-error {
  color: var(--error);
  margin: 0;
}

.callback-retry {
  color: var(--accent);
  text-decoration: none;
  font-weight: 600;
}
</style>

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

function readCookie(name) {
  const match = document.cookie.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]+)'))
  return match ? match[1] : null
}

function deleteCookie(name) {
  document.cookie = name + '=; Max-Age=0; Path=/'
}

onMounted(() => {
  // Backend error redirect
  if (route.query.error) {
    error.value = 'La connexion Google a échoué. Veuillez réessayer.'
    return
  }

  try {
    // Read credentials from temporary cookie set by backend callback
    // (state already validated server-side via Redis)
    const raw = readCookie('auth_callback')
    deleteCookie('auth_callback')

    if (!raw) {
      error.value = 'Données de connexion manquantes.'
      return
    }

    // base64url → base64 (replace chars + re-add padding)
    const b64 = raw.replace(/-/g, '+').replace(/_/g, '/')
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4)
    const data = JSON.parse(atob(padded))

    auth._persist(data.token, data.user)
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

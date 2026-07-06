<template>
  <div class="callback-page">
    <p class="callback-error">{{ message }}</p>
    <router-link to="/login" class="callback-retry">Réessayer</router-link>
  </div>
</template>

<script setup>
/**
 * This view only handles error redirects from the backend
 * (e.g. /login/callback?error=google_failed).
 * The success flow is handled by inline HTML returned by the API callback.
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const message = computed(() => {
  if (route.query.error) return 'La connexion Google a échoué. Veuillez réessayer.'
  return 'Erreur de connexion.'
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

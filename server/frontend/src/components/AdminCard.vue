<template>
  <div v-if="auth.user?.is_admin" class="admin-card" :class="variant">
    <span class="admin-label">{{ label }}</span>
    <slot />
  </div>
</template>

<script setup>
import { useAuthStore } from '../stores/auth.js'

defineProps({
  label: { type: String, default: 'Admin' },
  variant: { type: String, default: 'default' },
})

const auth = useAuthStore()
</script>

<style scoped>
.admin-card {
  margin: 16px 0;
  padding: 14px 18px;
  background: var(--surface-2);
  border: 1px dashed var(--line-2);
  border-radius: var(--r-md);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.admin-card.warn {
  background: var(--surface);
  border: 1px solid var(--warn-ink);
  border-radius: var(--r-sm);
}
.admin-label {
  font: 600 9.5px/1 var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.warn .admin-label {
  color: var(--warn-ink);
}
</style>

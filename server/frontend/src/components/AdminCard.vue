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
  margin: var(--space-4) 0;
  padding: var(--space-4) var(--space-5);
  background: var(--surface-2);
  border: 1px dashed var(--line-2);
  border-radius: var(--r-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-25);
}
.admin-card.warn {
  background: var(--surface);
  border: 1px dashed var(--warn-ink);
  border-radius: var(--r-sm);
}
.admin-label {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.warn .admin-label {
  color: var(--warn-ink);
}
</style>

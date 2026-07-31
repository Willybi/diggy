<template>
  <button type="button" class="dv-back" @click="goBack">
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M15 6l-6 6 6 6" />
    </svg>
    {{ label }}
  </button>
</template>

<script setup>
import { useRouter } from 'vue-router'

const props = defineProps({
  // Where to land when there is no in-app history to go back to
  // (deep link, page refresh, arrival from an external site).
  fallback: { type: String, required: true },
  label: { type: String, default: 'Retour' },
})

const router = useRouter()

function goBack() {
  // history.state.back holds the previous entry's location, but only when it
  // was reached within this SPA session — it is null on a fresh load / deep
  // link, where router.back() would leave the app. Fall back to the list then.
  if (window.history.state?.back) router.back()
  else router.push(props.fallback)
}
</script>

<style scoped>
.dv-back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  margin-bottom: var(--space-5);
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  text-decoration: none;
  color: var(--ink-2);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  transition: color 0.12s;
}
.dv-back:hover {
  color: var(--ink);
}
.dv-back svg {
  width: 16px;
  height: 16px;
}
</style>

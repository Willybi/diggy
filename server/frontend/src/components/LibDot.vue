<template>
  <span class="lib-dot" :class="inLib ? 'in' : 'out'" :title="inLib ? 'In lib' : 'Pas dans la lib'">
    <svg v-if="inLib" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M2 6.5 4.5 9 10 3.5" />
    </svg>
    <svg v-else viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <path d="M3 3l6 6M9 3l-6 6" />
    </svg>
  </span>
</template>

<script setup>
defineProps({
  inLib: { type: Boolean, required: true },
})
</script>

<style scoped>
.lib-dot {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  flex: none;
}
.lib-dot svg {
  width: 12px;
  height: 12px;
}
.lib-dot.in  { background: var(--pos-soft);   color: var(--pos-ink); }
.lib-dot.out { background: var(--surface-3);  color: var(--ink-3); outline: 1px solid var(--line); }
</style>

<template>
  <span class="badge" :class="inLib ? 'badge--in' : 'badge--out'">
    <svg
      v-if="inLib"
      class="check-icon"
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M2 6.5 4.5 9 10 3.5" />
    </svg>
    {{ inLib ? 'In lib' : 'Not in lib' }}
  </span>
</template>

<script setup>
defineProps({
  inLib: { type: Boolean, required: true },
})
</script>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font: 500 var(--fs-xs)/1 var(--font-ui);
  letter-spacing: 0.005em;
  padding: var(--space-1) var(--space-25) var(--space-1) var(--space-2);
  border-radius: var(--r-pill);
}
.badge--in {
  background: var(--pos-soft);
  color: var(--pos-ink);
}
.badge--out {
  color: var(--ink-3);
  border: 1px dashed var(--line-2);
}
.check-icon {
  width: 12px;
  height: 12px;
  flex: none;
}
</style>

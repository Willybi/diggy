<template>
  <button v-if="empty" type="button" class="fchip fchip--empty" @click="emit('remove')">
    <span class="fchip-label">{{ label }}</span>
    <span class="fchip-value">{{ value }}</span>
    <span class="fchip-x" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4">
        <path d="M18 6 6 18M6 6l12 12" stroke-linecap="round" />
      </svg>
    </span>
  </button>

  <span v-else class="fchip">
    <span class="fchip-label">{{ label }}</span>
    <span class="fchip-value">{{ value }}</span>
    <button type="button" class="fchip-x" :aria-label="`Retirer ${label}`" @click="emit('remove')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12" stroke-linecap="round" />
      </svg>
    </button>
  </span>
</template>

<script setup>
// Empty-state variant (`empty`): the whole chip becomes the remove button
// (retirer = réparer) — consumed by the page's « Aucun résultat » state.
defineProps({
  label: { type: String, required: true },
  value: { type: String, default: '' },
  empty: { type: Boolean, default: false },
})
const emit = defineEmits(['remove'])
</script>

<style scoped>
.fchip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  height: 26px;
  padding: 0 4px 0 10px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-pill);
  background: var(--surface);
  white-space: nowrap;
}
.fchip-label {
  font: 500 var(--fs-nano) var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-3);
}
.fchip-value {
  font: 600 var(--fs-xs) var(--font-mono);
  color: var(--ink);
}
.fchip-x {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s;
}
.fchip-x:hover {
  background: var(--surface-3);
  color: var(--ink);
}
.fchip-x svg {
  width: 10px;
  height: 10px;
}
.fchip-x:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.fchip--empty {
  cursor: pointer;
  transition:
    border-color 0.12s,
    color 0.12s;
}
.fchip--empty:hover {
  border-color: var(--neg);
}
.fchip--empty:hover .fchip-label,
.fchip--empty:hover .fchip-value,
.fchip--empty:hover .fchip-x {
  color: var(--neg);
}
.fchip--empty:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>

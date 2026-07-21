<template>
  <div class="cam" :class="{ 'cam--drawer': variant === 'drawer' }">
    <div class="cam-grid" role="group" aria-label="Clés Camelot">
      <button
        v-for="k in CAMELOT_KEYS"
        :key="k"
        type="button"
        class="cam-cell"
        :class="{ on: isOn(k) }"
        :aria-pressed="isOn(k)"
        @click="toggleKey(k)"
      >
        {{ k }}
      </button>
    </div>
    <span class="cam-legend">A mineures · B majeures</span>
  </div>
</template>

<script setup>
import { CAMELOT_KEYS } from './camelot.js'

const props = defineProps({
  // Array of selected Camelot keys ('1A'…'12B').
  modelValue: { type: Array, default: () => [] },
  variant: { type: String, default: 'panel' }, // 'panel' (12×2) | 'drawer' (6×4, 32px)
})
const emit = defineEmits(['update:modelValue'])

function isOn(k) {
  return props.modelValue.includes(k)
}

function toggleKey(k) {
  const next = isOn(k) ? props.modelValue.filter((v) => v !== k) : [...props.modelValue, k]
  emit('update:modelValue', next)
}
</script>

<style scoped>
.cam {
  display: flex;
  flex-direction: column;
  gap: var(--space-15);
}
/* 12 columns × 2 rows — minors (A) on top, majors (B) below: harmonic
   neighbours (±1 column, A↔B same column) are grid-adjacent. */
.cam-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: var(--space-05);
}
.cam--drawer .cam-grid {
  grid-template-columns: repeat(6, minmax(0, 1fr));
}
.cam-cell {
  min-height: 28px;
  padding: 0;
  border: 1px solid var(--line-2);
  border-radius: var(--r-xs);
  background: var(--surface);
  color: var(--ink-2);
  font: 600 var(--fs-xs) var(--font-mono);
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s,
    border-color 0.12s;
}
.cam--drawer .cam-cell {
  min-height: 32px;
}
.cam-cell:hover {
  background: var(--surface-2);
}
.cam-cell.on {
  background: var(--accent);
  color: var(--on-accent);
  border-color: transparent;
}
.cam-cell:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.cam-legend {
  font: 500 var(--fs-nano) var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-3);
}
</style>

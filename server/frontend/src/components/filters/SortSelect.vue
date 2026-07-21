<template>
  <label class="sort" :class="{ 'is-disabled': disabled }">
    <svg
      class="sort-ic"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      aria-hidden="true"
    >
      <path d="M4 6h16M6 12h12M9 18h6" stroke-linecap="round" />
    </svg>
    <select
      class="sort-select"
      :value="modelValue"
      :disabled="disabled"
      :aria-label="ariaLabel"
      @change="onChange"
    >
      <option v-for="opt in options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
    </select>
    <svg
      class="sort-chev"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      aria-hidden="true"
    >
      <path d="m6 9 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  </label>
</template>

<script setup>
// Sorting is URL state but NOT a filter: never a chip, never counted in the badge.
defineProps({
  modelValue: { type: String, default: '' },
  // [{ value, label }] — provided by the page.
  options: { type: Array, required: true },
  ariaLabel: { type: String, default: 'Trier' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

function onChange(e) {
  emit('update:modelValue', e.target.value)
}
</script>

<style scoped>
.sort {
  position: relative;
  display: inline-block;
}
.sort-select {
  appearance: none;
  -webkit-appearance: none;
  height: 38px;
  padding: 0 30px 0 32px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s,
    border-color 0.12s;
}
.sort-select:hover {
  background: var(--surface-2);
  color: var(--ink);
}
.sort-select:focus {
  outline: none;
  border-color: var(--accent);
}
.sort-select:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.sort-ic,
.sort-chev {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  color: var(--ink-3);
  pointer-events: none;
}
.sort-ic {
  left: var(--space-25);
  width: 14px;
  height: 14px;
}
.sort-chev {
  right: var(--space-25);
  width: 12px;
  height: 12px;
}
.is-disabled {
  opacity: 0.45;
  pointer-events: none;
}
</style>

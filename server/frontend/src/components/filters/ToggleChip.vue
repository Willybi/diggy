<template>
  <button
    type="button"
    class="tgl"
    :class="{ on: modelValue, 'tgl--drawer': variant === 'drawer' }"
    :aria-pressed="modelValue"
    :disabled="disabled"
    @click="toggle"
  >
    <span v-if="$slots.icon" class="tgl-ic"><slot name="icon" /></span>
    {{ label }}
  </button>
</template>

<script setup>
const props = defineProps({
  // Off = criterion absent.
  modelValue: { type: Boolean, default: false },
  label: { type: String, required: true },
  variant: { type: String, default: 'panel' }, // 'panel' (28px) | 'drawer' (32px)
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

function toggle() {
  emit('update:modelValue', !props.modelValue)
}
</script>

<style scoped>
.tgl {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  height: 28px;
  padding: 0 var(--space-25);
  border: 1px solid var(--line-2);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-xs) var(--font-ui);
  white-space: nowrap;
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s,
    border-color 0.12s;
}
.tgl--drawer {
  height: 32px;
  padding: 0 var(--space-3);
}
.tgl:hover {
  background: var(--surface-2);
}
.tgl.on {
  background: var(--accent);
  color: var(--on-accent);
  border-color: transparent;
}
.tgl:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.tgl:disabled {
  opacity: 0.45;
  pointer-events: none;
}
.tgl-ic {
  display: grid;
  place-items: center;
}
.tgl-ic :deep(svg) {
  width: 12px;
  height: 12px;
}
</style>

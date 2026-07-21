<template>
  <div class="seg" :class="{ 'seg--drawer': variant === 'drawer' }" role="group">
    <button
      v-for="opt in options"
      :key="String(opt.value)"
      type="button"
      class="seg-pill"
      :class="{ on: isOn(opt), mono: mono }"
      :aria-pressed="isOn(opt)"
      :disabled="disabled"
      @click="pick(opt)"
    >
      {{ opt.label }}
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // null = inactive criterion. With a « Tous » option (value: null) exactly one
  // pill is active; without it (presets) re-clicking the active pill deselects.
  modelValue: { type: [String, Number, Boolean], default: null },
  // [{ value, label }] — value null marks the « Tous » option.
  options: { type: Array, required: true },
  // Numeric values (durées) read better in mono.
  mono: { type: Boolean, default: false },
  variant: { type: String, default: 'panel' }, // 'panel' (28px) | 'drawer' (32px)
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const hasAll = computed(() => props.options.some((o) => o.value === null))

function isOn(opt) {
  if (opt.value === null) return props.modelValue == null
  return props.modelValue === opt.value
}

function pick(opt) {
  if (opt.value === null) {
    emit('update:modelValue', null)
    return
  }
  if (props.modelValue === opt.value) {
    // Presets without « Tous »: re-click = deselect. With « Tous », one stays active.
    if (!hasAll.value) emit('update:modelValue', null)
    return
  }
  emit('update:modelValue', opt.value)
}
</script>

<style scoped>
.seg {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}
.seg-pill {
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
.seg--drawer .seg-pill {
  height: 32px;
  padding: 0 var(--space-3);
}
.seg-pill.mono {
  font-family: var(--font-mono);
}
.seg-pill:hover {
  background: var(--surface-2);
}
.seg-pill.on {
  background: var(--accent);
  color: var(--on-accent);
  border-color: transparent;
}
.seg-pill:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.seg-pill:disabled {
  opacity: 0.45;
  pointer-events: none;
}
</style>

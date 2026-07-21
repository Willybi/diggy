<template>
  <div class="rs" :class="{ 'is-disabled': disabled }">
    <span class="rs-val">{{ display(lo) }}</span>
    <div class="rs-rail">
      <div class="rs-track">
        <div class="rs-fill" :style="fillStyle"></div>
      </div>
      <input
        class="rs-input"
        type="range"
        :min="min"
        :max="max"
        :step="step"
        :value="lo"
        :disabled="disabled"
        :aria-label="`${label} minimum`"
        @input="onLo"
      />
      <input
        class="rs-input"
        type="range"
        :min="min"
        :max="max"
        :step="step"
        :value="hi"
        :disabled="disabled"
        :aria-label="`${label} maximum`"
        @input="onHi"
      />
    </div>
    <span class="rs-val">{{ display(hi) }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // [lo, hi] — null/absent means the full range (inactive criterion).
  modelValue: { type: Array, default: null },
  min: { type: Number, required: true },
  max: { type: Number, required: true },
  step: { type: Number, default: 1 },
  label: { type: String, default: 'Plage' },
  format: { type: Function, default: null },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const lo = computed(() => clamp(props.modelValue?.[0] ?? props.min))
const hi = computed(() => clamp(props.modelValue?.[1] ?? props.max))

function clamp(v) {
  return Math.min(props.max, Math.max(props.min, Number(v)))
}

function display(v) {
  return props.format ? props.format(v) : String(v)
}

// Min never crosses max (and vice versa): the moving thumb is clamped onto
// the other one, and the native input is written back so it can't drift.
function onLo(e) {
  const v = Math.min(clamp(e.target.value), hi.value)
  e.target.value = String(v)
  emit('update:modelValue', [v, hi.value])
}

function onHi(e) {
  const v = Math.max(clamp(e.target.value), lo.value)
  e.target.value = String(v)
  emit('update:modelValue', [lo.value, v])
}

const fillStyle = computed(() => {
  const span = props.max - props.min || 1
  const left = ((lo.value - props.min) / span) * 100
  const right = 100 - ((hi.value - props.min) / span) * 100
  return { left: `${left}%`, right: `${right}%` }
})
</script>

<style scoped>
.rs {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.rs-val {
  font: 600 var(--fs-xs) var(--font-mono);
  color: var(--ink-2);
  min-width: 3ch;
  text-align: center;
  flex: none;
}
.rs-rail {
  position: relative;
  flex: 1;
  height: 16px;
  min-width: 0;
}
.rs-track {
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  height: 3px;
  border-radius: var(--r-pill);
  background: var(--surface-3);
}
.rs-fill {
  position: absolute;
  top: 0;
  bottom: 0;
  border-radius: var(--r-pill);
  background: var(--accent);
}

/* Two superposed native ranges — the rail ignores the pointer, thumbs catch it.
   Native keyboard arrows keep working on each input. */
.rs-input {
  position: absolute;
  inset: 0;
  width: 100%;
  margin: 0;
  appearance: none;
  -webkit-appearance: none;
  background: transparent;
  pointer-events: none;
}
.rs-input::-webkit-slider-thumb {
  appearance: none;
  -webkit-appearance: none;
  pointer-events: auto;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid var(--surface);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
}
.rs-input::-moz-range-thumb {
  pointer-events: auto;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid var(--surface);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
}
.rs-input:focus {
  outline: none;
}
.rs-input:focus-visible::-webkit-slider-thumb {
  box-shadow:
    0 0 0 2px var(--surface),
    0 0 0 4px var(--accent);
}
.rs-input:focus-visible::-moz-range-thumb {
  box-shadow:
    0 0 0 2px var(--surface),
    0 0 0 4px var(--accent);
}
.rs.is-disabled {
  opacity: 0.45;
  pointer-events: none;
}
.rs.is-disabled .rs-input::-webkit-slider-thumb {
  background: var(--ink-3);
}
.rs.is-disabled .rs-input::-moz-range-thumb {
  background: var(--ink-3);
}
</style>

<template>
  <span class="score-ring" :class="`score-ring--${size}`" role="img" :aria-label="ariaLabel">
    <svg class="sr-svg" :viewBox="`0 0 ${box} ${box}`">
      <circle class="sr-track" :cx="center" :cy="center" :r="radius" :stroke-width="stroke" />
      <circle
        class="sr-arc"
        :cx="center"
        :cy="center"
        :r="radius"
        :stroke-width="stroke"
        :stroke-dasharray="dash"
        stroke-linecap="round"
      />
    </svg>
    <span class="sr-note" :class="{ 'sr-note--pct': isPct }">{{ centerText }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

// Fine no-break space (U+202F) before "%", per French typography.
const THIN_NBSP = String.fromCharCode(0x202f)

const props = defineProps({
  // 'score' mode: 0-1 displayed as Math.round(score * 10).
  // 'pct' mode: 0-1 proportion displayed as Math.round(score * 100) + " %".
  score: { type: Number, required: true },
  size: { type: String, default: 'sm' }, // 'sm' 30px · 'md' 40px
  label: { type: String, default: '' }, // a11y label; defaults per mode
  mode: {
    type: String,
    default: 'score',
    validator: (v) => v === 'score' || v === 'pct',
  },
})

const isPct = computed(() => props.mode === 'pct')
const note = computed(() => Math.round(props.score * 10))
const pct = computed(() => Math.round(props.score * 100))
const box = computed(() => (props.size === 'md' ? 40 : 30))
const stroke = computed(() => (props.size === 'md' ? 3 : 2.5))
const center = computed(() => box.value / 2)
const radius = computed(() => (box.value - stroke.value) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
// Arc fill = the proportion itself in pct mode, note/10 in score mode.
const fraction = computed(() =>
  isPct.value ? Math.min(1, Math.max(0, props.score)) : note.value / 10,
)
const dash = computed(() => {
  const filled = circumference.value * fraction.value
  return `${filled.toFixed(2)} ${(circumference.value - filled).toFixed(2)}`
})
const centerText = computed(() => (isPct.value ? `${pct.value}${THIN_NBSP}%` : String(note.value)))
const ariaLabel = computed(() => {
  if (props.label) return props.label
  return isPct.value ? `${pct.value}${THIN_NBSP}%` : `Score ${note.value} /10`
})
</script>

<style scoped>
.score-ring {
  position: relative;
  display: inline-grid;
  place-items: center;
  flex: none;
}
.score-ring--sm {
  width: 30px;
  height: 30px;
}
.score-ring--md {
  width: 40px;
  height: 40px;
}
.sr-svg {
  width: 100%;
  height: 100%;
  /* Start the arc at 12 o'clock. */
  transform: rotate(-90deg);
}
.sr-track {
  fill: none;
  stroke: var(--line-2);
}
.sr-arc {
  fill: none;
  stroke: var(--accent);
}
.sr-note {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font: 600 var(--fs-xs) var(--font-mono);
  color: var(--ink);
}
.score-ring--md .sr-note {
  font-size: var(--fs-sm);
}
/* Percent mode: a denser center so "100 %" fits the ring at both sizes.
   Placed last with matching specificity so it wins over the md rule above. */
.score-ring .sr-note--pct {
  font-size: var(--fs-nano);
}
</style>

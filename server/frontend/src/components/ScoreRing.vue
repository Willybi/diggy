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
    <span class="sr-note">{{ note }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  score: { type: Number, required: true }, // 0-1, displayed as Math.round(score * 10)
  size: { type: String, default: 'sm' }, // 'sm' 30px · 'md' 40px
  label: { type: String, default: '' }, // a11y label; defaults to "Score N /10"
})

const note = computed(() => Math.round(props.score * 10))
const box = computed(() => (props.size === 'md' ? 40 : 30))
const stroke = computed(() => (props.size === 'md' ? 3 : 2.5))
const center = computed(() => box.value / 2)
const radius = computed(() => (box.value - stroke.value) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
const dash = computed(() => {
  const filled = circumference.value * (note.value / 10)
  return `${filled.toFixed(2)} ${(circumference.value - filled).toFixed(2)}`
})
const ariaLabel = computed(() => props.label || `Score ${note.value} /10`)
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
</style>

<template>
  <div class="tile" :class="`tile--${tone}`">
    <div class="tile-label">{{ label }}</div>
    <div class="tile-value-row">
      <span class="tile-value">{{ value }}</span>
      <span v-if="delta != null && delta !== ''" class="tile-delta" :class="deltaClass">
        {{ delta }}
      </span>
    </div>
    <div v-if="sublabel" class="tile-sub">{{ sublabel }}</div>
    <slot />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: '—' },
  // Small signed change, e.g. "+42". Colored by its leading sign.
  delta: { type: [String, Number], default: null },
  sublabel: { type: String, default: '' },
  // Accent marker: neutral | deezer | beatport | pos | neg | warn | accent
  tone: { type: String, default: 'neutral' },
})

const deltaClass = computed(() => {
  const d = String(props.delta ?? '').trim()
  if (d.startsWith('-')) return 'tile-delta--neg'
  if (d.startsWith('+')) return 'tile-delta--pos'
  return 'tile-delta--flat'
})
</script>

<style scoped>
.tile {
  position: relative;
  padding: var(--space-3) var(--space-3) var(--space-3) var(--space-4);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  overflow: hidden;
}
/* Left accent bar tinted by tone. */
.tile::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--tile-accent, var(--ink-3));
}
.tile--deezer {
  --tile-accent: var(--chart-deezer);
}
.tile--beatport {
  --tile-accent: var(--chart-beatport);
}
.tile--pos {
  --tile-accent: var(--pos);
}
.tile--neg {
  --tile-accent: var(--neg);
}
.tile--warn {
  --tile-accent: var(--warn);
}
.tile--accent {
  --tile-accent: var(--accent);
}
.tile--neutral {
  --tile-accent: var(--line-2);
}
.tile-label {
  font: 500 var(--fs-label)/1.2 var(--font-mono);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin-bottom: var(--space-1);
}
.tile-value-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
}
.tile-value {
  font: 600 var(--fs-lg)/1 var(--font-ui);
  color: var(--ink);
  letter-spacing: -0.02em;
}
.tile-delta {
  font: 500 var(--fs-xs)/1 var(--font-mono);
}
.tile-delta--pos {
  color: var(--pos-ink);
}
.tile-delta--neg {
  color: var(--neg-ink);
}
.tile-delta--flat {
  color: var(--ink-3);
}
.tile-sub {
  margin-top: var(--space-1);
  font: 400 var(--fs-xs)/1.3 var(--font-ui);
  color: var(--ink-3);
}
</style>

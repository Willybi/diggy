<template>
  <div class="tile" :class="[`tile--${tone}`, { 'tile--bar': showBar }]">
    <div class="tile-label">{{ label }}</div>
    <div class="tile-value-row">
      <span class="tile-value">{{ value }}</span>
      <span v-if="delta != null && delta !== ''" class="tile-delta" :class="deltaClass">
        {{ delta }}
      </span>
    </div>
    <div v-if="sublabel" class="tile-sub">{{ sublabel }}</div>
    <div v-if="hasFoot" class="tile-foot"><slot /></div>
  </div>
</template>

<script setup>
import { computed, useSlots } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: '—' },
  // Small signed change, e.g. "+42". Colored by its leading sign.
  delta: { type: [String, Number], default: null },
  sublabel: { type: String, default: '' },
  // Accent marker: neutral | deezer | beatport | embeddings | pos | neg | warn | accent
  tone: { type: String, default: 'neutral' },
})

const slots = useSlots()
// A tile carries a footer only when the parent passes a sparkline into the slot.
const hasFoot = computed(() => !!slots.default)

// Left tile bar (archétype F, D21/D22): only tiles that carry a SERIES get the
// 3px filet — a sparkline (footer slot) or an identified platform (deezer /
// beatport). Plain counters (integrity, backlog counts, durations) have none.
const showBar = computed(
  () => hasFoot.value || props.tone === 'deezer' || props.tone === 'beatport',
)

const deltaClass = computed(() => {
  const d = String(props.delta ?? '').trim()
  if (d.startsWith('-')) return 'tile-delta--neg'
  if (d.startsWith('+')) return 'tile-delta--pos'
  return 'tile-delta--flat'
})
</script>

<style scoped>
/* ── StatTile (archétype F) : --surface-2 + 1px --line + --r-sm, min-height 92px,
   clé mono nano · valeur mono 600 --fs-xl · delta · contexte · sparkline en pied
   (margin-top:auto). Le filet gauche coloré n'apparaît que sur `tile--bar`. ── */
.tile {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 92px;
  padding: var(--space-3) var(--space-3) var(--space-3) var(--space-4);
  background: var(--surface-2);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  overflow: hidden;
}
/* Left accent bar tinted by the series colour — series-bearing tiles only (D22). */
.tile--bar::before {
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
.tile--embeddings {
  --tile-accent: var(--chart-embeddings);
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
  font: 500 var(--fs-nano)/1.2 var(--font-mono);
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
  font: 600 var(--fs-xl)/1 var(--font-mono);
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
/* Sparkline footer: pinned to the bottom of the tile (D21 · 30px). */
.tile-foot {
  margin-top: auto;
  padding-top: var(--space-2);
}
</style>

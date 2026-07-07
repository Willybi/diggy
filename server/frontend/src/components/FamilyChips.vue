<template>
  <div class="fam-chips">
    <button
      v-for="chip in chips"
      :key="chip.key"
      class="fam-chip"
      :class="{ on: modelValue === chip.key }"
      :data-fam="chip.fam"
      @click="emit('update:modelValue', chip.key)"
    >
      <span v-if="chip.fam" class="fc-dot"></span>
      {{ chip.label }}<span class="fc-n">{{ fmtNum(chip.count) }}</span>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { PILLAR_ORDER, PILLAR_LABELS } from '../composables/useStyleMap.js'
import { fmtNum } from '../utils/format'

const props = defineProps({
  modelValue: { type: String, required: true },
  counts: { type: Object, required: true },
})
const emit = defineEmits(['update:modelValue'])

const chips = computed(() => {
  const allCount = Object.values(props.counts).reduce((s, v) => s + v, 0)
  return [
    { key: 'all', label: 'Tous', fam: null, count: allCount },
    ...PILLAR_ORDER.map((k) => ({
      key: k,
      label: PILLAR_LABELS[k],
      fam: k,
      count: props.counts[k] || 0,
    })),
  ]
})
</script>

<style scoped>
.fam-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 0 30px 16px;
}
.fam-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 12px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition:
    background 0.14s,
    border-color 0.14s,
    color 0.14s;
}
.fam-chip:hover {
  background: var(--surface-2);
  color: var(--ink);
}
.fc-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
  background: oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th));
  box-shadow: 0 0 0 1px oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th) / 0.28);
}
.fc-n {
  font: 600 11px/1 var(--font-mono);
  color: var(--ink-3);
}
.fam-chip.on {
  background: var(--accent-soft);
  border-color: transparent;
  color: var(--accent-ink);
}
.fam-chip.on .fc-n {
  color: var(--accent-ink);
}
/* Pillar hue mapping */
.fam-chip[data-fam='house'] {
  --th: var(--hue-house);
}
.fam-chip[data-fam='techno'] {
  --th: var(--hue-techno);
}
.fam-chip[data-fam='trance'] {
  --th: var(--hue-trance);
}
.fam-chip[data-fam='dnb'] {
  --th: var(--hue-dnb);
}
.fam-chip[data-fam='hardcore'] {
  --th: var(--hue-hardcore);
}
.fam-chip[data-fam='harddance'] {
  --th: var(--hue-harddance);
}
.fam-chip[data-fam='autres'] .fc-dot {
  background: var(--ink-3);
  box-shadow: 0 0 0 1px oklch(0 0 0 / 0.08);
}
.fam-chip:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>

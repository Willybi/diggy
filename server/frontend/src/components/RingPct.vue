<template>
  <span class="ring" :class="stateClass" :title="`${value} / ${total} tracks identifiées`">
    <template v-if="pct >= 100">
      <span class="chk">
        <svg viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" /></svg>
      </span>
    </template>
    <svg v-else viewBox="0 0 30 30">
      <circle class="bg" cx="15" cy="15" :r="R" />
      <circle
        class="fg"
        cx="15"
        cy="15"
        :r="R"
        :stroke-dasharray="C.toFixed(1)"
        :stroke-dashoffset="offset"
      />
    </svg>
    <span class="pct">{{ pct }}%</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: { type: Number, required: true },
  total: { type: Number, required: true },
})

const R = 13
const C = 2 * Math.PI * R

const pct = computed(() => (props.total ? Math.round((props.value / props.total) * 100) : 0))
const offset = computed(() => (C * (1 - pct.value / 100)).toFixed(1))
const stateClass = computed(() => {
  if (pct.value >= 100) return 'done'
  if (pct.value >= 60) return 'mid'
  return 'low'
})
</script>

<style scoped>
.ring {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}
.ring svg {
  width: 30px;
  height: 30px;
  transform: rotate(-90deg);
  flex: none;
}
.bg {
  fill: none;
  stroke: var(--surface-3);
  stroke-width: 3.4;
}
.fg {
  fill: none;
  stroke-width: 3.4;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.4s ease;
}
.ring.mid .fg {
  stroke: var(--accent);
}
.ring.low .fg {
  stroke: var(--warn);
}
.pct {
  font: 600 var(--fs-sm) var(--font-mono);
  color: var(--ink-2);
  min-width: 34px;
}
.ring.done .chk {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--surface-2);
  color: var(--ink-3);
}
.ring.done .chk svg {
  width: 13px;
  height: 13px;
  transform: none;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.ring.done .pct {
  color: var(--ink-3);
}
.ring.mid .pct {
  color: var(--accent-ink);
}
.ring.low .pct {
  color: var(--warn-ink);
}
</style>

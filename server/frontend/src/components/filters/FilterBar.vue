<template>
  <div ref="rootEl" class="fbar">
    <div class="fbar-row">
      <div v-if="$slots.search" class="fbar-search"><slot name="search" /></div>
      <button
        class="btn fbar-toggle"
        type="button"
        :aria-expanded="panelOpen"
        @click="onToggleClick"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M4 8h9M17 8h3M4 16h5M13 16h7" stroke-linecap="round" />
          <circle cx="15" cy="8" r="2" />
          <circle cx="11" cy="16" r="2" />
        </svg>
        Filtres
        <span v-if="activeCount" class="fbar-badge">{{ activeCount }}</span>
      </button>
      <slot name="sort" />
      <span class="fbar-count">{{ countText }}</span>
    </div>

    <div v-if="chips.length" class="fbar-chips">
      <FilterChip
        v-for="chip in chips"
        :key="chip.id"
        :label="chip.label"
        :value="chip.value"
        @remove="removeChip(chip)"
      />
      <button class="fbar-clear" type="button" @click="clearAll">Tout effacer</button>
    </div>

    <div v-if="panelOpen" class="fbar-panel"><slot name="panel" /></div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import FilterChip from './FilterChip.vue'
import { buildChips, countActive, defaultValue } from './criteria.js'

const props = defineProps({
  // Criterion descriptors — see criteria.js for the shape.
  criteria: { type: Array, required: true },
  // Flat filter state { key: value } (v-model:filters).
  filters: { type: Object, required: true },
  resultCount: { type: Number, default: null },
  loading: { type: Boolean, default: false },
  panelOpen: { type: Boolean, default: false },
  drawerOpen: { type: Boolean, default: false },
})
const emit = defineEmits([
  'update:filters',
  'update:panelOpen',
  'update:drawerOpen',
  'remove',
  'clear',
])

const rootEl = ref(null)

const activeCount = computed(() => countActive(props.criteria, props.filters))
const chips = computed(() => buildChips(props.criteria, props.filters))

const countText = computed(() => {
  if (props.loading) return '…'
  if (props.resultCount == null) return ''
  const n = props.resultCount
  return `${n.toLocaleString('fr-FR')} ${n > 1 ? 'résultats' : 'résultat'}`
})

// < 640px (bar width): the button opens the drawer; otherwise it toggles the
// inline panel. Width 0 (not laid out yet) falls back to the panel.
function onToggleClick() {
  const width = rootEl.value?.offsetWidth || 0
  if (width > 0 && width < 640) emit('update:drawerOpen', true)
  else emit('update:panelOpen', !props.panelOpen)
}

function removeChip(chip) {
  const criterion = props.criteria.find((c) => c.key === chip.key)
  if (!criterion) return
  let next
  if (criterion.type === 'multi' && criterion.chipPerValue) {
    // One chip per value: × removes THAT value only.
    next = props.filters[chip.key].filter((v) => v !== chip.rawValue)
  } else {
    next = defaultValue(criterion)
  }
  emit('update:filters', { ...props.filters, [chip.key]: next })
  emit('remove', chip.key, chip.rawValue)
}

function clearAll() {
  const next = { ...props.filters }
  for (const c of props.criteria) {
    if (c.chip === false) continue
    next[c.key] = defaultValue(c)
  }
  emit('update:filters', next)
  emit('clear')
}
</script>

<style scoped>
.fbar {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.fbar-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}
.fbar-search {
  flex: 1 1 220px;
  max-width: 400px;
  min-width: 0;
}
.fbar-toggle svg {
  width: 15px;
  height: 15px;
}
.fbar-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 var(--space-1);
  border-radius: var(--r-pill);
  background: var(--accent);
  color: var(--on-accent);
  font: 600 var(--fs-xs) var(--font-mono);
}
.fbar-count {
  margin-left: auto;
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--ink-2);
  white-space: nowrap;
}

.fbar-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-15);
}
.fbar-clear {
  border: 0;
  background: transparent;
  padding: 0 var(--space-1);
  font: 500 var(--fs-xs) var(--font-ui);
  color: var(--ink-3);
  cursor: pointer;
  transition: color 0.12s;
}
.fbar-clear:hover {
  color: var(--ink);
}
.fbar-clear:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>

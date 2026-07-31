<template>
  <div class="seg-splitter">
    <div class="seg-header">
      <span class="seg-label">Découper :</span>
      <strong class="seg-raw">{{ raw }}</strong>
      <button class="btn-seg-ghost" @click="emit('cancel')">Annuler</button>
    </div>

    <!-- Units + toggleable cut boundaries: toggling a "·" splits/merges. -->
    <div class="seg-units">
      <template v-for="(unit, i) in units" :key="i">
        <span class="seg-unit">{{ unit }}</span>
        <button
          v-if="i < units.length - 1"
          class="seg-cut"
          :class="{ active: cuts[i] }"
          :title="cuts[i] ? 'Fusionner ces deux morceaux' : 'Couper ici'"
          @click="toggleCut(i)"
        >
          {{ cuts[i] ? '|' : '·' }}
        </button>
      </template>
    </div>

    <!-- Resulting segments: each can be kept or marked as an artefact to drop. -->
    <div class="seg-chips">
      <div v-for="(seg, i) in segments" :key="i" class="seg-chip" :class="{ deleted: !seg.keep }">
        <span class="seg-chip-text">{{ seg.text }}</span>
        <button
          class="seg-trash"
          :title="seg.keep ? 'Marquer comme à supprimer' : 'Rétablir'"
          @click="toggleSegment(seg)"
        >
          {{ seg.keep ? '🗑' : '↩' }}
        </button>
      </div>
    </div>

    <div class="seg-actions">
      <button
        class="btn-seg-confirm"
        :disabled="pending || outputTokens.length === 0"
        @click="confirm"
      >
        {{ pending ? 'Split…' : confirmLabel }}
      </button>
      <span v-if="outputTokens.length === 0" class="seg-hint"> Gardez au moins un segment. </span>
      <span v-if="error" class="seg-error">{{ error }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { initSplitState, computeSegments, keptTokens } from '../../utils/artistSplit.js'

const props = defineProps({
  // Full original artist string — drives the backend relink/cleanup, must reach
  // the API verbatim; here it seeds the units and is shown as context.
  raw: { type: String, required: true },
  // Pre-made starting segments (Flags tab passes flag.tokens). Null = derive the
  // units from `raw`.
  initialTokens: { type: Array, default: null },
  pending: { type: Boolean, default: false },
  error: { type: String, default: '' },
  confirmLabel: { type: String, default: 'Confirmer le split' },
})

const emit = defineEmits(['confirm', 'cancel'])

const sep = ref(' ')
const units = ref([])
const cuts = ref([])
const keep = ref([])

function reset() {
  const state = initSplitState(props.raw, props.initialTokens)
  sep.value = state.sep
  units.value = state.units
  cuts.value = state.cuts
  keep.value = state.keep
}

watch(() => props.raw, reset, { immediate: true })

const segments = computed(() =>
  computeSegments(units.value, cuts.value, sep.value).map((seg) => ({
    ...seg,
    keep: seg.unitIndices.some((j) => keep.value[j]),
  })),
)

const outputTokens = computed(() => keptTokens(units.value, cuts.value, keep.value, sep.value))

function toggleCut(i) {
  cuts.value[i] = !cuts.value[i]
}

function toggleSegment(seg) {
  const next = !seg.keep
  seg.unitIndices.forEach((j) => {
    keep.value[j] = next
  })
}

function confirm() {
  if (props.pending || outputTokens.value.length === 0) return
  emit('confirm', outputTokens.value)
}
</script>

<style scoped>
.seg-splitter {
  padding: var(--space-3) var(--space-4);
  background: var(--surface-2);
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
}
.seg-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-2);
  flex-wrap: wrap;
}
.seg-label {
  white-space: nowrap;
}
.seg-raw {
  color: var(--ink);
}
.btn-seg-ghost {
  margin-left: auto;
  padding: var(--space-05) var(--space-15);
  border-radius: 4px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  font: 500 var(--fs-xs)/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-seg-ghost:hover {
  color: var(--ink-2);
  border-color: var(--ink-3);
}

/* Units + cut toggles */
.seg-units {
  display: flex;
  align-items: center;
  gap: 0;
  flex-wrap: wrap;
  margin-bottom: var(--space-3);
}
.seg-unit {
  font: 500 var(--fs-base)/1 var(--font-ui);
  color: var(--ink);
  padding: var(--space-1) 0;
}
.seg-cut {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 24px;
  margin: 0 var(--space-05);
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: 2px;
  cursor: pointer;
  font: 700 var(--fs-base)/1 var(--font-mono);
  color: var(--ink-3);
  transition:
    background 0.12s,
    color 0.12s,
    border-color 0.12s;
}
.seg-cut:hover {
  border-color: var(--accent);
  color: var(--accent-ink);
}
.seg-cut.active {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent-ink);
}

/* Resulting segments */
.seg-chips {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-bottom: var(--space-3);
}
.seg-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  background: var(--accent-soft);
  color: var(--accent-ink);
  padding: var(--space-05) var(--space-1) var(--space-05) var(--space-25);
  border-radius: 4px;
  border: 1px solid transparent;
}
.seg-chip.deleted {
  background: var(--surface);
  border-color: var(--line-2);
  color: var(--ink-3);
}
.seg-chip.deleted .seg-chip-text {
  text-decoration: line-through;
}
.seg-chip-text {
  font: 500 var(--fs-sm)/1 var(--font-ui);
  white-space: nowrap;
}
.seg-trash {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: var(--fs-xs);
  line-height: 1;
  padding: var(--space-05);
  border-radius: 3px;
  color: inherit;
}
.seg-trash:hover {
  background: var(--surface-2);
}

/* Actions */
.seg-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.btn-seg-confirm {
  padding: var(--space-15) var(--space-4);
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
}
.btn-seg-confirm:disabled {
  opacity: 0.5;
  cursor: default;
}
.seg-hint {
  font-size: var(--fs-xs);
  color: var(--ink-3);
  font-style: italic;
}
.seg-error {
  font-size: var(--fs-sm);
  color: var(--neg-ink);
}
</style>

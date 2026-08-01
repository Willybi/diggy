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

    <!-- Resulting segments: each can be kept or marked as an artefact to drop.
         A kept segment carries its live Deezer signal (display only). -->
    <div class="seg-chips">
      <div v-for="(seg, i) in segments" :key="i" class="seg-chip" :class="{ deleted: !seg.kept }">
        <span class="seg-chip-text">{{ seg.text }}</span>
        <span v-if="seg.kept && seg.deezer" class="seg-deezer">
          <span
            v-if="seg.deezer.status === 'searching'"
            class="seg-dz-spin"
            title="Recherche Deezer…"
          ></span>
          <span
            v-else-if="seg.deezer.status === 'found'"
            class="seg-dz-found"
            :title="`Match exact Deezer : ${seg.deezer.hit.name}`"
          >
            ✓ {{ seg.deezer.hit.name }} · {{ seg.deezer.hit.nb_fan?.toLocaleString() }} fans
          </span>
          <span v-else class="seg-dz-missing" title="Aucun match exact sur Deezer">✗</span>
        </span>
        <button
          class="seg-trash"
          :title="seg.kept ? 'Marquer comme à supprimer' : 'Rétablir'"
          @click="toggleSegment(seg)"
        >
          {{ seg.kept ? '🗑' : '↩' }}
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
import { ref, computed, watch, onUnmounted } from 'vue'
import api from '../../utils/api.js'
import {
  initSplitState,
  computeSegments,
  keptTokens,
  foldArtistName,
} from '../../utils/artistSplit.js'

const props = defineProps({
  // Full original artist string — drives the backend relink/cleanup, must reach
  // the API verbatim; here it seeds the units and is shown as context.
  raw: { type: String, required: true },
  pending: { type: Boolean, default: false },
  error: { type: String, default: '' },
  confirmLabel: { type: String, default: 'Confirmer le split' },
})

const emit = defineEmits(['confirm', 'cancel'])

const units = ref([])
const cuts = ref([])
const keep = ref([])

function reset() {
  const state = initSplitState(props.raw)
  units.value = state.units
  cuts.value = state.cuts
  keep.value = state.keep
}

watch(() => props.raw, reset, { immediate: true })

const baseSegments = computed(() => computeSegments(units.value, cuts.value, keep.value))

const outputTokens = computed(() => keptTokens(units.value, cuts.value, keep.value))

// ── Live Deezer signal (display only) ────────────────────────────────────────
// Every KEPT segment is searched on Deezer and shows ✓ (exact fold-match) or ✗
// so the admin cuts with eyes open. No linking happens here and the emitted
// tokens are untouched. Results are cached by segment text: a given text is
// searched at most ONCE and a deleted segment never enters the queue — the
// admin endpoint hits Deezer directly, unthrottled, hence the debounce too.
const DEEZER_DEBOUNCE_MS = 400

const deezerByText = ref({})
const deezerQueue = new Set()
let deezerTimer = null

const keptTexts = computed(() => baseSegments.value.filter((s) => s.kept).map((s) => s.text))

watch(
  keptTexts,
  (texts) => {
    let queued = false
    for (const text of texts) {
      if (deezerByText.value[text]) continue
      deezerByText.value[text] = { status: 'searching', hit: null }
      deezerQueue.add(text)
      queued = true
    }
    if (!queued) return
    clearTimeout(deezerTimer)
    deezerTimer = setTimeout(flushDeezerQueue, DEEZER_DEBOUNCE_MS)
  },
  { immediate: true },
)

function flushDeezerQueue() {
  // A segment deleted (or merged away) during the debounce window is never
  // searched: drop its entry so it re-queues if it ever comes back.
  const stillKept = new Set(keptTexts.value)
  const texts = [...deezerQueue]
  deezerQueue.clear()
  for (const text of texts) {
    if (stillKept.has(text)) {
      searchDeezer(text)
    } else {
      delete deezerByText.value[text]
    }
  }
}

// "Found" = a hit whose name equals the segment case- and accent-insensitively
// (foldArtistName) — Deezer returns fuzzy hits for anything, so a non-empty
// hit list alone proves nothing.
async function searchDeezer(text) {
  try {
    const { data } = await api.get('/api/admin/artists/search-deezer', { params: { q: text } })
    const hit = (data || []).find((h) => foldArtistName(h.name) === foldArtistName(text)) || null
    deezerByText.value[text] = { status: hit ? 'found' : 'missing', hit }
  } catch {
    // 429 / network errors are toasted by the api interceptor; drop the entry
    // so a later segment change retries instead of freezing a stale signal.
    delete deezerByText.value[text]
  }
}

onUnmounted(() => clearTimeout(deezerTimer))

// Segments as displayed: the pure split + each kept segment's Deezer signal.
const segments = computed(() =>
  baseSegments.value.map((seg) => ({
    ...seg,
    deezer: seg.kept ? deezerByText.value[seg.text] || null : null,
  })),
)

function toggleCut(i) {
  cuts.value[i] = !cuts.value[i]
}

function toggleSegment(seg) {
  const next = !seg.kept
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

/* Live Deezer signal */
.seg-deezer {
  display: inline-flex;
  align-items: center;
  gap: var(--space-05);
  font: 400 var(--fs-xs)/1 var(--font-ui);
  white-space: nowrap;
}
.seg-dz-spin {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid var(--line-2);
  border-top-color: var(--accent);
  animation: spin 0.7s linear infinite;
}
@media (prefers-reduced-motion: reduce) {
  .seg-dz-spin {
    animation: none;
  }
}
.seg-dz-found {
  color: var(--pos-ink);
}
.seg-dz-missing {
  color: var(--neg-ink);
  font-weight: 700;
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

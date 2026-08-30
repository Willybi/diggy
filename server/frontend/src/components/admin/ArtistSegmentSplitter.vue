<template>
  <div class="seg-splitter">
    <div class="seg-top">
      <span class="seg-eyebrow">Découper la chaîne</span>
      <span class="seg-count">{{ outputTokens.length }} segment{{ plural }}</span>
    </div>

    <!-- Bandeau de la chaîne : unités mono + boutons de coupe (barre verticale,
         D13). Toggler une coupe scinde/fusionne les deux morceaux adjacents. -->
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
          <span class="seg-bar"></span>
        </button>
      </template>
    </div>

    <!-- Resulting segments: each can be kept or marked as an artefact to drop.
         A kept segment carries its live Deezer signal (display only). -->
    <div class="seg-chips">
      <div v-for="(seg, i) in segments" :key="i" class="seg-chip" :class="{ deleted: !seg.kept }">
        <span class="seg-chip-text">{{ seg.text }}</span>
        <span v-if="seg.kept && seg.deezer" class="seg-deezer">
          <AdminIcon
            v-if="seg.deezer.status === 'searching'"
            name="arc"
            class="seg-dz-spin"
            :size="12"
          />
          <span
            v-else-if="seg.deezer.status === 'found'"
            class="seg-dz-found"
            :title="`Match exact Deezer : ${seg.deezer.hit.name}`"
          >
            <AdminIcon name="check" :size="12" />
            <span class="seg-dz-text">
              {{ seg.deezer.hit.name }} · {{ seg.deezer.hit.nb_fan?.toLocaleString('fr-FR') }} fans
            </span>
          </span>
          <span v-else class="seg-dz-missing" title="Aucun match exact sur Deezer">
            <AdminIcon name="x" :size="12" />
            <span class="seg-dz-text">0</span>
          </span>
        </span>
        <button
          class="seg-trash"
          :title="seg.kept ? 'Marquer comme à supprimer' : 'Rétablir'"
          @click="toggleSegment(seg)"
        >
          <AdminIcon :name="seg.kept ? 'trash' : 'skip'" :size="14" />
        </button>
      </div>
    </div>

    <div class="seg-actions">
      <span v-if="outputTokens.length === 0" class="seg-hint">Gardez au moins un segment.</span>
      <span v-if="error" class="seg-error">{{ error }}</span>
      <button class="btn btn--sm btn-seg-ghost" @click="emit('cancel')">Annuler</button>
      <button
        class="btn btn--sm btn--accent btn-seg-confirm"
        :disabled="pending || outputTokens.length === 0"
        @click="confirm"
      >
        {{ pending ? 'Découpe…' : confirmLabel }}
      </button>
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
import AdminIcon from './AdminIcon.vue'

const props = defineProps({
  // Full original artist string — drives the backend relink/cleanup, must reach
  // the API verbatim; here it seeds the units and is shown as context.
  raw: { type: String, required: true },
  pending: { type: Boolean, default: false },
  error: { type: String, default: '' },
  confirmLabel: { type: String, default: 'Confirmer la découpe' },
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

const plural = computed(() => (outputTokens.value.length > 1 ? 's' : ''))

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
/* Archétype E (D13) : le splitter est embarqué dans une surface --surface-2
   (editor-row des Flags / split-panel des Artistes) — il reste sans fond propre
   et laisse le bandeau de la chaîne porter le contraste. */
.seg-splitter {
  container-type: inline-size;
}
.seg-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}
.seg-eyebrow {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.seg-count {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}

/* Bandeau de la chaîne : unités mono + coupes (barre verticale). */
.seg-units {
  display: flex;
  align-items: center;
  gap: 0;
  flex-wrap: wrap;
  padding: var(--space-1) var(--space-2);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  margin-bottom: var(--space-3);
}
.seg-unit {
  font: 500 var(--fs-base)/1 var(--font-mono);
  color: var(--ink);
  padding: var(--space-1) 0;
}
/* Bouton de coupe : cible tactile 22×44, rendu = barre verticale dont la LARGEUR
   dit l'état (repos 5 px --line-2 · hover 14 px --ink-3 · actif 22 px --ink-2). */
.seg-cut {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 44px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
}
.seg-bar {
  width: 5px;
  height: 22px;
  border-radius: var(--r-pill);
  background: var(--line-2);
  transition:
    width 0.12s,
    background 0.12s;
}
.seg-cut:hover .seg-bar {
  width: 14px;
  background: var(--ink-3);
}
.seg-cut.active .seg-bar {
  width: 22px;
  background: var(--ink-2);
}

/* Chips de segments (38 px, --surface-2 + 1px --line). */
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
  gap: var(--space-15);
  min-height: 38px;
  padding: 0 var(--space-1) 0 var(--space-25);
  background: var(--surface-2);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
/* Segment supprimé : estompé mais rétablissable (le geste est exploratoire). */
.seg-chip.deleted {
  opacity: 0.45;
}
.seg-chip-text {
  font: 500 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
}

/* Signal Deezer par segment — 3 états (arc accent · check + fans --pos · skip + 0 --ink-3). */
.seg-deezer {
  display: inline-flex;
  align-items: center;
  gap: var(--space-05);
  white-space: nowrap;
}
.seg-dz-spin {
  color: var(--accent-ink);
}
.seg-dz-found {
  display: inline-flex;
  align-items: center;
  gap: var(--space-05);
  color: var(--pos-ink);
}
.seg-dz-missing {
  display: inline-flex;
  align-items: center;
  gap: var(--space-05);
  color: var(--ink-3);
}
.seg-dz-text {
  font: 500 var(--fs-xs)/1 var(--font-mono);
}

.seg-trash {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: var(--r-xs);
  color: var(--ink-3);
  transition:
    background 0.12s,
    color 0.12s;
}
.seg-trash:hover {
  background: var(--surface-3);
  color: var(--ink-2);
}

/* Actions : fer à droite (hint/erreur poussés à gauche). */
.seg-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.seg-hint {
  margin-right: auto;
  font-size: var(--fs-xs);
  color: var(--ink-3);
}
.seg-error {
  font-size: var(--fs-sm);
  color: var(--neg-ink);
}
.btn:disabled {
  opacity: 0.5;
  cursor: default;
}

@container (max-width: 859px) {
  .seg-cut {
    width: var(--touch-min);
    height: var(--touch-min);
  }
  .seg-trash {
    width: var(--touch-min);
    height: var(--touch-min);
  }
  .seg-actions {
    flex-direction: column-reverse;
    align-items: stretch;
  }
  .seg-actions .btn {
    width: 100%;
    min-height: var(--touch-min);
  }
  .seg-hint,
  .seg-error {
    margin-right: 0;
  }
}
</style>

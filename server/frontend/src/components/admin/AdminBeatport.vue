<template>
  <!-- Archétype A (D4/D18) : panneau de job Beatport, aligné sur AdminArtists. -->
  <section class="aj-region">
    <div class="aj-row">
      <div class="aj-body">
        <h2 class="aj-job-title">Enrichissement Beatport</h2>
        <p class="aj-job-desc">
          Enrichit le catalogue via Beatport : BPM, key (Camelot), label, genre, artwork. ISRC
          d'abord, fallback titre+artiste.
        </p>

        <!-- Job en cours (A7) : arc en rotation, mono --accent-ink. -->
        <p v-if="enrichingBeatport" class="aj-running">
          <AdminIcon name="arc" :size="13" /> Job en cours…
        </p>
        <!-- Cas already_running : pill neutre + arc, pas de ligne de résultat. -->
        <span v-else-if="beatportSkipped" class="aj-skip">
          <AdminIcon name="arc" :size="13" /> Déjà en cours
        </span>
        <!-- Ligne de résultat (D3) : paires icône + nombre mono + label. -->
        <div v-else-if="resultPairs.length || beatportError" class="aj-result">
          <span
            v-for="(p, i) in resultPairs"
            :key="i"
            class="aj-pair"
            :class="`aj-pair--${p.channel}`"
          >
            <AdminIcon :name="channelIcon(p.channel)" :size="13" />
            <span class="aj-num">{{ fmtInt(p.value) }}</span>
            <span class="aj-lbl">{{ p.label }}</span>
          </span>
          <span v-if="beatportError" class="aj-fail">
            <AdminIcon name="alert-triangle" :size="13" />
            <span class="aj-fail-word">Échec</span>
            <span class="aj-fail-msg">{{ beatportError }}</span>
          </span>
        </div>
      </div>
      <div class="aj-action">
        <label class="aj-field">
          <span class="aj-field-label">Batch size</span>
          <input
            v-model.number="beatportBatchSize"
            type="number"
            min="0"
            step="50"
            placeholder="0 = tout"
            class="aj-input"
          />
        </label>
        <button
          class="btn btn--sm btn--accent"
          :disabled="enrichingBeatport"
          @click="runEnrichBeatport"
        >
          {{ enrichingBeatport ? 'En cours…' : 'Enrich Beatport' }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed } from 'vue'
import api from '../../utils/api.js'
import { useTaskPoll } from '../../composables/useTaskPoll.js'
import AdminIcon from './AdminIcon.vue'

const enrichingBeatport = ref(false)
const beatportBatchSize = ref(0)
const beatportResult = ref(null)
const beatportSkipped = ref(false)
const beatportError = ref('')

// ── Ligne de résultat de job (D3) : paires icône/nombre/label, 3 canaux ──
// success (check, --pos-ink) · neutral (skip, --ink-2) · error (alert-triangle,
// --neg-ink). Les compteurs à 0 (ou absents) sont MASQUÉS (comptZero, défaut).
const CHANNEL_ICON = { success: 'check', neutral: 'skip', error: 'alert-triangle' }
function channelIcon(ch) {
  return CHANNEL_ICON[ch]
}
function fmtInt(n) {
  return Number(n).toLocaleString('fr-FR')
}

const resultPairs = computed(() => {
  const r = beatportResult.value
  if (!r) return []
  return [
    { value: r.enriched, label: 'enrichis', channel: 'success' },
    { value: r.not_found, label: 'non trouvés', channel: 'neutral' },
    { value: r.errors, label: 'erreurs', channel: 'error' },
    { value: r.total, label: 'traités', channel: 'neutral' },
  ].filter((d) => d.value != null && d.value !== 0)
})

const beatportPoll = useTaskPoll((taskId) => `/api/admin/tasks/${taskId}`, {
  intervalMs: 5000,
  maxAttempts: 300,
  onData(st, { stop }) {
    if (st.status === 'done') {
      const result = st.result || {}
      // A sweep already holds the lock → the task returns {skipped:'already_running'}
      // (no result counters). Surface a clear message instead of blank fields.
      if (result.skipped || result.total == null) {
        beatportSkipped.value = true
      } else {
        beatportResult.value = result
      }
      enrichingBeatport.value = false
      stop()
    } else if (st.status === 'error') {
      beatportError.value = st.error || 'Erreur'
      enrichingBeatport.value = false
      stop()
    }
  },
  onError(err) {
    beatportError.value = 'Erreur polling: ' + (err.message || 'inconnue')
    enrichingBeatport.value = false
  },
  onMaxAttempts() {
    beatportError.value = 'Timeout'
    enrichingBeatport.value = false
  },
})

async function runEnrichBeatport() {
  enrichingBeatport.value = true
  beatportResult.value = null
  beatportSkipped.value = false
  beatportError.value = ''
  try {
    const params = beatportBatchSize.value > 0 ? `?batch_size=${beatportBatchSize.value}` : ''
    const { data } = await api.post(`/api/admin/enrich-beatport${params}`)
    beatportPoll.start(data.task_id)
  } catch (e) {
    beatportError.value = e.response?.data?.detail || 'Erreur'
    enrichingBeatport.value = false
  }
}
</script>

<style scoped>
/* ── Archétype A — région de job (D4) : carte à bordure, sans ombre. ── */
.aj-region {
  container-type: inline-size;
  margin-bottom: var(--space-8);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
}
.aj-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-5);
  padding: var(--space-4);
}
.aj-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.aj-job-title {
  font: 600 var(--fs-title)/1.2 var(--font-ui);
  color: var(--ink);
}
.aj-job-desc {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-2);
  text-wrap: pretty;
  max-width: 76ch;
}
/* Champ + bouton, colonne d'action à droite (calqué sur AdminGenres § reclassify). */
.aj-action {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 190px;
}

/* Champ optionnel : label eyebrow mono AU-DESSUS de l'input mono --fs-input. */
.aj-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.aj-field-label {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.aj-input {
  width: 100%;
  height: 38px;
  padding: 0 var(--space-2);
  background: var(--surface-2);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink);
  font: 400 var(--fs-input)/1 var(--font-mono);
}
.aj-input:focus {
  outline: 2px solid var(--accent);
  outline-offset: -1px;
}

/* Job en cours (A7) : arc en rotation, mono --accent-ink — seul mouvement. */
.aj-running {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  margin-top: var(--space-2);
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--accent-ink);
}

/* Cas already_running : pill neutre --surface-2 / --ink-3 + arc. */
.aj-skip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  margin-top: var(--space-2);
  align-self: flex-start;
  padding: var(--space-1) var(--space-25);
  border-radius: var(--r-pill);
  background: var(--surface-2);
  color: var(--ink-3);
  font: 400 var(--fs-xs)/1 var(--font-mono);
}

/* Ligne de résultat (D3) : paires icône + nombre mono + label. */
.aj-result {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-2);
}
.aj-pair {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}
.aj-pair--success {
  color: var(--pos-ink);
}
.aj-pair--neutral {
  color: var(--ink-2);
}
.aj-pair--error {
  color: var(--neg-ink);
}
.aj-num {
  font: 600 var(--fs-xs)/1 var(--font-mono);
}
.aj-lbl {
  font: 400 var(--fs-xs)/1 var(--font-ui);
  color: var(--ink-3);
}
.aj-fail {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--neg-ink);
}
.aj-fail-word {
  font: 600 var(--fs-xs)/1 var(--font-ui);
}
.aj-fail-msg {
  font: 400 var(--fs-xs)/1.3 var(--font-mono);
  color: var(--ink-2);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  max-width: 340px;
}

.btn:disabled {
  opacity: 0.5;
  cursor: default;
}

/* ── Responsive — palier unique 859 px (D18) : rangée en pile, cibles 44 px. ── */
@container (max-width: 859px) {
  .aj-row {
    flex-direction: column;
    gap: var(--space-3);
  }
  .aj-action {
    width: 100%;
    min-width: 0;
  }
  .aj-action .btn {
    width: 100%;
    min-height: var(--touch-min);
    justify-content: center;
  }
  .aj-input {
    height: var(--touch-min);
  }
  .aj-fail-msg {
    max-width: none;
  }
}
</style>

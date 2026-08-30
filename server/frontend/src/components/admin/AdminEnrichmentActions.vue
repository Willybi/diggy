<template>
  <!-- Archétype A (D4/D18) : deux jobs d'enrichissement groupés dans UNE région. -->
  <section class="aj-region">
    <div class="aj-head">
      <h2 class="aj-title">Actions d'enrichissement <span class="aj-count">2</span></h2>
    </div>

    <!-- Action réversible : backfill multi-artistes -->
    <div class="aj-row">
      <div class="aj-body">
        <h3 class="aj-job-title">Backfill multi-artistes</h3>
        <p class="aj-job-desc">
          Re-interroge Deezer pour les titres à un seul artiste afin de découvrir les contributeurs
          manquants. Sans effet destructif.
        </p>
        <p v-if="backfilling" class="aj-running">
          <AdminIcon name="arc" :size="13" /> Job en cours…
        </p>
        <span v-else-if="backfillSkipped" class="aj-skip">
          <AdminIcon name="arc" :size="13" /> Déjà en cours
        </span>
        <div v-else-if="backfillPairs.length || backfillError" class="aj-result">
          <span
            v-for="(p, i) in backfillPairs"
            :key="i"
            class="aj-pair"
            :class="`aj-pair--${p.channel}`"
          >
            <AdminIcon :name="channelIcon(p.channel)" :size="13" />
            <span class="aj-num">{{ fmtInt(p.value) }}</span>
            <span class="aj-lbl">{{ p.label }}</span>
          </span>
          <span v-if="backfillError" class="aj-fail">
            <AdminIcon name="alert-triangle" :size="13" />
            <span class="aj-fail-word">Échec</span>
            <span class="aj-fail-msg">{{ backfillError }}</span>
          </span>
        </div>
      </div>
      <div class="aj-action">
        <button class="btn btn--sm btn--accent" :disabled="backfilling" @click="runBackfill">
          {{ backfilling ? 'En cours…' : 'Lancer le backfill' }}
        </button>
      </div>
    </div>

    <!-- Action destructive : reset Beatport — variante danger (D6). -->
    <div class="aj-row aj-row--danger">
      <div class="aj-body">
        <div class="aj-danger-head">
          <h3 class="aj-job-title">Réinitialiser l'enrichissement Beatport</h3>
          <span class="aj-badge-danger">Destructif</span>
        </div>
        <p class="aj-job-desc">
          Efface TOUTES les données issues de Beatport (ids, BPM/key sourcés Beatport) pour relancer
          l'enrichissement à zéro. Action destructive et irréversible.
        </p>

        <!-- Confirmation inline (D6) : dépliée sous la rangée, pas de modal. -->
        <div v-if="confirmingReset" class="aj-confirm">
          <span class="aj-confirm-mark">
            <AdminIcon name="alert-triangle" :size="15" />
          </span>
          <div class="aj-confirm-body">
            <p class="aj-confirm-q">
              Effacer l'enrichissement Beatport de tout le catalogue&nbsp;?
            </p>
            <p class="aj-confirm-consequence">
              <span class="aj-mono">Toutes</span> les données Beatport (ids, BPM et keys sourcés
              Beatport) sont effacées et reviennent à leur valeur d'origine. Aucune sauvegarde,
              aucun retour arrière.
            </p>
            <div class="aj-confirm-actions">
              <button class="btn btn--sm" :disabled="resetting" @click="cancelReset">
                Annuler
              </button>
              <button class="btn btn--sm btn--danger" :disabled="resetting" @click="doReset">
                {{ resetting ? 'Réinitialisation…' : 'Confirmer la réinitialisation' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Ligne de résultat NEUTRE (D6) : pas de rouge, le job a réussi. -->
        <div v-if="resetPairs.length || resetError" class="aj-result">
          <span v-for="(p, i) in resetPairs" :key="i" class="aj-pair aj-pair--neutral">
            <AdminIcon name="skip" :size="13" />
            <span class="aj-num">{{ fmtInt(p.value) }}</span>
            <span class="aj-lbl">{{ p.label }}</span>
          </span>
          <span v-if="resetError" class="aj-fail">
            <AdminIcon name="alert-triangle" :size="13" />
            <span class="aj-fail-word">Échec</span>
            <span class="aj-fail-msg">{{ resetError }}</span>
          </span>
        </div>
      </div>
      <div class="aj-action">
        <button
          v-if="!confirmingReset"
          class="btn btn--sm btn--danger"
          :disabled="resetting"
          @click="askReset"
        >
          Réinitialiser Beatport…
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

// ── Ligne de résultat de job (D3) : paires icône/nombre/label, 3 canaux ──
const CHANNEL_ICON = { success: 'check', neutral: 'skip', error: 'alert-triangle' }
function channelIcon(ch) {
  return CHANNEL_ICON[ch]
}
function fmtInt(n) {
  return Number(n).toLocaleString('fr-FR')
}

// ── Backfill multi-artistes (job) ──
const backfilling = ref(false)
const backfillResult = ref(null)
const backfillSkipped = ref(false)
const backfillError = ref('')

const backfillPairs = computed(() => {
  const r = backfillResult.value
  if (!r) return []
  return [
    { value: r.enriched, label: 'enrichis', channel: 'success' },
    { value: r.errors, label: 'erreurs', channel: 'error' },
    { value: r.total, label: 'traités', channel: 'neutral' },
  ].filter((d) => d.value != null && d.value !== 0)
})

const backfillPoll = useTaskPoll((taskId) => `/api/admin/tasks/${taskId}`, {
  intervalMs: 5000,
  maxAttempts: 300,
  onData(st, { stop }) {
    if (st.status === 'done') {
      const result = st.result || {}
      if (result.skipped || result.total == null) {
        backfillSkipped.value = true
      } else {
        backfillResult.value = result
      }
      backfilling.value = false
      stop()
    } else if (st.status === 'error') {
      backfillError.value = st.error || 'Erreur'
      backfilling.value = false
      stop()
    }
  },
  onError(err) {
    backfillError.value = 'Erreur polling: ' + (err.message || 'inconnue')
    backfilling.value = false
  },
  onMaxAttempts() {
    backfillError.value = 'Timeout'
    backfilling.value = false
  },
})

async function runBackfill() {
  backfilling.value = true
  backfillResult.value = null
  backfillSkipped.value = false
  backfillError.value = ''
  try {
    const { data } = await api.post('/api/admin/artists/backfill-multi-artists')
    backfillPoll.start(data.task_id)
  } catch (e) {
    backfillError.value = e.response?.data?.detail || 'Erreur'
    backfilling.value = false
  }
}

// ── Reset Beatport (destructif, confirmation inline) ──
const confirmingReset = ref(false)
const resetting = ref(false)
const resetResult = ref(null)
const resetError = ref('')

const resetPairs = computed(() => {
  const r = resetResult.value
  if (!r) return []
  // Canal NEUTRE uniquement (D6) : le reset a réussi, rien d'alarmant à peindre.
  return [
    { value: r.cleared, label: 'réinitialisés' },
    { value: r.bpm_reverted, label: 'BPM rétablis' },
    { value: r.key_reverted, label: 'key rétablies' },
  ].filter((d) => d.value != null && d.value !== 0)
})

function askReset() {
  confirmingReset.value = true
}

function cancelReset() {
  confirmingReset.value = false
}

async function doReset() {
  resetting.value = true
  resetResult.value = null
  resetError.value = ''
  try {
    const { data } = await api.post('/api/admin/reset-beatport')
    resetResult.value = data
    confirmingReset.value = false
  } catch (e) {
    resetError.value = e.response?.data?.detail || 'Erreur'
  } finally {
    resetting.value = false
  }
}
</script>

<style scoped>
/* ── Archétype A — région de jobs groupés (D4) : carte à bordure, sans ombre. ── */
.aj-region {
  container-type: inline-size;
  margin-bottom: var(--space-8);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
}
.aj-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--line);
}
.aj-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font: 600 var(--fs-title)/1.2 var(--font-ui);
  color: var(--ink);
}
.aj-count {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--r-pill);
  background: var(--surface-3);
  color: var(--ink-2);
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.04em;
}
.aj-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-5);
  padding: var(--space-4);
}
.aj-row + .aj-row {
  border-top: 1px solid var(--line);
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
.aj-action {
  flex: none;
}

/* Variante danger (D6) : en-tête avec badge Destructif. */
.aj-danger-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.aj-badge-danger {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--r-pill);
  background: var(--neg-soft);
  color: var(--neg-ink);
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.06em;
  text-transform: uppercase;
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

/* Confirmation inline danger (D6) : --neg cantonné (filet, pastille, bouton). */
.aj-confirm {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  margin-top: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--surface-2);
  border: 1px solid var(--neg);
  border-radius: var(--r-sm);
}
.aj-confirm-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  flex: none;
  border-radius: var(--r-pill);
  background: var(--neg-soft);
  color: var(--neg-ink);
}
.aj-confirm-body {
  flex: 1;
  min-width: 0;
}
.aj-confirm-q {
  font: 600 var(--fs-base)/1.3 var(--font-ui);
  color: var(--ink);
}
.aj-confirm-consequence {
  margin-top: var(--space-1);
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-2);
  text-wrap: pretty;
}
.aj-mono {
  font-family: var(--font-mono);
  color: var(--ink);
}
.aj-confirm-actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-top: var(--space-25);
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

/* buttons.css ne colore `.btn--danger` qu'au :hover → au repos le déclencheur ET
   le bouton de confirmation ressemblent à un `.btn` neutre, le signal destructif
   se perd. On donne aux boutons danger de CE composant un état de repos de
   CONTOUR (texte + bordure --neg), sans toucher buttons.css. */
.aj-row--danger .btn--danger {
  color: var(--neg-ink);
  border-color: var(--neg);
}

/* ── Responsive — palier unique 859 px (D18) : rangée en pile, cibles 44 px. ── */
@container (max-width: 859px) {
  .aj-head {
    flex-direction: column;
    align-items: flex-start;
  }
  .aj-row {
    flex-direction: column;
    gap: var(--space-3);
  }
  .aj-action {
    width: 100%;
  }
  .aj-action .btn {
    width: 100%;
    min-height: var(--touch-min);
    justify-content: center;
  }
  .aj-confirm-actions {
    width: 100%;
  }
  .aj-confirm-actions .btn {
    flex: 1;
    min-height: var(--touch-min);
    justify-content: center;
  }
  .aj-fail-msg {
    max-width: none;
  }
}
</style>

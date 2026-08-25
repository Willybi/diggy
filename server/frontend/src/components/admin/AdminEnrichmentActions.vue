<template>
  <section class="admin-section">
    <h2 class="section-title">Actions d'enrichissement</h2>

    <!-- Action réversible : backfill multi-artistes -->
    <div class="action-block">
      <h3 class="action-title">Backfill multi-artistes</h3>
      <p class="section-sub">
        Re-interroge Deezer pour les titres à un seul artiste afin de découvrir les contributeurs
        manquants. Sans effet destructif.
      </p>
      <div class="sync-row">
        <button class="btn-sync" :disabled="backfilling" @click="runBackfill">
          {{ backfilling ? 'Backfill en cours…' : 'Lancer le backfill' }}
        </button>
        <div v-if="backfillResult" class="sync-result">
          <span class="result-item ok">✓ {{ backfillResult.enriched ?? 0 }} enrichis</span>
          <span v-if="backfillResult.errors" class="result-item warn"
            >⚠ {{ backfillResult.errors }} erreurs</span
          >
          <span v-if="backfillResult.total != null" class="result-item muted"
            >/ {{ backfillResult.total }} traités</span
          >
        </div>
        <span v-if="backfillSkipped" class="sync-info">Backfill déjà en cours</span>
        <span v-if="backfillError" class="sync-error">{{ backfillError }}</span>
      </div>
    </div>

    <!-- Action destructive : reset Beatport (garde-fou de confirmation inline) -->
    <div class="action-block action-block--danger">
      <h3 class="action-title">Réinitialiser l'enrichissement Beatport</h3>
      <p class="section-sub">
        Efface TOUTES les données issues de Beatport (ids, BPM/key sourcés Beatport) pour relancer
        l'enrichissement à zéro. Action destructive et irréversible.
      </p>
      <div class="sync-row">
        <button
          v-if="!confirmingReset"
          class="btn-danger"
          :disabled="resetting"
          @click="confirmingReset = true"
        >
          Réinitialiser Beatport…
        </button>

        <div v-else class="confirm-zone">
          <p class="confirm-warning">
            ⚠ Réinitialise TOUT l'enrichissement Beatport de la base — irréversible.
          </p>
          <div class="confirm-actions">
            <button class="btn-danger" :disabled="resetting" @click="runReset">
              {{ resetting ? 'Réinitialisation…' : 'Confirmer la réinitialisation' }}
            </button>
            <button class="btn-cancel" :disabled="resetting" @click="confirmingReset = false">
              Annuler
            </button>
          </div>
        </div>

        <div v-if="resetResult" class="sync-result">
          <span class="result-item ok">✓ {{ resetResult.cleared }} réinitialisés</span>
          <span class="result-item muted">↩ {{ resetResult.bpm_reverted }} BPM</span>
          <span class="result-item muted">↩ {{ resetResult.key_reverted }} key</span>
        </div>
        <span v-if="resetError" class="sync-error">{{ resetError }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import api from '../../utils/api.js'
import { useTaskPoll } from '../../composables/useTaskPoll.js'

// ── Backfill multi-artistes (job) ──
const backfilling = ref(false)
const backfillResult = ref(null)
const backfillSkipped = ref(false)
const backfillError = ref('')

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

async function runReset() {
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
.admin-section {
  container-type: inline-size;
  margin-bottom: var(--space-8);
  padding: var(--space-5) var(--space-6);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
.section-title {
  font: 600 var(--fs-title)/1 var(--font-ui);
  color: var(--ink);
  margin-bottom: var(--space-4);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.action-block {
  padding: var(--space-4) 0;
}
.action-block + .action-block {
  border-top: 1px solid var(--line);
}
.action-block--danger {
  margin-top: var(--space-2);
}
.action-title {
  font: 600 var(--fs-base)/1 var(--font-ui);
  color: var(--ink);
  margin-bottom: var(--space-15);
}
.section-sub {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-3);
  margin-bottom: var(--space-4);
}
.sync-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex-wrap: wrap;
}
.btn-sync {
  padding: var(--space-2) var(--space-5);
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
  transition: opacity 0.12s;
}
.btn-sync:disabled {
  opacity: 0.5;
  cursor: default;
}
.btn-danger {
  padding: var(--space-2) var(--space-5);
  border-radius: var(--r-sm);
  border: 1px solid var(--neg);
  background: var(--neg-soft);
  color: var(--neg-ink);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
  transition: opacity 0.12s;
}
.btn-danger:disabled {
  opacity: 0.5;
  cursor: default;
}
.btn-cancel {
  padding: var(--space-2) var(--space-5);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
}
.btn-cancel:disabled {
  opacity: 0.5;
  cursor: default;
}
.confirm-zone {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--neg-soft);
  border: 1px solid var(--neg);
  border-radius: var(--r-sm);
}
.confirm-warning {
  font: 500 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--neg-ink);
  margin: 0;
}
.confirm-actions {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.sync-result {
  display: flex;
  gap: var(--space-4);
  font: 400 var(--fs-sm)/1 var(--font-mono);
}
.result-item.ok {
  color: var(--pos-ink);
}
.result-item.warn {
  color: var(--neg-ink);
}
.result-item.muted {
  color: var(--ink-3);
}
.sync-info {
  font: 400 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-3);
}
.sync-error {
  font-size: var(--fs-sm);
  color: var(--neg-ink);
}
</style>

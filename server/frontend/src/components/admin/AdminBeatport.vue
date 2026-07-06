<template>
  <section class="admin-section">
    <h2 class="section-title">Enrichissement Beatport</h2>
    <p class="section-sub">
      Enrichit le catalogue via Beatport : BPM, key (Camelot), label, genre, artwork. ISRC
      d'abord, fallback titre+artiste.
    </p>
    <div class="sync-row">
      <label class="batch-label">
        Batch size
        <input
          v-model.number="beatportBatchSize"
          type="number"
          min="0"
          step="50"
          placeholder="0 = tout"
          class="batch-input"
        />
      </label>
      <button class="btn-sync" :disabled="enrichingBeatport" @click="runEnrichBeatport">
        {{ enrichingBeatport ? 'Enrichissement en cours…' : 'Enrich Beatport' }}
      </button>
      <div v-if="beatportResult" class="sync-result">
        <span class="result-item ok">✓ {{ beatportResult.enriched }} enrichis</span>
        <span class="result-item muted">↷ {{ beatportResult.not_found }} non trouvés</span>
        <span v-if="beatportResult.errors" class="result-item warn"
          >⚠ {{ beatportResult.errors }} erreurs</span
        >
        <span class="result-item muted">/ {{ beatportResult.total }} traités</span>
      </div>
      <span v-if="beatportError" class="sync-error">{{ beatportError }}</span>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import api from '../../utils/api.js'

const enrichingBeatport = ref(false)
const beatportBatchSize = ref(0)
const beatportResult = ref(null)
const beatportError = ref('')

async function runEnrichBeatport() {
  enrichingBeatport.value = true
  beatportResult.value = null
  beatportError.value = ''
  try {
    const params = beatportBatchSize.value > 0 ? `?batch_size=${beatportBatchSize.value}` : ''
    const { data } = await api.post(`/api/admin/enrich-beatport${params}`)
    let attempts = 0
    const timer = setInterval(async () => {
      attempts++
      if (attempts > 300) {
        clearInterval(timer)
        beatportError.value = 'Timeout'
        enrichingBeatport.value = false
        return
      }
      try {
        const { data: st } = await api.get(`/api/admin/artists/sync/status/${data.task_id}`)
        if (st.status === 'done') {
          clearInterval(timer)
          beatportResult.value = st.result
          enrichingBeatport.value = false
        } else if (st.status === 'error') {
          clearInterval(timer)
          beatportError.value = st.error || 'Erreur'
          enrichingBeatport.value = false
        }
      } catch (err) {
        clearInterval(timer)
        beatportError.value = 'Erreur polling: ' + (err.message || 'inconnue')
        enrichingBeatport.value = false
      }
    }, 5000)
  } catch (e) {
    beatportError.value = e.response?.data?.detail || 'Erreur'
    enrichingBeatport.value = false
  }
}
</script>

<style scoped>
.admin-section {
  margin-bottom: 36px;
  padding: 20px 24px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
.section-title {
  font: 600 15px/1 var(--font-ui);
  color: var(--ink);
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-sub {
  font: 400 12px/1.4 var(--font-ui);
  color: var(--ink-3);
  margin-bottom: 14px;
}
.sync-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.btn-sync {
  padding: 9px 20px;
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
  transition: opacity 0.12s;
}
.btn-sync:disabled {
  opacity: 0.5;
  cursor: default;
}
.batch-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font: 400 13px/1 var(--font-ui);
  color: var(--ink-muted);
}
.batch-input {
  width: 80px;
  padding: 6px 8px;
  border-radius: var(--r-sm);
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--ink);
  font: 400 13px/1 var(--font-mono);
}
.sync-result {
  display: flex;
  gap: 14px;
  font: 400 13px/1 var(--font-mono);
}
.result-item.ok {
  color: var(--pos-ink);
}
.result-item.warn {
  color: var(--warn-ink);
}
.result-item.muted {
  color: var(--ink-3);
}
.sync-error {
  font-size: 13px;
  color: var(--neg-ink);
}
</style>

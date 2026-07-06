<template>
  <!-- Lier artistes aux sets -->
  <section class="admin-section">
    <h2 class="section-title">Artistes des sets</h2>
    <p class="section-sub">
      Parse les titres des sets pour trouver les artistes et les lier. Idempotent.
    </p>
    <div class="sync-row">
      <button class="btn-sync" :disabled="linkingSets" @click="runLinkSets">
        {{ linkingSets ? 'Liaison en cours…' : 'Lier artistes aux sets' }}
      </button>
      <div v-if="linkSetsResult" class="sync-result">
        <span class="result-item ok">✓ {{ linkSetsResult.linked }} liés</span>
        <span class="result-item muted">↷ {{ linkSetsResult.skipped }} déjà liés</span>
      </div>
      <span v-if="linkSetsError" class="sync-error">{{ linkSetsError }}</span>
    </div>
  </section>

  <!-- Enrich set tracks -->
  <section class="admin-section">
    <h2 class="section-title">Enrichir tracks des sets</h2>
    <p class="section-sub">
      Enrichit via Deezer + Beatport les tracks des sets sans infos. Ne touche pas aux tracks déjà
      enrichies.
    </p>
    <div class="sync-row">
      <button class="btn-sync" :disabled="enrichingSets" @click="runEnrichSets">
        {{ enrichingSets ? 'Enrichissement…' : 'Enrichir sets' }}
      </button>
      <div v-if="enrichSetsResult" class="sync-result">
        <span class="result-item ok">✓ {{ enrichSetsResult.enriched }} enrichis</span>
        <span class="result-item muted">/ {{ enrichSetsResult.total }} tracks</span>
      </div>
      <span v-if="enrichSetsError" class="sync-error">{{ enrichSetsError }}</span>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import api from '../../utils/api.js'

const linkingSets = ref(false)
const linkSetsResult = ref(null)
const linkSetsError = ref('')
const enrichingSets = ref(false)
const enrichSetsResult = ref(null)
const enrichSetsError = ref('')

async function runLinkSets() {
  linkingSets.value = true
  linkSetsResult.value = null
  linkSetsError.value = ''
  try {
    const { data } = await api.post('/api/admin/sets/link-artists')
    let attempts = 0
    const timer = setInterval(async () => {
      attempts++
      if (attempts > 150) {
        clearInterval(timer)
        linkSetsError.value = 'Timeout'
        linkingSets.value = false
        return
      }
      try {
        const { data: st } = await api.get(`/api/admin/artists/sync/status/${data.task_id}`)
        if (st.status === 'done') {
          clearInterval(timer)
          linkSetsResult.value = st.result
          linkingSets.value = false
        } else if (st.status === 'error') {
          clearInterval(timer)
          linkSetsError.value = st.error || 'Erreur'
          linkingSets.value = false
        }
      } catch (err) {
        clearInterval(timer)
        linkSetsError.value = 'Erreur polling: ' + (err.message || 'inconnue')
        linkingSets.value = false
      }
    }, 2000)
  } catch (e) {
    linkSetsError.value = e.response?.data?.detail || 'Erreur'
    linkingSets.value = false
  }
}

async function runEnrichSets() {
  enrichingSets.value = true
  enrichSetsResult.value = null
  enrichSetsError.value = ''
  try {
    const { data } = await api.post('/api/admin/sets/enrich-tracks')
    let attempts = 0
    const timer = setInterval(async () => {
      attempts++
      if (attempts > 300) {
        clearInterval(timer)
        enrichSetsError.value = 'Timeout'
        enrichingSets.value = false
        return
      }
      try {
        const { data: st } = await api.get(`/api/admin/artists/sync/status/${data.task_id}`)
        if (st.status === 'done') {
          clearInterval(timer)
          enrichSetsResult.value = st.result
          enrichingSets.value = false
        } else if (st.status === 'error') {
          clearInterval(timer)
          enrichSetsError.value = st.error || 'Erreur'
          enrichingSets.value = false
        }
      } catch (err) {
        clearInterval(timer)
        enrichSetsError.value = 'Erreur polling: ' + (err.message || 'inconnue')
        enrichingSets.value = false
      }
    }, 3000)
  } catch (e) {
    enrichSetsError.value = e.response?.data?.detail || 'Erreur'
    enrichingSets.value = false
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
.sync-result {
  display: flex;
  gap: 14px;
  font: 400 13px/1 var(--font-mono);
}
.result-item.ok {
  color: var(--pos-ink);
}
.result-item.muted {
  color: var(--ink-3);
}
.sync-error {
  font-size: 13px;
  color: var(--neg-ink);
}
</style>

<template>
  <!-- Flags en attente -->
  <section class="admin-section">
    <h2 class="section-title">
      Flags en attente
      <span v-if="flagsTotal > 0" class="flags-badge">{{ flagsTotal }}</span>
    </h2>
    <p class="section-sub">
      Candidats dupliqués ou parties identifiés par le service de déduplication.
    </p>
    <div v-if="flagsLoading" class="section-sub">Chargement…</div>
    <div v-else-if="flagsError" class="sync-error">{{ flagsError }}</div>
    <div v-else-if="flags.length === 0" class="section-sub">Aucun flag en attente.</div>
    <div v-else class="flags-list">
      <div v-for="flag in flags" :key="flag.id" class="flag-card">
        <div class="flag-sets">
          <template v-if="flag.member_set_ids">
            <div class="flag-members">
              <span
                v-for="(title, i) in flag.member_titles"
                :key="i"
                class="flag-set-title flag-member"
              >{{ title }}</span>
            </div>
          </template>
          <template v-else>
            <span class="flag-set-title">{{ flag.title_a }}</span>
            <span class="flag-sep">↔</span>
            <span class="flag-set-title">{{ flag.title_b }}</span>
          </template>
        </div>
        <div class="flag-meta">
          <span class="flag-type">{{ flagTypeLabel(flag.flag_type) }}</span>
          <span v-if="flag.confidence != null" class="flag-conf">
            Confiance : {{ Math.round(flag.confidence * 100) }}%
          </span>
          <span v-if="flag.signals?.part_numbers?.length" class="flag-conf">
            Parts : {{ flag.signals.part_numbers.join(', ') }}
          </span>
          <span v-if="flag.signals?.date_span_days > 0" class="flag-conf">
            Écart : {{ flag.signals.date_span_days }} j
          </span>
        </div>
        <div class="flag-actions">
          <button
            class="btn-sync"
            :disabled="flagLoadingIds.has(flag.id)"
            @click="attachFlag(flag)"
          >
            Attacher
          </button>
          <button
            class="btn-sync btn-reject"
            :disabled="flagLoadingIds.has(flag.id)"
            @click="rejectFlag(flag)"
          >
            Rejeter
          </button>
        </div>
      </div>
    </div>
  </section>

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
import { onMounted, ref } from 'vue'
import api from '../../utils/api.js'
import { useTaskPoll } from '../../composables/useTaskPoll.js'

// --- Flags ---
const flags = ref([])
const flagsTotal = ref(0)
const flagsLoading = ref(false)
const flagsError = ref('')
const flagLoadingIds = ref(new Set())

function flagTypeLabel(type) {
  if (type === 'duplicate_candidate') return 'Doublon'
  if (type === 'part_candidate') return 'Parties'
  return type
}

async function loadFlags() {
  flagsLoading.value = true
  flagsError.value = ''
  try {
    const { data } = await api.get('/api/admin/set-flags?status=pending&limit=50')
    flags.value = data.items
    flagsTotal.value = data.total
  } catch (e) {
    flagsError.value = e.response?.data?.detail || 'Erreur chargement flags'
  } finally {
    flagsLoading.value = false
  }
}

async function attachFlag(flag) {
  flagLoadingIds.value = new Set([...flagLoadingIds.value, flag.id])
  try {
    await api.post(`/api/admin/set-flags/${flag.id}/attach`)
    flags.value = flags.value.filter((f) => f.id !== flag.id)
    flagsTotal.value = Math.max(0, flagsTotal.value - 1)
  } catch (e) {
    flagsError.value = e.response?.data?.detail || 'Erreur attach'
  } finally {
    const next = new Set(flagLoadingIds.value)
    next.delete(flag.id)
    flagLoadingIds.value = next
  }
}

async function rejectFlag(flag) {
  flagLoadingIds.value = new Set([...flagLoadingIds.value, flag.id])
  try {
    await api.post(`/api/admin/set-flags/${flag.id}/reject`)
    flags.value = flags.value.filter((f) => f.id !== flag.id)
    flagsTotal.value = Math.max(0, flagsTotal.value - 1)
  } catch (e) {
    flagsError.value = e.response?.data?.detail || 'Erreur reject'
  } finally {
    const next = new Set(flagLoadingIds.value)
    next.delete(flag.id)
    flagLoadingIds.value = next
  }
}

onMounted(loadFlags)

const linkingSets = ref(false)
const linkSetsResult = ref(null)
const linkSetsError = ref('')
const enrichingSets = ref(false)
const enrichSetsResult = ref(null)
const enrichSetsError = ref('')

const linkSetsPoll = useTaskPoll((taskId) => `/api/admin/artists/sync/status/${taskId}`, {
  intervalMs: 2000,
  maxAttempts: 150,
  onData(st, { stop }) {
    if (st.status === 'done') {
      linkSetsResult.value = st.result
      linkingSets.value = false
      stop()
    } else if (st.status === 'error') {
      linkSetsError.value = st.error || 'Erreur'
      linkingSets.value = false
      stop()
    }
  },
  onError(err) {
    linkSetsError.value = 'Erreur polling: ' + (err.message || 'inconnue')
    linkingSets.value = false
  },
  onMaxAttempts() {
    linkSetsError.value = 'Timeout'
    linkingSets.value = false
  },
})

async function runLinkSets() {
  linkingSets.value = true
  linkSetsResult.value = null
  linkSetsError.value = ''
  try {
    const { data } = await api.post('/api/admin/sets/link-artists')
    linkSetsPoll.start(data.task_id)
  } catch (e) {
    linkSetsError.value = e.response?.data?.detail || 'Erreur'
    linkingSets.value = false
  }
}

const enrichSetsPoll = useTaskPoll((taskId) => `/api/admin/artists/sync/status/${taskId}`, {
  intervalMs: 3000,
  maxAttempts: 300,
  onData(st, { stop }) {
    if (st.status === 'done') {
      enrichSetsResult.value = st.result
      enrichingSets.value = false
      stop()
    } else if (st.status === 'error') {
      enrichSetsError.value = st.error || 'Erreur'
      enrichingSets.value = false
      stop()
    }
  },
  onError(err) {
    enrichSetsError.value = 'Erreur polling: ' + (err.message || 'inconnue')
    enrichingSets.value = false
  },
  onMaxAttempts() {
    enrichSetsError.value = 'Timeout'
    enrichingSets.value = false
  },
})

async function runEnrichSets() {
  enrichingSets.value = true
  enrichSetsResult.value = null
  enrichSetsError.value = ''
  try {
    const { data } = await api.post('/api/admin/sets/enrich-tracks')
    enrichSetsPoll.start(data.task_id)
  } catch (e) {
    enrichSetsError.value = e.response?.data?.detail || 'Erreur'
    enrichingSets.value = false
  }
}
</script>

<style scoped>
.admin-section {
  margin-bottom: var(--space-8);
  padding: var(--space-5) var(--space-6);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
.section-title {
  font: 600 var(--fs-title)/1 var(--font-ui);
  color: var(--ink);
  margin-bottom: var(--space-15);
  display: flex;
  align-items: center;
  gap: var(--space-2);
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
.sync-result {
  display: flex;
  gap: var(--space-4);
  font: 400 var(--fs-sm)/1 var(--font-mono);
}
.result-item.ok {
  color: var(--pos-ink);
}
.result-item.muted {
  color: var(--ink-3);
}
.sync-error {
  font-size: var(--fs-sm);
  color: var(--neg-ink);
}
.flags-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  padding: var(--space-05) var(--space-15);
  border-radius: 10px;
  background: var(--accent);
  color: var(--on-accent);
  font: 600 var(--fs-xs)/1 var(--font-ui);
}
.flags-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-25);
}
.flag-card {
  padding: var(--space-3) var(--space-4);
  background: var(--surface-2, var(--surface));
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.flag-sets {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.flag-set-title {
  font: 500 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink);
}
.flag-sep {
  font-size: var(--fs-base);
  color: var(--ink-3);
}
.flag-members {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-15);
}
.flag-member {
  padding: var(--space-05) var(--space-2);
  background: var(--surface-2, var(--surface));
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
.flag-meta {
  display: flex;
  gap: var(--space-3);
  font: 400 var(--fs-sm)/1 var(--font-ui);
}
.flag-type {
  color: var(--ink-3);
}
.flag-conf {
  color: var(--ink-2, var(--ink-3));
}
.flag-actions {
  display: flex;
  gap: var(--space-2);
}
.btn-reject {
  background: transparent;
  color: var(--neg-ink);
  border: 1px solid var(--neg-ink);
}
</style>

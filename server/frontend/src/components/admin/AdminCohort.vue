<template>
  <section class="cohort-wrap">
    <!-- Recalcul de la cohorte (job + poller) : dispatche la tâche Celery
         recompute_artist_cohort et suit son avancement via /admin/tasks/{id}. -->
    <div class="ch-toolbar">
      <div class="ch-toolbar-body">
        <h2 class="ch-toolbar-title">Recalcul de la cohorte</h2>
        <p class="ch-toolbar-desc">
          Recalcule les tiers depuis les signaux en base (lib, likes, sets, catalog). Les overrides
          admin (épinglé, exclu, tier forcé) ne sont jamais écrasés.
        </p>
        <p v-if="recomputing" class="ch-running">
          <AdminIcon name="arc" :size="13" /> Recalcul en cours…
        </p>
        <span v-else-if="recomputeSkipped" class="ch-skip">
          <AdminIcon name="arc" :size="13" /> Déjà en cours
        </span>
        <div v-else-if="recomputePairs.length || recomputeError" class="ch-result">
          <span v-for="(p, i) in recomputePairs" :key="i" class="ch-pair">
            <span class="ch-num">{{ fmtInt(p.value) }}</span>
            <span class="ch-lbl">{{ p.label }}</span>
          </span>
          <span v-if="recomputeError" class="ch-fail">
            <AdminIcon name="alert-triangle" :size="13" />
            <span class="ch-fail-word">Échec</span>
            <span class="ch-fail-msg">{{ recomputeError }}</span>
          </span>
        </div>
      </div>
      <div class="ch-toolbar-action">
        <button class="btn btn--sm btn--accent" :disabled="recomputing" @click="runRecompute">
          {{ recomputing ? 'En cours…' : 'Recalculer la cohorte' }}
        </button>
      </div>
    </div>

    <!-- Liste paginée des membres (socle .at-*). -->
    <div class="at-region">
      <div class="at-head">
        <h2 class="at-title">
          Membres
          <span v-if="total" class="at-count">{{ fmtInt(total) }}</span>
        </h2>
        <div class="ch-filters">
          <div class="at-seg" role="group" aria-label="Filtrer par tier">
            <button
              v-for="opt in TIER_FILTERS"
              :key="opt.label"
              class="at-seg-b"
              :class="{ active: tierFilter === opt.value }"
              @click="setTier(opt.value)"
            >
              {{ opt.label }}
            </button>
          </div>
          <div class="at-seg" role="group" aria-label="Filtrer par override">
            <button
              v-for="opt in OVERRIDE_FILTERS"
              :key="opt.label"
              class="at-seg-b"
              :class="{ active: overrideFilter === opt.value }"
              @click="setOverrideFilter(opt.value)"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="loading" class="at-empty">Chargement…</div>
      <div v-else-if="error" class="at-empty">Erreur de chargement de la cohorte.</div>
      <div v-else-if="items.length === 0" class="at-empty">Aucun artiste dans la cohorte.</div>

      <div v-else class="at-scroll">
        <table class="at-table">
          <thead>
            <tr>
              <th>Artiste</th>
              <th>Tier</th>
              <th>Signaux</th>
              <th>Dernier check</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in items" :key="item.artist_id">
              <td data-label="Artiste" data-lead>
                <router-link class="ch-name" :to="`/artist/${item.artist_id}`">
                  {{ item.name }}
                </router-link>
                <span class="ch-id">#{{ item.artist_id }}</span>
              </td>
              <td data-label="Tier">
                <div class="ch-badges">
                  <span class="at-pill at-pill--neutral">T{{ item.tier }}</span>
                  <span v-if="item.pinned" class="at-pill ch-pill-admin">Épinglé</span>
                  <span v-if="item.excluded" class="at-pill at-pill--err">Exclu</span>
                  <span v-if="item.forced_tier" class="at-pill ch-pill-admin">
                    Forcé T{{ item.forced_tier }}
                  </span>
                </div>
              </td>
              <td data-label="Signaux" data-stack>
                <div v-if="item.signals" class="at-chips">
                  <span class="at-chip">
                    <span class="at-chip-k">lib</span>
                    <span class="at-chip-v">{{ fmtInt(item.signals.nb_lib) }}</span>
                  </span>
                  <span class="at-chip">
                    <span class="at-chip-k">likes</span>
                    <span class="at-chip-v">{{ fmtInt(item.signals.nb_likes) }}</span>
                  </span>
                  <span class="at-chip">
                    <span class="at-chip-k">sets/12m</span>
                    <span class="at-chip-v">{{ fmtInt(item.signals.nb_sets_12m) }}</span>
                  </span>
                  <span class="at-chip">
                    <span class="at-chip-k">cat</span>
                    <span class="at-chip-v">{{ fmtInt(item.signals.nb_catalog) }}</span>
                  </span>
                </div>
                <span v-else class="ch-muted">—</span>
              </td>
              <td data-label="Dernier check">
                <span class="at-tech">{{ fmtDate(item.last_checked_at) }}</span>
              </td>
              <td data-act>
                <div class="ch-actions">
                  <button
                    class="btn btn--sm"
                    :disabled="mutating[item.artist_id]"
                    @click="togglePin(item)"
                  >
                    {{ item.pinned ? 'Désépingler' : 'Épingler' }}
                  </button>
                  <button
                    class="btn btn--sm"
                    :disabled="mutating[item.artist_id]"
                    @click="toggleExclude(item)"
                  >
                    {{ item.excluded ? 'Réintégrer' : 'Exclure' }}
                  </button>
                  <div class="ch-force at-seg" role="group" aria-label="Forcer un tier">
                    <button
                      class="at-seg-b"
                      :class="{ active: item.forced_tier == null }"
                      :disabled="mutating[item.artist_id]"
                      @click="unforceTier(item)"
                    >
                      Auto
                    </button>
                    <button
                      v-for="t in TIERS"
                      :key="t"
                      class="at-seg-b"
                      :class="{ active: item.forced_tier === t }"
                      :disabled="mutating[item.artist_id]"
                      @click="forceTier(item, t)"
                    >
                      T{{ t }}
                    </button>
                  </div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="totalPages > 1" class="at-pager">
        <button class="btn btn--sm" :disabled="page <= 1" @click="prevPage">Précédent</button>
        <span class="at-pager-count">{{ page }} / {{ totalPages }}</span>
        <button class="btn btn--sm" :disabled="page >= totalPages" @click="nextPage">
          Suivant
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '../../utils/api.js'
import { useTaskPoll } from '../../composables/useTaskPoll.js'
import AdminIcon from './AdminIcon.vue'

const PER_PAGE = 50
const TIERS = [1, 2, 3]

// Filtres alignés sur le contrat API (GET /admin/cohort ?tier= ?override=).
const TIER_FILTERS = [
  { label: 'Tous', value: null },
  { label: 'T1', value: 1 },
  { label: 'T2', value: 2 },
  { label: 'T3', value: 3 },
]
const OVERRIDE_FILTERS = [
  { label: 'Tous', value: null },
  { label: 'Épinglés', value: 'pinned' },
  { label: 'Exclus', value: 'excluded' },
]

const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const error = ref(false)
const tierFilter = ref(null)
const overrideFilter = ref(null)
// artist_id → true pendant qu'une mutation d'override est en vol (désactive la ligne).
const mutating = reactive({})

const totalPages = computed(() => Math.ceil(total.value / PER_PAGE))

function fmtInt(n) {
  return Number(n || 0).toLocaleString('fr-FR')
}

function fmtDate(iso) {
  if (!iso) return 'Jamais'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' })
}

async function fetchCohort() {
  loading.value = true
  error.value = false
  try {
    const params = { page: page.value, page_size: PER_PAGE }
    if (tierFilter.value != null) params.tier = tierFilter.value
    if (overrideFilter.value != null) params.override = overrideFilter.value
    const { data } = await api.get('/api/admin/cohort', { params })
    items.value = data.items
    total.value = data.total
  } catch {
    error.value = true
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function setTier(v) {
  if (tierFilter.value === v) return
  tierFilter.value = v
  page.value = 1
  fetchCohort()
}

function setOverrideFilter(v) {
  if (overrideFilter.value === v) return
  overrideFilter.value = v
  page.value = 1
  fetchCohort()
}

function prevPage() {
  if (page.value <= 1) return
  page.value--
  fetchCohort()
}

function nextPage() {
  if (page.value >= totalPages.value) return
  page.value++
  fetchCohort()
}

// PATCH un override (pin/exclude/forced_tier) et remplace la ligne EN PLACE avec
// l'item renvoyé (tier effectif recalculé côté back). Sémantique PATCH : un champ
// absent n'est pas modifié — on n'envoie donc que la clé mutée.
async function patchOverride(item, body) {
  if (mutating[item.artist_id]) return
  mutating[item.artist_id] = true
  try {
    const { data } = await api.patch(`/api/admin/cohort/${item.artist_id}`, body)
    const idx = items.value.findIndex((i) => i.artist_id === item.artist_id)
    if (idx !== -1) items.value[idx] = data
  } catch {
    // Les erreurs réseau/validation sont remontées par le toast de l'intercepteur api.
  } finally {
    mutating[item.artist_id] = false
  }
}

function togglePin(item) {
  patchOverride(item, { pinned: !item.pinned })
}

function toggleExclude(item) {
  patchOverride(item, { excluded: !item.excluded })
}

function forceTier(item, tier) {
  patchOverride(item, { forced_tier: tier })
}

// « Auto » : un-force → retour au tier calculé. Un null EXPLICITE (≠ absent) est
// requis pour que le PATCH efface forced_tier côté back (sémantique clé-par-clé).
function unforceTier(item) {
  patchOverride(item, { forced_tier: null })
}

// ── Recalcul de la cohorte (dispatch + poll) ──
const recomputing = ref(false)
const recomputeResult = ref(null)
const recomputeSkipped = ref(false)
const recomputeError = ref('')

const recomputePairs = computed(() => {
  const r = recomputeResult.value
  if (!r) return []
  return [
    { value: r.n_total, label: 'membres' },
    { value: r.n_t1, label: 'T1' },
    { value: r.n_t2, label: 'T2' },
    { value: r.n_pinned, label: 'épinglés' },
    { value: r.n_excluded, label: 'exclus' },
    { value: r.n_pruned, label: 'retirés' },
  ].filter((d) => d.value != null)
})

const recomputePoll = useTaskPoll((taskId) => `/api/admin/tasks/${taskId}`, {
  intervalMs: 3000,
  maxAttempts: 200,
  onData(st, { stop }) {
    if (st.status === 'done') {
      const result = st.result || {}
      if (result.skipped) {
        recomputeSkipped.value = true
      } else {
        recomputeResult.value = result
        // Les tiers ont pu changer — on rafraîchit la page courante.
        fetchCohort()
      }
      recomputing.value = false
      stop()
    } else if (st.status === 'error') {
      recomputeError.value = st.error || 'Erreur'
      recomputing.value = false
      stop()
    }
  },
  onError(err) {
    recomputeError.value = 'Erreur polling: ' + (err.message || 'inconnue')
    recomputing.value = false
  },
  onMaxAttempts() {
    recomputeError.value = 'Timeout'
    recomputing.value = false
  },
})

async function runRecompute() {
  recomputing.value = true
  recomputeResult.value = null
  recomputeSkipped.value = false
  recomputeError.value = ''
  try {
    const { data } = await api.post('/api/admin/cohort/recompute')
    recomputePoll.start(data.task_id)
  } catch (e) {
    recomputeError.value = e.response?.data?.detail || 'Erreur'
    recomputing.value = false
  }
}

onMounted(fetchCohort)
</script>

<style scoped>
/* Le wrap est le conteneur de requête du toolbar (un élément ne peut pas être
   requêté par sa PROPRE container-query → le toolbar est restylé via le wrap).
   Les rangées d'actions, elles, sont dans .at-region (son propre conteneur). */
.cohort-wrap {
  container-type: inline-size;
  margin-bottom: var(--space-8);
}

/* ── Barre de recalcul : carte à bordure, déclencheur fer à droite. ── */
.ch-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-5);
  margin-bottom: var(--space-5);
  padding: var(--space-4);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}
.ch-toolbar-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.ch-toolbar-action {
  flex: none;
}
.ch-toolbar-title {
  font: 600 var(--fs-title)/1.2 var(--font-ui);
  color: var(--ink);
}
.ch-toolbar-desc {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-2);
  text-wrap: pretty;
  max-width: 76ch;
}

/* Job en cours : arc en rotation, mono --accent-ink. */
.ch-running {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  margin-top: var(--space-1);
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--accent-ink);
}
/* Cas already_running : pill neutre + arc. */
.ch-skip {
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
/* Ligne de résultat : paires nombre mono + label. */
.ch-result {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-2);
}
.ch-pair {
  display: inline-flex;
  align-items: baseline;
  gap: var(--space-1);
}
.ch-num {
  font: 600 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink);
}
.ch-lbl {
  font: 400 var(--fs-xs)/1 var(--font-ui);
  color: var(--ink-3);
}
.ch-fail {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--neg-ink);
}
.ch-fail-word {
  font: 600 var(--fs-xs)/1 var(--font-ui);
}
.ch-fail-msg {
  font: 400 var(--fs-xs)/1.3 var(--font-mono);
  color: var(--ink-2);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  max-width: 340px;
}

/* ── Filtres de l'en-tête de région. ── */
.ch-filters {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

/* ── Cellules de ligne. ── */
.ch-name {
  font: 600 var(--fs-table-sm)/1.35 var(--font-ui);
  color: var(--accent-ink);
  text-decoration: none;
}
.ch-name:hover {
  text-decoration: underline;
}
.ch-id {
  margin-left: var(--space-1);
  font: 400 var(--fs-nano)/1 var(--font-mono);
  color: var(--ink-3);
}
.ch-badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}
/* Pill d'override admin (épinglé / tier forcé) : canal accent, réservé à l'action
   humaine — distinct des pills neutres/erreur du socle. */
.ch-pill-admin {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.ch-muted {
  color: var(--ink-3);
  font-size: var(--fs-table-sm);
}

/* ── Actions de ligne. ── */
.ch-actions {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  flex-wrap: wrap;
  justify-content: flex-end;
}
.ch-force {
  flex: none;
}

.btn:disabled {
  opacity: 0.5;
  cursor: default;
}

/* ── Responsive — palier unique 859 px. Le toolbar se requête via .cohort-wrap ;
   les actions de ligne via .at-region (leur conteneur le plus proche). ── */
@container (max-width: 859px) {
  .ch-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .ch-toolbar-action {
    width: 100%;
  }
  .ch-toolbar-action .btn {
    width: 100%;
    min-height: var(--touch-min);
    justify-content: center;
  }
  .ch-fail-msg {
    max-width: none;
  }

  /* En carte, les actions s'empilent (le socle donne déjà 100 % + 44 px aux
     boutons de [data-act] ; le segmenté forcé s'étire via admin-table.css). */
  .ch-actions {
    flex-direction: column;
    align-items: stretch;
    justify-content: stretch;
  }
}
</style>

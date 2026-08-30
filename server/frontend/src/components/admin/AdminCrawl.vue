<template>
  <section class="cr-wrap">
    <!-- Couture D10 : ce composant est monté juste sous le dashboard Monitoring.
         Filet --line pleine largeur (border-top de la rangée) + eyebrow JOURNAUX,
         fraîcheur fer à droite. Rien au-dessus du filet. -->
    <div class="cr-seam">
      <span class="cr-eyebrow">Journaux</span>
      <span class="cr-fresh">{{ freshnessLabel }}</span>
    </div>

    <div class="at-region">
      <div class="at-head">
        <h2 class="at-title">
          Historique de crawl
          <span v-if="crawlTotal" class="at-count">{{ crawlTotal.toLocaleString('fr-FR') }}</span>
        </h2>
        <div class="cr-filters">
          <select v-model="crawlTaskType" class="cr-select" @change="setCrawlFilter(crawlFilter)">
            <option value="">Tous les types</option>
            <option v-for="t in crawlTaskTypes" :key="t" :value="t">{{ t }}</option>
          </select>
          <div class="at-seg">
            <button
              v-for="f in crawlFilters"
              :key="f.value"
              class="at-seg-b"
              :class="{ active: crawlFilter === f.value }"
              @click="setCrawlFilter(f.value)"
            >
              {{ f.label }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="loadingCrawlLogs" class="at-empty">Chargement…</div>
      <div v-else-if="crawlLogs.length === 0" class="at-empty">Aucun crawl log.</div>

      <div v-else class="at-scroll">
        <table class="at-table">
          <thead>
            <tr>
              <th>Cible</th>
              <th>Date</th>
              <th>Type</th>
              <th>Source</th>
              <th>Statut</th>
              <th class="cr-th-right">Durée</th>
              <th>Stats</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in crawlLogs" :key="log.id">
              <td data-label="Cible" data-lead>
                <span class="at-id">{{ log.target_label || log.task_type }}</span>
              </td>
              <td class="at-tech" data-label="Date">
                {{ formatDate(log.started_at) }}
              </td>
              <td class="at-tech" data-label="Type" :class="{ 'cr-type-dup': !log.target_label }">
                {{ log.task_type }}
              </td>
              <td data-label="Source">
                <span v-if="log.source" class="at-source">{{ log.source }}</span>
              </td>
              <td data-label="Statut">
                <span class="at-pill" :class="statusPill(log.status)">
                  <AdminIcon v-if="log.status === 'running'" name="arc" :size="10" />
                  {{ log.status }}
                </span>
              </td>
              <td class="at-tech at-tech--right" data-label="Durée">
                <span v-if="log.duration_ms != null">{{ formatDuration(log.duration_ms) }}</span>
              </td>
              <td data-label="Stats" data-stack>
                <div v-if="log.stats" class="at-chips">
                  <span
                    v-for="(v, k) in log.stats"
                    :key="k"
                    class="at-chip"
                    :class="{ 'at-chip--true': v === true }"
                  >
                    <span class="at-chip-k">{{ k }}</span>
                    <span class="at-chip-v">{{ chipValue(v) }}</span>
                  </span>
                </div>
                <span v-if="log.error_message" class="at-err-msg" :title="log.error_message">
                  {{ log.error_message }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="crawlTotalPages > 1" class="at-pager">
        <button class="btn btn--sm" :disabled="crawlPage <= 1" @click="prevCrawlPage()">
          Précédent
        </button>
        <span class="at-pager-count">{{ crawlPage }} / {{ crawlTotalPages }}</span>
        <button
          class="btn btn--sm"
          :disabled="crawlPage >= crawlTotalPages"
          @click="nextCrawlPage()"
        >
          Suivant
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../../utils/api.js'
import AdminIcon from './AdminIcon.vue'

const crawlLogs = ref([])
const loadingCrawlLogs = ref(false)
const crawlPage = ref(1)
const crawlTotal = ref(0)
const crawlTotalPages = ref(0)
const crawlFilter = ref('')
const crawlTaskType = ref('')
const lastFetchedAt = ref(null)
const crawlFilters = [
  { label: 'Tous', value: '' },
  { label: 'Success', value: 'success' },
  { label: 'Error', value: 'error' },
  { label: 'Running', value: 'running' },
]
const crawlTaskTypes = [
  'crawl_radar',
  'crawl_playlist',
  'enrich_catalog',
  'enrich_beatport',
  'reclassify_genres',
  'sync_artists',
  'fetch_artworks',
  'resolve_set_tracks',
]

// Fraîcheur des journaux (couture D10) : heure du dernier fetch, libellé neutre avant
// le premier chargement. Pas de timer — un horaire figé suffit à situer le rafraîchissement.
const freshnessLabel = computed(() => {
  if (!lastFetchedAt.value) return 'Journaux serveur'
  const d = lastFetchedAt.value
  const pad = (n) => String(n).padStart(2, '0')
  return `Rafraîchi à ${pad(d.getHours())}:${pad(d.getMinutes())}`
})

function prevCrawlPage() {
  crawlPage.value--
  fetchCrawlLogs()
}

function nextCrawlPage() {
  crawlPage.value++
  fetchCrawlLogs()
}

async function fetchCrawlLogs() {
  loadingCrawlLogs.value = true
  try {
    const params = { page: crawlPage.value, per_page: 20 }
    if (crawlFilter.value) params.status = crawlFilter.value
    if (crawlTaskType.value) params.task_type = crawlTaskType.value
    const { data } = await api.get('/api/admin/crawl-logs', { params })
    crawlLogs.value = data.items
    crawlTotal.value = data.total
    crawlTotalPages.value = Math.ceil(data.total / data.per_page)
  } finally {
    loadingCrawlLogs.value = false
    lastFetchedAt.value = new Date()
  }
}

function setCrawlFilter(val) {
  crawlFilter.value = val
  crawlPage.value = 1
  fetchCrawlLogs()
}

// Canal de la pill de statut (D7) : success → --ok, error → --err, running → --run
// (héberge l'arc), tout le reste neutre.
function statusPill(status) {
  if (status === 'success') return 'at-pill--ok'
  if (status === 'error') return 'at-pill--err'
  if (status === 'running') return 'at-pill--run'
  return 'at-pill--neutral'
}

// Valeur d'une chip stats (D8) : nombres groupés fr-FR, booléens en toutes lettres
// (le poids 700 de la classe --true porte la distinction, pas la couleur).
function chipValue(v) {
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (typeof v === 'number') return v.toLocaleString('fr-FR')
  return v
}

function formatDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function formatDuration(ms) {
  if (ms < 1000) return `${ms}ms`
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return `${m}m${String(s % 60).padStart(2, '0')}s`
}

onMounted(() => {
  fetchCrawlLogs()
})
</script>

<style scoped>
.cr-wrap {
  margin-bottom: var(--space-5);
}

/* ── Couture D10 : filet pleine largeur + eyebrow JOURNAUX, fraîcheur fer à droite. ── */
.cr-seam {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-25);
  padding-top: var(--space-2);
  margin-bottom: var(--space-4);
  border-top: 1px solid var(--line);
}
.cr-eyebrow {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.cr-fresh {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}

/* ── Barre de filtres (D14) : select + segmenté fer à droite. La hauteur desktop
   34 px du select est portée par cette CLASSE, jamais en style inline — sinon un
   inline gagnerait sur la règle du palier 44 px. ── */
.cr-filters {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.cr-select {
  height: 34px;
  padding: 0 var(--space-2);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--ink-2);
  font: 400 var(--fs-sm)/1 var(--font-mono);
  cursor: pointer;
}

/* Alignement à droite de l'en-tête « Durée ». */
.cr-th-right {
  text-align: right;
}

/* Sous 859 px : la cible retombe parfois sur le task_type (logs sans cible) — la
   rangée Type ferait alors doublon avec la ligne de tête → on l'omet de la carte.
   Desktop garde la colonne Type intacte. */
@container (max-width: 859px) {
  .cr-filters {
    flex-direction: column;
    align-items: stretch;
    width: 100%;
  }
  .cr-select {
    width: 100%;
    min-height: var(--touch-min);
  }
  .cr-type-dup {
    display: none;
  }
}
</style>

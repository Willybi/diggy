<template>
  <div class="admin-view">
    <header class="view-header">
      <h1 class="view-title">Admin</h1>
    </header>

    <!-- Sync artistes -->
    <section class="admin-section">
      <h2 class="section-title">Sync artistes</h2>
      <p class="section-sub">Parse les noms d'artistes du catalog et peuple la table artistes. Idempotent.</p>
      <div class="sync-row">
        <button class="btn-sync" :disabled="syncing" @click="runSync">
          {{ syncing ? 'Sync en cours… (peut prendre ~5-10 min)' : 'Lancer la sync' }}
        </button>
        <div v-if="syncResult" class="sync-result">
          <span class="result-item ok">✓ {{ syncResult.created }} créés</span>
          <span class="result-item warn">⚠ {{ syncResult.flagged }} flags</span>
          <span class="result-item muted">↷ {{ syncResult.skipped }} skippés</span>
        </div>
        <span v-if="syncError" class="sync-error">{{ syncError }}</span>
      </div>
    </section>

    <!-- Fetch artworks -->
    <section class="admin-section">
      <h2 class="section-title">Artworks artistes</h2>
      <p class="section-sub">Fetche les images Deezer pour tous les artistes avec un deezer_id. Idempotent.</p>
      <div class="sync-row">
        <button class="btn-sync" :disabled="fetchingArtworks" @click="runFetchArtworks">
          {{ fetchingArtworks ? 'Fetch en cours…' : 'Fetch artworks' }}
        </button>
        <div v-if="artworksResult" class="sync-result">
          <span class="result-item ok">✓ {{ artworksResult.fetched }} artworks</span>
          <span v-if="artworksResult.linked != null" class="result-item ok">🔗 {{ artworksResult.linked }} liés Deezer</span>
          <span class="result-item muted">↷ {{ artworksResult.skipped }} skippés</span>
        </div>
        <span v-if="artworksError" class="sync-error">{{ artworksError }}</span>
      </div>
    </section>

    <!-- Artworks playlists -->
    <section class="admin-section">
      <h2 class="section-title">Artworks playlists</h2>
      <p class="section-sub">Fetche les images Deezer pour toutes les playlists sans artwork. Synchrone (~1s/playlist).</p>
      <div class="sync-row">
        <button class="btn-sync" :disabled="fetchingPlArtworks" @click="runFetchPlArtworks">
          {{ fetchingPlArtworks ? 'Fetch en cours…' : 'Fetch artworks playlists' }}
        </button>
        <div v-if="plArtworksResult" class="sync-result">
          <span class="result-item ok">✓ {{ plArtworksResult.fetched }} importés</span>
          <span v-if="plArtworksResult.failed" class="result-item warn">⚠ {{ plArtworksResult.failed }} échoués</span>
          <span class="result-item muted">/ {{ plArtworksResult.total }} sans artwork</span>
        </div>
        <span v-if="plArtworksError" class="sync-error">{{ plArtworksError }}</span>
      </div>
    </section>

    <!-- Lier artistes aux sets -->
    <section class="admin-section">
      <h2 class="section-title">Artistes des sets</h2>
      <p class="section-sub">Parse les titres des sets pour trouver les artistes et les lier. Idempotent.</p>
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
      <p class="section-sub">Enrichit via Deezer + Beatport les tracks des sets sans infos. Ne touche pas aux tracks déjà enrichies.</p>
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

    <!-- Enrich Beatport -->
    <section class="admin-section">
      <h2 class="section-title">Enrichissement Beatport</h2>
      <p class="section-sub">Enrichit le catalogue via Beatport : BPM, key (Camelot), label, genre, artwork. ISRC d'abord, fallback titre+artiste.</p>
      <div class="sync-row">
        <label class="batch-label">
          Batch size
          <input v-model.number="beatportBatchSize" type="number" min="0" step="50" placeholder="0 = tout" class="batch-input" />
        </label>
        <button class="btn-sync" :disabled="enrichingBeatport" @click="runEnrichBeatport">
          {{ enrichingBeatport ? 'Enrichissement en cours…' : 'Enrich Beatport' }}
        </button>
        <div v-if="beatportResult" class="sync-result">
          <span class="result-item ok">✓ {{ beatportResult.enriched }} enrichis</span>
          <span class="result-item muted">↷ {{ beatportResult.not_found }} non trouvés</span>
          <span v-if="beatportResult.errors" class="result-item warn">⚠ {{ beatportResult.errors }} erreurs</span>
          <span class="result-item muted">/ {{ beatportResult.total }} traités</span>
        </div>
        <span v-if="beatportError" class="sync-error">{{ beatportError }}</span>
      </div>
    </section>

    <!-- Reclassifier genres -->
    <section class="admin-section">
      <h2 class="section-title">Reclassifier tous les genres</h2>
      <p class="section-sub">Efface tous les genres et re-fetche : Deezer (album) d'abord, fallback Beatport. ~5200 tracks, peut prendre plusieurs heures.</p>
      <div class="sync-row">
        <label class="batch-label">
          Planifier à
          <input v-model="reclassifyEta" type="datetime-local" class="batch-input" style="width:180px" />
        </label>
        <button class="btn-sync" :disabled="reclassifying" @click="runReclassify">
          {{ reclassifying ? 'Lancé…' : reclassifyEta ? 'Planifier' : 'Lancer maintenant' }}
        </button>
        <span v-if="reclassifyResult" class="enrich-result" :class="reclassifyResult.cls">{{ reclassifyResult.text }}</span>
      </div>
    </section>

    <!-- Liaison manuelle artiste ↔ Deezer -->
    <section class="admin-section">
      <h2 class="section-title">Lier un artiste à Deezer</h2>
      <p class="section-sub">Recherche un artiste dans la DB et l'associe manuellement à un compte Deezer.</p>
      <div class="link-form">
        <input v-model="linkArtistQuery" class="form-input" placeholder="Filtrer les artistes sans Deezer…" @input="onLinkSearch" />
        <input v-model="linkDeezerQuery" class="form-input" placeholder="Recherche sur Deezer…" @input="onDeezerSearch" />
      </div>
      <div class="link-results">
        <div class="link-col">
          <p class="col-label">Artistes sans deezer_id ({{ dbArtistResults.length }})</p>
          <div class="link-list">
            <div v-for="a in dbArtistResults" :key="a.id"
              class="result-row" :class="{ selected: selectedDbArtist?.id === a.id }"
              @click="selectedDbArtist = a; linkDeezerQuery = a.name; onDeezerSearch()"
            >
              <div class="cover-thumb-sm">
                <img v-if="a.has_artwork" :src="`/storage/artist-artworks/${a.id}.jpg`" />
                <span v-else class="fallback-sm">{{ a.name?.[0] }}</span>
              </div>
              <span class="ar-name-sm">{{ a.name }}</span>
              <div class="row-actions" @click.stop>
                <button class="btn-row-action" title="Pas sur Deezer" @click="markNoDeezer(a)">✗ Deezer</button>
                <button v-if="detectSeparator(a.name)" class="btn-row-action flag" title="Envoyer vers les flags" @click="flagArtist(a)">Flagguer</button>
              </div>
            </div>
          </div>
        </div>
        <div class="link-col">
          <p class="col-label">Résultats Deezer</p>
          <div class="link-list">
            <div v-for="h in deezerHits" :key="h.deezer_id"
              class="result-row" :class="{ selected: selectedDeezerHit?.deezer_id === h.deezer_id }"
              @click="selectedDeezerHit = h"
            >
              <div class="cover-thumb-sm">
                <img v-if="h.picture" :src="h.picture" />
                <span v-else class="fallback-sm">{{ h.name?.[0] }}</span>
              </div>
              <div>
                <span class="ar-name-sm">{{ h.name }}</span>
                <span class="ar-meta mono muted">
                  {{ h.nb_fan?.toLocaleString() }} fans ·
                  <a :href="`https://www.deezer.com/artist/${h.deezer_id}`" target="_blank" class="dz-link" @click.stop>dz:{{ h.deezer_id }}</a>
                </span>
              </div>
            </div>
            <p v-if="linkDeezerQuery && deezerHits.length === 0" class="empty-hint">Aucun résultat</p>
          </div>
        </div>
      </div>
      <div v-if="selectedDbArtist && selectedDeezerHit" class="link-confirm">
        <span class="link-summary">
          Lier <strong>{{ selectedDbArtist.name }}</strong> → Deezer <strong>{{ selectedDeezerHit.name }}</strong> ({{ selectedDeezerHit.deezer_id }})
        </span>
        <button class="btn-confirm-link" :disabled="linking" @click="confirmLink">
          {{ linking ? 'Liaison…' : 'Confirmer' }}
        </button>
        <span v-if="linkSuccess" class="result-item ok">✓ Lié</span>
        <span v-if="linkError" class="sync-error">{{ linkError }}</span>
      </div>
    </section>

    <!-- Mappings genres -->
    <section class="admin-section">
      <div class="section-header">
        <h2 class="section-title">
          Mappings genres
          <span v-if="mappingStats" class="flag-count">{{ mappingStats.unmapped }} / {{ mappingStats.total }} non mappés</span>
        </h2>
        <div class="filter-group">
          <button class="filter-btn" :class="{ active: !mappingShowUnmapped }" @click="mappingShowUnmapped = false; fetchMappings()">Tous</button>
          <button class="filter-btn" :class="{ active: mappingShowUnmapped }" @click="mappingShowUnmapped = true; fetchMappings()">Non mappés</button>
        </div>
      </div>
      <p class="section-sub">Associe les noms de genres bruts (Beatport/Deezer) aux nœuds de la taxonomie Wikidata.</p>

      <div v-if="loadingMappings" class="state">Chargement…</div>
      <div v-else-if="mappings.length === 0" class="state">Aucun mapping.</div>

      <div v-else class="table-wrap">
        <table class="flag-table">
          <thead>
            <tr>
              <th>Nom brut</th>
              <th>Nœud taxonomique</th>
              <th style="width: 260px">Recherche</th>
              <th style="width: 80px" />
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in mappings" :key="m.id">
              <td>
                <span class="raw-string">{{ m.rawName }}</span>
              </td>
              <td>
                <span v-if="m.nodeLabel" class="token-pill">{{ m.nodeLabel }}</span>
                <span v-else class="muted" style="font-size: 12px; color: var(--ink-3)">—</span>
              </td>
              <td>
                <div class="mapping-search-wrap">
                  <input
                    v-model="mappingSearch[m.id]"
                    class="mapping-search-input"
                    placeholder="Chercher un genre…"
                    @input="onMappingSearch(m.id)"
                  />
                  <div v-if="mappingResults[m.id]?.length" class="mapping-dropdown">
                    <div
                      v-for="n in mappingResults[m.id]"
                      :key="n.id"
                      class="mapping-option"
                      :class="{ selected: mappingSelected[m.id] === n.id }"
                      @click="mappingSelected[m.id] = n.id; mappingSearch[m.id] = n.label; mappingResults[m.id] = []"
                    >
                      <span class="mapping-option-label">{{ n.label }}</span>
                      <span class="mapping-option-qid mono">{{ n.wikidataId }}</span>
                    </div>
                  </div>
                </div>
              </td>
              <td>
                <button
                  v-if="mappingSelected[m.id]"
                  class="btn-sync"
                  style="padding: 5px 12px; font-size: 11px"
                  :disabled="savingMapping[m.id]"
                  @click="saveMapping(m)"
                >
                  {{ savingMapping[m.id] ? '…' : 'Associer' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Crawl History -->
    <section class="admin-section">
      <div class="section-header">
        <h2 class="section-title">
          Crawl History
          <span v-if="crawlTotal" class="flag-count">{{ crawlTotal }}</span>
        </h2>
        <div class="crawl-filters">
          <select v-model="crawlTaskType" class="crawl-select" @change="setCrawlFilter(crawlFilter)">
            <option value="">Tous les types</option>
            <option v-for="t in crawlTaskTypes" :key="t" :value="t">{{ t }}</option>
          </select>
          <div class="filter-group">
            <button
              v-for="f in crawlFilters"
              :key="f.value"
              class="filter-btn"
              :class="{ active: crawlFilter === f.value }"
              @click="setCrawlFilter(f.value)"
            >{{ f.label }}</button>
          </div>
        </div>
      </div>

      <div v-if="loadingCrawlLogs" class="state">Chargement...</div>
      <div v-else-if="crawlLogs.length === 0" class="state">Aucun crawl log.</div>

      <div v-else class="table-wrap">
        <table class="flag-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Type</th>
              <th>Cible</th>
              <th>Source</th>
              <th>Status</th>
              <th>Duree</th>
              <th>Stats</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in crawlLogs" :key="log.id">
              <td class="mono" style="font-size: 11px; white-space: nowrap">
                {{ formatDate(log.started_at) }}
              </td>
              <td>
                <span class="token-pill">{{ log.task_type }}</span>
              </td>
              <td class="raw-string" style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
                {{ log.target_label || '-' }}
              </td>
              <td>
                <span v-if="log.source" class="token-pill">{{ log.source }}</span>
                <span v-else class="muted">-</span>
              </td>
              <td>
                <span class="status-badge" :class="log.status">{{ log.status }}</span>
              </td>
              <td class="mono" style="font-size: 11px">
                {{ log.duration_ms != null ? formatDuration(log.duration_ms) : '-' }}
              </td>
              <td style="font-size: 11px; display: flex; flex-wrap: wrap; gap: 3px; align-items: center">
                <template v-if="log.stats">
                  <span v-for="(v, k) in log.stats" :key="k" class="stat-chip">
                    {{ k }}: {{ v }}
                  </span>
                </template>
                <span v-if="log.error_message" class="sync-error" style="font-size: 10px" :title="log.error_message">
                  {{ log.error_message.slice(0, 60) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="crawlTotalPages > 1" class="crawl-pagination">
        <button :disabled="crawlPage <= 1" @click="crawlPage--; fetchCrawlLogs()">Prev</button>
        <span class="mono" style="font-size: 12px">{{ crawlPage }} / {{ crawlTotalPages }}</span>
        <button :disabled="crawlPage >= crawlTotalPages" @click="crawlPage++; fetchCrawlLogs()">Next</button>
      </div>
    </section>

    <!-- Flags à valider -->
    <section class="admin-section">
      <div class="section-header">
        <h2 class="section-title">
          Flags artistes
          <span v-if="flags.length" class="flag-count">{{ flags.length }}</span>
        </h2>
        <div class="filter-group">
          <button
            v-for="s in ['pending', 'validated', 'skipped']"
            :key="s"
            class="filter-btn"
            :class="{ active: filterStatus === s }"
            @click="setFilter(s)"
          >{{ s }}</button>
        </div>
      </div>

      <div v-if="loadingFlags" class="state">Chargement…</div>
      <div v-else-if="flags.length === 0" class="state">Aucun flag {{ filterStatus }}.</div>

      <div v-else class="table-wrap">
        <table class="flag-table">
          <thead>
            <tr>
              <th class="col-raw">String brute</th>
              <th class="col-reason">Raison</th>
              <th class="col-tokens">Tokens détectés</th>
              <th class="col-deezer">Deezer</th>
              <th class="col-action" />
            </tr>
          </thead>
          <tbody>
            <tr v-for="flag in flags" :key="flag.id" :class="{ resolved: flag.status !== 'pending' }">
              <td class="col-raw">
                <span class="raw-string">{{ flag.raw_artist_string }}</span>
              </td>
              <td class="col-reason">
                <span class="reason-badge" :class="flag.reason">{{ flag.reason }}</span>
              </td>
              <td class="col-tokens">
                <div class="token-list">
                  <span v-for="t in flag.tokens" :key="t" class="token-pill">{{ t }}</span>
                </div>
              </td>
              <td class="col-deezer">
                <div class="deezer-list">
                  <span
                    v-for="(did, name) in flag.deezer_ids"
                    :key="name"
                    class="deezer-entry"
                    :class="{ found: !!did, missing: !did }"
                  >
                    <span class="deezer-name">{{ name }}</span>
                    <a v-if="did" :href="`https://www.deezer.com/artist/${did}`" target="_blank" class="deezer-id mono dz-link">{{ did }}</a>
                    <span v-else class="deezer-id mono">✗</span>
                  </span>
                </div>
              </td>
              <td class="col-action">
                <template v-if="flag.status === 'pending'">
                  <div class="action-btns">
                    <button
                      class="btn-split"
                      :disabled="resolving[flag.id]"
                      :title="`Créer: ${flag.tokens.join(', ')}`"
                      @click="resolve(flag.id, 'split')"
                    >Splitter</button>
                    <button
                      class="btn-keep"
                      :disabled="resolving[flag.id]"
                      :title="`Créer: ${flag.raw_artist_string}`"
                      @click="resolve(flag.id, 'keep')"
                    >Garder</button>
                    <button
                      class="btn-skip"
                      :disabled="resolving[flag.id]"
                      @click="resolve(flag.id, 'skip')"
                    >Ignorer</button>
                  </div>
                </template>
                <template v-else>
                  <span class="status-badge" :class="flag.status">{{ flag.status }}</span>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import api from '../utils/api.js'
import { useAuthStore } from '../stores/auth.js'

const auth = useAuthStore()
const syncing = ref(false)
const syncResult = ref(null)
const syncError = ref('')
let pollTimer = null
const flags = ref([])
const loadingFlags = ref(false)
const filterStatus = ref('pending')
const resolving = reactive({})
const fetchingArtworks = ref(false)
const linkingSets = ref(false)
const linkSetsResult = ref(null)
const linkSetsError = ref('')
const artworksResult = ref(null)
const artworksError = ref('')
const fetchingPlArtworks = ref(false)
const plArtworksResult = ref(null)
const plArtworksError = ref('')
const enrichingSets = ref(false)
const enrichSetsResult = ref(null)
const enrichSetsError = ref('')
const enrichingBeatport = ref(false)
const beatportBatchSize = ref(0)
const beatportResult = ref(null)
const beatportError = ref('')
const reclassifying = ref(false)
const reclassifyEta = ref('')
const reclassifyResult = ref(null)

// Manual link
const linkArtistQuery = ref('')
const linkDeezerQuery = ref('')
const dbArtistResults = ref([])
const deezerHits = ref([])
const selectedDbArtist = ref(null)
const selectedDeezerHit = ref(null)
const linking = ref(false)
const linkSuccess = ref(false)
const linkError = ref('')
let linkDbTimer = null
let linkDeezerTimer = null

// Genre mappings
const mappings = ref([])
const loadingMappings = ref(false)
const mappingShowUnmapped = ref(true)
const mappingStats = ref(null)
const mappingSearch = reactive({})
const mappingResults = reactive({})
const mappingSelected = reactive({})
const savingMapping = reactive({})
let mappingTimers = {}

async function fetchMappings() {
  loadingMappings.value = true
  try {
    const params = { limit: 200 }
    if (mappingShowUnmapped.value) params.unmapped = true
    const { data } = await api.get('/api/taxonomy/mappings', { params })
    mappings.value = data.items
    for (const m of data.items) {
      if (!(m.id in mappingSearch)) mappingSearch[m.id] = ''
      if (!(m.id in mappingResults)) mappingResults[m.id] = []
      if (!(m.id in mappingSelected)) mappingSelected[m.id] = null
      if (!(m.id in savingMapping)) savingMapping[m.id] = false
    }
  } finally {
    loadingMappings.value = false
  }
}

async function fetchMappingStats() {
  const [all, unmapped] = await Promise.all([
    api.get('/api/taxonomy/mappings', { params: { limit: 1 } }),
    api.get('/api/taxonomy/mappings', { params: { unmapped: true, limit: 1 } }),
  ])
  mappingStats.value = { total: all.data.total, unmapped: unmapped.data.total }
}

function onMappingSearch(mappingId) {
  clearTimeout(mappingTimers[mappingId])
  mappingSelected[mappingId] = null
  const q = (mappingSearch[mappingId] || '').trim()
  if (!q) { mappingResults[mappingId] = []; return }
  mappingTimers[mappingId] = setTimeout(async () => {
    const { data } = await api.get('/api/taxonomy/nodes', { params: { q, limit: 8 } })
    mappingResults[mappingId] = data.items
  }, 250)
}

async function saveMapping(m) {
  const nodeId = mappingSelected[m.id]
  if (!nodeId) return
  savingMapping[m.id] = true
  try {
    await api.put(`/api/taxonomy/mappings/${encodeURIComponent(m.rawName)}`, null, {
      params: { node_id: nodeId },
    })
    // Update in-place
    const node = mappingResults[m.id]?.find(n => n.id === nodeId)
    m.nodeId = nodeId
    m.nodeLabel = node?.label || mappingSearch[m.id]
    m.nodeWikidataId = node?.wikidataId
    // Clear search state
    mappingSearch[m.id] = ''
    mappingResults[m.id] = []
    mappingSelected[m.id] = null
    // If showing unmapped, remove it from list
    if (mappingShowUnmapped.value) {
      mappings.value = mappings.value.filter(x => x.id !== m.id)
    }
    await fetchMappingStats()
  } finally {
    savingMapping[m.id] = false
  }
}

// Crawl logs
const crawlLogs = ref([])
const loadingCrawlLogs = ref(false)
const crawlPage = ref(1)
const crawlTotal = ref(0)
const crawlTotalPages = ref(0)
const crawlFilter = ref('')
const crawlTaskType = ref('')
const crawlFilters = [
  { label: 'Tous', value: '' },
  { label: 'Success', value: 'success' },
  { label: 'Error', value: 'error' },
  { label: 'Running', value: 'running' },
]
const crawlTaskTypes = [
  'crawl_radar', 'crawl_playlist', 'enrich_catalog', 'enrich_beatport',
  'reclassify_genres', 'sync_artists', 'fetch_artworks', 'resolve_set_tracks', 'enrich_set_tracks',
]

async function runSync() {
  syncing.value = true
  syncResult.value = null
  syncError.value = ''
  try {
    const { data } = await api.post('/api/admin/artists/sync')
    pollStatus(data.task_id)
  } catch (e) {
    syncError.value = e.response?.data?.detail || 'Erreur lors de la sync'
    syncing.value = false
  }
}

function pollStatus(taskId) {
  let attempts = 0
  const maxAttempts = 300 // 10min max (2s * 300)
  pollTimer = setInterval(async () => {
    attempts++
    if (attempts >= maxAttempts) {
      clearInterval(pollTimer)
      syncError.value = 'Timeout — vérifiez les logs Celery'
      syncing.value = false
      return
    }
    try {
      const { data } = await api.get(`/api/admin/artists/sync/status/${taskId}`)
      if (data.status === 'done') {
        clearInterval(pollTimer)
        syncResult.value = data.result
        syncing.value = false
        await fetchFlags()
      } else if (data.status === 'error') {
        clearInterval(pollTimer)
        syncError.value = data.error || 'Erreur Celery'
        syncing.value = false
      }
    } catch {}
  }, 2000)
}

async function fetchFlags() {
  loadingFlags.value = true
  try {
    const { data } = await api.get('/api/admin/artists/flags', {
      params: { status: filterStatus.value },
    })
    flags.value = data
  } finally {
    loadingFlags.value = false
  }
}

async function setFilter(s) {
  filterStatus.value = s
  await fetchFlags()
}

async function resolve(flagId, action) {
  resolving[flagId] = true
  try {
    const { data } = await api.post(
      `/api/admin/artists/flags/${flagId}/resolve`,
      { action },
    )
    // Update in-place
    const idx = flags.value.findIndex(f => f.id === flagId)
    if (idx !== -1) flags.value[idx] = data
    // If viewing pending, remove resolved ones
    if (filterStatus.value === 'pending') {
      flags.value = flags.value.filter(f => f.status === 'pending')
    }
  } finally {
    resolving[flagId] = false
  }
}

async function runFetchArtworks() {
  fetchingArtworks.value = true
  artworksResult.value = null
  artworksError.value = ''
  try {
    const { data } = await api.post('/api/admin/artists/fetch-artworks')
    pollArtworksStatus(data.task_id)
  } catch (e) {
    artworksError.value = e.response?.data?.detail || 'Erreur'
    fetchingArtworks.value = false
  }
}

function pollArtworksStatus(taskId) {
  let attempts = 0
  const timer = setInterval(async () => {
    attempts++
    if (attempts >= 150) { clearInterval(timer); fetchingArtworks.value = false; return }
    try {
      const { data } = await api.get(`/api/admin/artists/sync/status/${taskId}`)
      if (data.status === 'done') {
        clearInterval(timer)
        artworksResult.value = data.result
        fetchingArtworks.value = false
      } else if (data.status === 'error') {
        clearInterval(timer)
        artworksError.value = data.error || 'Erreur Celery'
        fetchingArtworks.value = false
      }
    } catch (err) {
      clearInterval(timer); artworksError.value = 'Erreur polling: ' + (err.message || 'inconnue'); fetchingArtworks.value = false
    }
  }, 2000)
}

async function runFetchPlArtworks() {
  fetchingPlArtworks.value = true
  plArtworksResult.value = null
  plArtworksError.value = ''
  try {
    const { data } = await api.post('/api/admin/playlists/fetch-artworks')
    plArtworksResult.value = data
  } catch (e) {
    plArtworksError.value = e.response?.data?.detail || 'Erreur'
  } finally {
    fetchingPlArtworks.value = false
  }
}

async function runLinkSets() {
  linkingSets.value = true
  linkSetsResult.value = null
  linkSetsError.value = ''
  try {
    const { data } = await api.post('/api/admin/sets/link-artists')
    let attempts = 0
    const timer = setInterval(async () => {
      attempts++
      if (attempts > 150) { clearInterval(timer); linkSetsError.value = 'Timeout'; linkingSets.value = false; return }
      try {
        const { data: st } = await api.get(`/api/admin/artists/sync/status/${data.task_id}`)
        if (st.status === 'done') { clearInterval(timer); linkSetsResult.value = st.result; linkingSets.value = false }
        else if (st.status === 'error') { clearInterval(timer); linkSetsError.value = st.error || 'Erreur'; linkingSets.value = false }
      } catch (err) {
        clearInterval(timer); linkSetsError.value = 'Erreur polling: ' + (err.message || 'inconnue'); linkingSets.value = false
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
      if (attempts > 300) { clearInterval(timer); enrichSetsError.value = 'Timeout'; enrichingSets.value = false; return }
      try {
        const { data: st } = await api.get(`/api/admin/artists/sync/status/${data.task_id}`)
        if (st.status === 'done') { clearInterval(timer); enrichSetsResult.value = st.result; enrichingSets.value = false }
        else if (st.status === 'error') { clearInterval(timer); enrichSetsError.value = st.error || 'Erreur'; enrichingSets.value = false }
      } catch (err) {
        clearInterval(timer); enrichSetsError.value = 'Erreur polling: ' + (err.message || 'inconnue'); enrichingSets.value = false
      }
    }, 3000)
  } catch (e) {
    enrichSetsError.value = e.response?.data?.detail || 'Erreur'
    enrichingSets.value = false
  }
}

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
      if (attempts > 300) { clearInterval(timer); beatportError.value = 'Timeout'; enrichingBeatport.value = false; return }
      try {
        const { data: st } = await api.get(`/api/admin/artists/sync/status/${data.task_id}`)
        if (st.status === 'done') { clearInterval(timer); beatportResult.value = st.result; enrichingBeatport.value = false }
        else if (st.status === 'error') { clearInterval(timer); beatportError.value = st.error || 'Erreur'; enrichingBeatport.value = false }
      } catch (err) {
        clearInterval(timer); beatportError.value = 'Erreur polling: ' + (err.message || 'inconnue'); enrichingBeatport.value = false
      }
    }, 5000)
  } catch (e) {
    beatportError.value = e.response?.data?.detail || 'Erreur'
    enrichingBeatport.value = false
  }
}

async function runReclassify() {
  reclassifying.value = true
  reclassifyResult.value = null
  try {
    const params = reclassifyEta.value ? `?eta=${new Date(reclassifyEta.value).toISOString()}` : ''
    const { data } = await api.post(`/api/admin/genres/reclassify${params}`)
    const when = reclassifyEta.value ? ` pour ${reclassifyEta.value}` : ''
    reclassifyResult.value = { text: `Task planifiée${when} (${data.task_id.slice(0, 8)}…)`, cls: 'ok' }
  } catch (e) {
    reclassifyResult.value = { text: e.response?.data?.detail || 'Erreur', cls: 'err' }
  } finally {
    reclassifying.value = false
  }
}

async function fetchNoDeezerArtists(q = '') {
  const params = { no_deezer: true, limit: 100 }
  if (q) params.q = q
  const { data } = await api.get('/api/artists/', { params })
  dbArtistResults.value = data.items || data
}

function onLinkSearch() {
  clearTimeout(linkDbTimer)
  selectedDbArtist.value = null
  linkDbTimer = setTimeout(() => fetchNoDeezerArtists(linkArtistQuery.value.trim()), 300)
}

function onDeezerSearch() {
  clearTimeout(linkDeezerTimer)
  selectedDeezerHit.value = null
  if (!linkDeezerQuery.value.trim()) { deezerHits.value = []; return }
  linkDeezerTimer = setTimeout(async () => {
    const { data } = await api.get('/api/admin/artists/search-deezer', {
      params: { q: linkDeezerQuery.value.trim() },
    })
    deezerHits.value = data
  }, 300)
}

async function confirmLink() {
  if (!selectedDbArtist.value || !selectedDeezerHit.value) return
  linking.value = true
  linkSuccess.value = false
  linkError.value = ''
  try {
    await api.patch(
      `/api/admin/artists/${selectedDbArtist.value.id}/deezer`,
      { deezer_id: selectedDeezerHit.value.deezer_id },
    )
    linkSuccess.value = true
    // Reset selections but keep query to refresh list
    const q = linkArtistQuery.value.trim()
    selectedDbArtist.value = null
    selectedDeezerHit.value = null
    linkDeezerQuery.value = ''
    deezerHits.value = []
    await fetchNoDeezerArtists(q)
  } catch (e) {
    linkError.value = e.response?.data?.detail || 'Erreur'
  } finally {
    linking.value = false
  }
}

async function markNoDeezer(artist) {
  try {
    await api.patch(`/api/admin/artists/${artist.id}/no-deezer`)
    dbArtistResults.value = dbArtistResults.value.filter(a => a.id !== artist.id)
  } catch {}
}

const SEPARATORS = ['/', ' & ', ', ', ' feat. ', ' feat ', ' ft. ', ' ft ']

function detectSeparator(name) {
  return SEPARATORS.find(sep => name.includes(sep)) || null
}

async function flagArtist(artist) {
  const sep = detectSeparator(artist.name)
  if (!sep) return
  const tokens = artist.name.split(sep).map(t => t.trim()).filter(Boolean)
  try {
    await api.post(
      '/api/admin/artists/flags/manual',
      { raw_artist_string: artist.name, tokens, reason: 'manual' },
    )
    // Remove from no-deezer list and refresh flags
    dbArtistResults.value = dbArtistResults.value.filter(a => a.id !== artist.id)
    if (filterStatus.value === 'pending') await fetchFlags()
  } catch {}
}

// Crawl logs functions
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
  }
}

function setCrawlFilter(val) {
  crawlFilter.value = val
  crawlPage.value = 1
  fetchCrawlLogs()
}

function formatDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  const pad = n => String(n).padStart(2, '0')
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
  fetchFlags()
  fetchNoDeezerArtists()
  fetchCrawlLogs()
  fetchMappings()
  fetchMappingStats()
})
</script>

<style scoped>
.admin-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: 1100px;
  margin: 0 auto;
}
.view-header { margin-bottom: 24px; }
.view-title {
  font: 600 22px/1.1 var(--font-ui);
  letter-spacing: -0.02em;
  color: var(--ink);
}

.admin-section {
  margin-bottom: 36px;
  padding: 20px 24px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.section-title {
  font: 600 15px/1 var(--font-ui);
  color: var(--ink);
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-header .section-title { margin-bottom: 0; }
.section-sub {
  font: 400 12px/1.4 var(--font-ui);
  color: var(--ink-3);
  margin-bottom: 14px;
}
.flag-count {
  font: 400 11px/1 var(--font-mono);
  background: var(--accent-soft);
  color: var(--accent-ink);
  padding: 2px 7px;
  border-radius: 10px;
}

/* Sync */
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
.btn-sync:disabled { opacity: 0.5; cursor: default; }
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
.result-item.ok { color: var(--pos-ink); }
.result-item.warn { color: var(--warn-ink); }
.result-item.muted { color: var(--ink-3); }
.sync-error { font-size: 13px; color: var(--neg-ink); }

/* Filter */
.filter-group {
  display: flex;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  overflow: hidden;
}
.filter-btn {
  padding: 6px 12px;
  border: none;
  background: var(--surface);
  color: var(--ink-3);
  font: 500 11px/1 var(--font-ui);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.filter-btn:not(:last-child) { border-right: 1px solid var(--line-2); }
.filter-btn.active { background: var(--accent-soft); color: var(--accent-ink); }

/* Table */
.table-wrap { overflow-x: auto; }
.flag-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.flag-table thead th {
  text-align: left;
  padding: 0 12px 10px;
  font: 500 10px/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
.flag-table tbody td {
  padding: 10px 12px;
  vertical-align: top;
  border-bottom: 1px solid var(--line);
}
.flag-table tbody tr:last-child td { border-bottom: none; }
.flag-table tbody tr.resolved td { opacity: 0.5; }

.col-raw    { min-width: 180px; }
.col-reason { width: 160px; }
.col-tokens { width: 200px; }
.col-deezer { width: 220px; }
.col-action { width: 200px; text-align: right; }

.raw-string {
  font: 500 13px/1.3 var(--font-ui);
  color: var(--ink);
}

.reason-badge {
  font: 500 11px/1 var(--font-mono);
  padding: 3px 7px;
  border-radius: 4px;
  white-space: nowrap;
}
.reason-badge.comma_unresolved { background: var(--warn-soft); color: var(--warn-ink); }
.reason-badge.ampersand_ambiguous { background: var(--neg-soft); color: var(--neg-ink); }
.reason-badge.ampersand_unknown { background: var(--surface-2); color: var(--ink-3); }

.token-list { display: flex; flex-wrap: wrap; gap: 4px; }
.token-pill {
  font: 400 11px/1 var(--font-mono);
  background: var(--surface-2);
  color: var(--ink-2);
  padding: 3px 7px;
  border-radius: 4px;
  white-space: nowrap;
}

.deezer-list { display: flex; flex-direction: column; gap: 3px; }
.deezer-entry { display: flex; gap: 6px; align-items: baseline; }
.deezer-name { font-size: 11px; color: var(--ink-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100px; }
.deezer-id { font-size: 10px; }
.deezer-entry.found .deezer-id { color: var(--pos-ink); }
.deezer-entry.missing .deezer-id { color: var(--neg-ink); }

.action-btns { display: flex; gap: 5px; justify-content: flex-end; flex-wrap: wrap; }
.btn-split, .btn-keep, .btn-skip {
  padding: 5px 10px;
  border-radius: var(--r-sm);
  font: 500 11px/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.12s;
}
.btn-split:disabled, .btn-keep:disabled, .btn-skip:disabled { opacity: 0.4; cursor: default; }
.btn-split { border: 1px solid var(--accent); background: var(--accent-soft); color: var(--accent-ink); }
.btn-split:hover:not(:disabled) { background: var(--accent); color: var(--on-accent); }
.btn-keep { border: 1px solid var(--line-2); background: var(--surface); color: var(--ink-2); }
.btn-keep:hover:not(:disabled) { background: var(--surface-2); }
.btn-skip { border: 1px solid var(--line-2); background: var(--surface); color: var(--ink-3); }
.btn-skip:hover:not(:disabled) { color: var(--neg-ink); border-color: var(--neg-ink); }

.status-badge {
  font: 500 11px/1 var(--font-mono);
  padding: 3px 8px;
  border-radius: 4px;
}
.status-badge.validated { background: var(--pos-soft); color: var(--pos-ink); }
.status-badge.skipped { background: var(--surface-2); color: var(--ink-3); }

.state { font-size: 13px; color: var(--ink-3); font-style: italic; padding: 12px 0; }
.mono { font-family: var(--font-mono); }

/* Manual link */
.link-form {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.link-results {
  display: flex;
  gap: 16px;
  margin-bottom: 14px;
}
.link-col {
  flex: 1;
  min-width: 200px;
}
.col-label {
  font: 500 10px/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin-bottom: 8px;
}
.result-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border-radius: var(--r-sm);
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.1s;
}
.result-row:hover { background: var(--surface-2); }
.result-row.selected { border-color: var(--accent); background: var(--accent-soft); }
.cover-thumb-sm {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: var(--surface-2);
  border: 1px solid var(--line);
  overflow: hidden;
  flex: none;
  display: flex; align-items: center; justify-content: center;
}
.cover-thumb-sm img { width: 100%; height: 100%; object-fit: cover; }
.fallback-sm { font: 600 13px/1 var(--font-ui); color: var(--ink-3); }
.ar-name-sm { display: block; font: 500 13px/1 var(--font-ui); color: var(--ink); }
.ar-meta { display: block; font-size: 11px; margin-top: 2px; }
.empty-hint { font-size: 12px; color: var(--ink-3); font-style: italic; padding: 8px 10px; }
.link-list {
  max-height: 320px;
  overflow-y: auto;
}
.dz-link {
  color: var(--accent-ink);
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 11px;
}
.dz-link:hover { text-decoration: underline; }
.row-actions {
  margin-left: auto;
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.1s;
}
.result-row:hover .row-actions { opacity: 1; }
.btn-row-action {
  padding: 3px 7px;
  border-radius: 4px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  font: 500 10px/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-row-action:hover { color: var(--neg-ink); border-color: var(--neg-ink); }
.btn-row-action.flag:hover { color: var(--warn-ink); border-color: var(--warn-ink); }
.link-confirm {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: var(--surface-2);
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  flex-wrap: wrap;
}
.link-summary { font: 400 13px/1.4 var(--font-ui); color: var(--ink-2); }
.btn-confirm-link {
  padding: 7px 16px;
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
}
.btn-confirm-link:disabled { opacity: 0.5; cursor: default; }

/* Crawl logs */
.crawl-filters {
  display: flex;
  align-items: center;
  gap: 8px;
}
.crawl-select {
  padding: 5px 8px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 400 11px/1 var(--font-mono);
  cursor: pointer;
}
.crawl-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 12px;
}
.crawl-pagination button {
  padding: 5px 12px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 12px/1 var(--font-ui);
  cursor: pointer;
}
.crawl-pagination button:disabled { opacity: 0.4; cursor: default; }
.stat-chip {
  display: inline-block;
  font: 400 10px/1 var(--font-mono);
  background: var(--surface-2);
  color: var(--ink-2);
  padding: 2px 6px;
  border-radius: 3px;
  margin: 1px 2px;
  white-space: nowrap;
}
.status-badge.running { background: var(--accent-soft); color: var(--accent-ink); }
.status-badge.success { background: var(--pos-soft); color: var(--pos-ink); }
.status-badge.error { background: var(--neg-soft); color: var(--neg-ink); }

/* Genre mappings */
.mapping-search-wrap { position: relative; }
.mapping-search-input {
  width: 100%;
  padding: 5px 8px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--ink);
  font: 400 12px/1 var(--font-ui);
  box-sizing: border-box;
}
.mapping-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 10;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  max-height: 200px;
  overflow-y: auto;
  margin-top: 2px;
}
.mapping-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  cursor: pointer;
  transition: background 0.1s;
}
.mapping-option:hover { background: var(--surface-2); }
.mapping-option.selected { background: var(--accent-soft); }
.mapping-option-label { font: 400 12px/1.3 var(--font-ui); color: var(--ink); }
.mapping-option-qid { font-size: 10px; color: var(--ink-3); }
.muted { color: var(--ink-3); }
</style>

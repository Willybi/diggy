<template>
  <section class="chn-wrap">
    <!-- Ajouter une chaîne. Chemin principal = RECHERCHE par nom (on choisit la
         bonne chaîne dans une liste au lieu de coller une URL à l'aveugle) ;
         voie avancée = URL directe. POST /admin/channels {url, name?, channel_type?}
         — 400 si l'URL/id est irrésolvable (message inline, l'intercepteur api ne
         toaste pas les 4xx). -->
    <div class="chn-toolbar">
      <div class="chn-toolbar-body">
        <h2 class="chn-toolbar-title">Ajouter une chaîne</h2>
        <p class="chn-toolbar-desc">
          Recherche une chaîne YouTube par son nom, puis choisis-la dans la liste. La recherche ne
          part qu'au clic (chaque requête consomme du quota YouTube).
        </p>

        <!-- Recherche add-by-search : JAMAIS de recherche à la frappe (chaque appel
             coûte 100 unités de quota) → uniquement au clic / Entrée. -->
        <div class="chn-search">
          <div class="chn-add-form">
            <input
              v-model="searchQuery"
              class="chn-input chn-input--grow"
              type="text"
              placeholder="Nom de la chaîne YouTube…"
              aria-label="Rechercher une chaîne YouTube"
              @keyup.enter="runSearch"
            />
            <button
              class="btn btn--sm btn--accent"
              :disabled="searching || !searchQuery.trim()"
              @click="runSearch"
            >
              <AdminIcon name="search" :size="14" />
              {{ searching ? 'Recherche…' : 'Rechercher' }}
            </button>
          </div>
          <p v-if="searchError" class="chn-add-error">
            <AdminIcon name="alert-triangle" :size="13" /> {{ searchError }}
          </p>

          <div v-if="searching" class="chn-search-msg">Recherche…</div>
          <div v-else-if="searched && searchResults.length === 0" class="chn-search-msg">
            Aucune chaîne trouvée.
          </div>
          <ul v-else-if="searchResults.length" class="chn-results">
            <li v-for="r in searchResults" :key="r.channel_id" class="chn-result">
              <img
                v-if="r.thumbnail_url"
                class="chn-result-thumb"
                :src="r.thumbnail_url"
                :alt="`Vignette de ${r.title}`"
                width="40"
                height="40"
                loading="lazy"
              />
              <span
                v-else
                class="chn-result-thumb chn-result-thumb--empty"
                aria-hidden="true"
              ></span>
              <div class="chn-result-body">
                <span class="chn-result-title">{{ r.title }}</span>
                <span v-if="r.description" class="chn-result-desc">{{ r.description }}</span>
              </div>
              <a
                class="chn-result-open"
                :href="ytChannelUrl(r.channel_id)"
                target="_blank"
                rel="noopener"
                :aria-label="`Ouvrir ${r.title} sur YouTube`"
              >
                <AdminIcon name="external" :size="14" />
              </a>
              <button
                class="btn btn--sm btn--accent"
                :disabled="addingResult[r.channel_id]"
                @click="addResult(r)"
              >
                {{ addingResult[r.channel_id] ? 'Ajout…' : 'Ajouter' }}
              </button>
              <p v-if="resultErrors[r.channel_id]" class="chn-add-error chn-result-err">
                <AdminIcon name="alert-triangle" :size="13" /> {{ resultErrors[r.channel_id] }}
              </p>
            </li>
          </ul>
        </div>

        <!-- Voie avancée : ajout par URL / handle / id brut directement. -->
        <details class="chn-direct at-details">
          <summary class="chn-direct-sum">
            <AdminIcon name="chevron" :size="14" class="at-details-chev" />
            URL directe (voie avancée)
          </summary>
          <p class="chn-toolbar-desc chn-direct-desc">
            Ajoute une chaîne par son URL, son handle («&nbsp;@…&nbsp;») ou son id brut
            («&nbsp;UC…&nbsp;»). L'id de plateforme est résolu côté serveur.
          </p>
          <div class="chn-add-form">
            <input
              v-model="addUrl"
              class="chn-input chn-input--grow"
              type="text"
              placeholder="URL / @handle / UC…"
              aria-label="URL de la chaîne"
              @keyup.enter="addByUrl"
            />
            <input
              v-model="addName"
              class="chn-input"
              type="text"
              placeholder="Nom (optionnel)"
              aria-label="Nom de la chaîne"
              @keyup.enter="addByUrl"
            />
            <select v-model="addType" class="chn-select" aria-label="Type de chaîne">
              <option :value="null">Type…</option>
              <option v-for="t in CHANNEL_TYPES" :key="t.value" :value="t.value">
                {{ t.label }}
              </option>
            </select>
            <button
              class="btn btn--sm btn--accent"
              :disabled="adding || !addUrl.trim()"
              @click="addByUrl"
            >
              {{ adding ? 'Ajout…' : 'Ajouter' }}
            </button>
          </div>
          <p v-if="addError" class="chn-add-error">
            <AdminIcon name="alert-triangle" :size="13" /> {{ addError }}
          </p>
        </details>
      </div>
    </div>

    <!-- Chaînes surveillées : liste paginée (socle .at-*). -->
    <div class="at-region chn-region">
      <div class="at-head">
        <h2 class="at-title">
          Chaînes surveillées
          <span v-if="total" class="at-count">{{ fmtInt(total) }}</span>
        </h2>
        <div class="at-seg" role="group" aria-label="Filtrer par état de surveillance">
          <button
            v-for="opt in WATCHED_FILTERS"
            :key="opt.label"
            class="at-seg-b"
            :class="{ active: watchedFilter === opt.value }"
            @click="setWatchedFilter(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>

      <div v-if="loading" class="at-empty">Chargement…</div>
      <div v-else-if="error" class="at-empty">Erreur de chargement des chaînes.</div>
      <div v-else-if="channels.length === 0" class="at-empty">Aucune chaîne.</div>

      <div v-else class="at-scroll">
        <table class="at-table">
          <thead>
            <tr>
              <th>Chaîne</th>
              <th>Plateforme</th>
              <th>Type</th>
              <th>Id externe</th>
              <th>Surveillée</th>
              <th>Exclue</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in channels" :key="item.id">
              <td data-label="Chaîne" data-lead>
                <a
                  v-if="item.external_id"
                  class="chn-yt-link"
                  :href="ytChannelUrl(item.external_id)"
                  target="_blank"
                  rel="noopener"
                  :aria-label="`Ouvrir ${item.name} sur YouTube`"
                >
                  <span class="at-id">{{ item.name }}</span>
                  <AdminIcon name="external" :size="12" />
                </a>
                <span v-else class="at-id">{{ item.name }}</span>
                <span class="chn-row-id">#{{ item.id }}</span>
              </td>
              <td data-label="Plateforme">
                <span class="at-source">{{ item.platform }}</span>
              </td>
              <td data-label="Type">
                <select
                  class="chn-select chn-select--sm"
                  :value="item.channel_type || ''"
                  :disabled="mutating[item.id]"
                  aria-label="Type de la chaîne"
                  @change="changeType(item, $event.target.value)"
                >
                  <option value="">Non défini</option>
                  <option v-for="t in CHANNEL_TYPES" :key="t.value" :value="t.value">
                    {{ t.label }}
                  </option>
                </select>
              </td>
              <td data-label="Id externe">
                <span v-if="item.external_id" class="at-tech">{{ item.external_id }}</span>
                <span v-else class="chn-muted">—</span>
              </td>
              <td data-label="Surveillée">
                <span class="at-pill" :class="item.watched ? 'at-pill--ok' : 'at-pill--neutral'">
                  {{ item.watched ? 'Oui' : 'Non' }}
                </span>
              </td>
              <td data-label="Exclue">
                <span class="at-pill" :class="item.excluded ? 'at-pill--err' : 'at-pill--neutral'">
                  {{ item.excluded ? 'Oui' : 'Non' }}
                </span>
              </td>
              <td data-act>
                <div class="chn-actions">
                  <button
                    class="btn btn--sm"
                    :disabled="mutating[item.id]"
                    @click="toggleWatched(item)"
                  >
                    {{ item.watched ? 'Ne plus surveiller' : 'Surveiller' }}
                  </button>
                  <button
                    class="btn btn--sm"
                    :disabled="mutating[item.id]"
                    @click="toggleExcluded(item)"
                  >
                    {{ item.excluded ? 'Réintégrer' : 'Exclure' }}
                  </button>
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

    <!-- Candidats : chaînes connues de la base (trackid_index) pas encore curées,
         triées par valeur de découverte (l'API les renvoie déjà ordonnées). Le nom
         est connu mais pas l'URL YouTube → l'admin la saisit pour la surveiller. -->
    <div class="at-region chn-region">
      <div class="at-head">
        <h2 class="at-title">
          Candidats
          <span v-if="candidates.length" class="at-count">{{ fmtInt(candidates.length) }}</span>
        </h2>
      </div>

      <div v-if="loadingCand" class="at-empty">Chargement…</div>
      <div v-else-if="errorCand" class="at-empty">Erreur de chargement des candidats.</div>
      <div v-else-if="candidates.length === 0" class="at-empty">Aucun candidat.</div>

      <div v-else class="at-scroll">
        <table class="at-table">
          <thead>
            <tr>
              <th>Chaîne</th>
              <th>Sets TrackID</th>
              <th>Couverts</th>
              <th>Ajouter</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in candidates" :key="c.name">
              <td data-label="Chaîne" data-lead>
                <span class="at-id">{{ c.name }}</span>
              </td>
              <td data-label="Sets TrackID">
                <span class="at-tech">{{ fmtInt(c.trackid_count) }}</span>
              </td>
              <td data-label="Couverts">
                <span class="at-tech">{{ fmtInt(c.set_count) }}</span>
              </td>
              <td data-label="Ajouter" data-stack>
                <div class="chn-cand-add">
                  <input
                    v-model="candidateUrls[c.name]"
                    class="chn-input chn-input--grow"
                    type="text"
                    placeholder="URL YouTube"
                    aria-label="URL YouTube de la chaîne candidate"
                    @keyup.enter="addCandidate(c)"
                  />
                  <button
                    class="btn btn--sm btn--accent"
                    :disabled="candAdding[c.name] || !candidateUrlFilled(c)"
                    @click="addCandidate(c)"
                  >
                    {{ candAdding[c.name] ? 'Ajout…' : 'Ajouter' }}
                  </button>
                </div>
                <p v-if="candErrors[c.name]" class="chn-add-error">
                  <AdminIcon name="alert-triangle" :size="13" /> {{ candErrors[c.name] }}
                </p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '../../utils/api.js'
import AdminIcon from './AdminIcon.vue'

const PER_PAGE = 50

// Types de chaîne (String libre côté back — pas d'enum). Le libellé UI est en FR.
const CHANNEL_TYPES = [
  { value: 'artist', label: 'Artiste' },
  { value: 'label', label: 'Label' },
  { value: 'organizer', label: 'Organisateur' },
  { value: 'radio', label: 'Radio' },
]

// Filtre sur GET /admin/channels ?watched= (bool | absent).
const WATCHED_FILTERS = [
  { label: 'Toutes', value: null },
  { label: 'Surveillées', value: true },
  { label: 'Non', value: false },
]

// ── Chaînes surveillées (liste paginée) ──
const channels = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const error = ref(false)
const watchedFilter = ref(null)
// channel.id → true pendant qu'une mutation d'override est en vol (désactive la ligne).
const mutating = reactive({})

const totalPages = computed(() => Math.ceil(total.value / PER_PAGE))

// ── Candidats (seed) ──
const candidates = ref([])
const loadingCand = ref(false)
const errorCand = ref(false)
// name → url saisie / erreur d'ajout / ajout en vol (état par candidat).
const candidateUrls = reactive({})
const candErrors = reactive({})
const candAdding = reactive({})

// ── Ajout d'une chaîne par URL (voie avancée) ──
const addUrl = ref('')
const addName = ref('')
const addType = ref(null)
const adding = ref(false)
const addError = ref('')

// ── Recherche YouTube (chemin d'ajout principal, add-by-search) ──
const searchQuery = ref('')
const searchResults = ref([])
const searching = ref(false)
// Vrai dès qu'une recherche a abouti → distingue « pas encore cherché » de
// « cherché, 0 résultat » pour l'état vide.
const searched = ref(false)
const searchError = ref('')
// channel_id → ajout d'un résultat en vol / erreur d'ajout inline.
const addingResult = reactive({})
const resultErrors = reactive({})

function fmtInt(n) {
  return Number(n || 0).toLocaleString('fr-FR')
}

function ytChannelUrl(externalId) {
  return `https://www.youtube.com/channel/${externalId}`
}

async function fetchChannels() {
  loading.value = true
  error.value = false
  try {
    const params = { page: page.value, page_size: PER_PAGE }
    if (watchedFilter.value != null) params.watched = watchedFilter.value
    const { data } = await api.get('/api/admin/channels', { params })
    channels.value = data.items
    total.value = data.total
  } catch {
    error.value = true
    channels.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function fetchCandidates() {
  loadingCand.value = true
  errorCand.value = false
  try {
    const { data } = await api.get('/api/admin/channels/candidates', { params: { limit: 50 } })
    candidates.value = data.items
  } catch {
    errorCand.value = true
    candidates.value = []
  } finally {
    loadingCand.value = false
  }
}

function setWatchedFilter(v) {
  if (watchedFilter.value === v) return
  watchedFilter.value = v
  page.value = 1
  fetchChannels()
}

function prevPage() {
  if (page.value <= 1) return
  page.value--
  fetchChannels()
}

function nextPage() {
  if (page.value >= totalPages.value) return
  page.value++
  fetchChannels()
}

// PATCH un override (watched/excluded/channel_type) et remplace la ligne EN PLACE
// avec l'item renvoyé. Sémantique PATCH : un champ absent n'est pas modifié — on
// n'envoie donc que la clé mutée.
async function patchChannel(item, body) {
  if (mutating[item.id]) return
  mutating[item.id] = true
  try {
    const { data } = await api.patch(`/api/admin/channels/${item.id}`, body)
    const idx = channels.value.findIndex((c) => c.id === item.id)
    if (idx !== -1) channels.value[idx] = data
  } catch {
    // Les erreurs réseau/serveur sont remontées par le toast de l'intercepteur api.
  } finally {
    mutating[item.id] = false
  }
}

function toggleWatched(item) {
  patchChannel(item, { watched: !item.watched })
}

function toggleExcluded(item) {
  patchChannel(item, { excluded: !item.excluded })
}

// Un null EXPLICITE efface le type côté back ; l'option vide renvoie "" → null.
function changeType(item, raw) {
  patchChannel(item, { channel_type: raw || null })
}

// Ajout hors seed : POST {url, name?, channel_type?}. Un 400 (URL irrésolvable) est
// affiché inline — l'intercepteur api ne toaste que les 5xx / erreurs réseau.
async function addByUrl() {
  const url = addUrl.value.trim()
  if (!url || adding.value) return
  adding.value = true
  addError.value = ''
  try {
    const body = { url }
    if (addName.value.trim()) body.name = addName.value.trim()
    if (addType.value) body.channel_type = addType.value
    await api.post('/api/admin/channels', body)
    addUrl.value = ''
    addName.value = ''
    addType.value = null
    page.value = 1
    await fetchChannels()
  } catch (e) {
    addError.value = e.response?.data?.detail || 'Ajout impossible'
  } finally {
    adding.value = false
  }
}

// Recherche YouTube : UNIQUEMENT au clic / Entrée (jamais à la frappe) — chaque
// appel coûte 100 unités de quota YouTube Data API. GET /admin/channels/search.
async function runSearch() {
  const q = searchQuery.value.trim()
  if (!q || searching.value) return
  searching.value = true
  searched.value = false
  searchError.value = ''
  try {
    const { data } = await api.get('/api/admin/channels/search', {
      params: { q, limit: 6 },
    })
    searchResults.value = data.items
    searched.value = true
  } catch (e) {
    searchResults.value = []
    // Un 4xx (ex. quota) s'affiche inline ; l'intercepteur api ne toaste que 5xx.
    searchError.value = e.response?.data?.detail || 'Recherche impossible'
  } finally {
    searching.value = false
  }
}

// Ajoute un résultat de recherche : son channel_id alimente le chemin d'ajout par
// URL existant (résolu côté serveur). En succès on vide les résultats et on
// rafraîchit la liste surveillée (la chaîne vient d'y entrer).
async function addResult(r) {
  if (addingResult[r.channel_id]) return
  addingResult[r.channel_id] = true
  resultErrors[r.channel_id] = ''
  try {
    await api.post('/api/admin/channels', { url: r.channel_id, name: r.title })
    searchResults.value = []
    searchQuery.value = ''
    searched.value = false
    page.value = 1
    await fetchChannels()
  } catch (e) {
    resultErrors[r.channel_id] = e.response?.data?.detail || 'Ajout impossible'
  } finally {
    addingResult[r.channel_id] = false
  }
}

function candidateUrlFilled(c) {
  return (candidateUrls[c.name] || '').trim().length > 0
}

// Ajoute un candidat comme chaîne surveillée : son nom est connu, l'admin fournit
// l'URL YouTube. En succès on retire le candidat de la liste et on rafraîchit la
// liste surveillée (le candidat vient d'y entrer).
async function addCandidate(c) {
  const url = (candidateUrls[c.name] || '').trim()
  if (!url || candAdding[c.name]) return
  candAdding[c.name] = true
  candErrors[c.name] = ''
  try {
    await api.post('/api/admin/channels', { url, name: c.name })
    candidates.value = candidates.value.filter((x) => x.name !== c.name)
    delete candidateUrls[c.name]
    page.value = 1
    await fetchChannels()
  } catch (e) {
    candErrors[c.name] = e.response?.data?.detail || 'Ajout impossible'
  } finally {
    candAdding[c.name] = false
  }
}

onMounted(() => {
  fetchChannels()
  fetchCandidates()
})
</script>

<style scoped>
/* Le wrap est le conteneur de requête du toolbar (un élément ne peut pas se
   requêter lui-même → le toolbar est restylé via le wrap). Les régions .at-* ont
   leur propre contexte de conteneur. */
.chn-wrap {
  container-type: inline-size;
  margin-bottom: var(--space-8);
}

/* ── Barre d'ajout : carte à bordure. ── */
.chn-toolbar {
  margin-bottom: var(--space-5);
  padding: var(--space-4);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}
.chn-toolbar-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.chn-toolbar-title {
  font: 600 var(--fs-title)/1.2 var(--font-ui);
  color: var(--ink);
}
.chn-toolbar-desc {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-2);
  text-wrap: pretty;
  max-width: 76ch;
}
.chn-add-form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-1);
}
.chn-add-error {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font: 400 var(--fs-xs)/1.3 var(--font-mono);
  color: var(--neg-ink);
}

/* ── Champs de saisie (calqués sur .aj-input d'AdminGenres). ── */
.chn-input {
  height: 38px;
  padding: 0 var(--space-2);
  background: var(--surface-2);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink);
  font: 400 var(--fs-input)/1 var(--font-mono);
}
.chn-input--grow {
  flex: 1;
  min-width: 220px;
}
.chn-input:focus {
  outline: 2px solid var(--accent);
  outline-offset: -1px;
}
.chn-select {
  height: 38px;
  padding: 0 var(--space-2);
  background: var(--surface-2);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink);
  font: 400 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
}
.chn-select:focus {
  outline: 2px solid var(--accent);
  outline-offset: -1px;
}
.chn-select--sm {
  height: 32px;
  font-size: var(--fs-table-sm);
}

/* ── Espacement entre régions. ── */
.chn-region {
  margin-top: var(--space-5);
}

/* ── Cellules de ligne. ── */
.chn-row-id {
  margin-left: var(--space-1);
  font: 400 var(--fs-nano)/1 var(--font-mono);
  color: var(--ink-3);
}
.chn-muted {
  color: var(--ink-3);
  font-size: var(--fs-table-sm);
}

/* ── Actions de ligne. ── */
.chn-actions {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  flex-wrap: wrap;
  justify-content: flex-end;
}

/* Ajout d'un candidat : champ URL extensible + bouton. */
.chn-cand-add {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
}

/* ── Recherche YouTube (add-by-search) ── */
.chn-search {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.chn-search-msg {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-3);
}
.chn-results {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.chn-result {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: var(--space-2);
  background: var(--surface-2);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
.chn-result-thumb {
  flex: none;
  width: 40px;
  height: 40px;
  border-radius: var(--r-pill);
  object-fit: cover;
  background: var(--surface-3);
}
.chn-result-thumb--empty {
  display: inline-block;
}
.chn-result-body {
  flex: 1;
  min-width: 160px;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
  overflow: hidden;
}
.chn-result-title {
  font: 600 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink);
}
.chn-result-desc {
  /* Tronquée à 2 lignes. */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font: 400 var(--fs-xs)/1.35 var(--font-ui);
  color: var(--ink-2);
}
.chn-result-open {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--r-sm);
  color: var(--ink-2);
}
.chn-result-open:hover {
  color: var(--ink);
  background: var(--surface-3);
}
.chn-result-err {
  flex-basis: 100%;
}

/* ── Lien ↗ YouTube sur une ligne surveillée ── */
.chn-yt-link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: inherit;
  text-decoration: none;
}
.chn-yt-link:hover {
  text-decoration: underline;
}
.chn-yt-link .admin-icon {
  color: var(--ink-3);
}

/* ── Voie avancée (URL directe) : bloc dépliable discret ── */
.chn-direct {
  margin-top: var(--space-1);
}
.chn-direct-desc {
  margin: var(--space-2) 0;
}

.btn:disabled {
  opacity: 0.5;
  cursor: default;
}

/* ── Responsive — palier unique 859 px. Le toolbar se requête via .chn-wrap ; les
   actions de ligne via .at-region (leur conteneur le plus proche). ── */
@container (max-width: 859px) {
  .chn-add-form {
    flex-direction: column;
    align-items: stretch;
  }
  .chn-input,
  .chn-input--grow,
  .chn-select {
    width: 100%;
    min-width: 0;
  }
  .chn-add-form .btn {
    width: 100%;
    min-height: var(--touch-min);
    justify-content: center;
  }
  /* En carte, les actions s'empilent (le socle donne déjà 100 % + 44 px aux
     boutons de [data-act]). */
  .chn-actions {
    flex-direction: column;
    align-items: stretch;
    justify-content: stretch;
  }
  .chn-cand-add {
    flex-direction: column;
    align-items: stretch;
  }
  .chn-cand-add .btn {
    min-height: var(--touch-min);
    justify-content: center;
  }
  /* Résultats de recherche : le corps peut rétrécir davantage avant que l'action
     ne passe à la ligne (le .chn-result reste en flex-wrap). */
  .chn-result-body {
    min-width: 120px;
  }
}
</style>

<template>
  <div class="sets-view">
    <div class="page-head">
      <div class="titles">
        <h1>Sets</h1>
        <div class="sub">
          {{ sets.length }} set{{ sets.length !== 1 ? 's' : '' }}
          <span v-if="mode !== 'all'" class="muted"
            >· {{ displayList.length }}
            {{ mode === 'liked' ? 'likés' : mode === 'disliked' ? 'dislikés' : 'à explorer' }}</span
          >
        </div>
      </div>
      <div class="head-tools">
        <SearchBox v-model="search" placeholder="Rechercher…" @update:modelValue="fetchSets" />
        <SegFilter
          v-model="mode"
          :options="[
            { value: 'all', label: 'Tous' },
            { value: 'liked', label: 'Liked', cls: 'liked' },
            { value: 'disliked', label: 'Disliked', cls: 'disliked' },
            { value: 'unrated', label: 'À explorer' },
          ]"
        />
        <button class="btn-add" :class="{ cancel: showForm }" @click="toggleForm">
          <span v-if="!showForm" class="plus">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="M12 5v14M5 12h14" stroke-linecap="round" />
            </svg>
          </span>
          <span class="addlbl">{{ showForm ? 'Annuler' : 'Ajouter' }}</span>
        </button>
      </div>
    </div>

    <!-- Add form -->
    <div v-if="showForm" class="addform">
      <div class="addcard">
        <div class="addtabs">
          <button class="addtab" :class="{ on: addMode === 'search' }" @click="addMode = 'search'">
            Rechercher
          </button>
          <button class="addtab" :class="{ on: addMode === 'url' }" @click="addMode = 'url'">
            URL
          </button>
        </div>

        <!-- Search mode -->
        <div v-if="addMode === 'search'">
          <div class="addrow">
            <input
              v-model="tdQuery"
              type="text"
              placeholder="Nom d'artiste, de DJ, d'event…"
              @keydown.enter="doTrackIDSearch"
              autofocus
            />
            <button class="btn-go" :disabled="tdSearching" @click="doTrackIDSearch">
              {{ tdSearching ? 'Recherche…' : 'Rechercher' }}
            </button>
          </div>
          <div v-if="tdResults.length" class="results">
            <div v-for="r in tdResults" :key="r.trackid_id" class="res">
              <div class="aw">
                <img v-if="r.artwork_url" :src="r.artwork_url" />
                <span v-else class="fallback-letter">{{ (r.title || '?')[0] }}</span>
              </div>
              <div class="rx">
                <div class="rt">{{ r.title }}</div>
                <div class="rm">
                  <template v-if="r.channel"
                    ><b>{{ r.channel }}</b></template
                  >
                  <template v-if="r.track_count"> · {{ r.track_count }} tracks</template>
                  <template v-if="r.created_on">
                    · {{ fmtDate(r.created_on?.slice(0, 10)) }}</template
                  >
                </div>
              </div>
              <button
                v-if="r.already_imported"
                class="btn-like liked"
                title="Déjà dans ta bibliothèque"
                aria-label="Déjà dans ta bibliothèque"
              >
                <svg viewBox="0 0 24 24">
                  <path
                    d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
                  />
                </svg>
              </button>
              <button
                v-else
                class="btn-like"
                :disabled="r._importing"
                title="Ajouter à ma bibliothèque"
                aria-label="Ajouter à ma bibliothèque"
                @click="doImportFromSearch(r)"
              >
                <svg viewBox="0 0 24 24">
                  <path
                    d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
                  />
                </svg>
              </button>
            </div>
          </div>
          <span v-if="formError" class="form-error">{{ formError }}</span>
        </div>

        <!-- URL mode -->
        <div v-if="addMode === 'url'">
          <div class="addrow">
            <input
              v-model="importUrl"
              type="text"
              placeholder="URL TrackID (ex : https://trackid.net/audiostream/…)"
              @keydown.enter="doImport"
              @input="formError = ''"
              autofocus
            />
            <button class="btn-go" :disabled="importing" @click="doImport">
              {{ importing ? 'Import…' : 'Importer' }}
            </button>
          </div>
          <span v-if="formError" class="form-error">{{ formError }}</span>
        </div>
      </div>
    </div>

    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="displayList.length === 0" class="state">Aucun set trouvé.</div>

    <div v-else class="table-wrap">
      <table class="tt">
        <colgroup>
          <col class="w-set" />
          <col class="w-date col-date" />
          <col class="w-tracks" />
          <col class="w-dur col-dur" />
          <col class="w-avis" />
        </colgroup>
        <thead>
          <tr>
            <th class="sortable" @click="toggleSort('title')">
              Set
              <span v-if="sortKey === 'title'" class="arr">{{
                sortDir === 'asc' ? '↑' : '↓'
              }}</span>
            </th>
            <th class="col-date sortable" @click="toggleSort('date')">
              Date
              <span v-if="sortKey === 'date'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th class="num sortable" @click="toggleSort('tracks')">
              Tracks
              <span v-if="sortKey === 'tracks'" class="arr">{{
                sortDir === 'asc' ? '↑' : '↓'
              }}</span>
            </th>
            <th class="num col-dur sortable" @click="toggleSort('duration')">
              Durée
              <span v-if="sortKey === 'duration'" class="arr">{{
                sortDir === 'asc' ? '↑' : '↓'
              }}</span>
            </th>
            <th class="end sortable" @click="toggleSort('avis')">
              Avis
              <span v-if="sortKey === 'avis'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in displayList"
            :key="s.id"
            :class="{
              liked: opinions.get('set', s.id) === 'liked',
              disliked: opinions.get('set', s.id) === 'disliked',
            }"
            @click="$router.push(`/set/${s.id}`)"
          >
            <td>
              <div class="td-track">
                <div class="aw">
                  <img
                    v-if="s.has_artwork"
                    :src="`/storage/set-artworks/${s.id}.jpg`"
                    :alt="s.title"
                  />
                  <span v-else class="fallback-letter">{{ (s.title || '?')[0] }}</span>
                </div>
                <div class="tx">
                  <div class="tt-title">{{ s.title }}</div>
                  <div v-if="s.artists.length" class="tt-art">{{ s.artists.join(', ') }}</div>
                </div>
              </div>
            </td>
            <td class="col-date">
              <span class="detect">{{ fmtDate(s.played_date) }}</span>
            </td>
            <td class="num">
              <RingPct :value="s.identified_tracks" :total="s.total_tracks" />
            </td>
            <td class="num col-dur">
              <span class="td-dur">{{ fmtMs(s.duration_ms) }}</span>
            </td>
            <td class="end td-avis" @click.stop>
              <LikeDislike
                :model-value="opinions.get('set', s.id)"
                @update:model-value="(v) => setOpinion(s.id, v)"
              />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../utils/api.js'
import { useRouter } from 'vue-router'
import { useOpinionsStore } from '../stores/opinions.js'
import { fmtMs, fmtDate } from '../utils/format'
import LikeDislike from '../components/LikeDislike.vue'
import SearchBox from '../components/SearchBox.vue'
import SegFilter from '../components/SegFilter.vue'
import RingPct from '../components/RingPct.vue'

const router = useRouter()
const opinions = useOpinionsStore()

const sets = ref([])
const loading = ref(false)
const search = ref('')
const mode = ref('all')
const showForm = ref(false)
const addMode = ref('search')
const importUrl = ref('')
const formError = ref('')
const importing = ref(false)
// TrackID search
const tdQuery = ref('')
const tdResults = ref([])
const tdSearching = ref(false)

// Sort
const sortKey = ref('date')
const sortDir = ref('desc')

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = key === 'title' ? 'asc' : 'desc'
  }
}

function sortValue(s, key) {
  if (key === 'title') return (s.title || '').toLowerCase()
  if (key === 'date') return s.played_date || ''
  if (key === 'tracks') return s.total_tracks ? s.identified_tracks / s.total_tracks : 0
  if (key === 'duration') return s.duration_ms || 0
  if (key === 'avis') {
    const op = opinions.get('set', s.id)
    if (op === 'liked') return 2
    if (op === 'disliked') return 1
    return 0
  }
  return 0
}

const displayList = computed(() => {
  let list
  if (mode.value === 'liked') {
    list = sets.value.filter((s) => opinions.get('set', s.id) === 'liked')
  } else if (mode.value === 'disliked') {
    list = sets.value.filter((s) => opinions.get('set', s.id) === 'disliked')
  } else if (mode.value === 'unrated') {
    list = sets.value.filter((s) => !opinions.get('set', s.id))
  } else {
    list = [...sets.value]
  }
  const dir = sortDir.value === 'asc' ? 1 : -1
  const key = sortKey.value
  list.sort((a, b) => {
    const va = sortValue(a, key)
    const vb = sortValue(b, key)
    if (va < vb) return -1 * dir
    if (va > vb) return 1 * dir
    return 0
  })
  return list
})

function toggleForm() {
  showForm.value = !showForm.value
  addMode.value = 'search'
  tdResults.value = []
  formError.value = ''
}

async function fetchSets() {
  loading.value = true
  try {
    const params = {}
    if (search.value.trim()) params.q = search.value.trim()
    const { data } = await api.get('/api/sets/', { params })
    sets.value = data.items
  } finally {
    loading.value = false
  }
}

async function doTrackIDSearch() {
  formError.value = ''
  if (!tdQuery.value.trim()) return
  tdSearching.value = true
  try {
    const { data } = await api.get('/api/sets/search', { params: { q: tdQuery.value.trim() } })
    tdResults.value = data
    if (!data.length) formError.value = 'Aucun résultat sur TrackID'
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Erreur recherche'
  } finally {
    tdSearching.value = false
  }
}

async function doImportFromSearch(result) {
  result._importing = true
  formError.value = ''
  try {
    const { data } = await api.post('/api/sets/import', { slug: result.slug })
    result.already_imported = true
    result._importing = false
    await opinions.set('set', data.id, 'liked')
    await fetchSets()
  } catch (e) {
    result._importing = false
    formError.value = e.response?.data?.detail || 'Erreur import'
  }
}

async function doImport() {
  formError.value = ''
  if (!importUrl.value.trim()) {
    formError.value = 'URL requise'
    return
  }
  importing.value = true
  try {
    const { data } = await api.post('/api/sets/import', { url: importUrl.value.trim() })
    importUrl.value = ''
    showForm.value = false
    router.push(`/set/${data.id}`)
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Erreur'
  } finally {
    importing.value = false
  }
}

async function setOpinion(setId, val) {
  await opinions.set('set', setId, val)
  await fetchSets()
}

onMounted(fetchSets)
</script>

<style scoped>
.sets-view {
  container-type: inline-size;
  min-height: 100%;
  max-width: var(--page-max-w);
  margin-inline: auto;
  width: 100%;
}

/* ============ PAGE HEAD ============ */
.titles h1 {
  margin: 0;
  font-size: var(--fs-xl);
  font-weight: 600;
  letter-spacing: -0.3px;
  color: var(--ink);
}
.sub {
  margin-top: var(--space-1);
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
}
.sub .muted {
  color: var(--ink-3);
}

.head-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

/* ============ BTN ADD ============ */
.btn-add {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  height: 38px;
  padding: 0 var(--space-4);
  border-radius: var(--r-sm);
  border: 1px solid transparent;
  background: var(--accent);
  color: var(--on-accent);
  font: 600 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-add:hover {
  background: var(--accent-hover);
}
.btn-add svg {
  width: 15px;
  height: 15px;
}
.btn-add.cancel {
  background: var(--surface);
  color: var(--ink-2);
  border-color: var(--line-2);
}
.btn-add.cancel .plus {
  display: none;
}
.btn-add.cancel:hover {
  color: var(--ink);
  border-color: var(--ink-3);
}

/* ============ ADD FORM ============ */
.addform {
  padding: 0 var(--page-px) var(--space-15);
}
.addcard {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-sm);
  padding: var(--space-15) var(--space-5) var(--space-5);
  margin-bottom: var(--space-2);
}
.addtabs {
  display: flex;
  gap: var(--space-6);
  border-bottom: 1px solid var(--line);
  margin-bottom: var(--space-4);
}
.addtab {
  border: 0;
  background: transparent;
  cursor: pointer;
  font: 500 var(--fs-base) var(--font-ui);
  color: var(--ink-3);
  padding: var(--space-4) var(--space-05) var(--space-3);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.addtab:hover {
  color: var(--ink-2);
}
.addtab.on {
  color: var(--accent-ink);
  border-bottom-color: var(--accent);
}
.addrow {
  display: flex;
  gap: var(--space-25);
}
.addrow input {
  flex: 1;
  min-width: 0;
  height: 42px;
  padding: 0 var(--space-4);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--bg);
  font: 400 var(--fs-input) var(--font-ui);
  color: var(--ink);
  outline: none;
}
.addrow input::placeholder {
  color: var(--ink-3);
}
.addrow input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.btn-go {
  height: 42px;
  padding: 0 var(--space-5);
  border: 0;
  border-radius: var(--r-sm);
  background: var(--accent);
  color: var(--on-accent);
  font: 600 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-go:hover {
  background: var(--accent-hover);
}
.btn-go:disabled {
  opacity: 0.5;
  cursor: default;
}
.form-error {
  display: block;
  margin-top: var(--space-25);
  font: 400 var(--fs-sm)/1 var(--font-mono);
  color: var(--neg-ink);
}

/* ============ BTN LIKE (résultats recherche) ============ */
.btn-like {
  width: 34px;
  height: 34px;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  cursor: pointer;
  padding: 0;
  transition:
    color 0.14s,
    border-color 0.14s,
    background 0.14s,
    transform 0.12s;
}
.btn-like svg {
  width: 16px;
  height: 16px;
  display: block;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
  pointer-events: none;
}
.btn-like:hover {
  color: var(--pos);
  border-color: var(--pos);
}
.btn-like:active {
  transform: scale(0.92);
}
.btn-like:disabled {
  opacity: 0.6;
  cursor: default;
}
.btn-like.liked {
  background: var(--pos-soft);
  border-color: transparent;
  color: var(--pos-ink);
  cursor: default;
}
.btn-like.liked svg {
  fill: var(--pos-ink);
  stroke: var(--pos-ink);
}
.btn-like.liked:hover {
  background: var(--pos-soft);
  border-color: transparent;
}

/* ============ SEARCH RESULTS ============ */
.results {
  margin-top: var(--space-4);
  max-height: 312px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.res {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-1);
  border-bottom: 1px solid var(--line);
}
.res:last-child {
  border-bottom: 0;
}
.res .aw {
  width: 40px;
  height: 40px;
  border-radius: var(--r-xs);
  flex: none;
  background: var(--surface-3);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.res .aw img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.rx {
  min-width: 0;
  flex: 1;
}
.rt {
  font: 500 var(--fs-base) var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rm {
  font: 500 var(--fs-xs)/1.4 var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: var(--space-05);
}
.rm b {
  color: var(--ink-2);
  font-weight: 500;
}

/* ============ TABLE ============ */
.table-wrap {
  padding: var(--space-1) var(--page-px) var(--space-8);
  overflow-x: auto;
}
table.tt {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  min-width: 440px;
}
table.tt col.w-set {
  width: auto;
}
table.tt col.w-date {
  width: 128px;
}
table.tt col.w-tracks {
  width: 116px;
}
table.tt col.w-dur {
  width: 110px;
}
table.tt col.w-avis {
  width: 100px;
}
table.tt thead th {
  font: 600 var(--fs-label)/1 var(--font-mono);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-3);
  text-align: left;
  padding: 0 var(--space-3) var(--space-25);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  user-select: none;
}
table.tt th.sortable {
  cursor: pointer;
}
table.tt th.sortable:hover {
  color: var(--ink-2);
}
table.tt th .arr {
  color: var(--accent-ink);
  margin-left: var(--space-1);
}
table.tt th.num,
table.tt td.num {
  text-align: center;
}
table.tt th.end,
table.tt td.end {
  text-align: right;
}
table.tt tbody tr {
  border-bottom: 1px solid var(--line);
  height: var(--row-h);
  cursor: pointer;
}
table.tt tbody tr:hover {
  background: var(--surface-2);
}
table.tt td {
  padding: 0 var(--space-3);
  vertical-align: middle;
}

/* ============ SET CELL (artwork + title + artists) ============ */
.td-track {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}
.td-track .aw {
  width: 38px;
  height: 38px;
  border-radius: var(--r-xs);
  flex: none;
  background: var(--surface-3);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.td-track .aw img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.fallback-letter {
  font: 600 var(--fs-title)/1 var(--font-ui);
  color: var(--ink-3);
  text-transform: uppercase;
}
.tx {
  min-width: 0;
  flex: 1;
}
.tt-title {
  font-size: var(--fs-table);
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tt-art {
  font-size: var(--fs-table-sm);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ============ DATE ============ */
.detect {
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--ink-2);
}

/* ============ DURATION ============ */
.td-dur {
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--ink-2);
}

/* ============ AVIS: hover-reveal LikeDislike ============ */
.td-avis :deep(.ld-btn) {
  opacity: 0;
  transition: opacity 0.14s;
}
table.tt tbody tr:hover .td-avis :deep(.ld-btn) {
  opacity: 1;
}
.td-avis :deep(.ld[data-state='liked'] .ld-btn.like),
.td-avis :deep(.ld[data-state='disliked'] .ld-btn.dislike) {
  opacity: 1;
}

/* ============ ROW AVIS STATES ============ */
table.tt tbody tr.liked {
  background: var(--pos-wash);
}
table.tt tbody tr.liked:hover {
  background: var(--pos-wash-2);
}
table.tt tbody tr.disliked td:not(.td-avis) {
  opacity: 0.42;
}
table.tt tbody tr.disliked:hover td:not(.td-avis) {
  opacity: 0.7;
}

/* ============ STATES ============ */
.state {
  padding: var(--space-10) var(--page-px);
  color: var(--ink-3);
  font: 400 var(--fs-base) var(--font-ui);
  font-style: italic;
}

/* ============ RESPONSIVE (container queries) ============ */
@container (max-width: 1040px) {
  .col-dur {
    display: none;
  }
}
@container (max-width: 820px) {
  .col-date {
    display: none;
  }
  .head-tools {
    width: 100%;
    margin-left: 0;
  }
  .search {
    flex: 1;
    min-width: 0;
    order: 3;
  }
}
@container (max-width: 640px) {
  .page-head,
  .addform {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  .table-wrap {
    padding: var(--space-1) var(--page-px-mobile) var(--space-6);
  }
  .addrow {
    flex-direction: column;
  }
  .btn-go {
    width: 100%;
  }
  /* Touch: always show avis buttons */
  .td-avis :deep(.ld-btn) {
    opacity: 1;
  }
  table.tt {
    min-width: 0;
  }
  table.tt col.w-tracks {
    width: 56px;
  }
  table.tt col.w-avis {
    width: 88px;
  }
}
@container (max-width: 600px) {
  :deep(.ring) .pct {
    display: none;
  }
}
</style>

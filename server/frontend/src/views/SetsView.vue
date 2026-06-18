<template>
  <div class="sets-view">
    <header class="view-header">
      <div>
        <h1 class="view-title">Sets</h1>
        <span class="view-sub">{{ displayList.length }} set{{ displayList.length !== 1 ? 's' : '' }}</span>
      </div>
      <div class="header-actions">
        <input
          v-model="search"
          class="search-input"
          placeholder="Rechercher…"
          @input="onSearch"
        />
        <div class="toggle-group">
          <button class="toggle-btn" :class="{ active: mode === 'all' }" @click="mode = 'all'">Tous</button>
          <button class="toggle-btn" :class="{ active: mode === 'followed' }" @click="mode = 'followed'">Suivis</button>
        </div>
        <button class="btn-add" @click="showForm = !showForm">
          {{ showForm ? 'Annuler' : '+ Ajouter' }}
        </button>
      </div>
    </header>

    <div v-if="showForm" class="add-form">
      <input
        v-model="importUrl"
        class="form-input"
        placeholder="URL TrackID  (ex: https://trackid.net/audiostream/...)"
        @keydown.enter="doImport"
        @input="formError = ''"
        autofocus
      />
      <button class="btn-confirm" :disabled="importing" @click="doImport">
        {{ importing ? 'Import…' : 'Importer' }}
      </button>
      <span v-if="formError" class="form-error">{{ formError }}</span>
    </div>

    <div v-if="loading" class="state">Chargement…</div>

    <div v-else-if="displayList.length === 0" class="state">Aucun set trouvé.</div>

    <div v-else class="table-wrap">
      <table class="st-table">
        <thead>
          <tr>
            <th class="col-cover" />
            <th class="col-title">Set</th>
            <th class="col-date">Date</th>
            <th class="col-tracks num">Tracks</th>
            <th class="col-dur num">Durée</th>
            <th class="col-action" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in displayList"
            :key="s.id"
            class="st-row"
            @click="$router.push(`/set/${s.id}`)"
          >
            <td class="col-cover">
              <div class="cover-thumb">
                <img v-if="s.has_artwork" :src="`/storage/set-artworks/${s.id}.jpg`" :alt="s.title" />
                <span v-else class="fallback-letter">{{ (s.title || '?')[0] }}</span>
              </div>
            </td>
            <td class="col-title">
              <span class="st-name">{{ s.title }}</span>
              <span v-if="s.artists.length" class="st-artists muted">{{ s.artists.join(', ') }}</span>
            </td>
            <td class="col-date">
              <span class="mono muted">{{ fmtDate(s.played_date) }}</span>
            </td>
            <td class="col-tracks num">
              <span class="mono">{{ s.identified_tracks }}/{{ s.total_tracks }}</span>
            </td>
            <td class="col-dur num">
              <span class="mono muted">{{ fmtMs(s.duration_ms) }}</span>
            </td>
            <td class="col-action" @click.stop>
              <button
                v-if="s.followed"
                class="btn-unfollow"
                @click="doUnfollow(s.id)"
              >Ne plus suivre</button>
              <button
                v-else
                class="btn-follow"
                @click="doFollow(s.id)"
              >Suivre</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { fmtMs, fmtDate } from '../utils/format'

const router = useRouter()
const auth = useAuthStore()

const sets = ref([])
const loading = ref(false)
const search = ref('')
const mode = ref('all')
const showForm = ref(false)
const importUrl = ref('')
const formError = ref('')
const importing = ref(false)
let debounceTimer = null

function authHeaders() {
  return auth.token ? { Authorization: `Bearer ${auth.token}` } : {}
}

const displayList = computed(() => {
  if (mode.value === 'followed') return sets.value.filter(s => s.followed)
  return sets.value
})

async function fetchSets() {
  loading.value = true
  try {
    const params = {}
    if (search.value.trim()) params.q = search.value.trim()
    const { data } = await axios.get('/api/sets/', { params })
    sets.value = data
  } finally {
    loading.value = false
  }
}

function onSearch() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(fetchSets, 300)
}

async function doImport() {
  formError.value = ''
  if (!importUrl.value.trim()) { formError.value = 'URL requise'; return }
  importing.value = true
  try {
    const { data } = await axios.post('/api/sets/import', { url: importUrl.value.trim() }, { headers: authHeaders() })
    importUrl.value = ''
    showForm.value = false
    router.push(`/set/${data.id}`)
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Erreur'
  } finally {
    importing.value = false
  }
}

async function doFollow(setId) {
  try {
    await axios.post(`/api/sets/${setId}/follow`, {}, { headers: authHeaders() })
    const s = sets.value.find(x => x.id === setId)
    if (s) s.followed = true
  } catch {}
}

async function doUnfollow(setId) {
  try {
    await axios.delete(`/api/sets/${setId}/follow`, { headers: authHeaders() })
    const s = sets.value.find(x => x.id === setId)
    if (s) s.followed = false
  } catch {}
}

onMounted(fetchSets)
</script>

<style scoped>
.sets-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: 960px;
  margin: 0 auto;
}
.view-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.view-title {
  font: 600 22px/1.1 var(--font-ui);
  letter-spacing: -0.02em;
  color: var(--ink);
}
.view-sub {
  font: 400 12px/1 var(--font-mono);
  color: var(--ink-3);
  margin-top: 4px;
  display: block;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.search-input {
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  padding: 8px 12px;
  font: inherit;
  font-size: 13px;
  color: var(--ink);
  outline: none;
  width: 180px;
}
.search-input::placeholder { color: var(--ink-3); }

/* Toggle */
.toggle-group {
  display: flex;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  overflow: hidden;
}
.toggle-btn {
  padding: 7px 14px;
  border: none;
  background: var(--surface);
  color: var(--ink-3);
  font: 500 12px/1 var(--font-ui);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.toggle-btn:not(:last-child) { border-right: 1px solid var(--line-2); }
.toggle-btn:hover { background: var(--surface-2); color: var(--ink-2); }
.toggle-btn.active {
  background: var(--accent-soft);
  color: var(--accent-ink);
}

.btn-add {
  padding: 8px 16px;
  border-radius: var(--r-sm);
  border: 1px solid var(--accent);
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
  transition: background 0.12s;
  white-space: nowrap;
}
.btn-add:hover { background: var(--accent); color: var(--on-accent); }

/* Add form */
.add-form {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
  padding: 14px 16px;
  background: var(--surface-2);
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  flex-wrap: wrap;
}
.form-input {
  flex: 1;
  min-width: 280px;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  padding: 8px 12px;
  font: inherit;
  font-size: 13px;
  color: var(--ink);
  outline: none;
}
.form-input::placeholder { color: var(--ink-3); }
.btn-confirm {
  padding: 8px 18px;
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
  transition: opacity 0.12s;
}
.btn-confirm:disabled { opacity: 0.5; cursor: default; }
.form-error {
  font: 400 12px/1 var(--font-mono);
  color: var(--neg-ink, #c0392b);
  width: 100%;
}

/* Table */
.table-wrap { overflow-x: auto; }
.st-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
  table-layout: fixed;
}
.st-table thead th {
  text-align: left;
  padding: 0 14px 12px;
  font: 500 10.5px/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
.st-table thead th.num { text-align: right; }
.st-table tbody td {
  height: 58px;
  padding: 0 14px;
  vertical-align: middle;
  border-bottom: 1px solid var(--line);
  overflow: hidden;
}
.st-table tbody tr:last-child td { border-bottom: none; }
.st-row { cursor: pointer; }
.st-row:hover td { background: var(--surface-2); }

.col-cover  { width: 54px; padding: 0 8px !important; }
.col-title  { width: auto; min-width: 200px; }
.col-date   { width: 100px; }
.col-tracks { width: 80px; }
.col-dur    { width: 80px; }
.col-action { width: 120px; text-align: right; }

/* Cover */
.cover-thumb {
  width: 40px; height: 40px;
  border-radius: var(--r-xs);
  border: 1px solid var(--line);
  overflow: hidden;
  background: var(--surface-2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
.cover-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.fallback-letter {
  font: 600 16px/1 var(--font-ui);
  color: var(--ink-3);
  text-transform: uppercase;
}

/* Title cell */
.st-name {
  display: block;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.st-artists {
  display: block;
  font-size: 12px;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Action buttons */
.btn-follow {
  padding: 5px 14px;
  border-radius: var(--r-sm);
  border: 1px solid var(--accent);
  background: var(--accent);
  color: var(--on-accent);
  font: 500 11px/1 var(--font-ui);
  cursor: pointer;
  transition: opacity 0.12s;
  white-space: nowrap;
}
.btn-follow:hover { opacity: 0.85; }

.btn-unfollow {
  padding: 5px 10px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  font: 500 11px/1 var(--font-ui);
  cursor: pointer;
  transition: color 0.12s, border-color 0.12s;
  white-space: nowrap;
}
.btn-unfollow:hover {
  color: var(--neg-ink, #c0392b);
  border-color: var(--neg-ink, #c0392b);
}

.num { text-align: right; }
.mono { font-family: var(--font-mono); }
.muted { color: var(--ink-3); }
.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
}
</style>

<template>
  <div class="watchlist-view">
    <header class="view-header">
      <div>
        <h1 class="view-title">Playlists</h1>
        <span class="view-sub">Playlists Deezer surveillées par le Radar</span>
      </div>
      <div class="header-actions">
        <div class="toggle-group">
          <button
            class="toggle-btn" :class="{ active: mode === 'followed' }"
            @click="mode = 'followed'"
          >Suivies</button>
          <button
            class="toggle-btn" :class="{ active: mode === 'browse' }"
            @click="mode = 'browse'"
          >Toutes</button>
        </div>
        <button class="btn-add" @click="showForm = !showForm">
          {{ showForm ? 'Annuler' : '+ Ajouter' }}
        </button>
      </div>
    </header>

    <div v-if="showForm" class="add-form">
      <input
        v-model="inputValue"
        class="form-input"
        placeholder="URL ou ID Deezer  (ex: https://www.deezer.com/playlist/1234567)"
        @keydown.enter="addPlaylist"
        @input="formError = ''"
        autofocus
      />
      <button class="btn-confirm" :disabled="adding" @click="addPlaylist">
        {{ adding ? 'Ajout…' : 'Suivre' }}
      </button>
      <span v-if="formError" class="form-error">{{ formError }}</span>
    </div>

    <div v-if="loading" class="state">Chargement…</div>

    <div v-else-if="displayList.length === 0 && !showForm" class="empty-state">
      <template v-if="mode === 'followed'">
        <p class="empty-text">Aucune playlist suivie.</p>
        <p class="empty-sub">Ajoutez une playlist Deezer pour alimenter le Radar.</p>
        <button class="btn-add" @click="showForm = true">+ Ajouter une playlist</button>
      </template>
      <template v-else>
        <p class="empty-text">Aucune playlist dans le système.</p>
      </template>
    </div>

    <div v-else-if="displayList.length > 0" class="table-wrap">
      <table class="pl-table">
        <thead>
          <tr>
            <th class="col-cover" />
            <th class="col-title">Playlist</th>
            <th class="col-owner">Créateur</th>
            <th class="col-tracks num">Tracks</th>
            <th class="col-crawled">Dernier crawl</th>
            <th class="col-action" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="pl in displayList" :key="pl.id">
            <td class="col-cover">
              <div class="cover-thumb">
                <img v-if="pl.has_artwork" :src="`/storage/catalog-artworks/${pl.id}.jpg`" :alt="pl.title" />
              </div>
            </td>
            <td class="col-title">
              <span class="pl-title">{{ pl.title || pl.external_id }}</span>
              <span class="pl-id mono muted">{{ pl.external_id }}</span>
            </td>
            <td class="col-owner"><span class="muted">{{ pl.owner || '—' }}</span></td>
            <td class="col-tracks num"><span class="mono">{{ pl.track_count ?? '—' }}</span></td>
            <td class="col-crawled">
              <span class="mono muted">{{ formatCrawled(pl.last_crawled_at) }}</span>
            </td>
            <td class="col-action">
              <div class="action-btns">
                <template v-if="mode === 'followed' || pl.followed">
                  <button
                    class="btn-crawl"
                    :disabled="crawling[pl.id] || isCooldown(pl)"
                    :title="isCooldown(pl) ? cooldownLabel(pl) : 'Lancer un crawl maintenant'"
                    @click="triggerCrawl(pl)"
                  >{{ crawling[pl.id] ? 'Crawl en cours…' : isCooldown(pl) ? cooldownLabel(pl) : 'Crawl now' }}</button>
                  <button class="btn-unfollow" @click="unfollow(pl.id)">Ne plus suivre</button>
                </template>
                <template v-else>
                  <button
                    class="btn-follow"
                    :disabled="following[pl.id]"
                    @click="followPlaylist(pl.id)"
                  >{{ following[pl.id] ? 'Suivi…' : 'Suivre' }}</button>
                </template>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, reactive } from 'vue'
import axios from 'axios'

const COOLDOWN_MS = 12 * 3600 * 1000

const playlists = ref([])
const browsePlaylists = ref([])
const loading = ref(false)
const showForm = ref(false)
const inputValue = ref('')
const formError = ref('')
const adding = ref(false)
const mode = ref('followed')
const crawling = reactive({})
const following = reactive({})
const pollTimers = {}

const displayList = computed(() => {
  if (mode.value === 'followed') return playlists.value
  return browsePlaylists.value
})

function isCooldown(pl) {
  if (!pl.last_crawled_at) return false
  return Date.now() - new Date(pl.last_crawled_at).getTime() < COOLDOWN_MS
}

function cooldownLabel(pl) {
  if (!pl.last_crawled_at) return ''
  const remaining = COOLDOWN_MS - (Date.now() - new Date(pl.last_crawled_at).getTime())
  if (remaining <= 0) return ''
  const h = Math.floor(remaining / 3600000)
  const m = Math.floor((remaining % 3600000) / 60000)
  return `${h}h${String(m).padStart(2, '0')} restantes`
}

function extractDeezerId(input) {
  const s = input.trim()
  const match = s.match(/playlist\/(\d+)/)
  if (match) return match[1]
  if (/^\d+$/.test(s)) return s
  return null
}

async function fetchPlaylists() {
  loading.value = true
  try {
    const [followed, all] = await Promise.all([
      axios.get('/api/watchlist/'),
      axios.get('/api/watchlist/browse'),
    ])
    playlists.value = followed.data
    browsePlaylists.value = all.data
  } finally {
    loading.value = false
  }
}

async function addPlaylist() {
  formError.value = ''
  const id = extractDeezerId(inputValue.value)
  if (!id) {
    formError.value = 'URL ou ID invalide'
    return
  }
  adding.value = true
  try {
    const { data } = await axios.post('/api/watchlist/', { external_id: id, source: 'deezer' })
    inputValue.value = ''
    showForm.value = false
    await fetchPlaylists()
    startPolling(data.id)
  } catch (e) {
    if (e.response?.status === 409) {
      formError.value = 'Playlist déjà suivie'
    } else {
      formError.value = 'Erreur lors de l\'ajout'
    }
  } finally {
    adding.value = false
  }
}

async function unfollow(id) {
  await axios.delete(`/api/watchlist/${id}`)
  await fetchPlaylists()
}

async function followPlaylist(id) {
  following[id] = true
  try {
    await axios.post(`/api/watchlist/${id}/follow`)
    await fetchPlaylists()
    startPolling(id)
  } catch (e) {
    if (e.response?.status === 409) {
      await fetchPlaylists()
    }
  } finally {
    following[id] = false
  }
}

async function triggerCrawl(pl) {
  crawling[pl.id] = true
  try {
    await axios.post(`/api/watchlist/${pl.id}/crawl`)
    startPolling(pl.id, pl.last_crawled_at)
  } catch (e) {
    if (e.response?.status === 429) {
      await fetchPlaylists()
    }
    crawling[pl.id] = false
  }
}

function startPolling(playlistId, oldCrawledAt) {
  crawling[playlistId] = true
  stopPolling(playlistId)
  let attempts = 0
  const maxAttempts = 60 // 5min max (5s * 60)
  pollTimers[playlistId] = setInterval(async () => {
    attempts++
    if (attempts >= maxAttempts) {
      stopPolling(playlistId)
      crawling[playlistId] = false
      return
    }
    try {
      const { data } = await axios.get('/api/watchlist/browse')
      const updated = data.find(p => p.id === playlistId)
      if (updated && updated.last_crawled_at !== oldCrawledAt) {
        stopPolling(playlistId)
        crawling[playlistId] = false
        playlists.value = playlists.value.map(p => p.id === playlistId ? { ...p, ...updated } : p)
        browsePlaylists.value = data
      }
    } catch {}
  }, 5000)
}

function stopPolling(playlistId) {
  if (pollTimers[playlistId]) {
    clearInterval(pollTimers[playlistId])
    delete pollTimers[playlistId]
  }
}

function formatCrawled(iso) {
  if (!iso) return 'jamais'
  const d = new Date(iso)
  const now = new Date()
  const diffDays = Math.floor((now - d) / 86400000)
  if (diffDays === 0) return "aujourd'hui"
  if (diffDays === 1) return 'il y a 1j'
  return `il y a ${diffDays}j`
}

onMounted(fetchPlaylists)
onUnmounted(() => Object.keys(pollTimers).forEach(stopPolling))
</script>

<style scoped>
.watchlist-view {
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

/* Toggle group */
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

/* Empty state */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--ink-3);
}
.empty-text {
  font: 500 15px/1.4 var(--font-ui);
  color: var(--ink-2);
  margin-bottom: 6px;
}
.empty-sub {
  font: 400 13px/1.4 var(--font-ui);
  margin-bottom: 20px;
}

/* Table */
.table-wrap { overflow-x: auto; }
.pl-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
  table-layout: fixed;
}
.pl-table thead th {
  text-align: left;
  padding: 0 14px 12px;
  font: 500 10.5px/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
.pl-table thead th.num { text-align: right; }
.pl-table tbody td {
  height: 58px;
  padding: 0 14px;
  vertical-align: middle;
  border-bottom: 1px solid var(--line);
  overflow: hidden;
}
.pl-table tbody tr:hover td { background: var(--surface-2); }
.pl-table tbody tr:last-child td { border-bottom: none; }

/* Column widths */
.col-cover  { width: 54px; padding: 0 8px !important; }
.col-title  { width: auto; min-width: 180px; }
.col-owner  { width: 140px; }
.col-tracks { width: 70px; }
.col-crawled { width: 110px; }
.col-action { width: 220px; text-align: right; }

/* Cover */
.cover-thumb {
  width: 40px; height: 40px;
  border-radius: var(--r-xs);
  border: 1px solid var(--line);
  overflow: hidden;
  background: repeating-linear-gradient(135deg, var(--surface-2) 0 5px, var(--surface-3) 5px 10px);
  flex: none;
}
.cover-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }

/* Playlist title cell */
.pl-title {
  display: block;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pl-id {
  display: block;
  font-size: 11px;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Cells */
.num { text-align: right; }
.mono { font-family: var(--font-mono); }
.muted { color: var(--ink-3); }

/* Action buttons */
.action-btns {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}
.btn-crawl {
  padding: 5px 10px;
  border-radius: var(--r-sm);
  border: 1px solid var(--accent);
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 500 11px/1 var(--font-ui);
  cursor: pointer;
  transition: background 0.12s;
  white-space: nowrap;
}
.btn-crawl:hover:not(:disabled) { background: var(--accent); color: var(--on-accent); }
.btn-crawl:disabled { opacity: 0.45; cursor: default; }

.btn-unfollow {
  padding: 5px 10px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  font: 500 11px/1 var(--font-ui);
  cursor: pointer;
  transition: color 0.12s, background 0.12s, border-color 0.12s;
  white-space: nowrap;
}
.btn-unfollow:hover {
  color: var(--neg-ink, #c0392b);
  border-color: var(--neg-ink, #c0392b);
  background: var(--surface-2);
}

.btn-follow {
  padding: 5px 14px;
  border-radius: var(--r-sm);
  border: 1px solid var(--accent);
  background: var(--accent);
  color: var(--on-accent);
  font: 500 12px/1 var(--font-ui);
  cursor: pointer;
  transition: opacity 0.12s;
  white-space: nowrap;
}
.btn-follow:hover { opacity: 0.85; }
.btn-follow:disabled { opacity: 0.5; cursor: default; }

.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
}
</style>

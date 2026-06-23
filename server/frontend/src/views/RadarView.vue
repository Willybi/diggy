<template>
  <div class="radar-view">
    <header class="page-head">
      <div class="titles">
        <h1>Radar</h1>
        <div class="sub">Recommandations · {{ allCount }} nouveautés détectées</div>
      </div>
      <div class="head-tools">
        <label class="search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2" stroke-linecap="round"/></svg>
          <input v-model="search" type="text" placeholder="Artiste ou titre…" @input="onSearch" />
        </label>
      </div>
    </header>

    <div class="tabsbar">
      <div class="tabs">
        <button class="tab" :class="{ on: activeTab === 'all' }" @click="setTab('all')">
          Tous <span class="cnt">{{ allCount }}</span>
        </button>
        <button class="tab liked" :class="{ on: activeTab === 'liked' }" @click="setTab('liked')">
          <span class="ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20s-7-4.4-7-9.3A3.7 3.7 0 0 1 12 8a3.7 3.7 0 0 1 7 2.7C19 15.6 12 20 12 20z" stroke-linejoin="round"/></svg></span>
          Liked <span class="cnt">{{ counts.added || 0 }}</span>
        </button>
        <button class="tab disliked" :class="{ on: activeTab === 'disliked' }" @click="setTab('disliked')">
          <span class="ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M7 10.5V19a1 1 0 0 0 1.5.9l1.2-.7a2 2 0 0 0 1-1.4l.6-3.3h4.9a2 2 0 0 0 2-2.4l-1-5A2 2 0 0 0 14.2 3H7M7 10.5H4.5a1.5 1.5 0 0 1-1.5-1.5v-4A1.5 1.5 0 0 1 4.5 3.5H7z" stroke-linejoin="round"/></svg></span>
          Disliked <span class="cnt">{{ counts.ignored || 0 }}</span>
        </button>
      </div>
      <div class="recency">
        <span class="rlbl">Détecté depuis</span>
        <div class="seg-rec">
          <button v-for="r in recencyOptions" :key="r.value"
            :class="{ on: recency === r.value }"
            @click="setRecency(r.value)"
          >{{ r.label }}</button>
        </div>
      </div>
    </div>

    <div v-if="loading && !items.length" class="state">Chargement…</div>
    <div v-else-if="!total && !loading" class="state">Aucun track dans ce filtre.</div>
    <template v-else>
      <div class="table-wrap">
        <table class="tt">
          <colgroup>
            <col class="w-play">
            <col class="w-track">
            <col class="w-style col-style">
            <col class="w-source col-source">
            <col class="w-detect col-detect">
            <col class="w-bpm col-bpm">
            <col class="w-key col-key">
            <col class="w-act">
          </colgroup>
          <thead>
            <tr>
              <th class="c-play"></th>
              <th class="sortable" :class="{ 'is-sorted': sortKey === 'title' }" @click="sort('title')">
                Track <span v-if="sortKey === 'title'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-style sortable" :class="{ 'is-sorted': sortKey === 'genre' }" @click="sort('genre')">
                Style <span v-if="sortKey === 'genre'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-source sortable" :class="{ 'is-sorted': sortKey === 'playlist_title' }" @click="sort('playlist_title')">
                Source <span v-if="sortKey === 'playlist_title'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-detect sortable" :class="{ 'is-sorted': sortKey === 'detected_at' }" @click="sort('detected_at')">
                Détecté <span v-if="sortKey === 'detected_at'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="num sortable col-bpm" :class="{ 'is-sorted': sortKey === 'bpm' }" @click="sort('bpm')">
                BPM <span v-if="sortKey === 'bpm'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="num col-key sortable" :class="{ 'is-sorted': sortKey === 'key' }" @click="sort('key')">
                Key <span v-if="sortKey === 'key'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="end">Avis</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in items" :key="t.catalog_id"
              :class="{
                playing: player.isCurrent(t.catalog_id),
                liked: uiStatus(t) === 'liked',
                disliked: uiStatus(t) === 'disliked',
              }"
            >
              <td class="c-play">
                <span
                  class="pbtn"
                  :class="{
                    'pbtn--playing': player.isCurrent(t.catalog_id),
                    'pbtn--disabled': !t.has_preview,
                  }"
                  @click="t.has_preview && player.play({ id: t.catalog_id, catalog_id: t.catalog_id, title: t.title, artist: t.artist, bpm: t.bpm, key: t.key })"
                >
                  <svg v-if="!player.isCurrent(t.catalog_id)" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>
                  <svg v-else viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="5" width="3.4" height="14" rx="1"/><rect x="13.6" y="5" width="3.4" height="14" rx="1"/></svg>
                </span>
              </td>
              <td>
                <div class="td-track">
                  <span class="aw">
                    <img v-if="t.has_artwork" :src="`/storage/catalog-artworks/${t.catalog_id}.jpg`" :alt="t.title" />
                  </span>
                  <span class="tx">
                    <RouterLink :to="`/catalog/${t.catalog_id}`" class="tt-title-link">
                      <div class="tt-title">{{ t.title }}</div>
                    </RouterLink>
                    <div class="tt-art">{{ t.artist }}</div>
                  </span>
                </div>
              </td>
              <td class="col-style">
                <StyleTag v-if="t.genre" :name="t.genre" />
                <span v-else class="td-empty">—</span>
              </td>
              <td class="col-source">
                <span v-if="t.playlist_title" class="src" :title="t.playlist_title">
                  <span class="ic">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h11M4 12h11M4 17h7" stroke-linecap="round"/><circle cx="18.5" cy="15.5" r="2.5"/><path d="M21 15.5V9l-2 .6" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  </span>
                  <span class="meta">
                    <span class="nm">{{ t.playlist_title }}</span>
                    <span class="kind">Playlist</span>
                  </span>
                </span>
                <span v-else class="td-empty">—</span>
              </td>
              <td class="col-detect">
                <span class="detect">{{ fmtRelative(t.detected_at) }}</span>
              </td>
              <td class="num col-bpm">
                <span :class="t.bpm != null ? 'td-bpm' : 'td-empty'">{{ t.bpm != null ? Math.round(t.bpm) : '—' }}</span>
              </td>
              <td class="num col-key">
                <span :class="t.key ? 'td-key' : 'td-empty'">{{ t.key || '—' }}</span>
              </td>
              <td class="end c-act">
                <span class="acts">
                  <span
                    class="act dislike"
                    :class="{ on: uiStatus(t) === 'disliked' }"
                    title="Dislike"
                    @click="toggleAction(t, 'disliked')"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M7 10.5V19a1 1 0 0 0 1.5.9l1.2-.7a2 2 0 0 0 1-1.4l.6-3.3h4.9a2 2 0 0 0 2-2.4l-1-5A2 2 0 0 0 14.2 3H7M7 10.5H4.5a1.5 1.5 0 0 1-1.5-1.5v-4A1.5 1.5 0 0 1 4.5 3.5H7z" stroke-linejoin="round"/></svg>
                  </span>
                  <span
                    class="act like"
                    :class="{ on: uiStatus(t) === 'liked' }"
                    title="Like"
                    @click="toggleAction(t, 'liked')"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20s-7-4.4-7-9.3A3.7 3.7 0 0 1 12 8a3.7 3.7 0 0 1 7 2.7C19 15.6 12 20 12 20z" stroke-linejoin="round"/></svg>
                  </span>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="totalPages > 1" class="pagination">
        <button class="page-btn" :disabled="page === 1" @click="goTo(page - 1)">←</button>
        <span class="page-info">{{ page }} / {{ totalPages }}</span>
        <button class="page-btn" :disabled="page === totalPages" @click="goTo(page + 1)">→</button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import axios from 'axios'
import { useAudioPlayer } from '../stores/audioPlayer'
import StyleTag from '../components/StyleTag.vue'

const PAGE_SIZE = 50

const player = useAudioPlayer()

const items     = ref([])
const total     = ref(0)
const loading   = ref(false)
const search    = ref('')
const page      = ref(1)
const sortKey   = ref('detected_at')
const sortDir   = ref('desc')
const activeTab = ref('all')
const counts    = ref({})
const recency   = ref(null)

let searchTimer = null
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

const allCount = computed(() => {
  const c = counts.value
  return (c.new || 0) + (c.seen || 0) + (c.added || 0) + (c.ignored || 0)
})

const recencyOptions = [
  { value: 24,   label: '24 h' },
  { value: 168,  label: '7 j' },
  { value: 720,  label: '30 j' },
  { value: 2160, label: '90 j' },
  { value: null, label: 'Tout' },
]

/* Backend uses added/ignored — UI shows liked/disliked */
const STATUS_TO_API = { liked: 'added', disliked: 'ignored' }
const API_TO_UI = { added: 'liked', ignored: 'disliked' }

function uiStatus(track) {
  return API_TO_UI[track.status] || track.status
}

function fmtRelative(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `il y a ${Math.max(1, mins)} min`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `il y a ${hours} h`
  const days = Math.floor(hours / 24)
  if (days < 30) return `il y a ${days} j`
  const months = Math.floor(days / 30)
  return `il y a ${months} mois`
}

function buildParams() {
  const params = { skip: (page.value - 1) * PAGE_SIZE, limit: PAGE_SIZE }
  if (activeTab.value === 'liked') params.status = 'added'
  else if (activeTab.value === 'disliked') params.status = 'ignored'
  if (search.value) params.search = search.value
  if (sortKey.value) params.sort = sortKey.value
  if (sortDir.value) params.order = sortDir.value
  if (recency.value) {
    const since = new Date(Date.now() - recency.value * 3600000)
    params.detected_after = since.toISOString()
  }
  return params
}

async function fetchPage() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/radar/full', { params: buildParams() })
    items.value = data.items
    total.value = data.total
    counts.value = data.counts || {}
  } finally {
    loading.value = false
  }
}

function goTo(p) {
  page.value = p
  fetchPage()
}

function setTab(key) {
  activeTab.value = key
  page.value = 1
  fetchPage()
}

function setRecency(val) {
  recency.value = val
  page.value = 1
  fetchPage()
}

function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    fetchPage()
  }, 300)
}

function sort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'desc'
  }
  page.value = 1
  fetchPage()
}

async function toggleAction(track, action) {
  const current = uiStatus(track)
  const newStatus = current === action ? 'new' : (STATUS_TO_API[action] || action)
  try {
    await axios.patch(`/api/radar/${track.catalog_id}/state`, { status: newStatus })
    track.status = newStatus === 'new' ? 'new' : newStatus
    fetchPage()
  } catch { /* ignore */ }
}

onMounted(fetchPage)
</script>

<style scoped>
/* ============ LAYOUT ============ */
.radar-view {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.page-head {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  padding: 26px 30px 18px;
  flex-wrap: wrap;
}
.titles h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.3px;
}
.sub {
  margin-top: 5px;
  font: 500 13px/1 var(--font-mono);
  color: var(--ink-2);
}
.head-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
}
.search {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  padding: 0 12px;
  height: 38px;
  min-width: 230px;
}
.search svg {
  width: 16px;
  height: 16px;
  color: var(--ink-3);
  flex: none;
}
.search input {
  border: 0;
  background: transparent;
  outline: none;
  width: 100%;
  font: 400 14px var(--font-ui);
  color: var(--ink);
}
.search input::placeholder { color: var(--ink-3); }

/* ============ TABS (Tous / New / Liked / Disliked) ============ */
.tabsbar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  padding: 4px 30px 14px;
  border-bottom: 1px solid var(--line);
}
.tabs { display: flex; gap: 4px; }
.tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 13px;
  border-radius: var(--r-sm);
  font: 500 14px var(--font-ui);
  color: var(--ink-2);
  cursor: pointer;
  line-height: 1;
  border: 0;
  background: transparent;
}
.tab:hover { background: var(--surface-2); color: var(--ink); }
.tab.on { background: var(--accent-soft); color: var(--accent-ink); }
.cnt { font: 500 11.5px/1 var(--font-mono); color: var(--ink-3); }
.tab.on .cnt { color: var(--accent-ink); }
.tab.liked.on { background: var(--pos-soft); color: var(--pos-ink); }
.tab.liked.on .cnt { color: var(--pos-ink); }
.tab.disliked.on { background: var(--neg-soft); color: var(--neg-ink); }
.tab.disliked.on .cnt { color: var(--neg-ink); }
.ic { display: inline-flex; }
.ic svg { width: 15px; height: 15px; }

/* recency filter — visible only on New tab */
.recency {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}
.rlbl {
  font: 600 10px/1 var(--font-mono);
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.seg-rec {
  display: flex;
  gap: 2px;
  background: var(--surface-2);
  padding: 3px;
  border-radius: var(--r-sm);
}
.seg-rec button {
  border: 0;
  background: transparent;
  color: var(--ink-2);
  font: 500 12px/1 var(--font-mono);
  padding: 7px 11px;
  border-radius: var(--r-xs);
  cursor: pointer;
}
.seg-rec button:hover { color: var(--ink); }
.seg-rec button.on {
  background: var(--surface);
  color: var(--accent-ink);
  box-shadow: var(--shadow-sm);
}

/* ============ TABLE ============ */
.table-wrap {
  padding: 4px 30px 30px;
  overflow-x: auto;
}
table.tt {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  min-width: 440px;
}
table.tt col.w-play   { width: 44px; }
table.tt col.w-track  { width: auto; }
table.tt col.w-style  { width: 150px; }
table.tt col.w-source { width: 224px; }
table.tt col.w-detect { width: 104px; }
table.tt col.w-bpm    { width: 72px; }
table.tt col.w-key    { width: 64px; }
table.tt col.w-act    { width: 92px; }

table.tt thead th {
  position: sticky;
  top: 0;
  font: 600 10.5px/1 var(--font-mono);
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-3);
  text-align: left;
  padding: 0 14px 11px;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  user-select: none;
}
table.tt th.num, table.tt td.num { text-align: center; }
table.tt th.end, table.tt td.end { text-align: right; }
table.tt th.sortable { cursor: pointer; }
table.tt th.sortable:hover { color: var(--ink-2); }
table.tt th.is-sorted { color: var(--accent-ink); }
.arr { color: var(--accent-ink); margin-left: 4px; }

table.tt tbody tr {
  border-bottom: 1px solid var(--line);
  height: var(--row-h);
}
table.tt tbody tr:hover { background: var(--surface-2); }
table.tt tbody tr.playing { background: var(--accent-wash); }
table.tt tbody tr.playing:hover { background: var(--accent-soft); }
table.tt td {
  padding: 0 14px;
  vertical-align: middle;
}

/* ============ PLAY BTN ============ */
.c-play { width: 44px; }
.pbtn {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  cursor: pointer;
  opacity: 0;
  transition: opacity .12s;
}
tr:hover .pbtn { opacity: 1; }
.pbtn svg { width: 13px; height: 13px; }
.pbtn--playing {
  opacity: 1 !important;
  background: var(--accent-soft);
  border-color: transparent;
  color: var(--accent-ink);
}
.pbtn--disabled {
  opacity: 0.2 !important;
  cursor: default;
  color: var(--ink-3);
}

/* ============ TRACK CELL ============ */
.td-track {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.aw {
  width: 38px;
  height: 38px;
  border-radius: var(--r-xs);
  flex: none;
  background: var(--surface-3);
  background-image: repeating-linear-gradient(135deg, transparent 0 5px, oklch(0.50 0.01 70 / .05) 5px 6px);
  overflow: hidden;
}
.aw img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.tx { min-width: 0; flex: 1; }
.tt-title-link {
  text-decoration: none;
  color: inherit;
  display: block;
  min-width: 0;
}
.tt-title {
  font-size: 14.5px;
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color .1s;
}
.tt-title-link:hover .tt-title { color: var(--accent-ink); }
tr.playing .tt-title { color: var(--accent-ink); }
.tt-art {
  font-size: 12.5px;
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ============ DATA CELLS ============ */
.td-bpm { font: 500 13px var(--font-mono); color: var(--ink-2); }
.td-key { font: 500 13px var(--font-mono); color: var(--accent-ink); }
.td-empty { font: 500 13px var(--font-mono); color: var(--ink-3); }

/* ============ SOURCE badge ============ */
.src {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  max-width: 100%;
  min-width: 0;
}
.src .ic {
  width: 26px;
  height: 26px;
  border-radius: var(--r-xs);
  flex: none;
  display: grid;
  place-items: center;
  background: var(--surface-2);
  color: var(--ink-2);
}
.src .ic svg { width: 14px; height: 14px; }
.src .meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.src .nm {
  font: 500 13px var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.src .kind {
  font: 500 9.5px/1 var(--font-mono);
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-3);
}

/* ============ DÉTECTÉ ============ */
.detect {
  font: 500 12.5px var(--font-mono);
  color: var(--ink-2);
  white-space: nowrap;
}

/* ============ ACTIONS like / dislike ============ */
.acts {
  display: inline-flex;
  gap: 6px;
  justify-content: flex-end;
}
.act {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  cursor: pointer;
  transition: opacity .12s, color .12s, background .12s, border-color .12s;
  opacity: 0;
}
tr:hover .act { opacity: 1; }
.act svg { width: 16px; height: 16px; }
.act.like:hover { color: var(--pos); border-color: var(--pos); }
.act.dislike:hover { color: var(--neg); border-color: var(--neg); }
.act.on { opacity: 1; }
.act.like.on { background: var(--pos-soft); border-color: transparent; color: var(--pos-ink); }
.act.dislike.on { background: var(--neg-soft); border-color: transparent; color: var(--neg-ink); }

/* ============ ÉTATS de ligne reco ============ */
tr.liked { background: oklch(var(--pos-l) var(--pos-c) var(--pos-h) / .06); }
tr.liked:hover { background: oklch(var(--pos-l) var(--pos-c) var(--pos-h) / .10); }
tr.disliked td:not(.c-act) { opacity: .42; }
tr.disliked:hover td:not(.c-act) { opacity: .7; }

/* ============ PAGINATION ============ */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 0 30px 30px;
}
.page-btn {
  padding: 6px 14px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
  transition: background 0.12s;
}
.page-btn:hover:not(:disabled) { background: var(--surface-2); }
.page-btn:disabled { opacity: 0.35; cursor: default; }
.page-info {
  font: 400 12px/1 var(--font-mono);
  color: var(--ink-3);
  min-width: 60px;
  text-align: center;
}

/* ============ STATES ============ */
.state {
  font: 400 14px var(--font-mono);
  color: var(--ink-3);
  text-align: center;
  padding: 60px 0;
}

/* ============ RESPONSIVE (container queries sur .app-container) ============ */
@container (max-width: 1180px) { .col-detect { display: none; } }
@container (max-width: 1040px) { .col-key { display: none; } }
@container (max-width: 780px) {
  .col-bpm { display: none; }
  .head-tools { width: 100%; margin-left: 0; }
  .search { flex: 1; min-width: 0; }
  .recency { margin-left: 0; }
}
@container (max-width: 640px) {
  .col-source { display: none; }
  .tabsbar, .page-head { padding-left: 18px; padding-right: 18px; }
  .table-wrap { padding: 4px 14px 22px; }
  .pagination { padding: 0 14px 22px; }
}
@container (max-width: 520px) {
  .col-style { display: none; }
  .tab .cnt { display: none; }
}
</style>

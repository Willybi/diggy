<template>
  <div class="detail-view">
    <!-- Loading skeleton -->
    <div v-if="loading" class="skeleton">
      <div class="sk-back"></div>
      <div class="sk-hero"></div>
      <div class="sk-strip"></div>
      <div class="sk-shelf"></div>
      <div class="sk-rows">
        <div v-for="i in 6" :key="i" class="sk-row"></div>
      </div>
    </div>

    <!-- 404 -->
    <div v-else-if="!genre" class="state-404">
      <span class="msg-404">Genre introuvable</span>
      <RouterLink to="/genres" class="back-link">← Retour aux genres</RouterLink>
    </div>

    <!-- Content -->
    <template v-else>
      <!-- Back -->
      <RouterLink to="/genres" class="back-link">← Genres</RouterLink>

      <!-- Hero -->
      <div class="hero" :data-fam="tone.pillar">
        <div class="hero-mosaic">
          <div v-for="(slot, i) in sixSlots" :key="i" class="hero-tile">
            <img v-if="slot" :src="slot" alt="" loading="lazy" @error="e => e.target.remove()" />
          </div>
          <div class="hero-scrim"></div>

          <!-- Avatars -->
          <div v-if="genre.artists?.length" class="hero-avatars">
            <img
              v-for="a in genre.artists.slice(0, 3)"
              :key="a.id"
              class="av"
              :src="a.image"
              :alt="a.name"
              loading="lazy"
              @error="e => e.target.style.display = 'none'"
            />
            <span v-if="genre.artistCount > 3" class="more">+{{ fmtNum(genre.artistCount - 3) }}</span>
          </div>

          <!-- Play button -->
          <button class="hero-play" :class="{ 'hero-play--playing': isPlaying }" aria-label="Lecture" @click="onHeroPlay">
            <svg v-if="!isPlaying" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>
          </button>
        </div>

        <div class="hero-body">
          <div class="hero-titlerow">
            <span class="hero-dot"></span>
            <h1 class="hero-title">{{ genre.name }}</h1>
          </div>
          <span class="hero-fam">{{ pillarLabel }}</span>
        </div>
      </div>

      <!-- StatStrip -->
      <StatStrip :stats="stats" />

      <!-- Admin -->
      <div v-if="auth.user?.is_admin" class="admin-card">
        <span class="admin-label">Admin</span>
        <div class="admin-row">
          <input v-model="renameVal" class="admin-input" placeholder="Nouveau nom…" />
          <button class="btn-ghost-sm" :disabled="!renameVal.trim() || renameVal.trim() === genre.name" @click="doRename">Renommer</button>
        </div>
        <div class="admin-row">
          <input v-model="mergeQuery" class="admin-input" placeholder="Fusionner dans…" @input="onMergeSearch" />
          <button class="btn-ghost-sm" :disabled="!mergeTarget" @click="doMerge">Fusionner</button>
        </div>
        <div v-if="mergeSuggestions.length" class="merge-list">
          <div
            v-for="s in mergeSuggestions"
            :key="s.name"
            class="merge-item"
            :class="{ selected: mergeTarget === s.name }"
            @click="mergeTarget = s.name; mergeQuery = s.name; mergeSuggestions = []"
          >{{ s.name }} <span class="mono muted">({{ s.trackCount }})</span></div>
        </div>
        <div v-if="adminMsg" class="admin-msg" :class="adminMsgType">{{ adminMsg }}</div>
      </div>

      <!-- Shelf: Artistes -->
      <RelBlock v-if="artists.length" title="Artistes" :count="artistsTotal">
        <div class="shelf">
          <ShelfCard
            v-for="a in artists"
            :key="a.id"
            variant="round"
            :image-src="a.hasArtwork ? `/storage/artist-artworks/${a.id}.jpg` : null"
            :title="a.name"
            :subtitle="`${a.trackCount} tracks`"
            :to="`/artist/${a.id}`"
            :fallback-letter="a.name[0]"
          />
        </div>
      </RelBlock>

      <!-- Shelf: Sets -->
      <RelBlock v-if="sets.length" title="Sets" :count="setsTotal">
        <div class="shelf">
          <ShelfCard
            v-for="s in sets"
            :key="s.id"
            :image-src="s.hasArtwork ? `/storage/set-artworks/${s.id}.jpg` : null"
            :title="s.title"
            :subtitle="s.playedDate ? fmtDate(s.playedDate) : null"
            :to="`/set/${s.id}`"
            :fallback-letter="(s.title || '?')[0]"
          >
            <template #overlay>
              <span class="ring" :class="ringClass(s)">{{ Math.round(s.genreTrackCount / s.totalTracks * 100) }}%</span>
            </template>
          </ShelfCard>
        </div>
      </RelBlock>

      <!-- Shelf: Playlists -->
      <RelBlock v-if="playlists.length" title="Playlists" :count="playlistsTotal">
        <div class="shelf">
          <ShelfCard
            v-for="p in playlists"
            :key="p.id"
            :image-src="p.hasArtwork ? `/storage/playlist-artworks/${p.id}.jpg` : null"
            :title="p.title"
            :subtitle="`${p.genreTrackCount} tracks`"
            :fallback-letter="(p.title || '?')[0]"
            :to="`/playlists/${p.id}`"
          >
            <template #badge>
              <span class="source-badge" :class="p.source">{{ p.source }}</span>
            </template>
          </ShelfCard>
        </div>
      </RelBlock>

      <!-- Tracks section -->
      <section class="tracks-section">
        <header class="tracks-head">
          <h2 class="section-title">Tracks <span class="section-count mono">{{ trackTotal }}</span></h2>
          <div class="tracks-tools">
            <input
              v-model="trackSearch"
              class="search-input"
              placeholder="Rechercher…"
              @input="onTrackSearch"
            />
            <div class="filterseg">
              <button v-for="opt in sortOptions" :key="opt.value" class="seg" :class="{ active: trackSort === opt.value }" @click="setSort(opt.value)">{{ opt.label }}</button>
            </div>
            <button class="seg lib-toggle" :class="{ active: trackInLib === 1 }" @click="toggleLib">
              <span class="libdot-mini" :class="{ active: trackInLib === 1 }"></span>
              En bib
            </button>
          </div>
        </header>

        <div v-if="!tracks.length && !tracksLoading" class="state-empty">Aucune track ne correspond.</div>
        <div v-else class="track-list">
          <GenreTrackRow v-for="t in tracks" :key="t.id" :track="t" />
        </div>

        <!-- Sentinel infinite scroll -->
        <div ref="sentinel" class="sentinel">
          <span v-if="tracksLoading" class="sentinel-spinner"></span>
        </div>
      </section>

      <!-- Neighbors -->
      <RelBlock v-if="neighbors.length" title="Genres proches">
        <div class="neighbor-chips">
          <RouterLink
            v-for="n in neighbors"
            :key="n.name"
            :to="`/style/${encodeURIComponent(n.name)}`"
            class="neighbor-chip"
          >
            <StyleTag :name="n.name" :family="n.pillar" :depth="n.depth" />
            <span class="neighbor-meta mono">{{ n.commonArtists }} artistes en commun</span>
          </RouterLink>
        </div>
      </RelBlock>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useAuthStore } from '../stores/auth.js'
import { useAudioPlayer } from '../stores/audioPlayer'
import { styleTone, PILLAR_LABELS } from '../composables/useStyleMap.js'
import { fmtDate, fmtNum } from '../utils/format'
import StatStrip from '../components/StatStrip.vue'
import RelBlock from '../components/RelBlock.vue'
import StyleTag from '../components/StyleTag.vue'
import GenreTrackRow from '../components/GenreTrackRow.vue'
import ShelfCard from '../components/ShelfCard.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const player = useAudioPlayer()

// -- State --
const loading = ref(true)
const genre = ref(null)
const artists = ref([])
const artistsTotal = ref(0)
const sets = ref([])
const setsTotal = ref(0)
const playlists = ref([])
const playlistsTotal = ref(0)
const tracks = ref([])
const trackTotal = ref(0)
const tracksLoading = ref(false)
const trackOffset = ref(0)
const trackSearch = ref('')
const trackSort = ref('recent')
const trackInLib = ref(null)
const neighbors = ref([])
const sentinel = ref(null)
let searchTimer = null
let observer = null

// Admin
const renameVal = ref('')
const mergeQuery = ref('')
const mergeTarget = ref(null)
const mergeSuggestions = ref([])
const adminMsg = ref('')
const adminMsgType = ref('')
let mergeTimer = null

// -- Computed --
const genreName = computed(() => decodeURIComponent(route.params.genre || ''))
const tone = computed(() => styleTone({ pillar: genre.value?.pillar, depth: genre.value?.depth }))
const pillarLabel = computed(() => PILLAR_LABELS[tone.value.pillar] || PILLAR_LABELS.autres)
const isPlaying = computed(() => player.genrePlaying === genreName.value)

const sixSlots = computed(() => {
  const aw = genre.value?.artworks || []
  return Array.from({ length: 6 }, (_, i) => aw[i] || null)
})

const stats = computed(() => {
  if (!genre.value) return []
  const g = genre.value
  return [
    { label: 'Tracks', value: fmtNum(g.trackCount) },
    { label: 'Artistes', value: fmtNum(g.artistCount) },
    { label: 'BPM', value: `${g.bpmLo}–${g.bpmHi}` },
    { label: 'En bib', value: fmtNum(g.inLibCount) },
  ]
})

const sortOptions = [
  { value: 'recent', label: 'Récent' },
  { value: 'bpm', label: 'BPM' },
  { value: 'key', label: 'Key' },
  { value: 'alpha', label: 'A–Z' },
]

// -- Helpers --
function ringClass(s) {
  const pct = s.totalTracks ? s.genreTrackCount / s.totalTracks : 0
  if (pct >= 0.8) return 'ring-full'
  if (pct >= 0.45) return 'ring-mid'
  return 'ring-low'
}

// -- Hero play --
function onHeroPlay() {
  if (isPlaying.value) {
    player.close()
  } else {
    player.playRandom(genreName.value)
  }
}

// -- Data fetching --
async function fetchGenre() {
  loading.value = true
  genre.value = null
  try {
    const { data } = await api.get(`/api/genres/detail/${encodeURIComponent(genreName.value)}`)
    genre.value = data
    renameVal.value = data.name
    // Fetch sub-data in parallel
    await Promise.all([
      fetchArtists(),
      fetchSets(),
      fetchPlaylists(),
      fetchTracks(true),
      fetchNeighbors(),
    ])
  } catch {
    genre.value = null
  } finally {
    loading.value = false
    await nextTick()
    setupObserver()
  }
}

async function fetchArtists() {
  try {
    const { data } = await api.get(`/api/genres/artists/${encodeURIComponent(genreName.value)}`, { params: { limit: 12 } })
    artists.value = data.items
    artistsTotal.value = data.total
  } catch { artists.value = [] }
}

async function fetchSets() {
  try {
    const { data } = await api.get(`/api/genres/sets/${encodeURIComponent(genreName.value)}`, { params: { limit: 12 } })
    sets.value = data.items
    setsTotal.value = data.total
  } catch { sets.value = [] }
}

async function fetchPlaylists() {
  try {
    const { data } = await api.get(`/api/genres/playlists/${encodeURIComponent(genreName.value)}`, { params: { limit: 12 } })
    playlists.value = data.items
    playlistsTotal.value = data.total
  } catch { playlists.value = [] }
}

async function fetchTracks(reset = false) {
  if (reset) {
    tracks.value = []
    trackOffset.value = 0
    trackTotal.value = 0
  }
  tracksLoading.value = true
  try {
    const params = {
      sort: trackSort.value,
      limit: 50,
      offset: trackOffset.value,
    }
    if (trackSearch.value.trim()) params.q = trackSearch.value.trim()
    if (trackInLib.value != null) params.inLib = trackInLib.value
    const { data } = await api.get(`/api/genres/tracks/${encodeURIComponent(genreName.value)}`, { params })
    if (reset) {
      tracks.value = data.items
    } else {
      tracks.value = [...tracks.value, ...data.items]
    }
    trackTotal.value = data.total
  } catch {
    if (reset) tracks.value = []
  } finally {
    tracksLoading.value = false
  }
}

async function fetchNeighbors() {
  try {
    const { data } = await api.get(`/api/genres/neighbors/${encodeURIComponent(genreName.value)}`)
    neighbors.value = data.items
  } catch { neighbors.value = [] }
}

// -- Track controls --
function onTrackSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => fetchTracks(true), 250)
}

function setSort(val) {
  trackSort.value = val
  fetchTracks(true)
}

function toggleLib() {
  trackInLib.value = trackInLib.value === 1 ? null : 1
  fetchTracks(true)
}

// -- Infinite scroll --
function setupObserver() {
  if (observer) observer.disconnect()
  if (!sentinel.value) return
  observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting && !tracksLoading.value && tracks.value.length < trackTotal.value) {
      trackOffset.value = tracks.value.length
      fetchTracks(false)
    }
  }, { rootMargin: '0px 0px 360px 0px' })
  observer.observe(sentinel.value)
}

// -- Admin --
async function doRename() {
  const newName = renameVal.value.trim()
  if (!newName || newName === genre.value.name) return
  try {
    const { data } = await api.patch(`/api/genres/rename/${encodeURIComponent(genre.value.name)}`, { new_name: newName })
    adminMsg.value = `Renommé → ${data.to} (${data.affected} tracks)`
    adminMsgType.value = 'ok'
    router.replace(`/style/${encodeURIComponent(data.to)}`)
  } catch (e) {
    adminMsg.value = e.response?.data?.detail || 'Erreur'
    adminMsgType.value = 'err'
  }
}

function onMergeSearch() {
  mergeTarget.value = null
  clearTimeout(mergeTimer)
  if (!mergeQuery.value.trim()) { mergeSuggestions.value = []; return }
  mergeTimer = setTimeout(async () => {
    try {
      const { data } = await api.get('/api/genres', { params: { q: mergeQuery.value.trim(), limit: 5 } })
      mergeSuggestions.value = data.items.filter(g => g.name !== genre.value?.name)
    } catch { mergeSuggestions.value = [] }
  }, 250)
}

async function doMerge() {
  if (!mergeTarget.value) return
  if (!confirm(`Fusionner "${genre.value.name}" dans "${mergeTarget.value}" ?`)) return
  try {
    const { data } = await api.post('/api/genres/merge', { source: genre.value.name, target: mergeTarget.value })
    adminMsg.value = `Fusionné ${data.affected} tracks → ${data.target}`
    adminMsgType.value = 'ok'
    router.replace(`/style/${encodeURIComponent(data.target)}`)
  } catch (e) {
    adminMsg.value = e.response?.data?.detail || 'Erreur'
    adminMsgType.value = 'err'
  }
}

// -- Lifecycle --
watch(() => route.params.genre, () => {
  trackSearch.value = ''
  trackSort.value = 'recent'
  trackInLib.value = null
  mergeQuery.value = ''
  mergeTarget.value = null
  mergeSuggestions.value = []
  adminMsg.value = ''
  fetchGenre()
})

onMounted(fetchGenre)
onUnmounted(() => { if (observer) observer.disconnect() })
</script>

<style scoped>
.detail-view {
  max-width: var(--detail-max-w);
  margin-inline: auto;
  padding: 26px 30px 56px;
}

/* Back link */
.back-link {
  font: 400 12px/1 var(--font-ui);
  color: var(--ink-3);
  text-decoration: none;
  display: inline-block;
  margin-bottom: 14px;
}
.back-link:hover { color: var(--ink); }

/* ── Pillar hue mapping ── */
.hero[data-fam="house"]     { --th: var(--hue-house); }
.hero[data-fam="techno"]    { --th: var(--hue-techno); }
.hero[data-fam="trance"]    { --th: var(--hue-trance); }
.hero[data-fam="dnb"]       { --th: var(--hue-dnb); }
.hero[data-fam="hardcore"]  { --th: var(--hue-hardcore); }
.hero[data-fam="harddance"] { --th: var(--hue-harddance); }
.hero[data-fam="autres"]    { --th: 0; }
.hero[data-fam="autres"] .hero-tile { --mc: 0; }
.hero[data-fam="autres"] .hero-dot { background: var(--ink-3); box-shadow: none; }
.hero[data-fam="autres"] .hero-title { color: var(--ink); }

/* ── Hero ── */
.hero {
  margin-bottom: 16px;
}
.hero-mosaic {
  position: relative;
  height: 180px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: 1fr 1fr;
  gap: 2px;
  border-radius: var(--r-md);
  overflow: hidden;
}

.hero-tile {
  position: relative;
  overflow: hidden;
  background: oklch(var(--ml) var(--mc, 0.15) var(--th, 0));
}
.hero-tile:nth-child(1) { --ml: 0.66; --mc: 0.155; }
.hero-tile:nth-child(2) { --ml: 0.75; --mc: 0.115; }
.hero-tile:nth-child(3) { --ml: 0.56; --mc: 0.165; }
.hero-tile:nth-child(4) { --ml: 0.70; --mc: 0.095; }
.hero-tile:nth-child(5) { --ml: 0.60; --mc: 0.140; }
.hero-tile:nth-child(6) { --ml: 0.72; --mc: 0.110; }
.hero-tile img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.hero-scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, oklch(0.20 0.02 70 / .42) 0%, transparent 46%);
  pointer-events: none;
}

/* Avatars */
.hero-avatars {
  position: absolute;
  left: 16px;
  bottom: 14px;
  display: flex;
  align-items: center;
}
.av {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  flex: none;
  margin-left: -10px;
  border: 2px solid oklch(0.99 0.004 92);
  object-fit: cover;
  box-shadow: var(--shadow-sm);
}
.av:first-child { margin-left: 0; }
[data-theme="dark"] .av { border-color: oklch(0.28 0.012 262); }
.more {
  margin-left: 8px;
  font: 600 12px/1 var(--font-mono);
  color: oklch(0.99 0.004 92);
  text-shadow: 0 1px 3px oklch(0.20 0.02 70 / .6);
}

/* Play */
.hero-play {
  position: absolute;
  right: 14px;
  bottom: 14px;
  width: 46px;
  height: 46px;
  border-radius: 50%;
  border: 0;
  background: var(--accent);
  color: var(--on-accent);
  display: grid;
  place-items: center;
  cursor: pointer;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity .18s ease, transform .18s ease, background .15s;
  box-shadow: var(--shadow-md);
}
.hero-play svg { width: 20px; height: 20px; margin-left: 2px; }
.hero:hover .hero-play { opacity: 1; transform: none; }
.hero-play--playing { opacity: 1; transform: none; }
.hero-play:hover { background: var(--accent-hover); }

/* Hero body */
.hero-body {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
}
.hero-titlerow {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.hero-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex: none;
  background: oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th, 0));
  box-shadow: 0 0 0 2px oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th, 0) / .28);
}
.hero-title {
  font: 700 26px/1.1 var(--font-ui);
  letter-spacing: -0.3px;
  color: oklch(var(--tag-fg-l) var(--tag-fg-c) var(--th, 0));
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hero-fam {
  font: 500 10px/1 var(--font-mono);
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-3);
  white-space: nowrap;
  flex: none;
  margin-left: auto;
}

/* ── Admin card ── */
.admin-card {
  margin: 16px 0;
  padding: 14px 18px;
  background: var(--surface-2);
  border: 1px dashed var(--line-2);
  border-radius: var(--r-sm);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.admin-label {
  font: 600 11px/1 var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-3);
}
.admin-row {
  display: flex;
  gap: 8px;
}
.admin-input {
  flex: 1;
  padding: 7px 12px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink);
  font: 400 13px/1.4 var(--font-ui);
}
.admin-input:focus { outline: none; border-color: var(--accent); }
.btn-ghost-sm {
  padding: 6px 14px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 12px/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-ghost-sm:hover { border-color: var(--accent); color: var(--ink); }
.btn-ghost-sm:disabled { opacity: 0.4; cursor: default; }
.merge-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.merge-item {
  padding: 6px 10px;
  border-radius: var(--r-xs);
  font: 400 13px/1.3 var(--font-ui);
  color: var(--ink);
  cursor: pointer;
}
.merge-item:hover { background: var(--surface); }
.merge-item.selected { background: var(--accent-wash); }
.admin-msg {
  font: 400 12px/1.3 var(--font-mono);
  padding: 6px 10px;
  border-radius: var(--r-xs);
}
.admin-msg.ok { color: var(--pos-ink); background: var(--pos-soft); }
.admin-msg.err { color: var(--accent-ink); background: var(--accent-soft); }
.muted { color: var(--ink-3); }
.mono { font-family: var(--font-mono); }

/* ── Shelves ── */
.shelf {
  display: flex;
  gap: 14px;
  overflow-x: auto;
  padding: 14px;
  scroll-snap-type: x proximity;
  -webkit-overflow-scrolling: touch;
}
.shelf::-webkit-scrollbar { display: none; }

/* Ring on set cards */
.ring {
  position: absolute;
  bottom: 6px;
  right: 6px;
  font: 600 9px/1 var(--font-mono);
  padding: 3px 6px;
  border-radius: 999px;
  border: 1.5px solid;
}
.ring-full { color: var(--pos-ink); border-color: var(--pos); background: var(--pos-soft); }
.ring-mid { color: var(--accent-ink); border-color: var(--accent); background: var(--accent-soft); }
.ring-low { color: var(--ink-2); border-color: var(--line-2); background: var(--surface); }

/* Source badges */
.source-badge {
  font: 600 9px/1 var(--font-mono);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 3px 7px;
  border-radius: 999px;
}
.source-badge.deezer { background: var(--accent-soft); color: var(--accent-ink); }
.source-badge.spotify { background: var(--pos-soft); color: var(--pos-ink); }
.source-badge.tidal { background: var(--surface-3); color: var(--ink-2); border: 1px solid var(--line); }

/* ── Tracks section ── */
.tracks-section {
  margin-top: 28px;
}
.tracks-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.section-title {
  font: 600 15px/1 var(--font-ui);
  color: var(--ink);
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-count {
  font: 500 11px/1 var(--font-mono);
  color: var(--ink-3);
  background: var(--surface-2);
  padding: 2px 8px;
  border-radius: 999px;
}
.tracks-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  flex-wrap: wrap;
}
.search-input {
  width: 180px;
  padding: 6px 12px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink);
  font: 400 12px/1.4 var(--font-ui);
}
.search-input:focus { outline: none; border-color: var(--accent); }

/* Segmented control */
.filterseg {
  display: inline-flex;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  overflow: hidden;
}
.seg {
  padding: 5px 10px;
  border: none;
  background: var(--surface);
  color: var(--ink-3);
  font: 500 11px/1 var(--font-ui);
  cursor: pointer;
  transition: background .12s, color .12s;
  white-space: nowrap;
}
.seg + .seg { border-left: 1px solid var(--line); }
.seg.active { background: var(--accent-soft); color: var(--accent-ink); }
.seg:hover:not(.active) { background: var(--surface-2); }

/* Lib toggle */
.lib-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
.lib-toggle.active {
  background: var(--pos-soft);
  color: var(--pos-ink);
  border-color: var(--pos);
}
.libdot-mini {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ink-3);
}
.libdot-mini.active { background: var(--pos); }

.track-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.state-empty {
  font: 400 13px/1.4 var(--font-mono);
  color: var(--ink-3);
  padding: 24px 14px;
  text-align: center;
}

/* Sentinel */
.sentinel {
  display: flex;
  justify-content: center;
  padding: 20px;
  min-height: 40px;
}
.sentinel-spinner {
  width: 22px;
  height: 22px;
  border: 2px solid var(--line);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin .6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .sentinel-spinner { animation: none; opacity: 0.5; }
}

/* ── Neighbors ── */
.neighbor-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 14px;
}
.neighbor-chip {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  text-decoration: none;
  color: inherit;
  cursor: pointer;
  padding: 8px 12px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface);
  transition: border-color .15s, box-shadow .15s;
}
.neighbor-chip:hover { border-color: var(--line-2); box-shadow: var(--shadow-sm); }
.neighbor-meta {
  font: 400 10px/1 var(--font-mono);
  color: var(--ink-3);
}

/* ── Skeleton ── */
.skeleton {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.sk-back { width: 60px; height: 12px; border-radius: var(--r-xs); background: var(--surface-2); }
.sk-hero { height: 180px; border-radius: var(--r-md); background: var(--surface-2); }
.sk-strip { height: 52px; border-radius: var(--r-md); background: var(--surface-2); }
.sk-shelf { height: 130px; border-radius: var(--r-md); background: var(--surface-2); }
.sk-rows { display: flex; flex-direction: column; gap: 4px; }
.sk-row { height: 48px; border-radius: var(--r-sm); background: var(--surface-2); }

/* ── 404 ── */
.state-404 {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 60px 20px;
}
.msg-404 {
  font: 500 16px/1 var(--font-ui);
  color: var(--ink-3);
}

/* ── Responsive ── */
@container app (max-width: 820px) {
  .tracks-tools { margin-left: 0; width: 100%; }
  .search-input { width: 100%; order: 1; }
}
@container app (max-width: 640px) {
  .detail-view { padding: 18px; }
}
@container app (max-width: 560px) {
  .hero-mosaic { height: 140px; grid-template-columns: repeat(2, 1fr); grid-template-rows: repeat(3, 1fr); }
}
</style>

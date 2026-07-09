<template>
  <div class="hub-page" :class="{ 'is-guest': !auth.isAuthenticated }">
    <!-- top bar -->
    <div class="hub-top">
      <span class="top-word" :class="{ hidden: isEmpty }"> <span class="glyph">D</span>Diggy </span>
      <div class="top-right">
        <template v-if="!auth.isAuthenticated">
          <button class="btn-login ghost" @click="$router.push('/login')">Créer un compte</button>
          <button class="btn-login" @click="$router.push('/login')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
              <path d="M10 17l5-5-5-5M15 12H3" stroke-linecap="round" stroke-linejoin="round" />
              <path d="M14 4h5a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-5" stroke-linecap="round" />
            </svg>
            Se connecter
          </button>
        </template>
        <span v-else class="top-user">
          <span class="av">{{ userInitial }}</span
          >{{ auth.user?.username }}
        </span>
      </div>
    </div>

    <!-- hub content -->
    <div class="hub" :class="{ 'is-empty': isEmpty }">
      <!-- hero (empty state) -->
      <div v-if="isEmpty" class="hub-hero">
        <div class="big-word"><span class="glyph">D</span><span class="w">Diggy</span></div>
        <div class="tag">
          Cherche un track, un set, un artiste, une playlist ou un genre — et écoute l'aperçu.
        </div>
      </div>

      <!-- search bar -->
      <div class="searchwrap" :class="{ focused: inputFocused }">
        <div class="scope" :class="{ open: scopeOpen }" v-click-outside="() => (scopeOpen = false)">
          <button class="scope-btn" @click="scopeOpen = !scopeOpen">
            <span class="lbl lbl-long">{{ currentScopeLabel }}</span>
            <span class="lbl lbl-short">{{ currentScopeIcon }}</span>
            <svg
              class="chev"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <div class="scope-menu">
            <button
              v-for="s in scopes"
              :key="s.value"
              :class="{ on: scope === s.value }"
              @click="selectScope(s.value)"
            >
              <span class="ic" v-html="s.icon"></span>{{ s.label }}
            </button>
          </div>
        </div>
        <div class="search-field">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.2-3.2" stroke-linecap="round" />
          </svg>
          <input
            ref="inputEl"
            type="text"
            v-model="query"
            placeholder="Rechercher dans tout Diggy…"
            autocomplete="off"
            @focus="inputFocused = true"
            @blur="inputFocused = false"
          />
          <button
            v-if="query"
            class="clear-q"
            aria-label="Effacer la recherche"
            @click="clearSearch"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" />
            </svg>
          </button>
        </div>
      </div>

      <!-- extras (empty state) -->
      <div v-if="isEmpty" class="extras">
        <div class="ex-section">
          <div class="ex-label">Genres populaires</div>
          <div class="gpills">
            <button
              v-for="g in topGenres"
              :key="g.name"
              class="gpill"
              :data-fam="g.pillar"
              @click="searchGenre(g.name)"
            >
              <span class="vd"></span>
              <span class="vn">{{ g.name }}</span>
              <span class="vc">{{ g.count }}</span>
            </button>
          </div>
        </div>
        <div class="ex-section">
          <div class="ex-label">Essaie</div>
          <div class="qsugs">
            <button v-for="s in suggestions" :key="s" class="qsug" @click="searchSuggestion(s)">
              {{ s }}
            </button>
          </div>
        </div>
      </div>

      <!-- discover: trend shelves -->
      <div v-if="isEmpty && trendTracks.length" class="discover">
        <h2 class="discover-title">Ca sort en ce moment</h2>
        <FamilyChips v-model="trendFamily" :counts="trendFamilyCounts" />
        <div class="trend-shelf">
          <div
            v-for="track in trendTracks"
            :key="track.catalog_id"
            class="trend-card"
            @click="openTrend(track)"
          >
            <div class="tc-art">
              <img
                v-if="track.has_artwork"
                :src="`/storage/catalog-artworks/${track.catalog_id}.jpg`"
                alt=""
                loading="lazy"
                @error="(e) => (e.target.style.display = 'none')"
              />
              <div v-if="track.has_preview" class="tc-play" @click.stop="playTrend(track)">
                <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
              </div>
            </div>
            <div class="tc-info">
              <span class="tc-rank">#{{ track.rank }}</span>
              <div class="tc-title">{{ track.title }}</div>
              <div class="tc-artist">{{ track.artist || '—' }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- results -->
      <div v-if="!isEmpty" class="results" aria-live="polite">
        <div class="results-head">
          <span class="rc"
            ><b>{{ total }}</b> résultat{{ total > 1 ? 's' : '' }} pour « {{ query }} »</span
          >
          <div v-if="auth.isAuthenticated" class="results-tools">
            <SegFilter
              v-model="sort"
              :options="[
                { value: 'rel', label: 'Pertinence' },
                { value: 'bpm', label: 'BPM' },
                { value: 'az', label: 'A–Z' },
              ]"
            />
          </div>
          <div v-else class="results-tools">
            <span class="tools-locked">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                <rect x="5" y="11" width="14" height="9" rx="2" />
                <path d="M8 11V8a4 4 0 0 1 8 0v3" stroke-linecap="round" />
              </svg>
              Tri & filtres — connecte-toi
            </span>
          </div>
        </div>

        <div class="rlist">
          <template v-if="sortedItems.length">
            <div
              v-for="item in sortedItems"
              :key="itemKey(item)"
              class="rrow"
              :class="{ playing: isPlaying(item) }"
              @click="onRowClick(item)"
            >
              <!-- type badge -->
              <span class="tbadge">
                <span v-html="typeIcon(item.type)"></span>
                <span class="lbl">{{ typeLabel(item.type) }}</span>
              </span>
              <!-- artwork -->
              <div class="rart" :class="artClass(item)" :data-fam="artFam(item)">
                <img
                  v-if="artworkUrl(item)"
                  :src="artworkUrl(item)"
                  alt=""
                  loading="lazy"
                  @error="(e) => (e.target.style.display = 'none')"
                />
                <span v-if="needsInitials(item)" class="ini">{{ initials(item) }}</span>
                <span v-if="item.type === 'genre'" class="gd"></span>
                <div v-if="isPlayable(item)" class="play" @click.stop="onPlay(item)">
                  <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
                </div>
              </div>
              <!-- text -->
              <div class="rtx">
                <div class="rtitle" v-html="highlight(itemTitle(item))"></div>
                <div v-if="itemSub(item)" class="rsub" v-html="highlight(itemSub(item))"></div>
              </div>
              <!-- meta (track) -->
              <div v-if="item.type === 'track'" class="rmeta">
                <span class="m-bpm">{{ fmtBpm(item.bpm) }}</span>
                <span class="m-key">{{ item.key || '—' }}</span>
                <span class="m-dur">{{ fmtMs(item.duration_ms) }}</span>
              </div>
              <!-- source badge (playlist) -->
              <SourceBadge v-if="item.type === 'playlist' && item.source" :source="item.source" />
              <!-- lib zone (logged in only) -->
              <div v-if="auth.isAuthenticated && item.type === 'track'" class="rlib">
                <span v-if="item.in_lib" class="enbib"><span class="d"></span>EN BIB</span>
                <button
                  v-else
                  class="r-add"
                  title="Ajouter à la bib"
                  aria-label="Ajouter à la bibliothèque"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 5v14M5 12h14" stroke-linecap="round" />
                  </svg>
                </button>
              </div>
            </div>
          </template>

          <!-- lock row (guest) -->
          <div v-if="!auth.isAuthenticated && remaining > 0" class="lockrow">
            <div class="lock-ic">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                <rect x="5" y="11" width="14" height="9" rx="2" />
                <path d="M8 11V8a4 4 0 0 1 8 0v3" stroke-linecap="round" />
              </svg>
            </div>
            <div class="lock-tx">
              <span class="t">Connecte-toi pour voir les {{ remaining }} autres résultats</span>
              <span class="s">Crée un compte gratuit pour accéder à tout Diggy.</span>
            </div>
            <button class="btn-login" @click="$router.push('/login')">Se connecter</button>
          </div>

          <!-- no results -->
          <div v-if="!sortedItems.length && !loading" class="r-empty">
            Aucun résultat. Essaie un autre mot-clé.
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../stores/toast.js'
import { useAudioPlayer } from '../stores/audioPlayer'
import { styleTone } from '../composables/useStyleMap.js'
import { fmtMs, fmtBpm } from '../utils/format.js'
import SegFilter from '../components/SegFilter.vue'
import SourceBadge from '../components/SourceBadge.vue'
import FamilyChips from '../components/FamilyChips.vue'

const router = useRouter()
const auth = useAuthStore()
const player = useAudioPlayer()

// ── state ──
const query = ref('')
const scope = ref('all')
const sort = ref('rel')
const scopeOpen = ref(false)
const inputFocused = ref(false)
const inputEl = ref(null)
const loading = ref(false)

const items = ref([])
const total = ref(0)
const totals = ref({})

const toast = useToast()

// ── static data ──
const suggestions = ['house', 'disclosure', 'boiler room', 'techno', 'trance', 'deep house']

const scopes = [
  { value: 'all', label: 'Tout', icon: '⊕' },
  { value: 'track', label: 'Tracks', icon: '♫' },
  { value: 'artist', label: 'Artistes', icon: '●' },
  { value: 'set', label: 'Sets', icon: '◎' },
  { value: 'playlist', label: 'Playlists', icon: '☰' },
  { value: 'genre', label: 'Genres', icon: '◆' },
]

const scopeIcons = {
  all: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><path d="M12 3v18M3 12h18" stroke-linecap="round"/></svg>`,
  track: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="16" r="4"/><path d="M16 16V4l-8 2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  artist: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="8" r="4"/><path d="M5 20a7 7 0 0 1 14 0" stroke-linecap="round"/></svg>`,
  set: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="1" fill="currentColor"/></svg>`,
  playlist: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M3 6h18M3 12h12M3 18h8"/></svg>`,
  genre: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 12V5a2 2 0 0 1 2-2h7l9 9-7 7-9-9z"/><circle cx="7.5" cy="7.5" r="1.2" fill="currentColor"/></svg>`,
}

// ── computed ──
const isEmpty = computed(() => !query.value.trim())
const currentScopeLabel = computed(
  () => scopes.find((s) => s.value === scope.value)?.label || 'Tout',
)
const currentScopeIcon = computed(() => scopes.find((s) => s.value === scope.value)?.icon || '⊕')
const remaining = computed(() => Math.max(0, total.value - items.value.length))
const userInitial = computed(() => (auth.user?.username || '?')[0].toUpperCase())

const sortedItems = computed(() => {
  if (sort.value === 'rel') return items.value
  const clone = [...items.value]
  if (sort.value === 'bpm') {
    clone.sort((a, b) => (a.bpm || 0) - (b.bpm || 0))
  } else if (sort.value === 'az') {
    clone.sort((a, b) => {
      const na = (a.name || a.title || '').toLowerCase()
      const nb = (b.name || b.title || '').toLowerCase()
      return na.localeCompare(nb, 'fr')
    })
  }
  return clone
})

// ── top genres (loaded once) ──
const topGenres = ref([])

async function loadTopGenres() {
  try {
    const { data } = await api.get('/api/genres', { params: { limit: 10, sort: 'tracks' } })
    topGenres.value = (data.items || []).map((g) => {
      const tone = styleTone({ pillar: g.pillar, depth: g.depth })
      return {
        name: g.name,
        count: g.trackCount || 0,
        pillar: tone.pillar,
        isAutres: tone.pillar === 'autres',
      }
    })
  } catch {
    /* silent */
  }
}

// ── trends ──
const trendFamily = ref('all')
const trendTracks = ref([])
const trendFamilyCounts = ref({})

async function loadTrends() {
  try {
    const params = { limit: 20 }
    if (trendFamily.value !== 'all') params.family = trendFamily.value
    const { data } = await api.get('/api/radar/trends', { params })
    trendTracks.value = data.items || []
    trendFamilyCounts.value = data.family_counts || {}
  } catch {
    /* silent */
  }
}

watch(trendFamily, loadTrends)

function openTrend(track) {
  if (!auth.isAuthenticated) {
    showToast('Connecte-toi pour ouvrir cette fiche.')
    return
  }
  router.push(`/catalog/${track.catalog_id}`)
}

function playTrend(track) {
  player.play({
    id: track.catalog_id,
    catalog_id: track.catalog_id,
    title: track.title,
    artist: track.artist,
    artist_id: track.artist_id,
    bpm: track.bpm,
    key: track.key,
  })
}

onMounted(() => {
  loadTopGenres()
  loadTrends()
})

// ── search ──
let debounceTimer = null

watch([query, scope], () => {
  sort.value = 'rel'
  clearTimeout(debounceTimer)
  if (!query.value.trim()) {
    items.value = []
    total.value = 0
    totals.value = {}
    return
  }
  debounceTimer = setTimeout(doSearch, 150)
})

async function doSearch() {
  const q = query.value.trim()
  if (!q) return
  loading.value = true
  try {
    const { data } = await api.get('/api/search', {
      params: { q, scope: scope.value, limit: 50 },
    })
    items.value = data.items || []
    total.value = data.total || 0
    totals.value = data.totals || {}
  } catch {
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

// ── helpers ──
function clearSearch() {
  query.value = ''
  nextTick(() => inputEl.value?.focus())
}
function focusInput() {
  nextTick(() => inputEl.value?.focus())
}
function selectScope(value) {
  scope.value = value
  scopeOpen.value = false
  focusInput()
}
function searchGenre(name) {
  scope.value = 'genre'
  query.value = name
}
function searchSuggestion(s) {
  scope.value = 'all'
  query.value = s
}

function itemKey(item) {
  return `${item.type}-${item.id || item.name}`
}
function itemTitle(item) {
  return item.name || item.title || '—'
}
function itemSub(item) {
  if (item.type === 'track') return item.artist || ''
  if (item.type === 'artist') return `${item.track_count || 0} tracks`
  if (item.type === 'set') {
    const parts = []
    if (item.played_date) parts.push(item.played_date)
    if (item.track_count != null) parts.push(`${item.track_count} tracks`)
    return parts.join(' · ')
  }
  if (item.type === 'playlist') return `${item.track_count || 0} tracks`
  if (item.type === 'genre') {
    const parts = [`${item.track_count || 0} tracks`, `${item.artist_count || 0} artistes`]
    if (item.bpm_lo && item.bpm_hi) parts.push(`${item.bpm_lo}–${item.bpm_hi} BPM`)
    return parts.join(' · ')
  }
  return ''
}

function highlight(text) {
  if (!query.value.trim() || !text) return text
  const q = query.value.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.replace(new RegExp(`(${q})`, 'gi'), '<mark>$1</mark>')
}

function typeLabel(type) {
  const map = {
    track: 'TRACK',
    artist: 'ARTISTE',
    set: 'SET',
    playlist: 'PLAYLIST',
    genre: 'GENRE',
  }
  return map[type] || type.toUpperCase()
}

function typeIcon(type) {
  return scopeIcons[type] || scopeIcons.all
}

function initials(item) {
  const s = item.name || item.artist || item.title || '?'
  return (
    s
      .replace(/[^A-Za-zÀ-ÿ0-9 ]/g, '')
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0] || '')
      .join('')
      .toUpperCase() || '?'
  )
}

function artworkUrl(item) {
  if (!item.has_artwork) return null
  if (item.type === 'track') return `/storage/catalog-artworks/${item.id}.jpg`
  if (item.type === 'artist') return `/storage/artist-artworks/${item.id}.jpg`
  if (item.type === 'set') return `/storage/set-artworks/${item.id}.jpg`
  if (item.type === 'playlist') return `/storage/playlist-artworks/${item.id}.jpg`
  return null
}

function needsInitials(item) {
  return item.type === 'artist' && !item.has_artwork
}

function artClass(item) {
  const cls = []
  if (item.type === 'artist') cls.push('round')
  if (item.type === 'genre') {
    cls.push('genre')
    if (item.pillar === 'autres' || !item.pillar) cls.push('is-autres')
  }
  return cls
}

function artFam(item) {
  if (item.type === 'genre') return item.pillar || 'autres'
  return undefined
}

function isPlayable(item) {
  return (item.type === 'track' && item.has_preview) || item.type === 'artist'
}

function isPlaying(item) {
  if (item.type === 'track') return player.track?.catalog_id === item.id && player.playing
  if (item.type === 'artist') return player.artistPlaying === item.id && player.playing
  return false
}

function onPlay(item) {
  if (item.type === 'track') {
    player.play({
      id: item.id,
      catalog_id: item.id,
      title: item.title,
      artist: item.artist,
      artist_id: item.artist_id,
      bpm: item.bpm,
      key: item.key,
    })
  } else if (item.type === 'artist') {
    player.playRandomArtist(item.id)
  }
}

function onRowClick(item) {
  if (!auth.isAuthenticated) {
    showToast('Connecte-toi pour ouvrir cette fiche.')
    return
  }
  const routes = {
    track: `/catalog/${item.id}`,
    artist: `/artist/${item.id}`,
    set: `/set/${item.id}`,
    playlist: `/playlists/${item.id}`,
    genre: `/style/${encodeURIComponent(item.name)}`,
  }
  if (routes[item.type]) router.push(routes[item.type])
}

function showToast(text) {
  toast.show(text, 'info', 3000, { label: 'Se connecter', route: '/login' })
}

// ── click outside directive ──
const vClickOutside = {
  mounted(el, binding) {
    el.__clickOutside = (e) => {
      if (!el.contains(e.target)) binding.value()
    }
    document.addEventListener('click', el.__clickOutside)
  },
  unmounted(el) {
    document.removeEventListener('click', el.__clickOutside)
  },
}
</script>

<style scoped>
.hub-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

/* ── top bar ── */
.hub-top {
  position: sticky;
  top: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--page-px);
  background: color-mix(in oklab, var(--bg) 86%, transparent);
  backdrop-filter: blur(8px);
}
.top-word {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-weight: 600;
  font-size: var(--fs-md);
  letter-spacing: 0.2px;
  color: var(--ink);
  transition: opacity 0.2s;
}
.top-word.hidden {
  opacity: 0;
  pointer-events: none;
}
.top-word .glyph {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: var(--accent);
  color: var(--on-accent);
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: var(--fs-base);
}
.top-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-25);
}

.btn-login {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  height: 38px;
  padding: 0 var(--space-4);
  border-radius: var(--r-sm);
  border: 0;
  background: var(--accent);
  color: var(--on-accent);
  font: 600 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-login:hover {
  background: var(--accent-hover);
}
.btn-login svg {
  width: 16px;
  height: 16px;
}
.btn-login.ghost {
  background: var(--surface);
  color: var(--ink-2);
  border: 1px solid var(--line-2);
}
.btn-login.ghost:hover {
  border-color: var(--ink-3);
  color: var(--ink);
}

.top-user {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  height: 38px;
  padding: 0 var(--space-15) 0 var(--space-3);
  border-radius: var(--r-pill);
  border: 1px solid var(--line);
  background: var(--surface);
  font: 500 var(--fs-sm) var(--font-ui);
  color: var(--ink-2);
}
.top-user .av {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent-ink);
  display: grid;
  place-items: center;
  font: 600 var(--fs-xs) var(--font-mono);
}

/* ── hub ── */
.hub {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0 var(--page-px) var(--space-10);
}
.hub.is-empty {
  justify-content: flex-start;
}

/* ── hero ── */
.hub-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--space-25);
  padding: var(--space-15x) 0 var(--space-8);
}
.big-word {
  display: inline-flex;
  align-items: center;
  gap: var(--space-4);
}
.big-word .glyph {
  width: 54px;
  height: 54px;
  border-radius: 15px;
  background: var(--accent);
  color: var(--on-accent);
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: var(--fs-xl);
  box-shadow: var(--shadow-md);
}
.big-word .w {
  font: 600 var(--fs-hero)/1 var(--font-ui);
  letter-spacing: -1.2px;
}
.hub-hero .tag {
  font: 500 var(--fs-base)/1.5 var(--font-mono);
  color: var(--ink-3);
  max-width: 420px;
}

/* ── search bar ── */
.searchwrap {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-pill);
  box-shadow: var(--shadow-md);
  padding: var(--space-15) var(--space-2) var(--space-15) var(--space-15);
  transition:
    box-shadow 0.16s,
    border-color 0.16s;
}
.searchwrap.focused {
  border-color: var(--accent);
  box-shadow:
    var(--shadow-md),
    0 0 0 4px var(--accent-soft);
}

/* scope dropdown */
.scope {
  position: relative;
  flex: none;
}
.scope-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  height: 46px;
  padding: 0 var(--space-3) 0 var(--space-3);
  border-radius: var(--r-pill);
  border: 0;
  background: var(--surface-2);
  color: var(--ink-2);
  font: 600 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.scope-btn:hover {
  background: var(--surface-3);
  color: var(--ink);
}
.scope-btn .chev {
  width: 14px;
  height: 14px;
  transition: transform 0.16s;
  color: var(--ink-3);
}
.scope.open .scope-btn .chev {
  transform: rotate(180deg);
}
.scope-btn .lbl-short {
  display: none;
}

.scope-menu {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  z-index: 40;
  min-width: 180px;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-lg);
  padding: var(--space-15);
  display: none;
}
.scope.open .scope-menu {
  display: block;
}
.scope-menu button {
  display: flex;
  align-items: center;
  gap: var(--space-25);
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--ink-2);
  font: 500 var(--fs-sm) var(--font-ui);
  padding: var(--space-2) var(--space-25);
  border-radius: var(--r-sm);
  cursor: pointer;
}
.scope-menu button:hover {
  background: var(--surface-2);
  color: var(--ink);
}
.scope-menu button.on {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.scope-menu button .ic {
  width: 16px;
  height: 16px;
  flex: none;
  color: var(--ink-3);
}
.scope-menu button.on .ic {
  color: var(--accent-ink);
}

/* search field */
.search-field {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--space-25);
  padding: 0 var(--space-2);
  min-width: 0;
}
.search-field > svg {
  width: 20px;
  height: 20px;
  color: var(--ink-3);
  flex: none;
}
.search-field input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  outline: none;
  font: 400 var(--fs-input) var(--font-ui);
  color: var(--ink);
}
.search-field input::placeholder {
  color: var(--ink-3);
}
.clear-q {
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 0;
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
  display: grid;
  place-items: center;
}
.clear-q svg {
  width: 16px;
  height: 16px;
}
.clear-q:hover {
  background: var(--surface-2);
  color: var(--ink);
}

/* ── extras ── */
.extras {
  width: 100%;
  max-width: 720px;
  margin: var(--space-6) auto 0;
}
.ex-section {
  margin-bottom: var(--space-6);
}
.ex-label {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin: 0 0 var(--space-3);
}

/* genre pills */
/* pillar hue mapping for genre pills */
.gpill[data-fam='house'] {
  --th: var(--hue-house);
}
.gpill[data-fam='techno'] {
  --th: var(--hue-techno);
}
.gpill[data-fam='trance'] {
  --th: var(--hue-trance);
}
.gpill[data-fam='dnb'] {
  --th: var(--hue-dnb);
}
.gpill[data-fam='hardcore'] {
  --th: var(--hue-hardcore);
}
.gpill[data-fam='harddance'] {
  --th: var(--hue-harddance);
}
.gpill[data-fam='autres'] .vd {
  background: var(--ink-3);
}
.gpill[data-fam='autres'] .vn {
  color: var(--ink);
}

.gpills {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.gpill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  background: var(--surface);
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition:
    border-color 0.14s,
    transform 0.14s,
    background 0.14s;
  font-family: var(--font-ui);
}
.gpill:hover {
  border-color: var(--line-2);
  transform: translateY(-1px);
  background: var(--surface-2);
}
.gpill .vd {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
  background: oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th));
}
.gpill .vn {
  font: 600 var(--fs-sm) var(--font-ui);
  color: oklch(var(--tag-fg-l) var(--tag-fg-c) var(--th));
  white-space: nowrap;
}
.gpill .vc {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}

/* suggestions */
.qsugs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-15);
}
.qsug {
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--ink-2);
  background: var(--surface-2);
  border: 0;
  border-radius: var(--r-pill);
  padding: var(--space-15) var(--space-3);
  cursor: pointer;
}
.qsug:hover {
  background: var(--surface-3);
  color: var(--ink);
}
.qsug::before {
  content: '↳ ';
  color: var(--ink-3);
}

/* ── results ── */
.results {
  width: 100%;
  max-width: 720px;
  margin: var(--space-6) auto 0;
}
.results-head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-05) var(--space-1) var(--space-3);
  flex-wrap: wrap;
}
.results-head .rc {
  font: 600 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-3);
}
.results-head .rc :deep(b) {
  color: var(--ink-2);
}
.results-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.tools-locked {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--ink-3);
  border: 1px dashed var(--line-2);
  border-radius: var(--r-sm);
  padding: var(--space-15) var(--space-25);
}
.tools-locked svg {
  width: 13px;
  height: 13px;
}

/* result list */
.rlist {
  display: flex;
  flex-direction: column;
}
.rrow {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-25) var(--space-3);
  border-radius: var(--r-md);
  cursor: pointer;
  text-decoration: none;
  transition: background 0.13s;
}
.rrow:hover {
  background: var(--surface-2);
}
.rrow.playing {
  background: var(--accent-wash);
}

/* type badge */
.tbadge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  flex: none;
  width: 92px;
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.tbadge :deep(svg) {
  width: 13px;
  height: 13px;
  flex: none;
}

/* artwork */
.rart {
  position: relative;
  flex: none;
  width: 46px;
  height: 46px;
  border-radius: var(--r-xs);
  overflow: hidden;
  background-color: var(--surface-3);
  background-image: repeating-linear-gradient(
    135deg,
    oklch(0.5 0.01 70 / 0.06) 0 1px,
    transparent 1px 9px
  );
  box-shadow: var(--shadow-sm);
  display: grid;
  place-items: center;
}
.rart.round {
  border-radius: 50%;
}
.rart img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.rart .ini {
  font: 600 var(--fs-base) var(--font-mono);
  color: var(--ink-3);
}
.rart .play {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: var(--overlay-soft);
  color: var(--overlay-text);
  opacity: 0;
  transition: opacity 0.12s;
}
.rart .play svg {
  width: 17px;
  height: 17px;
  margin-left: 1px; /* optical centering */
}
.rrow:hover .rart .play,
.rrow.playing .rart .play {
  opacity: 1;
}

/* genre result artwork — hue from [data-fam] on .rart */
.rart[data-fam='house'] {
  --th: var(--hue-house);
}
.rart[data-fam='techno'] {
  --th: var(--hue-techno);
}
.rart[data-fam='trance'] {
  --th: var(--hue-trance);
}
.rart[data-fam='dnb'] {
  --th: var(--hue-dnb);
}
.rart[data-fam='hardcore'] {
  --th: var(--hue-hardcore);
}
.rart[data-fam='harddance'] {
  --th: var(--hue-harddance);
}
.rart.genre {
  background: oklch(0.94 0.055 var(--th));
  background-image: none;
}
.rart.genre.is-autres {
  background: var(--surface-3);
}
.rart.genre .gd {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th));
}
.rart.genre.is-autres .gd {
  background: var(--ink-3);
}

/* text */
.rtx {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.rtitle {
  font: 500 var(--fs-title) var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rrow.playing .rtitle {
  color: var(--accent-ink);
}
.rsub {
  font: 400 var(--fs-sm) var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rtitle :deep(mark),
.rsub :deep(mark) {
  background: var(--accent-soft);
  color: var(--accent-ink);
  border-radius: 3px;
  padding: 0 var(--space-05);
}

/* meta */
.rmeta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex: none;
}
.rmeta .m-bpm {
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--ink-2);
}
.rmeta .m-key {
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--accent-ink);
}
.rmeta .m-dur {
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--ink-3);
}

/* lib zone */
.rlib {
  flex: none;
  width: 40px;
  display: flex;
  justify-content: flex-end;
}
.enbib {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.04em;
  color: var(--pos-ink);
  background: var(--pos-soft);
  padding: var(--space-1) var(--space-15);
  border-radius: var(--r-pill);
  white-space: nowrap;
}
.enbib .d {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--pos);
  flex: none;
}
.r-add {
  opacity: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px dashed var(--ink-3);
  background: transparent;
  color: var(--ink-3);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: opacity 0.12s;
}
.r-add svg {
  width: 14px;
  height: 14px;
}
.rrow:hover .r-add {
  opacity: 0.8;
}
.r-add:hover {
  opacity: 1;
  border-style: solid;
  border-color: var(--pos);
  color: var(--pos-ink);
}

/* lock row */
.lockrow {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin: var(--space-2) var(--space-1) 0;
  padding: var(--space-4) var(--space-5);
  border: 1px dashed var(--line-2);
  border-radius: var(--r-md);
  background: var(--surface-2);
}
.lock-ic {
  width: 38px;
  height: 38px;
  flex: none;
  border-radius: 50%;
  background: var(--surface);
  border: 1px solid var(--line-2);
  display: grid;
  place-items: center;
  color: var(--ink-3);
}
.lock-ic svg {
  width: 17px;
  height: 17px;
}
.lock-tx {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.lock-tx .t {
  font: 600 var(--fs-base) var(--font-ui);
  color: var(--ink);
}
.lock-tx .s {
  font: 400 var(--fs-sm) var(--font-ui);
  color: var(--ink-3);
  margin-top: var(--space-05);
}

/* no results */
.r-empty {
  padding: var(--space-10) 0;
  text-align: center;
  color: var(--ink-3);
  font: 500 var(--fs-base) var(--font-mono);
}

/* ── discover ── */
.discover {
  width: 100%;
  max-width: 960px;
  margin: var(--space-2) auto 0;
}
.discover-title {
  font: 600 var(--fs-md)/1 var(--font-ui);
  color: var(--ink);
  margin: 0 0 var(--space-4);
}
.discover :deep(.fam-chips) {
  padding: 0 0 var(--space-4);
}
.trend-shelf {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-25);
  padding: 0 0 var(--space-4);
}
.trend-card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2);
  border-radius: var(--r-md);
  background: var(--surface);
  border: 1px solid var(--line);
  cursor: pointer;
  transition: background 0.13s, border-color 0.13s;
}
.trend-card:hover {
  background: var(--surface-2);
  border-color: var(--line-2);
}
.tc-art {
  position: relative;
  width: 80px;
  height: 80px;
  border-radius: var(--r-sm);
  overflow: hidden;
  flex: none;
  background: var(--surface-3);
}
.tc-art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.tc-play {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: var(--overlay-soft);
  color: var(--overlay-text);
  opacity: 0;
  transition: opacity 0.12s;
}
.tc-play svg {
  width: 22px;
  height: 22px;
}
.trend-card:hover .tc-play {
  opacity: 1;
}
.tc-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.tc-rank {
  display: inline-flex;
  align-items: center;
  padding: var(--space-05) var(--space-15);
  border-radius: var(--r-xs);
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 600 var(--fs-xs)/1 var(--font-mono);
  align-self: flex-start;
}
.tc-title {
  font: 500 var(--fs-base) var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tc-artist {
  font: 400 var(--fs-sm) var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── responsive ── */
@container app (max-width: 680px) {
  .hub,
  .hub-top {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  .scope-btn .lbl-long {
    display: none;
  }
  .scope-btn .lbl-short {
    display: inline;
  }
  .rmeta .m-dur {
    display: none;
  }
  .tbadge {
    width: 30px;
  }
  .tbadge .lbl {
    display: none;
  }
}
@container app (max-width: 640px) {
  .searchwrap {
    max-width: 100%;
  }
  .results {
    max-width: 100%;
  }
  .extras {
    max-width: 100%;
  }
  .discover {
    max-width: 100%;
  }
  .trend-shelf {
    grid-template-columns: 1fr;
  }
  .tc-art {
    width: 56px;
    height: 56px;
  }
  .tc-play {
    opacity: 1;
  }
  .rart .play {
    opacity: 1;
  }
  .r-add {
    opacity: 0.8;
  }
}
@container app (max-width: 540px) {
  .big-word .w {
    font-size: var(--fs-display);
  }
  .rmeta .m-bpm {
    display: none;
  }
}
</style>

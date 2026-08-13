<template>
  <div class="results" aria-live="polite">
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
</template>

<script setup>
// Search results list for the Hub. HubView owns the search STATE (query, scope,
// fetch) and passes the raw items down; this component owns the display-only sort
// and every rendering helper, plus navigation/playback of a row. Lazy-loaded so
// SegFilter/SourceBadge and this render code stay out of the Hub's main chunk.
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { useToast } from '../../stores/toast.js'
import { useAudioPlayer } from '../../stores/audioPlayer'
import { fmtMs, fmtBpm } from '../../utils/format.js'
import { scopeIcons } from './scopeIcons.js'
import SegFilter from '../SegFilter.vue'
import SourceBadge from '../SourceBadge.vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  query: { type: String, default: '' },
  loading: { type: Boolean, default: false },
})

const router = useRouter()
const auth = useAuthStore()
const player = useAudioPlayer()
const toast = useToast()

// Display-only sort. Reset to relevance whenever a fresh result set lands (any
// new query OR scope produces a new `items` reference), matching the pre-split
// behavior where HubView reset `sort` on every `[query, scope]` change.
const sort = ref('rel')
watch(
  () => props.items,
  () => {
    sort.value = 'rel'
  },
)

const remaining = computed(() => Math.max(0, props.total - props.items.length))

const sortedItems = computed(() => {
  if (sort.value === 'rel') return props.items
  const clone = [...props.items]
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

// ── helpers ──
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
  if (!props.query.trim() || !text) return text
  const q = props.query.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
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
    toast.show('Connecte-toi pour ouvrir cette fiche.', 'info', 3000, {
      label: 'Se connecter',
      route: '/login',
    })
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
</script>

<style scoped>
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

/* ── login button (guest lock row) ── */
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

/* ── responsive — container queries (640) ── */
@container app (max-width: 640px) {
  .results {
    max-width: 100%;
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
  .rart .play {
    opacity: 1;
  }
  .r-add {
    opacity: 0.8;
  }
}
</style>

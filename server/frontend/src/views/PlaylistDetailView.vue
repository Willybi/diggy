<template>
  <div class="detail-view">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!playlist" class="state state--empty">
      <span>Playlist introuvable.</span>
      <RouterLink to="/playlists" class="btn">Retour aux playlists</RouterLink>
    </div>
    <template v-else>
      <!-- Back link -->
      <RouterLink to="/playlists" class="dv-back">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M15 6l-6 6 6 6" />
        </svg>
        Playlists
      </RouterLink>

      <!-- 1. Hero -->
      <section class="hero">
        <div class="hero-cover">
          <Artwork size="hero" :src="coverSrc" :alt="playlist.title || playlist.external_id" />
        </div>

        <div class="hero-main">
          <h1 class="hero-title" :class="{ 'hero-title--id': !playlist.title }">
            {{ playlist.title || playlist.external_id }}
          </h1>

          <div v-if="ownerLabel" class="hero-owner">{{ ownerLabel }}</div>

          <!-- Identity stats (P2) — Tracks · Dernier crawl -->
          <div class="hero-stats">
            <div v-if="playlist.track_count != null" class="stat-cell">
              <span class="stat-label">Tracks</span>
              <span class="stat-val">{{ playlist.track_count }}</span>
            </div>
            <div class="stat-cell">
              <span class="stat-label">Dernier crawl</span>
              <span class="stat-val" :class="{ 'stat-val--muted': !playlist.last_crawled_at }">
                {{ playlist.last_crawled_at ? fmtDate(playlist.last_crawled_at) : 'jamais' }}
              </span>
            </div>
          </div>

          <!-- Source link (P3) — unique hero action -->
          <div v-if="externalUrl" class="hero-source">
            <PlatformLink :platform="playlist.source" :href="externalUrl" size="md" />
            <span class="hero-source-tx">
              <span class="hero-source-label">Source</span>
              <span class="hero-source-name">{{ sourceLabel }}</span>
            </span>
          </div>
        </div>
      </section>

      <!-- 2. Crawl status banner (P4) -->
      <div v-if="crawlState" class="crawl-banner" :class="crawlState">
        <span class="crawl-dot"></span>
        <span class="crawl-text">{{ crawlText }}</span>
        <span class="crawl-status">{{ crawlState === 'running' ? 'RUNNING' : 'QUEUED' }}</span>
      </div>

      <!-- 3. Description (P5) -->
      <p v-if="playlist.description" class="desc">{{ playlist.description }}</p>

      <!-- 4. Dans cette playlist (P6) -->
      <section v-if="hasInsights" class="insights">
        <h2 class="sec-title">Dans cette playlist</h2>
        <div class="insights-card">
          <div class="ins-col">
            <template v-if="topArtists.length">
              <span class="ins-microlabel">Top artistes</span>
              <div class="ins-artists">
                <RouterLink
                  v-for="a in topArtists"
                  :key="a.id"
                  :to="`/artist/${a.id}`"
                  class="ins-artist"
                >
                  <img
                    v-if="a.has_artwork"
                    class="ins-av"
                    :src="`/storage/artist-artworks/${a.id}.jpg`"
                    :alt="a.name"
                  />
                  <span v-else class="ins-av ins-av--ph">{{ initials(a.name) }}</span>
                  <span class="ins-artist-tx">
                    <span class="ins-name">{{ a.name }}</span>
                    <span class="ins-count"
                      >{{ a.count }} {{ pl(a.count, 'track', 'tracks') }}</span
                    >
                  </span>
                </RouterLink>
              </div>
            </template>
          </div>

          <div class="ins-col">
            <template v-if="topGenres.length">
              <span class="ins-microlabel">Genres dominants</span>
              <div class="ins-genres">
                <div v-for="g in topGenres" :key="g.name" class="ins-genre">
                  <RouterLink :to="`/style/${encodeURIComponent(g.name)}`" class="ins-tag-link">
                    <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
                  </RouterLink>
                  <span class="ins-bar" :data-fam="g.pillar" :style="`--d:${g.depth}`">
                    <i :style="`width:${g.pct}%`"></i>
                  </span>
                  <span class="ins-pct">{{ g.pct }}&#8239;%</span>
                </div>
              </div>
            </template>
          </div>
        </div>
      </section>

      <!-- 5. Tracks détectées -->
      <section class="detected">
        <header class="sec-head">
          <h2 class="sec-title">Tracks détectées</h2>
          <span v-if="detectedCards.length" class="sec-count">
            {{ detectedCards.length }} {{ pl(detectedCards.length, 'track', 'tracks') }}
          </span>
        </header>

        <div v-if="detectedCards.length" class="track-list">
          <TrackCard
            v-for="t in detectedCards"
            :key="t.id"
            :track="t"
            show-artist
            show-duration
            :playing="rowPlaying(t.id)"
            @play="playTrack(t)"
            @click="goTrack(t.id)"
          />
        </div>

        <div v-else class="empty-crawl">
          <span class="empty-ph"></span>
          <p class="empty-title">Aucune track détectée pour l'instant</p>
          <p class="empty-sub">
            La playlist est surveillée — les tracks apparaîtront après le premier crawl.
          </p>
        </div>
      </section>

      <!-- 6. AdminCard — unchanged, gated is_admin, at the bottom -->
      <AdminCard v-if="!playlist.has_artwork && playlist.source === 'deezer'" variant="warn">
        <div class="admin-row">
          <button class="btn-sync" :disabled="fetchingArt" @click="fetchArtwork">
            {{ fetchingArt ? 'Fetch en cours…' : 'Fetch artwork Deezer' }}
          </button>
          <span v-if="artMsg" class="admin-msg" :class="artMsgType">{{ artMsg }}</span>
        </div>
      </AdminCard>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useTaskPoll } from '../composables/useTaskPoll.js'
import Artwork from '../components/Artwork.vue'
import TrackCard from '../components/TrackCard.vue'
import PlatformLink from '../components/PlatformLink.vue'
import StyleTag from '../components/StyleTag.vue'
import AdminCard from '../components/AdminCard.vue'
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtDate, pl } from '../utils/format'

const route = useRoute()
const router = useRouter()
const player = useAudioPlayer()
const playlist = ref(null)
const loading = ref(true)
const fetchingArt = ref(false)
const artMsg = ref('')
const artMsgType = ref('')
const crawlState = ref(null) // 'queued' | 'running' | null

// Crawl status poll — mechanic unchanged (useTaskPoll, keyed timers, unmount cleanup).
const crawlPoll = useTaskPoll(() => `/api/watchlist/${route.params.id}/crawl-status`, {
  intervalMs: 3000,
  async onData(data, { stop }) {
    if (!data.status || data.status === 'done') {
      stop()
      crawlState.value = null
      await fetchDetail()
    } else {
      crawlState.value = data.status
    }
  },
  onError() {
    crawlState.value = null
  },
})

const sourceLabel = computed(() => {
  const map = { deezer: 'Deezer', tidal: 'TIDAL', spotify: 'Spotify' }
  return map[playlist.value?.source] || null
})

const externalUrl = computed(() => {
  if (!playlist.value) return null
  const eid = playlist.value.external_id
  switch (playlist.value.source) {
    case 'deezer':
      return `https://www.deezer.com/playlist/${eid}`
    case 'tidal':
      return `https://listen.tidal.com/playlist/${eid}`
    case 'spotify':
      return `https://open.spotify.com/playlist/${eid}`
    default:
      return null
  }
})

// Owner is hidden when absent OR redundant with the source name (e.g. owner "Tidal").
const ownerLabel = computed(() => {
  const owner = playlist.value?.owner
  if (!owner) return null
  const src = sourceLabel.value
  if (src && owner.toLowerCase() === src.toLowerCase()) return null
  return owner
})

const crawlText = computed(() =>
  crawlState.value === 'running'
    ? 'Crawl en cours — les tracks détectées se mettront à jour à la fin.'
    : "Crawl en file d'attente — la playlist sera analysée sous peu.",
)

const topArtists = computed(() => (playlist.value?.top_artists ?? []).slice(0, 6))
const topGenres = computed(() => (playlist.value?.top_genres ?? []).slice(0, 5))
const hasInsights = computed(() => topArtists.value.length > 0 || topGenres.value.length > 0)

const coverSrc = computed(() =>
  playlist.value?.has_artwork ? `/storage/playlist-artworks/${playlist.value.id}.jpg` : undefined,
)

// Detected tracks → TrackCard shape (id = catalog_id drives cover + play + row link),
// newest detection first (detected_at desc).
const detectedCards = computed(() => {
  const tracks = [...(playlist.value?.tracks ?? [])]
  tracks.sort((a, b) => {
    const da = a.detected_at ? new Date(a.detected_at).getTime() : 0
    const db = b.detected_at ? new Date(b.detected_at).getTime() : 0
    return db - da
  })
  return tracks.map((t) => ({
    id: t.catalog_id,
    title: t.title,
    artist: t.artist,
    artists: t.artists,
    bpm: t.bpm,
    key: t.key,
    duration_ms: t.duration_ms,
    has_artwork: t.has_artwork,
    has_preview: t.has_preview,
    in_lib: t.in_lib,
  }))
})

// Initials fallback for an artist avatar without artwork.
function initials(name) {
  return (name || '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
}

// A row is "playing" only while the audio is actually running.
function rowPlaying(id) {
  return player.isCurrent(id) && player.playing
}

async function fetchDetail() {
  try {
    const { data } = await api.get(`/api/watchlist/${route.params.id}`)
    playlist.value = data
    if (data.current_task_id && !crawlPoll.isActive()) {
      crawlState.value = 'queued'
      crawlPoll.start()
    }
  } catch {
    playlist.value = null
  } finally {
    loading.value = false
  }
}

async function fetchArtwork() {
  fetchingArt.value = true
  artMsg.value = ''
  try {
    await api.post(`/api/watchlist/${playlist.value.id}/fetch-artwork`)
    artMsg.value = 'Artwork importé'
    artMsgType.value = 'success'
    await fetchDetail()
  } catch (e) {
    artMsg.value = e.response?.data?.detail || 'Erreur'
    artMsgType.value = 'error'
  } finally {
    fetchingArt.value = false
  }
}

function playTrack(t) {
  player.play({
    id: t.id,
    catalog_id: t.id,
    title: t.title,
    artist: t.artist,
    bpm: t.bpm,
    key: t.key,
  })
}

function goTrack(id) {
  router.push(`/catalog/${id}`)
}

onMounted(fetchDetail)
</script>

<style scoped>
.detail-view {
  padding: var(--space-6) var(--page-px) var(--space-10);
  max-width: var(--detail-max-w);
  margin-inline: auto;
  container-type: inline-size;
}

/* Not-found state — stacked message + return button */
.state--empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
}

/* Back link */
.dv-back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  margin-bottom: var(--space-5);
  text-decoration: none;
  color: var(--ink-2);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  transition: color 0.12s;
}
.dv-back:hover {
  color: var(--ink);
}
.dv-back svg {
  width: 16px;
  height: 16px;
}

/* ============ HERO ============ */
.hero {
  display: grid;
  grid-template-columns: 216px 1fr;
  gap: var(--space-8);
  align-items: start;
}
.hero-cover {
  width: 216px;
  max-width: 100%;
}
.hero-cover :deep(.artwork--hero) {
  width: 100%;
}
.hero-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.hero-title {
  margin: 0;
  font: 700 var(--fs-xl)/1.12 var(--font-ui);
  color: var(--ink);
  letter-spacing: -0.01em;
}
/* Missing title → external_id rendered mono ("technical identifier", P9). */
.hero-title--id {
  font-family: var(--font-mono);
  letter-spacing: 0;
}
.hero-owner {
  font: 400 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink-2);
}

/* Identity stats (P2) */
.hero-stats {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  margin-top: var(--space-1);
}
.stat-cell {
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.stat-label {
  font: 500 var(--fs-label)/1 var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--ink-3);
}
.stat-val {
  font: 600 var(--fs-md)/1 var(--font-mono);
  color: var(--ink);
}
.stat-val--muted {
  color: var(--ink-3);
}

/* Source link (P3) */
.hero-source {
  display: inline-flex;
  align-items: center;
  gap: var(--space-25);
  margin-top: var(--space-1);
}
.hero-source-tx {
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.hero-source-label {
  font: 500 var(--fs-label)/1 var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--ink-3);
}
.hero-source-name {
  font: 500 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink-2);
}

/* ============ CRAWL BANNER (P4) ============ */
.crawl-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-6);
  padding: var(--space-25) var(--space-4);
  border-radius: var(--r-md);
}
.crawl-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
.crawl-text {
  flex: 1;
  min-width: 0;
}
.crawl-status {
  font: 500 var(--fs-nano)/1 var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  white-space: nowrap;
}
.crawl-banner.queued {
  background: var(--surface);
  border: 1px solid var(--line);
}
.crawl-banner.queued .crawl-dot {
  background: var(--ink-3);
}
.crawl-banner.queued .crawl-text {
  font: 400 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink-2);
}
.crawl-banner.queued .crawl-status {
  color: var(--ink-3);
}
.crawl-banner.running {
  background: var(--accent-soft);
  border: 1px solid var(--accent-soft-2);
}
.crawl-banner.running .crawl-dot {
  background: var(--accent);
  animation: pulse-dot 1.2s ease-in-out infinite;
}
.crawl-banner.running .crawl-text {
  font: 500 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--accent-ink);
}
.crawl-banner.running .crawl-status {
  color: var(--accent-ink);
}
@keyframes pulse-dot {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}

/* ============ DESCRIPTION (P5) ============ */
.desc {
  margin: var(--space-6) 0 0;
  max-width: 640px;
  font: 400 var(--fs-sm)/1.55 var(--font-ui);
  color: var(--ink-2);
}

/* ============ SECTION HEADS ============ */
.sec-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.sec-title {
  margin: 0;
  font: 600 var(--fs-md)/1.2 var(--font-ui);
  color: var(--ink);
}
.sec-count {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
}

/* ============ DANS CETTE PLAYLIST (P6) ============ */
.insights {
  margin-top: var(--space-8);
}
.insights .sec-title {
  margin-bottom: var(--space-3);
}
.insights-card {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-8);
  padding: var(--space-5);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-sm);
}
.ins-col {
  min-width: 0;
}
.ins-microlabel {
  display: block;
  margin-bottom: var(--space-3);
  font: 500 var(--fs-label)/1 var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--ink-3);
}

/* Top artists */
.ins-artists {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}
.ins-artist {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex: 1 1 calc(50% - var(--space-3));
  min-width: 0;
  text-decoration: none;
}
.ins-av {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  flex: none;
  border: 1px solid var(--line);
  object-fit: cover;
  background: var(--surface-3);
}
.ins-av--ph {
  display: grid;
  place-items: center;
  border: none;
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 600 var(--fs-xs)/1 var(--font-ui);
}
.ins-artist-tx {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.ins-name {
  font: 500 var(--fs-xs)/1.2 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ins-artist:hover .ins-name {
  text-decoration: underline;
}
.ins-count {
  font: 400 var(--fs-nano)/1 var(--font-mono);
  color: var(--ink-3);
}

/* Dominant genres */
.ins-genres {
  display: flex;
  flex-direction: column;
  gap: var(--space-25);
}
.ins-genre {
  display: grid;
  grid-template-columns: 120px 1fr 40px;
  align-items: center;
  gap: var(--space-3);
}
.ins-tag-link {
  display: inline-flex;
  max-width: 100%;
  text-decoration: none;
}
.ins-bar {
  height: 6px;
  border-radius: var(--r-pill);
  background: var(--surface-2);
  overflow: hidden;
}
.ins-bar i {
  display: block;
  height: 100%;
  border-radius: var(--r-pill);
  background: oklch(
    calc(var(--tag-dot-l) + 0.04 * var(--d, 0)) calc(var(--tag-dot-c) * (1 - 0.19 * var(--d, 0)))
      var(--th, 0)
  );
}
.ins-bar[data-fam='house'] {
  --th: var(--hue-house);
}
.ins-bar[data-fam='techno'] {
  --th: var(--hue-techno);
}
.ins-bar[data-fam='trance'] {
  --th: var(--hue-trance);
}
.ins-bar[data-fam='dnb'] {
  --th: var(--hue-dnb);
}
.ins-bar[data-fam='hardcore'] {
  --th: var(--hue-hardcore);
}
.ins-bar[data-fam='harddance'] {
  --th: var(--hue-harddance);
}
.ins-bar[data-fam='autres'] i {
  background: oklch(var(--tag-dot-l) 0 0);
}
.ins-pct {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-2);
  text-align: right;
}

/* ============ TRACKS DÉTECTÉES ============ */
.detected {
  margin-top: var(--space-8);
}
.track-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* Never-crawled empty state — engaging card */
.empty-crawl {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-5);
  text-align: center;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-sm);
}
.empty-ph {
  width: 56px;
  height: 56px;
  margin-bottom: var(--space-2);
  border-radius: var(--r-sm);
  border: 1px solid var(--ct-line);
  background: repeating-linear-gradient(45deg, var(--surface-2) 0 6px, var(--surface-3) 6px 12px);
}
.empty-title {
  margin: 0;
  font: 500 var(--fs-base)/1.3 var(--font-ui);
  color: var(--ink-2);
}
.empty-sub {
  margin: 0;
  max-width: 360px;
  font: 400 var(--fs-sm)/1.5 var(--font-ui);
  color: var(--ink-3);
}

/* ============ ADMIN ============ */
.admin-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.btn-sync {
  padding: var(--space-15) var(--space-4);
  border-radius: var(--r-sm);
  border: 1px solid var(--accent);
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
  transition: opacity 0.12s;
}
.btn-sync:disabled {
  opacity: 0.5;
  cursor: default;
}
.admin-msg {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
}
.admin-msg.success {
  color: var(--pos-ink);
}
.admin-msg.error {
  color: var(--neg-ink);
}

/* ============ RESPONSIVE ============ */
@container (max-width: 720px) {
  .insights-card {
    grid-template-columns: 1fr;
    gap: var(--space-5);
  }
}
@container (max-width: 640px) {
  .detail-view {
    padding-inline: var(--page-px-mobile);
  }
  .hero {
    grid-template-columns: 1fr;
    gap: var(--space-5);
  }
  .hero-cover {
    width: 160px;
  }
  .hero-title {
    font-size: var(--fs-lg);
  }
}
</style>

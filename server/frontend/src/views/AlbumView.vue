<template>
  <div class="detail-view">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!album" class="state state--empty">
      <span>Album introuvable.</span>
      <BackButton fallback="/" label="Retour" />
    </div>
    <template v-else>
      <!-- Back link — no album listing, fall back to the Hub -->
      <BackButton fallback="/" />

      <!-- 1. Immersive hero -->
      <section class="hero">
        <!-- Backdrop = blurred cover, theme-adaptive opacity. Absent without artwork. -->
        <div v-if="album.has_artwork" class="hero-backdrop" aria-hidden="true">
          <img :src="coverSrc" alt="" />
        </div>

        <div class="hero-cover">
          <Artwork size="hero" :src="coverSrc" :alt="album.title" />
        </div>

        <div class="hero-main">
          <h1 class="hero-title">{{ album.title }}</h1>

          <!-- Album artist — link to the artist detail. Absent if none. -->
          <div v-if="album.artist" class="hero-artists">
            <RouterLink :to="`/artist/${album.artist.id}`" class="hero-artist-link">{{
              album.artist.name
            }}</RouterLink>
          </div>

          <!-- Identity stats — Type · Date · Label · Tracks -->
          <div class="hero-stats">
            <div v-if="recordTypeLabel" class="stat-cell">
              <span class="stat-label">Type</span>
              <span class="stat-val">{{ recordTypeLabel }}</span>
            </div>
            <div v-if="album.release_date" class="stat-cell">
              <span class="stat-label">Date</span>
              <span class="stat-val">{{ fmtDate(album.release_date) }}</span>
            </div>
            <div v-if="album.label" class="stat-cell">
              <span class="stat-label">Label</span>
              <span class="stat-val">{{ album.label }}</span>
            </div>
            <div class="stat-cell">
              <span class="stat-label">Tracks</span>
              <span class="stat-val">{{ album.total_tracks }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 2. Tracklist -->
      <section class="tracklist">
        <header class="sec-head">
          <h2 class="sec-title">Tracklist</h2>
          <span class="sec-count">
            {{ album.total_tracks }} {{ pl(album.total_tracks, 'track', 'tracks') }}
          </span>
        </header>
        <div class="track-list">
          <TrackCard
            v-for="row in trackRows"
            :key="row.key"
            :track="row.track"
            :position="row.position"
            show-artist
            show-duration
            :playing="rowPlaying(row.track.id)"
            @play="playTrack(row)"
            @click="onRowClick(row)"
          />
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import Artwork from '../components/Artwork.vue'
import BackButton from '../components/BackButton.vue'
import TrackCard from '../components/TrackCard.vue'
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtDate, pl } from '../utils/format'

const route = useRoute()
const router = useRouter()
const player = useAudioPlayer()
const album = ref(null)
const loading = ref(true)

const coverSrc = computed(() =>
  album.value?.has_artwork ? `/storage/album-artworks/${album.value.id}.jpg` : undefined,
)

// French labels for the (nullable) record_type enum.
const RECORD_TYPE_LABELS = {
  album: 'Album',
  single: 'Single',
  ep: 'EP',
  compile: 'Compilation',
}
const recordTypeLabel = computed(() => {
  const rt = album.value?.record_type
  if (!rt) return ''
  return RECORD_TYPE_LABELS[rt] || rt
})

// One TrackCard-ready row per tracklist entry. Album tracks are always
// identified catalog rows (no id/unresolved state), so the mapping is direct.
const trackRows = computed(() => {
  const list = album.value?.tracklist ?? []
  return list.map((t, i) => ({
    key: t.id,
    position: i + 1,
    track: {
      id: t.id,
      title: t.title,
      artist: t.artist,
      artists: t.artists,
      bpm: t.bpm,
      key: t.key,
      bpm_source: t.bpm_source,
      duration_ms: t.duration_ms,
      has_artwork: t.has_artwork,
      has_preview: t.has_preview,
      in_lib: t.in_lib,
    },
  }))
})

// A row is "playing" only while the audio is actually running.
function rowPlaying(id) {
  return player.isCurrent(id) && player.playing
}

function toPlayerTrack(t) {
  return {
    id: t.id,
    catalog_id: t.id,
    title: t.title,
    artist: t.artist,
    bpm: t.bpm,
    key: t.key,
    has_preview: t.has_preview,
  }
}

// Queue source: "next" walks the album's tracklist in order — playable rows only.
const playSource = {
  type: 'list',
  getItems: () =>
    trackRows.value.filter((r) => r.track.has_preview).map((r) => toPlayerTrack(r.track)),
}

function playTrack(row) {
  player.play(toPlayerTrack(row.track), playSource)
}

function onRowClick(row) {
  router.push(`/catalog/${row.track.id}`)
}

async function fetchDetail() {
  try {
    const { data } = await api.get(`/api/albums/${route.params.id}`)
    album.value = data
  } catch {
    album.value = null
  } finally {
    loading.value = false
  }
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

/* ============ HERO ============ */
.hero {
  position: relative;
  overflow: hidden;
  padding: var(--space-6);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--surface);
  display: grid;
  grid-template-columns: 216px 1fr;
  gap: var(--space-8);
  align-items: start;
}

/* Backdrop — the cover blurred behind everything, theme-adaptive opacity.
   `data-theme` is set on the document root, so the ancestor selector below wins. */
.hero-backdrop {
  position: absolute;
  inset: -48px;
  z-index: 0;
  pointer-events: none;
  opacity: 0.22;
}
[data-theme='dark'] .hero-backdrop {
  opacity: 0.5;
}
.hero-backdrop img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  filter: blur(48px) saturate(1.1);
}

.hero-cover {
  position: relative;
  z-index: 1;
  width: 216px;
  max-width: 100%;
}
.hero-cover :deep(.artwork--hero) {
  width: 100%;
}
/* Hero cover elevation — carried by the page on the artwork frame so its
   rounded corners are respected; Artwork.vue stays untouched. */
.hero-cover :deep(.aw-frame) {
  box-shadow: var(--shadow-md);
}
.hero-main {
  position: relative;
  z-index: 1;
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

/* Album artist */
.hero-artists {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
}
.hero-artist-link {
  font: 500 var(--fs-md)/1.3 var(--font-ui);
  color: var(--ink);
  text-decoration: none;
  transition: color 0.12s;
}
.hero-artist-link:hover {
  color: var(--accent-ink);
  text-decoration: underline;
}

/* Identity stats */
.hero-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
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

/* ============ TRACKLIST ============ */
.tracklist {
  margin-top: var(--space-8);
}
.track-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* ============ RESPONSIVE — container queries only ============ */
@container (max-width: 640px) {
  /* Horizontal padding only — never the shorthand (keep the vertical intact). */
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

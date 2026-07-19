<template>
  <div class="detail-view">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!djSet" class="state state--empty">
      <span>Set introuvable.</span>
      <RouterLink to="/sets" class="btn">Retour aux sets</RouterLink>
    </div>
    <template v-else>
      <!-- Back link -->
      <RouterLink to="/sets" class="dv-back">
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
        Sets
      </RouterLink>

      <!-- 1. Immersive hero (S1-S7) -->
      <section class="hero">
        <!-- Backdrop = blurred cover, theme-adaptive opacity (S1). Absent without artwork. -->
        <div v-if="djSet.has_artwork" class="hero-backdrop" aria-hidden="true">
          <img :src="coverSrc" alt="" />
        </div>

        <div class="hero-cover">
          <Artwork size="hero" :src="coverSrc" :alt="djSet.title" />
        </div>

        <div class="hero-main">
          <h1 class="hero-title">{{ djSet.title }}</h1>

          <!-- DJ artists — links, « b2b » separator from N ≥ 2 (S5). Absent if none. -->
          <div v-if="djSet.artists.length" class="hero-artists">
            <template v-for="(a, i) in djSet.artists" :key="a.artist_id">
              <span v-if="i > 0" class="hero-b2b">b2b</span>
              <RouterLink :to="`/artist/${a.artist_id}`" class="hero-artist-link">{{
                a.artist_name
              }}</RouterLink>
            </template>
          </div>

          <!-- Deduced genres — StyleTags only (S6). Absent when empty. -->
          <div v-if="topGenres.length" class="hero-tags">
            <RouterLink
              v-for="g in topGenres"
              :key="g.name"
              :to="`/style/${encodeURIComponent(g.name)}`"
              class="tag-link"
            >
              <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
            </RouterLink>
          </div>

          <!-- Identity stats (S3) — Durée · Date · Tracks · Identifiées (ring %, S4) -->
          <div class="hero-stats">
            <div v-if="djSet.duration_ms" class="stat-cell">
              <span class="stat-label">Durée</span>
              <span class="stat-val">{{ fmtMs(djSet.duration_ms) }}</span>
            </div>
            <div v-if="djSet.played_date" class="stat-cell">
              <span class="stat-label">Date</span>
              <span class="stat-val">{{ fmtDate(djSet.played_date) }}</span>
            </div>
            <div class="stat-cell">
              <span class="stat-label">Tracks</span>
              <span class="stat-val">{{ djSet.total_tracks }}</span>
            </div>
            <div class="stat-cell stat-cell--ident">
              <span class="stat-label">Identifiées</span>
              <span class="ident-val">
                <ScoreRing mode="pct" size="md" :score="identifiedRatio" :label="identifiedLabel" />
                <span class="ident-frac">{{ djSet.identified_tracks }}/{{ djSet.total_tracks }}</span>
              </span>
            </div>
          </div>

          <!-- Source link (S7) — PlatformLink + SOURCE micro-label. Absent if no url. -->
          <div v-if="djSet.source_url" class="hero-source">
            <PlatformLink :platform="sourcePlatform" :href="djSet.source_url" size="md" />
            <span class="hero-source-tx">
              <span class="hero-source-label">Source</span>
              <span class="hero-source-name">{{ sourceName }}</span>
            </span>
          </div>
        </div>
      </section>

      <!-- 2. Tracklist (S8-S9) -->
      <section class="tracklist">
        <header class="sec-head">
          <h2 class="sec-title">Tracklist</h2>
          <span class="sec-count">
            {{ djSet.total_tracks }} {{ pl(djSet.total_tracks, 'track', 'tracks') }} ·
            {{ djSet.identified_tracks }}
            {{ pl(djSet.identified_tracks, 'identifiée', 'identifiées') }}
          </span>
        </header>
        <div class="track-list">
          <TrackCard
            v-for="row in trackRows"
            :key="row.key"
            :track="row.track"
            :position="row.position"
            :timecode="row.timecode"
            :state="row.state"
            show-artist
            show-duration
            :playing="rowPlaying(row.track.id)"
            @play="playTrack(row)"
            @click="onRowClick(row)"
          />
        </div>
      </section>

      <!-- 3. Similar sets (S10) — hidden entirely when empty -->
      <section v-if="similarSets.length" class="similar">
        <header class="sec-head">
          <h2 class="sec-title">Sets similaires</h2>
          <span class="sec-count">{{ similarSets.length }} {{ pl(similarSets.length, 'set', 'sets') }}</span>
        </header>
        <div class="similar-grid">
          <SetCard v-for="s in similarSets" :key="s.id" :set="s" />
        </div>
      </section>

      <!-- 4. Admin: manage set artists — unchanged, gated is_admin -->
      <AdminCard label="Admin — Artistes du set" variant="warn">
        <div v-if="djSet.artists.length" class="set-artists-list">
          <div v-for="a in djSet.artists" :key="a.artist_id" class="set-artist-row">
            <RouterLink :to="`/artist/${a.artist_id}`" class="sa-name">{{
              a.artist_name
            }}</RouterLink>
            <span class="sa-role mono">{{ a.role }}</span>
            <button class="btn-row-action" @click="removeSetArtist(a.artist_id)">Retirer</button>
          </div>
        </div>
        <p v-else class="empty-hint">Aucun artiste lié.</p>
        <div class="sa-add-row">
          <input
            v-model="saQuery"
            class="admin-input"
            placeholder="Rechercher un artiste…"
            @input="onSaSearch"
          />
        </div>
        <div v-if="saResults.length" class="sa-results">
          <div v-for="a in saResults" :key="a.id" class="sa-hit" @click="addSetArtist(a.id)">
            <span class="sa-name">{{ a.name }}</span>
          </div>
        </div>
      </AdminCard>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useToast } from '../stores/toast.js'
import Artwork from '../components/Artwork.vue'
import TrackCard from '../components/TrackCard.vue'
import ScoreRing from '../components/ScoreRing.vue'
import SetCard from '../components/SetCard.vue'
import PlatformLink from '../components/PlatformLink.vue'
import StyleTag from '../components/StyleTag.vue'
import AdminCard from '../components/AdminCard.vue'
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtMs, fmtDate, pl } from '../utils/format'

const route = useRoute()
const router = useRouter()
const player = useAudioPlayer()
const djSet = ref(null)
const similarSets = ref([])
const loading = ref(true)

const coverSrc = computed(() =>
  djSet.value?.has_artwork ? `/storage/set-artworks/${djSet.value.id}.jpg` : undefined,
)

const topGenres = computed(() => (djSet.value?.top_genres ?? []).slice(0, 5))

// Ring % identifiées — proportion 0..1, division guarded when total_tracks is 0.
const identifiedRatio = computed(() => {
  const s = djSet.value
  if (!s || !s.total_tracks) return 0
  return s.identified_tracks / s.total_tracks
})
const identifiedLabel = computed(
  () => `${Math.round(identifiedRatio.value * 100)} % de tracks identifiées`,
)

// The back source value `1001tracklists` maps to the PlatformLink key `1001tl`;
// the others (youtube / soundcloud / trackid) are identical keys.
const SOURCE_PLATFORM = { '1001tracklists': '1001tl' }
const SOURCE_NAMES = {
  youtube: 'YouTube',
  soundcloud: 'SoundCloud',
  trackid: 'TrackID',
  '1001tracklists': '1001Tracklists',
}
const sourcePlatform = computed(() => {
  const src = djSet.value?.source
  return SOURCE_PLATFORM[src] || src
})
const sourceName = computed(() => SOURCE_NAMES[djSet.value?.source] || djSet.value?.source || '')

// Timestamped source URL — YouTube (?t= / &t=) and SoundCloud (#t=h:mm:ss) only;
// any other source (trackid, 1001tracklists) or a null url → no link (plain text).
function makeTimestampUrl(baseUrl, timecodeMs) {
  if (!baseUrl || !timecodeMs) return null
  const secs = Math.floor(timecodeMs / 1000)
  if (baseUrl.includes('youtube.com') || baseUrl.includes('youtu.be')) {
    return `${baseUrl}${baseUrl.includes('?') ? '&' : '?'}t=${secs}s`
  }
  if (baseUrl.includes('soundcloud.com')) {
    const h = Math.floor(secs / 3600)
    const m = Math.floor((secs % 3600) / 60)
    const s = secs % 60
    return `${baseUrl}#t=${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  return null
}

// One TrackCard-ready row per tracklist entry. State drives the shape:
//   'id'         → unidentified marker (title rendered "ID" by the component)
//   'unresolved' → read in the source but absent from the catalog (raw text, no link)
//   undefined    → identified track (full mapping expected by TrackCard)
const trackRows = computed(() => {
  const list = djSet.value?.tracklist ?? []
  const url = djSet.value?.source_url
  return list.map((t) => {
    let state
    if (t.is_id) state = 'id'
    else if (!t.catalog_id) state = 'unresolved'
    else state = undefined

    let track
    if (state === 'unresolved') {
      // The component reads track.title / track.artist → pass the raw fields.
      track = {
        id: t.catalog_id,
        title: t.raw_title,
        artist: t.raw_artist,
        has_artwork: false,
        has_preview: false,
        in_lib: false,
      }
    } else if (state === 'id') {
      // Title ignored by the component (always rendered "ID").
      track = {
        id: t.catalog_id,
        title: t.raw_title,
        has_artwork: false,
        has_preview: false,
        in_lib: false,
      }
    } else {
      track = {
        id: t.catalog_id,
        title: t.catalog_title || t.raw_title,
        artist: t.catalog_artist || t.raw_artist,
        artists: t.catalog_artists,
        bpm: t.bpm,
        key: t.key,
        duration_ms: t.duration_ms,
        has_artwork: t.has_artwork,
        has_preview: t.has_preview,
        in_lib: t.in_lib,
      }
    }

    return {
      key: t.id,
      position: t.position,
      timecode: { ms: t.timecode_ms, href: makeTimestampUrl(url, t.timecode_ms) || undefined },
      state,
      track,
      catalogId: state ? null : t.catalog_id,
    }
  })
})

// A row is "playing" only while the audio is actually running.
function rowPlaying(id) {
  return player.isCurrent(id) && player.playing
}

function playTrack(row) {
  const t = row.track
  player.play({
    id: t.id,
    catalog_id: t.id,
    title: t.title,
    artist: t.artist,
    bpm: t.bpm,
    key: t.key,
  })
}

// Only identified rows navigate; id/unresolved rows are inert.
function onRowClick(row) {
  if (!row.state && row.catalogId) router.push(`/catalog/${row.catalogId}`)
}

// ---- Admin: set artists (unchanged) ----
const saQuery = ref('')
const saResults = ref([])
let saTimer = null

function onSaSearch() {
  clearTimeout(saTimer)
  if (!saQuery.value.trim()) {
    saResults.value = []
    return
  }
  saTimer = setTimeout(async () => {
    const { data } = await api.get('/api/artists/', {
      params: { q: saQuery.value.trim(), limit: 10 },
    })
    saResults.value = data
  }, 300)
}

async function addSetArtist(artistId) {
  if (!djSet.value) return
  try {
    await api.post(`/api/admin/sets/${djSet.value.id}/artists`, { artist_id: artistId, role: 'dj' })
    const { data } = await api.get(`/api/sets/${route.params.id}`)
    djSet.value = data
    saQuery.value = ''
    saResults.value = []
  } catch {
    useToast().show('Erreur lors de l\'ajout de l\'artiste')
  }
}

async function removeSetArtist(artistId) {
  if (!djSet.value) return
  try {
    await api.delete(`/api/admin/sets/${djSet.value.id}/artists/${artistId}`)
    djSet.value.artists = djSet.value.artists.filter((a) => a.artist_id !== artistId)
  } catch {
    useToast().show('Erreur lors de la suppression de l\'artiste')
  }
}

// ---- Fetch — similar is independent of the main detail (the page never waits on it) ----
async function fetchDetail() {
  try {
    const { data } = await api.get(`/api/sets/${route.params.id}`)
    djSet.value = data
  } catch {
    djSet.value = null
  } finally {
    loading.value = false
  }
}

async function loadSimilar() {
  try {
    const { data } = await api.get(`/api/sets/${route.params.id}/similar`)
    similarSets.value = Array.isArray(data) ? data : []
  } catch {
    similarSets.value = []
  }
}

onMounted(() => {
  fetchDetail()
  loadSimilar()
})
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

/* Backdrop (S1) — the cover blurred behind everything, theme-adaptive opacity.
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

/* DJ artists (S5) */
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
.hero-b2b {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}

/* Deduced genres (S6) */
.hero-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-15);
}
.tag-link {
  display: inline-flex;
  max-width: 100%;
  text-decoration: none;
}

/* Identity stats (S3) */
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
/* Identifiées (S4) — ring % + fraction on one row */
.ident-val {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}
.ident-frac {
  font: 600 var(--fs-md)/1 var(--font-mono);
  color: var(--ink);
}

/* Source link (S7) */
.hero-source {
  display: inline-flex;
  align-self: flex-start;
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

/* ============ TRACKLIST (S8) ============ */
.tracklist {
  margin-top: var(--space-8);
}
.track-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* ============ SIMILAR SETS (S10) ============ */
.similar {
  margin-top: var(--space-8);
}
.similar-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
}
.similar-grid > * {
  min-width: 0;
}

/* ============ ADMIN ============ */
.set-artists-list {
  margin-bottom: var(--space-25);
}
.set-artist-row {
  display: flex;
  align-items: center;
  gap: var(--space-25);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--r-sm);
}
.set-artist-row:hover {
  background: var(--surface-2);
}
.sa-name {
  font: 500 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink);
  text-decoration: none;
}
.sa-name:hover {
  color: var(--accent-ink);
}
.sa-role {
  font-size: var(--fs-xs);
  color: var(--ink-3);
}
.mono {
  font-family: var(--font-mono);
  color: var(--ink-2);
}
.sa-add-row {
  display: flex;
  gap: var(--space-2);
}
.admin-input {
  flex: 1;
  padding: var(--space-15) var(--space-3);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface-2);
  color: var(--ink);
  font: 400 var(--fs-sm)/1 var(--font-ui);
  outline: none;
}
.admin-input:focus {
  border-color: var(--accent);
}
.sa-results {
  max-height: 160px;
  overflow-y: auto;
  margin-top: var(--space-15);
}
.sa-hit {
  padding: var(--space-15) var(--space-25);
  cursor: pointer;
  border-radius: var(--r-sm);
  font: 400 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink);
}
.sa-hit:hover {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.empty-hint {
  font-size: var(--fs-sm);
  color: var(--ink-3);
  font-style: italic;
  margin-bottom: var(--space-25);
}
.btn-row-action {
  margin-left: auto;
  padding: var(--space-05) var(--space-15);
  border-radius: 4px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  font: 500 var(--fs-xs)/1 var(--font-ui);
  cursor: pointer;
}
.btn-row-action:hover {
  color: var(--neg-ink);
  border-color: var(--neg-ink);
}

/* ============ RESPONSIVE — container queries only, 720 / 640 max-width ============ */
@container (max-width: 720px) {
  .similar-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
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
  .similar-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>

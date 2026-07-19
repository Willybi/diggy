<template>
  <div class="detail-view">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!artist" class="state state--empty">
      <span>Artiste introuvable.</span>
      <RouterLink to="/artists" class="btn">Retour aux artistes</RouterLink>
    </div>
    <template v-else>
      <!-- Back link -->
      <RouterLink to="/artists" class="dv-back">
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
        Artistes
      </RouterLink>

      <!-- 1. HERO — banner montage + avatar + genres + actions + repliée stats (A1-A4, A6) -->
      <section class="hero">
        <div class="hero-banner">
          <!-- Montage 6×2 : covers du catalog, tuiles cyclées (A3). 0 cover → bande rayée. -->
          <div v-if="bannerTiles.length" class="hb-tiles">
            <img
              v-for="(cid, i) in bannerTiles"
              :key="i"
              class="hb-tile"
              :src="`/storage/catalog-artworks/${cid}.jpg`"
              alt=""
            />
          </div>
          <div v-else class="hb-strip" aria-hidden="true"></div>
          <div class="hb-scrim" aria-hidden="true"></div>
          <h1 class="hb-name">{{ artist.name }}</h1>
        </div>

        <div class="hero-below">
          <!-- Avatar rond débordant (A4) — image ou initiale, jamais un Artwork rayé -->
          <div class="hero-avatar">
            <img
              v-if="artist.has_artwork"
              class="hero-av-img"
              :src="`/storage/artist-artworks/${artist.id}.jpg`"
              :alt="artist.name"
            />
            <span v-else class="hero-av-fb">{{ artist.name[0] }}</span>
          </div>

          <div class="hero-content">
            <!-- Genres cliquables → /style (rangée absente si 0) -->
            <div v-if="artist.genres.length" class="hero-genres">
              <RouterLink
                v-for="g in artist.genres"
                :key="g.name"
                :to="`/style/${encodeURIComponent(g.name)}`"
                class="tag-link"
              >
                <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
              </RouterLink>
            </div>

            <!-- Actions : aperçu (accent) · Suivre/Suivi · logos plateformes (A6) -->
            <div class="hero-actions">
              <button class="btn btn--accent" @click="playRandomTrack">
                <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M8 5v14l11-7z" />
                </svg>
                Écouter un aperçu
              </button>
              <button
                v-if="auth.isAuthenticated"
                class="btn btn-follow"
                :class="{ 'btn--ghost-accent': artist.following }"
                @click="toggleFollow"
              >
                {{ artist.following ? 'Suivi' : 'Suivre' }}
              </button>
              <PlatformLink v-if="deezerHref" platform="deezer" :href="deezerHref" size="md" />
              <PlatformLink v-if="trackidHref" platform="trackid" :href="trackidHref" size="md" />
            </div>

            <!-- Stats repliées (A2) — mono Catalog · In lib · Sets, pas de Rating -->
            <div class="hero-stats">
              <div class="stat-cell">
                <span class="stat-label">Catalog</span>
                <span class="stat-val">{{ artist.stats.nb_catalog ?? 0 }}</span>
              </div>
              <div class="stat-cell">
                <span class="stat-label">In lib</span>
                <span class="stat-val">{{ artist.stats.nb_lib ?? 0 }}</span>
              </div>
              <div class="stat-cell">
                <span class="stat-label">Sets</span>
                <span class="stat-val">{{ artist.stats.nb_sets ?? 0 }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 2. Aliases (ligne discrète, absente si vide) -->
      <div v-if="artist.aliases.length" class="aliases">
        <span class="aliases-label">Alias</span>
        <span class="aliases-names">{{ aliasNames }}</span>
      </div>

      <!-- slot futur: Bio artiste (source à définir) — aucun rendu tant que la feature n'existe pas -->

      <!-- 3. Tracks (A8) — TrackCard ligne, expand 10 + N -->
      <section class="tracks">
        <header class="sec-head">
          <h2 class="sec-title">Tracks</h2>
          <span class="sec-count">
            {{ artist.stats.nb_catalog }} {{ pl(artist.stats.nb_catalog, 'track', 'tracks') }}
          </span>
        </header>
        <div class="track-list">
          <TrackCard
            v-for="t in visibleTracks"
            :key="t.id"
            :track="t"
            show-artist
            show-duration
            :playing="rowPlaying(t.id)"
            @play="playTrack(t)"
            @click="goToTrack(t.id)"
          />
        </div>
        <div v-if="!showAllTracks && artist.catalog_tracks.length > 10" class="tracks-more">
          <button class="btn btn--sm" @click="showAllTracks = true">
            Afficher les {{ artist.catalog_tracks.length - 10 }} autres tracks
          </button>
        </div>
        <p v-if="artist.stats.nb_catalog > artist.catalog_tracks.length" class="more-note">
          … et {{ artist.stats.nb_catalog - artist.catalog_tracks.length }} autres tracks au catalog
        </p>
      </section>

      <!-- slot futur: Albums / Sorties — aucun rendu tant que l'objet album n'existe pas -->

      <!-- 4. Sets (A5, A7) — grille de SetCard, section masquée si vide -->
      <section v-if="artist.sets.length" class="sets">
        <header class="sec-head">
          <h2 class="sec-title">Sets</h2>
          <span class="sec-count">
            {{ artist.stats.nb_sets }} {{ pl(artist.stats.nb_sets, 'set', 'sets') }}
          </span>
        </header>
        <div class="sets-grid">
          <SetCard v-for="s in artist.sets" :key="s.set_id" :set="mapSet(s)">
            <template v-if="setIdentifiedPct(s) != null" #footer>
              <span class="set-ident-val">{{ setIdentifiedPct(s) }}&#8239;%</span>
              <span class="set-ident-lbl">identifiées</span>
            </template>
          </SetCard>
        </div>
      </section>

      <!-- 5. Artistes proches (A9) — ExpandableShelf + ShelfCard round, avatar + nom -->
      <div v-if="connections.length" class="proches">
        <ExpandableShelf
          title="Artistes proches"
          :items="connectionsPage"
          :total="connections.length"
          :loading="false"
          v-model:expanded="connectionsExpanded"
          v-model:page="connectionsPageNum"
          @load-page="onConnectionsLoadPage"
        >
          <template #default="{ item: c }">
            <ShelfCard
              variant="round"
              :image-src="c.has_artwork ? `/storage/artist-artworks/${c.artist_id}.jpg` : null"
              :title="c.name"
              :fallback-letter="c.name?.[0] || '?'"
              :to="`/artist/${c.artist_id}`"
            />
          </template>
        </ExpandableShelf>
      </div>

      <!-- 6. AdminCard — inchangée, gatée is_admin, en bas -->
      <AdminCard>
        <div class="admin-header">
          <span class="mono muted">deezer_id: {{ artist.deezer_id || '—' }}</span>
        </div>
        <div class="admin-link-row">
          <input
            v-model="dzQuery"
            class="admin-input"
            placeholder="Rechercher sur Deezer…"
            @input="onDzSearch"
          />
          <button
            v-if="artist.deezer_id && artist.deezer_id !== 'NOT_FOUND'"
            class="btn-ghost-sm danger"
            @click="unlinkDeezer"
          >
            Délier
          </button>
        </div>
        <div v-if="dzHits.length" class="dz-results">
          <div
            v-for="h in dzHits"
            :key="h.deezer_id"
            class="dz-row"
            :class="{ selected: selectedHit?.deezer_id === h.deezer_id }"
            @click="selectedHit = h"
          >
            <img v-if="h.picture" :src="h.picture" class="dz-pic" />
            <div>
              <span class="dz-name">{{ h.name }}</span>
              <span class="mono muted dz-meta">
                {{ h.nb_fan?.toLocaleString() }} fans ·
                <a
                  :href="`https://www.deezer.com/artist/${h.deezer_id}`"
                  target="_blank"
                  class="dz-link"
                  @click.stop
                  >dz:{{ h.deezer_id }}</a
                >
              </span>
            </div>
          </div>
        </div>
        <div v-if="selectedHit" class="admin-confirm">
          <span class="confirm-text">
            Lier → <strong>{{ selectedHit.name }}</strong> ({{ selectedHit.deezer_id }})
            <template v-if="selectedHit.deezer_id === artist.deezer_id"> (déjà lié)</template>
          </span>
          <button
            class="btn-accent-sm"
            :disabled="linking || selectedHit.deezer_id === artist.deezer_id"
            @click="confirmRelink"
          >
            {{ linking ? 'Liaison…' : 'Confirmer' }}
          </button>
        </div>
        <div v-if="adminMsg" class="admin-msg" :class="adminMsgType">{{ adminMsg }}</div>
      </AdminCard>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useAuthStore } from '../stores/auth.js'
import { useAudioPlayer } from '../stores/audioPlayer'
import StyleTag from '../components/StyleTag.vue'
import AdminCard from '../components/AdminCard.vue'
import ShelfCard from '../components/ShelfCard.vue'
import ExpandableShelf from '../components/ExpandableShelf.vue'
import TrackCard from '../components/TrackCard.vue'
import SetCard from '../components/SetCard.vue'
import PlatformLink from '../components/PlatformLink.vue'
import { pl } from '../utils/format'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const player = useAudioPlayer()
const artist = ref(null)
const loading = ref(true)
const showAllTracks = ref(false)
const connections = ref([])
const connectionsExpanded = ref(false)
const connectionsPageNum = ref(0)

const connectionsPage = computed(() => {
  if (!connectionsExpanded.value) return connections.value.slice(0, 12)
  const offset = connectionsPageNum.value * 48
  return connections.value.slice(offset, offset + 48)
})

function onConnectionsLoadPage() {
  // Client-side pagination — data already loaded, nothing to fetch
}

// Admin Deezer link
const dzQuery = ref('')
const dzHits = ref([])
const selectedHit = ref(null)
const linking = ref(false)
const adminMsg = ref('')
const adminMsgType = ref('ok')
let dzTimer = null

// Banner montage — 6×2 = 12 tiles cycled from the covers we have (A3).
// 0 cover → empty array → striped placeholder band rendered instead.
const bannerTiles = computed(() => {
  const covers = (artist.value?.catalog_tracks ?? []).filter((t) => t.has_artwork)
  if (!covers.length) return []
  return Array.from({ length: 12 }, (_, i) => covers[i % covers.length].id)
})

// First 10 tracks, or all once expanded (the button vanishes after expand — no collapse).
const visibleTracks = computed(() => {
  const tracks = artist.value?.catalog_tracks ?? []
  return showAllTracks.value ? tracks : tracks.slice(0, 10)
})

const aliasNames = computed(() => (artist.value?.aliases ?? []).map((a) => a.alias).join(' · '))

// External logos — a real id only (the NOT_FOUND sentinel is not a Deezer artist,
// so it must not produce a broken « Voir sur Deezer » link).
const deezerHref = computed(() => {
  const id = artist.value?.deezer_id
  return id && id !== 'NOT_FOUND' ? `https://www.deezer.com/artist/${id}` : null
})
const trackidHref = computed(() =>
  artist.value?.trackid_id ? `https://trackid.net/artist/${artist.value.trackid_id}` : null,
)

// SetCard expects `id`; the artist API gives `set_id`. Map + carry artists[]/duration_ms
// (lot back). `role` is never surfaced (A7).
function mapSet(s) {
  return {
    id: s.set_id,
    title: s.title,
    played_date: s.played_date,
    duration_ms: s.duration_ms,
    has_artwork: s.has_artwork,
    total_tracks: s.total_tracks,
    identified_tracks: s.identified_tracks,
    artists: s.artists,
  }
}

// % identifiées for the SetCard footer badge — null (no footer) when total is 0.
function setIdentifiedPct(s) {
  if (!s.total_tracks) return null
  return Math.round((s.identified_tracks / s.total_tracks) * 100)
}

// A row is "playing" only while the audio is actually running (same as Set/Playlist Detail).
function rowPlaying(id) {
  return player.isCurrent(id) && player.playing
}

function playRandomTrack() {
  player.playRandomArtist(artist.value.id)
}

function playTrack(t) {
  player.play({
    id: t.id,
    catalog_id: t.id,
    title: t.title,
    artist: t.artist,
    artist_id: t.artist_id,
    bpm: t.bpm,
    key: t.key,
  })
}

function goToTrack(id) {
  router.push(`/catalog/${id}`)
}

async function toggleFollow() {
  if (!artist.value) return
  // Optimistic update, rolled back if the API call fails
  const prev = artist.value.following
  artist.value.following = !prev
  try {
    if (prev) {
      await api.delete(`/api/artists/${artist.value.id}/follow`)
    } else {
      await api.post(`/api/artists/${artist.value.id}/follow`)
    }
  } catch {
    artist.value.following = prev
  }
}

function onDzSearch() {
  clearTimeout(dzTimer)
  selectedHit.value = null
  if (!dzQuery.value.trim()) {
    dzHits.value = []
    return
  }
  dzTimer = setTimeout(async () => {
    try {
      const { data } = await api.get('/api/admin/artists/search-deezer', {
        params: { q: dzQuery.value.trim() },
      })
      dzHits.value = data
    } catch {
      // 429 / network errors are surfaced by the api interceptor toast.
      dzHits.value = []
    }
  }, 300)
}

async function confirmRelink() {
  if (!selectedHit.value || !artist.value) return
  linking.value = true
  adminMsg.value = ''
  try {
    const { data } = await api.patch(`/api/admin/artists/${artist.value.id}/deezer`, {
      deezer_id: selectedHit.value.deezer_id,
    })
    if (data.merged && data.id !== artist.value.id) {
      adminMsg.value = `Fusionné avec l'artiste existant → redirection…`
      adminMsgType.value = 'ok'
      setTimeout(() => router.replace(`/artist/${data.id}`), 1200)
    } else {
      // Reload the page to reflect new name/artwork
      const { data: fresh } = await api.get(`/api/artists/${artist.value.id}`)
      artist.value = fresh
      dzQuery.value = ''
      dzHits.value = []
      selectedHit.value = null
      adminMsg.value = `Lié à ${data.name} (${data.deezer_id})`
      adminMsgType.value = 'ok'
    }
  } catch (e) {
    adminMsg.value = e.response?.data?.detail || 'Erreur'
    adminMsgType.value = 'err'
  } finally {
    linking.value = false
  }
}

async function unlinkDeezer() {
  if (!artist.value) return
  try {
    await api.patch(`/api/admin/artists/${artist.value.id}/deezer`, { deezer_id: '' })
    artist.value.deezer_id = null
    adminMsg.value = 'Deezer délié'
    adminMsgType.value = 'ok'
  } catch (e) {
    adminMsg.value = e.response?.data?.detail || 'Erreur'
    adminMsgType.value = 'err'
  }
}

async function loadArtist(id) {
  loading.value = true
  connections.value = []
  showAllTracks.value = false
  connectionsExpanded.value = false
  connectionsPageNum.value = 0
  try {
    const { data } = await api.get(`/api/artists/${id}`)
    artist.value = data
  } catch {
    artist.value = null
  } finally {
    loading.value = false
  }
  api
    .get(`/api/artists/${id}/connections`)
    .then(({ data }) => {
      connections.value = data
    })
    .catch(() => {})
}

onMounted(() => loadArtist(route.params.id))

watch(
  () => route.params.id,
  (id) => {
    if (id) loadArtist(id)
  },
)
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
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--surface);
}

/* Banner — montage + scrim + name */
.hero-banner {
  position: relative;
  height: 216px;
  border-bottom: 1px solid var(--line);
}
.hb-tiles {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  grid-template-rows: 1fr 1fr;
}
.hb-tile {
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: var(--surface-2);
}
/* 0 cover → standard striped placeholder band (A3), scrim kept for legibility. */
.hb-strip {
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(45deg, var(--surface-2) 0 6px, var(--surface-3) 6px 12px);
}
.hb-scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to top,
    oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.72),
    transparent 62%
  );
  pointer-events: none;
}
.hb-name {
  position: absolute;
  left: 156px;
  right: var(--space-6);
  bottom: var(--space-4);
  margin: 0;
  font: 700 var(--fs-xl)/1.1 var(--font-ui);
  color: var(--overlay-text);
  text-shadow:
    0 1px 4px var(--genre-tile-shadow),
    0 0 12px var(--genre-tile-shadow);
  letter-spacing: -0.01em;
  overflow-wrap: anywhere;
}

/* Below the banner — avatar (débordant) + content column */
.hero-below {
  display: flex;
  gap: var(--space-5);
  padding: 0 var(--space-6) var(--space-6);
}
.hero-avatar {
  flex: none;
  width: 120px;
  height: 120px;
  margin-top: -60px;
  border-radius: 50%;
  border: 3px solid var(--surface);
  overflow: hidden;
  background: var(--surface-3);
  display: grid;
  place-items: center;
  box-shadow: var(--shadow-md);
}
.hero-av-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.hero-av-fb {
  font: 600 var(--fs-fallback)/1 var(--font-ui);
  color: var(--ink-2);
  text-transform: uppercase;
}
.hero-content {
  flex: 1;
  min-width: 0;
  padding-top: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* Genres */
.hero-genres {
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

/* Actions */
.hero-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}
.btn-follow {
  cursor: pointer;
}

/* Stats repliées (A2) */
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

/* ============ ALIASES ============ */
.aliases {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  margin-top: var(--space-5);
}
.aliases-label {
  flex: none;
  font: 500 var(--fs-label)/1 var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--ink-3);
}
.aliases-names {
  font: 500 var(--fs-sm)/1.4 var(--font-ui);
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

/* ============ TRACKS (A8) ============ */
.tracks {
  margin-top: var(--space-8);
}
.track-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.tracks-more {
  display: flex;
  justify-content: center;
  margin-top: var(--space-3);
}
.more-note {
  margin: var(--space-3) 0 0;
  text-align: center;
  font: 400 var(--fs-xs)/1.4 var(--font-mono);
  color: var(--ink-3);
}

/* ============ SETS (A5, A7) ============ */
.sets {
  margin-top: var(--space-8);
}
.sets-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
}
.sets-grid > * {
  min-width: 0;
}
/* Footer badge « NN % identifiées » via the SetCard #footer slot (A5) — the card
   itself is untouched; the badge polish is a scoped :deep override of its footer. */
.sets-grid :deep(.sc-footer) {
  margin-top: auto;
  align-items: baseline;
  gap: var(--space-15);
  border-top: 1px solid var(--line);
  padding-top: var(--space-2);
}
.set-ident-val {
  font: 600 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
}
.set-ident-lbl {
  font: 400 var(--fs-xs)/1 var(--font-ui);
  color: var(--ink-3);
}

/* ============ ARTISTES PROCHES (A9) ============ */
.proches {
  margin-top: var(--space-8);
}
/* Polish only — the shelf/grid geometry per brief (ShelfCard/ExpandableShelf untouched). */
.proches :deep(.shelf),
.proches :deep(.shelf-grid) {
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: var(--space-2);
}

/* ============ ADMIN (inchangé) ============ */
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-25);
}
.admin-link-row {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
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
.dz-results {
  max-height: 200px;
  overflow-y: auto;
  margin-bottom: var(--space-2);
}
.dz-row {
  display: flex;
  align-items: center;
  gap: var(--space-25);
  padding: var(--space-15) var(--space-25);
  border-radius: var(--r-sm);
  cursor: pointer;
  border: 1px solid transparent;
}
.dz-row:hover {
  background: var(--surface-2);
}
.dz-row.selected {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.dz-pic {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  object-fit: cover;
}
.dz-name {
  display: block;
  font: 500 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink);
}
.dz-meta {
  display: block;
  font-size: var(--fs-xs);
  margin-top: var(--space-05);
}
.dz-link {
  color: var(--accent-ink);
  text-decoration: none;
}
.dz-link:hover {
  text-decoration: underline;
}
.admin-confirm {
  display: flex;
  align-items: center;
  gap: var(--space-25);
  padding: var(--space-25) var(--space-3);
  background: var(--surface-2);
  border-radius: var(--r-sm);
  margin-top: var(--space-15);
}
.confirm-text {
  font: 400 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink-2);
}
.btn-accent-sm {
  padding: var(--space-15) var(--space-3);
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-accent-sm:disabled {
  opacity: 0.5;
  cursor: default;
}
.btn-ghost-sm {
  padding: var(--space-15) var(--space-3);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
}
.btn-ghost-sm.danger:hover {
  color: var(--neg-ink);
  border-color: var(--neg-ink);
}
.admin-msg {
  font: 400 var(--fs-sm)/1 var(--font-ui);
  margin-top: var(--space-2);
  padding: var(--space-15) var(--space-25);
  border-radius: 4px;
}
.admin-msg.ok {
  color: var(--pos-ink);
  background: var(--pos-soft);
}
.admin-msg.err {
  color: var(--neg-ink);
  background: var(--neg-soft);
}
.mono {
  font-family: var(--font-mono);
  color: var(--ink-2);
}
.muted {
  color: var(--ink-3);
}

/* ============ RESPONSIVE — container queries only, 720 / 640 max-width ============ */
@container (max-width: 720px) {
  .sets-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
@container (max-width: 640px) {
  /* Horizontal padding only — never the shorthand (keep the vertical intact). */
  .detail-view {
    padding-inline: var(--page-px-mobile);
  }
  .hero-banner {
    height: 150px;
  }
  /* Name left-aligned, no longer offset by the avatar. */
  .hb-name {
    left: var(--space-4);
    right: var(--space-4);
    font-size: var(--fs-lg);
  }
  /* Avatar back in flow (72 px) below the banner; content stacks under it. */
  .hero-below {
    flex-direction: column;
    gap: var(--space-3);
  }
  .hero-avatar {
    width: 72px;
    height: 72px;
    margin-top: var(--space-3);
  }
  .hero-content {
    padding-top: 0;
  }
  .sets-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>

<template>
  <div class="detail-view">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!track" class="state state--empty">
      <span>Track introuvable.</span>
      <RouterLink to="/catalog" class="btn">Retour au catalog</RouterLink>
    </div>
    <template v-else>
      <!-- Back link -->
      <RouterLink to="/catalog" class="dv-back">
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
        Catalog
      </RouterLink>

      <!-- Hero -->
      <section class="hero">
        <div class="hero-cover">
          <Artwork size="hero" :src="coverSrc" :alt="track.title" :in-lib="track.in_lib" />
        </div>

        <div class="hero-main">
          <h1 class="hero-title">{{ track.title }}</h1>

          <!-- Artist chip(s) — one pill per artist -->
          <div v-if="track.artists?.length" class="hero-artists">
            <RouterLink
              v-for="a in track.artists"
              :key="a.id"
              :to="`/artist/${a.id}`"
              class="artist-chip"
            >
              <img
                v-if="a.has_artwork"
                class="chip-av"
                :src="`/storage/artist-artworks/${a.id}.jpg`"
                :alt="a.name"
              />
              <span v-else class="chip-av"></span>
              {{ a.name }}
            </RouterLink>
          </div>

          <!-- Genres + Rekordbox tags -->
          <div v-if="track.genres?.length || track.style || track.tags?.length" class="hero-tags">
            <template v-if="track.genres?.length">
              <RouterLink
                v-for="g in track.genres"
                :key="g.name"
                :to="`/style/${encodeURIComponent(g.name)}`"
                class="tag-link"
              >
                <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
              </RouterLink>
            </template>
            <StyleTag v-else-if="track.style" :name="track.style" />
            <span v-for="tag in track.tags" :key="tag" class="rb-tag">{{ tag }}</span>
          </div>

          <!-- Musical stats integrated in the hero (D1) -->
          <div class="hero-stats">
            <div class="stat-cell">
              <span class="stat-label">BPM</span>
              <span class="stat-val">{{ fmtBpm(track.bpm) }}</span>
            </div>
            <div class="stat-cell">
              <span class="stat-label">Key</span>
              <span class="stat-val stat-val--key">{{ track.key || '—' }}</span>
            </div>
            <div class="stat-cell">
              <span class="stat-label">Durée</span>
              <span class="stat-val">{{ fmtMs(track.duration_ms) }}</span>
            </div>
            <div class="stat-cell">
              <span class="stat-label">Année</span>
              <span class="stat-val">{{ releaseYear }}</span>
            </div>
          </div>

          <!-- Actions -->
          <div class="hero-actions">
            <HeroPlayer
              v-if="track.has_preview"
              :catalog-id="track.id"
              :title="track.title"
              :artist="track.artist"
              :artist-id="track.artist_id"
              :bpm="track.bpm"
              :track-key="track.key"
            />
            <LikeDislike v-model="opinion" />
            <div class="coll-add-wrap">
              <button class="btn-coll" @click="toggleCollDropdown">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.7"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <rect x="3" y="5" width="18" height="16" rx="2" />
                  <path d="M12 10v6M9 13h6" />
                </svg>
                <span>Collection</span>
              </button>
              <div v-if="showCollDropdown" class="coll-dropdown">
                <div v-if="collLoading" class="coll-dd-state">Chargement…</div>
                <template v-else>
                  <div v-if="!userCollections.length" class="coll-dd-state">Aucune collection</div>
                  <button
                    v-for="c in userCollections"
                    :key="c.id"
                    class="coll-dd-item"
                    :disabled="c._added"
                    @click="addToCollection(c)"
                  >
                    {{ c.name }}
                    <span v-if="c._added" class="coll-dd-check">✓</span>
                  </button>
                  <div class="coll-dd-new">
                    <input
                      v-if="creatingNew"
                      ref="newCollInput"
                      v-model="newCollName"
                      class="coll-dd-input"
                      type="text"
                      placeholder="Nom de la collection"
                      @keydown.enter="createCollection"
                      @keydown.esc="cancelNewColl"
                      @blur="cancelNewColl"
                    />
                    <button v-else class="coll-dd-add" @click="startNewColl">
                      + Nouvelle collection
                    </button>
                  </div>
                </template>
              </div>
            </div>
          </div>

          <!-- External links + label -->
          <div v-if="track.beatport_id || track.deezer_id || track.label" class="hero-links">
            <PlatformLink v-if="track.beatport_id" platform="beatport" :href="beatportUrl" />
            <PlatformLink v-if="track.deezer_id" platform="deezer" :href="deezerUrl" />
            <span v-if="track.label" class="hero-label">
              <span class="hero-label-tag">Label</span>
              <span class="hero-label-name">{{ track.label }}</span>
            </span>
          </div>
        </div>
      </section>

      <!-- Découverte -->
      <div class="discovery">
        <!-- Du même artiste — TrackCard without artist, truncated to 6 -->
        <section v-if="track.same_artist_tracks.length" class="disc-block">
          <header class="disc-head">
            <h2 class="disc-title">Du même artiste</h2>
            <span class="disc-count">{{ track.same_artist_tracks.length }}</span>
          </header>
          <div class="mini-grid">
            <TrackCard
              v-for="t in sameArtistShown"
              :key="t.id"
              :track="t"
              :playing="rowPlaying(t.id)"
              @play="playTrack(t)"
              @click="goTrack(t.id)"
            />
          </div>
          <div v-if="track.same_artist_tracks.length > SAME_ARTIST_LIMIT" class="disc-more">
            <button class="btn btn--sm" @click="sameArtistExpanded = !sameArtistExpanded">
              {{ sameArtistExpanded ? 'Afficher moins' : `Afficher plus (${sameArtistHidden})` }}
            </button>
          </div>
        </section>

        <!-- Tracks similaires — TrackCard with artist + ScoreRing -->
        <section v-if="similarLoading || similarTracks.length" class="disc-block">
          <header class="disc-head">
            <h2 class="disc-title">Tracks similaires</h2>
            <span v-if="similarTracks.length" class="disc-count">{{ similarTracks.length }}</span>
          </header>
          <div v-if="similarLoading" class="sim-skeleton">
            <div v-for="n in 4" :key="n" class="skel-row">
              <span class="skel-art"></span>
              <span class="skel-lines">
                <span class="skel-bar skel-bar--1"></span>
                <span class="skel-bar skel-bar--2"></span>
              </span>
            </div>
          </div>
          <div v-else class="mini-grid">
            <TrackCard
              v-for="t in similarTracks"
              :key="t.id"
              :track="t"
              show-artist
              :playing="rowPlaying(t.id)"
              @play="playTrack(t)"
              @click="goTrack(t.id)"
            >
              <template #end>
                <ScoreRing
                  size="sm"
                  :score="t.similarity.score"
                  :label="simLabel(t.similarity.score)"
                />
              </template>
            </TrackCard>
          </div>
        </section>
      </div>

      <!-- Où on l'entend — 2-column layout (D3) -->
      <div v-if="track.set_appearances.length || track.radar_appearances.length" class="rel-cols">
        <!-- Apparaît dans (sets) — clickable timecode -->
        <section v-if="track.set_appearances.length" class="rel-card">
          <header class="rel-head">
            <h2 class="rel-title">Apparaît dans</h2>
            <span class="rel-count">
              {{ track.set_appearances.length }}
              {{ pl(track.set_appearances.length, 'set', 'sets') }}
            </span>
          </header>
          <RouterLink
            v-for="s in setsShown"
            :key="s.set_id"
            :to="`/set/${s.set_id}`"
            class="rel-row"
          >
            <span class="rel-tx">
              <span class="rel-row-title">{{ s.set_title }}</span>
              <span class="rel-meta">
                <span v-if="s.timecode_ms != null" class="timecode"
                  >▶ {{ fmtCue(s.timecode_ms) }}</span
                >
                <span v-if="s.played_date" class="rel-date">{{ fmtDate(s.played_date) }}</span>
              </span>
            </span>
            <span class="rel-chevron">›</span>
          </RouterLink>
          <button
            v-if="track.set_appearances.length > REL_LIMIT"
            class="rel-more"
            @click="setsExpanded = !setsExpanded"
          >
            {{ setsExpanded ? 'Afficher moins' : `Afficher plus (${setsHidden})` }}
          </button>
        </section>

        <!-- Détecté dans (playlists) — source glyph + date -->
        <section v-if="track.radar_appearances.length" class="rel-card">
          <header class="rel-head">
            <h2 class="rel-title">Détecté dans</h2>
            <span class="rel-count">
              {{ track.radar_appearances.length }}
              {{ pl(track.radar_appearances.length, 'playlist', 'playlists') }}
            </span>
          </header>
          <RouterLink
            v-for="r in playlistsShown"
            :key="r.playlist_id"
            :to="`/playlists/${r.playlist_id}`"
            class="rel-row"
          >
            <span class="rel-tx">
              <span class="rel-row-title">{{ r.playlist_title || 'Playlist' }}</span>
              <span class="rel-meta">
                <PlatformLink variant="glyph" :platform="(r.playlist_source || '').toLowerCase()" />
                <span class="rel-date">{{ fmtDate(r.detected_at) }}</span>
              </span>
            </span>
            <span class="rel-chevron">›</span>
          </RouterLink>
          <button
            v-if="track.radar_appearances.length > REL_LIMIT"
            class="rel-more"
            @click="playlistsExpanded = !playlistsExpanded"
          >
            {{ playlistsExpanded ? 'Afficher moins' : `Afficher plus (${playlistsHidden})` }}
          </button>
        </section>
      </div>

      <!-- AdminCard — unchanged, gated is_admin, at the bottom -->
      <AdminCard variant="warn">
        <div class="admin-header">
          <span class="mono muted"
            >beatport_id: {{ track.beatport_id || '—' }} · deezer_id: {{ track.deezer_id || '—' }} ·
            isrc: {{ track.isrc || '—' }}</span
          >
        </div>

        <div class="admin-row">
          <button class="btn-sync" :disabled="enriching" @click="enrichBeatport(false)">
            {{
              enriching
                ? 'Recherche…'
                : track.beatport_id
                  ? 'Re-enrichir Beatport'
                  : 'Enrichir via Beatport'
            }}
          </button>
          <button class="btn-sync" :disabled="enriching" @click="enrichBeatport(true)">
            {{ enriching ? '…' : 'Forcer genre Beatport' }}
          </button>
          <span v-if="enrichResult" class="enrich-result" :class="enrichResult.cls">{{
            enrichResult.text
          }}</span>
        </div>

        <div class="admin-row" style="margin-top: var(--space-2)">
          <button
            class="btn-sync"
            :disabled="!track.deezer_id || fetchingDzGenre"
            @click="fetchDeezerGenre(false)"
          >
            {{ fetchingDzGenre ? 'Recherche…' : 'Genre Deezer' }}
          </button>
          <template v-if="dzGenreResult">
            <span class="enrich-result" :class="dzGenreResult.cls">{{ dzGenreResult.text }}</span>
            <button
              v-if="dzGenreResult.genres?.length"
              class="btn-sync"
              :disabled="fetchingDzGenre"
              @click="applyDeezerGenres()"
            >
              Appliquer {{ dzGenreResult.genres.join(', ') }}
            </button>
          </template>
        </div>
      </AdminCard>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import Artwork from '../components/Artwork.vue'
import TrackCard from '../components/TrackCard.vue'
import ScoreRing from '../components/ScoreRing.vue'
import PlatformLink from '../components/PlatformLink.vue'
import StyleTag from '../components/StyleTag.vue'
import HeroPlayer from '../components/HeroPlayer.vue'
import AdminCard from '../components/AdminCard.vue'
import LikeDislike from '../components/LikeDislike.vue'
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtMs, fmtBpm, fmtDate, fmtCue, pl } from '../utils/format'

const SAME_ARTIST_LIMIT = 6
const REL_LIMIT = 5

const route = useRoute()
const router = useRouter()
const player = useAudioPlayer()
const track = ref(null)
const loading = ref(true)
const enriching = ref(false)
const enrichResult = ref(null)
const fetchingDzGenre = ref(false)
const dzGenreResult = ref(null)
const opinion = ref(null)
const showCollDropdown = ref(false)
const userCollections = ref([])
const collLoading = ref(false)
const creatingNew = ref(false)
const newCollName = ref('')
const newCollInput = ref(null)
const savingColl = ref(false)
const similarTracks = ref([])
const similarLoading = ref(false)
const sameArtistExpanded = ref(false)
const setsExpanded = ref(false)
const playlistsExpanded = ref(false)

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

// A row is "playing" only while the audio is actually running (drives both the
// TrackCard tint and its pause icon).
function rowPlaying(id) {
  return player.isCurrent(id) && player.playing
}

function simLabel(score) {
  return `Similarité ${Math.round(score * 10)} /10`
}

const coverSrc = computed(() => {
  if (!track.value) return undefined
  const t = track.value
  if (t.lib_track_id && t.has_artwork) return `/storage/artworks/${t.lib_track_id}.jpg`
  if (t.has_artwork) return `/storage/catalog-artworks/${t.id}.jpg`
  return undefined
})

const releaseYear = computed(() =>
  track.value?.release_date ? new Date(track.value.release_date).getFullYear() : '—',
)

const beatportUrl = computed(() =>
  track.value?.beatport_id ? `https://www.beatport.com/track/-/${track.value.beatport_id}` : '',
)
const deezerUrl = computed(() =>
  track.value?.deezer_id ? `https://www.deezer.com/track/${track.value.deezer_id}` : '',
)

const sameArtistShown = computed(() => {
  const all = track.value?.same_artist_tracks ?? []
  return sameArtistExpanded.value ? all : all.slice(0, SAME_ARTIST_LIMIT)
})
const sameArtistHidden = computed(() =>
  Math.max(0, (track.value?.same_artist_tracks?.length ?? 0) - SAME_ARTIST_LIMIT),
)

const setsShown = computed(() => {
  const all = track.value?.set_appearances ?? []
  return setsExpanded.value ? all : all.slice(0, REL_LIMIT)
})
const setsHidden = computed(() =>
  Math.max(0, (track.value?.set_appearances?.length ?? 0) - REL_LIMIT),
)

const playlistsShown = computed(() => {
  const all = track.value?.radar_appearances ?? []
  return playlistsExpanded.value ? all : all.slice(0, REL_LIMIT)
})
const playlistsHidden = computed(() =>
  Math.max(0, (track.value?.radar_appearances?.length ?? 0) - REL_LIMIT),
)

// Persist opinion (canonical avis endpoint, same as CatalogView)
watch(opinion, async (val) => {
  if (!track.value) return
  try {
    await api.patch(`/api/catalog/${track.value.id}/avis`, { avis: val })
  } catch {
    // silent
  }
})

async function toggleCollDropdown() {
  showCollDropdown.value = !showCollDropdown.value
  if (showCollDropdown.value && !userCollections.value.length) {
    collLoading.value = true
    try {
      const { data } = await api.get('/api/collections/')
      userCollections.value = data.map((c) => ({ ...c, _added: false }))
    } finally {
      collLoading.value = false
    }
  }
}

async function addToCollection(coll) {
  if (coll._added) return
  try {
    await api.post(`/api/collections/${coll.id}/items`, { catalog_id: track.value.id })
    coll._added = true
  } catch (e) {
    if (e.response?.status === 409) coll._added = true
  }
}

// Inline "+ Nouvelle collection" flow inside the dropdown.
function startNewColl() {
  creatingNew.value = true
  newCollName.value = ''
  nextTick(() => newCollInput.value?.focus())
}

function cancelNewColl() {
  creatingNew.value = false
  newCollName.value = ''
}

async function createCollection() {
  const name = newCollName.value.trim()
  if (!name || savingColl.value) return
  savingColl.value = true
  try {
    const { data } = await api.post('/api/collections/', { name })
    await api.post(`/api/collections/${data.id}/items`, { catalog_id: track.value.id })
    userCollections.value.push({ ...data, _added: true })
    cancelNewColl()
  } catch {
    // silent — leave the input open, like the rest of the dropdown
  } finally {
    savingColl.value = false
  }
}

async function enrichBeatport(forceGenre = false) {
  enriching.value = true
  enrichResult.value = null
  try {
    const params = forceGenre ? '?force_genre=true' : ''
    const { data } = await api.post(`/api/admin/enrich-beatport/${track.value.id}${params}`, {})
    if (data.status === 'enriched') {
      track.value.bpm = data.bpm
      track.value.key = data.key
      track.value.label = data.label
      track.value.genres = (data.genres || []).map((g) =>
        typeof g === 'string' ? { name: g, pillar: 'autres', depth: 0 } : g,
      )
      track.value.beatport_id = data.beatport_id
      track.value.bpm_source = 'beatport'
      track.value.key_source = 'beatport'
      const parts = [`BPM=${data.bpm}`, `Key=${data.key}`]
      if (data.genres?.length) parts.push(`Genres=${data.genres.join(', ')}`)
      if (data.label) parts.push(`Label=${data.label}`)
      enrichResult.value = { text: parts.join(' '), cls: 'ok' }
    } else if (data.status === 'unchanged') {
      enrichResult.value = { text: 'Déjà à jour', cls: 'muted' }
    } else {
      if (forceGenre) track.value.genres = []
      enrichResult.value = {
        text: 'Non trouvé sur Beatport' + (forceGenre ? ' — genre effacé' : ''),
        cls: 'warn',
      }
    }
  } catch (e) {
    enrichResult.value = { text: e.response?.data?.detail || 'Erreur', cls: 'err' }
  } finally {
    enriching.value = false
  }
}

async function fetchDeezerGenre() {
  fetchingDzGenre.value = true
  dzGenreResult.value = null
  try {
    const { data } = await api.get(`/api/admin/deezer-genre/${track.value.id}`)
    if (data.genres?.length) {
      dzGenreResult.value = { text: data.genres.join(', '), cls: 'ok', genres: data.genres }
    } else {
      dzGenreResult.value = { text: 'Aucun genre Deezer', cls: 'warn' }
    }
  } catch (e) {
    dzGenreResult.value = { text: e.response?.data?.detail || 'Erreur', cls: 'err' }
  } finally {
    fetchingDzGenre.value = false
  }
}

async function applyDeezerGenres() {
  fetchingDzGenre.value = true
  try {
    const { data } = await api.get(`/api/admin/deezer-genre/${track.value.id}?apply=true`)
    const rawGenres = data.genres || dzGenreResult.value.genres
    track.value.genres = rawGenres.map((g) =>
      typeof g === 'string' ? { name: g, pillar: 'autres', depth: 0 } : g,
    )
    dzGenreResult.value = { text: `Appliqué : ${rawGenres.join(', ')}`, cls: 'ok' }
  } catch (e) {
    dzGenreResult.value = { text: e.response?.data?.detail || 'Erreur', cls: 'err' }
  } finally {
    fetchingDzGenre.value = false
  }
}

async function loadSimilar(catalogId) {
  similarLoading.value = true
  try {
    const { data } = await api.get(`/api/catalog/${catalogId}/similar?limit=8`)
    similarTracks.value = data
  } catch {
    // silencieux
  } finally {
    similarLoading.value = false
  }
}

async function loadTrack(id) {
  loading.value = true
  track.value = null
  similarTracks.value = []
  enrichResult.value = null
  dzGenreResult.value = null
  sameArtistExpanded.value = false
  setsExpanded.value = false
  playlistsExpanded.value = false
  showCollDropdown.value = false
  creatingNew.value = false
  newCollName.value = ''
  try {
    const { data } = await api.get(`/api/catalog/${id}`)
    track.value = data
    opinion.value = data.avis ?? null
    loadSimilar(id)
  } catch {
    track.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => route.params.id,
  (id) => {
    if (id) loadTrack(id)
  },
)
onMounted(() => loadTrack(route.params.id))
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

/* Artist chips */
.hero-artists {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.artist-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-05) var(--space-25) var(--space-05) var(--space-1);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  text-decoration: none;
  color: var(--ink-2);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  transition:
    background 0.12s,
    color 0.12s,
    border-color 0.12s;
}
.artist-chip:hover {
  background: var(--surface-2);
  color: var(--ink);
}
.chip-av {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  flex: none;
  border: 1px solid var(--line);
  background: var(--surface-3);
  object-fit: cover;
}

/* Genres + Rekordbox tags */
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
.rb-tag {
  display: inline-flex;
  align-items: center;
  font: 500 var(--fs-xs)/1 var(--font-mono);
  letter-spacing: 0.03em;
  color: var(--ink-2);
  background: var(--surface-2);
  border: 1px solid var(--line-2);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--r-pill);
  white-space: nowrap;
}

/* Musical stats (D1) */
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
.stat-val--key {
  color: var(--accent-ink);
}

/* Actions */
.hero-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-1);
}

/* Collection add button + dropdown */
.coll-add-wrap {
  position: relative;
}
.btn-coll {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  height: 38px;
  padding: 0 var(--space-3);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition:
    color 0.12s,
    border-color 0.12s;
}
.btn-coll:hover {
  color: var(--ink);
  border-color: var(--ink-3);
}
.btn-coll svg {
  width: 16px;
  height: 16px;
}
.coll-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 200px;
  max-height: 240px;
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-md);
  z-index: 50;
  padding: var(--space-1);
}
.coll-dd-state {
  padding: var(--space-25) var(--space-3);
  font: 400 var(--fs-sm) var(--font-ui);
  color: var(--ink-3);
}
.coll-dd-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: none;
  background: transparent;
  color: var(--ink);
  font: 500 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  border-radius: var(--r-sm);
  text-align: left;
  transition: background 0.1s;
}
.coll-dd-item:hover:not(:disabled) {
  background: var(--surface-2);
}
.coll-dd-item:disabled {
  color: var(--ink-3);
  cursor: default;
}
.coll-dd-check {
  color: var(--pos-ink);
  font-weight: 600;
}

/* "+ Nouvelle collection" — separated footer that swaps to an inline input */
.coll-dd-new {
  margin-top: var(--space-1);
  padding-top: var(--space-1);
  border-top: 1px solid var(--line);
}
.coll-dd-add {
  display: block;
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: none;
  background: transparent;
  color: var(--accent-ink);
  font: 500 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  border-radius: var(--r-sm);
  text-align: left;
  transition: background 0.1s;
}
.coll-dd-add:hover {
  background: var(--surface-2);
}
.coll-dd-input {
  width: 100%;
  height: 34px;
  padding: 0 var(--space-3);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--bg);
  color: var(--ink);
  font: 500 var(--fs-sm) var(--font-ui);
  outline: none;
  box-sizing: border-box;
}
.coll-dd-input::placeholder {
  color: var(--ink-3);
}
.coll-dd-input:focus {
  border-color: var(--accent);
}

/* External links + label */
.hero-links {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}
.hero-label {
  display: inline-flex;
  align-items: baseline;
  gap: var(--space-2);
}
.hero-label-tag {
  font: 500 var(--fs-label)/1 var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--ink-3);
}
.hero-label-name {
  font: 500 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink-2);
}

/* ============ DÉCOUVERTE ============ */
.discovery {
  margin-top: var(--space-8);
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
}
.disc-block {
  min-width: 0;
}
.disc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.disc-title {
  margin: 0;
  font: 600 var(--fs-title)/1 var(--font-ui);
  color: var(--ink);
  letter-spacing: -0.01em;
}
.disc-count {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}
.disc-more {
  display: flex;
  justify-content: center;
  margin-top: var(--space-3);
}

.mini-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2) var(--space-4);
}
/* grid items must shrink below min-content for equal 1fr columns */
.mini-grid > * {
  min-width: 0;
}
@container (max-width: 720px) {
  .mini-grid {
    grid-template-columns: 1fr;
  }
}

/* Similar loading skeleton — 4 rows, pulse on opacity */
.sim-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.skel-row {
  display: grid;
  grid-template-columns: 36px 1fr;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--surface);
}
.skel-art {
  width: 36px;
  height: 36px;
  border-radius: var(--r-xs);
  background: var(--surface-2);
  animation: pulse 1.2s ease-in-out infinite;
}
.skel-lines {
  display: flex;
  flex-direction: column;
  gap: var(--space-15);
}
.skel-bar {
  height: 9px;
  border-radius: var(--r-pill);
  background: var(--surface-2);
  animation: pulse 1.2s ease-in-out infinite;
}
.skel-bar--1 {
  width: 60%;
}
.skel-bar--2 {
  width: 35%;
}
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}

/* ============ OÙ ON L'ENTEND ============ */
.rel-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
  align-items: start;
  margin-top: var(--space-8);
}
@container (max-width: 720px) {
  .rel-cols {
    grid-template-columns: 1fr;
  }
}
.rel-card {
  min-width: 0;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.rel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--line);
}
.rel-title {
  margin: 0;
  font: 600 var(--fs-title)/1 var(--font-ui);
  color: var(--ink);
}
.rel-count {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
}
.rel-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 52px;
  padding: var(--space-2) var(--space-4);
  border-top: 1px solid var(--line);
  text-decoration: none;
  color: inherit;
  transition: background 0.12s;
}
.rel-row:first-of-type {
  border-top: none;
}
.rel-row:hover {
  background: var(--surface-2);
}
.rel-tx {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.rel-row-title {
  font: 500 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rel-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font: 400 var(--fs-xs)/1.3 var(--font-mono);
  color: var(--ink-3);
}
.rel-date {
  color: var(--ink-3);
}
.rel-chevron {
  flex: none;
  font-size: var(--fs-md);
  line-height: 1;
  color: var(--ink-3);
}
.timecode {
  display: inline-flex;
  align-items: center;
  gap: var(--space-05);
  padding: var(--space-05) var(--space-15);
  background: var(--accent-soft);
  color: var(--accent-ink);
  border-radius: var(--r-xs);
  font: 500 var(--fs-xs)/1 var(--font-mono);
  white-space: nowrap;
}
.rel-more {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 40px;
  padding: var(--space-2) var(--space-4);
  border: none;
  border-top: 1px solid var(--line);
  background: transparent;
  color: var(--accent-ink);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
  transition: background 0.12s;
}
.rel-more:hover {
  background: var(--surface-2);
}

/* ============ ADMIN ============ */
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-25);
}
.mono {
  font-family: var(--font-mono);
  color: var(--ink-2);
}
.muted {
  color: var(--ink-3);
}
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
.enrich-result {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
}
.enrich-result.ok {
  color: var(--pos-ink);
}
.enrich-result.warn {
  color: var(--warn-ink);
}
.enrich-result.err {
  color: var(--neg-ink);
}
.enrich-result.muted {
  color: var(--ink-3);
}

/* ============ RESPONSIVE ============ */
@container (max-width: 640px) {
  .detail-view {
    padding: var(--page-px-mobile);
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
  .rel-chevron {
    display: none;
  }
}
</style>

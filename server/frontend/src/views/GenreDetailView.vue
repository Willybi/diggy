<template>
  <div class="detail-view" :data-fam="genre ? tone.pillar : null" :style="genre ? `--d:${tone.depth}` : null">
    <!-- États page -->
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!genre" class="state state--empty">
      <span>Genre introuvable.</span>
      <RouterLink to="/genres" class="btn">Retour aux genres</RouterLink>
    </div>

    <template v-else>
      <BackButton fallback="/genres" label="Genres" />

      <!-- 1. HERO immersif — mosaïque 3×2 + voile + teinte pilier + scrim + overlay (G1-G6) -->
      <section class="hero">
        <div class="hero-mosaic" aria-hidden="true">
          <div v-for="(slot, i) in sixSlots" :key="i" class="hero-tile">
            <img v-if="slot" :src="slot" alt="" loading="lazy" @error="(e) => e.target.remove()" />
          </div>
        </div>
        <div class="hero-veil" aria-hidden="true"></div>
        <div class="hero-tint" aria-hidden="true"></div>
        <div class="hero-scrim" aria-hidden="true"></div>

        <div class="hero-overlay">
          <span class="hero-pill"><span class="hp-dot"></span>{{ pillarLabel }}</span>

          <div class="hero-titlerow">
            <h1 class="hero-title">{{ genre.name }}</h1>
            <!-- Cluster preuve sociale — absent si 0 avatar, rien ne le remplace (G6) -->
            <div v-if="heroAvatars.length" class="hero-avatars">
              <RouterLink
                v-for="a in heroAvatars"
                :key="a.id"
                :to="`/artist/${a.id}`"
                class="hero-av"
                :aria-label="a.name"
              >
                <img :src="a.image" :alt="a.name" loading="lazy" @error="() => (brokenAvatars[a.id] = true)" />
              </RouterLink>
              <span v-if="avatarsMore > 0" class="hero-av-more">+{{ fmtNum(avatarsMore) }}</span>
            </div>
          </div>

          <div class="hero-bottom">
            <div class="hero-stats">
              <div class="hstat">
                <span class="hs-k">Tracks</span>
                <span class="hs-v">{{ fmtNum(genre.trackCount) }}</span>
              </div>
              <div class="hstat">
                <span class="hs-k">Artistes</span>
                <span class="hs-v">{{ fmtNum(genre.artistCount) }}</span>
              </div>
              <div class="hstat">
                <span class="hs-k">BPM</span>
                <span class="hs-v">{{ heroBpm }}</span>
              </div>
            </div>
            <button
              class="hero-play"
              :class="{ playing: isPlaying }"
              :aria-label="isPlaying ? 'Pause' : `Écouter un extrait aléatoire de ${genre.name}`"
              @click="onHeroPlay"
            >
              <svg v-if="!isPlaying" viewBox="0 0 24 24" fill="currentColor">
                <path d="M8 5v14l11-7z" />
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="currentColor">
                <path d="M6 5h4v14H6zm8 0h4v14h-4z" />
              </svg>
            </button>
          </div>
        </div>
      </section>

      <!-- 2. Stats secondaires + actions — une seule ligne, remplace la StatStrip -->
      <div class="statline">
        <div class="sline-stats">
          <div class="sstat">
            <span class="ss-k">En bib</span>
            <span v-if="genre.inLibCount > 0" class="ss-v ss-v--pos">{{ fmtNum(genre.inLibCount) }}</span>
            <span v-else class="ss-v ss-v--empty">—</span>
          </div>
          <div class="sstat">
            <span class="ss-k">Sets</span>
            <span class="ss-v">{{ fmtNum(genre.setCount || 0) }}</span>
          </div>
          <div class="sstat">
            <span class="ss-k">Playlists</span>
            <span class="ss-v">{{ fmtNum(genre.playlistCount || 0) }}</span>
          </div>
        </div>
        <div class="sline-actions">
          <button class="btn btn--accent" @click="player.playRandom(genreName)">
            <svg viewBox="0 0 24 24" fill="currentColor" width="15" height="15">
              <path d="M8 5v14l11-7z" />
            </svg>
            Écouter un aperçu
          </button>
          <LikeDislike
            :model-value="genreOpinion"
            @update:model-value="(v) => opinions.set('genre', genreName, v)"
          />
        </div>
      </div>

      <!-- 3. Shelf Artistes -->
      <ExpandableShelf
        v-if="artists.length"
        class="shelf-panel shelf-artists"
        title="Artistes"
        :items="artists"
        :total="artistsTotal"
        :loading="artistsLoading"
        v-model:expanded="artistsExpanded"
        v-model:page="artistsPage"
        @load-page="onArtistsLoadPage"
      >
        <template #default="{ item: a }">
          <ShelfCard
            variant="round"
            :image-src="a.hasArtwork ? `/storage/artist-artworks/${a.id}.jpg` : null"
            :title="a.name"
            :subtitle="`${fmtNum(a.trackCount)} tracks`"
            :to="`/artist/${a.id}`"
            :fallback-letter="(a.name || '?')[0]"
          >
            <template #badge>
              <span v-if="a.inLibCount > 0" class="ac-lib">{{ fmtNum(a.inLibCount) }} en bib</span>
            </template>
          </ShelfCard>
        </template>
      </ExpandableShelf>

      <!-- 4. Shelf Sets — masquée si 0 ; pied « NN % de ce genre » (G7) -->
      <RelBlock v-if="sets.length" class="shelf-panel" title="Sets" :count="setsTotal">
        <div class="cards-grid">
          <ShelfCard
            v-for="s in sets"
            :key="s.id"
            :image-src="s.hasArtwork ? `/storage/set-artworks/${s.id}.jpg` : null"
            :title="s.title"
            :subtitle="s.playedDate ? fmtDate(s.playedDate) : null"
            :to="`/set/${s.id}`"
          >
            <template #badge>
              <span v-if="setPct(s) != null" class="card-foot card-foot--sets">
                <span class="cf-pct">{{ setPct(s) }}&#8239;%</span>
                <span class="cf-lbl">de ce genre</span>
              </span>
            </template>
          </ShelfCard>
        </div>
        <button
          v-if="sets.length < setsTotal"
          class="load-more"
          :disabled="setsLoading"
          @click="fetchSets(true)"
        >
          {{ setsLoading ? 'Chargement…' : `Voir les ${setsTotal - sets.length} autres` }}
        </button>
      </RelBlock>

      <!-- 5. Shelf Playlists — masquée si 0 ; pied glyph source + N tracks (G8) -->
      <RelBlock v-if="playlists.length" class="shelf-panel" title="Playlists" :count="playlistsTotal">
        <div class="cards-grid">
          <ShelfCard
            v-for="p in playlists"
            :key="p.id"
            :image-src="p.hasArtwork ? `/storage/playlist-artworks/${p.id}.jpg` : null"
            :title="p.title"
            :subtitle="p.owner || null"
            :to="`/playlists/${p.id}`"
          >
            <template #badge>
              <span class="card-foot card-foot--pl">
                <PlatformLink :platform="p.source" variant="glyph" />
                <span class="cf-count">{{ fmtNum(p.genreTrackCount) }} tracks</span>
              </span>
            </template>
          </ShelfCard>
        </div>
        <button
          v-if="playlists.length < playlistsTotal"
          class="load-more"
          :disabled="playlistsLoading"
          @click="fetchPlaylists(true)"
        >
          {{ playlistsLoading ? 'Chargement…' : `Voir les ${playlistsTotal - playlists.length} autres` }}
        </button>
      </RelBlock>
      <!-- 6. Tracks — aperçu fini : une seule page par état de filtre, la suite
           se consulte dans Explorer pré-filtré sur le genre (D8.b). -->
      <section class="tracks-section">
        <header class="tracks-head">
          <h2 class="sec-title">
            Tracks <span class="sec-count">{{ fmtNum(trackTotal) }}</span>
          </h2>
          <div class="tracks-tools">
            <SearchBox
              v-model="trackSearch"
              placeholder="Rechercher…"
              @update:modelValue="fetchTracks(true)"
            />
            <div class="sortseg" role="group" aria-label="Trier les tracks">
              <button
                v-for="opt in sortOptions"
                :key="opt.value"
                class="seg"
                :class="{ active: trackSort === opt.value }"
                @click="setSort(opt.value)"
              >
                {{ opt.label }}
              </button>
            </div>
            <button
              class="lib-toggle"
              :class="{ active: trackInLib === 1 }"
              :aria-pressed="trackInLib === 1"
              @click="toggleLib"
            >
              <span class="lt-dot"></span>En bib
            </button>
          </div>
        </header>

        <div v-if="!tracks.length && !tracksLoading" class="tracks-empty">
          <span class="te-msg">Aucune track ne correspond.</span>
          <button class="btn btn--sm" @click="resetTrackFilters">Réinitialiser</button>
        </div>
        <div v-else class="track-list">
          <TrackCard
            v-for="t in tracks"
            :key="t.id"
            :track="toCard(t)"
            :class="{ liked: t.avis === 'liked', disliked: t.avis === 'disliked' }"
            show-artist
            show-duration
            :playing="rowPlaying(t.id)"
            @play="playTrack(t)"
            @click="goToTrack(t.id)"
          >
            <template #end>
              <LikeDislike :model-value="t.avis" @update:model-value="(v) => setTrackAvis(t, v)" />
            </template>
          </TrackCard>
        </div>

        <RouterLink
          v-if="!tracksLoading && trackTotal > tracks.length"
          class="load-more load-more--link"
          :to="`/explorer?genre=${encodeURIComponent(genreName)}`"
        >
          Voir les {{ fmtNum(trackTotal - tracks.length) }} autres dans Explorer
        </RouterLink>
      </section>

      <!-- 7. Genres proches -->
      <RelBlock
        v-if="neighbors.length"
        class="shelf-panel"
        title="Genres proches"
        :count="neighbors.length"
      >
        <div class="neighbor-grid">
          <RouterLink
            v-for="n in neighbors"
            :key="n.name"
            :to="`/style/${encodeURIComponent(n.name)}`"
            class="neighbor-chip"
          >
            <StyleTag :name="n.name" :family="n.pillar" :depth="n.depth" />
            <span class="neighbor-meta">{{ fmtNum(n.commonArtists) }} artistes en commun</span>
          </RouterLink>
        </div>
      </RelBlock>

      <!-- 8. Admin — en dernier, gate is_admin interne à AdminCard -->
      <AdminCard>
        <div class="admin-row">
          <input v-model="renameVal" class="admin-input" placeholder="Nouveau nom…" />
          <button
            class="btn-ghost-sm"
            :disabled="!renameVal.trim() || renameVal.trim() === genre.name"
            @click="doRename"
          >
            Renommer
          </button>
        </div>
        <div class="admin-row">
          <input
            v-model="mergeQuery"
            class="admin-input"
            placeholder="Fusionner dans…"
            @input="onMergeSearch"
          />
          <button class="btn-ghost-sm" :disabled="!mergeTarget" @click="doMerge">Fusionner</button>
        </div>
        <div v-if="mergeSuggestions.length" class="merge-list">
          <div
            v-for="s in mergeSuggestions"
            :key="s.name"
            class="merge-item"
            :class="{ selected: mergeTarget === s.name }"
            @click="selectMergeSuggestion(s)"
          >
            {{ s.name }} <span class="mono muted">({{ s.trackCount }})</span>
          </div>
        </div>
        <div v-if="adminMsg" class="admin-msg" :class="adminMsgType">{{ adminMsg }}</div>
      </AdminCard>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useAudioPlayer } from '../stores/audioPlayer'
import { useOpinionsStore } from '../stores/opinions.js'
import { styleTone, PILLAR_LABELS } from '../composables/useStyleMap.js'
import { usePaginatedList } from '../composables/usePaginatedList.js'
import { fmtDate, fmtNum } from '../utils/format'
import BackButton from '../components/BackButton.vue'
import TrackCard from '../components/TrackCard.vue'
import LikeDislike from '../components/LikeDislike.vue'
import PlatformLink from '../components/PlatformLink.vue'
import StyleTag from '../components/StyleTag.vue'
import ExpandableShelf from '../components/ExpandableShelf.vue'
import ShelfCard from '../components/ShelfCard.vue'
import RelBlock from '../components/RelBlock.vue'
import SearchBox from '../components/SearchBox.vue'
import AdminCard from '../components/AdminCard.vue'

const route = useRoute()
const router = useRouter()
const player = useAudioPlayer()
const opinions = useOpinionsStore()

// -- State --
const loading = ref(true)
const genre = ref(null)
const artists = ref([])
const artistsTotal = ref(0)
const artistsLoading = ref(false)
const artistsExpanded = ref(false)
const artistsPage = ref(0)
const sets = ref([])
const setsTotal = ref(0)
const setsLoading = ref(false)
const playlists = ref([])
const playlistsTotal = ref(0)
const playlistsLoading = ref(false)
const neighbors = ref([])

// Aperçu 8 cards (grilles 4 colonnes × 2 rangées) — le « Voir les N autres »
// n'apparaît donc que si total > 8 (spec Playlists, appliquée aux deux shelves).
const SHELF_PREVIEW = 8

// Admin
const renameVal = ref('')
const mergeQuery = ref('')
const mergeTarget = ref(null)
const mergeSuggestions = ref([])
const adminMsg = ref('')
const adminMsgType = ref('')
let mergeTimer = null

function selectMergeSuggestion(s) {
  mergeTarget.value = s.name
  mergeQuery.value = s.name
  mergeSuggestions.value = []
}

// -- Computed --
const genreName = computed(() => decodeURIComponent(route.params.genre || ''))
const tone = computed(() => styleTone({ pillar: genre.value?.pillar, depth: genre.value?.depth }))
const pillarLabel = computed(() => PILLAR_LABELS[tone.value.pillar] || PILLAR_LABELS.autres)
const isPlaying = computed(() => player.genrePlaying === genreName.value)
const genreOpinion = computed(() => opinions.get('genre', genreName.value))

const sixSlots = computed(() => {
  const aw = genre.value?.artworks || []
  return Array.from({ length: 6 }, (_, i) => aw[i] || null)
})

// Avatars cassés retirés du cluster — le « +N » = artistCount − avatars affichés (G6).
const brokenAvatars = reactive({})
const heroAvatars = computed(() =>
  (genre.value?.artists || []).filter((a) => !brokenAvatars[a.id]).slice(0, 3),
)
const avatarsMore = computed(() =>
  Math.max(0, (genre.value?.artistCount || 0) - heroAvatars.value.length),
)

// « — » quand aucun BPM (bpmLo/bpmHi coalescés à 0 côté back) — jamais « 0–0 ».
const heroBpm = computed(() => {
  const g = genre.value
  if (!g || (!g.bpmLo && !g.bpmHi)) return '—'
  const lo = Math.round(g.bpmLo)
  const hi = Math.round(g.bpmHi)
  return lo === hi ? String(lo) : `${lo}–${hi}`
})

const sortOptions = [
  { value: 'recent', label: 'Récent' },
  { value: 'bpm', label: 'BPM' },
  { value: 'key', label: 'Key' },
  { value: 'alpha', label: 'A–Z' },
]

// -- Tracklist (usePaginatedList : sort/query natifs, inLib via extraParams) --
const trackSearch = ref('')
const trackSort = ref('recent')
const trackInLib = ref(null)

// Pas de sentinelle rendue (aperçu fini, D8.b) : l'observer du composable reste
// sans ref liée = no-op. loadMoreTracks survit à la sentinelle — c'est le canal
// PROGRAMMATIQUE de la file de lecture (playNext tire la page suivante).
const {
  items: tracks,
  total: trackTotal,
  loading: tracksLoading,
  fetch: fetchTracks,
  loadMore: loadMoreTracks,
} = usePaginatedList({
  endpoint: () => `/api/genres/tracks/${encodeURIComponent(genreName.value)}`,
  pageSize: 50,
  sort: trackSort,
  query: trackSearch,
  extraParams: () => (trackInLib.value != null ? { inLib: trackInLib.value } : null),
})

// L'endpoint genre renvoie du camelCase ; TrackCard parle le snake_case du catalog.
function toCard(t) {
  return {
    id: t.id,
    title: t.title,
    artist: t.artist,
    artists: t.artists,
    bpm: t.bpm,
    key: t.key,
    duration_ms: t.durationMs,
    has_artwork: t.hasArtwork,
    has_preview: t.hasPreview,
    in_lib: t.inLib,
  }
}

function setSort(val) {
  trackSort.value = val
  fetchTracks(true)
}

function toggleLib() {
  trackInLib.value = trackInLib.value === 1 ? null : 1
  fetchTracks(true)
}

function resetTrackFilters() {
  trackSearch.value = ''
  trackInLib.value = null
  fetchTracks(true)
}

// Avis par rangée : delta local sur l'item + endpoint canonique (pattern Explorer).
async function setTrackAvis(t, avis) {
  const prev = t.avis
  t.avis = avis
  player.syncAvis(t.id, avis)
  try {
    await api.patch(`/api/catalog/${t.id}/avis`, { avis })
  } catch {
    t.avis = prev
    player.syncAvis(t.id, prev)
  }
}

// -- Lecture --
function onHeroPlay() {
  if (isPlaying.value) {
    player.close()
  } else {
    player.playRandom(genreName.value)
  }
}

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
    avis: t.avis,
    has_preview: t.hasPreview,
  }
}

// Queue source: "next" follows the tracklist as displayed (sort + filters),
// pulling the next page when the loaded window runs out.
const playSource = {
  type: 'list',
  getItems: () => tracks.value.map(toPlayerTrack),
  loadMore: loadMoreTracks,
  onAvis: (id, avis) => {
    const row = tracks.value.find((r) => r.id === id)
    if (row) row.avis = avis
  },
}

function playTrack(t) {
  player.play(toPlayerTrack(t), playSource)
}

function goToTrack(id) {
  router.push(`/catalog/${id}`)
}

// -- Helpers --
function setPct(s) {
  return s.totalTracks ? Math.round((s.genreTrackCount / s.totalTracks) * 100) : null
}

// -- Data fetching --
async function fetchGenre() {
  loading.value = true
  genre.value = null
  try {
    const { data } = await api.get(`/api/genres/detail/${encodeURIComponent(genreName.value)}`)
    genre.value = data
    renameVal.value = data.name
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
  }
}

async function fetchArtists() {
  artistsLoading.value = true
  try {
    const { data } = await api.get(`/api/genres/artists/${encodeURIComponent(genreName.value)}`, {
      params: { limit: 12, offset: 0 },
    })
    artists.value = data.items
    artistsTotal.value = data.total
  } catch {
    artists.value = []
  } finally {
    artistsLoading.value = false
  }
}

function onArtistsLoadPage({ offset, limit }) {
  artistsLoading.value = true
  api
    .get(`/api/genres/artists/${encodeURIComponent(genreName.value)}`, {
      params: { limit, offset },
    })
    .then(({ data }) => {
      artists.value = data.items
      artistsTotal.value = data.total
    })
    .catch(() => {})
    .finally(() => {
      artistsLoading.value = false
    })
}

async function fetchSets(append = false) {
  setsLoading.value = true
  try {
    const params = { limit: append ? 12 : SHELF_PREVIEW }
    if (append) params.offset = sets.value.length
    const { data } = await api.get(`/api/genres/sets/${encodeURIComponent(genreName.value)}`, {
      params,
    })
    sets.value = append ? [...sets.value, ...data.items] : data.items
    setsTotal.value = data.total
  } catch {
    if (!append) sets.value = []
  } finally {
    setsLoading.value = false
  }
}

async function fetchPlaylists(append = false) {
  playlistsLoading.value = true
  try {
    const params = { limit: append ? 12 : SHELF_PREVIEW }
    if (append) params.offset = playlists.value.length
    const { data } = await api.get(`/api/genres/playlists/${encodeURIComponent(genreName.value)}`, {
      params,
    })
    playlists.value = append ? [...playlists.value, ...data.items] : data.items
    playlistsTotal.value = data.total
  } catch {
    if (!append) playlists.value = []
  } finally {
    playlistsLoading.value = false
  }
}

async function fetchNeighbors() {
  try {
    const { data } = await api.get(`/api/genres/neighbors/${encodeURIComponent(genreName.value)}`)
    neighbors.value = data.items
  } catch {
    neighbors.value = []
  }
}

// -- Admin --
async function doRename() {
  const newName = renameVal.value.trim()
  if (!newName || newName === genre.value.name) return
  try {
    const { data } = await api.patch(`/api/genres/rename/${encodeURIComponent(genre.value.name)}`, {
      new_name: newName,
    })
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
  if (!mergeQuery.value.trim()) {
    mergeSuggestions.value = []
    return
  }
  mergeTimer = setTimeout(async () => {
    try {
      const { data } = await api.get('/api/genres', {
        params: { q: mergeQuery.value.trim(), limit: 5 },
      })
      mergeSuggestions.value = data.items.filter((g) => g.name !== genre.value?.name)
    } catch {
      mergeSuggestions.value = []
    }
  }, 250)
}

async function doMerge() {
  if (!mergeTarget.value) return
  if (!confirm(`Fusionner "${genre.value.name}" dans "${mergeTarget.value}" ?`)) return
  try {
    const { data } = await api.post('/api/genres/merge', {
      source: genre.value.name,
      target: mergeTarget.value,
    })
    adminMsg.value = `Fusionné ${data.affected} tracks → ${data.target}`
    adminMsgType.value = 'ok'
    router.replace(`/style/${encodeURIComponent(data.target)}`)
  } catch (e) {
    adminMsg.value = e.response?.data?.detail || 'Erreur'
    adminMsgType.value = 'err'
  }
}

// -- Lifecycle --
watch(
  () => route.params.genre,
  (val) => {
    if (!val) return
    trackSearch.value = ''
    trackSort.value = 'recent'
    trackInLib.value = null
    artistsExpanded.value = false
    artistsPage.value = 0
    mergeQuery.value = ''
    mergeTarget.value = null
    mergeSuggestions.value = []
    adminMsg.value = ''
    fetchGenre()
  },
)

onMounted(fetchGenre)
</script>

<style scoped>
.detail-view {
  container-type: inline-size;
  max-width: var(--detail-max-w);
  margin-inline: auto;
  padding: var(--space-6) var(--page-px) var(--space-15x);
  /* Hue pilier + multiplicateur de chroma (« autres » → 0, G11) */
  --th: 0;
  --hc: 1;
}
.detail-view[data-fam='house'] {
  --th: var(--hue-house);
}
.detail-view[data-fam='techno'] {
  --th: var(--hue-techno);
}
.detail-view[data-fam='trance'] {
  --th: var(--hue-trance);
}
.detail-view[data-fam='dnb'] {
  --th: var(--hue-dnb);
}
.detail-view[data-fam='hardcore'] {
  --th: var(--hue-hardcore);
}
.detail-view[data-fam='harddance'] {
  --th: var(--hue-harddance);
}
.detail-view[data-fam='autres'] {
  --th: 0;
  --hc: 0;
}
/* Teinte pilier prolongée sur le corps, bornée à 520px (G11) */
.detail-view[data-fam] {
  background: linear-gradient(
    to bottom,
    oklch(var(--ct-l) calc(var(--ct-c) * var(--hc)) var(--th)),
    var(--bg) 520px
  );
}

/* État introuvable — message + bouton retour (utilitaire .state global) */
.state--empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
}

/* ══ 1. HERO (G1-G6) ══ */
.hero {
  position: relative;
  overflow: hidden;
  height: 340px;
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
}
.hero-mosaic {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: repeat(2, 1fr);
}
/* Tuile manquante : dégradé teinté pilier + hairline inset — jamais de trou */
.hero-tile {
  position: relative;
  overflow: hidden;
  background: linear-gradient(
    145deg,
    oklch(var(--fb-l1) calc(var(--fb-c1) * var(--hc)) var(--th)),
    oklch(var(--fb-l2) calc(var(--fb-c2) * var(--hc)) var(--th))
  );
  box-shadow: inset 0 0 0 1px var(--ct-line);
}
.hero-tile img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* Trois couches fixes, dans cet ordre (G2) : voile, teinte pilier, scrim vertical */
.hero-veil,
.hero-tint,
.hero-scrim {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.hero-veil {
  background: oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.34);
}
.hero-tint {
  background: oklch(var(--tag-dot-l) calc(var(--tag-dot-c) * 0.9) var(--th) / 0.3);
}
.detail-view[data-fam='autres'] .hero-tint {
  background: none;
}
.hero-scrim {
  background: linear-gradient(
    to top,
    oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.92) 0%,
    oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.62) 38%,
    oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.18) 74%,
    oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.28) 100%
  );
}

/* Overlay en colonne calée en bas : label pilier → titre → (stats · play) */
.hero-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-5);
}
.hero-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  padding: var(--space-1) var(--space-25);
  border-radius: var(--r-pill);
  background: var(--overlay-soft);
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--genre-tile-ink);
}
.hp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
  background: oklch(
    calc(var(--tag-dot-l) + 0.04 * var(--d, 0))
      calc(var(--tag-dot-c) * (1 - 0.19 * var(--d, 0)) * var(--hc)) var(--th)
  );
}
.hero-titlerow {
  align-self: stretch;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-4);
}
/* Échelle fluide cqw, 2 lignes max, jamais d'ellipsis sur une ligne (G3) */
.hero-title {
  margin: 0;
  min-width: 0;
  font: 700 clamp(var(--fs-lg), 4.3cqw, var(--fs-display)) / 1.08 var(--font-ui);
  letter-spacing: -0.01em;
  color: var(--overlay-text);
  text-shadow:
    0 1px 4px var(--genre-tile-shadow),
    0 0 12px var(--genre-tile-shadow);
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.hero-avatars {
  display: flex;
  align-items: center;
  flex: none;
}
.hero-av {
  display: block;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  flex: none;
  margin-left: -12px;
  border: 2px solid var(--genre-tile-ink);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.hero-av:first-child {
  margin-left: 0;
}
[data-theme='dark'] .hero-av {
  border-color: var(--genre-tile-border-dark);
}
.hero-av img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.hero-av-more {
  margin-left: var(--space-2);
  font: 600 var(--fs-sm)/1 var(--font-mono);
  color: var(--genre-tile-ink);
  text-shadow: 0 1px 3px var(--genre-tile-shadow);
}
.hero-bottom {
  align-self: stretch;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-4);
}
.hero-stats {
  display: flex;
  gap: var(--space-8);
}
.hstat {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.hs-k {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--genre-tile-ink);
  opacity: 0.78;
}
.hs-v {
  font: 600 var(--fs-md)/1 var(--font-mono);
  color: var(--overlay-text);
  text-shadow: 0 1px 3px var(--genre-tile-shadow);
}
/* Play rond 56px en verre → hover accent plein — seul le bouton d'actions
   garde le .btn--accent de la page (G5) */
.hero-play {
  flex: none;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 0;
  padding: 0;
  display: grid;
  place-items: center;
  cursor: pointer;
  background: var(--overlay-soft);
  color: var(--overlay-text);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: inset 0 0 0 1px var(--genre-tile-ink);
  transition:
    background 0.15s,
    color 0.15s,
    box-shadow 0.15s;
}
.hero-play:hover,
.hero-play:focus-visible {
  background: var(--accent);
  color: var(--on-accent);
  box-shadow: none;
}
.hero-play svg {
  width: 22px;
  height: 22px;
}
.hero-play:not(.playing) svg {
  margin-left: var(--space-05);
}

/* ══ 2. Stats secondaires + actions ══ */
.statline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3) var(--space-5);
  margin-top: var(--space-4);
}
.sline-stats {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-5);
}
.sstat {
  display: inline-flex;
  align-items: baseline;
  gap: var(--space-15);
}
.ss-k {
  font: 500 var(--fs-label)/1 var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--ink-3);
}
.ss-v {
  font: 600 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
}
.ss-v--pos {
  color: var(--pos-ink);
}
.ss-v--empty {
  color: var(--ink-3);
}
.sline-actions {
  display: flex;
  align-items: center;
  gap: var(--space-25);
  margin-left: auto;
}
/* Avis genre : 38px, repos surface/ink-2/line — toujours visible (porte un état) */
.sline-actions :deep(.ld-btn) {
  width: 38px;
  height: 38px;
  border-color: var(--line);
  color: var(--ink-2);
}

/* ══ Panneau commun des shelves ══ */
.shelf-panel :deep(.rel-title) {
  font: 600 var(--fs-md)/1.2 var(--font-ui);
}
.shelf-panel :deep(.rel-count) {
  background: none;
  padding: 0;
}
.shelf-panel :deep(.rel-body) {
  box-shadow: var(--shadow-sm);
}

/* ── 3. Artistes (ShelfCard round 72px + N tracks + N en bib) ── */
.shelf-artists :deep(.shelf),
.shelf-artists :deep(.shelf-grid) {
  grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
}
/* Repli mono-rangée à toute largeur : rangée 1 explicite, rangées implicites à 0
   (row-gap: 0 pour ne pas gonfler la boîte clippée ; l'item d'une rangée 0, étiré
   et overflow:hidden, se résout à 0 et ne peint rien) — plus de max-height fragile.
   Résidu accepté : les items masqués restent dans le DOM (liens tabbables invisibles),
   comme le crop 180px d'origine du composant. */
.shelf-artists :deep(.shelf) {
  grid-template-rows: auto;
  grid-auto-rows: 0;
  row-gap: 0;
  max-height: none;
}
.shelf-artists :deep(.shelf > *) {
  overflow: hidden;
}
.shelf-artists :deep(.sc-img) {
  width: 72px;
  height: 72px;
  background: var(--surface-3);
}
.shelf-artists :deep(.sc-fb) {
  font: 600 var(--fs-md)/1 var(--font-ui);
  color: var(--ink-2);
}
.shelf-artists :deep(.sc-title) {
  font: 500 var(--fs-xs)/1.3 var(--font-ui);
}
.shelf-artists :deep(.sc-sub) {
  font: 400 var(--fs-nano)/1 var(--font-mono);
}
.ac-lib {
  font: 500 var(--fs-nano)/1 var(--font-mono);
  color: var(--pos-ink);
}

/* ── 4-5. Sets & Playlists (grille 4 → 3 → 2, cartes fer à gauche) ── */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  padding: var(--space-4);
}
.cards-grid :deep(.shelf-card) {
  width: auto;
  flex: initial;
  align-items: stretch;
}
.cards-grid :deep(.sc-img) {
  width: 100%;
  height: auto;
  aspect-ratio: 1;
  border-radius: var(--r-sm);
  /* Placeholder rayé standard quand l'artwork manque */
  background: repeating-linear-gradient(45deg, var(--surface-2) 0 6px, var(--surface-3) 6px 12px);
}
.cards-grid :deep(.sc-fb) {
  display: none;
}
.cards-grid :deep(.sc-title) {
  font: 600 var(--fs-xs)/1.3 var(--font-ui);
  text-align: left;
}
.cards-grid :deep(.sc-sub) {
  font: 400 var(--fs-nano)/1 var(--font-mono);
  text-align: left;
}
/* Pied de carte sous hairline (G7/G8) */
.card-foot {
  width: 100%;
  display: flex;
  gap: var(--space-15);
  border-top: 1px solid var(--line);
  padding-top: var(--space-2);
  margin-top: var(--space-1);
}
.card-foot--sets {
  align-items: baseline;
}
.card-foot--pl {
  align-items: center;
}
.card-foot :deep(.plink) {
  color: var(--ink-3);
}
.cf-pct {
  font: 600 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
}
.cf-lbl {
  font: 400 var(--fs-xs)/1 var(--font-ui);
  color: var(--ink-3);
}
.cf-count {
  font: 500 var(--fs-nano)/1 var(--font-mono);
  color: var(--ink-2);
}

/* Load more (comportement existant conservé) */
.load-more {
  display: block;
  margin: var(--space-2) auto 0;
  padding: var(--space-15) var(--space-4);
  border: none;
  background: none;
  color: var(--accent);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
}
.load-more:hover:not(:disabled) {
  text-decoration: underline;
}
.load-more:disabled {
  opacity: 0.6;
  cursor: default;
}
/* Variante lien (renvoi Explorer) : ancre centrée sans soulignement au repos —
   le hover du .load-more le rétablit. */
.load-more--link {
  width: fit-content;
  text-decoration: none;
}

/* ══ 6. Tracks ══ */
.tracks-section {
  margin-top: var(--space-8);
}
.tracks-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.sec-title {
  margin: 0;
  font: 600 var(--fs-md)/1.2 var(--font-ui);
  color: var(--ink);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.sec-count {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}
.tracks-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.tracks-tools :deep(.search) {
  min-width: 210px;
  width: 210px;
}
.tracks-tools :deep(.search > svg) {
  width: 14px;
  height: 14px;
}
/* Tri segmenté — actif = accent plein (G10) */
.sortseg {
  display: inline-flex;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  overflow: hidden;
}
.seg {
  height: 38px;
  padding: 0 var(--space-25);
  border: 0;
  background: var(--surface);
  color: var(--ink-3);
  font: 500 var(--fs-xs)/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition:
    background 0.12s,
    color 0.12s;
}
.seg + .seg {
  border-left: 1px solid var(--line);
}
.seg.active {
  background: var(--accent);
  color: var(--on-accent);
}
.seg:hover:not(.active) {
  background: var(--surface-2);
}
/* Toggle En bib — sémantique bibliothèque : duo positif, point plein quand actif */
.lib-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  height: 38px;
  padding: 0 var(--space-25);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-xs)/1 var(--font-ui);
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s,
    border-color 0.12s;
}
.lt-dot {
  box-sizing: border-box;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  border: 1.5px dashed var(--ink-3);
  flex: none;
}
.lib-toggle.active {
  background: var(--pos-soft);
  color: var(--pos-ink);
  border-color: transparent;
}
.lib-toggle.active .lt-dot {
  background: var(--pos);
  border: 0;
}

/* Rangées TrackCard — grille du BRIEF (cover · titre · BPM · Key · durée · avis) */
.track-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.track-list :deep(.track-card) {
  grid-template-columns: 36px minmax(0, 1fr) 44px 34px 46px 64px;
}
/* Avis en slot end : hover-reveal, actif épinglé, fond soft (G9, pattern Explorer) */
.track-list :deep(.tk-end .ld) {
  gap: var(--space-15);
}
.track-list :deep(.tk-end .ld-btn) {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  opacity: 0;
}
.track-list :deep(.track-card:hover .tk-end .ld-btn) {
  opacity: 1;
}
.track-list :deep(.tk-end .ld-btn:hover) {
  background: var(--surface-3);
}
.track-list :deep(.tk-end .ld[data-state='liked'] .ld-btn.like),
.track-list :deep(.tk-end .ld[data-state='disliked'] .ld-btn.dislike) {
  opacity: 1;
}
.track-list :deep(.tk-end .ld[data-state='liked'] .ld-btn.like) {
  background: var(--pos-soft);
}
.track-list :deep(.tk-end .ld[data-state='disliked'] .ld-btn.dislike) {
  background: var(--neg-soft);
}
/* Teintes de rangée : likée / dislikée — la lecture (accent-wash) garde la main */
.track-list :deep(.track-card.liked) {
  background: var(--pos-wash);
}
.track-list :deep(.track-card.liked:hover) {
  background: var(--pos-wash-2);
}
.track-list :deep(.track-card.disliked > *:not(.tk-end)) {
  opacity: 0.5;
}
.track-list :deep(.track-card.playing),
.track-list :deep(.track-card.playing:hover) {
  background: var(--accent-wash);
}

/* Empty state recherche — en-tête et outils restent affichés */
.tracks-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-8) var(--space-4);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}
.te-msg {
  font: 400 var(--fs-base)/1.4 var(--font-ui);
  color: var(--ink-2);
}

/* ══ 7. Genres proches ══ */
.neighbor-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(196px, 1fr));
  gap: var(--space-2);
  padding: var(--space-4);
}
.neighbor-chip {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-15);
  min-height: var(--touch-min);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface);
  text-decoration: none;
  color: inherit;
  transition:
    background 0.12s,
    border-color 0.12s;
}
.neighbor-chip:hover {
  background: var(--surface-2);
  border-color: var(--line-2);
}
.neighbor-meta {
  font: 400 var(--fs-nano)/1 var(--font-mono);
  color: var(--ink-3);
}

/* ══ 8. Admin (aucun re-design) ══ */
.admin-row {
  display: flex;
  gap: var(--space-2);
}
.admin-input {
  flex: 1;
  padding: var(--space-15) var(--space-3);
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink);
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
}
.admin-input:focus {
  outline: none;
  border-color: var(--accent);
}
.btn-ghost-sm {
  padding: var(--space-15) var(--space-3);
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-ghost-sm:hover {
  border-color: var(--accent);
  color: var(--ink);
}
.btn-ghost-sm:disabled {
  opacity: 0.4;
  cursor: default;
}
.merge-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.merge-item {
  padding: var(--space-15) var(--space-25);
  border-radius: var(--r-xs);
  font: 400 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink);
  cursor: pointer;
}
.merge-item:hover {
  background: var(--surface);
}
.merge-item.selected {
  background: var(--accent-wash);
}
.admin-msg {
  font: 400 var(--fs-sm)/1.3 var(--font-mono);
  padding: var(--space-15) var(--space-25);
  border-radius: var(--r-xs);
}
.admin-msg.ok {
  color: var(--pos-ink);
  background: var(--pos-soft);
}
.admin-msg.err {
  color: var(--neg-ink);
  background: var(--neg-soft);
}
.muted {
  color: var(--ink-3);
}
.mono {
  font-family: var(--font-mono);
}

/* ══ Responsive — container queries uniquement, seuils 720 / 640 ══ */
@container (max-width: 720px) {
  .cards-grid {
    grid-template-columns: repeat(3, 1fr);
  }
  .tracks-tools {
    margin-left: 0;
    width: 100%;
  }
  .tracks-tools :deep(.search) {
    flex: 1;
    width: auto;
    min-width: 0;
  }
}
@container (max-width: 640px) {
  /* Padding horizontal seul — jamais le shorthand */
  .detail-view {
    padding-inline: var(--page-px-mobile);
  }
  .hero {
    height: 288px;
  }
  .hero-mosaic {
    grid-template-columns: repeat(2, 1fr);
    grid-template-rows: repeat(3, 1fr);
  }
  .hero-overlay {
    padding: var(--space-4);
  }
  /* Avatars sous le titre */
  .hero-titlerow {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
  }
  .hero-stats {
    gap: var(--space-5);
  }
  /* Stats puis actions sur deux lignes, cibles ≥ 44px */
  .sline-actions {
    margin-left: 0;
    width: 100%;
  }
  .sline-actions .btn--accent {
    height: var(--touch-min);
  }
  .sline-actions :deep(.ld-btn) {
    width: var(--touch-min);
    height: var(--touch-min);
  }
  .shelf-artists :deep(.shelf),
  .shelf-artists :deep(.shelf-grid) {
    grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
  }
  .cards-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .seg,
  .lib-toggle {
    height: var(--touch-min);
  }
  /* Durée masquée par TrackCard lui-même ; play + avis toujours visibles */
  .track-list :deep(.track-card) {
    grid-template-columns: 36px minmax(0, 1fr) 44px 34px 64px;
  }
  .track-list :deep(.tk-end .ld-btn) {
    opacity: 1;
  }
  .neighbor-grid {
    grid-template-columns: 1fr;
  }
}
</style>

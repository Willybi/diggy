<template>
  <div class="detail-view">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!track" class="state">Track introuvable.</div>
    <template v-else>
      <PageHero
        variant="square"
        :image-src="coverSrc"
        :title="track.title"
        :fallback-letter="(track.title || '?')[0]"
      >
        <!-- T1: artist-chip(s) with round avatar -->
        <template #subtitle>
          <template v-for="(a, i) in track.artists" :key="a.id">
            <span v-if="i > 0" class="chip-sep">, </span>
            <RouterLink :to="`/artist/${a.id}`" class="artist-chip">
              <img
                v-if="a.has_artwork"
                class="chip-av"
                :src="`/storage/artist-artworks/${a.id}.jpg`"
                :alt="a.name"
              />
              <span v-else class="chip-av"></span>
              {{ a.name }}
            </RouterLink>
          </template>
        </template>

        <template #badges>
          <InLibBadge :in-lib="track.in_lib" />
          <template v-if="track.genres?.length">
            <RouterLink
              v-for="g in track.genres"
              :key="g.name"
              :to="`/style/${encodeURIComponent(g.name)}`"
              style="text-decoration: none"
            >
              <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
            </RouterLink>
          </template>
          <StyleTag v-else-if="track.style" :name="track.style" />
          <!-- T2: Rekordbox tags -->
          <span v-for="tag in track.tags" :key="tag" class="rb-tag">{{ tag }}</span>
        </template>

        <!-- T3: LikeDislike + HeroPlayer + Add to collection -->
        <template #actions>
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
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="5" width="18" height="16" rx="2" />
                <path d="M12 10v6M9 13h6" />
              </svg>
              <span>Collection</span>
            </button>
            <div v-if="showCollDropdown" class="coll-dropdown">
              <div v-if="collLoading" class="coll-dd-state">Chargement…</div>
              <div v-else-if="!userCollections.length" class="coll-dd-state">Aucune collection</div>
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
            </div>
          </div>
        </template>
      </PageHero>

      <StatStrip :stats="stats" />

      <div v-if="track.label || track.beatport_id" class="track-meta">
        <span v-if="track.label" class="meta-label">{{ track.label }}</span>
        <a
          v-if="track.beatport_id"
          :href="`https://www.beatport.com/track/-/${track.beatport_id}`"
          target="_blank"
          rel="noopener"
          class="meta-link beatport-link"
          >Beatport ↗</a
        >
      </div>

      <!-- STRUCTURAL: 2-column layout for Détecté + Apparaît -->
      <div
        v-if="track.radar_appearances.length || track.set_appearances.length"
        class="rel-cols"
      >
        <!-- T6: Détecté dans — source badge + date -->
        <RelBlock
          v-if="track.radar_appearances.length"
          title="Détecté dans"
          :count="track.radar_appearances.length"
        >
          <RouterLink
            v-for="r in track.radar_appearances"
            :key="r.playlist_id"
            :to="`/playlists/${r.playlist_id}`"
            class="appear appear--link"
          >
            <span class="ap-tx">
              <span class="appear-title">{{ r.playlist_title || 'Playlist' }}</span>
              <span class="appear-sub">
                <SourceBadge :source="r.playlist_source" />
                <span>détecté le {{ fmtDate(r.detected_at) }}</span>
              </span>
            </span>
            <span class="appear-arrow">›</span>
          </RouterLink>
        </RelBlock>

        <!-- T7: Apparaît dans — timecode cliquable -->
        <RelBlock
          v-if="track.set_appearances.length"
          title="Apparaît dans"
          :count="track.set_appearances.length"
        >
          <RouterLink
            v-for="s in track.set_appearances"
            :key="s.set_id"
            :to="`/set/${s.set_id}`"
            class="appear appear--link"
          >
            <span class="ap-tx">
              <span class="appear-title">{{ s.set_title }}</span>
              <span class="appear-sub">
                <span v-if="s.timecode_ms != null" class="timecode">▶ {{ fmtCue(s.timecode_ms) }}</span>
                <template v-if="s.played_date">
                  <span class="sep">·</span>{{ fmtDate(s.played_date) }}
                </template>
              </span>
            </span>
            <span class="appear-arrow">›</span>
          </RouterLink>
        </RelBlock>
      </div>

      <!-- T8: Du même artiste — compact 2-col grid -->
      <RelBlock
        v-if="track.same_artist_tracks.length"
        :title="`Du même artiste`"
        :count="track.same_artist_tracks.length"
      >
        <div class="mini-grid">
          <div
            v-for="t in track.same_artist_tracks"
            :key="t.id"
            class="mini-row"
            :class="{ playing: player.isCurrent(t.id) }"
            @click="$router.push(`/catalog/${t.id}`)"
          >
            <img
              v-if="t.has_artwork"
              class="mr-cover"
              :src="`/storage/catalog-artworks/${t.id}.jpg`"
              alt=""
            />
            <span v-else class="mr-cover mr-cover--empty"></span>
            <span class="mini-tx">
              <span class="mr-title">{{ t.title }}</span>
            </span>
            <span class="m-bpm mono">{{ t.bpm ? fmtBpm(t.bpm) : '' }}</span>
            <span class="m-key mono">{{ t.key || '' }}</span>
            <span class="m-play" @click.stop>
              <button
                v-if="t.has_preview"
                class="play-btn"
                :class="{ playing: player.isCurrent(t.id) && player.playing }"
                @click="playTrack(t)"
              >
                <svg v-if="player.isCurrent(t.id) && player.playing" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="5" width="4" height="14" />
                  <rect x="14" y="5" width="4" height="14" />
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="currentColor">
                  <path d="M8 5v14l11-7z" />
                </svg>
              </button>
            </span>
            <span class="m-rating">
              <span v-if="t.rating" class="rating">
                <span
                  v-for="n in 5"
                  :key="n"
                  class="star"
                  :class="{ 'is-on': n <= t.rating }"
                  >★</span
                >
              </span>
            </span>
            <span class="m-lib"><LibDot :in-lib="!!t.in_lib" /></span>
          </div>
        </div>
      </RelBlock>

      <!-- T9: Tracks similaires -->
      <RelBlock
        v-if="similarLoading || similarTracks.length"
        title="Tracks similaires"
        :count="similarTracks.length || undefined"
      >
        <div v-if="similarLoading" class="state state--inline">Chargement…</div>
        <div v-else class="mini-grid">
          <div
            v-for="t in similarTracks"
            :key="t.id"
            class="mini-row mini-row--sim"
            :class="{ playing: player.isCurrent(t.id) }"
            @click="$router.push(`/catalog/${t.id}`)"
          >
            <img
              v-if="t.has_artwork"
              class="mr-cover"
              :src="`/storage/catalog-artworks/${t.id}.jpg`"
              alt=""
            />
            <span v-else class="mr-cover mr-cover--empty"></span>
            <span class="mini-tx">
              <span class="mr-title">{{ t.title }}</span>
              <span class="mr-artist">{{ t.artist }}</span>
            </span>
            <span class="m-bpm mono">{{ t.bpm ? fmtBpm(t.bpm) : '' }}</span>
            <span class="m-key mono">{{ t.key || '' }}</span>
            <span class="m-play" @click.stop>
              <button
                v-if="t.has_preview"
                class="play-btn"
                :class="{ playing: player.isCurrent(t.id) && player.playing }"
                @click="playTrack(t)"
              >
                <svg v-if="player.isCurrent(t.id) && player.playing" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="5" width="4" height="14" />
                  <rect x="14" y="5" width="4" height="14" />
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="currentColor">
                  <path d="M8 5v14l11-7z" />
                </svg>
              </button>
            </span>
            <span class="m-sim-score">{{ Math.round(t.similarity.score * 100) }}%</span>
            <span class="m-lib"><LibDot :in-lib="!!t.in_lib" /></span>
          </div>
        </div>
      </RelBlock>

      <!-- STRUCTURAL: AdminCard moved to bottom -->
      <!-- T5: ISRC added -->
      <AdminCard variant="warn">
        <div class="admin-header">
          <span class="mono muted"
            >beatport_id: {{ track.beatport_id || '—' }} · deezer_id:
            {{ track.deezer_id || '—' }} · isrc: {{ track.isrc || '—' }}</span
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
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../utils/api.js'
import PageHero from '../components/PageHero.vue'
import StatStrip from '../components/StatStrip.vue'
import RelBlock from '../components/RelBlock.vue'
import InLibBadge from '../components/InLibBadge.vue'
import StyleTag from '../components/StyleTag.vue'
import HeroPlayer from '../components/HeroPlayer.vue'
import AdminCard from '../components/AdminCard.vue'
import LikeDislike from '../components/LikeDislike.vue'
import SourceBadge from '../components/SourceBadge.vue'
import LibDot from '../components/LibDot.vue'
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtMs, fmtBpm, fmtDate, fmtCue } from '../utils/format'

const route = useRoute()
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
const similarTracks = ref([])
const similarLoading = ref(false)

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

const coverSrc = computed(() => {
  if (!track.value) return null
  const t = track.value
  if (t.lib_track_id && t.has_artwork) return `/storage/artworks/${t.lib_track_id}.jpg`
  if (t.has_artwork) return `/storage/catalog-artworks/${t.id}.jpg`
  return null
})

const stats = computed(() => {
  if (!track.value) return []
  const t = track.value
  return [
    { label: 'BPM', value: fmtBpm(t.bpm) },
    { label: 'Key', value: t.key || '—' },
    { label: 'Durée', value: fmtMs(t.duration_ms) },
    { label: 'Année', value: t.release_date ? new Date(t.release_date).getFullYear() : '—' },
    { label: 'Rating', value: t.rating ? '★'.repeat(t.rating) : '—' },
    { label: 'Radar', value: t.nb_radar_playlists || '—' },
    { label: 'Radar sets', value: t.nb_radar_sets || '—' },
  ]
})

// T3: persist opinion (canonical avis endpoint, same as CatalogView)
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

watch(() => route.params.id, (id) => { if (id) loadTrack(id) })
onMounted(() => loadTrack(route.params.id))
</script>

<style scoped>
.detail-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: var(--detail-max-w);
  margin-inline: auto;
  container-type: inline-size;
}
.state {
  color: var(--ink-3);
  font-size: var(--fs-base);
  font-style: italic;
  padding-top: var(--space-10);
}

/* T1: Artist chips */
.artist-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  text-decoration: none;
  color: var(--ink-2);
  font: 500 var(--fs-base) var(--font-ui);
}
.chip-av {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  flex: none;
  border: 1px solid var(--line);
  background: var(--surface-3);
  object-fit: cover;
}
.artist-chip:hover {
  color: var(--accent-ink);
}
.artist-chip:hover .chip-av {
  border-color: var(--accent);
}
.chip-sep {
  color: var(--ink-3);
}

/* T2: Rekordbox tags */
.rb-tag {
  display: inline-flex;
  align-items: center;
  font: 500 var(--fs-label)/1 var(--font-mono);
  letter-spacing: 0.03em;
  color: var(--ink-2);
  background: var(--surface-2);
  border: 1px solid var(--line-2);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--r-pill);
  white-space: nowrap;
}

/* Collection add button */
.coll-add-wrap {
  position: relative;
}
.btn-coll {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  height: 34px;
  padding: 0 var(--space-3);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.12s, border-color 0.12s;
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
  border: 1px solid var(--line);
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

/* Track meta (label + external links) */
.track-meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin: var(--space-3) 0 var(--space-1);
  font: 400 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink-3);
}
.meta-label {
  color: var(--ink-2);
}
.meta-link {
  color: var(--accent);
  text-decoration: none;
  font-weight: 500;
}
.meta-link:hover {
  text-decoration: underline;
}

/* STRUCTURAL: 2-column layout */
.rel-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-6) var(--space-8);
  align-items: start;
}
.rel-cols > :deep(.rel-block) {
  margin-top: 0;
  min-width: 0;
  overflow: hidden;
}
@container (max-width: 720px) {
  .rel-cols {
    grid-template-columns: 1fr;
  }
}

/* T6/T7: Appear rows (custom) */
.appear {
  display: flex;
  align-items: center;
  gap: var(--space-25);
  padding: var(--space-25) var(--space-3);
  border-bottom: 1px solid var(--line);
  text-decoration: none;
  color: inherit;
  transition: background 0.1s;
  min-width: 0;
}
.appear:last-child {
  border-bottom: none;
}
.appear--link:hover {
  background: var(--surface-2);
}
.ap-tx {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.appear-title {
  display: block;
  font: 500 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.appear-sub {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  font: 400 var(--fs-sm)/1.3 var(--font-mono);
  color: var(--ink-3);
}
.sep {
  opacity: 0.5;
}
.appear-arrow {
  flex: none;
  font-size: var(--fs-md);
  color: var(--ink-3);
}
.timecode {
  color: var(--accent-ink);
  font-family: var(--font-mono);
}

/* T8: Same artist — compact 2-col grid with fixed columns */
.mini-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-05);
}
/* grid items must shrink below min-content for equal 1fr columns */
.mini-grid > .mini-row {
  min-width: 0;
  overflow: hidden;
}
@container (max-width: 720px) {
  .mini-grid {
    grid-template-columns: 1fr;
  }
}
.mini-row {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) 34px 30px 30px 72px 16px;
  align-items: center;
  gap: var(--space-25);
  padding: var(--space-2) var(--space-25);
  text-decoration: none;
  color: inherit;
  border-radius: var(--r-sm);
  transition: background 0.1s;
  min-width: 0;
  cursor: pointer;
}
.mini-row:hover {
  background: var(--surface-2);
}
.mr-cover {
  width: 36px;
  height: 36px;
  border-radius: var(--r-xs);
  object-fit: cover;
  border: 1px solid var(--line);
}
.mr-cover--empty {
  background: var(--surface-3);
}
.mini-tx {
  min-width: 0;
  overflow: hidden;
}
.mr-title {
  display: block;
  max-width: 100%;
  font: 500 var(--fs-sm)/1.2 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mini-row:hover .mr-title {
  color: var(--accent-ink);
}
.m-bpm {
  text-align: right;
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
}
.m-key {
  text-align: center;
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--accent-ink);
}
.m-rating {
  text-align: center;
}
.m-lib {
  display: flex;
  justify-content: center;
}
.mono {
  font-family: var(--font-mono);
  color: var(--ink-2);
}
.rating {
  white-space: nowrap;
}
.star {
  color: var(--ink-3);
  font-size: var(--fs-xs);
}
.star.is-on {
  color: var(--accent-ink);
}

/* Admin card */
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-25);
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

/* T9: Similar tracks */
.mini-row--sim {
  grid-template-columns: 38px minmax(0, 1fr) 34px 30px 30px 36px 16px;
}
.mr-artist {
  display: block;
  font: 400 var(--fs-xs)/1.2 var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.m-sim-score {
  text-align: right;
  font: 600 var(--fs-xs)/1 var(--font-mono);
  color: var(--accent-ink);
  opacity: 0.75;
}
.state--inline {
  padding: 0 var(--space-4) var(--space-3);
  font-size: var(--fs-sm);
}

/* Play button */
.m-play {
  display: flex;
  justify-content: center;
  min-height: 30px;
  align-items: center;
}
.play-btn {
  display: inline-grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  cursor: pointer;
  color: var(--ink-3);
  border: 1px solid var(--line-2);
  background: var(--surface);
  opacity: 0;
  transition: opacity 0.12s;
}
.play-btn svg {
  width: 14px;
  height: 14px;
}
.mini-row:hover .play-btn {
  opacity: 1;
}
.play-btn:hover {
  color: var(--ink);
  background: var(--surface-2);
}
.play-btn.playing {
  opacity: 1;
  color: var(--accent-ink);
  background: var(--accent-soft);
  border-color: transparent;
}
.mini-row.playing {
  background: var(--accent-soft);
}

/* ============ RESPONSIVE ============ */
@container (max-width: 640px) {
  .detail-view {
    padding: var(--page-px-mobile);
  }
  .play-btn {
    opacity: 1;
  }
}
</style>

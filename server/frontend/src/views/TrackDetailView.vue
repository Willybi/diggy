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

        <!-- T3: LikeDislike + HeroPlayer -->
        <template #actions>
          <HeroPlayer
            v-if="track.has_preview"
            :catalog-id="track.id"
            :title="track.title"
            :artist="track.artist"
            :bpm="track.bpm"
            :track-key="track.key"
          />
          <LikeDislike v-model="opinion" />
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
          <div
            v-for="r in track.radar_appearances"
            :key="r.playlist_id"
            class="appear"
          >
            <span class="appear-title">{{ r.playlist_title || 'Playlist' }}</span>
            <span class="appear-sub">
              <SourceBadge :source="r.playlist_source" />
              détecté le {{ fmtDate(r.detected_at) }}
            </span>
          </div>
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
            <span class="appear-title">{{ s.set_title }}</span>
            <span class="appear-sub">
              <span v-if="s.timecode_ms != null" class="timecode">▶ {{ fmtCue(s.timecode_ms) }}</span>
              <template v-if="s.played_date">{{ fmtDate(s.played_date) }}</template>
            </span>
            <span class="appear-arrow">›</span>
          </RouterLink>
        </RelBlock>
      </div>

      <!-- T8: Du même artiste — mini-table -->
      <RelBlock
        v-if="track.same_artist_tracks.length"
        :title="`Du même artiste`"
        :count="track.same_artist_tracks.length"
      >
        <div class="mini-table-wrap">
          <table class="mini-table">
            <thead>
              <tr>
                <th class="mt-cover"></th>
                <th class="mt-track">Track</th>
                <th class="mt-num">BPM</th>
                <th class="mt-num">Key</th>
                <th class="mt-num">Rating</th>
                <th class="mt-num">Lib</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in track.same_artist_tracks" :key="t.id">
                <td class="mt-cover">
                  <img
                    v-if="t.has_artwork"
                    class="mt-thumb"
                    :src="`/storage/catalog-artworks/${t.id}.jpg`"
                    alt=""
                  />
                  <span v-else class="mt-thumb mt-thumb--empty"></span>
                </td>
                <td class="mt-track">
                  <RouterLink :to="`/catalog/${t.id}`" class="mt-link">
                    <span class="mt-title">{{ t.title }}</span>
                    <span class="mt-artist"
                      ><ArtistLinks :artists="t.artists" :fallback="t.artist"
                    /></span>
                  </RouterLink>
                </td>
                <td class="mt-num mono">{{ t.bpm ? fmtBpm(t.bpm) : '—' }}</td>
                <td class="mt-num mono key-cell">{{ t.key || '—' }}</td>
                <td class="mt-num">
                  <span v-if="t.rating" class="rating">
                    <span
                      v-for="n in 5"
                      :key="n"
                      class="star"
                      :class="{ 'is-on': n <= t.rating }"
                      >★</span
                    >
                  </span>
                  <span v-else class="dash">—</span>
                </td>
                <td class="mt-num">
                  <LibDot :in-lib="!!t.in_lib" />
                </td>
              </tr>
            </tbody>
          </table>
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

        <div class="admin-row" style="margin-top: 8px">
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
import ArtistLinks from '../components/ArtistLinks.vue'
import LibDot from '../components/LibDot.vue'
import { fmtMs, fmtBpm, fmtDate, fmtCue } from '../utils/format'

const route = useRoute()
const track = ref(null)
const loading = ref(true)
const enriching = ref(false)
const enrichResult = ref(null)
const fetchingDzGenre = ref(false)
const dzGenreResult = ref(null)
const opinion = ref(null)

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

// T3: persist opinion
watch(opinion, async (val) => {
  if (!track.value) return
  try {
    await api.post(`/api/opinions/${track.value.id}`, { opinion: val })
  } catch {
    // silent
  }
})

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

onMounted(async () => {
  try {
    const { data } = await api.get(`/api/catalog/${route.params.id}`)
    track.value = data
    opinion.value = data.avis ?? null
  } catch {
    track.value = null
  } finally {
    loading.value = false
  }
})
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
  font-size: 14px;
  font-style: italic;
  padding-top: 40px;
}

/* T1: Artist chips */
.artist-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: var(--ink-2);
  font: 500 14.5px var(--font-ui);
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
  font: 500 10.5px/1 var(--font-mono);
  letter-spacing: 0.03em;
  color: var(--ink-2);
  background: var(--surface-2);
  border: 1px solid var(--line-2);
  padding: 5px 9px;
  border-radius: 999px;
  white-space: nowrap;
}

/* Track meta (label + external links) */
.track-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0 4px;
  font: 400 13px/1 var(--font-ui);
  color: var(--ink-muted);
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
  gap: 26px 34px;
  align-items: start;
}
.rel-cols > :deep(.rel) {
  margin-top: 0;
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
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  text-decoration: none;
  color: inherit;
  transition: background 0.1s;
}
.appear:last-child {
  border-bottom: none;
}
.appear--link:hover {
  background: var(--surface-2);
}
.appear-title {
  display: block;
  font: 500 13.5px/1.3 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}
.appear-sub {
  display: flex;
  align-items: center;
  gap: 8px;
  font: 400 12px/1.3 var(--font-mono);
  color: var(--ink-3);
  margin-top: 2px;
  flex: none;
}
.appear-arrow {
  flex: none;
  font-size: 18px;
  color: var(--ink-3);
  margin-left: 8px;
}
.timecode {
  color: var(--accent-ink);
  font-family: var(--font-mono);
}

/* T8: Mini track table */
.mini-table-wrap {
  overflow-x: auto;
}
.mini-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.mini-table thead th {
  text-align: left;
  padding: 8px 12px;
  font: 500 10.5px/1 var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line);
}
.mini-table tbody td {
  padding: 8px 12px;
  vertical-align: middle;
  border-bottom: 1px solid var(--line);
}
.mini-table tbody tr:last-child td {
  border-bottom: none;
}
.mini-table tbody tr:hover td {
  background: var(--surface-2);
}
.mt-cover {
  width: 44px;
}
.mt-thumb {
  display: block;
  width: 32px;
  height: 32px;
  border-radius: var(--r-sm);
  object-fit: cover;
  border: 1px solid var(--line);
}
.mt-thumb--empty {
  background: var(--surface-3);
}
.mt-track {
  min-width: 160px;
}
.mt-num {
  width: 56px;
  text-align: center;
}
.mono {
  font-family: var(--font-mono);
  color: var(--ink-2);
}
.key-cell {
  color: var(--accent-ink);
}
.mt-link {
  text-decoration: none;
  color: inherit;
}
.mt-link:hover .mt-title {
  color: var(--accent-ink);
}
.mt-title {
  display: block;
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mt-artist {
  display: block;
  font-size: 12px;
  color: var(--ink-2);
}
.rating {
  white-space: nowrap;
}
.star {
  color: var(--ink-3);
  font-size: 12px;
}
.star.is-on {
  color: var(--accent-ink);
}
.dash {
  color: var(--ink-3);
}

/* Admin card */
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.muted {
  color: var(--ink-3);
}
.admin-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.btn-sync {
  padding: 7px 16px;
  border-radius: var(--r-sm);
  border: 1px solid var(--accent);
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
  transition: opacity 0.12s;
}
.btn-sync:disabled {
  opacity: 0.5;
  cursor: default;
}
.enrich-result {
  font: 400 13px/1.4 var(--font-ui);
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
</style>

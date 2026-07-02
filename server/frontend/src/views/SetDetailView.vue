<template>
  <div class="detail-view">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!djSet" class="state">Set introuvable.</div>
    <template v-else>
      <PageHero
        variant="wide"
        :image-src="djSet.has_artwork ? `/storage/set-artworks/${djSet.id}.jpg` : null"
        :title="djSet.title"
        :subtitle="heroSub"
        :fallback-letter="(djSet.title || '?')[0]"
      >
        <template #badges>
          <template v-if="djSet.genres?.length">
            <RouterLink
              v-for="g in djSet.genres"
              :key="g.name"
              :to="`/style/${encodeURIComponent(g.name)}`"
              style="text-decoration: none"
            >
              <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
            </RouterLink>
          </template>
        </template>
        <template #actions>
          <a
            v-if="sourceLabel && djSet.source_url"
            class="btn-ghost"
            :href="djSet.source_url"
            target="_blank"
          >
            Voir sur {{ sourceLabel }}
          </a>
        </template>
      </PageHero>

      <StatStrip :stats="stats">
        <div v-if="djSet.total_tracks" class="stat-cell">
          <span class="stat-value ring-val">
            <RingPct :value="djSet.identified_tracks" :total="djSet.total_tracks" />
          </span>
          <span class="stat-label">Identifiées</span>
        </div>
      </StatStrip>

      <RelBlock v-if="djSet.description" title="Description">
        <p class="rel-prose">{{ djSet.description }}</p>
      </RelBlock>

      <!-- Artists -->
      <RelBlock v-if="djSet.artists.length > 1" title="Artistes">
        <RouterLink
          v-for="a in djSet.artists"
          :key="a.artist_id"
          class="appear"
          :to="`/artist/${a.artist_id}`"
        >
          <img
            v-if="a.has_artwork"
            class="ap-thumb round"
            :src="`/storage/artist-artworks/${a.artist_id}.jpg`"
          />
          <span v-else class="ap-thumb round ap-thumb--empty"></span>
          <span class="ap-tx">
            <span class="ap-title">{{ a.artist_name }}</span>
            <span class="ap-sub">{{ a.role === 'b2b' ? 'B2B' : 'Live' }}</span>
          </span>
        </RouterLink>
      </RelBlock>

      <!-- Tracklist -->
      <RelBlock title="Tracklist" :count="djSet.total_tracks">
        <div class="tracklist-wrap">
          <table class="tracklist">
            <thead>
              <tr>
                <th class="tl-pos">#</th>
                <th class="tl-play"></th>
                <th class="tl-time">Time</th>
                <th class="tl-cover"></th>
                <th class="tl-track">Track</th>
                <th class="tl-lib">Lib</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="t in djSet.tracklist"
                :key="t.id"
                :class="[trackRowClass(t), { playing: player.isCurrent(t.catalog_id) }]"
              >
                <td class="tl-pos mono">{{ t.position }}</td>
                <td class="tl-play">
                  <button
                    v-if="t.has_preview && !t.is_id"
                    class="play-btn"
                    :class="{ playing: player.isCurrent(t.catalog_id) && player.playing }"
                    @click="playTrack(t)"
                  >
                    <svg
                      v-if="player.isCurrent(t.catalog_id) && player.playing"
                      viewBox="0 0 24 24"
                      width="14"
                      height="14"
                    >
                      <rect x="6" y="5" width="4" height="14" fill="currentColor" />
                      <rect x="14" y="5" width="4" height="14" fill="currentColor" />
                    </svg>
                    <svg v-else viewBox="0 0 24 24" width="14" height="14">
                      <polygon points="7,4 21,12 7,20" fill="currentColor" />
                    </svg>
                  </button>
                </td>
                <td class="tl-time mono">
                  <a
                    v-if="makeTimestampUrl(djSet.source_url, t.timecode_ms)"
                    :href="makeTimestampUrl(djSet.source_url, t.timecode_ms)"
                    target="_blank"
                    class="tl-time-link"
                    >{{ fmtCue(t.timecode_ms) }}</a
                  >
                  <span v-else>{{ fmtCue(t.timecode_ms) }}</span>
                </td>
                <td class="tl-cover">
                  <img
                    v-if="t.has_artwork && t.catalog_id"
                    :src="`/storage/catalog-artworks/${t.catalog_id}.jpg`"
                    class="tl-thumb"
                    loading="lazy"
                  />
                  <span v-else class="tl-thumb tl-thumb--empty"></span>
                </td>
                <td class="tl-track">
                  <RouterLink
                    v-if="t.catalog_id && !t.is_id"
                    :to="`/catalog/${t.catalog_id}`"
                    class="tl-link"
                  >
                    <span class="tl-title">{{ t.catalog_title || t.raw_title }}</span>
                    <span class="tl-artist">
                      <ArtistLinks
                        v-if="t.catalog_artists?.length"
                        :artists="t.catalog_artists"
                        :fallback="t.catalog_artist || t.raw_artist"
                      />
                      <template v-else>{{ t.catalog_artist || t.raw_artist }}</template>
                    </span>
                  </RouterLink>
                  <div v-else>
                    <span class="tl-title">{{ t.is_id ? 'ID' : t.raw_title || '?' }}</span>
                    <span class="tl-artist">{{
                      t.is_id ? 'non identifié' : t.raw_artist || ''
                    }}</span>
                  </div>
                </td>
                <td class="tl-lib">
                  <span v-if="t.is_id" class="id-label">ID</span>
                  <LibDot v-else :in-lib="t.in_lib" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </RelBlock>

      <!-- Admin: manage set artists -->
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
import { useRoute } from 'vue-router'
import api from '../utils/api.js'
import PageHero from '../components/PageHero.vue'
import StatStrip from '../components/StatStrip.vue'
import RelBlock from '../components/RelBlock.vue'
import RingPct from '../components/RingPct.vue'
import StyleTag from '../components/StyleTag.vue'
import LibDot from '../components/LibDot.vue'
import ArtistLinks from '../components/ArtistLinks.vue'
import AdminCard from '../components/AdminCard.vue'
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtMs, fmtDate, fmtCue } from '../utils/format'

const player = useAudioPlayer()

// Admin: set artists
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
  } catch {}
}

async function removeSetArtist(artistId) {
  if (!djSet.value) return
  try {
    await api.delete(`/api/admin/sets/${djSet.value.id}/artists/${artistId}`)
    djSet.value.artists = djSet.value.artists.filter((a) => a.artist_id !== artistId)
  } catch {}
}

function playTrack(t) {
  if (player.isCurrent(t.catalog_id) && player.playing) {
    player.toggle()
    return
  }
  player.play({
    id: t.catalog_id,
    catalog_id: t.catalog_id,
    title: t.catalog_title || t.raw_title,
    artist: t.catalog_artist || t.raw_artist,
  })
}

const SOURCE_META = {
  youtube: { label: 'YouTube' },
  '1001tracklists': { label: '1001Tracklists' },
  trackid: { label: 'TrackID.net' },
  soundcloud: { label: 'SoundCloud' },
}

function detectSourceLabel(url) {
  if (!url) return null
  if (url.includes('youtube.com') || url.includes('youtu.be')) return 'YouTube'
  if (url.includes('soundcloud.com')) return 'SoundCloud'
  if (url.includes('1001tracklists.com')) return '1001Tracklists'
  if (url.includes('trackid.net')) return 'TrackID.net'
  return null
}

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

const route = useRoute()
const djSet = ref(null)
const loading = ref(true)

const heroSub = computed(() => {
  if (!djSet.value) return null
  const parts = []
  if (djSet.value.artists.length) {
    const names = djSet.value.artists.map((a) => a.artist_name)
    parts.push(names.join(' B2B '))
  }
  if (djSet.value.event) parts.push(djSet.value.event)
  if (djSet.value.venue) parts.push(djSet.value.venue)
  return parts.join(' · ') || null
})

const sourceLabel = computed(() => {
  if (!djSet.value) return null
  return detectSourceLabel(djSet.value.source_url) || SOURCE_META[djSet.value.source]?.label || null
})

const stats = computed(() => {
  if (!djSet.value) return []
  const s = djSet.value
  return [
    { label: 'Durée', value: fmtMs(s.duration_ms) },
    { label: 'Date', value: fmtDate(s.played_date) },
    { label: 'Tracks', value: s.total_tracks },
  ]
})

function trackRowClass(t) {
  if (t.is_id) return 'row--id'
  if (!t.catalog_id) return 'row--unknown'
  return ''
}

onMounted(async () => {
  try {
    const { data } = await api.get(`/api/sets/${route.params.id}`)
    djSet.value = data
  } catch {
    djSet.value = null
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
}

/* Identifiées cell inside StatStrip */
.stat-cell {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 16px;
  border-right: 1px solid var(--line);
}
.stat-cell:last-child {
  border-right: none;
}
.stat-value {
  font: 600 15px/1 var(--font-mono);
  color: var(--ink);
}
.stat-label {
  font: 400 10.5px/1 var(--font-mono);
  color: var(--ink-3);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-top: 4px;
}
.ring-val {
  display: inline-flex;
  align-items: center;
}

/* Description */
.rel-prose {
  font: 400 14px/1.6 var(--font-ui);
  color: var(--ink-2);
  max-width: 78ch;
  padding: 0 10px;
}

/* Artist appear rows */
.appear {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  border-radius: var(--r-sm);
  text-decoration: none;
  color: inherit;
  transition: background 0.12s;
}
.appear:hover {
  background: var(--surface-2);
}
.ap-thumb {
  width: 42px;
  height: 42px;
  border-radius: var(--r-xs);
  flex: none;
  object-fit: cover;
  border: 1px solid var(--line);
  background: var(--surface-3);
}
.ap-thumb.round {
  border-radius: 50%;
}
.ap-thumb--empty {
  background: var(--surface-2);
}
.ap-tx {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ap-title {
  font: 500 14px/1 var(--font-ui);
  color: var(--ink);
}
.ap-sub {
  font: 400 12px/1 var(--font-ui);
  color: var(--ink-3);
}

/* Tracklist */
.tracklist-wrap {
  overflow-x: auto;
}
.tracklist {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.tracklist thead th {
  text-align: left;
  padding: 8px 12px;
  font: 500 10.5px/1 var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line);
}
.tracklist tbody td {
  padding: 8px 12px;
  vertical-align: middle;
  border-bottom: 1px solid var(--line);
}
.tracklist tbody tr:last-child td {
  border-bottom: none;
}
.tracklist tbody tr:hover td {
  background: var(--surface-2);
}

.tl-pos {
  width: 36px;
  text-align: center;
}
.tl-play {
  width: 44px;
  text-align: center;
  padding: 4px !important;
}
.tl-time {
  width: 72px;
}
.tl-cover {
  width: 40px;
  padding: 4px 8px !important;
}
.tl-track {
  min-width: 180px;
}
.tl-lib {
  width: 44px;
  text-align: center;
}

.tl-thumb {
  display: block;
  width: 32px;
  height: 32px;
  border-radius: var(--r-xs);
  object-fit: cover;
  border: 1px solid var(--line);
}
.tl-thumb--empty {
  background: var(--surface-2);
}

.tl-time-link {
  color: var(--ink-2);
  text-decoration: none;
  transition: color 0.12s;
}
.tl-time-link:hover {
  color: var(--accent-ink);
  text-decoration: underline;
}

.mono {
  font-family: var(--font-mono);
  color: var(--ink-2);
}

.tl-link {
  text-decoration: none;
  color: inherit;
}
.tl-link:hover .tl-title {
  color: var(--accent-ink);
}

.tl-title {
  display: block;
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tl-artist {
  display: block;
  font-size: 12px;
  color: var(--ink-2);
}

/* Play button */
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
tr:hover .play-btn {
  opacity: 1;
}
.play-btn.playing {
  opacity: 1;
  color: var(--accent-ink);
  background: var(--accent-soft);
  border-color: transparent;
}

/* Row states */
.row--unknown .tl-title {
  color: var(--ink-3);
  font-style: italic;
}
.row--unknown .tl-artist {
  color: var(--ink-3);
}
.row--id .tl-title {
  color: var(--ink-3);
  font-style: italic;
  opacity: 0.6;
}
.row--id .tl-artist {
  color: var(--ink-3);
  opacity: 0.6;
}

/* Playing row */
tr.playing td {
  background: var(--accent-soft);
}

/* ID label */
.id-label {
  font: 600 9px/1 var(--font-mono);
  color: var(--ink-3);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.btn-ghost {
  padding: 8px 16px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 13px/1 var(--font-ui);
  text-decoration: none;
  transition:
    background 0.12s,
    color 0.12s;
}
.btn-ghost:hover {
  background: var(--surface-2);
  color: var(--ink);
}

.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
  padding-top: 40px;
}

/* Admin card */
.set-artists-list {
  margin-bottom: 10px;
}
.set-artist-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 8px;
  border-radius: var(--r-sm);
}
.set-artist-row:hover {
  background: var(--surface-2);
}
.sa-name {
  font: 500 13px/1 var(--font-ui);
  color: var(--ink);
  text-decoration: none;
}
.sa-name:hover {
  color: var(--accent-ink);
}
.sa-role {
  font-size: 11px;
  color: var(--ink-3);
}
.sa-add-row {
  display: flex;
  gap: 8px;
}
.admin-input {
  flex: 1;
  padding: 7px 12px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface-2);
  color: var(--ink);
  font: 400 13px/1 var(--font-ui);
  outline: none;
}
.admin-input:focus {
  border-color: var(--accent);
}
.sa-results {
  max-height: 160px;
  overflow-y: auto;
  margin-top: 6px;
}
.sa-hit {
  padding: 6px 10px;
  cursor: pointer;
  border-radius: var(--r-sm);
  font: 400 13px/1 var(--font-ui);
  color: var(--ink);
}
.sa-hit:hover {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.empty-hint {
  font-size: 12px;
  color: var(--ink-3);
  font-style: italic;
  margin-bottom: 10px;
}
.btn-row-action {
  margin-left: auto;
  padding: 3px 7px;
  border-radius: 4px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  font: 500 10px/1 var(--font-ui);
  cursor: pointer;
}
.btn-row-action:hover {
  color: var(--neg-ink);
  border-color: var(--neg-ink);
}

/* ============ RESPONSIVE ============ */
@container app (max-width: 640px) {
  .detail-view {
    padding: var(--page-px-mobile);
  }
  .tl-time {
    display: none;
  }
  .play-btn {
    opacity: 1;
  }
}
</style>

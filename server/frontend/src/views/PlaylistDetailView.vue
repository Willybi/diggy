<template>
  <div class="detail-view">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!playlist" class="state">Playlist introuvable.</div>
    <template v-else>
      <!-- 1. Hero -->
      <PageHero
        variant="square"
        :image-src="playlist.has_artwork ? `/storage/playlist-artworks/${playlist.id}.jpg` : null"
        :title="playlist.title || playlist.external_id"
        :subtitle="heroSub"
        :fallback-letter="(playlist.title || 'P')[0]"
      >
        <template #badges>
          <SourceBadge :source="playlist.source" />
        </template>
        <template #actions>
          <a v-if="externalUrl" class="btn-ghost" :href="externalUrl" target="_blank">
            Voir sur {{ sourceLabel }} ↗
          </a>
          <button
            v-if="playlist.followed"
            class="btn-ghost btn-ghost--danger"
            @click="toggleFollow"
          >
            Ne plus suivre
          </button>
          <button v-else class="btn-ghost btn-ghost--accent" @click="toggleFollow">Suivre</button>
        </template>
      </PageHero>

      <!-- 2. Crawl status banner -->
      <div v-if="crawlState" class="crawl-banner" :class="crawlState">
        <span class="crawl-dot" />
        {{ crawlState === 'running' ? 'Crawl en cours…' : "Crawl en file d'attente" }}
      </div>

      <!-- 3. StatStrip -->
      <StatStrip :stats="stats" />

      <!-- 4. Description -->
      <RelBlock v-if="playlist.description" title="Description">
        <div class="desc-text">{{ playlist.description }}</div>
      </RelBlock>

      <!-- 5. Dans cette playlist (placeholder) -->
      <RelBlock
        v-if="playlist.top_artists?.length || playlist.top_genres?.length"
        title="Dans cette playlist"
      >
        <div class="dom-grid">
          <div v-if="playlist.top_artists?.length" class="dom-col">
            <h3>Artistes principaux</h3>
            <div class="dom-artists">
              <RouterLink
                v-for="a in playlist.top_artists"
                :key="a.id"
                class="dom-artist"
                :to="`/artist/${a.id}`"
              >
                <img
                  v-if="a.has_artwork"
                  class="dom-av"
                  :src="`/storage/artist-artworks/${a.id}.jpg`"
                />
                <span v-else class="dom-av"></span>
                <span class="dom-name">{{ a.name }}</span>
              </RouterLink>
            </div>
          </div>
          <div v-if="playlist.top_genres?.length" class="dom-col">
            <h3>Genres dominants</h3>
            <div class="dom-genres">
              <div v-for="g in playlist.top_genres" :key="g.name" class="dom-genre">
                <RouterLink
                  :to="`/style/${encodeURIComponent(g.name)}`"
                  style="text-decoration: none"
                >
                  <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
                </RouterLink>
                <span class="dom-bar" :data-fam="g.pillar">
                  <i :style="`width:${g.pct}%`"></i>
                </span>
                <span class="dom-pct">{{ g.pct }}%</span>
              </div>
            </div>
          </div>
        </div>
      </RelBlock>

      <!-- 6. Tracks -->
      <RelBlock v-if="playlist.tracks.length" title="Tracks" :count="playlist.tracks.length">
        <div class="mini-table-wrap">
          <table class="mini-table">
            <thead>
              <tr>
                <th class="mt-cover" />
                <th class="mt-track">Track</th>
                <th class="mt-num">BPM</th>
                <th class="mt-num">Key</th>
                <th class="mt-dur">Durée</th>
                <th class="mt-lib"></th>
                <th class="mt-preview" />
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in playlist.tracks" :key="t.catalog_id">
                <td class="mt-cover">
                  <div class="cover-mini">
                    <img
                      v-if="t.has_artwork"
                      :src="`/storage/catalog-artworks/${t.catalog_id}.jpg`"
                      :alt="t.title"
                    />
                  </div>
                </td>
                <td class="mt-track">
                  <RouterLink :to="`/catalog/${t.catalog_id}`" class="mt-link">
                    <span class="mt-title">{{ t.title }}</span>
                    <span class="mt-artist"
                      ><ArtistLinks :artists="t.artists" :fallback="t.artist || '—'"
                    /></span>
                  </RouterLink>
                </td>
                <td class="mt-num mono">{{ t.bpm ? fmtBpm(t.bpm) : '—' }}</td>
                <td class="mt-num mono">{{ t.key || '—' }}</td>
                <td class="mt-dur mono">{{ fmtMs(t.duration_ms) }}</td>
                <td class="mt-lib"><LibDot :in-lib="t.in_lib" /></td>
                <td class="mt-preview">
                  <span
                    v-if="t.has_preview"
                    class="play-btn"
                    :class="{ 'play-btn--playing': player.isCurrent(t.catalog_id) }"
                    @click="playTrack(t)"
                  >
                    <svg
                      v-if="!(player.isCurrent(t.catalog_id) && player.playing)"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                    >
                      <path d="M8 5.5v13l11-6.5z" />
                    </svg>
                    <svg v-else viewBox="0 0 24 24" fill="currentColor">
                      <path d="M6 5h4v14H6zm8 0h4v14h-4z" />
                    </svg>
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </RelBlock>

      <!-- 7. AdminCard (bottom) -->
      <AdminCard v-if="!playlist.has_artwork && playlist.source === 'deezer'" variant="warn">
        <button class="btn-ghost btn-ghost--accent" :disabled="fetchingArt" @click="fetchArtwork">
          {{ fetchingArt ? 'Fetch en cours…' : 'Fetch artwork Deezer' }}
        </button>
        <span v-if="artMsg" class="admin-msg" :class="artMsgType">{{ artMsg }}</span>
      </AdminCard>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../utils/api.js'
import { useToast } from '../stores/toast.js'
import PageHero from '../components/PageHero.vue'
import StatStrip from '../components/StatStrip.vue'
import RelBlock from '../components/RelBlock.vue'
import ArtistLinks from '../components/ArtistLinks.vue'
import LibDot from '../components/LibDot.vue'
import SourceBadge from '../components/SourceBadge.vue'
import StyleTag from '../components/StyleTag.vue'
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtBpm, fmtMs, fmtDate } from '../utils/format'
import AdminCard from '../components/AdminCard.vue'

const route = useRoute()
const player = useAudioPlayer()
const playlist = ref(null)
const loading = ref(true)
const fetchingArt = ref(false)
const artMsg = ref('')
const artMsgType = ref('')
const crawlState = ref(null) // 'queued' | 'running' | null
let crawlPollTimer = null

const heroSub = computed(() => {
  if (!playlist.value) return null
  const owner = playlist.value.owner
  if (!owner) return null
  const srcLabel = sourceLabel.value
  if (srcLabel && owner.toLowerCase() === srcLabel.toLowerCase()) return null
  return owner
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

const sourceLabel = computed(() => {
  const map = { deezer: 'Deezer', tidal: 'TIDAL', spotify: 'Spotify' }
  return map[playlist.value?.source] || null
})

const stats = computed(() => {
  if (!playlist.value) return []
  const p = playlist.value
  return [
    { label: 'Tracks', value: p.track_count ?? p.tracks.length },
    { label: 'Tracks radar', value: p.tracks.length },
    { label: 'Dernier crawl', value: p.last_crawled_at ? fmtDate(p.last_crawled_at) : 'jamais' },
    { label: 'Ajoutée le', value: p.created_at ? fmtDate(p.created_at) : '—' },
  ]
})

async function fetchDetail() {
  try {
    const { data } = await api.get(`/api/watchlist/${route.params.id}`)
    playlist.value = data
    if (data.current_task_id && !crawlPollTimer) {
      crawlState.value = 'queued'
      startCrawlPoll()
    }
  } catch {
    playlist.value = null
  } finally {
    loading.value = false
  }
}

function startCrawlPoll() {
  stopCrawlPoll()
  crawlPollTimer = setInterval(async () => {
    try {
      const { data } = await api.get(`/api/watchlist/${route.params.id}/crawl-status`)
      if (!data.status || data.status === 'done') {
        stopCrawlPoll()
        crawlState.value = null
        await fetchDetail()
      } else {
        crawlState.value = data.status
      }
    } catch {
      stopCrawlPoll()
      crawlState.value = null
    }
  }, 3000)
}

function stopCrawlPoll() {
  if (crawlPollTimer) {
    clearInterval(crawlPollTimer)
    crawlPollTimer = null
  }
}

async function toggleFollow() {
  if (!playlist.value) return
  try {
    if (playlist.value.followed) {
      await api.delete(`/api/watchlist/${playlist.value.id}`)
    } else {
      await api.post(`/api/watchlist/${playlist.value.id}/follow`)
    }
    await fetchDetail()
  } catch {
    useToast().show('Erreur lors du suivi de la playlist')
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
    id: t.catalog_id,
    catalog_id: t.catalog_id,
    title: t.title,
    artist: t.artist,
    bpm: t.bpm,
    key: t.key,
  })
}

onMounted(fetchDetail)
onUnmounted(stopCrawlPoll)
</script>

<style scoped>
.detail-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: var(--detail-max-w);
  margin-inline: auto;
  container-type: inline-size;
}
.desc-text {
  padding: 12px 14px;
  font: 400 13.5px/1.5 var(--font-ui);
  color: var(--ink-2);
}
.btn-ghost {
  padding: 8px 16px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 13px/1 var(--font-ui);
  text-decoration: none;
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s;
}
.btn-ghost:hover {
  background: var(--surface-2);
  color: var(--ink);
}
.btn-ghost--accent {
  border-color: var(--accent);
  color: var(--accent-ink);
}
.btn-ghost--accent:hover {
  background: var(--accent-soft);
}
.btn-ghost--danger:hover {
  color: var(--neg-ink);
  border-color: var(--neg-ink);
}

/* Mini track table */
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
  padding: 6px 12px;
  vertical-align: middle;
  border-bottom: 1px solid var(--line);
}
.mini-table tbody tr:last-child td {
  border-bottom: none;
}
.mini-table tbody tr:hover td {
  background: var(--surface-2);
}

.mt-lib {
  width: 48px;
  text-align: center;
}
.mt-cover {
  width: 40px;
  padding: 4px 8px !important;
}
.mt-track {
  min-width: 180px;
}
.mt-num {
  width: 56px;
  text-align: center;
}
.mt-dur {
  width: 56px;
  text-align: center;
}
.mt-preview {
  width: 40px;
  text-align: center;
}
.mono {
  font-family: var(--font-mono);
  color: var(--ink-2);
}

.cover-mini {
  width: 32px;
  height: 32px;
  border-radius: var(--r-xs);
  border: 1px solid var(--line);
  overflow: hidden;
  background: var(--surface-2);
}
.cover-mini img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
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

.play-btn {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  cursor: pointer;
  color: var(--ink-3);
  transition:
    color 0.12s,
    background 0.12s;
}
.play-btn:hover {
  color: var(--ink);
  background: var(--surface-2);
}
.play-btn--playing {
  color: var(--accent-ink);
}
.play-btn svg {
  width: 16px;
  height: 16px;
}

.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
  padding-top: 40px;
}

/* Crawl status banner */
.crawl-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0;
  padding: 10px 16px;
  border-radius: var(--r-sm);
  font: 500 13px/1 var(--font-ui);
}
.crawl-banner .crawl-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
}
.crawl-banner.running {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.crawl-banner.running .crawl-dot {
  background: var(--accent-ink);
  animation: pulse-dot 1.2s ease-in-out infinite;
}
.crawl-banner.queued {
  background: var(--surface-2);
  color: var(--ink-2);
}
.crawl-banner.queued .crawl-dot {
  background: var(--ink-3);
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

.admin-msg {
  font: 400 13px/1 var(--font-ui);
}
.admin-msg.success {
  color: var(--pos-ink);
}
.admin-msg.error {
  color: var(--neg-ink);
}

/* Dans cette playlist — top artists & genres */
.dom-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 22px;
}
.dom-col h3 {
  margin: 0 0 11px;
  font: 600 11px/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.dom-artists {
  display: flex;
  gap: 14px;
}
.dom-artist {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-decoration: none;
}
.dom-av {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 1px solid var(--line);
  object-fit: cover;
  background: var(--surface-3);
}
.dom-name {
  font: 500 12px var(--font-ui);
  color: var(--ink);
  max-width: 72px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: center;
}
.dom-artist:hover .dom-name {
  color: var(--accent-ink);
}
.dom-genres {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.dom-genre {
  display: grid;
  grid-template-columns: 132px 1fr 38px;
  align-items: center;
  gap: 10px;
}
.dom-bar {
  height: 7px;
  border-radius: 999px;
  background: var(--surface-2);
  overflow: hidden;
}
.dom-bar i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th, 0));
}
.dom-bar[data-fam='house'] { --th: var(--hue-house); }
.dom-bar[data-fam='techno'] { --th: var(--hue-techno); }
.dom-bar[data-fam='trance'] { --th: var(--hue-trance); }
.dom-bar[data-fam='dnb'] { --th: var(--hue-dnb); }
.dom-bar[data-fam='hardcore'] { --th: var(--hue-hardcore); }
.dom-bar[data-fam='harddance'] { --th: var(--hue-harddance); }
.dom-bar[data-fam='autres'] i { background: var(--ink-3); }
.dom-pct {
  font: 500 11px/1 var(--font-mono);
  color: var(--ink-3);
  text-align: right;
}

@container (max-width: 720px) {
  .dom-grid {
    grid-template-columns: 1fr;
  }
}
@container (max-width: 640px) {
  .detail-view {
    padding: var(--page-px-mobile);
  }
}
</style>

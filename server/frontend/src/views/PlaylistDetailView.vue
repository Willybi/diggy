<template>
  <div class="detail-view">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!playlist" class="state">Playlist introuvable.</div>
    <template v-else>
      <PageHero
        variant="square"
        :image-src="playlist.has_artwork ? `/storage/playlist-artworks/${playlist.id}.jpg` : null"
        :title="playlist.title || playlist.external_id"
        :subtitle="heroSub"
        :fallback-letter="(playlist.title || 'P')[0]"
      >
        <template #actions>
          <a class="btn-ghost" :href="`https://deezer.com/playlist/${playlist.external_id}`" target="_blank">Deezer</a>
          <button
            v-if="playlist.followed"
            class="btn-ghost btn-ghost--danger"
            @click="toggleFollow"
          >Ne plus suivre</button>
          <button
            v-else
            class="btn-ghost btn-ghost--accent"
            @click="toggleFollow"
          >Suivre</button>
        </template>
      </PageHero>

      <!-- Admin: fetch artwork -->
      <div v-if="auth.user?.is_admin && !playlist.has_artwork && playlist.source === 'deezer'" class="admin-card">
        <button class="btn-ghost btn-ghost--accent" :disabled="fetchingArt" @click="fetchArtwork">
          {{ fetchingArt ? 'Fetch en cours…' : 'Fetch artwork Deezer' }}
        </button>
        <span v-if="artMsg" class="admin-msg" :class="artMsgType">{{ artMsg }}</span>
      </div>

      <!-- Crawl status banner -->
      <div v-if="crawlState" class="crawl-banner" :class="crawlState">
        <span class="crawl-dot" />
        {{ crawlState === 'running' ? 'Crawl en cours…' : 'Crawl en file d\'attente' }}
      </div>

      <StatStrip :stats="stats" />

      <RelBlock v-if="playlist.description" title="Description">
        <div class="desc-text">{{ playlist.description }}</div>
      </RelBlock>

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
                <th class="mt-preview" />
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in playlist.tracks" :key="t.catalog_id">
                <td class="mt-cover">
                  <div class="cover-mini">
                    <img v-if="t.has_artwork" :src="`/storage/catalog-artworks/${t.catalog_id}.jpg`" :alt="t.title" />
                  </div>
                </td>
                <td class="mt-track">
                  <RouterLink :to="`/catalog/${t.catalog_id}`" class="mt-link">
                    <span class="mt-title">{{ t.title }}</span>
                    <span class="mt-artist"><ArtistLinks :artists="t.artists" :fallback="t.artist || '—'" /></span>
                  </RouterLink>
                </td>
                <td class="mt-num mono">{{ t.bpm ? fmtBpm(t.bpm) : '—' }}</td>
                <td class="mt-num mono">{{ t.key || '—' }}</td>
                <td class="mt-dur mono">{{ fmtMs(t.duration_ms) }}</td>
                <td class="mt-preview">
                  <span
                    v-if="t.has_preview"
                    class="play-btn"
                    :class="{ 'play-btn--playing': player.isCurrent(t.catalog_id) }"
                    @click="player.play({ id: t.catalog_id, catalog_id: t.catalog_id, title: t.title, artist: t.artist, bpm: t.bpm, key: t.key })"
                  >
                    <svg v-if="!(player.isCurrent(t.catalog_id) && player.playing)" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>
                    <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </RelBlock>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../utils/api.js'
import PageHero from '../components/PageHero.vue'
import StatStrip from '../components/StatStrip.vue'
import RelBlock from '../components/RelBlock.vue'
import ArtistLinks from '../components/ArtistLinks.vue'
import { useAudioPlayer } from '../stores/audioPlayer'
import { useAuthStore } from '../stores/auth.js'
import { fmtBpm, fmtMs, fmtDate } from '../utils/format'

const route = useRoute()
const auth = useAuthStore()
const player = useAudioPlayer()
const playlist = ref(null)
const loading = ref(true)
const fetchingArt = ref(false)
const artMsg = ref('')
const artMsgType = ref('')
const crawlState = ref(null)  // 'queued' | 'running' | null
let crawlPollTimer = null

const heroSub = computed(() => {
  if (!playlist.value) return null
  const parts = []
  if (playlist.value.owner) parts.push(playlist.value.owner)
  if (playlist.value.source) parts.push(playlist.value.source)
  return parts.join(' · ') || null
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
  } catch {}
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

onMounted(fetchDetail)
onUnmounted(stopCrawlPoll)
</script>

<style scoped>
.detail-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: var(--detail-max-w);
  margin-inline: auto;
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
  transition: background 0.12s, color 0.12s;
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
.mini-table-wrap { overflow-x: auto; }
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
.mini-table tbody tr:last-child td { border-bottom: none; }
.mini-table tbody tr:hover td { background: var(--surface-2); }

.mt-cover { width: 40px; padding: 4px 8px !important; }
.mt-track { min-width: 180px; }
.mt-num { width: 56px; text-align: center; }
.mt-dur { width: 56px; text-align: center; }
.mt-preview { width: 40px; text-align: center; }
.mono { font-family: var(--font-mono); color: var(--ink-2); }

.cover-mini {
  width: 32px; height: 32px;
  border-radius: var(--r-xs);
  border: 1px solid var(--line);
  overflow: hidden;
  background: var(--surface-2);
}
.cover-mini img { width: 100%; height: 100%; object-fit: cover; display: block; }

.mt-link { text-decoration: none; color: inherit; }
.mt-link:hover .mt-title { color: var(--accent-ink); }
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
  width: 28px; height: 28px;
  border-radius: 50%;
  cursor: pointer;
  color: var(--ink-3);
  transition: color 0.12s, background 0.12s;
}
.play-btn:hover { color: var(--ink); background: var(--surface-2); }
.play-btn--playing { color: var(--accent-ink); }
.play-btn svg { width: 16px; height: 16px; }

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
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.admin-card {
  margin: 12px 0;
  padding: 12px 16px;
  border: 1px solid var(--warn-ink);
  border-radius: var(--r-sm);
  background: color-mix(in srgb, var(--warn-ink) 6%, var(--surface));
  display: flex;
  align-items: center;
  gap: 12px;
}
.admin-msg {
  font: 400 13px/1 var(--font-ui);
}
.admin-msg.success { color: var(--pos-ink); }
.admin-msg.error { color: var(--neg-ink); }
</style>

<template>
  <div class="detail-view">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!playlist" class="state">Playlist introuvable.</div>
    <template v-else>
      <PageHero
        variant="square"
        :image-src="playlist.has_artwork ? `/storage/catalog-artworks/playlist-${playlist.id}.jpg` : null"
        :title="playlist.title || playlist.external_id"
        :subtitle="heroSub"
        :fallback-letter="(playlist.title || 'P')[0]"
      >
        <template #actions>
          <a
            class="btn-ghost"
            :href="externalUrl"
            target="_blank"
          >{{ playlist.source === 'tidal' ? 'Tidal' : 'Deezer' }}</a>
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
                    <span class="mt-artist">{{ t.artist || '—' }}</span>
                  </RouterLink>
                </td>
                <td class="mt-num mono">{{ t.bpm ? fmtBpm(t.bpm) : '—' }}</td>
                <td class="mt-num mono">{{ t.key || '—' }}</td>
                <td class="mt-dur mono">{{ fmtMs(t.duration_ms) }}</td>
                <td class="mt-preview">
                  <span
                    v-if="t.has_preview"
                    class="play-btn"
                    :class="{ 'play-btn--playing': playingId === t.catalog_id }"
                    @click="togglePlay(t.catalog_id, t.catalog_id)"
                  >
                    <svg v-if="playingId !== t.catalog_id" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>
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
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { storeToRefs } from 'pinia'
import PageHero from '../components/PageHero.vue'
import StatStrip from '../components/StatStrip.vue'
import RelBlock from '../components/RelBlock.vue'
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtBpm, fmtMs, fmtDate } from '../utils/format'

const route = useRoute()
const router = useRouter()
const player = useAudioPlayer()
const { playingId } = storeToRefs(player)
const { toggle: togglePlay } = player
const playlist = ref(null)
const loading = ref(true)

const externalUrl = computed(() => {
  if (!playlist.value) return '#'
  if (playlist.value.source === 'tidal') {
    return `https://tidal.com/playlist/${playlist.value.external_id}`
  }
  return `https://deezer.com/playlist/${playlist.value.external_id}`
})

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
    const { data } = await axios.get(`/api/watchlist/${route.params.id}`)
    playlist.value = data
  } catch {
    playlist.value = null
  } finally {
    loading.value = false
  }
}

async function toggleFollow() {
  if (!playlist.value) return
  try {
    if (playlist.value.followed) {
      await axios.delete(`/api/watchlist/${playlist.value.id}`)
    } else {
      await axios.post(`/api/watchlist/${playlist.value.id}/follow`)
    }
    await fetchDetail()
  } catch {}
}

onMounted(fetchDetail)
</script>

<style scoped>
.detail-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: 900px;
  margin: 0 auto;
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
  color: var(--neg-ink, #c0392b);
  border-color: var(--neg-ink, #c0392b);
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
</style>

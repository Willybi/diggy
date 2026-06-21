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
        <template #badges />
        <template #actions>
          <a v-if="sourceLabel && djSet.source_url" class="btn-ghost" :href="djSet.source_url" target="_blank">
            Voir sur {{ sourceLabel }}
          </a>
        </template>
      </PageHero>

      <StatStrip :stats="stats" />

      <!-- Admin: manage set artists -->
      <div v-if="auth.user?.is_admin" class="admin-card">
        <div class="admin-header">
          <span class="admin-label">Admin — Artistes du set</span>
        </div>
        <div v-if="djSet.artists.length" class="set-artists-list">
          <div v-for="a in djSet.artists" :key="a.artist_id" class="set-artist-row">
            <RouterLink :to="`/artist/${a.artist_id}`" class="sa-name">{{ a.artist_name }}</RouterLink>
            <span class="sa-role mono">{{ a.role }}</span>
            <button class="btn-row-action" @click="removeSetArtist(a.artist_id)">Retirer</button>
          </div>
        </div>
        <p v-else class="empty-hint">Aucun artiste lié.</p>
        <div class="sa-add-row">
          <input v-model="saQuery" class="admin-input" placeholder="Rechercher un artiste…" @input="onSaSearch" />
        </div>
        <div v-if="saResults.length" class="sa-results">
          <div v-for="a in saResults" :key="a.id" class="sa-hit" @click="addSetArtist(a.id)">
            <span class="sa-name">{{ a.name }}</span>
          </div>
        </div>
      </div>

      <!-- Artists -->
      <RelBlock v-if="djSet.artists.length > 1" title="Artistes">
        <AppearRow
          v-for="a in djSet.artists"
          :key="a.artist_id"
          :title="a.artist_name"
          :subtitle="a.role === 'b2b' ? 'B2B' : null"
          :to="`/artist/${a.artist_id}`"
        />
      </RelBlock>

      <!-- Tracklist -->
      <RelBlock title="Tracklist" :count="djSet.total_tracks">
        <div class="tracklist-wrap">
          <table class="tracklist">
            <thead>
              <tr>
                <th class="tl-pos">#</th>
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
                :class="trackRowClass(t)"
              >
                <td class="tl-pos mono">{{ t.position }}</td>
                <td class="tl-time mono">
                  <a
                    v-if="makeTimestampUrl(djSet.source_url, t.timecode_ms)"
                    :href="makeTimestampUrl(djSet.source_url, t.timecode_ms)"
                    target="_blank"
                    class="tl-time-link"
                  >{{ fmtCue(t.timecode_ms) }}</a>
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
                  <RouterLink v-if="t.catalog_id && !t.is_id" :to="`/catalog/${t.catalog_id}`" class="tl-link">
                    <span class="tl-title">{{ t.catalog_title || t.raw_title }}</span>
                    <span class="tl-artist">{{ t.catalog_artist || t.raw_artist }}</span>
                  </RouterLink>
                  <div v-else>
                    <span class="tl-title">{{ t.is_id ? 'ID' : (t.raw_title || '?') }}</span>
                    <span class="tl-artist">{{ t.is_id ? 'non identifié' : (t.raw_artist || '') }}</span>
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
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import PageHero from '../components/PageHero.vue'
import StatStrip from '../components/StatStrip.vue'
import RelBlock from '../components/RelBlock.vue'
import AppearRow from '../components/AppearRow.vue'

import LibDot from '../components/LibDot.vue'
import { useAuthStore } from '../stores/auth.js'
import { fmtMs, fmtDate, fmtCue } from '../utils/format'

const auth = useAuthStore()

// Admin: set artists
const saQuery = ref('')
const saResults = ref([])
let saTimer = null

function authHeaders() {
  return auth.token ? { Authorization: `Bearer ${auth.token}` } : {}
}

function onSaSearch() {
  clearTimeout(saTimer)
  if (!saQuery.value.trim()) { saResults.value = []; return }
  saTimer = setTimeout(async () => {
    const { data } = await axios.get('/api/artists/', { params: { q: saQuery.value.trim(), limit: 10 } })
    saResults.value = data
  }, 300)
}

async function addSetArtist(artistId) {
  if (!djSet.value) return
  try {
    await axios.post(`/api/admin/sets/${djSet.value.id}/artists`, { artist_id: artistId, role: 'dj' }, { headers: authHeaders() })
    // Reload set data
    const { data } = await axios.get(`/api/sets/${route.params.id}`)
    djSet.value = data
    saQuery.value = ''
    saResults.value = []
  } catch {}
}

async function removeSetArtist(artistId) {
  if (!djSet.value) return
  try {
    await axios.delete(`/api/admin/sets/${djSet.value.id}/artists/${artistId}`, { headers: authHeaders() })
    djSet.value.artists = djSet.value.artists.filter(a => a.artist_id !== artistId)
  } catch {}
}

const SOURCE_META = {
  youtube:         { label: 'YouTube' },
  '1001tracklists': { label: '1001Tracklists' },
  trackid:         { label: 'TrackID.net' },
  soundcloud:      { label: 'SoundCloud' },
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
  if (djSet.value.artists.length === 1) parts.push(djSet.value.artists[0].artist_name)
  if (djSet.value.event) parts.push(djSet.value.event)
  if (djSet.value.venue) parts.push(djSet.value.venue)
  return parts.join(' · ') || null
})

const sourceLabel = computed(() => {
  if (!djSet.value) return null
  // Prefer detecting from actual URL, fallback to source field
  return detectSourceLabel(djSet.value.source_url)
    || SOURCE_META[djSet.value.source]?.label
    || null
})

const stats = computed(() => {
  if (!djSet.value) return []
  const s = djSet.value
  return [
    { label: 'Durée', value: fmtMs(s.duration_ms) },
    { label: 'Date', value: fmtDate(s.played_date) },
    { label: 'Tracks', value: s.total_tracks },
    { label: 'Identifiées', value: s.identified_tracks },
  ]
})

function trackRowClass(t) {
  if (t.is_id) return 'row--id'
  if (!t.catalog_id) return 'row--unknown'
  return ''
}

onMounted(async () => {
  try {
    const { data } = await axios.get(`/api/sets/${route.params.id}`)
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
  max-width: 900px;
  margin: 0 auto;
}

/* Tracklist */
.tracklist-wrap { overflow-x: auto; }
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
.tracklist tbody tr:last-child td { border-bottom: none; }
.tracklist tbody tr:hover td { background: var(--surface-2); }

.tl-pos  { width: 36px; text-align: center; }
.tl-time { width: 72px; }
.tl-cover { width: 40px; padding: 4px 8px !important; }
.tl-track { min-width: 180px; }
.tl-lib { width: 44px; text-align: center; }

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

.mono { font-family: var(--font-mono); color: var(--ink-2); }

.tl-link {
  text-decoration: none;
  color: inherit;
}
.tl-link:hover .tl-title { color: var(--accent-ink); }

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

/* Row states */
.row--unknown .tl-title { color: var(--ink-3); font-style: italic; }
.row--unknown .tl-artist { color: var(--ink-3); }
.row--id .tl-title { color: var(--ink-3); font-style: italic; opacity: 0.6; }
.row--id .tl-artist { color: var(--ink-3); opacity: 0.6; }

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
  transition: background 0.12s, color 0.12s;
}
.btn-ghost:hover { background: var(--surface-2); color: var(--ink); }

.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
  padding-top: 40px;
}

/* Admin card */
.admin-card {
  margin: 16px 0;
  padding: 14px 18px;
  background: var(--surface);
  border: 1px solid var(--warn-ink, #e67e22);
  border-radius: var(--r-sm);
}
.admin-header { margin-bottom: 10px; }
.admin-label {
  font: 600 11px/1 var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--warn-ink, #e67e22);
}
.set-artists-list { margin-bottom: 10px; }
.set-artist-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 8px;
  border-radius: var(--r-sm);
}
.set-artist-row:hover { background: var(--surface-2); }
.sa-name { font: 500 13px/1 var(--font-ui); color: var(--ink); text-decoration: none; }
.sa-name:hover { color: var(--accent-ink); }
.sa-role { font-size: 11px; color: var(--ink-3); }
.sa-add-row { display: flex; gap: 8px; }
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
.admin-input:focus { border-color: var(--accent); }
.sa-results { max-height: 160px; overflow-y: auto; margin-top: 6px; }
.sa-hit {
  padding: 6px 10px;
  cursor: pointer;
  border-radius: var(--r-sm);
  font: 400 13px/1 var(--font-ui);
  color: var(--ink);
}
.sa-hit:hover { background: var(--accent-soft); color: var(--accent-ink); }
.empty-hint { font-size: 12px; color: var(--ink-3); font-style: italic; margin-bottom: 10px; }
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
.btn-row-action:hover { color: var(--neg-ink, #c0392b); border-color: var(--neg-ink, #c0392b); }
</style>

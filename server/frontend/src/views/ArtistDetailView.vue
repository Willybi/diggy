<template>
  <div class="detail-view">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!artist" class="state">Artiste introuvable.</div>
    <template v-else>
      <!-- HERO BANNER -->
      <section class="page-hero hero--banner">
        <div class="hero-banner">
          <div class="hb-tiles">
            <img
              v-for="t in bannerCovers"
              :key="t.id"
              class="hb-tile"
              :src="`/storage/catalog-artworks/${t.id}.jpg`"
            />
            <span
              v-for="n in Math.max(0, 12 - bannerCovers.length)"
              :key="'ph' + n"
              class="hb-tile"
            ></span>
          </div>
          <div class="hb-scrim"></div>
          <!-- Title on the banner, white + text-shadow -->
          <h1 class="hb-name">{{ artist.name }}</h1>
        </div>
        <!-- Avatar outside hero-banner to avoid overflow:hidden clipping -->
        <div class="hb-avatar">
          <div class="hero-visual hero-visual--round">
            <img
              v-if="artist.has_artwork"
              :src="`/storage/artist-artworks/${artist.id}.jpg`"
            />
            <span v-else class="hero-fallback">{{ artist.name[0] }}</span>
          </div>
        </div>
        <!-- Body below the banner -->
        <div class="hero-body-below">
          <p v-if="heroSub" class="hero-sub">{{ heroSub }}</p>
          <div v-if="artist.genres.length" class="hero-badges">
            <RouterLink
              v-for="g in artist.genres"
              :key="g.name"
              :to="`/style/${encodeURIComponent(g.name)}`"
              style="text-decoration: none"
            >
              <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
            </RouterLink>
          </div>
          <div class="hero-actions">
            <button class="btn-accent" @click="playRandomTrack">
              <svg viewBox="0 0 24 24" fill="currentColor" width="15" height="15">
                <path d="M8 5v14l11-7z" />
              </svg>
              Écouter un aperçu
            </button>
            <a
              v-if="artist.deezer_id"
              class="btn-ghost"
              :href="`https://deezer.com/artist/${artist.deezer_id}`"
              target="_blank"
            >Deezer</a>
            <a
              v-if="artist.soundcloud_id"
              class="btn-ghost"
              :href="`https://soundcloud.com/${artist.soundcloud_id}`"
              target="_blank"
            >SoundCloud</a>
            <a
              v-if="artist.trackid_id"
              class="btn-ghost"
              :href="`https://trackid.net/artist/${artist.trackid_id}`"
              target="_blank"
            >TrackID</a>
          </div>
        </div>
      </section>

      <StatStrip :stats="stats" />

      <RelBlock v-if="artist.aliases.length" title="Aliases">
        <div class="aliases-text">
          {{ artist.aliases.map((a) => a.alias).join(', ') }}
        </div>
      </RelBlock>

      <RelBlock v-if="artist.bio" title="Biographie">
        <div class="bio-text">{{ artist.bio }}</div>
      </RelBlock>

      <RelBlock v-if="artist.catalog_tracks.length" title="Tracks" :count="artist.stats.nb_catalog">
        <div class="mini-table-wrap">
          <table class="mini-table">
            <thead>
              <tr>
                <th class="mt-track">Track</th>
                <th class="mt-style">Style</th>
                <th class="mt-num">BPM</th>
                <th class="mt-num">Key</th>
                <th class="mt-dur">DUR.</th>
                <th class="mt-play"></th>
                <th class="mt-num">Rating</th>
                <th class="mt-lib"></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="t in artist.catalog_tracks"
                :key="t.id"
                :class="{ playing: player.isCurrent(t.id) }"
              >
                <td class="mt-track">
                  <RouterLink :to="`/catalog/${t.id}`" class="mt-link">
                    <span class="mt-title">{{ t.title }}</span>
                    <span class="mt-artist">
                      <ArtistLinks :artists="t.artists" :fallback="t.artist" />
                    </span>
                  </RouterLink>
                </td>
                <td class="mt-style">
                  <template v-if="t.genres?.length">
                    <RouterLink
                      v-for="g in t.genres"
                      :key="g.name"
                      :to="`/style/${encodeURIComponent(g.name)}`"
                      style="text-decoration: none"
                    >
                      <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
                    </RouterLink>
                  </template>
                  <StyleTag v-else-if="t.style" :name="t.style" />
                </td>
                <td class="mt-num mono">{{ t.bpm ? fmtBpm(t.bpm) : '—' }}</td>
                <td class="mt-num mono">{{ t.key || '—' }}</td>
                <td class="mt-dur mono">{{ t.duration_ms ? fmtMs(t.duration_ms) : '—' }}</td>
                <td class="mt-play">
                  <button
                    v-if="t.has_preview"
                    class="play-btn"
                    :class="{ playing: player.isCurrent(t.id) }"
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
                </td>
                <td class="mt-num">
                  <span v-if="t.rating" class="rating">
                    <span v-for="n in 5" :key="n" class="star" :class="{ 'is-on': n <= t.rating }">★</span>
                  </span>
                  <span v-else class="dash">—</span>
                </td>
                <td class="mt-lib">
                  <LibDot :in-lib="t.in_lib" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p
          v-if="artist.stats.nb_catalog > artist.catalog_tracks.length"
          class="more-note"
        >
          … et {{ artist.stats.nb_catalog - artist.catalog_tracks.length }} autres
        </p>
      </RelBlock>

      <RelBlock v-if="artist.sets.length" title="Sets" :count="artist.stats.nb_sets">
        <RouterLink
          v-for="s in artist.sets"
          :key="s.set_id"
          class="appear"
          :to="`/set/${s.set_id}`"
        >
          <img
            v-if="s.has_artwork"
            class="ap-thumb"
            :src="`/storage/set-artworks/${s.set_id}.jpg`"
          />
          <span v-else class="ap-thumb ap-thumb--empty"></span>
          <span class="ap-tx">
            <span class="ap-title">{{ s.title }}</span>
            <span class="ap-sub">{{ setSub(s) }}</span>
          </span>
          <span class="ap-right">
            <RingPct :value="s.identified_tracks" :total="s.total_tracks" />
          </span>
        </RouterLink>
      </RelBlock>

      <!-- Admin panel -->
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
                >dz:{{ h.deezer_id }}</a>
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
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useAudioPlayer } from '../stores/audioPlayer'
import StatStrip from '../components/StatStrip.vue'
import RelBlock from '../components/RelBlock.vue'
import StyleTag from '../components/StyleTag.vue'
import ArtistLinks from '../components/ArtistLinks.vue'
import AdminCard from '../components/AdminCard.vue'
import LibDot from '../components/LibDot.vue'
import RingPct from '../components/RingPct.vue'
import { fmtBpm, fmtMs, fmtDate } from '../utils/format'

const route = useRoute()
const router = useRouter()
const player = useAudioPlayer()
const artist = ref(null)
const loading = ref(true)

// Admin Deezer link
const dzQuery = ref('')
const dzHits = ref([])
const selectedHit = ref(null)
const linking = ref(false)
const adminMsg = ref('')
const adminMsgType = ref('ok')
let dzTimer = null

const bannerCovers = computed(() => {
  if (!artist.value) return []
  return artist.value.catalog_tracks.filter((t) => t.has_artwork).slice(0, 12)
})

function playRandomTrack() {
  player.playRandomArtist(artist.value.id)
}

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

function onDzSearch() {
  clearTimeout(dzTimer)
  selectedHit.value = null
  if (!dzQuery.value.trim()) {
    dzHits.value = []
    return
  }
  dzTimer = setTimeout(async () => {
    const { data } = await api.get('/api/admin/artists/search-deezer', {
      params: { q: dzQuery.value.trim() },
    })
    dzHits.value = data
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

const heroSub = computed(() => {
  if (!artist.value) return null
  const parts = []
  if (artist.value.real_name) parts.push(artist.value.real_name)
  if (artist.value.country) parts.push(artist.value.country)
  return parts.join(' · ') || null
})

const stats = computed(() => {
  if (!artist.value) return []
  const s = artist.value.stats
  return [
    { label: 'Catalog', value: s.nb_catalog ?? 0 },
    { label: 'In lib', value: s.nb_lib ?? 0 },
    { label: 'Sets', value: s.nb_sets ?? 0 },
    { label: 'Rating moy.', value: s.avg_rating ?? '--' },
  ]
})

function setSub(s) {
  const parts = []
  if (s.played_date) parts.push(fmtDate(s.played_date))
  if (s.role === 'b2b') parts.push('B2B')
  const id =
    s.identified_tracks === s.total_tracks
      ? `${s.total_tracks} tracks · toutes identifiées`
      : `${s.total_tracks} tracks · ${s.identified_tracks} identifiées`
  parts.push(id)
  return parts.join(' · ')
}

onMounted(async () => {
  try {
    const { data } = await api.get(`/api/artists/${route.params.id}`)
    artist.value = data
  } catch {
    artist.value = null
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

/* Hero banner */
.hero--banner {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0 0 22px;
  position: relative;
}
.hero-banner {
  position: relative;
  width: 100%;
  height: 184px;
  border-radius: var(--r-lg);
  overflow: hidden;
  box-shadow: var(--shadow-md);
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
.hb-scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to top,
    oklch(0.12 0.01 70 / 0.7) 0%,
    oklch(0.12 0.01 70 / 0.3) 40%,
    transparent 70%
  );
  pointer-events: none;
}
/* Avatar — positioned relative to .hero--banner, outside .hero-banner */
.hb-avatar {
  position: absolute;
  left: 16px;
  top: 92px;
  z-index: 2;
}
.hero-visual--round {
  flex: none;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  border: 4px solid var(--bg);
  overflow: hidden;
  background: var(--surface-2);
  display: grid;
  place-items: center;
  box-shadow: var(--shadow-md);
}
.hero-visual--round img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.hero-fallback {
  font: 700 32px/1 var(--font-ui);
  color: var(--ink-3);
  text-transform: uppercase;
}
/* Title on the banner — white + shadow */
.hb-name {
  position: absolute;
  left: 152px;
  bottom: 18px;
  right: 16px;
  font: 600 clamp(22px, 2.4vw, 34px)/1.1 var(--font-ui);
  letter-spacing: -0.02em;
  color: oklch(0.99 0 0);
  margin: 0;
  text-shadow: 0 1px 4px oklch(0.1 0.02 70 / 0.6), 0 0 12px oklch(0.1 0.02 70 / 0.3);
  overflow-wrap: break-word;
  z-index: 1;
}
/* Body below the banner — offset right of avatar */
.hero-body-below {
  padding: 16px 0 0 156px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.hero-sub {
  font: 400 14px/1.3 var(--font-ui);
  color: var(--ink-2);
  margin: 0;
}
.hero-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.hero-actions {
  display: flex;
  gap: 8px;
}

/* Buttons */
.btn-accent {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 16px;
  border-radius: var(--r-sm);
  border: 0;
  background: var(--accent);
  color: var(--on-accent);
  font: 600 13.5px var(--font-ui);
  cursor: pointer;
}
.btn-accent svg {
  width: 15px;
  height: 15px;
}
.btn-accent:hover {
  background: var(--accent-hover);
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

/* Text blocks */
.aliases-text,
.bio-text {
  padding: 12px 14px;
  font: 400 13.5px/1.5 var(--font-ui);
  color: var(--ink-2);
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
.mt-track {
  min-width: 160px;
}
.mt-style {
  width: 90px;
}
.mt-num {
  width: 56px;
  text-align: center;
}
.mt-dur {
  width: 58px;
  text-align: right;
  font-family: var(--font-mono);
  color: var(--ink-2);
}
.mt-play {
  width: 42px;
  text-align: center;
}
.mt-lib {
  width: 48px;
  text-align: center;
}
.mono {
  font-family: var(--font-mono);
  color: var(--ink-2);
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
.more-note {
  font: 400 13px var(--font-ui);
  color: var(--ink-3);
  margin-top: 8px;
  text-align: center;
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
.play-btn svg {
  width: 14px;
  height: 14px;
}
tr:hover .play-btn {
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
tr.playing td {
  background: var(--accent-soft);
}

/* Sets appearances */
.appear {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  text-decoration: none;
  color: inherit;
  border-bottom: 1px solid var(--line);
  transition: background 0.12s;
}
.appear:last-child {
  border-bottom: none;
}
.appear:hover {
  background: var(--surface-2);
}
.ap-thumb {
  width: 48px;
  height: 48px;
  border-radius: var(--r-sm);
  object-fit: cover;
  flex: none;
}
.ap-thumb--empty {
  display: block;
  background: var(--surface-2);
}
.ap-tx {
  flex: 1;
  min-width: 0;
}
.ap-title {
  display: block;
  font: 500 13.5px/1.3 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-sub {
  display: block;
  font: 400 12px/1.3 var(--font-ui);
  color: var(--ink-3);
  margin-top: 2px;
}
.ap-right {
  flex: none;
}

.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
  padding-top: 40px;
}

/* Admin card */
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.admin-link-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
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
.dz-results {
  max-height: 200px;
  overflow-y: auto;
  margin-bottom: 8px;
}
.dz-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
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
  font: 500 13px/1 var(--font-ui);
  color: var(--ink);
}
.dz-meta {
  display: block;
  font-size: 11px;
  margin-top: 2px;
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
  gap: 10px;
  padding: 10px 12px;
  background: var(--surface-2);
  border-radius: var(--r-sm);
  margin-top: 6px;
}
.confirm-text {
  font: 400 13px/1.3 var(--font-ui);
  color: var(--ink-2);
}
.btn-accent-sm {
  padding: 6px 14px;
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 500 12px/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-accent-sm:disabled {
  opacity: 0.5;
  cursor: default;
}
.btn-ghost-sm {
  padding: 6px 12px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 12px/1 var(--font-ui);
  cursor: pointer;
}
.btn-ghost-sm.danger:hover {
  color: var(--neg-ink);
  border-color: var(--neg-ink);
}
.admin-msg {
  font: 400 12px/1 var(--font-ui);
  margin-top: 8px;
  padding: 6px 10px;
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
.muted {
  color: var(--ink-3);
}

/* Responsive: narrow — avatar in flow, body full-width */
@container (max-width: 560px) {
  .hb-avatar {
    position: relative;
    top: -40px;
    left: 16px;
    margin-bottom: -20px;
  }
  .hero-body-below {
    padding-left: 0;
  }
}
</style>

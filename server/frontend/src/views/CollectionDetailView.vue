<template>
  <div class="collection-detail">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!collection" class="state">Collection introuvable.</div>
    <template v-else>
      <div class="page-head">
        <div class="titles">
          <h1>{{ collection.name }}</h1>
          <div class="sub">
            {{ collection.item_count }} {{ pl(collection.item_count, 'élément', 'éléments') }}
          </div>
        </div>
        <div class="head-tools">
          <button class="btn-del" @click="confirmDeleteCollection">Supprimer</button>
        </div>
      </div>

      <div v-if="!collection.items.length" class="state">
        Collection vide — ajoute des tracks, artistes, sets, genres ou playlists depuis leurs pages.
      </div>

      <div v-else class="rlist">
        <div
          v-for="item in collection.items"
          :key="itemKey(item)"
          class="rrow"
          :class="{ playing: isPlaying(item), missing: item.missing }"
          @click="onRowClick(item)"
        >
          <!-- type badge -->
          <span class="tbadge">
            <span v-html="typeIcon(item.item_type)"></span>
            <span class="lbl">{{ typeLabel(item.item_type) }}</span>
          </span>

          <!-- artwork -->
          <div class="rart" :class="artClass(item)">
            <img
              v-if="artworkUrl(item)"
              :src="artworkUrl(item)"
              alt=""
              loading="lazy"
              @error="(e) => (e.target.style.display = 'none')"
            />
            <span v-else-if="item.item_type === 'genre'" class="gd"></span>
            <span v-else class="ini">{{ initials(item) }}</span>
            <div v-if="isPlayable(item)" class="play" @click.stop="playTrack(item)">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
            </div>
          </div>

          <!-- text -->
          <div class="rtx">
            <div class="rtitle">{{ itemTitle(item) }}</div>
            <div v-if="item.subtitle" class="rsub">{{ item.subtitle }}</div>
            <div v-else-if="item.missing" class="rsub muted">Élément indisponible</div>
          </div>

          <!-- meta (track only) -->
          <div v-if="item.item_type === 'track' && !item.missing" class="rmeta">
            <span class="m-bpm">{{ item.bpm ? fmtBpm(item.bpm) : '—' }}</span>
            <span class="m-key">{{ item.key || '—' }}</span>
            <span class="m-dur">{{ fmtMs(item.duration_ms) }}</span>
          </div>

          <!-- remove -->
          <button
            class="rm-btn"
            title="Retirer"
            aria-label="Retirer"
            @click.stop="removeItem(item)"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.7"
              stroke-linecap="round"
            >
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
// C5 v2: a collection holds a HETEROGENEOUS mix (track / artist / set / genre /
// playlist). Presentation choice: ONE unified list of typed rows (modeled on the
// Hub search results), NOT a tracks-only table — a table's fixed columns (BPM/Key)
// are meaningless for a non-track row, so a per-type row keeps the mix readable
// with a single layout. The player/queue stays track-only (only tracks have a
// preview). Removal targets the polymorphic route.
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtMs, fmtBpm, pl } from '../utils/format'
import { scopeIcons } from '../components/hub/scopeIcons.js'

const route = useRoute()
const router = useRouter()
const player = useAudioPlayer()

const collection = ref(null)
const loading = ref(true)

async function fetchCollection() {
  try {
    const { data } = await api.get(`/api/collections/${route.params.id}`)
    collection.value = data
  } catch {
    collection.value = null
  } finally {
    loading.value = false
  }
}

// ── render helpers ──
function itemKey(item) {
  return `${item.item_type}-${item.item_id ?? item.item_name}`
}
function itemTitle(item) {
  return item.title || item.item_name || 'Élément indisponible'
}
function typeLabel(type) {
  const map = {
    track: 'TRACK',
    artist: 'ARTISTE',
    set: 'SET',
    genre: 'GENRE',
    playlist: 'PLAYLIST',
  }
  return map[type] || String(type).toUpperCase()
}
function typeIcon(type) {
  return scopeIcons[type] || scopeIcons.all
}
function artworkUrl(item) {
  if (item.missing || !item.has_artwork) return null
  if (item.item_type === 'track') return `/storage/catalog-artworks/${item.item_id}.jpg`
  if (item.item_type === 'artist') return `/storage/artist-artworks/${item.item_id}.jpg`
  if (item.item_type === 'set') return `/storage/set-artworks/${item.item_id}.jpg`
  if (item.item_type === 'playlist') return `/storage/playlist-artworks/${item.item_id}.jpg`
  return null
}
function artClass(item) {
  const cls = []
  if (item.item_type === 'artist') cls.push('round')
  if (item.item_type === 'genre') cls.push('genre')
  return cls
}
function initials(item) {
  const s = itemTitle(item)
  return (
    s
      .replace(/[^A-Za-zÀ-ÿ0-9 ]/g, '')
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0] || '')
      .join('')
      .toUpperCase() || '?'
  )
}

// ── playback (track-only) ──
function isPlayable(item) {
  return item.item_type === 'track' && !item.missing && item.has_preview
}
function isPlaying(item) {
  return item.item_type === 'track' && player.isCurrent(item.item_id) && player.playing
}
function toPlayerTrack(item) {
  return {
    id: item.item_id,
    catalog_id: item.item_id,
    title: item.title,
    artist: item.subtitle,
    bpm: item.bpm,
    key: item.key,
    has_preview: item.has_preview,
  }
}

// Queue source: only the collection's TRACK items feed the player.
const playSource = {
  type: 'list',
  getItems: () =>
    (collection.value?.items ?? [])
      .filter((i) => i.item_type === 'track' && !i.missing && i.has_preview)
      .map(toPlayerTrack),
}

function playTrack(item) {
  player.play(toPlayerTrack(item), playSource)
}

// ── navigation ──
function onRowClick(item) {
  if (item.missing) return
  const routes = {
    track: `/catalog/${item.item_id}`,
    artist: `/artist/${item.item_id}`,
    set: `/set/${item.item_id}`,
    playlist: `/playlists/${item.item_id}`,
    genre: `/style/${encodeURIComponent(item.item_name || item.title || '')}`,
  }
  const target = routes[item.item_type]
  if (target) router.push(target)
}

// ── removal (polymorphic) ──
async function removeItem(item) {
  // genre has a NULL item_id → matched by item_name query param (path id = placeholder 0)
  const id = item.item_id ?? 0
  let url = `/api/collections/${route.params.id}/items/${item.item_type}/${id}`
  if (item.item_type === 'genre') {
    url += `?item_name=${encodeURIComponent(item.item_name || '')}`
  }
  try {
    await api.delete(url)
    collection.value.items = collection.value.items.filter((i) => itemKey(i) !== itemKey(item))
    collection.value.item_count = collection.value.items.length
  } catch {
    // silent
  }
}

async function confirmDeleteCollection() {
  if (!confirm(`Supprimer « ${collection.value.name} » ?`)) return
  try {
    await api.delete(`/api/collections/${route.params.id}`)
    router.push('/collections')
  } catch {
    // silent
  }
}

onMounted(fetchCollection)
</script>

<style scoped>
.collection-detail {
  container-type: inline-size;
  min-height: 100%;
  max-width: var(--page-max-w);
  margin-inline: auto;
  width: 100%;
}

/* ============ PAGE HEAD ============ */
.page-head {
  display: flex;
  align-items: flex-start;
  padding: var(--space-6) var(--page-px) var(--space-4);
}
.titles h1 {
  margin: 0;
  font-size: var(--fs-xl);
  font-weight: 600;
  letter-spacing: -0.3px;
  color: var(--ink);
}
.sub {
  margin-top: var(--space-1);
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
}
.head-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

/* ============ BTN DELETE ============ */
.btn-del {
  height: 38px;
  padding: 0 var(--space-4);
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
.btn-del:hover {
  color: var(--neg-ink);
  border-color: var(--neg-ink);
}

/* ============ LIST ============ */
.rlist {
  display: flex;
  flex-direction: column;
  padding: var(--space-1) var(--page-px) var(--space-8);
}
.rrow {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-25) var(--space-3);
  border-radius: var(--r-md);
  cursor: pointer;
  transition: background 0.13s;
}
.rrow:hover {
  background: var(--surface-2);
}
.rrow.playing {
  background: var(--accent-wash);
}
.rrow.missing {
  cursor: default;
}
.rrow.missing:hover {
  background: transparent;
}

/* type badge */
.tbadge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  flex: none;
  width: 92px;
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.tbadge :deep(svg) {
  width: 13px;
  height: 13px;
  flex: none;
}

/* artwork */
.rart {
  position: relative;
  flex: none;
  width: 46px;
  height: 46px;
  border-radius: var(--r-xs);
  overflow: hidden;
  background-color: var(--surface-3);
  box-shadow: var(--shadow-sm);
  display: grid;
  place-items: center;
}
.rart.round {
  border-radius: 50%;
}
.rart img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.rart .ini {
  font: 600 var(--fs-base) var(--font-mono);
  color: var(--ink-3);
}
.rart.genre {
  background: var(--surface-3);
}
.rart.genre .gd {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--ink-3);
}
.rart .play {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: var(--overlay-soft);
  color: var(--overlay-text);
  opacity: 0;
  transition: opacity 0.12s;
}
.rart .play svg {
  width: 17px;
  height: 17px;
  margin-left: 1px;
}
.rrow:hover .rart .play,
.rrow.playing .rart .play {
  opacity: 1;
}
.rrow.missing .rart {
  opacity: 0.5;
}

/* text */
.rtx {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.rtitle {
  font: 500 var(--fs-title) var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rrow.playing .rtitle {
  color: var(--accent-ink);
}
.rrow.missing .rtitle {
  color: var(--ink-3);
}
.rsub {
  font: 400 var(--fs-sm) var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rsub.muted {
  font-style: italic;
}

/* meta */
.rmeta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex: none;
}
.rmeta .m-bpm {
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--ink-2);
}
.rmeta .m-key {
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--accent-ink);
}
.rmeta .m-dur {
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--ink-3);
}

/* remove */
.rm-btn {
  flex: none;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
  display: grid;
  place-items: center;
  border-radius: var(--r-xs);
  padding: 0;
  opacity: 0;
  transition:
    opacity 0.14s,
    color 0.14s;
}
.rrow:hover .rm-btn {
  opacity: 1;
}
.rm-btn:hover {
  color: var(--neg-ink);
}
.rm-btn svg {
  width: 16px;
  height: 16px;
}

/* ============ STATES ============ */
.state {
  /* diverges from canonical .state: horizontal page padding (listing view) */
  padding: var(--space-10) var(--page-px);
}

/* ============ RESPONSIVE ============ */
@container (max-width: 640px) {
  .page-head {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  .rlist {
    padding: var(--space-1) var(--page-px-mobile) var(--space-6);
  }
  .state {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  .tbadge {
    width: 30px;
  }
  .tbadge .lbl {
    display: none;
  }
  .rmeta .m-dur {
    display: none;
  }
  .rart .play {
    opacity: 1;
  }
  .rm-btn {
    opacity: 1;
  }
}
</style>

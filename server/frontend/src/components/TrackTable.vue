<template>
  <div class="table-wrap">
    <table class="track-table">
      <thead>
        <tr>
          <th class="col-play" />
          <th v-for="col in COLS" :key="col.key"
            :class="['col-' + col.key, col.num ? 'num' : '', col.sortable ? 'sortable' : '', sortKey === col.key ? 'is-sorted' : '']"
            @click="col.sortable && toggleSort(col.key)"
          >
            {{ col.label }}
            <span v-if="col.sortable && sortKey === col.key" class="sort-indicator">
              {{ sortDir === 'asc' ? '↑' : '↓' }}
            </span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="loading">
          <td :colspan="COLS.length + 1" class="state-cell">Chargement…</td>
        </tr>
        <tr v-else-if="!sortedTracks.length">
          <td :colspan="COLS.length + 1" class="state-cell">Aucun track.</td>
        </tr>
        <tr v-else v-for="track in sortedTracks" :key="track.id"
          :class="{ 'is-playing': playingId === track.id }"
        >
          <td class="col-play">
            <span
              class="play-btn"
              :class="{ 'play-btn--disabled': !track.has_preview, 'play-btn--playing': playingId === track.id }"
              @click="track.has_preview && handlePlay(track)"
            >
              <svg v-if="playingId !== track.id" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>
              <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>
            </span>
          </td>
          <td class="col-title">
            <div class="cell-track">
              <div class="mini-art">
                <img v-if="track.has_artwork"
                  :src="`/storage/artworks/${track.id}.jpg`"
                  :alt="track.title"
                />
              </div>
              <div class="track-info">
                <span class="track-title" :class="{ 'track-title--playing': playingId === track.id }">{{ track.title }}</span>
                <span class="track-artist">{{ track.artist }}</span>
              </div>
            </div>
          </td>
          <td class="col-style">
            <StyleTag v-if="firstTag(track)" :name="firstTag(track)" />
          </td>
          <td class="col-bpm num"><span class="mono">{{ track.bpm != null ? Math.round(track.bpm) : '—' }}</span></td>
          <td class="col-key num key-cell"><span class="mono">{{ track.key }}</span></td>
          <td class="col-duration num"><span class="mono">{{ formatDuration(track.duration) }}</span></td>
          <td class="col-rating num">
            <span class="rating">
              <span v-for="n in 5" :key="n" class="star" :class="{ 'is-on': n <= track.rating }">★</span>
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import StyleTag from './StyleTag.vue'
import { storeToRefs } from 'pinia'
import { useAudioPlayer } from '../stores/audioPlayer'

const props = defineProps({
  tracks: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const COLS = [
  { key: 'title',    label: 'Track',    sortable: true,  num: false },
  { key: 'style',    label: 'Style',    sortable: false, num: false },
  { key: 'bpm',      label: 'BPM',      sortable: true,  num: true  },
  { key: 'key',      label: 'Key',      sortable: false, num: true  },
  { key: 'duration', label: 'Durée',    sortable: true,  num: true  },
  { key: 'rating',   label: 'Rating',   sortable: true,  num: true  },
]

const player = useAudioPlayer()
const { playingId } = storeToRefs(player)
const { toggle: togglePlay } = player

function handlePlay(track) {
  togglePlay(track.id, track.catalog_id)
}

const sortKey = ref('title')
const sortDir = ref('asc')

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
}

const sortedTracks = computed(() => {
  const arr = [...props.tracks]
  const k = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  return arr.sort((a, b) => {
    const av = a[k] ?? ''
    const bv = b[k] ?? ''
    if (av < bv) return -1 * dir
    if (av > bv) return 1 * dir
    return 0
  })
})

function firstTag(track) {
  try {
    const tags = Array.isArray(track.tags) ? track.tags : JSON.parse(track.tags || '[]')
    return tags[0] || null
  } catch {
    return null
  }
}

function formatDuration(ms) {
  if (!ms) return '–'
  const total = Math.round(ms / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
</script>

<style scoped>
.table-wrap {
  overflow-x: auto;
}
.track-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
  table-layout: fixed;
}
.track-table thead th {
  text-align: left;
  padding: 0 14px 12px;
  font: 500 10.5px/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  user-select: none;
}
.track-table thead th.sortable {
  cursor: pointer;
}
.track-table thead th.sortable:hover {
  color: var(--ink-2);
}
.track-table thead th.is-sorted {
  color: var(--accent-ink);
}
.track-table thead th.num {
  text-align: right;
}
.track-table tbody td {
  height: var(--row-h);
  padding: 0 14px;
  vertical-align: middle;
  border-bottom: 1px solid var(--line);
}
.track-table tbody tr:hover td {
  background: var(--surface-2);
}
.track-table tbody tr.is-playing td {
  background: var(--accent-wash);
}
.track-table tbody tr.is-playing:hover td {
  background: var(--accent-soft);
}
.track-table tbody tr:last-child td {
  border-bottom: none;
}
.sort-indicator {
  margin-left: 4px;
  color: var(--accent-ink);
}
.state-cell {
  color: var(--ink-3);
  font-style: italic;
  text-align: center;
}

/* Play button */
.col-play {
  width: 30px;
  padding: 0 8px !important;
}
.play-btn {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 1px solid var(--line-2);
  background: var(--surface);
  display: grid;
  place-items: center;
  color: var(--ink-2);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s, background 0.12s, color 0.12s;
}
.play-btn--playing {
  opacity: 1 !important;
  background: var(--accent-soft);
  color: var(--accent-ink);
  border-color: transparent;
}
.play-btn--disabled {
  opacity: 0.2 !important;
  cursor: default;
  color: var(--ink-3);
}
.play-btn svg {
  width: 13px;
  height: 13px;
}
.track-table tbody tr:hover .play-btn {
  opacity: 1;
}

/* Column widths */
.col-play     { width: 38px; }
.col-title    { width: auto; }
.col-style    { width: 130px; }
.col-bpm      { width: 72px; }
.col-key      { width: 60px; }
.col-duration { width: 72px; }
.col-rating   { width: 90px; }

/* Track cell */
.cell-track {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.mini-art {
  width: 38px;
  height: 38px;
  flex: none;
  border-radius: var(--r-xs);
  border: 1px solid var(--line);
  overflow: hidden;
  background: repeating-linear-gradient(
    135deg,
    var(--surface-2) 0 5px,
    var(--surface-3) 5px 10px
  );
}
.mini-art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.track-info {
  min-width: 0;
  flex: 1;
}
.track-title {
  display: block;
  font-weight: 600;
  letter-spacing: -0.005em;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.track-title--playing {
  color: var(--accent-ink);
}
.track-artist {
  display: block;
  font-size: 12px;
  color: var(--ink-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Numeric cells */
.num {
  text-align: right;
}
.mono {
  font-family: var(--font-mono);
  color: var(--ink-2);
}
.key-cell .mono {
  color: var(--accent-ink);
  font-weight: 500;
}

/* Rating */
.rating {
  display: inline-flex;
  gap: 1px;
}
.star {
  font-size: 13px;
  color: var(--line-2);
  line-height: 1;
}
.star.is-on {
  color: var(--accent);
}
</style>

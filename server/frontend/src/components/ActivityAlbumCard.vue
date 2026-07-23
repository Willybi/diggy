<template>
  <div class="album-card" :class="{ open: expanded }">
    <div class="ac-head" @click="expanded = !expanded">
      <span class="tc-art">
        <img
          v-if="album.cover_id"
          :src="`/storage/catalog-artworks/${album.cover_id}.jpg`"
          alt=""
          loading="lazy"
          @error="hideImg"
        />
        <span v-else class="tc-ph"></span>
        <button
          v-if="coverTrack"
          class="tc-play"
          aria-label="Écouter l'aperçu"
          @click.stop="emit('play', coverTrack)"
        >
          <span class="tc-play-btn">
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M7 4.5l13 7.5-13 7.5z" />
            </svg>
          </span>
        </button>
      </span>
      <span class="tc-info">
        <span class="ac-titleline">
          <span class="ac-badge">Album</span>
          <span class="tc-title">{{ album.album_title || '—' }}</span>
        </span>
        <span class="tc-artist">{{ album.artist_name || '—' }}</span>
        <span class="ac-sub">{{ headMeta }}</span>
      </span>
      <button
        class="ac-toggle"
        :class="{ open: expanded }"
        :aria-expanded="expanded ? 'true' : 'false'"
        aria-label="Voir les titres"
        @click.stop="expanded = !expanded"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
    </div>
    <ul v-if="expanded" class="ac-list">
      <li v-for="(t, i) in album.tracks" :key="trackKey(t)" class="ac-item">
        <span class="ac-inum">{{ i + 1 }}</span>
        <button
          v-if="t.has_preview"
          class="ac-iplay"
          aria-label="Écouter l'aperçu"
          @click="emit('play', t)"
        >
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
        </button>
        <span v-else class="ac-idot"></span>
        <a
          v-if="!t.catalog_id && t.external_url"
          class="ac-ititle"
          :href="t.external_url"
          target="_blank"
          rel="noopener"
          >{{ t.title }}</a
        >
        <button v-else-if="t.catalog_id" class="ac-ititle" @click="emit('open', t)">
          {{ t.title }}
        </button>
        <!-- no catalog_id AND no external_url → nowhere to go: inert label -->
        <span v-else class="ac-ititle ac-ititle--inert">{{ t.title }}</span>
        <span v-if="trackMeta(t)" class="ac-imeta">{{ trackMeta(t) }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { fmtBpm, relativeAge } from '../utils/format'

const props = defineProps({
  // { album_id, album_title, artist_name, release_date, cover_id, tracks: [...] }
  album: { type: Object, required: true },
})
const emit = defineEmits(['play', 'open'])

const expanded = ref(false)

// First playable track backs the cover play button (previews come with a catalog id).
const coverTrack = computed(() => props.album.tracks.find((t) => t.has_preview) || null)
const age = computed(() => relativeAge(props.album.release_date))
// Mono meta line, aligned with <DiscoveryCard> — "N titres · il y a X".
const headMeta = computed(() => {
  const count = `${props.album.tracks.length} titres`
  return age.value ? `${count} · ${age.value}` : count
})

// Per-track BPM · KEY for the expanded rows (empty → no meta cell, never a dash).
function trackMeta(t) {
  const parts = []
  if (t.bpm) parts.push(fmtBpm(t.bpm))
  if (t.key) parts.push(t.key)
  return parts.join(' · ')
}
function trackKey(t) {
  return t.id ?? t.catalog_id ?? t.title
}
function hideImg(e) {
  e.target.style.display = 'none'
}
</script>

<style scoped>
/* Self-contained container aligned with <DiscoveryCard> (same surface/line/radius,
   same 64px cover, same collapsed height so both cohabit in .hb-shelfgrid). */
.album-card {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  min-width: 0;
  transition:
    background 0.12s,
    border-color 0.12s;
}
.album-card:hover {
  background: var(--surface-2);
  border-color: var(--line-2);
}
.ac-head {
  display: flex;
  gap: var(--space-25);
  padding: var(--space-2);
  cursor: pointer;
}

/* cover + play — mirrors DiscoveryCard */
.tc-art {
  position: relative;
  width: 64px;
  height: 64px;
  border-radius: var(--r-sm);
  overflow: hidden;
  flex: none;
  background: var(--surface-2);
}
.tc-art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.tc-ph {
  display: block;
  width: 100%;
  height: 100%;
  background: repeating-linear-gradient(45deg, var(--surface-2) 0 6px, var(--surface-3) 6px 12px);
}
.tc-play {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  cursor: pointer;
  opacity: 0;
  transition:
    opacity 0.12s,
    background 0.12s;
}
.album-card:hover .tc-play {
  opacity: 1;
  background: var(--overlay-soft);
}
.tc-play-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--surface);
  border: 1px solid var(--line-2);
  color: var(--ink);
}
.tc-play-btn svg {
  width: 15px;
  height: 15px;
}

/* body */
.tc-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
  justify-content: center;
}
.ac-titleline {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  min-width: 0;
}
.ac-badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: var(--r-pill);
  background: var(--surface-2);
  color: var(--ink-2);
  font: 600 var(--fs-nano) var(--font-mono);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.tc-title {
  font: 600 var(--fs-title) var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tc-artist {
  font: 400 var(--fs-sm) var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ac-sub {
  margin-top: 1px;
  font: 500 var(--fs-xs) var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* chevron toggle (in place of the play disc) */
.ac-toggle {
  flex: none;
  align-self: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 0;
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
  display: grid;
  place-items: center;
}
.ac-toggle:hover {
  background: var(--surface-3);
  color: var(--ink);
}
.ac-toggle svg {
  width: 16px;
  height: 16px;
  transition: transform 0.16s;
}
.ac-toggle.open svg {
  transform: rotate(180deg);
}

/* expanded tracklist — [# mono] [title] [BPM · KEY] rows */
.ac-list {
  list-style: none;
  margin: 0;
  padding: var(--space-1) var(--space-2) var(--space-2);
  border-top: 1px solid var(--line);
}
.ac-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-15) var(--space-1);
  border-radius: var(--r-xs);
}
.ac-item:hover {
  background: var(--surface-2);
}
.ac-inum {
  flex: none;
  width: 18px;
  text-align: right;
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}
.ac-iplay {
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 0;
  background: var(--surface-3);
  color: var(--ink-2);
  cursor: pointer;
  display: grid;
  place-items: center;
}
.ac-iplay:hover {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.ac-iplay svg {
  width: 13px;
  height: 13px;
  margin-left: 1px;
}
.ac-idot {
  flex: none;
  width: 26px;
  display: grid;
  place-items: center;
}
.ac-idot::before {
  content: '';
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--ink-3);
}
.ac-ititle {
  flex: 1;
  min-width: 0;
  text-align: left;
  border: 0;
  background: transparent;
  padding: 0;
  cursor: pointer;
  text-decoration: none;
  font: 400 var(--fs-sm) var(--font-ui);
  color: var(--ink-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ac-ititle:hover {
  color: var(--accent-ink);
}
/* No target (no catalog_id, no external_url) → not interactive. */
.ac-ititle--inert {
  cursor: default;
}
.ac-ititle--inert:hover {
  color: var(--ink-2);
}
.ac-imeta {
  flex: none;
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
}

/* No hover on touch → cover play stays visible on narrow containers. */
@container app (max-width: 640px) {
  .tc-play {
    opacity: 1;
  }
}
</style>

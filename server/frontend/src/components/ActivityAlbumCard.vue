<template>
  <div class="trend-card activity-card album-card" :class="{ open: expanded }">
    <div class="ac-head" @click="expanded = !expanded">
      <div class="tc-art">
        <img
          v-if="album.cover_id"
          :src="`/storage/catalog-artworks/${album.cover_id}.jpg`"
          alt=""
          loading="lazy"
          @error="hideImg"
        />
        <div v-if="coverTrack" class="tc-play" @click.stop="emit('play', coverTrack)">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
        </div>
      </div>
      <div class="tc-info">
        <span class="ac-badge">Nouveauté</span>
        <div class="tc-title">{{ album.album_title || '—' }}</div>
        <div class="tc-artist">{{ album.artist_name || '—' }}</div>
        <div class="ac-sub">
          {{ album.tracks.length }} titres<span v-if="age"> · Sorti {{ age }}</span>
        </div>
      </div>
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
      <li v-for="t in album.tracks" :key="trackKey(t)" class="ac-item">
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
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { relativeAge } from '../utils/format'

const props = defineProps({
  // { album_id, album_title, artist_name, release_date, cover_id, tracks: [...] }
  album: { type: Object, required: true },
})
const emit = defineEmits(['play', 'open'])

const expanded = ref(false)

// First playable track backs the cover play button (previews come with a catalog id).
const coverTrack = computed(() => props.album.tracks.find((t) => t.has_preview) || null)
const age = computed(() => relativeAge(props.album.release_date))

function trackKey(t) {
  return t.id ?? t.catalog_id ?? t.title
}
function hideImg(e) {
  e.target.style.display = 'none'
}
</script>

<style scoped>
.album-card {
  flex-direction: column;
  align-items: stretch;
  gap: 0;
  padding: 0;
}
.ac-head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2);
}
.tc-art {
  position: relative;
  width: 80px;
  height: 80px;
  border-radius: var(--r-sm);
  overflow: hidden;
  flex: none;
  background: var(--surface-3);
}
.tc-art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.tc-play {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: var(--overlay-soft);
  color: var(--overlay-text);
  opacity: 0;
  transition: opacity 0.12s;
}
.tc-play svg {
  width: 22px;
  height: 22px;
}
.album-card:hover .tc-play {
  opacity: 1;
}
.tc-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.ac-badge {
  display: inline-flex;
  align-items: center;
  padding: var(--space-05) var(--space-15);
  border-radius: var(--r-xs);
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 600 var(--fs-xs)/1 var(--font-mono);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  align-self: flex-start;
}
.tc-title {
  font: 500 var(--fs-base) var(--font-ui);
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
  font: 400 var(--fs-xs) var(--font-ui);
  color: var(--ink-3);
  margin-top: var(--space-05);
}
.ac-toggle {
  flex: none;
  width: 30px;
  height: 30px;
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
.ac-list {
  list-style: none;
  margin: 0;
  padding: 0 var(--space-2) var(--space-2);
  border-top: 1px solid var(--line);
}
.ac-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-15) var(--space-1);
}
.ac-item + .ac-item {
  border-top: 1px solid var(--line);
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
</style>

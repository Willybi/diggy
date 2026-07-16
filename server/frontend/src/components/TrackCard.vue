<template>
  <div class="track-card" :class="{ playing, 'has-end': !!$slots.end }">
    <div class="tk-art">
      <Artwork size="row" :src="coverSrc" :alt="track.title" :in-lib="!!track.in_lib" />
      <button
        v-if="track.has_preview"
        class="tk-play"
        :class="{ playing }"
        :aria-label="playing ? 'Pause' : `Écouter ${track.title}`"
        @click.stop="emitPlay"
      >
        <svg v-if="playing" class="tk-play-icon" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="5" width="4" height="14" />
          <rect x="14" y="5" width="4" height="14" />
        </svg>
        <svg v-else class="tk-play-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M8 5v14l11-7z" />
        </svg>
      </button>
    </div>

    <div class="tk-tx">
      <span class="tk-title">{{ track.title }}</span>
      <span v-if="showArtist" class="tk-artist">{{ track.artist }}</span>
    </div>

    <span class="tk-bpm">{{ fmtBpm(track.bpm) }}</span>
    <span class="tk-key">{{ track.key || '' }}</span>

    <span v-if="$slots.end" class="tk-end"><slot name="end"></slot></span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Artwork from './Artwork.vue'
import { fmtBpm } from '../utils/format'

const props = defineProps({
  // { id, title, artist?, bpm, key, has_artwork, has_preview, in_lib }
  track: { type: Object, required: true },
  showArtist: { type: Boolean, default: false },
  playing: { type: Boolean, default: false },
})
const emit = defineEmits(['play'])

// Same cover convention as the existing views. No artwork → Artwork placeholder.
const coverSrc = computed(() =>
  props.track.has_artwork ? `/storage/catalog-artworks/${props.track.id}.jpg` : undefined,
)

function emitPlay() {
  emit('play')
}
</script>

<style scoped>
.track-card {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) 42px 30px;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-2) var(--space-3);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition:
    background 0.12s,
    border-color 0.12s;
}
.track-card.has-end {
  grid-template-columns: 36px minmax(0, 1fr) 42px 30px auto;
}
.track-card:hover {
  background: var(--surface-2);
  border-color: var(--line-2);
}
.track-card.playing,
.track-card.playing:hover {
  background: var(--accent-wash);
}

.tk-art {
  position: relative;
  width: 36px;
  height: 36px;
  flex: none;
}
.tk-play {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: var(--r-xs);
  background: var(--overlay-soft);
  color: var(--overlay-text);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s;
}
.track-card:hover .tk-play,
.tk-play.playing {
  opacity: 1;
}
.tk-play-icon {
  width: 16px;
  height: 16px;
}

.tk-tx {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.tk-title {
  font: 600 var(--fs-sm)/1.2 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tk-artist {
  font: 400 var(--fs-xs)/1.2 var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tk-bpm {
  font: 400 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
  text-align: right;
}
.tk-key {
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--accent-ink);
}
.tk-end {
  display: inline-flex;
  align-items: center;
}

/* No hover on touch → play stays visible on narrow containers (page container query). */
@container (max-width: 640px) {
  .tk-play {
    opacity: 1;
  }
}
</style>

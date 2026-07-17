<template>
  <div
    class="track-card"
    :class="{ playing, 'has-end': !!$slots.end, 'has-duration': showDuration }"
  >
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
      <span v-if="showArtist" class="tk-artist">
        <template v-if="track.artists && track.artists.length">
          <template v-for="(a, i) in track.artists" :key="a.id">
            <span v-if="i > 0" class="tk-artist-sep">, </span>
            <RouterLink :to="`/artist/${a.id}`" class="tk-artist-link" @click.stop>
              {{ a.name }}
            </RouterLink>
          </template>
        </template>
        <template v-else>{{ track.artist }}</template>
      </span>
    </div>

    <span class="tk-bpm">{{ fmtBpm(track.bpm) }}</span>
    <span class="tk-key">{{ track.key || '' }}</span>
    <span v-if="showDuration" class="tk-dur" :class="{ 'tk-dur--empty': !track.duration_ms }">{{
      fmtMs(track.duration_ms)
    }}</span>

    <span v-if="$slots.end" class="tk-end"><slot name="end"></slot></span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Artwork from './Artwork.vue'
import { fmtBpm, fmtMs } from '../utils/format'

const props = defineProps({
  // { id, title, artist?, artists?: [{ id, name }], bpm, key, duration_ms?, has_artwork, has_preview, in_lib }
  track: { type: Object, required: true },
  showArtist: { type: Boolean, default: false },
  // Opt-in duration column (m:ss / h:mm:ss) inserted between Key and the end slot.
  showDuration: { type: Boolean, default: false },
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
/* Duration column (44px) inserted between Key and the end slot. */
.track-card.has-duration {
  grid-template-columns: 36px minmax(0, 1fr) 42px 30px 44px;
}
.track-card.has-duration.has-end {
  grid-template-columns: 36px minmax(0, 1fr) 42px 30px 44px auto;
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
/* Clickable artists — same voice as the plain string, underline on hover only. */
.tk-artist-link {
  color: inherit;
  text-decoration: none;
  transition: color 0.12s;
}
.tk-artist-link:hover {
  color: var(--ink);
  text-decoration: underline;
}
.tk-artist-sep {
  color: var(--ink-3);
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
/* Duration — same voice as BPM (mono, --ink-2, right-aligned); the Key keeps the accent. */
.tk-dur {
  font: 400 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
  text-align: right;
}
/* Missing duration → dimmer dash (grid alignment preserved). */
.tk-dur--empty {
  color: var(--ink-3);
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
  /* Duration is secondary — drop it (and its column) under 640px; BPM/Key stay. */
  .tk-dur {
    display: none;
  }
  .track-card.has-duration {
    grid-template-columns: 36px minmax(0, 1fr) 42px 30px;
  }
  .track-card.has-duration.has-end {
    grid-template-columns: 36px minmax(0, 1fr) 42px 30px auto;
  }
}
</style>

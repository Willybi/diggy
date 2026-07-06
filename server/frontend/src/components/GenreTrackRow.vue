<template>
  <div class="track-row" :class="{ playing: isCurrent }" @click="onPlay">
    <!-- Play overlay -->
    <button
      class="play-btn"
      :class="{ visible: isCurrent }"
      @click.stop="onPlay"
      aria-label="Lecture"
    >
      <svg v-if="!isPlaying" viewBox="0 0 24 24" fill="currentColor">
        <path d="M8 5v14l11-7z" />
      </svg>
      <svg v-else viewBox="0 0 24 24" fill="currentColor">
        <path d="M6 5h4v14H6zm8 0h4v14h-4z" />
      </svg>
    </button>

    <!-- Cover -->
    <div class="cover">
      <img
        v-if="track.hasArtwork"
        :src="`/storage/catalog-artworks/${track.id}.jpg`"
        alt=""
        loading="lazy"
        @error="(e) => (e.target.style.display = 'none')"
      />
      <span v-else class="fb">{{ (track.title || '?')[0] }}</span>
    </div>

    <!-- Title + Artist -->
    <div class="info">
      <span class="title">{{ track.title }}</span>
      <span class="artist"><ArtistLinks :artists="track.artists" :fallback="track.artist" /></span>
    </div>

    <!-- BPM -->
    <span class="meta bpm">{{ track.bpm ? Math.round(track.bpm) : '—' }}</span>

    <!-- Key -->
    <span class="meta key">{{ track.key || '—' }}</span>

    <!-- Duration -->
    <span class="meta dur">{{ fmtMs(track.durationMs) }}</span>

    <!-- In-lib -->
    <LibDot :in-lib="!!track.inLib" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtMs } from '../utils/format'
import LibDot from './LibDot.vue'
import ArtistLinks from './ArtistLinks.vue'

const props = defineProps({
  track: { type: Object, required: true },
})

const player = useAudioPlayer()
const isCurrent = computed(() => player.isCurrent(props.track.id))
const isPlaying = computed(() => isCurrent.value && player.playing)

function onPlay() {
  if (!props.track.hasPreview) return
  player.play({
    id: props.track.id,
    catalog_id: props.track.id,
    title: props.track.title,
    artist: props.track.artist,
    artist_id: props.track.artist_id,
    bpm: props.track.bpm,
    key: props.track.key,
  })
}
</script>

<style scoped>
.track-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 14px;
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: background 0.12s;
  min-height: var(--row-h, 48px);
}
.track-row:hover {
  background: var(--surface-2);
}
.track-row.playing {
  background: var(--accent-wash, var(--surface-2));
}

/* Play button */
.play-btn {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 50%;
  background: var(--accent);
  color: var(--on-accent);
  display: grid;
  place-items: center;
  cursor: pointer;
  opacity: 0;
  flex: none;
  transition: opacity 0.15s;
}
.play-btn svg {
  width: 14px;
  height: 14px;
}
.track-row:hover .play-btn {
  opacity: 1;
}
.play-btn.visible {
  opacity: 1;
}

/* Cover */
.cover {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  background: var(--surface-2);
  border: 1px solid var(--line);
  overflow: hidden;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
}
.cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.fb {
  font: 600 14px/1 var(--font-ui);
  color: var(--ink-3);
}

/* Info */
.info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.title {
  font: 500 13px/1.2 var(--font-ui);
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.artist {
  font: 400 11px/1.2 var(--font-ui);
  color: var(--ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Meta fields */
.meta {
  font: 400 11.5px/1 var(--font-mono);
  white-space: nowrap;
  flex: none;
}
.bpm {
  color: var(--ink-2);
  min-width: 30px;
  text-align: right;
}
.key {
  color: var(--accent-ink);
  min-width: 28px;
  text-align: center;
}
.dur {
  color: var(--ink-3);
  min-width: 36px;
  text-align: right;
}

/* Responsive: hide duration on narrow */
@container app (max-width: 640px) {
  .dur {
    display: none;
  }
}
</style>

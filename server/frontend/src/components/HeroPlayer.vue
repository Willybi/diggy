<template>
  <button
    class="hero-play"
    :class="{ 'hero-play--playing': isPlaying, 'hero-play--disabled': disabled }"
    :disabled="disabled"
    @click="!disabled && onPlay()"
  >
    <svg v-if="!isPlaying" viewBox="0 0 24 24" fill="currentColor">
      <path d="M8 5.5v13l11-6.5z" />
    </svg>
    <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zm8 0h4v14h-4z" /></svg>
    <span class="hero-play-label">{{ isPlaying ? 'Pause' : 'Preview' }}</span>
  </button>
</template>

<script setup>
import { computed } from 'vue'
import { useAudioPlayer } from '../stores/audioPlayer'

const props = defineProps({
  catalogId: { type: Number, required: true },
  disabled: { type: Boolean, default: false },
  title: { type: String, default: '' },
  artist: { type: String, default: '' },
  bpm: { type: Number, default: null },
  trackKey: { type: String, default: '' },
})

const player = useAudioPlayer()

const isPlaying = computed(() => player.isCurrent(props.catalogId) && player.playing)

function onPlay() {
  player.play({
    id: props.catalogId,
    catalog_id: props.catalogId,
    title: props.title,
    artist: props.artist,
    bpm: props.bpm,
    key: props.trackKey,
  })
}
</script>

<style scoped>
.hero-play {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s;
}
.hero-play svg {
  width: 16px;
  height: 16px;
}
.hero-play:hover:not(:disabled) {
  background: var(--surface-2);
  color: var(--ink);
}
.hero-play--playing {
  background: var(--accent-soft);
  color: var(--accent-ink);
  border-color: transparent;
}
.hero-play--disabled {
  opacity: 0.35;
  cursor: default;
}
</style>

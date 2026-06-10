<template>
  <article class="track-card">
    <div class="artwork">
      <img v-if="track.has_artwork"
        :src="`/storage/artworks/${track.id}.jpg`"
        :alt="`${track.artist} – ${track.title}`"
      />
    </div>
    <div class="meta">
      <p class="title">{{ track.title }}</p>
      <p class="artist">{{ track.artist }}</p>
      <div class="metrics">
        <span class="metric mono">{{ track.bpm }} <span class="unit">BPM</span></span>
        <span class="metric mono key">{{ track.key }}</span>
        <span class="metric mono">{{ formatDuration(track.duration) }}</span>
      </div>
      <div v-if="parsedTags.length" class="tags">
        <StyleTag v-for="tag in parsedTags" :key="tag" :name="tag" />
      </div>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import StyleTag from './StyleTag.vue'

const props = defineProps({
  track: { type: Object, required: true },
})

const parsedTags = computed(() => {
  try {
    const t = props.track.tags
    if (!t) return []
    return Array.isArray(t) ? t : JSON.parse(t)
  } catch {
    return []
  }
})

function formatDuration(ms) {
  if (!ms) return '–'
  const total = Math.round(ms / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
</script>

<style scoped>
.track-card {
  display: flex;
  gap: 14px;
  padding: 12px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.2s, border-color 0.2s, transform 0.2s;
}
.track-card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--line-2);
  transform: translateY(-1px);
}
.artwork {
  width: 74px;
  height: 74px;
  flex: none;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  overflow: hidden;
  background: repeating-linear-gradient(
    135deg,
    var(--surface-2) 0 7px,
    var(--surface-3) 7px 14px
  );
}
.artwork img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.title {
  font: 600 15px/1.3 var(--font-ui);
  letter-spacing: -0.01em;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin: 0;
}
.artist {
  font: 400 13px/1.3 var(--font-ui);
  color: var(--ink-2);
  margin: 0;
}
.metrics {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: auto;
}
.metric {
  font: 500 12px/1 var(--font-mono);
  color: var(--ink-2);
}
.metric.key {
  color: var(--accent-ink);
}
.unit {
  color: var(--ink-3);
  font-size: 10px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 4px;
}
</style>

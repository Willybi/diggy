<template>
  <RouterLink :to="`/set/${set.id}`" class="set-card">
    <Artwork size="card" :src="coverSrc" :alt="set.title" />
    <span class="sc-title">{{ set.title }}</span>
    <span v-if="artistsText" class="sc-artists">{{ artistsText }}</span>
    <span v-if="metaParts.length" class="sc-meta">{{ metaParts.join(' · ') }}</span>
    <div v-if="$slots.footer" class="sc-footer"><slot name="footer"></slot></div>
  </RouterLink>
</template>

<script setup>
import { computed } from 'vue'
import Artwork from './Artwork.vue'
import { fmtDate, fmtMs, pl } from '../utils/format'

const props = defineProps({
  // Contract GET /api/sets/{id}/similar — artists[] are plain names, not links.
  // { id, title, source, played_date, duration_ms, has_artwork, total_tracks, identified_tracks, artists[] }
  set: { type: Object, required: true },
})

// Set covers live under a distinct bucket. No artwork → Artwork placeholder.
const coverSrc = computed(() =>
  props.set.has_artwork ? `/storage/set-artworks/${props.set.id}.jpg` : undefined,
)

const artistsText = computed(() =>
  props.set.artists && props.set.artists.length ? props.set.artists.join(', ') : '',
)

// Mono meta line `date · durée · N tracks` — null fields omitted, never a dash.
const metaParts = computed(() => {
  const parts = []
  if (props.set.played_date) parts.push(fmtDate(props.set.played_date))
  if (props.set.duration_ms) parts.push(fmtMs(props.set.duration_ms))
  if (props.set.total_tracks != null) {
    parts.push(`${props.set.total_tracks} ${pl(props.set.total_tracks, 'track', 'tracks')}`)
  }
  return parts
})
</script>

<style scoped>
.set-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-25);
  padding: var(--space-3);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-sm);
  text-decoration: none;
  color: inherit;
  transition:
    background 0.12s,
    border-color 0.12s;
}
.set-card:hover {
  background: var(--surface-2);
  border-color: var(--line-2);
}
.set-card:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* Titles of sets are long → clamp to two lines, break anywhere. */
.sc-title {
  font: 600 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
}
.sc-artists {
  font: 400 var(--fs-xs)/1.3 var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sc-meta {
  font: 500 var(--fs-xs)/1.3 var(--font-mono);
  color: var(--ink-3);
}
.sc-footer {
  display: flex;
  align-items: center;
}
</style>

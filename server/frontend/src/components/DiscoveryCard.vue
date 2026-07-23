<template>
  <component
    :is="rootTag"
    class="dc-card"
    :class="{ playing, 'dc-card--skeleton': skeleton }"
    v-bind="rootAttrs"
    @click="onRootClick"
    @keydown="onRootKey"
  >
    <template v-if="skeleton">
      <span class="dc-sk-cover"></span>
      <span class="dc-sk-body">
        <span class="dc-sk-line dc-sk-line--1"></span>
        <span class="dc-sk-line dc-sk-line--2"></span>
        <span class="dc-sk-line dc-sk-line--3"></span>
      </span>
    </template>

    <template v-else>
      <span class="dc-cover">
        <Artwork size="card" :src="coverSrc" :alt="title" :in-lib="inLib" />
        <button
          v-if="hasPreview"
          class="dc-play"
          :class="{ playing }"
          :aria-label="playing ? 'Pause' : `Écouter ${title}`"
          @click.stop="emitPlay"
        >
          <span class="dc-play-btn">
            <svg
              v-if="playing"
              class="dc-play-icon"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <rect x="6" y="5" width="4" height="14" rx="1" />
              <rect x="14" y="5" width="4" height="14" rx="1" />
            </svg>
            <svg
              v-else
              class="dc-play-icon"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M7 4.5l13 7.5-13 7.5z" />
            </svg>
          </span>
        </button>
      </span>

      <span class="dc-body">
        <span class="dc-titleline">
          <span v-if="badgeText" class="dc-badge" :class="badgeClass">
            <svg
              v-if="badgeIcon === 'set'"
              class="dc-badge-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="9" />
              <circle cx="12" cy="12" r="2.4" />
            </svg>
            <svg
              v-else-if="badgeIcon === 'ext'"
              class="dc-badge-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M14 4h6v6" />
              <path d="M20 4l-8.5 8.5" />
              <path
                d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"
              />
            </svg>
            {{ badgeText }}
          </span>
          <span class="dc-title">{{ title }}</span>
        </span>
        <span v-if="artistsText" class="dc-artist">{{ artistsText }}</span>
        <span v-if="metaText" class="dc-meta">{{ metaText }}</span>
      </span>
    </template>
  </component>
</template>

<script setup>
// Reusable discovery card (Hub shelves + future destinations). Single root:
// external link → <a>; otherwise a clickable element that emits `open` (the parent
// owns internal navigation + guest→login interception). `skeleton` renders an inert
// loading ghost so shelves reuse this component instead of duplicating placeholders.
import { computed } from 'vue'
import Artwork from './Artwork.vue'

const props = defineProps({
  title: { type: String, default: '' },
  // Multiple artists possible per track — joined by ", ". Falls back to the flat
  // `artist` string when the endpoint doesn't provide the array.
  artists: { type: Array, default: () => [] }, // [{ id, name }]
  artist: { type: String, default: '' },
  coverId: { type: Number, default: undefined },
  hasArtwork: { type: Boolean, default: false },
  hasPreview: { type: Boolean, default: false },
  // Trend variant → `#rank` accent badge.
  rank: { type: Number, default: undefined },
  // Type pill: 'Nouveauté' (accent) or 'Set' (neutral). Optional glyph via badgeIcon.
  badge: { type: String, default: undefined },
  badgeIcon: { type: String, default: undefined }, // 'set' | 'ext'
  // Already-built meta cells (["125","4A","6 j"] / ["il y a 1 sem"]). The component
  // joins with " · " and drops empties — it never formats the values itself.
  metaParts: { type: Array, default: () => [] },
  // undefined = no in-lib indicator (data absent from the endpoint); passed as-is
  // to Artwork, which draws the dot only when the value is a real boolean.
  inLib: { type: Boolean, default: undefined },
  // External link (Deezer, …) → root becomes <a target="_blank" rel="noopener">.
  href: { type: String, default: undefined },
  playing: { type: Boolean, default: false },
  skeleton: { type: Boolean, default: false },
})
const emit = defineEmits(['play', 'open'])

// Same cover convention as the other views; no artwork → Artwork placeholder.
const coverSrc = computed(() =>
  props.hasArtwork && props.coverId != null
    ? `/storage/catalog-artworks/${props.coverId}.jpg`
    : undefined,
)

const artistsText = computed(() =>
  props.artists && props.artists.length
    ? props.artists.map((a) => a.name).join(', ')
    : props.artist || '',
)

// Join the parent-built cells; a falsy cell drops out (never a dash).
const metaText = computed(() => (props.metaParts || []).filter(Boolean).join(' · '))

// Rank wins over badge (mutually exclusive by design); rank & "Nouveauté" are
// accent, only "Set" gets the neutral treatment.
const badgeText = computed(() => (props.rank != null ? `#${props.rank}` : props.badge || ''))
const badgeClass = computed(() =>
  props.rank == null && props.badge === 'Set' ? 'dc-badge--set' : 'dc-badge--accent',
)

const isExternal = computed(() => !!props.href && !props.skeleton)
const rootTag = computed(() => (isExternal.value ? 'a' : 'div'))
const rootAttrs = computed(() => {
  if (props.skeleton) return { 'aria-hidden': 'true' }
  return isExternal.value
    ? { href: props.href, target: '_blank', rel: 'noopener' }
    : { role: 'button', tabindex: 0 }
})

// Internal, non-skeleton root only: external navigation is native, a skeleton is inert.
const clickable = computed(() => !props.skeleton && !isExternal.value)
function onRootClick() {
  if (clickable.value) emit('open')
}
function onRootKey(e) {
  if (!clickable.value) return
  if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
    e.preventDefault()
    emit('open')
  }
}
function emitPlay() {
  emit('play')
}
</script>

<style scoped>
.dc-card {
  position: relative;
  display: flex;
  gap: var(--space-25);
  padding: var(--space-2);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  text-decoration: none;
  color: inherit;
  cursor: pointer;
  min-width: 0;
  transition:
    background 0.12s,
    border-color 0.12s;
}
.dc-card:hover {
  background: var(--surface-2);
  border-color: var(--line-2);
}
.dc-card:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.dc-card.playing,
.dc-card.playing:hover {
  background: var(--accent-wash);
}

/* ---- cover + play ---- */
.dc-cover {
  position: relative;
  width: 64px;
  height: 64px;
  flex-shrink: 0;
}
/* Full-cover tap target; the 32px disc is centered inside. Scrim stays transparent
   at rest (the cover breathes), fades in on hover/lecture for icon legibility. */
.dc-play {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  border-radius: var(--r-md);
  background: transparent;
  cursor: pointer;
  opacity: 0;
  transition:
    opacity 0.12s,
    background 0.12s;
}
.dc-card:hover .dc-play,
.dc-play.playing {
  opacity: 1;
  background: var(--overlay-soft);
}
.dc-play-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--surface);
  border: 1px solid var(--line-2);
  color: var(--ink);
  transition:
    background 0.12s,
    border-color 0.12s,
    color 0.12s;
}
.dc-play.playing .dc-play-btn {
  background: var(--accent);
  border-color: transparent;
  color: var(--on-accent);
}
.dc-play-icon {
  width: 15px;
  height: 15px;
}

/* ---- body ---- */
.dc-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
  justify-content: center;
  min-width: 0;
  flex: 1;
}
.dc-titleline {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  min-width: 0;
}
.dc-badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border-radius: var(--r-pill);
  font: 600 var(--fs-nano) var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.dc-badge--accent {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.dc-badge--set {
  background: var(--surface-2);
  color: var(--ink-2);
}
.dc-badge-icon {
  width: 10px;
  height: 10px;
}
.dc-title {
  font: 600 var(--fs-title) var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dc-artist {
  font: 400 var(--fs-sm) var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dc-meta {
  margin-top: 1px;
  font: 500 var(--fs-xs) var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ---- skeleton ---- */
.dc-card--skeleton {
  cursor: default;
}
.dc-sk-cover {
  width: 64px;
  height: 64px;
  flex-shrink: 0;
  border-radius: var(--r-sm);
  background: var(--surface-3);
  animation: dc-pulse 1.4s ease-in-out infinite;
}
.dc-sk-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-15);
  justify-content: center;
  min-width: 0;
}
.dc-sk-line {
  border-radius: 5px;
  animation: dc-pulse 1.4s ease-in-out infinite;
}
.dc-sk-line--1 {
  height: 11px;
  width: 70%;
  background: var(--surface-3);
}
.dc-sk-line--2 {
  height: 9px;
  width: 45%;
  background: var(--surface-2);
}
.dc-sk-line--3 {
  height: 9px;
  width: 60%;
  background: var(--surface-2);
}
@keyframes dc-pulse {
  0%,
  100% {
    opacity: 0.4;
  }
  50% {
    opacity: 0.9;
  }
}

/* No hover on touch → play stays visible on narrow containers (page container query). */
@container (max-width: 640px) {
  .dc-play {
    opacity: 1;
  }
}
</style>

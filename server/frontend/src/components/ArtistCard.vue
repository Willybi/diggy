<template>
  <RouterLink :to="`/artist/${artist.id}`" class="artist-card" :style="cardStyle">
    <div class="ac-art">
      <div class="ac-scrim"></div>

      <span v-if="artist.avg_rating != null" class="ac-rating">
        <svg viewBox="0 0 24 24"><path d="M12 2.5l2.9 6.2 6.6.7-4.9 4.5 1.4 6.6L12 18.6 6 21l1.4-6.6L2.5 9.4l6.6-.7z"/></svg>
        {{ artist.avg_rating.toFixed(1) }}
      </span>

      <span v-if="artist.nb_lib > 0" class="ac-lib">
        <span class="libdot"></span>{{ artist.nb_lib }} en bib
      </span>

      <div class="ac-avatar">
        <img
          v-if="artist.has_artwork && !imgBroken"
          :src="`/storage/artist-artworks/${artist.id}.jpg`"
          :alt="artist.name"
          loading="lazy"
          @error="imgBroken = true"
        />
        <template v-else>{{ initials }}</template>
      </div>

      <button class="ac-play" :class="{ 'ac-play--playing': isPlaying }" aria-label="Lecture" @click.prevent.stop="onPlay">
        <svg v-if="!isPlaying" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
        <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>
      </button>
    </div>

    <div class="ac-body">
      <div class="ac-name">{{ artist.name }}</div>
      <div v-if="displayGenres.length" class="ac-genres">
        <StyleTag v-for="g in displayGenres" :key="g" :name="g" />
      </div>
      <div class="ac-stats">
        <div class="ac-stat">
          <span class="k">Catalog</span>
          <span class="v">{{ artist.nb_catalog }}</span>
        </div>
        <div class="ac-stat">
          <span class="k">In Lib</span>
          <span v-if="artist.nb_lib" class="v">{{ artist.nb_lib }}</span>
          <span v-else class="v-empty">&mdash;</span>
        </div>
        <div class="ac-stat liked">
          <span class="k">Liked</span>
          <template v-if="artist.nb_liked">
            <span class="v">
              <svg viewBox="0 0 24 24"><path d="M12 20.5l-1.5-1.35C5.2 14.5 2 11.6 2 8.05 2 5.6 3.9 3.7 6.35 3.7c1.4 0 2.75.66 3.65 1.7.9-1.04 2.25-1.7 3.65-1.7C16.1 3.7 18 5.6 18 8.05c0 3.55-3.2 6.45-8.5 11.1z"/></svg>
              {{ artist.nb_liked }}
            </span>
          </template>
          <span v-else class="v-empty">&mdash;</span>
        </div>
      </div>
    </div>
  </RouterLink>
</template>

<script setup>
import { computed, ref } from 'vue'
import { styleTone } from '../composables/useStyleMap.js'
import { useAudioPlayer } from '../stores/audioPlayer'
import StyleTag from './StyleTag.vue'

const props = defineProps({
  artist: { type: Object, required: true },
})

const player = useAudioPlayer()
const isPlaying = computed(() => player.artistPlaying === props.artist.id)

function onPlay() {
  if (isPlaying.value) {
    player.close()
  } else {
    player.playRandomArtist(props.artist.id)
  }
}

const imgBroken = ref(false)

const tone = computed(() => {
  if (!props.artist.genres?.length) return { family: 'misc', hue: null }
  return styleTone(props.artist.genres[0])
})

const cardStyle = computed(() =>
  tone.value.hue != null ? { '--th': tone.value.hue } : undefined
)

const initials = computed(() => {
  const words = props.artist.name.trim().split(/[\s\-_./]+/).filter(w => /[a-zA-Z0-9]/.test(w))
  if (!words.length) return '?'
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[words.length - 1][0]).toUpperCase()
})

const displayGenres = computed(() => (props.artist.genres || []).slice(0, 2))
</script>

<style scoped>
.artist-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  text-decoration: none;
  color: inherit;
  transition: box-shadow .18s ease, transform .18s ease, border-color .18s ease;
}
.artist-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
  border-color: var(--line-2);
}

/* ---- art zone ---- */
.ac-art {
  --art-l: 0.920;
  --art-c: 0.054;
  position: relative;
  height: 132px;
  background: oklch(var(--art-l) var(--art-c) var(--th, 42));
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
[data-theme="dark"] .ac-art {
  --art-l: 0.258;
  --art-c: 0.068;
}
.ac-art::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: repeating-linear-gradient(
    135deg,
    transparent 0 9px,
    oklch(0 0 0 / .038) 9px 10px
  );
  pointer-events: none;
}
.ac-scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, oklch(0.14 0.018 70 / .24) 0%, transparent 56%);
  pointer-events: none;
}

/* ---- avatar ---- */
.ac-avatar {
  width: 84px;
  height: 84px;
  border-radius: 50%;
  border: 3px solid var(--surface);
  background: oklch(calc(var(--art-l) - 0.072) calc(var(--art-c) + 0.022) var(--th, 42));
  display: flex;
  align-items: center;
  justify-content: center;
  font: 700 27px/1 var(--font-ui);
  letter-spacing: -.5px;
  color: oklch(0.40 0.130 var(--th, 42));
  box-shadow: 0 4px 18px oklch(0.14 0.018 70 / .24), 0 1px 4px oklch(0.14 0.018 70 / .16);
  position: relative;
  z-index: 1;
  flex: none;
  overflow: hidden;
  transition: transform .18s ease;
  user-select: none;
}
[data-theme="dark"] .ac-avatar {
  border-color: oklch(0.270 0.015 262);
  color: oklch(0.76 0.088 var(--th, 42));
}
.ac-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.artist-card:hover .ac-avatar {
  transform: scale(1.07);
}

/* ---- rating badge ---- */
.ac-rating {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 4px 8px 4px 7px;
  font: 700 11.5px/1 var(--font-mono);
  color: var(--accent-ink);
  box-shadow: var(--shadow-sm);
  pointer-events: none;
}
.ac-rating svg {
  width: 11px;
  height: 11px;
  fill: var(--accent);
  flex: none;
}

/* ---- in-lib badge ---- */
.ac-lib {
  position: absolute;
  bottom: 10px;
  left: 10px;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 5px;
  font: 600 10.5px/1 var(--font-mono);
  color: var(--pos-ink);
  background: var(--surface);
  padding: 5px 8px 5px 7px;
  border-radius: 999px;
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--line);
  pointer-events: none;
}
.libdot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--pos);
  flex: none;
}

/* ---- play button ---- */
.ac-play {
  position: absolute;
  right: 10px;
  bottom: 10px;
  z-index: 3;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 0;
  background: var(--accent);
  color: var(--on-accent);
  display: grid;
  place-items: center;
  cursor: pointer;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity .18s ease, transform .18s ease, background .14s;
  box-shadow: var(--shadow-md);
}
.ac-play svg { width: 14px; height: 14px; margin-left: 2px; }
.artist-card:hover .ac-play { opacity: 1; transform: none; }
.ac-play--playing { opacity: 1; transform: none; }
.ac-play:hover { background: var(--accent-hover); }

/* ---- body ---- */
.ac-body {
  padding: 13px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  flex: 1;
}
.ac-name {
  font: 600 15px/1.2 var(--font-ui);
  letter-spacing: -.2px;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ac-genres {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  min-height: 22px;
}

/* ---- stats ---- */
.ac-stats {
  display: flex;
  margin-top: auto;
  border-top: 1px solid var(--line);
  padding-top: 10px;
}
.ac-stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
  align-items: center;
}
.ac-stat + .ac-stat { border-left: 1px solid var(--line); }
.ac-stat .k {
  font: 600 8.5px/1 var(--font-mono);
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.ac-stat .v {
  font: 600 14px/1 var(--font-mono);
  color: var(--ink);
}
.ac-stat.liked .v {
  color: var(--pos-ink);
}
.ac-stat.liked .v svg {
  width: 12px;
  height: 12px;
  fill: var(--pos);
  vertical-align: -1px;
  margin-right: 3px;
}
.v-empty {
  font: 500 13px/1 var(--font-mono);
  color: var(--ink-3);
}
</style>

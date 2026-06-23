<template>
  <RouterLink
    :to="`/style/${encodeURIComponent(genre.name)}`"
    class="genre-card"
    :style="hue != null ? { '--th': hue } : undefined"
  >
    <!-- Artwork zone: always 4 slots — image or tinted placeholder -->
    <div class="gc-art" :class="{ misc: tone.family === 'misc' }">
      <div v-for="(slot, i) in fourSlots" :key="i" class="gc-tile">
        <img
          v-if="slot"
          class="gc-cover"
          :src="slot"
          alt=""
          loading="lazy"
          @error="onCoverError"
        />
      </div>
      <div class="gc-scrim"></div>

      <!-- Badge in-lib -->
      <span v-if="genre.inLibCount > 0" class="gc-lib">
        <span class="libdot"></span>{{ fmtNum(genre.inLibCount) }} en bib
      </span>

      <!-- Avatars artistes -->
      <div v-if="genre.artists?.length" class="gc-avatars">
        <img
          v-for="a in genre.artists.slice(0, 3)"
          :key="a.id"
          class="av"
          :src="a.image"
          :alt="a.name"
          loading="lazy"
          @error="onAvatarError"
        />
        <span v-if="genre.artistCount > 3" class="more">+{{ fmtNum(genre.artistCount - 3) }}</span>
      </div>

      <!-- Play button (hover reveal) -->
      <button class="gc-play" aria-label="Lecture" @click.prevent>
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
      </button>
    </div>

    <!-- Body -->
    <div class="gc-body">
      <div class="gc-titlerow">
        <span class="gc-dot" :class="{ misc: tone.family === 'misc' }"></span>
        <span class="gc-title" :class="{ misc: tone.family === 'misc' }">{{ genre.name }}</span>
        <span class="gc-fam">{{ familyLabel }}</span>
      </div>
      <div class="gc-stats">
        <div class="gc-stat">
          <span class="k">Tracks</span>
          <span class="v">{{ fmtNum(genre.trackCount) }}</span>
        </div>
        <div class="gc-stat">
          <span class="k">Artistes</span>
          <span class="v">{{ fmtNum(genre.artistCount) }}</span>
        </div>
        <div class="gc-stat bpm">
          <span class="k">BPM</span>
          <span class="v">{{ genre.bpmLo }}–{{ genre.bpmHi }}</span>
        </div>
      </div>
    </div>
  </RouterLink>
</template>

<script setup>
import { computed } from 'vue'
import { styleTone, FAMILY_LABELS } from '../composables/useStyleMap.js'

const props = defineProps({
  genre: { type: Object, required: true },
})

const tone = computed(() => styleTone(props.genre.name))
const hue = computed(() => tone.value.hue)
const familyLabel = computed(() => FAMILY_LABELS[props.genre.family] || FAMILY_LABELS.misc)

// 4 slots: use available covers, null = tinted placeholder (no repeating)
const fourSlots = computed(() => {
  const aw = props.genre.artworks || []
  return [aw[0] || null, aw[1] || null, aw[2] || null, aw[3] || null]
})

function fmtNum(n) {
  return (n || 0).toLocaleString('fr-FR').replace(/\u202f/g, ' ')
}

function onCoverError(e) {
  e.target.remove()
}

function onAvatarError(e) {
  e.target.style.display = 'none'
}
</script>

<style scoped>
.genre-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  transition: box-shadow .18s ease, transform .18s ease, border-color .18s ease;
  text-decoration: none;
  color: inherit;
}
.genre-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
  border-color: var(--line-2);
}

/* ── Artwork zone — 2×2 square cells, fixed height ── */
.gc-art {
  --art-l: 0.910;
  --art-c: 0.052;
  position: relative;
  height: 130px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}
.gc-art.misc { --art-l: 0.880; --art-c: 0.008; --th: 70; }

/* Each tile = grid cell, contains either a cover <img> or is a bare placeholder */
.gc-tile {
  position: relative;
  overflow: hidden;
  min-height: 0;
  background-color: oklch(var(--art-l) var(--art-c) var(--th));
  background-image: repeating-linear-gradient(135deg, oklch(1 0 0 / .10) 0 1px, transparent 1px 9px);
}
.gc-tile:nth-child(2) { background-color: oklch(calc(var(--art-l) - 0.060) var(--art-c) var(--th)); }
.gc-tile:nth-child(3) { background-color: oklch(calc(var(--art-l) - 0.030) calc(var(--art-c) + 0.018) var(--th)); }
.gc-tile:nth-child(4) { background-color: oklch(calc(var(--art-l) + 0.030) var(--art-c) var(--th)); }

/* Cover image fills its tile cell — crop, never stretch */
.gc-cover {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  display: block;
  background: var(--surface-2);
}

.gc-scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, oklch(0.20 0.02 70 / .42) 0%, transparent 46%);
  pointer-events: none;
}

/* Badge in-lib */
.gc-lib {
  position: absolute;
  top: 10px;
  right: 10px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font: 600 10.5px/1 var(--font-mono);
  color: var(--pos-ink);
  background: var(--surface);
  padding: 5px 8px 5px 7px;
  border-radius: 999px;
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--line);
}
.libdot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--pos);
  flex: none;
}

/* Avatars */
.gc-avatars {
  position: absolute;
  left: 12px;
  bottom: 11px;
  display: flex;
  align-items: center;
}
.av {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  flex: none;
  margin-left: -9px;
  border: 2px solid oklch(0.99 0.004 92);
  object-fit: cover;
  box-shadow: var(--shadow-sm);
  background-color: oklch(var(--art-l) calc(var(--art-c) + 0.02) var(--th));
}
.av:first-child { margin-left: 0; }
[data-theme="dark"] .av { border-color: oklch(0.28 0.012 262); }
.more {
  margin-left: 7px;
  font: 600 11px/1 var(--font-mono);
  color: oklch(0.99 0.004 92);
  text-shadow: 0 1px 3px oklch(0.20 0.02 70 / .6);
}

/* Play button */
.gc-play {
  position: absolute;
  right: 11px;
  bottom: 11px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 0;
  background: var(--accent);
  color: var(--on-accent);
  display: grid;
  place-items: center;
  cursor: pointer;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity .18s ease, transform .18s ease, background .15s;
  box-shadow: var(--shadow-md);
}
.gc-play svg { width: 17px; height: 17px; margin-left: 2px; }
.genre-card:hover .gc-play { opacity: 1; transform: none; }
.gc-play:hover { background: var(--accent-hover); }

/* ── Body ── */
.gc-body {
  padding: 13px 16px 15px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}
.gc-titlerow {
  display: flex;
  align-items: baseline;
  gap: 9px;
  min-width: 0;
}
.gc-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
  align-self: center;
  background: oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th));
  box-shadow: 0 0 0 1px oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th) / .28);
}
.gc-dot.misc { background: var(--ink-3); }
.gc-title {
  font: 600 17px var(--font-ui);
  letter-spacing: -.2px;
  color: oklch(var(--tag-fg-l) var(--tag-fg-c) var(--th));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gc-title.misc { color: var(--ink-2); }
.gc-fam {
  margin-left: auto;
  font: 500 9.5px/1 var(--font-mono);
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-3);
  white-space: nowrap;
  flex: none;
}

/* ── Stats ── */
.gc-stats {
  display: flex;
  margin-top: auto;
  border-top: 1px solid var(--line);
  padding-top: 11px;
}
.gc-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-right: 14px;
}
.gc-stat + .gc-stat {
  padding-left: 14px;
  border-left: 1px solid var(--line);
}
.gc-stat .k {
  font: 600 9px/1 var(--font-mono);
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-3);
  white-space: nowrap;
}
.gc-stat .v {
  font: 600 14.5px/1 var(--font-mono);
  color: var(--ink);
  white-space: nowrap;
}
.gc-stat.bpm .v {
  color: var(--ink-2);
  font-size: 13px;
}
</style>

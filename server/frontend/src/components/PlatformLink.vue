<template>
  <a
    v-if="variant === 'button'"
    class="plink plink--btn"
    :class="`plink--${size}`"
    :href="href"
    target="_blank"
    rel="noopener"
    :aria-label="`Voir sur ${name}`"
  >
    <svg class="plink-logo" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path :d="path" />
    </svg>
  </a>
  <span
    v-else
    class="plink plink--glyph"
    role="img"
    :title="`Détecté sur ${name}`"
    :aria-label="`Détecté sur ${name}`"
  >
    <svg class="plink-logo" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path :d="path" />
    </svg>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  platform: { type: String, required: true }, // beatport|deezer|tidal|soundcloud|youtube|spotify|trackid|1001tl
  href: { type: String, default: '' },
  size: { type: String, default: 'md' }, // 'md' 38px · 'sm' 30px
  variant: { type: String, default: 'button' }, // 'button' | 'glyph'
})

// TODO logos officiels — tracés placeholders simplifiés, à remplacer par les SVG officiels monochromes (un seul fichier à toucher)
const LOGO_PATHS = {
  beatport: 'M4 9h2.5v6H4zM8.75 5h2.5v14h-2.5zM13.5 8h2.5v8h-2.5zM18.25 6h2.5v12h-2.5z',
  deezer: 'M3 14h3.5v4H3zM8.25 10h3.5v8h-3.5zM13.5 6h3.5v12h-3.5zM18.75 12H22v6h-3.25z',
  tidal: 'M6 6l2.5 2.5L6 11 3.5 8.5zM18 6l2.5 2.5L18 11l-2.5-2.5zM12 12l2.5 2.5L12 17l-2.5-2.5z',
  soundcloud:
    'M4 16h1.5v-5H4zM7 16h1.5V8H7zM10 16h1.5V6H10zM13 16h7a3 3 0 0 0 0-6 4.5 4.5 0 0 0-8.7-1.2A2.5 2.5 0 0 0 13 13.5z',
  youtube:
    'M2 7.5A3.5 3.5 0 0 1 5.5 4h13A3.5 3.5 0 0 1 22 7.5v9A3.5 3.5 0 0 1 18.5 20h-13A3.5 3.5 0 0 1 2 16.5zM10 8.5v7l6-3.5z',
  spotify:
    'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm4.6 14.4a.75.75 0 0 1-1 .25c-2.7-1.65-6.1-2-10.1-1.1a.75.75 0 1 1-.33-1.46c4.3-.97 8.06-.57 11.06 1.26.36.22.47.7.37 1.05zm.05-3.4a.9.9 0 0 1-1.24.3c-3-1.85-7.6-2.4-11.1-1.33a.9.9 0 1 1-.52-1.72c4-1.2 9.05-.6 12.5 1.5.42.26.56.82.36 1.25z',
  trackid:
    'M10 3a7 7 0 0 1 5.5 11.3l5 5-1.7 1.7-5-5A7 7 0 1 1 10 3zm0 2.4a4.6 4.6 0 1 0 0 9.2 4.6 4.6 0 0 0 0-9.2z',
  '1001tl': 'M3.5 6h17v2.4h-17zM3.5 10.8h17v2.4h-17zM3.5 15.6h17V18h-17z',
}

const PLATFORM_NAMES = {
  beatport: 'Beatport',
  deezer: 'Deezer',
  tidal: 'TIDAL',
  soundcloud: 'SoundCloud',
  youtube: 'YouTube',
  spotify: 'Spotify',
  trackid: 'TrackID',
  '1001tl': '1001Tracklists',
}

const path = computed(() => LOGO_PATHS[props.platform] || '')
const name = computed(() => PLATFORM_NAMES[props.platform] || props.platform)
</script>

<style scoped>
.plink {
  display: inline-grid;
  place-items: center;
  flex: none;
  color: var(--ink-2);
}

/* button — square .btn-like tile, clickable */
.plink--btn {
  aspect-ratio: 1;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  transition:
    background 0.12s,
    color 0.12s;
}
.plink--md {
  width: 38px;
}
.plink--sm {
  width: 30px;
}
.plink--btn:hover {
  background: var(--surface-2);
  color: var(--ink);
}
.plink--btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.plink--btn .plink-logo {
  width: 16px;
  height: 16px;
}

/* glyph — logo only, non-interactive source marker */
.plink--glyph .plink-logo {
  width: 13px;
  height: 13px;
}
</style>

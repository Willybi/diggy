<template>
  <svg
    class="admin-icon"
    :class="{ 'admin-icon--spin': name === 'arc' }"
    :style="sizeStyle"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <component :is="el.t" v-for="(el, i) in shapes" :key="i" v-bind="el.a" />
  </svg>
</template>

<script setup>
import { computed } from 'vue'

// ── Jeu d'icônes admin-local (D2) : 10 glyphes SVG inline `currentColor`,
// stroke fin, jamais de fill, jamais de couleur propre — la couleur vient du
// contexte. Chaque entrée est une liste d'éléments { t: tag, a: attrs } rendus
// dans le namespace SVG (viewBox 24×24, tracés façon trait). Zéro emoji. ──
const ICONS = {
  check: [{ t: 'path', a: { d: 'M20 6 9 17l-5-5' } }],
  // Flèche de retour : compteur neutre (ignorés, non trouvés, abandonnés…).
  skip: [
    { t: 'path', a: { d: 'M9 14 4 9l5-5' } },
    { t: 'path', a: { d: 'M4 9h11a4 4 0 0 1 4 4v3' } },
  ],
  'alert-triangle': [
    {
      t: 'path',
      a: {
        d: 'M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z',
      },
    },
    { t: 'path', a: { d: 'M12 9v4' } },
    { t: 'path', a: { d: 'M12 17h.01' } },
  ],
  // Spinner : arc ouvert (dasharray) mis en rotation via .admin-icon--spin.
  arc: [{ t: 'circle', a: { cx: 12, cy: 12, r: 9, 'stroke-dasharray': '40 60' } }],
  'link-off': [
    { t: 'path', a: { d: 'M9 17H7A5 5 0 0 1 7 7h2' } },
    { t: 'path', a: { d: 'M15 7h2a5 5 0 0 1 0 10h-2' } },
    { t: 'path', a: { d: 'M8 12h8' } },
    { t: 'path', a: { d: 'm3 3 18 18' } },
  ],
  flag: [
    { t: 'path', a: { d: 'M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z' } },
    { t: 'path', a: { d: 'M4 22v-7' } },
  ],
  // Découper une chaîne d'artiste (cisaille).
  split: [
    { t: 'circle', a: { cx: 6, cy: 6, r: 3 } },
    { t: 'circle', a: { cx: 6, cy: 18, r: 3 } },
    { t: 'path', a: { d: 'M20 4 8.12 15.88' } },
    { t: 'path', a: { d: 'M14.47 14.48 20 20' } },
    { t: 'path', a: { d: 'M8.12 8.12 12 12' } },
  ],
  search: [
    { t: 'circle', a: { cx: 11, cy: 11, r: 8 } },
    { t: 'path', a: { d: 'm21 21-4.3-4.3' } },
  ],
  trash: [
    { t: 'path', a: { d: 'M3 6h18' } },
    {
      t: 'path',
      a: { d: 'M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2' },
    },
    { t: 'path', a: { d: 'M10 11v6' } },
    { t: 'path', a: { d: 'M14 11v6' } },
  ],
  chevron: [{ t: 'path', a: { d: 'm6 9 6 6 6-6' } }],
  // Rafraîchir / actualiser : arc circulaire + tête de flèche (tracé cohérent
  // avec le refresh d'AdminOverview).
  refresh: [
    { t: 'path', a: { d: 'M21 12a9 9 0 1 1-2.64-6.36' } },
    { t: 'path', a: { d: 'M21 3v6h-6' } },
  ],
  // Croix : absent / non trouvé (signal Deezer « aucun match », D13).
  x: [
    { t: 'path', a: { d: 'M18 6 6 18' } },
    { t: 'path', a: { d: 'm6 6 12 12' } },
  ],
}

const props = defineProps({
  name: {
    type: String,
    required: true,
    validator: (v) =>
      [
        'check',
        'skip',
        'alert-triangle',
        'arc',
        'link-off',
        'flag',
        'split',
        'search',
        'trash',
        'chevron',
        'refresh',
        'x',
      ].includes(v),
  },
  // Taille en px. Omise → largeur/hauteur héritées du CSS (défaut 1em).
  size: { type: [Number, String], default: null },
})

const shapes = computed(() => ICONS[props.name] || [])
const sizeStyle = computed(() =>
  props.size == null ? null : { width: `${props.size}px`, height: `${props.size}px` },
)
</script>

<style scoped>
.admin-icon {
  display: inline-block;
  flex: none;
  width: 1em;
  height: 1em;
  vertical-align: middle;
}
/* Rotation réutilisable (@keyframes spin global, assets/page.css). */
.admin-icon--spin {
  animation: spin 0.9s linear infinite;
}
</style>

/* ============================================================
   DIGGY — Genre → colour map  ·  v2 "taxonomy"
   ------------------------------------------------------------
   6 piliers + Autres. Chaque pilier = UN hue (tokens --hue-*).
   Le hue d'un genre = le hue de sa RACINE taxonomique
   (résolu côté API via genre_mappings → ancestors → ROOT_TO_PILLAR).
   La PROFONDEUR (0..3) désature le chip — ne touche JAMAIS le hue.
   Roue : "Évocateur". Collision : Option A (tolérant).
   ============================================================ */

export const DEPTH_MAX = 3

export const PILLARS = {
  house: { hue: 72, label: 'House', vibe: 'Groovy · club · disco roots' },
  techno: { hue: 242, label: 'Techno', vibe: 'Brut · industriel · hypnotique' },
  trance: { hue: 292, label: 'Trance', vibe: 'Euphorique · psyché · éthéré' },
  dnb: { hue: 162, label: 'Drum & Bass', vibe: 'Rapide · jungle · liquide' },
  hardcore: { hue: 28, label: 'Hardcore', vibe: 'Dur · gabber · distorsion' },
  harddance: { hue: 338, label: 'Hard Dance', vibe: 'Hardstyle · jumpstyle · rave' },
  autres: { hue: null, label: 'Autres', vibe: 'Inclassable' },
}

export const PILLAR_ORDER = ['house', 'techno', 'trance', 'dnb', 'hardcore', 'harddance', 'autres']

export const PILLAR_LABELS = Object.fromEntries(
  Object.entries(PILLARS).map(([k, v]) => [k, v.label]),
)

/* CSS-safe slug: 'Classic/Min. Techno' -> 'classic-min-techno' */
export const slug = (name) =>
  String(name)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')

/**
 * Tonalité d'un genre.
 * @param {{pillar:string, depth?:number}} g  pilier + profondeur (de l'API)
 * @returns {{pillar:string, hue:number|null, depth:number}}
 */
export function styleTone({ pillar, depth = 0 } = {}) {
  const key = PILLARS[pillar] ? pillar : 'autres'
  return {
    pillar: key,
    hue: PILLARS[key].hue,
    depth: Math.max(0, Math.min(DEPTH_MAX, depth | 0)),
  }
}

/**
 * Attributs prêts à binder sur <StyleTag>, dot mosaïque, etc.
 *   <span class="style-tag" v-bind="tagAttrs(tone)">…</span>
 * Le hue est lu côté CSS via [data-fam] -> var(--hue-*) ; Autres
 * passe en chroma 0 par le même sélecteur. On ne pousse que --d.
 */
export function tagAttrs(tone) {
  return { 'data-fam': tone.pillar, style: `--d:${tone.depth}` }
}

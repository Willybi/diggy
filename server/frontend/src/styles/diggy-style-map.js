/* ============================================================
   DIGGY — Genre -> colour mapping  ·  v3.0
   ------------------------------------------------------------
   Palette BORNEE a 5 tons (anti-rainbow) :
     House  260 (violet)  — groovy / club
     Techno 320 (magenta) — brut / hypnotique
     Trance 352 (rose)    — psyche / euphorique
     Other   42 (ambre)   — vrais genres hors-piste
     Misc   null (gris)   — non-genres / bruit

   Normalisation par slug : "Nu-Disco" et "Nu Disco / Disco"
   tombent sur le meme slug -> meme couleur, toujours.

   Tout genre non mappe tombe en Misc (gris neutre).
   Pas de fallback hash — si un genre manque, on l'ajoute ici.
   ============================================================ */

/* CSS-safe slug: 'Classic/Min. Techno' -> 'classic-min-techno' */
export const slug = (name) =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

/* ── Palette par famille ─────────────────────────────────────── */
const FAMILY_HUES = {
  house:  260,
  techno: 320,
  trance: 352,
  other:   42,
  misc:   null,
}

/* ── Mapping exhaustif : slug -> famille ─────────────────────── */
const SLUG_FAMILY = {}
function register(family, names) {
  names.forEach(n => { SLUG_FAMILY[slug(n)] = family })
}

register('house', [
  'House', 'Deep House', 'Tech House', 'Afro House', 'Bass House',
  'Progressive House', 'Jackin House', 'Funky House', 'Soulful House',
  'Organic House', 'Organic House / Downtempo', 'Afro / Organic House',
  'Nu Disco / Disco', 'Nu-Disco', 'Nu Disco', 'Indie Dance',
  'Melodic House', 'French Touch', 'UK House', 'UK Garage', 'UK Garage / Bassline',
  'Downtempo', 'Minimal / Deep Tech',
])

register('techno', [
  'Techno (Peak Time / Driving)', 'Techno (Peak Time)', 'Techno (Raw / Deep / Hypnotic)',
  'Hard Techno', 'Melodic House & Techno', 'Melodic Techno', 'Minimal Techno',
  'Electro (Classic / Detroit / Modern)', 'Electro Brut', 'Electro brut',
  'Classic/Min. Techno', 'Hard/Dark Techno', 'Trance Techno',
])

register('trance', [
  'Trance (Main Floor)', 'Trance (Raw / Deep / Hypnotic)',
  'Psy-Trance', 'Psytrance',
  'Hard Dance / Hardcore / Neo Rave', 'Hard Dance',
])

register('other', [
  'Drum & Bass', 'Breaks / Breakbeat / UK Bass', 'Electronica',
  'Rock', 'Hip-Hop', 'R&B', 'Pop', 'Funk / Soul', 'Funk-Soul',
  'Bass', 'Country', 'Latin', 'Latin Electronic',
  '140 / Deep Dubstep / Grime', 'Dubstep', 'Trap / Future Bass',
  'Bass / Club', 'Ambient / Experimental', 'African', 'Caribbean',
])

register('misc', [
  'DJ Tools / Acapellas', 'DJ Tools / Acape', 'DJ Edits',
  'Mainstage', 'Dance / Pop', 'Misc. Tracks',
])


/* ── Labels famille (source unique) ────────────────────────── */
export const FAMILY_LABELS = {
  house: 'House', techno: 'Techno', trance: 'Trance',
  other: 'Autre', misc: 'Autre',
}

/* ── API publique ──────────────────────────────────────────── */

export function styleTone(name) {
  const family = SLUG_FAMILY[slug(name)]
  if (family === 'misc' || family === undefined) {
    return { family: 'misc', hue: null, shade: 0 }
  }
  return { family, hue: FAMILY_HUES[family], shade: 0 }
}

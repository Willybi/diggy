/* ============================================================
   DIGGY — Genre → colour mapping  ·  v2.0
   ------------------------------------------------------------
   Architecture 3 couches :
     1. GENRE_FAMILIES  — mapping genre → famille (DONNEE, remplacable)
     2. FAMILY_HUES     — teinte par famille (PALETTE, stable)
     3. stableHue()     — fallback hash pour genres non mappes (MECANIQUE)

   Futur : remplacer couche 1 par un fetch API ou table DB,
   sans toucher couches 2 et 3.
   ============================================================ */

/* ── Couche 1 : mapping genre → famille ────────────────────── */
const GENRE_FAMILIES = {
  'House':                          'house',
  'Deep House':                     'house',
  'Tech House':                     'house',
  'Afro House':                     'house',
  'Bass House':                     'house',
  'UK Garage / Bassline':           'house',
  'Progressive House':              'house',
  'Mainstage':                      'misc',
  'Jackin House':                   'house',
  'Funky House':                    'house',
  'Soulful House':                  'house',
  'Organic House / Downtempo':      'house',

  'Techno (Peak Time / Driving)':   'techno',
  'Techno (Raw / Deep / Hypnotic)': 'techno',
  'Hard Techno':                    'techno',
  'Minimal / Deep Tech':            'techno',
  'Melodic House & Techno':         'techno',

  'Trance (Main Floor)':            'trance',
  'Hard Dance / Hardcore / Neo Rave': 'trance',
  'Psy-Trance':                     'trance',

  'Electronica':                    'electro',
  'Breaks / Breakbeat / UK Bass':   'electro',
  'Drum & Bass':                    'electro',
  'Indie Dance':                    'electro',

  'Dance / Pop':                    'misc',
  'Pop':                            'pop',
  'Nu Disco / Disco':               'pop',

  'DJ Tools / Acape':               'misc',
  'Misc. Tracks':                   'misc',

  /* Legacy styles from Rekordbox tags */
  'Downtempo':                      'house',
  'Nu Disco':                       'pop',
  'UK House':                       'house',
  'French Touch':                   'house',
  'UK Garage':                      'house',
  'Electro brut':                   'techno',
  'Melodic Techno':                 'techno',
  'Classic/Min. Techno':            'techno',
  'Hard/Dark Techno':               'techno',
  'Psytrance':                      'trance',
  'Trance Techno':                  'trance',
}

/* ── Couche 2 : palette par famille ────────────────────────── */
const FAMILY_HUES = {
  house:   268,
  techno:  312,
  trance:  352,
  electro: 180,
  pop:      42,
  misc:    null,
}

/* ── Couche 3 : fallback hash deterministe ─────────────────── */
function stableHue(name) {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0
  }
  return ((hash % 360) + 360) % 360
}

/* ── API publique ──────────────────────────────────────────── */

export const slug = (name) =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

export function styleTone(name) {
  const family = GENRE_FAMILIES[name]
  if (family === 'misc') return { family: 'misc', hue: null, shade: 0 }
  if (family && FAMILY_HUES[family] != null) {
    return { family, hue: FAMILY_HUES[family], shade: 0 }
  }
  return { family: null, hue: stableHue(name), shade: 0 }
}

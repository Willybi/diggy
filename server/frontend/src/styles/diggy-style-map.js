/* ============================================================
   DIGGY — Style → colour family map  ·  v1.2
   ------------------------------------------------------------
   Source de vérité pour les familles musicales et leurs styles.
   Ajouter un style = l'ajouter à la fin du tableau de sa famille.

   v1.2 — taxonomie réelle (House / Techno / Trance / Misc),
   offset & shade étendus à 7 membres, slug() durci.
   ============================================================ */

export const FAMILIES = {
  House:  { baseHue: 268, label: 'Groovy · club' },
  Techno: { baseHue: 312, label: 'Brut · hypnotique' },
  Trance: { baseHue: 352, label: 'Psyché · euphorique' },
  Misc:   { baseHue: 42,  label: 'Inclassable' },
}

const MEMBER_OFFSET = [-4, 5, -10, 11, -15, 15, 0]
const MEMBER_SHADE  = [0, 0.018, 0.036, 0.054, 0.012, 0.030, 0.048]

export const FAMILY_MEMBERS = {
  House:  ['Downtempo', 'Nu Disco', 'Deep House', 'UK House', 'French Touch', 'Tech House', 'UK Garage'],
  Techno: ['Electro brut', 'Melodic Techno', 'Classic/Min. Techno', 'Hard/Dark Techno'],
  Trance: ['Psytrance', 'Trance Techno'],
  Misc:   ['Misc. Tracks'],
}

/* Liste blanche complète — utilisée pour filtrer les tags RB internes */
export const KNOWN_STYLES = new Set(Object.values(FAMILY_MEMBERS).flat())

/* CSS-safe slug: 'Classic/Min. Techno' -> 'classic-min-techno' */
export const slug = (name) =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

/** Resolve {family, hue, shade} for any registered style. */
export function styleTone(name) {
  for (const [family, members] of Object.entries(FAMILY_MEMBERS)) {
    const idx = members.indexOf(name)
    if (idx !== -1) {
      return {
        family,
        hue:   FAMILIES[family].baseHue + (MEMBER_OFFSET[idx] || 0),
        shade: MEMBER_SHADE[idx] || 0,
      }
    }
  }
  return { family: null, hue: 0, shade: 0 }
}

export function styleTagClass(name) {
  return `style-tag style-tag--${slug(name)}`
}

export function styleVarsCss() {
  let out = ''
  for (const members of Object.values(FAMILY_MEMBERS)) {
    for (const name of members) {
      const t = styleTone(name)
      out += `--h-${slug(name)}: ${t.hue}; --s-${slug(name)}: ${t.shade};\n`
    }
  }
  return out
}

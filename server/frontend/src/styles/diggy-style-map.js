/* ============================================================
   DIGGY — Style → colour family map  ·  v1
   ------------------------------------------------------------
   Source de vérité pour les familles musicales et leurs styles.
   Ajouter un style = l'ajouter à la fin du tableau de sa famille.
   ============================================================ */

export const FAMILIES = {
  House:  { baseHue: 28,  label: 'Groovy · dancefloor' },
  Techno: { baseHue: 268, label: 'Sombre · industriel' },
  Trance: { baseHue: 312, label: 'Mélodique · hypnotique' },
  Misc:   { baseHue: 92,  label: 'Divers' },
}

const MEMBER_OFFSET = [-6, 4, -10, 8, -4, 12, 6]
const MEMBER_SHADE  = [0, 0.018, 0.036, 0.054, 0.018, 0.036, 0.054]

export const FAMILY_MEMBERS = {
  House:  ['Downtempo', 'Nu Disco', 'Deep House', 'UK House', 'French Touch', 'Tech House', 'UK Garage'],
  Techno: ['Electro brut', 'Melodic Techno', 'Classic/Min. Techno', 'Hard/Dark Techno'],
  Trance: ['Psytrance', 'Trance Techno'],
  Misc:   ['Misc. Tracks'],
}

/* Liste blanche complète — utilisée pour filtrer les tags RB internes */
export const KNOWN_STYLES = new Set(Object.values(FAMILY_MEMBERS).flat())

export const slug = (name) => name.toLowerCase().replace(/[\s./]+/g, '-')

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

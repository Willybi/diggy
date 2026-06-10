/* ============================================================
   DIGGY — Style → colour family map  ·  v1
   ------------------------------------------------------------
   The single source of truth for which style belongs to which
   colour family. Use it to:
     • render a tag's modifier class  -> styleTagClass('Tech House')
     • register the CSS vars for NEW styles you add later
       (so you don't recompute hue offsets by hand)

   Families share a base hue; members get a small hue offset +
   lightness shade by their index, so siblings look related.
   ============================================================ */

export const FAMILIES = {
  House:   { baseHue: 268, label: 'Groovy · club' },
  Melodic: { baseHue: 312, label: 'Profond · hypnotique' },
  Disco:   { baseHue: 352, label: 'Rétro · funky' },
  Roots:   { baseHue: 42,  label: 'Terreux · world' },
};

const MEMBER_OFFSET = [-4, 5, -10, 11];          // hue spread within a family
const MEMBER_SHADE  = [0, 0.018, 0.036, 0.054];  // lightness ladder within a family

/* Ordered members per family. Append new styles to the right
   end of their family array — index drives their variation. */
export const FAMILY_MEMBERS = {
  House:   ['Tech House', 'Deep House'],
  Melodic: ['Melodic Techno', 'Progressive'],
  Disco:   ['Nu Disco', 'Breaks'],
  Roots:   ['Afro House', 'Organic'],
};

export const slug = (name) => name.toLowerCase().replace(/\s+/g, '-');

/** Resolve {family, hue, shade} for any registered style. */
export function styleTone(name) {
  for (const [family, members] of Object.entries(FAMILY_MEMBERS)) {
    const idx = members.indexOf(name);
    if (idx !== -1) {
      return {
        family,
        hue:   FAMILIES[family].baseHue + (MEMBER_OFFSET[idx] || 0),
        shade: MEMBER_SHADE[idx] || 0,
      };
    }
  }
  return { family: null, hue: 0, shade: 0 }; // unknown style -> neutral
}

/** CSS modifier class for a tag, e.g. 'style-tag style-tag--tech-house'. */
export function styleTagClass(name) {
  return `style-tag style-tag--${slug(name)}`;
}

/** Build the `--h-*` / `--s-*` declarations for ALL styles.
   Inject into :root if you add styles and want CSS to know them. */
export function styleVarsCss() {
  let out = '';
  for (const members of Object.values(FAMILY_MEMBERS)) {
    for (const name of members) {
      const t = styleTone(name);
      out += `--h-${slug(name)}: ${t.hue}; --s-${slug(name)}: ${t.shade};\n`;
    }
  }
  return out;
}

/* Inline style fallback (no per-style CSS class needed):
   <span class="style-tag" :style="`--th:${styleTone(s).hue};--ts:${styleTone(s).shade}`"> */

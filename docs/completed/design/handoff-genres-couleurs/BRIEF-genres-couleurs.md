# BRIEF — Refacto couleurs genres (v2 "taxonomy")

> **Statut** : roue **Évocateur** validée · collision **Option A** (tolérant) validée.
> **Pilote de référence** : `Couleurs Genres (pilote).html` (roue/thème/densité dans la barre).

---

## Le modèle en une phrase

6 piliers + Autres → **un hue par pilier** ; un genre prend le hue de sa **racine taxonomique** ; sa **profondeur** dans l'arbre **désature** le chip, sans jamais bouger le hue.

On abandonne le modèle v1 (4 familles + `MEMBER_OFFSET`/`MEMBER_SHADE` qui faisait *dériver la teinte* des sous-genres — d'où des siblings qui ne se ressemblaient plus).

---

## Hues (roue Évocateur)

| Pilier | hue | Vibe |
|---|---|---|
| House | **72** | groovy · club · disco |
| Techno | **242** | brut · industriel · hypnotique |
| Trance | **292** | euphorique · psyché · éthéré |
| Drum & Bass | **162** | rapide · jungle · liquide |
| Hardcore | **28** | dur · gabber · distorsion |
| Hard Dance | **338** | hardstyle · jumpstyle · rave |
| Autres | gris (chroma 0) | inclassable |

### Rattachement des petits piliers (à leur ancêtre, pas un hue séparé)
- `disco`, `UK garage` → **house**
- `dubstep`, `breakbeat` → **dnb**
- tout le reste suit sa racine naturelle.

---

## Fichiers — état

### 1. `diggy-tokens.css` ✅ fait
Le bloc `--family-*` + la table `--h-*/--s-*` sont **supprimés**, remplacés par 6 `--hue-*`. Tag-lightness/chroma (`--tag-bg-l`…) inchangés.

### 2. `diggy-style-map.js` ✅ fait (v2)
Expose : `PILLARS`, `PILLAR_ORDER`, `ROOT_TO_PILLAR`, `pillarFromAncestors(ancestors)`, `styleTone({pillar, depth})`, `tagAttrs(tone)`, `slug()`.

### 3. `StyleTag.vue` — à implémenter
Props : `name`, `family` (clé de pilier), `depth` (0–3). Un seul mécanisme : `data-fam` (→ hue) + `--d` (→ désaturation).

```css
.style-tag[data-fam="house"]     { --th: var(--hue-house); }
.style-tag[data-fam="techno"]    { --th: var(--hue-techno); }
.style-tag[data-fam="trance"]    { --th: var(--hue-trance); }
.style-tag[data-fam="dnb"]       { --th: var(--hue-dnb); }
.style-tag[data-fam="hardcore"]  { --th: var(--hue-hardcore); }
.style-tag[data-fam="harddance"] { --th: var(--hue-harddance); }
.style-tag[data-fam="autres"]    { --th: 0; --tag-bg-c: 0; --tag-fg-c: 0; --tag-dot-c: 0; }

.style-tag {
  background: oklch(var(--tag-bg-l) calc(var(--tag-bg-c) * (1 - 0.17 * var(--d,0))) var(--th));
  color:      oklch(var(--tag-fg-l) calc(var(--tag-fg-c) * (1 - 0.10 * var(--d,0))) var(--th));
}
.style-tag .dot {
  background: oklch(calc(var(--tag-dot-l) + 0.04 * var(--d,0))
                    calc(var(--tag-dot-c) * (1 - 0.19 * var(--d,0))) var(--th));
}
```
Template : `<span class="style-tag" v-bind="tagAttrs(tone)"><span class="dot"></span>{{ name }}</span>`

### 4. `GenreCard.vue` / `GenreDetailView.vue` (hero) — à implémenter
Mosaïque = même `--th` (data-fam sur la carte), rampe de **lightness** : 4 tuiles carte / 6 tuiles hero. Valeurs dans le pilote (`.mosaic i:nth-child(n)`).

### 5. `FamilyChips.vue` — à implémenter
Dots = `oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th))`. `Autres` → dot `var(--ink-3)`. Ordre via `PILLAR_ORDER`.

---

## Collision accent/pos — Option A (rien à coder)

Pas de zone d'exclusion. Le StyleTag a son propre contexte (pastille soft + dot + libellé texte), distinct de l'accent (actions) et du pos (dot in-lib). **Seul garde-fou** : ne pas poser un *dot* de pilier à < ~10° de l'accent `328`. Sur Évocateur, Hard Dance = `338` (Δ10°, ok) ; marge possible en glissant à `342–345` si besoin.

---

## Pré-requis backend (à vérifier avant le front)

L'API doit fournir, par genre :
1. ses **ancestors** (ou directement la clé de pilier) → le front fait `pillarFromAncestors(labels)` ;
2. sa **profondeur** dans l'arbre (entier) → clampée 0–3 côté front.

Sans ces deux champs, le front ne peut pas résoudre hue + depth.

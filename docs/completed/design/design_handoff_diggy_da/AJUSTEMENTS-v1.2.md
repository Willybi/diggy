# Diggy — Ajustements DA v1.2 (review du 11 juin 2026)

Contexte : review design de l'implémentation en ligne (`/tracks` Live lib, `/catalog`,
état « playing ») contre la DA v1 « Wildflower ». La structure est fidèle — ces
ajustements corrigent les écarts restants, **par ordre de priorité**.

Les fichiers du paquet `design_handoff_diggy_da/` ont été mis à jour (v1.2,
alignés sur la taxonomie réelle du front House / Techno / Trance / Misc) :
- `diggy-style-map.js` — taxonomie réelle du front (4 familles, 14 styles),
  échelles d'offsets/shades étendues à 7 membres, `slug()` corrigé
- `diggy-tokens.css` — vars `--h-*`/`--s-*` recalculées pour les 14 styles + token `--accent-wash`
- `diggy-components.css` — modifiers des 14 tags + spec `is-playing` / `.play-pill`

**Re-copie ces 3 fichiers dans le repo avant de commencer** (remplace les anciens).

---

## 1. Style tags : brancher le système de familles ⚠️ priorité max

**Constat :** les couleurs des tags ne suivent pas le système. Tech House sort rouge,
UK House orange, Electro brut bleu — couleurs arbitraires ou fallback. La règle DA :
**une famille sonore = une teinte**, ses membres en sont des variations. Tech House,
Deep House et UK House doivent se lire comme des frères (violets ~268°).

**À faire :**
- Supprimer toute couleur de tag définie en dur dans les composants Vue.
- Rendre chaque tag via `diggy-style-map.js` : `styleTagClass(track.style)`
  (classes CSS) **ou** `styleTone(track.style)` (style inline `--th`/`--ts`).
  Les deux mécanismes sont décrits dans le README §3.
- **Remplacer la copie du front par la v1.2 du fichier** — trois changements
  d'algorithme, pas seulement de données :
  1. `MEMBER_OFFSET` / `MEMBER_SHADE` étendus à **7 entrées** (la famille House
     a 7 membres ; les anciens tableaux de 4 renvoyaient `offset 0` / `shade 0`
     aux membres 5+, d'où des doublons de couleur) ;
  2. `slug()` durci : `Classic/Min. Techno` → `classic-min-techno`
     (l'ancienne version laissait passer `/` et `.`, invalides en classe CSS) ;
  3. Teintes de base : **House 268°** (violets), **Techno 312°** (violet profond),
     **Trance 352°** (rose), **Misc 42°** (ambre).

- Hues résolus (= ce que `styleVarsCss()` génère, déjà dans `diggy-tokens.css`) :

| Famille | Style | Hue | Shade |
|---|---|---|---|
| House 268° | Downtempo | 264 | 0 |
| | Nu Disco | 273 | 0.018 |
| | Deep House | 258 | 0.036 |
| | UK House | 279 | 0.054 |
| | French Touch | 253 | 0.012 |
| | Tech House | 283 | 0.030 |
| | UK Garage | 268 | 0.048 |
| Techno 312° | Electro brut | 308 | 0 |
| | Melodic Techno | 317 | 0.018 |
| | Classic/Min. Techno | 302 | 0.036 |
| | Hard/Dark Techno | 323 | 0.054 |
| Trance 352° | Psytrance | 348 | 0 |
| | Trance Techno | 357 | 0.018 |
| Misc 42° | Misc. Tracks | 38 | 0 |

- **Tout nouveau style à l'avenir** : l'ajouter à `FAMILY_MEMBERS` dans
  `diggy-style-map.js` (à la fin du tableau de sa famille), jamais de couleur à la main.
  Un style absent de la map = fallback neutre, c'est le signal qu'il faut l'enregistrer.

## 2. ScorePill (Catalog) : remettre le meter

**Constat :** la colonne RADAR affiche un petit rond avec le chiffre seul.
La spec `score-pill` = pill `--accent-soft` contenant **le chiffre en mono + un meter
de 10 ticks** (`.meter i`, `.is-on` pour les remplis). C'est la lecture « jauge »
d'un coup d'œil qui justifie le composant. Spec exacte dans `diggy-components.css`
section SCORE PILL.

## 3. Données manquantes : `—`, jamais `0:00`

**Constat :** Live lib affiche `0:00` dans la colonne Durée quand la donnée manque ;
le Catalog fait juste avec `—`. Règle globale : **valeur absente → tiret cadratin `—`**
en `--ink-3`, sur toutes les colonnes (BPM, key, durée, rating). `0:00` se lit
comme un bug.

## 4. Affichage BPM : arrondir

`121.29`, `130.43` → afficher l'entier arrondi (`121`, `130`). La précision au
centième n'apporte rien et casse l'alignement de la colonne. Garde la valeur exacte
en data, l'arrondi est purement affichage.

## 5. Toggle « In lib only » : chip-toggle, pas switch iOS

**Constat :** le filtre utilise un switch iOS. La DA prévoit le `chip-toggle`
(pill bordée, qui passe fond `--pos-soft` / texte `--pos-ink` quand actif —
vert = sémantique « in lib »). Spec dans `diggy-components.css` section FILTERS.
Même règle pour `Pas dans RB` et `Radar ≥ 2` sur le Catalog : état actif
= `--pos-soft` (filtres lib) ou `--accent-soft` (filtres radar).

## 6. Vérifier l'accent (mauve 328°, pas fuchsia)

L'accent à l'écran semble plus rose/saturé que le mauve Wildflower. À vérifier :
- `diggy-tokens.css` est importé **tel quel**, une seule fois, sans surcharge ;
- aucune couleur accent redéfinie en dur dans un composant ou une config Tailwind ;
- au pipette sur le logo : attendu ≈ `oklch(0.615 0.132 328)`.

## 7. Nouveau : état « playing » (désormais au contrat)

L'état lecture improvisé était dans le bon esprit ; il est maintenant spec'é
dans `diggy-components.css` (section TRACK TABLE, v1.1) :

- ligne : `tr.is-playing` → fond `--accent-wash` (nouveau token, **plus discret
  que le hover**) ; au hover d'une ligne playing → `--accent-soft` ;
- titre du track en `--accent-ink` pendant la lecture (second indice, pas
  seulement la couleur — tient en dark mode et pour les daltoniens) ;
- bouton : `.play-pill` 28px, rond, `--accent-soft` / icône `--accent-ink`,
  hover `--accent-soft-2` ;
- **pas de barre/bordure accent à gauche de la ligne** (trope écarté par la DA).

`--accent-wash` existe en light et dark dans les tokens — rien à calculer.

---

## Checklist de validation (à vérifier écran par écran)

- [ ] Les 7 styles House rendent dans des violets voisins (253–283°), distincts par nuance
- [ ] Les 4 styles Techno ≈ violet profond (302–323°), les 2 Trance ≈ rosés (348/357°)
- [ ] Misc. Tracks ≈ ambre (38°) — différent du fallback neutre
- [ ] `Classic/Min. Techno` et `Hard/Dark Techno` produisent des classes CSS valides
- [ ] Un style inconnu rend neutre (et déclenche son ajout à la map)
- [ ] RADAR : pill avec meter 10 ticks + chiffre mono
- [ ] Plus aucun `0:00` ; `—` partout où la donnée manque
- [ ] BPM entiers
- [ ] Filtres = chips, état actif `--pos-soft` ou `--accent-soft`, plus de switch
- [ ] Logo au pipette ≈ `oklch(0.615 0.132 328)`
- [ ] Ligne playing : fond plus discret que le hover, titre accent, pas de bordure gauche
- [ ] Tout passe en dark mode (`data-theme="dark"`) sans ajustement manuel

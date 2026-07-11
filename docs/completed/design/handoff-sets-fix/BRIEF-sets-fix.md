# Brief — Sets, correctifs DA (audit prod)

> Maquette : `realign/Sets v2 (pilote).html` · Cible : `server/frontend/src/views/SetsView.vue`
> Audité contre la prod (screenshots willi) + le code GitHub `Willybi/diggy@master`.
> Toggle maquette « Anneau 100% : calme / vert » = la seule décision DA à trancher (voir §2).

---

## Résumé : 4 correctifs

| # | Problème | Gravité | Fichier |
|---|----------|---------|---------|
| 1 | Boutons « Importer + Suivre » **non stylés** (boutons natifs bruts) | **Bug** | `SetsView.vue` (CSS) |
| 2 | **Mur de vert** : anneau 100% plein + cœur liked = 2 signaux verts identiques par ligne, colonne Tracks morte | DA / hiérarchie | `SetsView.vue` |
| 3 | Compteur d'en-tête **trompeur** (affiche le total filtré, pas la bibliothèque) | UX | `SetsView.vue` |
| 4 | Copy **« Suivre »** obsolète (la table est passée à Avis like/dislike) | Cohérence | `SetsView.vue` |

> ⚠️ L'anneau n'est **pas** cassé : à 100% c'est un cercle vert plein complet, normal. Le souci est qu'à l'état stationnaire **tout** est à 100%, donc la couleur ne signale plus rien.

---

## 1. Bug — boutons des résultats de recherche non stylés

**Cause** : `SetsView.vue` n'a **aucune** règle `.btn-follow` / `.btn-follow.done` dans son `<style scoped>` (elles existaient dans le pilote d'origine et ont sauté). Les `<button class="btn-follow">` du panneau de résultats tombent sur le style natif du navigateur.

**Fix** — réintégrer ces règles dans le `<style scoped>` :

```css
.btn-follow {
  height: 32px; padding: 0 16px; border-radius: 999px; cursor: pointer; white-space: nowrap;
  font: 600 12.5px var(--font-ui); border: 1px solid transparent;
  background: var(--accent); color: var(--on-accent);
}
.btn-follow:hover { background: var(--accent-hover); }
.btn-follow:disabled { opacity: .6; cursor: default; }
.btn-follow.done {
  background: transparent; color: var(--ink-3); border-color: var(--line-2); cursor: default;
}
```

---

## 2. DA — anneau « tracks » : le vert ne sert qu'à l'EXCEPTION

Aujourd'hui chaque ligne empile **anneau plein vert (100%)** + **cœur liked vert** → la moitié droite de la table lit comme un aplat vert, l'accent (mauve) disparaît, et la colonne Tracks n'informe sur rien (tout est à 100%). Viole la règle CLAUDE.md « `--pos` = positif, jamais décoration ».

**Principe** : la couleur de l'anneau = **un set incomplet à enrichir** (actionnable). Un set complet = état **calme**.

- **100%** → `ring.done` : pastille **neutre** (`--surface-2` / `--ink-3`) avec un **check** + « 100% » en `--ink-3`. Pas de vert.
- **60–99%** → donut **`--accent`** (mauve) + % `--accent-ink`.
- **< 60%** → donut **ambre** (`oklch(0.74 0.13 60)`) + % `oklch(0.52 0.13 60)`.

**Implémentation** (calquer la maquette) — `ringClass` / le template :

```js
function ringClass(ident, total) {
  const p = ringPct(ident, total)
  if (p >= 100) return 'done'      // était 'full'
  if (p >= 60)  return 'mid'
  return 'low'
}
```

```vue
<span class="ring" :class="ringClass(s.identified_tracks, s.total_tracks)" :title="`${s.identified_tracks} / ${s.total_tracks} tracks identifiées`">
  <template v-if="ringPct(s.identified_tracks, s.total_tracks) >= 100">
    <span class="chk"><svg viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg></span>
  </template>
  <svg v-else viewBox="0 0 30 30"> … bg + fg inchangés … </svg>
  <span class="pct">{{ ringPct(...) }}%</span>
</span>
```

```css
/* supprimer .ring.full .fg / .ring.full .pct, ajouter : */
.ring.done .chk {
  width: 24px; height: 24px; display: grid; place-items: center; border-radius: 50%;
  background: var(--surface-2); color: var(--ink-3);
}
.ring.done .chk svg { width: 13px; height: 13px; fill: none; stroke: currentColor; stroke-width: 2.6; stroke-linecap: round; stroke-linejoin: round; }
.ring.done .pct { color: var(--ink-3); }
.ring.mid .pct { color: var(--accent-ink); }
.ring.low .pct { color: oklch(0.52 0.13 60); }
```

> **À trancher (willi)** : garder le 100% **calme** (reco — un seul vert par ligne, le cœur) ou **vert** ? Le toggle de la maquette montre les deux côte à côte. Si « vert » est retenu : `.ring.done .chk { background: var(--pos-soft); color: var(--pos-ink); }` + `.ring.done .pct { color: var(--pos-ink); }`.

---

## 3. UX — compteur d'en-tête

`{{ displayList.length }} sets` change avec le filtre/recherche → en mode Liked, « 71 sets » devient le nombre de likés et on perd le total bibliothèque.

**Fix** : afficher le **total réel** (longueur non filtrée, idéalement renvoyée par l'API même quand `q` est posé), et n'ajouter le sous-compte qu'en mode filtré :

```vue
<div class="sub">
  {{ total }} sets
  <span v-if="mode !== 'all'" class="muted">· {{ displayList.length }} {{ mode === 'liked' ? 'likés' : 'dislikés' }}</span>
</div>
```
`.sub .muted { color: var(--ink-3); }`. (`total` = `sets.value.length` si pas de recherche serveur, sinon un compteur dédié.)

---

## 4. Cohérence — vocabulaire « Suivre » → Avis

La table n'a plus d'action « Suivre » (remplacée par le composant `LikeDislike` = colonne **Avis**), mais le bouton des résultats dit encore « Importer **+ Suivre** » et le filtre est passé de `Tous / Suivis` (pilote) à `Tous / Liked / Disliked`.

**Décision à acter (puis CLAUDE.md)** : Avis (like/dislike, partagé avec Radar) **remplace** Suivre sur Sets.
- Bouton résultats : **plus de pill texte « Importer / Importé »**. À la place un **bouton cœur** (cohérent avec l'Avis de la table + règle DA « `--pos` = in-lib ») :
  - au repos → cœur **contour** (`--ink-3`, hover `--pos`), `title="Ajouter à ma bibliothèque"` ;
  - déjà importé → cœur **vert plein** (`--pos-soft` / `--pos-ink`), inerte, `title="Déjà dans ta bibliothèque"`.
- Côté Vue : remplacer `.btn-follow` par `.btn-like` (voir maquette), garder le SVG cœur de `LikeDislike.vue`. L'action `doImportFromSearch` reste identique (import backend) ; seul l'habillage change.

```css
.btn-like {
  width: 34px; height: 34px; flex: none; display: grid; place-items: center;
  border-radius: var(--r-sm); border: 1px solid var(--line-2);
  background: var(--surface); color: var(--ink-3); cursor: pointer; padding: 0;
  transition: color .14s, border-color .14s, background .14s;
}
.btn-like svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.btn-like:hover { color: var(--pos); border-color: var(--pos); }
.btn-like.liked { background: var(--pos-soft); border-color: transparent; color: var(--pos-ink); cursor: default; }
.btn-like.liked svg { fill: var(--pos-ink); stroke: var(--pos-ink); }
```

---

## Hors-scope mais à vérifier (willi)
- **Avis posé sur (presque) tous les sets** : le hover-reveal perd son sens si tout est déjà liked (mur de cœurs). Confirmer que c'est bien la donnée réelle (willi a liké) et non un défaut de binding `opinions.get('set', id)`.
- Seuils anneau **60 / 100** OK ? (inchangés depuis le pilote v1)

---

## Checklist DA (rappel)
- [x] Couleurs 100% tokens
- [x] `--pos` = positif seulement (plus dupliqué par l'anneau)
- [x] Accent discipliné
- [x] Type UI / Mono données
- [x] Responsive container-queries inchangé
- [x] Dark mode (vérifié sur la maquette)

# Diggy — Handoff : Fusion Catalog + Live lib (v1.2)

**Date :** 11 juin 2026  
**Contexte :** La page `/tracks` (Live lib) et la page `/catalog` sont fusionnées en une seule vue `/catalog`. La Live lib n'est plus une route distincte — c'est un **état de filtre** sur le catalog.

---

## 1. Principe

> « In lib » n'est pas un lieu, c'est un état d'une track.

Une seule source de vérité : le **Catalog** (`/catalog`). Le filtre `In lib` bascule la vue sur les tracks possédées uniquement. La sidebar perd l'item « Live lib », et le compteur du Catalog reflète les deux chiffres (`1.4k tracks · 312 in lib`).

---

## 2. Changements de routing / navigation

| Avant | Après |
|---|---|
| `/tracks` → Live lib (table filtrée) | **Supprimer cette route** |
| `/catalog` → Catalog (table complète) | Conserver, devient la vue principale |
| Sidebar : `Live lib` + `Catalog` | Sidebar : `Catalog` uniquement (sous `LIBRARY`) |

**Redirect :** tout lien interne ou favori vers `/tracks` → redirect 301 vers `/catalog?inlib=true`.

---

## 3. Persistance du filtre

Le chip « In lib » doit être **persistant** par session :

```js
// Lire au montage
const saved = sessionStorage.getItem('catalog_inlib');
const [inlib, setInlib] = useState(saved === 'true');

// Persister au changement
const toggle = (val) => {
  setInlib(val);
  sessionStorage.setItem('catalog_inlib', String(val));
};
```

Aussi supporter le query param `?inlib=true` (pour le redirect de `/tracks` et les liens directs).

---

## 4. Colonnes de la table

Colonnes dans l'ordre exact :

| # | Colonne | Type | Notes |
|---|---|---|---|
| 1 | *(play)* | bouton icône | `.pbtn` — grisé si pas en lib |
| 2 | Track | titre + artiste | `.td-track` — titre en `--accent-ink` si `is-playing` |
| 3 | Style | tag coloré famille | `PTag` / `styleTagClass()` |
| 4 | BPM | mono, entier arrondi | `—` si absent |
| 5 | Key | mono, accent | `—` si absent |
| 6 | Durée | mono | `—` si absent (jamais `0:00`) |
| 7 | Rating | `<Rating n={1..5} />` | `—` si absent |
| 8 | Radar | `<ScorePill score={1..10} />` | `—` si absent |
| 9 | **In lib** | `<LibDot inlib={bool} />` | **masquée quand le filtre `inlib` est actif** |

### Règle colonne « In lib »
- Vue **mixte** (chip off) → colonne visible, pastille ✓ verte ou ✕ grise
- Vue **in lib** (chip on) → colonne **absente du DOM** (redondante, tout est in lib)
- Bouton play : **caché** pour les tracks hors lib (pas de fichier à lire)

---

## 5. Composant `<LibDot>`

Remplace les anciens badges `InLibBadge` dans la table. Même objet partout (catalog, tracklist de set, etc.).

```jsx
/* CSS */
.lib-dot { display: inline-grid; place-items: center; width: 22px; height: 22px;
  border-radius: 50%; }
.lib-dot svg { width: 12px; height: 12px; }
.lib-dot.in  { background: var(--pos-soft);   color: var(--pos-ink); }
.lib-dot.out { background: var(--surface-3);  color: var(--ink-3);   }

/* JSX */
function LibDot({ inlib }) {
  return (
    <span className={"lib-dot " + (inlib ? "in" : "out")}
          title={inlib ? "In lib" : "Pas dans la lib"}>
      {inlib ? <CheckIcon /> : <XIcon />}
    </span>
  );
}
```

---

## 6. Barre de filtres

La filter-bar du Catalog (déjà en place) accueille le chip `In lib` **en dernier**, après les filtres Style / BPM / Key. Il utilise le composant `chip-toggle` existant (pas un switch iOS).

```jsx
<button
  className={"chip-toggle" + (inlib ? " on" : "")}
  onClick={() => toggle(!inlib)}
>
  <span className="switch" />In lib
</button>
```

État actif : `--pos-soft` fond / `--pos-ink` texte (sémantique verte = « possédé »).

---

## 7. Compteur en en-tête

```jsx
<h1>Catalog</h1>
<span className="cnt">
  {inlib
    ? `${nLib} tracks · in lib`
    : `${total} tracks · ${nLib} in lib`}
</span>
```

`.cnt` : `font-family: var(--font-mono); font-size: 12px; color: var(--ink-3);`

---

## 8. État « playing » (contrat v1.1)

Inchangé, s'applique sur les deux vues :

```css
.track-table tbody tr.is-playing          { background: var(--accent-wash); }
.track-table tbody tr.is-playing:hover    { background: var(--accent-soft); }
.track-table tr.is-playing .tt            { color: var(--accent-ink); }
```

`--accent-wash` (à ajouter si absent) :
```css
:root       { --accent-wash: oklch(0.962 0.022 var(--accent-h)); }
[data-theme="dark"] { --accent-wash: oklch(0.272 0.038 var(--accent-h)); }
```

---

## 9. Sidebar

Supprimer l'item `Live lib`. Garder uniquement :

```
LIBRARY
  Catalog      [total]
DISCOVER
  Radar        [n]
  Style tags   [14]
```

Le compteur du Catalog affiche le **total** (pas juste la lib), toujours.

---

## 10. Checklist de validation

- [ ] `/tracks` redirige vers `/catalog?inlib=true`
- [ ] La sidebar n'a plus l'item « Live lib »
- [ ] Chip « In lib » visible dans la filter-bar, en dernier
- [ ] Chip actif → fond vert `--pos-soft`, texte `--pos-ink`
- [ ] Filtre persistant : rechargement page conserve l'état du chip
- [ ] Vue mixte : colonne « In lib » visible, `LibDot` ✓/✕ uniformes
- [ ] Vue in lib : colonne « In lib » absente, bouton play masqué sur non-lib
- [ ] Compteur en-tête correct dans les deux états
- [ ] BPM entiers (arrondi `.toFixed(0)` ou `Math.round()`)
- [ ] Durée absente → `—` (jamais `0:00`)
- [ ] Ligne playing : fond `--accent-wash` + titre `--accent-ink`
- [ ] Tout passe en dark mode sans surcharge manuelle

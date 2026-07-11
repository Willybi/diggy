# Fix round 3 — Points non résolus

> 14 juin 2026 — uniquement les corrections qui n'ont pas été appliquées

---

## 1. 🔴 ARTISTE — Nom affiché en slug (ex. "adambeyer")

`artist.name` n'est pas utilisé dans le hero. Le titre affiche probablement
`artist.soundcloud_id` ou le slug.

```jsx
// ✓ Correct
<h1>{artist.name}</h1>          // → "Adam Beyer"

// ✗ Ce qui se passe actuellement
<h1>{artist.soundcloud_id}</h1> // → "adambeyer"
```

---

## 2. 🔴 ARTISTE — Catalog = 0 / In lib = 0 (string match cassé)

La requête `catalog.artist = "adambeyer"` ne trouve rien.
Il faut comparer sur `artist.name` (pas le slug) + insensible à la casse.

```sql
WHERE LOWER(c.artist) = LOWER(:artist_name)
   OR EXISTS (
     SELECT 1 FROM artist_aliases aa
     WHERE aa.artist_id = :artist_id
       AND LOWER(c.artist) = LOWER(aa.normalized_alias)
   )
```

S'applique à : `tracks_in_catalog`, `tracks_in_lib`, `rating_moyen`, et le bloc liste de tracks.

---

## 3. SET — Deux colonnes STATUT + LIB → fusionner en une seule

La tracklist a deux colonnes séparées qui font la même chose.
Supprimer la colonne "STATUT" (texte "OK"), garder uniquement "IN LIB" avec `LibDot` :

```css
.lib-dot { display: inline-grid; place-items: center;
  width: 22px; height: 22px; border-radius: 50%; }
.lib-dot svg { width: 12px; height: 12px; }
.lib-dot.in  { background: var(--pos-soft);  color: var(--pos-ink); }
.lib-dot.out { background: var(--surface-3); color: var(--ink-3);
               outline: 1px solid var(--line); }
```

```jsx
<LibDot inlib={track.catalog_id !== null && !track.is_id} />
// is_id = true → afficher "ID" en mono ink-3, pas de pastille
```

---

## 4. SET — Bouton source en accent → ghost

"Voir sur TrackID.net" utilise le style accent (fond mauve).
Les liens externes = toujours `btn-ghost`.

```jsx
// ✓
<a className="btn-ghost">{PI.ext} Voir sur TrackID.net</a>
// ✗
<a className="btn-accent">Voir sur TrackID.net</a>
```

---

## 5. CATALOG — Durée `0:00` encore présente

```js
const fmt = (v) => (!v || v === '0:00' || v === 0) ? '—' : v;
// Appliquer sur la colonne durée du catalog
fmt(fmtMs(track.duration_ms))
```

---

## Checklist

- [ ] Artiste : `artist.name` dans le hero (pas le slug)
- [ ] Artiste : requête SQL insensible à la casse + aliases → stats non nulles
- [ ] Set : colonnes STATUT + LIB fusionnées → `LibDot` unique
- [ ] Set : bouton source en `btn-ghost`
- [ ] Catalog : durée `fmt()` appliqué, plus de `0:00`

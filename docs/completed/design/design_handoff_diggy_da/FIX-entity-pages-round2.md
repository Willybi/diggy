# Fix — Pages d'entité (Track · Set · Artiste)

> Review du 14 juin 2026 — corrections post-implémentation

---

## Page TRACK — 4 corrections

### 1. Supprimer ISRC de la stat strip
Code technique d'ayant-droit, aucune utilité pour un DJ.

Stat strip finale dans cet ordre exact :
```
BPM · KEY · DURÉE · ANNÉE · RATING · RADAR
```

### 2. DURÉE et ANNÉE à `0:00` / `--` → appliquer `fmt()`
Le fix `fmt()` n'a pas été appliqué sur ces deux champs.

```js
const fmt = (v) => (!v || v === '0:00' || v === 0 || v === '--') ? '—' : v;

// Durée
fmt(fmtMs(track.duration_ms))

// Année
track.release_date ? new Date(track.release_date).getFullYear() : '—'
```

### 3. Supprimer le bloc "Genres" sous la stat strip
Redondant avec les tags déjà affichés dans le hero. Un seul endroit suffit.

### 4. Rating : un seul endroit — stat strip uniquement
Le rating apparaît à deux endroits (hero + stat strip). Le supprimer du hero,
garder uniquement dans la stat strip. Le hero garde : `InLibBadge` + style tag.

---

## Page SET — 2 corrections

### 1. Colonne LIB — appliquer `LibDot` strict
Les pastilles actuelles (`OK` vert / `×` gris) ne suivent pas le composant DA.
Tailles différentes, texte au lieu d'icône.

```css
.lib-dot { display: inline-grid; place-items: center;
  width: 22px; height: 22px; border-radius: 50%; }
.lib-dot svg { width: 12px; height: 12px; }
.lib-dot.in  { background: var(--pos-soft);  color: var(--pos-ink); }
.lib-dot.out { background: var(--surface-3); color: var(--ink-3);   }
```

```jsx
// Icône ✓ (check SVG) si résolu, ✕ (x SVG) si non résolu/ID
<LibDot inlib={track.catalog_id !== null && !track.is_id} />
// Pour les lignes is_id = true → afficher "ID" en mono ink-3, pas de pastille
```

### 2. Bloc "Artistes" — conditionnel selon nb d'artistes
Un seul artiste → l'afficher dans le sub du hero, pas dans un bloc dédié.
Le bloc "Artistes" n'a du sens que pour les B2B (≥ 2 artistes).

```jsx
// Sub du hero (set solo)
sub={<><a href={`/artist/${set.artists[0].id}`}>{set.artists[0].name}</a>
  <span className="dot-sep" /><span>{set.venue}</span></>}

// Bloc artistes uniquement si B2B
{set.artists.length > 1 && (
  <RelBlock title="Artistes" count={set.artists.length} flush>
    {set.artists.map(a => <ArtistRow key={a.id} {...a} />)}
  </RelBlock>
)}
```

**Titre long :** si `sets.title` dépasse ~60 caractères, réduire le font-size du hero-title :
```css
.hero-title { font-size: clamp(22px, 2.5vw, 34px); }
```

---

## Page ARTISTE — 3 corrections (dont 1 critique)

### 1. 🔴 CRITIQUE — Nom affiché en minuscules sans espace
"adambeyer" est probablement le `soundcloud_id` ou le slug affiché à la place de `artists.name`.

**Vérifier** que le hero utilise bien `artist.name` (ex. "Adam Beyer")
et non `artist.soundcloud_id`, `artist.trackid_id` ou un slug.

```jsx
// ✓ Correct
<h1 className="hero-title">{artist.name}</h1>

// ✗ À éviter
<h1 className="hero-title">{artist.soundcloud_id}</h1>
```

### 2. 🔴 CRITIQUE — Catalog = 0, In lib = 0 (string match insensible à la casse)
`catalog.artist = "adambeyer"` ne trouve rien car les tracks sont enregistrées
"Adam Beyer". La comparaison doit être insensible à la casse ET chercher dans les aliases.

```sql
-- Requête corrigée : tracks de cet artiste
SELECT c.*, lt.rating
FROM catalog c
LEFT JOIN lib_tracks lt ON lt.catalog_id = c.id
WHERE LOWER(c.artist) = LOWER(:artist_name)
   OR EXISTS (
     SELECT 1 FROM artist_aliases aa
     WHERE aa.artist_id = :artist_id
       AND LOWER(c.artist) = LOWER(aa.normalized_alias)
   )
ORDER BY lt.rating DESC NULLS LAST
```

Idem pour les stats `tracks_in_lib` et `tracks_in_catalog`.

### 3. Bouton "TrackID" en accent → ghost
Le bouton lien externe utilise le style accent (fond mauve).
L'accent est réservé à l'action principale. Tous les liens externes = `btn-ghost`.

```jsx
// ✓ Correct
<a className="btn-ghost" href={...}>{PI.ext} TrackID</a>

// ✗ À corriger
<a className="btn-accent" href={...}>TrackID</a>
```

---

## Checklist

- [ ] ISRC retiré de la stat strip Track
- [ ] Durée et Année : `fmt()` appliqué, plus de `0:00` ni `--`
- [ ] Bloc "Genres" Track supprimé
- [ ] Rating Track : stat strip uniquement, retiré du hero
- [ ] `LibDot` 22px uniforme sur la tracklist Set (plus de texte "OK"/"×")
- [ ] Bloc "Artistes" Set conditionnel (seulement si B2B)
- [ ] Artiste : `artist.name` dans le hero (pas le slug/soundcloud_id)
- [ ] Artiste : requête insensible à la casse + aliases → stats non nulles
- [ ] Liens externes artiste : tous en `btn-ghost`

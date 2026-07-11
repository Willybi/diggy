# Fix round 4 — Points restants

> 14 juin 2026

---

## Page ARTISTE — 3 corrections

### 1. In lib = 0 (même bug que Catalog, pas résolu sur lib_tracks)
Le compteur `tracks_in_catalog` fonctionne mais `tracks_in_lib` retourne 0.
La requête sur `lib_tracks` n'utilise pas encore le match insensible à la casse.

```sql
-- Compteur in_lib corrigé
SELECT COUNT(*)
FROM lib_tracks lt
JOIN catalog c ON c.id = lt.catalog_id
WHERE LOWER(c.artist) = LOWER(:artist_name)
   OR EXISTS (
     SELECT 1 FROM artist_aliases aa
     WHERE aa.artist_id = :artist_id
       AND LOWER(c.artist) = LOWER(aa.normalized_alias)
   )
```

Le `rating_moyen` se résoudra automatiquement quand `in_lib` sera > 0.

### 2. Bloc "Tracks" — utiliser la MiniTrackTable
La liste actuelle affiche juste les titres sans aucune donnée (style, BPM, key, rating).
Utiliser le composant table existant du catalog :

Colonnes à afficher : `TRACK · STYLE · BPM · KEY · RATING`
(pas de colonne IN LIB — on est déjà sur la page artiste, c'est redondant)

### 3. Format "13/13 ID" dans les sets → plus lisible
"ID" est ambigu (identifiant ? identity ?). Remplacer par :

```
// ✗ Actuel
"13/13 ID"

// ✓ Correct
"13 tracks · 13 identifiées"
// ou si toutes identifiées :
"13 tracks · toutes identifiées"
```

---

## Page SET — 2 corrections

### 1. Bouton source encore en accent → ghost
"Voir sur TrackID.net" est toujours en fond mauve (btn-accent).
Les liens externes = toujours `btn-ghost`.

```jsx
// ✓
<a className="btn-ghost" href={set.source_url} target="_blank">
  {PI.ext} Voir sur TrackID.net
</a>
```

### 2. Titre long — clamp sur le font-size
Les titres de sets type "DCR827 – Drumcode Radio Live - Adam Beyer live from Drumcode Mallorca"
débordent du hero. Appliquer un clamp :

```css
.hero-title {
  font-size: clamp(20px, 2.2vw, 34px);
  overflow-wrap: break-word;
}
```

---

## Page CATALOG — donnée manquante (pas un bug de code)

BPM / KEY / DURÉE à `—` sur la majorité des tracks : les données existent
en base uniquement pour les tracks importées depuis Beatport (Talk To You par exemple).
Les tracks détectées via Deezer/radar n'ont pas ces champs alimentés.

**Ce n'est pas un bug d'affichage** — le `—` est correct.
C'est un chantier d'enrichissement de données : lors de l'import Deezer,
récupérer et stocker `bpm`, `key`, `duration_ms` si disponibles dans l'API.

---

## Checklist

- [ ] Artiste : `lib_tracks` compteur avec match insensible à la casse + aliases
- [ ] Artiste : bloc Tracks avec colonnes (style, BPM, key, rating)
- [ ] Artiste : sets — "13/13 ID" → "13 tracks · 13 identifiées"
- [ ] Set : bouton source en `btn-ghost`
- [ ] Set : `clamp(20px, 2.2vw, 34px)` sur `.hero-title`

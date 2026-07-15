# Sets (liste) — `/sets`

Statut : ✅ figé  |  Vue : `views/SetsView.vue`

## 1. Ce qu'on a (actuel)

**Données** : `GET /api/sets/` (param `q` ; `SetListResponse` {total, items}). `SetListItemOut` : id, title, **source**, **source_url**, played_date, duration_ms, has_artwork, total_tracks, identified_tracks, artists[]. **Pas de genre.** Sort + filtres **client-side** (tous les sets chargés d'un coup — **pas de pagination**). Formulaire **Ajouter** (recherche TrackID + import URL).

**Structure** :
- **Header** : « Sets » + count, SearchBox, SegFilter (Tous / Liked / Disliked / À explorer), bouton **Ajouter** (form TrackID / URL).
- **Table** (fixed) : Set (cover + titre + artistes) · Date · **Tracks (`RingPct` %)** · Durée · Avis. Colonnes sortables, row → détail, états liked/disliked.

**Dette** :
- **Pas de pagination** : tous les sets chargés + sort/filtre **client-side** (≠ `usePaginatedList` des autres listes) → lourd.
- **Beaucoup de sets à 0 %** identifié (bruit).
- **Genre absent** (dispo côté détail via déduction).
- **Source dispo en data mais pas affichée**.

## 2. Vision (William)

- Un des visuels **le moins aimé**.
- **Trop de sets à 0 %** → **ne pas les afficher** tant qu'ils sont à 0 %.
- Gardés : **cover, titre, date, % de tracks, durée, avis**.
- **Manque le genre** + peut-être d'autres infos → **Claude propose**.

## 3. Revue de cohérence (Claude)

**Décisions proposées** :
- **Exclure les sets à 0 %** (identified_tracks == 0) — masqués par défaut.
- **Gardé** : cover, titre + artistes, date, `RingPct` %, durée, avis.
- **+ Genre** : **déduit des tracks** (comme Set detail), StyleTag(s) dans la row.
- **+ Source** : **déjà en data** (youtube / soundcloud / 1001 / trackid) → **badge/logo** (`<PlatformLink>`) dans la row.
- **Structurel** : passer en **infinite scroll** (`usePaginatedList`) + sort/filtre **server-side** (cohérence avec Artistes/Genres + perf).

**Autres infos possibles (à piocher)** :
- **Nb de tracks brut** à côté du % (« 24 tracks · 80 % »).
- **Play** rapide (aperçu d'un track du set), comme les autres listes.

**Keep / Improve / Remove**
- ✅ **Garder** : cover, titre, date, %, durée, avis, form Ajouter, tri.
- ➕ **Améliorer** : exclure 0 % ; **+ genre déduit** ; **+ source (logo)** ; **infinite scroll** partagé ; (option nb tracks brut, play).
- ➖ **Retirer** : les sets à 0 % (masqués).

**Réponses (William)** : 0 % masqués **sans toggle** · genre déduit ✅ · autres infos (nb brut, play) ❌ · infinite scroll ✅ · source = **logo** ✅.

## 4. Ré-allocation des points retirés
- **Sets à 0 %** → **masqués** (hard exclude, pas de toggle).
- **Options** nb tracks brut / play → écartées.
- Rien à déplacer vers d'autres pages.

## 5. Décisions figées
- **Exclure les sets à 0 %** (`identified_tracks == 0`) — **par défaut, sans toggle**.
- **Row** : cover · titre + artistes · **Genre (déduit, StyleTag)** · Date · **Source (logo, `<PlatformLink>`)** · Tracks (`RingPct` %) · Durée · Avis.
- **Genre** : déduit des tracks (aucun champ set).
- **Source** : logo de plateforme (`<PlatformLink>`).
- **Infinite scroll** (`usePaginatedList`) + sort/filtre **server-side**.
- **Écarté** : nb tracks brut, play.
- **Gardé** : form **Ajouter** (TrackID / URL), tri par colonne, états liked/disliked, row → détail.

## 6. Sortie next-step
**Handoff Design**
- [ ] Row set enrichie : **+ genre (StyleTag)** + **source (logo)** ; layout colonnes + responsive (masquage progressif).

**Chantier work_manager**
- **Back** : `/api/sets/` — **exclure `identified_tracks == 0`** ; ajouter **genres déduits** à `SetListItemOut` ; supporter **sort + pagination server-side** (skip/limit/sort).
- **Front** : `SetsView` → **`usePaginatedList`** ; row + genre + source logo (`<PlatformLink>`) ; retrait du sort/filtre client-side. NB : filtres opinion (liked/disliked/à explorer) à gérer comme la liste Artistes (résolution via opinions store / ids).
- **Transverse** : `<PlatformLink>`, cohérence de la rangée.

**Dépend de** : `<PlatformLink>` (transverse).

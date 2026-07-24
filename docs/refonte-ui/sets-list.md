# Sets (liste) — `/sets`

Statut : ✅ figé  |  Vue : `views/SetsView.vue`

## 1. Ce qu'on a (actuel)

**Données** : `GET /api/sets/` (param `q` ; `SetListResponse` {total, items}). `SetListItemOut` : id, title, **source**, **source_url**, played_date, duration_ms, has_artwork, total_tracks, identified_tracks, artists[]. **Pas de genre.** Sort + filtres **client-side** (tous les sets chargés d'un coup — **pas de pagination**). Formulaire **Ajouter** (recherche TrackID + import URL).

**Structure** :
- **Header** : « Sets » + count, SearchBox, SegFilter (Tous / Liked / Disliked / À explorer), bouton **Ajouter** (form TrackID / URL).
- **Table** (fixed) : Set (cover + titre + artistes) · Date · **Tracks (`RingPct` %)** · Durée · Avis. Colonnes sortables, row → détail, états liked/disliked.

**Dette** :
- **Pagination front absente** : ⚠️ _correction pré-vol 2026-07-23_ — le back `/api/sets/` **pagine déjà** (`limit`/`offset` défaut 50 + `total`). C'est le **front** qui ne s'en sert pas : il charge la page 1 et trie/filtre **client-side** dessus (≠ `usePaginatedList`). Reste à câbler : infinite scroll front + `sort` server-side (le back n'a pas encore de param `sort`, ordre figé date desc).
- **Beaucoup de sets à 0 %** identifié (bruit).
- **Genre absent** (dispo côté détail via déduction — le back sait le calculer via `aggregate_top_genres`).
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
- **Row** : cover · titre + artistes · **Genre (déduit, StyleTag)** · Date · Tracks (`RingPct` %) · Durée · Avis.
- **Genre** : déduit des tracks (aucun champ set).
- ~~**Source** : logo de plateforme (`<PlatformLink>`).~~ **RETIRÉE (pré-vol 2026-07-23)** : en base 100 % des sets sont `source='trackid'` (origine réelle `platform` connue pour seulement 68/11800) → un logo de source serait identique partout ou vide à ~99 %, aucune valeur. Décision William. Le lien vers l'origine reste sur la page Set detail.
- **Infinite scroll** (`usePaginatedList`) + sort/filtre **server-side**.
- **Écarté** : nb tracks brut, play.
- **Gardé** : form **Ajouter** (TrackID / URL), tri par colonne, états liked/disliked, row → détail.

### Précisions pré-vol chantier (2026-07-23)
- **Format = TABLEAU enrichi** (décision William) — l'incohérence `TRANSVERSE.md` (qui annonçait une grille `<SetCard>`) est tranchée en faveur de la row : `<SetCard>` **n'est pas** réutilisé ici (TRANSVERSE corrigé).
- **Opinion (like/dislike)** géré **comme la liste Artistes** : le SegFilter (Tous/Liked/Disliked/À explorer) résout les ids via le store `opinions` puis un fetch `ids=…` (non paginé). → **le tri par colonne « Avis » est retiré** (opinion = filtre, pas colonne triable server-side) ; les boutons avis restent dans la row. Colonnes triables server-side = **titre · date · tracks (%) · durée**.
- **Genre** : le back renvoie `top_genres` (liste `TopGenreOut`, même agrégat que le détail) ; la DA affiche **1–2 StyleTags**.
- **Source** : colonne **RETIRÉE** (voir §5 — donnée sans valeur : 100 % trackid). `<PlatformLink>` n'est donc plus une dépendance de cette page.
- **Composants transverses** : tous déjà livrés (`<StyleTag>`, `<ScoreRing>`, `<Artwork>`, `usePaginatedList`). **Aucun nouveau composant** → pas de lot composant.

### Décisions du handoff Design (round Claude Design, 2026-07-24 — voir `handoff-sets-list/`)
- **Colonne Tracks (%) = `<ScoreRing mode="pct" size="md">`** (`score = identified_tracks / total_tracks`), **pas** `<RingPct>` : le brief décrit la géométrie ScoreRing (40 px, % centré, espace fine insécable) → concrétise la migration RingPct→ScoreRing de TRANSVERSE. Anneau jamais nul (0 % exclus).
- **Panneau « Ajouter » = MODAL 2 onglets** (recentré desktop, bottom-sheet `position: fixed` mobile) — l'actuel formulaire inline devient un modal ; flux inchangé (recherche TrackID + import par résultat · import URL).
- **Genre : colonne dédiée desktop qui se replie sous le titre (chips) < 860 px** (ne disparaît pas). Column-drop : Durée < 1000 · Genre(colonne) < 860 · Date < 700 · mobile < 640 garde Set + Tracks(%) + Avis.
- **Artistes cliquables → `/artist/:id`** dans la cellule Set → **le lot back renvoie `artists: [{id, name}]`** (au lieu de `list[str]`), l'`artist_id` étant dispo via `SetArtist`. _Petit ajout de contrat au-delà de la fiche._
- **Reliquat/caveat** : le genre déduit d'un set à peu de tracks identifiés est bruité (1–2 tracks) — accepté, non bloquant.

## 6. Sortie next-step
**Handoff Design**
- [ ] Row set enrichie : **+ genre (StyleTag)** ; layout colonnes + responsive (masquage progressif). _(Source retirée — voir §5.)_

**Chantier work_manager**
- **Lot 0 — Back** : `/api/sets/` — **exclure `identified_tracks == 0`** (HAVING) ; ajouter **genres déduits** (`top_genres: list[TopGenreOut]`) à `SetListItemOut` (batch + `catalog_visible(uid)` + warm pillar cache, comme set-detail → ajoute `get_current_user_optional`) ; ajouter param **`sort`** (titre/date/tracks/durée ; pagination `limit`/`offset` déjà en place) et param **`ids`** (résolution filtre opinion façon Artistes).
- **Lot 1 — Front** : `SetsView` → **`usePaginatedList`** (sentinel infinite scroll) ; row + colonne genre (StyleTag) ; retrait du sort/filtre client-side ; filtres opinion (liked/disliked/à explorer) gérés **comme la liste Artistes** (résolution via opinions store / `ids`). Tri par colonne retiré sur « Avis ».
- **Transverse** : aucun nouveau composant (tous livrés).

**Dépend de** : rien (composants transverses tous livrés).

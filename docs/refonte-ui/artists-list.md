# Artistes (liste) — `/artists`

Statut : ✅ figé  |  Vue : `views/ArtistsView.vue` + `components/ArtistCard.vue`

## 1. Ce qu'on a (actuel)

**Données** : `/api/artists/` via `usePaginatedList` (pageSize 24 ; dimensions sort / family / query). `ArtistListItemOut` : id, name, has_artwork, **nb_catalog**, **nb_lib**, nb_liked, **avg_rating**, genres, top_track_artworks, tracks_with_artwork. Filtres opinion (liked/disliked) résolus **client-side** (opinions store + param `ids`).

**Structure** :
- **Header** : titre « Artistes » + compteur, SearchBox, **SegFilter** (Catalog / In Bib / Liked / Disliked / **Rating** / A–Z).
- **FamilyChips** (filtre pilier).
- **Grille** d'`ArtistCard` + **infinite scroll** (`usePaginatedList` ✅ déjà le composable partagé).

**ArtistCard** (propre, apprécié) :
- **Art zone** : mosaïque (4 covers top-tracks) + scrim **teinté par pilier** + **avatar rond** centré ; overlays : **badge rating (haut-droit)**, **badge in-lib « N en bib » (haut-gauche)**, play (hover, bas-droit).
- **Body** (teinté pilier) : nom, genres (2 tags), ligne de stats : **Catalog · In Lib · LikeDislike**. Bordure verte si liké, estompée si disliké.

**Dette** :
- **In-lib affiché 2×** : badge overlay (haut-gauche) **+** stat « In Lib ».
- **Rating** : badge overlay (haut-droit) **+** option de tri « Rating » **+** champ `avg_rating` → à retirer (transverse).
- **Pas d'indicateur « suivi »** alors que **suivi ≠ liké** (décorrélés par design) → le feedback follow manque.
- `following` **pas renvoyé** par le endpoint liste (à ajouter pour l'indicateur).

## 2. Vision (William)

- Card **propre** (photo + cover en fond + couleur de genre) : **gardée**.
- **Un seul « in lib »** (retirer le doublon).
- **Retirer le rating moyen** (comme partout).
- **Ajouter un feedback visuel « suivi »** — suivi ≠ liké, il faut afficher **les deux**.
- « Est-ce que tu vois autre chose ? »

## 3. Revue de cohérence (Claude)

**Décisions proposées** :
- **Card gardée** (structure inchangée).
- **In-lib** : garder le **stat « In Lib »** (structuré, à côté de Catalog), **retirer le badge overlay** → libère le coin haut-gauche.
- **Rating** : retirer le **badge** (haut-droit) + l'**option de tri « Rating »** + le champ `avg_rating`.
- **Indicateur « suivi »** : nouveau badge sur l'art (coin haut-gauche libéré) — **suivi ≠ liké** (liké = bordure verte + boutons ; suivi = ce nouvel indicateur). Nécessite `following` dans le endpoint liste.

**Mon « autre chose » (Claude)** :
1. **Filtre « Suivis »** dans la SegFilter (à la place de « Rating ») — cohérent avec l'ajout de la visibilité follow : voir / prioriser les artistes suivis.
2. *(option)* **Suivre directement depuis la card** (toggle follow, comme le like/dislike) — suivre sans ouvrir la fiche.
3. Le coin libéré par le retrait du badge in-lib accueille l'**indicateur « suivi »**.

**Réponses (William)** : in-lib overlay retiré (stat gardé) · suivi = **pastille qui sert aussi de bouton toggle** (follow/unfollow depuis la card) · tri « Rating » → filtre « Suivis ».

## 4. Ré-allocation des points retirés
- **Rating** (badge + option de tri + `avg_rating`) → suppression globale (transverse).
- **Badge in-lib overlay** → supprimé (doublon) ; **stat « In Lib » gardé**.
- Rien à déplacer vers d'autres pages.

## 5. Décisions figées
- **Card gardée** (photo + cover en fond + couleur de genre).
- **In-lib** : badge overlay **retiré** ; **stat « In Lib » gardé** (à côté de Catalog).
- **Rating** : retiré **partout** (badge haut-droit + option de tri « Rating » + `avg_rating`).
- **Suivi = pastille-toggle** sur l'art (coin haut-gauche libéré) : affiche l'état suivi **et** sert de **bouton follow/unfollow** directement depuis la card. Suivi ≠ liké (liké = bordure verte + like/dislike ; suivi = cette pastille).
- **Filtre « Suivis »** dans la SegFilter (remplace « Rating »).
- **Infinite scroll** (`usePaginatedList`) conservé.
- **(recap C5)** : **nb_liked** en 3e stat (« N ajoutés depuis le radar », déjà renvoyé) ; **toggle « sans Deezer »** (cibler le backlog des ~1000 artistes non liés).

## 6. Sortie next-step
**Handoff Design**
- [ ] Card : retrait badges in-lib overlay + rating ; **pastille-toggle « Suivi »** (états suivi/non-suivi + affordance bouton) sur l'art.

**Chantier work_manager**
- **Front** : `ArtistCard` — retrait badges in-lib overlay + rating ; **pastille-toggle follow** (POST/DELETE `/api/artists/{id}/follow`) ; SegFilter « Rating » → « Suivis » ; retrait du tri rating.
- **Back** : `following` ajouté à `ArtistListItemOut` ; filtre `followed=true` sur `/api/artists/` ; retrait `avg_rating` (via chantier transverse Rating).
- **Transverse** : suppression Rating.

**Dépend de** : suppression Rating (transverse). Sinon autonome.

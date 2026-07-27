# Artistes (liste) — `/artists`

Statut : ✅ figé  |  Vue : `views/ArtistsView.vue` + `components/ArtistCard.vue`

> **Précisions pré-vol 2026-07-27 (chantier liste Artistes) — priment sur le reste de la fiche en cas d'écart.**
> Vérifs prod (SQL read-only) + arbitrages William avant le prompt Design :
> - **Follow — données quasi-vides mais feature GARDÉE.** Prod : **3 artistes suivis** (1 user) sur 57 687. William tranche : garder la **pastille-toggle « Suivi »** ET le **filtre « Suivis »** — la pastille EST le moyen de suivre (aujourd'hui il faut ouvrir la fiche → d'où le vide) ; feature live qui alimente le Hub « Nouveautés ». **Non-suivi = état normal de la quasi-totalité des cards, ce n'est pas un repli à masquer.**
> - **Recap C5 — seul le toggle « sans Deezer » retenu.** **534** artistes `deezer_id IS NULL` (cible réelle ; param back `no_deezer` déjà existant). Le **nb_liked en 3e stat est REPORTÉ** en backlog : données quasi-nulles (**39** artistes sur 57 k) + surcharge la card. → la card garde **2 stats (Catalog · In Lib) + avis**.
> - **Rating — retrait PAGE-SCOPED.** Sur les seules surfaces Artistes-liste (badge card + tri « Rating » + `avg_rating` du endpoint/service liste). Le drop de colonne DB global reste un transverse séparé (précédent Explorer/Track Detail).
> - **État code réel vs fiche §1** : endpoints `POST/DELETE /artists/{id}/follow` **déjà là** · param `no_deezer` **déjà là** · `nb_liked` **déjà renvoyé** (non affiché) · `following` **absent** du schéma liste (à ajouter, LEFT JOIN `followed_artists`) · filtre `followed=true` à ajouter · pas de migration.

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

## 7. Handoff Design (livré 2026-07-27) — décisions DA qui raffinent les décisions figées

Handoff versionné : `docs/refonte-ui/handoff-artists-list/` (BRIEF + README de provenance + check conformité PASS). Ces décisions **complètent** le §5, elles ne le contredisent pas.

- **A1 — Pastille « Suivi » TOUJOURS présente** (jamais hover-only), **opacité 0,5 au repos → 1 au survol de la card**. Non-suivi = **cloche filaire** `--overlay-text` sur disque `--overlay-soft` ; suivi = **cloche pleine** `--on-accent` sur disque `--accent` (seul mauve plein de la grille). Un contrôle qui affiche un état ne peut pas être masqué (sinon l'état non-suivi — quasi-totalité des cards — devient indécouvrable).
- **A2 — Icône = cloche** (veille/nouveautés). Explicitement **PAS étoile** (ex-rating) ni **« personne+ »** (confusion in-lib).
- **A3 — Suivi ≠ liké porté par 3 canaux** : emplacement (art haut-gauche vs body), couleur (`--accent` vs `--pos`), forme (cloche vs cœur). **Le suivi ne touche JAMAIS la bordure de la card** (réservée au liké + à la lecture).
- **A5 — Coin haut-droit laissé vide** après retrait du badge rating (rien n'y est déplacé).
- **A8 — Valeur « In Lib » en `--pos-ink` quand > 0** (« — » `--ink-3` sinon) : porte seule l'info de l'ex-badge overlay. Card = **2 stats (Catalog · In Lib) + avis** (nb_liked reporté).
- **A10 — Toggle « Sans Deezer » = interrupteur** en fin de rangée **FamilyChips** (`margin-left:auto`), pas dans le head. Off par défaut. Param `no_deezer`.
- **A12/A13 — Grille jamais 1 colonne** : `minmax(208px,1fr)` → `minmax(168px,1fr)` < 720 → **2 colonnes fixes** < 640. **Container query PAR card** (`container-type: inline-size`) : body empilé + 2ᵉ StyleTag masqué sous 190 px de card. (Diverge du code actuel qui passait à 1 col < 380 px.)
- **A7 — Anatomie art gardée, scrim allégé + radial central** (avatar mieux détaché, covers plus lisibles).
- **Empty « Suivis » vide** = seul empty à pastille accent + bouton « Voir tout le catalogue » : porte l'onboarding de la nouveauté (100 % des users le verront au 1er clic, 3 suivis en prod).

**Lot back confirmé (léger, pas de migration)** : `following` dans `ArtistListItemOut` (LEFT JOIN `followed_artists`) · filtre `followed=true` · retrait `avg_rating` **page-scoped** (schéma/service/endpoint liste + tri). Endpoints follow + param `no_deezer` **déjà en prod**.

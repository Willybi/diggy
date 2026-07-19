# Détail artiste — `/artist/:id`

Statut : ✅ figé (bio + albums = slots futurs)  |  Vue : `views/ArtistDetailView.vue`

## 1. Ce qu'on a (actuel)

Encore une **refonte** : la page couvre déjà l'essentiel de la vision.

**Données** : `GET /api/artists/{id}` (`ArtistDetailOut` : id, name, deezer_id, trackid_id, has_artwork, **aliases**, genres, **catalog_tracks** [CatalogEntryOut], **sets** [ArtistSetOut], **stats** {nb_catalog, nb_lib, nb_sets, **avg_rating**}, following). + `GET /api/artists/{id}/connections` (`ArtistConnectionOut` : score + **components** collabs/sets/playlists/style + **shared_tracks/sets/playlists**). Follow via `POST/DELETE /api/artists/{id}/follow`. Admin Deezer link via `/api/admin/artists/…`.

**Structure actuelle** :
1. **Hero banner** : montage 6×2 des covers du catalog + scrim + nom (blanc), avatar rond débordant. Sous : sous-titre (real_name · country), genres StyleTags → `/style`, actions (**Écouter un aperçu** = preview random, **Suivre/Suivi**, liens **Deezer / SoundCloud / TrackID**).
2. **StatStrip** : Catalog · In lib · Sets · **Rating moy.**
3. **Aliases** (si présents).
4. **Biographie** (artist.bio).
5. **Tracks** (grid 2 col, 10 + « afficher les N autres » ; mini-rows : cover / title / artists / style / bpm / key / durée / play / lib dot).
6. **Artistes proches** (`ExpandableShelf`, `ShelfCard` rond → `/artist`).
7. **Sets** (si présents) : thumb, titre, sous-titre (date / B2B / identifiées), `RingPct`.
8. **Admin** (recherche/lien/délier Deezer) — **visible par tous**.

**Dette / divergences (factuel)** :
- ⚠️ **Blocs morts** : `ArtistDetailOut` **ne renvoie plus** `real_name`, `country`, `bio`, `soundcloud_id` (retirés en AU3, données encore en DB). Donc **le sous-titre (real_name · country), la Biographie et le lien SoundCloud ne s'affichent jamais** → code mort à trancher.
- **Rating moy.** (StatStrip + `avg_rating` — présent aussi dans la **liste** artistes) → à retirer (transverse).
- ~~**Admin visible par tous** (pas de garde `is_admin`)~~ — **OBSOLÈTE (vérifié 2026-07-20)** : `AdminCard.vue` s'auto-gate déjà `v-if="auth.user?.is_admin"`. Rien à faire (même conclusion que Track detail).
- Mini-rows tracks + shelf artistes proches = bespoke → candidats aux **composants partagés** (`<TrackCard>` compact, shelf/card partagé, `<Artwork>` in-lib).
- Pas de section **Albums** (roadmap).

## 2. Vision (William)

- **Bandeau** avec plein d'infos de base (comme Track detail).
- **Liste des tracks**.
- **Retirer le rating** (prévu).
- **« Artiste proche »** gardé.
- Section **Sets** si elle existe.
- Section **Albums** à prévoir : l'**objet album** est en roadmap → prévoir le slot **et** sa future **page détail album**. ⚠️ **un single n'est pas un album** — à distinguer.
- Pas d'autres idées pour l'instant.

## 3. Revue de cohérence (Claude)

**Structure proposée** (ton ordre, poli) :
1. **Hero banner** (garder — il est réussi) : montage + avatar + nom + genres + actions (écouter, suivre, liens externes).
2. **StatStrip** : Catalog · In lib · Sets (**Rating moy. retiré**).
3. **Aliases** (si présents).
4. **Tracks** → `<TrackCard>` compact + `<Artwork>` in-lib.
5. **Albums / Sorties** (NOUVEAU, futur) — regroupe les **vraies sorties** (album/EP) ; **singles exclus** (ils restent dans Tracks). Dépend de l'objet album (roadmap) + **future page détail album** (à ajouter au registre).
6. **Sets** (si présents) — garder.
7. **Artistes proches** — garder ; *(option)* afficher le **« pourquoi »** (X tracks / Y sets en commun — la donnée est déjà dans `connections`).
8. **Admin** — gardé **`is_admin`**.

**Keep / Improve / Remove**
- ✅ **Garder** : hero, tracks, artistes proches, sets, follow, liens externes, écouter un aperçu, aliases.
- ➕ **Améliorer** : mini-rows → `<TrackCard>` compact + `<Artwork>` in-lib ; shelf artistes proches → composant partagé ; *(option)* « pourquoi » sur artistes proches ; **section Albums**.
- ➖ **Retirer** : Rating moy. (transverse) ; AdminCard → gardée `is_admin` ; **blocs morts** (bio / real_name / country / soundcloud) → droper **ou restaurer** (voir questions).

**Réponses (William) & précision données**
1. **Bio** : voulue → mais ⚠️ la colonne `artists.bio` existe **et n'est peuplée par aucun code** (aucune écriture ; Deezer ne fournit pas de bio). Ce n'est **pas un simple ré-affichage** : il faut **une source** (Wikipedia / MusicBrainz / Discogs / Last.fm). → **feature future « Bio artiste (source à définir) »**, slot réservé. **Pays / real_name / SoundCloud : dropés** (morts + non voulus).
2. **Albums** : ✅ slot **après Tracks** (futur, objet album roadmap) ; **single ≠ album** (singles → Tracks, album/EP → Albums) ; **Tracks = TOUTES les tracks** (y compris celles des albums) ; fiche « Détail album » future ajoutée au registre.
3. **Artistes proches** : **avatar + nom** suffisent (pas de « pourquoi »).

## 4. Ré-allocation des points retirés
- **Rating** → suppression globale (transverse).
- **Admin** → restreint `is_admin` (reste sur la page).
- **Blocs morts** real_name / country / soundcloud → **supprimés**.
- **Bio** → **feature future** (source à définir), slot réservé dans le layout.
- **Albums** → **nouvelle section future** + **fiche « Détail album »** au registre.

## 5. Décisions figées
- **Structure** : Hero → StatStrip (sans Rating) → Aliases → Tracks → *[Albums/Sorties — futur]* → Sets → Artistes proches → Admin (`is_admin`).
- **Hero** : garder le banner ; **retirer** le sous-titre real_name · country + le lien SoundCloud (morts) ; garder liens **Deezer / TrackID** + **Suivre** + **Écouter un aperçu**.
- **Bio** : **feature future** — colonne vide, aucune source branchée ; nécessite une source (Wikipedia / MusicBrainz / Discogs / Last.fm). Slot réservé, non livrable tant que la source n'est pas choisie.
- **Rating moy.** retiré (StatStrip + liste artistes).
- **Admin** → `is_admin`.
- **Tracks** : `<TrackCard>` compact + `<Artwork>` in-lib ; **liste = toutes les tracks** (albums inclus).
- **Albums / Sorties** : section **future** ; **album/EP uniquement** (singles restent dans Tracks) ; dépend de l'objet album (roadmap) ; **page « Détail album »** future.
- **Artistes proches** : avatar + nom (shelf/card partagé), pas de « pourquoi ».
- **Aliases** : gardé.

## 6. Sortie next-step
**Handoff Design**
- [ ] Hero poli (sans sous-titre mort) ; **slot bio** réservé.
- [ ] Tracks → `<TrackCard>` compact + `<Artwork>` ; shelf artistes proches → composant partagé.
- [ ] Emplacement de la section **Albums** (future).

**Chantier work_manager**
- **Front** : retrait Rating (StatStrip) ; **garde `is_admin`** sur l'Admin ; retrait des blocs morts (real_name / country / soundcloud) ; mini-rows → `<TrackCard>` ; shelf partagé.
- **Back** : rien de bloquant pour la refonte immédiate. **Futurs** : objet **album** (roadmap) ; feature **Bio** (source + peuplement).
- **Transverse** : composants partagés ; suppression Rating.

**Dépend de** : composants partagés ; objet album (section Albums) ; source bio (feature Bio).

## 7. Arbitrages pré-vol (2026-07-20 — avant prompt Design)

Vérification code réel vs fiche (leçon Track Detail : les dettes peuvent être obsolètes). Conclusions figées :

- **Admin `is_admin`** : DÉJÀ FAIT — `AdminCard.vue` s'auto-gate (dette §1 obsolète). Bloc hors design.
- **Blocs morts CONFIRMÉS** : `ArtistDetailOut` n'expose ni `real_name`/`country`/`bio`/`soundcloud_id` → le sous-titre hero (real_name·country), le bloc Biographie et le lien SoundCloud sont du code réellement mort → **supprimés**.
- **Rating moy.** : retiré de la StatStrip (front). Le drop back global (colonne + `ArtistListOut` + `ArtistCard`) reste le chantier **transverse** Rating, hors périmètre de cette page.
- **Composants transverses : TOUS présents** (`Artwork`, `TrackCard` ligne étendu, `ScoreRing` pct, `PlatformLink`, `SetCard`, `ShelfCard`, `ExpandableShelf`). **Aucun nouveau composant à créer** → pas de lot transverse. « Artistes proches » utilise **déjà** `ShelfCard`+`ExpandableShelf` (polish visuel seulement, pas de « pourquoi » — figé).
- **Tracks → `<TrackCard>` ligne** (`showArtist` + `showDuration`), in-lib via `<Artwork>`. La colonne genre par ligne **disparaît** (cohérent avec Playlist/Set Detail). Conserve l'expand « 10 + afficher les N autres ».
- **Hero liens externes → `<PlatformLink>` logos** (Deezer + TrackID) au lieu des boutons texte (décision transverse logos).
- **StatStrip** : latitude DA de **replier les stats dans le hero** (précédent Track/Playlist/Set) OU garder une strip séparée — les stats (Catalog · In lib · Sets) restent, seul le contenant est DA.
- **Section Sets → `<SetCard>` grille** (décision William 2026-07-20 ; cohérence avec « Sets similaires » de Set Detail). **Ouvre un lot back 0** : ajouter `artists[]` (noms) + `duration_ms` à `ArtistSetOut` + les peupler dans `artist_service` (aujourd'hui absents). Le % identifiées passe dans le slot `#footer` de `SetCard` (`ScoreRing` pct ou badge — DA).
- **Slots futurs** (Bio, Albums/Sorties) : emplacements **réservés seulement**, non construits (dépendent de la source bio et de l'objet album C7).
- **Back refonte immédiate** : rien d'autre que le lot Sets ci-dessus. `CatalogEntryOut` porte déjà tout pour `<TrackCard>` ; hero/connections/follow inchangés.

## 8. Décisions handoff (2026-07-20 — round unique Claude Design)

Handoff versionné dans `docs/refonte-ui/handoff-artist-detail/` (BRIEF + pilote + README de conformité). Décisions DA actées :

- **Stats repliées dans le hero** (data-row mono Catalog · In lib · Sets) — pas de StatStrip séparée (A2, aligné Track/Playlist/Set).
- **Montage banner** : 1-11 covers → tuiles cyclées ; catalog vide → bande placeholder rayé, scrim conservé (A3).
- **Footer `<SetCard>` = badge sobre** « NN % identifiées » — pas de `ScoreRing pct` en grille (discipline accent, A5). Grille 4 → 3 (<720) → 2 (<640).
- **Artistes des SetCard joints par « , »** (spec canonique consommée telle quelle) ; `role` d'import jamais affiché (A7).
- **Avatar** : ring 3 px `--surface` ; < 640 px en flux, 72 px (A4).
- **« Artiste introuvable »** enrichi d'un bouton « Retour aux artistes ».
- **Aucun composant créé, aucune extension** — consommation pure des transverses en prod.

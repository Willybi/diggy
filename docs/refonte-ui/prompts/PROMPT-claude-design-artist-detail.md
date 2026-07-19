# Prompt — Claude Design · Refonte Artist Detail (D4, page 4)

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `server/frontend/src/styles/diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/artist-detail.md` (fiche de cadrage figée — décisions produit + **arbitrages pré-vol §7 du 2026-07-20**)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — composants partagés, logos plateformes, Rating supprimé)
> - `docs/refonte-ui/handoff-track-detail/BRIEF-composants-transverses.md` (**spec canonique** de `<Artwork>` / `<TrackCard>` ligne / `<ScoreRing>` / `<PlatformLink>` — cette page les CONSOMME)
> - `docs/refonte-ui/handoff-playlist-detail/BRIEF-trackcard-extension.md` (extension `<TrackCard>` durée + artistes cliquables, **LIVRÉE et en prod** — la liste Tracks la consomme)
> - `docs/refonte-ui/handoff-set-detail/SPEC-set-card.md` (**spec du composant `<SetCard>`** — la section « Sets » de cette page le CONSOMME tel quel)
> - `docs/refonte-ui/handoff-set-detail/BRIEF-set-detail.md` (référence de **FORMAT uniquement** — son contenu est spécifique à Set Detail, ne pas le transposer)
> - (optionnel) screenshot de la page actuelle `/artist/:id`

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark mode par défaut, tokens centralisés). Refonte UI page par page : chaque page est cadrée produit dans une fiche figée, tu produis le **handoff purement design** (brief + maquette) qu'un agent d'implémentation appliquera tel quel.

**Page 4 : Détail artiste — `/artist/:id`** (ArtistDetailView). La fiche d'un artiste : un **hero-bannière** (montage des covers de son catalog + avatar rond débordant + nom), ses genres, des actions (écouter un aperçu, suivre, liens externes), ses **tracks**, ses **sets** (où il a joué), et les **artistes proches** (moteur de proximité). C'est une **refonte** d'une page déjà réussie (le hero-bannière est aimé, on le garde) : on la **polit**, on **supprime le code mort**, on **migre les rangées bespoke vers les composants partagés**, et on **remplace la section Sets par des cartes**.

**Composants transverses : TOUT existe déjà en prod** — `<Artwork>` (cover + placeholder rayé + point in-lib en coin), `<TrackCard>` ligne (extension durée + artistes cliquables incluse), `<ScoreRing>` (note /10 + mode `pct`), `<PlatformLink>` (logos monochromes, map couvre deezer/soundcloud/trackid/…), `<SetCard>` (carte set verticale réutilisable), `<ShelfCard>` + `<ExpandableShelf>` (étagère horizontale paginée). **Tu les consommes, tu ne les re-spécifies pas. Aucun nouveau composant transverse n'est attendu sur cette page.**

**Périmètre strict : design/UX uniquement.** Les données listées plus bas sont exhaustives — ne rien inventer au-delà.

## Décisions produit FIGÉES (fiche jointe, §5 + §7 — à respecter, pas à rediscuter)

1. **Structure verticale** : Hero → **StatStrip** (Catalog · In lib · Sets) → Aliases (si présents) → *[slot Bio — futur, réservé]* → **Tracks** → *[slot Albums/Sorties — futur, réservé]* → **Sets** → **Artistes proches** → Admin. Le bloc **Admin est hors design** (composant existant, déjà gaté `is_admin`) — mentionne-le juste en bas de l'ordre vertical.

2. **Hero** (garder le banner, il est réussi) : **montage des covers** du catalog (grille de tuiles) + **scrim** + **nom** en blanc, **avatar rond** débordant. Sous le banner : **genres** en `StyleTag` cliquables (`/style/{name}`), puis une rangée d'**actions** :
   - **« Écouter un aperçu »** (bouton accent — lance un preview aléatoire de l'artiste),
   - **Suivre / Suivi** (bouton, état `following` — présent seulement si authentifié, mais rappel : **pas d'état invité à concevoir**, la page est toujours authentifiée),
   - **liens externes** = **logos `<PlatformLink>`** : **Deezer** (si `deezer_id`) + **TrackID** (si `trackid_id`). Plus de bouton texte, plus de lien SoundCloud.
   - **RETIRÉ (code mort, ne pas faire revivre)** : le sous-titre `real_name · country` et le lien **SoundCloud** (`ArtistDetailOut` ne les renvoie plus).
   - **Latitude DA** : comme sur le pilote Track Detail (et Playlist/Set), tu peux **replier les stats de la StatStrip dans le hero** ou garder une StatStrip séparée — les stats (Catalog · In lib · Sets) restent, seul leur contenant/placement est ta décision. Composition, proportions et traitement du banner (option fond/scrim) = latitude DA.

3. **Rating moy. RETIRÉ** de la StatStrip (décision transverse « Rating supprimé »). Il ne reste que **Catalog · In lib · Sets**.

4. **Tracks** : rangées `<TrackCard>` ligne (`showArtist` + `showDuration`), cover + in-lib via `<Artwork>`. **Pas de StyleTag par ligne** (cohérent avec Playlist/Set Detail). Liens : titre → `/catalog/:id`, artistes → `/artist/:id`. Conserve l'**expand progressif** : 10 tracks visibles + bouton « Afficher les N autres tracks », et une note « … et N autres » si le catalog total dépasse les tracks chargées. En-tête de section avec compteur (`nb_catalog`).

5. **Sets** (NOUVEAU rendu) : **grille de cartes `<SetCard>`**, clic → `/set/:id`. Section **masquée si vide**. La carte affiche artwork, titre, artistes, méta (date · durée · N tracks — nulls omis, cf. spec `SetCard`) ; le **% identifiées** va dans le slot `#footer` de la carte — **`<ScoreRing mode="pct">`** (valeur `identified_tracks/total_tracks`) **ou** un badge sobre, ton choix DA. En-tête avec compteur (`nb_sets`). *(Base réutilisable : cette carte sert aussi la future liste `/sets`.)*

6. **Artistes proches** : **`<ShelfCard variant="round">`** (avatar + nom) dans un **`<ExpandableShelf>`**, clic → `/artist/:id`. **Avatar + nom UNIQUEMENT** — **pas** de score, **pas** de « pourquoi » (X tracks / Y sets en commun) : décision figée. Polish visuel seulement (la structure partagée est déjà en place).

7. **Aliases** : conservé — liste texte simple des alias (si présents).

8. **Slots futurs** (Bio, Albums/Sorties) : **emplacements réservés seulement** — indique **où** ils s'insèrent (Bio après Aliases, Albums après Tracks), **ne les conçois pas comme livrables**. La Bio dépend d'une source externe non branchée ; les Albums dépendent de l'objet album (roadmap). Un simple repère de layout suffit.

## Ce que tu dois livrer

### 1. `BRIEF-artist-detail.md` — le handoff de la page

Même format que les briefs existants (tableaux de tokens, anatomie, états, décisions DA explicites). Doit couvrir :

- **Hero** : anatomie complète (montage de covers + son fallback quand peu/pas de covers, scrim, nom, avatar rond `has_artwork=false` → initiale, genres StyleTags, actions avec logos `<PlatformLink>`). Cas : **0 genre** (masquer la rangée), **artiste sans deezer_id / sans trackid_id** (masquer le logo correspondant), **catalog vide** (montage sans tuiles → traitement du banner « vide »). Précise ton choix StatStrip repliée-dans-le-hero vs séparée.
- **StatStrip** (si conservée séparée) : Catalog · In lib · Sets, mono pour les nombres. Sinon documente l'intégration hero.
- **Tracks** : rangée `<TrackCard>` (états : normale, playing, hover, in-lib ±, `has_preview` absent = pas de play, BPM/KEY/durée absents = tirets), l'expand « 10 + N autres » et la note « … et N autres ». Aucune colonne genre.
- **Sets** : grille `<SetCard>` (anatomie de la carte via sa spec jointe), traitement du footer % identifiées (ScoreRing pct ou badge), responsive de la grille, section masquée si vide, artwork absent (`has_artwork=false` → placeholder), 0 / 1 / N artistes (séparateur B2B), date/durée nulles (omises).
- **Artistes proches** : `<ShelfCard variant="round">` (avatar → initiale si `has_artwork=false`), comportement `<ExpandableShelf>` (aperçu 12 + expand paginé). Rappel : avatar + nom seulement.
- **Aliases** : rendu de la liste (si présents).
- **États page** : loading (utilitaire global `.state` : « Chargement… »), artiste introuvable (« Artiste introuvable. »).
- **Responsive** : container queries (`@container`), pilote sur 375px. Convention repo : breakpoints **720px / 640px** en `max-width` **exclusif**. Play toujours visible < 640px (pas de hover mobile). Précise le comportement du hero-bannière + avatar en étroit (l'actuel fait passer l'avatar « en flux » sous le banner < 640px) et la retombée de colonnes des `<TrackCard>` (durée tombe < 640px par défaut du composant).
- **Pas d'état invité** : les invités sont confinés au Hub, cette page est toujours authentifiée.

### 2. `Artist Detail (pilote).html` — maquette interactive

Maquette HTML autonome consommant les tokens de `diggy-tokens.css` (zéro couleur hardcodée), avec :
- la page complète (hero, StatStrip, aliases, tracks, sets, artistes proches) avec des données réalistes d'artiste DJ,
- les variantes/états clés visibles : hero avec/sans avatar, catalog riche vs pauvre (montage vide), rangée track playing / sans preview / méta absente, grille de sets pleine **et** section masquée, artistes proches en aperçu et déplié,
- toggle **dark/light**, toggle **viewport desktop / 375px**.

> **Aucun `BRIEF-composants-transverses` ni spec de nouveau composant attendus** : la page ne crée aucun composant. Si — et seulement si — tu estimais qu'un composant existant doit évoluer, ce serait une **extension additive** documentée à part avec la contrainte dure « zéro régression pour les consommateurs en prod » ; mais l'attendu est **zéro extension** (tout est déjà couvert).

## Données disponibles (exhaustif — ne rien inventer au-delà)

> ⚠️ Contrat **cible** : les champs marqués ✦ sont livrés par le lot back du même chantier (arbitré le 2026-07-20) — disponibles avant l'implémentation front. Tout le reste est déjà en prod.

`GET /api/artists/{id}` → `ArtistDetailOut` :
- `id`, `name`, `deezer_id` (nullable), `trackid_id` (nullable), `has_artwork`, `created_at` (nullable)
- `aliases[]` : `{ id, artist_id, alias, normalized_alias }`
- `genres[]` : `GenreRef` `{ name, pillar, depth }` (→ `<StyleTag :name :family=pillar :depth>`, lien `/style/{name}`)
- `catalog_tracks[]` : `CatalogEntryOut` — champs utiles : `id`, `title`, `artist` (fallback chaîne), `artists[]` `{ id, name, role, has_artwork }`, `bpm` (nullable), `key` (nullable), `duration_ms` (nullable), `has_artwork`, `has_preview`, `in_lib`. *(genres présents mais NON affichés en ligne — décision figée.)*
- `sets[]` : `ArtistSetOut` — `set_id`, `title`, `played_date` (nullable), `role` (nullable : `dj`/`b2b`/`live`), `has_artwork`, `total_tracks`, `identified_tracks`, ✦`artists[]` (liste de **noms**), ✦`duration_ms` (nullable)
- `stats` : `{ nb_catalog, nb_lib, nb_sets }` *(l'ancien `avg_rating` est retiré de l'affichage)*
- `following` : bool

`GET /api/artists/{id}/connections` → `list[ArtistConnectionOut]` : `artist_id`, `name`, `has_artwork`, `genres[]`, `score` (0..1), `components{collabs,sets,playlists,style}`, `shared_tracks`, `shared_sets`, `shared_playlists`.
→ Pour « Artistes proches » on **n'utilise que** `artist_id`, `name`, `has_artwork` (avatar + nom). `score` / `components` / `shared_*` **ne sont pas affichés** (figé).

Actions : `POST /api/artists/{id}/follow` / `DELETE …/follow` (toggle Suivre). Admin (hors design) : recherche/lien Deezer via `/api/admin/artists/…`.

**Chemins artwork** :
- Avatar artiste : `/storage/artist-artworks/{id}.jpg` si `has_artwork`.
- Montage hero + covers tracks : `/storage/catalog-artworks/{catalog_id}.jpg`.
- Artwork set (cartes `<SetCard>`) : `/storage/set-artworks/{set_id}.jpg`.

## Design system — contraintes (rappel)

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. Zéro couleur hardcodée.
- **Typo** : `--font-ui` (Space Grotesk) pour le texte, `--font-mono` (JetBrains Mono) pour les données numériques (BPM, key, durées, dates, compteurs, %).
- **Thèmes** : `[data-theme="dark"]` par défaut + light — la maquette supporte les deux (attention au scrim du banner en light).
- **Responsive** : container queries (`@container`), jamais `@media` sauf éléments `position: fixed`. La page vit dans `.detail-view` (max-width `--detail-max-w`, `container-type: inline-size`). **Convention repo : breakpoints 720px / 640px en `max-width` exclusif** — s'y tenir.
- **CSP stricte** : logos/icônes en SVG inline ou data-URI, aucun CDN, aucune image externe.
- **Monochrome plateformes** : `<PlatformLink>` en `currentColor`, jamais les couleurs de marque (décision D6).
- **UI en français.**

## Récapitulatif des livrables

| Fichier | Contenu |
|---------|---------|
| `BRIEF-artist-detail.md` | Handoff page : hero poli (code mort retiré, logos plateformes), StatStrip sans Rating, tracks `<TrackCard>`, sets en grille `<SetCard>`, artistes proches, aliases, slots futurs, états, responsive, tokens |
| `Artist Detail (pilote).html` | Maquette interactive (page + variantes/états, toggles theme/viewport) |

**Livraison** : en fin de round, fournis tous les livrables dans une **archive zip téléchargeable** (un seul lien de téléchargement), en plus de leur affichage dans la conversation.

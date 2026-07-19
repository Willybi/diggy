# Prompt — Claude Design · Refonte Set Detail (D4, page 3)

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `server/frontend/src/styles/diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/set-detail.md` (fiche de cadrage figée — décisions produit, incluant les arbitrages pré-vol du 2026-07-17)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — composants partagés)
> - `docs/refonte-ui/handoff-track-detail/BRIEF-composants-transverses.md` (**spec canonique des composants existants** `<Artwork>` / `<TrackCard>` ligne / `<ScoreRing>` / `<PlatformLink>` — cette page les CONSOMME)
> - `docs/refonte-ui/handoff-playlist-detail/BRIEF-trackcard-extension.md` (extension `<TrackCard>` durée + artistes cliquables, **LIVRÉE et en prod** — la tracklist set la consomme ; toute nouvelle extension suit le même modèle additif)
> - `docs/refonte-ui/handoff-playlist-detail/BRIEF-playlist-detail.md` (référence de **FORMAT uniquement** — son contenu est spécifique à Playlist Detail, ne pas le transposer)
> - (optionnel) screenshot de la page actuelle `/set/:id`

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark mode par défaut, tokens centralisés). Refonte UI page par page : chaque page est cadrée produit dans une fiche figée, tu produis le **handoff purement design** (brief + maquette) qu'un agent d'implémentation appliquera tel quel.

**Page 3 : Détail set — `/set/:id`** (SetDetailView). Un **set DJ** importé de TrackID.net (captures radio, livestreams, sets communautaires) : artwork, artiste(s)-DJ, date, durée, et une **tracklist horodatée partiellement identifiée** (des rangées sont « ID » = non identifiées, d'autres pointent vers le catalog). C'est la page la **moins aimée** du site — peu d'infos, froide. Objectif produit : la rendre **plus vivante et immersive**. C'est une **refonte, pas une création** : la structure verticale reste proche, mais le hero est repensé, la tracklist enrichie, et une section « Sets similaires » apparaît.

**Composants transverses : tout existe déjà en prod** — `<Artwork>` (cover + placeholder rayé + point in-lib en coin), `<TrackCard>` ligne (avec extension durée + artistes cliquables), `<ScoreRing>` (note /10), `<PlatformLink>` (logos monochromes ; sa map couvre déjà youtube / soundcloud / trackid / 1001tracklists — rien à créer). Tu les consommes, tu ne les re-spécifies pas.

**Périmètre strict : design/UX uniquement.** Les données listées plus bas sont exhaustives — ne rien inventer au-delà.

## Décisions produit FIGÉES (fiche jointe — à respecter, pas à rediscuter)

1. **Structure verticale** : Hero immersif → Tracklist enrichie → **Sets similaires** → Admin. Le bloc Admin est **hors design** (composant existant, déjà gaté `is_admin`) — mentionne-le juste en bas de l'ordre vertical.
2. **Hero immersif** : artwork set **plus grand** qu'aujourd'hui (latitude DA : option fond flouté généré depuis la cover), titre, **artistes-DJ cliquables** (`/artist/:id` — B2B possibles : 0, 1 ou N artistes), **genres déduits** en `StyleTag` cliquables (`/style/{name}`), bande d'infos **Durée · Date · Tracks**, **% identifiées en ring discret** (la grosse cellule « Identifiées » de l'actuelle StatStrip disparaît), **lien source en logo** via `<PlatformLink>` (plus de bouton texte « Voir sur … »). Latitude DA : composition, proportions, placement de la bande d'infos (le pilote Track Detail a intégré les stats au hero — tu peux faire pareil ou non).
3. **Genres du set** : **déduits des tracks identifiées** (`top_genres[]`, cap 5, name/pillar/depth/pct). Le set n'a **aucun genre propre**.
4. **Tracklist enrichie, SOBRE** : # (position) · play · cover + in-lib (`<Artwork>`) · titre · artiste(s) cliquable(s) · **BPM · KEY · durée** · **timecode cliquable** (→ source horodatée, feature appréciée à préserver) · état ID. **Pas** de StyleTag par ligne. Base = `<TrackCard>` ligne étendu (durée + artistes déjà livrés) ; il **manque** au composant : position, timecode, état ID/non-identifié. **À toi de trancher** : extension additive de `<TrackCard>` (alors spec autonome séparée, contrainte dure : zéro changement pour Track Detail et Playlist Detail en prod) OU rangée dédiée à la page réutilisant `<Artwork>` (alors documentée dans le brief page). Documente ton choix et sa raison.
5. **Sets similaires** (NOUVEAU, bas de page) : sets proches calculés par le moteur de proximité global agrégé au niveau set (tracklists recouvrantes/proches). **Cap 8**, section **masquée si vide**. Le `score` de proximité est exposé par l'API : **l'afficher ou non est ta décision DA** (une section sobre sans score est légitime ; `<ScoreRing>` existe si tu veux l'afficher).
6. **Retiré** : event / venue / description (champs morts, déjà purgés du back — ne les fais pas revivre).

## Ce que tu dois livrer

### 1. `BRIEF-set-detail.md` — le handoff de la page

Même format que les briefs existants (tableaux de tokens, anatomie, états, décisions DA explicites). Doit couvrir :

- **Hero** : anatomie complète (artwork agrandi, option fond flouté et son traitement dark/light, titre, artistes-DJ, StyleTags genres, bande d'infos, ring % identifiées, logo source). Cas : `has_artwork=false` (placeholder), 0 / 1 / N artistes (séparateur B2B), `top_genres` vide (0 track identifiée — masquer les tags), `played_date` / `duration_ms` null, `source_url` null (pas de lien source).
- **Ring % identifiées** : géométrie — la cible TRANSVERSE est d'aligner les % sur la géométrie de `<ScoreRing>` (mode %) ; l'existant `RingPct` reste dispo. Spécifie ton choix : variante % de `<ScoreRing>` (alors spec additive courte) ou `RingPct` tel quel.
- **Tracklist** : tous les états de rangée — identifiée (liens titre → `/catalog/:id`, artistes → `/artist/:id`), **ID** (non identifiée : « ID / non identifié », visuellement en retrait), **non résolue** (raw_title/raw_artist sans lien), BPM/KEY/durée **absents** (fréquent — enrichissement partiel), timecode absent, timecode **non cliquable** (source non horodatable), in-lib ±, playing, hover. En-tête de section avec compteur.
- **Sets similaires** : carte set (artwork `<Artwork>`, titre, artistes, date, durée, tracks — champs exacts plus bas), grille ou rangées, clic → `/set/:id`, affichage ou non du score, responsive.
- **États page** : loading (utilitaire global `.state`), set introuvable.
- **Responsive** : container queries (`@container`), pilote sur 375px. Play toujours visible < 640px (pas de hover mobile). Spécifie quelles colonnes de la tracklist tombent en étroit (aujourd'hui le timecode disparaît < 640px — à toi de re-trancher).
- **Pas d'état invité** : les invités sont confinés au Hub, cette page est toujours authentifiée.

### 2. (si tu étends `<TrackCard>`) `BRIEF-trackcard-extension-set.md`

Spec **additive** autonome, même modèle que `BRIEF-trackcard-extension.md` joint : position, timecode cliquable, état ID/non-identifié — tout optionnel, **zéro changement de rendu pour les consommateurs actuels** (Track Detail + Playlist Detail en prod).

### 3. (si tu crées une carte set) spec autonome courte

La refonte de la liste `/sets` (page future) réutilisera cette carte — spécifie-la comme composant réutilisable, pas comme un fragment de la page.

### 4. `Set Detail (pilote).html` — maquette interactive

Maquette HTML autonome consommant les tokens de `diggy-tokens.css` (zéro couleur hardcodée), avec :
- la page complète (hero, tracklist, sets similaires) avec des données réalistes de set DJ,
- les variantes/états clés visibles : hero sans artwork, rangées identifiée / ID / non résolue, BPM-KEY absents, playing, section similaires pleine et masquée,
- toggle dark/light, toggle viewport desktop / 375px.

## Données disponibles (exhaustif — ne rien inventer au-delà)

> ⚠️ Contrat **cible** : les champs marqués ✦ sont livrés par le lot back du même chantier (arbitré le 2026-07-17) — disponibles avant l'implémentation front. Tout le reste est déjà en prod.

`GET /api/sets/{id}` : `id`, `external_id`, `source` (`trackid` majoritaire ; historiques `youtube` / `soundcloud` / `1001tracklists`), `source_url` (nullable), `title`, `played_date` (nullable), `duration_ms` (nullable), `has_artwork`, `created_at`, `last_crawled_at`, `total_tracks`, `identified_tracks`, `artists[]` (`artist_id`, `artist_name`, `has_artwork`, `role` nullable — `dj`/`b2b`/`live`, `position`), `tracklist[]` (`id`, `catalog_id` nullable, `position`, `timecode_ms` nullable, `raw_title`, `raw_artist`, `is_id`, `catalog_title`, `catalog_artist` chaîne fallback, `catalog_artists[]` (id, name, role, has_artwork), `has_artwork`, `in_lib`, `has_preview`, ✦`bpm`, ✦`key`, ✦`duration_ms`), ✦`top_genres[]` (`name`, `pillar`, `depth`, `pct` — cap 5, agrégé sur les tracks identifiées).

✦`GET /api/sets/{id}/similar` : liste de cartes set — `id`, `title`, `source`, `played_date`, `duration_ms`, `has_artwork`, `total_tracks`, `identified_tracks`, `artists[]` (noms), `score` (0..1, tri décroissant). Cap 8, peut renvoyer moins ou vide.

Artwork set : `/storage/set-artworks/{id}.jpg` si `has_artwork`. Covers tracks : `/storage/catalog-artworks/{catalog_id}.jpg`. Avatars artistes : `/storage/artist-artworks/{artist_id}.jpg`.

**Timecode cliquable** : construit côté front depuis `source_url` — possible **uniquement** YouTube (`?t=`) et SoundCloud (`#t=h:mm:ss`) ; pour `trackid` / `1001tracklists` / `source_url` null, le timecode est **texte non cliquable**. `% identifiées` = `identified_tracks / total_tracks`.

## Design system — contraintes (rappel)

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. Zéro couleur hardcodée.
- **Typo** : `--font-ui` (Space Grotesk) pour le texte, `--font-mono` (JetBrains Mono) pour les données numériques (BPM, key, durées, timecodes, dates, %).
- **Thèmes** : `[data-theme="dark"]` par défaut + light — la maquette supporte les deux (attention au fond flouté en light si tu retiens l'option).
- **Responsive** : container queries (`@container`), jamais `@media` sauf éléments `position: fixed`. La page vit dans `.detail-view` (max-width `--detail-max-w`, `container-type: inline-size`). **Convention repo : breakpoints 720px / 640px en `max-width` exclusif** — s'y tenir.
- **CSP stricte** : logos/icônes en SVG inline ou data-URI, aucun CDN, aucune image externe.
- **Monochrome plateformes** : `<PlatformLink>` en `currentColor`, jamais les couleurs de marque (décision D6).
- **UI en français.**

## Récapitulatif des livrables

| Fichier | Contenu |
|---------|---------|
| `BRIEF-set-detail.md` | Handoff page : hero immersif, ring % identifiées, tracklist enrichie, sets similaires, états, responsive, tokens |
| `BRIEF-trackcard-extension-set.md` *(si extension retenue)* | Spec additive `<TrackCard>` : position + timecode + état ID (optionnels, zéro régression) |
| Spec carte set *(si carte créée)* | Composant réutilisable pour la future liste `/sets` |
| `Set Detail (pilote).html` | Maquette interactive (page + variantes/états, toggles theme/viewport) |

**Livraison** : en fin de round, fournis tous les livrables dans une **archive zip téléchargeable** (un seul lien de téléchargement), en plus de leur affichage dans la conversation.

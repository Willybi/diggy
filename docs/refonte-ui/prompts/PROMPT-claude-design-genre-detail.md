# Prompt — Claude Design · Refonte Détail genre — `/style/:genre` (D6, dernière page)

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/genre-detail.md` (fiche de cadrage figée — décisions produit ; le bloc **« Pré-vol chantier 2026-08-02 » prime** en cas d'écart)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — composants partagés)
> - `docs/refonte-ui/handoff-artist-detail/BRIEF-artist-detail.md` (référence de **FORMAT uniquement** — brief le plus proche : **même paradigme page détail à hero immersif + shelves + tracklist** ; ⚠️ son **contenu** concerne l'Artiste — banner montage, stats repliées, aliases — qui **n'existe pas ici**, ne PAS le reprendre)
> - Captures de la page ACTUELLE (dossier `C:\tmp\captures-genre-detail\`) :
>   - `01-desktop-dark-full.png` — genre RICHE (« Techno (Raw / Deep / Hypnotic) », 15 664 tracks), desktop dark 1440px, pleine page : hero mosaïque 3×2 teintée pilier (avatars top-3 + play hover) avec **titre + pilier EN DESSOUS** (la dette), actions avec **« Tout filtrer dans Catalog »** (à retirer), **StatStrip 6 stats** (à absorber dans le hero), carte Admin **en haut** (à déplacer en bas), shelves Artistes/Sets (badge %)/Playlists (badge source TEXTE, à passer en glyph), tracklist `GenreTrackRow` bespoke (à remplacer par la rangée partagée).
>   - `02-desktop-light-full.png` — même vue, light.
>   - `03-mobile-375-dark.png` — mobile 375px : mosaïque 2×3 (140px), **titre tronqué** (« Techno (Raw / Deep / Hypnc… »), actions serrées sur 2 lignes, StatStrip qui déborde, BottomNav.
>   - `04-desktop-dark-genre-pauvre-trance.png` — genre MOYEN/PAUVRE (« Trance », 141 tracks, 7 en bib) : stats basses, rangées avec BPM/Key « — », volumes réalistes du bas de gamme.
>   - `05-desktop-dark-genres-proches.png` — bas de page : fin de tracklist + bloc **« Genres proches »** (chips StyleTag colorées + « N artistes en commun »), gardé tel quel dans l'esprit.

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark par défaut, tokens centralisés). La refonte page par page touche à sa fin : les 4 pages détail (Track, Playlist, Set, Artist) et les 7 pages D6 (Explorer, Radar, Hub, Sets, Playlists, Artistes, Genres liste) sont livrées. On refait la **dernière page : Détail genre**.

**Cette page : Détail genre — `/style/:genre`.** La page la **plus complète** du site, et William **l'aime déjà beaucoup**. Le mouvement n'est PAS une refonte de paradigme, c'est une **mise au niveau des autres pages détail** :

1. **Hero immersif** : la mosaïque s'agrandit et le **titre + pilier + stats clés passent PAR-DESSUS** (aujourd'hui ils sont dessous, et la StatStrip fait doublon en dessous — elle disparaît, absorbée par le hero) ;
2. **Tracklist alignée sur le reste de l'app** : la rangée bespoke est remplacée par le **composant de rangée partagé `<TrackCard>`** (celui des tracklists Track/Playlist/Set/Artist Detail) = « comme Explorer, sans la colonne genre » ;
3. **Assainissement** : « Tout filtrer dans Catalog » retiré, Admin déplacé en bas, badge source des playlists aligné sur la convention glyph.

Tout le reste (shelves Artistes/Sets/Playlists, Genres proches, search/sort/En bib/infinite scroll, play, avis) est **conservé**.

**Périmètre strict : design/UX uniquement.** Le shell de l'app (sidebar, BottomNav) est hors périmètre — tu ne designs que le **contenu de la page**. Les données listées plus bas sont **exhaustives : ne rien inventer au-delà**.

> **Cette page ne crée AUCUN composant transverse nouveau.** Elle CONSOMME sans les modifier : `<TrackCard>` (rangée, specs dans TRANSVERSE.md), `<Artwork>` (in-lib), `<LikeDislike>`, `<PlatformLink variant="glyph">`, `<StyleTag>`, les shelves existantes (`ExpandableShelf`/`ShelfCard`/`RelBlock`), `SearchBox`, `AdminCard`, `BackButton`. Un besoin local se règle par override scopé, pas en touchant le composant.

## Décisions produit FIGÉES (fiche jointe — à respecter, pas à rediscuter)

1. **Structure de page** : Hero immersif → Actions → Shelves (Artistes / Sets / Playlists) → Tracks → Genres proches → **Admin en DERNIER** (aujourd'hui en haut ; visible admin uniquement — le gate existe déjà).
2. **Hero immersif** : mosaïque de covers **agrandie**, **titre + pilier + stats clés écrits PAR-DESSUS** — stats clés = **Tracks · Artistes · BPM range** ; **avatars** des top-3 artistes + « +N » ; **play** (extrait aléatoire du genre). Le **reste des stats (En bib · Sets · Playlists) en petit dessous**. La **StatStrip disparaît** (absorbée). La mosaïque et le body restent **teintés par le pilier** (house/techno/trance/dnb/hardcore/harddance/autres — « autres » = neutre sans teinte).
3. **Actions** : « Écouter un aperçu » + `<LikeDislike>` (avis sur le GENRE). **« Tout filtrer dans Catalog » RETIRÉ**, non ré-alloué (le filtre genre d'Explorer couvre).
4. **Tracklist = rangée partagée `<TrackCard>`** (SANS la modifier) : cover `<Artwork>` avec **point in-lib**, titre, **artistes cliquables** (multi-artistes structurés — fallback texte plat non cliquable pour ~10 % des rangées), **BPM**, **Key**, **durée**, **play** + **boutons avis `<LikeDislike>` par rangée** (arbitrage 2026-08-02, cohérence Explorer — via le slot `end` de TrackCard). Garde **search + sort (Récent / BPM / Key / A–Z) + toggle « En bib » + infinite scroll**. ⚠️ PAS le système de filtres riches d'Explorer (FilterBar/panneau) — les contrôles simples actuels, restylés.
5. **Shelves gardées** : Artistes (cards rondes, « Voir les N autres ») · Sets (badge **% = part des tracks du set dans CE genre** — vrai signal, 20–96 % mesuré en prod) · Playlists. **Badge source des playlists → logo glyph `<PlatformLink variant="glyph">`** (deezer/tidal/spotify, monochrome — remplace le badge texte coloré, convention transverse actée).
6. **Genres proches gardés** : chips `<StyleTag>` (couleur pilier) + « N artistes en commun ».
7. **Admin (rename / merge)** : conservé fonctionnellement tel quel, admin-only, en bas de page.
8. **Libellés 100 % français.** **Pas d'état invité** (page interne toujours authentifiée — l'invité est confiné au Hub).

## Latitude DA (à toi de trancher, décisions à expliciter dans le brief)

- **Le hero immersif = LE morceau central du chantier.** Aujourd'hui : mosaïque 3×2 de 180px, titre dessous. Cible : mosaïque **agrandie** avec overlay. À trancher : hauteur/format, **scrim et lisibilité** (le titre est teinté pilier SUR des covers hétérogènes — contraste à garantir, dark ET light), position de chaque élément (titre, label pilier, stats clés, avatars, play), **stats secondaires** (En bib · Sets · Playlists) en petit sous le hero, comportement quand la mosaïque est **incomplète** (< 6 covers : tuiles placeholder teintées, déjà le cas) ou le pilier « autres » (neutre).
- **Titre long** : « Techno (Raw / Deep / Hypnotic) » tronque à 375px (capture 03). Un titre par-dessus la mosaïque doit gérer 2 lignes ou une échelle fluide — pas d'ellipsis brutale sur le nom du genre.
- **Mobile** : mosaïque actuelle passe 2×3 à 140px sous 560px ; les actions s'empilent mal (capture 03). Redessine le hero étroit (hauteur, overlay, stats) — BPM range reste une info DJ clé.
- **Rangée tracklist** : TrackCard porte déjà l'anatomie (cover 40px, titre/artistes, BPM, Key, durée — durée tombe < 640px). À toi : l'intégration des **avis** dans le slot de fin (hover-reveal desktop / toujours visibles tactile — pattern des listes récentes), la densité, l'en-tête de section (compteur, SearchBox, segmented sort, toggle En bib) et son repli mobile (aujourd'hui : tools passent pleine largeur sous 820px).
- **Shelves** : habillage des sections (titres + compteurs + « Voir les N autres »), sans redessiner les composants partagés en profondeur. Le badge % des cards Sets peut être raffiné (aujourd'hui pill texte coin bas-droit, seuils 80/45).
- **Genres proches** : chips gardées — finitions libres (espacement, hover).
- **Empty states** : genre **sans sets ni playlists** (sections aujourd'hui masquées — OK), tracklist vide sur recherche (« Aucune track ne correspond. »), et le **BPM absent** : 2 genres sur 75 n'ont AUCUN bpm → afficher « — », jamais « 0–0 ».

## Note DONNÉES importante (vérifiée en prod — cadre tes choix)

- **Volumes réels** : tracks par genre de **1 à 15 664** ; artistes 1 à 4 517 ; **sets 0 à 4 689** ; **playlists 0 à 15** ; en bib 0 à 132 ; BPM ranges variés (70–170), **2 genres sans aucun BPM**.
- **% des cards Sets** : réellement variable (20–96 % mesuré) — c'est la part des tracks du set qui appartiennent à CE genre, pas un « % identifié ».
- **Artistes structurés** : ~90 % des rangées tracklist auront des artistes cliquables ; ~10 % retombent sur la chaîne plate (non cliquable). Prévois les deux rendus (déjà gérés par TrackCard).
- **Avatars du hero** : uniquement des artistes AVEC photo (jamais de placeholder cassé) ; parfois 0 avatar disponible → le hero doit vivre sans.
- **Sources playlists** : deezer / tidal / spotify (33/22/1 en prod) — le glyph varie vraiment.

## Ce que tu dois livrer

### 1. `BRIEF-genre-detail.md` — le handoff de la page

Même format que les briefs existants (tableaux de tokens, anatomie, états, décisions DA explicites). Doit couvrir : **hero immersif** (anatomie complète overlay : titre/pilier/stats clés/avatars/play, scrim, teinte pilier, cas « autres », cas < 6 covers, cas 0 avatar, mobile, titre 2 lignes), **stats secondaires** (En bib · Sets · Playlists, « — » BPM), **actions** (aperçu + avis, sans « Tout filtrer »), **section Tracks** (en-tête : compteur + SearchBox + sort + En bib ; rangée TrackCard + avis slot end ; états hover/lecture ; responsive), **shelves** (Artistes/Sets % badge/Playlists glyph source), **Genres proches**, **Admin en bas** (style AdminCard existant), **empty states**. Explicite chaque token utilisé et argumente les arbitrages (hauteur hero, scrim, position stats).

### 2. `Genre Detail (pilote).html` — maquette interactive

Maquette HTML autonome consommant les tokens de `diggy-tokens.css` (**zéro couleur hardcodée**), avec :
- la page complète d'un **genre riche** (données réalistes type Techno : 15 664 tracks · 4 517 artistes · 78–145 BPM · 12 en bib · 4 689 sets · 8 playlists, mosaïque 6 covers, 3 avatars, ~15 rangées tracklist avec BPM/Key/durée variés dont quelques « — », 2-3 rangées in-lib, une rangée liked) ;
- un **état genre pauvre** (type Trance 141 tracks : mosaïque incomplète avec tuiles placeholder, 7 en bib, stats basses) — section ou toggle ;
- **survol** d'une rangée (play + avis révélés) et d'une card shelf ;
- le bloc **Genres proches** + la carte **Admin** en bas ;
- un **empty state** (tracklist vide sur recherche) ;
- toggle **dark/light**, toggle **viewport desktop / 375px** (hero étroit re-designé visible).

### 3. ⚠️ **Livraison : une archive ZIP téléchargeable UNIQUE (un seul lien) contenant les 2 livrables.** Sans archive, le transfert des fichiers est manuel et casse le pipeline.

## Données disponibles (exhaustif — ne rien inventer au-delà)

`GET /api/genres/detail/{name}` → l'en-tête de page :

| Champ | Type | Usage design |
|---|---|---|
| `name` | string | titre (peut être long — « Techno (Raw / Deep / Hypnotic) ») |
| `pillar` / `depth` | string / int | **teinte toute la page** (mosaïque, point, titre, tags) ; house/techno/trance/dnb/hardcore/harddance/**autres** (= neutre) |
| `trackCount` | int | stat clé **Tracks** (hero) |
| `artistCount` | int | stat clé **Artistes** (hero) + « +N » avatars |
| `bpmLo` / `bpmHi` | int | stat clé **BPM range** (hero) — « — » si les deux à 0 |
| `inLibCount` | int | stat secondaire **En bib** |
| `setCount` / `playlistCount` | int | stats secondaires (0 possible) |
| `artworks` | string[] ≤ 6 (urls) | mosaïque du hero (tuile placeholder teintée si manquante) |
| `artists` | objet[] ≤ 3 | avatars hero : `{ id, name, image }` (toujours avec vraie photo ; peut être vide) |

Sous-endpoints (sections, tous paginés `{ items[], total }`) :
- `GET /api/genres/artists/{name}` → cards Artistes : `{ id, name, hasArtwork, trackCount, inLibCount }`
- `GET /api/genres/sets/{name}` → cards Sets : `{ id, title, playedDate, hasArtwork, genreTrackCount, totalTracks }` (badge % = genreTrackCount/totalTracks)
- `GET /api/genres/playlists/{name}` → cards Playlists : `{ id, title, source, hasArtwork, owner, genreTrackCount }` (source → glyph)
- `GET /api/genres/tracks/{name}?sort&q&inLib` → rangées : `{ id, title, artist (fallback plat), artists[] {id,name} (lot back de ce chantier), bpm, key, durationMs, hasArtwork, hasPreview, inLib }` — sorts : `recent` (défaut) / `bpm` / `key` / `alpha`
- `GET /api/genres/neighbors/{name}` → chips : `{ name, pillar, depth, commonArtists }`

Contrôles interactifs : **play hero** (aléatoire du genre), **avis GENRE** (actions), **play + avis par rangée** (interceptent le clic), **admin rename/merge** (formulaire existant).

**Il n'y a PAS** : de bouton « Tout filtrer dans Catalog » (retiré), de StatStrip (absorbée), de rating (jamais eu ici), de pastille de suivi (concept Artistes), de % de couverture bib (piège écarté sur la liste Genres), de filtres riches Explorer (contrôles simples seulement).

## Design system — contraintes (rappel)

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. **Zéro couleur hardcodée.**
- **Typo** : `--font-ui` (Space Grotesk) pour le texte, `--font-mono` (JetBrains Mono) pour les données numériques (stats, BPM, Key, durées, compteurs).
- **Couleurs de pilier** : seule coloration sémantique large (mosaïque/scrim, point, titre, StyleTag) — conservée. Sinon **monochrome `currentColor`** pour l'iconographie + **accent mauve** = signal d'action/état actif + **`--pos`/`--pos-ink`** pour l'in-lib et le liké.
- **Thèmes** : `[data-theme="dark"]` par défaut + light — la maquette supporte les deux (lisibilité de l'overlay hero dans les DEUX).
- **Responsive** : container queries (`@container`), jamais `@media` sauf éléments `position: fixed`. Convention repo : penser seuils **720/640**.
- **CSP stricte** : icônes en SVG inline ou data-URI, aucun CDN, aucune font externe.
- **UI en français.**

## Récapitulatif des livrables

| Fichier | Contenu |
|---------|---------|
| `BRIEF-genre-detail.md` | Handoff page : hero immersif (overlay titre/pilier/stats + avatars + play, tous les cas), stats secondaires, actions sans « Tout filtrer », tracklist TrackCard + avis, shelves (% sets, glyph playlists), Genres proches, Admin en bas, empty states, tokens |
| `Genre Detail (pilote).html` | Maquette interactive (genre riche complet + état genre pauvre, survols, empty state, toggles theme/viewport) |
| **Archive ZIP unique** | Les 2 livrables téléchargeables en un lien |

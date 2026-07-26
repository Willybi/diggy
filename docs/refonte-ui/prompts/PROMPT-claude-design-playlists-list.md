# Prompt — Claude Design · Refonte Playlists (liste) — `/playlists` (D6)

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/playlists-list.md` (fiche de cadrage figée de la page — décisions produit ; les « Précisions pré-vol 2026-07-25 » priment)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — composants partagés)
> - `docs/refonte-ui/handoff-sets-list/BRIEF-sets-list.md` (référence de **FORMAT uniquement** — c'est la **liste jumelle** en tableau, tout juste livrée ; son **contenu** concerne les Sets et **diffère** des décisions ci-dessous, ne PAS le reprendre tel quel)
> - Captures de la page ACTUELLE (dossier `C:\tmp\captures-playlists-list\`) :
>   - `01-desktop-dark-full.png` — tableau actuel, desktop dark 1440px (colonnes PLAYLIST · CRÉATEUR · TRACKS · DERNIER CRAWL · AVIS). Source en **badge texte** (TIDAL/DEEZER), `external_id` (UUID) affiché sous le titre = **bruit à retirer**.
>   - `02-desktop-light-full.png` — même vue, light.
>   - `03-mobile-375-dark.png` — mobile actuel 375px (colonnes réduites à PLAYLIST seul, head empilé, BottomNav 7 items). Le bruit `external_id` est très visible ici.

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark par défaut, tokens centralisés). La refonte page par page continue : les 4 pages détail (Track, Playlist, Set, Artist) et 4 pages D6 (Explorer, Radar, Hub, **Sets liste**) sont livrées. On refait les **listes** ; celle-ci est la **jumelle directe de la liste Sets** (même fondation tableau).

**Cette page : Playlists (liste) — `/playlists`.** C'est la liste des **playlists surveillées** (watchlist) — les sources externes (Deezer/Tidal/Spotify) dont Diggy crawle le contenu pour alimenter le radar de tendances. ~56 playlists. Aujourd'hui : un **tableau dense** peu aimé. Le mouvement produit : **garder le format tableau** mais l'**assainir et l'enrichir** — source en **logo** (plus badge texte), ajouter le **genre déduit**, retirer le bruit `external_id`, passer en **infinite scroll**, et exposer un discret signal de **cadence** (à quelle fréquence la playlist change). C'est une refonte de **densité/hiérarchie/enrichissement de rangée**, pas un changement de paradigme.

**Format = TABLEAU (verrouillé, comme sa jumelle Sets).** Ne propose pas de grille de cartes.

**Périmètre strict : design/UX uniquement.** Le shell de l'app (sidebar, BottomNav) est hors périmètre — tu ne designs que le **contenu de la page**. Les données listées plus bas sont **exhaustives : ne rien inventer au-delà**.

**Composants transverses : cette page n'en crée AUCUN.** Tu CONSOMMES des composants déjà implémentés (spec dans TRANSVERSE.md) :
- `<Artwork>` — cover réelle + placeholder rayé (la cover de playlist vit sous `/storage/playlist-artworks/{id}.jpg`). **Pas d'indicateur in-lib ici** (une playlist n'est pas « dans la bibliothèque »).
- `<PlatformLink variant="glyph">` — **logo de plateforme monochrome** (`currentColor`, ~13px), marqueur de source **non-cliquable**. Couvre `deezer` / `tidal` / `spotify`. C'est le remplaçant des badges texte DEEZER/TIDAL actuels.
- `<StyleTag>` — pastille de genre colorée par pilier, cliquable → `/style/:name`.
- `<LikeDislike>` — boutons avis (like/dislike).

> ⚠️ **Pas de `<ScoreRing>` / `<RingPct>` ici.** Contrairement à la liste Sets, il n'y a **pas de ratio** à afficher : la colonne Tracks est un **nombre brut** (le compte de la source), pas un pourcentage.

## Décisions produit FIGÉES (fiche jointe — à respecter, pas à rediscuter)

1. **Colonnes de la rangée** (contenu figé ; l'ordre exact, le regroupement et le placement responsive sont de la latitude DA, mais ce sont ces informations et pas d'autres) :
   - **Playlist** : cover (`<Artwork>`) + **titre** + **source** (`<PlatformLink variant="glyph">`, logo monochrome). **Retirer l'`external_id`** affiché sous le titre aujourd'hui (bruit technique).
   - **Genre** : **1–2 `<StyleTag>`** déduits des tracks détectées de la playlist (cliquables → `/style/:name`). **Peut être vide** pour une rangée → on **omet**, jamais de tiret.
   - **Créateur** : `owner` (le curateur de la source). Nullable ; en pratique toujours présent, mais **peut être un nom générique de plateforme** (les playlists TIDAL affichent souvent `owner = "TIDAL"`, les Deezer un vrai label comme « Defected Records » / « Armada Music »).
   - **Tracks** : `track_count` — **nombre brut** de la source (mono). Pas d'anneau, pas de %.
   - **Dernier crawl** : bloc composite (voir §2).
   - **Avis** : `<LikeDislike>` (like/dislike).
2. **Colonne « Dernier crawl » = bloc de veille** (cœur spécifique de cette page, à soigner) réunissant :
   - **date du dernier crawl** (`last_crawled_at`, relatif : « aujourd'hui » / « il y a 14 j » / « jamais », mono) ;
   - **statut crawl LIVE** (temps réel, remplace la date pendant un crawl) : `En attente` (point creux) → `En cours` (point accentué animé) → `Crawlé` (point positif) ;
   - **bouton « Crawl »** (déclenche un crawl manuel) — **masqué** pendant un cooldown de 12 h après le dernier crawl ;
   - **pastille de cadence** (voir §3).
3. **Pastille de cadence** (`Quotidien` / `Hebdo` / `Mensuel`) : petit marqueur indiquant à quelle fréquence la playlist **change** (≠ à quelle fréquence on la crawle). Dérivée de `last_changed_at`. **Règle stricte (arbitrage produit) : la pastille n'apparaît QUE si `last_changed_at` existe.** Beaucoup de rangées n'en auront pas aujourd'hui (la donnée se remplit à l'usage) — **c'est voulu, ne fabrique pas d'état de repli**. Seuils : `< 14 j` = Quotidien, `14–60 j` = Hebdo, `> 60 j` = Mensuel. Tooltip = « dernière nouveauté il y a X ». Place-la avec discrétion (dans/à côté du bloc « Dernier crawl » ou en coin de rangée — latitude DA).
4. **Pas de colonne Play, pas de BPM/Key, pas de rating, pas de % identifié, pas d'indicateur in-lib.** **Aucune nouvelle colonne** au-delà de la liste §1.
5. **Le concept « suivre » est masqué de l'UI.** Une playlist listée est surveillée par défaut ; **n'affiche aucun toggle/état « suivi »** sur la rangée. (Le bouton d'ajout crée le suivi en coulisse.)
6. **Scroll : infinite scroll** (sentinel, façon Explorer/Sets/Artistes) — la table se charge par pages server-side au défilement. **Plus de pagination `‹ page/N ›`** (l'actuelle), plus de tri/filtre client-side.
7. **Tri** : par **clic d'en-tête de colonne**, server-side. Colonnes triables = **Playlist (titre) · Créateur · Tracks · Dernier crawl**. Défaut = **Titre A→Z**. Genre, Avis et Cadence **non triables**.
8. **Filtre d'avis** : le **SegFilter** (Toutes / Liked / Disliked / À explorer) reste dans le head — c'est un **filtre**, pas un tri. (Pour toi : un segmented control à 4 segments dans le head.)
9. **Form « Ajouter » conservé** : bouton **Ajouter** ouvrant un panneau simple = **un champ URL** (playlist Deezer / Tidal / Spotify) + bouton de validation + message d'erreur (URL invalide / déjà ajoutée). Le **flux** est conservé ; tu peux **rafraîchir le style** du panneau (et le passer en **modal** comme la liste Sets si tu le juges mieux) sans réinventer le flux. Libellé du bouton de validation = **« Ajouter »** (pas « Suivre » — le concept follow est masqué, §5).
10. **Conservés** : coloration de rangée avis (liked = wash positif, disliked = rangée estompée), **clic rangée → `/playlists/:id`**.
11. **Libellés 100 % français.**
12. **Pas d'état invité** : page interne toujours authentifiée (l'invité est confiné au Hub).

## Latitude DA (à toi de trancher, décisions à expliciter dans le brief)

- **Hiérarchie et densité de la rangée enrichie** : c'est le cœur du travail. Où placer le genre (colonne dédiée ? sous le titre dans la cellule Playlist ?), comment intégrer le **logo de source** près du titre, équilibre visuel entre cover / titre+source / genre / créateur / tracks / bloc crawl / avis, hauteur de rangée, séparateurs, hover.
- **Composition du bloc « Dernier crawl »** : agencer date relative + statut live + bouton Crawl + pastille cadence sans surcharge. C'est la cellule la plus riche — trouve une hiérarchie lisible (la cadence est secondaire, le statut live est prioritaire quand il est actif).
- **Traitement de la pastille cadence** : forme (chip / point coloré / libellé), couleur (rappel : monochrome sauf l'accent — évite un code couleur à 3 teintes ; préfère un libellé mono discret ou une nuance d'accent). Rappelle-toi qu'elle est **souvent absente**.
- **Placement du genre en responsive** : piste = colonne Genre dédiée en desktop qui **se replie sous le titre** (chips dans la cellule Playlist) quand la largeur diminue, plutôt que de disparaître — à toi de trancher.
- **Échelle de column-drop responsive** : redéfinis-la pour ce jeu de colonnes. Contraintes : sous 640px, **avis toujours visible** (tactile) ; garder au minimum **Playlist + Avis**. Le bloc « Dernier crawl » (colonne large) tombe tôt ; décide de l'ordre de chute (Dernier crawl → Créateur → Tracks → Genre replié).
- **Head de page** : titre + compteur, SegFilter avis, bouton Ajouter — agencement + repli mobile (le head actuel empile sur mobile). *(NB : pas de champ de recherche texte sur cette page aujourd'hui — n'en ajoute pas.)*
- **Panneau Ajouter** : rafraîchissement visuel (champ URL, bouton, message d'erreur ; modal recentré possible façon Sets).
- **Empty states** : chargement (skeleton/message) ; filtre avis vide (« Aucune playlist likée »…). *(Pas d'empty state « recherche » — pas de recherche ici.)*
- Densité, hover, transitions — dans l'esprit de la table actuelle (captures 01/03), en plus soigné.

## Ce que tu dois livrer

### 1. `BRIEF-playlists-list.md` — le handoff de la page

Même format que les briefs existants (tableaux de tokens, anatomie, états, décisions DA explicites). Doit couvrir : head de page (titre, compteur, SegFilter avis, bouton Ajouter), panneau Ajouter (champ URL + erreurs), tableau (colonnes, dimensions, hauteur de rangée, en-tête triable + indicateur de tri, hover), **rangée enrichie** (cover Artwork, titre + logo source, chips genre, créateur, tracks, **bloc Dernier crawl** dans ses états, avis), **bloc Dernier crawl détaillé** (date relative / statut live queued·running·done / bouton Crawl / cooldown / pastille cadence présente|absente), états de rangée (hover, liked = wash positif, disliked = estompée), empty states (chargement / filtre avis vide), responsive complet (échelle de column-drop + repli du genre + head mobile), pilote 375px.

### 2. `Playlists (pilote).html` — maquette interactive

Maquette HTML autonome consommant les tokens de `diggy-tokens.css` (**zéro couleur hardcodée**), avec :
- la page complète, **~14 rangées de données réalistes** : mélange de couvertures présentes/placeholder, **sources variées** (Deezer / Tidal / Spotify, via le logo glyph), **1–2 chips genre** (dont **quelques rangées sans genre**), créateurs variés (dont un générique « TIDAL » et un vrai label), `track_count` variés (petits et gros : 45 → 472), **bloc Dernier crawl dans plusieurs états** (date « aujourd'hui » / « il y a 14 j » / « jamais » ; une rangée `En cours` animée ; une rangée `Crawlé` ; une rangée en cooldown sans bouton Crawl), **pastille cadence présente sur ~1/4 des rangées seulement** (le reste sans pastille), quelques rangées liked / disliked, titres longs (ellipsis) ;
- le head dans ses états (SegFilter sur « Toutes » puis sur « Liked ») ;
- le **panneau Ajouter ouvert** (champ URL + un exemple de message d'erreur) ;
- un **empty state** (filtre avis « Disliked » vide) ;
- toggle **dark/light**, toggle **viewport desktop / 375px**.

### 3. ⚠️ **Livraison : une archive ZIP téléchargeable UNIQUE (un seul lien) contenant les 2 livrables.** Sans archive, le transfert des fichiers est manuel et casse le pipeline.

## Données disponibles (exhaustif — ne rien inventer au-delà)

`GET /api/watchlist/browse` → `{ total, items[] }` (paginé, infinite scroll). Champs par item **à la cible** (après le lot back de ce chantier) :

| Champ | Type | Usage design |
|---|---|---|
| `id` | int | clé + lien `/playlists/:id` + cover |
| `title` | string (nullable) | titre de la rangée (fallback : `external_id` si absent) |
| `source` | `"deezer"` \| `"tidal"` \| `"spotify"` | **logo** `<PlatformLink variant="glyph">` près du titre |
| `top_genres` | objet[] **(NOUVEAU)** | genres déduits, chacun `{ name, pillar, depth, pct }` → **1–2 `<StyleTag>`** (`name` affiché, `pillar` colore, lien `/style/:name`). Liste **possiblement vide**. |
| `owner` | string (nullable) | colonne Créateur — **peut être un nom de plateforme générique** (ex. « TIDAL ») |
| `track_count` | int (nullable) | colonne Tracks — **nombre brut** (mono), pas de % |
| `has_artwork` | bool | cover `/storage/playlist-artworks/{id}.jpg` si vrai, sinon placeholder `<Artwork>` |
| `last_crawled_at` | datetime (nullable) | date relative du bloc Dernier crawl (« jamais » si null) |
| `last_changed_at` | datetime (nullable) **(NOUVEAU)** | alimente la **pastille cadence** — **absente sur la majorité des rangées** aujourd'hui (pas de pastille alors) |
| `current_task_id` | string (nullable) | présence d'un crawl en cours → déclenche l'affichage du **statut live** |

Statut crawl LIVE (temps réel, polling) : valeurs `En attente` / `En cours` / `Crawlé` — un seul de ces états remplace la date+bouton pendant un crawl, puis revient à la date.
Filtre d'avis : le SegFilter résout les playlists aimées/dislikées côté app ; pour toi c'est un segmented control dans le head (4 segments).
Tri : clic d'en-tête → `sort` server-side (titre / créateur / tracks / dernier crawl) + sens.

Champs **présents dans le payload mais NON affichés** (ne pas les surfacer) : `external_id` (bruit technique — **retiré**), `followed` (concept « suivi » masqué), `description`, `created_at`.
**Il n'y a PAS**, au niveau playlist : bpm, key, rating, % de tracks identifiées, extrait audio/play, indicateur in-lib.

Source des genres cliquables : `<StyleTag>` pointe vers `/style/:name` (page détail genre existante).

## Design system — contraintes (rappel)

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. **Zéro couleur hardcodée.**
- **Typo** : `--font-ui` (Space Grotesk) pour le texte, `--font-mono` (JetBrains Mono) pour les données numériques (dates, compteurs de tracks, cadence).
- **Thèmes** : `[data-theme="dark"]` par défaut + light — la maquette supporte les deux.
- **Responsive** : container queries (`@container`), jamais `@media` sauf éléments `position: fixed`. Convention repo : seuils **720/640**.
- **CSP stricte** : icônes/logos en SVG inline ou data-URI, aucun CDN, aucune font externe.
- **UI en français.**
- **Monochrome `currentColor`** pour toute iconographie (dont les logos de plateforme) — l'accent mauve reste le seul signal coloré ; les couleurs de pilier des `<StyleTag>` sont la seule autre couleur sémantique.

## Récapitulatif des livrables

| Fichier | Contenu |
|---------|---------|
| `BRIEF-playlists-list.md` | Handoff page : head, panneau Ajouter, tableau enrichi (rangée + genre + logo source + bloc Dernier crawl/cadence), états, empty states, responsive, tokens |
| `Playlists (pilote).html` | Maquette interactive (table ~14 rangées + head + panneau Ajouter + empty state, états crawl live, cadence partielle, toggles theme/viewport) |
| **Archive ZIP unique** | Les 2 livrables téléchargeables en un lien |

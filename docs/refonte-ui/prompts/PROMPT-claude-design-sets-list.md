# Prompt — Claude Design · Refonte Sets (liste) — `/sets` (D6)

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/sets-list.md` (fiche de cadrage figée de la page — décisions produit ; les « Précisions pré-vol 2026-07-23 » priment)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — composants partagés)
> - `docs/refonte-ui/handoff-explorer/BRIEF-explorer.md` (référence de **FORMAT uniquement** — c'est l'autre page-liste en tableau ; son **contenu** concerne Explorer et peut contredire les décisions ci-dessous, ne PAS le reprendre)
> - Captures de la page ACTUELLE (dossier `C:\tmp\captures-sets-list\`) :
>   - `01-desktop-dark-full.png` — tableau actuel, desktop dark 1440px (colonnes SET · DATE · TRACKS · DURÉE · AVIS). ⚠️ la 1ʳᵉ page (tri date desc) tombe par hasard sur des sets 100 % identifiés : **après exclusion des 0 %, la colonne % affichera un vrai éventail** (30–100 %). **Ni genre ni source** aujourd'hui.
>   - `02-desktop-light-full.png` — même vue, light.
>   - `03-mobile-375-dark.png` — mobile actuel 375px (colonnes réduites à SET · TRACKS · AVIS, head empilé, avis toujours visibles au tactile).

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark par défaut, tokens centralisés). La refonte page par page continue : les 4 pages détail (Track, Playlist, Set, Artist) et 3 pages D6 (Explorer, Radar, Hub) sont livrées. On refait maintenant les **listes**. Chaque page est cadrée produit dans une fiche figée, et tu produis le **handoff purement design** (brief + maquette) qu'un agent d'implémentation applique tel quel.

**Cette page : Sets (liste) — `/sets`.** C'est la liste des DJ sets importés (~11 800). Aujourd'hui : un **tableau dense** (mêmes fondations que la liste Playlists, sa jumelle). William la juge « un des visuels les moins aimés ». Le mouvement produit : **garder le format tableau** mais l'**assainir et l'enrichir** — exclure le bruit (sets 0 % identifiés), ajouter le **genre déduit**, passer en **infinite scroll**. C'est une refonte de **densité/hiérarchie/enrichissement de rangée**, pas un changement de paradigme.

**Format = TABLEAU (décision William, verrouillée).** `TRANSVERSE.md` a une ligne stale qui suggérait une grille de cartes `<SetCard>` pour cette page — **c'est corrigé, on reste en tableau**. Ne propose pas de grille de cartes.

**Périmètre strict : design/UX uniquement.** Le shell de l'app (sidebar, BottomNav) est hors périmètre — tu ne designs que le **contenu de la page**. Les données listées plus bas sont **exhaustives : ne rien inventer au-delà**.

**Composants transverses : cette page n'en crée AUCUN.** Tu CONSOMMES des composants déjà implémentés (spec dans TRANSVERSE.md) :
- `<Artwork>` — cover réelle + placeholder rayé (tailles existantes ; ici la cover de set vit sous `/storage/set-artworks/{id}.jpg`). **Pas d'indicateur in-lib ici** (un set n'est pas « dans la bibliothèque »).
- `<StyleTag>` — pastille de genre colorée par pilier, cliquable → `/style/:name`.
- `<RingPct>` — anneau de proportion + « N % » au centre (déjà utilisé dans la colonne Tracks actuelle). Tu le CONSOMMES tel quel.
- `<LikeDislike>` — boutons avis (like/dislike).

## Décisions produit FIGÉES (fiche jointe — à respecter, pas à rediscuter)

1. **Exclure les sets à 0 % identifié** (`identified_tracks == 0`) — masqués **par défaut, sans toggle**. Conséquence design : **toute rangée a au moins 1 track identifié**, la colonne % ne descend jamais à 0.
2. **Colonnes de la rangée** (contenu figé ; l'ordre exact et le regroupement sont de la latitude DA, mais ce sont ces informations et pas d'autres) :
   - **Set** : cover (`<Artwork>`) + **titre** + **artistes** (noms simples, plusieurs possibles, jamais en supposer un seul ; peut être vide).
   - **Genre** : **1–2 `<StyleTag>`** déduits des tracks du set (cliquables → `/style/:name`). **Peut être vide** pour une rangée (peu de tracks identifiés / pas de genre) → on **omet**, jamais de tiret.
   - **Date** : `played_date` (mono), nullable.
   - **Tracks** : `<RingPct>` (part de tracks identifiés en %).
   - **Durée** : `duration_ms` (mono).
   - **Avis** : `<LikeDislike>` (like/dislike).
3. **Colonne « Source » RETIRÉE** — décidée à l'origine dans la fiche puis **abandonnée au pré-vol** : en base 100 % des sets sont `source='trackid'` (origine réelle connue pour 68 sur 11 800) → un logo de source serait identique partout ou vide à ~99 %. **Aucune colonne source, aucun `<PlatformLink>`** sur cette page.
4. **Pas de colonne Play, pas de BPM/Key, pas de rating** (écartés / inexistants au niveau set). **Aucune nouvelle colonne** au-delà de la liste ci-dessus.
5. **Scroll : infinite scroll** (sentinel, façon Explorer/Artistes/Genres) — la table se charge par pages server-side au défilement. **Plus de pagination `← page/N →`**, plus de tri/filtre client-side.
6. **Tri** : par **clic d'en-tête de colonne** (comme aujourd'hui), server-side. Colonnes triables = **Titre · Date · Tracks (%) · Durée**. Défaut = **Date décroissante**. Genre et Avis **non triables**.
7. **Filtre d'avis** : le **SegFilter** (Tous / Liked / Disliked / À explorer) reste dans le head — c'est un **filtre**, pas un tri. (Implémentation façon liste Artistes ; pour toi c'est juste un segmented control dans le head.)
8. **Form « Ajouter » conservé** : bouton **Ajouter** ouvrant un panneau à **2 onglets** — « Rechercher » (recherche TrackID → liste de résultats avec bouton d'import par résultat) et « URL » (coller une URL TrackID). Le **flux** est conservé ; tu fournis le layout du head et peux **rafraîchir le style** du panneau pour l'accorder à la refonte, sans réinventer le flux.
9. **Conservés** : recherche texte (head), coloration de rangée avis (liked = wash positif, disliked = rangée estompée), **clic rangée → `/set/:id`**.
10. **Libellés 100 % français.**
11. **Pas d'état invité** : page interne toujours authentifiée (l'invité est confiné au Hub).

## Latitude DA (à toi de trancher, décisions à expliciter dans le brief)

- **Hiérarchie et densité de la rangée enrichie** : c'est le cœur du travail. Où placer le genre (colonne dédiée ? sous le titre dans la cellule Set ?), équilibre visuel entre cover / titre+artistes / genre / % / durée / avis, hauteur de rangée, séparateurs, hover.
- **Placement du genre en responsive** : une piste = colonne Genre dédiée en desktop qui **se replie sous le titre** (chips dans la cellule Set) quand la largeur diminue, plutôt que de disparaître — à toi de trancher.
- **Échelle de column-drop responsive** : redéfinis-la pour ce jeu de colonnes. Contraintes : sous 640px, **avis toujours visible** (tactile) ; garder au minimum **Set + Tracks(%) + Avis**. La colonne % peut réduire son libellé (anneau seul sans « N % ») sur les largeurs étroites.
- **Head de page** : titre + compteur, recherche, SegFilter avis, bouton Ajouter — agencement + repli mobile (le head actuel empile sur mobile).
- **Panneau Ajouter** : rafraîchissement visuel (onglets, champ, liste de résultats de recherche, bouton d'import par résultat, message d'erreur).
- **Empty states** : chargement (skeleton/message) ; aucun set trouvé (recherche trop stricte) ; filtre avis vide (« Aucun set liké »…).
- Densité, hover, transitions — dans l'esprit de la table actuelle (captures 01/03), en plus soigné.

## Ce que tu dois livrer

### 1. `BRIEF-sets-list.md` — le handoff de la page

Même format que les briefs existants (tableaux de tokens, anatomie, états, décisions DA explicites). Doit couvrir : head de page (titre, compteur, recherche, SegFilter avis, bouton Ajouter), panneau Ajouter (2 onglets + résultats + import), tableau (colonnes, dimensions, hauteur de rangée, en-tête triable + indicateur de tri, hover), **rangée enrichie** (cover Artwork, titre+artistes, chips genre, RingPct, durée, avis), états de rangée (hover, liked = wash positif, disliked = estompée), empty states (chargement / aucun résultat / filtre avis vide), responsive complet (échelle de column-drop + repli du genre + head mobile), pilote 375px.

### 2. `Sets (pilote).html` — maquette interactive

Maquette HTML autonome consommant les tokens de `diggy-tokens.css` (**zéro couleur hardcodée**), avec :
- la page complète, **~15 rangées de données réalistes** : mélange de couvertures présentes/placeholder, **% variés (30→100 %)**, **1–2 chips genre** (dont **quelques rangées sans genre**), 1 ou plusieurs artistes (dont une rangée sans artiste), quelques rangées liked / disliked, titres longs (les titres de sets sont souvent longs → gestion de l'ellipsis) ;
- le head dans ses états (SegFilter sur « Tous » puis sur « Liked ») ;
- le **panneau Ajouter ouvert** (onglet Rechercher avec ~3 résultats + onglet URL) ;
- un **empty state** (aucun résultat) ;
- toggle **dark/light**, toggle **viewport desktop / 375px**.

### 3. ⚠️ **Livraison : une archive ZIP téléchargeable UNIQUE (un seul lien) contenant les 2 livrables.** Sans archive, le transfert des fichiers est manuel et casse le pipeline.

## Données disponibles (exhaustif — ne rien inventer au-delà)

`GET /api/sets/` → `{ total, items[] }`. Champs par item **à la cible** (après le lot back de ce chantier) :

| Champ | Type | Usage design |
|---|---|---|
| `id` | int | clé + lien `/set/:id` + cover |
| `title` | string | titre de la rangée (souvent long) |
| `artists` | string[] | noms simples (0..n), joints par « , » — **jamais supposer un seul** |
| `top_genres` | objet[] **(NOUVEAU)** | genres déduits, chacun `{ name, pillar, depth, pct }` → **1–2 `<StyleTag>`** (name affiché, `pillar` colore, lien `/style/:name`). Liste **possiblement vide**. |
| `played_date` | date (nullable) | colonne Date (mono) |
| `duration_ms` | int (nullable) | colonne Durée (mono, `m:ss` / `h:mm:ss`) |
| `has_artwork` | bool | cover `/storage/set-artworks/{id}.jpg` si vrai, sinon placeholder `<Artwork>` |
| `total_tracks` | int | dénominateur du `<RingPct>` |
| `identified_tracks` | int | numérateur du `<RingPct>` → **toujours ≥ 1** (les 0 % sont exclus) |

Champs **présents dans le payload mais NON affichés** (ne pas les surfacer) : `source` (toujours `trackid`), `source_url`.
**Il n'y a PAS**, au niveau set : bpm, key, rating, extrait audio/play, indicateur in-lib, nombre de tracks brut affiché (le % suffit).

Filtre d'avis : le SegFilter résout les sets aimés/dislikés côté app ; pour toi c'est un segmented control dans le head (4 segments). Recherche texte : paramètre `q` (server-side). Tri : clic d'en-tête → `sort` server-side (titre / date / tracks / durée) + sens.

Source des genres cliquables : `<StyleTag>` pointe vers `/style/:name` (page détail genre existante).

## Design system — contraintes (rappel)

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. **Zéro couleur hardcodée.**
- **Typo** : `--font-ui` (Space Grotesk) pour le texte, `--font-mono` (JetBrains Mono) pour les données numériques (dates, durées, %, compteurs).
- **Thèmes** : `[data-theme="dark"]` par défaut + light — la maquette supporte les deux.
- **Responsive** : container queries (`@container`), jamais `@media` sauf éléments `position: fixed`. Convention repo : seuils **720/640**.
- **CSP stricte** : icônes en SVG inline ou data-URI, aucun CDN, aucune font externe.
- **UI en français.**
- **Monochrome `currentColor`** pour toute iconographie — l'accent mauve reste le seul signal coloré (les couleurs de pilier des `<StyleTag>` sont la seule autre couleur sémantique).

## Récapitulatif des livrables

| Fichier | Contenu |
|---------|---------|
| `BRIEF-sets-list.md` | Handoff page : head, panneau Ajouter, tableau enrichi (rangée + genre), états, empty states, responsive, tokens |
| `Sets (pilote).html` | Maquette interactive (table ~15 rangées + head + panneau Ajouter + empty state, toggles theme/viewport) |
| **Archive ZIP unique** | Les 2 livrables téléchargeables en un lien |

# Prompt — Claude Design · Refonte Genres (liste) — `/genres` (D6 p.7)

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/genres-list.md` (fiche de cadrage figée — décisions produit ; le bloc **« Précisions pré-vol 2026-07-28 » prime** en cas d'écart)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — composants partagés)
> - `docs/refonte-ui/handoff-artists-list/BRIEF-artists-list.md` (référence de **FORMAT uniquement** — brief le plus proche : **même paradigme grille-de-cards** ; ⚠️ son **contenu** concerne les Artistes — pastille follow, toggle sans-Deezer — qui **n'existent pas ici**, ne PAS le reprendre)
> - Captures de la page ACTUELLE (dossier `C:\tmp\captures-genres-list\`) :
>   - `01-desktop-dark-full.png` — grille de cards actuelle, desktop dark 1440px. Sur chaque card : **badge in-lib « N en bib »** (coin haut-gauche, disque + point vert) = **la dette à retirer** ; avatars d'artistes empilés (bas-gauche) + « +N » ; body teinté pilier : point + nom + pilier + stats **TRACKS · ARTISTES · BPM**.
>   - `02-desktop-light-full.png` — même vue, light.
>   - `03-mobile-375-dark.png` — mobile 375px (head empilé, FamilyChips en 3 rangées, grille 1 colonne, BottomNav 7 items).

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark par défaut, tokens centralisés). La refonte page par page continue : les 4 pages détail (Track, Playlist, Set, Artist) et 6 pages D6 (Explorer, Radar, Hub, Sets liste, Playlists liste, **Artistes liste**) sont livrées. On refait maintenant la liste **Genres**.

**Cette page : Genres (liste) — `/genres`.** ~75 genres, **grille de cards** avec infinite scroll, filtrable par pilier de genre et triable. La card actuelle (`GenreCard`) est **déjà propre et appréciée** (mosaïque 2×2 de covers en fond teintée par la couleur du pilier + avatars d'artistes + body teinté). William : « affichage clean, aimé, je ne vois pas trop quoi améliorer ». Le mouvement produit est donc un **assainissement léger + une harmonisation**, PAS une refonte de paradigme :

1. **retirer le badge in-lib overlay** (« N en bib », coin haut-gauche) qui est un **badge** alors que partout ailleurs (ArtistCard) l'in-lib est devenu une **stat de body** → on **harmonise** : l'in-lib devient une **stat « En bib »** dans la ligne de stats ;
2. côté head : **ajouter un segment de tri « En bib »** à la SegFilter (cohérence avec la liste Artistes qui a « In Bib »).

C'est tout. Aucune autre structure ne bouge.

**Format = GRILLE DE CARTES (verrouillé).** Contrairement aux listes Sets/Playlists (tableaux), Genres reste une grille de cards visuelles. Ne propose pas de tableau.

**Périmètre strict : design/UX uniquement.** Le shell de l'app (sidebar, BottomNav) est hors périmètre — tu ne designs que le **contenu de la page** (head + admin strip + FamilyChips + grille + card). Les données listées plus bas sont **exhaustives : ne rien inventer au-delà**.

**Composant : la card `GenreCard` est PROPRE à cette page** (aucune autre vue ne la consomme) — tu la **redessines** dans le respect de son anatomie gardée. Tu **consommes** par ailleurs `<LikeDislike>` (boutons avis, déjà implémenté, **sans le modifier** — spec dans TRANSVERSE.md).

> **Cette page ne crée AUCUN composant transverse nouveau.**

## Décisions produit FIGÉES (fiche jointe — à respecter, pas à rediscuter)

1. **Card GARDÉE dans son anatomie** : zone d'art (**mosaïque 2×2 de 4 covers** de tracks du genre en fond + tuiles placeholder **teintées par le pilier** quand une cover manque + scrim dégradé ; **avatars ronds** des top-3 artistes empilés en bas-gauche + pastille « +N » ; **boutons avis** `<LikeDislike>` en haut-droit au survol ; **bouton play** en bas-droit au survol = extrait aléatoire du genre) ; body **teinté par le pilier** (point coloré + nom + label pilier en petit + ligne de stats). Coloration de card selon l'avis : **liked = bordure/halo positif**, **disliked = card estompée**. Tout cela est **conservé** — raffine l'exécution (finitions, hover), ne casse pas l'anatomie.
2. **Retrait du badge in-lib overlay** (« N en bib », disque + point vert, coin haut-gauche) : **supprimé** de l'art. Le coin haut-gauche **se libère** — **ne rien y remettre** (n'ajoute aucune info non listée ; ce n'est PAS une page à pastille de suivi comme Artistes).
3. **In-lib devient une STAT de body « En bib »** : ajoutée à la ligne de stats, harmonisée avec la stat « In Lib » de la card Artistes → **valeur en `--pos-ink` quand > 0, « — » (`--ink-3`) quand 0**. C'est le seul canal de l'info in-lib désormais (plus de doublon badge + stat).
4. **PAS de « % de couverture » ni de mini-barre.** (La fiche l'évoquait en recap C2 ; retiré au pré-vol — mesuré en prod : le ratio in-lib/tracks vaut 0,1–5 % **partout**, une barre serait quasi-vide sur 100 % des cards = signal mort.) **Seul le compte in-lib brut est affiché.**
5. **Ligne de stats du body** = **Tracks** (`trackCount`) · **Artistes** (`artistCount`) · **BPM** (`bpmLo–bpmHi`, « – » si 0) · **En bib** (`inLibCount`, « — » si 0). *(Voir latitude DA §layout : 4 stats sur une ligne peuvent serrer — arbitrage à toi.)*
6. **Segment de tri « En bib » ajouté à la SegFilter** du head. SegFilter cible = **Tracks · A–Z · En bib · Liked · Disliked** (segmented control mêlant tris — Tracks / A–Z / En bib — et facettes d'avis — Liked / Disliked). « En bib » trie les genres par nombre de tracks dans la bibliothèque (décroissant). Place-le parmi les tris quantitatifs (près de « Tracks »), avant les facettes Liked/Disliked.
7. **Admin strip conservé** (visible **admin uniquement**) : bandeau « N tracks sans genre attribué — à classer » + bouton « Lancer le classement auto ». Latitude sur le style, pas sur la présence. (Note repli mobile : aujourd'hui le texte s'empile mal — tu peux améliorer.)
8. **FamilyChips conservés** : rangée de chips pilier (Tous / House / Techno / Trance / Drum & Bass / Hard Dance / Autres, chacun avec son compteur) = filtre par pilier. Latitude sur le style, pas sur la présence.
9. **Play conservé** : bouton play en survol (bas-droit de l'art) → extrait aléatoire du genre. Comportement inchangé.
10. **Scroll : infinite scroll** (sentinel, façon Explorer/Sets/Playlists/Artistes). Conservé. *(Note : les facettes Liked/Disliked sont résolues côté client sur la page chargée — pas de changement à concevoir.)*
11. **Clic sur la card → `/style/:name`** (la card entière est un lien). Les contrôles internes (play, avis) interceptent le clic sans naviguer.
12. **Libellés 100 % français.** **Pas d'état invité** (page interne toujours authentifiée — l'invité est confiné au Hub).

## Latitude DA (à toi de trancher, décisions à expliciter dans le brief)

- **Layout de la ligne de stats — LE point d'arbitrage central.** La card passe de **3 à 4 stats** (ajout « En bib »). Deux voies possibles, choisis et argumente :
  - (a) **4 stats sur une ligne** : Tracks · Artistes · BPM · En bib (séparateurs verticaux). Vérifie que ça ne serre pas trop, surtout sur card étroite (mobile 2 colonnes).
  - (b) **Remonter le BPM range** près du label pilier (ligne titre) et garder **3 stats** en bas : Tracks · Artistes · En bib. Libère de la place et met le BPM (info technique DJ) en évidence.
  - Tu peux aussi proposer une 3ᵉ variante cohérente (ex. En bib mis en exergue coloré à droite façon « avis »). Reste lisible et dense.
- **Traitement visuel de la stat « En bib »** : c'est l'info promue depuis le badge. Elle doit rester **repérable** (l'utilisateur qui cherchait le badge doit la retrouver) sans crier. Couleur `--pos-ink` quand > 0 (cohérent ArtistCard). Iconographie optionnelle (petit point/pastille) — monochrome, pas d'emoji.
- **Recomposition du coin haut-gauche** libéré par le retrait du badge in-lib : **le laisser vide** (recommandé — l'art respire). Ne déplace pas d'info technique dessus.
- **Head de page** : titre + compteur (« N genres » ; « N / Total » si filtré), SearchBox, SegFilter (5 segments avec « En bib »), rangée FamilyChips, admin strip — agencement, hiérarchie, **repli mobile** (aujourd'hui le head s'empile sous 820px, la search passe pleine largeur ; l'admin strip s'empile mal).
- **Grille responsive** : la grille actuelle est `repeat(auto-fill, minmax(296px, 1fr))` → 2 colonnes sous 720px → `minmax(150px,1fr)` sous 640px → 1 colonne sous 520px. Tu peux réajuster les paliers (convention repo : penser **720/640**) mais garde une grille dense et lisible ; évite le passage à 1 colonne trop tôt (la card Artistes a acté « jamais 1 colonne » en 2-col fixe < 640 — tu peux t'en inspirer).
- **Finitions de la card** : hover (élévation actuelle), transitions, densité du body, avatars (taille, chevauchement, « +N »), gestion des noms longs (ellipsis), scrim/lisibilité des covers.
- **Empty states** : chargement (skeleton de cards, déjà en place) ; filtre vide (« Aucun genre ne correspond. ») ; facette **Liked / Disliked vide** (message adapté).

## Note DONNÉES importante (vérifiée en prod — cadre tes choix)

- **L'in-lib est un vrai signal, variable** : sur 75 genres, **41 ont un compte in-lib > 0** (max **132**, ex. Dance/Pop), 34 à 0. C'est bien une info à afficher (compte), mais **pas un % de couverture** (le ratio est structurellement < 5 % partout, cf. §4 FIGÉ — n'affiche donc **jamais** de pourcentage ni de barre de progression).
- **Volumes réels** (pour des cards réalistes dans la maquette) : Tracks par genre de ~140 à ~11 900 ; Artistes de quelques-uns à ~6 800 ; BPM ranges variés (70–154) ; in-lib de 0 à 132. Piliers : House / Techno / Trance / Drum & Bass / Hard Dance / Autres (+ un gros « Autres » de 42 genres).

## Ce que tu dois livrer

### 1. `BRIEF-genres-list.md` — le handoff de la page

Même format que les briefs existants (tableaux de tokens, anatomie, états, décisions DA explicites). Doit couvrir : head de page (titre + compteur, SearchBox, **SegFilter 5 segments avec « En bib »**, FamilyChips, admin strip admin-only), **card redessinée** (anatomie art gardée : mosaïque 2×2 + scrim teinté pilier + avatars + « +N » + play hover + avis hover ; **retrait du badge in-lib overlay** ; body : point + nom + pilier + **ligne de stats Tracks · Artistes · BPM · En bib** avec ton arbitrage de layout), **états de card** (hover, liked = halo positif, disliked = estompée, en lecture), grille responsive (paliers + colonnes), empty states, repli mobile du head + admin strip. Explicite chaque token utilisé et **argumente l'arbitrage de layout des stats**.

### 2. `Genres (pilote).html` — maquette interactive

Maquette HTML autonome consommant les tokens de `diggy-tokens.css` (**zéro couleur hardcodée**), avec :
- la page complète, **~12–15 cards de données réalistes** : mosaïques de covers présentes ET tuiles placeholder teintées (genres sans assez de covers), **piliers variés** (house/techno/trance/dnb/hardcore/harddance/autres → couleurs de scrim/point/tag différentes), avatars présents + « +N », **stats variées** (Tracks de 140 à 11 900, BPM ranges, **En bib de 0 « — » à 132**), quelques cards liked (halo) / disliked (estompée) ;
- le **head dans ses états** : SegFilter sur « Tracks » puis sur « En bib » ; FamilyChips avec compteurs ; admin strip visible ;
- un **empty state** au choix (filtre vide ou facette Liked vide) ;
- **survol** d'une card montrant play + avis ;
- toggle **dark/light**, toggle **viewport desktop / 375px**.

### 3. ⚠️ **Livraison : une archive ZIP téléchargeable UNIQUE (un seul lien) contenant les 2 livrables.** Sans archive, le transfert des fichiers est manuel et casse le pipeline.

## Données disponibles (exhaustif — ne rien inventer au-delà)

`GET /api/genres` → `{ items[], total, pillarCounts }` (paginé, infinite scroll). Champs par item :

| Champ | Type | Usage design |
|---|---|---|
| `name` | string | nom de la card + lien `/style/:name` (ellipsis si long) |
| `pillar` | string | **colore toute la card** (scrim mosaïque + point + label + body + tags) ; l'un de house/techno/trance/dnb/hardcore/harddance/autres |
| `depth` | int | profondeur de style (nuance de teinte) |
| `trackCount` | int | stat **Tracks** |
| `artistCount` | int | stat **Artistes** |
| `bpmLo` / `bpmHi` | int | stat **BPM** (`lo–hi` ; `lo` seul si égaux ; « – » si les deux 0) |
| `inLibCount` | int | stat **En bib** (« — » si 0 ; `--pos-ink` si > 0) — **ex-badge overlay** |
| `artworks` | string[] (urls) | **mosaïque 2×2** de covers en fond (jusqu'à 4 ; tuile placeholder teintée si absente) |
| `artists` | objet[] | avatars empilés (bas-gauche) : `{ id, name, image }` (top-3) + « +N » via `artistCount` |

**Filtres / tri** (contrôles du head → params server-side) :
- `sort` : `tracks` \| `alpha` \| `lib` **(NOUVEAU = segment « En bib »)**. Les segments **Liked / Disliked** sont des **facettes d'avis** résolues côté client (n'affichent que les genres likés/dislikés de la page chargée) — pas un `sort` serveur.
- `family` : pilier (FamilyChips) ; `q` : recherche texte.
- `pillarCounts` : `{ pilier → compte }` pour les FamilyChips.

Contrôles interactifs **dans** la card (interceptent le clic, ne naviguent pas) : bouton **play** (hover, extrait aléatoire du genre), **boutons avis** `<LikeDislike>`.

**Il n'y a PAS**, au niveau card : bpm/key par track, durée, **% de couverture / mini-barre** (retiré), **badge in-lib overlay** (retiré), rating (jamais eu), pastille de suivi (concept Artistes, pas ici).

## Design system — contraintes (rappel)

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. **Zéro couleur hardcodée.**
- **Typo** : `--font-ui` (Space Grotesk) pour le texte, `--font-mono` (JetBrains Mono) pour les données numériques (stats Tracks/Artistes/BPM/En bib, compteurs de piliers).
- **Couleurs de pilier** : la card est **teintée par le pilier** (scrim + point + body + tags) — seule coloration sémantique large, **conservée**. Sinon **monochrome `currentColor`** pour l'iconographie (play, avis) + l'**accent mauve** comme signal d'action/état actif + **`--pos` / `--pos-ink`** pour le liké et la stat « En bib » positive.
- **Thèmes** : `[data-theme="dark"]` par défaut + light — la maquette supporte les deux.
- **Responsive** : container queries (`@container`), jamais `@media` sauf éléments `position: fixed`. Convention repo : penser seuils **720/640**.
- **CSP stricte** : icônes en SVG inline ou data-URI, aucun CDN, aucune font externe.
- **UI en français.**

## Récapitulatif des livrables

| Fichier | Contenu |
|---------|---------|
| `BRIEF-genres-list.md` | Handoff page : head (SegFilter + « En bib » + FamilyChips + admin strip), card redessinée (anatomie gardée + **retrait badge in-lib overlay** + **stat « En bib »** + arbitrage layout 3/4 stats), états de card, grille responsive, empty states, tokens |
| `Genres (pilote).html` | Maquette interactive (grille ~12–15 cards réalistes, stats En bib variées dont « — », head dans ses états, admin strip, empty, toggles theme/viewport) |
| **Archive ZIP unique** | Les 2 livrables téléchargeables en un lien |

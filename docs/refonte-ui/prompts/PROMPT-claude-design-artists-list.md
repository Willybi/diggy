# Prompt — Claude Design · Refonte Artistes (liste) — `/artists` (D6)

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/artists-list.md` (fiche de cadrage figée — décisions produit ; le bloc **« Précisions pré-vol 2026-07-27 » prime** en cas d'écart)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — composants partagés)
> - `docs/refonte-ui/handoff-playlists-list/BRIEF-playlists-list.md` (référence de **FORMAT uniquement** — brief récent, structure/tokens/anatomie ; ⚠️ son **contenu** concerne une liste **en TABLEAU** (Playlists) et **diffère** : ici la page est une **GRILLE DE CARTES**, ne PAS reprendre son layout)
> - Captures de la page ACTUELLE (dossier `C:\tmp\captures-artists-list\`) :
>   - `01-desktop-dark-full.png` — grille de cards actuelle, desktop dark 1440px. Sur les cards : **badge rating** « ★ 2.3 » (coin haut-droit) et **badge in-lib** « 32 en bib » (coin haut-gauche) = les **deux dettes à retirer**. Body : nom, tags genre, stats **CATALOG · IN LIB** + boutons avis.
>   - `02-desktop-light-full.png` — même vue, light.
>   - `03-mobile-375-dark.png` — mobile 375px (grille 1 colonne, head empilé, FamilyChips en ligne, BottomNav 7 items).

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark par défaut, tokens centralisés). La refonte page par page continue : les 4 pages détail (Track, Playlist, Set, Artist) et 5 pages D6 (Explorer, Radar, Hub, **Sets liste**, **Playlists liste**) sont livrées. On refait maintenant la liste **Artistes**.

**Cette page : Artistes (liste) — `/artists`.** ~57 700 artistes, **grille de cards** avec infinite scroll, filtrable par pilier de genre et triable. La card actuelle est **propre et appréciée** (photo d'artiste ronde centrée + mosaïque de covers en fond teintée par la couleur du pilier de genre) : **elle est GARDÉE**. Le mouvement produit est un **assainissement + un ajout ciblé**, pas une refonte de paradigme :
1. **retirer 2 badges parasites** de l'art de la card (le badge **rating** ★, le badge **in-lib** « N en bib » qui **double** la stat « In Lib » du body) ;
2. **ajouter la vraie nouveauté** : une **pastille-toggle « Suivi »** dans le coin haut-gauche ainsi libéré — elle **affiche l'état suivi ET sert de bouton follow/unfollow directement depuis la card** ;
3. côté head : remplacer le segment de tri **« Rating »** par un filtre **« Suivis »**, et ajouter un **toggle « sans Deezer »**.

**Format = GRILLE DE CARTES (verrouillé).** Contrairement aux listes Sets/Playlists (tableaux), Artistes reste une grille de cards visuelles (entité photo-driven). Ne propose pas de tableau.

**Périmètre strict : design/UX uniquement.** Le shell de l'app (sidebar, BottomNav) est hors périmètre — tu ne designs que le **contenu de la page** (head + grille + card). Les données listées plus bas sont **exhaustives : ne rien inventer au-delà**.

**Composant : la card `ArtistCard` est PROPRE à cette page** (aucune autre vue ne la consomme) — tu la **redessines** dans le respect de sa structure gardée. Tu **consommes** par ailleurs des composants partagés déjà implémentés, **sans les modifier** (spec dans TRANSVERSE.md) :
- `<StyleTag>` — pastille de genre colorée par pilier, cliquable → `/style/:name` (2 max sur la card).
- `<LikeDislike>` — boutons avis (like/dislike) dans le body.

> **Cette page ne crée AUCUN composant transverse nouveau.** La pastille-toggle « Suivi » est un élément **interne à la card** (comme le bouton play et les boutons avis qui y vivent déjà).

## Décisions produit FIGÉES (fiche jointe — à respecter, pas à rediscuter)

1. **Card GARDÉE dans sa structure** : zone d'art (mosaïque de 4 covers de top-tracks en fond + **scrim dégradé teinté par le pilier** du genre principal + **avatar rond centré** = photo de l'artiste ou initiales) ; body teinté pilier (nom centré, 1–2 `<StyleTag>`, ligne de stats + avis). **Fallback** sans covers = dégradé plein du pilier. Coloration de card selon l'avis : **liked = bordure/halo positif**, **disliked = card estompée**. Tout cela est **conservé** — tu peux raffiner l'exécution (finitions, hover), pas casser l'anatomie.
2. **Retrait du badge rating** (« ★ 2.3 » coin haut-droit) : **supprimé** de la card. Le rating disparaît **partout** sur cette page (badge + option de tri « Rating », voir §6).
3. **Retrait du badge in-lib overlay** (« N en bib » coin haut-gauche) : **supprimé** — il **double** la stat « In Lib » du body. L'info in-lib ne vit plus que dans la **stat « In Lib »** du body (§5).
4. **Pastille-toggle « Suivi » (LA nouveauté)** : dans le **coin haut-gauche libéré** par le retrait du badge in-lib. Double rôle **non négociable** :
   - **affiche l'état** : suivi / non-suivi, lisible d'un coup d'œil ;
   - **sert de bouton** : clic = follow/unfollow **directement depuis la card** (sans ouvrir la fiche).
   - **Suivi ≠ liké** (concepts décorrélés par design) : le **liké** s'exprime par la bordure/halo + les boutons avis du body ; le **suivi** par cette pastille. Les deux coexistent sur une même card, il faut les **distinguer visuellement**.
   - Elle a donc **au moins 2 états** (suivi actif / non-suivi) + une **affordance de bouton** (hover, focus). Pense au non-suivi comme **discret mais présent** (c'est l'état de la quasi-totalité des cards — voir note données), et au suivi comme **affirmé** (accent).
5. **Ligne de stats du body = 2 stats + avis** : **Catalog** (`nb_catalog`) · **In Lib** (`nb_lib`, « — » si 0) · puis les boutons **avis** (`<LikeDislike>`). *(Pas de 3e stat « nb_liked » : reportée — voir note données.)* Structure actuelle conservée.
6. **Rating retiré du tri** : la SegFilter du head perd le segment **« Rating »**, remplacé par un segment **« Suivis »** (filtre : n'afficher que les artistes suivis). SegFilter cible = **Catalog · In Bib · Liked · Disliked · Suivis · A–Z**. (Comme aujourd'hui, c'est un segmented control mêlant tris — Catalog/In Bib/A–Z — et filtres — Liked/Disliked/Suivis.)
7. **Toggle « sans Deezer »** : un contrôle de filtre **on/off** dans le head (à côté de la SegFilter ou des FamilyChips — latitude DA) qui restreint aux artistes **non liés à Deezer** (outil de curation : cibler le backlog d'enrichissement). Discret, off par défaut.
8. **FamilyChips conservés** : la rangée de chips pilier (Tous / House / Techno / Trance / Drum & Bass / Hard Dance / Autres, chacun avec son compteur) reste le filtre par pilier. Latitude sur le style, pas sur la présence.
9. **Play conservé** : bouton play en survol (coin bas-droit de l'art) qui lance un extrait aléatoire de l'artiste. Comportement inchangé.
10. **Scroll : infinite scroll** (sentinel, façon Explorer/Sets/Playlists). Conservé.
11. **Clic sur la card → `/artist/:id`** (la card entière est un lien). Les contrôles internes (play, pastille suivi, avis) interceptent le clic sans naviguer.
12. **Libellés 100 % français.** **Pas d'état invité** (page interne toujours authentifiée — l'invité est confiné au Hub).

## Latitude DA (à toi de trancher, décisions à expliciter dans le brief)

- **Traitement de la pastille-toggle « Suivi »** — c'est le cœur du travail. Forme (pastille ronde, chip, icône dans un rond) ; iconographie du suivi (une **icône SVG inline** — p.ex. cloche/étoile/personne+ — monochrome `currentColor`, pas d'emoji) ; **contraste des 2 états** (non-suivi discret sur l'art sombre vs suivi accentué mauve) ; **affordance de bouton** (hover/active/focus, feedback au clic) ; cohabitation visuelle avec le bouton play (bas-droit) et les boutons avis (body) pour qu'un utilisateur comprenne « suivre » ≠ « aimer ». Prévois l'état **hover-reveal** (comme le play) ou **toujours visible** — argumente.
- **Recomposition des coins de l'art** maintenant que rating (haut-droit) et in-lib (haut-gauche) partent : le haut-gauche accueille la pastille suivi ; le haut-droit se libère (le laisser vide est OK, ou y déplacer quelque chose — mais **n'ajoute pas d'info non listée**).
- **Head de page** : titre + compteur (« N artistes » ; « N / Total » si filtré), SearchBox, SegFilter (6 segments), toggle « sans Deezer », rangée FamilyChips — agencement, hiérarchie, et **repli mobile** (aujourd'hui le head s'empile sous 820px, la search passe pleine largeur sous 640px).
- **Placement du toggle « sans Deezer »** : près de la SegFilter, en fin de rangée FamilyChips, ou dans un petit groupe d'outils — à toi. Forme = `ToggleChip` / interrupteur discret (monochrome + accent quand actif).
- **Grille responsive** : la grille actuelle est `repeat(auto-fill, minmax(208px, 1fr))` puis passe à 2 colonnes sous 560px et 1 colonne sous 380px. Tu peux réajuster les paliers (convention repo : penser 720/640) mais garde une grille dense et lisible.
- **Finitions de la card** : hover (élévation actuelle), transitions, densité du body, gestion des noms longs (ellipsis), min-height des tags. Raffine sans casser l'anatomie gardée.
- **Empty states** : chargement (skeleton de cards, déjà en place) ; filtre vide (« Aucun artiste ne correspond. ») ; **filtre « Suivis » vide** (cas fréquent — voir note données : proposer un message d'invitation à suivre des artistes, p.ex. « Tu ne suis aucun artiste pour l'instant. »).

## Note DONNÉES importante (vérifiée en prod — cadre tes choix)

- **Le suivi est quasi-vide aujourd'hui** : sur ~57 700 artistes, **3** sont suivis (par un seul utilisateur). C'est **voulu et assumé** : la pastille-toggle est précisément **le moyen de suivre** (aujourd'hui il faut ouvrir la fiche → d'où le vide), et c'est une feature live qui alimente le Hub « Nouveautés ». **Conséquences design** : (a) l'état **non-suivi est l'état par défaut de la quasi-totalité des cards** → il doit être **discret** (ne pas polluer la grille) mais **présent et cliquable** ; (b) l'état **suivi est rare et précieux** → **affirmé** (accent). Ne conçois pas la pastille comme si la moitié des cards étaient suivies.
- **`nb_liked` (3e stat) est reporté** : données trop rares (39 artistes concernés). La card garde **2 stats + avis**.
- **Le toggle « sans Deezer » a une vraie cible** : 534 artistes non liés à Deezer.

## Ce que tu dois livrer

### 1. `BRIEF-artists-list.md` — le handoff de la page

Même format que les briefs existants (tableaux de tokens, anatomie, états, décisions DA explicites). Doit couvrir : head de page (titre + compteur, SearchBox, SegFilter 6 segments avec « Suivis », toggle « sans Deezer », rangée FamilyChips), **card redessinée** (anatomie art : mosaïque + scrim teinté pilier + avatar ; **pastille-toggle « Suivi » dans ses états** suivi/non-suivi + hover/focus ; play hover ; body : nom, tags genre, stats Catalog · In Lib, avis), **états de card** (hover, liked = halo positif, disliked = estompée, suivi actif, en lecture), grille responsive (paliers + colonnes), empty states (chargement / filtre vide / **filtre « Suivis » vide**), repli mobile du head. Explicite chaque token utilisé.

### 2. `Artistes (pilote).html` — maquette interactive

Maquette HTML autonome consommant les tokens de `diggy-tokens.css` (**zéro couleur hardcodée**), avec :
- la page complète, **~12–15 cards de données réalistes** : mélange de photos d'artiste présentes / initiales (fallback), **mosaïques de covers** présentes et **fallback dégradé plein** (artistes sans covers), **piliers de genre variés** (house/techno/trance/dnb/hardcore/autres → couleurs de scrim différentes), 1–2 `<StyleTag>` (dont noms longs en ellipsis), stats Catalog/In Lib variées (dont In Lib « — »), **quelques cards suivies (pastille active)** mais **la majorité non-suivies (pastille discrète)** — reflète le ratio réel, quelques cards liked (halo) / disliked (estompée) ;
- le **head dans ses états** : SegFilter sur « Catalog » puis sur « Suivis » ; toggle « sans Deezer » off puis on ; FamilyChips avec compteurs ;
- un **empty state** : filtre « Suivis » vide (message d'invitation) ;
- **survol** d'une card montrant play + pastille suivi + affordances ;
- toggle **dark/light**, toggle **viewport desktop / 375px**.

### 3. ⚠️ **Livraison : une archive ZIP téléchargeable UNIQUE (un seul lien) contenant les 2 livrables.** Sans archive, le transfert des fichiers est manuel et casse le pipeline.

## Données disponibles (exhaustif — ne rien inventer au-delà)

`GET /api/artists/` → `{ items[], total, pillarCounts }` (paginé, infinite scroll). Champs par item **à la cible** (après le lot back de ce chantier) :

| Champ | Type | Usage design |
|---|---|---|
| `id` | int | clé + lien `/artist/:id` + avatar `/storage/artist-artworks/{id}.jpg` |
| `name` | string | nom de la card (centré, ellipsis si long) |
| `has_artwork` | bool | avatar = photo si vrai, sinon **initiales** |
| `nb_catalog` | int | stat **Catalog** |
| `nb_lib` | int | stat **In Lib** (« — » si 0) |
| `following` | bool **(NOUVEAU)** | état de la **pastille-toggle « Suivi »** (suivi / non-suivi) |
| `genres` | objet[] | 1–2 `<StyleTag>`, chacun `{ name, pillar, depth }` : `name` affiché, `pillar` **colore la card + le scrim + les tags**, lien `/style/:name`. Le **pilier de `genres[0]` teinte toute la card**. Peut être vide → card « autres » (neutre). |
| `top_track_artworks` | string[] (urls) | **mosaïque** de covers en fond (4 tuiles ; les covers réelles des top-tracks) |
| `tracks_with_artwork` | int | ≥ 1 → mosaïque affichée ; 0 → fallback dégradé plein |

**Filtres / tri** (contrôles du head → params server-side) :
- `sort` : `catalog` \| `lib` \| `liked` \| `disliked` \| `alpha` — **`rating` RETIRÉ**.
- filtre **« Suivis »** → `followed=true` **(NOUVEAU)** (n'affiche que les `following=true`).
- `family` : pilier (FamilyChips) ; `q` : recherche texte ; `no_deezer=true` : toggle « sans Deezer ».
- `pillarCounts` : `{ pilier → compte }` pour les FamilyChips.

Contrôles interactifs **dans** la card (interceptent le clic, ne naviguent pas) : bouton **play** (hover, extrait aléatoire), **pastille-toggle Suivi** (POST/DELETE `/api/artists/{id}/follow`), **boutons avis** `<LikeDislike>`.

Champs **présents mais NON affichés** (ne pas les surfacer) : `avg_rating` (**retiré**), `nb_liked` (**reporté**, pas de 3e stat).
**Il n'y a PAS**, au niveau card : bpm, key, durée, % identifié, badge in-lib overlay, badge rating.

## Design system — contraintes (rappel)

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. **Zéro couleur hardcodée.**
- **Typo** : `--font-ui` (Space Grotesk) pour le texte, `--font-mono` (JetBrains Mono) pour les données numériques (compteurs Catalog/In Lib, compteurs de piliers).
- **Couleurs de pilier** : la card est **teintée par le pilier du genre principal** (scrim + body + tags) — c'est la seule coloration sémantique large, elle est **conservée**. Sinon **monochrome `currentColor`** pour l'iconographie (play, pastille suivi, avis) + l'**accent mauve** comme signal d'action/état actif.
- **Thèmes** : `[data-theme="dark"]` par défaut + light — la maquette supporte les deux.
- **Responsive** : container queries (`@container`), jamais `@media` sauf éléments `position: fixed`. Convention repo : penser seuils **720/640**.
- **CSP stricte** : icônes en SVG inline ou data-URI, aucun CDN, aucune font externe.
- **UI en français.**

## Récapitulatif des livrables

| Fichier | Contenu |
|---------|---------|
| `BRIEF-artists-list.md` | Handoff page : head (SegFilter + « Suivis » + toggle sans-Deezer + FamilyChips), card redessinée (anatomie gardée + **pastille-toggle Suivi** dans ses états + retrait badges rating/in-lib), états de card, grille responsive, empty states (dont « Suivis » vide), tokens |
| `Artistes (pilote).html` | Maquette interactive (grille ~12–15 cards réalistes, pastille suivi majoritairement discrète + quelques suivies, head dans ses états, toggle sans-Deezer, empty « Suivis », toggles theme/viewport) |
| **Archive ZIP unique** | Les 2 livrables téléchargeables en un lien |

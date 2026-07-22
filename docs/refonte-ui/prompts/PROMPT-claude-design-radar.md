# Prompt — Claude Design · Nouvelle page Radar (D6)

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/radar.md` (fiche de cadrage figée de la page Radar — décisions produit, dont la §7 « Décisions Phase 0 »)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — composants partagés, dont `<ScoreRing>`)
> - `docs/refonte-ui/handoff-explorer/BRIEF-explorer.md` (référence de FORMAT + la table/filtres que Radar réutilise — son contenu concerne Explorer et peut contredire les décisions ci-dessous, qui priment)
> - `docs/refonte-ui/handoff-explorer/BRIEF-filtres-partages.md` (spec de la mécanique de filtres que Radar réutilise **telle quelle** — à ne PAS redessiner)
> - Captures de la page de RÉFÉRENCE (Explorer actuel, dont Radar reprend le squelette de table + la barre de filtres) — dossier `C:\tmp\captures-radar\` :
>   - `01-explorer-desktop-dark.png` — table Explorer, desktop dark 1440px (head + barre de filtres fermée + rangées) : **le squelette que Radar étend**
>   - `02-explorer-desktop-light.png` — idem, thème light
>   - `03-explorer-mobile-375-dark.png` — mobile 375px : column-drop + play/avis toujours visibles
>   - `04-explorer-desktop-dark-filters-open.png` — **panneau de filtres déplié** (BPM/Année, grille Camelot, Styles par pilier, Durée, Bibliothèque, Artiste, Label, Avis, Extrait) : la mécanique que Radar réutilise sans la re-concevoir

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark mode par défaut, tokens centralisés). La refonte page par page continue : les 4 pages détail (Track, Playlist, Set, Artist) et **Explorer** sont livrées. On crée maintenant une **nouvelle page : Radar — `/radar`**.

**Ce qu'est Radar : la surface de recommandation bi-score de l'app.** Une **seule liste** de sons, où chaque ligne porte **deux scores de recommandation côte à côte** :
- **Tendance** — ce qui monte dans la scène (classement global, calculé chaque nuit).
- **Pour toi** — recommandation personnalisée (croisement de tes goûts et du moteur de similarité).

On **trie par l'un ou l'autre**. Beaucoup de sons n'auront qu'un des deux scores → l'autre colonne affiche « — ». Radar n'est **pas** une boîte de tri/inbox : c'est une surface de découverte curée, dense, façon Explorer mais orientée reco.

**Radar réutilise le squelette d'Explorer** : même table dense virtualisée, même barre de filtres (captures 01/04), mêmes composants partagés. La nouveauté design = **les deux colonnes de score** (`<ScoreRing>`) intégrées proprement dans la ligne, leur en-tête triable/surligné, l'état « — », le cold-start, et le re-calibrage responsif induit par ces 2 colonnes en plus.

**Périmètre strict : design/UX du contenu de la page uniquement.** Le shell (sidebar, BottomNav) est hors périmètre — tu ne le designs pas (une entrée de nav « Radar » sera ajoutée côté implémentation, ne t'en occupe pas). Les données listées plus bas sont **exhaustives** : ne rien inventer au-delà.

**Composants transverses : cette page n'en crée AUCUN.** `<ScoreRing>`, `<Artwork>` (cover + placeholder rayé + indicateur in-lib en coin : point plein = dans la bibliothèque Rekordbox, cercle pointillé = absent), la famille de filtres (`FilterBar`/`FilterPanel`/`FilterDrawer` + contrôles), `<StyleTag>`, `<LikeDislike>` existent déjà et sont implémentés. Tu les **CONSOMMES**, tu ne les re-designes pas. En particulier :
- **`<ScoreRing>` (contrat FIGÉ)** : jauge circulaire, arc mauve `--accent`, **note entière /10 au centre** (police mono). Deux tailles : `sm` 30px, `md` 40px. Entrée = un score 0–1, affichage = `round(score×10)`. Ne redéfinis PAS sa géométrie ; décide juste **où** il se place, **quelle taille**, et son comportement en colonne.
- **La barre/panneau/drawer de filtres** : identique à Explorer (BRIEF-filtres-partagés joint). Ne la re-conçois pas ; montre-la dans la maquette Radar telle qu'elle est, avec le jeu de filtres pertinent (ci-dessous).

## Décisions produit FIGÉES (fiche jointe + §7 — à respecter, pas à rediscuter)

1. **Rôle** : Radar = **liste unique bi-score**. Chaque son = infos + **score Tendance + score Pour toi** (deux `<ScoreRing>` côte à côte), tri par l'un ou l'autre.
2. **Colonnes** (jeu figé, fiche §5) : **Play** · **Track** (cover `<Artwork>` avec indicateur in-lib + titre + artistes cliquables) · **Style** (`StyleTag` cliquable → `/style/:genre`) · **BPM** · **Key** · **Tendance** (`<ScoreRing>`) · **Pour toi** (`<ScoreRing>`) · **Avis** (like/dislike). **Pas de colonne Durée** (contrairement à Explorer — elle saute pour laisser la place aux 2 scores). Pas de rating (purge projet). Badge `#rank` (petit, sur le titre, si `trend_rank` ≤ 50) conservé comme sur Explorer.
3. **Les 2 scores** : rendus en `<ScoreRing>`. Note `/10` **relative à SA colonne** (10 = le plus tendance / 10 = ton meilleur match) — ce sont deux recommandations distinctes, pas la même échelle. Un score absent = **« — »** discret (pas de ring, tiret muet `--ink-3`), fréquent : beaucoup de lignes n'ont qu'un seul des deux.
4. **Tri** : sélecteur explicite — **Tendance (défaut, TOUJOURS)** · Pour toi · BPM · Récent. La **colonne de score active est surlignée**. Le tri par clic d'en-tête reste souhaitable sur Tendance / Pour toi / BPM.
5. **Filtres façon Explorer** (mécanique réutilisée telle quelle) : priorité au trio **Style · BPM · Key** (cas d'usage cible : « ce qui monte en techno 130–135 qui me correspond »). Les autres contrôles Explorer (Année, Durée-en-filtre, Bibliothèque tri-state, Artiste, Label, Avis, Écoutable) restent disponibles via le même panneau. Filtres synchronisés dans l'URL (bookmarkable).
6. **Like/dislike classique** : comportement identique à Explorer (coloration de ligne : liked = wash positif, disliked = ligne estompée), **aucune pondération spéciale** des likes Radar.
7. **Cold-start** (utilisateur connecté sans likes) : la colonne **Pour toi est vide (« — » partout)** → la page s'ouvre sur le tri **Tendance** (le défaut de toute façon) + une **invite légère à liker** pour activer « Pour toi ». À designer comme un état, pas une page séparée.
8. **Scroll : infinite scroll virtualisé** (windowing — seules les lignes visibles rendues). Induit : **hauteur de rangée CONSTANTE**, en-tête de table **sticky**. Pas de pagination.
9. **Conservés** : play inline (extrait), clic ligne → page détail track (`/catalog/:id`), ligne en cours de lecture surlignée.
10. **Libellés 100 % français.** **Pas d'état invité** : page interne toujours authentifiée (l'invité est confiné au Hub — ne conçois aucun état déconnecté).

## Latitude DA (à toi de trancher, à expliciter dans le brief)

- **Intégration des 2 colonnes de score** : c'est LE morceau design de cette page. Taille des `<ScoreRing>` (`sm`/`md`) dans une rangée dense (~56px comme Explorer), en-têtes « Tendance » / « Pour toi », traitement de la colonne **active** (surlignage de l'en-tête + éventuellement de la colonne), lisibilité des deux anneaux côte à côte sans surcharger, alignement, largeur de colonne.
- **État « — »** (score absent) : forme exacte du tiret muet, pour qu'une ligne mono-score reste lisible et n'ait pas l'air « cassée ».
- **Accent velocity (OPTIONNEL, basse priorité)** : un son qui « monte vite » (`velocity` élevée) peut recevoir un accent léger sur l'anneau Tendance (ex. petit ▲). Propose-le si élégant, sinon ignore — non bloquant.
- **Échelle de column-drop responsive** : Radar a **2 colonnes de plus** qu'Explorer (les 2 scores) et une de moins (Durée). Les 2 scores sont **la raison d'être de la page** → ils doivent **survivre le plus longtemps** dans l'ordre de disparition (Style, puis Key, puis BPM tombent avant). Sous 640px (tactile) : **play et avis toujours visibles** ; propose ce qui reste (a minima Track + les 2 scores + play/avis).
- **Cold-start** : forme de l'invite à liker quand « Pour toi » est vide (bandeau discret ? état de colonne ? tooltip d'en-tête ?).
- **Empty states** : aucun résultat avec les filtres (assouplir/reset, comme Explorer) vs chargement (skeleton en rangées fantômes dans la grille).
- **En-tête de page** : titre « Radar » + sous-titre/compteur éventuel, place de la barre de filtres et du sélecteur de tri (réutilise la disposition Explorer, capture 01).

## Ce que tu dois livrer

### 1. `BRIEF-radar.md` — le handoff de la page

Même format que les briefs existants (tableaux de tokens, anatomie, états, décisions DA explicites). Doit couvrir : head de page (titre, compteur, tri), rappel de la barre de filtres réutilisée (sans la re-spécifier — pointer vers BRIEF-filtres-partagés), **anatomie de la ligne avec les 2 colonnes de score** (dimensions, alignements, tailles de `<ScoreRing>`, en-têtes triables + surlignage colonne active, état « — », accent velocity optionnel), hauteur de rangée fixe, sticky header, états de ligne (hover, playing, liked, disliked, sans preview), badge #rank, **cold-start (Pour toi vide + invite)**, empty states, **responsive complet** (échelle de column-drop qui préserve les 2 scores + comportement mobile), pilote 375px.

### 2. `Radar (pilote).html` — maquette interactive

Maquette HTML autonome consommant les tokens de `diggy-tokens.css` (zéro couleur hardcodée), avec :
- la page complète avec données réalistes (~20 rangées), incluant : des lignes **avec les deux scores**, des lignes **Tendance seule** (« — » côté Pour toi), des lignes **Pour toi seule** (« — » côté Tendance), mélange in-lib/hors-lib, avec/sans cover, liked/disliked, badge #rank sur 1–2 titres, 1 ligne avec accent velocity si tu l'implémentes ;
- le tri par **Tendance** actif par défaut (colonne surlignée), et une vue montrant le tri **Pour toi** actif ;
- l'état **cold-start** (colonne Pour toi entièrement « — » + invite à liker) ;
- la barre de filtres (fermée + panneau ouvert avec quelques filtres actifs + chips), et l'**empty state** « aucun résultat » ;
- le **drawer mobile** ouvert ;
- toggle **dark/light**, toggle viewport **desktop / 375px**.

### 3. ⚠️ **Livraison : une archive ZIP téléchargeable UNIQUE (un seul lien) contenant les 2 livrables.** Sans archive, le transfert des fichiers est manuel et casse le pipeline.

## Données disponibles (exhaustif — ne rien inventer au-delà)

Un **nouvel endpoint** (lot back du chantier) renverra la liste bi-score. Forme par item (surface = catalog + 2 scores) :
`id`, `title`, `artist` (chaîne de repli), `artists[]` (id, name — plusieurs possibles, jamais en supposer un seul), `bpm` (float, arrondi à l'affichage), `key` (Camelot `"8A"`, nullable), `genres[]` (name, pillar, depth), `style` (repli si `genres` vide), `has_artwork` (cover : `/storage/catalog-artworks/{id}.jpg`), `has_preview`, `in_lib` (bool), `avis` (`liked`/`disliked`/null), `artist_id`, `trend_rank` (nullable, badge si ≤ 50), **`trend_score_10`** (float /10, **nullable** → « — » si non tendance), **`reco_score_10`** (float /10, **nullable** → « — » si non recommandé), `velocity` (float nullable — pour l'accent « monte vite » optionnel).
`duration_ms` existe mais **n'est pas affiché** (pas de colonne Durée sur Radar).

- La liste est une **union bornée** : top tendances par famille de genre ∪ tes ≤100 recommandations perso. La plupart des lignes n'ont donc qu'un seul score.
- **Auth obligatoire** (JWT). Cold-start (aucun like) → `reco_score_10` = null partout.

Sources des options de filtres (identiques à Explorer) :
- Styles : `GET /api/catalog/genres` → liste plate `{ name, count, pillar, depth }` (groupée par pilier dans le multi-select).
- Artiste (type-ahead) : `GET /api/artists/?q=…` → `{ id, name, … }`.
- Keys : les 24 valeurs Camelot `1A`…`12B` (statiques).

## Design system — contraintes (rappel)

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. Zéro couleur hardcodée.
- **Typo** : `--font-ui` (Space Grotesk) pour le texte, `--font-mono` (JetBrains Mono) pour les données numériques (BPM, key, notes des scores, compteurs).
- **Thèmes** : `[data-theme="dark"]` par défaut + light — la maquette supporte les deux.
- **Responsive** : container queries (`@container`), jamais `@media` sauf éléments `position: fixed` (le drawer mobile peut en être un). Convention repo : seuils 720/640.
- **CSP stricte** : icônes/logos en SVG inline ou data-URI, aucun CDN, aucune font externe.
- **UI en français.**
- **Monochrome `currentColor`** pour toute iconographie — l'accent mauve reste le seul signal coloré (y compris l'arc des `<ScoreRing>`).

## Récapitulatif des livrables

| Fichier | Contenu |
|---------|---------|
| `BRIEF-radar.md` | Handoff page : head, rappel filtres, **ligne bi-score (2 ScoreRing)**, tri/colonne active, état « — », cold-start, états de ligne, empty states, responsive préservant les 2 scores, tokens |
| `Radar (pilote).html` | Maquette interactive (page + états bi-score + cold-start + filtres + drawer mobile, toggles theme/viewport) |
| **Archive ZIP unique** | Les 2 livrables téléchargeables en un lien |

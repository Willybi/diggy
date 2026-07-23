# Prompt — Claude Design · Refonte Hub / accueil (D6)

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/hub.md` (fiche de cadrage figée du Hub — décisions produit)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — composants partagés, funnel invité, système d'icônes)
> - `docs/refonte-ui/handoff-radar/BRIEF-radar.md` (**référence de FORMAT uniquement** — son contenu concerne Radar et peut contredire les décisions ci-dessous, qui priment)
> - Captures de la page ACTUELLE (`/`) — dossier `C:\tmp\captures-hub\` :
>   - `01-current-desktop-dark-full.png` — Hub **connecté**, desktop dark, pleine hauteur : hero + search + Genres populaires + Essaie + les 3 étagères (Ça sort / Pour toi / Nouveautés). **C'est la surface principale à refondre.**
>   - `02-current-desktop-light-full.png` — idem, thème light.
>   - `03-current-mobile-375-dark.png` — connecté, mobile 375px (shelves en 1 colonne).
>   - `04-current-guest-desktop-dark.png` — Hub **invité**, desktop dark : PAS de sidebar (invité confiné au Hub, pleine largeur), top-right « Créer un compte / Se connecter », Ça sort visible MAIS ni Pour toi ni Nouveautés.
>   - `05-current-search-results-desktop-dark.png` — **état résultats de recherche** (connecté, requête « house ») : liste unifiée typée (GENRE/PLAYLIST/SET/ARTISTE/TRACK), badges de type + source, tri Pertinence/BPM/A–Z, highlight du terme.

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark mode par défaut, tokens centralisés). La refonte page par page continue : les 4 pages détail, **Explorer** et **Radar** sont livrées. On refond maintenant la page d'accueil : **Hub — `/`** (`HubView.vue`).

**Ce qu'est le Hub : la porte d'entrée de l'app + le moteur de recherche global.** C'est la **seule** page à double état (toutes les autres pages internes sont réservées aux connectés) :
- **État vide** (champ de recherche vide) = accueil : hero + search bar + amorces + étagères de découverte.
- **État recherche** (champ rempli) : liste de résultats unifiée (track/artiste/set/playlist/genre).

Et il gère **deux publics** :
- **Invité** : PAS de sidebar (confiné au Hub), voit le hero + search + Ça sort (aperçu tendances) ; le « voir plus » et les actions profondes **mènent au login** (funnel de conversion voulu, pas un manque). En recherche : lock-row « connecte-toi pour voir les N autres ».
- **Connecté** : sidebar présente (shell hors périmètre), voit les 3 étagères (Ça sort / Pour toi / Nouveautés) + outils de tri en recherche.

**C'est une REFONTE, pas une création** : la page existe (captures jointes), les données sont déjà servies par l'API (une seule exception back listée plus bas). Ton travail : réorganiser l'état vide, **créer la spec d'un composant carte de découverte partagé** enrichi (BPM · KEY · âge), et polir l'ensemble.

**Périmètre strict : design/UX du contenu du Hub.** Le shell (sidebar, BottomNav, PlayerBar) est **hors périmètre** — ne le designe pas. Les données listées plus bas sont **exhaustives** : ne rien inventer au-delà.

## Décisions produit FIGÉES (fiche + arbitrages Phase 0 — à respecter, pas à rediscuter)

1. **Genres populaires : bloc SUPPRIMÉ** du Hub (allègement, « état vide maîtrisé »). L'entrée par genre reste couverte par « Essaie », le scope `genre` de la recherche et la page Genres. Ne le fais PAS réapparaître.
2. **« Essaie » déplacé JUSTE sous la search bar** (ce sont des amorces de recherche, leur place est avec l'input). Nouvelle **icône flèche** (fin du `↳` en `::before`). Devient le seul bloc d'amorces de l'état vide.
3. **« Ça sort en ce moment »** : aperçu réduit au **top 9** (grille 3×3 nette) + bouton **« Voir plus »**. Cible : **`/radar`** (la page Radar EXISTE désormais — oublie l'ancienne cible provisoire `/catalog?view=radar` de la fiche). **Invité → `/login`.** L'étagère et ses `FamilyChips` restent visibles aux invités ; ouvrir une carte en invité → invite à se connecter.
4. **« Pour toi »** : **reste en aperçu sur le Hub** (top 9) + **« Voir plus » → `/radar`** (colonne « Pour toi » ; connecté uniquement).
5. **« Nouveautés de tes artistes »** : aperçu (connecté) + bouton **« Voir plus » DÉSACTIVÉ** (état grisé/non cliquable, libellé type « bientôt ») — la page dédiée `/new-releases` n'existe pas encore (chantier ultérieur). Le bouton doit exister visuellement (cohérence avec les 2 autres étagères) mais être **inerte et lisiblement désactivé**, sans lien mort. À designer comme un **état désactivé** propre.
6. **Cartes de découverte enrichies** : afficher **BPM · KEY · « Sorti il y a… »** (âge) en **ligne mono compacte** sur les cartes des **3 étagères** — PAS en lignes empilées (la carte est compacte). Dégrader proprement quand une donnée manque (sets sans BPM/KEY ; carte sans `release_date` → pas d'âge). → produit un **composant carte partagé** (voir livrables).
7. **Search bar — dropdown de scope** : **unifier les icônes en SVG** (fin des emoji `⊕ ♫ ● ◎ ☰ ◆` du bouton ; un set SVG cohérent existe déjà côté menu) + afficher un **compteur par scope** dans le menu en état recherche (nombre de résultats de CE type pour la requête courante). Latitude sur la forme ; « Tout » peut se passer d'icône (texte seul).
8. **Logo** : **hors périmètre** (sujet brand transverse, long terme). Le glyph « D » dans un carré accent reste tel quel (top bar + hero). Ne conçois PAS de nouveau logo.
9. **Parcours invité = funnel voulu** : montrer LIBREMENT le contenu (Ça sort, aperçus), **gater** le « voir plus » et les actions profondes derrière le login. Ce n'est pas un manque, c'est le design. **Aucun autre état invité à concevoir sur les pages internes** (elles sont toujours authentifiées) — mais le Hub, LUI, gère bien les deux publics.
10. **Libellés 100 % français.** Rating (étoiles Rekordbox) : absent du Hub, ne rien ajouter.

## Latitude DA (à toi de trancher, à expliciter dans le brief)

- **La carte de découverte** (le morceau design de ce handoff) : aujourd'hui horizontale (cover ~80px à gauche, infos à droite ; grille `repeat(auto-fill, minmax(240px, 1fr))`). Tu peux garder l'horizontale ou proposer une verticale — **contrainte** : elle doit accueillir la **ligne méta `BPM · KEY · âge`** sans surcharge, rester lisible en 1 colonne mobile, et **cohabiter dans la même grille** avec la carte album dépliable existante (voir plus bas). Tranche et justifie.
- **Placement de la méta** `BPM · KEY · âge` : ligne mono compacte (façon `.rmeta`), séparateurs, quoi masquer d'abord si la place manque.
- **Icône « Essaie »** : la nouvelle flèche/marqueur d'amorce.
- **Dropdown de scope** : traitement des icônes SVG + du compteur par type (état recherche), état sélectionné, hover.
- **Hiérarchie de l'état vide** après retrait de Genres populaires : rythme vertical hero → search → Essaie → étagères (éviter l'empilement d'accueil ; recherche en priorité, puis découverte).
- **En-têtes d'étagère** : titre + « Voir plus » (dont l'état **désactivé** de Nouveautés), badge « N nouvelles » de Nouveautés, place des `FamilyChips` sous « Ça sort ».
- **Bouton play** sur les cartes : au survol desktop, **toujours visible < 640px** (tactile).
- **Polish transverse** : hero, top bar (glyph D + CTA login invité / pastille user connecté), search bar (focus ring), état résultats (léger — voir périmètre). Harmonise, ne réinvente pas la liste de résultats.

## Périmètre de l'état RÉSULTATS de recherche (capture 05)

**Conservé fonctionnellement**, tu le POLIS seulement (typo, espacements, cohérence tokens) : liste `rrow` typée (badge de type + libellé), `<Artwork>` par ligne, highlight du terme, méta track `BPM · KEY · durée`, badge source playlist, zone in-lib (« EN BIB » / bouton +), outils de tri (Pertinence/BPM/A–Z) pour les connectés, **lock-row invité** « connecte-toi pour voir les N autres ». N'ajoute PAS de fonctionnalité ici (hormis les compteurs de scope du point 7, qui vivent dans le dropdown). Montre-le dans la maquette pour valider l'harmonie visuelle.

## Ce que tu dois livrer

### 1. `BRIEF-hub.md` — le handoff de la page

Même format que les briefs existants (tableaux de tokens, anatomie, états, décisions DA explicites). Doit couvrir :
- **Top bar** (sticky) : glyph « D » + wordmark « Diggy » (masqué en état recherche aujourd'hui), à droite CTA invité (« Créer un compte » ghost + « Se connecter » plein) OU pastille user connecté.
- **Hero** (état vide) : gros glyph « D » + « Diggy » + tagline. Empilé/réduit sur mobile.
- **Search bar** : dropdown de scope (SVG + compteurs en recherche) + champ + bouton clear. Focus ring accent. C'est l'élément central.
- **« Essaie »** : juste sous la search bar, chips d'amorces (house, disclosure, boiler room…), nouvelle icône.
- **Les 3 étagères** (état vide, connecté) : en-tête (titre + « Voir plus »/désactivé), grille top 9 3×3 desktop / 1 colonne mobile, `FamilyChips` sous « Ça sort », badge « N nouvelles » sur Nouveautés. Anatomie de la **carte de découverte** enrichie (voir composant).
- **Carte album dépliable** (`ActivityAlbumCard`, EXISTE déjà) : dans « Nouveautés », un artiste sortant un album produit **1 carte album dépliable en N titres** (au lieu de N cartes). Elle vit dans la même grille que les cartes unitaires → spécifie son **alignement visuel** avec la nouvelle carte (mêmes dimensions, même méta) ; tu ne la re-crées pas, tu cales son look.
- **État résultats** : cf. section périmètre ci-dessus (polish).
- **Double public** : décris explicitement l'état **invité** (pas de sidebar — mais tu ne designes pas la sidebar ; pleine largeur ; Ça sort visible ; « Voir plus » → login ; lock-row en recherche) vs **connecté** (3 étagères + outils de tri).
- **États** : chargement des étagères (**skeleton** en cartes fantômes — déjà en place sur « Pour toi »), étagère vide (« Ça sort » avec une famille à 0 titre visible → message « aucune sortie dans ce style », chips conservées), aucun résultat de recherche, ligne/carte en cours de lecture (`playing`), hover.
- **Responsive** : container queries (`@container`). Seuils actuels 680 / 640 / 540px (convention repo 720/640 — aligne si pertinent, justifie). Play toujours visible < 640px. Shelves en 1 colonne < 640px.

### 2. `BRIEF-composants-hub.md` — la spec du composant carte de découverte partagé

**Point clé de ce handoff.** Aujourd'hui les 3 étagères dupliquent chacune leur markup de carte inline. Spécifier **un composant réutilisable** (nom proposé : **`<DiscoveryCard>`** — NE PAS l'appeler `TrackCard`, qui est déjà le composant **ligne dense** existant, distinct). Il sera consommé par les aperçus Hub ET les futures pages destinations (`/new-releases`). À spécifier comme composant autonome, pas comme du styling de page. Il doit couvrir cette **matrice de variantes** (une seule anatomie, props optionnelles) :

| Variante | Badge | Méta | Cible clic | Cover/Play |
|---|---|---|---|---|
| Ça sort (tendance) | `#rank` (accent) | `BPM · KEY` (+ âge après back) | `/catalog/:id` (invité → login) | cover + play si preview |
| Pour toi (reco) | — | `BPM · KEY · âge` | `/catalog/:id` | cover + play si preview + indicateur in-lib possible |
| Nouveautés — release crawlée | « Nouveauté » | `BPM · KEY · âge` | `/catalog/:id` | cover + play si preview |
| Nouveautés — release lien externe | « Nouveauté » | — | lien Deezer externe (`target=_blank`) | pas de cover/play |
| Nouveautés — set | « Set » | — | `/set/:id` | pas de cover/play |

- **`<Artwork>`** (EXISTE) : la cover réelle OU le placeholder rayé + indicateur in-lib optionnel en coin (point plein = dans la bib Rekordbox, cercle pointillé = absent). Tu le **consommes**, tu ne le re-designes pas.
- Props attendues (indicatif) : `title`, `artist`, cover id + `has_artwork`, `has_preview`, `rank?`, `badge?` (« Nouveauté » / « Set »), `meta?` (bpm/key/age), `inLib?`, cible (route ou href externe). Slot ou état pour le bouton play.
- États : hover (play apparaît), `playing` (surligné), sans preview (pas de play), placeholder sans cover, titre/artiste tronqués (ellipsis).
- Prévois la **cohabitation** avec `ActivityAlbumCard` (même grille, même hauteur, même langage visuel).

### 3. `Hub (pilote).html` — maquette interactive

Maquette HTML autonome consommant les tokens de `diggy-tokens.css` (zéro couleur hardcodée), avec :
- l'**état vide connecté** complet (hero, search + Essaie, les 3 étagères en top 9 avec cartes enrichies BPM·KEY·âge, FamilyChips, 1 carte album dépliable dans Nouveautés, bouton « Voir plus » actif sur Ça sort/Pour toi et **désactivé** sur Nouveautés) ;
- l'**état vide invité** (pas de sidebar/pleine largeur, top-right login, Ça sort seul avec « Voir plus » menant au login) ;
- l'**état résultats** (liste typée + tri + dropdown scope avec icônes SVG et compteurs ; + variante **lock-row invité**) ;
- un **nuancier** de la `<DiscoveryCard>` dans ses variantes/états (tendance #rank, reco, nouveauté, set, lien externe, sans cover, playing, skeleton) ;
- toggle **dark/light**, toggle viewport **desktop / 375px**.

### 4. ⚠️ **Livraison : une archive ZIP téléchargeable UNIQUE (un seul lien) contenant les 3 livrables.** Sans archive, le transfert des fichiers est manuel et casse le pipeline.

## Données disponibles (exhaustif — ne rien inventer au-delà)

**« Ça sort »** — `GET /api/radar/trends?limit=9` → par item : `catalog_id`, `title`, `artist`, `has_artwork` (cover `/storage/catalog-artworks/{catalog_id}.jpg`), `has_preview`, `bpm` (float), `key` (Camelot, nullable), `rank` (1..N), `family`, `source_count`, **`release_date`** *(AJOUTÉ par le lot back de ce chantier — seule évolution API)*. Réponse aussi : `family_counts` (pour `FamilyChips`). PAS de `duration_ms`, PAS de `genres`.

**« Pour toi »** — `GET /api/recommendations/?limit=9` (JWT) → par item (CatalogEntryOut) : `id`, `title`, `artist`, `bpm`, `key`, `duration_ms`, `genres[]` (name, pillar, depth), `release_date`, `has_artwork` (`/storage/catalog-artworks/{id}.jpg`), `has_preview`, `in_lib`. PAS de `source_count`.

**« Nouveautés »** — `GET /api/following/activity?limit=12` (JWT) → par item : `type` (`release`/`set`), `title`, `artist` / `artist_name`, `artist_id`, `catalog_id` (nullable), `set_id` (nullable), `external_url` (nullable), `bpm`, `key`, `duration_ms`, `release_date`, `has_artwork`, `has_preview`, `payload` (dont `album_id` / `album_title` → regroupement album). Badge « N nouvelles » via `GET /api/following/activity/new-count`.

**Recherche** — `GET /api/search?q=…&scope=…&limit=50` → `items[]` typés (`type` ∈ track/artist/set/playlist/genre, + champs par type : titre/nom, artist, bpm, key, duration_ms, has_artwork, in_lib, source, track_count, artist_count, bpm_lo/hi…), `total`, **`totals`** (compteur par type — ALIMENTE les compteurs du dropdown de scope, dispo seulement en état recherche). Amorces « Essaie » = statiques.

> **Rappel important** : plusieurs artistes possibles par track (`artists[]`) — ne jamais supposer un seul. Âge = `release_date` formaté « Sorti il y a Nj / N sem / N mois » (la fonction existe côté front).

## Design system — contraintes (rappel)

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. Zéro couleur hardcodée.
- **Typo** : `--font-ui` (Space Grotesk) pour le texte, `--font-mono` (JetBrains Mono) pour les données numériques (BPM, key, âges, compteurs, ranks).
- **Thèmes** : `[data-theme="dark"]` par défaut + light — la maquette supporte les deux.
- **Responsive** : container queries (`@container`), jamais `@media` sauf éléments `position: fixed`.
- **CSP stricte** : icônes/logos en **SVG inline / data-URI**, aucun CDN, aucune font externe.
- **Monochrome `currentColor`** pour toute iconographie — l'accent mauve reste le seul signal coloré (les pastilles de pilier des genres gardent leur teinte).
- **UI en français.**

## Récapitulatif des livrables

| Fichier | Contenu |
|---------|---------|
| `BRIEF-hub.md` | Handoff page : top bar, hero, search + Essaie, 3 étagères top 9, carte album dépliable, double public invité/connecté, état résultats (polish), états, responsive, tokens |
| `BRIEF-composants-hub.md` | Spec réutilisable `<DiscoveryCard>` (matrice tendance/reco/nouveauté/set/lien externe, méta BPM·KEY·âge, états, cohabitation carte album) |
| `Hub (pilote).html` | Maquette interactive (état vide connecté + invité + résultats + nuancier DiscoveryCard, toggles theme/viewport) |
| **Archive ZIP unique** | Les 3 livrables téléchargeables en un lien |

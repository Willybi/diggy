# Handoff — Playlists (liste) `/playlists` · Refonte D6

## Provenance
- **Fiche de cadrage** : [`../playlists-list.md`](../playlists-list.md) (✅ figé ; les « Précisions pré-vol 2026-07-25 » priment sur le corps d'origine).
- **Prompt Design** : [`../prompts/PROMPT-claude-design-playlists-list.md`](../prompts/PROMPT-claude-design-playlists-list.md).
- **Livré par Claude Design** (2026-07-26), reçu via `Downloads/livraison-playlists-list/` :
  - `BRIEF-playlists-list.md` — handoff page (versionné ici, encodage vérifié propre, aucun mojibake — livré en fichier, pas collé).
  - `pilote/Playlists (pilote).html` — maquette interactive (toggles thème/viewport + scénarios démo : liste, filtre liked, panneau ajouter, ajouter-erreur, filtre avis vide, chargement ; densité + visibilité bouton Crawl via Tweaks).
- Captures de la page ACTUELLE (référence Design) : `C:\tmp\captures-playlists-list\` (01 desktop dark · 02 desktop light · 03 mobile 375).

## Décisions produit (rappel — verrouillées à la fiche)
Tableau enrichi (pas de grille de cartes) · **source gardée en logo** `<PlatformLink variant="glyph">` non-cliquable (multi-plateforme réel deezer/tidal/spotify — ≠ /sets) · genre déduit (1–2 StyleTags) · **colonne « Dernier crawl » riche** (date + statut live + bouton Crawl + cadence) · **pastille cadence stricte** (uniquement si `last_changed_at`, pas de fallback) · Tracks = **nombre brut** (pas d'anneau/%) · retrait `external_id` · concept « suivre » masqué · infinite scroll `usePaginatedList` + sort server-side · opinion = filtre SegFilter + `ids`/`exclude_ids` (tri « Avis » retiré) · form Ajouter (URL) conservé · **aucun composant transverse créé**.

## Évolutions légitimes issues de Claude Design (latitude DA — à retenir pour le chantier)
1. **Bouton Crawl révélé au survol de la rangée** (P5) : ≠ l'actuel (bouton gris permanent). Opacité 0→1 au hover, visible aussi `:focus-visible`, **toujours visible < 640 px / tactile**. Pendant le **cooldown 12 h** : pas de bouton, remplacé **au survol** par le libellé mono `cooldown 12 h` (répond à l'absence sans polluer le repos). Aligne la colonne sur la logique « au repos, que de la donnée ».
2. **Panneau Ajouter → MODAL** (P10) : le formulaire inline actuel devient un **modal** (recentré desktop `--r-lg`, **bottom-sheet `position: fixed`** mobile `--r-xl`). Flux conservé (1 champ URL). Aligne la page sur la jumelle Sets.
3. **Column-drop — « Dernier crawl » tombe TARD, pas en premier** (P12) : le prompt suggérait de le faire chuter tôt ; Claude Design **refuse** (argument : c'est le cœur de veille, plus utile que `owner` souvent générique « TIDAL »). Ordre retenu : Créateur (< 1040) → Genre replié (< 880) → Dernier crawl replié en méta mono (< 720) → mobile (< 640). La donnée crawl **survit repliée** (`crawl 14 j` + cadence) ; seul le **bouton** Crawl n'est pas repris en mobile (dispo sur `/playlists/:id`). Arbitrage accepté.
4. **Cadence = libellé mono nano uppercase** (pas de point tricolore) dans une pill `--surface-2`/`--ink-3` (P7) — respecte le monochrome DA ; supporte l'absence sans laisser de trou visuel.
5. **Genre replié sous le titre < 880 px** (P1) : la colonne Genre desktop se replie en chips (`--fs-nano`) dans la cellule Playlist plutôt que de disparaître (identique à Sets).
6. **Rangée `min-height`** (P11, pas de hauteur fixe) : infinite scroll **non virtualisé** → la rangée peut grandir quand genre + méta crawl se replient sous le titre.

## Résolutions Phase 2 (écarts brief vs code) — handoff PLUS PROPRE que Sets, peu d'écarts
1. **Statut live** : le brief P6 (`En attente` / `En cours` / `Crawlé`) mappe **exactement** les valeurs du endpoint `GET /api/watchlist/{id}/crawl-status` (`queued` / `running` / `done`) — déjà géré par `WatchlistView` + `useTaskPoll` aujourd'hui. **Aucun changement back**, on réutilise le polling existant.
2. **Cadence** : dérivation **client-side** depuis `last_changed_at` (seuils 14 j / 60 j, tiers Quotidien/Hebdo/Mensuel — mêmes seuils que la cadence de crawl C6.e). Le **back expose juste `last_changed_at`** (nullable) ; la pastille n'apparaît que s'il est non nul. Pas de calcul back.
3. **Créateur non cliquable** : `owner` est une **string libre** (nom de curateur/plateforme), **pas une entité Diggy** → aucun besoin back `[{id,name}]` (≠ l'écart « artistes cliquables » de la liste Sets). Simple texte ellipsé.
4. **Aucun anneau / ScoreRing / RingPct** : Tracks = `track_count` brut → pas de migration RingPct ici (≠ Sets).
5. **Pilote — hex hardcodés** : les seuls hex hors tokens sont dans le **harness du bundler** Claude Design (`#__bundler_err` overlay d'erreur L53, fond de preview) — la CSS design réelle est **100 % tokens** (304 `var(--)`). L'implémentation suit le BRIEF (erreurs du modal = `--neg`/`--neg-ink`/`--neg-soft`, jamais d'hex).
6. **Pilote — bruit démo** : une URL `soundcloud.com/sets/summer` traîne dans les données démo du pilote ; **sans objet** (les sources réelles sont deezer/tidal/spotify, cf. `<PlatformLink>` + `parsePlaylistInput`). À ignorer.

## Lot back confirmé (patron `routers/sets.list_sets`, quasi-copiable)
`GET /api/watchlist/browse` gagne : param **`sort`** (`title`/`creator`/`tracks`/`crawl`, `-` = desc, défaut `title` asc) + **`ids`/`exclude_ids`** (`_parse_id_csv`, filtre avis façon Artistes) + **`top_genres`** batché (radar_tracks→catalog, `catalog_visible`, warm pillar cache) + **expose `last_changed_at`** dans `WatchedEntityBrowseOut`. **Aucune migration** (`last_changed_at` déjà en base, C6.e). Corrige au passage le `limit=50` qui n'affichait que 50/56.

## Vérifications faites
- **Tokens** : tous les tokens cités par le brief existent dans `diggy-tokens.css` (audit ciblé OK : `--fs-nano`, `--fs-table`, `--fs-table-sm`, `--overlay-modal`, `--shadow-lg`, `--r-xl`, `--pos-wash-2`, `--neg-*`, `--accent-*`…).
- **Données inventées** : **aucune** hors API cible (tous les champs = `WatchedEntityBrowseOut` après lot back).
- **CDN** : Google Fonts + React unpkg = **harness de preview** Claude Design uniquement, pas la CSS design (CSP-safe côté implémentation : polices locales + SVG inline).

## Verdict : **GO**
Handoff conforme aux décisions figées, aucune donnée inventée, écarts brief/code nuls ou triviaux (résolus ci-dessus), lot back cadré et sans migration. Prêt pour le chantier `/work_manager` (lot 0 back → lot page front).

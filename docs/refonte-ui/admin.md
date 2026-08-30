# Admin — `/admin`

Statut : ✅ figé (fiche v1) → **arbitrages chantier ajoutés §7 (2026-08-06)** → **§8 = D11 reskin desktop (2026-08-30, 🟡 en figeage)**  |  Vue : `views/AdminView.vue` + `components/admin/*`

> 🧭 **Pour D11 (reskin graphique des 5 onglets non-designés), lire §8 — elle PRIME sur §1-7.** §7 = chantier D4-Admin (Aperçu + finition mobile, desktop dense volontairement gardé) ; §8 lève ce gel sur le contenu desktop.

> ⚠️ Cette fiche v1 a été gelée AVANT le chantier MON : elle parle de « 6 onglets » et d'un « Aperçu » à créer comme s'il n'existait aucune vue backlog. Depuis, MON a livré un **7ᵉ onglet Monitoring** (dashboard backlog déjà consolidé). Les décisions de chantier réconciliées avec cette réalité + le pré-vol données + la fusion D7 (mobile) sont en **§7 — elles priment sur les §1-6 en cas de contradiction**.

## 1. Ce qu'on a (actuel)

Page `require_admin`. **6 onglets** (chacun un composant), surtout **orientés action** :
- **Artistes** : sync artists, fetch-artworks, link-deezer (+ playlists artworks), recherche/lien Deezer par artiste, no-deezer, flags manuels.
- **Flags** : flags de fusion d'artistes (pending / validated / skipped) + résolution (split). Badge count.
- **Sets** : set-flags (pending) attach/reject, link-artists. _(enrich-tracks retiré le 2026-08-08 : tâche redondante avec l'enrich nocturne + plantages ObjectDeletedError/soft-timeout.)_
- **Genres** : mappings taxonomie (mappés / non mappés), reclassify, recherche de nodes. Badge count.
- **Crawl** : logs de crawl (badge total).
- **Beatport** : déclencher enrich-beatport.

**Constat** : chaque onglet = des **boutons pour lancer des jobs** + quelques compteurs isolés. **Pas de vue consolidée du backlog** : les volumes de « travail en attente » ne sont pas visibles sans ouvrir chaque onglet.

**Dette** : pas d'aperçu global ; monitoring + actions mélangés ; on ne sait pas d'un coup d'œil s'il reste du backlog (Beatport, sets, artistes…).

## 2. Vision (William)

- Déjà bien ; peut-être un **ajustement visuel** (ordre / forme).
- Surtout : un **affichage de l'état du backlog** — s'il y a du backlog sur l'enrichissement **Beatport**, les **sets**, les **artistes**, etc.

## 3. Proposition (Claude)

1. **Onglet « Aperçu » (backlog dashboard) en landing** : des **cartes par pipeline**, chacune avec son **compteur de pending** + une **action rapide** (le job existe déjà dans l'onglet correspondant). Pipelines proposés :
   - **Beatport** : tracks en attente d'enrichissement (retry-eligible, non abandonnées).
   - **Deezer** : tracks en attente d'enrichissement.
   - **Artistes** : sans `deezer_id` (link backlog) + sans artwork.
   - **Sets** : à recrawler (`recrawl_status != final`) + set-flags **pending**.
   - **Flags artistes** : **pending**.
   - **Genres** : tracks **non classées** + mappings **non mappés**.
   - **Crawl** : playlists dues / taille DLQ.
   > Compteurs déjà dispo : genres unclassified, flags, mappings, crawl total. Les autres = **nouveaux endpoints count** (feature-first).
2. **Badges de compte sur les onglets** (ex. « Flags 3 », « Sets 2 », « Genres 128 ») → voir le pending **sans ouvrir** l'onglet.
3. **Ordre** : **Aperçu en premier**, puis les onglets domaine (on garde les 6 — ils portent les actions).

**Keep / Improve / Remove**
- ✅ **Garder** : les 6 onglets orientés action, `require_admin`.
- ➕ **Améliorer** : **+ Aperçu / backlog dashboard** (landing) ; **badges de compte** sur les onglets.
- ➖ **Retirer** : rien.

**Réponses (William)** : dashboard « Aperçu » ✅ (tous les pipelines proposés) · badges de compte sur les onglets ✅ · ordre gardé (Aperçu en premier, reste inchangé).

## 4. Ré-allocation des points retirés
- Rien retiré (on ajoute seulement).

## 5. Décisions figées
- **+ Onglet « Aperçu » (landing) = dashboard backlog** : cartes par pipeline, chacune **compteur de pending + action rapide** :
  - **Beatport** (tracks en attente) · **Deezer** (tracks en attente) · **Artistes** (sans `deezer_id` + sans artwork) · **Sets** (à recrawler + set-flags pending) · **Flags artistes** (pending) · **Genres** (non classées + mappings non mappés) · **Crawl** (playlists dues / DLQ).
- **Badges de compte sur les 6 onglets** (pending visible sans ouvrir).
- **Ordre** : Aperçu en premier, puis les **6 onglets inchangés** (contenu conservé).
- **Gardé** : `require_admin`, les 6 onglets orientés action.

## 6. Sortie next-step
**Handoff Design**
- [ ] Onglet « Aperçu » : grille de **cartes backlog** (compteur + action rapide), lisible d'un coup d'œil.
- [ ] Badges de compte sur les onglets.

**Chantier work_manager**
- **Back** : un **endpoint agrégé** `/api/admin/backlog` renvoyant tous les compteurs d'un coup (Beatport pending, Deezer pending, artistes sans `deezer_id`, sans artwork, sets à recrawler, set-flags pending, artist-flags pending, genres non classées [existe], mappings non mappés [existe], crawl dues / DLQ). Alimente **à la fois** les cartes Aperçu et les badges d'onglets.
- **Front** : `AdminView` + onglet **Aperçu** (cartes) ; **badges** sur les onglets (mêmes données).

**Dépend de** : endpoint agrégé `/api/admin/backlog`.

## 7. Pré-vol & décisions chantier (2026-08-06) — PRIME sur §1-6

Chantier lancé en **fusionnant D4-Admin + D7** (D7 « polish mobile Flags + Lier » = sous-ensemble strict du périmètre admin → absorbé, pas de livrable D7 séparé).

### 7.1 Réalité code (vs fiche v1)
- L'admin a **7 onglets**, pas 6 : le chantier **MON** a ajouté **Monitoring** (`AdminMonitoring.vue`), un dashboard qui **rend déjà le backlog enrichissement consolidé** (burn-down `metric_snapshots` + `count_enrich_backlog` : deezer/beatport/artistes/sets). La prémisse §1 « pas de vue consolidée du backlog » est donc **partiellement obsolète**.
- Responsive déjà fait (commit `d400ba8`, 01/08) : `AdminFlags` (table→cartes @859px) + bloc « Lier » d'`AdminArtists` (@639px, tactile). **Reste à faire côté mobile** : revue **SetFlag** d'`AdminSets` (flex-only), tables **Genres**/**Crawl** (overflow-x seul, pas de table→card), les **4 sections sync** d'`AdminArtists` (non scopées container).

### 7.2 Décisions figées (arbitrées avec William au pré-vol)
- **Aperçu vs Monitoring = COEXISTENCE** : nouvel onglet **Aperçu** en landing, orienté **action** (cartes par pipeline : compteur + action rapide + badges sur les onglets). **Monitoring gardé tel quel** (rôle observation : graphes, historique) — **hors reskin**, non re-designé.
- **Ampleur = CIBLÉE, pas de reskin DA Wildflower** : seul l'**Aperçu** reçoit le traitement « designé » ; les onglets existants **gardent leur look ops-console dense** (tables OK). On **finit le mobile résiduel** (7.1).
- **Métrique des cartes enrichissement = actionnable `never_tried + due_retry`**, PAS `total_missing` (dominé par le cooldown non-actionnable). `total_missing`/`abandoned` peuvent servir de contexte secondaire. La fiche §5 « retry-eligible, non abandonnées » est ainsi respectée.
- **État sain (0) élégant** : au pré-vol prod, plusieurs compteurs sont légitimement à 0 (artist-flags 0, mappings non mappés 0, deezer actionnable 0) — variables, pas constants. Une carte à 0 = « à jour ✓ », pas une alerte vide. Le design DOIT être beau quand la majorité est à 0.
- **Ordre** : Aperçu premier, puis les 7 onglets existants inchangés (contenu conservé, Monitoring compris).

### 7.3 Back — `GET /api/admin/backlog` (Lot 0)
Endpoint agrégé unique (alimente cartes Aperçu ET badges d'onglets). Forme cible :
```
beatport:     { pending (never+due), total_missing, abandoned }
deezer:       { pending (never+due), total_missing, abandoned }
artists:      { to_link, no_artwork }
sets:         { recrawl, flags_pending }
artist_flags: { pending }
genres:       { unclassified, mappings_unmapped }
crawl:        { playlists_due, dlq }
```
Réutilise `workers/enrichment.count_enrich_backlog` (enrich) + comptes live (`set_flags`/`artist_flags` status='pending', `genre_mappings` node_id IS NULL, `genres/unclassified-count` existe). `crawl.playlists_due` = cadence `crawl_radar` ; `crawl.dlq` = taille clé Redis `dead_letter`.

### 7.4 Valeurs prod de référence (snapshot 2026-08-06 11:30)
beatport pending **2607** (total_missing 65722) · deezer pending **0** (total_missing 29403) · artistes à lier **5** / sans pochette **2990** · sets recrawl **501** · **set-flags pending 158** · artist-flags pending **0** · mappings non mappés **0**. → backlogs réels visés : beatport, artistes-pochettes, sets recrawl, set-flags.

### 7.5 Composants
Aucun composant **transverse** nouveau attendu (les cartes Aperçu sont **admin-locales** ; la famille `components/charts/` de MON reste dans Monitoring). Lots chantier : **Lot 0 back** (`/api/admin/backlog`) → **Lot 1 page** (AdminView : onglet Aperçu + badges + finition mobile). Pas de lot composants transverses.

### 7.6 Handoff Claude Design acté (2026-08-06) — GO
Livraison `handoff-admin/` (BRIEF-admin.md = contrat). Décisions de design tranchées dans la latitude accordée : **11 cartes pour 7 pipelines** (A1 — deux métriques → deux cartes, état booléen « à jour » net) ; **badge onglet = somme des actionnables** (A8) ; **barre d'onglets en scroll horizontal ancré** (A10, jamais de wrap) ; **palier mobile unique 859px** (A11) ; nouveau composant **admin-local `AdminOverview.vue`** (grille 11 cartes, 2 régimes backlog/à-jour, squelettes/erreur/job-en-cours). Conformité vérifiée, zéro donnée inventée. **⚠️ Câblage actions rapides à trancher au Lot 0** : cartes Genres (`auto-classify` cassé, reliquat) et Deezer (aucun trigger manuel) → défaut = **renvoi vers l'onglet** plutôt qu'absorber la dette (voir `handoff-admin/README.md`).

## 8. D11 — Reskin desktop des 5 onglets non-designés (2026-08-30) — PRIME sur §1-7 pour ce périmètre

Statut : ✅ **figé (2026-08-30)** — périmètre 9 composants confirmé (William), ampleur = reskin DA complet via round Claude Design, densité laissée en proposition à Claude Design, `auto-classify` écarté (§8.7). Prêt pour le prompt Design (Phase 1). D4-Admin (§7) a designé **l'Aperçu** et posé la **finition mobile** ; il a délibérément **gardé le desktop dense « ops-console »** des onglets d'action (§7.2 : « Ampleur = CIBLÉE, pas de reskin »). **D11 lève exactement ce gel** : il applique la DA de l'app au **contenu desktop** des onglets qui ne l'ont jamais reçu. D10 a entre-temps figé l'IA à **6 onglets** (rendu groupé).

### 8.1 Périmètre (arbitré avec William, 2026-08-30)

- **Ampleur = reskin DA COMPLET via un round Claude Design** (nouveau BRIEF étendant la grammaire de l'Aperçu). Pas une simple homogénéisation : les tokens sont **déjà 100 % propres** (999 `var(--…)`, 0 couleur en dur) — le travail est du **langage visuel**, pas du nettoyage mécanique.
- **TOUT le panel admin DANS le périmètre** (décision élargie 2026-08-30 : Aperçu **puis** Monitoring ajoutés) — 11 composants + la famille charts : `AdminOverview` (Aperçu) · `AdminArtists`, `AdminFlags` (Artistes) · `AdminSets` (Sets) · `AdminGenres` (Genres) · `AdminBeatport`, `AdminEnrichmentActions` (Enrichissement) · `AdminMonitoring` + **`components/charts/`** (`TimeSeriesChart`/`SparkLine`/`StatTile`), `AdminCrawl`, `AdminAuditLog` (Observabilité) · `ArtistSegmentSplitter` (partagé Artistes/Flags). **Plus rien d'INTACT** hormis le chrome `AdminView.vue` (grammaire A10/A9 onglets/badges acquise, latitude légère sur le spacing). **`components/charts/` n'est consommé QUE par `AdminMonitoring`** → le re-styler ne viole PAS la règle « composant partagé jamais modifié pour une page » (aucune autre vue ne le monte).
- **Aperçu = HARMONISATION, pas refonte** (2026-08-30) : l'Aperçu a **déjà une DA validée** (le `BRIEF-admin.md`, sa grille de cartes / 2 régimes backlog↔à-jour). Repris dans le handoff D11 pour une console cohérente d'un bloc — Claude Design le **ré-émet en l'harmonisant** (icônes SVG, pills, tokens) mais **NE jette PAS** la structure éprouvée (grille de cartes, 2 régimes, badges A8/A9). NB : **12 cartes** aujourd'hui (E2.c a ajouté « À analyser (BPM) » depuis le BRIEF D4 qui en listait 11).
- **Monitoring = reskin du dashboard d'observation** (ajouté 2026-08-30) : `AdminMonitoring` est le **6ᵉ archétype (F)** — rangées de **StatTiles**, blocs de **courbes** (`TimeSeriesChart` : enrichissement dans le temps, backfills de contenu, petits soldes/qualité, débit & taux de réussite), **sparklines** (`StatTile` erreurs/durées), table « Dernier passage par tâche ». On re-style les 3 composants SVG maison (déjà token-driven) + la mise en page/densité/légendes/axes du dashboard, **sans changer les données ni les séries**. L'onglet Observabilité devient **entièrement designé** (Monitoring + Crawl + Audit cohérents) — la « couture » n'est plus une contrainte de coexistence mais une **cohérence interne** à composer.

### 8.2 Pré-vol données & back — VERDICT : rien de neuf côté back

Inventaire endpoint-par-endpoint des 9 composants fait (agent, 2026-08-30). **Tous** consomment des endpoints **existants**, **tous** les champs affichés sont **déjà renvoyés**. D11 = **pur front**, **0 endpoint, 0 modèle, 0 migration** (conforme au cadrage roadmap). Aucune contradiction §5/§6 : aucune idée de reskin n'exige une donnée absente. Données disponibles exhaustives (pour le prompt Design) :
- **Panneaux d'action** (jobs) : réponses `{task_id}` puis poll `GET /admin/tasks/{id}` → `{status, result, error}`. `result` par job : sync `{created, flagged, skipped}` · link-deezer `{linked, searched, abandoned, errors, dropped_by_budget}` · artworks `{fetched, skipped, errors, dropped_by_budget}` · artworks-playlists `{fetched, failed, total}` (sync) · beatport `{enriched, not_found, errors, total}` | `{skipped:'already_running'}` · backfill-multi `{enriched, errors, total}` · link-sets `{linked, skipped}` · reset-beatport `{cleared, bpm_reverted, key_reverted}` (sync).
- **Tables** : flags artistes `{id, raw_artist_string, reason, tokens[], status}` · set-flags `{id, flag_type, confidence, member_titles[], title_a/b, signals{part_numbers[], date_span_days, date_gap_days}}` · mappings `{id, rawName, nodeLabel, nodeId, nodeWikidataId}` · crawl-logs `{id, started_at, task_type, target_label, source, status, duration_ms, stats{}, error_message}` · audit-log `{id, created_at, user_email, action, target_type, target_id, details{}}`.
- **Formulaire liaison** : `GET /artists/?no_deezer` → items `{id, name, has_artwork}` + `active_count`/`dormant_count` · `GET /admin/artists/search-deezer?q` → hits `{deezer_id, name, picture, nb_fan}`.

### 8.3 Archétypes UI à designer (le cœur du BRIEF)

Les 9 composants se ramènent à **5 archétypes** ; le BRIEF doit fixer un langage par archétype, appliqué uniformément (fin de la divergence ad-hoc `.sync-*`/`.flag-table`/`.state` re-déclarés composant par composant) :

- **A — Panneau d'action / déclencheur de job** (`AdminArtists` ×4 sections sync, `AdminBeatport`, `AdminEnrichmentActions`, `AdminSets` § link-artists, `AdminGenres` § reclassify). Titre + description + bouton + **ligne de résultat mono**. Réutiliser la grammaire de carte de l'Aperçu (surface/`--r-md`/`--line`), `.btn--accent` pour les jobs, **état « job en cours » = pattern A7** (bouton disabled + arc rotatif `--accent-ink`). **Variante danger** pour `reset-beatport` : discipline `--neg`, confirmation inline conservée (garde-fou D10).
- **B — Table dense paginée** (`AdminFlags`, `AdminCrawl`, `AdminAuditLog`, `AdminGenres` § mappings). Header (titre + badge compte + barre de filtres) → table → pagination. **Statuts en pills** (`--pos`/`--neg`/neutre soft), **nombres/dates/durées en mono**, filet `--line`. Mobile 859px `data-label` **acquis** (ne pas casser).
- **C — Revue par cartes de paires** (`AdminSets` § set-flags + § sets attachés). Cartes VS déjà en place → raffiner le langage desktop pour matcher les cartes Aperçu (le mobile 859px empilement + bande VS est acquis).
- **D — Formulaire de recherche + double liste** (`AdminArtists` § « Lier un artiste »). Inputs (`--fs-input` ≥ 16px), liste d'artistes (vignette + nom + actions hover), liste de hits Deezer, carte de confirmation.
- **E — Widget interactif** (`ArtistSegmentSplitter`). Chips de segments + boutons de coupe + signal Deezer par segment.

### 8.4 Décisions figées D11

1. **Purge des emoji** : le code actuel affiche `✓ ⚠ ↷ 🔗 🔎 ⌀ 🗑 ↩` dans les lignes de résultat/chips. La DA impose **SVG inline `currentColor`, zéro emoji**. Le BRIEF doit fournir/nommer le petit jeu d'icônes (check, warn, skip/undo, link, search, trash, spinner) et un traitement typographique des compteurs de résultat (mono).
2. **Container queries only, palier 859px** comme norme (déjà en prod). **Combler les 3 trous mobiles** : `AdminBeatport` (aucun `container-type` ni `@container`), `AdminEnrichmentActions` (pas de palier ; boutons danger/confirm non agrandis), `ArtistSegmentSplitter` (boutons de coupe/poubelle ~20px < cible tactile `--touch-min` 44px). Aucun `@media` (sauf `position:fixed`, absent ici), aucun `position:fixed`.
3. **`--r-md` et les tokens du BRIEF Aperçu font foi** — accent discipliné (jobs, onglet actif, spinner), `--pos` = à jour/OK, `--neg` = erreur/échec/danger reset ; **aucun rouge/ambre décoratif**.
4. **Page `require_admin`, utilisateur unique** : aucun état invité, aucune permission à dessiner.
5. **Aperçu + Monitoring INTACTS** : ne pas re-designer, ne pas re-toucher `components/charts/`. La couture Observabilité (charts intacts au-dessus des tables reskinnées) est une contrainte de **cohérence**, pas une invitation à toucher Monitoring.
6. **Logique métier inchangée** : mêmes endpoints, mêmes payloads, mêmes jobs, mêmes gardes (confirmation reset, poll `/admin/tasks/{id}`). Reskin **visuel pur**.

### 8.5 Latitude accordée à Claude Design

- Trancher si les **4 tables** de l'archétype B partagent **un socle CSS admin commun** (piste : `assets/list-table.css` `.lt-*`, déjà le socle Sets/Watchlist — **PAS `TrackTable`**, qui est track-spécifique et virtualisé, inapplicable à ces tables paginées non-track) ou restent scoped par composant. Recommandation fiche : un socle partagé pour ne pas re-diverger, mais c'est de l'implémentation — la DA décrit le rendu.
- Densité/hiérarchie des panneaux d'action (archétype A) : carte pleine vs bande, regroupement des 4 sections sync d'`AdminArtists`.
- Traitement des filtres segmentés (réutiliser le look de `components/filters/SegmentedFilter` **sans le modifier**, ou un segmenté admin-local).
- Le chrome `AdminView` (spacing du header/barre d'onglets) tant que la grammaire onglet/badge A9/A10 reste.

### 8.6 Composants & lots pressentis (indicatif, à confirmer au handoff)

- **Aucun composant transverse Vue nouveau** attendu (surfaces admin-locales). Un éventuel **socle CSS admin partagé** (`assets/…`) n'est pas un composant Vue → pas de lot vitrine DesignSystemView.
- **Pas de lot back** (§8.2).
- Lots front séquentiels par onglet/archétype (à découper au handoff selon le BRIEF). Règle refonte : composants **partagés jamais modifiés pour l'admin** (`SegmentedFilter`, `list-table.css` — s'il est étendu, additif et non régressif pour Sets/Watchlist).

### 8.8 Handoff Claude Design acté (2026-08-30) — GO avec 1 correction

Livraison `handoff-admin-d11/` (`BRIEF-admin-D11.md` = contrat, réencodé UTF-8 propre ; `Admin-D11-pilote.html` = maquette référence, React+CDN, déposée par William ; `README.md` = provenance + conformité). **6 archétypes A→F** + Aperçu harmonisé, 22 décisions DA (D1-D22). Décisions de latitude légitimes : socle CSS admin partagé `.at-*` (D1, admin-local — rejette `TrackTable`/`list-table.css`), panneaux d'action groupés en région (D4), **filtres segmentés sans accent** (D5, sélection par relief), archétype C paginé 10/page (D19), Aperçu harmonisation seule (D20 : 5 alignements + régime « inconnu » pour métrique `null` + 12ᵉ carte `bpm`), Monitoring re-stylé (D21). Absorbe les reliquats `FIX-admin.md` (V1-V7, S1, « DLQ null ») sans round séparé. **Conformité vérifiée** : décisions figées §8.4 respectées, aucune donnée hors API, aucun composant transverse Vue créé.

**⚠️ 1 correction portée comme instruction d'implémentation (PAS un round Claude Design)** : **D22 palette de courbes**. Le BRIEF réinvente une palette depuis les hues de piliers (`oklch(L C var(--hue-*))`, L/C en dur) alors que `diggy-tokens.css` a DÉJÀ une palette de charts dédiée, CVD-validée, theme-flippante (`--chart-deezer/-soft`, `--chart-beatport/-soft`, `--chart-bpm`, `--chart-sets`, `--chart-albums`, `--chart-embeddings`, `--chart-neutral/-grid/-axis`) que l'`AdminMonitoring` actuel consomme déjà (lignes 95/292-299/458-479). Le lot Monitoring **garde le mapping `--chart-*` existant** (couleur pleine = actionnable, `-soft` = total), NE PAS introduire les `--mon-s*` de la maquette. Corrigé dans le BRIEF versionné (D22 + note de réception en tête). Rien de transverse touché (tout est admin-local ; `TRANSVERSE.md` inchangé).

**Verdict : GO.**

### 8.7 Reliquat opportuniste noté (hors D11, ne pas absorber)

`POST /admin/genres/auto-classify` (bouton « Lancer le classement auto ») : **hors périmètre D11** (il vit sur **GenresView**, page user déjà refondue en D6 — PAS dans le panel admin ; l'`AdminGenres` du périmètre utilise l'autre tâche `reclassify_all_genres`, saine). Vérifié 2026-08-30 : **il n'est PLUS cassé** — le kwarg `genre_only` existe désormais sur `enrich_catalog_beatport` (A3-01) et la chaîne endpoint→tâche→`select_enrich_candidates`→`array_is_empty(genres)` est complète et correcte. La ligne 2192 de `ROADMAP.md` (« bouton CASSÉ, correctif PLANIFIÉ ») est du **doc périmé** → à marquer RÉSOLU à la clôture D11 (Phase 7), sans lot de code.

# Admin — `/admin`

Statut : ✅ figé (fiche v1) → **arbitrages chantier ajoutés §7 (2026-08-06)**  |  Vue : `views/AdminView.vue` + `components/admin/*`

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

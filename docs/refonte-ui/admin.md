# Admin — `/admin`

Statut : ✅ figé  |  Vue : `views/AdminView.vue` + `components/admin/*`

## 1. Ce qu'on a (actuel)

Page `require_admin`. **6 onglets** (chacun un composant), surtout **orientés action** :
- **Artistes** : sync artists, fetch-artworks, link-deezer (+ playlists artworks), recherche/lien Deezer par artiste, no-deezer, flags manuels.
- **Flags** : flags de fusion d'artistes (pending / validated / skipped) + résolution (split). Badge count.
- **Sets** : set-flags (pending) attach/reject, link-artists, enrich-tracks.
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

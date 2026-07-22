# Radar — `/radar` (nouvelle page, extraite de Catalog)

Statut : ✅ figé  |  Vue : à créer (aujourd'hui `/radar` → redirect `/catalog?view=radar`)

## 1. Ce qu'on a (actuel)

**« Radar » n'est pas une page** aujourd'hui — c'est un concept éparpillé :
- **Mode radar de Catalog** (`/catalog?view=radar`) : liste plate des détections (Source, Détecté, Période, ScorePill). → migre sur cette page.
- **Étagère Hub « Ça sort en ce moment »** (`GET /radar/trends`) : top tendances + FamilyChips.
- **Badge BottomNav** (`GET /radar/new-count`) : compteur « new ».

**Trois facettes de données disponibles :**

1. **Tendances** — table `radar_trends` (calculée chaque nuit par `compute_trends`) : `trend_score`, `family`, `rank_in_family` / `rank_global`, **`velocity`** (vitesse de montée — *calculée mais jamais affichée*), `source_count`, `detection_count`, `window_days`. Endpoint `GET /radar/trends` (filtre `family` + `family_counts`).
2. **Détections / veille** — table `radar_tracks` : chaque track vu sur une playlist surveillée → `detected_at`, `removed_at` (cycle de vie), `is_initial_detection` (biais 1er crawl), `source`, `isrc`, lien `catalog_id`. Les sources = `watched_entities` (source, titre, `last_changed_at`), qu'un user peut suivre (`user_follows` = signal de priorité).
3. **Triage perso** — table `user_radar_state` : statut par (user, track) parmi **new / seen / added / ignored / liked / disliked**.

**⭐ Insight clé** : il existe déjà un **backend de triage complet, NON branché au front** :
- `GET /radar/full` — listing riche : filtre `status` (new/seen/added/ignored/liked/disliked), `playlist_id`, `search`, `detected_after`, tri (detected_at/title/artist/bpm/key/genre/playlist_title/trend_score), pagination.
- `PATCH /radar/{id}/state` + `PATCH /radar/state/batch` (sélection multiple « select & mark »).
- `GET /radar/new-count` (seul le badge BottomNav l'utilise).

→ Le badge « new » du BottomNav **pointe déjà vers un radar-inbox qui n'a pas d'écran**. La page Radar peut s'appuyer sur cet existant, pas repartir de zéro.

**Ce qui arrive d'Explorer** (retiré là-bas) : mode radar, colonnes Source + Détecté, filtre Période, ScorePill, chip Radar ≥ 2.

## 2. Vision (William)

- Radar = la page qui affiche **les 2 notations de recommandation principales** de l'app :
  - **Tendances** (global / scène) — `radar_trends`, endpoint `/radar/trends`.
  - **Pour toi** (perso) — moteur de reco C4, endpoint `/api/recommendations`.
- **Pas** une boîte de réception / triage : la mécanique « à trier » n'est pas dans le cheminement user → la facette `user_radar_state` (new/seen/added…) reste **de côté**.
- **Format encore ouvert** (voir §3).

**Réconciliation Hub** : Radar = Tendances + Pour toi ⇒ ça **absorbe la page `/for-you`** (le « voir plus » de « Pour toi » du Hub pointerait sur Radar, plus une page séparée). « Nouveautés de tes artistes » (`/new-releases`) **reste séparé** : c'est un 3e signal (sorties des artistes suivis), pas une des 2 notations de reco.

## 3. Format retenu

**Principe (William)** : **une seule liste** de recommandations. Chaque ligne = un son (infos) + **2 colonnes de score côte à côte : `Tendance` et `Pour toi`**. On **trie par l'une ou l'autre**.

**À compléter (données)** : la liste = **union des 2 univers** (ce qui *trend* ∪ ce qui t'est *recommandé*). Beaucoup de sons n'auront qu'un des deux scores → l'autre colonne = « — ». Nécessite un endpoint qui **merge `trend_score` (radar_trends) + `reco_score` (recommendations)** par `catalog_id`. **Tranché en Phase 0 (cf. §7)** : union **bornée & symétrique** — Tendance = top-N **par famille** (via `rank_in_family`), Pour toi ≤100 (plafond existant du moteur C4). Les deux notes `/10` sont **relatives à leur propre colonne** (max-normalisation par colonne, comme l'actuel `trend_score_10`).

**Décisions de rendu & contenu :**
1. **Rendu des 2 scores** : **jauge circulaire** (anneau de progression) avec **note entière /10 au centre** ; le **float reste stocké** pour un tri précis. Même composant pour Tendance et Pour toi → candidat `<ScoreRing>` réutilisable. *(Velocity = accent optionnel léger sur la jauge Tendance, ex. petit ▲ « monte vite » — basse priorité.)*
2. **Colonnes** (mutualisées Explorer) : cover + **indicateur in-lib**, titre/artiste, **BPM**, **Key**, **Genre/Style**, puis **Tendance** + **Pour toi** (jauges), + play + like/dislike.
3. **Tri** : `Trier par : [Pour toi] [Tendance]` (+ BPM / récent) ; colonne active surlignée.
4. **Filtres façon Explorer** (famille/style, BPM, key) → « ce qui monte en techno 130–135 qui me correspond ».
5. **Like/dislike** : conservés, **comportement classique** — pas de pondération spéciale des likes Radar (évite une usine à gaz back).
6. **Cold-start** (user connecté sans likes) : Pour toi faible → tri **Tendance par défaut** + invite à liker. *(Pas d'état invité : l'invité ne quitte pas le Hub → [TRANSVERSE.md](TRANSVERSE.md) § Principes UX.)*
7. **Conserve** : play, like/dislike, click → détail, indicateur cover in-lib.

**Écarté** : indice « pourquoi » du Pour toi ; pondération renforcée des likes ; boîte de triage (`user_radar_state`).

**Relation à Explorer** : Radar partage les composants (liste virtualisée, colonnes, filtres, `<Artwork>`) mais **dataset & intention différents** — Explorer = chercher dans toute la base ; Radar = la **surface de recommandation** (union curée, bi-score).

**Ouvert (non bloquant)** : liste exacte des colonnes ; velocity (accent optionnel) ; nom « Radar » (page devenue « reco »).

## 4. Ré-allocation des points retirés
- **Page `/for-you` supprimée** → **fusionnée dans Radar** (colonne « Pour toi »). Le « voir plus » de « Pour toi » du Hub pointe désormais sur Radar. ✅
- L'ancien mode radar de Catalog (Source, Détecté, Période, ScorePill, chip Radar ≥ 2) : le **classement + velocity** nourrissent la colonne Tendance ; la liste plate de détections brutes (`radar_tracks`) n'est **pas** reprise (hors vision), reste dispo en base.
- `/new-releases` (nouveautés artistes suivis) **reste séparé**.

## 5. Décisions figées
- **Radar = surface de recommandation bi-score** : liste unique, chaque son avec **score Tendance + score Pour toi**, tri par l'un ou l'autre.
- **Rendu des scores** : **jauge circulaire + note /10 entière** au centre (float conservé pour le tri précis) → composant `<ScoreRing>`.
- **Colonnes** : cover + in-lib · titre/artiste · BPM · Key · Genre/Style · Tendance · Pour toi · actions (play, like/dislike).
- **Filtres façon Explorer** ; **like/dislike classique** (aucune pondération spéciale) ; **cold-start** → tri Tendance par défaut.
- **`/for-you` fusionné** dans Radar.
- **Composants partagés** avec Explorer (liste virtualisée, colonnes, `<Artwork>`, filtres) + `<ScoreRing>`.
- **Écarté** : triage (`user_radar_state`), indice « pourquoi », pondération des likes, états invité (invité confiné au Hub).
- **Ouvert (non bloquant)** : liste exacte des colonnes ; velocity (accent optionnel) ; nom « Radar » (défaut Phase 0 : on **garde « Radar »**, continuité nav).

## 6. Sortie next-step
**Handoff Design**
- [ ] `<ScoreRing>` : jauge circulaire + note /10 (× Tendance / Pour toi) ; colonne de tri active surlignée.
- [ ] Jeu de colonnes (BPM/Key/Genre) + filtres + drawer mobile (mutualisés Explorer).

**Chantier work_manager**
- **Back** : endpoint **merge `trend_score` + `reco_score`** par `catalog_id` (union), normalisation → note /10 (float conservé pour le tri), tri par l'un/l'autre, filtres, `catalog_visible`.
- **Front** : page Radar réutilisant liste virtualisée + colonnes + filtres d'Explorer ; composant `<ScoreRing>` ; suppression `/for-you` + redirection « voir plus » Hub → Radar.
- **Transverse** : composants partagés (dont `<ScoreRing>`).

**Dépend de** : composants Explorer ; chantier nav (place de Radar).

## 7. Décisions Phase 0 (cadrage refonte, 2026-07-22)

Arbitrages William au lancement de `/refonte_page radar` (tranchés avant le prompt Design) :

1. **Union bornée & symétrique** (back). Dataset de l'endpoint merge = **top-N Tendance par famille** (`radar_trends.rank_in_family`, ~40-60/famille → filtres profonds « techno 130-135 » restent peuplés) **∪ ≤100 recommandations** (plafond existant du moteur C4). Écarté : la liste exhaustive façon Explorer (des milliers de lignes trend). Motif : Radar = **surface de reco curée**, pas un dump ; le coût reco est déjà plafonné (calcul à la volée, cache 1h, ~6,6s à froid) et sans valeur au-delà de ~100.
2. **Normalisation `/10` par colonne** (relative). Chaque anneau dit « à quel point c'est haut dans CE classement » (10 = le plus tendance / 10 = ton meilleur match). Ce sont **deux recommandations distinctes** côte à côte, pas la même échelle — l'asymétrie de tailles ne casse donc pas la cohérence. Réutilise la max-normalisation déjà en place pour `trend_score_10`.
3. **Tri par défaut = Tendance, TOUJOURS** (pas seulement au cold-start). « Pour toi » reste une colonne triable, mais l'ouverture se fait sur le classement Tendance objectif quel que soit l'historique.
4. **Périmètre au-delà de la page** : (a) **entrée de nav dédiée Radar** dans SidebarNav + BottomNav (entrée simple ; la restructuration nav complète reste le chantier transverse nav, 🔲) ; (b) rebrancher **Hub « Pour toi » → /radar** ; (c) rebrancher **Hub « Ça sort en ce moment » → /radar** (les deux étagères gagnent un « voir plus » qui n'existe pas aujourd'hui).
5. **Nom** : on **garde « Radar »** (continuité nav).

### Divergences fiche ↔ code relevées au pré-vol (à ne pas traiter comme des tâches existantes)

- **`/for-you` n'a jamais existé** : ni route, ni vue, ni lien « voir plus » sur le Hub. La tâche « supprimer `/for-you` » de la fiche/roadmap est **sans objet** ; rebrancher un « voir plus » vers `/radar` (décision 4b/4c) est du **net-new**.
- **La liste virtualisée d'Explorer n'est PAS un composant** : ~1300 lignes inline dans `ExplorerView.vue`. Radar **réécrit son tableau** (grille + rangées) en réutilisant les *primitives* partagées (composables `useFilterState`/`useVirtualWindow`/`useWindowedList`, famille `filters/`, `Artwork`/`StyleTag`/`ArtistLinks`/`LikeDislike`) + 2 colonnes `<ScoreRing>`. On **ne modifie pas** Explorer (doctrine refonte).
- **Aucun nouveau composant transverse** : `<ScoreRing>` (contrat figé : entrée score **0–1**, affichage `/10`), `<Artwork>`, la famille `filters/` sont déjà livrés. Le handoff Design est allégé (composition de page + maquette, pas de spec composant).
- Le mode radar de Catalog (Source/Détecté/ScorePill/chip Radar≥2) a **déjà été retiré** d'Explorer en D6 ; la liste brute `radar_tracks` n'est pas reprise (hors vision, §4).

### Décisions du handoff Claude Design (round unique, 2026-07-22)

Handoff versionné dans `handoff-radar/` (BRIEF-radar.md + pilote), conforme aux décisions figées. Évolutions actées au round (latitude DA), à porter au chantier :

- **Menu « + » imports RETIRÉ** du head Radar (« Ajouter un track » / « Importer XML » restent sur Explorer) — sans sens sur une surface de reco.
- **Colonne active = bande verticale `--accent-wash`** (en-tête + toutes les cellules de la colonne triée), pas seulement l'en-tête — repère de tri continu en scroll virtualisé.
- **Accent velocity = ▲** en coin de l'anneau **Tendance** uniquement (jamais Pour toi), optionnel.
- **Cold-start** = bandeau « Débloque Pour toi » (fermable) + colonne Pour toi entière « — » ; ouverture sur tri Tendance.
- Column-drop 4 paliers (1000/860/700/640) hérité d'Explorer, réordonné pour **préserver les 2 scores jusqu'au 375 px**.

**Impacts back (lot 0) nés du handoff** :
- L'endpoint doit exposer les **bornes de l'union** pour le compteur de head (« N tendances · M pour toi »), en plus du `total` filtré (compteur live « N sons »).
- **Seuil velocity « élevée »** (déclencheur du ▲) à définir au lot : percentile serveur ou booléen `is_rising` renvoyé par l'endpoint (non bloquant, optionnel).

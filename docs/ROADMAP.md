# Diggy — Roadmap

> Document maitre. Chaque chantier est autonome et assignable a un dev/agent independant.
> Les dependances inter-chantiers sont explicites.
>
> **Roadmaps archivees** : voir `docs/completed/`
> - `ROADMAP_2026-06.md` — audit technique T1-T6, chantiers C1-C13 (100%)
> - `ROADMAP_2026-06-backlog.md` — ancien backlog L1-L3, F3-F4 (absorbe ici)
> - `ROADMAP_MULTIUSER.md` — multi-user phases 0-4 (100%)
> - `ROADMAP_AUDIT_2026-07.md` — rapport d'audit CTO complet (reference)
>
> **Derniere mise a jour** : 2026-07-07 (C6.0 + C6.1 termines ; C6 EN COURS)

---

## Vision cible

Avant l'ouverture aux amis (5-10 DJs), Diggy doit offrir :
1. Une experience mobile utilisable (ils seront sur telephone)
2. Une recommandation de tendance solide, decorrellee des likes (offre par defaut des nouveaux arrivants sans historique)
3. Un moteur de similarite fonctionnel (socle de toute recommandation, avec ou sans user)
4. Une application fermee et etanche entre utilisateurs (auth obligatoire, scopes respectes)

Apres l'ouverture : la recommandation personnalisee (croisement similarite x likes), utile des un seul user et enrichie par chaque nouvel utilisateur.

**Sequence verrouillee** : ~~C0 -> R1 -> C1 -> C2~~ (TERMINE) -> ~~H0 + P1~~ (TERMINE) -> F5 + C6 (paralleles) -> C3 (ouverture) -> C4 -> C5. L'ordre des chantiers est fixe et ne doit pas etre modifie.

---

## Vue d'ensemble

```
 #    Chantier                              Priorite    Estimation   Statut
----  ------------------------------------  ----------  ----------   ------
 C0   Correctifs critiques + fondations     CRITIQUE    1-2 jours    TERMINE
 R1   Responsive / Support Mobile           HAUT        3-4 jours    TERMINE
 C1   Trend v2 + Decouvrir + Collections    HAUT        5-7 jours    TERMINE
 C2   Moteur de Similarite (absorbe F3)     MOYEN       7-10 jours   TERMINE (graphe D3 reporte)
 H0   Hygiene & Solidification              MOYEN       2 jours      TERMINE
 P1   Polish & Correctifs UI               MOYEN       1-2 jours    TERMINE
 C6   Veille elargie & Suivi artistes       HAUT        7-10 jours   EN COURS (C6.0 + C6.1 + C6.a TERMINES)
 F5   Import manuel (recherche externe)    MOYEN       2-3 jours    A FAIRE
 C3   Ouverture aux amis                    MOYEN       5-7 jours    DECLENCHEMENT MANUEL (apres H0)
 C4   Reco personnalisee                    BAS         3-5 jours    APRES OUVERTURE
 C5   Collections v2 (polymorphe + dossiers) BAS       3-5 jours    APRES OUVERTURE
 D4   Pages Detail (Vague 3)               BAS         5-7 jours    BLOQUE (briefs)
 N1   Nettoyage residus                     BAS         1 jour       A FAIRE
```

### Chantiers termines (reference)

```
 #    Chantier                           Statut
----  ---------------------------------  ------
 S1   Securite & Hardening              TERMINE
 S2   Qualite & CI Pipeline             TERMINE
 A1   Service Layer Backend             TERMINE
 A2   Refactor Workers                  TERMINE
 A3   Frontend Perf & Accessibilite     TERMINE
 D1   FIX Design immediats             TERMINE
 D2   Genres — Refonte complete         TERMINE
 D3   Hub / Search                      TERMINE
 D5   Refactor Composants partages      TERMINE
 F4   Import Rekordbox Web              TERMINE
 C0   Correctifs critiques + fondations TERMINE
 R1   Responsive / Support Mobile     TERMINE
 C1   Trend v2 + Decouvrir + Collections TERMINE
 C2   Moteur de Similarite + Artistes    TERMINE (graphe D3 reporte)
 H0   Hygiene & Solidification          TERMINE
 P1   Polish & Correctifs UI            TERMINE
```

### Dependances

```
C0 ─────────> Tout (prerequis securite + fondations data)              ✅ TERMINE
R1 ─────────> C1 (mobile requis pour l'UX decouvrir)                  ✅ TERMINE
C1 (trend) ─> C3 (reco par defaut prete avant ouverture)              ✅ TERMINE
C2 (simil) ─> C4 (socle de la reco personnalisee)                     ✅ TERMINE

H0 ─────────> C3 (hygiene secu/infra avant ouverture)              ✅ TERMINE
P1 ─────────> Rien (parallelisable avec tout)                      ✅ TERMINE

--- actif ---
C6 (veille) ┬ C6.0 dedup prerequis avant C6.a crawl massif
             ├ parallele avec F5
             └ avant C3 idealement (plus de donnees = meilleure XP nouveaux users)
F5 ─────────> Rien (parallelisable avec tout)
C3 (ouvert) = declenchement manuel, apres H0 (FAIT) + C1 + idealement C6
C4 ─────────> C2 + C3 (similarite + likes + users)
C5 ─────────> C3 (apres ouverture)
N1 ─────────> Rien (parallelisable avec tout, priorite basse)
```

### Decisions produit actees

| Decision | Contenu |
|---|---|
| Politique de scope a l'import | Track absente du catalog -> tentative d'enrichissement. Match plateforme -> `shared`. Pas de match ou match ambigu -> `private`, visible uniquement par l'importeur. Re-tentative periodique avec promotion automatique si un match apparait. Doublons entre scopes prives : non traites, par design. |
| Collections perso | v1 (tracks only) integree dans C1. v2 prevue dans C5 : items polymorphes (tracks/sets/artistes/genres/playlists) + dossiers. Strictement privees : une collection n'est visible que par son proprietaire. |
| F3 Graphe artistes | Absorbe dans le moteur de similarite (C2). Le graphe devient une vue du moteur, pas un chantier separe. |
| Trend | Classement (pas score absolu), calcule par famille de genre, recalcule chaque nuit. Formule composite : detections ponderees (type de source, taille de playlist) x decay temporel x velocite x convergence multi-sources. Distinction fraicheur / revival portee par la ponderation temporelle. |
| Reco de trend | Decorrellee des likes. Offre par defaut, notamment pour les nouveaux users sans historique. |
| Reco personnalisee | Apres ouverture. Necessite le moteur de similarite + les likes. |
| Dedup sets | Un set logique = un seul signal trend, peu importe le nombre de sources (YouTube + Soundcloud) ou de parties. Les doublons sont rattaches (parent/enfant ou multi-source) et exclus du scoring. |
| Follow vs Like | Like = signal passif de gout pour la reco. Follow = surveillance active d'un artiste (releases, sets, activite). Les deux systemes coexistent, decorrelees. |

---

> Detail des 6 chantiers termines : voir `docs/completed/ROADMAP_chantiers_termines_2026-07.md`

---

## C6 — Veille elargie & Suivi artistes

**Priorite : HAUT**
**Estimation : 7-10 jours**
**Depend de : C1 (TERMINE). Parallelisable avec C2.**
**Statut : EN COURS — C6.0 + C6.1 + C6.a TERMINES (2026-07-07 / 2026-07-08)**

### Objectif

Le bottleneck de Diggy n'est ni l'algo ni l'UI : c'est le volume et la diversite des donnees entrantes. Aujourd'hui 29 playlists suivies + 27 sets manuels = bassin trop etroit et biaise vers les choix de curation du createur. Ce chantier elargit les sources de donnees automatiques pour alimenter le trend, la similarite (C2), et la reco (C4).

Trois axes :
1. Crawler global TrackID.net (pas juste les sets user)
2. Suivi actif d'artistes (releases, sets, activite multi-source)
3. Re-crawl intelligent des sets incomplets

### Constats

- Les 29 playlists produisent ~5000 radar_tracks : seul flux entrant automatique
- Les sets sont ajoutes manuellement, jamais re-crawles apres import
- Un track qui passe dans un set DJ = signal de trending fort et objectif (pondere 3x dans C1), mais on ne capture quasi rien de ce signal aujourd'hui
- TrackID.net publie des dizaines de sets quotidiennement avec tracklists identifiees : mine d'or inexploitee
- Probleme de doublons TrackID.net : meme set sur YouTube + Soundcloud = 2 lignes, sets en parties (PART1, PART2...) = pollution du scoring

### C6.0 — Dedup sets TrackID (prerequis)

**Doit passer AVANT le crawl massif, sinon on cree de la dette immediatement.**

Deux cas de doublons a traiter :

**Cas 1 : Meme set, sources differentes (YouTube + Soundcloud)**

Signaux de dedup par ordre de confiance :
- Artiste + titre normalise (apres strip des tags source, lowercase, trim) : couvre ~90% des cas
- Premiere track identique + meme artiste : quasi certain
- Tracklist overlap > 80% dans le meme ordre : meme set

Modele : ne pas supprimer le doublon, mais le **rattacher** via une table `set_sources` :
```
set_sources (nouvelle table)
  set_id      → sets.id (le set "master")
  source      → enum (youtube, soundcloud, mixcloud, etc.)
  external_url
  trackid_id  → identifiant TrackID.net de cette version
```
Avantages : un seul set dans le scoring, on garde les deux sources, on peut **merger les tracklists** (YouTube a identifie tracks 1-5, Soundcloud 3-8 → on recupere 1-8).

**Cas 2 : Set complet + parties (PART 1, PART 2...)**

- Detection : regex sur le titre → `(part\s*\d+|pt\.?\s*\d+|p\d+)` en fin de titre
- Groupement : meme artiste + meme titre de base (sans suffixe part) → candidats au regroupement
- Si un set "complet" existe : les parties sont rattachees comme enfants (`parent_set_id` sur `sets`)
- Si pas de set complet : les parties partagent un `group_id`, scorees comme un seul set logique

**Regle scoring : un set logique = un seul signal trend, peu importe le nombre de sources ou de parties.**

Taches :
- [x] Normalisation titre : fonction `normalize_set_title()` (strip tags source, lowercase, trim, retirer "Official", "Full Set", etc.)
- [ ] Migration : table `set_sources` (set_id, source, external_url, trackid_id, created_at)
- [x] Migration : colonne `parent_set_id` (nullable FK vers `sets.id`) + `group_id` (nullable) sur `sets`
- [x] Logique de detection de doublons a l'import (avant insertion)
- [x] Merge tracklists entre sources d'un meme set (union ordonnee)
- [x] Adapter `compute_trends` : exclure les sets avec `parent_set_id IS NOT NULL` du scoring
- [x] Audit des 27 sets existants pour valider la logique de dedup

### C6.a — Crawler global TrackID.net

Crawler le flux global de TrackID.net (pas juste les sets importes par un user). Deux axes paralleles : prospectif (nouveaux sets) + backfill (rattrapage historique progressif).

**Pourquoi le backfill est utile au-dela du trend :**
Le trend ne valorise que les sets recents (signal chaud). Mais le graphe de proximite C2 est base sur la co-occurrence dans les sets : un set de 2019 qui contient Eric Prydz + Nina Kraviz est aussi utile qu'un set de 2025 pour confirmer leur proximite. L'historique enrichit le graphe de facon cumulative, independamment de la valeur trend.

**Volume TrackID.net (sonde le 2026-07-07) :**
```
Total sets indexes : 363 650
Cadence actuelle  : ~150 sets/jour ajoutes
Plus ancien       : 1978-11-17 (addedOn 2024-01-31)
Distribution approximative :
  avant 2018  →  ~50 000 sets  (exotiques, peu pertinents)
  2018-2020   →  ~50 000 sets
  2021-2022   →  ~50 000 sets
  2023-2024   → ~100 000 sets
  2025-2026   → ~100 000 sets  (cadence ~150/j)
```

**Note API :** champ `addedOn` = date d'indexation TrackID (fiable pour le tri backfill). Champ `createdOn` = date declaree du set (peut etre vintage, non fiable pour ordonner le crawl).

#### C6.a.0 — Prospectif (flux quotidien)

- [x] Task Celery Beat : `crawl_trackid_latest`, schedule quotidien (03:30, avant compute_trends)
- [x] Crawl des sets indexes depuis la derniere execution (`addedOn > last_run_ts`, stocke en Redis : `trackid_crawl_last_run`)
- [x] Import automatique dans `sets` + `set_tracks` via `import_audiostream()`
- [x] Dedup a l'import via C6.0 (verifier doublon avant insertion)
- [ ] Filtrage optionnel par pertinence genre (a evaluer apres quelques jours — risque de bruit hors-scope : pop, rock)
- [x] Rate limiting : `trackid` deja configure dans `rate_limiter.py` (0.66 req/s, 1 concurrent)
- [x] Declenchement de `resolve_set_tracks` apres chaque run (lien catalog + enrichissement Deezer)

#### C6.a.1 — Backfill historique (rattrapage progressif)

Recuperer l'historique TrackID a raison de X sets/jour, en remontant dans le temps depuis la date d'implementation. Converge naturellement sans spike de charge.

**Mecanique :**
- Curseur Redis : `trackid_backfill_cursor` = `addedOn` du set le plus ancien traite (ISO8601)
- Chaque run : fetch X sets avec `addedOn < curseur`, tri `addedOn` desc, met a jour le curseur
- Condition d'arret : curseur < `TRACKID_BACKFILL_MIN_DATE` (env var, defaut = `today - 2ans`) ou plus aucun resultat
- Partage la meme logique d'import et de dedup que C6.a.0

**Estimation charge (pipeline complet par set) :**
```
Etape                    Detail                            Temps/set
────────────────────────────────────────────────────────────────────
1. Fetch TrackID detail  0.66 req/s (rate limiter)        ~1.5s    ← goulot
2. DB catalog lookup     bulk_get_or_create_catalog()     ~50ms
3. Deezer enrich         tache nightly separee (05:00)    —
4. Beatport enrich       tache nightly separee (06:00)    —
```

**Impact sur les taches nightly (estimation 20% nouvelles tracks par set) :**
```
Backfill      Crawl TrackID    Nouvelles tracks/j   Overhead Deezer   Overhead Beatport
──────────────────────────────────────────────────────────────────────────────────────
100 sets/j    2.5 min          ~500                 +1 min            +5 min
500 sets/j    12.5 min         ~2 500               +4 min            +25 min   ← recommande
1 000 sets/j  25 min           ~5 000               +8 min            +50 min
3 000 sets/j  75 min           ~15 000              +25 min           +2h30
```

> Beatport : `soft_time_limit=7h` dans `enrich_catalog_beatport`. A surveiller au-dela de 1000 sets/j.

**Cadence recommandee : 500 sets/jour**
- 1 an d'historique (~55 000 sets) → rattrapé en ~110 jours
- 2 ans (~100 000 sets) → rattrapé en ~200 jours
- Charge totale par nuit : ~15 min de trafic TrackID + 25 min overhead Beatport

Taches :
- [x] Task Celery Beat : `backfill_trackid_sets`, schedule quotidien (02:00, avant prospectif)
- [x] Curseur Redis `trackid_backfill_cursor` init a `today` au premier run
- [x] Env var `TRACKID_BACKFILL_SETS_PER_DAY` (defaut : 500) + `TRACKID_BACKFILL_MIN_DATE` (defaut : today - 730j)
- [x] Condition d'arret : curseur < min_date ou reponse vide → marquer backfill termine dans Redis
- [x] Log du curseur courant a chaque run (monitoring progression)

### C6.b — Re-crawl decroissant des sets incomplets

Les sets TrackID.net ne sont pas toujours complets a la premiere visite (identification en cours). Re-crawler intelligemment sans gaspiller de bande passante.

Cadence de re-crawl (backoff exponentiel) :

```
Age du set           Frequence
───────────────────  ─────────────────────
0 - 7 jours          tous les jours
7 - 30 jours         1x / semaine
30 - 90 jours        1x / mois
90+ jours             STOP (marque "final")
```

Sortie anticipee : si le % d'identification n'a pas bouge sur 3 re-crawls consecutifs → marque "final" immediatement, peu importe l'age.

- [ ] Colonnes sur `sets` : `completion_pct` (float), `last_recrawl_at`, `recrawl_count`, `recrawl_status` (enum: active/final)
- [ ] Task Celery : `recrawl_incomplete_sets`, schedule quotidien, selectionne les sets eligibles selon la cadence
- [ ] Logique de sortie anticipee (3 crawls sans changement → final)
- [ ] Mise a jour des tracklists au re-crawl (ajout des tracks nouvellement identifiees)

### C6.c — Suivi d'artistes v1 (Deezer + TrackID)

Feature user-facing : "suivre" un artiste = surveillance active de son activite. Decouple du like (qui reste un signal de gout passif pour la reco).

| Source | Signal surveille | Faisabilite |
|--------|-----------------|-------------|
| **Deezer** | Nouvelles releases (`/artist/{id}/albums?order=date`) | Trivial — `deezer_id` sur 99% des artistes |
| **TrackID.net** | Nouveaux sets contenant l'artiste | Faisable — on scrape deja le site |

- [ ] Migration : table `followed_artists` (user_id, artist_id, followed_at)
- [ ] Migration : table `artist_activity` (id, artist_id, activity_type enum, source, title, external_url, catalog_id nullable, set_id nullable, detected_at, payload_json)
- [ ] Bouton "Suivre" sur ArtistDetailView (distinct du like)
- [ ] Task Celery Beat : `check_followed_artists`, quotidien, batch sur tous les artistes suivis par au moins 1 user
- [ ] Check Deezer releases : comparer derniere release connue vs API, creer `artist_activity` si nouveau
- [ ] Check TrackID.net : rechercher sets recents contenant l'artiste, croiser avec sets deja importes
- [ ] Surface frontend : section "Nouveautes de tes artistes" (vue dediee ou shelf sur le Hub)
- [ ] Badge/notification : indicateur de nouvelles activites non vues

### C6.d — Suivi d'artistes v2 (Soundcloud) — futur

Extension du suivi artiste a Soundcloud. **Reporte apres validation de C6.c** car le scraping Soundcloud est fragile (pas d'API officielle, anti-bot).

| Source | Signal surveille | Faisabilite |
|--------|-----------------|-------------|
| **Soundcloud** | Nouveaux tracks + reposts + mixes | Moyen — scraping ou `soundcloud-lib`, fragile |

- [ ] Colonne `soundcloud_url` sur `artists`
- [ ] Scraping profil Soundcloud (tracks + reposts)
- [ ] Import des tracks trouvees → enrichissement Deezer/Beatport
- [ ] Integration dans `artist_activity`

Extensions futures possibles (non planifiees) :
- YouTube : Data API v3, quota limite mais suffisant pour des checks quotidiens
- Bandcamp : RSS/feed scraping
- Beatport : extension naturelle de l'enrichissement existant

### C6.e — Playlists auto-follow

Toute playlist en base devrait etre surveillee a intervalle regulier, pas seulement les 29 "watched".

- [ ] Supprimer la distinction rigide watched/non-watched : toute playlist connue = crawl periodique
- [ ] Cadence adaptative (meme principe que C6.b : frequente au debut, decroissante si stable)
- [ ] Ou a minima : elargir les criteres d'ajout automatique de playlists a surveiller

### Risques identifies

| Risque | Mitigation |
|--------|-----------|
| Rate limiting / ban TrackID.net | Headers polis, throttling, potentiellement proxy rotatif |
| Bruit hors-genre (pop, rock) | Filtrage post-crawl par pertinence genre — a evaluer empiriquement |
| Volume DB (5k → 50k+ radar_tracks) | Pas un probleme pour Postgres, mais surveiller index et temps de `compute_trends` |
| Fragilite scraping Soundcloud | Ne pas en faire un pilier critique en v1, d'ou le report en C6.d |

### Definition of Done

```bash
# Dedup
# Doublons sets existants identifies et rattaches
# Nouveau set importe → dedup automatique avant insertion
# compute_trends exclut les doublons/parties

# Crawler global
# crawl_trackid_latest tourne quotidiennement
# Nouveaux sets apparaissent dans la table sets sans intervention manuelle
# Impact visible sur le trend (plus de signaux set)

# Re-crawl
# Sets incomplets re-crawles avec backoff exponentiel
# Sets "final" ne consomment plus de bande passante

# Suivi artistes
# Bouton "Suivre" sur Artist Detail, distinct du like
# check_followed_artists detecte les nouvelles releases Deezer
# Section "Nouveautes" accessible dans l'app
```

---

## F5 — Import manuel (recherche externe)

**Priorite : MOYEN**
**Estimation : 2-3 jours**
**Depend de : rien (APIs Deezer/TIDAL deja accessibles)**
**Statut : A FAIRE — parallelisable avec C6/P1**

### Objectif

Permettre a tout utilisateur connecte d'ajouter un track au catalog via une recherche sur les sources externes (Deezer, TIDAL). Aujourd'hui les tracks n'entrent que par import en masse (Rekordbox XML, crawl playlists, import sets TrackID) — aucun moyen d'ajouter un son a la main.

### Faisabilite technique

| Source | Recherche | Auth | ISRC | Statut |
|--------|-----------|------|------|--------|
| **Deezer** | `search_deezer()` dans `deezer_enrich.py` | Aucune (API publique) | Oui | Pret a l'emploi |
| **TIDAL** | `tidalapi.session.search()` | OAuth device flow (tokens deja en Redis) | Oui | Trivial a ajouter |
| **Spotify** | Pas de search dans `spotifyscraper` | — | Non | Pas faisable |

### F5.a — Backend : endpoint recherche externe

- [ ] `GET /api/search/external?q=...` : recherche parallele Deezer + TIDAL
- [ ] Resultats fusionnes, dedupliques par ISRC (priorite Deezer si doublon)
- [ ] Rate limiting Deezer (0.12s entre requetes, deja en place dans `deezer_enrich.py`)
- [ ] Indiquer dans la reponse si le track existe deja dans le catalog (`catalog_id` si match ISRC/normalized_key)

### F5.b — Backend : endpoint import

- [ ] `POST /api/catalog/import` : prend un `deezer_id` ou `tidal_id`
- [ ] Enrichissement via `deezer_enrich.py` (flow existant : artwork, ISRC, duration, etc.)
- [ ] Scope `shared` (source officielle = match confirme)
- [ ] Dedup : verifier ISRC / `normalized_key` avant insertion, retourner l'entree existante si doublon
- [ ] Creation artiste(s) via le flow existant (`get_or_create_artist`)

### F5.c — Frontend : barre de recherche + import

- [ ] UI de recherche (vue dediee ou modale depuis le header)
- [ ] Affichage resultats : artwork, titre, artiste, source (badge Deezer/TIDAL)
- [ ] Badge "Deja dans le catalog" si le track existe
- [ ] Bouton "Importer" par resultat, feedback immediat (track ajoutee, lien vers la fiche catalog)

### Definition of Done

```bash
# GET /api/search/external?q=artist+title -> resultats Deezer + TIDAL
# POST /api/catalog/import avec deezer_id -> entree catalog creee
# Dedup : meme ISRC -> pas de doublon, retourne l'existant
# Frontend : recherche + affichage + bouton import fonctionnels
# Accessible a tout utilisateur connecte
```

---

## C3 — Ouverture aux amis

**Priorite : MOYEN**
**Estimation : 5-7 jours**
**Depend de : C1 (TERMINE) + H0 (hygiene secu/infra) + idealement C6 (donnees)**
**Declenchement : ta decision d'inviter, pas la roadmap**
**Statut : A FAIRE**

### Objectif

Fermer l'application et garantir l'etancheite entre users. Regroupe le reliquat Phase 6, la verification Phase 7, et les prerequis d'accueil.

### C3.a — Fermeture (reliquat Phase 6, dimensionne par l'audit)

L'audit invalide le "normalement deja traite" : le middleware laisse public tout GET sur catalog/artists/sets/genres/search/taxonomy.

- [ ] Basculer les GET publics en auth obligatoire (`get_current_user_optional` -> `get_current_user`), exemptions restantes : `/api/auth/*`, `/api/health`, `/api/watchlist/active` (a securiser autrement : token interne ou appel direct DB par le worker)
- [ ] **Filtrer `scope=private` d'autrui sur tous les endpoints catalog** (browse, detail, search, stats genres) : bloquant, sans ca la politique de scope est violee des le browse
- [ ] `GET /api/sets/{id}` : filtre `user_id` sur le check in_lib (`sets.py:281`)
- [ ] `/storage/*` : proteger les artworks (auth au niveau Nginx via `auth_request` vers l'API, ou URLs signees MinIO) : IDs sequentiels enumerables aujourd'hui
- [ ] Supprimer le guest cap (plus de visiteurs = plus besoin de cap)

### C3.b — Import multi-user (verification Phase 7, audit largement OK)

L'audit confirme : chaine user_id propre de bout en bout, lock Redis per-user, champ scope actif, et la promotion private -> shared via enrichissement Deezer **deja implementee** (`deezer_enrich.py`). La politique decidee est a ~80% en place.

Reste :
- [ ] **Corriger le perimetre d'enrichissement** : le check SQL montre 0/259 tracks private enrichies, preuve que les tasks d'enrichissement excluent `scope=private`. La mecanique de promotion existe (`deezer_enrich.py`) mais ne s'execute jamais sur les private. Inclure explicitement le scope private dans les passes d'enrichissement (tache Celery Beat dediee ou extension de `enrich_catalog`), sinon une track mal taguee ou un unreleased qui sort officiellement reste private a vie
- [ ] Etendre le test d'admission a Beatport (pas seulement Deezer) si pertinent
- [ ] Test reel de bout en bout : import d'une deuxieme bibliotheque Rekordbox (compte de test), verification dedup ISRC/normalized_key, scopes, non-regression sur ta lib
- [ ] Verifier le comportement funnel en cas de match ambigu : rester private (acte : en cas de doute, on ne matche pas)

### C3.c — Accueil

- [ ] Onboarding minimal : que voit un nouvel utilisateur sans bibliotheque ? (reponse : le catalogue shared + le trend par famille = la reco par defaut, d'ou C1 avant C3)
- [x] ~~Frontend build statique de prod~~ — FAIT (Nginx static build, voir reliquats)
- [ ] Sentry DSN configure (monitoring minimal avant d'avoir des users reels)

### Definition of Done

```bash
# Tout GET sans token -> 401 (sauf /api/auth/*, /api/health)
# scope=private d'un autre user invisible dans catalog/search/genres
# /storage/* protege (pas d'acces anonyme)
# Import d'une 2e lib Rekordbox : dedup OK, scopes OK
# Build frontend statique (pas Vite dev server)
```

---

## C4 — Recommandation personnalisee (apres ouverture)

**Priorite : BAS**
**Estimation : 3-5 jours**
**Depend de : C2 + C3**
**Statut : APRES OUVERTURE**

### Objectif

Croiser le moteur de similarite (C2) avec les likes (`user_opinions`). Utile des un seul user (toi), mais volontairement place apres l'ouverture : chaque nouvel utilisateur enrichit le signal.

- [ ] Profil de gout par user : agregation des scores de similarite (C2) des tracks likees (penalisation des dislikees)
- [ ] Reco = scoring C2 (metadonnees + co-occurrence) pondere par le profil, filtre par famille/BPM, excluant la lib existante
- [ ] Surface : section "Pour toi" distincte de la section trend (les deux recos coexistent, decorrelees)
- [ ] Long terme (parque, inchange) : track2vec sur tracklists de sets, pgvector si embeddings necessaires, audio features, LLM normalisation

### Definition of Done

```bash
# Endpoint /api/recommendations -> tracks personnalisees
# Section "Pour toi" dans le Hub, distincte du trend
```

---

## C5 — Collections v2 (polymorphe + dossiers)

**Priorite : BAS**
**Estimation : 3-5 jours**
**Depend de : C1 (TERMINE)**
**Statut : A FAIRE — après ouverture**

### Objectif

Transformer les collections (actuellement tracks-only) en un système de curation général :
n'importe quelle entité de l'app peut être ajoutée à une collection, et les collections
peuvent être organisées en dossiers. Concept : "boards" de curation DJ (inspiration Pinterest/Rekordbox folders).

### C5.a — Items polymorphes

Actuellement `collection_items` a une FK stricte vers `catalog.id`. Migration vers un pattern
polymorphe : `item_type` (enum) + `item_id` (integer) + `item_name` optionnel (pour les entités
adressées par slug comme les genres).

- [ ] Migration Alembic : alter `collection_items` — supprimer FK `catalog_id`, ajouter `item_type VARCHAR(20)` + `item_id INTEGER` + `item_name VARCHAR(255)` nullable
- [ ] Types supportés : `track` / `set` / `artist` / `genre` / `playlist`
- [ ] Mettre à jour le router `/api/collections` : sérialisation et désérialisation par type
- [ ] Bouton "Ajouter à une collection" sur les pages : ArtistDetailView, SetDetailView, GenreDetailView, CollectionDetailView (pour les playlists/watched)
- [ ] `CollectionDetailView` : render hétérogène selon le type de chaque item (card artiste ≠ card track ≠ card set)

### C5.b — Dossiers

Ajouter un niveau hiérarchique au-dessus des collections, dans l'esprit des dossiers Rekordbox.

- [ ] Migration Alembic : nouvelle table `collection_folders` (id, user_id, name, position, created_at)
- [ ] Ajouter `folder_id INTEGER NULL` FK vers `collection_folders` sur `user_collections`
- [ ] CRUD dossiers : POST/PATCH/DELETE `/api/collections/folders`
- [ ] `CollectionsView` : affichage arborescent — dossiers dépliables avec leurs collections, collections "orphelines" (sans dossier) en bas
- [ ] UX déplacement : assigner/retirer une collection d'un dossier (simple select ou drag & drop)

### Decision produit actee

| Decision | Contenu |
|---|---|
| Intégrité référentielle | Pattern polymorphe sans FK native PostgreSQL — intégrité gérée au niveau applicatif. Acceptable à l'échelle de Diggy. |
| Dossiers | Un seul niveau (dossier > collection > items). Pas de dossiers imbriqués. |
| Visibilité | Collections et dossiers strictement privés par user (inchangé). |

### Definition of Done

```bash
# collection_items supporte track/set/artist/genre/playlist
# Bouton "Ajouter à une collection" présent sur Artist/Set/Genre/Playlist detail
# CollectionDetailView render correct pour chaque type d'item
# collection_folders CRUD fonctionnel
# CollectionsView affiche l'arborescence dossiers > collections
```

---

## D4 — Pages Detail (Vague 3 Design)

**Priorite : BAS**
**Estimation : 5-7 jours**
**Depend de : D5 (composants partages)**
**Statut : BLOQUE — en attente briefs designer pour Track/Playlist detail**

### Taches

- [ ] **Verifier FIX appliques** sur Artist Detail et Set Detail
- [ ] **Track Detail** `/catalog/:id` (quand brief livre) : Hero + StatStrip + blocs relationnels
- [ ] **Playlist Detail** `/playlists/:id` (quand brief livre) : Hero square + StatStrip + table tracks
- [ ] **Vague 5 — Admin panel** `/admin` (quand brief livre) : Refonte visuelle selon DA Wildflower

---

## N1 — Nettoyage residus

**Priorite : BAS**
**Estimation : 1 jour**
**Depend de : rien (parallelisable avec tout)**
**Statut : A FAIRE**

### Objectif

Supprimer le code mort et les residus de fonctionnalites supprimees. Reduction de surface d'attaque + coherence avec les conventions actuelles.

### N1.a — Residus auth email/password

L'auth est Google OAuth only depuis F3, mais des restes de l'ancien login email/password subsistent probablement :

- [ ] Routes mortes dans `server/api/routers/auth.py` (login/register email/password)
- [ ] Variables d'env avec defaults liees a l'ancien flow
- [ ] Colonne `hashed_password` eventuelle sur `users` (verifier `models.py`, prevoir migration de drop si elle existe)
- [ ] Tests obsoletes couvrant l'ancien flow

### N1.b — Suppression TagsView

TagsView est une vue morte, `/tags` redirige vers `/genres`.

- [ ] Supprimer `TagsView.vue` du frontend
- [ ] Supprimer la route `/tags` du router Vue

### Definition of Done

```bash
# Aucune route email/password dans auth.py
# Pas de colonne hashed_password sur users
# Pas de TagsView.vue dans le frontend
# Pas de route /tags dans le router
# Tests CI passent (pytest + vitest + lint)
```

---

## Reliquats hors chantiers (opportunistes)

| Point | Quand |
|---|---|
| ~~Refonte AdminView (1725 LOC)~~ | Absorbe dans H0.d |
| Monitoring complet (Flower, UptimeRobot, pg_stat_statements) | Apres ouverture, si le besoin apparait |
| Websocket progression import | Jamais peut-etre : le polling 2s suffit |
| Tests composants frontend | Au fil de l'eau (tests integration backend dans H0.f) |
| ~~Auto-migration au deploy~~ | FAIT — `alembic upgrade head` dans deploy.yml |
| ~~`/api/radar/full` crash genres sort~~ | FAIT — `literal_column` au lieu de `StringArray[1]` |
| ~~CSP bloque requetes API~~ | FAIT — `upgrade-insecure-requests` + location priority `^~` sur `/api/` et `/storage/` |
| ~~Frontend build statique~~ | FAIT — Vite dev server → Nginx static build. Container 5 MB au lieu de 512 MB. CSP propre. |
| ~~Nginx location priority~~ | FAIT — regex `\.(jpg)$` captait `/storage/` → fix avec `^~` prefix priority |

---

## Recapitulatif de sequence

| # | Chantier | Declencheur | Depend de |
|---|---|---|---|
| C0 | Correctifs critiques + cycle de vie detections | Immediat | - |
| R1 | Responsive mobile | Immediat apres C0 | - |
| C1 | Trend v2 + velocite + Decouvrir + Collections | Apres R1 | - (velocite calculable sur l'existant) |
| C2 | Moteur de similarite + graphe artistes | Apres C1 (ou en parallele partiel) | pgvector (metadonnees verifiees OK) |
| H0 | Hygiene & Solidification | TERMINE | Rien (audit 06/07) |
| P1 | Polish & Correctifs UI | TERMINE | C1 |
| F5 | Import manuel (recherche externe Deezer/TIDAL) | Parallelisable avec C6 | Rien (APIs deja accessibles) |
| C6 | Veille elargie & Suivi artistes | Parallelisable avec F5 | C1 (trend). C6.0 dedup prerequis a C6.a crawl |
| C3 | Ouverture (fermeture app + import multi-user + accueil) | Ta decision d'inviter | H0 (FAIT) + C1 + idealement C6 |
| C4 | Reco personnalisee | Apres ouverture | C2 + likes |
| C5 | Collections v2 (items polymorphes + dossiers) | Apres ouverture | C1 |
| N1 | Nettoyage residus (auth legacy + TagsView morte) | Opportuniste | Rien |

Notes :
- La velocite sur les ajouts (C1.b) est calculable des maintenant depuis `radar_tracks`. Seul le signal de retrait (`removed_at`) necessite d'accumuler de l'historique a partir de C0.1.
- C6 alimente directement C2 (plus de co-occurrences en set) et le trend C1 (plus de signaux). Lancer C6.0 + C6.a tot maximise les benefices pour les autres chantiers.

---

## Methode de travail

Chaque chantier suit le cycle :

1. **Brief** : ce document sert de brief — chaque section est autonome et assignable
2. **Execution** : le dev/agent execute selon le perimetre defini
3. **Review** : relecture du code + tests CI (`pytest tests/ -v`)
4. **Deploy** : `git push origin master` -> GitHub Actions -> SSH -> rebuild Docker
5. **Verification** : smoke tests VPS + validation visuelle
6. **Update** : cocher les taches dans ce document

**Commit naming** : `type(scope): description` (conventional commits)

```
fix(api): remove legacy unauthenticated radar endpoint
feat(frontend): add bottom nav for mobile responsive
feat(api): compute_trends v2 with source weighting
```

**Regles** :
- Un chantier = un delivrable deployable. On ne passe pas au suivant tant que le precedent n'est pas deploye et verifie.
- Les tests CI doivent passer a chaque commit.
- Zero couleur hardcodee dans le frontend — tout via `var(--...)`.
- Code en anglais, UI en francais.

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
> **Derniere mise a jour** : 2026-07-12 (C3.b — etancheite import multi-user livree : `catalog_visible()` gagne une clause `user_track`, l'importeur voit un track en collision avec le prive d'un autre user via son propre user_track SANS promouvoir ni muter la ligne d'autrui ; design « promotion a la collision » REJETE en review (fuite cross-user). C3.a fermeture GET + guest cap ECARTEES, /storage DIFFERE = decisions produit. Test e2e multi-user reel VERIFIE en prod (import compte B user 7, ligne d'autrui 7402 intacte, 0 fuite) : reliquat technique C3 CLOS ; declenchement de l'ouverture = decision William)

---

## Vision cible

Avant l'ouverture aux amis (5-10 DJs), Diggy doit offrir :
1. Une experience mobile utilisable (ils seront sur telephone)
2. Une recommandation de tendance solide, decorrellee des likes (offre par defaut des nouveaux arrivants sans historique)
3. Un moteur de similarite fonctionnel (socle de toute recommandation, avec ou sans user)
4. Une application fermee et etanche entre utilisateurs (auth obligatoire, scopes respectes)

Apres l'ouverture : la recommandation personnalisee (croisement similarite x likes), utile des un seul user et enrichie par chaque nouvel utilisateur.

**Sequence verrouillee** : ~~C0 -> R1 -> C1 -> C2~~ (TERMINE) -> ~~H0 + P1~~ (TERMINE) -> F5 + C6 (paralleles) -> **serie AU (audit 2026-07)** -> C3 (ouverture) -> C4 -> C5. L'ordre des chantiers est fixe et ne doit pas etre modifie.

**Sequencement interne serie AU** (arbitre dans `docs/audit_2026-07/DECISIONS.md`) : AU1 -> AU2 -> AU3 -> AU7 -> AU4 -> AU5 -> AU6 -> AU8. Contrainte imperative : le volet enrichissement de AU7 s'execute AVANT ou AVEC AU4.

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
 C6   Veille elargie & Suivi artistes       HAUT        7-10 jours   TERMINE (2026-07-12, C6.d reporte)
 AU1  Quick Wins audit                      HAUT        1-2 jours    TERMINE (2026-07-09)
 AU2  Sauvegardes & deploiement             HAUT        1-2 jours    TERMINE (2026-07-10)
 AU3  Integrite donnees (migration 0031)    HAUT        1-2 jours    TERMINE (2026-07-10)
 AU7  Dette de tests (enrich + auth)        HAUT        1-2 jours    TERMINE (2026-07-10)
 AU4  Robustesse workers                    MOYEN       2 jours      TERMINE (2026-07-10)
 AU5  Couche service backend                MOYEN       2-3 jours    TERMINE (2026-07-10)
 AU6  Dette frontend                        MOYEN       1-2 jours    TERMINE (2026-07-11)
 AU8  Hygiene repo & documentation          MOYEN       1-2 jours    TERMINE (2026-07-11)
 E1   Re-scan enrichissement (backoff+budget) MOYEN     1 jour       TERMINE (2026-07-10)
 F5   Import manuel (recherche externe)    MOYEN       2-3 jours    TERMINE (2026-07-12)
 C3   Ouverture aux amis                    MOYEN       5-7 jours    EN COURS (reliquat technique clos 2026-07-12 ; ouverture = decision William)
 C4   Reco personnalisee                    BAS         3-5 jours    APRES OUVERTURE
 C5   Collections v2 (polymorphe + dossiers) BAS       3-5 jours    APRES OUVERTURE
 D4   Pages Detail (Vague 3)               BAS         5-7 jours    BLOQUE (briefs)
 N1   Nettoyage residus                     BAS         1 jour       A FAIRE (partiel : N1.b fait, reste N1.a)
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
 AU1  Quick Wins audit                  TERMINE
 AU2  Sauvegardes & deploiement         TERMINE
 AU3  Integrite donnees (migration 0031) TERMINE
 AU7  Dette de tests (enrich + auth)    TERMINE
 AU4  Robustesse workers                TERMINE
 E1   Re-scan enrichissement (backoff+budget) TERMINE
 AU5  Couche service backend            TERMINE
 AU6  Dette frontend                    TERMINE
 AU8  Hygiene repo & documentation      TERMINE
 C6   Veille elargie & Suivi artistes   TERMINE (C6.d Soundcloud reporte)
 F5   Import manuel (recherche externe) TERMINE (2026-07-12)
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
C6 (veille) ┬ C6.0 dedup prerequis avant C6.a crawl massif              ✅ TERMINE
             ├ parallele avec F5
             └ avant C3 idealement (plus de donnees = meilleure XP nouveaux users)
F5 ─────────> Rien (parallelisable avec tout)
C3 (ouvert) = declenchement manuel, apres H0 (FAIT) + C1 + idealement C6

--- serie AU (audit 2026-07 — findings dans docs/audit_2026-07/CONSOLIDATED.md, arbitrages dans DECISIONS.md) ---
AU1 ────────> Rien (demarrage immediat, parallelisable avec C6)      ✅ TERMINE
AU2 ────────> AU1 (le cron backup est pose en AU1 ; offsite + restore en AU2)   ✅ TERMINE
AU3 ────────> ordre interne impose : migration 0031 -> A2-04 (index dans les modeles) -> /schema_doc -> passe doc CLAUDE.md   ✅ TERMINE
AU7 ────────> AVANT ou AVEC AU4 (filet de tests sur l'enrichissement avant de le modifier)   ✅ TERMINE
AU5 ────────> apres AU1 (A1-02 fixe en AU1, verification de non-regression en AU5)   ✅ TERMINE
E1 ─────────> AU7 imperatif (filet de tests enrichment.py avant modification) ; recommande avec ou juste apres AU4 (meme zone de code, coordonner avec A3-05 rate limiting partage)   ✅ TERMINE
Serie AU ───> avant C3 (les findings lie-chantier:C3/C6 restent dans leurs briefs respectifs)   ✅ TERMINEE (2026-07-11)
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
**Statut : TERMINE (2026-07-12) — C6.0 + C6.1 + C6.a (2026-07-07 / 2026-07-08) ; C6.b + C6.c (2026-07-11, commit e976e0d) ; C6.e (2026-07-12, commit a65b9f3, deploye et verifie — premier run du crawl universel CONTROLE dans les crawl-logs le 2026-07-12 : SAIN, 10/10 taches success 0 erreur. 56 playlists considerees, dispatched 7 = uniquement celles reellement modifiees (court-circuit `has_changed`), skipped_cadence 2, dropped_by_cap 0 ; le "~40+ attendu" etait une surestimation ignorant `has_changed`. recrawl_incomplete_sets finalized_complete 2585 / crawled 84 ; check_followed_artists artists_checked 2 + 1 release au feed. is_initial_detection pas encore exerce (aucune dormante >30j)). Seul reliquat : C6.d (Soundcloud), reporte**
**Renvois audit 2026-07** : rattaches a ce chantier (arbitrage Q8) — A1-10 (deplacer la logique attach/detach de `routers/admin.py` vers `set_dedup_service`), A1-11 (garde `is_virtual` avant suppression du parent dans `detach_set`), A2-12 (N+1 dans `match_set`, opportuniste). Voir `docs/audit_2026-07/CONSOLIDATED.md`.

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
- [x] ~~Migration : table `set_sources` (set_id, source, external_url, trackid_id, created_at)~~ — ABANDONNEE : le rattachement multi-source passe par `parent_set_id` + `is_virtual` (C6.1)
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

> Beatport : `soft_time_limit=7h` dans `enrich_catalog_beatport`. CONFIRME en prod (2026-07-10) : a 500 sets/j le sweep atteint deja ~7h (~6 500 tracks/nuit a 0.66 req/s) et depasse le soft limit (SoftTimeLimitExceeded + retry quotidiens). Traite par le chantier **E1** (budget nightly + re-scan backoff).

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

- [x] Colonnes sur `sets` : `completion_pct` (float), `last_recrawl_at`, `recrawl_count`, `recrawl_status` (enum: active/final)
- [x] Task Celery : `recrawl_incomplete_sets`, schedule quotidien, selectionne les sets eligibles selon la cadence
- [x] Logique de sortie anticipee (3 crawls sans changement → final)
- [x] Mise a jour des tracklists au re-crawl (ajout des tracks nouvellement identifiees)

### C6.c — Suivi d'artistes v1 (Deezer + TrackID)

Feature user-facing : "suivre" un artiste = surveillance active de son activite. Decouple du like (qui reste un signal de gout passif pour la reco).

| Source | Signal surveille | Faisabilite |
|--------|-----------------|-------------|
| **Deezer** | Nouvelles releases (`/artist/{id}/albums?order=date`) | Trivial — `deezer_id` sur 99% des artistes |
| **TrackID.net** | Nouveaux sets contenant l'artiste | Faisable — on scrape deja le site |

- [x] Migration : table `followed_artists` (user_id, artist_id, followed_at)
- [x] Migration : table `artist_activity` (id, artist_id, activity_type enum, source, title, external_url, catalog_id nullable, set_id nullable, detected_at, payload_json)
- [x] Bouton "Suivre" sur ArtistDetailView (distinct du like)
- [x] Task Celery Beat : `check_followed_artists`, quotidien, batch sur tous les artistes suivis par au moins 1 user
- [x] Check Deezer releases : comparer derniere release connue vs API, creer `artist_activity` si nouveau
- [x] Check TrackID.net : rechercher sets recents contenant l'artiste, croiser avec sets deja importes — realise en DB pure (sets deja importes des dernieres 48h), pas de recherche TrackID active (ecart assume)
- [x] Surface frontend : section "Nouveautes de tes artistes" (vue dediee ou shelf sur le Hub)
- [x] Badge/notification : indicateur de nouvelles activites non vues

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

- [x] Supprimer la distinction rigide watched/non-watched : toute playlist connue = crawl periodique
- [x] Cadence adaptative (meme principe que C6.b : frequente au debut, decroissante si stable)
- [ ] Ou a minima : elargir les criteres d'ajout automatique de playlists a surveiller — SANS OBJET (option complete retenue)

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

# Serie AU — Audit global 2026-07

> Issue de l'audit read-only du 2026-07-09 : 114 findings bruts, 106 uniques (2 critiques, 9 hautes, 38 moyennes, 57 basses).
> References : `docs/audit_2026-07/CONSOLIDATED.md` (findings + preuves), `docs/audit_2026-07/DECISIONS.md` (arbitrages Q1-Q9).
> Chaque tache reference l'ID de son finding source (tracabilite vers les rapports A1-A7).
> Sequencement : AU1 -> AU2 -> AU3 -> AU7 -> AU4 -> AU5 -> AU6 -> AU8. La serie passe avant C3.
> Deja fait hors chantier (2026-07-09, William) : dump manuel copie hors VPS (mitigation A5-01/02) ; rotation des tokens TIDAL (M3).

---

## AU1 — Quick Wins audit

**Priorite : HAUT**
**Estimation : 1-2 jours**
**Depend de : rien (parallelisable avec C6)**
**Statut : TERMINE (2026-07-09) — code deploye et verifie en prod (ebca46b, 9eb90dd, e2e4488) ; OPS VPS fait : cron backup actif (01:30 + check fraicheur 09:00), rattrapage A3-01 execute (235 promues, 0 restante), menage A5-13 (certbot fantome + 11 volumes orphelins)**

### Objectif

Les 8 QUICK WINS stricts (impact haute/critique x effort S) + les quick-wins candidats de confiance haute sans decision produit (arbitrage Q1, option A). Revue de la PR par lots thematiques : workers ensemble, infra ensemble, frontend ensemble.

### AU1.a — Les 8 quick wins stricts

- [x] A5-01 : cron backup quotidien sur le VPS (`docker compose run --rm backup`) + verification de fraicheur (alerte si latest > 26h)
- [x] M1 (A1-03/A2-10) : filtrer `in_lib` par `user_id` sur `GET /sets/{id}` (`sets.py:264`), `in_lib=False` pour les guests
- [x] M2 (A1-24/A4-01) : corriger `api.get('/radar/new-count')` -> `/api/radar/new-count` (`BottomNav.vue:58`) + ne fetcher que si authentifie
- [x] A4-02 : rebrancher les avis TrackDetailView sur le chemin canonique (trancher : `PATCH /api/catalog/{id}/avis` comme CatalogView, ou store opinions) — le POST actuel vise un endpoint inexistant
- [x] A3-01 : porter la promotion `private -> shared` dans `_enrich_entry_async` (`enrichment.py`) + test. Rattrapage des 235 lignes prod = script SEPARE, execute apres validation du fix (modalite Q1)
- [x] A6-02 : rate limiting — lire `X-Real-IP` (pose par nginx, non spoofable) au lieu de la 1re valeur de `X-Forwarded-For` (`rate_limit.py:36-40`) ; + A6-13 : logger le fail-open Redis (meme fichier)
- [x] A5-04 : `pip-audit -r server/api/requirements.txt --desc` dans la CI (le job actuel scanne le runner)
- [x] A7-01 : `git rm --cached .coverage` + patterns `.coverage`/`.coverage.*` dans `.gitignore`

### AU1.b — Volet repo/tokens (reliquat M3, rotation deja faite)

- [x] A6-01/A7-02 : `git rm --cached server/scripts/.tidal_tokens.json` + pattern `.tidal_tokens.json` au `.gitignore`
- [x] A3-16 : fallback fichier de `source_clients.py:246-259` -> chemin hors repo via env `TIDAL_TOKEN_FILE` (ou suppression du fallback, Redis + env suffisent)

### AU1.c — Bugs et suppressions actees (Q1b)

- [x] A1-02 : pagination `/search` — ORDER BY stable dans chaque helper + offset pousse en DB (ou retire de la signature). Fix minimal, independant du refactor AU5
- [x] A1-06 : supprimer `PATCH /watchlist/{id}/crawled` (preuve mecanique : 0 appelant)
- [x] A1-13 : supprimer `POST /genres/refresh-pillars` (casse en multi-process)
- [x] M7 (A4-03/A4-04/A7-13) : supprimer `AppearRow.vue` + `TagsView.vue` + retirer la mention TagsView de CLAUDE.md + corriger la ligne AppearRow de `detail-pages-audit.md` (absorbe N1.b)

### AU1.d — Lot backend (QW-c confiance haute)

- [x] A1-19/A1-20 : `GET /opinions/` avec response_model + validation `Literal` dans `OpinionUpdate` + garde `int(entity_key)` (422 au lieu de 500)
- [x] A1-21 : constante unique `BUCKET_PLAYLIST` importee depuis `image_service` (3 definitions du bucket)
- [x] A6-03 : `defusedxml.ElementTree` dans `rekordbox_xml.py` (billion laughs)
- [x] A6-05 : borner les payloads (`PATCH /radar/state/batch` max_length, `image_base64` max_length, strings watchlist)
- [x] A6-10 (volet docs) : desactiver `/api/docs` + `/api/openapi.json` en `ENV=production`. NB : le volet `/api/watchlist/active` part en AU5 (depend de A1-17, sinon `crawl_radar` casse)
- [x] A6-11 : ne plus logger `resp.text` du endpoint token Google (`auth.py:50-52`)
- [x] A6-12 : aligner `client_max_body_size` nginx sur 10M (ou lecture par chunks)

### AU1.e — Lot frontend (QW-c)

- [x] A4-10 : `'/api/genres/'` -> `'/api/genres'` dans HubView (307 a chaque affichage du Hub)
- [x] A4-11 : AdminGenres — deriver les stats du fetch principal (3 appels -> 2) + try/catch sur `fetchMappingStats`

### AU1.f — Lot infra (QW-c)

- [x] A5-05 : `COPY package-lock.json` + `npm ci` dans le Dockerfile frontend (build reproductible)
- [x] A5-10 : bloc `concurrency: deploy-prod` dans le workflow deploy
- [x] A5-11 : pinner `minio/minio` et `certbot/certbot` sur des tags versionnes
- [x] A5-12 : retirer le mapping `8080:80` du compose de base (le deplacer dans l'override local)
- [x] A5-13 : VPS — `docker rm` du certbot fantome + `docker volume prune` (fenetre de maintenance)
- [x] A5-16 : `.env.example` — `SECRET_KEY` -> `JWT_SECRET` + variables Google/Sentry/Backup manquantes
- [x] A5-18 : `http2 on;` sur le listener 443
- [x] A5-19 : `cache: npm` + `node-version: 22` dans la CI (alignement avec l'image prod)

### Definition of Done

```bash
# Backup : cron actif, dump quotidien frais dans diggy_backups
# Badge radar mobile > 0 pour un user avec du nouveau ; avis track persistes apres reload
# 0 entree scope=private avec deezer_id valide en prod (apres script de rattrapage)
# pip-audit audite requirements.txt ; .coverage et .tidal_tokens.json hors du suivi git
# pytest + vitest + ruff + eslint passent
```

---

## AU2 — Sauvegardes & deploiement

**Priorite : HAUT**
**Estimation : 1-2 jours**
**Depend de : AU1 (cron backup pose)**
**Statut : TERMINE (2026-07-10) — code deploye et verifie en prod (643dc67, 51fa038) ; OPS VPS fait : offsite rclone actif (Google Drive, `gdrive:diggy-backups/postgres`), test de restauration reel sur DB jetable (docs/restore.md date), crontab nettoye (A5-14), symlinks latest.* orphelins purges**

### Objectif

Rendre les backups reellement protecteurs (offsite + restauration testee) et fiabiliser le pipeline de deploiement. Integre la refonte du contexte de build workers (arbitrage Q9, test local complet du build obligatoire avant push).

### Taches

- [x] A5-02 : copie offsite des dumps chiffres (S3/B2/rclone hors Hostinger) + rétention >= 2 generations hors retention locale + verifier les snapshots dans le panel Hostinger
- [x] A5-03 : `docs/restore.md` (dechiffrement GPG + psql + re-mirror MinIO), cle GPG stockee hors VPS, test de restauration reel sur DB jetable, date
- [x] A5-06 : retirer `--force-recreate` du deploy (coupure DB/Redis a chaque push)
- [x] A5-07 : executer `alembic upgrade head` AVANT la bascule du nouveau code (meme bloc de script que A5-06)
- [x] A5-08 + A5-09 (Q9) : contexte de build `./server` + Dockerfile copiant api/ et workers/ + `.dockerignore` par contexte + suppression des bind mounts du compose de base. CONDITION : build local complet valide avant push
- [x] A5-14 : nettoyer le cron reload nginx redondant (apres A5-01)
- [x] A5-20 : healthchecks celery sur worker/worker_enrich + beat

### Definition of Done

```bash
# Un dump existe hors du VPS, restaure avec succes sur une DB jetable (procedure datee)
# Push sur master : postgres/redis/minio ne sont plus recrees sans changement
# docker inspect worker : plus de bind mount du repo hote en prod
```

---

## AU3 — Integrite donnees (migration 0031)

**Priorite : HAUT**
**Estimation : 1-2 jours**
**Depend de : rien. Ordre interne impose : 0031 -> A2-04 -> /schema_doc -> passe doc CLAUDE.md**
**Statut : TERMINE (2026-07-10) — code deploye et verifie en prod (2a17e12) : alembic_version=0031, colonnes/table mortes supprimees, champs retires des reponses API, flux preview live intact, autogenerate a blanc vide ; purge radar_trends effective au prochain compute_trends (07:00)**

### Objectif

Purger le schema des elements morts prouves (arbitrage Q3), realigner modeles/migrations/doc, et corriger les donnees servies perimees.

### AU3.a — Migration 0031 (perimetre exact Q3)

- [x] A2-01 : `DROP TABLE watched_playlists` (dump de precaution deja en place)
- [x] A2-06 : drop `catalog.fingerprint` + son index unique
- [x] A2-07 : drop `catalog.preview_url` + retirer le champ des schemas API (`schemas/catalog.py:26`, `schemas/radar.py:94`) et des SELECT (radar, similarity, catalog detail). NE PAS toucher `PreviewUrlResponse` (endpoint live, utilise par audioPlayer — garde-fou verifie le 2026-07-09)
- [x] A2-09 : `server_default=func.now()` sur `user_tracks.created_at`
- [x] A2-11 : index `ix_user_tracks_catalog_id` + `ix_user_follows_entity_id` (les 4 autres FK differees a C3)

### AU3.b — Realignement schema

- [x] A2-05 : retirer `artists.bio/country/real_name/soundcloud_id` des schemas Pydantic (colonnes conservees)
- [x] A2-08 : retirer `sets.event/venue/description` de `DJSetDetailOut` (colonnes conservees) + documenter leur statut reserve dans le MANUAL block
- [x] A2-02 : reserver `create_all` au harnais de test ; en dev Docker, `alembic upgrade head` au demarrage (cause racine de la table orpheline)
- [x] A2-04 : declarer dans les modeles les ~10 index/contraintes existant uniquement en migration (0020/0028/0029/0030) + autogenerate a blanc = diff vide
- [x] M4 (A2-03/A7-06) : regenerer `docs/database-schema.md` via `/schema_doc` (APRES A2-04)
- [x] A7-05 + M5 (A1-22/A3-15) : passe doc CLAUDE.md — 5 compteurs, arborescence `deezer_enrich.py` sous workers/, docstring `image_service.py`, "weekly" -> "daily", date Last verified

### AU3.c — Donnees servies perimees

- [x] A3-02 : purger `radar_trends` a chaque `compute_trends` (DELETE des lignes non touchees par le run, meme transaction) — 28% de lignes perimees servies aujourd'hui
- [x] A3-04 : distinguer echec HTTP Deezer de "not found" — ne poser `deezer_searched_at` que sur reponse 200 vide (sinon les entrees sortent definitivement du pipeline)

### Definition of Done

```bash
# alembic upgrade head OK en prod ; alembic revision --autogenerate = diff vide
# SELECT count(*) FROM radar_trends WHERE computed_at < (SELECT max(computed_at)...) = 0 apres compute_trends
# database-schema.md et CLAUDE.md a jour (compteurs, arborescence)
```

---

## AU7 — Dette de tests (enrichissement + auth)

**Priorite : HAUT**
**Estimation : 1-2 jours**
**Depend de : rien. IMPERATIF : s'execute AVANT ou AVEC AU4 (filet pour les modifications workers)**
**Statut : TERMINE (2026-07-10) — code deploye et verifie en prod (db25832) : 17 tests enrichment.py (cascade Deezer + conflits ISRC sur vraie session SQLite), 4 tests Vitest LoginCallbackView, enrichment.py + async_http.py hors du omit (gate mesure a 68,9 %, seuil 55 ; tasks/* et source_clients.py restent omis, dette AU4+), test_check_sync.py supprime (M6)**

### Objectif

Perimetre reduit par l'arbitrage Q7 : tester le code le plus critique aujourd'hui a zero filet, et rendre le gate de coverage honnete. A6-08 (import RB) et A6-14 (branches OAuth) restent opportunistes, au fil des chantiers.

### Taches

- [x] A6-04 (prioritaire) : retirer progressivement `enrichment.py`, `source_clients.py`, `workers/tasks/*` du `omit` de `pyproject.toml` — un gate aveugle est pire que pas de gate
- [x] A6-04 : tests unitaires sur `enrichment.py` (mock HTTP) — en priorite la resolution de conflits ISRC et la cascade Deezer
- [x] A6-07 : tests Vitest sur `LoginCallbackView` (cookie valide -> persist + redirect, cookie absent, base64 malforme, `?error=`)
- [x] M6 (A6-09/A7-08) : supprimer la fausse couverture `test_check_sync.py` (helper mort visant un module supprime) — pointer sur `server/deezer/sync_checker.py` si la logique y vit, sinon archiver

### Definition of Done

```bash
# pyproject.toml : enrichment.py hors du omit, gate CI toujours vert
# Cascade Deezer + conflits ISRC testes ; LoginCallbackView couvert (4 branches)
# Plus aucun test validant du code supprime
```

---

## AU4 — Robustesse workers

**Priorite : MOYEN**
**Estimation : 2 jours**
**Depend de : AU7 (volet enrichissement = filet de tests)**
**Statut : TERMINE (2026-07-10) — code deploye et verifie en prod (0f12091) : locks SET NX EX avec TTL > time_limit partout (resolve_set_tracks, crawl playlist 4600s, import RB atomique), suppression de playlist uniquement sur PlaylistGoneError typee par source, 10 except:pass logges, CrawlLogger sur crawl_followed_sets + link_set_artists, reclassify en chord (plus de result.get), rate limiting deezer/beatport partage via fenetre Redis (fail-open logge), artists.deezer_searched_at + re-recherche 30j (migration 0032) ; sanity check des crawls nightly prevu le 2026-07-11 matin**
**Renvoi : E1 (re-scan enrichissement + budget nightly) recommande dans la meme fenetre — meme zone de code, meme filet AU7 ; A3-05 (rate limiting partage) et le budget E1 se coordonnent.**

### Objectif

Erreurs typees, locks corrects, observabilite : que les crawls nocturnes echouent bruyamment et proprement au lieu de corrompre ou de se taire.

### Taches

- [x] A3-03 : `reclassify_genres_chunk` — ne vider `entry.genres` qu'a l'affectation d'une nouvelle valeur ; distinguer "aucun genre trouve (200)" d'"erreur source"
- [x] A3-05 : rate limiting partage (token bucket Redis pour deezer/beatport, ou borner la concurrence de la queue crawl) — limites actuellement multipliees par la concurrence prefork
- [x] A3-06 : clients Deezer sync — verifier status 200 + absence de cle `error` du JSON, lever sinon (tracklist partielle => faux `removed_at`)
- [x] A3-07 : remplacer le matching de chaine "404" par une exception typee `PlaylistGoneError` par source (suppression destructive actuellement declenchable par un message d'erreur quelconque)
- [x] A3-08 : logger les 6 `except: pass` muets (materialize_parent x3, post-import dedup, artwork, link artist)
- [x] A3-09 : `CrawlLogger` sur `crawl_followed_sets` et `link_set_artists`
- [x] A3-10 : `chord` au lieu de `result.get()` dans `reclassify_all_genres` (slot worker bloque jusqu'a 7h)
- [x] A3-11 : lock Redis sur `resolve_set_tracks` (pattern `enrich_catalog_beatport`, TTL 7500s)
- [x] A3-12 : `deezer_searched_at` sur Artist (stop aux re-recherches des 226 memes artistes a chaque run)
- [x] A3-13 : lock `crawl_single_playlist` TTL 4600s (> time_limit, actuellement 900s)
- [x] A3-14 : lock import RB en `SET NX EX` + delete conditionnel a la valeur, TTL >= time_limit

### Definition of Done

```bash
# Plus aucun except:pass muet dans workers/ + trackid/
# crawl_followed_sets visible dans /api/admin/crawl-logs
# Locks : TTL >= time_limit partout, acquisition atomique, release conditionnel
```

---

## AU5 — Couche service backend

**Priorite : MOYEN**
**Estimation : 2-3 jours**
**Depend de : AU1 (A1-02 deja fixe — verifier la non-regression)**
**Statut : TERMINE (2026-07-10) — code deploye et verifie en prod (8bb21a0, /deploy_verify SAIN) : search et watchlist extraits en services (routers 392->32 et 417->138 LOC), like_escape sur les LIKE de search + taxonomy, I/O watchlist async (httpx + run_in_threadpool), crawl_radar en DB directe + endpoint /api/watchlist/active supprime (router + _OPEN_PREFIXES), opinion_sync et get_or_create_catalog deplaces dans services/, sets/import via sync_set_opinion, API publique pillars (ensure_pillar_cache/ALL_PILLARS/pillar_map), taxonomy en ORM (CTE recursives conservees) + 20 smoke tests. Tests 981->1017, non-regression A1-02 verifiee. Ecart DoD assume : watchlist.py a 138 LOC (>100, zero logique metier restante). Reliquats opportunistes : requests sync dans admin.py/artist_service.py, LIKE non echappes hors search/taxonomy. Premier run prod de crawl_radar DB directe a verifier le 2026-07-11 (crawl-logs, avec le sanity check AU4/E1)**

### Objectif

Perimetre reduit par l'arbitrage Q8 : finir la couche service pour search et watchlist (les deux seuls domaines sans service) + rangements S. Contrainte : zero changement de comportement, protege par les tests existants. A1-10/A1-11 sont rattaches a C6.

### Taches

- [x] A1-01 : extraire `services/search_service.py` depuis `routers/search.py` (365 LOC, 5 helpers metier) + verifier la non-regression du fix A1-02
- [x] A6-06 : au passage dans search — helper `like_escape()` pour les metacaracteres `%`/`_` (~11 emplacements)
- [x] A1-05 : extraire `services/watchlist_service.py` (metadonnees Deezer, artwork, trigger crawl, cooldown)
- [x] A1-04 : remplacer les I/O synchrones (requests, MinIO) des endpoints async par httpx.AsyncClient / run_in_executor — a combiner avec A1-05 pour watchlist
- [x] A1-17 : `crawl_radar` lit les playlists actives en DB directe (via `workers/db.py`) au lieu de HTTP ; puis A6-10 (volet watchlist) : retirer `/api/watchlist/active` de `_OPEN_PREFIXES` et supprimer l'endpoint
- [x] A1-15 : deplacer `api/catalog.py` et `api/opinion_sync.py` vers `services/` (6 imports a mettre a jour)
- [x] A1-25 : `POST /sets/import` utilise `opinion_sync.sync_set_opinion` au lieu de sa reimplementation
- [x] A1-16 : API publique du cache pillars (`genre_service.ensure_pillar_cache()`) au lieu des imports de membres `_prives` par 3 routers
- [x] A1-18 + Q1b-2 : taxonomy (endpoints conserves, arbitrage Q1b) — smoke test 200 par endpoint + nettoyage SQL brut/camelCase sur le perimetre conserve

### Definition of Done

```bash
# routers/search.py et routers/watchlist.py < 100 LOC chacun, logique en service
# Plus d'appel HTTP worker -> API ; /api/watchlist/active supprime de _OPEN_PREFIXES
# 11 endpoints taxonomy smoke-testes ; pytest sans regression
```

---

## AU6 — Dette frontend

**Priorite : MOYEN**
**Estimation : 1-2 jours**
**Depend de : rien**
**Statut : TERMINE (2026-07-11) — code deploye et verifie en prod (d07c272, /deploy_verify SAIN) : useTaskPoll (timers par cle, cleanup onUnmounted integre, 8 sites setInterval migres — l'audit en comptait 7 —, fuite des 5 polls admin corrigee), usePaginatedList adopte par ArtistsView + GenresView (ref `loading` mort retire d'useInfiniteScroll), `.state` canonique + `@keyframes spin` uniques dans assets/page.css (12 blocs + 4 keyframes dedupliques — l'audit en comptait 10 —, overrides scoped conserves pour les divergences reelles), refreshUser() au boot via GET /auth/me (401 -> logout, erreur reseau -> silencieux), stub RouterLink de BottomNav.test.js rendu effectif. A4-09 clos SANS decoupage : bundle principal mesure 191,9 kB (72,3 kB gzip), HubView en import statique = choix deliberate verrouille par a11y.test.js, gain (~5-8 kB gzip) non justifie. Tests frontend 32 -> 50 ; CLAUDE.md mis a jour (composables, stores, 3 pitfalls frontend)**

### Objectif

Factoriser les patterns dupliques (pagination, polling, styles) et stopper les fuites d'intervals. A4-09 (HubView dans le bundle principal) : mesurer avant/apres, ne decouper que si le gain le justifie.

### Taches

- [x] A4-07 : composable `useTaskPoll(statusUrlFn, {intervalMs, onDone, onError})` avec cleanup `onUnmounted` integre — migrer les 7 implementations (5 admin d'abord)
- [x] A4-06 : resolu par construction via A4-07 (verifier : plus aucun `setInterval` sans cleanup dans `components/admin/`)
- [x] A4-05 : composable `usePaginatedList({endpoint, pageSize})` — adopter dans ArtistsView + GenresView (CatalogView hors scope)
- [x] A4-08 : trancher le `loading` de `useInfiniteScroll` (le retirer ou y integrer le guard) — avec A4-05
- [x] A4-12 : classe utilitaire `.state` + keyframe `spin` dans `assets/page.css`, migration vue par vue validee contre /design-system
- [x] A1-23 (volet frontend) : appeler `GET /auth/me` au boot pour rafraichir `user` (un passage `is_admin` false->true n'est visible qu'au re-login aujourd'hui)
- [ ] A4-09 (optionnel, mesure d'abord) : reduire ce que HubView embarque (sections lazy sous le fold) — `vite build` avant/apres — MESURE FAITE, decoupage non justifie (voir Statut), clos sans action

### Definition of Done

```bash
# 0 setInterval sans onUnmounted dans src/
# 1 seule implementation du poll de task Celery ; 1 seule du pattern liste paginee infinite-scroll
# vitest + eslint passent
```

---

## AU8 — Hygiene repo & documentation

**Priorite : MOYEN**
**Estimation : 1-2 jours**
**Depend de : AU1 (suppressions actees), decisions Q2/Q5/Q6**
**Statut : TERMINE (2026-07-11) — code deploye et verifie en prod (b72d994, /deploy_verify SAIN — containers image ./server recrees, frontend intact, aucune migration). Router `tracks` supprime (API : 13 routers / 91 endpoints ; `TrackImport` conserve, consomme par le flux XML rekordbox_xml.py ; tests multi-user via /tracks/bulk supprimes avec le router, e2e reporte a C3.b), import_rekordbox.py archive, `.claude/commands/` versionne (5 fichiers), 39 .md de `_design/` archives dans docs/completed/design/, README reecrit + server/api/scripts/README.md (8 rejouables / 6 one-shot dates), passe CLAUDE.md (compteurs, outillage local, Q6 stack locale + realite du proxy Vite api:8000 injoignable depuis le host, taxonomy, curl admin). Sentry verifie FONCTIONNEL (reception d'evenements confirmee dans l'UI le 2026-07-11). Serie AU close.**

### Objectif

Executer les decisions de rangement (Q2 import legacy, Q5 design clean, Q6 stack locale) et remettre la documentation d'entree au niveau (README bloquant pour C3).

### AU8.a — Import legacy (Q2)

- [x] A7-07/A1-08 : archiver `worker/import_rekordbox.py` dans `docs/completed/` (pas de suppression seche)
- [x] A1-08 : supprimer le router `tracks` (5 endpoints, ~500 LOC) + ses tests dedies. Garde-fou deja verifie (2026-07-09) : 0 appel frontend, seule une redirection de route. A1-09 sans objet
- [x] A7-07 : documenter dans CLAUDE.md — `worker/` + `server/deezer/` = outillage local cote PC Rekordbox (relocate, sync-check), hors runtime serveur

### AU8.b — Design clean (Q5)

- [x] A7-09 : versionner `.claude/commands/` (retirer `.claude/` du .gitignore pour ce chemin)
- [x] A7-09 : archiver les .md de reference de `_design/` dans `docs/completed/design/` ; `_design/` cesse d'etre reference par CLAUDE.md (les futurs handoffs viennent du projet Claude Design) — 39 .md archives, arborescence preservee ; le dossier local `_design/` (gitignore) reste a nettoyer manuellement
- [x] A7-10 : deplacer `design-decisions.md` vers `docs/` (a cote de design-audit.md)
- [x] `.gitignore` : newline finale + slash sur `docs/prompts/` (reste ignore, convention conservee)

### AU8.c — Documentation d'entree

- [x] A7-04 : reecrire README.md (structure actuelle, quickstart `docker compose up` + `.env.example`, liens CLAUDE.md / database-schema.md) — il decrit un projet qui n'existe plus
- [x] Q6/A5-17 : documenter dans CLAUDE.md que le dev local full-stack n'est PAS supporte (flux = push -> CI -> prod) + verifier que `npm run dev` seul degrade proprement (pas de crash de page si l'API est absente) — verifie PASS (boot avale les erreurs reseau) ; constat en plus : le proxy Vite `/api` cible `api:8000`, injoignable depuis le host, meme stack lancee
- [x] Q1b-2 : documenter les 8 endpoints taxonomy dans CLAUDE.md comme "reserves, non branches, futur explorateur de genres" — compte reel : 11 endpoints
- [x] Q1b-4 : documenter `GET /watchlist/`, `POST /reset-beatport`, `POST /artists/backfill-multi-artists` comme outillage curl admin (A1-07/A1-14) — correction en session : GET /watchlist/ alimente WatchlistView (pas curl-only), c'est POST /api/watchlist/ qui est documente ; chemins reels /api/admin/reset-beatport et /api/admin/artists/backfill-multi-artists
- [x] A5-15 : corriger les notes internes "Sentry non configure" (DSN pose, SDK initialise) + verifier la reception des evenements dans l'UI Sentry — reception CONFIRMEE le 2026-07-11 (evenements recus dans l'UI)
- [x] A7-11 : `server/api/scripts/README.md` — classer chaque script `rejouable` / `one-shot execute le X`
- [x] A7-12 : renommer `server/scripts/test_sources.py` -> `bootstrap_tidal_tokens.py` + docstring du role reel
- [x] A7-03 : deplacer `out/*.csv` vers `scripts/data/` (seed du graphe de genres — NE PAS supprimer) + `out/` au .gitignore

### Definition of Done

```bash
# Un tiers peut cloner, lire le README et lancer la stack sans instruction cassee
# Plus de router tracks ; worker/import_rekordbox.py archive
# .claude/commands/ versionne ; _design/ archive et deference de CLAUDE.md
```

---

## E1 — Re-scan enrichissement (backoff + budget nightly)

**Priorite : MOYEN**
**Estimation : 1 jour**
**Depend de : AU7 (IMPERATIF — filet de tests sur `enrichment.py` avant modification, meme contrainte que AU4). Recommande : execution avec ou juste apres AU4 (meme zone de code ; coordonner le budget avec A3-05 rate limiting partage).**
**Statut : TERMINE (2026-07-10) — code deploye et verifie en prod (0f12091), execute AVEC AU4 : migration 0033 (compteurs attempts + backfill 23885 dz / 30542 bp + index partiels ; numerotee 0033 car 0032 = A3-12), selection par tiers sous ENRICH_NIGHTLY_BUDGET (defaut 6000, non pose dans le .env), increment uniquement sur recherche aboutie (distinction A3-04 preservee), garde 24h inline etendue a radar.py en plus de sets.py ; preuve nightly attendue le 2026-07-11 matin (sweep Beatport sans SoftTimeLimitExceeded)**
**Origine : analyse prod du 2026-07-10 (saturation `enrich_catalog_beatport` + population not-found abandonnee) — hors perimetre audit 2026-07.**

### Objectif

Remplacer la politique "une recherche a vie" de l'enrichissement (Deezer + Beatport) par un re-scan borne avec backoff, et borner la duree des sweeps nightly. Deux problemes symetriques observes en prod :

1. **Abandon definitif** : un track non trouve est marque `searched_at` et n'est JAMAIS re-cherche. Or les tracks detectees dans les sets DJ sont souvent des promos/unreleased qui sortent sur Beatport des semaines plus tard — la population qui a le plus besoin d'un re-check est precisement celle qu'on abandonne, alors que Beatport est l'autorite canonique BPM/key (principe 3 des Data Authority Principles).
2. **Saturation du sweep** : aucune borne de volume par nuit. Avec le backfill C6.a.1 (500 sets/j), le sweep Beatport traite ~6 500 tracks/nuit et depasse son `soft_time_limit` de 7h — SoftTimeLimitExceeded + retry quasi quotidiens (les retries Celery servent de mecanisme de fonctionnement normal).

### Constats (mesures prod 2026-07-10)

- 2 844 tracks Beatport not-found abandonnees (croissance ~600-1000/j pendant le backfill), 1 537 cote Deezer
- Sweep du 2026-07-10 : 6 580 tracks, 7h de run a rythme constant (~3.8s/track = rate limiter 0.66 req/s x ~2.5 req/track), soft limit atteint a ~530 tracks de la fin
- Pipeline inline `resolve_set_tracks` SANS garde `searched_at` (`tasks/sets.py:156-165`) : re-cherche tout track sans `beatport_id` reapparaissant dans un set importe — retry accidentel non borne + re-recherches redondantes avec le sweep (~440 occurrences mesurees)

### Design

Selection par tiers sous un budget global par nuit (env `ENRICH_NIGHTLY_BUDGET`, defaut 6000 ~= 6h20 Beatport, sous le soft limit 7h). Le budget est un PLAFOND (nouveaux + retries confondus), pas un ajout au flux :

1. Jamais cherches (`searched_at IS NULL`), tries du plus RECENT au plus ancien — les tracks fraiches passent devant la queue historique du backfill
2. 1 tentative et `searched_at` > 30 j
3. 2 tentatives et `searched_at` > 90 j
4. 3 tentatives = abandon definitif (population morte plafonnee, pas de re-scan perpetuel)

Les retries ne consomment que le budget restant apres les nouveaux : pendant les nuits chargees du backfill ils attendent, ils rattrapent quand ca se calme. Le delai de 30 j rend le deploiement neutre le jour J. Seuils 30/90/3 en code (ajustables sans migration).

### Taches

- [x] Migration 0032 (additive) : `catalog.beatport_search_attempts` + `catalog.deezer_search_attempts` (SMALLINT NOT NULL DEFAULT 0) + backfill `attempts=1 WHERE searched_at IS NOT NULL` + index partiels `(beatport_searched_at) WHERE beatport_id IS NULL` (idem Deezer)
- [x] Modele `models/catalog.py` : 2 colonnes + index (autogenerate a blanc = diff vide)
- [x] `tasks/catalog.py` : les 2 requetes sweep (Deezer + Beatport) — WHERE 3 tiers + ORDER BY priorite + LIMIT budget
- [x] `enrichment.py` : incrementer `attempts` aux 2 points qui posent `searched_at` — CONSERVER la distinction A3-04 (echec HTTP != not found : pas de searched_at ni d'increment sur erreur reseau)
- [x] `tasks/sets.py` : garde `searched_at IS NULL OR searched_at < now() - 24h` sur les selections inline `dz_entries` / `bp_entries`
- [x] Tests : selection par tiers, increment du compteur, garde inline, respect du budget (s'appuie sur le filet AU7)
- [x] `/schema_doc` apres le changement de modele
- [ ] Hors scope (note pour plus tard) : bouton admin "forcer re-scan" (reset `searched_at` + `attempts`) — pattern existant dans `artist_service.py:606`

### Boutons de reglage lies (pas dans ce chantier)

| Bouton | Effet |
|---|---|
| `ENRICH_NIGHTLY_BUDGET` (E1) | Plafond de duree du sweep ; a baisser apres la fin de la vague backfill |
| `TRACKID_BACKFILL_SETS_PER_DAY` (C6.a.1) | Flux entrant ; 500 -> 400 aligne le flux sur le budget si les nuits de 6h20 genent encore |

### Definition of Done

```bash
# Sweep Beatport nightly borne : duree <= ~6h30, plus de SoftTimeLimitExceeded recurrent
# Track not-found re-eligible a +30j puis +90j, abandonne apres 3 tentatives
# resolve_set_tracks ne re-cherche plus un track deja cherche il y a < 24h
# alembic autogenerate a blanc = diff vide ; database-schema.md regenere
```

---

## F5 — Import manuel (recherche externe)

**Priorite : MOYEN**
**Estimation : 2-3 jours**
**Depend de : rien (APIs Deezer/TIDAL deja accessibles)**
**Statut : TERMINE (2026-07-12) — deploye et verifie en prod (commit 001d3d5). GET /api/search/external (Deezer+TIDAL, dedup ISRC, flag catalog_id, degradation gracieuse TIDAL) + POST /api/catalog/import (deezer_id|tidal_id, get_or_create_catalog, scope=shared, liaison artiste async, dedup) + modal ExternalImportModal.vue + declencheur CatalogView + CSP img-src TIDAL (resources.tidal.com). Aucune migration. Checklist humaine validee (import Deezer+TIDAL, dedup, vignettes TIDAL). Anomalie deploiement : nginx non recree quand seul le template change → restart manuel effectue (pitfall a surveiller).**

### Objectif

Permettre a tout utilisateur connecte d'ajouter un track au catalog via une recherche sur les sources externes (Deezer, TIDAL). Aujourd'hui les tracks n'entrent que par import en masse (Rekordbox XML, crawl playlists, import sets TrackID) — aucun moyen d'ajouter un son a la main.

### Faisabilite technique

| Source | Recherche | Auth | ISRC | Statut |
|--------|-----------|------|------|--------|
| **Deezer** | `search_deezer()` dans `deezer_enrich.py` | Aucune (API publique) | Oui | Pret a l'emploi |
| **TIDAL** | `tidalapi.session.search()` | OAuth device flow (tokens deja en Redis) | Oui | Trivial a ajouter |
| **Spotify** | Pas de search dans `spotifyscraper` | — | Non | Pas faisable |

### F5.a — Backend : endpoint recherche externe

- [x] `GET /api/search/external?q=...` : recherche parallele Deezer + TIDAL
- [x] Resultats fusionnes, dedupliques par ISRC (priorite Deezer si doublon)
- [x] Rate limiting Deezer (0.12s entre requetes, deja en place dans `deezer_enrich.py`)
- [x] Indiquer dans la reponse si le track existe deja dans le catalog (`catalog_id` si match ISRC/normalized_key)

### F5.b — Backend : endpoint import

- [x] `POST /api/catalog/import` : prend un `deezer_id` ou `tidal_id`
- [x] Enrichissement via `deezer_enrich.py` (flow existant : artwork, ISRC, duration, etc.)
- [x] Scope `shared` (source officielle = match confirme)
- [x] Dedup : verifier ISRC / `normalized_key` avant insertion, retourner l'entree existante si doublon
- [x] Creation artiste(s) via le flow existant (`get_or_create_artist`)

### F5.c — Frontend : barre de recherche + import

- [x] UI de recherche (vue dediee ou modale depuis le header)
- [x] Affichage resultats : artwork, titre, artiste, source (badge Deezer/TIDAL)
- [x] Badge "Deja dans le catalog" si le track existe
- [x] Bouton "Importer" par resultat, feedback immediat (track ajoutee, lien vers la fiche catalog)

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
**Statut : EN COURS (reliquat technique clos 2026-07-12 ; ouverture = decision produit William) — etancheite scope prive LIVREE et verifiee (commit 314763b, /deploy_verify SAIN) : predicat `catalog_visible()` / `catalog_visible_sql()` applique a TOUS les read-paths catalog (browse, detail, preview-url, avis, search, detail artiste, genre, similarite, radar/trends, watchlist, collections). DECISIONS PRODUIT divergeant du perimetre C3 initial : fermeture des GET publics ECARTEE (acces invite conserve — la decouverte reste ouverte) + guest cap conserve ; protection `/storage/*` DIFFEREE (documentee comme risque connu, pochettes seules, `<img>` ne porte pas de Bearer). RESIDUS assumes : comptes agreges genre/artiste + tracklist de set non filtres (non identifiants). C3.b enrichissement private CLOS (2026-07-12, commit f8b43c0, /deploy_verify SAIN) : promotion Beatport livree + rattrapage prod (4 promues, 3 faux positifs du matcher Beatport ecartes). Onboarding C3.c acte suffisant (Hub existant). C3.b etancheite import multi-user LIVREE (2026-07-12) : sur collision `normalized_key` avec le prive d'un autre user, l'importeur est lie via `user_track` a la ligne existante et la voit par la nouvelle clause `user_track` de `catalog_visible()` — la ligne d'autrui n'est JAMAIS promue ni mutee (design « promotion a la collision » rejete en review : fuite cross-user vers invites + tous les users). Funnel match ambigu OK par construction (jamais de promotion sur collision de nom). C3.a fermeture GET + guest cap ECARTEES, /storage DIFFERE (decisions produit). Test e2e multi-user reel VERIFIE EN PROD (2026-07-12, compte B user 7 en collision avec la ligne privee 7402 : ligne d'autrui intacte, user_track cree, 0 fuite) : reliquat technique C3 CLOS. Declenchement de l'ouverture = decision de William.**

**Renvois audit 2026-07** (voir `docs/audit_2026-07/CONSOLIDATED.md` + `DECISIONS.md`) :
- C3.a in_lib `GET /sets/{id}` : fixe en **AU1** (M1/A1-03) — la tache ci-dessous devient une simple verification.
- C3.b : diagnostic corrige par l'audit (A3-01, R6) — les tracks private SONT enrichies (aucun filtre scope dans les queries), c'est la promotion `private -> shared` qui manquait dans le pipeline async. Fix + rattrapage des 235 lignes en **AU1**. Reste a C3.b : le test de bout en bout multi-user.
- C3.c Sentry : deja configure en prod (A5-15 — DSN pose, SDK initialise API + workers). Reception des evenements verifiee dans l'UI le 2026-07-11 (AU8) — plus rien a faire.
- A reprendre dans ce chantier : A2-11 (4 FK restantes sans index, a reevaluer avec la volumetrie), A2-14 (index `radar_trends (family, rank_in_family)` + `(rank_global)` — endpoint public le plus expose), A6-14 (branches d'echec OAuth + lifecycle radar en CI PG, opportuniste).
- **Condition Q4** : si le repo est un jour ouvert (public ou contributeurs), la purge `git filter-repo` de l'historique (tokens TIDAL, A6-01) devient un prerequis BLOQUANT de cette ouverture.

### Objectif

Fermer l'application et garantir l'etancheite entre users. Regroupe le reliquat Phase 6, la verification Phase 7, et les prerequis d'accueil.

### C3.a — Fermeture (reliquat Phase 6, dimensionne par l'audit)

L'audit invalide le "normalement deja traite" : le middleware laisse public tout GET sur catalog/artists/sets/genres/search/taxonomy.

- [ ] ~~Basculer les GET publics en auth obligatoire~~ — ECARTEE (decision produit William, 2026-07-12) : l'acces invite reste ouvert, la decouverte reste publique ; l'etancheite est assuree par le scope (`catalog_visible`), pas par un mur d'auth
- [x] **Filtrer `scope=private` d'autrui sur tous les endpoints catalog** (browse, detail, search, stats genres) : bloquant, sans ca la politique de scope est violee des le browse — FAIT (2026-07-12, commit 314763b : helper `catalog_visible()`, etendu a similarite/radar-trends/watchlist/collections)
- [x] `GET /api/sets/{id}` : filtre `user_id` sur le check in_lib (`sets.py:281`) — FAIT en AU1 (verifie 2026-07-12)
- [ ] `/storage/*` : proteger les artworks (auth au niveau Nginx via `auth_request` vers l'API, ou URLs signees MinIO) : IDs sequentiels enumerables aujourd'hui — DIFFERE (risque connu documente : pochettes seules, `<img>` ne porte pas de Bearer ; travail futur)
- [ ] ~~Supprimer le guest cap~~ — ECARTEE (decision produit, 2026-07-12) : guest cap conserve, l'acces invite reste

### C3.b — Import multi-user (verification Phase 7, audit largement OK)

L'audit confirme : chaine user_id propre de bout en bout, lock Redis per-user, champ scope actif, et la promotion private -> shared via enrichissement Deezer **deja implementee** (`deezer_enrich.py`). La politique decidee est a ~80% en place.

Reste :
- [x] **Corriger le perimetre d'enrichissement** : le check SQL montre 0/259 tracks private enrichies, preuve que les tasks d'enrichissement excluent `scope=private`. La mecanique de promotion existe (`deezer_enrich.py`) mais ne s'execute jamais sur les private. Inclure explicitement le scope private dans les passes d'enrichissement (tache Celery Beat dediee ou extension de `enrich_catalog`), sinon une track mal taguee ou un unreleased qui sort officiellement reste private a vie — SANS OBJET (2026-07-12) : diagnostic PERIME depuis AU4/E1. Plus aucun chemin d'enrichissement ne filtre le scope (sweep nightly `select_enrich_candidates`, inline sets/radar selectionnent sur `{source}_id IS NULL` seul) ; la promotion Deezer existait deja. Aucun code de selection a changer
- [x] Etendre le test d'admission a Beatport (pas seulement Deezer) si pertinent — FAIT (2026-07-12, commit f8b43c0) : promotion `private -> shared` ajoutee sur match Beatport dans `enrich_from_beatport` (miroir de Deezer) + script `promote_private_shared` etendu aux deux sources ; rattrapage prod = 4 promues, 3 faux positifs neutralises (meme `beatport_id` colle a 3 bootlegs par le matcher)
- [x] **Etancheite import multi-user (fix emergent de la cloture C3.b, 2026-07-12)** : l'import RB liait le `user_track` de l'importeur a la ligne privee d'un AUTRE user (dedup `normalized_key` globalement UNIQUE) qui restait invisible pour lui — trou de bibliotheque. Corrige au read-layer : `catalog_visible()` / `catalog_visible_sql()` gagnent une clause `EXISTS(user_track du viewer)` ; l'importeur voit la ligne via son propre user_track, la ligne d'autrui reste `private`/`owner` INTACTE. Design alternatif « promotion a shared sur collision » REJETE en review (aurait rendu le prive d'autrui visible aux invites + tous les users sur simple collision de nom — l'inverse de l'etancheite C3). Tests : test_import_rb_scope.py + test_scope_visibility.py, suite 1114 verte
- [x] Test reel de bout en bout : import d'une deuxieme bibliotheque Rekordbox — FAIT et VERIFIE EN PROD (2026-07-12) : import depuis le compte B (user 7) d'un XML en collision avec la ligne privee `House 1` (id 7402, owner=William/user 2). Resultat DB : ligne 7402 INCHANGEE (`private`/owner 2, aucune promotion ni flip), `user_track (user 7 -> catalog 7402)` cree (B voit le track via la clause user_track, invite + tiers ne le voient pas), track inconnu cree `private`/owner=B (funnel OK), aucun doublon catalog (normalized_key UNIQUE respecte)
- [x] Verifier le comportement funnel en cas de match ambigu : rester private — FAIT (2026-07-12) : l'import RB dedup exact `normalized_key` uniquement (pas de fuzzy) ; une collision inter-user ne promeut ni ne mute la ligne d'autrui. « En cas de doute on ne matche pas » = jamais de promotion sur collision de nom

### C3.c — Accueil

- [x] Onboarding minimal : que voit un nouvel utilisateur sans bibliotheque ? (reponse : le catalogue shared + le trend par famille = la reco par defaut, d'ou C1 avant C3) — ACTE SUFFISANT (2026-07-12, decision William) : le Hub existant (recherche + genres populaires + trend par famille + nouveautes des artistes suivis) fait office d'onboarding ; zero code
- [x] ~~Frontend build statique de prod~~ — FAIT (Nginx static build, voir reliquats)
- [x] ~~Sentry DSN configure~~ — FAIT (A5-15 : DSN pose en prod + SDK initialise cote API et workers). Reste : verifier la reception effective des evenements dans l'UI Sentry (action humaine)

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
**Statut : A FAIRE (partiel — N1.b execute via AU1 le 2026-07-09 ; reste N1.a residus auth email/password)**

### Objectif

Supprimer le code mort et les residus de fonctionnalites supprimees. Reduction de surface d'attaque + coherence avec les conventions actuelles.

### N1.a — Residus auth email/password

L'auth est Google OAuth only depuis F3, mais des restes de l'ancien login email/password subsistent probablement :

- [ ] Routes mortes dans `server/api/routers/auth.py` (login/register email/password)
- [ ] Variables d'env avec defaults liees a l'ancien flow
- [ ] Colonne `hashed_password` eventuelle sur `users` (verifier `models.py`, prevoir migration de drop si elle existe)
- [ ] Tests obsoletes couvrant l'ancien flow

### N1.b — Suppression TagsView

> **Absorbe par AU1** (M7 : TagsView + AppearRow, audit 2026-07). Conserve ici pour trace jusqu'a execution d'AU1.

TagsView est une vue morte, `/tags` redirige vers `/genres`.

- [x] Supprimer `TagsView.vue` du frontend
- [x] Supprimer la route `/tags` du router Vue

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
| Tests import RB + branches OAuth (A6-08, A6-14 — arbitrage Q7) | Opportuniste, au fil des chantiers touchant ces zones |
| Batch upsert import RB (A2-13) | Opportuniste, meme zone que A6-08 |
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
| AU1 | Quick Wins audit | Immediat | - |
| AU2 | Sauvegardes & deploiement | Apres AU1 | AU1 (cron backup) |
| AU3 | Integrite donnees (migration 0031) | Apres AU2 | Ordre interne : 0031 -> A2-04 -> /schema_doc -> doc |
| AU7 | Dette de tests (enrich + auth) | AVANT ou AVEC AU4 | - |
| AU4 | Robustesse workers | Apres AU7 (filet enrichissement) | AU7 |
| AU5 | Couche service backend | Apres AU1 | AU1 (A1-02) |
| AU6 | Dette frontend | Apres AU5 (ou parallele) | - |
| AU8 | Hygiene repo & documentation | Fin de serie | Decisions Q2/Q5/Q6 (actees) |
| E1 | Re-scan enrichissement (backoff + budget nightly) | Apres AU7, avec ou juste apres AU4 | AU7 (filet de tests enrichment) |
| C3 | Ouverture (fermeture app + import multi-user + accueil) | Ta decision d'inviter | H0 (FAIT) + C1 + serie AU + idealement C6 |
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

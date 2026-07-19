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
> **Derniere mise a jour** : 2026-07-13 (C6.c v2 deploye — les releases Deezer des artistes suivis sont desormais crawlees DANS le catalog : album eclate en tracklist, 1 `artist_activity` par titre lie a une entree catalog `scope='shared'` (cover/preview/artistes/release_date), rendu comme un track normal dans la shelf "Nouveautes" du Hub ; fallback lien externe si le fetch `/track` echoue, cap 40 titres/release, aucune migration. Raffinement de C6.c (deja TERMINE le 2026-07-12), commit 245c1cc, /deploy_verify SAIN — ne rouvre pas le chantier. Etat global : series AU + C6 + F5 + C3 + C4 + N1 TERMINE. **Mise a jour 2026-07-13 (2)** : les deux derniers chantiers, C5 (Collections v2) et D4 (Pages Detail), sont desormais STANDALONE et prets a demarrer — retrait des statuts 'apres ouverture' (C5) et 'bloque briefs' (D4). Plus aucune dependance ni condition bloquante : leur lancement est un choix de priorite (William), pas un blocage. D4 = a demarrer en binome avec Claude Design (briefs Track/Playlist co-produits dans le chantier) ; C5 = gros refacto de la feature Collections.) **Mise a jour 2026-07-14** : ajout de 4 nouveaux items backlog issus d'une revue produit/technique (aucun statut de chantier existant modifie) — **P2** (lot correctifs UX/admin : affichage sortie album Hub, loading "Pour toi", compteurs vrai total x3, Beatport skip-lock, chips trend familles vides), **N2** (fix split artiste multi + separateur "|"), **C7** (entite Album + M2M catalog_albums), **C8** (fiabilite des sets TrackID : flag hidden + exclusion des calculs de proximite). Deux divergences CLAUDE.md corrigees le meme jour : la similarite consomme les sets (via `_load_set_map`, PAS catalog-only) ; commentaire `external_id` dans `models/artist.py` (track id Deezer depuis C6.c v2, plus album id). **Mise a jour 2026-07-16** : **N2** et **P2** TERMINES (commit d11f28e + follow-ups, deployes, /deploy_verify SAIN). Le **fix durable pooling de C4** est LIVRE (commits 58c91b0 + 3fae063) : contexte de similarite cache in-process + candidate pooling (pool construit 1x, scoring en memoire) + `_load_set_map` roots-only ; optimisation PURE (byte-identique, ancree par test golden), reco a froid mesuree ~60s -> ~6.6s en prod, SEED_CAP reste a 12. Corriges hors chantier le meme jour (bugs prod emergents, pas de nouveau chantier) : pillar-count `list_artists` via sous-requete (cap asyncpg 32767 bind params sur GET /api/artists une fois la table artistes > 32767 lignes, commit 383588d) et le separateur "|" sans espaces "A|B". **Mise a jour 2026-07-17** : **D4 passe EN COURS** — page 1 (Track Detail) TERMINEE et deployee (0c47a8c, /deploy_verify SAIN, checklist William validee) : 4 composants transverses (Artwork/TrackCard/ScoreRing/PlatformLink, logos placeholders → reliquat) + refonte TrackDetailView. Restent Playlist Detail, verif FIX Artist/Set, Admin Vague 5. **Mise a jour 2026-07-17 (2)** : page 2 (Playlist Detail) TERMINEE et deployee (ef8505f + FIX bcb3845, /deploy_verify SAIN, checklist validee, revue design soldee) — lot 0 back (top_artists/top_genres/in_lib/artists[] sur GET /api/watchlist/{id}, perimetre catalog_visible) + extension additive TrackCard (duree + artistes cliquables) + refonte PlaylistDetailView (bouton Suivre retire de l'UI). La contradiction back de la fiche playlist-detail est tranchee et livree. Restent verif FIX Artist/Set + Admin Vague 5. **Mise a jour 2026-07-20** : page 3 (Set Detail) TERMINEE et deployee (41e9315 + FIX ef7117f, /deploy_verify SAIN x2, checklist validee, revue design FIX round unique solde 5/2/1) — lot 0 back (bpm/key/duree tracklist + top_genres[] perimetre catalog_visible + NOUVEL endpoint GET /api/sets/{id}/similar, moteur C2 agrege niveau set, cache Redis 6h + seed cap 12 apres mesure 21s → 0,12s chaud) + extension TrackCard « set » (position/timecode/etats) + ScoreRing mode pct + NOUVEAU SetCard (40 composants) + refonte SetDetailView. La moitie Set de « verif FIX Artist/Set » est soldee par la refonte ; restent verif FIX Artist Detail + Admin Vague 5. Nettoyage doc : les mentions C7.b/C8.b du double-comptage `_load_set_map` annotees DEJA CORRIGE (roots-only, 2026-07-16).

---

## Vision cible

Avant l'ouverture aux amis (5-10 DJs), Diggy doit offrir :
1. Une experience mobile utilisable (ils seront sur telephone)
2. Une recommandation de tendance solide, decorrellee des likes (offre par defaut des nouveaux arrivants sans historique)
3. Un moteur de similarite fonctionnel (socle de toute recommandation, avec ou sans user)
4. Une application fermee et etanche entre utilisateurs (auth obligatoire, scopes respectes)

Apres l'ouverture : la recommandation personnalisee (croisement similarite x likes), utile des un seul user et enrichie par chaque nouvel utilisateur.

**Sequence verrouillee (historique — soldee)** : ~~C0 -> R1 -> C1 -> C2 -> H0 + P1 -> F5 + C6 -> serie AU -> C3 -> C4~~ (TOUT TERMINE). Restent **C5** et **D4** : hors sequence, deux chantiers STANDALONE sans ordre impose ni dependance bloquante, lancables au choix.

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
 C3   Ouverture aux amis                    MOYEN       5-7 jours    TERMINE (2026-07-13 ; ouverture effective = decision William)
 C4   Reco personnalisee                    BAS         3-5 jours    TERMINE (2026-07-13)
 C5   Collections v2 (polymorphe + dossiers) BAS       3-5 jours    A FAIRE — standalone
 D4   Pages Detail (Vague 3)               BAS         5-7 jours    EN COURS — Track + Playlist + Set Detail TERMINES (2026-07-19)
 N1   Nettoyage residus                     BAS         1 jour       TERMINE (2026-07-13)
 P2   Correctifs UX/admin (revue 07-14)     MOYEN       1 jour       TERMINE (2026-07-16)
 N2   Split artiste multi + separateur "|"  MOYEN       1-2 jours    TERMINE (2026-07-16)
 C7   Entite Album (M2M catalog_albums)     BAS         5-7 jours    A FAIRE
 C8   Fiabilite des sets TrackID            BAS         3-4 jours    A FAIRE
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
 N1   Nettoyage residus                 TERMINE (2026-07-13)
 C3   Ouverture aux amis              TERMINE (2026-07-13 ; ouverture = decision William)
 C4   Reco personnalisee              TERMINE (2026-07-13 ; fix durable pooling LIVRE 2026-07-16)
 P2   Correctifs UX/admin (revue 07-14) TERMINE (2026-07-16)
 N2   Split artiste multi + separateur "|" TERMINE (2026-07-16)
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
C5 ─────────> Rien — C1 (TERMINE). Refacto standalone, pret a demarrer, aucun blocage
D4 ─────────> Rien — D5 (TERMINE). Standalone, briefs Track/Playlist co-produits en binome avec Claude Design
N1 ─────────> Rien (parallelisable avec tout, priorite basse)

--- revue 2026-07-14 (nouveaux items backlog) ---
P2 ─────────> Rien (lot correctifs front ; P2.a partage la surface Hub avec C7, non bloquant)
N2 ─────────> Rien
C7 ─────────> Rien de bloquant — complementaire de P2.a (Album justifie par reco/linking, pas l'affichage)
C8 ─────────> Rien — touche le moteur de similarite (_load_set_map), pas qu'un filtre d'affichage
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
**Statut : TERMINE (2026-07-12) — C6.0 + C6.1 + C6.a (2026-07-07 / 2026-07-08) ; C6.b + C6.c (2026-07-11, commit e976e0d) ; C6.e (2026-07-12, commit a65b9f3, deploye et verifie — premier run du crawl universel CONTROLE dans les crawl-logs le 2026-07-12 : SAIN, 10/10 taches success 0 erreur. 56 playlists considerees, dispatched 7 = uniquement celles reellement modifiees (court-circuit `has_changed`), skipped_cadence 2, dropped_by_cap 0 ; le "~40+ attendu" etait une surestimation ignorant `has_changed`. recrawl_incomplete_sets finalized_complete 2585 / crawled 84 ; check_followed_artists artists_checked 2 + 1 release au feed. is_initial_detection pas encore exerce (aucune dormante >30j)). C6.c v2 (2026-07-13, commit 245c1cc, deploye, /deploy_verify SAIN) : les releases Deezer des artistes suivis sont desormais crawlees DANS le catalog — album eclate en tracklist, 1 `artist_activity` par titre (external_id = track id Deezer) lie a une entree `scope='shared'` (cover/preview/artistes/release_date), rendu comme un track normal dans la shelf "Nouveautes" du Hub ; fallback lien externe si le fetch `/track` echoue, cap 40 titres/release, carte album legacy self-healed, aucune migration ; raffinement de C6.c, ne rouvre pas le chantier. Seul reliquat : C6.d (Soundcloud), reporte**
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
- [x] Env var `TRACKID_BACKFILL_SETS_PER_DAY` (defaut : 500, releve a 1000 le 2026-07-16) + `TRACKID_BACKFILL_MIN_DATE` (defaut : today - 730j)
- [x] Condition d'arret : curseur < min_date ou reponse vide → marquer backfill termine dans Redis
- [x] Log du curseur courant a chaque run (monitoring progression)

> Backfill : CONSTATE en prod (2026-07-16) : stall total depuis ~mi-juin — soft limit global 1800s + `autoretry_for=(Exception,)` (4 timeouts/nuit puis DLQ, curseur fige a 2026-06-10) + curseur date-only qui sautait definitivement les sets same-day aux frontieres de batch (~10-20% de l'historique) + re-paging integral croissant. CORRIGE par deux fixes deployes le 2026-07-16 : c52fcc4 (limites propres 3600/3900, curseur incremental, catch SoftTimeLimitExceeded, lock Redis, no autoretry) + 56c17b6 (curseur addedOn ISO8601 complet, reprise pagination via `trackid_backfill_page` persiste sur batch complet uniquement, budget 1000/j). Curseur reinitialise a `2026-06-15T00:00:00` pour re-balayer la fenetre trouee 10-15 juin (idempotent).
> **CHECK 1er run FAIT le 2026-07-17 — VERT** : run nuit 16→17/07 `succeeded in 2751s (~46 min)`, `{status:running, imported:999, skipped:1, new_cursor:2026-06-10T05:02:35.549329Z, page:340}`. Les 4 points passent : curseur timestamp complet et < 2026-06-15 (descendu de 06-15 reset → 06-10, ~5j d'historique = re-balayage de la fenetre trouee 10-15 juin OK), `trackid_backfill_page`=340 (entier), soft-limit 3600s non atteint, DLQ `dead_letter` vide. Aparte : 1 set (367741) skip sur `httpx.ReadError` transitoire (catche per-set, non bloquant) ; `resolve_set_tracks` a touche son soft-limit 7200s cette nuit (attendu apres 999 nouveaux sets, lock a bloque le doublon) — a re-regarder Nuit 2.
> **CHECK Nuit 2 FAIT le 2026-07-19 — VERT (2 nuits verifiees).** Nuit 17→18 : `1761s (~29 min)`, imported 1000, page 407, cursor 2026-06-06 ; Nuit 18→19 : `1800s (~30 min)`, imported 1000, page 482, cursor 2026-06-01. Taxe de re-paging MORTE : `page` monte proprement 340→407→482 (PAS de reset a 0 puis re-climb ; la prediction "page ~340 stable" etait fausse — l'offset descend le flux global, le bon signal est "monte sans reset"), duree plate = travail utile pur, soft-limit 3600s jamais touche, DLQ `dead_letter` vide. **Backfill C6.a.1 CLOS VERT.** En revanche `resolve_set_tracks` a tape son soft-limit 7200s les DEUX nuits (13320 puis 19336 resolus) — la prediction qu'il redescende etait fausse, c'etait chronique (enrichissement Deezer/Beatport inline) → traite par C6.a.2 ci-dessous.

#### C6.a.2 — Debit d'enrichissement Beatport (2e passe) — DEPLOYE le 2026-07-19, SUIVI en cours

Mesure prod 2026-07-19 : backlog Beatport actif **33 084** (jamais-cherche **12 359**, tous < 2 j = lag stable ~2 j, PAS en fuite), Deezer sain (0 jamais-cherche). Plafond Beatport ~6000/nuit = rate scrape **0,66 req/s** (pas d'API, throttle anti-ban) x fenetre ~7h ; **~860 tracks/h**, ~2,7 req/track (les 24% d'introuvables partent en fallback release a 3-4 req). Stock eligible/nuit borne (~12k tier-1 ; les 20,7k tier-2 verrouilles 30j). Taux de trouvaille 1er essai = **76%**.

DEPLOYE le 2026-07-19 (f4c7f57 + a5b1859, deploy_verify SAIN — budget prod verifie `deezer 15000 / beatport 6000`, 2e passe presente dans le beat) : (1) `resolve_set_tracks` decouple = liage seul (plus d'enrichissement inline, cf. C6.a.1) ; (2) **budget par-source** Deezer 15000 / Beatport 6000 (compense le decouplage cote Deezer, qui plafonnait Deezer a 6000) ; (3) **2e passe `enrich_catalog_beatport` a 15h** (06h + 15h) → capacite ~12000/nuit au meme rate. Objectif : capacite > inflow → jamais-cherche **decroit vers 0** et n'augmente plus.

A CHECKER chaque jour (`enrich_beatport` dans `/api/admin/crawl-logs` + requete backlog `beatport_id IS NULL AND attempts=0`) :
- passe 1 (06h) : `enriched` / `not_found` / duree
- passe 2 (15h) : `enriched` / `not_found` / duree — **ou tourne a vide** (= 1 passe suffit, l'inflow tient dans 6000)
- backlog jamais-cherche : tendance J+1 → J+3 (doit baisser)

DECISION apres ~3-5 j : passe 2 trouve regulierement du travail ET backlog ↓ → garder ; passe 2 a vide → revenir a 1 passe. Bonus efficacite en reserve si besoin de plus : fallback release plus malin (couper le cout des introuvables) + backoff tier-2 allonge (30j → 60-90j).
- [ ] CHECK J+1 (20/07) : passe1=… passe2=… backlog=…
- [ ] CHECK J+2 (21/07) : passe1=… passe2=… backlog=…
- [ ] CHECK J+3 (22/07) : passe1=… passe2=… backlog=…

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
**Statut : TERMINE (2026-07-13 — reliquat technique CLOS, protection /storage ECARTEE ce jour ; ouverture effective = decision produit William) — etancheite scope prive LIVREE et verifiee (commit 314763b, /deploy_verify SAIN) : predicat `catalog_visible()` / `catalog_visible_sql()` applique a TOUS les read-paths catalog (browse, detail, preview-url, avis, search, detail artiste, genre, similarite, radar/trends, watchlist, collections). DECISIONS PRODUIT divergeant du perimetre C3 initial : fermeture des GET publics ECARTEE (acces invite conserve — la decouverte reste ouverte) + guest cap conserve ; protection `/storage/*` ECARTEE le 2026-07-13 (risque assume, non bloquant : pochettes seules, l'enumeration revele l'existence pas la donnee privee, `<img>` ne porte pas de Bearer). RESIDUS assumes : comptes agreges genre/artiste + tracklist de set non filtres (non identifiants). C3.b enrichissement private CLOS (2026-07-12, commit f8b43c0, /deploy_verify SAIN) : promotion Beatport livree + rattrapage prod (4 promues, 3 faux positifs du matcher Beatport ecartes). Onboarding C3.c acte suffisant (Hub existant). C3.b etancheite import multi-user LIVREE (2026-07-12) : sur collision `normalized_key` avec le prive d'un autre user, l'importeur est lie via `user_track` a la ligne existante et la voit par la nouvelle clause `user_track` de `catalog_visible()` — la ligne d'autrui n'est JAMAIS promue ni mutee (design « promotion a la collision » rejete en review : fuite cross-user vers invites + tous les users). Funnel match ambigu OK par construction (jamais de promotion sur collision de nom). C3.a fermeture GET + guest cap + protection /storage ECARTEES (decisions produit). Test e2e multi-user reel VERIFIE EN PROD (2026-07-12, compte B user 7 en collision avec la ligne privee 7402 : ligne d'autrui intacte, user_track cree, 0 fuite) : reliquat technique C3 CLOS. Declenchement de l'ouverture = decision de William.**

**Renvois audit 2026-07** (voir `docs/audit_2026-07/CONSOLIDATED.md` + `DECISIONS.md`) :
- C3.a in_lib `GET /sets/{id}` : fixe en **AU1** (M1/A1-03) — la tache ci-dessous devient une simple verification.
- C3.b : diagnostic corrige par l'audit (A3-01, R6) — les tracks private SONT enrichies (aucun filtre scope dans les queries), c'est la promotion `private -> shared` qui manquait dans le pipeline async. Fix + rattrapage des 235 lignes en **AU1**. Reste a C3.b : le test de bout en bout multi-user.
- C3.c Sentry : deja configure en prod (A5-15 — DSN pose, SDK initialise API + workers). Reception des evenements verifiee dans l'UI le 2026-07-11 (AU8) — plus rien a faire.
- Hardening non bloquant DEPLACE vers « Reliquats hors chantiers » (C3 clos sans eux, purement opportunistes) : A2-11 (4 FK restantes sans index, a reevaluer avec la volumetrie), A2-14 (index `radar_trends (family, rank_in_family)` + `(rank_global)`), A6-14 (branches d'echec OAuth + lifecycle radar en CI PG).
- **Condition Q4** : si le repo est un jour ouvert (public ou contributeurs), la purge `git filter-repo` de l'historique (tokens TIDAL, A6-01) devient un prerequis BLOQUANT de cette ouverture.

### Objectif

Fermer l'application et garantir l'etancheite entre users. Regroupe le reliquat Phase 6, la verification Phase 7, et les prerequis d'accueil.

### C3.a — Fermeture (reliquat Phase 6, dimensionne par l'audit)

L'audit invalide le "normalement deja traite" : le middleware laisse public tout GET sur catalog/artists/sets/genres/search/taxonomy.

- [ ] ~~Basculer les GET publics en auth obligatoire~~ — ECARTEE (decision produit William, 2026-07-12) : l'acces invite reste ouvert, la decouverte reste publique ; l'etancheite est assuree par le scope (`catalog_visible`), pas par un mur d'auth
- [x] **Filtrer `scope=private` d'autrui sur tous les endpoints catalog** (browse, detail, search, stats genres) : bloquant, sans ca la politique de scope est violee des le browse — FAIT (2026-07-12, commit 314763b : helper `catalog_visible()`, etendu a similarite/radar-trends/watchlist/collections)
- [x] `GET /api/sets/{id}` : filtre `user_id` sur le check in_lib (`sets.py:281`) — FAIT en AU1 (verifie 2026-07-12)
- [x] `/storage/*` : protection ECARTEE (decision produit William, 2026-07-13) — risque assume et non bloquant : pochettes seules, les IDs enumerables revelent l'existence d'une image, pas de donnee privee ; `<img>` ne porte pas de Bearer. Solutions futures possibles si ouverture large (`auth_request` Nginx ou URLs signees MinIO)
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
# Acces invite conserve (fermeture des GET publics ECARTEE, decision produit) ; etancheite garantie par le scope (catalog_visible)
# scope=private d'un autre user invisible dans catalog/search/genres
# /storage/* : protection ECARTEE (risque assume, decision produit 2026-07-13 — pochettes seules, non identifiant)
# Import d'une 2e lib Rekordbox : dedup OK, scopes OK
# Build frontend statique (pas Vite dev server)
```

---

## C4 — Recommandation personnalisee (apres ouverture)

**Priorite : BAS**
**Estimation : 3-5 jours**
**Depend de : C2 + C3**
**Statut : TERMINE (2026-07-13) — reco "Pour toi" livree, deployee, /deploy_verify SAIN (commit 7fd64c4 + hotfix hang CI 2b91bb4 + stop-gap 504 c288cc6). Calcul on-the-fly + cache Redis (pas de precalcul/table). Fix durable candidate pooling LIVRE le 2026-07-16 (commits 58c91b0 + 3fae063, /deploy_verify SAIN) : (1) load_similarity_context cache in-process (TTL 6h) — le contexte user/seed-agnostic n'est plus reconstruit a chaque requete ; (2) candidate pooling — pool candidats construit 1x (projection legere + genres/label precalcules) + scoring en memoire, plus les lignes ORM completes que pour les ~20 gagnants ; (3) _load_set_map roots-only (fin du double-comptage parents virtuels + enfants). Optimisation PURE (resultats byte-identiques, ancres par test golden). Mesure prod : reco a froid ~60s -> ~6.6s, endpoint /similar ~2.5s -> ~1.9s. SEED_CAP reste a 12. Precalcul nocturne non necessaire (garde en reserve).**

### Objectif

Croiser le moteur de similarite (C2) avec les likes (`user_opinions`). Utile des un seul user (toi), mais volontairement place apres l'ouverture : chaque nouvel utilisateur enrichit le signal.

- [x] Profil de gout par user : agregation des scores de similarite (C2) des tracks likees (penalisation des dislikees)
- [x] Reco = scoring C2 (metadonnees + co-occurrence) pondere par le profil, filtre par famille/BPM, excluant la lib existante
- [x] Surface : section "Pour toi" distincte de la section trend (les deux recos coexistent, decorrelees)
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
**Depend de : C1 (TERMINE) — aucune dependance bloquante**
**Statut : A FAIRE — pret a demarrer (STANDALONE). Gros refacto de la feature Collections (items polymorphes + dossiers). Aucune condition d'ouverture, aucun blocage. Declenchement = choix de priorite (William).**

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
**Depend de : D5 (composants partages) — TERMINE, aucune dependance bloquante**
**Statut : EN COURS — page 1 (Track Detail) TERMINEE (2026-07-17, commit 0c47a8c, deployee, /deploy_verify SAIN, checklist humaine validee). Livree via le handoff Claude Design `docs/refonte-ui/handoff-track-detail/` (round 2 acte dans la fiche `docs/refonte-ui/track-detail.md`) : 4 composants transverses crees (Artwork, TrackCard ligne, ScoreRing, PlatformLink — logos PLACEHOLDERS, reliquat roadmap) + refonte TrackDetailView (StatStrip supprimee, stats dans le hero, Decouverte avant « Ou on l'entend », troncatures, glyphes source, Rating retire de la page). +36 tests front (125 verts). Page 2 (Playlist Detail) TERMINEE (2026-07-17, commits ef8505f + FIX bcb3845, deployee, /deploy_verify SAIN, checklist humaine validee, revue design FIX round unique solde : 3 ecarts corriges, 1 clos non-ecart donnee, 1 rejete conforme au brief). La contradiction back de la fiche a ete TRANCHEE en pre-vol et LIVREE en lot 0 : `GET /api/watchlist/{id}` renvoie desormais top_artists/top_genres (caps 6/5, pct), in_lib et artists[] peuples, calcules sur le perimetre `catalog_visible` (etancheite C3) ; + extension ADDITIVE de TrackCard (duree + artistes cliquables, zero regression Track Detail) + refonte PlaylistDetailView (hero cover+infos, bloc « Dans cette playlist » enfin cable, bouton Suivre retire de l'UI — decision produit, mecanisme back conserve —, AdminCard en bas). +35 tests (pytest 1221, vitest 155). Page 3 (Set Detail) TERMINEE (2026-07-19, commits 41e9315 + FIX ef7117f, deployee, /deploy_verify SAIN x2, checklist humaine validee, revue design FIX round unique solde : 5 acceptes / 2 clos non-ecarts / 1 rejete conforme). Livree via le handoff `docs/refonte-ui/handoff-set-detail/` : lot 0 back (bpm/key/duree sur la tracklist, top_genres[] miroir playlist perimetre catalog_visible, NOUVEL endpoint `GET /api/sets/{id}/similar` — moteur C2 agrege au niveau set, cache Redis par (set_id, viewer) TTL 6h + seed cap 12 poses au FIX apres mesure prod 21s → 11,6s froid / 0,12s chaud) + extension ADDITIVE TrackCard « set » (position/timecode/etats id-unresolved, zero regression) + ScoreRing mode pct + NOUVEAU composant SetCard reutilisable (future liste /sets) + refonte SetDetailView (hero immersif floute, StatStrip/RingPct/blocs morts retires, AdminCard conservee). +29 pytest (1250), +66 vitest (221). La moitie « Set Detail » de la verif FIX est SOLDEE par la refonte complete. Restent : verif FIX Artist Detail, Admin (Vague 5).**

### Taches

- [ ] **Verifier FIX appliques** sur Artist Detail et Set Detail — moitie Set Detail SOLDEE par la refonte complete p.3 (2026-07-19) ; reste Artist Detail
- [x] **Track Detail** `/catalog/:id` (brief co-produit avec Claude Design) : Hero + StatStrip + blocs relationnels — TERMINE (2026-07-17, 0c47a8c) ; la StatStrip a finalement ete SUPPRIMEE (stats integrees au hero, decision round 2)
- [x] **Playlist Detail** `/playlists/:id` (brief co-produit avec Claude Design) : Hero square + StatStrip + table tracks — TERMINE (2026-07-17, ef8505f + FIX bcb3845) ; decisions handoff : hero finalement « cover + infos a cote » SANS StatStrip, table remplacee par des rangees TrackCard etendues
- [ ] **Vague 5 — Admin panel** `/admin` (brief co-produit avec Claude Design) : Refonte visuelle selon DA Wildflower

---

## N1 — Nettoyage residus

**Priorite : BAS**
**Estimation : 1 jour**
**Depend de : rien (parallelisable avec tout)**
**Statut : TERMINE (2026-07-13) — N1.b (TagsView) execute via AU1 le 2026-07-09 ; N1.a purge des residus de l'ancien flow auth email/password (deploye 4ccb916, /deploy_verify SAIN) : le coeur etait deja solde par F3 (routes login/register absentes de auth.py, colonne hashed_password droppee en migration 0024, aucune var d'env legacy) ; reliquat retire ce jour = 2 entrees RATE_LIMITS mortes (/api/auth/login + /api/auth/register), 2 tests obsoletes, dependance de test bcrypt**

### Objectif

Supprimer le code mort et les residus de fonctionnalites supprimees. Reduction de surface d'attaque + coherence avec les conventions actuelles.

### N1.a — Residus auth email/password

L'auth est Google OAuth only depuis F3, mais des restes de l'ancien login email/password subsistent probablement :

- [x] Routes mortes dans `server/api/routers/auth.py` (login/register email/password) — DEJA solde par F3 : `auth.py` est OAuth-only (login/callback/me), aucune route login/register
- [x] Variables d'env avec defaults liees a l'ancien flow — SANS OBJET : aucune var d'env legacy (SECRET_KEY -> JWT_SECRET deja fait en AU1)
- [x] Colonne `hashed_password` eventuelle sur `users` (verifier `models.py`, prevoir migration de drop si elle existe) — DEJA droppee par la migration 0024 (F3) ; absente de `models/user.py`, aucune nouvelle migration
- [x] Tests obsoletes couvrant l'ancien flow — FAIT (2026-07-13, commit 4ccb916) : reliquat reel retire = 2 entrees RATE_LIMITS mortes (/api/auth/login + /api/auth/register), leurs 2 tests obsoletes, et la dependance de test `bcrypt`

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

# Revue high-level 2026-07-14 — nouveaux items backlog

> Issus d'une revue produit/technique du 2026-07-14 (William + agent). Ce ne sont PAS des chantiers termines :
> ce sont de nouveaux items backlog. Aucun statut de chantier existant n'a change.
> Deux divergences CLAUDE.md relevees pendant la revue ont ete corrigees le jour meme :
> (1) la similarite consomme la co-occurrence des sets via `similarity_service._load_set_map` (PAS catalog-only,
> contrairement au cadrage du doc) ; (2) le commentaire `external_id` de `models/artist.py` (= track id Deezer
> depuis C6.c v2, l'album id/title vivent dans `payload`).

---

## P2 — Correctifs UX/admin (lot quick-wins)

**Priorite : MOYEN**
**Estimation : 1 jour**
**Depend de : rien (parallelisable). P2.a partage la surface du Hub avec C7 mais ne le bloque pas.**
**Statut : TERMINE (2026-07-16, commit d11f28e, deploye, /deploy_verify SAIN) — P2.a (regroupement activite par album via ActivityAlbumCard), P2.b (skeleton "Pour toi"), P2.c (compteurs total DB : Sets + Watchlist front ; compteur admin "sans deezer_id" fondu dans N2 avec AdminArtists), P2.d (Beatport skip-lock "deja en cours"), P2.e (FamilyChips masque les familles vides + bloc trend decouple). Front only (radar.py family_counts+catalog_visible non pris, stretch). Tests +13 vitest.**

### Objectif

Quatre correctifs front independants et peu risques, issus de la revue.

### P2.a — Affichage d'une sortie d'album sur le Hub (motivation 1, quick-win)

Depuis C6.c v2, un album suivi est eclate en N `artist_activity` (une par titre) → le shelf "Nouveautes de tes artistes" affiche N cartes-titres quasi identiques, et un seul album (cap 40 titres, shelf `limit=12`) peut remplir tout le shelf et enterrer les autres artistes suivis.

- [ ] Regrouper les cartes du shelf par `payload.album_id` au lieu de `catalog_id` (HubView `activityShelf`) → 1 carte album depliable en titres
- [ ] `payload.album_id` / `album_title` sont DEJA ecrits (`_check_releases`) et DEJA renvoyes par `get_activity` — aucun modele, aucune migration
- [ ] Fallback : les activites `set` et les releases sans `album_id` restent des cartes unitaires

### P2.b — Loading "Pour toi"

- [ ] Etat loading/skeleton sur le shelf "Pour toi" tant que `GET /api/recommendations` n'a pas repondu (aujourd'hui : rien pendant le chargement)

### P2.c — Compteurs "vrai total" (x3)

Trois endroits affichent le nombre de lignes CHARGEES, pas le total DB. Le backend renvoie DEJA `total` dans les trois cas → fix purement front (lire `data.total`).

- [ ] `/sets` (SetsView) : afficher `data.total` de `GET /api/sets/` au lieu de `sets.length`
- [ ] `/playlists` (WatchlistView) : afficher `data.total` de `GET /api/watchlist/browse` au lieu de `browsePlaylists.length`
- [ ] Admin "Artistes sans deezer_id (N)" (AdminArtists) : afficher `data.total` de `GET /api/artists/?no_deezer=true` au lieu de `dbArtistResults.length`
- [ ] NOTE : WatchlistView pagine cote client sur <=50 lignes chargees (6/56 playlists jamais chargees) → vraie pagination serveur = decision separee, hors perimetre de ce fix

### P2.d — Beatport "vide" (enveloppe skip-lock)

L'admin "Enrichissement Beatport" affiche 3 champs BLANCS (pas `0/0/0`) quand un sweep tourne deja : la tache renvoie `{skipped: "already_running"}` (lock Redis, TTL ~8h) dont les cles ne matchent pas le template.

- [ ] Le front detecte `result.skipped` et affiche "deja en cours" au lieu des champs blancs (AdminBeatport)
- [ ] Optionnel : rendre le contrat de retour explicite (skip vs stats)

### P2.e — "Ca sort en ce moment" : familles vides + bloc defensif

Le shelf trend du Hub propose des familles STATIQUES (`PILLAR_ORDER`) : une famille sans titre (ex. "hardcore") est proposee, et la selectionner vide `trendTracks` → le garde `v-if="isEmpty && trendTracks.length"` (HubView L117) demonte TOUT le bloc, chips comprises → l'utilisateur est coince (plus aucun controle pour revenir).

- [ ] (a) Filtrer les chips sur `counts[k] > 0` (garder toujours `all` + la famille active) — `family_counts` est DEJA renvoye par `/api/radar/trends` (GROUP BY family : les familles a 0 ligne n'y sont pas) → touche uniquement `FamilyChips.vue`
- [ ] (b) Defensif : decoupler la visibilite du bloc du compte de la famille courante — garder les chips montees + etat vide "aucune sortie dans ce style" (HubView). NECESSAIRE car `family_counts` n'applique PAS `catalog_visible` : une famille peut avoir `count>0` mais 0 titre VISIBLE (invite / titres prives) → (a) seule re-declencherait le bug
- [ ] (Optionnel) coherence back : appliquer `catalog_visible` a `family_counts` (`radar.py`)

### Definition of Done

```bash
# Un album suivi = 1 carte sur le Hub (depliable), plus N doublons
# Shelf "Pour toi" : loading visible pendant le fetch reco
# /sets, /playlists, admin deezer : compteur = total DB
# Beatport deja en cours : message clair, plus de champs blancs
# Trend : familles vides non proposees ; le bloc ne disparait jamais (etat vide si 0 titre)
```

---

## N2 — Fix split artiste multi + separateur "|"

**Priorite : MOYEN**
**Estimation : 1-2 jours**
**Depend de : rien**
**Statut : TERMINE (2026-07-16, commits d11f28e + bare-pipe follow-up, deploye, /deploy_verify SAIN). N2.a : resolve_flag(split) dispose la ligne combinee (deezer_id NULL) apres fan-out 1->2 des liens catalog_artists (role/position, dedup PK) ; set_artists droppes par cascade (passive_deletes='all') ; fin du rebond dans la liste admin. N2.b : separateur "|" reconnu de bout en bout (Phase A/B/C worker + populate_artists + front SEPARATORS), route rule_type "ampersand" ; logique de dispatch extraite en helpers purs classify_artist_string/split_artist_parts (source unique, DRY Phase A/C) ; "/" reste front-only (AC/DC). Bare pipe "A|B" (sans espaces) reconnu (follow-up post-deploy sur cas reel "Oliver Ho|James Ruskin"). Compteur admin "sans deezer_id" = total DB (ex-P2.c) fondu ici. Tests +12 pytest.**

### Objectif

L'admin "Lier un artiste a Deezer" liste les artistes sans `deezer_id`, dont beaucoup sont des chaines multi-artistes ("A & B", "A | B"). Le split manuel ne cloture pas ces lignes : elles reviennent a chaque refresh.

### N2.a — Bug : la ligne combinee orpheline

`resolve_flag(action='split')` cree les artistes tokens mais ne DISPOSE JAMAIS de la ligne combinee d'origine (`deezer_id NULL`) → elle re-apparait dans `WHERE deezer_id IS NULL`, et les 2 tokens (aussi NULL) s'ajoutent → la liste grossit.

- [ ] `resolve_flag(split)` : reassigner les liens `catalog_artists` / `set_artists` de la ligne combinee vers les tokens (fan-out 1→2, avec role/position), puis SUPPRIMER la ligne combinee
- [ ] Reassignation en SQL bulk AVANT `db.delete` (piege ORM delete blank-out PK composite — deja gere dans `link_to_deezer`, voir memoire projet)
- [ ] Corriger le splitter manuel du front (AdminArtists) qui ne coupe que sur les espaces (`name.split(' ')`) → couper sur le separateur detecte / offrir un vrai point de coupe

### N2.b — Ajouter le separateur "|"

- [ ] Poser ` | ` (avec espaces, comme ` & `) en front `SEPARATORS` (AdminArtists) ET back `sync_artists` Phase A + Phase C (`workers/tasks/artists.py`)
- [ ] (Optionnel) script one-shot `populate_artists.py`
- [ ] Unifier les listes de separateurs front/back, aujourd'hui DESYNCHRONISEES (front a `/` sans `vs`, back a `vs`/`,`/`&`/feat sans `/` ni `|`)
- [ ] NOTE : un separateur reste une heuristique de MISE EN REVUE, jamais un merge auto (un `|` peut faire partie d'un nom legitime)

### Definition of Done

```bash
# Split manuel d'une chaine multi-artiste : la ligne combinee disparait definitivement de la liste
# Les liens catalog/set du track pointent vers les vrais artistes splittes
# "|" reconnu comme separateur (front + sync nocturne), listes front/back alignees
```

---

## C7 — Entite Album (M2M catalog_albums)

**Priorite : BAS**
**Estimation : 5-7 jours**
**Depend de : rien de bloquant. Complementaire de P2.a (le regroupement Hub peut vivre sans C7).**
**Statut : A FAIRE — chantier de fond, justifie par la reco/linking (PAS par l'affichage, deja traite en P2.a avec la base actuelle).**

### Objectif

Introduire un objet Album premiere classe. Aujourd'hui AUCUNE notion d'album n'existe : `catalog` n'a pas de regroupement, la similarite/reco n'ont aucune conscience d'album — seul `artist_activity.payload` porte `album_id`/`album_title`, non requetable ni joignable.

### C7.a — Modele + relation

- [ ] Modele `Album` (title, `deezer_album_id` unique, release_date, record_type, label?, has_artwork, relation artiste)
- [ ] M2M `catalog_albums` — M2M OBLIGATOIRE (pas de FK `catalog.album_id`) : asymetrie de merge, un titre vit sur single + album + compil
- [ ] Migration Alembic + bucket MinIO `album-artworks` (invariant : has_artwork = fichier present dans MinIO, jamais d'URL externe en DB ; retirer `album-artworks` de `.dockerignore` si un dossier runtime est ajoute)
- [ ] Point d'insertion : `_crawl_track` et les chemins d'enrichissement recoivent DEJA l'objet album Deezer (aujourd'hui seule la cover est extraite) → upsert de l'Album a cet endroit

### C7.b — Integration reco / similarite

- [ ] Similarite : empecher de recommander N titres du meme album ; affiner le contexte era/label via l'identite d'album (`similarity_service`)
- [ ] Reco : signal "nouvel album d'un artiste proche/suivi"
- [ ] (Lie C8) `_load_set_map` double-compte aujourd'hui parents virtuels + enfants — a corriger dans la meme passe similarite — DEJA CORRIGE le 2026-07-16 (fix pooling C4 : roots-only) → SANS OBJET pour C7

### C7.c — Frontend

- [ ] Carte album sur le Hub (resume N titres + age) — au-dela du simple regroupement P2.a
- [ ] `AlbumView` + route + `/storage/album-artworks/{id}.jpg`
- [ ] Scope de recherche "album" (aujourd'hui : track/artist/set/playlist/genre)

### Definition of Done

```bash
# Tables albums + catalog_albums peuplees a l'enrichissement/crawl
# Reco : plus de N titres du meme album dans une meme sortie
# AlbumView accessible, recherche par album
```

---

## C8 — Fiabilite des sets TrackID (flag + exclusion des calculs)

**Priorite : BAS**
**Estimation : 3-4 jours**
**Depend de : rien**
**Statut : A FAIRE — chantier + INFO (voir note "statut source" ci-dessous).**

### Objectif

TOUS les sets viennent de TrackID.net (audiostreams communautaires : captures radio/livestream/sets soumises par des users). Certains sont peu fiables (cover placeholder, pas de `source_url`, majoritairement `ID - ID`). But : les FLAGGER, les CACHER partout, et les EXCLURE des calculs de proximite — sans supprimer les titres sous-jacents (qui restent une bonne source de donnees au niveau catalog).

### INFO — statut "source peu fiable" (decision produit)

Les audiostreams TrackID sont une source COMMUNAUTAIRE peu fiable, retenue comme telle. Ce chantier pose un flag pour ne plus polluer les calculs ; le RETRAITEMENT en profondeur (classification propre de cette classe de contenu, distinction capture radio vs set propre) est repousse a tres long terme.

IMPORTANT : "exclure des calculs" touche REELLEMENT le moteur de similarite — `_load_set_map` injecte la co-occurrence des sets dans la similarite ET (transitivement) la reco, ce n'est PAS qu'un filtre d'affichage. Cacher un set ne retire PAS ses titres du catalog : ils y restent (resolus scope=shared) ; on ne coupe que le lien DERIVE du set (co-occurrence, poids x3 trend, comptes "artiste vu dans N sets"). Si c'etait le seul lien d'un titre, il reste dans le catalog sans ce signal.

### C8.a — Detection + flag persistant

Aucune colonne de statut/hidden/quality n'existe sur `sets` aujourd'hui. Signaux, par ordre de force :

- [ ] Migration : colonne `reliability` / `hidden` sur `sets`, MATERIALISEE (calculee a l'import + au recrawl — le ratio d'ID n'est fiable qu'a l'ingestion, `completion_pct` est NULL pour les sets jamais recrawles)
- [ ] Signal 1 (le plus fort) : ratio d'identification base `is_id` (`completion_pct` si present, sinon `(total - is_id)/total`) — "majoritairement ID" = faible valeur, stable au re-import (contrairement a tout ce qui est base sur `catalog_id`)
- [ ] Signal 2 : `source_url IS NULL` (pas de provenance)
- [ ] Signal 3 (piste William, retenue) : placeholder artwork = MATCH EXACT — les images placeholder TrackID sont byte-identiques (md5 partage `6e4c7dc9...`). Ingestion : comparer `artworkUrl` a l'URL placeholder connue avant upload ; backfill : match md5/bytes de l'image stockee (l'`artworkUrl` n'est pas persiste aujourd'hui)
- [ ] Bonus provenance : backfill `source_url` depuis `external_slug` (`https://trackid.net/audiostream/{slug}`) pour rendre la provenance cliquable meme quand `url` etait NULL

### C8.b — Application du flag (cacher + exclure)

Ajouter le predicat d'exclusion aux sites recenses (enquete 2026-07-14) :

- [ ] Scoring (~4 sites) : `compute_trends` (branche set, poids x3), `similarity_service._load_set_map`, `artist_connection_service._load_set_counts`, `catalog_service` (`nb_sets`)
- [ ] Affichage (~11 sites) : liste/detail sets, search, page artiste (+ `nb_sets`), genres, follow-feed (`_check_new_sets`), track detail (`set_appearances`)
- [ ] Corriger au passage le double-comptage parents virtuels/enfants dans `_load_set_map` (bug latent releve) — DEJA CORRIGE le 2026-07-16 (fix pooling C4 : roots-only) → SANS OBJET, le reste de C8.b demeure
- [ ] Decider par politique : dedup, `link_set_artists`, UI de review admin (probablement garder visibles)

### Definition of Done

```bash
# Sets peu fiables flagges (ratio ID + source_url + placeholder), calcules a l'import/recrawl
# Sets flagges absents des listings, search, pages, follow-feed
# compute_trends / similarite / connexions / nb_sets excluent les sets flagges
# Les titres sous-jacents restent dans le catalog (non supprimes)
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
| Index `radar_trends` A2-14 (family, rank_in_family) + (rank_global) — endpoint public expose | Opportuniste (issu de C3 clos, non bloquant) |
| Index 4 FK restantes A2-11 — a reevaluer avec la volumetrie | Opportuniste (issu de C3 clos, non bloquant) |
| Batch upsert import RB (A2-13) | Opportuniste, meme zone que A6-08 |
| Logos plateformes DEFINITIFS : remplacer les traces placeholders de `PlatformLink.vue` (map `platform → path`, poses au chantier refonte Track Detail 2026-07) par les SVG officiels monochromes | Quand William fournit les SVG officiels — un seul fichier a toucher |
| TrackDetailView : `padding-inline` mobile — le shorthand `padding` < 640px ecrase les paddings verticaux (meme ecart corrige sur Playlist Detail au FIX round bcb3845, le round FIX de Track Detail etait deja clos) | Prochaine retouche de TrackDetailView — 1 ligne |
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
| C5 | Collections v2 (items polymorphes + dossiers) | Au choix (standalone) | C1 (TERMINE) |
| D4 | Pages Detail (Track/Playlist, binome Claude Design) | Au choix (standalone) | D5 (TERMINE) |
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

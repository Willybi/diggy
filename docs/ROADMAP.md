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
> **Derniere mise a jour** : 2026-08-26 (voir la derniere entree « Mise a jour » en fin de ce paragraphe ; entree d'origine ci-dessous) — C6.c v2 deploye : les releases Deezer des artistes suivis sont desormais crawlees DANS le catalog : album eclate en tracklist, 1 `artist_activity` par titre lie a une entree catalog `scope='shared'` (cover/preview/artistes/release_date), rendu comme un track normal dans la shelf "Nouveautes" du Hub ; fallback lien externe si le fetch `/track` echoue, cap 40 titres/release, aucune migration. Raffinement de C6.c (deja TERMINE le 2026-07-12), commit 245c1cc, /deploy_verify SAIN — ne rouvre pas le chantier. Etat global : series AU + C6 + F5 + C3 + C4 + N1 TERMINE. **Mise a jour 2026-07-13 (2)** : les deux derniers chantiers, C5 (Collections v2) et D4 (Pages Detail), sont desormais STANDALONE et prets a demarrer — retrait des statuts 'apres ouverture' (C5) et 'bloque briefs' (D4). Plus aucune dependance ni condition bloquante : leur lancement est un choix de priorite (William), pas un blocage. D4 = a demarrer en binome avec Claude Design (briefs Track/Playlist co-produits dans le chantier) ; C5 = gros refacto de la feature Collections.) **Mise a jour 2026-07-14** : ajout de 4 nouveaux items backlog issus d'une revue produit/technique (aucun statut de chantier existant modifie) — **P2** (lot correctifs UX/admin : affichage sortie album Hub, loading "Pour toi", compteurs vrai total x3, Beatport skip-lock, chips trend familles vides), **N2** (fix split artiste multi + separateur "|"), **C7** (entite Album + M2M catalog_albums), **C8** (fiabilite des sets TrackID : flag hidden + exclusion des calculs de proximite). Deux divergences CLAUDE.md corrigees le meme jour : la similarite consomme les sets (via `_load_set_map`, PAS catalog-only) ; commentaire `external_id` dans `models/artist.py` (track id Deezer depuis C6.c v2, plus album id). **Mise a jour 2026-07-16** : **N2** et **P2** TERMINES (commit d11f28e + follow-ups, deployes, /deploy_verify SAIN). Le **fix durable pooling de C4** est LIVRE (commits 58c91b0 + 3fae063) : contexte de similarite cache in-process + candidate pooling (pool construit 1x, scoring en memoire) + `_load_set_map` roots-only ; optimisation PURE (byte-identique, ancree par test golden), reco a froid mesuree ~60s -> ~6.6s en prod, SEED_CAP reste a 12. Corriges hors chantier le meme jour (bugs prod emergents, pas de nouveau chantier) : pillar-count `list_artists` via sous-requete (cap asyncpg 32767 bind params sur GET /api/artists une fois la table artistes > 32767 lignes, commit 383588d) et le separateur "|" sans espaces "A|B". **Mise a jour 2026-07-17** : **D4 passe EN COURS** — page 1 (Track Detail) TERMINEE et deployee (0c47a8c, /deploy_verify SAIN, checklist William validee) : 4 composants transverses (Artwork/TrackCard/ScoreRing/PlatformLink, logos placeholders → reliquat) + refonte TrackDetailView. Restent Playlist Detail, verif FIX Artist/Set, Admin Vague 5. **Mise a jour 2026-07-17 (2)** : page 2 (Playlist Detail) TERMINEE et deployee (ef8505f + FIX bcb3845, /deploy_verify SAIN, checklist validee, revue design soldee) — lot 0 back (top_artists/top_genres/in_lib/artists[] sur GET /api/watchlist/{id}, perimetre catalog_visible) + extension additive TrackCard (duree + artistes cliquables) + refonte PlaylistDetailView (bouton Suivre retire de l'UI). La contradiction back de la fiche playlist-detail est tranchee et livree. Restent verif FIX Artist/Set + Admin Vague 5. **Mise a jour 2026-07-20** : page 3 (Set Detail) TERMINEE et deployee (41e9315 + FIX ef7117f, /deploy_verify SAIN x2, checklist validee, revue design FIX round unique solde 5/2/1) — lot 0 back (bpm/key/duree tracklist + top_genres[] perimetre catalog_visible + NOUVEL endpoint GET /api/sets/{id}/similar, moteur C2 agrege niveau set, cache Redis 6h + seed cap 12 apres mesure 21s → 0,12s chaud) + extension TrackCard « set » (position/timecode/etats) + ScoreRing mode pct + NOUVEAU SetCard (40 composants) + refonte SetDetailView. La moitie Set de « verif FIX Artist/Set » est soldee par la refonte ; restent verif FIX Artist Detail + Admin Vague 5. Nettoyage doc : les mentions C7.b/C8.b du double-comptage `_load_set_map` annotees DEJA CORRIGE (roots-only, 2026-07-16). **Mise a jour 2026-07-20 (2)** : page 4 (Artist Detail) TERMINEE et deployee (cb88318 + FIX c81b7e3/01548f4/fbbec21/8411317, /deploy_verify SAIN, revue design 2 rounds soldes) — lot 0 back additif (ArtistSetOut.artists[]/duration_ms) + refonte ArtistDetailView (hero poli, code mort retire, TrackCard/SetCard/PlatformLink consommes, AUCUN composant cree). Leçon majeure versionnee dans le FIX archive : les ecarts #1-#4 venaient d'UNE cause racine layout (fr = minmax(auto,1fr)) invisible au controle statique — verification visuelle headless authentifiee desormais outillee. La verif FIX Artist/Set est entierement soldee ; D4 : reste Admin Vague 5. Nouveaux reliquats : polish transverse ExpandableShelf (libelle/style bouton expand), filtrage placeholders Deezer dans fetch_artist_artworks. **Mise a jour 2026-07-20 (3)** : ajout du chantier **D6 — Refonte UI : listes, Radar & transverses** — inscription a la roadmap du reliquat refonte UI deja SPECIFIE et FIGE dans `docs/refonte-ui/` (Hub, Explorer ex-Catalog, listes Sets/Playlists/Artistes/Genres, Genre Detail, nouvelle page Radar bi-score, suppression Rating projet-wide, restructuration nav) : la roadmap ne planifiait jusqu'ici que les pages detail (D4) ; sans D6 le gros du travail cadre le 2026-07-14 (dont Explorer et son lot back) restait orphelin. Aucun statut existant modifie. **Mise a jour 2026-07-21** : **D6 p.1 Explorer TERMINEE** (D6 passe EN COURS) — refonte Catalog → Explorer deployee (e2b90ac) + 2 rounds FIX (b8e7875 tri/mobile/trim, 056183f revue design), /deploy_verify SAIN x3, revue design Claude Design soldee (1 ecart reel corrige = avis visibles au repos ; 2 faux ecarts verifies : BPM deja aligne a droite mesure CDP, cellule Style avait deja son « — »). Livree : query-builder `GET /api/catalog/` (filtres riches URL-synces, tri defaut created_at, radar mode + champ rating retires), migration 0039 (5 index catalog), NOUVELLE famille `components/filters/` (12) + composables useVirtualWindow/useWindowedList/useFilterState (reutilises par Radar). Retours utilisateur traites : tri whitespace/casse corrige (+ trim ingestion get_or_create + bulk crawl, migration 0040 nettoie 66 titres), swap colonne mobile Key→BPM. **Nouveaux chantiers inscrits** (arbitrage William) : **X1 Dedup catalog** (HAUT, PROCHAIN — ~1934 lignes dupliquees sur deezer_id, fausse trend/similarite/reco) et **X2 Explorer etat de navigation** (BAS). Reliquats : normalisation rb_key→Camelot a l'import, tri mobile dans le drawer, barre de filtres reduite toujours affichee. Reste D6 : Radar, listes Sets/Playlists/Artistes/Genres, Hub, Genre Detail. **Mise a jour 2026-07-22** : **X1 Dedup catalog TERMINE** — prevention deployee (6735ef9 puis correction 2319abf) + nettoyage prod applique (588 doublons reels fusionnes, ~5000 groupes distincts epargnes, dump prealable pris, FK verifiees propres). DECOUVERTE MAJEURE en cours de chantier (spot-check pre-destructif) : `deezer_id`/`beatport_id` ne sont PAS une identite par enregistrement — la recherche Deezer renvoie hits[0] non verifie (un remix herite du deezer_id de l'original) et le fallback release Beatport tamponne un seul id sur tous les titres d'un EP ; mesure prod = 77% des groupes deezer et 94% des groupes beatport partagent un id entre morceaux DISTINCTS. Fusionner sur l'id plateforme seul (approche X1.a/X1.b initiale) aurait detruit des milliers de remixes/versions (asymetrie de merge). Design corrige et livre : fusion gardee par `same_track` (egalite ISRC, sinon titre remix-aware via `normalize_track_title`), **index unique deezer_id/beatport_id ABANDONNE** (migration 0041 supprimee — les ids ne sont pas uniques par morceau). Nouveaux modules `workers/catalog_merge.py` (primitive de fusion FK-safe + `pick_canonical` + `same_track`) + `workers/catalog_dedup.py` (garde a l'enrichissement) + script `scripts/dedup_catalog.py` (dry-run/--apply, clustering clique). Les descriptions X1.a/X1.b de la section X1 decrivent l'approche initiale, desormais partiellement caduque (index unique). Suivis identifies, NON planifies (aucun nouveau chantier cree ici) : bugs racine d'enrichissement (Deezer hits[0] non verifie, Beatport release-fallback) ; residus deferes de la prevention (`_crawl_track`, `enrich_single_beatport`) ; passe doc CLAUDE.md/database-schema.md a refaire sur le design corrige. Roadmap nettoyee le meme jour : sections X1 (Constat/Cause racine/X1.a/X1.b/DoD) reecrites sur le design livre, et **chantier X3 cree** (Fiabilite du matching d'enrichissement Deezer/Beatport — corrige les causes racine des faux ids ; la moitie Beatport a une affinite avec C7). Residus deferes verses aux « Reliquats hors chantiers ». **Mise a jour 2026-07-22 (2)** : **X3 prevention LIVREE et DEPLOYEE** (commit bedd997, /deploy_verify SAIN — containers healthy, imports runtime X3 OK dans worker_enrich + script reverify OK dans api, smoke tests verts). X3.a + X3.b : la validation du match vit dans les fonctions de RECHERCHE (pas seulement `enrich_entry`) — helper `deezer_enrich._deezer_hit_matches` (ISRC sinon titre remix-aware via `normalize_track_title` + artiste folde) branche dans les DEUX jumeaux sync/async de la recherche Deezer, et `beatport/client._release_title_matches` (egalite normalisee sur name+mix_name reconstruit) durcit le fallback release Beatport dans ses DEUX jumeaux (suppression du retour aveugle `len==1` + substring lache) ; un non-match ne pose RIEN → l'entree reste eligible au re-scan E1. Aucun modele ni migration (l'index unique reste volontairement abandonne, X1). X3.c : script `scripts/reverify_platform_ids.py` LIVRE (dry-run/`--apply`, idempotent, efface les ids partages entre enregistrements distincts + reset l'etat E1 ; reutilise le clustering de `dedup_catalog`) mais le rollout `--apply` reste EN ATTENTE (decision ops : dry-run de mesure puis dump prealable). Suivis post-deploiement NON planifies : (1) watch recall au 1er nightly (variantes *-Mix/remix/titres non-latins cessent d'obtenir un id — direction voulue « mieux rien qu'un mauvais id »), (2) residu metadonnee mal-derivee que reverify ne blanchit pas, (3) observation infra MinIO proche de sa limite memoire (voir « Reliquats hors chantiers »). CLAUDE.md a jour (bullet dedup catalog reecrit sur le design livre + Last verified 2026-07-22). **Mise a jour 2026-07-22 (3)** : **X3 TERMINE**. X3.c-ext deploye (15016d0 : reverify efface AUSSI le bpm/key beatport-source pour re-derivation, garde invariant #2 sur une valeur rekordbox/deezer) puis **rollout `--apply` execute en prod** apres dump chiffre (2779 deezer + 10111 beatport ids effaces + 20212 champs bpm/key nulles ; `Remaining suspect groups: 0` verifie + dry-run frais + spot-check SQL confirmant le nettoyage chirurgical par-colonne). Les ~12,9k lignes re-derivent id + bpm/key corrects au re-scan E1 nocturne (drain 1-3 nuits). X3 verse aux « Chantiers termines ». Mitigation **MinIO deployee** (252e53b : `mem_limit` 2G — container recree, mem 999→66 MiB, /deploy_verify SAIN ; + cron VPS restart hebdo lundi 00:30 Europe/Paris) ; reste la mesure J+1 working-set vs fuite (voir « Reliquats hors chantiers »). **Mise a jour 2026-07-22 (4)** : **MON — Monitoring enrichissement + scheduler Beatport horaire LIVRE et DEPLOYE** (commit d6fd7eb, /deploy_verify SAIN — migration 0041, endpoint GET /admin/monitoring, nouveaux assets front, tache `snapshot_backlogs` enregistree+executee, page admin OK, zero erreur). **Chantier ne au fil de la session, NON numerote** (hors table « Vue d'ensemble »). Deux volets : (1) `enrich_catalog_beatport` passe de 2 passes quotidiennes (06h/15h) a un DRAIN HORAIRE borne (`crontab(minute=0, hour="6-23")`, `batch_size=800`/run, `time_limit` 3300s, `BEATPORT_LOCK_TTL` 3900s, `autoretry_for` retire) : un kill de deploiement coute <=1h au lieu de ~8h, les heures creuses sont remplies, no-op en secondes quand le backlog est vide (auto-throttle). **Cela SUPERSEDE le volet C6.a.2 « 2e passe Beatport 15h » et tranche sa DECISION en attente** — la reponse n'est ni 1 ni 2 passes mais un drain horaire (les CHECK J+2/J+3 de C6.a.2 sont donc caducs, non edites ici par respect du perimetre). (2) Nouvelle table `metric_snapshots` (migration 0041) + tache horaire `snapshot_backlogs` (`tasks/monitoring.py`, `count_enrich_backlog` fidele aux tiers E1 : never/due/cooldown/abandoned partitionnent, `total_missing` autoritaire) + `services/monitoring_service.py` (agregation `crawl_logs` en Python, dialect-neutre) + `GET /admin/monitoring` + page admin `AdminMonitoring` (composants SVG maison `components/charts/` : TimeSeriesChart/SparkLine/StatTile, tokens `--chart-*` light+dark). Vues : burn-down des backlogs, debit/hit-rate, erreurs/durees, statut des taches + verrou. 1er snapshot prod verifie (deezer total_missing 11257, beatport 49372 dont 23211 jamais-tentes apres le reverify X3.c, artistes 969 a lier / 2362 sans pochette, sets 188, catalog 127211). Incident de transition traite : le deploiement a recree les workers pendant une passe Beatport ancien-code -> lock `lock:enrich_beatport` orphelin (ancien TTL 30000, ~7h) purge a la main ; le TTL court du nouveau code empeche la recurrence. **Reliquats hors chantier** (non planifies) : (a) bug pre-existant `POST /admin/genres/auto-classify` -> `enrich_catalog_beatport(genre_only=True)` (parametre inexistant -> TypeError, endpoint casse) ; (b) `enrich_catalog` Deezer garde encore `autoretry_for=(Exception,)` + soft-limit 7200s, jumeau du fix Beatport, a traiter ; (c) `5de55a1` (X3.c) consigne a posteriori : reverify reinitialise le `has_preview` perime en vidant `deezer_id` (~2,3k boutons Play qui 404), prod remediee + script patche. **Mise a jour 2026-07-23** : **D6 p.2 Radar LIVRE et DEPLOYE** (commits 4675445 feat + 53b1d62 fix revue design ; /deploy_verify SAIN x2). Nouvelle page `/radar` = surface de reco bi-score : endpoint `GET /api/radar/feed` (`radar_service.list_bi_score`) fusionne top-N Tendance par famille (`radar_trends.rank_in_family`) + <=100 reco perso (`recommendation_service`) par `catalog_id`, 2 notes /10 max-normalisees PAR COLONNE (« — » si absente sur un axe), filtres facon Explorer, tri Tendance par defaut, `catalog_visible`, JWT. `catalog_service.list_catalog` gagne un param ADDITIF `catalog_ids` (defaut None = inchange) reutilise comme builder canonique des lignes Tendance. Front : `RadarView.vue` (reutilise composables + famille `filters/` + `ScoreRing` x2, bande colonne active, « — » muet, ▲ velocity seuil 1.5, cold-start, responsive preservant les 2 scores), entree nav Sidebar+Bottom, « voir plus » Hub (« Ca sort »/« Pour toi ») → /radar. AUCUN modele ni migration. Revue design Claude Design soldee (round unique) : 1 ecart accepte (lisibilite en-tetes score mobile → `--fs-nano`, corrige 53b1d62), 1 rejete (couleur ▲ velocity deja `--accent-ink`). D6 avance : reste listes (Sets/Playlists/Artistes/Genres), Hub (refonte complete), Genre Detail. **Mise a jour 2026-07-23 (2)** : **Hotfix mobile hors chantier** (ne au fil de la session, NON numerote, AUCUN statut de chantier modifie, hors perimetre D6) — commit a212595, /deploy_verify SAIN (front-only : seul `diggy_frontend` recree, workers intacts donc pas de risque de lock enrich orphelin ; bundle prod verifie = ne contient plus que `/api/recommendations/` avec slash), checklist humaine validee sur iPhone (login OK, shelf « Pour toi » affiche, verrou scroll OK, non-regression desktop OK). Deux correctifs. (1) **Login Google KO sur Safari iPhone uniquement** (OK sur PC) : diagnostic par logs nginx par-device (vraie IP + User-Agent + referer — la ou `docker logs api` ne montre que l'IP nginx interne). Le login REUSSISSAIT (`/api/auth/me` -> 200, token valide) mais le Hub appelait `/api/recommendations` SANS slash final -> 307 vers le chemin canonique -> **Safari/WebKit supprime le header `Authorization` en suivant la redirection** (Chrome/desktop le conserve, d'ou « marche sur PC ») -> 401 -> l'intercepteur `utils/api.js` (auto-logout sur tout 401, comportement INTENTIONNEL et teste dans `api.test.js`, donc NON modifie) faisait `logout()` + `router.push('/login')` juste apres un login reussi -> retour au bouton sans message. Fix minimal : viser le chemin canonique `/api/recommendations/` (`HubView.vue` `loadReco`) — seul endpoint a la fois authentifie ET appele sans slash (les autres bare-prefix sont publics : `/api/genres`, `/api/search`). Meme classe de bug 307 que A4-10 (AU1.e, deja traitee pour `/genres`), en sens inverse (public -> on retire le slash ; authentifie -> on l'ajoute, sinon perte du token sur Safari). AUCUN modele ni migration. (2) **Verrou de la translation laterale mobile** : `overflow-x: hidden` + `overscroll-behavior-x: none` sur `.app-main` (`App.vue`) — `overflow-y: auto` forcait l'axe X a `auto`, donc tout debordement de quelques px rendait le conteneur scrollable horizontalement (drag lateral + rebond iOS) ; le scroll vertical est preserve. Front-only, 400/400 tests front verts, lint OK. Piege consigne en memoire projet (Safari drop Authorization sur redirection 307). **Mise a jour 2026-07-23 (3)** : **D6 p.3 Hub LIVRE et DEPLOYE** (commit 74376da ; /deploy_verify SAIN, checklist humaine validee). Refonte de l'etat vide du Hub + nouveau composant partage `<DiscoveryCard>` (carte de decouverte horizontale, 5 variantes par props : tendance #rank / reco in-lib / nouveaute / set / lien externe ; meta mono `BPM · KEY · age` degradee SANS tiret ; play hover-reveal desktop + toujours visible <640 ; consomme `<Artwork>`) + vitrine DesignSystemView §7 + 15 tests Vitest. Back UNIQUE : `release_date` ajoute a `TrendItem` + query `list_trends` (`routers/radar.py`) pour l'age de sortie sur « Ca sort », AUCUNE migration (colonne `catalog.release_date` deja indexee). Page : bloc « Genres populaires » retire, « Essaie » sous la search bar + fleche SVG, top 9 (Ca sort / Pour toi), 3 etageres branchees sur `<DiscoveryCard>`, « Voir plus » → /radar (invite → /login), « Nouveautes » « voir plus » livre en DESACTIVE « Bientot » (arbitrage William : `/new-releases` = D6.d non cadree, pas de lien mort), dropdown de scope unifie en SVG (fin des emoji) + compteurs par type en recherche (recap C1 integre), `ActivityAlbumCard` alignee (auto-portante, Hub-only), helper `format.relativeAgeShort`. Revue design Claude Design (Phase 5) SAUTEE (choix William, rendu fidele au pilote). Reporte en backlog (AUCUN chantier cree) : recap C5 (badges « sur N sources » / genre / duree sur les cards, heterogene entre etageres + back en plus). Handoff versionne `docs/refonte-ui/handoff-hub/` ; fiche hub.md + TRANSVERSE (`<DiscoveryCard>`) a jour. D6 avance : reste listes (Sets/Playlists/Artistes/Genres), Genre Detail, + reliquat desactive `/new-releases` (D6.d). **Mise a jour 2026-07-24** : **D6 p.4 Sets (liste) LIVRE et DEPLOYE** (commits 06fbf35 feat + a0b1498/cad5998 correctifs ; /deploy_verify SAIN x3, captures headless desktop+mobile, checklist William validee). Refonte de la liste `/sets` en TABLEAU enrichi. Lot 0 back `GET /api/sets/` : exclusion des sets a 0 track identifie (HAVING, `total` honore), params `sort` (titre/date/tracks/duree, `-date` defaut) + `ids`/`exclude_ids` (resolution du filtre d'avis facon Artistes), `top_genres` deduits par set (batch, perimetre `catalog_visible`, `get_current_user_optional`, cap 3), `artists` passe de `list[str]` a `[{id,name}]` (via `SetArtist`). Front `SetsView` reecrit : `usePaginatedList` (infinite scroll), rangee enrichie (`<Artwork>` sans in-lib, `<ArtistLinks>` cliquables, `<StyleTag>` genre replie <860px, `<ScoreRing mode=pct>`, `<LikeDislike>`), tri par en-tete server-side, panneau Ajouter en MODAL 2 onglets centre, empty states, column-drop 1000/860/700/640. AUCUN composant transverse cree (tous livres) ; AUCUNE migration. Deux incoherences fiche vs donnees tranchees avec William au pre-vol : (1) colonne **Source RETIREE** — 100% des sets sont `source='trackid'` (origine `platform` connue pour 68/11800 seulement) donc un logo serait identique partout ou vide a ~99% ; (2) colonne **Tracks** = anneau ScoreRing `%` — l'import ne stocke QUE les tracks identifiees, donc `identified==total` pour 100% des sets listables (verifie prod : 0 placeholder ID, 0 track sans catalogue) → le `%` vaut structurellement ~100% ; bref detour vers un compteur `N tracks` (a0b1498) puis anneau `%` RETABLI a la demande de William (cad5998), `%` desormais visible aussi sur mobile (vrai bug initial), le tri en-tete « Tracks » se faisant par nombre de tracks. Handoff versionne `docs/refonte-ui/handoff-sets-list/` ; fiche sets-list.md + TRANSVERSE a jour. Nouveaux reliquats (voir « Reliquats hors chantiers ») : enrichissement set→artiste (44/12345 lies), `RingPct.vue` orphelin, filtre « A explorer » plafonne a 200. D6 avance : reste listes Playlists/Artistes/Genres, Genre Detail, + reliquat desactive `/new-releases` (D6.d). **Mise a jour 2026-07-27** : **D6 p.5 Playlists (liste) LIVREE et DEPLOYEE** (commits 9b0b9d8 back + 49d9386 front + eddb960 revue design + c2acac9 retrait pastille ; /deploy_verify SAIN, checklist William validee, mesures CDP). Refonte de la liste `/playlists` en TABLEAU enrichi (jumelle de Sets). Lot 0 back `GET /api/watchlist/browse` : params additifs `sort` (title/creator/tracks/crawl, prefixe `-`=desc, defaut title) + `ids`/`exclude_ids` (filtre d'avis facon Artistes) + `top_genres` deduits par playlist (batch radar_tracks→catalog, perimetre `catalog_visible`) + expose `last_changed_at` ; patron `routers/sets.list_sets`, AUCUNE migration (corrige au passage le `limit=50` par defaut qui n'affichait que 50/56). Front `WatchlistView` reecrit : `usePaginatedList` (infinite scroll), rangee enrichie (`<Artwork>` sans in-lib, source en logo `<PlatformLink>` variante glyph accolee au titre, `<StyleTag>` genre replie <880px, `owner`, `track_count` brut, bloc « Dernier crawl » date + statut live `useTaskPoll` + bouton Crawl revele au survol, `<LikeDislike>`), tri par en-tete server-side, modal Ajouter (URL) recentre desktop / bottom-sheet mobile, retrait `external_id`, column-drop 1040/880/720/640 ; AUCUN composant transverse cree. Revue design Claude Design (round unique) : 4 ecarts retenus et corriges (E1 bloc crawl sur la ligne de base, E2 demi-droite reequilibree, E5 chip genre nano en mobile, E6 fleche de tri decollee) ; 2 rejetes apres verif code = conventions de composants partages (E3 segment Liked vert = `SegFilter` par design ; E4 dislike coeur barre = `LikeDislike` app-wide → brief a corriger, pas le code). Arbitrages produit William : concept « suivre » masque de l'UI ; **pastille cadence/fraicheur RETIREE** apres 2 iterations (Quotidien/Hebdo/Mensuel → « MAJ Xj » → retrait complet) — redondante avec « Dernier crawl » dans les donnees actuelles (`last_changed_at` coincide avec le crawl ; 8/56 playlists datees, toutes recentes) et son rendu 2 lignes decentrait le bouton Crawl (verifie CDP : apres retrait, 46/46 boutons centres) ; `last_changed_at` reste expose par le back (reutilisable). Handoff versionne `docs/refonte-ui/handoff-playlists-list/` ; fiche playlists-list.md + TRANSVERSE a jour. **Reliquats** (non planifies) : indicateur « dormante/stale » a reintroduire post-ouverture quand les donnees divergeront ; tooltip glyph `<PlatformLink>` « Detecte sur X » a reconcilier cote composant partage. D6 avance : reste listes **Artistes/Genres**, Genre Detail, + reliquat desactive `/new-releases` (D6.d). **Mise a jour 2026-07-31** : inscription de 2 nouveaux chantiers moyen/long terme issus du cadrage « analyse audio des previews Deezer » (AUCUN statut existant modifie). Mesure prod du gisement : 195 914 entrees catalog, 137 045 liees Beatport (70,0 %), 175 254 liees Deezer (89,5 %) ; **48 872 entrees ont une preview Deezer mais NI bpm NI key** (toutes sans lien Beatport). **E2 — Analyse audio des previews (BPM + Key)** (MOYEN, 3-5 j) : deriver bpm+key des 30 s de preview en local (stack recommandee : Essentia `RhythmExtractor2013` + `KeyExtractor` profil `edma` calibre electro ; conversion → Camelot cote worker), provenance `bpm_source/key_source='analysis'` JAMAIS prioritaire sur beatport/rekordbox/deezer (invariants #2/#3 — un lien Beatport ulterieur ecrase la valeur analysis), benchmark prealable E2.a sur ~500 refs Beatport+preview avec GO/NO-GO chiffre, analyse transiente SANS stockage audio, AUCUNE migration. **C9 — Embeddings audio & reco par contenu** (BAS, 8-12 j, phases separables) : vectoriser ~175k previews (v1 Essentia Discogs-EffNet CPU-friendly, candidats CLAP texte→audio et MERT GPU a benchmarker), stockage **pgvector** sur le PG16 existant (index HNSW, requetes composables avec `catalog_visible`), feature « sonne comme » (Track Detail), eval quantitative voisins-embedding vs co-occurrence sets, injection en 2e axe dans `recommendation_service` (reco hybride, cold-start resolu), phase recherche OPTIONNELLE C9.d = fine-tuning contrastif « mixabilite » supervise par les ~12k sets DJ. Garde-fou : un encodeur audio n'est PAS un LLM (score = produit scalaire deterministe, invariant #5 respecte) — a consigner dans CLAUDE.md au lancement. **Mise a jour 2026-07-31 (2)** : **D6 p.7 Genres (liste) TERMINEE et DEPLOYEE** (commit b6b8a4f feat + 83e0ffb revue design ; /deploy_verify SAIN x2, captures headless dark/light + mobile 375, checklist William, mesures CDP). Refonte de la liste `/genres` — la page reste une **GRILLE DE CARTES** cover-driven (pas un tableau), mouvement = assainissement + harmonisation. Lot back leger `GET /api/genres` : nouveau tri `sort=lib` (« En bib ») ajoute au pattern (`^(tracks|alpha|lib)$`) + branche Python (`-in_lib_count`, tie-break `-track_count` puis nom ; tri deja en memoire sur le `fetchall` complet, `in_lib_count` deja au SQL), AUCUNE migration, precedent = tri `lib` de `/api/artists`. Front `GenreCard` + `GenresView` : retrait du badge in-lib overlay → in-lib passe en **STAT de body « En bib »** (`--pos-ink` si >0, « — » sinon, harmonise avec `ArtistCard`) ; **BPM sorti de la ligne de stats** vers une ligne de signature (`PILIER · lo–hi BPM`) sous le nom ; SegFilter 5 segments (Tracks · En bib · A–Z · Liked · Disliked) ; avis `<LikeDislike>` restyles en `:deep()` (hover-reveal + bouton actif epingle quand un avis est pose, composant NON modifie) ; grille **jamais 1 colonne** (2-col fixes <640) + container-queries par card (243/219) ; empty states facettes ; hover sans transform ; admin strip gate `is_admin` neutre. AUCUN composant transverse cree ; `GenreCard` propre a la page. **Arbitrage pre-vol DONNEES** (leçon /sets, tranche avec William) : le « % de couverture bib » (recap C2) **RETIRE** — mesure prod : `inLibCount/trackCount` = 0,1–5 % sur TOUS les genres (denominateur = catalog global ~127k, non filtre) → barre morte partout ; seul le **compte** in-lib (0→132, variable) est conserve. Revue design Claude Design (round unique) : **6 correctifs ACCEPTES sur 6, 0 rejet**, deployes en 83e0ffb — (1) compteur de page faux en facette d'avis (« 75/75 » sur grille vide → `shownCount` = nb affiche), (2) copy empty « Disliked » (« pouce » → « cœur barre », glyphe reel de `LikeDislike`), (3) estompe disliked descendue sur art+body (jamais sur les controles → avis epingle relisible, l'opacite d'ancetre ne s'annule pas sur un descendant), (4) signature 2-col mobile sur 2 lignes (plus de troncature « 70–145 B… » en cours d'unite), (5) bouton admin en `.btn`/`.btn--sm` partage (retrait hover accent parasite), (6) 4 tokens (`--ink-3`, `--r-xs`, titre `700 --fs-lg` aligne sur Sets/Playlists/Explorer/Radar, `+N` en `--overlay-modal`). Handoff versionne `docs/refonte-ui/handoff-genres-list/` (BRIEF + FIX annote + README) ; fiche `genres-list.md` (bloc pre-vol + §7) + TRANSVERSE (in-lib en stat LIVRE sur Genres + pattern avis hover/epingle) a jour. Reliquats notes (hors perimetre, aucun chantier cree) : `ArtistsView` titre `--fs-xl` = outlier a aligner sur `--fs-lg` ; cible tactile 30px des avis + `title` par segment SegFilter = limites de composants partages a traiter au niveau composant. D6 avance : reste **Genre Detail** + reliquat desactive `/new-releases` (D6.d). **Mise a jour 2026-08-02** : **X2 — Explorer etat de navigation (filtre+scroll) TERMINE et DEPLOYE**, livre AU-DELA du perimetre initial (Explorer seul). Restauration de la **position de scroll** ET des **filtres** au retour depuis une fiche detail, sur les 6 listes : pilote Explorer (nouveau composable `useScrollRestore` via `history.state` + salve parallele bornee `fetchUpTo` sur `useWindowedList` — commits 8e47adb bouton retour / c9bd8c4 pilote / fd63817 salve parallele), puis Radar (c5cae9f) et les 4 grilles Artistes/Genres/Sets/Playlists (527d613). DECOUVERTE en cours : les 4 grilles ne persistaient **AUCUN filtre en URL** avant (divergence avec Explorer/Radar via `useFilterState`) → nouveau composable `useUrlSync` (miroir refs<->URL, garde les refs locales des grilles) + `fetchUpTo` ajoute a `usePaginatedList`. Bouton « Retour » des 5 fiches detail factorise en composant partage `BackButton` (vrai `router.back()` + repli liste si pas d'historique interne). 533 tests front verts, /deploy_verify SAIN. **Incident traite hors chantier (aucun statut modifie)** : au deploiement, `/api/radar/feed` (endpoint lourd, ~550 MB/appel) OOM-killait `diggy_api` (cap 1 GiB, 2 workers uvicorn) → 502 sur TOUT (health inclus) ; **fragilite PREEXISTANTE**, non causee par ce chantier ; remede = cap memoire api **1G→3G** (commit dbc550e, deploye + teste OK). Suivi non planifie (aucun chantier cree) : adoucir les salves paralleles `fetchUpTo` cote code (efficacite ; l'OOM est couvert par le 3G). Consigne en memoire projet `api-oom-radar-feed`. **Mise a jour 2026-08-03** : inscription du chantier **D8 — Voir-plus contextuels** (BAS, 2-3 j, aucun statut existant modifie) — retour d'usage William sur Genre Detail fraichement livree (80285ef) : « Voir les N autres » des sous-boites append une poignee de cards inline au lieu de NAVIGUER vers la page liste pre-filtree (grammaire deja actee sur le Hub top-9 → Radar), et la tracklist infinite-scroll (15,6k tracks sur Techno) rend « Genres proches » inatteignable. Etat des lieux verifie : Explorer filtre deja genres[]/artist_id[] ; /sets /playlists /artists n'ont AUCUN filtre genre (le `top_genres` de /sets est de l'affichage) → D8.a = 3 params back additifs, D8.b = renvois contextuels + tracklist bornee + amendement fiche genre-detail (re-introduction contextuelle assumee de la fonction de l'ex-bouton « Tout filtrer dans Catalog »), D8.c = generalisation opportuniste (Artist Detail — attention semantique /sets?artist=, SetArtist ne couvre que 44/12345 sets). **Mise a jour 2026-08-03** : diagnostic prod du bouton admin « Lancer le classement auto » (/genres) — le reliquat (a) de la mise a jour 2026-07-22 (4) est CONFIRME : `POST /admin/genres/auto-classify` enqueue `enrich_catalog_beatport(genre_only=True)` mais le kwarg n'a JAMAIS existe cote worker (signature `batch_size` seul) → TypeError immediat sur `diggy_worker_enrich`, echec SILENCIEUX (l'API repond 200 « queued » avant l'execution ; trace uniquement dans le result backend Redis — rien dans `crawl_logs` ni les logs worker). Casse depuis sa creation (5b6c7f7, 2026-06-23, seul commit de l'historique contenant `genre_only`). Correctif desormais PLANIFIE « a terme » — entree detaillee versee aux « Reliquats hors chantiers » (implementer le mode `genre_only` dans la tache + `select_enrich_candidates`, ou a defaut retirer le kwarg cote endpoint). AUCUN statut de chantier modifie. **Mise a jour 2026-08-03 (3)** : inscription du chantier **N3 — Decoupage verifie des chaines multi-artistes sans separateur** (BAS, 2-3 j, proposition William) + **nettoyage hors chantier du backlog admin « Lier a Deezer »** (aucun statut existant modifie). Audit prod : les 303 artistes `deezer_id IS NULL` du panneau etaient TOUS des orphelins complets (0 `catalog_artists`, 0 `set_artists`, 0 follow/activity/alias — verifie sur les 5 FK referencant `artists`) ; 292/303 crees lors d'un burst semaines du 29/06 au 06/07 (ere backfill TrackID), flux residuel ~2-5/semaine. Les lier a Deezer n'aurait rien apporte (lignes mortes) → remede applique le jour meme : GC one-shot en prod (294 lignes agees > 7 j supprimees, 9 recentes restantes) + le filtre `no_deezer` de `list_artists` exige desormais un rattachement catalog OU set (EXISTS), donc les orphelins ne reapparaissent plus dans le panneau (tests adaptes + cas orphelin ajoute). Les noms orphelins revelent le vrai phenomene amont, non couvert par N2 : chaines multi-artistes collees par des ESPACES sans separateur (« salute Sammy Virji », « Enrico Sangiuliano Charlotte De Witte ») que `classify_artist_string` classe forcement `single` → chantier N3 (decoupages aux frontieres de mots, verification hierarchisee locale-liee > decoupage unique > Deezer+plancher fans, contributeurs du track Deezer en juge de paix, sortie = flags pre-remplis PAS d'auto-liaison). A elucider en N3.0 avant tout dev : dimensionnement du gisement rattache + producteur residuel d'orphelins (fragments « Mitchell »/« Laing »/« Jonathan » crees le 2026-08-03 = chemin de split qui cree les tokens puis echoue a relier). **Mise a jour 2026-08-04** : **D6 p.8 Genre Detail LIVREE et DEPLOYEE** — la DERNIERE page de la refonte UI (les 8 pages D6 sont livrees). Commits 80285ef (refonte) + 5c945ed (fix shelf Artistes mono-rangee) + 3574e1d (tracklist bornee D8.b), /deploy_verify SAIN x3, captures headless dark/light/mobile + genre pauvre, mesures CDP. Lot 0 back ADDITIF (aucune migration) : `GET /api/genres/tracks/{name}` gagne `artists[]` structures (ArtistRef, ordre position, batch catalog_artists sans N+1) + `avis` canonique `COALESCE(user_opinions.opinion, user_tracks.avis)` (invite → null). Front : `GenreDetailView` reecrite sur le BRIEF Claude Design (hero immersif 340/288 : voile + teinte pilier + scrim, titre fluide cqw 2 lignes sans ellipsis, stats clefs en overlay, avatars +N, play verre ; StatStrip ABSORBEE ; « Tout filtrer dans Catalog » RETIRE du hero ; shelves : pied « NN % de ce genre », glyph source `<PlatformLink variant=glyph>`, « N en bib » ; tracklist `<TrackCard>` + avis slot end en `:deep()` epingle ; migration `usePaginatedList` — l'endpoint accepte un MaybeRefOrGetter lu via toValue, no-op pour une chaine ; Admin en dernier, container-queries 720/640). Purge des orphelins **GenreTrackRow/LibDot/StatStrip** (comptage composants 57→56). Aucun composant transverse cree ni modifie (override `:deep()` scopes). Handoff versionne `docs/refonte-ui/handoff-genre-detail/` (BRIEF + README) ; fiche `genre-detail.md` (bloc pre-vol + §7) + TRANSVERSE (glyph 2e conso cards + avis epingle etendu aux rangees) a jour. **D8.b tracklist livre PAR ANTICIPATION** (retour usage William) : scroll infini retire → apercu borne (1 page de 50) + « Voir les N autres dans Explorer » (`/explorer?genre=`) → « Genres proches » enfin atteignable (pain declencheur) ; canal file de lecture player PRESERVE (`playSource.loadMore` = chargement programmatique, seul le declencheur au scroll disparait). Fiche `genre-detail.md` §5 amendee (infinite scroll → apercu borne). **RESTE sur D6** : revue design Phase 5 de Genre Detail (non lancee) + volet transverse **D6.0 Suppression Rating** (jamais fait). Cases D6.c « Genres » (p.7) et « Genre Detail » (p.8) cochees ; case D6.c « Genres » remise a jour (etait restee `[ ]` alors que deployee le 2026-07-31). Travaux HORS chantier Genre Detail deployes en parallele (non traites ici, deja consignes a leurs entrees/commits) : file de lecture audioPlayer (9e1abdd), barre player epaissie (b8e7727), admin « Lier a Deezer » exclut les orphelins + inscription N3 (3035324). **Mise a jour 2026-08-04 (2)** : **D6.0 Suppression Rating TERMINE et DEPLOYE** (commit 1594763, migration 0042, /deploy_verify SAIN) — dernier volet transverse de D6 hors revue design. La note etoile Rekordbox `user_tracks.rating` (0-5) est retiree de tout le backend (le front l'etait deja, purge incrementale D6.a/D6.c). L1 (purge applicative, non destructif) : `avg_rating` retire du detail artiste (dict `stats`) ; les 2 tris `rating.desc()` (top-tracks artiste + related « meme artiste » de Track Detail) remplaces par « en-lib d'abord » (`catalog_id.desc().nulls_last()`, deterministe, PAS de ponderation avis) ; champ `TrackImport.rating`, parsing XML `Rating` (`rekordbox_xml`), ecriture a l'import (`import_rb`) et clause `rating` du merge (`catalog_merge`) supprimes. L2 (drop colonne, destructif) : `UserTrack.rating` retire du modele + migration 0042 (DROP COLUMN + DROP CONSTRAINT `ck_rating_range`, downgrade symetrique). `server/deezer/sync_checker.py` (outillage local, note Rekordbox brute) HORS perimetre, intact. Verifie en prod : `alembic_version=0042`, colonne + contrainte absentes, /api/catalog & /api/artists sans rating/avg_rating, `same_artist_tracks`=10 (tri OK), detail artiste 197 tracks. 1559 tests verts, schema doc regenere, CLAUDE.md aligne (42 migrations). Chantier orchestre via /work_manager (2 lots valides). **RESTE sur D6 : uniquement la revue design Phase 5 de Genre Detail** (non lancee) avant cloture complete du chantier. **Mise a jour 2026-08-06** : **D6 TERMINE — revue design Genre Detail soldee (DERNIER item du chantier)**. Round unique Claude Design sur la refonte deja livree : verdict « implementation fidele », 5 ecarts → **3 acceptes** (lot correctif 8417615, deploye + verifie visuellement headless avant/apres) : (1) debord de la 2e colonne de la shelf Playlists en mobile corrige — grille des shelves `repeat(N,1fr)` → `repeat(N,minmax(0,1fr))` (4/3/2) + `overflow:hidden`/`text-overflow:ellipsis` sur `:deep(.sc-sub)`, le sous-titre long (`owner`) s'ellipse au lieu de deborder le panneau [piege `minmax(auto,1fr)` documente CLAUDE.md, aggrave par `.sc-sub{white-space:nowrap}` de ShelfCard + `.rel-body{overflow:hidden}` de RelBlock] ; (2) `fmtNum()` sur les compteurs « Voir les N autres » des shelves ; (3) statline Sets/Playlists bindee sur `setsTotal`/`playlistsTotal` (totaux de section) au lieu de `genre.setCount`/`playlistCount` qui divergeaient (mesure prod 5218 vs 5140, « Musiques de films » 3 vs 1) + **2 rejetes** apres verif (compteur d'en-tete `RelBlock` rend `{{count}}` brut = composant partage non modifie pour une page → reliquat ; anneau avatar dark `--genre-tile-border-dark` = convention repo `ArtistCard`/`GenreCard`, avatars distinguables au zoom → amender le brief, pas le code). Captures headless avant/apres produites par Claude (pipeline CDP + JWT). **Les 8 pages D6 + les transverses (Rating, navigation, icones SVG) sont livrees ; D6.d (/new-releases, Collections liste) reste hors DoD.** Reliquats de la revue verses a la table dediee. Chantier D6 CLOS. **Mise a jour 2026-08-06 (2)** : **E2.a — Benchmark analyse audio des previews TERMINE (decision GO/NO-GO tracee)** ; E2 passe EN COURS. Mesure sur 600 refs Beatport+preview GELEES (`docs/e2a-benchmark/`, kit reproductible) en conteneur Linux Docker (Windows ne peut pas heberger Essentia ; R2 base Debian bullseye car la binding `keyfinder` ne compile pas sur bookworm/ffmpeg5 — API libav `channel_layout` retiree). Deux rounds : R1 = stack roadmap (Essentia RhythmExtractor2013 + KeyExtractor edma) ; R2 (arbitrage William) = alternatives **TempoCNN** (BPM) + **shaath** & **real libkeyfinder** (KEY). **BPM = GO** : TempoCNN ~76% brut / **~84% au gate de confiance conf>=2.0** (couvre 82%, mediane 0), RhythmExtractor2013 ~73%/~81% ; le **PRIOR DE PLAGE N'AIDE PAS** (le catalog s'etale reellement 60-180 BPM, pas que 120-140) donc l'oracle-fold ~82% n'est PAS deployable — le seul levier = le gate de confiance ; les ~15% d'echecs restants ne sont PAS metriques (repli etendu plafonne ~85% pour les 2 methodes) mais du materiel non-4/4 (folk/art-pop/ambient). **KEY = NO-GO v1**, triple-confirme : edma ~= shaath (~62-63% voisin, exact <=66%), **real libkeyfinder = LE PIRE (55% voisin)** ; mesure contre la key Beatport (elle-meme algorithmique) → insuffisant pour du mix harmonique (une mauvaise key est activement nuisible, invariant #4). Seuils PROPOSES roadmap (BPM >=95%, key >=75%) recalibres : 95% irrealiste pour 30s de preview, ~84% gate = plafond realiste et deja utile (remplit 48 872 tracks aujourd'hui muettes sur les filtres BPM). **Decision (William)** : GO **E2.b BPM seul**, moteur **LEGER RhythmExtractor2013** (evite d'embarquer TensorFlow ~500Mo dans le worker pour +2-3 pts), **backfill LOCAL** (pattern A7-07 ; VPS CPU partage avec Postgres + memoire contrainte) ; valeur `bpm_source='analysis'` labellisee ESTIMEE, gatee conf>=2.0, jamais prioritaire sur beatport/rekordbox (un run Beatport ulterieur l'ecrase), garde `bpm IS NULL`, AUCUNE migration ; KEY non ecrite en v1. E2.b a cadrer (work_manager) avant tout code prod. **Mise a jour 2026-08-07** : inscription du chantier **D9 — Fluidite de navigation (cache vues + skeletons + prefetch)** (MOYEN, 2-3 j, front-only, AUCUN statut existant modifie) — retour d'usage William : delai d'affichage systematique a chaque ouverture de page (Radar/Explorer/listes). Diagnostic code : `<RouterView>` SANS `<KeepAlive>` (`App.vue`) → re-montage + refetch de zero a chaque navigation ; aucun cache client (`usePaginatedList`/`useWindowedList` repartent a `offset:0`) ; round-trip API a CHAQUE arrivee, maximal sur `/radar` (endpoint ~550 MB/req, cf. `api-oom-radar-feed`). Trois leviers : **D9.a** KeepAlive sur les vues liste (retour instantane, scroll/filtres preserves, a borner + reconcilier avec `useScrollRestore` X2), **D9.b** skeletons instantanes (`<SkeletonGrid>` deja dispo, perceived-perf), **D9.c** prefetch au survol du lien de nav (version CIBLEE). L'idee initiale « precharger 100 lignes de CHAQUE page au demarrage » est ECARTEE : declencher `/radar/feed` en salve au boot = scenario du 502 OOM (X2), deplace le delai, fetch inutilement 6-7 pages pour 1-2 ouvertes. Front-only, AUCUNE migration. **Mise a jour 2026-08-08** : **E2 (Analyse audio previews) TERMINE** — chaine complete livree, deployee, deploy_verify SAIN. **E2.a** : benchmark 2 rounds / 5 analyseurs (Essentia RhythmExtractor2013 + KeyExtractor edma/edmm ; librosa ; TempoCNN ; real libkeyfinder) sur 600 refs Beatport+preview gelees en conteneur Linux Docker → **BPM GO** (~84% au gate de confiance conf>=2.0 ; TempoCNN ~+2pts mais TensorFlow ecarte) / **KEY NO-GO** (edma~=shaath ~62% voisin, real libkeyfinder LE PIRE, insuffisant pour le mix harmonique), livrable + kit reproductible `docs/e2a-benchmark/` (0424274). **E2.b** : outil de backfill LOCAL `worker/bpm_backfill/` (e49ca04, conteneur Docker, dry-run/--apply via ssh psql, garde `bpm IS NULL`) + label front « estime » quand `bpm_source='analysis'` (garde override rekordbox) + `bpm_source` expose dans les builders list/detail. **E2.c** : AUTOMATISATION VPS (cce583a + 989329c) — task Celery nocturne `analyze_bpm_previews` (queue enrich, drain horaire 00h-03h, batch 2000 ≈ 8000/nuit self-tapering, lock `lock:analyze_bpm`, PAS d'autoretry, Essentia hors boucle async via `run_in_executor`) qui SUPERSEDE l'outil local ; essentia+ffmpeg dans l'image worker partagee (~312 Mo, pin `essentia==2.1b6.dev1389` seul wheel cp313) ; **migration 0043** (`bpm_analyzed_at`/`bpm_analysis_attempts` = marqueur d'attempt stampe sur VERDICT seulement — DIVERGENCE assumee vs le « aucune migration attendue » du DoD initial, necessaire pour ne pas re-analyser en boucle les low-conf) ; 12e carte admin Apercu « A analyser (BPM) » (count `bpm_analysis_candidate_filter` partage, renvoi neutre Monitoring). **E2.c.2** : courbe backlog BPM sur Monitoring (`catalog.bpm_missing` dans le snapshot horaire, serie TimeSeriesChart, token `--chart-bpm`, c2b724f). La task draine en prod (~3000 BPM ecrits la 1re nuit, backlog ~57,6k decroissant). Orchestre via /work_manager (E2.c en 3 lots + E2.c.2 en 1 lot, tous relus/valides). Hors DoD initial : E2.c.2 (courbe) est un bonus ; la KEY reste non ecrite (NO-GO). Retrait hors E2 (c0c7392, deploye en meme temps) : tache `enrich_set_tracks` redondante/instable supprimee. **Mise a jour 2026-08-09 (2)** : **AV1 — Quick wins audit 2026-08 TERMINE et DEPLOYE** (commits a09fafd + correction restore.md 32cfa62, /deploy_verify SAIN — 10/10 conteneurs healthy, 0 erreur logs, alembic 0043 inchange car AUCUNE migration). 21 items S / 6 lots orchestres via /work_manager (backend 1672 tests verts, frontend 607 x6 stable, ruff/eslint/prettier clean), chaque lot relu au diff + tests rejoues. Livre : M1 (fuite inter-users Artist Detail — `lib_sub` scope par user_id, la page publique ne fuit plus le rb_bpm/rb_key/rb_mytags d'autrui), A1-03 (invalidation cache reco depuis `catalog_service.update_avis`, apres commit), A1-06 (tie-break id DESC sur les 4 builders Genre Detail ; part `list_followed` reportee AV6), A6-06 (`like_escape` + ESCAPE sur 7 sites LIKE), A6-02+M5 (buckets `RATE_LIMITS` radar/feed + sets/search + matcher etendu aux SUFFIXES `/preview-url` et `/similar` sans throttler la navigation ; 429 verifie en prod), A6-09 (`Depends(get_current_user)` sur crawl-status), A3-01 (mode `genre_only` implemente + helper `array_is_empty` per-dialect → le bouton admin auto-classify fonctionne enfin, plus de TypeError) + A3-06 (garde `retries<max_retries` retiree du hook DLQ), A1-04 (commit de `fetch_playlist_artworks`), A1-11 (log des 3 excepts Deezer muets), 2026-07/A1-11 (garde `is_virtual` sur le delete parent de `detach_set`), suppressions mortes (`TrackIDClient.get_styles`, `workers/db.get_session`, `DEFAULT_ANALYSIS_BPM_BATCH_SIZE`), A4-02 (concurrence `fetchUpTo` plafonnee a 3 — mitigation OOM /radar/feed), A4-03 (facette liked/disliked GenresView charge toutes les pages avant filtre), A4-08 (`onScopeDispose(clearTimeout)` dans useUrlSync/useFilterState), A4-09 (avance auto BORNEE sur preview morte via helper `autoAdvance` a `.catch` — corrige aussi une rejection non geree fire-and-forget qui rendait la suite vitest flaky), A5-03 (MinIO cap 2G→3G + GOMEMLIMIT 1800→2700MiB), A5-02 (alerte webhook `BACKUP_ALERT_WEBHOOK` sur echec freshness + logrotate `su root root` documente restore.md ; `--quiet` mirror deja present depuis AU2, non re-ajoute), A5-07 v1 (`npm audit fix` non-breaking), A7-03 (triage README des 3 scripts destructifs). AUCUNE migration (les colonnes `bpm_analysis_*` etc. intactes) ; `array_is_empty` ajoute au pitfall StringArray de CLAUDE.md. Reliquats identifies NON traites (deja rattaches a leurs chantiers, aucun nouveau chantier cree) : suppressions d'API Radar v1 + `GET /watchlist/` → AV6, tie-break `list_followed` → AV6, deep-link `?sort=liked` GenresView passe encore par le fetch page-1 seule (initialFetch hors perimetre A4-03). Serie AV : reste AV2-AV7. **Mise a jour 2026-08-10** : **AV2 — Dependances backend & gate CI TERMINE et DEPLOYE** (commit 50a1e39 + hotfix `3c0c8b6`, `/deploy_verify` SAIN : 10/10 conteneurs healthy, versions prod verifiees, endpoints 200, gate bloquant prouve). Upgrades securite `server/api/requirements.txt` : **python-jose 3.3.0→3.5.0** (PAS 3.4.0 comme planifie : 3.4.x plafonne `pyasn1<0.5.0`=0.4.8 qui porte 4 DoS CORRIGEABLES ; 3.5.0 relache le cap → pyasn1 0.6.4 ; ecart decouvert au moment de rendre le gate bloquant, valide par pip-audit vert), python-multipart 0.0.9→0.0.32, **fastapi 0.115.0→0.141.1 + starlette pinne EXPLICITEMENT 1.6.0** (avant transitif ~0.38), requests 2.34.2, curl_cffi 0.7.4→0.16.0, python-dotenv 1.2.2 ; `pyproject.toml`/`poetry.lock` synchronises (requires-python `>=3.13,<4.0`). Gate **pip-audit rendu BLOQUANT** (A5-01 : `audit` ajoute au `needs:` deploy + retrait `continue-on-error` ; 2 `--ignore-vuln` commentes SANS fix upstream : PYSEC-2025-185 jose + PYSEC-2026-1325 ecdsa Minerva WON'T-FIX) — prouve fonctionnel (le deploy n'a eu lieu qu'apres audit vert). Pins **nginx 1.29-alpine** (A5-06 ; node/python juges acceptables). +2 tests middleware (401 court-circuit + catch-all 500 a travers les 2 BaseHTTPMiddleware). AUCUN modele ni migration. **INCIDENT au 1er deploy** (50a1e39) : l'API crashait au boot — sur starlette 1.6.0 `starlette.templating` leve ImportError a l'import si `jinja2` absent, et sentry-sdk `StarletteIntegration` l'importe au `sentry_sdk.init` (prod 502 sur tout, workers sains) ; NON vu par la CI car `requirements-test.txt` non epingle → suite sur starlette 1.3.1, pas le pin 1.6.0 → hotfix `jinja2==3.1.6` (3c0c8b6), prod restauree a chaud. Pieges consignes CLAUDE.md (divergence test/prod ; valider un upgrade de PIN par build image + smoke prod, pas seulement la suite). **Reste a confirmer cote humain** (checklist deploy_verify, NON bloquant) : login Google prod (bump starlette majeur) + enrichissement Beatport (curl_cffi 0.7→0.16, impersonation TLS non testable en unitaire). Serie AV : reste **AV3-AV7** (AV3 ∥ AV4 parallelisables ensuite). **Mise a jour 2026-08-10 (2)** : **AV3 — Perf data & OOM TERMINE et DEPLOYE** (commit 593ab47, deploy_verify SAIN). Orchestre via /work_manager en 4 lots (fichiers disjoints), tous relus au diff. **L1** cache resultat Redis 6h fail-open sur `get_similar_tracks` par `(seed,viewer,top_n,score_floor,in_lib)` (jumeau de `similar_sets`, `redis` injecte dans `/api/catalog/{id}/similar`, barème C2 INTACT). **L2** migration 0044 groupee : index composite `ix_catalog_created_at_id` `(created_at DESC NULLS LAST, id DESC)` remplacant `ix_catalog_created_at` (sert enfin le tri Explorer par defaut — EXPLAIN prod verifie = **`Index Only Scan`**, plus de Sort ~256k), 2 index `radar_trends` (`family,rank_in_family` + `rank_global`), index partiel `ix_catalog_bpm_analysis_backlog` (miroir `bpm_analysis_candidate_filter()`), DROP de 4 colonnes mortes (`catalog.origin`/`status`/`needs_reconciliation` + `sets.platform`, 0 reader — seul writer retire : `origin="rekordbox"` de `import_rb`). DIVERGENCE assumee modele↔migration : le modele omet le token `NULLS LAST` (SQLite le refuse en `CREATE INDEX`, la suite bâtit via `create_all` sur SQLite ou `DESC` ordonne deja les NULL en dernier), la prod (migration) porte la variante exacte — consignee dans le MANUAL block du schema doc. **L3** retention `RETENTION_DAYS=396` (~13 mois) sur `metric_snapshots`+`crawl_logs` dans `snapshot_backlogs` (session separee APRES le commit du snapshot, idempotent, `admin_audit_log` jamais purge) + tie-break `/api/sets/` `created_at.desc()`→`id.desc()` (determinisme du windowing). **L4** purge de l'I/O sync bloquante ×5 : httpx async (2 appels Deezer `admin.search_deezer_artist` + `artist_service.link_to_deezer`) + `run_in_threadpool` (BeatportClient de `enrich_single_beatport`, boucle artworks + `ensure_bucket` de `fetch_playlist_artworks`, upload MinIO de l'import) + nouvelle `ImageService.upload_fileobj` publique. Gate pre-commit passe : schema doc regenere (drops + index refletes), CLAUDE.md aligne (44 migrations, retention monitoring). Verifie en prod : `alembic_version=0044`, 4 colonnes absentes, 4 index presents, cache Redis `track_similar:*` ecrit, 1683 tests verts. **C10 (pool precalcule nightly) reste CONDITIONNEL** — a declencher seulement si les mesures post-AV3 (RSS, latence /similar) restent insuffisantes. **Deux hotfix OOM de William deployes dans la meme fenetre, HORS AV3 et hors serie** (aucun statut modifie) : `62b12e3` (chunk reclassify genres + drop autoretry — recoupe PARTIELLEMENT l'item M3/A3-04 d'AV4 sur `reclassify_genres_chunk`, mais AV4 reste **A FAIRE**, le gros du chantier — BeatportHTTPError, jumeau enrich_catalog Deezer, locks x6, CrawlLogger, routing — intact) et `6be81a6` (bound similarity scorer memory to top-N, fix uvicorn OOM — mitigation memoire ad-hoc de la famille OOM, ne complete aucun chantier). Serie AV : reste **AV4-AV7**. **Mise a jour 2026-08-13** : **Fix durable du 504 `/api/radar/feed` deploye — incident HORS CHANTIER, aucun statut modifie**. Suite durable de l'incident OOM/502 du 2026-08-02 (memoire projet `api-oom-radar-feed`) : le cap api 1G→3G avait tue l'OOM mais le compute reco « Pour toi » a froid (~30s = pool candidat sur ~269k lignes visibles + scoring multi-seed) restait, et le catalog ayant grossi le symptome est devenu un **504 (timeout nginx `proxy_read_timeout` 60s)**, plus un crash. Cause mesuree : cache reco Redis TTL 1h + le feed tirait DEUX appels concurrents au chargement (la liste + un `feed?limit=1` REDONDANT juste pour les compteurs) → a cache froid les deux recalculaient en parallele, saturant les 2 workers uvicorn au-dela de 60s → 504 sur les deux. Fix (commit 702dd70, /deploy_verify SAIN — chemin chaud 0,43s / froid 32,6s single-flighte, lock relache, tache enregistree au boot worker, cap worker 2G confirme, aucun lock enrich orphelin) : (1) **front dedouble** — compteurs `trend_count`/`reco_count` lus dans la reponse liste via un hook `onData` ajoute a `useWindowedList`, suppression du 2e appel ; (2) **single-flight** `lock:reco:<uid>` (TTL 120s) dans `recommendation_service` — un seul `_compute` a la fois par user, les requetes concurrentes pollent puis relisent le cache (degradent en liste vide si depassement du budget de poll, JAMAIS un 504) ; (3) **tache nightly** `precompute_recommendations` (`tasks/recommendations.py`, beat 05h45, queue `celery`, `lock:precompute_reco`, no-autoretry + catch SoftTimeLimit) pre-chauffe `reco:<uid>` des users actifs, `CACHE_TTL` reco 1h→25h ; (4) **cap memoire `diggy_worker` 1G→2G** (un compute reco pique ~433 Mo au-dessus de la baseline worker ~615 Mo → aurait OOM le worker sous 1G). AUCUN modele ni migration. **C10 (pool similarite precalcule nightly) reste CONDITIONNEL** : ce fix precalcule le RESULTAT reco par user (pas le pool de similarite partage), il de-risque le declencheur /radar/feed de C10 mais laisse la latence /similar intacte. Tests : api 1043, worker 633, front 655 verts ; ruff/eslint/prettier clean. **Mise a jour 2026-08-15** : **AV6 (Backend archi & suppressions) TERMINE et DEPLOYE** (f15b52c, /deploy_verify SAIN). De-engraissement backend, AUCUN modele ni migration, zero changement de comportement, 5 lots orchestres via /work_manager (chacun relu au diff + tests rejoues) : (L1) retrait de la surface Radar v1 morte — endpoints GET /radar/full, PATCH /{id}/state, PATCH /state/batch, DELETE /{id} + fns radar_service list_full/update_state/batch_update_state/add_track + 6 schemas RadarFull*/RadarState*/RadarBatch* ; opinion_sync + UserRadarState INTACTS (le sens opinion->radar survit via /catalog/{id}/avis) ; extraction ADDITIVE de /trends dans radar_service.list_trends. (L2) retrait de GET /api/watchlist/ mort + watchlist_service.list_followed + schema WatchlistListResponse (/browse couvre deja le listing followed ; following_service.list_followed, artistes, intact). (L3) list_sets extrait du router vers NOUVEAU services/set_service.py (deplacement byte-identique, dominance genre GENRE_MIN_SHARE_PCT). (L4) corps de GET /admin/backlog -> monitoring_service.get_backlog_counters ; logique attach/reject/detach set-flags -> set_dedup_service (le service leve LookupError/ValueError jamais HTTPException et ne commite pas, le router garde 404/400 + _audit + commit, invariant #4 preserve). (L5) suppression de 4 composants front morts PageHero/RingPct/ScorePill/InLibBadge + de leurs demos DesignSystemView. 1898 tests backend + 655 front verts, ruff/eslint clean. deploy_verify SAIN (containers healthy, /radar/trends et /sets/ vivants en prod = extractions OK, 0 erreur logs) avec 1 observation non bloquante : image frontend non reconstruite (changements front inertes = composants morts + page dev-only). CLAUDE.md aligne (services set_service + notes AV6, 100 endpoints, 61 composants, Last verified 2026-08-15) ; le re-comptage mecanique COMPLET des compteurs doc reste chartered AV7 (dernier maillon de la serie AV, desormais debloque). Aucun statut d'autre chantier modifie. Piege consigne : les 5 lots ont tourne en parallele dans UN SEUL working tree malgre la consigne serielle — saufs uniquement parce que fichiers strictement disjoints (worktrees separes requis pour du vrai parallele). **Mise a jour 2026-08-15 (2)** : **N3 — NO-GO sur le decoupage verifie (N3.a/N3.b), PIVOT « Hygiene des chaines d'artistes » LIVRE + DEPLOYE** (52544b6, deploy_verify SAIN). N3.0 (dimensionnement prod) a tranche NO-GO : ~3-5 vraies collabs espace-collees dans toute la base, signal fort « 2 segments = artistes locaux lies » trop faux-positif (« Bill Evans Trio ») ; le gisement rattache mesure (737) etait un artefact one-shot du backfill X4 (majorite de noms legitimes). Livre a la place, AUCUN modele ni migration : (L1) module pur `workers/artist_names.py` (`strip_artist_noise` liste-blanche PRO + puce « Vinyl • » / `punct_fold_key` / `looks_acronym` / `dominant_by_fans`) ; (L2) strip cable au funnel de creation d'artiste ; (L3) helper partage `_matching_deezer_hits` des 2 matchers Deezer = fold ponctuation ADDITIF gate + preference au plus grand `nb_fan` (free-id/merge/blank-fold non-latin preserves) ; (L4) script OPS `scripts/cleanup_artists.py` (dry-run/--apply, passes NOISE+DUPES, merge FK-safe, invariant #4 : auto-merge seulement « 1 lie + N NULL sans acronyme », reste flagge) ; (L5) `resolve_flag(split)` fan-out AUSSI les `set_artists` de la source — corrige le producteur d'orphelins (tokens de titres de sets restes 0 catalog/0 set). 1929 tests verts, ruff clean. RESTE : appliquer `cleanup_artists.py` en prod (dump → --apply ; dry-run mesure = 26 noise + 52 dupes fusionnes, 576 flags laisses pour revue humaine). AUCUN autre statut de chantier modifie. **Mise a jour 2026-08-16** : **Hotfix hors chantier — resilience du monitoring (durcissement MON, NON numerote, AUCUN statut de chantier modifie)**. Diagnostic d'un trou 10→14/08 des courbes « Backlog a traiter dans le temps » (page AdminMonitoring) : `diggy_worker` (queue celery, qui porte `snapshot_backlogs`) est reste MUET ~4j apres le deploiement AV3 du 10/08, SANS alerte — `restart: unless-stopped` ne reagit qu'a la sortie de PID 1, pas a un healthcheck `unhealthy`, donc un worker wedge reste mort jusqu'a un restart manuel (survenu le 14/08 06:54, avec drain en rafale de ~90 snapshots empiles par le beat). Le travail MESURE (enrichissement) tournait sur `diggy_worker_enrich` sain tout du long → la tendance restait reelle et l'interpolation du graphe masquait le trou (piege d'interpretation consigne). 3 correctifs livres (commit 080d34b, deploye, /deploy_verify SAIN — 11/11 conteneurs healthy dont le nouveau `autoheal`, 0 erreur logs, AUCUNE migration) : (1) **detection** = check-in Sentry Cron horaire sur `snapshot_backlogs` (`sentry_sdk.crons.monitor`, self-upserting via monitor_config, gate `SENTRY_DSN`) → alerte « missed check-in » des que le sampler s'arrete + **banniere de fraicheur** sur AdminMonitoring (`monitoring_service.get_current_status` expose `snapshot_stale`/`snapshot_age_seconds`, seuil 2h) ; (2) **recuperation** = sidecar `willfarrell/autoheal:1.2.0` (overlay prod `docker-compose.ssl.yml`) qui relance tout conteneur `unhealthy` labelle `autoheal=true` (worker/worker_enrich/beat) — **VALIDE en prod par test controle** (pause `diggy_worker` → autoheal detecte unhealthy et relance en ~24s, retour healthy) ; (3) **prevention** = `--max-memory-per-child` sur les 2 workers (1,46 GiB worker / 780 MiB worker_enrich) recycle proprement un enfant qui gonfle AVANT l'OOM-kill silencieux du cgroup. Backend 1902 tests + AdminMonitoring vitest verts, ruff/eslint/prettier clean. Reste (checklist humaine) : confirmer la banniere verte sur AdminMonitoring + le monitor Sentry `snapshot-backlogs` OK. **Mise a jour 2026-08-16** : **AV8 TERMINE — Robustesse workers/infra v3 (triage Sentry, AUCUN modele/migration, commit 45d7731).** 4 lots livres : cap conteneur `worker_enrich` 1G->2G (OOM signal 9 sur la queue `enrich -c 2`, DIGGY-APP-V/X) ; `postgres` `shm_size: 256mb` (DiskFull du HashAgg `unnest(genres)+group by` de `/api/artists/`, DIGGY-APP-13) ; `reclassify_genres_chunk` durci (timeout/item `RECLASSIFY_ITEM_TIMEOUT` + catch `SoftTimeLimitExceeded` + flush partiel + chunk 500->200, DIGGY-APP-12/15/11) ; `CrawlLogger.__exit__` prefixe le type d'exception + `exc_info` (echecs a message vide de `crawl_trackid_latest`, DIGGY-APP-D). Fixes code rapides DIGGY-APP-4 (quota Deezer transitoire != DLQ) / DIGGY-APP-10 (race ObjectDeletedError) livres hors AV8 (616b430). 741 tests worker verts, ruff clean, `docker compose config` OK. Divergences doc pre-existantes reperees (enrich_catalog_beatport porte `genre_only`, routing `reclassify_genres_chunk` en `enrich`, count `catalog_artists` ~30k) deleguees AV7. Statut AV8 : A FAIRE -> TERMINE. Clot la serie AV cote code ; reste AV7 (doc + tests + LEDGER). **Mise a jour 2026-08-16 (2)** : **AV7 TERMINE — Doc & tests, cloture de la serie AV (AUCUN modele/migration, commit b5d736f, deploy_verify SAIN).** 5 lots : recherche externe scopee par `catalog_visible` (A6-05) + doc d'integrite du lookup dedup `import_external` ; commentaires backfill/visibility_timeout rafraichis (A3-11) ; 3 tests branches `google_callback` (A6-07) ; test PG-only de l'upsert import RB (A6-08) ; lot DOC = recompte mecanique des compteurs CLAUDE.md (endpoints 100->99, modules `tasks/` 8->10, classes 31->28 tables, composants 65->61) + 8 divergences qualitatives + fixes ROADMAP AV4 (cases cochees, routing) ; LEDGER solde (75 lignes -> CORRIGE, plus aucune ligne EN ROADMAP sur la serie AV). 1912 tests backend verts (+4), ruff clean, schema doc regenere. **La serie AV1-AV8 est desormais integralement close.** **Mise a jour 2026-08-17** : **D9 — Fluidite de navigation TERMINE et DEPLOYE** (df310ff, deploy_verify SAIN, front-only, AUCUN modele/migration). 3 lots via /work_manager : (D9.a) `<KeepAlive :include>` des 6 vues listes + reconciliation scroll/lifecycle (gardes `route.path===ownPath` sur useUrlSync/useFilterState anti-clobber en fond, detach/attach useVirtualWindow, pause/reprise polls Watchlist, useScrollRestore.reapply en onActivated) ; (D9.b) skeletons Sets/Playlists DEJA instantanes depuis D6 -> lot reduit a la NON-REGRESSION (premisse « blanc/spinner » du brief FAUSSE, signalee) ; (D9.c) prefetch du CHUNK JS au survol/focus nav (router.prefetchRoute + utils/prefetch.js, dedup, jamais de donnees -> /radar/feed jamais prefetche). Verif RENDU headless locale (Chrome CDP + seed) : retour Explorer PIXEL-IDENTIQUE, 0 refetch liste, scroll 900->900 conserve, prefetch = seul chunk Radar au survol, /radar/feed JAMAIS au boot. 676 tests front verts, eslint clean. CLAUDE.md : 2 pitfalls Frontend (KeepAlive listes + prefetch nav) + entree changelog, Last verified 2026-08-17. Residu a11y consigne : @focus clavier inerte sur les `<span>` Sidebar (effectif sur les `<button>` BottomNav). **Mise a jour 2026-08-17** : **AV9 — Drain enrich deadline interne elapsed TERMINE et DEPLOYE** (0daada7, deploy_verify SAIN, AUCUN modele/migration). Garde deadline `time.monotonic()` = soft limit − DEADLINE_MARGIN (120s, env) verifiee en tete de chaque batch sur les 3 drains (enrich_catalog_beatport / enrich_catalog Deezer / analyze_bpm_previews) → break propre (flush partiel deja commite par batch, stats, retour succes, release lock au finally), stat additive `deadline_hit` dans crawl_logs, soft limits extraits en constantes module partagees decorateur+garde ; catch SoftTimeLimitExceeded CONSERVE (defense en profondeur), rien stampe sur les entrees non atteintes (invariant E1). 8 tests (test_deadline_exit.py), 1927 backend verts, ruff clean. Pitfall CLAUDE.md ajoute (signal soft-limit avale par le handler du transport asyncio, DIGGY-APP-J). Constat au deploy : run enrich_beatport #1369 (22h) fige `running` + creneau 23h skippe = derniere manifestation du bug pre-fix (SIGKILL hard limit AVANT le deploy), lock auto-gueri par TTL, aucune action. RESTE AV9-03 : apres ~1 semaine d'observation (runs nocturnes avec `deadline_hit`, 0 nouvel event DIGGY-APP-T/W/J/V), re-run /sentry_triage pour resolve les 4 issues. **Mise a jour 2026-08-18** : **AV9-03 SOLDE — cloture Sentry, lot AV9 integralement clos.** Les 4 issues DIGGY-APP-V (SIGKILL, 1814 ev.) / J (soft-limit avale par le handler asyncio) / T (hard limit 3300s) / W (TimeLimitExceeded billiard) passees en `resolved` via /sentry_triage (commit 0daada7 en commentaire d'activite ; resolvedInNextRelease → Sentry rouvre en cas de recidive). Verif J+1 : 22 runs `enrich_beatport` en success post-deploy (dernier 08-18 17:00), 0 nouvel event depuis le 08-14, `deadline_hit=0` (backlog draine → garde pas encore sollicitee mais famille de crash eteinte). **Mise a jour 2026-08-18 (2)** : **N4 — Majeurs frontend TERMINE et DEPLOYE** (f436f38, deploy_verify SAIN, front-only, AUCUN modele/migration). 3 lots serie via /work_manager : (L1) vite 5→8 (bundler Rolldown) + vitest 3→4 + @vitejs/plugin-vue 5→6 ; (L2) pinia 2→4 + vue-router 4→5.2.0 ; (L3) re-validation rendu CDP local 31 captures 0 diff. vue-router 5.2.0 (officiel vuejs/router) s'est revele un VIRAGE D'ARCHI : ~18 deps runtime (unplugin/chokidar/@babel/generator, toutes tree-shakees du bundle navigateur = 0 fuite) + plancher Node releve a `^22.18.0 || >=24.11.0` (via @babel/generator@8), satisfait par node:22-alpine / setup-node "22" (resolution flottante >22.18) — arbitrage William : on adopte 5.2.0, plancher Node + surface deps acceptes. Surface applicative quasi nulle (stores setup-store, API router/guards inchangee, 0 fichier source modifie). npm audit = 0 (ferme high vite path-traversal `.map` + moderate esbuild dev-server) ; bundle boot ~190 kB (index ~119 kB + helper precharge ~71 kB) iso AV5 ~192,6 kB (re-decoupage Rolldown, pas une regression) ; 677 tests front verts, eslint/prettier clean. Pitfall CLAUDE.md ajoute (toolchain + plancher Node 22.18, ne pas epingler un tag 22.x < 22.18). N4 = dernier majeur front en attente ; reste C10 CONDITIONNEL. **Mise a jour 2026-08-18 (3)** : **C8 — Fiabilite des sets TrackID TERMINE et DEPLOYE** (3491d68 + monitoring 879ed09, deploy_verify SAIN, backend/workers, migration 0045). Via /work_manager (3 lots serie) : colonne materialisee `sets.unreliable` calculee au funnel `import_audiostream` a chaque (re-)import — le recrawl repasse par lui (`min_age_hours=0`), pas de recompute separe — via le module PUR `trackid/reliability.py` = source unique de la regle : ratio ID>=0.8 DOMINANT ; secondaire = source_url absent ET placeholder (les deux requis, conservateur invariant #4) ; total=0 → unreliable. Predicat d'exclusion `set_reliable()` (ORM) / `set_reliable_sql()` (SQL brut) ajoute EN PLUS du roots-only (`parent_set_id IS NULL`, jamais en remplacement) a ~11 sites : scoring (compute_trends x3, `_load_set_map`, `_load_set_counts` +join, nb_radar_sets +join) + affichage (list_sets, search, artiste +nb_sets, genres list/detail +join, set_appearances, follow-feed `_check_new_sets`). PAS d'exclusion du recrawl (un set flagge peut se de-flagger) ni de l'acces mono-id `get_set_detail` ; titres catalog INTACTS (seul le lien derive du set est coupe). Backfill OPS `scripts/backfill_set_reliability.py` (dry-run/`--apply`, idempotent) applique en prod APRES dump chiffre (`diggy_20260818_203404`) : 1192 sets flagges/35843 (3,3 %, tous 100%-ID → 0 lecture artwork, signal placeholder INERTE en pratique, aucun flag n'en depend), 128 source_url recuperees du slug, re-check convergent 0/0. Ajout monitoring (879ed09) : tuile « Sets non fiables » + courbe burn-down « Sets · non fiables » (token `--chart-sets`) via cle additive `sets.unreliable` du payload `snapshot_backlogs` (0 modele/migration). 1978 tests backend + 677 front verts, ruff/eslint clean. SUIVI OPS non bloquant : URL/md5 placeholder (`6e4c7dc9`) a confirmer sur un vrai payload + reconcilier la semantique source import (url payload) vs backfill (source effective slug-aware) AVANT d'activer le signal secondaire (inerte d'ici la, ratio ID porte le flag seul). Reste C5/C7/C9 A FAIRE + C10 CONDITIONNEL. **Mise a jour 2026-08-20** : **AV10 — Throttle CPU Hostinger TERMINE** (a9d2e62 « Hostinger throttle adjustment », deploy_verify SAIN, infra-only, 0 modele/migration/code applicatif). 2 leviers : (L1, docker-compose.yml) workers/beat `--loglevel=info→warning` + healthchecks postgres/redis/minio `10s→60s` → attaque la ligne dockerd, zero perte fonctionnelle ; (L2, `.env` VPS) `ANALYSIS_BPM_EXECUTOR_WORKERS=1` → `analyze_bpm_previews` epingle 1 coeur Essentia (au lieu de 2) sur la fenetre 00-03h, applique par `up -d worker_enrich` sans deploy de code. Verif J+1 : CPU revenu a la baseline (sar ~89% idle soutenu sur 24h, %steal 1,8), dockerd 23%→~1%, 4 runs analyze_bpm nocturnes success budget 2000/run consomme A 1 COEUR sans deadline_hit/soft_limit (~3700 BPM estimes, ~10-15min/run, aucun debit perdu — batch borne par l'I/O previews, pas Essentia), backlog BPM resorbe ~6000 sur la nuit. Le pic aigu ~80% du 12-18/08 (churn `catalog` post reverify --pre-x3 de X4 + autovacuum) etait DEJA retombe de lui-meme le 18/08 ; les 2 leviers sont structurels/preventifs. Divergence signalee (hors perimetre AV10, NON modifiee) : **C7** (entite Album) est DEPLOYE en prod (VPS a 5e6262c inclut 7e02633 + f234944 + 5e6262c) alors que son statut roadmap reste « A FAIRE » — a clore separement apres verif de ses residuels (rendu headless AlbumView, cron covers backfill). Reste C5/C7/C9 A FAIRE + C10 CONDITIONNEL. **Mise a jour 2026-08-20 (2)** : **C7** (Entite Album) A FAIRE → TERMINE. Objet Album 1re classe livre+deploye (7e02633, migration 0046 : albums + M2M catalog_albums) — peuplement fil-de-l'eau au funnel Deezer, reco/similarite album-aware (de-dup <=1 titre/album), album_service + GET /api/albums/{id} + AlbumView (/album/:id) + scope recherche album. 3 follow-ups post-deploy verifies SAIN : allowlist /api/albums public (f234944), bucket album-artworks manquant corrige + mode backfill --source covers (5e6262c), tuile+courbe monitoring albums (a6b5f77). Cron VPS quotidien covers 2500/j operationnel (1er run 0 erreur ; NB cron systeme = UTC, CRON_TZ ignore). 2039 back + 686 front verts. Reste C5/C9 A FAIRE + C10 CONDITIONNEL. **Mise a jour 2026-08-21** : **C5** (Collections v2) A FAIRE → TERMINE. Items polymorphes + dossiers livres+deployes (664ff41, migrations 0047 polymorphe + 0048 collection_folders) : `collection_items` passe tracks-only → polymorphe (track/set/artist/genre/playlist, PK surrogate, AUCUNE FK native = integrite applicative facon user_opinions, backfill `item_type='track'` sans perte) + dossiers prives un niveau (`collection_folders`, FK `ON DELETE SET NULL`) ; `catalog_merge` repointe les items track SEULEMENT ; front : `AddToCollectionButton` partage gate auth sur les 5 vues detail, `CollectionDetailView` heterogene, `CollectionsView` arborescence. 2074 back + 710 front verts, /deploy_verify SAIN (alembic_version=0048, schema polymorphe confirme, 0 perte au backfill). Reste C9 A FAIRE + C10 CONDITIONNEL. **Mise a jour 2026-08-21 (2)** : **C9** — GATE BENCHMARK C9.0 (GO/NO-GO, calque E2.a) PASSE ; chantier reste A FAIRE (seul le gate d'entree est joue, pas de code applicatif ni migration). Question tranchee : les voisins d'un embedding de CONTENU predisent-ils la co-occurrence en sets DJ ? Kit `docs/c9-benchmark/` (echantillon gele 500 sets fiables → 6819/6901 previews Deezer embeddees Essentia Discogs-EffNet 1280-d en conteneur Linux, aucune persistance audio ; metrique lift@k voisins-cosinus vs setmates, 3 passes all/cross-artist/controle-melange). Verdict GO FRANC : lift@10 = 34.97x all / **32.53x cross-artist** (>> seuil GO 3x), controle embeddings melanges 1.15x (metrique calibree), rang median du 1er setmate 24 vs 314 aleatoire — le signal SURVIT a l'exclusion « meme artiste » = vraie proximite acoustique, pas fuite d'identite d'artiste. Consequences : C9.a (migration pgvector + backfill embeddings 175k) justifie, C9.b (« sonne comme ») / C9.c (reco hybride) demarrables sur EffNet brut, C9.d (fine-tuning contrastif « mixabilite ») degrade de prerequis en stretch. Prochain arbitrage (William) : figer EffNet v1 et lancer C9.a, ou benchmarker CLAP/MERT avec le meme harnais avant de figer. Reste C9.a/b/c A FAIRE + C10 CONDITIONNEL. **Mise a jour 2026-08-24** : **N3** (theme « Hygiene des chaines d'artistes ») — sweep opportuniste d'hygiene artiste LIVRE+DEPLOYE (10 commits 77d0cd3->ef3afd2, aucune migration, 2163 tests verts, CI vertes) qui ETEND le pivot N3 SANS en realiser le RESTE (`cleanup_artists.py` toujours a appliquer) : (1) matcher Deezer `_matching_deezer_hits` — folds `punct_sep_key` (R.Kelly = R. Kelly), `fold_base` translitteration lettres latines non-decomposables + smart-quotes (Altin Gun, Angel'in) et `space_fold_key` hard-gate (AUX88 = AUX 88), + tier de RESURRECTION `ARTIST_LONG_RETRY_DAYS`=180j des artistes abandonnes (3 tentatives) ; (2) panneau admin « Lier un artiste a Deezer » : masquage des dead-ends dormants (abandonnes ET non-splittables) + exclusion des noms routes vers Flags (`artist_flags` pending OU validated) + compteur `dormant_count` → panneau 3825 → ~248 ; (3) routage des chaines multi-artistes vers la file Flags via OPS `backfill_artist_flags.py` (tokenizer regex tolerant aux separateurs colles feat./ft./pres.../+, applique = 215 flags pending crees) ; (4) 2 nouveaux scripts OPS APPLIQUES en prod apres dump cible : `cleanup_orphan_artists.py` (10716 artistes orphelins references par rien supprimes + 5327 artworks MinIO) et `cleanup_placeholder_artists.py` (9 placeholders Various Artists/Unknown Artist/VA... supprimes, 420 liens catalog delies en CASCADE) + `is_placeholder_artist` (whitelist exacte, jamais substring) bloque au funnel Deezer+sync. NB : les commits C9.a socle pgvector + throttle BPM du meme log git = session ANTERIEURE, hors perimetre de cette entree. AUCUN statut de chantier modifie (travail opportuniste ; N3 RESTE inchange). **Mise a jour 2026-08-24 (2)** : **N3** NO-GO -> CLOS. Cloture actee en session : N3.a/N3.b restent un NO-GO chiffre (N3.0 : ~3-5 vrais cas dans 92k artistes, splitter verifie ABANDONNE), le pivot Hygiene des chaines d'artistes est livre/deploye et ETENDU au fil de l'eau (sweep 2026-08-24) ; plus aucun livrable structure restant. Le residu (cleanup_artists.py a appliquer au besoin + chaines lettres-espacees deleguees au flag) devient opportuniste hors chantier. C10 reste CONDITIONNEL (declencheur non arme). **Mise a jour 2026-08-24 (3)** : **C9** A FAIRE -> EN COURS. C9.a demarre : socle pgvector deploye (migration 0049, modele Discogs-EffNet fige v1), backfill local des embeddings en salves ~24% (69k/282k previews), et phase monitoring livree/deployee (1987fa3, /deploy_verify SAIN) — courbe couverture embeddings (StatTile % couverts + serie « a vectoriser » dans le burn-down) et split du graphe monitoring en 3 graphes thematiques (plateforme / backfills contenu / petits soldes). C9.b (« sonne comme ») et C9.c (reco hybride) restent A FAIRE ; C9.a se cloturera au backfill ~100% + eval a l'echelle. **Mise a jour 2026-08-24 (4)** : **C9.b** LIVRE en mode ADMIN-ONLY (endpoint + shelf). Lot 1 back (d3dad75) : endpoint GET /api/catalog/{id}/content-similar — KNN cosine pgvector (comparator EmbeddingVector.cosine_distance) compose avec catalog_visible + cache Redis, valide en prod (voisins coherents, diversite d'artistes). Lot 2 front (45e4559) : shelf « Sonne comme » sur Track Detail, gate admin (v-if auth.user?.is_admin + garde reseau), sans score expose, masque si vide. Les deux /deploy_verify SAIN. Feature VOLONTAIREMENT admin-only le temps que la couverture embeddings (~24%) monte ; passage public differe. C9.c (reco hybride) reste A FAIRE ; C9 reste EN COURS. **Mise a jour 2026-08-25** : **D10** (Admin — Coherence & socle) A FAIRE → TERMINE (54006fb, /deploy_verify SAIN). Front+back, AUCUN modele ni migration : IA admin 8->6 onglets URL-adressables (/admin/:tab, redirect /admin->/admin/overview, fallback overview sur tab inconnu ; fusions Flags->Artistes, Beatport->Enrichissement, Crawl+Monitoring+Audit->Observabilite en rendu groupe, templates non fusionnes) ; **GET /admin/audit-log** paginee (lecture de admin_audit_log jusque-la write-only, user_email via LEFT JOIN, routeur mince -> monitoring_service) + composant AdminAuditLog ; **poller Celery generique renomme** /admin/artists/sync/status/{id} -> /admin/tasks/{id} (5 appels front bascules, pas d'alias) ; **3 actions curl-only exposees** : reset-beatport (garde-fou confirmation inline) + backfill-multi-artists dans le nouveau composant AdminEnrichmentActions (onglet Enrichissement), detach set via section « Sets attaches » d'AdminSets (liste les set-flags status=attached) ; renvois Apercu remappes vers les vrais onglets. +1 endpoint (106), +2 composants admin (65). Verif RENDU headless locale conforme (7 points ; 1 ecart routing /admin corrige en cloture). 2173 back + 730 front verts, ruff/eslint clean. **D11 (refonte graphique admin) desormais DEBLOQUE** (la structure est figee). **Mise a jour 2026-08-25 (2)** : **D10** raffinement UX same-day — les badges des onglets admin, qui additionnaient des compteurs heterogenes (majoritairement des backlogs qui se drainent automatiquement), sont recentres sur les seules files d'ACTION HUMAINE : Artistes = artist_flags.pending, Sets = sets.flags_pending, Observabilite = crawl.dlq (Genres/Enrichissement/Apercu n'ont plus de badge). Chaque badge correspond desormais a une file reellement visible dans l'onglet. Commit dde9eae, /deploy_verify SAIN. Ne rouvre pas le chantier (D10 reste TERMINE ; gap note pour D11 : l'onglet Observabilite ne LISTE pas encore le contenu de la DLQ). **Mise a jour 2026-08-25 (3)** : epuration du panneau admin « Lier un artiste a Deezer » — extension fil-de-l'eau du pivot hygiene des chaines d'artistes (N3 reste CLOS, ne rouvre aucun chantier). Commits 915b92d + c552c55 + cced355, /deploy_verify SAIN, AUCUNE migration. (1) Numeros de desambiguisation Discogs « X (N) » : helper pur `strip_disambiguation_number` (+ jumeau JS) retire le « (N) » a l'AFFICHAGE partout (ArtistLinks / ArtistCard / hero ArtistDetail / AdminArtists) ET a la requete de match, mais le GARDE en base (un « (2) » marque un homonyme DISTINCT cote Discogs — le retirer fusionnerait deux noeuds) ; le match Deezer n'auto-lie que si un seul homonyme distinct ressort (sinon on laisse). (2) Remix : `is_remix_noise` masque du panneau les titres-morceaux captures comme artistes (« Free Bitch (Sinjin Hawke Remix) »). (3) « with » → split : `w` / `with` / `(w …)` ajoutes aux separateurs (front `detectSeparator` + back `_name_is_splittable`) + NOUVELLE tache nocturne `autosplit_with_artists` (04h30, queue enrich, gated Deezer-vide) qui decoupe « X with Y » quand Deezer ne connait pas la chaine entiere : tokeniseur pur `split_with_parts` (retire les verbes colles duet/duo/feat), primitive sync de split (fan-out des liens catalog+set vers les tokens puis suppression du combine, jumelle worker de `resolve_flag(split)`), selection HORS tiers E1 (fix cced355 : les « with » deja cherchees+abandonnees par `link_artists_deezer` etaient invisibles au selecteur a base de tiers → drain impossible). Run manuel declenche : 28 splittees / 0 erreur / 0 « with » eligible restant (1 ligne « ... featuring ... » laissee a la file de flags par la garde `not_flagged`). Tests +pytest (helpers purs + tache, fan-out des liens, gardes) + vitest, ruff/eslint/prettier clean. **Mise a jour 2026-08-25 (4)** : raffinement same-day du panneau admin « Flags artistes » (onglet Artistes) — meme veine que (3), N3 reste CLOS et D10 reste TERMINE, ne rouvre aucun chantier. Commit 13ff6b2, /deploy_verify SAIN, AUCUNE migration (feat front + endpoint paginE). (1) Propositions Deezer LIVE : la colonne Deezer d'un flag n'etait qu'un instantane FIGE rempli par le seul worker `sync_artists` → les flags `auto_split` (backfill) et manuels naissaient avec `deezer_ids={}`, donc zero proposition ; desormais la colonne interroge Deezer en direct pour chaque token (endpoint admin `search-deezer`, match strict fold accents/casse via `foldArtistName`, jumelle du signal live deja present dans le splitter) → ✓ N fans / ✗ / spinner, cache par texte (une recherche max inter-pages), debounce 400 ms, traitement SEQUENTIEL (anti-429 du bucket admin) ; marche pour tous les flags quelle que soit leur origine. (2) Pagination : `GET /artists/flags` gagne `page`/`per_page` (25, plafond 100) et renvoie `{total, items}` (calque sur `list_set_flags`) + pager Precedent/Suivant dans AdminFlags (calque sur AdminAuditLog), reset page au changement de filtre — la table « Flags artistes » n'est plus interminable. (3) Bonus : badge de style pour les raisons `auto_split`/`manual`. Tests +2 back (forme paginee + pagination), 27 back verts, eslint/prettier clean. **Mise a jour 2026-08-26** : raffinement same-day du splitter manuel des flags artistes (`ArtistSegmentSplitter`) — meme veine que (3)/(4), N3 reste CLOS et D10 reste TERMINE, ne rouvre aucun chantier. Commit d617903, /deploy_verify SAIN, AUCUNE migration (front-only, aucun endpoint). Les parentheses `(` `)` et le `/` colle deviennent des unites coupables/supprimables A LA MAIN : ajoutes a `HARD_PUNCT_RE` (detaches en unites propres, meme colles : « (feat », « AC/DC ») + a `DROP_SET` (barres d'office mais restaurables, comme « & »/« feat ») → un split de « Artist (feat Other) » emet « Artist »/« Other » sans le residu « }) » / « (feat » qui subsistait. Garde-fou `GLUE_SET` : un `/` RESTAURE se recolle a ses voisins (« AC/DC » reconstruit en fusionnant les frontieres, pas « AC / DC ») pour ne pas casser les vrais noms a slash colle. N'affecte QUE l'outil de split manuel (l'auto-split back + la liste `SEPARATORS` des boutons de ligne inchanges). Tests util + composant mis a jour (couverture parentheses + recollage AC/DC), 741 front verts, eslint/prettier clean.

---

## Vision cible

Avant l'ouverture aux amis (5-10 DJs), Diggy doit offrir :
1. Une experience mobile utilisable (ils seront sur telephone)
2. Une recommandation de tendance solide, decorrellee des likes (offre par defaut des nouveaux arrivants sans historique)
3. Un moteur de similarite fonctionnel (socle de toute recommandation, avec ou sans user)
4. Une application fermee et etanche entre utilisateurs (auth obligatoire, scopes respectes)

Apres l'ouverture : la recommandation personnalisee (croisement similarite x likes), utile des un seul user et enrichie par chaque nouvel utilisateur.

**Sequence verrouillee (historique — soldee)** : ~~C0 -> R1 -> C1 -> C2 -> H0 + P1 -> F5 + C6 -> serie AU -> C3 -> C4~~ (TOUT TERMINE). Restent **C5**, **D4** (en cours — reste Admin), **D6** (refonte UI listes/Radar/transverses, ajoute 2026-07-20), **C7** et **C8** : hors sequence, chantiers STANDALONE sans ordre impose ni dependance bloquante (seule contrainte legere : D6 s'appuie sur les composants deja livres par D4), lancables au choix.

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
 C5   Collections v2 (polymorphe + dossiers) BAS       3-5 jours    TERMINE (2026-08-21) — items polymorphes (track/set/artist/genre/playlist) + dossiers prives ; migrations 0047/0048 ; deploy_verify SAIN
 D4   Pages Detail (Vague 3)               BAS         5-7 jours    TERMINE (2026-08-08) — Track + Playlist + Set + Artist Detail (2026-07-20) + Admin Vague 5 (onglet Apercu + badges + responsive 12b7b87, fix d212522, revue design soldee 667ceed) ; D7 absorbe
 D6   Refonte UI listes + Radar + transverses BAS      8-12 jours   TERMINE (2026-08-06) — 8 pages (Explorer/Radar/Hub/Sets/Playlists/Artistes/Genres/Genre Detail) + D6.0 Suppression Rating + revue design Genre Detail soldee (lot correctif 8417615) ; D6.d (/new-releases, Collections liste) hors DoD
 X1   Dedup catalog (fusion deezer/beatport) HAUT      3-5 jours    TERMINE (2026-07-22 ; garde same_track, 588 doublons fusionnes, index unique abandonne)
 X2   Explorer — etat de navigation (filtre+scroll) BAS 1-2 jours   TERMINE (2026-08-02 ; restauration scroll + filtres URL depuis la fiche detail — Explorer/Radar + etendu aux 4 grilles ; bouton retour = vrai back)
 X3   Fiabilite matching enrichissement    MOYEN       3-5 jours    TERMINE (2026-07-22 ; prevention A/B deployee + rollout X3.c applique : 2779 deezer + 10111 beatport reset, 20212 bpm/key re-derives) — reliquats decouverts 2026-08-10 (ids UNIQUES pre-X3 non nettoyes + champ artiste divergent) traites en X4
 N1   Nettoyage residus                     BAS         1 jour       TERMINE (2026-07-13)
 P2   Correctifs UX/admin (revue 07-14)     MOYEN       1 jour       TERMINE (2026-07-16)
 N2   Split artiste multi + separateur "|"  MOYEN       1-2 jours    TERMINE (2026-07-16)
 N3   Decoupage verifie chaines multi-artistes sans separateur BAS 2-3 jours CLOS 2026-08-24 (NO-GO N3.a/N3.b acte 2026-08-14) — N3.0 : ~3-5 vraies collabs espace-collees dans TOUTE la base, signal fort trop faux-positif ; pivote en chantier « Hygiene des chaines d'artistes » LIVRE+DEPLOYE (52544b6, deploy_verify SAIN) : strip bruit au funnel + fold ponctuation/fans matcher Deezer + script cleanup + fix orphelins ; ETENDU au fil de l'eau par le sweep opportuniste 2026-08-24 (77d0cd3->ef3afd2 : resurrection Deezer 180j, cleanup orphelins/placeholders, routage chaines->Flags). CLOS : plus aucun livrable structure restant ; residu hors chantier (cleanup_artists.py au besoin + chaines lettres-espacees deleguees aux flags)
 C7   Entite Album (M2M catalog_albums)     BAS         5-7 jours    TERMINE (2026-08-20 ; 7e02633 + follow-ups f234944/5e6262c/a6b5f77, deploy_verify SAIN) — objet Album 1re classe (migration 0046 : albums + M2M catalog_albums, deezer_album_id partial-unique, AlbumType name==value) peuple fil-de-l'eau au funnel Deezer (upsert + cover bucket album-artworks + top-up release via _check_releases) ; reco/similarite album-aware (de-dup <=1 titre/album, _load_album_map cache, album_id sur CatalogEntryOut) ; album_service.get_detail + GET /api/albums/{id} + AlbumView (/album/:id, hors KeepAlive) + scope recherche album ; OPS scripts/backfill_albums.py (payload/deezer/covers). Follow-ups post-deploy : allowlist /api/albums public (f234944), bucket album-artworks manquant → 0 cover corrige + mode --source covers rattrapage (5e6262c), tuile+courbe monitoring albums (a6b5f77) ; cron VPS quotidien covers 2500/j operationnel (1er run 0 erreur, cron=UTC). 2039 back + 686 front verts
 C8   Fiabilite des sets TrackID            BAS         3-4 jours    TERMINE (2026-08-18 ; 3491d68 + monitoring 879ed09, deploy_verify SAIN) — flag materialise sets.unreliable (migration 0045, ratio ID>=0.8 DOMINANT + source/placeholder secondaire), calcule au funnel import/recrawl ; exclusion sur ~11 sites scoring/affichage (EN PLUS du roots-only) ; backfill OPS applique apres dump (1192 flagges/35843, tous 100%-ID → placeholder inerte, convergent 0/0) + tuile/courbe monitoring ; titres catalog intacts ; 1978 back + 677 front verts
 E2   Analyse audio previews (BPM + Key)    MOYEN       3-5 jours    TERMINE (2026-08-08) — benchmark (BPM GO ~84% gate / KEY NO-GO) + outil local (e49ca04) + label front estime + AUTOMATISATION VPS task nocturne (cce583a+989329c : migration 0043, essentia dans l'image, carte admin) + courbe Monitoring (c2b724f) ; drain 00-03h ~8000/nuit self-tapering, tourne en prod
 C9   Embeddings audio & reco par contenu   BAS         8-12 jours   EN COURS — C9.a socle pgvector deploye (migration 0049, modele EffNet fige) + backfill local ~24% (69k/282k) + monitoring couverture embeddings livre 2026-08-24 ; C9.b endpoint + shelf « sonne comme » LIVRE admin-only 2026-08-24 (public differe) ; C9.c A FAIRE ; moyen/long terme, phases separables ; GATE BENCHMARK C9.0 PASSE 2026-08-21 (GO FRANC) : Discogs-EffNet vs co-occurrence sets, lift@10 cross-artist 32.5x (controle melange 1.1x), kit docs/c9-benchmark/ — C9.a/b/c debloques, C9.d degrade en stretch
 D7   Admin mobile Flags + Lier (design)    BAS         2-3 jours    TERMINE (2026-08-08) — ABSORBE par D4 Vague 5 (perimetre = sous-ensemble strict de la finition responsive mobile livree : 12b7b87 + d212522 + revue design 667ceed)
 D8   Voir-plus contextuels (sous-boites → listes pre-filtrees) BAS 2-3 jours TERMINE (2026-08-17 ; d687b76, deploy_verify SAIN) — D8.a filtre genre back /playlists (dominance >=25%) + /artists (presence >=1 track) + filtre artist_id /sets (SetArtist) ; D8.b chips URL 3 listes + renvois shelves Genre Detail (RouterLink, ExpandableShelf intact) ; D8.c renvois Artist Detail (sets/tracks) ; review adversariale (1 fix layout .artists-grid) ; doc amendee (fiches refonte-ui + genre-detail §5/§3). Smoke prod OK (artists?genre=House 10245/97723, sets?artist_id=1 total 2, 0 erreur logs). Prior : D8.b tracklist livre 2026-08-04 (3574e1d)
 D9   Fluidite de navigation (cache vues + skeletons + prefetch) MOYEN 2-3 jours TERMINE (2026-08-17 ; df310ff, deploy_verify SAIN) — KeepAlive 6 vues listes + reconciliation scroll/lifecycle + prefetch chunk nav ; skeletons Sets/Playlists deja en place (D9.b non-regression) ; 676 tests front verts, eslint clean
 AV1  Quick wins audit 2026-08              HAUT        1-2 jours    TERMINE (2026-08-09 ; a09fafd, deploy_verify SAIN) — 21 items S / 6 lots : fuite Artist Detail M1, admin auto-classify + DLQ, buckets rate-limit + matcher suffixes (radar/feed, sets/search, preview-url, similar), lissage fetchUpTo (cap 3), bump MinIO 3G (Q7), tie-breaks, like_escape, alerte backup + logrotate
 AV2  Dependances backend & gate CI         HAUT        1-2 jours    TERMINE (2026-08-10 ; 50a1e39 + hotfix jinja2 3c0c8b6, deploy_verify SAIN) — jose 3.3→3.5 (pas 3.4 : plafond pyasn1) + multipart 0.0.32 + fastapi 0.141.1/starlette 1.6.0 + requests/curl-cffi/dotenv ; gate pip-audit BLOQUANT (ignore-vuln PYSEC-2025-185/2026-1325) ; nginx 1.29-alpine
 AV3  Perf data & OOM (cache + index + drops) MOYEN     2 jours      TERMINE (2026-08-10 ; 593ab47, deploy_verify SAIN) — cache Redis /similar (Q3a), migration groupee : index Explorer/radar_trends/backlog BPM + drops colonnes mortes (Q5) + retention 13 mois ; I/O sync x5
 AV4  Robustesse workers v2                 MOYEN       2 jours      TERMINE (2026-08-12 ; aad0a07, deploy_verify SAIN) — BeatportHTTPError (outage != attempt) + guard enrich_beatport ; 0 autoretry_for=(Exception,) restant dans workers/tasks ; locks enrich_deezer/crawl_trackid_latest/sync_artists/link_set_artists/backfill + orchestrateur reclassify ; CrawlLogger running visible (A3-07) ; routing enrich x3 ; merge carry-over bpm_analyzed_at ; 1821 tests verts
 AV5  Dette frontend — table partagee       MOYEN       2-3 jours    TERMINE (2026-08-13 ; 43e0302, deploy_verify SAIN) — <TrackTable> = 1 SEULE table virtualisee Explorer/Radar (Radar injecte ses 2 ScoreRing + cold-start par slots #head-extra/#row-extra ; correctif dim disliked des cellules score slottees) ; socle list-table.css ADDITIF Sets/Watchlist (.lt-*, st-*/pl-* gardes) + AddModal partage ; useOpinionOneShot x3 (Artists/Sets/Watchlist) + indicateur « N premiers affiches » sur le plafond 100/200 ; split HubView 4 sections defineAsyncComponent (components/hub/, bundle principal 211,8→192,6 kB = -19 kB + CSS -17 kB) ; M6 table.css @media(hover:none) ; cible DoD <150 kB actee INATTEIGNABLE (plancher ~184 kB = framework + nav omnipresente) ; 653 tests front verts ; verif CDP prod des 4 tables = zero diff visuel ; leve le gel des evolutions de tables
 AV6  Backend archi & suppressions          BAS         1-2 jours    TERMINE (2026-08-15 ; f15b52c, deploy_verify SAIN) — de-engraissement routers : list_sets→set_service, get_backlog→monitoring_service.get_backlog_counters, attach/reject/detach set-flags→set_dedup_service (router=404/audit/commit) ; suppressions Q4 : surface Radar v1 (GET /radar/full, PATCH /{id}/state + /state/batch, DELETE /{id} + fns + 6 schemas ; opinion_sync/UserRadarState intacts), GET /watchlist/, 4 composants front morts (PageHero/RingPct/ScorePill/InLibBadge) ; extraction ADDITIVE list_trends→radar_service ; 0 modele/0 migration, 1898 back + 655 front verts ; recompte doc delegue AV7
 AV7  Doc & tests (cloture serie AV)        BAS         1 jour       TERMINE (2026-08-16 ; b5d736f, deploy_verify SAIN, AUCUN modele/migration) — lot doc CLAUDE.md (9 divergences), /schema_doc post-migration AV3, tests auth callback + upsert RB, catalog_visible external search, LEDGER solde
 N4   Majeurs frontend (vite 8, pinia 4...) BAS         2-3 jours    TERMINE (2026-08-18 ; f436f38, deploy_verify SAIN, front-only, AUCUN modele/migration) — vite 5→8 (bundler Rolldown) + vitest 3→4 + @vitejs/plugin-vue 5→6 (L1), pinia 2→4 + vue-router 4→5.2.0 (L2, surface applicative quasi nulle : stores setup-store, API router/guards inchangee), re-validation rendu CDP 31 captures 0 diff (L3) ; npm audit = 0 (ferme high vite path-traversal + moderate esbuild) ; bundle boot ~190 kB iso AV5 ; 677 tests front verts ; PIEGE plancher Node 22.18 (vue-router 5 tire @babel/generator@8) satisfait par node:22-alpine/setup-node "22"
 C10  Pool similarite precalcule (nightly)  BAS         3-5 jours    CONDITIONNEL — inscrit 2026-08-09 (audit Q3b) : le « fix durable » du pool par requete ; declenche SEULEMENT si les mesures post-AV3 (RSS, latence /similar) restent insuffisantes
 X4   Integrite artiste & liaisons plateforme v2 (reliquats X3) MOYEN 4-6 jours TERMINE (2026-08-12) — inscrit 2026-08-10 (diagnostics /catalog/15952 + artiste « t e s t p r e s s ») : (1) reverify X3 n'a nettoye que les ids PARTAGES → ~73k beatport / ~106k deezer ids UNIQUES pre-X3 jamais revus ; (2) matcher valide contre catalog.artist (plat) != catalog_artists (M2M affiche) — 3670 divergences dont 1664 POST-X3 ; (3) 29101 lignes (~11%) sans lien catalog_artists → artiste non cliquable (fallback texte ArtistLinks) ; (4) recherche non insensible aux espaces → 41 artistes « espaces » introuvables. ORDRE : fix champ/liens AVANT re-drain. Code+outillage des 6 lots LIVRE & deploye 2026-08-12 (fedfee5 X4 + f7b1c19 X4.g + 905a73c X4.h, deploy_verify SAIN x3) ; scripts OPS appliques en prod 2026-08-12 apres dump : resync 2779+1583 flats, backfill 30078 lignes / 10715 artistes, reverify --pre-x3 106106 deezer + 73767 beatport reset ; compteurs integrite retombes (divergence 89 ambigues, sans-lien 8 N3, ids pre-X3 0) ; tuile pre-X3 retiree du monitoring (2f3fc21, nulle par definition) ; drain E1 auto ~7-8j en cours ; residuel delegue N3 (testpress/espaces sans separateur)
 AV8  Robustesse workers/infra v3 (triage Sentry) HAUT  2-3 jours  TERMINE (2026-08-16 ; 45d7731, AUCUN modele/migration) — 4 lots : (1) worker `enrich` OOM/SIGKILL (DIGGY-APP-V/X) → cap conteneur `worker_enrich` 1G->2G ; (2) `reclassify_genres_chunk` hang >1800s (DIGGY-APP-12/15/11) → timeout/item RECLASSIFY_ITEM_TIMEOUT + catch SoftTimeLimitExceeded + chunk 500->200 ; (3) `/api/artists/` DiskFull shared memory (DIGGY-APP-13) → postgres `shm_size: 256mb` ; (4) `crawl_trackid_latest` echecs message vide (DIGGY-APP-D) → CrawlLogger prefixe le type d'exception + exc_info. Fixes code rapides DIGGY-APP-4/10 livres hors AV8 (616b430). 741 tests worker verts. Divergences doc pre-existantes (enrich_catalog_beatport genre_only, routing reclassify enrich, count catalog_artists) deleguees AV7.
 AV9  Drain enrich — deadline interne elapsed BAS       1 jour       TERMINE (2026-08-17 ; 0daada7, deploy_verify SAIN, AUCUN modele/migration) — inscrit le meme jour (triage Sentry) : le signal soft-limit peut etre leve DANS les internals asyncio et avale par le handler du transport (preuve DIGGY-APP-J « Fatal write error on socket transport ») → il n'atteint jamais le catch de la tache, le run continue jusqu'au hard limit 3300s puis SIGKILL (~12 kills/mois, ≤1h de drain perdu chacun, lock TTL auto-heal). Fix = deadline time.monotonic() verifiee entre batches (marge sous le soft limit) sortant par le chemin du catch SoftTimeLimitExceeded existant (flush partiel, stats, release lock) ; cibles : enrich_catalog_beatport + jumelles enrich_catalog (Deezer) / analyze_bpm_previews. LIVRE : garde deadline sur les 3 drains + constantes soft-limit partagees decorateur+garde + stat additive deadline_hit (8 tests). RESTE AV9-03 : resolve DIGGY-APP-T/W/J/V apres ~1 semaine d'observation (runs nocturnes avec deadline_hit, 0 nouvel event T/W/J/V)
 AV10 Throttle CPU Hostinger — plafonner l'analyse BPM   URGENT      1 jour       TERMINE (2026-08-20 ; a9d2e62, deploy_verify SAIN) — inscrit 2026-08-19 : Hostinger a applique une LIMITATION de ressources (fair-use CPU, VPS 4 vCPU) apres surconsommation moyenne. Coupables mesures : dockerd 23.1% (surtout logs worker `--loglevel=info` demuxes en json-file + healthchecks 10s postgres/minio/redis), celery enrich 18.7% (dont analyse BPM Essentia 00h→03h, CPU pur), minio 10.4%. RAM/disque SAINS (12 Gi libres, disque 36%). LEVIER 1 (docker-compose.yml, ce commit) : worker/worker_enrich/beat `--loglevel=warning` + healthchecks postgres/redis/minio 10s→60s → attaque la ligne dockerd, zero perte fonctionnelle. LEVIER 2 (PLAFONNEMENT retenu, PAS « etaler ») : `analyze_bpm_previews` tourne sur un `ThreadPoolExecutor(max_workers=ANALYSIS_BPM_EXECUTOR_WORKERS)` defaut 2 → 2 analyses Essentia en parallele = 2 coeurs epingles 00-03h ; on pose **`ANALYSIS_BPM_EXECUTOR_WORKERS=1`** dans le `.env` VPS (var lue a l'import du worker, `up -d worker_enrich` pour l'appliquer, PAS de deploy de code) → −1 coeur sur le pic nocturne, debit ~divise par 2 (accelerateur optionnel, acceptable), reversible. NB : etaler sur la journee flattene le pic mais ne reduit PAS le total CPU-secondes 24h et percuterait le drain Beatport 6h→23h → ecarte. DoD : dockerd < ~12%, pic BPM a 1 coeur, throttle Hostinger leve, /deploy_verify SAIN. Suite possible si insuffisant : baisser le debit quotidien (`ANALYSIS_BPM_NIGHTLY_BUDGET`) ou espacer le drain Beatport
 D10  Admin — Coherence & socle (URL, IA, audit, actions) MOYEN 3-4 jours TERMINE (2026-08-25 ; 54006fb, /deploy_verify SAIN) — sous-routes /admin/:tab (redirect /admin->/admin/overview, persistance refresh, fallback overview) + IA 8->6 onglets (fusions Flags->Artistes, Beatport->Enrichissement, Crawl+Monitoring+Audit->Observabilite, rendu groupe) + GET /admin/audit-log paginee (admin_audit_log jusque-la write-only) + composant AdminAuditLog + poller generique renomme /admin/artists/sync/status/{id}->/admin/tasks/{id} (pas d'alias) + 3 actions curl-only exposees (reset-beatport a confirmation inline + backfill-multi-artists dans AdminEnrichmentActions ; detach set via « Sets attaches » d'AdminSets) + renvois Apercu remappes. +1 endpoint (106), +2 composants (65). Verif RENDU headless conforme (1 ecart routing corrige). 2173 back + 730 front verts. Prerequis de D11 (desormais debloque).
 D11  Admin — Refonte graphique (design)     BAS         3-5 jours    A FAIRE (inscrit 2026-08-24) — pipeline /refonte_page sur la structure figee par D10 ; habillage homogene (tokens, TrackTable/charts partages), 2 regimes de l'Apercu, responsive mobile. Depend de D10.
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
 X1   Dedup catalog (fusion deezer/beatport) TERMINE (2026-07-22 ; garde same_track, index unique abandonne)
 X3   Fiabilite matching enrichissement      TERMINE (2026-07-22 ; prevention A/B deployee + rollout X3.c applique)
 X2   Explorer — navigation (filtre+scroll)   TERMINE (2026-08-02 ; scroll + filtres URL, Explorer/Radar + 4 grilles)
 D6   Refonte UI listes + Radar + transverses TERMINE (2026-08-06 ; 8 pages + D6.0 Rating + revue design Genre Detail)
 E2   Analyse audio previews (BPM + Key)         TERMINE (2026-08-08 ; benchmark BPM GO ~84% / KEY NO-GO + backfill local + task VPS nocturne self-tapering 00-03h + carte/courbe admin)
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
D6 ─────────> D4 (composants Artwork/TrackCard/SetCard/ScoreRing/PlatformLink livres) — cadrage fige dans docs/refonte-ui/, lancable en parallele de la fin de D4 (Admin)
N1 ─────────> Rien (parallelisable avec tout, priorite basse)

--- revue 2026-07-14 (nouveaux items backlog) ---
P2 ─────────> Rien (lot correctifs front ; P2.a partage la surface Hub avec C7, non bloquant)
N2 ─────────> Rien
C7 ─────────> Rien de bloquant — complementaire de P2.a (Album justifie par reco/linking, pas l'affichage)
C8 ─────────> Rien — touche le moteur de similarite (_load_set_map), pas qu'un filtre d'affichage

--- analyse audio des previews (cadrage 2026-07-31) ---
E2 ─────────> Rien de bloquant (colonnes bpm/key + provenance bpm_source/key_source existantes ; E1/X3 TERMINES) — ordre interne impose : E2.a benchmark AVANT toute industrialisation
C9 ─────────> E2 conseille avant (meme tuyauterie preview→analyse, stack Essentia partagee) ; C2 + C4 TERMINES (moteur co-occurrence a hybrider) ; pgvector = nouvelle dependance infra (extension PG16)

--- voir-plus contextuels (retour usage 2026-08-03) ---
D8 ─────────> Rien de bloquant — s'appuie sur l'existant : filtres URL des listes (X2, useUrlSync/useFilterState) + filtre genres[] d'Explorer (D6 p.1). Amende la fiche genre-detail (tracklist « infinite scroll » → apercu borne)

--- liaisons plateforme v2 (diagnostic 2026-08-10) ---
X4 ─────────> X3 (TERMINE, prevention A/B en place). ORDRE INTERNE IMPERATIF : X4.a (correctif champ artiste) + X4.b (reconciliation) + X4.e (backfill liens M2M) AVANT X4.c (re-drain), sinon le re-scan re-pose les memes mauvais ids. N3 = sous-ensemble de X4.e (decoupage multi-artistes sans separateur). Complementaire de AV4 (workers)
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

#### C6.a.2 — Debit d'enrichissement Beatport (2e passe) — DEPLOYE le 2026-07-19 ; SUIVI CLOS le 2026-08-17 (schema « 2 passes » superseded → drain horaire + page Monitoring)

Mesure prod 2026-07-19 : backlog Beatport actif **33 084** (jamais-cherche **12 359**, tous < 2 j = lag stable ~2 j, PAS en fuite), Deezer sain (0 jamais-cherche). Plafond Beatport ~6000/nuit = rate scrape **0,66 req/s** (pas d'API, throttle anti-ban) x fenetre ~7h ; **~860 tracks/h**, ~2,7 req/track (les 24% d'introuvables partent en fallback release a 3-4 req). Stock eligible/nuit borne (~12k tier-1 ; les 20,7k tier-2 verrouilles 30j). Taux de trouvaille 1er essai = **76%**.

DEPLOYE le 2026-07-19 (f4c7f57 + a5b1859, deploy_verify SAIN — budget prod verifie `deezer 15000 / beatport 6000`, 2e passe presente dans le beat) : (1) `resolve_set_tracks` decouple = liage seul (plus d'enrichissement inline, cf. C6.a.1) ; (2) **budget par-source** Deezer 15000 / Beatport 6000 (compense le decouplage cote Deezer, qui plafonnait Deezer a 6000) ; (3) **2e passe `enrich_catalog_beatport` a 15h** (06h + 15h) → capacite ~12000/nuit au meme rate. Objectif : capacite > inflow → jamais-cherche **decroit vers 0** et n'augmente plus.

A CHECKER chaque jour (`enrich_beatport` dans `/api/admin/crawl-logs` + requete backlog `beatport_id IS NULL AND attempts=0`) :
- passe 1 (06h) : `enriched` / `not_found` / duree
- passe 2 (15h) : `enriched` / `not_found` / duree — **ou tourne a vide** (= 1 passe suffit, l'inflow tient dans 6000)
- backlog jamais-cherche : tendance J+1 → J+3 (doit baisser)

DECISION apres ~3-5 j : passe 2 trouve regulierement du travail ET backlog ↓ → garder ; passe 2 a vide → revenir a 1 passe. Bonus efficacite en reserve si besoin de plus : fallback release plus malin (couper le cout des introuvables) + backoff tier-2 allonge (30j → 60-90j).
- [x] CHECK J+1 (20/07) : **passe1** (06h) = 5201 enr / 799 nf / ~6h24 (budget 6000 SATURE ; nf en baisse nette 1488→1041→799 sur 3 nuits). **passe2** (15h) = EN COURS a l'heure du check (demarree 15h03, ~4h41 de run, lock OK, finit ~21h30 ; stats non committees = invisibles dans crawl_logs, flush-only) — backlog >> 6000 donc **PAS a vide** = signal « garder ». **backlog jamais-cherche = 21 114 (▲ vs 12 359 J0)** — ATTENTION : mesure prise ~17h44 PENDANT la passe 15h (a ~4550/6000), donc PAS un creux propre ; la passe finit ~21h20 en enrichissant ~1150 de plus → creux reel fin de J+1 ≈ **19,7k**. Comparer J+2 a heure equivalente (apres les 2 passes). Cause identifiee, pas une fuite anormale : (a) le decouplage `resolve_set_tracks` (7201s soft-limit → **17s**, gros WIN) redirige ~19-21k resolutions/nuit vers le sweep au lieu de les enrichir inline ; (b) le backfill C6.a.1 tourne toujours (1000 sets/nuit, page 563, cursor 2026-05-25). Inflow catalog mesure = 07-18:10 323 / 07-19:14 057 / 07-20:19 252 → **14-19k/j > capacite 12k/nuit** (2×6000). Conclusion J+1 : la capacite 2 passes NE bat PAS l'inflow tant que le backfill historique n'est pas epuise → le backlog MONTERA encore a J+2/J+3. A surveiller : le n° de page du backfill (plateau = archive epuisee) ET l'inflexion de never_searched une fois le backfill fini. Si never_searched continue de monter APRES epuisement du backfill, il faut AJOUTER de la capacite (3e passe / budget ↑), pas retirer la 2e passe.
- **ACTION 20/07 (soir)** : backfill throttlé **1000 → 200 sets/nuit** (`TRACKID_BACKFILL_SETS_PER_DAY=200` ajouté au `.env` VPS, `diggy_worker` recréé — effet à la run 02:00 cette nuit). Motif : attribution J+1 = **100 % de l'inflow catalog vient des sets TrackID** (0 du radar/releases : radar dispatched=1, playlist inserted=0) ; split ~1025 backfill (fini) / ~592 latest (permanent, EN HAUSSE ~200→620/j sur 12j = saison festivals). À 200/nuit l'inflow total (~10,4k) repasse SOUS la capacité 12k → le backlog jamais-cherché doit **décroître ~1,6k/nuit** tout en laissant l'historique avancer. Décision de calibrer le rythme backfill soutenable APRÈS résorption, en observant le drain réel. **Nouvelle attente J+2/J+3 : backlog en BAISSE** (si toujours en hausse → tracks/set sous-estimé ou latest a encore grimpé → baisser backfill davantage / pause).
- [x] ~~CHECK J+2 / J+3 (21-22/07)~~ **SANS OBJET — suivi CLOS le 2026-08-17.** Le schema « 2 passes 06h/15h » que ces cases surveillaient a ete remplace DES LE LENDEMAIN (2026-07-22, MON, commit d6fd7eb) par le **drain Beatport horaire borne 6h→23h** (`batch_size` 550, no-op quand le backlog eligible est vide) : « passe 2 15h » n'existe plus, d'ou les cases jamais remplies. Le sanity-check crawl/backlogs du 2026-07-31 (consigne CLAUDE.md) a re-mesure l'inflow reel (~12000 tracks/j > capacite Beatport ~9900/j) et corrige `TRACKID_BACKFILL_SETS_PER_DAY` 1000→600 (break-even). Le suivi manuel quotidien est desormais AUTOMATISE par la page admin **`/admin/monitoring`** (`metric_snapshots` horaire : never_tried / total_missing + debit `crawl_logs`). Verif live 2026-08-17 : **0 erreur crawl/48h**, toutes les taches nightly vertes (`enrich_beatport` 34 runs OK/48h, `crawl_trackid_latest`/`backfill_trackid_sets`/`crawl_radar`/`recrawl_incomplete_sets` verts).

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
**Statut : TERMINE (2026-08-21) — code deploye et verifie en prod (664ff41, /deploy_verify SAIN) : `collection_items` tracks-only → polymorphe (5 types track/set/artist/genre/playlist, PK surrogate, AUCUNE FK native = integrite applicative facon user_opinions, item disparu → `missing`) + dossiers prives `collection_folders` (un niveau, FK `ON DELETE SET NULL`) ; migrations 0047/0048 (backfill `item_type='track'` sans perte) ; `catalog_merge` repointe les items track SEULEMENT ; front : `AddToCollectionButton` partage gate auth sur les 5 vues detail, `CollectionDetailView` heterogene, `CollectionsView` arborescence dossiers. 2074 tests back + 710 front verts ; prod : alembic_version=0048, schema polymorphe confirme, 0 perte au backfill.**

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
**Statut : TERMINE (2026-08-08) — page 1 (Track Detail) TERMINEE (2026-07-17, commit 0c47a8c, deployee, /deploy_verify SAIN, checklist humaine validee). Livree via le handoff Claude Design `docs/refonte-ui/handoff-track-detail/` (round 2 acte dans la fiche `docs/refonte-ui/track-detail.md`) : 4 composants transverses crees (Artwork, TrackCard ligne, ScoreRing, PlatformLink — logos PLACEHOLDERS, reliquat roadmap) + refonte TrackDetailView (StatStrip supprimee, stats dans le hero, Decouverte avant « Ou on l'entend », troncatures, glyphes source, Rating retire de la page). +36 tests front (125 verts). Page 2 (Playlist Detail) TERMINEE (2026-07-17, commits ef8505f + FIX bcb3845, deployee, /deploy_verify SAIN, checklist humaine validee, revue design FIX round unique solde : 3 ecarts corriges, 1 clos non-ecart donnee, 1 rejete conforme au brief). La contradiction back de la fiche a ete TRANCHEE en pre-vol et LIVREE en lot 0 : `GET /api/watchlist/{id}` renvoie desormais top_artists/top_genres (caps 6/5, pct), in_lib et artists[] peuples, calcules sur le perimetre `catalog_visible` (etancheite C3) ; + extension ADDITIVE de TrackCard (duree + artistes cliquables, zero regression Track Detail) + refonte PlaylistDetailView (hero cover+infos, bloc « Dans cette playlist » enfin cable, bouton Suivre retire de l'UI — decision produit, mecanisme back conserve —, AdminCard en bas). +35 tests (pytest 1221, vitest 155). Page 3 (Set Detail) TERMINEE (2026-07-19, commits 41e9315 + FIX ef7117f, deployee, /deploy_verify SAIN x2, checklist humaine validee, revue design FIX round unique solde : 5 acceptes / 2 clos non-ecarts / 1 rejete conforme). Livree via le handoff `docs/refonte-ui/handoff-set-detail/` : lot 0 back (bpm/key/duree sur la tracklist, top_genres[] miroir playlist perimetre catalog_visible, NOUVEL endpoint `GET /api/sets/{id}/similar` — moteur C2 agrege au niveau set, cache Redis par (set_id, viewer) TTL 6h + seed cap 12 poses au FIX apres mesure prod 21s → 11,6s froid / 0,12s chaud) + extension ADDITIVE TrackCard « set » (position/timecode/etats id-unresolved, zero regression) + ScoreRing mode pct + NOUVEAU composant SetCard reutilisable (future liste /sets) + refonte SetDetailView (hero immersif floute, StatStrip/RingPct/blocs morts retires, AdminCard conservee). +29 pytest (1250), +66 vitest (221). La moitie « Set Detail » de la verif FIX est SOLDEE par la refonte complete. Page 4 (Artist Detail) TERMINEE (2026-07-20, commits cb88318 + FIX c81b7e3/01548f4/fbbec21/8411317, deployee, /deploy_verify SAIN, verification visuelle headless authentifiee au pixel, revue design 2 rounds soldes : round 1 #1-#4 acceptes = UNE cause racine layout (rangees fr du montage = minmax(auto,1fr), covers 250x250 debordaient et peignaient par-dessus le bloc sous-banner — corrige minmax(0,1fr) + overflow hidden + avatar positionne), #5 accepte (crop 1-rangee ExpandableShelf neutralise par override scoped), #6 rejete → transverse, #7 clos arbitrage, #8 clos donnee ; round 2 : conforme, #9 clos mesure (ring = --surface exact), #10 accepte (dedup genres par libelle visible — troncature StyleTag). Livree via le handoff `docs/refonte-ui/handoff-artist-detail/` : lot 0 back (ArtistSetOut + artists[] noms ordre position + duration_ms, fetch groupe compat SQLite) + refonte ArtistDetailView (hero banner montage cycle/placeholder + stats repliees sans Rating, code mort real_name/country/bio/soundcloud retire, logos PlatformLink avec sentinelle NOT_FOUND masquee, tracks → TrackCard expand 10+N, sets → grille SetCard 4/3/2 footer badge % identifiees, proches polish, aliases, dv-back) — AUCUN composant cree ni etendu (1er chantier D4 dans ce cas). +4 pytest (1254), +23 vitest (244). La verif FIX Artist Detail est SOLDEE par la refonte complete. Vague 5 (Admin) TERMINEE (2026-08-08) : onglet Apercu backlog 12 cartes + badges d'onglets + finition responsive mobile (12b7b87), fix compteur carte « A lier sur Deezer » (d212522), regime « inconnu » DLQ (989329c), revue design C1-C7 soldee (667ceed). D7 (mobile Flags/Lier) ABSORBE — sous-ensemble strict du perimetre livre. D4 CLOS.**

### Taches

- [x] **Verifier FIX appliques** sur Artist Detail et Set Detail — moitie Set Detail SOLDEE par la refonte complete p.3 (2026-07-19) ; moitie Artist Detail SOLDEE par la refonte complete p.4 (2026-07-20, cb88318 + FIX)
- [x] **Track Detail** `/catalog/:id` (brief co-produit avec Claude Design) : Hero + StatStrip + blocs relationnels — TERMINE (2026-07-17, 0c47a8c) ; la StatStrip a finalement ete SUPPRIMEE (stats integrees au hero, decision round 2)
- [x] **Playlist Detail** `/playlists/:id` (brief co-produit avec Claude Design) : Hero square + StatStrip + table tracks — TERMINE (2026-07-17, ef8505f + FIX bcb3845) ; decisions handoff : hero finalement « cover + infos a cote » SANS StatStrip, table remplacee par des rangees TrackCard etendues
- [x] **Vague 5 — Admin panel** `/admin` (brief co-produit avec Claude Design) : Refonte visuelle selon DA Wildflower — TERMINE (2026-08-08, 12b7b87 + d212522 + 989329c, revue design soldee 667ceed)

> La suite de la refonte (Hub, listes, Explorer, page Radar, transverses) est inscrite au chantier **D6** ci-dessous.

---

## D6 — Refonte UI : listes, Radar & transverses

**Priorite : BAS**
**Estimation : 8-12 jours (page par page, chaque page = un livrable deployable via `/refonte_page`)**
**Depend de : D4 (composants transverses livres : Artwork, TrackCard, SetCard, ScoreRing, PlatformLink) — lancable en parallele de la fin de D4 (Admin). Source de verite : fiches FIGEES de `docs/refonte-ui/` (INDEX.md = registre, TRANSVERSE.md = sujets transverses).**
**Statut : TERMINE (2026-08-06) — 8 pages livrees (Explorer/Radar/Hub/Sets/Playlists/Artistes/Genres/Genre Detail) + D6.0 Suppression Rating + revue design Genre Detail soldee (lot correctif 8417615) ; D6.d (/new-releases, Collections liste) hors DoD. Le cadrage etait DEJA FAIT (fiches ✅ figees avec William, revue page par page 2026-07-14). Ce chantier inscrivait a la roadmap le reliquat refonte UI hors pages detail, qui n'etait planifie nulle part (constat 2026-07-20).**

### Objectif

D4 couvre les pages detail (+ Admin). Ce chantier couvre le RESTE du site deja specifie dans `docs/refonte-ui/` : le Hub, les listes (Explorer ex-Catalog, Sets, Playlists, Artistes, Genres), le detail genre, la NOUVELLE page Radar, et les sujets transverses (suppression du Rating, navigation). Hors perimetre (INDEX.md) : Login (laisse tel quel), LoginCallback (flow Safari iOS — ne pas toucher), Design System (vitrine dev-only).

L'ordre interne ci-dessous est indicatif (une page = un livrable) ; seules vraies contraintes : la nav et Radar avant de finaliser les « voir plus » du Hub, et la rangee partagee d'Explorer avant la tracklist de Genre Detail.

### D6.0 — Transverses prealables

- [x] **Suppression du Rating (etoiles Rekordbox) de TOUT le projet** — decision actee (interpretation 100% perso, aucune valeur partagee), inventaire complet dans `TRANSVERSE.md` § Rating : front (CatalogView colonne + tri, ArtistsView/ArtistCard badge + tri + `avg_rating` — les pages detail refondues en D4 sont deja purgees), back (schemas/routers/services catalog + artists, `rekordbox_xml.py` cesse d'importer le champ, drop colonne DB en migration a terme). Feature-first : le back suit. — TERMINE (2026-08-04, commit 1594763, /deploy_verify SAIN) : le front etait deja purge (retraits incrementaux D6.a/D6.c ; seuls 2 commentaires morts nettoyes). L1 purge applicative — retrait de `avg_rating` (detail artiste), les 2 tris `rating.desc()` (top-tracks artiste + related « meme artiste » Track Detail) remplaces par « en-lib d'abord » (`catalog_id.desc().nulls_last()`, deterministe, purge pure sans ponderation avis), champ `TrackImport.rating`, parsing de l'attribut XML `Rating` (`rekordbox_xml`), ecriture a l'import (`import_rb`) et clause `rating` du merge (`catalog_merge`) supprimes. L2 drop colonne (destructif) — `UserTrack.rating` retire du modele + migration 0042 (DROP COLUMN + DROP CONSTRAINT `ck_rating_range`, downgrade symetrique). `server/deezer/sync_checker.py` (outillage local, note Rekordbox brute pour dedup) HORS perimetre. 1559 tests verts, schema doc regenere, CLAUDE.md (42 migrations).
- [x] **Restructuration navigation** (TRANSVERSE.md § Navigation, statut « a travailler ») : entree Radar (sidebar + BottomNav), renommage Catalog → Explorer, cibles « voir plus » du Hub — A CADRER avec William AVANT D6.a (conditionne la place de Radar)
- [ ] (Opportuniste) systeme d'icones SVG unifie (fin des emoji des scopes de recherche) — TRANSVERSE § icones, non bloquant

### D6.a — Explorer (ex-Catalog) + page Radar

Couplees : le mode Radar SORT de CatalogView vers une page dediee (`catalog.md` + `radar.md`).

- [x] **Explorer** : route `/explorer` (redirects `/catalog`, `/tracks`, `/radar`) ; moteur de recherche sur la base brute — filtres riches (BPM range, Key multi-select, Style multi, Artiste type-ahead, In lib tri-state, Duree, Ecoutable, Avis, Annee, Label) SYNCHRONISES dans l'URL ; tri defaut « recemment ajoutes » ; infinite scroll VIRTUALISE (windowing) ; colonne In lib → indicateur cover `<Artwork>` ; colonnes Rating/Radar/Source/Detecte retirees ; imports ranges dans un menu « + » ; libelles FR ; fix du handler inline play — TERMINE (2026-07-21)
- [x] Back Explorer : query-builder `GET /api/catalog/` (bpm range, key[], genre[], artist_id[], duration, has_preview, avis 4 etats, annee, label) + 5 index (bpm, key, duration_ms, release_date, created_at) — `catalog_visible` preserve. Migration 0039. NOUVELLE famille de composants filtres reutilisable (`components/filters/`, 12) + composables `useVirtualWindow`/`useWindowedList`/`useFilterState` — reutilises par Radar. TERMINE (2026-07-21)
- [x] **Radar** : NOUVELLE page = surface de recommandation bi-score — liste unique, chaque son avec scores **Tendance** + **Pour toi** (`ScoreRing` /10, float conserve pour le tri), tri par l'un ou l'autre, filtres facon Explorer, cold-start → tri Tendance par defaut ; `/for-you` FUSIONNE dedans (le « voir plus » Pour toi du Hub pointe ici). ECARTE (fiche) : triage `user_radar_state`, indice « pourquoi », ponderation des likes
- [x] Back Radar : endpoint qui MERGE `trend_score` (radar_trends) + `reco_score` (recommendations C4) par `catalog_id` (union des 2 univers, « — » si score absent), normalisation note /10, filtres, `catalog_visible`

### D6.b — Listes Sets + Playlists (jumelles)

- [ ] **Sets** (`sets-list.md`) : sets a 0 % identifies MASQUES (hard, sans toggle) ; row = cover · titre + artistes · genre deduit (StyleTag) · date · source (logo `PlatformLink`) · % tracks · duree · avis ; passage `usePaginatedList` + sort/pagination server-side. Back : exclusion `identified_tracks == 0`, genres deduits dans `SetListItemOut`, skip/limit/sort
- [ ] **Playlists** (`playlists-list.md`) : aligne sur Sets — logo source, genre dominant deduit (A CONSTRUIRE cote back, meme mecanique que le detail), retrait `external_id`, pastille cadence Quotidien/Hebdo/Mensuel (derivee de `last_changed_at`, C6.e), statut crawl live (`useTaskPoll`) + bouton Crawl conserves, PAS d'exclusion. ECARTE (fiche) : tracks detectees, follow toggle (masque de l'UI, mecanisme back conserve)

### D6.c — Hub + listes Artistes/Genres + Genre Detail (retouches)

- [x] **Hub** (`hub.md`) : « Essaie » deplace sous la search bar, bloc Genres populaires RETIRE, « Ca sort » top 9 + « voir plus » → Radar (invite → login), « Pour toi » top 9 + « voir plus » → Radar, « Nouveautes » « voir plus » → `/new-releases` (actif une fois la page cadree, D6.d), meta `BPM · KEY · age` sur les cards des 3 etageres. Back : `release_date` ajoute a `TrendItem` (`list_trends`) — TERMINE (2026-07-23, commit 74376da, /deploy_verify SAIN) : nouveau composant partage `<DiscoveryCard>` (5 variantes, vitrine DesignSystemView + 15 tests) ; back `release_date` livre sans migration ; « Nouveautes » « voir plus » livre en DESACTIVE « Bientot » (arbitrage William : `/new-releases` = D6.d non cadree → pas de lien mort) ; dropdown de scope unifie SVG + compteurs par type en recherche (recap C1 integre) ; `ActivityAlbumCard` alignee (auto-portante) ; helper `format.relativeAgeShort`. Revue design Phase 5 SAUTEE (choix William, rendu fidele au pilote). Reporte en backlog (aucun chantier cree) : recap C5 (badges « sur N sources » / genre / duree sur les cards)
- [x] **Artistes** (`artists-list.md`) : ArtistCard — badge in-lib overlay retire (stat « In Lib » gardee), rating retire (D6.0), **pastille-TOGGLE « Suivi »** (follow/unfollow depuis la card, coin haut-gauche libere), SegFilter « Rating » → « Suivis ». Back : `following` dans `ArtistListItemOut` + filtre `followed=true` — TERMINE (2026-07-28, commits b0f56a6 refonte + 0c2a97c fix, /deploy_verify SAIN) : pastille cloche filaire→pleine (optimistic follow/unfollow), toggle « Sans Deezer » **admin-only**, In Lib en `--pos-ink` si >0, scrim allege + radial tokenise, container-query 190px, grille 2-col min, empty state « Suivis » dedie ; garde a11y clavier ; retrait `avg_rating`/tri rating page-scoped ; extension additive `usePaginatedList.extraParams`. Retour prod traite : fix pagination (tie-breaker `Artist.id` sur tous les tris — doublons ex-aequo type « Floating Points »). Reporte backlog : nb_liked 3e stat (donnees quasi-nulles)
- [x] **Genres** (`genres-list.md`) : tri « En bib » (SegFilter + back `sort=lib`), GenreCard in-lib en STAT (badge retire, harmonise avec ArtistCard) — TERMINE (2026-07-31, commits b6b8a4f + 83e0ffb revue design, /deploy_verify SAIN) ; le « % de couverture bib » a ete RETIRE au pre-vol (0,1-5 % partout = barre morte), seul le compte in-lib est garde
- [x] **Genre Detail** (`genre-detail.md`) : hero immersif (mosaique agrandie, titre + pilier + stats par-dessus), bouton « Tout filtrer dans Catalog » RETIRE, `GenreTrackRow` bespoke → rangee partagee `<TrackCard>` SANS colonne genre (back : `artists[]` + `avis` sur genre/tracks), Admin gate `is_admin` — TERMINE (2026-08-04, commits 80285ef refonte + 5c945ed fix shelf + 3574e1d tracklist bornee D8.b, /deploy_verify SAIN x3) : lot 0 back additif (artists[] structures + avis canonique), tracklist TrackCard + avis par rangee, migration usePaginatedList, purge orphelins GenreTrackRow/LibDot/StatStrip ; tracklist bornee + « Voir les N autres dans Explorer » (D8.b anticipe). Revue design Phase 5 SOLDEE (2026-08-06, round unique Claude Design) : verdict « implementation fidele », 5 ecarts → 3 acceptes corriges (lot 8417615 : shelves `minmax(0,1fr)` + ellipsis `.sc-sub` = fix debord colonne Playlists mobile ; `fmtNum` sur « Voir les N autres » ; statline Sets/Playlists = totaux de section) + 2 rejetes (compteur RelBlock partage, anneau avatar dark = convention repo). Verifie visuellement (headless avant/apres). **D6 CLOS**
- [ ] Reliquats a solder au passage (deja listes en « Reliquats hors chantiers ») : polish `ExpandableShelf` (libelle/style bouton), logos officiels `PlatformLink` (quand SVG fournis), padding-inline TrackDetailView

### D6.d — A cadrer (fiches NON figees — hors DoD de ce chantier)

- [ ] **`/new-releases`** (nouveautes des artistes suivis, nee du Hub) : fiche 🔲 a discuter — feed heterogene (track crawle / lien externe fallback / set) a gerer proprement
- [ ] **Collections liste + detail** : fiches 🔲 (« a la toute fin », vraie feature a designer) — a cadrer AVEC C5 (Collections v2), meme surface
- [ ] Logo/brand `<BrandLogo>` : long terme DA (TRANSVERSE § Brand), hors chantier

### Definition of Done

```bash
# /explorer : filtres riches URL-synces + scroll virtualise ; plus aucune trace du mode Radar dans CatalogView
# /radar : liste bi-score Tendance / Pour toi triable ; /for-you n'existe pas (fusionne)
# /sets : 0 % masques, genre + logo source, pagination server-side ; /playlists : idem + pastille cadence, sans external_id
# Hub : Essaie sous la search, plus de bloc Genres populaires, top 9 + « voir plus » cables vers Radar / new-releases
# Rating : plus aucune etoile dans l'app (UI + API), l'import XML ne le lit plus
# Chaque page livree via /refonte_page (handoff Design → lots → deploy → revue design → cloture) + verif visuelle headless
```

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

## N3 — Decoupage verifie des chaines multi-artistes sans separateur

**Priorite : BAS**
**Estimation : 2-3 jours**
**Depend de : rien de bloquant (s'appuie sur `ArtistSegmentSplitter` + signal Deezer live, deja livres)**
**Statut : CLOS 2026-08-24 (NO-GO sur N3.a/N3.b acte 2026-08-14) — N3.0 a chiffre le gisement en prod : ~3-5 vraies collabs espace-collees dans TOUTE la base (92k artistes), le signal fort « les 2 segments = artistes locaux lies » est trop faux-positif (« Bill Evans Trio » → « Bill Evans » + « Trio ») → splitter verifie ABANDONNE ; le « gisement » rattache mesure (737) etait un artefact one-shot du backfill X4 (majorite de noms legitimes a laisser). PIVOT LIVRE + DEPLOYE a la place — chantier « Hygiene des chaines d'artistes » (52544b6, deploy_verify SAIN, AUCUN modele ni migration, 1929 tests verts) : (L1) module pur `workers/artist_names.py` — `strip_artist_noise` (liste-blanche PRO + puce « Vinyl • »), `punct_fold_key`, `looks_acronym`, `dominant_by_fans` ; (L2) strip cable au funnel de creation d'artiste (`_resolve_or_create_artist`, `_get_or_create`) ; (L3) helper partage `_matching_deezer_hits` des 2 matchers Deezer = fold ponctuation ADDITIF gate (acronyme + plancher fans) + preference au plus grand `nb_fan` ; (L4) script OPS `scripts/cleanup_artists.py` (dry-run/--apply, 2 passes NOISE+DUPES, merge FK-safe `merge_artist_into`, invariant #4 : auto-merge seulement « 1 lie Deezer + N NULL sans acronyme », reste flagge) ; (L5) `resolve_flag(split)` fan-out AUSSI les `set_artists` de la source (`_fanout_source_links`) — corrige le producteur d'orphelins. RESIDU OPPORTUNISTE HORS CHANTIER (CLOS 2026-08-24 ; pivot hygiene etendu au fil de l'eau, cf. journal de tete) : `cleanup_artists.py` a appliquer au besoin (dump prealable → --apply ; dry-run mesure = 13 rename + 13 merge noise + 16 flats, 52 dupes fusionnes / 576 flags laisses). Les residus « lettres espacees » restent non traites (deja hors N3, delegues au flag).**

### Contexte (audit prod 2026-08-03)

Le backlog admin « Lier a Deezer » (303 lignes) etait constitue a 100% d'ORPHELINS complets
(0 `catalog_artists`, 0 `set_artists`, 0 follow/activity/alias — verifie sur les 5 FK) : nettoye
hors chantier le meme jour (GC 294 lignes > 7 j + le filtre `no_deezer` de `list_artists` exige
desormais un rattachement catalog OU set). MAIS les noms des orphelins revelent un vrai phenomene
amont, non couvert par N2 : des chaines multi-artistes collees par des ESPACES, sans aucun
separateur (« salute Sammy Virji », « Enrico Sangiuliano Charlotte De Witte », « Barry Can't Swim
O'Flynn », « Anyma Future Fred again.. ») que `classify_artist_string` classe forcement `single`.
Idee (William) : tenter des decoupages aux frontieres de mots et les VERIFIER (Deezer + base
locale) pour proposer le split sans le faire a la main.

### N3.0 — Dimensionner (GO/NO-GO)

- [ ] Mesurer le flux reel de chaines espace-collees encore RATTACHEES (catalog/sets) non resolues —
      si c'est du meme ordre que le flux d'orphelins (~2-5/semaine), la file manuelle suffit, NO-GO
- [ ] Elucider le producteur residuel d'orphelins : des fragments (« Mitchell », « Laing »,
      « Jonathan », « The South African » + « Youth Choir ») crees le 2026-08-03 suggerent un chemin
      de split qui cree les tokens puis ECHOUE a les relier (fragilite casse/espacement deja notee
      dans le commentaire N2.a de `resolve_flag`). Corriger le producteur > GC a perpetuite

### N3.a — Generateur de decoupages verifies

- [ ] Cible : artistes non lies RATTACHES, >= 3 mots, aucun separateur connu, recherche Deezer
      full-string deja en echec (regle ampersand existante)
- [ ] Tenter les 2-compositions (et 3-compositions) aux frontieres de mots
- [ ] Hierarchie de corroboration par segment — « le segment existe sur Deezer » est un signal
      FAIBLE seul (Deezer a un artiste au nom exact pour presque tout prenom/mot courant, piege
      mesure le 2026-07-30 sur les separateurs) :
      1. segment = artiste local DEJA LIE (fort)
      2. decoupage UNIQUE couvrant toute la chaine avec TOUS les segments verifies
      3. hit Deezer exact avec plancher de fans (faible, jamais suffisant seul)
- [ ] Juge de paix quand disponible : contributeurs du track Deezer lui-meme (la ligne catalog
      porteuse a souvent un `deezer_id`) — on lit la reponse au lieu de deviner

### N3.b — Proposition, PAS auto-liaison

- [ ] Sortie = flags `space_joined` pre-remplis (tokens + deezer_ids) dans AdminFlags, resolution
      1-clic via `ArtistSegmentSplitter` + signal Deezer ✓/✗ live (tout deja livre cote front)
- [ ] Auto-resolution UNIQUEMENT pour le palier corrobore par les contributeurs du track (optionnel)
- [ ] Invariant #4 (asymetrie de fusion) + decision William 2026-07-30 (duos brandes → flag,
      decision humaine) : un decoupage douteux reste un flag, jamais un split silencieux

### Definition of Done

```bash
# Une chaine espace-collee rattachee ("salute Sammy Virji") genere un flag pre-rempli verifiable en 1 clic
# Aucun split automatique sans corroboration par les contributeurs du track Deezer
# Le producteur residuel d'orphelins est identifie et corrige (ou documente si acceptable)
# N3.0 chiffre le gisement AVANT tout dev de N3.a/N3.b
```

---

## X1 — Dedup catalog (fusion sur deezer_id/beatport_id)

**Priorite : HAUT**
**Estimation : 3-5 jours**
**Depend de : rien de bloquant. A lancer APRES la cloture d'Explorer (D6 p.1).**
**Statut : TERMINE (2026-07-22). Prevention deployee + nettoyage applique : 588 doublons REELS fusionnes, ~5000 groupes distincts (remixes/EP) epargnes. IMPORTANT — design corrige en cours de chantier : les ids plateforme ne sont PAS une identite par enregistrement (Deezer hits[0] non verifie ; Beatport release-fallback), donc l'index unique de X1.a est ABANDONNE et la fusion est gardee par `same_track` (ISRC sinon titre remix-aware). Les sections X1.a/X1.b ci-dessous decrivent l'approche INITIALE, partiellement caduque (voir la Mise a jour 2026-07-22 en tete de document). Suivis : bugs racine d'enrichissement (Deezer/Beatport) + residus deferes (`_crawl_track`, `enrich_single_beatport`).**

### Constat (mesure prod 2026-07-21, corrige 2026-07-22)

La mesure initiale — « 1 749 `deezer_id` sur >=2 lignes, ~1 934 lignes en trop » (+ doublons `beatport_id` non comptes) — **sur-comptait massivement** : elle supposait qu'un id plateforme partage = meme morceau. C'est FAUX (voir Cause racine §2). Apres le garde d'identite `same_track`, les VRAIS doublons etaient **588** (deezer 567 + beatport 21), les ~5000 autres groupes etant des enregistrements DISTINCTS (remixes, titres d'EP) partageant un id. Vrai doublon : « ten » de Fred again.. en 4 lignes (chaines d'artistes variables, meme titre). Contre-exemple NON doublon (meme deezer_id) : « Meridian » vs « Meridian (Julian Muller Remix) ».

### Cause racine (confirmee code + donnees)

Deux niveaux :
1. **Ingestion** — la dedup se fait sur `isrc` (souvent NULL) sinon `normalized_key` (`utils.make_normalized_key`) ; `normalize()` ne canonicalise pas la liste d'artistes (featurings/separateurs variables : `fred again..` / `fred again.., jozzy`), donc le meme morceau arrive en plusieurs lignes.
2. **Identite plateforme non fiable (decouverte 2026-07-22)** — contrairement a l'hypothese initiale, `deezer_id`/`beatport_id` **ne sont PAS une identite par enregistrement** : la recherche Deezer renvoie `hits[0]` non verifie (un remix herite du deezer_id de l'original) et le fallback release Beatport tamponne un seul id sur tous les titres d'un EP. 77% des groupes deezer / 94% beatport partagent donc un id entre morceaux DISTINCTS → fusionner sur l'id plateforme seul detruirait des remixes/versions. Corrige cote enrichissement par le chantier **X3** ; invariant acte dans la memoire projet `catalog-platform-id-identity`.

### X1.a — Prevention (LIVRE, design corrige)

- [x] **Primitive de fusion FK-safe** `workers/catalog_merge.py::merge_catalog_entries` : repointe toutes les FK (`catalog_artists`, `user_tracks` [RESTRICT], `set_tracks`, `radar_tracks`, `radar_trends`, `user_radar_state`, `collection_items`, `artist_activity`) + le pseudo-FK `user_opinions`, unit la metadata (NULL-fill, autorite Beatport bpm/key preservee), supprime la perdante. `pick_canonical` choisit la ligne a garder.
- [x] **Garde d'identite `same_track`** (le point cle, remplace la « cle robuste » jadis optionnelle) : fusion UNIQUEMENT si meme enregistrement — egalite ISRC, sinon titre normalise remix-aware (`normalize_track_title` retire feat./« (original mix) », preserve remix/edit/dub/version). Branche sur les points d'ecriture d'id a l'enrichissement (`workers/catalog_dedup.py`).
- [x] ~~**Index unique partiel** sur `catalog.deezer_id`/`beatport_id`~~ — **ABANDONNE** : les ids ne sont pas uniques par morceau (des enregistrements distincts partagent legitimement un id), un index unique echouerait et interdirait des versions distinctes. Migration 0041 supprimee.

### X1.b — Nettoyage de l'existant (LIVRE — applique 2026-07-22)

- [x] Dump prealable pris avant `--apply` (chiffre + offsite Google Drive).
- [x] `scripts/dedup_catalog.py` : par groupe d'id plateforme, **clusterisation par `same_track`** (clique — ne fusionne jamais a tort a la frontiere ISRC/titre non-transitive) ; seuls les clusters 2+ (vrais doublons) fusionnent, les singletons (remixes/EP) restent intacts. Dry-run par defaut, `--apply` explicite, idempotent.
- [x] Applique en prod : **588 lignes fusionnees** (deezer 567 + beatport 21 apres re-requete), ~5000 groupes distincts epargnes, FK verifiees propres.
- [x] Trend/similarite : recalcul automatique au run nightly (aucun recompute manuel).
- [x] Trim des 66 titres a espace de tete : deja fait par migration 0040.

### Definition of Done — ATTEINTE (design corrige)

```bash
# enrichir vers un id plateforme deja porte par le MEME enregistrement (same_track) => fusion
# enrichir vers un id porte par un morceau DIFFERENT (remix/EP) => pas de fusion, coexistence
# doublons existants (memes enregistrements) fusionnes ; remixes/versions distincts preserves
# PAS d'index unique (ids non uniques par morceau) ; trend/similarite recalcules au nightly
```

---

## X2 — Explorer : etat de navigation (memoire du filtre + scroll)

**Priorite : BAS**
**Estimation : 1-2 jours**
**Depend de : Explorer livre (D6 p.1, 2026-07-21).**
**Statut : TERMINE (2026-08-02) — livre AU-DELA du perimetre initial (Explorer seul). Pilote Explorer : nouveau composable `useScrollRestore` (snapshot `{top,count}` dans `history.state`, restauration au retour) + salve parallele bornee `fetchUpTo` (commits c9bd8c4 pilote / fd63817 salve). Etendu a Radar (c5cae9f) et aux 4 grilles Artistes/Genres/Sets/Playlists (527d613) — ces 4 grilles ne persistaient AUCUN filtre en URL avant (divergence Explorer/Radar) : ajout du composable `useUrlSync` (miroir refs<->URL). Bouton « Retour » des 5 fiches detail factorise en composant partage `BackButton` (vrai `router.back()` + repli liste, 8e47adb). 533 tests front verts, /deploy_verify SAIN. Incident hors chantier au deploiement : `/api/radar/feed` (lourd, ~550 MB/appel) OOM-killait l'api (cap 1 GiB, 2 workers) → 502 sur tout ; fragilite PREEXISTANTE, remede = cap memoire api 1G→3G (dbc550e). Suivi non planifie : adoucir les salves `fetchUpTo` (efficacite). Memoire projet `api-oom-radar-feed`.**

### Objectif

Depuis Explorer, cliquer un son ouvre la fiche detail ; le bouton retour « ‹ Explorer » ramene a `/explorer` SANS les filtres ni la position de scroll. Rendre le retour « la ou j'etais ».

- [x] **Memoire du filtre (#3)** : le retour de `TrackDetailView` (lien statique `to="/explorer"`) doit reporter la query active (via `router.back()` ou en transportant la query). Simple.
- [x] **Restauration du scroll (#5)** : le scroll vit dans `.app-main` (pas la window) => le `scrollBehavior`/`savedPosition` natif de Vue Router ne suffit pas ; restauration custom liee a l'historique (memoriser l'offset du conteneur scrollable a la navigation, le restaurer au retour). Plus couteux.

### Definition of Done

```bash
# Explorer -> fiche detail -> retour : filtres ET position de scroll restaures
```

---

## X3 — Fiabilite du matching d'enrichissement (Deezer / Beatport)

**Priorite : MOYEN**
**Estimation : 3-5 jours**
**Depend de : rien de bloquant. Complementaire de C7 (la moitie Beatport/release peut etre absorbee par la modelisation Album).**
**Statut : TERMINE (2026-07-22) — prevention X3.a (Deezer) + X3.b (Beatport) deployee (bedd997) ; script X3.c `scripts/reverify_platform_ids.py` etendu pour re-deriver le bpm/key beatport-source (15016d0, garde invariant #2) ; rollout `--apply` execute en prod apres dump chiffre : 2779 deezer + 10111 beatport ids effaces + 20212 champs bpm/key nulles, `Remaining suspect groups: 0` verifie (+ dry-run frais + spot-check SQL). Les lignes reparees re-derivent id + bpm/key corrects au re-scan E1 nocturne (drain 1-3 nuits, watch crawl-logs). Correctif de suivi 5de55a1 : la passe deezer reset aussi le `has_preview` obsolete (sinon bouton Play qui 404 sur ~2333 lignes) — prod remediee + script patche/teste, deploye.**
**⚠️ Cloture prematuree (diagnostic 2026-08-10) : deux trous restaient et sont traites en X4 — (1) `reverify_platform_ids.py` ne nettoie QUE les ids PARTAGES (`_duplicate_values`) → les ~73k beatport / ~106k deezer ids pre-X3 a id UNIQUE (mismatch titre-seul) n'ont jamais ete revus ; (2) le matcher valide l'artiste contre la colonne plate `catalog.artist` alors que l'UI affiche `catalog_artists` (M2M) — divergence franche sur 3670 lignes dont 1664 POST-X3, bug encore actif. Ne PAS re-ouvrir X3 : suivi en X4.**

### Objectif

X1 a montre que `deezer_id`/`beatport_id` ne sont pas une identite par enregistrement (77% des groupes deezer / 94% beatport partagent un id entre morceaux DISTINCTS). Cause : l'enrichissement stampe un id sans verifier le match. Impact au-dela du dedup : un remix portant le `deezer_id` de l'original herite de SA cover/preview/duree/ISRC → **metadata erronee affichee** sur le remix/version. Ce chantier corrige le matching a la source pour que l'id pose corresponde reellement au morceau. Garde-fou imperatif : ne pas casser le recall d'enrichissement (mieux vaut ne rien poser que poser un mauvais id — l'entree reste eligible au backoff E1).

### X3.a — Deezer : verification du match

- [x] `_search_deezer_async` / `enrich_entry` (`workers/`) prennent `hits[0]` sans controle. Verifier le candidat avant de stamper le `deezer_id` : correspondance titre (normalisee remix-aware, reutiliser `catalog_merge.normalize_track_title`) et/ou ISRC et/ou duree. Non-match => ne pas poser d'id.

### X3.b — Beatport : fallback release

- [x] Le fallback release de `_search_beatport_async` renvoie un id qui n'identifie pas le bon track d'un EP (un seul id sur tous les titres). Durcir : ne retenir un track de release que si titre/ISRC correspond ; sinon pas d'id. **Affinite C7** : la modelisation Album peut porter proprement l'identite de release et corriger ce point — coordonner si C7 passe.

### X3.c — Reparation de l'existant

- [x] Backfill : re-verifier / re-enrichir les lignes dont l'id a ete pose par un match douteux (metadata potentiellement issue du mauvais morceau). Suspects = les lignes des groupes `same_track`-distincts partageant un id (mesurables via la logique de `scripts/dedup_catalog.py`). FAIT (2026-07-22) : `scripts/reverify_platform_ids.py` (dry-run/`--apply`, idempotent, +reset bpm/key beatport-source) execute en prod apres dump — 2779 deezer + 10111 beatport reset.
- [x] Correctif de suivi (2026-07-22, 5de55a1) : le run `--apply` avait laisse `has_preview=True` (signal Deezer-only) sur les lignes deezer dont l'id etait efface sans source radar deezer restante => bouton Play offert cote front qui repond 404 (`get_preview_url` ne resout que via Deezer). ~2333 lignes remediees en prod (`UPDATE has_preview=false`, still_broken=0 verifie) et la passe deezer de `reverify_platform_ids.py` reset desormais `has_preview` (symetrique au reset bpm/key beatport) + tests. Deploye et `/deploy_verify` SAIN + checklist humaine validee.

### Definition of Done

```bash
# un deezer_id/beatport_id n'est pose que si le morceau trouve correspond (titre/ISRC/duree)
# plus de nouveaux faux positifs d'id plateforme (remix -> id de l'original, EP -> id partage)
# lignes existantes mal-tagguees re-verifiees / re-enrichies
```

---

## X4 — Integrite artiste & liaisons plateforme v2 (reliquats X3)

**Priorite : MOYEN**
**Estimation : 4-6 jours (dont ~7-8 jours de drain Beatport en tache de fond, non bloquant)**
**Depend de : X3 (TERMINE, prevention A/B en place). ORDRE INTERNE IMPERATIF : X4.a + X4.b + X4.e AVANT X4.c. Coordination conseillee avec N3 (decoupage multi-artistes sans separateur, sous-ensemble de X4.e) et AV4 (workers).**
**Statut : TERMINE (2026-08-12) — code+outillage des 6 lots (L1 matcher M2M, L2/L3/L4 scripts resync/backfill/reverify --pre-x3, L5/L6) LIVRE & deploye 2026-08-12 (fedfee5), etendu par X4.g (f7b1c19, recherche Explorer) et X4.h (905a73c, recherche insensible aux espaces sur toutes les surfaces) ; deploy_verify SAIN x3. Scripts OPS appliques en prod 2026-08-12 (dump prealable /root/x4_pre_dump_20260812.sql.gz) : X4.b resync 2779+1583 flats (2 passes — backfill avant resync sinon separateurs `&`<->`,` re-divergent), X4.e backfill 30078 lignes / 10715 artistes, X4.c reverify --pre-x3 106106 deezer (+105287 has_preview) + 73767 beatport (+147441 bpm/key) reset. Compteurs integrite retombes (divergence franche 2860->89 ambigues invariant #4, sans-lien 30086->8 delegues N3, ids pre-X3 ->0) ; tuile pre-X3 retiree du monitoring (2f3fc21, nulle par definition post-reset). Drain E1 auto ~7-8j EN COURS (re-pose les bons ids via matcher corrige) ; residuels assumes : /catalog/15952 a verifier post-drain, 5718 deezer sans searched_at hors perimetre pre-X3, testpress/espaces sans separateur delegue N3. Inscrit 2026-08-10 (diagnostic /catalog/15952 : « Rhythm Of The House » affiche Carl Cox mais l'embed Beatport pointe beatport_id 29099904 = « Rhythm Of The House » d'Ejeca / Alex Culross ; elargi le meme jour par le cas artiste « t e s t p r e s s » : non cliquable + introuvable).**

### Objectif

X3 a pose une validation AVANT stamping (artiste + titre remix-aware) mais a ete cloture « TERMINE » en laissant DEUX trous : l'un dans le nettoyage de l'existant, l'autre encore ACTIF dans le code. S'y ajoutent deux symptomes de MEME racine remontes le 2026-08-10 (les deux representations d'artiste `catalog.artist` plat vs `catalog_artists` M2M ne sont pas maintenues coherentes ni completes) : des artistes non cliquables et des artistes introuvables. Cote utilisateur, l'effet cumule est direct : previews/embeds qui ne correspondent pas au morceau, et artistes qu'on ne peut ni ouvrir ni chercher — ce qui ebranle la confiance dans les donnees. Ce chantier traite l'ensemble et re-derive les lignes concernees. Garde-fou repris de X3 : mieux vaut ne rien poser qu'un mauvais id (l'entree reste eligible au backoff E1).

### Constat (mesures prod 2026-08-10)

**Trou 1 — reliquats pre-X3 a id UNIQUE, jamais inspectes.** `scripts/reverify_platform_ids.py` (X3.c) part de `_duplicate_values` : il ne nettoie QUE les ids partages par 2+ enregistrements distincts (6320 groupes sur 178981 ids distincts). Un mauvais id UNIQUE a une seule ligne — le cas majoritaire d'un mismatch titre-seul — n'est jamais examine. Prod :
- 73767 lignes portent un `beatport_id` dont la derniere recherche est ANTERIEURE au correctif X3 (2026-07-22), dont 73692 avec `bpm_source='beatport'` (BPM derive du mauvais morceau — ex. /catalog/15952 : BPM 132 issu du track Ejeca).
- 106116 lignes idem pour `deezer_id` (105652 avec `has_preview`) → la meme classe de bug touche le bouton Play (preview Deezer), pas seulement l'embed Beatport.

**Trou 2 — le matcher valide contre le MAUVAIS champ (BUG ENCORE ACTIF).** `enrich_beatport_batch` appelle `_search_beatport_async(pool, entry.title, entry.artist, ...)` (`server/workers/enrichment.py`) : la validation artiste porte sur la colonne denormalisee `catalog.artist`. Mais l'UI (`TrackDetailView.vue` → `track.artists`) affiche la relation M2M `catalog_artists`. Les deux ont diverge :
- 3670 lignes enrichies Beatport ont un desaccord FRANC (aucun des deux noms n'est inclus dans l'autre) entre `catalog.artist` et le 1er `catalog_artists` (position 0) ; dont 2006 pre-X3 et **1664 POST-X3** (ce n'est donc pas que du legacy, ca se reproduit).
- 98% (3591/3670) portent un `deezer_id` : le M2M a ete (re)resolu via Deezer (`link_catalog_artist_from_hit` / `link_artists_deezer`) sans re-synchroniser la colonne plate `catalog.artist`.
- Exemple /catalog/15952 : `catalog.artist='Alex Culross'` alors que `catalog_artists`=Carl Cox (artist 1295, deezer_id 3951). Le matcher a « valide » Alex Culross → track Ejeca/Alex Culross, tout en affichant Carl Cox.

**Consequence croisee (justifie l'ordre des lots)** : re-enrichir (Trou 1) SANS corriger le champ artiste (Trou 2) re-posera le meme mauvais id sur ces lignes, puisque l'entree du matcher est elle-meme fausse. D'ou X4.a + X4.b + X4.e AVANT X4.c.

**Symptomes additionnels (meme racine, diagnostic 2026-08-10) :**
- **Artiste non cliquable — 29101 lignes (~11% du catalog).** Elles ont `catalog.artist` non vide mais AUCUN lien `catalog_artists`. `components/ArtistLinks.vue` rend un `RouterLink` par artiste M2M et, liste vide, retombe sur la chaine plate en TEXTE non cliquable (Explorer via `<ArtistLinks>` + Track Detail) → aucun chemin vers la page artiste. Le peuplement M2M depend d'un hit Deezer avec `contributors` (`link_catalog_artist_from_hit`) ou de l'import ; les lignes arrivees autrement (Beatport-only, jamais matchees Deezer, crawl) gardent la chaine plate sans lien. Ex. /artiste « t e s t p r e s s » (id 2613) : 4 titres non/partiellement lies (160095 FLOW, 263547 PEOPLE IN THE BACK, 112328 SHOOT TO KILL, 200230 BOUNCE N BREAK). Sous-ensemble SANS separateur (`t e s t p r e s s Kichta`) = perimetre N3.
- **Recherche artiste aveugle aux espaces — 41 artistes.** Les noms stylises « lettres espacees » (ex. `t e s t p r e s s`, nom Deezer REEL de l'artiste 2613, confirme via l'API) sont introuvables : la recherche fait un match sous-chaine (`ILIKE '%q%'`) et `utils.normalize` ne collapse pas les espaces internes, donc « testpress » (et meme « test ») ne matche rien. La page existe (HTTP 200) mais n'est atteignable que par la forme espacee exacte ou un clic depuis un titre (quand le lien M2M existe).

### X4.a — Correctif code : source de verite artiste unique pour l'enrichissement

- [x] Faire valider l'enrichissement (Beatport `_search_beatport_async` + `beatport/client.py`, Deezer `search_deezer` / `_search_deezer_async`) contre les noms de `catalog_artists` (source de verite affichee), pas la colonne plate `catalog.artist`. Passer la liste des noms M2M (ordonnee par `position`) au matcher, ou reconstruire la chaine depuis le M2M.
- [x] Trancher le statut de `catalog.artist` : (a) champ derive re-synchronise depuis le M2M, ou (b) deprecie au profit du M2M. Attention : `catalog_service.list_catalog` l'utilise pour le tri `sort=artist` et le search `ilike` — tout basculement doit couvrir ces chemins.
- [x] Tests : un morceau dont `catalog.artist` != `catalog_artists` n'obtient pas d'id contre le mauvais nom (Beatport + Deezer, twins sync + async).

### X4.b — Reconciliation donnees catalog.artist <-> catalog_artists

- [x] Confirmer la cause racine (probable : le M2M est mis a jour par la resolution Deezer / l'import sans jamais re-ecrire `catalog.artist`). Documenter le sens de verite retenu.
- [x] Script one-shot (dry-run/`--apply`) qui re-synchronise `catalog.artist` depuis `catalog_artists` (concat ordonnee), ou l'inverse selon (a)/(b). Invariant #4 : sur ambiguite (les deux plausibles), NE PAS trancher automatiquement — laisser tel quel et lister.
- [x] Compteur de controle : requete « lignes a divergence franche » avant/apres (~3670 → ~0 attendu).

### X4.c — Reset cible + re-drain des reliquats pre-X3

- [x] Etendre `reverify_platform_ids.py` (ou nouveau script) pour resetter l'etat de recherche (`*_id`, `*_searched_at`, `*_search_attempts`, bpm/key beatport-source, `has_preview` deezer-stale) des lignes recherchees AVANT 2026-07-22 — PAS seulement les ids partages. Idempotent, dry-run par defaut, DUMP PROD avant `--apply`.
- [x] Lancer APRES X4.a + X4.b + X4.e (sinon re-stamp des mauvais ids / matcher aveugle aux liens fraichement crees). Dimensionnement : ~73k beatport / ~9900/j ≈ 7-8 j de drain horaire ; ~106k deezer sur le sweep nocturne (surveiller la capacite / le rate-limit Deezer). Etaler, suivre via la page Monitoring et les crawl-logs.
- [x] Alternative a evaluer au dimensionnement : ne resetter que le sous-ensemble a divergence franche + un echantillon de controle, plutot que 73k en bloc, pour borner la churn de re-enrichissement.
- [x] Verifier /catalog/15952 corrige (id correct ou vide) — FAIT (2026-08-17, verif prod) : artiste = **Carl Cox** (`catalog.artist` re-synchro + `catalog_artists` 1295/deezer 3951), `deezer_id`/`beatport_id`/`bpm`/`key` VIDES (le BPM 132 herite du track Ejeca a disparu ; `beatport_searched_at` NULL = re-enrichissement E1 a venir, `deezer_searched_at` 08-08 = not-found correctement non-stampe). « id vide » = cas accepte par le check.
- [x] **SUIVI drain E1 → DÉCISION 2026-08-17 : ACCEPT + MONITOR (ne rien throttler).** Verif J+5 : reliquats pre-X3 (`*_id` present + `*_searched_at` < 2026-07-22) = **0/0** (reset complet, aucun re-stamp). Deezer converge (`never_tried` 88785→63808 en 3j ≈ 8k/j → ~7j restants). **Beatport fait du surplace** (`never_tried` ~62-68k plat, `total_missing` ~145k) : capacite ~9900/j **plafonnee en dur** (scrape 0,66 req/s anti-ban, non augmentable) ≈ inflow ~12k/j, et le tiering *never-searched newest-first* défère les ~73k lignes reset (ids bas) derriere l'inflow frais. Le backfill TrackID historique tourne encore (curseur Redis `trackid_backfill_cursor`=2026-04-06, plancher `today-730j`≈2024-08 → **~mois de runway**), donc l'inflow reste eleve longtemps. **Décision : accepter la convergence lente** — (1) aucun bug, les reset affichent VIDE pas faux (invariant #4) ; (2) capacite plafonnee → le seul levier est throttler le backfill = echanger une nicety de fond (couverture vieux sets) contre une autre (BPM back-catalog), zero gain net ; (3) newest-first priorise deja correctement (contenu frais couvert, queue historique deferee = bonne posture discovery). REJETÉ : throttler le backfill (preventif), drain prioritaire order-by id ASC (volerait la capacite plafonnee au contenu frais = mauvaise priorite), allonger le backoff tier-2 (inefficace : reset en tier-1 `never_tried` jamais vide → tier-2 jamais servi). **Signal d'alarme unique** : `total_missing` qui grossit structurellement sans borne sur `/admin/monitoring`. **Revisiter seulement si** la couverture BPM du back-catalog devient un besoin (qualite similarite vieux titres) → alors pauser le backfill un temps puis reprendre.

### X4.d — Observabilite (optionnel)

- [x] Exposer les compteurs « divergence artiste », « lignes a id pre-X3 » et « lignes sans lien catalog_artists » dans `/admin/monitoring` (ou une requete admin) pour suivre la non-regression dans le temps.

### X4.e — Backfill des liens `catalog_artists` manquants (~29101 lignes)

- [x] Script (dry-run/`--apply`, idempotent) qui re-peuple `catalog_artists` depuis la chaine plate `catalog.artist` pour les lignes a M2M vide : split par separateur reconnu (`,`/`&`/`feat`/`ft`/`x`/`vs`/`|`), resolution/creation d'artiste (reutiliser `deezer_enrich._resolve_or_create_artist` + alias), lien avec role/position.
- [x] Sous-ensemble SANS separateur (ex. `t e s t p r e s s Kichta`) : NE PAS deviner le decoupage — deleguer a N3 (decoupage verifie) ou laisser en l'etat et lister a part (invariant #4, erreur vers la separation).
- [x] A executer AVEC/AVANT X4.c : un lien M2M correct est aussi ce que X4.a veut valider — un backfill posterieur au re-drain manquerait la fenetre. Verifier que l'artiste redevient cliquable en Explorer + Track Detail sur les 4 titres testpress cites — FAIT (2026-08-17, verif prod) : artiste **2613 « t e s t p r e s s »** porte `deezer_id=60055992` + **16 liens `catalog_artists`** (dont PEOPLE IN THE BACK, GO INSANE ×2, et la chaine combinee « t e s t p r e s s Kichta » cat.271501) = clicable partout. Le sous-ensemble sans separateur (cat.271501) reste delegue N3 mais est deja lie a 2613.

### X4.f — Recherche artiste insensible aux espaces

- [x] Rendre la recherche (`artist_service.list_artists` filtre `q` + `search_service` / `/search` global) insensible aux espaces internes : comparer une forme « compacte » (`replace(x,' ','')`) cote requete ET cote nom indexe, ou materialiser une cle de recherche compacte. Debloque les 41 noms « espaces » d'un coup.
- [x] Ne PAS renommer les artistes (le nom espace est le nom canonique Deezer, invariant : Diggy reste fidele a la source). Complement ponctuel possible : alias « testpress » sur l'artiste 2613 (mecanisme d'alias existant).

### Divergence doc a corriger (flag)

CLAUDE.md et la roadmap marquent X3 « TERMINE — rollout X3.c applique » sans mentionner que seuls les ids PARTAGES ont ete nettoyes ni le bug du champ artiste. A amender a la cloture de X4 (X3 pointe deja vers X4 ci-dessus ; ne pas re-ouvrir X3).

### Definition of Done

```bash
# l'enrichissement valide contre catalog_artists (source UI) — test Beatport + Deezer, twins sync+async
# 0 nouvelle ligne enrichie POST-fix avec divergence franche artiste sur un beatport_id/deezer_id frais
# catalog.artist re-synchronise (ou deprecie) : divergence franche ~0 apres X4.b
# reliquats pre-X3 reset et en cours de re-drain ; /catalog/15952 corrige (id correct ou vide)
# artiste cliquable partout : 0 ligne servie avec un artiste en texte plat quand un lien est resolvable (backfill X4.e ; sous-ensemble sans separateur explicitement liste/delegue N3)
# recherche « testpress » (sans espaces) trouve l'artiste 2613 ; les 41 noms « espaces » redeviennent trouvables
# CLAUDE.md + roadmap : note X3->X4 posee ; database-schema.md regenere si le statut de catalog.artist change
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
- [ ] (Affinite X3) la modelisation de la release/album peut corriger le fallback Beatport qui tamponne un seul `beatport_id` sur tous les titres d'un EP (source de faux doublons, cf. X3.b) — coordonner si C7 passe avant/avec X3

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
**Statut : TERMINE (2026-08-18 ; 3491d68 + monitoring 879ed09, deploy_verify SAIN) — flag materialise `sets.unreliable` (migration 0045) calcule au funnel import/recrawl (module pur `trackid/reliability.py` = source unique : ratio ID>=0.8 DOMINANT ; secondaire = source_url absent ET placeholder, les deux requis) + exclusion `set_reliable()`/`set_reliable_sql()` sur ~11 sites scoring/affichage (EN PLUS du roots-only) ; PAS d'exclusion recrawl/get_set_detail ; backfill OPS `scripts/backfill_set_reliability.py` applique apres dump (1192/35843 flagges, 128 source_url recuperees, convergent 0/0) ; tuile/courbe « Sets non fiables » sur AdminMonitoring (cle additive payload snapshot_backlogs, 0 migration). Titres catalog intacts. SUIVI OPS non bloquant : URL/md5 placeholder a confirmer + reconcilier semantique source import/backfill avant d'activer le signal secondaire (inerte d'ici la). L'INFO "statut source" ci-dessous reste valable.**

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

## E2 — Analyse audio des previews (BPM + Key)

**Priorite : MOYEN**
**Estimation : 3-5 jours (hors temps de calcul du backfill, qui court en tache de fond)**
**Depend de : rien de bloquant (E1/X3 TERMINES — etat de recherche et provenance deja en place). Ordre interne impose : E2.a (benchmark) AVANT E2.b (industrialisation). Synergique avec C9 (meme tuyauterie preview→analyse).**
**Statut : TERMINE (2026-08-08). E2.a benchmark : BPM GO (~84% gate conf>=2.0) / KEY NO-GO (edma~=shaath, real libkeyfinder le pire), livrable docs/e2a-benchmark/. Industrialisation livree en 2 temps : (1) outil local `worker/bpm_backfill/` (e49ca04, dry-run/--apply via ssh psql, pilote ~170 lignes ecrites) + label front « estime » quand `bpm_source='analysis'` + `bpm_source` expose dans les builders list/detail ; (2) AUTOMATISATION VPS (cce583a+989329c) : task Celery nocturne `analyze_bpm_previews` (queue enrich, drain horaire 00h-03h, batch 2000 ≈ 8000/nuit self-tapering, lock Redis, pas d'autoretry, Essentia hors boucle async via run_in_executor), essentia+ffmpeg dans l'image worker (pin cp313), 12e carte admin Apercu + courbe backlog Monitoring (c2b724f). Migration 0043 (`bpm_analyzed_at`/`bpm_analysis_attempts` = marqueur d'attempt) — DIVERGENCE assumee vs le « aucune migration attendue » du DoD initial : necessaire pour ne pas re-analyser en boucle les low-conf. Tout deploye, deploy_verify SAIN, la task draine en prod (~3000 BPM ecrits la 1re nuit ; backlog ~57,6k decroissant). KEY non ecrite (E2.a NO-GO).**

### Objectif

48 872 entrees catalog (mesure prod 2026-07-31) ont une preview Deezer 30 s mais AUCUN lien Beatport, donc ni `bpm` ni `key` : muettes sur les filtres BPM/Key d'Explorer et Radar. Ce chantier analyse la preview en local (MIR classique) pour deriver un BPM et une key ESTIMES, tamponnes avec une provenance dediee `'analysis'` — sans jamais concurrencer les invariants #2/#3 (une valeur rekordbox/beatport reste prioritaire ; un lien Beatport ulterieur ecrase la valeur analysis).

### Constats (mesure prod 2026-07-31)

- 195 914 entrees catalog ; 137 045 liees Beatport (70,0 %), 175 254 liees Deezer (89,5 %)
- 48 872 entrees `beatport_id IS NULL AND has_preview` — 100 % sans bpm ET sans key
- Verite terrain disponible pour un benchmark : les entrees AVEC bpm/key Beatport ET preview Deezer permettent de mesurer la precision de l'analyse sur NOTRE musique avant tout rollout

### Stack recommandee

- **Essentia** (bindings Python, extracteurs C++, rapide) : `RhythmExtractor2013` pour le BPM + `KeyExtractor` profil **`edma`** (calibre musique electronique). ~1 s / extrait 30 s sur CPU.
- Alternatives a departager au benchmark : librosa (`beat_track`, pur Python, plus simple a installer) pour le BPM ; `libkeyfinder` (algo KeyFinder, reference DJ open-source) pour la key.
- Conversion sortie (« A minor ») → notation Camelot cote worker (jumeau Python de `camelot.js` ; reutiliser la table de correspondance de `beatport/client.py`).
- Execution : CPU-bound, AUCUNE API rate-limitee — soit script local PC (pattern outillage local A7-07) ecrivant via l'API, soit tache Celery throttlee (attention CPU du VPS partage avec Postgres ; queue a trancher, PAS `enrich` qui est dimensionnee pour du rate-limit reseau).
- Preview ~400 KB : telechargement, analyse TRANSIENTE, aucun stockage de l'audio (posture CGU Deezer : le vecteur/la mesure est une donnee derivee, l'audio ne persiste jamais).

### E2.a — Prototype de validation (benchmark, GO/NO-GO)

- [x] Script local : ~500 entrees AVEC bpm/key Beatport ET preview → analyse des 30 s → mesures : ecart BPM (avec repli d'octave x2/÷2 dans une plage plausible 70-180), taux d'accord key (exact + voisins Camelot ±1/relative)
- [x] Seuils GO/NO-GO a fixer et documenter (proposition : BPM >= 95 % apres repli d'octave ; key >= 75 % exact-ou-voisin)
- [x] Le benchmark fige la stack (Essentia seul, ou mix librosa/libkeyfinder) et les parametres

### E2.b — Industrialisation (backfill + fil de l'eau)

- [x] Backfill des ~49k : batch-commit, reprise sur interruption, throttle poli du telechargement des previews (~20 GB au total)
- [x] Provenance : `bpm_source='analysis'` / `key_source='analysis'` ; ne JAMAIS ecraser une valeur rekordbox/beatport/deezer existante ; un enrichissement Beatport ulterieur ECRASE la valeur analysis (hierarchie invariant #3)
- [x] Fil de l'eau : une entree qui gagne une preview sans lien Beatport devient candidate (hook post-enrichissement Deezer ou sweep periodique budgete, pattern E1)
- [ ] AUCUNE migration attendue (`bpm`/`key`/`bpm_source`/`key_source` existent)

### E2.c — Frontend (mineur, optionnel v1)

- [x] Signaler la valeur estimee (ex. tooltip/affichage discret la ou bpm/key sont rendus) — a cadrer ; les filtres Explorer/Radar remontent ces valeurs sans changement

### Definition of Done

```bash
# Benchmark E2.a documente (precision BPM et key mesurees sur ~500 refs Beatport, decision GO/NO-GO tracee)
# Si GO : ~49k entrees porteuses de bpm+key 'analysis', visibles dans les filtres BPM/Key Explorer/Radar
# Aucune valeur beatport/rekordbox/deezer ecrasee ; aucune preview stockee (MinIO intact)
```

---

## C9 — Embeddings audio & reco par contenu (« sonne comme »)

**Priorite : BAS (moyen/long terme)**
**Estimation : 8-12 jours — phases C9.a/b/c livrables SEPAREMENT, C9.d explicitement optionnel/recherche**
**Depend de : E2 conseille avant (installe la tuyauterie preview→telechargement→analyse et la posture CGU) ; C2 + C4 TERMINES (le moteur co-occurrence est le socle a hybrider) ; pgvector = nouvelle dependance infra (extension PostgreSQL 16).**
**Statut : EN COURS — cadre le 2026-07-31. Horizon recherche assume (C9.d). GATE BENCHMARK C9.0 PASSE 2026-08-21 : GO FRANC (lift@10 cross-artist 32.5x, voir docs/c9-benchmark/) — C9.a/b/c debloques, C9.d degrade en stretch. C9.a EN COURS : socle pgvector deploye (migration 0049, modele Discogs-EffNet fige v1) + backfill local des embeddings en salves ~24% (69k/282k previews, relançable) + monitoring couverture embeddings livre 2026-08-24 (1987fa3 : bloc payload embeddings covered/eligible/missing + StatTile % + split du burn-down en 3 graphes thematiques) ; reste backfill jusqu'a ~100% + eval a l'echelle. C9.b LIVRE en mode ADMIN-ONLY 2026-08-24 : Lot 1 back (d3dad75) = endpoint GET /api/catalog/{id}/content-similar (KNN cosine pgvector via comparator EmbeddingVector.cosine_distance, compose avec catalog_visible + cache Redis, [] si seed sans embedding), valide en prod (voisins coherents, diversite d'artistes) ; Lot 2 front (45e4559) = shelf « Sonne comme » sur Track Detail gate admin (v-if auth.user?.is_admin + garde reseau, sans score expose, masque si vide) ; les deux /deploy_verify SAIN. Passage PUBLIC differe jusqu'a couverture embeddings haute. C9.c reste A FAIRE.**

### Objectif

Vectoriser les ~175k previews Deezer (30 s) avec un modele d'embedding audio pre-entraine : chaque track obtient un vecteur encodant son CONTENU sonore (timbre, texture, energie, ambiance). La similarite par contenu complete la co-occurrence C2/C4 : feature « sonne comme » par track, cold-start resolu (un son sans historique de sets/likes est recommandable des son arrivee — LA faiblesse structurelle de la co-occurrence), et reco hybride signal collaboratif x signal contenu (architecture standard des recsys industriels).

### Garde-fous invariants

- Un encodeur audio n'est PAS un LLM : le score de similarite reste un produit scalaire deterministe et reproductible sur des vecteurs stockes — l'invariant #5 (les LLMs ne calculent jamais de score de similarite) n'est PAS viole. L'ecrire noir sur blanc dans CLAUDE.md au lancement pour garder la frontiere nette.
- Meme posture CGU que E2 : analyse transiente, on stocke le VECTEUR (donnee derivee), jamais l'audio.
- Asymetrie de merge (invariant #4) inchangee : l'embedding est un signal de similarite/reco, JAMAIS une preuve d'identite — aucune fusion catalog sur proximite d'embedding.

### Stack recommandee

- **Modele v1 : Essentia Discogs-EffNet** — entraine sur donnees Discogs (taxonomie electronique profonde, 400 styles), CPU-friendly, embeddings 1280-d + tetes de classification genre/mood/danceability en bonus. Coherent avec la brique Essentia de E2.
- Candidats a benchmarker ensuite : **CLAP (LAION)** — espace audio-TEXTE aligne, ouvre la recherche en langage naturel (« dark rolling techno with acid bassline ») ; **MERT** — representation musicale la plus riche, GPU requis.
- **Stockage : pgvector** sur le PostgreSQL 16 existant — index HNSW, requetes de voisinage en SQL qui COMPOSENT avec `catalog_visible` (C3) et les filtres existants. Volumetrie : ~175k x 1280 float32 < 1 GB. Migration Alembic (extension + colonne/table dediee).
- Calcul : backfill en local (PC, GPU si disponible) ou CPU multi-coeurs ; fil de l'eau via tache Celery CPU-bound (queue a trancher — ni `enrich` ni saturer `celery`).

### C9.a — Pipeline embeddings + stockage + evaluation

- [x] Migration pgvector + schema versionne par modele (`model_name`/`model_version` — changer de modele = re-embedder, pas de vecteurs heterogenes melanges) — LIVRE (migration 0049 deployee)
- [ ] Backfill ~175k previews (batch, reprise, throttle) + fil de l'eau post-enrichissement
- [ ] Evaluation quantitative AVANT toute feature : les voisins d'embedding predisent-ils la co-occurrence en sets ? (metrique maison sur NOS donnees — c'est elle qui departage EffNet/CLAP/MERT, pas les benchmarks generiques)

### C9.b — Feature « sonne comme »

- [x] Endpoint voisins par `catalog_id` (perimetre `catalog_visible`, cache Redis, pattern `GET /api/sets/{id}/similar`) — LIVRE (d3dad75 : GET /api/catalog/{id}/content-similar, KNN cosine pgvector)
- [x] Shelf « Sonne comme » sur Track Detail (consomme TrackCard, aucune nouvelle famille de composants attendue) — LIVRE gate admin, sans score (45e4559)
- [ ] (option vitrine) cartographie 2D de la bibliotheque (projection UMAP) — pas prioritaire

### C9.c — Reco hybride

- [ ] Injecter le score contenu comme SECOND axe dans `similarity_service`/`recommendation_service` (ponderation a calibrer ; golden tests d'ancrage comme le fix pooling C4)
- [ ] Cold-start : verifier qu'un son sans historique remonte dans « Pour toi »/Radar via le seul axe contenu

### C9.d — Recherche (long terme, OPTIONNEL — ne bloque aucune phase)

- [ ] Fine-tuning contrastif « mixabilite » : positifs = co-occurrence dans les ~12k sets DJ (signal de supervision quasi unique — des jugements de compatibilite emis par des DJs pros) → l'espace apprend « les DJs les mixent ensemble » plutot que « sonne pareil »
- [ ] (option CLAP) recherche texte→audio dans la bibliotheque

### Definition of Done

```bash
# C9.a : embeddings pgvector en place (schema versionne), eval voisins-vs-co-occurrence documentee
# C9.b : « sonne comme » sur Track Detail, perimetre catalog_visible respecte
# C9.c : reco hybride en prod, ponderation calibree, golden tests verts
# C9.d : hors DoD — objet de recherche, a re-cadrer le moment venu
```

---

## D8 — Voir-plus contextuels : sous-boîtes → pages listes pré-filtrées

**Priorite : BAS**
**Estimation : 2-3 jours**
**Depend de : rien de bloquant — s'appuie sur les filtres URL des listes (X2) et le filtre genres[] d'Explorer (D6 p.1). AUCUNE migration.**
**Statut : TERMINE (2026-08-17 ; d687b76, deploy_verify SAIN — tests verts 1919 pytest / 676 vitest en isole, ruff/eslint/prettier clean). D8.a (filtre genre back + filtre artiste /sets) + D8.b (chips URL + renvois shelves Genre Detail + doc) + D8.c (renvois Artist Detail) livres. Cadrage tranche par William : semantique DOMINANCE >=25% pour /sets (INCHANGE, deja en prod) + /playlists, PRESENCE >=1 track pour /artists ; /sets?artist_id= sur SetArtist (jumeau de la section Sets d'Artist Detail). Review adversariale (6 dimensions + verif sceptique) : 1 VRAI defaut trouve+corrige = grille `.artists-grid` de Genre Detail sans le reset `width:auto` de `ShelfCard` (width:120px fixe -> debordement au palier etroit ; calque de `.cards-grid`). Residus ACCEPTES notes : (a) shelf Artistes = flat `catalog.artist`, destination `/artists?genre=` = `catalog_artists` M2M (destination = source de verite X4, renvoi sans compteur -> pas de N faux ; meme classe d'ecart que /sets presence<->dominance) ; (b) casse : renvois raw `genres.any` vs shelf `resolve_genre` = identique au renvoi tracklist `/explorer?genre=` deja livre (genreName canonique -> matche). Verif RENDU headless CDP de Genre Detail = RECOMMANDEE avant/apres deploy (non faite ici, limite de session ; le fix layout calque un pattern deja en prod). Deploye 2026-08-17 (d687b76), smoke prod OK (artists?genre=House 10245/97723, sets?artist_id=1 total 2, 0 erreur logs api/front). Verif RENDU headless CDP Genre Detail NON faite (limite de session ; le fix layout calque un pattern deja en prod) -> coup d'oeil visuel Genre Detail conseille. Prior : D8.b tracklist livre le 2026-08-04 (3574e1d).**

### Constat (retour usage 2026-08-03)

Sur une page detail, « Voir les N autres » d'une sous-boite APPEND une poignee de cards inline (12 sur les shelves Sets/Playlists de Genre Detail) : la promesse « voir les 4 523 autres » n'est pas tenue, et la tracklist en infinite scroll (15 600 tracks sur le plus gros genre) rend le bas de page (« Genres proches ») inatteignable. Le bon pattern existe deja dans l'app : les etageres du Hub sont des apercus top-9 dont le « voir plus » NAVIGUE vers la page destination (Radar). Une section de page detail est un APERCU ; l'exploration complete appartient aux pages LISTES, qui ont depuis X2 tout ce qu'il faut (filtres persistes en URL, tri, scroll restaure au retour).

Etat des lieux verifie (2026-08-03) : Explorer sait DEJA filtrer par genre (`list_catalog.genres[]`, filtre Style URL-synce) et par artiste (`artist_id[]`) ; les listes /sets, /playlists et /artists n'ont AUCUN filtre genre (le `top_genres` de /sets est un champ d'affichage, pas un filtre). La boite Artistes de Genre Detail a deja une vraie pagination en mode deplie (ExpandableShelf, 48/page) — faux coupable, mais a aligner par coherence.

### D8.a — Back : filtre genre sur les 3 listes (additif)

- [x] `GET /api/sets/` : le filtre genre EXISTAIT DEJA (param `genres` CSV, DOMINANCE >=25% `GENRE_MIN_SHARE_PCT`, cable front depuis D6) → D8.a-sets deja satisfait, laisse INCHANGE (semantique dominance retenue). D8.c y AJOUTE le param `artist_id` (CSV, filtre SetArtist)
- [x] `GET /api/watchlist/browse` : param `genres` (CSV) en DOMINANCE >=25% (jumeau /sets ; `COUNT(DISTINCT catalog_id)` car radar_tracks duplique un catalog_id ; `catalog_visible` DANS la sous-requete, pose avant le count) — NEUF
- [x] `GET /api/artists/` : param `genre` en PRESENCE >=1 track (semi-join `catalog_artists→catalog` via la subquery `id_filter_query`, sur base_query ET id_filter_query, `catalog_visible` inclus) — NEUF ; orthogonal au filtre PILIER (FamilyChips)
- [x] Perimetre `catalog_visible` respecte dans chaque sous-requete ; AUCUNE migration

### D8.b — Front : renvois contextuels depuis Genre Detail

- [x] Chips/etat URL sur les 3 listes : `/sets?genre=X` (deja via le criterion genre existant de SetsView), `/playlists?genre=X` + `/artists?genre=X` (NEUF : `genreFilter` ref + `useUrlSync` param `genre` + `<FilterChip>` standalone + injection `extraParams` ET `opinionOneShot.buildParams`) + chip retirable affichee
- [x] Genre Detail : « Voir les N autres » des shelves Sets/Playlists/Artistes → RouterLink vers la liste pre-filtree (append inline Sets/Playlists + mode deplie `ExpandableShelf` Artistes REMPLACES). Libelle SANS compteur pour Sets/Playlists (destination = DOMINANCE ≠ le compte PRESENCE du shelf → un « N » y serait faux) ; Artistes migre vers une grille locale `.artists-grid` + `<RelBlock>`, le composant partage `ExpandableShelf` reste INTACT
- [x] Genre Detail : tracklist → APERCU BORNE (1 page de 50) + « Voir les N autres dans Explorer » (`/explorer?genre=`) — **LIVRE PAR ANTICIPATION 2026-08-04** (mini-lot post-refonte, scroll infini retire, canal player programmatique preserve)
- [x] Amender la fiche `genre-detail.md` §5 (shelves + tracklist) + §3 (mention « infinite scroll ») ; + blocs additifs D8 dans `sets-list.md` / `playlists-list.md` / `artists-list.md` + `TRANSVERSE.md` (consommateurs du filtre) — FAIT 2026-08-17

### D8.c — Generalisation opportuniste (autres pages detail)

- [x] Artist Detail : grille sets → `/sets?artist_id=` (param `artist_id` neuf cote /sets, filtre **SetArtist** = la relation exacte de la section Sets d'Artist Detail — pas `set_tracks`), tracks → `/explorer?artist_id=` (filtre `artist_id[]` deja supporte, chip nom **hydratee** via `/api/artists/?ids=`) — FAIT 2026-08-17. Semantique SetArtist ASSUMEE : le renvoi sets n'apparait que la ou la section Sets existe (ergo le trou 44/12345 n'est pas un probleme UX)
- [ ] Autres pages au fil de l'eau ; le Hub est deja conforme (top-9 → Radar), les tracklists bornees (Set/Playlist Detail) restent inline

### Definition of Done

```bash
# « Voir les N autres » d'une sous-boite de Genre Detail NAVIGUE vers la liste pre-filtree (chip visible, retirable)
# Tracklist Genre Detail bornee + « Tout voir dans Explorer » ; « Genres proches » atteignable au scroll
# /sets /playlists /artists acceptent ?genre= (URL-synce, catalog_visible)
# Fiche genre-detail.md amendee (apercu borne assume)
```

---

## D9 — Fluidite de navigation (cache des vues + skeletons + prefetch)

**Priorite : MOYEN**
**Estimation : 2-3 jours**
**Depend de : rien de bloquant — front-only, s'appuie sur les composables de liste existants (usePaginatedList/useWindowedList) et useScrollRestore (X2). AUCUN back, AUCUNE migration.**
**Statut : TERMINE (2026-08-17 ; df310ff, deploy_verify SAIN) — front-only, AUCUN modele/migration. 3 lots via /work_manager : (D9.a) `<KeepAlive :include>` des 6 vues listes (`:max=6` ; details jamais caches) + reconciliation scroll/lifecycle (gardes `route.path===ownPath` sur useUrlSync/useFilterState anti-clobber en fond, detach/attach useVirtualWindow, pause/reprise polls Watchlist, useScrollRestore.reapply en onActivated) ; (D9.b) skeletons Sets/Playlists DEJA en place depuis D6 -> lot reduit a la NON-REGRESSION (premisse « blanc/spinner » du brief FAUSSE, signalee) ; (D9.c) prefetch du CHUNK JS au survol/focus nav (router.prefetchRoute + utils/prefetch.js, jamais de donnees -> /radar/feed jamais prefetche). Verif RENDU headless locale (Chrome CDP + seed) : retour Explorer pixel-identique, 0 refetch liste, scroll conserve, prefetch chunk Radar seul, /radar/feed jamais au boot. 676 tests front verts, eslint clean. Inscrit 2026-08-07 (retour William : delai d'affichage a chaque ouverture de page).**

### Constat (retour usage 2026-08-07)

A chaque navigation vers une liste (Radar, Explorer, Sets, Playlists, Artistes, Genres), un delai d'affichage systematique. Diagnostic code : (1) le `<RouterView>` n'est PAS enveloppe dans `<KeepAlive>` (`App.vue`) → Vue DETRUIT la vue quittee et RE-MONTE la cible de zero a chaque aller-retour, et le `onMounted` relance un fetch complet (`RadarView.vue` et jumelles) ; (2) chaque vue attend son aller-retour API avant tout affichage — aucun store ne garde la derniere liste, `usePaginatedList`/`useWindowedList` repartent a `offset:0` a chaque montage ; (3) 1re visite d'une page = telechargement du chunk JS (routes lazy `() => import(...)`, `router.js`) — one-shot, cache navigateur ensuite. Le delai ressenti = surtout le round-trip API (2) a CHAQUE arrivee, maximal sur `/radar` (endpoint le plus lourd, ~550 MB/req, cf. reliquat `api-oom-radar-feed`).

Idee initiale ECARTEE (arbitrage 2026-08-07) : « precharger les 100 premieres lignes de CHAQUE page a l'arrivee sur le site ». Rejetee tel quel — (a) declencher l'endpoint le plus memoire-intensif (`/radar/feed`) a chaque demarrage de session, en salve avec le boot, est exactement le scenario du 502 OOM (incident X2) ; (b) deplace le delai au demarrage au lieu de le supprimer ; (c) fetch 6-7 pages pour 1-2 reellement ouvertes, donnees vite perimees. Les leviers ci-dessous obtiennent le meme benefice sans ces couts.

### D9.a — Cache des vues visitees (KeepAlive)

- [ ] Envelopper le `<RouterView>` dans `<KeepAlive>` pour les vues LISTE (Radar/Explorer/Sets/Playlists/Artistes/Genres) : retour a une page deja ouverte = instantane (0 refetch, scroll + filtres + etat preserves en memoire)
- [ ] Borner le cache (`:include` limite aux listes, ou `:max`) — ne pas empiler les grosses vues (Radar/Explorer) indefiniment en RAM
- [ ] Reconcilier avec `useScrollRestore` (X2) : KeepAlive preserve DEJA scroll + etat nativement → le mecanisme de restauration via `history.state` se simplifie (voire devient redondant) pour ces vues ; garder `onActivated` pour un refresh doux optionnel en arriere-plan si la donnee doit rester fraiche
- [ ] NE PAS cacher les pages detail (`/catalog/:id`, `/artist/:id`, `/set/:id`, `/style/:genre`…) — elles varient par param de route

### D9.b — Skeletons instantanes (perceived-perf)

- [ ] Afficher `<SkeletonGrid>` (composant DEJA existant) des le montage, avant la resolution du fetch — le delai *ressenti* chute meme si l'API met le meme temps ; cheap, zero risque back
- [ ] Generaliser aux vues tableau (Explorer/Sets/Playlists) et grilles (Artistes/Genres/Radar) qui montrent aujourd'hui un blanc ou un spinner

### D9.c — Prefetch au survol/focus du lien de nav (version CIBLEE de l'idee initiale)

- [ ] Au survol (desktop) / focus (clavier) d'un lien Sidebar/BottomNav, declencher le fetch de la page cible — au clic (~200-300 ms plus tard) la donnee arrive deja
- [ ] Ciblage self-limite : SEULE la page que l'utilisateur s'apprete a ouvrir est prefetchee (pas les 6-7 d'un coup) → aucun risque de salve OOM sur `/radar`
- [ ] Optionnel : prefetch du chunk JS de la route au meme evenement (supporte par vue-router)

### Definition of Done

```bash
# Retour sur une liste deja visitee = instantane (aucun spinner, scroll + filtres conserves)
# 1re arrivee sur une liste = skeleton immediat puis contenu (plus de blanc fige)
# Survol d'un lien de nav = fetch anticipe, page quasi-prete au clic
# /radar jamais fetche au demarrage de session (pas de regression OOM)
# Front-only : 0 migration, 0 endpoint touche ; tests front verts
```

---

## Serie AV — audit global 2026-08

> Issue de l'audit `docs/audits/2026-08/` (68 findings uniques : 0 critique, 8 hautes toutes contre-verifiees), arbitree le 2026-08-09 dans `docs/audits/2026-08/DECISIONS.md` (Q1-Q8). Suivi inter-audits : `docs/audits/LEDGER.md` (chaque finding EN ROADMAP pointe son lot AVn).
> **Sequencement : AV1 -> AV2 -> AV3 ∥ AV4 (zones disjointes, parallelisables) -> AV5 -> AV6 -> AV7.**
> Contraintes transverses : AV2 a un ordre INTERNE imperatif (upgrades AVANT gate bloquant) ; AV5 impose un gel des evolutions fonctionnelles des tables listes tant que l'extraction n'est pas faite.

## AV1 — Quick wins audit 2026-08

**Priorite : HAUT**
**Estimation : 1-2 jours**
**Depend de : rien**
**Statut : TERMINE (2026-08-09)**

### Taches

- [x] M1 (A1-01) : filtrer `lib_sub` par `user_id` dans `artist_service.get_detail` (fuite inter-users rb_bpm/rb_key/rb_mytags + in_lib union + doublons) + test jumeau 2 users (pattern test_scope_visibility)
- [x] A3-01 + A3-06 : reparer le dispatch `genre_only` du bouton admin auto-classify (contrat routeur↔tache teste) + supprimer le garde `retries < max_retries` du hook DLQ (echec provoque en staging → carte admin monte a 1)
- [x] A6-02 + M5 (A1-07) : buckets `RATE_LIMITS` pour `/api/radar/feed`, `/api/sets/search`, preview-url, `/similar` (tracks + sets) — respecter l'ordre d'insertion des prefixes
- [x] A4-02 : limiter la concurrence de `fetchUpTo` (12 → 2-3) dans `useWindowedList` ET `usePaginatedList`
- [x] A1-03 : invalidation du cache reco depuis `catalog_service.update_avis` (ou dans `sync_track_opinion`)
- [x] A1-04 : commit manquant de `fetch_playlist_artworks` (has_artwork persiste)
- [x] A1-06 : tie-break id sur les 4 tris de Genre Detail (la part `list_followed` tombe avec AV6)
- [x] A4-03 : facette liked/disliked GenresView — charger toutes les pages avant le filtre client
- [x] A5-02 : canal d'alerte backup (push sur echec du freshness check) + logrotate `/var/log/diggy-*.log` + `--quiet` sur le mirror
- [x] A5-03 (Q7) : MinIO cap 2G→3G + GOMEMLIMIT 2700MiB + commentaire compose corrige
- [x] A6-06 : `like_escape` sur les 6-8 sites LIKE restants (catalog/radar/artist/genre/sets)
- [x] A6-09 : `Depends(get_current_user)` sur `GET /watchlist/{id}/crawl-status`
- [x] A4-08 : `onScopeDispose(clearTimeout)` dans useUrlSync + useFilterState
- [x] A4-09 : echec preview non-503 en mode file → `playNext()` borne au lieu de `close()`
- [x] 2026-07/A1-11 : garde `is_virtual` sur le delete parent de `detach_set`
- [x] A1-11 : logger les 3 excepts muets Deezer admin
- [x] Suppressions simples (Q4) : `TrackIDClient.get_styles`, `DEFAULT_ANALYSIS_BPM_BATCH_SIZE` (ou reference beat), `workers/db.get_session`
- [x] A7-03 : 3 lignes manquantes au triage `server/api/scripts/README.md` (dedup_catalog, reverify_platform_ids, dedup_artists_deezer)
- [x] A5-07 volet 1 : `npm audit fix` (brace-expansion, nanoid, postcss — sans breaking)

### Definition of Done

```bash
# Test 2-users M1 vert ; guest sur Artist Detail : in_lib=False partout, bpm catalogue
# Echec de tache provoque → carte DLQ admin = 1 ; bouton auto-classify lance un run reel
# Salve sur /api/radar/feed et preview-url → 429 ; fetchUpTo max 3 requetes simultanees
# pytest + vitest + ruff + eslint verts
```

---

## AV2 — Dependances backend & gate CI

**Priorite : HAUT**
**Estimation : 1-2 jours**
**Depend de : AV1 (rien de bloquant, mais la serie s'execute dans l'ordre)**
**Statut : TERMINE (2026-08-10 ; commits 50a1e39 + hotfix jinja2 3c0c8b6, deploy_verify SAIN)**

### Taches

- [x] A6-03 (1) : python-jose 3.3.0→3.4.0 + python-multipart 0.0.9→≥0.0.18 (drop-in, tests verts)
- [x] A6-03 (2) : lot fastapi + starlette (≥0.47/1.x selon compat) + requests/curl-cffi/python-dotenv — filet = suite API complete, verifier login OAuth en prod apres deploy
- [x] A5-01 (3) : gate pip-audit BLOQUANT (`needs:` du job deploy + retrait `continue-on-error`) ; avis sans fix (PYSEC-2025-185 si encore la) via `--ignore-vuln` explicites commentes
- [x] A5-06 : pin `nginx:1.29-alpine` (compose + frontend Dockerfile)

### Definition of Done

```bash
# pip-audit vert en CI (ignore-vuln documentes) ET bloquant pour deploy
# python -c "from jose import jwt" + login Google verifie en prod
# 1655+ tests verts sur les nouvelles versions
```

---

## AV3 — Perf data & OOM (cache + index + drops)

**Priorite : MOYEN**
**Estimation : 2 jours**
**Depend de : AV1 (buckets poses). Parallelisable avec AV4 (zones disjointes).**
**Statut : TERMINE (2026-08-10 ; commit 593ab47, deploy_verify SAIN) — perimetre Q3(a) livre ; le pool precalcule (C10) reste CONDITIONNEL hors serie**

### Taches

- [x] A1-02 : cache Redis resultat sur `get_similar_tracks` par (seed_id, viewer) TTL 6h — pattern similar_sets existant ; ne PAS toucher au bareme C2
- [x] Migration groupee : A2-01 (index composite `created_at DESC NULLS LAST, id DESC` en remplacement de ix_catalog_created_at), A2-02 (`ix_radar_trends_family_rank` + `ix_radar_trends_rank_global`), A2-07 (index partiel backlog BPM), + drops Q5 : `catalog.needs_reconciliation`, `catalog.status`, `catalog.origin`, `sets.platform` — declares aux modeles
- [x] A2-06 (Q5) : purge >13 mois de `metric_snapshots` + `crawl_logs` dans `snapshot_backlogs`
- [x] A2-09 : tie-break `DJSet.id.desc()` sur /api/sets/ (la denormalisation track_count reste differee)
- [x] 2026-07/A1-04 : I/O sync restante ×5 (httpx async pour les 2 appels Deezer, run_in_threadpool pour BeatportClient/boucle artworks/upload import)
- [x] `/schema_doc` APRES la migration (MANUAL block purge des lignes needs_reconciliation/status)

### Definition of Done

```bash
# EXPLAIN prod du tri Explorer par defaut = Index Scan (plus de Sort 256k)
# /similar cache-hit < 100 ms ; RSS api stable sous salve de 3 fetchUpTo
# Colonnes droppees absentes du schema doc regenere ; retention active (lignes >13 mois purgees)
```

---

## AV4 — Robustesse workers v2

**Priorite : MOYEN**
**Estimation : 2 jours**
**Depend de : rien (parallelisable avec AV3, zones disjointes)**
**Statut : TERMINE (2026-08-12 ; aad0a07, deploy_verify SAIN) — 7 lots / 9 taches (A3-02/03/04/05/07/08/09/12 + A8-03) ; 0 autoretry_for=(Exception,) restant dans workers/tasks ; nouveaux locks single-instance (enrich_deezer/crawl_trackid_latest/sync_artists/link_set_artists/backfill) + lock orchestrateur reclassify_genres ; CrawlLogger commit la ligne running (runs tues visibles) ; 1821 tests verts, ruff clean**

### Taches

- [x] M2 (A3-02) : `BeatportHTTPError` typee sur non-200 dans les 3 helpers async → catch `errors += 1` SANS `_mark_searched` (miroir exact du fix Deezer ; outage ≠ attempt)
- [x] A3-03 : jumeau `enrich_catalog` Deezer — retirer autoretry, catch SoftTimeLimitExceeded + flush partiel, lock `lock:enrich_deezer` TTL ≥ 9000 (clot la fiche memoire enrich-beatport-autoretry)
- [x] M3 (A3-04) : purge `autoretry_for=(Exception,)` des taches a soft-limit restantes (reclassify_genres_chunk et backfill_multi_artists en priorite) ; retry conserve UNIQUEMENT sur exceptions typees des taches courtes idempotentes — LIVRE AV4 : plus aucun autoretry dans `workers/tasks/`, `reclassify_genres_chunk` porte `soft_time_limit=1800` (pas 16200s : chiffre errone corrige au triage AV7)
- [x] A8-03 : locks SET NX EX sur les 6 taches longues restantes (sync_artists, backfill_multi_artists, crawl_trackid_latest, link_set_artists, reclassify_genres_chunk + enrich_catalog via A3-03)
- [x] A3-05 : clause-guard `except SoftTimeLimitExceeded: raise` dans les boucles par-item de recrawl_incomplete_sets + crawl_trackid_latest (pattern backfill) + catch niveau tache
- [x] A3-07 : CrawlLogger — commit de la ligne `running` au `__enter__`, `__exit__` = UPDATE (transactions courtes, runs tues visibles)
- [x] A3-08 : routes `enrich` pour sync_artists, backfill_multi_artists, reclassify_genres_chunk — LIVRE AV4, confirme dans le code (`celery_app.py` `task_routes` : les 3 sont bien `{"queue": "enrich"}`)
- [x] A3-09 : merge_catalog_entries reporte bpm_analyzed_at/bpm_analysis_attempts
- [x] A3-12 : backfill_multi_artists — commit hors gather (chunks pattern fetch_artist_artworks)

### Definition of Done

```bash
# 0 autoretry_for=(Exception,) sur tache a soft-limit ; 16/16 taches longues lockees
# Vague de 403 Beatport simulee → errors comptes, AUCUN beatport_searched_at stampe
# Run tue (SIGKILL) → ligne crawl_logs 'running' orpheline visible dans l'admin
```

---

## AV5 — Dette frontend : table partagee + Hub

**Priorite : MOYEN**
**Estimation : 2-3 jours**
**Depend de : AV2 (serie) ; GEL des evolutions fonctionnelles des tables listes d'ici la (Q6)**
**Statut : TERMINE (2026-08-13 ; 43e0302, deploy_verify SAIN) — 5 lots : A4-01 (<TrackTable> = 1 seule table virtualisee Explorer/Radar, Radar injecte ses 2 ScoreRing + cold-start par slots, windowing/scroll-restore gardes par la vue via defineExpose(bodyEl) ; correctif : dim disliked des cellules score slottees re-declare cote RadarView) ; A4-04 (socle list-table.css ADDITIF + AddModal partage, helper de tri NON extrait car modeles d'etat incompatibles) ; A4-05 (useOpinionOneShot x3 + indicateur « N premiers affiches » sur le plafond 100/200) ; A4-06 (split HubView 4 sections defineAsyncComponent, bundle 211,8→192,6 kB, -19 kB) ; M6 (table.css @media(hover:none) + @container). Cible DoD <150 kB actee INATTEIGNABLE (plancher mesure ~184 kB meme en Hub 100% lazy = framework + nav omnipresente). 653 tests front verts, verif CDP prod des 4 tables = zero diff visuel. Leve le gel des evolutions de tables (debloque N4). Reliquats notes hors chantier : cellule avis Sets = code mort .st-cell--avis pre-existant ; cible <150 kB a reviser (AV7)**

### Taches

- [x] A4-01 : extraire la table virtualisee partagee Explorer/Radar (thead trie + rows + paliers container-query + wiring windowing/scroll-restore) — Radar n'ajoute que ses 2 ScoreRing et son tri defaut
- [x] A4-04 : etendre l'extraction a Sets/Watchlist (ou a minima blocs verbatim : thead, socle CSS, modal add)
- [x] A4-05 : helper `useOpinionOneShot` partage ×3 + traitement du plafond silencieux 100/200 (« N premiers affiches » si total > items)
- [x] A4-06 : split HubView — sections lazy sous le fold (defineAsyncComponent), mesure vite build avant/apres (recurrence 2026-07/A4-09, cliquet verifie 211,6 kB)
- [x] M6 (A4-10) : bloc opacity de table.css → `@media (hover: none)` (bouge avec l'extraction)

### Definition of Done

```bash
# Verif RENDU CDP (pipeline verif-visuelle-headless) sur Explorer/Radar/Sets/Playlists : zero diff visuel
# 1 seule implementation de la table triable virtualisee ; bundle principal < 150 kB (mesure)
# vitest verts (suites des 4 vues + nouveaux composants)
```

---

## AV6 — Backend archi & suppressions

**Priorite : BAS**
**Estimation : 1-2 jours**
**Depend de : AV4 (admin.py touche par A3-01) ; decisions Q4 actees**
**Statut : TERMINE (2026-08-15 ; f15b52c, deploy_verify SAIN)**

### Taches

- [x] A1-05 (Q4) : supprimer la surface Radar v1 — GET /radar/full, PATCH /{id}/state, PATCH /state/batch, DELETE /{id} + list_full/update_state/batch_update_state/add_track + leurs tests (UserRadarState et opinion_sync INTACTS)
- [x] 2026-07/A1-07 (Q4) : supprimer `GET /api/watchlist/` + reecrire les tests follow sur /browse
- [x] A1-08 : extraire `set_service.list_sets` (dominance genre reutilisable), `monitoring_service.get_backlog_counters`, `radar_service.list_trends` — mouvement mecanique, zero changement de comportement
- [x] 2026-07/A1-10 : deplacer attach/detach dedup sets dans `set_dedup_service` (router = 404/audit/commit)
- [x] A4-07 (Q4) : supprimer PageHero.vue, RingPct.vue, ScorePill.vue/InLibBadge.vue + leurs sections DesignSystemView

### Definition of Done

```bash
# Routers sets/admin/radar delegent aux services ; grep des endpoints supprimes = 0 hit front
# pytest + vitest verts ; compteur composants CLAUDE.md mis a jour en AV7
```

---

## AV7 — Doc & tests (cloture serie AV)

**Priorite : BAS**
**Estimation : 1 jour**
**Depend de : AV3 (migration faite → /schema_doc), AV6 (suppressions actees → compteurs)**
**Statut : TERMINE (2026-08-16 ; b5d736f, deploy_verify SAIN, AUCUN modele ni migration) — CLOT LA SERIE AV. 5 lots : (A6-05) `search_external`/`_match_catalog` scopes par `catalog_visible(user_id)` (le router GET /search/external threade `_uid(user)`) — une recherche externe ne divulgue plus l'EXISTENCE d'une ligne privee d'autrui ; le lookup dedup de `import_external` reste DELIBEREMENT non scope (invariant #4, doc d'integrite ajoutee) ; (A3-11) commentaires periemes backfill 1000/visibility_timeout rafraichis (prod 600) ; (A6-07) 3 tests branches `google_callback` (google_failed, collision username, picture update) ; (A6-08) test PG-only de l'upsert import RB (insert->update->refresh, compteurs, base jetable dediee, skipif non-PG) ; lot DOC = recompte mecanique CLAUDE.md (endpoints 100->99, modules `tasks/` 8->10, classes 31->28 tables/33 defs, composants 65->61 reconcilie) + 8 divergences qualitatives (image worker ~852 Mo, primitive reco C4 = load_similarity_context+load_candidate_pool+prives, invariant #1 re-scope serveur/`relocate_tracks`, `uq_artists_deezer_id` porte par migration 0034 + modele, localhost:8080 vs Q6, chemins `scripts/`) + fixes ROADMAP AV4 (9 cases cochees, `16200s`->`soft_time_limit=1800`, routing `reclassify_genres_chunk`->`enrich`). LEDGER solde : 75 lignes EN ROADMAP -> CORRIGE, plus AUCUNE ligne EN ROADMAP sur la serie AV. schema doc regenere (reordonnancement d'index cosmetique). 1912 tests backend verts (+4), ruff clean.**

### Taches

- [ ] Lot doc CLAUDE.md (9 divergences) : A7-01 (compteurs tasks/composables/classes/tests), A5-04 (image ~850 Mo, pas 312), A5-05 (localhost:8080 vs Q6), A8-01 (invariant #1 re-scope : relocate_tracks = exception locale assumee), A8-05 (uq_artists_deezer_id porte par 0034), A1-09 (primitives reelles de la reco), A3-11 (commentaires backfill 1000 + visibility_timeout), A7-04 (chemins server/api/scripts/)
- [ ] A6-05 : `catalog_visible` dans `external_search_service._match_catalog` + documenter l'exception d'integrite du lookup dedup d'import_external
- [ ] A6-07 (2026-07/A6-14) : 3 tests branches google_callback (google_failed, collision username, picture update)
- [ ] A6-08 (2026-07/A6-08) : test PG-only de l'upsert import RB (import → re-import → compteurs corrects)
- [ ] LEDGER : solder les lignes AV livrees (statut CORRIGE + commit) — cloture de la serie

### Definition of Done

```bash
# CLAUDE.md exact (compteurs re-verifies mecaniquement) ; schema doc regenere sans drift
# Upsert PG teste en CI ; branches callback couvertes
# docs/audits/LEDGER.md : plus aucune ligne EN ROADMAP sur la serie AV
```

---

## N4 — Majeurs frontend (vite 8, pinia 4, vue-router 5, vitest 4)

**Priorite : BAS**
**Estimation : 2-3 jours**
**Depend de : AV5 (l'extraction de la table partagee reduit la surface a re-valider)**
**Statut : TERMINE (2026-08-18 ; f436f38, deploy_verify SAIN, front-only, AUCUN modele/migration) — inscrit 2026-08-09 (audit 2026-08, decision Q8). 3 lots serie via /work_manager. vue-router 5 s'est revele un virage d'archi (18 deps runtime unplugin/chokidar/@babel/generator tree-shakees, plancher Node releve a 22.18) plus lourd qu'un majeur de routine — arbitrage William : on adopte 5.2.0. Bundle boot iso AV5, 0 vuln, 677 tests verts, rendu CDP 0 diff.**

- [x] Lot 1 : vite 5→8 (bundler Rolldown) + vitest 3→4 + @vitejs/plugin-vue 5→6 (ferme la high vite path-traversal `.map` + la moderate esbuild du dev-server)
- [x] Lot 2 : pinia 2→4, puis vue-router 4→5.2.0 (aucun ajustement d'API : stores en setup-store, createRouter/guards/RouterLink inchanges)
- [x] Re-validation rendu CDP local 31 captures (Explorer/Radar/Hub/details, light+dark, desktop+mobile) 0 diff + navigation D9 (KeepAlive 0 refetch, prefetch chunk, /api/radar/feed absent au boot) ; `npm audit` = 0

---

## C10 — Pool similarite precalcule (nightly)

**Priorite : BAS**
**Estimation : 3-5 jours**
**Depend de : AV3 (palliatifs Q3a livres + mesures)**
**Statut : CONDITIONNEL — inscrit 2026-08-09 (audit 2026-08, decision Q3b). NE SE DECLENCHE QUE si les mesures post-AV3 (RSS par requete, latence /similar et /radar/feed) restent insuffisantes. Le « fix durable » deja note dans RecommendationConfig : pool de candidats construit 1×/nuit au lieu d'une materialisation ~256k lignes par requete. Ne PAS toucher au bareme C2 (invariant #5 : jamais de LLM dans le scoring).**

---

## AV8 — Robustesse workers/infra v3 (triage Sentry 2026-08-16)

**Priorite : HAUT** (portee par l'OOM worker enrich)
**Estimation : 2-3 jours**
**Statut : TERMINE (2026-08-16 ; 45d7731, AUCUN modele/migration) — inscrit 2026-08-16 (triage /sentry_triage sur les 17 issues prod non resolues). 4 items robustesse/infra livres (741 tests worker verts, ruff clean, `docker compose config` OK). Les fixes code rapides (DIGGY-APP-4 quota Deezer, DIGGY-APP-10 race ObjectDeletedError) livres SEPAREMENT (616b430, hors AV8).**

Source : issues Sentry prod (org `diggy-music`, projet `diggy-app`, region `de.sentry.io`). Dashboard : https://diggy-music.sentry.io/issues/?project=diggy-app

- [x] **AV8-01 (HAUT) — Worker `enrich` OOM/SIGKILL** [DIGGY-APP-V 1814 events + DIGGY-APP-X 1794 (WorkerLostError, meme racine), last seen 2026-08-14]. Le worker `diggy_worker_enrich` (`-Q enrich -c 2`) est OOM-kille (signal 9) sans `--max-memory-per-child` (le worker `celery,crawl` en a un a 1,5 Go). Le hotfix monitoring 080d34b traite le symptome (trous silencieux), PAS la cause. → identifier la tache memoire-lourde (suspects : `analyze_bpm_previews`/Essentia, `enrich_catalog_beatport`), ajouter `--max-memory-per-child` au worker enrich et/ou relever le cap conteneur ; mesurer le RSS par tache.
- [x] **AV8-02 (MOYEN) — `reclassify_genres_chunk` hang >1800s** [DIGGY-APP-12 537 events depuis 2026-08-10, + echos chord DIGGY-APP-15 / DIGGY-APP-11]. Des chunks de 10 ids restent bloques au-dela du `soft_time_limit=1800` (event loop en `selector.poll` idle) → SoftTimeLimitExceeded propre (l'autoretry-loop est deja regle par AV4). → investiguer l'I/O bloquant dans `_async_reclassify`, ajouter un timeout par item + chunks plus petits ; CONFIRMER si un run manuel `reclassify_all_genres` est encore en cours (tache pas au beat).
- [x] **AV8-03 (MOYEN) — `/api/artists/` DiskFull shared memory** [DIGGY-APP-13, 500 utilisateur]. La requete `unnest(catalog.genres) + group by` sur `catalog_artists x catalog` de `artist_service.list_artists` fait echouer un resize de segment shared memory PG a 8 Mo (`/dev/shm` tmpfs sature). → soit relever `shm_size` du conteneur `postgres` (docker-compose), soit borner/optimiser la requete (le contournement « >32767 params »).
- [x] **AV8-04 (BAS) — `crawl_trackid_latest` echecs a message vide** [DIGGY-APP-D, 46 events, ~1/j]. Le `CrawlLogger` logue « failed after 261027ms: » avec `str(exception)` VIDE → cause racine non capturee. → instrumenter le `CrawlLogger` pour capturer le type + la trace de l'exception racine avant tout fix.

**Divergences doc reperees au triage — RESOLUES AV7 (2026-08-16)** : (a) la case M3 (A3-04) plus bas est desormais `[x]` — le code n'a plus d'autoretry et porte `soft_time_limit=1800` (le « 16200s » etait errone, corrige) ; (b) A3-08 : `reclassify_genres_chunk` EST bien route vers la queue `enrich` dans le code (`celery_app.py` `task_routes`, case A3-08 cochee) — l'observation d'un run sur `celery,crawl` etait un artefact anterieur au deploiement du routing, plus d'actualite.

---

## AV9 — Drain enrich : deadline interne elapsed (triage Sentry 2026-08-17)

**Priorite : BAS** (perte de runs + bruit Sentry recurrent, aucune corruption de donnees)
**Estimation : 1 jour**
**Statut : TERMINE (2026-08-17 ; 0daada7, deploy_verify SAIN, AUCUN modele/migration) — AV9-01/02/03 tous livres ; AV9-03 SOLDE le 2026-08-18 apres observation J+1 (constate : 22 runs `enrich_beatport` en success post-deploy, 0 nouvel event DIGGY-APP-T/W/J/V depuis le 08-14, aucune nouvelle ligne crawl_logs figee `running` ; `deadline_hit=0` car backlog draine → garde pas encore sollicitee mais famille de crash eteinte). Inscrit 2026-08-17 (triage /sentry_triage, seul reliquat VIVANT du lot : les 11 autres issues du triage sont resolues avec leur commit en commentaire d'activite Sentry). Les 4 issues DIGGY-APP-T/W/J/V sont desormais `resolved` (via /sentry_triage le 2026-08-18, commit 0daada7 en commentaire ; rouvrent si recidive).**

Source : issues Sentry prod (org `diggy-music`, projet `diggy-app`). Dashboard : https://diggy-music.sentry.io/issues/?project=diggy-app

**Mecanisme prouve** (event DIGGY-APP-J du 2026-08-13) : `SoftTimeLimitExceeded` est levee par le signal billiard PENDANT `asyncio/selector_events._write_sendmsg` et capturee par le handler d'erreur du transport asyncio (« Fatal write error on socket transport », logger=asyncio, handled=yes) — elle n'atteint JAMAIS le `except SoftTimeLimitExceeded` de la tache. Le run continue jusqu'au hard limit 3300s (DIGGY-APP-T, 12 events) → billiard tue au SIGKILL (DIGGY-APP-W TimeLimitExceeded + DIGGY-APP-V SIGKILL process-exit, trace partagee constatee le 2026-08-14 05:55). Cout par kill : le travail non commite du run est perdu + `lock:enrich_beatport` orphelin ≤1h (TTL 3900s auto-heal, invariant OK). Le catch SoftTimeLimitExceeded pose en 21d0a7f/AV4 reste necessaire mais pas suffisant : il ne fonctionne que si le signal atteint le code de la tache.

- [x] **AV9-01 — `enrich_catalog_beatport`** : capturer `time.monotonic()` en debut de run ; entre chaque batch/item, si elapsed > soft_time_limit − marge (~120s), sortir par le MEME chemin que le catch `SoftTimeLimitExceeded` existant (stats hoistees, flush partiel, retour succes, release lock au finally). Ne REMPLACE pas le catch (defense en profondeur), le double d'une garde qui ne depend pas de la livraison d'un signal.
- [x] **AV9-02 — jumelles a drain long sur asyncio** : meme garde sur `enrich_catalog` (Deezer 05:00) et `analyze_bpm_previews` (00h-03h). Meme pattern, meme marge.
- [x] **AV9-03 — cloture Sentry** : apres deploy + /deploy_verify SAIN, resolve DIGGY-APP-T/W/J/V (re-run /sentry_triage pour poser les statuts). FAIT 2026-08-18 : les 4 issues passees en `resolved`.

Invariants : pas d'autoretry, locks inchanges (TTL > time_limit), la sortie deadline ne stampe RIEN sur les entrees non traitees (un run ecourte n'est pas une tentative E1).

---

## D10 — Admin : Coherence & socle (fonctionnel + wiring)

**Priorite : MOYEN**
**Estimation : 3-4 jours**
**Depend de : rien de bloquant. Prerequis de D11 (le design habille une structure figee).**
**Statut : TERMINE — 2026-08-25 (54006fb, /deploy_verify SAIN). Front + back, AUCUN modele ni migration. Cadre via /work_manager (4 lots L1 back + L2/L3/L4 front, tous valides ; 1 micro-correctif routing en cloture). Verif RENDU headless locale conforme (6 onglets, routing/refresh/fallback, garde-fou reset, section Sets attaches, table Audit log, renvois Apercu). 2173 back + 730 front verts, ruff/eslint clean.**

### Constat (inventaire 2026-08-24)

L'admin = 1 seule route `/admin`, **8 onglets** montes en `v-if` (`activeTab = ref('overview')`, AdminView.vue), **zero URL, zero persistance** : refresh (F5) ramene toujours sur Apercu, aucun onglet n'est bookmarkable/partageable. Au-dela de l'URL, l'inventaire a releve de la dette de coherence reelle :
- **Renvois trompeurs de l'Apercu** : les cartes « DLQ » / « Playlists dues » renvoient vers l'onglet **Crawl** (qui n'affiche qu'un historique de logs, ni DLQ ni file des dues) ; « Deezer a enrichir » / « BPM a analyser » renvoient vers **Monitoring** (lecture seule, aucun bouton d'action).
- **Asymetrie attach/detach sets** : `attach` a un bouton UI, son inverse `detach` est **curl-only**.
- **3 actions curl-only** sans surface UI : `POST /admin/reset-beatport` (**DESTRUCTIF**, wipe global Beatport, aucun garde-fou hors `require_admin`), `POST /admin/artists/backfill-multi-artists`, `POST /admin/sets/{id}/detach`.
- **Vue audit log manquante** : 8+ actions ecrivent dans `admin_audit_log` (merge artiste, reset beatport, attach/reject flags, remove set artist, merge/rename genres) mais **aucune route ne lit cette table** — journal write-only, invisible.
- **Nommage trompeur** : `GET /admin/artists/sync/status/{task_id}` est le poller **generique** de TOUTES les taches Celery, pas juste les artistes.
- **Deux notions de « flags »** (artistes vs sets) sur deux onglets ; actions d'enrichissement dispersees (Apercu + onglets dedies).

### Nouvelle architecture d'onglets (6, validee 2026-08-24)

Regroupement par domaine fonctionnel (8 -> 6) — chaque fusion resout un irritant :
- **Apercu** : dashboard backlog (reste le point d'entree ; renvois **corriges** vers les vraies cibles).
- **Artistes** : liaison Deezer + sync + artworks **+ flags/splits artistes** (absorbe l'onglet **Flags** ; fin de la confusion « 2 notions de flags »). `ArtistSegmentSplitter` reste partage.
- **Sets** : set-flags dedup (attach **+ detach** expose) + liaison artistes de sets.
- **Genres** : reclassify + mappings taxonomie (inchange, deja coherent).
- **Enrichissement** : Beatport batch (absorbe l'onglet **Beatport**) + Deezer + BPM + `backfill-multi-artists` + `reset-beatport` (avec confirmation) — centralise les actions aujourd'hui dispersees, expose les curl-only.
- **Observabilite** : Monitoring (series) + Crawl (logs) **+ Audit log** (nouveau) — tout le lecture-seule d'observation.

### Perimetre

- [x] **D10-01 — URL & IA** : passage a des sous-routes `/admin/:tab` (ou query `?tab=`) → persistance au refresh + liens partageables, en posant la nouvelle structure a 6 onglets d'un seul coup. Attention KeepAlive : l'admin est une vue detail (hors allowlist), verifier le comportement onglet↔route. LIVRE (/admin/:tab, redirect /admin->/admin/overview, fallback overview, rendu groupe).
- [x] **D10-02 — Vue Audit log** : nouvel endpoint `GET /admin/audit-log` (paginee, lecture de `admin_audit_log`) + section dans Observabilite (qui/quoi/quand). LIVRE (routeur mince -> monitoring_service.get_audit_log, user_email via LEFT JOIN ; composant AdminAuditLog).
- [x] **D10-03 — Exposer les 3 actions curl-only** : boutons UI `detach` (Sets), `backfill-multi-artists` (Enrichissement), `reset-beatport` (Enrichissement, **garde-fou de confirmation** vu le caractere destructif). LIVRE (AdminEnrichmentActions pour backfill+reset ; section « Sets attaches » d'AdminSets pour detach).
- [x] **D10-04 — Corriger les renvois de l'Apercu** : chaque carte renvoie vers l'onglet qui affiche/actionne REELLEMENT le backlog concerne. LIVRE (remap vers enrichment/observability/artists).
- [x] **D10-05 (bonus faible cout)** : renommer `GET /admin/artists/sync/status/{id}` → `/admin/tasks/{id}` (poller generique). LIVRE (5 appels front bascules, pas d'alias).

**Invariants** : logique metier inchangee (juste reorganisee/exposee) ; les actions destructives restent auditees (`_audit`) et gardent 404/400 au routeur (invariant #4) ; aucune migration a priori (l'audit log existe deja).

---

## D11 — Admin : Refonte graphique (design)

**Priorite : BAS**
**Estimation : 3-5 jours**
**Depend de : D10 (le design habille la structure figee ; designer une IA qui bouge encore = gaspillage).**
**Statut : A FAIRE — inscrit 2026-08-24. Pipeline /refonte_page (fiche → Claude Design → work_manager → deploy → revue design → cloture). Ne touche PAS a la logique — pur habillage.**

### Perimetre

- [ ] Habillage homogene avec le reste de l'app : tokens `diggy-tokens.css`, reutilisation des composants partages (`TrackTable`, famille `charts/`, `AdminCard` des vues detail), zero couleur hardcodee.
- [ ] Les 2 regimes visuels de l'Apercu (backlog en attente / a jour / inconnu) traites proprement.
- [ ] Responsive mobile (barre d'onglets scrollable, cartes, tables, graphes).
- [ ] Coherence visuelle des 6 onglets (densite, hierarchie, etats vide/chargement via `assets/page.css`).

**Note** : `components/AdminCard.vue` est un faux ami — malgre son nom il sert les vues DETAIL, pas le panel admin. Ne pas le confondre pendant la refonte.

---

## Reliquats hors chantiers (opportunistes)

| Point | Quand |
|---|---|
| **Barre de filtres « toujours affichee » (Explorer/D6)** : au lieu du panneau qui s'ouvre a la demande, garder une version REDUITE toujours visible avec quelques options de base (ex. BPM, Key, Style), extensible au panneau complet actuel (toutes les options). Amelioration UX du systeme de filtres partages (`components/filters/`) → benef aussi a Radar. Optionnel, « si on a du temps ». | Opportuniste — quand une iteration touche le systeme de filtres |
| **Prevention dedup sur `_crawl_track` et `enrich_single_beatport`** (residu X1) : merge-on-collision desactive sur ces 2 chemins (contexte rollback du crawler / AsyncSession admin). Faible valeur depuis l'abandon de l'index unique — ne pas fusionner y est le comportement sur par defaut. | Opportuniste — si une passe touche ces chemins |
| ~~Refonte AdminView (1725 LOC)~~ | Absorbe dans H0.d |
| Monitoring complet (Flower, UptimeRobot, pg_stat_statements) | Apres ouverture, si le besoin apparait |
| **MinIO memoire — mitigations DEPLOYEES 2026-07-22, mesure J+1 restante** : mem montee 90,6 %→97,56 % de 1 GiB (sans lien avec X3). Faites : (1) `mem_limit` 1G→**2G** DEPLOYE (252e53b) — minio recree, mem retombee 999→66 MiB, /deploy_verify SAIN ; (2) cron VPS **restart hebdo `minio`** lundi 00:30 Europe/Paris (`CRON_TZ` + `30 0 * * 1`, log `/var/log/diggy-minio-restart.log`), 1er run lundi. RESTE : re-mesurer `docker stats minio` a J+1 — remontee LENTE = working-set (2G OK) ; remontee RAPIDE vers ~2G = vraie fuite a investiguer (version MinIO). | Mesure J+1 + apres 1er restart lundi |
| Websocket progression import | Jamais peut-etre : le polling 2s suffit |
| Tests composants frontend | Au fil de l'eau (tests integration backend dans H0.f) |
| Tests import RB + branches OAuth (A6-08, A6-14 — arbitrage Q7) | Opportuniste, au fil des chantiers touchant ces zones |
| Index `radar_trends` A2-14 (family, rank_in_family) + (rank_global) — endpoint public expose | Opportuniste (issu de C3 clos, non bloquant) |
| Index 4 FK restantes A2-11 — a reevaluer avec la volumetrie | Opportuniste (issu de C3 clos, non bloquant) |
| Batch upsert import RB (A2-13) | Opportuniste, meme zone que A6-08 |
| Logos plateformes DEFINITIFS : remplacer les traces placeholders de `PlatformLink.vue` (map `platform → path`, poses au chantier refonte Track Detail 2026-07) par les SVG officiels monochromes | Quand William fournit les SVG officiels — un seul fichier a toucher |
| TrackDetailView : `padding-inline` mobile — le shorthand `padding` < 640px ecrase les paddings verticaux (meme ecart corrige sur Playlist Detail au FIX round bcb3845, le round FIX de Track Detail etait deja clos) | Prochaine retouche de TrackDetailView — 1 ligne |
| Polish transverse `ExpandableShelf` : libelle « Voir les N autres » + style lien texte codes en dur → prop label + style `.btn--sm` (ecart #6 revue Artist Detail, rejete au niveau page : composant partage jamais modifie pour une page) | Quand une prochaine page consommant ExpandableShelf est refondue |
| Tri mobile Explorer : < 640 px le sélecteur de tri est masqué en v1 (ordre par défaut) — décision handoff Explorer 2026-07-21, le tri doit rejoindre le `<FilterDrawer>` | Prochaine itération d'Explorer, ou chantier page Radar (même système de filtres partagés) |
| Normalisation `rb_key` → Camelot à l'import : `rekordbox_xml.py` stocke l'attribut Tonality du XML verbatim (ex. `Am`, `Fm` en notation classique). Comme `key_col = coalesce(rb_key, catalog.key)`, un utilisateur dont Rekordbox exporte les clés en notation classique voit ses tracks in-lib disparaître du filtre Key d'Explorer (`.in_(['1A'])` ne matche jamais `Am`) et mal triées. `catalog.key` est déjà Camelot. Fix = convertir `rb_key`→Camelot à l'ingestion (réutiliser la table de `beatport/client.py`) — touche le pipeline d'import (revue interne Explorer #2, 2026-07-21) | Quand un import de bib à clés classiques est constaté, ou avec un chantier touchant `rekordbox_xml.py` |
| **Compteur d'en-tête `RelBlock` non formaté** (revue Genre Detail, écart #3 rejeté au niveau page) : `RelBlock` rend `{{ count }}` brut (prop `count:{type:Number}`) → « Sets 4976 » au lieu de « 4 976 », sur TOUTES les fiches détail (Track/Artist/Set/Genre). Fix transverse : élargir `count` à `[Number,String]` (ou format interne) pour que les pages passent `fmtNum(...)`. | Quand une itération touche `RelBlock` ou une fiche détail |
| **`GET /api/genres/detail` sur-compte `setCount`** vs `GET /api/genres/sets` (`total`) — mesuré prod : Techno 5218 vs 5140, « Musiques de films » 3 vs 1 (les playlists concordent). Contourné côté front (statline Genre Detail bindée sur le total de section, lot 8417615) mais la divergence back reste : aligner les 2 requêtes à la source. | Opportuniste — passe sur `services/genre.py` |
| **`StyleTag.shortLabel` tronque sur `/`** (`name.split('/')[0]`) → parenthèse ouvrante orpheline (« Techno (Peak Time »), constaté sur les chips voisins de Genre Detail. Non rattrapable par `:deep()` (label JS). Fix transverse : couper sur la parenthèse fermante, ou laisser l'ellipsis CSS opérer sur le nom complet (`title` déjà porté). | Quand une page touche `StyleTag` |
| **Pluralisation « 1 tracks » / « 1 artistes en commun »** : cards/shelves affichent « N tracks » invariablement (brief littéral, conforme). Règle `fmtCount` (singulier/pluriel) à décider au niveau du kit. | Opportuniste — décision transverse |
| **Tuiles placeholder du hero Genre Detail à plat noir sous le scrim** (suggestion DA, revue) : la formule G2 (`--fb-*` dark × scrim 0.92) rend la rangée basse des mosaïques < 6 covers comme un trou. Piste : relever la lightness des `--fb-*` pour les tuiles hero, ou n'appliquer que le voile (sans bas de scrim) sur les tuiles vides. + amender le BRIEF G6 (anneau avatar dark = `--genre-tile-border-dark`, convention repo, pas `--genre-tile-ink`). | Opportuniste — retouche hero Genre Detail |
| **Gate Prettier absent → RÉSOLU 2026-08-06** (commits `0dec964` reformat 38 fichiers + `afa661c` gate) : Prettier n'avait jamais été enforced (38 fichiers non conformes) → `format:check` ajouté au job CI `lint-frontend`, `.git-blame-ignore-revs` pour ne pas polluer `git blame`, CLAUDE.md aligné. Le « vitest casse en pool parallèle sous Windows » signalé au même moment était une **FAUSSE ALERTE** (artefact de cwd : la repro tournait depuis la racine du repo, sans `vite.config.js` → environnement `node`) ; depuis `server/frontend`, `npx vitest run` passe en pool `threads`, 572 verts — ne pas ré-investiguer. | Clos |
| Filtrage des placeholders Deezer dans `fetch_artist_artworks` : l'image « silhouette » par defaut de Deezer est ingeree comme un vrai artwork (`has_artwork=true`, ex. artist 4248) — detection md5/URL connue a l'ingestion + backfill, meme logique que le placeholder TrackID prevu en C8.a (ecart #8 revue Artist Detail, clos donnee) | Opportuniste — idealement avec C8.a (meme mecanique placeholder) |
| **Enrichissement set→artiste (D6 Sets liste)** : seuls **44 sets sur 12 345** sont lies a un `SetArtist` — le matcher `tasks/artists.py` exige que le DJ existe deja comme Artist ET apparaisse verbatim dans le titre du set. Consequence : les artistes ne sont cliquables (`/artist/:id`) que sur ces 44 rangees ; ailleurs le DJ n'est que dans le texte du titre. Chantier data a cadrer pour peupler `SetArtist` plus largement (parse du titre TrackID / lien channel). | Opportuniste — quand une passe touche l'import de sets ou le linker artistes |
| **`RingPct.vue` orphelin (D6 Sets liste)** : SetsView consomme desormais `<ScoreRing mode=pct>` (et non plus `RingPct`) → `RingPct.vue` n'a plus aucun consommateur. Nettoyage/suppression ou migration transverse a trancher. | Opportuniste — nettoyage composant |
| **Filtre « A explorer » plafonne a 200 (D6 Sets liste)** : les filtres d'avis (liked/disliked/unrated) resolvent les ids cote front en un fetch NON pagine (facon Artistes), donc « A explorer » n'affiche que 200 sets non notes — pas d'infinite scroll sur ce filtre (ameliore toutefois l'ancien comportement client-side sur ~50). | Opportuniste — si le besoin d'explorer au-dela de 200 apparait |
| **nb_liked en 3e stat de la card Artiste (D6 Artistes liste, recap C5)** : figure a la fiche §5 mais REPORTE au pre-vol 2026-07-27 — donnees quasi-nulles (39 artistes sur 57 k ont >=1 like radar) + surcharge la card (3 stats + avis). `nb_liked` reste renvoye par `/api/artists/`. A reprendre si l'usage des likes radar decolle. | Opportuniste — post-ouverture, si les likes radar se densifient |
| **Bouton admin « Lancer le classement auto » (/genres) CASSE — correctif PLANIFIE** : `POST /admin/genres/auto-classify` (`routers/admin.py`) enqueue `enrich_catalog_beatport` avec `kwargs={"genre_only": True}`, mais ce kwarg n'a JAMAIS existe cote worker (signature reelle `enrich_catalog_beatport(self, batch_size: int = 0)`, `tasks/catalog.py`) → TypeError immediat sur `diggy_worker_enrich`, echec SILENCIEUX : l'API repond 200 « queued » avant l'execution, l'UI affiche un succes, et la trace ne vit QUE dans le result backend Redis (`celery-task-meta-*`, statut FAILURE) — rien dans `crawl_logs` ni les logs worker (Sentry capte via son integration Celery). Casse depuis sa creation (5b6c7f7, 2026-06-23) ; confirme en prod le 2026-08-03 (clic 00:41 Paris, result FAILURE retrouve dans Redis). Correctif vise = implementer le mode prevu : param `genre_only: bool = False` sur la tache, propage a `select_enrich_candidates` pour cibler les rows a `genres` vide — attention, une row qui a deja son `beatport_id` mais pas de genre n'est PAS dans le backlog E1, c'est precisement la cible du mode. Repli minimal si le mode est juge sans valeur : retirer le kwarg cote endpoint (le bouton devient un drain Beatport manuel 550, perd le ciblage « sans genre » qui etait l'intention) — a trancher avec William au lancement. Respecter le lock `lock:enrich_beatport` (deja gere par la tache : skip si un drain horaire court). | Planifie a terme — prochain lot correctifs back/admin (type P2), ou avec toute passe touchant `enrich_catalog_beatport` / `select_enrich_candidates` |
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
| D6 | Refonte UI : listes + Radar + transverses | Au choix, apres/avec la fin de D4 | D4 (composants partages) ; fiches figees docs/refonte-ui/ |
| N1 | Nettoyage residus (auth legacy + TagsView morte) | Opportuniste | Rien |
| AV1-AV7 | Serie audit 2026-08 (quick wins → doc) | AV1 immediat, puis AV2 → AV3 ∥ AV4 → AV5 → AV6 → AV7 | docs/audits/2026-08/DECISIONS.md (Q1-Q8) |
| N4 | Majeurs frontend (vite 8, pinia 4, vue-router 5, vitest 4) | Apres AV5 | AV5 (surface reduite) |
| C10 | Pool similarite precalcule nightly | CONDITIONNEL — si mesures post-AV3 insuffisantes | AV3 (palliatifs + mesures) |

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

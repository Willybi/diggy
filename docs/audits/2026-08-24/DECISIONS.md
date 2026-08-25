# Audit 2026-08-24 — Décisions d'arbitrage (Phase 3)

> Date : 2026-08-24. Décisions prises par William en session, sur la base de `CONSOLIDATED.md` (57 findings uniques).
> Deux questions (Q4 volet 2, Q7 GHCR) ont fait l'objet d'un second tour d'explication vulgarisée avant décision.
> Cohérence vérifiée par le main agent contre le CONSOLIDATED : aucune contradiction. Un point de séquencement
> précisé par William sur Q5 (fenêtre calme), compatible avec l'ordre imposé du CONSOLIDATED (« avant la FIN du
> backfill » ≠ « pendant une salve ») — consigné ci-dessous.

---

## Q1 — Lot AW1 Quick Wins : **GO en bloc**

Les 3 hautes (A3-01 aiguillage deadline backfill, A4-01 échappement highlight Hub, A5-01 cap postgres —
timing Q5) + les QW-c sans décision produit : A6-02 (throttle content-similar), A2-01 (repoint
`catalog_albums` au merge), A5-02 (6 buckets backup), M4 volet doc (prérequis pgvector dans restore.md —
le re-test part en AW4), A4-03 (« N éléments »), A4-04 (corbeille tactile, vérif CDP), A4-06 (volume 0),
A4-08 (listener KeepAlive), A1-08 (commentaire auth_middleware), A1-06 (contrat 404/no-cache
content-similar), A7-04 (nettoyage disque `docs/c9-benchmark;C` + node_modules racine + __pycache__),
+ les suppressions actées en Q3 et le gate acté en Q2.

## Q2 — `content-similar` (C9.b) : **option (a) — `require_admin` serveur le temps du ramp-up**

Le gate annoncé « admin-only » devient RÉEL côté serveur (3 lignes + 1 test), retiré au dé-gate
front/GA (C9.c ou fin de ramp-up couverture embeddings). A6-02 (bucket `"/content-similar": (20, 60)`
dans `RATE_LIMIT_SUFFIXES` + test miroir) reste nécessaire quel que soit le gate et part en AW1.
A1-06 (404 sur seed inexistant / ne pas cacher le vide fabricable) dans le même lot.

## Q3 — Code mort : **tout supprimer**

| Élément | Décision |
|---|---|
| `similar_from_context` + ses tests dédiés (A1-03, 2 audits sans caller) | **SUPPRIMER** — git garde l'historique si C9.c veut un wrapper de composition ; amender la mention CLAUDE.md |
| `MatchCandidate.total_identified` + la boucle N+1 de COUNT par candidat (A1-02) | **SUPPRIMER** (champ + boucle + assertion de test) |
| `CrawlLogger.update_stats` + propriété `log_id` (A3-06) | **SUPPRIMER** — `set_stats` reste l'unique API |
| Bouton « Ajouter à la bib » sans handler, résultats de recherche Hub (A4-02) | **SUPPRIMER le bouton** (pas d'endpoint d'ajout unitaire ; le badge EN BIB reste) |

## Q4 — DB Collections & albums : **GO les deux volets**

- **Contrainte unique `collection_items`** (M2) : deux index uniques partiels dialecte-safe
  (`(collection_id, item_type, item_id) WHERE item_id IS NOT NULL` + `(collection_id, item_type,
  item_name) WHERE item_id IS NULL`), router rattrape `IntegrityError` → 409 (check applicatif conservé
  en fast-path). Répare au passage le DELETE 500 (`MultipleResultsFound`) et rend le downgrade 0047
  rejouable. Même migration : fix downgrade 0046 (`DROP TYPE album_type` checkfirst, A2-03). → AW3.
- **`track_position` sur `catalog_albums`** (A1-10) : **GO** — « plus clean à long terme et ça ne coûte
  rien ». Colonne `track_position SMALLINT NULL` (migration), peuplée au funnel
  `link_catalog_album_from_hit` (la donnée est dans les payloads Deezer), backfill via
  `scripts/backfill_albums.py`, tracklist `order_by(coalesce(track_position, id))`. Chantier dédié
  **C7.c** hors série AW (follow-up produit C7, pas une remédiation d'audit).

## Q5 — Postgres cap 1G→3G + `shared_buffers` ~768M : **GO, fenêtre choisie**

Contrainte de séquencement posée par William : ne PAS recréer postgres en plein rattrapage backfill
embeddings — choisir une fenêtre calme (entre deux salves du backfill local, hors fenêtres enrich).
Compatible avec l'ordre du CONSOLIDATED : le bump doit être fait avant la FIN du backfill (pour que
l'éval à l'échelle C9.a mesure des latences réalistes), pas à un instant précis. Exécution : dans AW1,
mais le `docker compose up -d --no-deps postgres` se planifie manuellement (geste OPS coordonné,
coupure brève).

## Q6 — Lot backup/DR & CI (AW4) : **GO complet**

A5-03 (image backup dédiée, `mc`/rclone pinnés — plus de téléchargement non vérifié à chaque run,
offsite du dump AVANT le mirror), A5-04 (crontab VPS réécrit en UTC avec commentaires de conversion —
geste OPS ; corriger les mentions « Paris » des mémoires), re-test restore complet post-pgvector +
re-stamp de la date (M4), A5-06 (empreinte host figée dans un secret `VPS_KNOWN_HOSTS`), A5-08 (retry
borné du health check post-deploy), A5-09 (`timeout-minutes` sur les jobs), A5-10 (`--maxmemory 400mb`
en gardant `noeviction`).

## Q7 — Chantiers structurels : **les deux inscrits**

- **Build GHCR** (A5-11) : **inscrit, PLANIFIÉ priorité basse** (pas conditionnel) — « on le fera,
  c'est toujours mieux et plus propre ». Build des images dans GitHub Actions → push GHCR → le VPS ne
  fait plus que `pull` + `up -d` ; bonus rollback = re-tag. Chantier L, hors série AW.
- **Nginx resolver dynamique** (A5-07) : **GO, inscrit** — `resolver 127.0.0.11 valid=30s` + upstreams
  en variables dans `default.ssl.conf.template`, avec le point d'attention documenté (sémantique
  `proxy_pass` + variable : réécriture d'URI explicite pour `/storage/`), vérif RENDU après bascule.
  Supprime structurellement le piège « restart nginx après deploy manuel ». Peut absorber A5-12
  (dédup default.conf/empty.conf) au passage.

---

## Impacts sur la proposition de chantiers (§7 du CONSOLIDATED)

| Chantier | Ajustements actés |
|---|---|
| AW1 | Confirmé + Q2(a) (require_admin) + suppressions Q3 ; A5-01 = geste OPS coordonné (fenêtre calme, Q5) |
| AW2 | Inchangé (M3, A3-08, A3-03+A3-04, A1-04 ; A3-05 attend le diagnostic OPS) |
| AW3 | Confirmé : A6-04 (tests d'abord) → A1-01 (extraction service) → M2 + A2-03 (une migration) ; + A4-05, A4-09, A4-11 |
| AW4 | Confirmé complet (Q6) |
| AW5 | Confirmé : lot doc (A7-01 + processus de bump en clôture de chantier, A7-02, A7-03, A2-02, A7-05, A1-07, A8-02) + A2-06 rattaché à l'arbitrage FK du ledger |
| Hors série | **C7.c track_position** (Q4, nouveau) ; **GHCR planifié low** (Q7) ; **nginx resolver** (Q7) ; suivis : A2-05 (EXPLAIN KNN post-backfill), A3-05 (post-diagnostic), opportunistes A1-09/A3-07/A6-05/A4-07/A4-10/A4-12 |

Séquencement : **AW1** → **AW2 ∥ AW3** (zones disjointes) → **AW4** → **AW5** ; C7.c / resolver nginx / GHCR à caler dans la roadmap générale hors série.

---

*Phase 4 : LEDGER mis à jour (findings 2026-08-24 insérés avec leur affectation AW), bloc roadmap proposé,
message de commit proposé. La suite naturelle est `/work_manager` sur AW1.*

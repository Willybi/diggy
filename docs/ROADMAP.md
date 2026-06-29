# Diggy — Roadmap

> Roadmaps completees : voir `docs/completed/`
> - `ROADMAP_2026-06.md` — audit technique T1-T6, chantiers C1-C13 (100% fait)
> - `ROADMAP_MULTIUSER.md` — phases 0-7 multi-user (100% fait)

---

## En attente

### F2 — HTTPS / Domaine

**Bloque par :** achat du nom de domaine
**Plan pret :** `docs/PLAN_HTTPS.md`

- [ ] Acheter et configurer le nom de domaine
- [ ] Pointer le DNS A vers 82.29.168.247
- [ ] Executer le provisioning initial (voir PLAN_HTTPS.md)

---

## Backlog

### L1 — Monitoring & Observabilite

- [ ] Sentry (FastAPI + Celery workers)
- [ ] Endpoint `/api/health` enrichi (version, uptime, status DB/Redis)
- [ ] Celery Flower ou equivalent
- [ ] UptimeRobot (check HTTP `/api/health`)
- [ ] pg_stat_statements (slow queries)

### L2 — Multi-artiste par track

Table `catalog_artists(catalog_id, artist_id, role)` pour les feats.
136 artistes orphelins issus de splits feat attendent cette feature.

### L3 — Graphe artistes

Visualisation des connexions entre artistes (sets, feats, playlists).
Necessite L2. Stack envisagee : D3.js ou vue-flow.

### F3 — Design Realignment (vagues 3-5)

- Vague 3 : Pages detail (Track, Artist, Set, Playlist)
- Vague 4 : Genres + Login redesign
- Vague 5 : Admin panel

---

## Opportunites techniques

- [ ] **Tests CI avec PostgreSQL** — remplacer SQLite par un service PG dans GitHub Actions
  pour eviter les bugs dialecte (ex: `round(float, int)`)

---

## Methode de travail

Voir `docs/completed/ROADMAP_2026-06.md` section "Methode de travail" pour le process
complet (prompts agent, review, deploy, smoke tests, commit naming, rapports).

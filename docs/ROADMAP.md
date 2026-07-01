# Diggy — Roadmap

> Roadmaps completees : voir `docs/completed/`
> - `ROADMAP_2026-06.md` — audit technique T1-T6, chantiers C1-C13 (100% fait)
> - `ROADMAP_MULTIUSER.md` — phases 0-7 multi-user (100% fait)
> - F2 HTTPS — domaine `diggy-music.fr`, Let's Encrypt, certbot auto-renew (100% fait)

---

## Backlog

### L1 — Monitoring & Observabilite

- [x] Sentry (FastAPI + Celery workers)
- [x] Endpoint `/api/health` enrichi (version, uptime, status DB/Redis)
- [ ] Celery Flower ou equivalent
- [ ] UptimeRobot (check HTTP `/api/health`)
- [ ] pg_stat_statements (slow queries)

### L2 — Multi-artiste par track

Table `catalog_artists(catalog_id, artist_id, role)` pour les feats.
136 artistes orphelins issus de splits feat attendent cette feature.

### L3 — Graphe artistes

Visualisation des connexions entre artistes (sets, feats, playlists).
Necessite L2. Stack envisagee : D3.js ou vue-flow.

### F3 — Google OAuth

Connexion via compte Google en alternative au login email/password.
- Google Cloud Console : projet + ecran de consentement OAuth
- Redirect URI : `https://diggy-music.fr/api/auth/google/callback`
- Backend : endpoint callback, creation/liaison de compte, JWT
- Frontend : bouton "Se connecter avec Google" sur LoginView

### F4 — Design Realignment (vagues 3-5)

- Vague 3 : Pages detail (Track, Artist, Set, Playlist)
- Vague 4 : Genres + Login redesign
- Vague 5 : Admin panel

---

## Opportunites techniques

- [~] **Tests CI avec PostgreSQL** — PRET mais INHIBE temporairement (CI trop lente en dev intensif).
  Conftest dual SQLite/PG pret, asyncpg + service PG commentes dans `deploy.yml`.
  A reactiver quand le rythme de dev se calme (decommenter le bloc services + DATABASE_URL).
- [x] **Lint frontend dans CI/CD** — ESLint + eslint-plugin-vue, job `lint-frontend`
  dans le workflow deploy. Zero erreurs/warnings au depart.

---

## Methode de travail

Voir `docs/completed/ROADMAP_2026-06.md` section "Methode de travail" pour le process
complet (prompts agent, review, deploy, smoke tests, commit naming, rapports).

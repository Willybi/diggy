# A5 — Audit Infra, Docker, CI/CD (2026-08)

> **Date** : 2026-08-09 · **HEAD audité** : `9b305d6` (2026-08-08)
> **Agent** : A5 (audit global, lecture seule)
> **Périmètre** : `server/Dockerfile`, `server/frontend/Dockerfile`, `docker-compose*.yml`, `server/nginx/`, `.github/workflows/deploy.yml`, `.dockerignore`s, `server/scripts/backup*.sh`, `docs/restore.md`, crons et état live du VPS (lecture seule via `ssh diggy-vps`).
> **Méthode** : lecture des fichiers du repo + commandes SSH strictement en lecture (`docker compose ps`, `docker stats --no-stream`, `docker inspect`, `docker images`, `crontab -l`, `ls`, `tail` de logs, `openssl s_client`) + runs outillés locaux contre-vérifiés (`pip-audit`, `npm audit`). Aucune écriture locale (hors ce rapport) ni distante.
> **Audit précédent** : `docs/audit_2026-07/A5_infra.md` (20 findings) — fixes livrés via AU1 (`ebca46b`) + AU2 (`643dc67`).

---

## Ce qui va bien

Le delta depuis 2026-07 est spectaculaire côté infra : **17 des 20 findings de l'audit précédent sont corrigés et vérifiés live**.

- **Backups vivants et complets (A5-01/02/03 réglés)** : cron `30 1 * * *` (`crontab -l` VPS) → 9 dumps quotidiens consécutifs vérifiés (`/var/lib/docker/volumes/diggy_backups/_data/postgres/` : 2026-08-01 → 2026-08-09, 32→41 Mo, tous `.sql.gz.gpg` chiffrés). Offsite rclone opérationnel : log du 2026-08-08 → `Offsite copy done: diggy_20260808_013010.sql.gz.gpg` + rétention 14 appliquée (`deleting diggy_20260725...`). Check de fraîcheur 09:00 vivant : `OK: latest local backup is 7h old` + `OK: latest offsite backup is 7h old`. Mount rclone bien resté read-write avec commentaire explicite (`docker-compose.yml:287-289`).
- **`docs/restore.md` existe et sa date est honnête** : dernier test de restauration réel daté **2026-07-10** (AU2-L4, dump offsite → base jetable, counts vérifiés) — moins d'un mois au moment de l'audit. À re-tester ~trimestriellement pour garder la ligne honnête.
- **Séquence deploy conforme** (`deploy.yml:125-132`) : `build` → `docker compose run --rm -T api python -m alembic upgrade head` (migration sur la **nouvelle** image, **avant** le switch — A5-07 réglé) → `up -d` sans `--force-recreate` (A5-06 réglé) → health check + smoke tests 4 endpoints. `concurrency: group: deploy-prod, cancel-in-progress: false` posé (`deploy.yml:8-10`, A5-10 réglé).
- **Prod = code de l'image, plus aucun bind-mount** (A5-08 réglé) : `docker inspect diggy_worker`/`diggy_api` → `Mounts` **vide**. Build single-image contexte `./server` (api+workers), les 5 services partagent l'image (852 MB ×4 tags = mêmes layers).
- **`.dockerignore` par contexte** (A5-09 réglé) : `server/.dockerignore` + `server/frontend/.dockerignore`, celui de la racine supprimé. Aucun répertoire runtime manquant (vérifié, cf. hypothèses réfutées).
- **Healthchecks partout, 10/10 healthy** (A5-20 réglé) : workers via `celery inspect ping -d celery@$$HOSTNAME`, beat via fraîcheur du fichier schedule (`docker-compose.yml:106-111,138-143,172-178`) ; `docker compose ps` → tous `(healthy)`.
- **Pitfalls nginx tous respectés** (`server/nginx/default.ssl.conf.template`) : `^~` sur `/api/` (l.45), `/storage/` (l.54), `/minio/` bloqué 403 (l.60) ; headers serveur en `always` (l.33-37) avec CSP `upgrade-insecure-requests` ; locations assets **imbriquées** dans `location /` sans `add_header` propre (l.65-82) donc CSP héritée ; `http2 on` (l.18, A5-18 réglé) ; `client_max_body_size 12M` (l.23) toujours couplé à `MAX_FILE_SIZE` 10 MB (`import_rb.py:17`) avec le commentaire de couplage.
- **Port 8080 public retiré en prod** (A5-12 réglé) : nginx n'expose que 80/443 (`docker compose ps`), le mapping `${NGINX_PORT:-8080}:80` vit dans `docker-compose.override.yml:26` non chargé en prod (`COMPOSE_FILE=docker-compose.yml:docker-compose.ssl.yml` dans le `.env` VPS).
- **Pins critiques posés** (A5-11 essentiel réglé) : `minio/minio:RELEASE.2025-09-07T16-13-09Z` (`docker-compose.yml:206`), `certbot/certbot:v5.7.0` (`docker-compose.ssl.yml:27`).
- **Frontend Dockerfile reproductible** (A5-05 réglé) : `COPY package.json package-lock.json` + `npm ci` dans les deux stages, image 82 MB.
- **CI renforcée** : Node 22 + cache npm (A5-19 réglé), gate Prettier (`deploy.yml:30-31`, afa661c), pytest xdist `-n auto --dist loadscope` + PG par worker (bf141ed), coverage gate `--cov-fail-under=55` réellement dans la commande (`deploy.yml:78`).
- **Hygiène VPS** : cert TLS valide jusqu'au **2026-09-26** (`openssl s_client`), boucle certbot 12h + deploy-hook `.reload` ; plus aucun container fantôme, **1** seul volume dangling (12 en juillet) ; cron `nginx -s reload` 03:00 supprimé avec commentaire de tombstone (A5-13/14 réglés) ; disque à 35 % ; rotation `json-file 50m×3` sur tous les services ; RAM saine (voir hypothèses réfutées).
- **`.env.example` complet** (A5-16 réglé) : `JWT_SECRET`, Google OAuth, Sentry, `BACKUP_ENCRYPTION_KEY`/`RCLONE_REMOTE`, budgets E1/E2.c documentés.
- **MinIO : mitigation mémoire documentée dans le code** (`docker-compose.yml:212-228`) : cap 1G→2G + `GOMEMLIMIT: 1800MiB` + restart hebdo cron (log du 2026-08-03 OK) — `RestartCount=0`, `OOMKilled=false`. Le régime reste toutefois collé au cap (finding A5-03).

---

## Findings

### [A5-01] Gate CI pip-audit doublement non-bloquant pendant que 26 vulnérabilités connues passent en prod — RÉCURRENCE aggravée de 2026-07/A5-04
- **Type** : sécu
- **Sévérité** : haute
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `.github/workflows/deploy.yml:80-90` :
    ```yaml
    audit:
      runs-on: ubuntu-latest
      continue-on-error: true
      steps:
        ...
        - run: pip install pip-audit && pip-audit -r server/api/requirements.txt --desc
    ```
  - `.github/workflows/deploy.yml:108` : `needs: [lint-frontend, lint-python, test, test-frontend]` — le job `audit` est absent. Seul trigger du workflow : `push` sur master (l.3-6), **aucun `schedule:`**.
  - Run direct (2026-08-09, `python -m pip_audit -r requirements.txt` moins `essentia`, wheel Linux-only) : **`Found 26 known vulnerabilities in 7 packages`** — extrait :
    ```
    python-jose      3.3.0   PYSEC-2024-232/233 (×2 chacun)  fix 3.4.0 ; PYSEC-2025-185 SANS fix
    python-multipart 0.0.9   PYSEC-2026-1851/1852/3036-3040 (7 avis)  fix jusqu'à 0.0.31
    starlette        0.38.6  PYSEC-2026-161/248/249/1941/1943/2280/2281 (9 avis)
    requests 2.32.3 · curl-cffi 0.7.4 · python-dotenv 1.0.1 · ecdsa 0.19.2 (transitif jose)
    ```
  - Pins concernés : `server/api/requirements.txt:16` (`python-jose[cryptography]==3.3.0`), `:18` (`python-multipart==0.0.9`), `:10`, `:12`, `:8` ; starlette 0.38.6 transitif de `fastapi==0.115.0` (`:1`).
- **Constat** : AU1 (`ebca46b`) a corrigé la **cible** du job (le `-r server/api/requirements.txt` manquant, cœur de 2026-07/A5-04) mais a laissé le job doublement non-bloquant : `continue-on-error: true` masque le rouge au niveau workflow ET l'absence du `needs:` fait que `deploy` n'attend même pas son résultat. La recommandation d'origine (« non-bloquant défendable **si** run planifié + notification, sinon bloquant avec allowlist ») n'a été suivie sur aucune des deux branches. Résultat concret : le job échoue à chaque push depuis des semaines sans que personne ne le voie, et 26 vulnérabilités — dont `python-jose` (la lib qui valide les JWT de l'auth), `python-multipart` (parsing de l'upload XML Rekordbox) et `starlette` (FastAPI lui-même) — sont déployées silencieusement. Le gate donne un faux sentiment de couverture pire que son absence.
- **Recommandation** : rendre le job bloquant (`needs` + retrait de `continue-on-error`) **après** la mise à jour des dépendances (sinon il bloque tout deploy immédiatement) ; maintenir les CVE sans fix (`PYSEC-2025-185`) via `--ignore-vuln` explicite et commenté. Alternative minimale si William veut rester non-bloquant : ajouter un trigger `schedule:` hebdo + notification (issue GitHub auto ou mail) pour que l'échec soit VU.
- **Dépendances** : **A6** porte l'exposition des vulnérabilités elles-mêmes (upgrade python-jose/multipart/fastapi-starlette — effort M, tests requis) ; ce finding-ci porte uniquement le gate. Ordre : upgrades A6 d'abord, gate bloquant ensuite.
- **Tags** : QW-c (le changement de workflow lui-même est S et sans risque)

### [A5-02] L'alerte de fraîcheur backup est un cul-de-sac : « ALERT » écrit dans un log que personne ne lit
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `crontab -l` VPS : `0 9 * * * cd /root/diggy && docker compose run --rm ... --entrypoint /freshness.sh backup >> /var/log/diggy-backup.log 2>&1` — stdout **et** stderr redirigés vers le log ; aucun `MAILTO` dans le crontab (vérifié), pas de MTA configuré.
  - `server/scripts/backup_freshness_check.sh:9-12` : « Prints an "ALERT:" line and exits non-zero **so a cron wrapper can forward the message to its notification channel** » — le wrapper de notification n'a jamais été créé ; l'exit code non-zéro est avalé (cron n'a rien à mailer puisque tout est redirigé).
  - `/var/log/diggy-backup.log` : **22 Mo**, aucune entrée `logrotate` (`grep -rl diggy /etc/logrotate.d/` → vide) — le `mc mirror` nocturne y logge chaque artwork copié (des centaines de lignes/jour), un `ALERT:` y serait noyé.
- **Constat** : le dispositif AU2 détecte correctement un backup absent/périmé (local ET offsite, testé dans le design), mais la détection n'atteint aucun humain : elle finit dans un fichier de 22 Mo que rien ne surveille. Une casse silencieuse du pipeline backup (clé GPG retirée du `.env`, token rclone expiré, disque plein, dl.min.io down — le container ré-installe `apk add` + télécharge `mc` par le réseau **à chaque run**, `docker-compose.yml:299-301`) ne serait découverte qu'à la prochaine inspection manuelle — potentiellement des semaines, soit exactement le scénario A5-01 de 2026-07 (8 jours sans dump, découvert par audit).
- **Recommandation** : brancher le canal manquant — le plus simple : wrapper cron qui n'envoie que les échecs vers une notification poussée (ntfy.sh/webhook Discord/mail via `msmtp`), ex. `... /freshness.sh backup >> log 2>&1 || curl -d "Diggy backup ALERT" ntfy.sh/...`. Au passage : `--quiet` sur le `mc mirror` du backup (le script le fait déjà pour l'alias mais pas le mirror en cron — le log montre le mode verbeux) + une entrée logrotate pour `/var/log/diggy-*.log`.
- **Dépendances** : aucune
- **Tags** : QW-c

### [A5-03] MinIO sature son cap mémoire 2G en ~5 jours : la mitigation de juillet a déplacé le plafond, pas arrêté la dérive
- **Type** : perf
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute (observation) / moyenne (risque projeté)
- **Preuve** :
  - `docker stats --no-stream` (2026-08-08 22h UTC) : `diggy_minio  1.991GiB / 2GiB  99.55%` — 5 jours après son dernier restart hebdo (`docker inspect` : `StartedAt=2026-08-03T00:30`, `RestartCount=0`, `OOMKilled=false`).
  - `docker-compose.yml:212-218` : le commentaire du cap 1G→2G (2026-07-22) décrit le même symptôme à 1G (« working-set crept to ~98% of 1G ») ; `:223-228` : `GOMEMLIMIT: 1800MiB` censé garder la RSS bornée (« this keeps it bounded »), avec ~250MiB de marge off-heap.
  - Volume d'objets en croissance continue : mirror backup du 2026-08-08 = 217 MiB transférés (nouveaux artworks quotidiens, ~190k objets au total d'après le commentaire compose).
- **Constat** : le pattern de juillet se répète à l'identique un cran au-dessus : le working-set remplit le cap disponible en quelques jours. Pas d'OOM constaté (le GOMEMLIMIT transforme bien la pression en GC, comme conçu) et le restart hebdo purge — le dispositif TIENT aujourd'hui. Mais le régime permanent « collé à 99,5 % du cap » signifie : GC de plus en plus agressif en fin de semaine (latence sur `/storage/*`), marge off-heap de ~250MiB seulement face à un pic (gros mirror, scanner + rafale de PUT artworks), et une dérive structurelle avec la croissance du catalogue — chaque cap finira saturé. L'hôte a 11G disponibles : la contrainte est artificiellement serrée.
- **Recommandation** : relever cap 2G→3G + `GOMEMLIMIT` 1800→2700MiB (même géométrie, marge ×3, coût nul vu la RAM libre) **ou** décider que le couple restart-hebdo/GOMEMLIMIT est le régime assumé et le documenter comme tel dans le commentaire compose (en retirant « this keeps it bounded », démenti par l'observation). Point de surveillance : si `RestartCount>0` ou `OOMKilled=true` apparaissent entre deux lundis, le bump devient obligatoire.
- **Dépendances** : aucune
- **Tags** : QW-c

### [A5-04] CLAUDE.md : taille d'image worker annoncée « ~doublée à 312 Mo » — la réalité est 852 MB
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `docker images` VPS : `diggy-api` / `diggy-worker` / `diggy-worker_enrich` / `diggy-beat` = **852MB** chacun (même image, 4 tags). CLAUDE.md (en-tête, E2.c) : « Essentia+ffmpeg ajoutés à l'IMAGE worker partagée (**~doublée à 312 Mo**) ». L'audit 2026-07 mesurait l'image pré-E2.c à 294 MB : « doublée » donnerait ~588 MB ; ni 312 ni 588 ne correspondent au réel.
- **Constat** : la phrase est doublement fausse (le chiffre ET l'arithmétique du « doublée »). L'image a en fait presque **triplé** (294→852 MB) — cohérent avec la stack native essentia (wheel + numpy/scipy) + ffmpeg. Sans conséquence opérationnelle (disque VPS à 35 %, prune quotidien), mais CLAUDE.md demande explicitement de signaler ses divergences, et un futur arbitrage « peut-on ajouter telle dépendance à l'image ? » se ferait sur un chiffre 2,7× trop optimiste.
- **Recommandation** : corriger CLAUDE.md : « image worker partagée ~triplée à ~850 Mo (essentia + ffmpeg + stack native) ».
- **Dépendances** : à consolider avec A7 (exactitude CLAUDE.md)
- **Tags** : QW-c

### [A5-05] CLAUDE.md affirme que « the full local app is served by nginx on http://localhost:8080 » — contredit par la config versionnée (et par Q6)
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : moyenne (config lue, comportement local non exécuté)
- **Preuve** : CLAUDE.md § Dev Commands : « The full local app (static frontend + API + `/api/docs`) is served by nginx on http://localhost:8080 ». Or en local (base + override, sans ssl.yml) nginx monte `./server/nginx/default.conf:/etc/nginx/conf.d/default.conf` (`docker-compose.yml:253`) dont le contenu intégral est `# intentionally empty — SSL config is loaded via /etc/nginx/templates/` : aucun server block, donc rien n'écoute derrière le mapping `8080:80` de l'override. C'était le finding 2026-07/A5-17, arbitré **Q6 : dev local full-stack non supporté** (résidu accepté — non re-signalé ici).
- **Constat** : ce n'est pas le flux local cassé qui est signalé (accepté Q6), c'est la phrase de CLAUDE.md qui affirme l'**inverse** du résidu accepté : elle promet un chemin (`localhost:8080` = app complète) que la config versionnée ne peut pas servir. Un agent ou William suivant cette phrase perdrait du temps à déboguer un « nginx cassé » qui est en fait l'état arbitré.
- **Recommandation** : reformuler CLAUDE.md : le port 8080 local n'est fonctionnel qu'avec une config nginx locale ad hoc (non versionnée) ; le chemin officiel reste push → CI → prod (Q6). Si un vrai besoin local existe, c'est une RÉÉVALUATION de Q6, pas un fix doc.
- **Dépendances** : à consolider avec A7 ; réf. 2026-07/A5-17 + DECISIONS Q6
- **Tags** : QW-c

### [A5-06] Tags de base encore flottants : `nginx:alpine` (×2), `node:22-alpine`, `python:3.13-slim` — reliquat de 2026-07/A5-11
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `docker-compose.yml:244` (`nginx:alpine`), `server/frontend/Dockerfile:1,8,15` (`node:22-alpine` ×2, `nginx:alpine`), `server/Dockerfile:1,6` (`python:3.13-slim`). VPS : `nginx alpine ... 2 months ago`. Le cœur du finding 2026-07/A5-11 (minio, certbot — services de données/certs) est pinné ; ces quatre restent des tags mobiles.
- **Constat** : RÉCURRENCE partielle assumée — la recommandation de juillet disait « pinner au minimum MinIO + certbot », c'est fait. Le risque résiduel est faible et lent (les bases ne sont re-pull qu'en cas d'absence locale, pas à chaque build), mais `nginx:alpine` est le plus mobile du lot (suit les majeures nginx sans aucun chiffre) et c'est le proxy TLS de prod ; un re-provisionnement de VPS (scénario restore B) tirerait des versions jamais testées.
- **Recommandation** : pinner mineur : `nginx:1.29-alpine` (compose + frontend Dockerfile), `python:3.13-slim` est acceptable (pin de minor Python), `node:22-alpine` acceptable (pin de major LTS). Basse priorité, à glisser dans un commit d'hygiène.
- **Dépendances** : réf. 2026-07/A5-11
- **Tags** : —

### [A5-07] Chaîne de build frontend : 5 vulnérabilités npm (4 high) dont 3 packages fixables immédiatement, et 4 majeurs de retard (vite 5→8, pinia 2→4, vue-router 4→5, vitest 3→4)
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S (audit fix) + L (saut vite 8 / majeurs)
- **Confiance** : haute
- **Preuve** : `npm audit` (run direct 2026-08-09, `server/frontend`) : **5 vulnerabilities (1 moderate, 4 high)** —
  ```
  brace-expansion 2.0.0-2.1.3   high  DoS (×4 avis)             fix: npm audit fix
  nanoid ≤3.3.16                high  boucle infinie            fix: npm audit fix
  postcss ≤8.5.22               high  path traversal sourcemap  fix: npm audit fix
  esbuild ≤0.24.2 (← vite ≤6.4.2)  moderate  dev-server         fix: vite@8.2.1 (breaking)
  ```
  `npm outdated` (inventaire Phase 0, §5) : vite 5.4.21→8, pinia 2→4, vue-router 4→5, vitest 3→4, @vitejs/plugin-vue 5→6, jsdom 26→29.
- **Constat** : aucune de ces vulns n'atteint le runtime navigateur (chaîne dev/build uniquement — l'avis esbuild ne concerne que le dev-server, qui ne tourne jamais en prod) ; sévérité globale basse pour Diggy. Mais la chaîne de build s'exécute en CI et **sur le VPS** à chaque deploy (build de l'image frontend), et le retard de 4 majeurs s'accumule : plus on attend vite 8, plus le saut (et la ré-validation des 18 vues) coûtera cher — pinia 2→4 et vue-router 4→5 touchent du code applicatif.
- **Recommandation** : (1) tout de suite : `npm audit fix` (brace-expansion/nanoid/postcss — patchs sans breaking) ; (2) planifier un chantier « majeurs frontend » dédié (vite 8 + vitest 4 ensemble, puis pinia/vue-router) plutôt que de le laisser grossir — hors périmètre d'un commit d'hygiène.
- **Dépendances** : le volet (1) est indépendant ; le volet (2) mérite un arbitrage roadmap (Phase 3)
- **Tags** : QW-c (volet 1 uniquement)

---

## Hypothèses réfutées

- **« Un répertoire runtime récent manquerait au `.dockerignore` du contexte `./server` »** (angle 2 du brief) : réfuté. Le pattern `scripts/` de `server/.dockerignore:5` ne matche que `server/scripts/` (racine du contexte), PAS `server/api/scripts/` — les 18 scripts OPS (`dedup_catalog.py`, `reverify_platform_ids.py`, `dedup_artists_deezer.py`, `rescore_set_flags.py`…) sont dans `server/api/scripts/`, donc **dans l'image** via `COPY api/ /app/` (`server/Dockerfile:17`), comme requis pour les exécuter en prod. `workers/tasks/bpm.py` + `bpm_analysis.py` (E2.c) shippent via `COPY workers/`. Les exclusions restantes sont toutes légitimes : `server/scripts/` (backup.sh/freshness bind-mountés depuis l'hôte à l'exécution, `docker-compose.yml:284-285` ; bootstrap_tidal/generate_schema_doc = outillage local), `deezer/` (outillage PC, A7-07), `nginx/` (monté depuis l'hôte), `frontend/` (contexte séparé). Seul import inter-répertoires trouvé : `api/scripts/reverify_platform_ids.py:104` → `scripts.dedup_catalog`, tous deux DANS l'image.
- **« Le backup du jour aurait pu sauter »** : réfuté — dump du 2026-08-09 01:32 présent (`/var/log/diggy-backup.log` mtime), 9e jour consécutif.
- **« Surallocation mémoire des caps vs RAM VPS »** : réfutée. Somme des limits = 9,4G (postgres 1G + redis 512M + api 3G + worker 1G + worker_enrich 1G + beat 256M + frontend 128M + minio 2G + nginx 512M) pour **15,6G** de RAM ; usage réel 3,6G + 11G buff/cache. Le cap api 3G (2026-08-01, OOM /radar) est absorbé sans pression. Marge saine même avec le second projet hébergé (`dofusdepioute`, 12MiB).
- **« Les fantômes Docker de juillet (A5-13) traîneraient encore »** : réfuté — aucun container arrêté/fantôme (`docker ps -a`), 1 seul volume dangling (12 en juillet), le container certbot-run orphelin a disparu.
- **« Le healthcheck beat pourrait être décoratif »** : réfuté — il teste la fraîcheur réelle du fichier schedule (`find /var/spool/celery -name 'beat-schedule*' -mmin -15`, `docker-compose.yml:174`), un beat wedgé deviendrait unhealthy en ≤15 min.
- **« La CI valide un frontend différent de la prod »** (résidu A5-19) : réfuté — Node 22 partout (`deploy.yml:20,98` vs `node:22-alpine`), `npm ci` partout, lockfile dans l'image.
- **« essentia ferait échouer le job pip-audit pour une mauvaise raison (wheel introuvable) plutôt que pour les vulns »** : non tranché en local (Windows : pip-audit échoue sur le wheel Linux-only avant d'auditer — comportement local seulement ; le job CI ubuntu résout le wheel cp313 manylinux). Dans les deux cas le job est rouge et masqué (A5-01) ; sur ubuntu, ce sont bien les 26 vulns qui le font échouer.

## Non couvert

- **Statut réel des runs GitHub Actions** (le job `audit` est-il rouge depuis afa661c ou ebca46b ?) : `gh` absent de la machine d'audit ; déduit de la config + du run pip-audit local, pas observé dans l'UI Actions.
- **Réception effective Sentry** (résidu 2026-07/A5-15) : toujours invérifiable en read-only.
- **Console Hostinger** (snapshots hebdo annoncés dans `docs/restore.md:238-244`, dernières vues 02/07 et 09/07) : invérifiable depuis le VPS — à re-vérifier manuellement dans le panel à l'occasion.

# A5 — Audit Infra, Docker, CI/CD

> **Date** : 2026-07-09
> **Agent** : A5 (audit global read-only)
> **Périmètre** : `docker-compose.yml`, `docker-compose.ssl.yml`, `docker-compose.override.yml`, `server/nginx/`, `.github/workflows/deploy.yml`, `server/api/Dockerfile`, `server/frontend/Dockerfile`, `server/scripts/backup.sh`, `.env.example`, état live du VPS (82.29.168.247, lecture seule via SSH).
> **Méthode** : lecture des fichiers du repo + commandes SSH strictement en lecture (`docker ps`, `docker images`, `docker inspect`, `docker volume inspect`, `ls`, `cat`, `grep`, `crontab -l`, `systemctl list-timers`, `df`, `docker logs --tail`, `openssl x509`). Aucune modification locale ni distante.

---

## Ce qui va bien

- **Pitfalls Nginx respectés** : `^~` sur `/api/`, `/storage/`, `/minio/` (`default.ssl.conf.template:41,50,56`) ; les locations assets sont bien imbriquées dans `location /` sans `add_header` propre (lignes 66-77), donc la CSP server-level est héritée ; la console MinIO est bloquée (403, ligne 57).
- **Headers de sécurité complets** : HSTS (`max-age=15768000; includeSubDomains`), `X-Content-Type-Options`, `X-Frame-Options SAMEORIGIN`, `Referrer-Policy`, CSP avec `upgrade-insecure-requests` — tous en `always` (`default.ssl.conf.template:29-33`).
- **Ports internes non exposés** : postgres, redis, minio n'ont aucun mapping de port hôte (`docker ps` : `5432/tcp`, `6379/tcp`, `9000/tcp` sans binding `0.0.0.0`). Seul nginx publie des ports.
- **Image API propre** : multi-stage build + user non-root `diggy` (`server/api/Dockerfile:1-13`). Image finale 294 MB.
- **Limites de ressources et rotation de logs partout** : chaque service a `deploy.resources.limits` + `logging json-file max-size 50m / max-file 3` (`docker-compose.yml`), vérifié live : `docker inspect diggy_api` → `json-file map[max-file:3 max-size:50m]`.
- **Healthchecks** présents sur postgres, redis, api, minio, nginx, frontend (`docker ps` : tous `(healthy)`).
- **Certbot fonctionnel** : cert valide jusqu'au **2026-09-26** (`openssl x509 -enddate` sur le volume), boucle `renew` toutes les 12 h + deploy-hook `.reload` relu toutes les 60 s par nginx (`docker-compose.ssl.yml:14-32`), `docker logs diggy_certbot` confirme un cycle sain.
- **Hygiène VPS** : `docker image prune -af --filter until=24h` quotidien (`/etc/cron.d/docker-image-prune`), disque à **9 %** (16G/193G), `alembic upgrade head` automatique au déploiement, smoke tests HTTP post-deploy dans le pipeline (`deploy.yml:118-145`).
- **Secrets bien gérés** : `VPS_SSH_KEY`/`VPS_HOST`/`VPS_USER` en secrets GitHub (`deploy.yml:96-97,106-107`), `.env` uniquement sur le VPS, requirements backend intégralement pinnés (`server/api/requirements.txt`).
- **Frontend prod sain** (le point "Vite dev server en prod" du brief est obsolète) : build statique servi par nginx (`server/frontend/Dockerfile`, target `production`), image 81.9 MB, assets hashés en `Cache-Control: public, immutable` + `index.html` en `no-store` (`server/frontend/nginx.prod.conf`), cache edge cohérent (`expires 1y` / `30d`).

---

## Findings

### [A5-01] Aucun backup planifié : le script existe, rien ne l'exécute
- **ID** : A5-01
- **Type** : bug
- **Sévérité** : critique
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - `ssh crontab -l` → une seule entrée : `0 3 * * * cd /root/diggy && docker compose exec -T nginx nginx -s reload` (aucun backup).
  - `systemctl list-timers --all` → 17 timers, tous système (apt, logrotate, sysstat…), aucun lié à Diggy.
  - `/etc/crontab` + `/etc/cron.d/` → seul `docker-image-prune`, pas de backup. `ls /var/spool/cron/crontabs/` → seul `root`.
  - `ls /var/lib/docker/volumes/diggy_backups/_data/postgres/` → **un unique dump** : `diggy_20260701_134313.sql.gz.gpg` (1.06 MB, 2026-07-01 13:43), soit un seul run manuel il y a 8 jours ; miroir MinIO daté du même instant.
  - Le mécanisme existe pourtant : `server/scripts/backup.sh` (pg_dump + mc mirror, chiffrement GPG si `BACKUP_ENCRYPTION_KEY` — présente dans le `.env` prod) et le service `backup` en profile compose (`docker-compose.yml:247-275`, usage documenté `docker compose run --rm backup`).
- **Constat** : toute la tuyauterie de backup (script, service compose, clé de chiffrement) est en place mais aucun scheduler ne l'appelle. La base prod (catalog 15 836 lignes, 30 migrations) et les buckets MinIO ne sont protégés que par un dump manuel vieux de 8 jours. Une corruption de `postgres_data` = perte de tout le delta depuis le 2026-07-01.
- **Recommandation** : ajouter une entrée crontab root (ex. `30 1 * * * cd /root/diggy && docker compose run --rm backup >> /var/log/diggy-backup.log 2>&1`) ou un systemd timer équivalent, + une vérification de fraîcheur (alerte si `latest.*` a plus de 26 h).
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A5-02] Backups stockés sur le même disque du même VPS, aucune copie offsite
- **ID** : A5-02
- **Type** : archi
- **Sévérité** : haute
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** : `backup.sh:15` → `BACKUP_DIR="/backups"` = volume Docker `diggy_backups` sur `/var/lib/docker/volumes/` du VPS lui-même (`docker volume inspect diggy_backups` → mountpoint local). Aucune commande d'upload externe dans le script (lignes 24-73). `RETENTION_DAYS=7` (`backup.sh:17`) + `find ... -mtime +7 -delete` (ligne 57).
- **Constat** : même si A5-01 était corrigé, un backup local sur `/dev/sda1` ne protège ni d'une panne disque, ni d'une compromission, ni d'une suppression du VPS. Effet pervers immédiat : le dump unique du 2026-07-01 a plus de 7 jours — le prochain run le **supprimera** via la rétention avant qu'une copie externe existe. Aucun snapshot Hostinger vérifiable depuis le VPS (rien dans les timers/crons ; non confirmable côté hyperviseur — à vérifier dans le panel Hostinger).
- **Recommandation** : pousser les dumps chiffrés vers un stockage externe (bucket S3/B2/rclone vers un autre provider) à la fin de `backup.sh` ; conserver ≥ 2 générations hors rétention locale. Vérifier dans le panel Hostinger si des snapshots VPS existent et le documenter.
- **Dépendances** : A5-01

### [A5-03] Restauration jamais testée ni documentée
- **ID** : A5-03
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** : aucun script/doc de restore dans le repo (`server/scripts/` ne contient que `backup.sh`, `generate_schema_doc.py`, `test_sources.py`, `.tidal_tokens.json`) ; aucune trace de restauration sur le VPS (volume backups intact depuis le 2026-07-01). Le dump est chiffré GPG (`backup.sh:36`) : sans procédure, la clé `BACKUP_ENCRYPTION_KEY` du `.env` est le seul chemin de déchiffrement, non documenté.
- **Constat** : un backup non restauré n'est pas un backup. Le chiffrement GPG ajoute un point de défaillance : si le `.env` du VPS disparaît en même temps que la base (scénario précis où on a besoin du backup), le dump est indéchiffrable si la clé n'est stockée nulle part ailleurs.
- **Recommandation** : écrire `docs/restore.md` (déchiffrer + `psql` + re-mirror MinIO), stocker la clé GPG dans un gestionnaire de secrets hors VPS, faire un test de restauration réel sur une DB jetable et le dater.
- **Dépendances** : A5-01, A5-02

### [A5-04] Le job CI `pip-audit` n'audite pas le projet (no-op)
- **ID** : A5-04
- **Type** : bug
- **Sévérité** : haute
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `.github/workflows/deploy.yml:66-76` :
  ```yaml
  audit:
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5 ...
      - run: pip install pip-audit && pip-audit --desc
  ```
- **Constat** : `pip-audit` sans argument audite **l'environnement Python courant**, dans lequel seul `pip-audit` et ses dépendances viennent d'être installés — jamais `server/api/requirements.txt`. Le job scanne donc le runner, pas Diggy. Triple neutralisation : mauvaise cible + `continue-on-error: true` + job absent du `needs:` de `deploy` (ligne 92). La CI donne un faux sentiment de couverture sécurité des dépendances.
- **Recommandation** : `pip-audit -r server/api/requirements.txt --desc`. Le maintenir non-bloquant est défendable pour un projet solo (éviter les deploys bloqués par une CVE sans fix), mais alors ajouter un run planifié (`schedule:` hebdo) avec notification, ou le rendre bloquant avec une allowlist `--ignore-vuln` explicite.
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A5-05] Build frontend prod non reproductible : le lockfile n'est pas utilisé dans l'image
- **ID** : A5-05
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `server/frontend/Dockerfile:9-11` (stage builder) :
  ```dockerfile
  COPY package.json .
  RUN npm install
  ```
  `package-lock.json` existe (`ls server/frontend`) et la CI, elle, utilise `npm ci` (`deploy.yml:19,86`).
- **Constat** : l'image prod résout les versions npm à chaque build (`npm install` sans lockfile copié), alors que lint et vitest tournent sur les versions verrouillées du lockfile. Ce qui est testé en CI n'est pas ce qui est déployé ; un patch de dépendance publié entre deux builds peut casser la prod silencieusement.
- **Recommandation** : `COPY package.json package-lock.json ./` puis `RUN npm ci` dans les deux stages (development et builder).
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A5-06] `--force-recreate` au déploiement redémarre toute la stack, DB comprise, à chaque push
- **ID** : A5-06
- **Type** : perf
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `deploy.yml:113` → `docker compose up -d --build --force-recreate`. Confirmé live : `docker ps` montre les 10 containers Diggy « Up 32 minutes », y compris `diggy_postgres`, `diggy_redis`, `diggy_minio`, `diggy_certbot` — tous recréés au dernier push.
- **Constat** : chaque push sur master recrée postgres/redis/minio/nginx même sans changement, provoquant une coupure complète (connexions DB tuées, queue Redis vidée de ses états transitoires, downtime front) alors que `up -d --build` seul ne recréerait que les services dont l'image ou la config a changé.
- **Recommandation** : retirer `--force-recreate` ; `docker compose up -d --build` suffit (compose recrée ce qui a changé). Si le flag couvrait un cas réel (env modifié non détecté), le documenter et cibler : `--force-recreate api worker worker_enrich beat frontend`.
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A5-07] Migrations Alembic appliquées APRÈS la mise en ligne du nouveau code
- **ID** : A5-07
- **Type** : archi
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `deploy.yml:113-114` : `docker compose up -d --build --force-recreate && docker compose exec -T api python -m alembic upgrade head`.
- **Constat** : entre le démarrage du nouveau container api et la fin d'`alembic upgrade head`, le nouveau code sert du trafic sur l'ancien schéma (fenêtre de quelques secondes à minutes selon la migration). Sur un modèle avec colonne ajoutée, chaque requête touchant la table 500 pendant cette fenêtre.
- **Recommandation** : exécuter la migration avant de basculer : `docker compose up -d postgres && docker compose run --rm api python -m alembic upgrade head && docker compose up -d --build`. Faible urgence vu le trafic actuel, mais gratuit à corriger.
- **Dépendances** : A5-06 (même bloc de script)

### [A5-08] Les workers/beat exécutent le code du repo hôte via bind mounts en prod, pas celui de l'image
- **ID** : A5-08
- **Type** : archi
- **Sévérité** : moyenne
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** : `docker-compose.yml:98-100` (worker), `126-128` (worker_enrich), `154-157` (beat) — dans le compose de **base**, donc actif en prod :
  ```yaml
  volumes:
    - ./server/api:/app
    - ./server/workers:/app/workers
  ```
  L'API, elle, n'a ce mount que dans `docker-compose.override.yml:1-4` (local uniquement).
- **Constat** : structurellement forcé — le contexte de build est `./server/api`, donc `server/workers/` ne peut pas être dans l'image ; le bind mount est le contournement. Conséquences : l'image des workers ne reflète pas ce qui tourne (rollback d'image inopérant), `git reset --hard` du deploy change le code sous les processus en cours avant leur recreate, et les fichiers root du repo hôte sont lus par l'user container `diggy` (uid 1000) — fonctionne tant que tout est world-readable.
- **Recommandation** : remonter le contexte de build à `./server` avec un Dockerfile copiant `api/` et `workers/` (+ `.dockerignore` dédié), et supprimer les bind mounts du compose de base (les garder dans l'override local).
- **Dépendances** : A5-09 (même refonte de contexte)

### [A5-09] Aucun `.dockerignore` dans les contextes de build ; celui de la racine est inopérant
- **ID** : A5-09
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `Glob **/.dockerignore` → un seul fichier, à la racine du repo. Or les contextes sont `./server/api` et `./server/frontend` (`docker-compose.yml:51-52,166-168`) — Docker ne lit le `.dockerignore` qu'à la racine du **contexte**. `server/api/Dockerfile:11` fait `COPY . .` et `ls server/api` montre `__pycache__/` présent sur le disque (copié dans l'image). Côté frontend, `node_modules/` et `dist/` existent localement et seraient copiés par le `COPY . .` de `Dockerfile:5,12` (sur le VPS ils sont absents car non versionnés, l'impact prod est limité au cache/contexte).
- **Constat** : le `.dockerignore` racine (qui exclut `.env`, `tests`, `docs`, `_design`…) ne protège aucun des deux builds réels. `__pycache__` hôte entre dans l'image API ; en build local, des centaines de Mo de `node_modules` Windows partent dans le contexte frontend et écrasent le `npm install` de l'image.
- **Recommandation** : créer `server/api/.dockerignore` (`__pycache__`, `*.pyc`, `.pytest_cache`) et `server/frontend/.dockerignore` (`node_modules`, `dist`), supprimer ou raccourcir celui de la racine (aucun build ne l'utilise).
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A5-10] Workflow deploy sans garde de concurrence
- **ID** : A5-10
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `.github/workflows/deploy.yml:1-7` — aucun bloc `concurrency:` dans le workflow.
- **Constat** : deux pushes rapprochés sur master lancent deux pipelines qui peuvent atteindre le step Deploy en parallèle : deux `git reset --hard` + `docker compose up --build` entrelacés sur le VPS, avec un état final non déterministe (le deploy du commit N peut finir après celui du commit N+1).
- **Recommandation** : ajouter en tête de workflow :
  ```yaml
  concurrency:
    group: deploy-prod
    cancel-in-progress: false
  ```
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A5-11] Images de base non pinnées : `minio/minio:latest`, `certbot/certbot:latest`, tags flottants partout
- **ID** : A5-11
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `docker-compose.yml:191` → `minio/minio:latest` ; `docker-compose.ssl.yml:27` → `certbot/certbot` (implicite `:latest`) ; `docker-compose.yml:218` → `nginx:alpine` ; `server/api/Dockerfile:1,6` → `python:3.13-slim` ; `server/frontend/Dockerfile:1,8,15` → `node:22-alpine`, `nginx:alpine`. Confirmé live : `docker images` → `minio/minio latest`, `certbot/certbot latest`.
- **Constat** : chaque `docker compose up --build` (donc chaque push, cf. A5-06) peut tirer une nouvelle version majeure de MinIO ou certbot sans revue. MinIO est le cas le plus risqué : c'est un service de données (breaking changes de format/API déjà survenus historiquement chez MinIO) et il serait mis à jour silencieusement pendant un deploy applicatif.
- **Recommandation** : pinner au minimum MinIO sur une release datée (`minio/minio:RELEASE.2025-xx-xx...`) et certbot sur un tag versionné ; garder `postgres:16-alpine`/`redis:7-alpine` (pin majeur acceptable). Optionnel : digests pour les images de build.
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A5-12] Port 8080 HTTP exposé publiquement en prod, en plus de 80/443
- **ID** : A5-12
- **Type** : securite
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `docker ps` → `diggy_nginx ... 0.0.0.0:80->80, 0.0.0.0:443->443, 0.0.0.0:8080->80`. Cause : `docker-compose.yml:227` (`"${NGINX_PORT:-8080}:80"`) reste actif en prod car le chaînage `COMPOSE_FILE` **ajoute** les ports de `docker-compose.ssl.yml:3-5` au lieu de les remplacer, et `grep NGINX_PORT /root/diggy/.env` → absent (défaut 8080 appliqué).
- **Constat** : le port 8080 sert le server block HTTP (redirect 301 + ACME), donc pas de fuite de contenu, mais c'est une surface d'écoute publique inutile qui trouble les scans et duplique le port 80.
- **Recommandation** : soit `NGINX_PORT=127.0.0.1:8080` n'est pas possible avec ce format — préférer déplacer le mapping `8080:80` dans `docker-compose.override.yml` (local only, non versionné sur le VPS via COMPOSE_FILE) et le retirer du compose de base, soit poser `NGINX_PORT` avec un binding loopback (`"127.0.0.1:8080:80"` en dur dans l'override).
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A5-13] Hygiène Docker VPS : container certbot fantôme depuis 9 jours + 12 volumes anonymes orphelins
- **ID** : A5-13
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `docker ps` → `diggy-certbot-run-143d85a7f153  Up 9 days` ; `docker inspect` → entrypoint `while :; do certbot renew; sleep 12h; done` avec en Args résiduels `certonly --standalone ... -d diggy-music.fr` (un `docker compose run certbot certonly` du 2026-06-29 dont l'entrypoint shell a ignoré les args et bouclé). `docker volume ls -q -f dangling=true | wc -l` → **12**.
- **Constat** : deux boucles `certbot renew` tournent en parallèle (le service + le container run oublié) — sans danger (verrous certbot + « not yet due »), mais c'est un process orphelin. Les 12 volumes anonymes sont des résidus de recreates (le prune quotidien ne couvre que les images, pas les volumes).
- **Recommandation** : `docker rm -f diggy-certbot-run-143d85a7f153` et `docker volume prune` lors d'une fenêtre de maintenance (hors de cet audit — aucune action effectuée). Pour l'avenir : `docker compose run --rm ...` systématique.
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A5-14] Cron 03:00 « reload nginx » redondant avec le mécanisme `.reload` du compose SSL
- **ID** : A5-14
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `crontab -l` → `0 3 * * * ... nginx -s reload` ; or `docker-compose.ssl.yml:13-24` fait déjà recharger nginx dans les 60 s quand certbot pose le flag `/etc/letsencrypt/.reload` (deploy-hook ligne 32), et `deploy.yml:115` reload aussi après chaque deploy.
- **Constat** : trois mécanismes de reload coexistent. Le cron quotidien est l'héritage d'avant le flag `.reload` ; il est inoffensif mais entretient la confusion sur « qui recharge nginx et pourquoi » (il a d'ailleurs été le seul cron trouvé, masquant presque l'absence de cron backup).
- **Recommandation** : supprimer l'entrée crontab (ou la commenter avec un mot d'explication) une fois A5-01 traité, pour que le crontab reflète les vrais jobs.
- **Dépendances** : A5-01 (profiter du même passage sur le crontab)

### [A5-15] Sentry est câblé ET le DSN est renseigné en prod — la croyance « Sentry non configuré » est obsolète
- **ID** : A5-15
- **Type** : dead-doc
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : moyenne
- **Preuve** : code : `server/api/main.py:38-46` et `server/workers/celery_app.py:10-22` (`sentry_sdk.init` si `SENTRY_DSN`, traces 0.2, env via `SENTRY_ENV`), `sentry-sdk[fastapi,celery]==2.29.1` pinné (`requirements.txt:20`). Prod : `grep '^SENTRY' /root/diggy/.env` → `SENTRY_DSN` longueur **95** caractères (non vide) + `SENTRY_ENV` longueur 10 (valeurs non lues, seules les longueurs ont été extraites).
- **Constat** : contrairement au brief d'audit (« Sentry DSN non configuré — connu »), le DSN est bien posé sur le VPS et le code s'initialise pour l'API ET les workers Celery. L'effort d'« activation » est donc nul côté code/config ; ce qui reste incertain, c'est la **réception effective** d'événements (DSN valide ? projet Sentry vivant ? — invérifiable en read-only depuis le VPS).
- **Recommandation** : vérifier dans l'UI Sentry que des événements/transactions arrivent (ou déclencher une erreur de test en préprod) ; mettre à jour le brief/les notes internes qui affirment que Sentry n'est pas configuré.
- **Dépendances** : aucune

### [A5-16] `.env.example` divergent du code : `JWT_SECRET` absent alors qu'il est obligatoire au boot
- **ID** : A5-16
- **Type** : dead-doc
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `.env.example:18` documente `SECRET_KEY=...`, mais le code lit `JWT_SECRET` en accès strict : `server/api/auth.py:10` → `JWT_SECRET = os.environ["JWT_SECRET"]` (KeyError au démarrage s'il manque). Aucune occurrence de `SECRET_KEY` dans `server/` (grep). Manquent aussi à l'exemple : `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` (OAuth), `SENTRY_DSN`/`SENTRY_ENV`, `BACKUP_ENCRYPTION_KEY` (utilisée par `backup.sh:27`), `TRACKID_*` partiellement présents. CLAUDE.md (section env) liste d'ailleurs `JWT_SECRET` comme requis — l'exemple est en retard.
- **Constat** : un setup neuf depuis `.env.example` échoue au boot de l'API avec une KeyError non explicite, et laisse croire qu'une variable `SECRET_KEY` sert à quelque chose.
- **Recommandation** : remplacer `SECRET_KEY` par `JWT_SECRET` et compléter l'exemple avec les variables Google/Sentry/Backup (valeurs factices).
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A5-17] Stack locale incohérente : nginx local sans server block et proxy Vite vers un hostname Docker
- **ID** : A5-17
- **Type** : bug
- **Sévérité** : basse
- **Effort estimé** : M (1h-1j)
- **Confiance** : moyenne
- **Preuve** : en local (base + override, sans ssl.yml) nginx monte `server/nginx/default.conf` (`docker-compose.yml:229`) qui est **vide** (« intentionally empty ») → aucun server block, le port 8080 publié ne sert rien, et le healthcheck du compose de base vise `https://127.0.0.1:443` (`docker-compose.yml:242`) qui ne peut pas répondre sans la config SSL. Côté dev : `server/frontend/vite.config.js:16-19` proxifie `/api` vers `http://api:8000`, hostname résolvable uniquement dans `diggy_network`, alors que le service `api` ne publie aucun port hôte et que le flux documenté est « `npm run dev` sur l'hôte » (CLAUDE.md, Dev Commands).
- **Constat** : tel que versionné, le chemin local documenté (« local = port 8080 HTTP » + vite dev sur l'hôte) semble non fonctionnel : nginx local est un container unhealthy qui ne sert rien, et le proxy Vite ne peut joindre `api:8000` que si Vite tourne DANS le réseau Docker (le target `development` du Dockerfile frontend existe mais aucun service compose ne l'utilise). Confiance moyenne : il existe peut-être un usage local non versionné (edit temporaire de `default.conf`, entrée hosts, service ad hoc).
- **Recommandation** : trancher un seul flux local et l'aligner : soit un `default.conf` local minimal (proxy `/api` → api:8000, reste → host.docker.internal:5173 ou frontend), soit publier `8000:8000` sur l'api dans l'override et pointer le proxy Vite sur `http://localhost:8000`. Corriger le healthcheck nginx du compose de base (tester `http://127.0.0.1:80`) ou le déplacer dans ssl.yml.
- **Dépendances** : aucune

### [A5-18] HTTP/2 non activé sur le listener TLS
- **ID** : A5-18
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `server/nginx/default.ssl.conf.template:17` → `listen 443 ssl;` sans `http2 on;` (ni `listen 443 ssl http2;`).
- **Constat** : tout le trafic HTTPS reste en HTTP/1.1 : pas de multiplexage pour les assets hashés (js/css/woff2/images) ni pour les rafales d'appels `/api/` du frontend. Gain gratuit sur mobile, cible principale du projet (chantier R1).
- **Recommandation** : ajouter `http2 on;` dans le server block 443 (syntaxe nginx ≥ 1.25.1, l'image `nginx:alpine` actuelle la supporte). Optionnel au même endroit : `ssl_session_cache shared:SSL:10m;`.
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A5-19] CI : pas de cache npm et version Node différente de l'image de prod
- **ID** : A5-19
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `deploy.yml:14-16,82-84` → `actions/setup-node@v4` avec `node-version: "20"` mais **sans** `cache: "npm"` (alors que setup-python a `cache: "pip"`, lignes 31,56,74) ; `npm ci` complet exécuté dans 2 jobs (lint-frontend, test-frontend). L'image de build prod utilise `node:22-alpine` (`server/frontend/Dockerfile:1,8`).
- **Constat** : chaque pipeline retélécharge deux fois l'arbre npm (temps + flakiness réseau), et la CI valide le frontend sous Node 20 quand la prod builde sous Node 22 — écart mineur mais gratuit à éliminer.
- **Recommandation** : ajouter `cache: "npm"` + `cache-dependency-path: server/frontend/package-lock.json` aux deux `setup-node`, et aligner `node-version: "22"`.
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A5-20] Workers Celery et beat sans healthcheck
- **ID** : A5-20
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `docker-compose.yml:80-163` — les services `worker`, `worker_enrich`, `beat` n'ont aucun bloc `healthcheck` (contrairement à postgres/redis/api/minio/nginx/frontend). `docker ps` le confirme : ce sont les seuls containers Diggy sans état `(healthy)`.
- **Constat** : un worker dont le process celery est vivant mais déconnecté du broker (ou bloqué) reste « Up » indéfiniment ; personne n'est alerté si `crawl_radar` ou l'enrichissement s'arrêtent de consommer. Avec Sentry actif (A5-15) les exceptions remontent, mais pas les blocages silencieux.
- **Recommandation** : ajouter `healthcheck: celery -A workers.celery_app inspect ping -d celery@$$HOSTNAME` (timeout large, interval 60s+) sur les deux workers ; pour beat, un test sur la fraîcheur du fichier schedule suffit.
- **Dépendances** : aucune

---

## Non couvert

- **Snapshots Hostinger** : invérifiables depuis le VPS (aucun agent/timer visible) ; seule la console Hostinger peut confirmer ou infirmer une couverture snapshot au niveau hyperviseur (à faire manuellement, pertinent pour A5-02).
- **Réception effective des événements Sentry** : le DSN est posé (A5-15) mais la vérification nécessite l'UI Sentry, hors de portée read-only.
- **Temps réels du pipeline CI** : la config a été analysée (jobs parallèles, points de cache) mais les durées effectives des runs GitHub Actions n'ont pas été consultées (pas d'accès `gh` au repo distant tenté, hors périmètre).
- **Audit fin du contenu des images** (couches, CVE des images de base) : non réalisé, seul le pinning et la structure des Dockerfiles ont été évalués.
- Le second projet hébergé sur le VPS (`dofusdepioute`, container + image vus dans `docker ps`/`docker images`) : hors périmètre Diggy, simplement noté — il partage les ressources de la machine.

# A5 — Infra / CI (audit global 2026-08-24)

Périmètre : Dockerfiles (`server/Dockerfile`, `server/frontend/Dockerfile`, `postgres/Dockerfile`, `worker/*/Dockerfile`), `docker-compose.yml` + `.ssl.yml` + override, `server/nginx/`, `.github/workflows/deploy.yml`, `server/.dockerignore`, `server/scripts/` (backup), `docs/restore.md`, + vérifications SSH read-only sur le VPS (crontab, `docker compose ps`, conf Redis effective, logs backup/covers, taille `track_embeddings`).

## Ce qui va bien

- **Piège pgvector C9.a structurellement réglé** : `deploy.yml:141` fait `docker compose up -d --no-deps postgres` AVANT `alembic upgrade head` à chaque deploy (commit 5a29e1c) — l'ordonnancement « recréer postgres avant la migration » n'est plus un geste manuel one-time, il est câblé. Aucun résidu bancal constaté.
- **Mitigation partielle du piège « IP amont périmée »** : `deploy.yml:144` recharge nginx (`nginx -s reload || true`) après `up -d` — le chemin CI est couvert ; seul le deploy manuel reste exposé (cf. A5-07).
- **Gates CI réels et bloquants** : `pip-audit` est bien dans le `needs:` du job deploy (`deploy.yml:119`), sans `continue-on-error`, avec SEULEMENT les 2 ignore-vuln documentés sans fix upstream ; pytest tourne sur `pgvector/pgvector:pg16` aligné prod ; coverage gate 55 ; Prettier gaté ; `concurrency: deploy-prod` avec `cancel-in-progress: false` (pas de deploy tronqué).
- **Hotfix jinja2 pinné** : `server/api/requirements.txt:9` `jinja2==3.1.6` avec commentaire expliquant la casse AV2.
- **Redis persisté conforme** : vérifié en prod — `appendonly yes`, `appendfsync everysec`, `dir /data` sur le volume nommé `diggy_redis_data` ; un recreate ne perd plus le curseur backfill.
- **Backups vivants, chiffrés, alertés** : cron 01:30 + freshness 09:00 (crontab VPS), log du jour `OK: latest local backup is 7h old … .sql.gz.gpg` + `OK: latest offsite backup is 7h old` ; `BACKUP_ENCRYPTION_KEY`, `RCLONE_REMOTE` ET `BACKUP_ALERT_WEBHOOK` tous présents dans le `.env` VPS (noms vérifiés, valeurs non lues). Date du dernier test de restore dans `docs/restore.md` : **2026-07-10**, honnête et < 6 mois (mais voir A5-05).
- **Nginx conforme à ses propres pièges** : headers de sécu au niveau server avec `always`, AUCUN `add_header` dans les locations imbriquées d'assets (elles héritent la CSP), `^~` sur `/api/` `/storage/` `/minio/`, `client_max_body_size 12M` couplé au 10M applicatif, `upgrade-insecure-requests` conservé, images pinnées (`nginx:1.29-alpine`, `certbot:v5.7.0`, `minio RELEASE.2025-09-07`).
- **Caps mémoire cohérents avec la RAM** : somme des limites = 12,4 G (pg 1G + redis 512M + api 3G + worker 2G + worker_enrich 2G + beat 256M + frontend 128M + minio 3G + nginx 512M) vs 15,6 G — ~3 G de marge hôte. Commentaires AV8/AV10 à jour dans le compose (`shm_size: 256mb`, `--loglevel=warning`, healthchecks 60s, `--max-memory-per-child` sous les caps). Autoheal + healthchecks fonctionnels : 11/11 conteneurs healthy au moment de l'audit.
- **`.dockerignore` par contexte OK** : `server/.dockerignore` exclut exactement les répertoires hors runtime (`frontend/ nginx/ scripts/ deezer/`) et le commentaire rappelle de NE PAS exclure `api/alembic/` ; aucun nouveau répertoire runtime sous `server/` n'est silencieusement exclu. `server/frontend/.dockerignore` exclut `node_modules`/`dist`.
- **Cron covers C7 (13:30)** : toujours vivant et toujours utile — le run du jour a drainé 2500 albums (2060 covers uploadées, 2 erreurs), pas encore convergé au no-op ; conforme à son commentaire « Remove once drained ». À re-vérifier début septembre (mais voir A5-04 : il tourne en réalité à 15:30 Paris).

---

### [A5-01] Cap mémoire postgres 1G face à ~3,5 G de données pgvector à venir
- **Type** : perf
- **Sévérité** : haute
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `docker-compose.yml:9-13` (`postgres` → `limits.memory: 1G`) ; mesure prod : `SELECT count(*), pg_size_pretty(pg_total_relation_size('track_embeddings'))` → **69 144 lignes | 940 MB** (table + index HNSW), soit ~24 % du backfill visé (~266k). Extrapolation linéaire : **~3,5-3,6 GB** à terme. Migration `0049` : index HNSW `vector_cosine_ops` (paramètres par défaut). Aucun tuning `shared_buffers` dans le service (image aux défauts : 128 MB).
- **Constat** : le cgroup 1G du conteneur postgres compte AUSSI le page cache de ses process. Aujourd'hui déjà, la seule relation `track_embeddings` (940 MB) ne tient plus sous le cap avec le reste de la base ; à ~266k embeddings, chaque recherche ANN « sonne comme » (C9.b, déployé) traversera un graphe HNSW de plusieurs Go à travers un cache plafonné à 1G → thrash disque systématique, latence dégradée, et pression accrue quand C9.c branchera la reco hybride. La RAM hôte a la marge (somme des caps 12,4G / 15,6G).
- **Recommandation** : relever le cap postgres 1G → 3G (la somme des caps passe à ~14,4G, encore tenable ; sinon 2G + arbitrage du cap api 3G peu utilisé) et poser `shared_buffers` ~512MB-1GB via `command: postgres -c shared_buffers=768MB` dans le compose. À faire AVANT la fin du backfill local ~266k pour que l'éval à l'échelle (C9.a) mesure des latences réalistes.
- **Dépendances** : à séquencer avec le run backfill C9.a en cours ; recreate postgres = coupure brève (fenêtre calme).
- **Tags** : QW-c

### [A5-02] backup.sh ne mirrore que 3 buckets MinIO sur 6
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/scripts/backup.sh:74` → `BUCKETS="artworks catalog-artworks artist-artworks"` ; or `server/api/services/image_service.py:29-34` déclare 6 buckets : + `playlist-artworks`, `set-artworks`, `album-artworks` (C7, clé = id album).
- **Constat** : le mirror MinIO local (assumé local-only, les artworks étant re-fetchables) est incomplet par rapport à son propre objectif : les covers de playlists, de sets et d'albums ne sont dans AUCUN backup. La liste a été figée avant C6/C7 et jamais rafraîchie — dérive silencieuse classique d'une liste en dur (le prochain bucket sera oublié pareil).
- **Recommandation** : remplacer la liste en dur par une énumération dynamique (`mc ls diggy` → boucle sur tous les buckets), ou a minima ajouter les 3 manquants + un commentaire pointant `image_service.py` comme source de vérité.
- **Dépendances** : aucune.
- **Tags** : —

### [A5-03] Binaire `mc` téléchargé non-pinné à CHAQUE run de backup (dépendance réseau au moment du backup)
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `docker-compose.yml:351-358` (service backup) : `apk add … rclone` puis `curl -sSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc` à chaque exécution — dernière release, aucun checksum, aucune version.
- **Constat** : (1) supply chain : un binaire exécuté en prod avec les credentials MinIO root est tiré du réseau sans pinning ni vérification d'intégrité ; (2) disponibilité : si `dl.min.io` (ou le miroir apk) est indisponible à 01:30, `mc alias set` échoue et `backup.sh` (`set -eu`) sort AVANT la section offsite → le dump local existe mais **pas de copie offsite cette nuit-là** (le freshness 09:00 alertera, mais l'échec était évitable) ; (3) coût : ~re-télécharge apk+mc toutes les nuits.
- **Recommandation** : construire une petite image backup dédiée (Dockerfile alpine + `apk add postgresql16-client gnupg rclone minio-client` versions du repo apk, ou `mc` pinné par version + sha256), référencée par le service à la place d'`alpine:3.20` + install au run. Bonus : réordonner backup.sh pour faire la copie offsite du dump AVANT le mirror MinIO (le dump chiffré est la donnée critique).
- **Dépendances** : aucune.
- **Tags** : —

### [A5-04] `CRON_TZ=Europe/Paris` silencieusement ignoré par le cron d'Ubuntu 24.04 — tous les crons VPS tournent en UTC
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : crontab VPS (lu via ssh) déclare `CRON_TZ=Europe/Paris` avant l'entrée minio « Mon 00:30 Europe/Paris » ; or syslog : `2026-08-24T00:30:01 UTC … CMD (… docker compose restart minio …)` (idem 08-17) → exécution à **00:30 UTC = 02:30 Paris**. `dpkg -l cron` = `3.0pl1-184ubuntu2` (vixie), `man cron` ne mentionne pas CRON_TZ. TZ système = `Etc/UTC`.
- **Constat** : toutes les heures « pensées Paris » du crontab dérivent de +2h en été : backup à 01:30 UTC = **03:30 Paris** (chevauche `crawl_trackid_latest` 03:30 Paris — pg_dump concurrent d'un crawl écrivain, pas bloquant mais non voulu), covers C7 à 13:30 UTC = **15:30 Paris** (la mémoire projet dit « 13:30 Paris »), minio restart à 02:30 Paris. Rien de cassant aujourd'hui, mais la variable no-op est un piège dormant : la prochaine entrée calée « Paris » (ex. pour éviter la fenêtre Deezer 05:00 Paris) ratera sa fenêtre de 1-2h selon la saison.
- **Recommandation** : supprimer la ligne `CRON_TZ` et écrire les heures en UTC avec un commentaire de conversion par entrée (ou installer `cronie` qui supporte CRON_TZ). Corriger au passage les mentions « 13:30 Paris »/« 00:30 Paris » dans la mémoire projet et le commentaire du crontab.
- **Dépendances** : aucune (édition crontab VPS = geste OPS hors périmètre de cet audit).
- **Tags** : —

### [A5-05] `docs/restore.md` ignore pgvector : une restauration hors du postgres custom échoue, et le dernier test de restore précède le schéma vectoriel
- **Type** : doc
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `grep -i 'vector\|extension\|diggy-postgres' docs/restore.md` → **0 résultat**. Dernier test de restore : `docs/restore.md:229` « Dernier test réussi : **2026-07-10** » — antérieur à la migration 0049 (C9.a, 2026-08) qui a introduit `CREATE EXTENSION vector` + la colonne `Vector(1280)`. La prod tourne désormais sur l'image custom `diggy-postgres:16-pgvector` (`docker-compose.yml:5-6`).
- **Constat** : le scénario DR « repartir d'un hôte neuf » du doc restaurera un dump qui contient `CREATE EXTENSION vector` et des colonnes `vector` — sur un `postgres:16` vanilla (le réflexe naturel en urgence), le restore échoue à mi-chemin. Le doc ne dit nulle part qu'il faut d'abord builder/utiliser l'image `./postgres`. Par ailleurs la procédure testée le 2026-07-10 n'a jamais exercé un dump contenant `track_embeddings` (aujourd'hui 940 MB — le dump grossit aussi).
- **Recommandation** : ajouter à `docs/restore.md` un pré-requis explicite « l'hôte de restauration doit exécuter l'image `postgres/Dockerfile` (ou tout postgres16+pgvector ≥ 0.8) » + re-jouer un test de restore complet post-0049 et rafraîchir la date « dernier test ».
- **Dépendances** : le re-test peut attendre la fin du backfill C9.a (dump plus représentatif).
- **Tags** : —

### [A5-06] Step « Setup SSH » : `ssh-keyscan` TOFU, erreurs avalées — l'échec déjà observé se reproduira
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `deploy.yml:129` → `ssh-keyscan -H "$VPS_HOST" >> ~/.ssh/known_hosts 2>/dev/null` : stderr jeté, code retour non vérifié, aucune retry. Mémoire projet (redis-persistence) : « CI deploy avait échoué à “Setup SSH” » (2026-08-21).
- **Constat** : deux problèmes : (1) robustesse — un échec transitoire de keyscan (réseau, VPS chargé) laisse `known_hosts` vide, le step passe VERT et c'est le step Deploy qui échoue plus loin avec « Host key verification failed », diagnostic brouillé (exactement l'incident vécu) ; (2) sécu — trust-on-first-use à chaque run : la clé host est re-scannée du réseau à chaque deploy, un MITM entre GitHub et le VPS obtiendrait la session SSH (et la clé privée du deploy n'exécute pas de commande restreinte).
- **Recommandation** : figer l'empreinte host dans un secret `VPS_KNOWN_HOSTS` (sortie one-shot de `ssh-keyscan`) écrit tel quel dans `~/.ssh/known_hosts` — supprime à la fois le TOFU et la dépendance réseau du step. À défaut, au minimum `ssh-keyscan … || exit 1` avec 2-3 retries.
- **Dépendances** : aucune.
- **Tags** : —

### [A5-07] IP amont nginx périmée sur deploy manuel — mitigation structurelle possible (resolver Docker + variable)
- **Type** : archi
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `server/nginx/default.ssl.conf.template:45-82` — tous les `proxy_pass http://api:8000` / `http://minio:9000/` / `http://frontend:80` en hostname statique : nginx résout au chargement de la conf et fige l'IP. Piège documenté (mémoire redis-persistence) : deploy manuel `up -d` recréant l'api → 502 jusqu'à `restart nginx`. Le chemin CI est couvert par le reload (`deploy.yml:144`) ; le chemin manuel repose sur la mémoire humaine.
- **Constat** : le pattern nginx standard pour des upstreams Docker éphémères est le resolver embarqué : `resolver 127.0.0.11 valid=30s;` + `set $api_upstream http://api:8000;` + `proxy_pass $api_upstream;` — la résolution devient par-requête (cache 30s), un recreate de l'api ne casse plus jamais le proxy. Attention à la sémantique : avec une variable, `proxy_pass` ne réécrit plus l'URI implicitement — la location `/storage/` qui strippe le préfixe via le `/` final devra le faire explicitement (`rewrite ^/storage/(.*)$ /$1 break;`), et les locations assets imbriquées doivent être re-testées (piège add_header/héritage déjà en place).
- **Recommandation** : finding archi à planifier (pas un fix à exécuter) : basculer les 3 upstreams sur resolver+variable dans `default.ssl.conf.template`, vérif RENDU + `/storage/` après coup. Alternativement, statuer que le reload CI suffit et ritualiser `restart nginx` dans une checklist de deploy manuel.
- **Dépendances** : tester conjointement avec A5-12 (dédup des conf) si traité.
- **Tags** : —

### [A5-08] Health check post-deploy : un seul curl après un sleep fixe de 15 s
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `deploy.yml:152-155` → `sleep 15` puis `curl -sfLk https://localhost/api/health || exit 1` (un seul essai).
- **Constat** : le boot de l'api (2 workers uvicorn, imports, `sentry_sdk.init`) peut dépasser 15 s sur le VPS sous charge (fair-use, throttle AV10) : le deploy serait marqué FAILED alors que la prod converge quelques secondes plus tard — faux négatif qui pousse à re-pousser ou à ignorer le rouge. L'inverse (vert trompeur) est couvert par le smoke test qui suit.
- **Recommandation** : boucle de retry bornée (ex. 10 essais × 6 s) à la place du sleep+curl unique.
- **Dépendances** : aucune.
- **Tags** : —

### [A5-09] Aucun `timeout-minutes` sur les jobs CI — un SSH pendu bloque le pipeline jusqu'à 6 h
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `deploy.yml` — aucun `timeout-minutes` sur les 6 jobs ; le step Deploy exécute `docker compose build` + migration sur le VPS via ssh (`ServerAliveInterval` protège la session, pas la durée de la commande distante).
- **Constat** : un build docker coincé (apt/npm qui pend, VPS throttlé) laisse le job courir jusqu'au défaut GitHub de 360 min ; combiné à `concurrency: deploy-prod` sans annulation, les pushes suivants s'empilent derrière pendant des heures.
- **Recommandation** : `timeout-minutes: 25` sur le job deploy (~build VPS typique + marge), `10-15` sur les jobs lint/test/audit.
- **Dépendances** : aucune.
- **Tags** : —

### [A5-10] Redis sans `maxmemory` sous un cap cgroup 512M : la saturation finira en SIGKILL au lieu d'une erreur propre
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : conf effective prod (redis-cli) : `maxmemory 0`, `maxmemory-policy noeviction` ; `docker-compose.yml:61-65` → cap `memory: 512M`.
- **Constat** : Redis porte broker Celery + caches reco/similarité (TTL 25h par user) + curseurs + rate-limit windows. Avec `maxmemory 0`, Redis ne refuse ni n'évince jamais : si le dataset + surcoût AOF approche 512M, c'est le cgroup qui OOM-kill le process (signal 9) — recovery via AOF + restart policy, mais perte des connexions en vol et aucune télémétrie applicative. Un `maxmemory` sous le cap transformerait ça en erreurs `OOM command not allowed` visibles côté app/Sentry.
- **Recommandation** : ajouter `--maxmemory 400mb` à la command (en gardant `noeviction` : le broker Celery ne doit JAMAIS évincer — une policy d'éviction perdrait des tâches). Surveiller `INFO memory` au préalable pour confirmer la marge actuelle.
- **Dépendances** : aucune.
- **Tags** : —

### [A5-11] Build des images sur le VPS de prod à chaque deploy — CPU fair-use consommé par la CI
- **Type** : archi
- **Sévérité** : basse
- **Effort estimé** : L
- **Confiance** : haute
- **Preuve** : `deploy.yml:140` → `docker compose build` s'exécute SUR le VPS (npm ci + vite build frontend, pip install serveur, compilation pgvector si le cache saute) ; contexte : VPS 4 vCPU sous police fair-use, throttle déjà trippé (chantier AV10, mémoire hostinger-cpu-throttle).
- **Constat** : chaque push master fait payer au VPS de prod plusieurs minutes de build multi-images, en concurrence avec les drains horaires (Beatport 6h→23h) et le trafic. Les caches Docker amortissent le cas courant, mais un cache froid (upgrade de base image, prune) ou une rafale de pushes ajoute une charge notable à la fenêtre fair-use — précisément la ressource sous surveillance.
- **Recommandation** : à terme, builder dans GitHub Actions et pousser sur un registry (GHCR), le VPS ne faisant plus que `pull` + `up -d` (gain secondaire : rollback = re-tag). C'est un chantier (secrets registry, tags, nettoyage), pas un quick win — d'où L. En attendant, éviter les pushes en fenêtre de throttle reste la mitigation documentée.
- **Dépendances** : restructure `deploy.yml` — à coordonner avec A5-06/A5-08/A5-09 si le workflow est repris.
- **Tags** : —

### [A5-12] `default.conf` / `empty.conf` : deux fichiers « intentionally empty » identiques montés au même endroit
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/nginx/default.conf` et `server/nginx/empty.conf` ont le même contenu (1 ligne de commentaire). `docker-compose.yml:308` monte `default.conf` → `/etc/nginx/conf.d/default.conf` ; `docker-compose.ssl.yml:8` re-monte `empty.conf` sur LA MÊME cible (le merge compose fait gagner l'overlay en prod).
- **Constat** : duplication sans fonction : en prod seul `empty.conf` est effectif, en local seul `default.conf` l'est — deux noms pour le même vide, et un lecteur peut croire que `default.conf` porte une conf locale (CLAUDE.md dit d'ailleurs « default.conf is intentionally empty » sans mentionner `empty.conf`). Zéro impact runtime.
- **Recommandation** : supprimer l'un des deux et ne référencer que l'autre dans les deux compose (ou documenter la paire d'une ligne dans CLAUDE.md section Nginx).
- **Dépendances** : trivial ; à regrouper avec A5-07 si la conf nginx est reprise.
- **Tags** : —

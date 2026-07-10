# Procédure de restauration des sauvegardes

> Couvre la restauration des dumps PostgreSQL (volume local + offsite Google Drive)
> et du mirror MinIO. Rédigé pour le lot AU2-L1 (findings audit A5-02 / A5-03).
>
> Rappel du dispositif de sauvegarde :
> - Cron VPS **01:30** : `docker compose run --rm backup` → dump PostgreSQL chiffré GPG
>   (`/backups/postgres/diggy_YYYYmmdd_HHMMSS.sql.gz.gpg`, rétention locale 7 jours)
>   + copie offsite rclone (`gdrive:diggy-backups/postgres`, rétention 14 dumps)
>   + mirror MinIO (`/backups/minio/<bucket>`, local uniquement).
> - Cron VPS **09:00** : check de fraîcheur local + offsite
>   (`server/scripts/backup_freshness_check.sh`, seuil 26h).

## Prérequis

- **Clé de chiffrement `BACKUP_ENCRYPTION_KEY`** : les dumps sont chiffrés en GPG
  symétrique (AES256) avec cette passphrase. Elle est stockée dans le gestionnaire
  de mots de passe de William, et présente dans le `.env` du VPS (`/root/diggy/.env`).
  **Sans cette clé, les dumps chiffrés sont irrécupérables.**
- **Accès rclone (pour l'offsite)** : la config vit sur le VPS dans
  `/root/.config/rclone/rclone.conf` (remote `gdrive`, type Google Drive).
  Si le VPS est perdu, ré-authentifier depuis n'importe quelle machine via
  `rclone config` en recréant un remote `gdrive` de type `drive` avec le client
  OAuth Google dont les identifiants (client id + secret) sont dans le même
  gestionnaire de mots de passe. Fallback sans rclone : téléchargement manuel
  depuis l'interface web Google Drive (dossier `diggy-backups/postgres`).
- Les commandes ci-dessous s'exécutent depuis `/root/diggy` sur le VPS,
  sauf mention contraire.

## Scénario A — restaurer depuis le volume local

Cas d'usage : le VPS est intact (fausse manip, corruption de données, retour arrière).

### 1. Ouvrir un shell dans le container backup

```bash
cd /root/diggy
docker compose run --rm --entrypoint /bin/sh backup
```

Le container est un Alpine nu : l'entrypoint étant remplacé, les outils installés
par la commande compose ne le sont pas. Installer ce qu'il faut :

```sh
apk add --no-cache postgresql16-client gnupg
```

Les variables `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` et
`BACKUP_ENCRYPTION_KEY` sont déjà présentes dans l'environnement du container
(`env_file: .env`).

### 2. Localiser le dump

```sh
ls -lh /backups/postgres/
```

Les dumps sont nommés `diggy_YYYYmmdd_HHMMSS.sql.gz.gpg` (chiffrés) ; le lien
symbolique `latest.sql.gz.gpg` pointe vers le plus récent. Un dump `.sql.gz`
sans `.gpg` signifie qu'il a été produit SANS chiffrement (clé absente au moment
du backup) : dans ce cas, sauter l'étape `gpg` des commandes ci-dessous.

### 3. Restaurer d'abord dans une base de test

Toujours valider le dump sur une base jetable avant de toucher à la base réelle :

```sh
export PGPASSWORD="$POSTGRES_PASSWORD"
createdb -h postgres -U "$POSTGRES_USER" diggy_restore_test

gpg --batch --passphrase "$BACKUP_ENCRYPTION_KEY" -d /backups/postgres/diggy_YYYYmmdd_HHMMSS.sql.gz.gpg \
  | gunzip \
  | psql -h postgres -U "$POSTGRES_USER" -d diggy_restore_test -q -v ON_ERROR_STOP=1
```

Le dump est produit par `pg_dump --no-owner --no-acl` (SQL plain, gzippé) : il se
rejoue tel quel avec `psql`, les objets appartiennent à l'utilisateur qui restaure.
Malgré `-q`, la restauration affiche une série de lignes `set_config` / `setval`
(repositionnement des séquences) : c'est normal, ce ne sont pas des erreurs.

Contrôles de cohérence :

```sh
psql -h postgres -U "$POSTGRES_USER" -d diggy_restore_test -c "SELECT count(*) FROM catalog;"
psql -h postgres -U "$POSTGRES_USER" -d diggy_restore_test -c "SELECT count(*) FROM users;"
psql -h postgres -U "$POSTGRES_USER" -d diggy_restore_test -c "SELECT version_num FROM alembic_version;"
```

Les volumes attendus (ordres de grandeur) sont dans `docs/database-schema.md`.

### 4. Restaurer la base réelle (DESTRUCTIF)

Arrêter d'abord tout ce qui écrit en base (depuis l'hôte, PAS dans le container) :

```bash
docker compose stop api worker worker_enrich beat
```

Puis, dans le shell du container backup :

```sh
export PGPASSWORD="$POSTGRES_PASSWORD"
dropdb --force -h postgres -U "$POSTGRES_USER" "$POSTGRES_DB"   # DESTRUCTIF
createdb -h postgres -U "$POSTGRES_USER" "$POSTGRES_DB"

gpg --batch --passphrase "$BACKUP_ENCRYPTION_KEY" -d /backups/postgres/diggy_YYYYmmdd_HHMMSS.sql.gz.gpg \
  | gunzip \
  | psql -h postgres -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q -v ON_ERROR_STOP=1

# Ménage
dropdb -h postgres -U "$POSTGRES_USER" diggy_restore_test
```

Redémarrer la stack (depuis l'hôte) :

```bash
docker compose up -d
```

## Scénario B — VPS perdu

Cas d'usage : disque mort, VPS résilié, machine compromise. Les seules données
qui survivent sont les dumps offsite sur Google Drive (+ la clé et les secrets
dans le gestionnaire de mots de passe).

### 1. Récupérer le dump depuis Google Drive

Sur une machine de travail (ou le nouveau VPS) avec rclone configuré
(cf. Prérequis) :

```bash
rclone lsf gdrive:diggy-backups/postgres/
rclone copy gdrive:diggy-backups/postgres/diggy_YYYYmmdd_HHMMSS.sql.gz.gpg .
```

> Note (constaté au test du 2026-07-10) : sur le VPS lui-même, rclone n'est PAS
> installé sur l'hôte — seule sa config (`/root/.config/rclone`) y vit. Pour
> récupérer un dump offsite depuis le VPS, passer par le container backup avec
> `/tmp` monté :
>
> ```bash
> docker compose run --rm -v /tmp:/restore --entrypoint /bin/sh backup \
>   -c 'apk add --no-cache rclone >/dev/null && rclone copy gdrive:diggy-backups/postgres/diggy_YYYYmmdd_HHMMSS.sql.gz.gpg /restore/'
> ```

### 2. Remonter une stack neuve

1. Provisionner le VPS (Ubuntu 24.04, Docker + plugin compose), cloner le repo
   dans `/root/diggy`.
2. Recréer `/root/diggy/.env` depuis le gestionnaire de mots de passe
   (le `.env` n'est jamais dans git — repartir de `.env.example` pour la liste
   des variables).
3. Démarrer la base seule : `docker compose up -d postgres` et attendre qu'elle
   soit healthy (`docker compose ps`). Au premier démarrage, le container crée
   automatiquement la base `$POSTGRES_DB` (vide).

### 3. Restaurer le dump

Copier le dump sur le VPS (ex. `scp diggy_*.sql.gz.gpg root@<ip>:/root/restore/`),
puis le monter dans le container backup :

```bash
cd /root/diggy
docker compose run --rm -v /root/restore:/restore --entrypoint /bin/sh backup
```

Dans le container :

```sh
apk add --no-cache postgresql16-client gnupg
export PGPASSWORD="$POSTGRES_PASSWORD"

gpg --batch --passphrase "$BACKUP_ENCRYPTION_KEY" -d /restore/diggy_YYYYmmdd_HHMMSS.sql.gz.gpg \
  | gunzip \
  | psql -h postgres -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q -v ON_ERROR_STOP=1
```

Mêmes contrôles de cohérence qu'au scénario A (catalog, users, alembic_version).

### 4. Finaliser

- `docker compose up -d` pour démarrer le reste de la stack. Le schéma est déjà
  au bon niveau (la table `alembic_version` fait partie du dump) ; le
  `alembic upgrade head` du deploy est alors un no-op.
- Pointer le DNS `diggy-music.fr` vers la nouvelle IP ; le container certbot
  ré-émet le certificat (prod : `COMPOSE_FILE=docker-compose.yml:docker-compose.ssl.yml`
  + `DOMAIN` dans le `.env`).
- Reconfigurer l'offsite : recréer `/root/.config/rclone/rclone.conf` (cf.
  Prérequis) et remettre en place les crons backup (01:30) et fraîcheur (09:00).

## Volet MinIO (artworks)

**Décision actée (AU2)** : les artworks ne sont PAS copiés offsite. Ils sont
re-fetchables via l'enrichissement (Deezer) ; seul le mirror local
`/backups/minio/<bucket>` existe.

### VPS intact : re-mirror depuis le backup local

Dans un shell du container backup (`docker compose run --rm --entrypoint /bin/sh backup`) :

```sh
apk add --no-cache curl
curl -sSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc
chmod +x /usr/local/bin/mc

mc alias set diggy http://minio:9000 "$MINIO_USER" "$MINIO_PASSWORD" --quiet

# Sens inverse du backup : le mirror local redevient la source
mc mirror --overwrite /backups/minio/artworks diggy/artworks
mc mirror --overwrite /backups/minio/catalog-artworks diggy/catalog-artworks
mc mirror --overwrite /backups/minio/artist-artworks diggy/artist-artworks
```

### VPS perdu : artworks perdus, re-fetch progressif

Recréer les buckets vides puis laisser l'enrichissement re-télécharger les images
au fil des crawls :

```sh
mc mb --ignore-existing diggy/artworks diggy/catalog-artworks diggy/artist-artworks
```

Conséquence temporaire : `has_artwork` en base peut référencer des fichiers
absents de MinIO → vignettes manquantes dans l'UI jusqu'au re-fetch par les
tâches d'enrichissement.

## Test de restauration

Dernier test réussi : **2026-07-10** (AU2-L4) — dump chiffré récupéré depuis
Google Drive (offsite) → restauré dans la base jetable `diggy_restore_test` ;
counts `catalog` / `users` / `alembic_version` identiques à la prod.

## Snapshots Hostinger

Filet de sécurité indépendant du dispositif rclone, géré par Hostinger
(actions via le panel Hostinger uniquement) :

- **Sauvegardes automatiques hebdomadaires** incluses dans le pack VPS :
  2 générations conservées, stockage séparé (Pays-Bas), restauration complète
  du VPS en ~30 min. Dernières vues : 02/07/2026 et 09/07/2026.
- **1 snapshot manuel gratuit** : créé avant le deploy AU2. Un nouveau snapshot
  écrase le précédent — en refaire un avant toute opération risquée.
- L'upgrade payant « sauvegardes quotidiennes » est inutile : le RPO quotidien
  est déjà couvert par l'offsite rclone (dump chiffré chaque nuit à 01:30).

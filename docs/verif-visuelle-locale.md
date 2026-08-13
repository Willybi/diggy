# Vérification visuelle headless — instance LOCALE (pré-commit)

> But : vérifier au **RENDU** du code frontend **non encore déployé** (DoD d'une refonte / d'un chantier layout), **avant** commit/push.
> Le pipeline **PROD** (JWT minté sur le VPS + navigation `diggy-music.fr`) est décrit dans la mémoire `verif-visuelle-headless` — il ne vaut QUE pour du code **déjà déployé**. Ici on monte une instance locale.
> Rappel CLAUDE.md : « Full-stack local dev is NOT a supported flow ». Attends-toi donc aux obstacles ci-dessous — tous re-remédiables. Recette éprouvée le 2026-08-13 (chantier AV5).

## 0. Prérequis
- Docker Desktop lancé (`docker info` répond). Chrome installé. Node ≥ 22 (WebSocket natif, pas de dépendance).
- La stack locale sert via le service **`nginx`**, mappé par `NGINX_PORT` du `.env` (souvent `80`). Si le port 80 est pris/bloqué côté Windows : `NGINX_PORT=8090 docker compose up -d nginx` puis tester `http://localhost:8090`.

## 1. Monter la stack avec le build à vérifier
- `docker compose build frontend` (recompile le bundle statique avec tes changements) puis `docker compose up -d`.
- Chantier **front-only** : inutile de rebuild l'image `api` (lourde) ; les images existantes suffisent.

## 2. Obstacle Alembic — base `create_all` non rejouable
Symptôme : `diggy_api` en crash-loop, `NoSuchTableError: watched_playlists` (la migration 0001 suppose des tables pré-Alembic). Cf. pitfall CLAUDE.md « migration chain not replayable from empty DB ».
Fix : stamper la base (elle a déjà le schéma via create_all) —
```
docker compose run --rm --no-deps --entrypoint sh api -c "alembic stamp head"
docker compose up -d api
```

## 3. Obstacle drift de schéma — colonnes manquantes (500 sur les endpoints)
Symptôme : `500 UndefinedColumnError: column X does not exist` (le volume create_all précède des migrations qui ont ajouté des colonnes, ex. `bpm_analyzed_at`).
Fix : réconcilier **tout** le schéma en une passe idempotente, en générant les ALTER depuis les modèles —
```
docker compose exec -T api python -c "
import models
from database import Base
from sqlalchemy.dialects import postgresql
d = postgresql.dialect()
for t in Base.metadata.sorted_tables:
    for c in t.columns:
        try: ty = c.type.compile(dialect=d)
        except Exception: ty = 'text'
        print(f'ALTER TABLE {t.name} ADD COLUMN IF NOT EXISTS \"{c.name}\" {ty};')
" | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```
`ADD COLUMN IF NOT EXISTS` (sans transaction) = les colonnes existantes sont ignorées, et les erreurs sur des **tables** absentes (ajoutées par des migrations postérieures, non nécessaires aux 4 listes) ne bloquent pas le reste.

## 4. Obstacle nginx — reverse-proxy local non câblé
Symptôme : `:PORT` refuse ; `docker compose exec nginx nginx -T` ne montre aucun `server`/`listen` (le `conf.d/default.conf` est **vide** et bind-mounté). Le container `frontend` sert bien le SPA statique sur son `:80` mais **sans** proxy `/api`.
Fix : poser une conf sibling throwaway (ne PAS écraser `default.conf`, il est busy/mounté) —
```
# fichier local-proxy.conf :
server {
  listen 80; server_name localhost;
  location /api/     { proxy_pass http://api:8000; proxy_set_header Host $host; }
  location /storage/ { proxy_pass http://minio:9000/; }
  location /         { proxy_pass http://frontend:80; proxy_set_header Host $host; }
}
docker cp local-proxy.conf diggy_nginx:/etc/nginx/conf.d/zlocal.conf   # zlocal.conf, PAS default.conf
docker compose exec -T nginx nginx -t && docker compose exec -T nginx nginx -s reload
```
(Throwaway : vit dans le container, disparaît au recreate. Ne touche aucun fichier du repo.)

## 5. Seed synthétique + JWT
Le volume local est souvent **vide** (`SELECT count(*) FROM catalog` = 0) → seeder des lignes synthétiques suffisantes pour faire rendre les tables : `users` (id=2), `catalog`, `radar_trends` (pour /radar/feed), `sets` + `set_tracks` (identifiés, sinon exclus par le HAVING), `watched_entities`, `user_opinions`.
- **Avis d'un track** = `user_opinions(user_id, entity_type='track', entity_key='<catalog_id>', opinion='disliked')`. Pour tester le **dim des cellules score dislikées de Radar** : mettre la même entrée catalog dans `radar_trends` ET dislikée.
- JWT (user 2) : `docker compose exec -T api python -c "from auth import create_token; print(create_token(2))"`.

## 6. Captures CDP
- Recette Chrome CDP (headless, port debug frais, seed `localStorage` `diggy_token`/`diggy_user`/`diggy-theme`) : voir la mémoire `verif-visuelle-headless` (mêmes pièges : valeur à `msg.result.result.value` ; préfixer `MSYS_NO_PATHCONV=1` sous Git Bash ; scroll interne dans `.app-main`).
- **Attendre les vraies lignes, pas le skeleton** : sélecteur d'attente `.tt-row:not(.tt-row--skel)` (idem `.st-row`/`.pl-row`) — sinon la capture fire sur les 8 lignes fantômes avant l'arrivée des données.
- Puis **INSPECTER chaque capture** (Read de la PNG) — pas seulement compter les lignes rendues.

## 7. Ménage
- `docker compose down` (conserve les volumes). Les scripts/JWT/captures throwaway vivent dans le scratchpad et `C:\tmp\`, hors repo.

# Diggy — Plan HTTPS (Let's Encrypt)

> A deployer quand le nom de domaine sera actif et le DNS pointera vers le VPS (82.29.168.247).

---

## Approche

Fichier compose overlay (`docker-compose.ssl.yml`) qui surcharge le service nginx et ajoute un container certbot. Active sur le VPS via `COMPOSE_FILE` dans `.env`. Le dev local reste inchange en HTTP.

---

## Fichiers a creer/modifier

### 1. Creer `server/nginx/default.ssl.conf.template`

Config nginx avec deux server blocks. Le `${DOMAIN}` est substitue automatiquement par `envsubst` de l'image `nginx:alpine`.

```nginx
# HTTP — challenge ACME + redirect HTTPS
server {
    listen 80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS — TLS termination + proxy
server {
    listen 443 ssl;
    server_name ${DOMAIN};
    client_max_body_size 50M;

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    add_header Strict-Transport-Security "max-age=15768000; includeSubDomains" always;

    # Frontend Vue.js
    location / {
        proxy_pass http://frontend:5173;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # FastAPI backend
    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # MinIO console (admin)
    location /minio/ {
        proxy_pass http://minio:9001/;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # MinIO fichiers (artworks publics)
    location /storage/ {
        proxy_pass http://minio:9000/;
        proxy_set_header Host minio:9000;
    }
}
```

### 2. Creer `docker-compose.ssl.yml`

Override compose pour la prod HTTPS :

```yaml
services:
  nginx:
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./server/nginx/default.ssl.conf.template:/etc/nginx/templates/default.conf.template:ro
      - certbot_conf:/etc/letsencrypt:ro
      - certbot_www:/var/www/certbot:ro
    environment:
      DOMAIN: ${DOMAIN}

  certbot:
    image: certbot/certbot
    container_name: diggy_certbot
    volumes:
      - certbot_conf:/etc/letsencrypt
      - certbot_www:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done'"
    networks:
      - diggy_network

volumes:
  certbot_conf:
  certbot_www:
```

- Le override remplace les ports (80+443 au lieu de 8080:80) et les volumes nginx
- Le template va dans `/etc/nginx/templates/` (traite auto par l'image nginx:alpine)
- Certbot partage les volumes de certificats avec nginx
- Le loop `certbot renew` tourne toutes les 12h (ne renouvelle que si <30j avant expiration)

### 3. Modifier `.env.example`

Ajouter :

```
# HTTPS (production only)
# DOMAIN=diggy.example.com
# COMPOSE_FILE=docker-compose.yml:docker-compose.ssl.yml
```

### 4. Modifier `.github/workflows/deploy.yml` (ligne 48)

Remplacer :

```yaml
docker compose restart nginx
```

Par :

```yaml
docker compose exec -T nginx nginx -s reload 2>/dev/null || true
```

### 5. Config VPS (manuel, hors git)

Dans `/root/diggy/.env`, ajouter :

```
DOMAIN=le-domaine.com
COMPOSE_FILE=docker-compose.yml:docker-compose.ssl.yml
```

`COMPOSE_FILE` fait que `docker compose up` charge automatiquement les deux fichiers. Aucun `-f` necessaire dans le CI/CD.

Supprimer `NGINX_PORT` du `.env` VPS (plus utilise avec l'overlay SSL).

---

## Provisioning initial (une seule fois, sur le VPS)

```bash
ssh -i /c/Users/willi/.ssh/claude_diggy root@82.29.168.247
cd /root/diggy

# 1. Ajouter DOMAIN et COMPOSE_FILE dans .env (voir section 5 ci-dessus)

# 2. Demarrer le stack (nginx va echouer car pas de cert — normal)
docker compose up -d

# 3. Stopper nginx, lancer certbot en standalone
docker compose stop nginx
docker compose run --rm certbot certonly \
  --standalone \
  --email ton-email@example.com \
  --agree-tos --no-eff-email \
  -d ton-domaine.com

# 4. Relancer nginx (les certs existent maintenant)
docker compose start nginx

# 5. Verifier
curl -I https://ton-domaine.com    # 200, HSTS present
curl -I http://ton-domaine.com     # 301 redirect vers https
```

---

## Renouvellement auto

Le container certbot renouvelle automatiquement. Ajouter un cron VPS pour recharger nginx apres renouvellement :

```bash
# Sur le VPS, ajouter au crontab root :
crontab -e
# Ajouter :
0 3 * * * cd /root/diggy && docker compose exec -T nginx nginx -s reload > /dev/null 2>&1
```

---

## Verification post-deploiement

1. `curl -I http://domaine.com` → 301 redirect vers https
2. `curl -I https://domaine.com` → 200, header `Strict-Transport-Security` present
3. Dev local : `docker compose up` → fonctionne en HTTP sur localhost:8080 (inchange)
4. CI/CD : push sur master → deploy + reload nginx sans erreur

---

## Fichiers concernes (resume)

| Fichier | Action |
|---------|--------|
| `server/nginx/default.conf` | Inchange (dev local HTTP) |
| `server/nginx/default.ssl.conf.template` | **Nouveau** — config HTTPS |
| `docker-compose.yml` | Inchange (base) |
| `docker-compose.ssl.yml` | **Nouveau** — overlay SSL |
| `.github/workflows/deploy.yml` (L48) | **Modifie** — reload gracieux |
| `.env.example` | **Modifie** — ajout DOMAIN + COMPOSE_FILE |
| `.env` VPS | **Manuel** — ajout DOMAIN + COMPOSE_FILE |

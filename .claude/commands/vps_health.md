---
description: Health check du VPS Hostinger (état, métriques CPU/RAM/disque, backups) via le MCP Hostinger, avec volet conteneurs SSH optionnel
allowed-tools: ToolSearch, mcp__hostinger-api__VPS_getVirtualMachinesV1, mcp__hostinger-api__VPS_getVirtualMachineDetailsV1, mcp__hostinger-api__VPS_getMetricsV1, mcp__hostinger-api__VPS_getBackupsV1, Bash(ssh diggy-vps:*)
argument-hint: [--conteneurs pour ajouter le volet SSH docker | fenêtre ex. 24h/7j]
---

Tu fais un bilan de santé du VPS Hostinger qui héberge Diggy. Intervention en **lecture seule STRICTE** : aucun redémarrage, recréation, snapshot, ni aucune action mutative, même si un outil MCP le permet. Si une remédiation semble nécessaire, tu la **proposes** dans le rapport sans l'exécuter.

Contexte machine connu : VPS **ID 736027**, hostname `srv736027.hstgr.cloud`, plan KVM 4 (**4 vCPU / 16 Go RAM / 200 Go disque**), IPv4 `82.29.168.247` (= l'alias `diggy-vps`), Ubuntu 24.04. Le serveur MCP `hostinger-api` est déjà connecté et authentifié. Les outils MCP sont *deferred* : charge leurs schémas via ToolSearch (`select:mcp__hostinger-api__VPS_getMetricsV1,...`) avant de les appeler si besoin.

Argument $ARGUMENTS : si contient `--conteneurs` (ou `--ssh`), exécute AUSSI l'étape 5 (volet applicatif SSH). Si contient une fenêtre (`24h`, `48h`, `7j`), l'utiliser pour les métriques (défaut : **24h**).

## Étape 1 : Identifier & état machine
Appelle `VPS_getVirtualMachineDetailsV1` (id 736027 ; si l'id a changé, découvre-le d'abord via `VPS_getVirtualMachinesV1`). Vérifie :
- `state` = **running**, `actions_lock` = **unlocked** (un lock = opération en cours ou incident)
- relève `firewall_group_id` (si `null` → aucun firewall réseau Hostinger attaché : à signaler, non bloquant)

## Étape 2 : Métriques ressources (fenêtre demandée, défaut 24h)
Appelle `VPS_getMetricsV1` avec `date_from`/`date_to` couvrant la fenêtre (dates ISO 8601 UTC, calculées depuis la date du jour du contexte). Les séries sont des maps `timestamp_unix → valeur`. Analyse **baseline + pic** de chacune :

| Métrique | Unité | Seuils d'alerte (VPS 4 vCPU / 16 Go / 200 Go) |
|---|---|---|
| `cpu_usage` | % (des 4 vCPU) | **baseline > 50 % soutenu** = à surveiller ; **> 75-80 % soutenu sur plusieurs heures/jours** = risque de throttle fair-use Hostinger (cf. pitfall AV10) |
| `ram_usage` | bytes | > 12 Go (~75 %) = tension ; pente monotone continue = fuite possible |
| `disk_space` | bytes | > 170 Go (~85 % de 200 Go) = critique ; noter la vitesse de croissance |
| `outgoing`/`incoming_traffic` | bytes | contextuel : les pics entrants (~centaines de Mo/intervalle) = drains enrich Deezer/Beatport, **normaux** |
| `uptime` | secondes | un reset inattendu (uptime qui retombe) = reboot non planifié à investiguer |

Distingue toujours **pic ponctuel** (ex. drain horaire) de **plateau soutenu** (le vrai signal de throttle). Un CPU à ~80 % pendant 6-7 j sans hausse de débit = profil de dette post-rollout (ré-enrich + autovacuum), pas un pic de trafic.

## Étape 3 : Sauvegardes
Appelle `VPS_getBackupsV1`. Vérifie qu'il existe un backup **récent** (< quelques jours) et note la date du plus récent + le nombre de points. Rappel : c'est la sauvegarde niveau-VPS Hostinger, **distincte** des dumps PG chiffrés offsite (rclone) — les deux couvrent des choses différentes, ne pas conclure « pas de backup » si l'un des deux manque.

## Étape 4 : Vue conteneurs — limite de l'API
`VPS_getProjectListV1` renvoie `VPS:2044 — OS does not support Docker Manager` : **attendu**, Diggy tourne via `docker compose` en SSH, pas via l'outil managé Hostinger. Donc l'API ne voit PAS la santé des conteneurs. Mentionne-le, et fais l'étape 5 si demandé.

## Étape 5 (si `--conteneurs`/`--ssh`) : Volet applicatif SSH
En lecture seule via `ssh diggy-vps "…"`, projet dans `/root/diggy` :
- `ssh diggy-vps "cd /root/diggy && docker compose ps"` : tous les conteneurs `Up`/`healthy`, aucun restart loop (10 attendus : api, worker, worker_enrich, beat, frontend, nginx, postgres, redis, minio, certbot ; + backup)
- `ssh diggy-vps "docker stats --no-stream"` : conso par conteneur, repère un worker qui gonfle vers son cap mémoire (2G pour api/worker/worker_enrich)
- `ssh diggy-vps "df -h"` : aucune partition > 85 %
- Optionnel selon symptôme : `ssh diggy-vps "docker compose logs --since 30m <service>"` pour un service suspect

## Étape 6 : Rapport
Produis un **tableau synthétique** : Indicateur | Valeur | Verdict (🟢/🟠/🔴), suivi d'un **verdict global** : SAIN / ANOMALIES DÉTECTÉES / CRITIQUE.

- Pour chaque 🟠/🔴 : cause probable + gravité + **action recommandée non exécutée** (ex. « CPU ~80 % soutenu 5 j → probable dette post-rollout, envisager d'étaler un re-drain ; diagnostiquer via `ssh docker stats` / `sar` »).
- Termine par ce qui échappe à ce check (zones aveugles : santé fine des conteneurs si `--conteneurs` non demandé, cohérence applicative, backups PG offsite) et propose la suite pertinente (`/deploy_verify` si post-déploiement, volet `--conteneurs`, etc.).

Reste factuel : un 200/`running` avec une métrique dégradée n'est pas « SAIN ». Ne masque pas un signal faible sous un verdict vert.

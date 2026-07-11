---
description: Vérifie le déploiement en prod sur le VPS après push et CI/CD
allowed-tools: Read, Glob, Grep, Bash(ssh diggy-vps:*), Bash(curl:*), Bash(git log:*), Bash(git diff:*)
argument-hint: [chantier déployé ou commit concerné]
---

Le chantier suivant vient d'être déployé en production sur le VPS (push effectué, CI/CD passée) : $ARGUMENTS

Ton rôle : vérifier que le déploiement est sain, exécuter les checks automatisables, puis me remettre une checklist des vérifications qui nécessitent un humain. Tu interviens en lecture seule : aucun redémarrage, aucune modification sur le serveur sans mon accord explicite.

Accès : SSH via l'alias configuré, sous la forme ssh diggy-vps "commande". Projet sur le VPS : /root/diggy. Site de prod : https://diggy-music.fr

## Étape 1 : Identifier ce qui a été déployé
Relis le contexte de la session (compte rendu du work manager, message de commit) ou, à défaut, !`git log --oneline -5`. Liste les features/changements déployés : c'est ce qui pilote les checks des étapes suivantes.

## Étape 2 : Santé de l'infrastructure
- État des containers : ssh diggy-vps "cd /root/diggy && docker compose ps" ; vérifie que tous sont Up, sans restart loop (colonne status, uptime cohérent avec l'heure du déploiement)
- Logs récents de chaque service impacté par le chantier : ssh diggy-vps "cd /root/diggy && docker compose logs --since 15m <service>" parmi : api, worker, worker_enrich, beat, frontend, nginx, postgres, redis, minio, certbot ; cherche erreurs, stack traces, warnings inhabituels
- Ressources : ssh diggy-vps "docker stats --no-stream" ; signale toute consommation anormale (mémoire qui gonfle, CPU bloqué)
- Espace disque : ssh diggy-vps "df -h" ; signale si une partition dépasse 85%

## Étape 3 : Smoke tests HTTP
Toujours exécuter :
- curl -s https://diggy-music.fr/api/health (attendu : réponse OK)
- curl -sI http://diggy-music.fr (attendu : 301 vers HTTPS)
- curl -sI https://diggy-music.fr (attendu : 200, page servie)
- curl -s "https://diggy-music.fr/api/catalog?limit=1"
- curl -s "https://diggy-music.fr/api/artists?limit=1"
- curl -s "https://diggy-music.fr/api/genres"

Pour chaque réponse : vérifie le code HTTP ET la structure du JSON (pas seulement un 200 ; un 200 avec un body d'erreur ou vide est un échec).

## Étape 4 : Checks ciblés sur les features déployées
En fonction de ce qui a été identifié à l'étape 1 :
- si le chantier a ajouté/modifié des endpoints : teste-les via curl (endpoints publics uniquement ; liste-moi ceux derrière auth pour la checklist humaine)
- si le chantier touche à la base de données : vérifie dans les logs du service concerné que les migrations sont passées sans erreur
- si le chantier touche au front : vérifie que les assets sont servis (curl -sI sur le bundle principal, code 200 et content-type correct)
- propose et exécute tout autre check en lecture seule pertinent pour CE chantier ; si un check utile nécessite une action intrusive, demande-moi avant

## Étape 5 : Rapport
Produis :

### Bilan automatisé
Tableau : Check | Résultat | Détail. Verdict global : SAIN / ANOMALIES DÉTECTÉES / CRITIQUE.
En cas d'anomalie : cause probable, gravité, et action recommandée (sans l'exécuter).

### Checklist humaine
Liste à cocher des vérifications que je dois faire moi-même, ADAPTÉE aux features déployées, par exemple :
- [ ] parcours fonctionnel de la feature X sur le site (étapes précises à suivre)
- [ ] rendu visuel des pages modifiées (desktop + mobile)
- [ ] fonctionnalités derrière authentification que tu n'as pas pu tester (lesquelles, quoi vérifier)
- [ ] comportements difficilement automatisables : upload, lecture audio, emails, paiements si concernés

Pour chaque item : ce qu'il faut faire et ce qui est attendu, formulé pour être vérifiable en une phrase.

Si le verdict est SAIN et la checklist humaine validée de mon côté, la suite du workflow est /roadmap_update.
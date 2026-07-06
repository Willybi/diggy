# C0 — Correctifs critiques & fondations data

Tu dois implementer le chantier C0 de la roadmap Diggy. Il comporte 2 volets : securite API (C0.2) et cycle de vie des detections radar (C0.1).

Lis `CLAUDE.md` a la racine pour les conventions du projet.

---

## C0.2 — Correctifs securite (3 fixes)

### Fix 1 : `GET /api/radar/` legacy non authentifie

**Fichier** : `server/api/routers/radar.py` (lignes 79-91)

L'endpoint legacy `GET /api/radar/` n'a pas de `Depends(get_current_user)` — il est ouvert a tous sans auth. Deux options :
- **Option A (preferee)** : supprimer purement cet endpoint. Il est marque "Legacy endpoints (kept for crawl_radar task compat)" mais le worker `crawl_single_playlist` (`server/workers/tasks/radar.py`) fait du direct DB access, il n'appelle plus cet endpoint.
- **Option B** : ajouter `user: User = Depends(get_current_user)` si un autre consommateur en a besoin.

Verifie d'abord qu'aucun code n'appelle `GET /api/radar/` (grep dans tout le projet). Si personne ne l'appelle, supprime-le. Supprime aussi le `POST /api/radar/` legacy (lignes 94-107) s'il est egalement inutilise — meme raisonnement.

### Fix 2 : `DELETE /api/radar/{entry_id}` sans check ownership

**Fichier** : `server/api/routers/radar.py` (lignes 110-122)

Actuellement, n'importe quel user authentifie peut supprimer n'importe quel RadarTrack par son ID. Le fix :
- Apres avoir recupere l'`entry`, verifier que l'utilisateur a le droit de supprimer. Comme `RadarTrack` n'a pas de `user_id`, la suppression est une action admin. Ajouter `require_admin` comme dependance, OU supprimer cet endpoint s'il est inutilise (meme demarche : grep d'abord).

### Fix 3 : `uid()` fallback `user_id=1`

**Fichier** : `server/api/dependencies.py` (lignes 67-74)

```python
_DEFAULT_USER_ID = 1

def uid(user: User | None) -> int:
    return user.id if user else _DEFAULT_USER_ID
```

Ce fallback silencieux fait que tout visiteur non-auth voit les donnees du user 1. Le fix :
- Supprimer `_DEFAULT_USER_ID`
- Quand `user is None`, retourner `None` (pas un ID fallback)
- Type de retour : `int | None`

**Attention — impact cascade** : `uid()` est utilise dans 6 routers via `_uid(user)` :
- `catalog.py` (lignes 68, 83)
- `search.py` (ligne 352)
- `artists.py` (ligne 26)
- `genres.py` (lignes 60, 87, 102, 149)
- `watchlist.py` (lignes 87, 123, 153, 202, 260, 411)

Tous ces routers utilisent `get_current_user_optional` et passent `_uid(user)` aux services. Quand `user` est `None`, le service recevra maintenant `None` au lieu de `1`.

Il faut verifier dans chaque service appele (`catalog_service`, `radar_service`, `genre_service`, `artist_service`) comment `user_id` est utilise. Typiquement il sert a determiner `in_lib` (est-ce que la track est dans la bibliotheque de l'user). Si `user_id is None`, le service doit simplement ne pas joindre `user_tracks` et retourner `in_lib=False` pour toutes les tracks. Verifie que c'est bien le cas, et corrige si necessaire.

---

## C0.1 — Cycle de vie des detections radar

### Tache 1 : Ajouter `removed_at` sur `RadarTrack`

**Fichier modele** : `server/api/models.py` (classe `RadarTrack`, ligne 263)

Ajouter une colonne :
```python
removed_at = Column(DateTime(timezone=True), nullable=True)
```

**Migration Alembic** : creer `0026_radar_removed_at.py` dans `server/api/alembic/versions/`. Suit la convention de nommage existante (prefixe numerique 4 chiffres). La migration doit :
- Ajouter la colonne `removed_at` (nullable, pas de defaut)
- C'est tout — pas d'index necessaire pour le moment

### Tache 2 : Logique de diff dans le crawl

**Fichier** : `server/workers/db.py` — fonction `bulk_insert_radar_tracks` (ligne 145)

Apres l'insertion des nouvelles tracks, ajouter une logique de diff :
1. Recuperer les `external_track_id` des tracks crawlees (`source_tracks`)
2. Les tracks en base pour cette playlist qui ne sont PAS dans les tracks crawlees ET qui ont `removed_at IS NULL` → marquer `removed_at = now`
3. Les tracks en base pour cette playlist qui SONT dans les tracks crawlees ET qui ont `removed_at IS NOT NULL` → remettre `removed_at = NULL` (re-apparition)
4. Retourner aussi le nombre de tracks marquees comme retirees

Attention : ne touche pas aux tracks deja marquees `removed_at` d'un crawl precedent (ne pas re-dater).

### Tache 3 : Flagger le premier crawl d'une playlist

**But** : quand une playlist entre pour la premiere fois dans le radar, tout son contenu prend `detected_at = maintenant`, ce qui cree un faux pic de velocite. Il faut pouvoir distinguer ce premier crawl.

**Approche suggeree** :
- Ajouter un booleen `is_initial_crawl` sur `WatchedEntity` (ou utiliser `last_crawled_at IS NULL` comme proxy — c'est deja disponible). Verifie si `last_crawled_at` est fiable pour ca.
- Dans `bulk_insert_radar_tracks`, accepter un parametre `is_initial_crawl: bool`. Quand c'est le premier crawl, les `RadarTrack` inserees recoivent un flag (soit une colonne `is_initial_detection = True`, soit on utilise le fait que `detected_at == last_crawled_at` de la playlist comme heuristique).
- **Option la plus simple** : ajouter `is_initial_detection = Column(Boolean, default=False)` sur `RadarTrack`. Le compute_trends pourra filtrer ces detections. Inclure dans la migration 0026.

---

## Tests a ecrire

Fichier existant : `tests/api/test_radar.py` (21 tests existants).

### Tests securite (C0.2)
- `test_legacy_get_radar_removed` : verifier que `GET /api/radar/` retourne 404 (ou 405 si le endpoint est supprime)
- `test_delete_radar_requires_admin` : verifier que `DELETE /api/radar/{id}` par un user non-admin retourne 403 (si on garde l'endpoint avec `require_admin`)
- `test_uid_none_when_no_user` : verifier que `uid(None)` retourne `None`
- `test_catalog_browse_no_auth_no_user_data` : verifier qu'un browse catalog sans auth ne leak pas de donnees `in_lib`

### Tests cycle de vie (C0.1)
- `test_radar_track_removed_at_column` : verifier que le modele a la colonne
- `test_crawl_marks_removed_tracks` : simuler un crawl ou une track disparait → `removed_at` doit etre set
- `test_crawl_reappearing_track_clears_removed_at` : simuler un crawl ou une track reapparait → `removed_at` doit etre None
- `test_initial_crawl_flag` : verifier que le premier crawl d'une playlist flag les detections

---

## Definition of Done

```bash
# Securite
# GET /api/radar/ → 404 ou 405 (endpoint supprime)
# DELETE /api/radar/{id} par non-admin → 403 (ou endpoint supprime)
# uid(None) retourne None (plus de fallback user_id=1)

# Cycle de vie
# RadarTrack a un champ removed_at (migration 0026)
# crawl_single_playlist marque les tracks absentes avec removed_at
# Les re-apparitions remettent removed_at a NULL
# Premier crawl d'une playlist est detectable (is_initial_detection ou equivalent)

# Qualite
# Tous les tests existants passent toujours
# Les nouveaux tests passent
# Linting OK : ruff check server/ && cd server/frontend && npm run lint
```

## Ordre d'execution recommande

1. C0.2 Fix 3 (`uid()`) — c'est le plus impactant, a faire en premier pour stabiliser
2. C0.2 Fix 1 et 2 (endpoints legacy) — rapide, grep + suppression/protection
3. C0.1 Tache 1 (migration + modele)
4. C0.1 Tache 2 (logique de diff dans le crawl)
5. C0.1 Tache 3 (flag premier crawl)
6. Tests
7. Lint final

## Commits

Un commit par fix logique, convention `type(scope): description` :

```
fix(api): remove uid() fallback to user_id=1
fix(api): remove legacy unauthenticated radar endpoints
feat(api): add removed_at column to radar_tracks (migration 0026)
feat(workers): mark removed radar tracks during crawl diff
feat(workers): flag initial crawl detections
test(api): add C0 security and lifecycle tests
```

Ne pousse PAS sur master — je review avant.

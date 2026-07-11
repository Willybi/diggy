# Scripts de maintenance backend

Scripts opérationnels et migrations de données ponctuelles, exécutés à la main
depuis le conteneur API sur le VPS :

```bash
docker compose exec api python scripts/<nom>.py [--options]
```

La plupart acceptent `--dry-run` et/ou `--limit` (voir la docstring en tête de fichier).
Ce répertoire est du **tooling hors runtime** : rien ici n'est déclenché automatiquement
(les traitements récurrents vivent dans `server/workers/tasks/`, cf. Celery Beat).

## Statuts

- **rejouable** : idempotent ou outil opérationnel réutilisable — sûr à relancer.
- **one-shot — exécuté** : migration de données ponctuelle, déjà passée en prod,
  conservée pour trace. Généralement sans effet en cas de re-run (clause `WHERE`
  qui ne cible que les lignes non traitées), mais ce n'est pas une raison de la relancer.

## Inventaire

| Script | Rôle | Statut |
|--------|------|--------|
| `audit_set_dedup.py` | Audit de déduplication des sets (rapport en dry-run ; `--apply` pour exécuter AUTO_ATTACH + FLAG) | rejouable |
| `backfill_aliases.py` | Crée les `artist_aliases` depuis les chaînes `catalog.artist` (skip les alias existants) | rejouable |
| `discover_trackid_sets.py` | Découvre sur TrackID.net les sets contenant une track donnée (par artiste/titre ou `--catalog-id`) | rejouable |
| `enrich_catalog_deezer.py` | Enrichit le catalog via Deezer (deezer_id, isrc, durée, preview, cover) ; cible les entrées sans deezer_id (`--force` pour tout). Doublon manuel de la tâche nightly `enrich_catalog` | rejouable |
| `fetch_catalog_artworks.py` | Télécharge les covers Deezer pour les entrées catalog sans artwork (`--force` pour re-télécharger) | rejouable |
| `import_trackid_sets.py` | Importe des sets TrackID.net par channel ou mot-clé (`--resolve` pour résoudre les tracklists) | rejouable |
| `populate_artists.py` | Peuple la table `artists` depuis `catalog.artist` (split feat/&/virgule + flags d'ambiguïté) ; explicitement idempotent | rejouable |
| `populate_has_preview.py` | Renseigne `has_preview` en interrogeant l'API Deezer track | rejouable |
| `backfill_deezer_id.py` | Renseigne `deezer_id` sur les entrées `has_preview` sans radar_track lié | one-shot — exécuté (2026-07-01) |
| `backfill_set_artworks.py` | Récupère les artworks des sets existants depuis TrackID `artworkUrl` | one-shot — exécuté (2026-07-01) |
| `backfill_set_slugs.py` | Backfill `external_slug` des sets TrackID existants | one-shot — exécuté (2026-07-01) |
| `fix_artist_names.py` | Corrige les noms d'artistes stockés comme slugs (`adambeyer` → `Adam Beyer`) | one-shot — exécuté (2026-07-01) |
| `backfill_set_parts.py` | C6.1 : renseigne `part_number` / `part_total` (à lancer après la migration 0030) | one-shot — exécuté (2026-07-07) |
| `promote_private_shared.py` | Rattrapage A3-01 : promeut en `shared` les tracks `private` déjà confirmées par Deezer | one-shot — exécuté (2026-07-09) |

> Dates = dernier commit `git log --follow` du fichier (repère d'exécution, pas garantie formelle).

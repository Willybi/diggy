# Revue interne du chantier Explorer (avant commit) — 2026-07-21

> Revue adversariale multi-agents (6 dimensions × vérification indépendante) passée sur l'ensemble du diff
> AVANT le commit qui auto-déploie en prod. Distincte de la revue design post-implémentation Claude Design
> (Phase 5 du pipeline → `FIX-explorer.md`). Résultat : **0 blocker, 0 major, 8 minor, 2 nit, 1 réfuté.**

## Confirmés & traités dans le lot correctif (commit initial)

| # | Sév. | Fichier | Défaut | Résolution |
|---|------|---------|--------|-----------|
| 1 | minor | `services/catalog_service.py` | tri `bpm`/`duration_ms` enveloppés en `coalesce(col,0)` → annule le `.nulls_last()` : les tracks sans valeur remontent EN TÊTE en `order=asc` (incohérent avec title/artist/key/release_date) | retrait du `coalesce(...,0)` pour ces 2 tris, `.nulls_last()` seul (comme les autres) |
| 3 | minor | `router.js` | redirect `/catalog` préserve la query brute → un vieux bookmark `?inlib=true` (ancien nom du filtre bib) est ignoré par Explorer (qui possède `lib`) → catalog complet au lieu de la bib | mapping legacy dans le redirect : `inlib=true`→`lib=in`, `view` retiré |
| 4 | minor | `components/filters/ArtistTypeAhead.vue` | `search()` sans garde in-flight → une réponse périmée réécrit des résultats plus récents / rouvre le dropdown sur un champ vidé | token monotone (même pattern que `useWindowedList`) |
| 7 | minor | `composables/useWindowedList.js` | sur erreur de fetch en reset → `total=0` → la page affiche l'empty state « Aucun résultat avec ces filtres » sur une panne réseau (trompeur) | distinguer erreur ≠ vide (ne pas écraser `total` à 0 sur erreur / exposer un état d'erreur) |
| 8 | minor | `components/filters/ArtistTypeAhead.vue` | aucune fermeture au clic-dehors/blur → le dropdown `position:absolute` flotte sur les champs suivants jusqu'à Échap/select | fermeture au blur (léger délai pour laisser passer le click de sélection) |
| 5 | minor | tests back | `sort=artist` et `sort=duration_ms` n'ont NI test d'acceptation NI test d'ordre → une régression de mapping resterait verte | ajout de la couverture dans `tests/api/test_catalog.py` |
| 6 | minor | `__tests__/views/ExplorerView.test.js` | `routeMock` non réactif + `routerReplace` mock nu → le watch `route.query`→dédup→refetch ne se déclenche jamais : les 8 tests n'exercent que le fetch `onMounted`, jamais un changement de filtre/tri post-mount | rendre le mock router réactif + 1 test de changement de filtre post-mount (refetch avec nouveaux params) |
| 9 | nit | `components/filters/SearchInput.vue` (usage Explorer) | double debounce : `SearchInput` (250 ms) + `useFilterState` (250 ms) empilés ≈ 500 ms de latence saisie→requête sur `q` et `label` | `:debounce="0"` sur les SearchInput d'Explorer (useFilterState debounce déjà) |
| 10 | nit | `schemas/catalog.py` | `SameArtistTrackOut.rating` (BaseModel autonome, pas héritier de `CatalogEntryOut`) reste déclaré → champ mort, toujours `null` (le constructeur ne le peuple plus) | retrait du champ (cohérent avec la purge Rating) |

## Reliquat (hors périmètre — inscrit ROADMAP)

| # | Sév. | Défaut | Pourquoi différé |
|---|------|--------|------------------|
| 2 | minor | `rb_key` est stocké verbatim depuis l'attribut Tonality du XML Rekordbox SANS conversion Camelot (`rekordbox_xml.py`). `key_col = coalesce(rb_key, catalog.key)` : un utilisateur dont Rekordbox exporte les clés en notation classique (`Am`, `Fm`…) voit ses tracks in-lib DISPARAÎTRE du filtre Key (`.in_(['1A'])` ne matche jamais `Am`) et mal triées | fix propre = normaliser `rb_key`→Camelot à l'import (touche le pipeline d'import, hors chantier UI) ou décision produit (coalesce `catalog.key` d'abord pour le filtre key, mais `rb_key` est autoritaire). Conditionné au réglage d'affichage des clés de l'utilisateur |

## Réfuté (vérification adversariale)

- **[nit] test combiné filtres + `catalog_visible`** : la revue notait l'absence d'un test seedant une ligne passant 8 filtres sur 9 et échouant au 9e. Réfuté : chaque filtre a déjà son test négatif dédié dans `TestExplorerFilters`, le query-builder compose les filtres en `where()` indépendants gardés un par un (le AND est une garantie du framework SQLAlchemy), les seuls `or_` sont intra-filtre (search+label, genre-multi) et testés. Aucun scénario réaliste que le test proposé attraperait au-delà de l'existant.

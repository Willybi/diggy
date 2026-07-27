# FIX — Artistes (liste) `/artists` (D6 p.6)

Triage des retours post-déploiement (William, 2026-07-28), après le déploiement `b0f56a6` + `/deploy_verify` SAIN.

## Validés par William (aucune action)
Follow depuis la card · état suivi mauve · filtres In Lib / Suivis · toggle Sans Deezer (fonctionnel) · In Lib vert · tags genre cliquables · play · mobile.

## Écarts traités

| # | Retour | Tag | Verdict | Résolution |
|---|---|---|---|---|
| F1 | « 2 Floating Points dans la liste » | [comportement] | **ACCEPTÉ — bug confirmé** | Pas un doublon de données (1 seule ligne id 1859 en base). **Bug de pagination** : diagnostic prod = 9 artistes en double sur 168 récupérés (Floating Points aux offsets 96 **et** 120), car les tris de `list_artists` n'avaient **pas de départage stable** → ordre non total → LIMIT/OFFSET réémet/saute des lignes sur ex-æquo. **Pré-existant** (le tri d'origine était déjà sans tie-breaker), corrigé ici. Fix : `Artist.id` en dernier critère de chaque branche `order_by` (catalog/lib/liked/disliked/alpha) → ordre total, pagination déterministe. |
| F2 | « Sans Deezer visible partout, le rendre admin-only » | [spec] | **ACCEPTÉ** | `v-if="auth.user?.is_admin"` sur le bouton toggle (pattern bande admin de `GenresView`). FamilyChips inchangés, layout `.tools-row` OK sans le toggle. |
| F3 | « Tab embêtant : traverse tous les contrôles d'une card avant la suivante » | [comportement] | **LAISSÉ TEL QUEL — décision William** | Tension a11y : rendre la card focusable en un seul arrêt masquerait la pastille follow au clavier (feature qu'on venait de rendre accessible). Options présentées (card = 1 arrêt / nom = lien + card non focusable / statu quo) → William choisit **statu quo** (comportement a11y-correct : tout reste atteignable au clavier, juste verbeux). Aucun changement. |

## Livraison
Commit FIX (séparé du chantier `b0f56a6`) :
- Back : `services/artist_service.py` (tie-breaker `Artist.id` × 5 branches) + test `test_pagination_stable_on_tied_catalog_count`.
- Front : `views/ArtistsView.vue` (toggle admin-only) + tests visibilité toggle (ArtistsView.test.js).
- Suite verte : back 1501, front 456. Lint back + front verts.

## Suivi identifié (non planifié)
Les listes sœurs paginées (`/api/sets/`, `/api/watchlist/browse`) devraient être auditées pour le **même** défaut (offset pagination sans tie-breaker total sur des tris à ex-æquo) — reliquat opportuniste, pas ouvert ici.

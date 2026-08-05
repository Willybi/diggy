# Prompt agent — Lot correctif revue design Genre Detail

```
CONTEXTE
Projet Diggy (frontend Vue 3 + Vite, tokens CSS, container queries). La page « Détail genre » (/style/:genre) vient de passer sa revue design. Trois écarts ACCEPTÉS sont à corriger, tous dans UN SEUL fichier de vue, en CSS + template. Aucun composant partagé ne doit être modifié (contrainte dure), aucune logique métier, aucune migration, aucun back.

FICHIER À MODIFIER (le seul)
- server/frontend/src/views/GenreDetailView.vue

FICHIERS À LIRE D'ABORD (contexte, NE PAS modifier)
- server/frontend/src/views/GenreDetailView.vue (toute la vue)
- server/frontend/src/components/ShelfCard.vue (pour comprendre .sc-sub / .sc-title — NE PAS modifier)
- server/frontend/src/components/RelBlock.vue (NE PAS modifier)

CORRECTIONS ATTENDUES (exactement ces 3, rien d'autre)

1. ÉCART BLOQUANT — la 2ᵉ colonne de la shelf Playlists déborde et est coupée en mobile.
   Cause : `.cards-grid` utilise `grid-template-columns: repeat(N, 1fr)`. Or `1fr` = `minmax(auto, 1fr)`, dont le plancher est le min-content ; le sous-titre des cards (`.sc-sub` de ShelfCard) est en `white-space: nowrap`, donc un `owner` long (« Georges - Deezer Electronic Editor ») force la colonne plus large que la piste, et le débord est masqué par `.rel-body { overflow: hidden }` du panneau.
   Correctif (dans le <style scoped> de la vue) :
   a. Remplacer les 3 déclarations de `grid-template-columns` de `.cards-grid` par la variante bornée `minmax(0, 1fr)` :
      - base : `repeat(4, 1fr)` → `repeat(4, minmax(0, 1fr))`
      - `@container (max-width: 720px)` : `repeat(3, 1fr)` → `repeat(3, minmax(0, 1fr))`
      - `@container (max-width: 640px)` : `repeat(2, 1fr)` → `repeat(2, minmax(0, 1fr))`
   b. Sur l'override scopé `.cards-grid :deep(.sc-sub)` (qui fixe déjà font + text-align:left), AJOUTER : `overflow: hidden;` et `text-overflow: ellipsis;` (le `white-space: nowrap` est hérité de ShelfCard — le sous-titre trop long doit désormais s'ellipser dans la cellule, pas déborder).
   NE PAS modifier ShelfCard ni RelBlock. Le comportement des Sets (sous-titre = date courte) ne doit pas régresser.

2. ÉCART MINEUR — les liens « Voir les N autres » des shelves Sets et Playlists affichent le nombre brut (« Voir les 4968 autres »), sans espace fine des milliers, alors que le lien Explorer de la tracklist (juste en dessous) utilise déjà `fmtNum(...)`.
   Correctif (dans le <template>) : envelopper le calcul du nombre dans les DEUX boutons `.load-more` (Sets et Playlists) avec le helper `fmtNum` déjà importé — ex. `Voir les ${setsTotal - sets.length} autres` → `Voir les ${fmtNum(setsTotal - sets.length)} autres`, idem pour les playlists (`playlistsTotal - playlists.length`). Ne pas toucher au reste de l'expression (label « Chargement… », etc.).

3. ÉCART MINEUR — la statline affiche « SETS n » avec un compteur (`genre.setCount`) qui diverge du total de la section Sets affiché dans l'en-tête de la shelf (mesuré en prod : 5218 vs 5140 ; sur un petit genre 3 vs 1). La stat de la statline est un compteur de navigation vers la section → elle doit afficher le MÊME total que la section.
   Correctif (dans le <template>, bloc `.statline` / `.sline-stats`) : remplacer la source des valeurs Sets et Playlists de la statline par les totaux de section déjà présents dans le composant :
   - Sets : `fmtNum(genre.setCount || 0)` → `fmtNum(setsTotal)`
   - Playlists : `fmtNum(genre.playlistCount || 0)` → `fmtNum(playlistsTotal)`
   (`setsTotal` et `playlistsTotal` sont des refs déjà définies et alimentées par `fetchSets`/`fetchPlaylists`, appelées dans le `Promise.all` de `fetchGenre` avant que `loading` ne repasse à false — donc peuplées au rendu.) La stat « En bib » ne change pas.

HORS PÉRIMÈTRE (ne pas faire)
- Ne PAS modifier ShelfCard.vue, RelBlock.vue, ni aucun autre composant partagé.
- Ne PAS toucher au back, aux endpoints, aux composables.
- Ne PAS traiter les écarts REJETÉS ni les reliquats : compteur d'en-tête de shelf (RelBlock), anneau d'avatar dark, tuiles placeholder hero, troncature StyleTag, pluralisation « 1 tracks ». Hors de ce lot.

CONVENTIONS
Avant d'écrire, observe le style de la vue (tokens `var(--...)`, container queries `@container (max-width: …)` sans nom de conteneur, `:deep()` pour les overrides de composants partagés, zéro couleur hardcodée) et conforme-toi. Code/CSS en anglais, textes UI en français.

TESTS (obligatoire)
- AVANT modif : place-toi dans server/frontend (appel dédié) puis `npx vitest run`. Note l'état de référence.
- APRÈS modif : `npx vitest run`. Aucune régression attendue (changements CSS + bindings d'affichage). Si un test de GenreDetailView asserte l'ancienne source de la statline (`setCount`/`playlistCount`) et casse légitimement, mets-le à jour vers `setsTotal`/`playlistsTotal` en le documentant ; si un test casse sans rapport, signale-le sans le rafistoler.
- Ne refactore pas l'infra de test.

LINT (obligatoire)
- Dans server/frontend (appel dédié) : `npm run lint`.

GIT : INTERDICTION STRICTE de committer ou toute manipulation git hors lecture (git diff/status). Aucun add/commit.

COMPTE RENDU FINAL (format exact)
## Compte rendu - Lot correctif Genre Detail
- Statut : TERMINÉ / TERMINÉ AVEC RÉSERVES / BLOQUÉ
- Fichiers modifiés :
- Ce qui a été fait (par écart 1/2/3) :
- Résultat des tests : (avant / après)
- Tests modifiés et pourquoi :
- Résultat du lint :
- Difficultés ou écarts par rapport à la consigne :
```

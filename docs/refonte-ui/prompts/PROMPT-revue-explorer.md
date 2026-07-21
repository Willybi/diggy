# Prompt — Claude Design · Revue post-implémentation Explorer (D6 p.1)

> À envoyer au projet Claude Design. Round de revue UNIQUE et timeboxé.
> William joint : ce prompt + les 6 captures listées ci-dessous (dossier `C:\tmp\captures-explorer\`).
> Livrable attendu : **un seul fichier `FIX-explorer.md`** listant les écarts, chacun tagué **[visuel]** ou **[spec]**, avec valeur constatée vs attendue.

## Contexte

Tu avais produit le handoff design de la page **Explorer** (ex-Catalog) de Diggy : `BRIEF-explorer.md` (décisions DA E1-E13) + `BRIEF-filtres-partages.md` (famille de composants filtres) + la maquette pilote. L'implémentation est **déployée en prod** (`https://diggy-music.fr/explorer`). Tu fais maintenant la revue de conformité de l'implémentation à **TES propres briefs**.

**Périmètre de la revue** : fidélité **visuelle / DA / UX** au handoff uniquement (tokens, espacements, états, responsive, anatomie). 
**HORS périmètre, interdit de commenter** : l'architecture JS/Vue, le découpage des composants, les choix techniques (composables, virtualisation, sync URL), la qualité du code. Tu ne juges QUE le rendu et sa conformité à tes briefs.

## Arbitrages d'implémentation DÉJÀ ACTÉS (ne PAS les remonter comme écarts)

Ces points s'écartent volontairement de la maquette ou tranchent une latitude que le brief te laissait — ils sont validés, ne les reporte pas :

1. **Params d'URL des ranges compacts** : `?bpm=124-130`, `?year=1985-2005` (1 param par critère), pas `bpm_min/bpm_max`. Choix produit.
2. **Durée = presets** (`< 3 / 3-5 / 5-8 / > 8 min`), pas de slider (E5, latitude donnée).
3. **Recherche texte dans la barre de filtres** (1er contrôle), plus dans le head (E6).
4. **Panneau de filtres inline** qui pousse la table (E1), pas un overlay.
5. **Grille Camelot 12×2** desktop / **6×4** en drawer mobile (E4).
6. **Colonne Style = 1 `StyleTag` + « +N »** si plusieurs genres (E12, hauteur de rangée constante pour la virtualisation).
7. **Column-drop mobile** : à < 640 px les colonnes sont **Play · Track · BPM · Avis** (Key tombe AVANT BPM — décision produit : les DJs privilégient le BPM sur mobile). Le tri (select) est **masqué < 640 px** en v1 (reliquat assumé, le tri rejoindra le drawer plus tard).
8. **Cap à 150 styles** dans le multi-select (endpoint trié par count desc) + scroll interne.
9. **Tri alphabétique** : insensible à la casse, espaces de tête trimés, artiste vide en dernier. Les vrais noms commençant par de la **ponctuation** (`!!!`, `"976..."`) trient en premier — limite cross-DB assumée (comme Spotify/Apple Music), pas un écart.
10. **Bornes statiques** des sliders : BPM 60-200, Année 1985-2026.
11. Les composants transverses réutilisés (`Artwork` + indicateur in-lib, `StyleTag`, `LikeDislike`) ne sont pas modifiés pour cette page — écarts éventuels de CES composants partagés se notent pour les autres pages, pas ici.

## Captures jointes (prod, commit déployé)

| # | Fichier | Contenu |
|---|---------|---------|
| 01 | `01-desktop-dark-full.png` | Page complète desktop **dark** 1440px — head (titre, compteur, recherche, bouton Filtres, tri, menu +), table (Play·Track·Style·BPM·Key·Durée·Avis), indicateur in-lib sur les covers, `—` pour les nulls |
| 02 | `02-desktop-dark-filtres-actifs.png` | **Panneau de filtres ouvert AVEC filtres actifs** (BPM 124-130, Key 8A+9A, Style House) — chips actives + « Tout effacer », badge « Filtres 4 », sliders/Camelot/style en état sélectionné, « 773 résultats », liste filtrée en dessous |
| 03 | `03-desktop-dark-empty.png` | **Empty state** (E10) — « 0 résultat », « Aucun résultat avec ces filtres », chips retirables, bouton « Réinitialiser tous les filtres » |
| 04 | `04-desktop-light-full.png` | Page complète desktop **light** — parité de thème |
| 05 | `05-mobile-375-dark.png` | Mobile **375px** dark — colonnes réduites Play·Track·**BPM**·Avis, play/avis visibles |
| 06 | `06-mobile-375-drawer.png` | Mobile 375px — **drawer de filtres ouvert** (bottom-sheet, poignée, header + Réinitialiser, BPM/Année sliders, Durée, Camelot 6×4, Bibliothèque, Styles/pilier, Artiste, Label, Avis, Extrait audio, CTA sticky « Afficher N résultats ») |

## Fichiers d'implémentation à relire (GitHub, branche master)

Pour vérifier la conformité aux tokens/valeurs de tes briefs (rendu uniquement, pas le code) :
- `server/frontend/src/views/ExplorerView.vue` (la page : head, table, grille, états, responsive)
- `server/frontend/src/components/filters/*.vue` (les 12 composants de la famille) + `filter-fields.css`
- Réfère-toi à `docs/refonte-ui/handoff-explorer/BRIEF-explorer.md` et `BRIEF-filtres-partages.md` comme référentiel.

## Ce que tu dois produire : `FIX-explorer.md`

Pour chaque écart constaté entre le rendu (captures) / l'implémentation et TES briefs :
- **[visuel]** : différence de rendu observable (couleur/token hors palette, espacement, taille, alignement, état manquant, contraste, responsive cassé…).
- **[spec]** : élément de tes briefs non implémenté ou implémenté différemment (hors arbitrages actés ci-dessus).
- Pour chacun : **localisation** (capture # ou composant), **constaté** vs **attendu** (valeur/token précis), **sévérité** (bloquant / moyen / mineur).
- Si tout est conforme sur un axe, dis-le explicitement.
- Ne propose pas de refonte ni de nouvelles features : uniquement la conformité au handoff existant.

Merci de livrer `FIX-explorer.md` en un seul bloc téléchargeable.

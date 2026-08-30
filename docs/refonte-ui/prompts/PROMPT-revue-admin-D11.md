# Prompt — Revue design Claude Design · Admin D11 (round unique)

> Envoyer au projet Claude Design. Round UNIQUE, timeboxé. Objectif : vérifier la conformité de l'implémentation LIVRÉE à TON brief `BRIEF-admin-D11.md`, rien d'autre.

## Cadre de la revue

Le reskin D11 de la console admin est **déployé en prod** et conforme aux tests (741 front verts, tokens/container-queries/zéro-emoji vérifiés). Tu reçois : (canal captures) le rendu réel des 6 onglets en dark/light/mobile ; (canal code) les fichiers exacts à relire sur GitHub. Produis **UN SEUL fichier `FIX-admin-D11.md`**, écarts tagués `[visuel]` (rendu ≠ intention) ou `[spec]` (code ≠ brief), avec **valeur constatée vs attendue**. Si tout est conforme, dis-le.

**Interdictions strictes** : ne commente PAS l'architecture JS / les patterns Vue / le nommage des classes / la structure des composants — uniquement la conformité VISUELLE et de SPEC à ton brief. Les placeholders/reliquats assumés ne sont pas des écarts.

## Arbitrages d'implémentation DÉJÀ ACTÉS (ne pas les rouvrir comme écarts)

1. **D22 palette de courbes** : l'implémentation consomme les tokens `--chart-*` EXISTANTS de `diggy-tokens.css` (`--chart-deezer/-soft`, `--chart-beatport/-soft`, `--chart-bpm`, `--chart-sets`, `--chart-albums`, `--chart-embeddings`, `--chart-grid/-axis`), PAS une palette réinventée à partir des hues de piliers. Ces tokens sont CVD-validés et theme-flippants. Couleur pleine = actionnable, `-soft` = total. **C'est une décision, pas un écart.**
2. **Jeu d'icônes** : le jeu D2 a été complété de `refresh` (boutons Actualiser/Rafraîchir) et `x` (croix — état « segment non trouvé sur Deezer », D13). 12 glyphes au total.
3. **« Détacher le groupe » (Sets)** : aucun endpoint back « groupe » n'existe → câblé en boucle client sur l'endpoint par-set existant ; sur échec partiel, message « N détaché(s) sur M — réessayez ». (Un vrai endpoint atomique est un futur back, hors D11.)
4. **Horodatage de fin de job** : NON rendu (les payloads Celery ne contiennent pas de timestamp de fin exploitable — aucune donnée fabriquée).
5. **Conséquence chiffrée du reset Beatport** : NON chiffrée (l'endpoint ne pré-compte pas ; emphase mono qualitative « Toutes les données Beatport » au lieu d'un nombre fictif).
6. **Table Mappings (Genres)** : NON paginée (fetch unique `limit=200`, affichage complet — comportement existant conservé, 0 back).
7. **Cas « déjà en cours »** : le bouton reste RÉ-ACTIVABLE après le skip (fidélité à la logique existante, pour permettre un nouvel essai) ; la pill neutre « Déjà en cours » + arc porte le signal d'état.
8. **Aperçu** : le régime « inconnu » (métrique `null`) et les nombres de contexte groupés+mono existaient déjà avant D11 — L6 n'a fait qu'aligner icônes/slot centré/carte à jour enfoncée.

## Canal captures (dans `C:\tmp\captures-admin-d11-livre\`, jointes)

Desktop DARK (1280) : `apercu-dark-desktop.png` · `artistes-dark-desktop.png` · `sets-dark-desktop.png` · `genres-dark-desktop.png` · `enrichissement-dark-desktop.png` · `observabilite-dark-desktop.png`.
Desktop LIGHT (1280) : `apercu-light-desktop.png` · `artistes-light-desktop.png` · `sets-light-desktop.png` · `genres-light-desktop.png` · `enrichissement-light-desktop.png` · `observabilite-light-desktop.png`.
Mobile 375 DARK : `apercu-dark-mobile.png` · `artistes-dark-mobile.png` · `sets-dark-mobile.png` · `genres-dark-mobile.png` · `enrichissement-dark-mobile.png` · `observabilite-dark-mobile.png`.
Monitoring (clip du bloc, courbes rendues) : `monitoring-dark-clip.png` · `monitoring-light-clip.png`.

Correspondance onglet → archétypes de ton brief : Aperçu (grille harmonisée D20) · Artistes (A jobs groupés + D double liste + B flags + E splitter) · Sets (C cartes de groupes) · Genres (A reclassify + B mappings + recherche node) · Enrichissement (A + variante danger D6) · Observabilité (F Monitoring en haut + B tables Crawl/Audit + couture D10).

## Canal code (relire sur GitHub, commit f57956a)

- `server/frontend/src/assets/admin-table.css` (socle `.at-*` + `.at-seg`)
- `server/frontend/src/components/admin/AdminIcon.vue` (jeu d'icônes)
- `server/frontend/src/components/admin/AdminArtists.vue` · `AdminFlags.vue` · `ArtistSegmentSplitter.vue`
- `server/frontend/src/components/admin/AdminSets.vue`
- `server/frontend/src/components/admin/AdminGenres.vue`
- `server/frontend/src/components/admin/AdminBeatport.vue` · `AdminEnrichmentActions.vue`
- `server/frontend/src/components/admin/AdminCrawl.vue` · `AdminAuditLog.vue`
- `server/frontend/src/components/admin/AdminMonitoring.vue` · `components/charts/{StatTile,TimeSeriesChart,SparkLine}.vue`
- `server/frontend/src/components/admin/AdminOverview.vue`

## Livrable

`FIX-admin-D11.md` : liste d'écarts `[visuel]`/`[spec]` (valeur constatée vs attendue de ton brief), triés par gravité. Si conforme, une ligne « RAS ». Pas de refonte, pas de nouvelle décision DA — uniquement l'écart entre le livré et `BRIEF-admin-D11.md`.
```

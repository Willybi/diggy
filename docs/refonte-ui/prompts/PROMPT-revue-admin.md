# Prompt — Claude Design · Revue post-implémentation Admin (`/admin`)

> Round de revue UNIQUE, timeboxé. Objectif : confronter l'implémentation déployée au `BRIEF-admin.md` que tu as produit. Livrable = un seul `FIX-admin.md`, écarts tagués `[visuel]` (rendu ≠ brief, mesurable) / `[spec]` (comportement/état ≠ brief).

## Contexte
Chantier Admin (D4-Admin + D7 fusionnés) livré et déployé en prod. **Refonte ciblée** : le seul écran designé est le nouvel onglet **« Aperçu »** (dashboard backlog, 11 cartes, badges d'onglets) ; le reste = finition responsive mobile (palier 859px, grammaire `data-label` d'AdminFlags) des onglets existants. Monitoring et le contenu desktop des 7 onglets sont **hors périmètre** (non re-designés).

Revue STRICTEMENT limitée à la conformité à TES briefs (`BRIEF-admin.md`). **Interdit** : commenter l'architecture JS / les patterns Vue / le nommage / la structure des composants. Les placeholders et arbitrages déclarés ci-dessous **ne sont pas des écarts**.

## Captures fournies (dans `C:\tmp\captures-admin\`, produites en headless authentifié sur la prod réelle)
- `01-apercu-desktop-dark.png` — Aperçu desktop dark, 11 cartes, état réel mixte (6 backlog / 5 à-jour), badges d'onglets.
- `04-apercu-desktop-light.png` — idem en light.
- `02-apercu-mobile-375.png` — Aperçu mobile : 1 colonne, barre d'onglets scrollable.
- `03-crawl-mobile-375.png` — onglet Crawl mobile : table 7 colonnes → cartes `data-label` (référence du pattern responsive).
- `05-genres-mobile-375.png` — onglet Genres mobile (sections Reclassifier + Mappings ; le filtre « Non mappé » est vide car 0 mapping non mappé en prod — le table→card est illustré par 03).
- `06-sets-mobile-375.png` — onglet Sets mobile : revue set-flags empilée + actions tactiles.

## Fichiers de code à relire (conformité au BRIEF uniquement)
- `server/frontend/src/components/admin/AdminOverview.vue` (le cœur : 11 cartes, 2 régimes, états).
- `server/frontend/src/views/AdminView.vue` (onglet Aperçu, barre scrollable, badges).
- `server/frontend/src/components/admin/{AdminGenres,AdminCrawl,AdminSets,AdminArtists}.vue` (finition responsive 859px).

## Arbitrages d'implémentation DÉJÀ ACTÉS (ne pas les remonter comme écarts)
1. **Cartes en renvoi neutre** (bouton neutre → ouvre l'onglet, pas de job) : **Deezer**, **Genres** (×2), **Sets à recrawler**, Crawl (×2), Flags, Set-flags. Raison : pas de déclencheur back existant (ou revue humaine). Seules **Beatport**, **Artistes à lier**, **Artistes sans pochette** ont un bouton accent (job réel). C'est volontaire — le BRIEF listait « Sets à recrawler » en job accent, mais aucun endpoint de recrawl manuel n'existe → renvoi.
2. **Liens secondaires « Onglet X »** sur les 3 cartes à job : conservés (fidèle à A6).
3. **AdminSets actions** : `flex-direction: column` (pas `column-reverse`) — le DOM réel est déjà `[Attacher, Rejeter]`, donc `column` place bien **Attacher au-dessus** (but de A11). Un grep littéral de `column-reverse` le noterait absent : c'est intentionnel.
4. **Carte « À lier sur Deezer » affiche « 5 »** sur les captures : c'est l'ancien compteur brut (orphelins inclus). Un **correctif de données** est déjà livré (compte = même filtre que le panneau, délié + rattaché → 0 → « À jour ✓ ») mais **pas encore déployé** au moment des captures. Ne PAS le remonter — c'est de la donnée, pas du design.
5. **Colonnes Genres réelles** = `Nom brut / Nœud taxonomique / Recherche` (pas de colonne « Statut » comme dans le pattern générique du BRIEF) — mappé sur le composant réel.

## Deux points déjà repérés — ton avis bienvenu (pas des blocages)
- **DLQ (Redis injoignable, `dlq=null`)** : la carte « File d'échec (DLQ) » bascule alors en visuel « À jour ✓ » avec contexte « indisponible ». Aucun régime « inconnu » n'était designé. Veux-tu un traitement visuel distinct (ex. neutre « — » plutôt que le check vert) pour ce cas de bord ?
- **Barre d'onglets** : l'onglet actif sélectionné n'est **pas** ramené dans la vue par scroll (si on clique un onglet hors-écran en mobile, la barre ne défile pas jusqu'à lui). Nicety A10 non implémentée. Souhaitable ?

## Livrable
Un seul `FIX-admin.md` :
- écarts tagués `[visuel]` / `[spec]`, avec **valeur constatée vs attendue** (référence le nº de capture ou la ligne de brief) ;
- si rien de significatif : le dire clairement (« implémentation fidèle »).

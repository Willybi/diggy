# Prompt — Claude Design · Revue post-implémentation Radar (D6)

> À envoyer au projet Claude Design. Round de revue UNIQUE et timeboxé.
> William joint : ce prompt + les 6 captures listées ci-dessous (dossier `C:\tmp\captures-radar\`).
> Livrable attendu : **un seul fichier `FIX-radar.md`** listant les écarts, chacun tagué **[visuel]** ou **[spec]**, avec valeur constatée vs attendue.

## Contexte

Tu avais produit le handoff design de la **nouvelle page Radar** de Diggy = surface de recommandation **bi-score** (une liste unique où chaque son porte deux scores côte à côte, **Tendance** + **Pour toi**, triable par l'un ou l'autre) : `BRIEF-radar.md` (décisions DA R1–R9) + la maquette pilote. L'implémentation est **déployée en prod** (`https://diggy-music.fr/radar`). Tu fais maintenant la revue de conformité de l'implémentation à **TON propre brief**.

**Périmètre de la revue** : fidélité **visuelle / DA / UX** au handoff uniquement (tokens, espacements, états, responsive, anatomie de la ligne bi-score, colonne active, « — », velocity).
**HORS périmètre, interdit de commenter** : l'architecture JS/Vue, le découpage des composants, les choix techniques (composables, virtualisation, sync URL, fetch), la qualité du code. Tu ne juges QUE le rendu et sa conformité à ton brief.

## Arbitrages d'implémentation DÉJÀ ACTÉS (ne PAS les remonter comme écarts)

Ces points s'écartent volontairement de la maquette ou tranchent une latitude — ils sont validés :

1. **Compteur live « N résultats »** (et non « N sons ») : le libellé vient du composant partagé `FilterBar` (réutilisé tel quel, comme Explorer) — on ne le modifie pas pour cette page.
2. **Compteur de head** « N tendances · M pour toi » (cold-start → « … · Pour toi en attente de tes likes ») : conforme au brief.
3. **Menu « + » imports absent** du head (décidé au handoff : sans objet sur une surface reco).
4. **Column-drop mobile** : sous 640 px les colonnes sont **Play · Track · Tendance · Pour toi · Avis** (les 2 scores survivent ; Style→Key→BPM tombent avant). Le **sélecteur de tri est masqué < 640 px** en v1 (reliquat assumé, rejoindra le drawer plus tard, comme Explorer).
5. **Seuil velocity ▲** = velocity ≥ 1,5 (bornée 0..5 côté serveur) → ▲ sur l'anneau **Tendance** uniquement.
6. **Bornes statiques** des sliders : BPM 60–200, Année 1985–2026 (comme Explorer).
7. **Recherche = titre + artiste** (le filtre **Label** dédié du panneau couvre le label) — arbitrage acté.
8. **Badge `#rank`** conservé sur le titre si `trend_rank` ≤ 50 (comme Explorer).
9. Les composants transverses réutilisés (`<ScoreRing>` géométrie non redéfinie, `<Artwork>` + indicateur in-lib, `<StyleTag>`, `<LikeDislike>`, famille `filters/`) ne sont **pas** modifiés pour cette page — un écart éventuel de CES composants partagés se note pour d'autres pages, pas ici.

## Point DÉJÀ IDENTIFIÉ à trancher (pas un écart à découvrir — donne ta reco de correction)

- **Chevauchement des en-têtes de colonne de score en mobile** (capture 06) : sous ~450 px, les libellés d'en-tête mono uppercase « TENDANCE » et « POUR TOI » sont plus larges que leurs colonnes (~52 px) et **se superposent**. Les rangées (anneaux, bande, « — », ▲) sont correctes ; seul le header déborde. **Recommande l'approche de correction** que tu préconises (ex. réduire la police des en-têtes de score < 640 px / abréger / masquer le libellé texte puisque l'anneau + la bande active identifient déjà la colonne triée / autre). C'est le principal point du round.

## Captures jointes (prod, commit déployé)

| # | Fichier | Contenu |
|---|---------|---------|
| 01 | `01-desktop-dark-full.png` | Page complète desktop **dark** 1440px — head (« Radar » + « 413 tendances · 100 pour toi »), barre de filtres, tri « Tendance » actif, colonnes Play·Track·Style·BPM·Key·**Tendance·Pour toi**·Avis, « 505 résultats » |
| 02 | `02-desktop-dark-scores-zoom.png` | **Zoom colonnes de score** — en-tête « TENDANCE ↓ » avec **bande de colonne active** `--accent-wash` continue, anneaux `<ScoreRing>` /10, **▲ velocity** sur les anneaux Tendance, **« — » muet** côté Pour toi, un anneau Pour toi « 6 », lignes liked (cœur vert) |
| 03 | `03-desktop-dark-sort-pourtoi.png` | **Tri « Pour toi » actif** — la bande `--accent-wash` s'est déplacée sur la colonne Pour toi, en-tête Pour toi surligné + flèche ; vérifie la symétrie du surlignage de colonne active |
| 04 | `04-desktop-light-full.png` | Page complète desktop **light** — parité de thème (bande, anneaux, ▲, « — », liked) |
| 05 | `05-mobile-390-dark-full.png` | Mobile **390px** dark — colonnes réduites **Play·Track·Tendance·Pour toi·Avis** (les 2 scores survivent), play/avis visibles ; BottomNav |
| 06 | `06-mobile-390-header-zoom.png` | **Zoom header mobile** — met en évidence le **chevauchement « TENDANCE »/« POUR TOI »** (point à trancher ci-dessus) ; rangées correctes en dessous |

## Fichier d'implémentation à relire (GitHub, branche master)

Pour vérifier la conformité aux tokens/valeurs de ton brief (rendu uniquement, pas le code) :
- `server/frontend/src/views/RadarView.vue` (la page : head, table bi-score, colonne active, « — », velocity, cold-start, états, responsive)
- Référentiel : `docs/refonte-ui/handoff-radar/BRIEF-radar.md`.

## Ce que tu dois produire : `FIX-radar.md`

Pour chaque écart constaté entre le rendu (captures) / l'implémentation et TON brief :
- **[visuel]** : différence de rendu observable (couleur/token hors palette, espacement, taille, alignement, état manquant, contraste, responsive cassé…).
- **[spec]** : élément de ton brief non implémenté ou implémenté différemment (hors arbitrages actés ci-dessus).
- Pour chacun : **localisation** (capture # ou zone), **constaté** vs **attendu** (valeur/token précis), **sévérité** (bloquant / moyen / mineur).
- Inclure ta **reco de correction pour le chevauchement header mobile** (point identifié).
- Si tout est conforme sur un axe, dis-le explicitement.
- Ne propose pas de refonte ni de nouvelles features : uniquement la conformité au handoff existant.

Merci de livrer `FIX-radar.md` en un seul bloc téléchargeable.

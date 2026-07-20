# Prompt — Claude Design · Re-check Artist Detail (round 2, après correctifs)

> Envoyer au projet Claude Design avec les 6 captures listées en bas.
> Round de CONTRÔLE court : tu as déjà livré ton FIX (round 1) ; les correctifs sont déployés.
> Objectif : confirmer que la page est conforme à TON `BRIEF-artist-detail.md` (A1-A9), ou lister les écarts résiduels.

---

## Ce qui a été corrigé depuis ton FIX (commits c81b7e3, 01548f4, + fix avatar)

- **#1-#4 (hero)** : une seule cause racine — les rangées du montage (`1fr` = `minmax(auto,1fr)`) débordaient (covers 250×250 → ~170px/rangée dans un banner 216px) et le grid positionné peignait par-dessus tout le bloc sous-banner. Corrigé : `minmax(0,1fr)` + `overflow:hidden` sur le banner (parité avec ta maquette). L'avatar est aussi passé en positionné (il était peint SOUS le montage). Le nom est sur l'axe du contenu (`calc(--space-6 + 120px + --space-5)`).
- **#5 (proches croppés)** : le crop 1-rangée d'`ExpandableShelf` est neutralisé par override scoped — aperçu 12 cartes entières.

## Verdicts actés au triage round 1 — NE PAS re-signaler

- **#6** (« Voir les N autres » lien texte vs `.btn--sm` « Afficher les N autres artistes ») : libellé/style codés en dur dans le composant partagé `ExpandableShelf` — REJETÉ au niveau page, noté comme chantier transverse futur du composant. Pas un écart de cette page.
- **#7** (compteur en pastille) : en-tête rendu par le composant partagé (inchangeable) — arbitrage acté.
- **#8** (silhouette Danil Wright) : le fallback code est bien l'initiale ; l'image stockée EST un placeholder Deezer ingéré (problème de donnée, backlog worker). Pas un écart de rendu.
- Logos plateformes = tracés placeholders (reliquat assumé). AdminCard hors périmètre. Breakpoints `@container (max-width: 720/640px)` sans nom de container = convention repo, prime sur le pilote.

## Ta mission (round unique, court)

Sur les 6 captures : confirmer point par point la conformité du hero (montage 6×2 contraint, scrim, nom sur l'axe, avatar débordant ring 3px, genres, actions, stats repliées sans Rating), des tracks, des sets (grille + footer « NN % identifiées »), des proches (12 entières), des aliases, du light et du mobile — ou lister les écarts résiduels au MÊME format que ton FIX (tableau : # · Tag [visuel] · Capture · Constaté · Attendu (réf A1-A9) · Sévérité). Si tout est conforme : dis-le explicitement, livrable = « RAS, page conforme au brief ».

## Captures jointes

| # | Fichier | Contenu |
|---|---------|---------|
| 1 | 01-desktop-dark-full.png | `/artist/27` (Fred again.., riche) — page complète dark |
| 2 | 02-desktop-dark-hero.png | Zoom hero dark : montage, nom, avatar, genres, actions, stats |
| 3 | 03-desktop-dark-aliases.png | `/artist/686` (DJ Heartstring) — hero + ligne ALIAS |
| 4 | 04-desktop-light-full.png | `/artist/27` — page complète light |
| 5 | 05-desktop-light-hero.png | Zoom hero light (lisibilité nom/scrim, ring avatar) |
| 6 | 06-mobile-375-dark-full.png | `/artist/27` — mobile 375px (banner 150, avatar en flux 72, durée masquée, stats) |

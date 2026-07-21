# FIX Explorer — revue design Claude Design + triage work_manager (2026-07-21)

> Round de revue UNIQUE. Revue Claude Design ci-dessous, **annotée des verdicts work_manager** (chaque [spec]/[visuel] vérifié contre le code / le rendu réel AVANT acceptation — pipeline `/refonte_page` Phase 6).
> Prompt de revue : `docs/refonte-ui/prompts/PROMPT-revue-explorer.md`.
> Verdict revue : conforme dans l'ensemble, 3 écarts annoncés (1 moyen, 2 mineurs).
> **Résultat triage : 1 ACCEPTÉ (É1), 2 REJETÉS (É2 + É3, faux écarts vérifiés).** (É3 rectifié après contrôle du code réel — voir sa section.)

## Note sur les captures

Claude Design a été relu avec l'ancien jeu (`prod-01..04` + `prod-fix-mobile`), pas le pack de revue numéroté (`01..06`). Sa section « non vérifiables » (empty state, drawer mobile, filtres actifs + chips) est donc un artefact du mauvais jeu : ces surfaces **ont été vérifiées par le work_manager** sur les captures `02-desktop-dark-filtres-actifs`, `03-desktop-dark-empty`, `06-mobile-375-drawer` → **conformes** (chips + badge « Filtres 4 » + Camelot/segments sélectionnés en accent ; empty state E10 complet ; drawer bottom-sheet + Camelot 6×4 + CTA sticky). Aucune action.

## Écarts — verdicts

### É1 — Boutons Avis masqués au repos sur desktop · [spec] · moyen → **ACCEPTÉ**
- **Constaté (revue)** : colonne AVIS vide au repos desktop (dark + light) ; icônes révélées au hover seulement. Visibles sur mobile.
- **Vérification (CDP, prod)** : `getComputedStyle('.xp-cell--avis .ld-btn').opacity === "0"` au repos → confirmé. CSS : `.xp-cell--avis :deep(.ld-btn){opacity:0}` + `.xp-row:hover … {opacity:1}` (ExplorerView.vue). Le brief (Table › Avis) spécifie les 2 boutons **visibles au repos** (`--ink-3`), seul **Play** est en hover-reveal desktop.
- **Résolution** : rendre les boutons Avis visibles au repos sur desktop (`--ink-3`), conserver le hover-reveal UNIQUEMENT sur Play ; états liked/disliked colorés et comportement mobile inchangés.

### É2 — BPM / Durée alignés à gauche · [visuel] · mineur → **REJETÉ (faux écart)**
- **Constaté (revue)** : valeurs BPM/Durée « alignées à gauche ».
- **Vérification (CDP, prod)** : cellule `.xp-cell.col-bpm` → `textAlign:"right"`, texte interne collé au bord droit (`gapRight:0`, `gapLeft:30` sur une cellule de 56 px). Les cellules portent `xp-cell--right` (`text-align:right`) en-têtes inclus. **Le rendu EST aligné à droite, conforme au brief.** Lecture erronée de la capture (colonne étroite). Aucune action.

### É3 — Style vide rendu blanc au lieu de « — » · [spec] · mineur → **REJETÉ (faux écart)**
- **Constaté (revue)** : cellule STYLE totalement vide quand la track n'a ni genre ni style (Surveillance, Cruize, TNGHT, Dah Welcome).
- **Vérification (code réel)** : la cellule Style A DÉJÀ la branche finale — `ExplorerView.vue:263` : `<span v-else class="xp-null">—</span>` (classe `xp-null` = `--ink-3`, la même que le tiret BPM/Key null), présente depuis le commit d'origine `e2b90ac`. La track sans genre ni style affiche donc bien « — ». Aucune action.
- **Note de process (erreur de triage rectifiée)** : mon acceptation initiale reposait sur une lecture INCOMPLÈTE du code (grep limité aux lignes de match, tronqué à la l.262 — le `v-else` est à la l.263 juste en dessous). L'agent correctif l'a signalé et n'a — à raison — rien ajouté (un 2ᵉ `v-else` serait invalide). Leçon : un [spec] se vérifie sur le BLOC complet autour des lignes citées, pas sur des lignes de grep. Le reviewer avait aussi mal lu (~l.252-262).

## Déjà résolu (traçabilité)
- **Colonne mobile Key → BPM** : `prod-03` (avant fix) montrait Key ; le round FIX tri+mobile (commit b8e7875) a livré BPM au palier étroit — conforme à l'arbitrage acté #7. Rien à faire.

## Suite
Mini-lot correctif : **É1 uniquement** (CSS, `ExplorerView.vue`). É2 et É3 clos sans action (faux écarts vérifiés). Déploiement léger (front pur) → vérification visuelle headless (avis visibles au repos desktop). vitest 381 + eslint verts.

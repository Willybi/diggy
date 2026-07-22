# FIX — Radar `/radar` · Revue post-implémentation (D6)

> Round de revue design UNIQUE (Claude Design), sur l'implémentation prod (`diggy-music.fr/radar`, captures 01–06) vs `BRIEF-radar.md` (R1–R9). Périmètre rendu/DA/UX.
> **Triage work manager (2026-07-23)** annoté sous chaque point : chaque [visuel]/[spec] vérifié contre le code avant acceptation.
> Bilan revue : implémentation **très fidèle**. 1 point moyen (header mobile), 1 mineur (rejeté après vérif code), 1 observation.

---

## 1. [visuel] Chevauchement des en-têtes de colonne de score en mobile · MOYEN

- **Localisation** : capture 06 (header mobile 390 px), sous ~450 px.
- **Constaté** : « TENDANCE » et « POUR TOI » se superposent, le second débordant sur la bande active. Rangées correctes.
- **Attendu** : deux en-têtes lisibles, non chevauchants.
- **Cause (revue)** : colonnes score mobile 52 px ; en-tête `--fs-label` (10,5 px) mono uppercase + `letter-spacing 0.07em` → « TENDANCE » ≈ 55 px > 52 px.
- **Reco (revue)** : sous 640 px, en-têtes score en `--fs-nano` + `letter-spacing 0` + centré. **Ne pas masquer les libellés** : en mobile le tri est figé sur Tendance (select masqué), la colonne Pour toi n'est jamais surlignée → sans libellé les 2 anneaux adjacents deviennent indistinguables. Abréviation rejetée aussi (mots complets plus petits = plus clairs).

**→ TRIAGE : ACCEPTÉ.** Confirmé par capture 06 + code. Le raisonnement anti-masquage est correct (tri figé mobile → pas de désambiguïsation par la bande active). **Correction** : dans le bloc `@container (max-width: 639px)` existant de `RadarView.vue` (seuil repo = 639, pas 640), cibler la **vraie classe `.rd-th--score`** (les deux en-têtes Tendance + Pour toi) → `font-size: var(--fs-nano)` + `letter-spacing: 0`. (La reco citait `.rd-c-score`, classe inexistante — corrigé en `.rd-th--score`.) Porté au mini-lot correctif.

## 2. [visuel] Couleur de l'accent velocity ▲ · MINEUR *(à confirmer)*

- **Constaté (revue)** : le ▲ semble en `--accent` saturé (comme l'arc), plus soutenu que `--accent-ink`.
- **Attendu (R5)** : ▲ 9 px en `--accent-ink`, discret.

**→ TRIAGE : REJETÉ — déjà conforme.** Vérification code `RadarView.vue` : `.rd-velo { color: var(--accent-ink); }` + `<path fill="currentColor">`. Le ▲ est **déjà `--accent-ink`** (conforme R5). L'arc de l'anneau, lui, est `--accent` (`ScoreRing .sr-arc`) — d'où la proximité visuelle en dark et la confusion de lecture. Aucun changement.

## Observation — troncature Track mobile (conforme, pas un écart)

Capture 05 : titres/artistes très tronqués (« Wit… ») sous 640 px. **Conséquence directe de la grille du brief** (`40px 1fr 52px 52px 76px` : les 2 scores + play + avis laissent ~76 px au `1fr` Track). L'implémentation respecte le handoff. Évolution éventuelle (rogner un peu les colonnes score) = modif du handoff, hors de cette revue → **aucune action**.

---

## Axes vérifiés — CONFORMES (revue)

Head bi-score, anatomie ligne (2 `ScoreRing` sm, ordre Tendance→Pour toi, pas de Durée), colonne active (bande `--accent-wash` continue + libellé `--accent-ink` + flèche ; symétrie Tendance↔Pour toi selon le tri, capture 03), « — » muet, BPM/Key null, StyleTag + « +N » (hues piliers), badge #rank, like/wash liked, parité dark/light, column-drop mobile (2 scores survivent, play+avis visibles), barre de filtres fermée + select tri. Tous **conformes**.

## Non couvert par ce round (aucune capture — non jugé)
Cold-start (R7), empty state, skeleton, panneau/drawer filtres ouverts, header sticky en scroll, rangées playing/disliked. Implémentés et couverts par les tests Vitest ; non re-vérifiés visuellement ici.

---

## Synthèse triage

| # | Type | Point | Sévérité | Verdict |
|---|------|-------|----------|---------|
| 1 | [visuel] | Chevauchement en-têtes score mobile <~450px | Moyen | **ACCEPTÉ** → mini-lot (`.rd-th--score` `--fs-nano`+ls0 @639) |
| 2 | [visuel] | ▲ velocity couleur | Mineur | **REJETÉ** — code déjà `--accent-ink`, conforme R5 |
| — | obs. | Troncature Track mobile | Info | **CLOS** — issue du grid du brief, pas une déviation |

Aucun écart bloquant. Un seul correctif retenu : la lisibilité des en-têtes de score en mobile.

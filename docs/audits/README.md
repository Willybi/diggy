# Audits globaux — fonctionnement

> Système d'audit périodique de santé du code, lancé via la commande `/audit_global`.
> Objectif : détecter dette technique, failles, perfs, code mort, opportunités de refactor — et en faire des chantiers roadmap arbitrés.
> Modèle d'origine : l'audit de juillet 2026 (`docs/audit_2026-07/`, chemin historique) qui a produit la série AU de la roadmap.

## Organisation des fichiers

```
docs/audits/
├── README.md            # ce fichier (doc du système, stable)
├── LEDGER.md            # suivi inter-audits : un finding = une ligne, statut vivant
└── <AAAA-MM>/           # un dossier par audit (ex. 2026-11/)
    ├── _inventory.md    # Phase 0 : sorties brutes des outils (CANDIDATS, pas findings)
    ├── A1_backend.md    # Phase 1 : un rapport par dimension (A1..A8)
    ├── ...
    ├── CONSOLIDATED.md  # Phase 2 : dédup, top 5, delta vs audit précédent, priorisation
    └── DECISIONS.md     # Phase 3 : arbitrages de William (Q1..Qn)
```

Le premier audit (2026-07) vit à son chemin historique `docs/audit_2026-07/` et n'est pas déplacé. **Dernier audit complet : `docs/audits/2026-08/`** (mettre à jour cette ligne à chaque audit).

## Pipeline (résumé — le détail est dans `.claude/commands/audit_global.md`)

1. **Phase 0 — Inventaire outillé** : ruff, vulture, deptry, pip-audit, npm audit/outdated, TODO/FIXME, churn git. Sorties brutes = candidats à vérifier, jamais des findings.
2. **Phase 1 — Agents par dimension** (parallèle, lecture seule) : A1 Backend, A2 Database, A3 Workers, A4 Frontend, A5 Infra/CI, A6 Sécurité & tests, A7 Hygiène repo/doc, A8 Invariants projet. Chaque rapport ouvre par « Ce qui va bien » puis des findings au format imposé (preuve obligatoire).
3. **Phase 2 — Consolidation** : dédoublonnage, contre-vérification ligne à ligne des findings lourds, croisement avec le LEDGER, delta vs audit précédent, matrice de priorisation.
4. **Phase 3 — Arbitrage** : questions de décision posées à William, consignées dans DECISIONS.md. Rien ne part en chantier sans arbitrage humain.
5. **Phase 4 — Ledger & roadmap** : mise à jour du LEDGER, proposition d'un bloc roadmap (série type AU), commit docs.

## Taxonomie

- **Sévérité** : `critique` (perte de données, faille exploitable, prod en danger) · `haute` (bug utilisateur réel, fuite inter-users, invariant violé) · `moyenne` (dette qui freine, perf dégradée, risque latent) · `basse` (hygiène, code mort, doc).
- **Effort** : S (< ½ journée) · M (1-2 jours) · L (chantier).
- **Confiance** : haute (preuve directe vérifiée) · moyenne (preuve indirecte) · basse (soupçon argumenté).
- **QUICK WIN** : impact haute|critique × effort S. Tag `QW-c` = candidat quick win (effort S, risque faible) même en sévérité moyenne.
- **Clé de finding** : `<AAAA-MM>/Ax-nn` (audit qui l'a découvert + ID local). Un finding récurrent garde sa clé d'origine — la récurrence se lit dans « Dernière vue » du LEDGER.

## Statuts du LEDGER

| Statut | Sens |
|---|---|
| OUVERT | découvert, pas encore arbitré ou pas encore corrigé |
| EN ROADMAP | intégré à un chantier (référence du chantier en colonne Résolution) |
| CORRIGÉ | fixé (commit + date en colonne Résolution) |
| ACCEPTÉ | arbitré « on vit avec » (référence DECISIONS Qn) — ne doit plus être re-signalé |
| OBSOLÈTE | le code concerné a disparu ou le contexte a changé |

Un finding ACCEPTÉ ne ressort dans un audit suivant que marqué **RÉÉVALUATION**, avec ce qui a matériellement changé.

## Cadence recommandée

- **Audit complet** : ~trimestriel, ou après la clôture d'une grosse série de chantiers (le moment où la dette s'est accumulée sans être visible).
- **Audit incrémental** (`/audit_global incremental`) : entre deux complets — périmètre = fichiers touchés depuis le dernier audit + leurs consommateurs directs.
- **Audit ciblé** (`/audit_global securite`, `/audit_global frontend`…) : une ou deux dimensions, quand un doute précis existe.

Éviter de lancer un audit pendant un chantier en cours de livraison : l'état du code doit être stable (commit propre) pour que le rapport soit réutilisable.

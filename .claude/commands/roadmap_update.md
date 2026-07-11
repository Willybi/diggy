---
description: Met à jour les statuts de la roadmap après un chantier
allowed-tools: Read, Glob, Grep, Edit, Bash(git log:*), Bash(git diff:*), Bash(git status:*)
argument-hint: [chemin roadmap optionnel]
---

Nous venons de terminer un chantier. Mets à jour la roadmap : $ARGUMENTS (si vide, cherche ROADMAP.md ou équivalent à la racine puis dans docs/).

## Étape 1 : Identifier les travaux effectués
Croise deux sources :
- le contexte de notre session en cours (ce que nous avons fait ensemble)
- l'historique git récent : !`git log --oneline -15` et le diff non commité s'il existe

Si les deux sources divergent (travail fait en session mais non commité, ou commits sans lien avec la session), signale-le avant de continuer.

## Étape 2 : Mettre à jour la roadmap
Modifie UNIQUEMENT les statuts des chantiers existants :
- passer en "terminé" ce qui est achevé
- passer en "en cours" ou noter l'avancement partiel si le chantier n'est pas fini
- ajouter la date du jour au chantier terminé si la roadmap date ses entrées

Contraintes strictes :
- ne crée AUCUN nouveau chantier, même si le travail a révélé des besoins
- ne modifie ni les descriptions, ni les priorités, ni la structure du document
- respecte scrupuleusement le format existant (syntaxe des statuts, casse, style)

## Étape 3 : Rapport
Résume en 3-5 lignes : quels statuts ont changé et pourquoi. Si des travaux effectués ne correspondent à aucun chantier de la roadmap, liste-les à part sans toucher au document.
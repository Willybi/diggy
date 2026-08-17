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
- **journal de tête** : si la roadmap tient un journal de clôtures (ex. un paragraphe « Dernière mise à jour » où chaque chantier terminé laisse une entrée), c'est un **log de statut → dans le périmètre** : ajoutes-y une entrée CONCISE (date + code chantier + 1 phrase de résumé) et bump la date de tête, dans le style exact des entrées existantes. C'est la seule addition tolérée hors des champs de statut ; ne touche à rien d'autre.

Contraintes strictes :
- ne crée AUCUN nouveau chantier, même si le travail a révélé des besoins
- ne modifie ni les descriptions, ni les priorités, ni la structure du document
- respecte scrupuleusement le format existant (syntaxe des statuts, casse, style)

## Étape 3 : Rapport
Résume en 3-5 lignes : quels statuts ont changé et pourquoi. Si des travaux effectués ne correspondent à aucun chantier de la roadmap, liste-les à part sans toucher au document.

Termine par un **nom de commit proposé** pour ce changement de roadmap, au format `docs(roadmap): <code chantier> <ancien statut> → <nouveau statut> (<résumé court>)` (ex. `docs(roadmap): D9 A FAIRE → TERMINE (fluidité navigation — KeepAlive + prefetch nav)`). Le commit roadmap est TOUJOURS séparé du commit du chantier (que le work manager a déjà proposé de son côté). Ne committe pas toi-même.
---
description: Etat de la roadmap et recommandation du prochain chantier
allowed-tools: Read, Glob, Grep
argument-hint: [chemin roadmap optionnel]
---

Lis la roadmap du projet : $ARGUMENTS (si vide, cherche ROADMAP.md ou équivalent à la racine puis dans docs/). Base-toi UNIQUEMENT sur ce document, ne va pas inspecter le code ou l'historique git.

Produis :

## 1. Chantiers en attente
Tableau : Chantier | Statut indiqué | Dépendances mentionnées | Taille estimée (S/M/L d'après la description)

## 2. Recommandation
Propose LE prochain chantier à lancer. Justifie en pondérant explicitement :
- dépendances (débloque-t-il d'autres chantiers ?)
- valeur apportée
- effort estimé
- cohérence avec ce qui vient d'être terminé

Mentionne brièvement le second choix et pourquoi il passe après.

Si la roadmap est ambiguë (statuts absents, chantiers non datés), signale-le en fin de réponse plutôt que d'inventer.
# Prompt — Revue design post-implémentation · Playlists (liste) `/playlists` (D6)

> À envoyer au projet Claude Design. **Round de revue UNIQUE, timeboxé.** La page est **déployée en prod** ; ci-dessous les captures du rendu réel + les fichiers de code à relire. Tu compares l'implémentation à **TON propre brief** (`BRIEF-playlists-list.md`) et tu produis un seul livrable : `FIX-playlists-list.md`.

## Ce que tu dois faire

Vérifier que le rendu déployé est **fidèle à ton brief** (hiérarchie de rangée, tokens, états, responsive, densité). William a le sentiment que **certains éléments sont « mal placés »** sans les nommer : porte une attention particulière à la **hiérarchie et au placement** dans la rangée enrichie (équilibre cover / titre+source / genre / créateur / tracks / bloc Dernier crawl / avis, alignements, espacements, densité verticale).

## Règles de la revue (strictes)

- **Périmètre = conformité à TON brief uniquement** + qualité visuelle du rendu. **Interdiction** de commenter l'architecture JS / les patterns Vue / le nommage / la gestion d'état — tu ne vois que le rendu et le CSS.
- Les **logos de plateforme** sont des tracés **placeholders** temporaires (map `platform→path` centralisée, remplacement prévu) — **ce n'est pas un écart**.
- Tag chaque écart **[visuel]** (rendu ≠ intention, ex. espacement/alignement/taille) ou **[spec]** (rendu ≠ une décision explicite du brief), avec **valeur constatée** vs **valeur attendue**.
- Les **placeholders/reliquats assumés** ne sont pas des écarts.

## Arbitrages d'implémentation DÉJÀ ACTÉS (ne pas les remonter comme écarts)

1. **Pastille cadence — le libellé change.** Le brief spécifiait `Quotidien / Hebdo / Mensuel` ; une **décision produit post-recette** le remplace par la **fraîcheur brute** (ex. « MAJ 3 j » / « MAJ 2 sem », l'âge relatif de la dernière nouveauté), toujours **uniquement si la donnée existe**, même emplacement, même style de pill mono. Sur les captures tu vois encore l'ancien libellé (`QUOTIDIEN`) : **ne le commente pas** — seul son **emplacement / style** est dans le périmètre, pas son texte.
2. **En-tête de tableau `sticky top: 0`** (calqué sur la liste Sets déployée, jumelle) — intentionnel, pas un écart.
3. **Bouton Crawl révélé au survol** de la rangée (invisible au repos sur les captures statiques) et **non repris en mobile** (< 640, action ponctuelle dispo sur la fiche `/playlists/:id`) — conforme à ton brief (P5/P12).
4. **Logo de source = glyph non cliquable** accolé au titre (contrainte : la rangée est un lien, pas d'ancre imbriquée). Son tooltip natif dit « Détecté sur X » (composant partagé non modifiable pour cette page) — hors périmètre.
5. **Genre replié à 1 seule chip** sous 720 px (dominante) — conforme P12.

## Captures du rendu DÉPLOYÉ (dossier joint `captures-playlists-list-review`)

- `01-desktop-dark-full.png` — page complète, desktop dark 1440px. Colonnes PLAYLIST (cover + titre + glyph source) · GENRE (1–2 StyleTags) · CRÉATEUR · TRACKS (nombre brut, aligné droite) · DERNIER CRAWL (date relative + pastille cadence quand présente) · AVIS. Défaut tri = Titre A→Z.
- `03-desktop-dark-modal.png` — modal **Ajouter** ouvert (champ URL, aide, bouton « Ajouter »), desktop dark.
- `04-desktop-dark-liked.png` — filtre d'avis **Liked** actif (sous-ensemble des playlists likées ; sous-compteur du head).
- `05-desktop-light-full.png` — page complète, desktop **light** 1440px.
- `06-mobile-375-dark.png` — mobile 375px : colonnes repliées à PLAYLIST (+ genre 1 chip + méta crawl sous le titre) · TRACKS · AVIS ; avis visibles au tactile.

*(Le bloc « Dernier crawl » avec statut live animé — En attente / En cours / Crawlé — est transitoire, non capturable en statique ; réfère-toi à ton brief P6 pour ces états.)*

## Fichiers de code à relire (sur GitHub, pour la conformité CSS/tokens)

- `docs/refonte-ui/handoff-playlists-list/BRIEF-playlists-list.md` — **ton brief** (référence de conformité).
- `server/frontend/src/views/WatchlistView.vue` — l'implémentation (template + `<style scoped>`). Vérifie tokens, dimensions, états, responsive contre ton brief. **Ne commente que le CSS/rendu.**

## Livrable

Un seul fichier **`FIX-playlists-list.md`** : liste d'écarts, chacun `[visuel]` ou `[spec]`, avec **emplacement**, **constaté**, **attendu**, et une **reco** courte. Si aucun écart : dis-le explicitement. Priorise ce qui touche la **hiérarchie/placement de la rangée** (préoccupation de William). **Archive ZIP inutile** — un seul `.md` collé suffit.

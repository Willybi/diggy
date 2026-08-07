# Handoff — Admin (`/admin`) · chantier D4-Admin + D7 (fusionnés)

Provenance : projet **Claude Design** (livraison `livraison-admin`, 2026-08-06), sur la base de [`PROMPT-claude-design-admin.md`](../prompts/PROMPT-claude-design-admin.md) + fiche [`admin.md`](../admin.md) (§7 prime).

## Fichiers

| Fichier | Rôle |
|---|---|
| `BRIEF-admin.md` | **Contrat d'implémentation** (source de vérité du chantier). |
| `Admin-pilote.html` | Maquette de prévisualisation interactive (régimes Backlog/À jour/Chargement/Erreur, 8 onglets cliquables, toggles thème/viewport). **Référence visuelle uniquement** — bâtie en React + Google Fonts CDN ; on implémente en Vue d'après le BRIEF, PAS d'après ce code. |

## Décisions issues des rounds Claude Design (légitimes, pas des anomalies)

- **A1 — 11 cartes pour 7 pipelines** : les pipelines à deux métriques sont éclatés en 2 cartes (Artistes, Sets, Genres, Crawl). Latitude accordée par le prompt (« carte à deux métriques OU deux cartes — tranche »). Justifié par l'état booléen « à jour » (net seulement sur une métrique unique).
- **A8 — badge onglet = somme des compteurs actionnables** portés par l'onglet (Sets 659 = 501+158…). Aperçu et Monitoring sans badge.
- **A5 — ligne de synthèse** « N chantiers sur 11 ont du travail en attente » + horodatage snapshot + bouton Actualiser.
- **A10 — barre d'onglets en scroll horizontal ancré** (jamais de wrap) ; **A11 — palier mobile unique 859px** (le 639px de l'ex-bloc « Lier » devient un cas interne toléré).

## Conformité (Phase 2)

✅ Toutes les décisions figées (fiche §7) respectées · aucune donnée inventée hors `/api/admin/backlog` · coexistence Aperçu/Monitoring (Monitoring intact) · métrique actionnable `never+due` · état 0 élégant · pas de reskin · 859px · zéro composant transverse. **Verdict : GO.**

## Câblage des actions rapides — TRANCHÉ (William, 2026-08-06) : renvoi pour les deux

Le BRIEF suppose une action rapide par carte ; deux d'entre elles n'ont pas de déclencheur back sain. **Décision : les deux cartes = boutons NEUTRES de renvoi vers l'onglet, aucun job lancé depuis l'Aperçu.** Le Lot 0 back reste donc purement lecture (`GET /api/admin/backlog`), aucune dette absorbée.

1. **Carte Genres « Tracks non classées »** → bouton neutre `Voir les mappings` / renvoi **onglet Genres**. On NE wire PAS `POST /admin/genres/auto-classify` (CASSÉ : kwarg `genre_only` inexistant → TypeError silencieux, reliquat roadmap depuis 2026-06-23) — il reste un reliquat traité à part.
2. **Carte Deezer « Tracks à enrichir »** → bouton neutre de renvoi **onglet Monitoring** (déjà le lien secondaire du BRIEF ; enrich Deezer = passe de nuit unique, rien à déclencher à la main).

> Conséquence sur A6 : ces 2 cartes n'ont jamais de bouton accent, même en régime backlog (elles sont des renvois, pas des lanceurs de job). Les cartes à job réel gardent l'accent (Beatport, Artistes à lier, Sans pochette, Sets à recrawler).

Autres notes back (Lot 0 `GET /api/admin/backlog`) :
- `crawl.dlq` = taille de la clé **Redis** `dead_letter` (l'endpoint touche Redis, pas que la DB).
- `crawl.playlists_due` = sous-ensemble « dues » de `watched_entities` selon la cadence `crawl_radar` (calcul non trivial).
- `genres.unclassified` = réutiliser la logique de `GET /genres/unclassified-count` (existe).
- Enrich (`beatport`/`deezer`) = `count_enrich_backlog` (pending = `never_tried + due_retry`).

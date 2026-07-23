# Handoff — Hub / accueil (`/`) · Refonte D6

Provenance et registre du handoff design de la page **Hub**. Chantier piloté via `/refonte_page hub`.

## Contenu

| Fichier | Rôle |
|---|---|
| `BRIEF-hub.md` | Handoff de la page (top bar, hero, search + Essaie, 3 étagères top 9, carte album dépliable, double public invité/connecté, état résultats poli, états, responsive, tokens). Décisions DA H1–H10. |
| `BRIEF-composants-hub.md` | Spec du **nouveau composant partagé `<DiscoveryCard>`** (carte de découverte horizontale, 5 variantes par props : tendance/reco/nouveauté/set/lien externe, méta `BPM · KEY · âge` dégradée, cohabitation `ActivityAlbumCard`). |
| `pilote/Hub (pilote).html` | Maquette interactive Claude Design (bundle autonome). Écrans : Connecté · Invité · Recherche · Rech. invité · Nuancier. Toggles thème dark/light + viewport 375. |

## Provenance

- **Produit par** : projet Claude Design (claude.ai), à partir de `docs/refonte-ui/prompts/PROMPT-claude-design-hub.md`.
- **Livré** : 2026-07-23, archive ZIP unique (`livraison-hub/`), UTF-8 propre (aucune réparation d'encodage nécessaire).
- **Source de vérité produit** : `docs/refonte-ui/hub.md` (fiche figée) + `docs/refonte-ui/TRANSVERSE.md`. En cas de divergence, la fiche prime sur le brief.
- **Captures de la page ACTUELLE** ayant servi au prompt : `C:\tmp\captures-hub\01..05-current-*.png` (connecté dark/light/mobile, invité, résultats).

## Décisions DA notables (issues du handoff, ne contredisent pas la fiche)

- **H1** — Carte de découverte **horizontale** (cover 64 px + corps 3 lignes), grille `3 → 2 → 1` col. Choisie pour cohabiter avec la carte album dépliable dans la même grille. Nommée **`<DiscoveryCard>`** (≠ `TrackCard`, le composant ligne dense existant).
- **H3** — Âge affiché en **token brut** (`6 j` / `2 sem` / `3 mois`), sans le préfixe « Sorti il y a… » (compacité de la ligne méta). Le préfixe verbeux reste pour les contextes larges.
- **H5** — Indicateur in-lib affiché **seulement sur « Pour toi »** (seul endpoint renvoyant `in_lib`) — pas de faux indicateur ailleurs.
- **H7** — « Voir plus » de Nouveautés = **désactivé « Bientôt »** (arbitrage William Phase 0), les 3 en-têtes gardent la même structure.
- **Breakpoints** : la maquette **adopte la convention repo 720/640** (les seuils historiques 680/640/540 du Hub sont alignés).

## Périmètre / reliquats

- **Back** (1 seul) : `release_date` ajouté à `TrendItem` + query `list_trends` (`routers/radar.py`). Aucune migration.
- **Reporté** (hors chantier, backlog roadmap) : recap **C5** (badges *sur N sources* / genre / durée sur les cartes) — hétérogène entre étagères + back supplémentaire.
- **Reliquat désactivé** : bouton « Voir plus » de Nouveautés inerte tant que `/new-releases` (D6.d) n'existe pas.
- Badges source `DEEZER`/`TIDAL` des résultats = placeholders texte → migreront vers `<PlatformLink variant="glyph">` (chantier transverse `PlatformLink`).

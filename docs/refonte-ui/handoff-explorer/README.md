# Handoff Claude Design — Explorer (D6, page 1)

> **Provenance** : projet Claude Design (claude.ai/projects), round unique, livré le **2026-07-21**
> (dossier `handoff-explorer` déposé par William), versionné tel quel le même jour.
> Prompt d'origine : `docs/refonte-ui/prompts/PROMPT-claude-design-explorer.md`.
> Fiche de cadrage source de vérité : `docs/refonte-ui/catalog.md` (arbitrages pré-vol du 2026-07-20).

## Contenu

| Fichier | Rôle |
|---------|------|
| `BRIEF-explorer.md` | Handoff page : head (menu « + » imports), barre de filtres + chips actives + panneau inline, table CSS grid à rangée fixe `--row-h` (windowing), états de rangée/page, column-drop 4 paliers, drawer mobile. Décisions DA E1-E13 |
| `BRIEF-filtres-partages.md` | Spec AUTONOME du système de filtres (réutilisé tel quel par la future page Radar) : `<FilterBar>` `<FilterChip>` `<FilterPanel>` `<FilterDrawer>` + 8 contrôles (`SearchInput`, `RangeSlider`, `CamelotSelect`, `StyleMultiSelect`, `ArtistTypeAhead`, `SegmentedFilter`, `ToggleChip`, `SortSelect`), états, contrat consommateur |
| `pilote/Explorer (pilote).html` | Maquette interactive (format export artifact : wrapper bundler Claude Design + React via unpkg + fontes Google — nécessite le réseau pour s'ouvrir). Toggles dark/light + desktop/375 px, panneau Tweaks (scénarios filtres actifs / vierge / aucun résultat / chargement, densité), filtrage réellement appliqué aux 20 rangées démo |

## Notes de versionnage

- **Encodage** : fichiers livrés en UTF-8 propre (téléchargement direct, pas copier-coller) — aucune réparation nécessaire.
- `diggy-tokens.css` livré dans le dossier Downloads : copie de travail Claude Design — non versionné ici pour éviter une copie divergente.
- Les refs externes du pilote (unpkg React, Google Fonts) et les hex hardcodés (`#2a1215`, `#ff8a80`…) appartiennent au **wrapper bundler** de l'export (loader + overlay d'erreur), pas au design : le CSS de la page est 100 % tokens (602 `var(--…)`, vérifié au check du 2026-07-21). Écart de forme assumé : l'archive ZIP unique demandée n'a pas été produite (dossier de fichiers — transfert OK malgré tout) et le pilote n'est pas autonome hors-ligne. Les BRIEFs restent la référence d'implémentation.
- Rendu du pilote vérifié en headless le 2026-07-21 (`C:\tmp\captures-explorer\pilote-render-desktop.png`).

## Conformité (check du 2026-07-21)

Décisions figées de la fiche : toutes respectées — mode Radar intégralement absent (seul le badge #rank subsiste comme info trend), colonnes exactes Play · Track · Style · BPM · Key · Durée · Avis (aucune nouvelle, In lib → indicateur cover `<Artwork>`), **Rating absent partout**, les 10 filtres arbitrés présents (« a une cover » bien écarté), tri défaut « Récemment ajoutés », hauteur de rangée constante + en-tête sticky + pagination supprimée (windowing), imports en menu « + », libellés 100 % FR, pas d'état invité. Zéro donnée inventée hors surface cible `GET /api/catalog/` (+ sources d'options `GET /api/catalog/genres`, `GET /api/artists/?q=`). Composants existants consommés sans modification (`<Artwork>`, `<StyleTag>`) ; le système de filtres est spécifié comme famille de composants NOUVEAUX — attendu (lot 1 du chantier).

Évolutions légitimes issues du round (latitude donnée par le prompt) — **avec impact back lot 0 pour les 3 marquées ✦** :
- **E5** Durée = presets single-select (`< 3` / `3–5` / `5–8` / `> 8 min`), pas de range (latitude explicitement donnée) ;
- **E6** la recherche texte quitte le head pour devenir le 1er contrôle de la barre de filtres ; ✦ placeholder « Artiste, titre ou label… » → le `search` back (aujourd'hui titre + artiste) s'étend au label ;
- ✦ **Avis** gagne une 4ᵉ option « Sans avis » (le « neutre » de la fiche devient filtrable : `avis` back doit accepter l'absence d'avis, aujourd'hui `liked|disliked` seulement) ;
- ✦ **Artiste = multi-sélection** (chips × N dans le type-ahead) → le filtre back accepte plusieurs ids ;
- **E1/E2** panneau inline (pousse la table) + chips actives toujours visibles = représentation canonique de l'état URL ;
- **E4** Key = grille Camelot 12×2 (A mineures / B majeures, adjacence harmonique) — pas de roue ;
- **E12** colonne Style = 1 `StyleTag` + « +N » (jamais d'empilement — garantit la hauteur de rangée constante) ;
- Column-drop redéfini en 4 paliers (1000 / 860 / 700 / 640) au lieu de ~8 ;
- **Reliquat assumé** : < 640 px le tri est masqué en v1 (ordre par défaut) — « le tri vit dans le drawer à terme » (inscrit aux reliquats ROADMAP) ;
- Bornes statiques des sliders : BPM 60–200, Année 1985–2026 (choix design, pas des données serveur).

Ces fichiers sont la référence d'implémentation du chantier ; en cas de contradiction, la fiche `catalog.md` prime.

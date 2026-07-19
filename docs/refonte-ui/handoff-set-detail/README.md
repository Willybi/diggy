# Handoff Claude Design — Set Detail (D4, page 3)

> **Provenance** : projet Claude Design (claude.ai/projects), round unique, livré le **2026-07-17**
> en archive zip (`handoff-set-detail`), versionné tel quel le même jour.
> Prompt d'origine : `docs/refonte-ui/prompts/PROMPT-claude-design-set-detail.md`.
> Fiche de cadrage source de vérité : `docs/refonte-ui/set-detail.md` (§7 arbitrages pré-vol, §8 décisions handoff).

## Contenu

| Fichier | Rôle |
|---------|------|
| `BRIEF-set-detail.md` | Handoff page : hero immersif (fond flouté S1), tracklist enrichie, sets similaires, états, responsive. Décisions DA S1-S10 |
| `BRIEF-trackcard-extension-set.md` | Spec extension ADDITIVE `<TrackCard>` ligne : `position` + `timecode {ms, href?}` + `state ('id'/'unresolved')` — zéro régression Track/Playlist Detail |
| `SPEC-set-card.md` | Spec `<SetCard>` réutilisable (1ʳᵉ conso : Sets similaires ; future : refonte liste `/sets`) — slot `#footer` d'extension |
| `pilote/Set Detail (pilote).html` | Maquette interactive autonome (format export `.dc.html` : wrapper bundler Claude Design + React inline). Toggles dark/light + desktop/375 px, panneau Tweaks (états), nuanciers en bas |

## Notes de versionnage

- **Encodage** : fichiers livrés en UTF-8 propre (zip, pas copier-coller) — aucune réparation nécessaire.
- `diggy-tokens.css` livré dans le zip = **byte-identique** au repo (`server/frontend/src/styles/diggy-tokens.css`) — non versionné ici pour éviter une copie divergente.
- Le pilote contient des références unpkg/React et 4 hex hardcodés : ils appartiennent au **wrapper bundler** de l'export Claude Design (manifest + overlay d'erreur du loader), pas au design de la page — le CSS de la page est 100 % tokens.
- Le brief mentionne `Set Detail (pilote).dc.html` ; le fichier livré s'appelle `Set Detail (pilote).html` — même artefact.

## Conformité (check du 2026-07-17)

Décisions figées de la fiche : toutes respectées. Zéro donnée inventée hors contrats `GET /api/sets/{id}` (+ champs ✦ lot back) et `GET /api/sets/{id}/similar`. Compat composants vérifiée : `Artwork` a déjà `size 'hero'/'card'`, `ScoreRing mode="pct"` = extension à créer (lot 1), `dv-back` = pattern existant (Track/Playlist Detail).

Évolutions légitimes issues du round (latitude donnée par le prompt) :
- **S1** fond flouté retenu (opacité 0.22 light / 0.50 dark, pas de scrim) ;
- **S3** StatStrip supprimée, stats en data-row dans le hero (aligné Track/Playlist Detail) ;
- **S4** ring % identifiées = **`<ScoreRing mode="pct">`** (1ʳᵉ migration de la géométrie % — `RingPct` reste en prod ailleurs) ;
- **S5** séparateur « b2b » générique dès N ≥ 2 artistes (le `role` d'import, peu fiable, n'est plus affiché) ;
- **S6** genres déduits **sans %** (le `pct` du contrat sert au tri d'agrégation) ;
- **S8** tracklist = **extension additive de `<TrackCard>`** (pas de rangée bespoke) ;
- **S9** responsive < 640 px **re-tranché** : le timecode RESTE, BPM + durée tombent (inverse de l'actuel) ;
- **S10** score de proximité **non affiché** (tri seul) — le slot `#footer` de `<SetCard>` garde la porte ouverte.

Ces fichiers sont la référence d'implémentation du chantier ; en cas de contradiction, la fiche `set-detail.md` prime.

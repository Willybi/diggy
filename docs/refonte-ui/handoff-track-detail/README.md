# Handoff Design — Track Detail (refonte D4, page 1)

> Produit par le projet **Claude Design** (claude.ai) le 2026-07-17, après un round 2 de retours William.
> Prompt d'origine : `docs/refonte-ui/prompts/PROMPT-claude-design-track-detail.md`.
> Cadrage produit source : `docs/refonte-ui/track-detail.md` (fiche mise à jour avec les décisions du round 2) + `docs/refonte-ui/TRANSVERSE.md`.

## Contenu

| Fichier | Rôle |
|---|---|
| `BRIEF-track-detail.md` | Handoff de la page : ordre vertical, hero, Découverte, « Où on l'entend », états, responsive, décisions DA D1-D6 |
| `BRIEF-composants-transverses.md` | Spec réutilisable des 4 composants partagés : `<Artwork>`, `<TrackCard>` ligne, `<ScoreRing>`, `<PlatformLink>` |
| `Track Detail (pilote).html` | Maquette interactive (à déposer ici par William — fichier lourd, toggles thème/viewport + panneau Tweaks + nuancier) |

## Notes d'implémentation

- **Logos plateformes** : les SVG officiels ne sont pas encore fournis — l'implémentation embarque les tracés simplifiés de la maquette comme **placeholders temporaires**, centralisés dans la map `platform → path` de `PlatformLink.vue` (`TODO logos officiels`). Remplacement futur = ce seul fichier.
- **Lien retour** : libellé « Catalog » et route actuelle tant que la refonte Explorer n'est pas implémentée.
- Front only : zéro backend, zéro migration (toutes les données sortent de `GET /api/catalog/{id}` + `/similar`).

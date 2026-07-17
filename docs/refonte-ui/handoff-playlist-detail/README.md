# Handoff Design — Playlist Detail (refonte D4, page 2)

> Produit par le projet **Claude Design** (claude.ai) le 2026-07-17 (livraison zip, rounds William).
> Prompt d'origine : `docs/refonte-ui/prompts/PROMPT-claude-design-playlist-detail.md`.
> Cadrage produit source : `docs/refonte-ui/playlist-detail.md` (fiche + arbitrages pré-vol du 2026-07-17 : lot 0 back complet, extension TrackCard) + `docs/refonte-ui/TRANSVERSE.md`.

## Contenu

| Fichier | Rôle |
|---|---|
| `BRIEF-playlist-detail.md` | Handoff de la page : ordre vertical, hero cover+infos, bannière crawl, « Dans cette playlist », tracks détectées, états, responsive, décisions DA P1-P9 |
| `BRIEF-trackcard-extension.md` | Spec de l'extension ADDITIVE du `<TrackCard>` ligne : `showDuration` + `artists[]` cliquables (zéro changement pour les consommateurs actuels) |
| `pilote/Playlist Detail (pilote).dc.html` | Maquette interactive — format workspace Claude Design : dépend de `pilote/support.js` + `pilote/_ds/` (ouvrir le .dc.html tel quel, les 3 doivent rester ensemble) |

## Notes d'implémentation

- **Lot 0 back requis AVANT le front** (arbitrage 2026-07-17, voir fiche §6) : `top_artists[]`, `top_genres[]`, `in_lib`, `artists[]` peuplés dans `GET /api/watchlist/{id}` — les champs marqués ✦ dans les briefs.
- **Extension TrackCard = lot dédié** avec tests Vitest + vitrine DesignSystemView, contrainte « bit-à-bit identique sans les nouvelles props » (Track Detail est en prod dessus).
- **AdminCard** : composant existant inchangé (gate `is_admin` déjà intégré), simplement déplacé en bas de page.
- **Logos plateformes** : toujours les tracés placeholders de `PlatformLink.vue` (reliquat roadmap inchangé — `TODO logos officiels`).
- Tous les tokens cités par les briefs vérifiés existants dans `diggy-tokens.css` (2026-07-17) : `--accent-soft-2`, `--ct-line`, `--touch-min`, `--fs-label`, `--fs-nano`, `--accent-wash`, hues familles, etc.

## Évolutions issues des rounds (légitimes, actées dans la fiche)

- **StatStrip supprimée** : Tracks · Dernier crawl intégrés au hero en data-row mono (même patron que Track Detail round 2) ; « Ajoutée le » retiré.
- **Micro-label `SOURCE` + nom de plateforme** en texte à côté du `<PlatformLink>` (lève l'ambiguïté du carré logo seul).
- **« Dans cette playlist » = une seule carte 2 colonnes** (top 6 artistes | top 5 genres), avatars fallback initiales sur `--accent-soft`.
- **État vide « jamais crawlée »** spécifié (carte engageante + bannière crawl possiblement active au-dessus).
- **Titre absent → `external_id` rendu mono** (dit honnêtement « identifiant technique »).
- **Durée = 5ᵉ colonne TrackCard** (grille `36px 1fr 42px 30px 44px [auto]`), masquée < 640 px.

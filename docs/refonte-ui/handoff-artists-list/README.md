# Handoff — Artistes (liste) `/artists` (D6 p.6)

Provenance et périmètre du handoff Claude Design pour la refonte de la **liste Artistes**.

## Fichiers

| Fichier | Où | Rôle |
|---|---|---|
| `BRIEF-artists-list.md` | **ici** (versionné) | Handoff design : anatomie card, pastille-toggle « Suivi », head, grille responsive, empty states, tokens |
| `Artistes (pilote).html` | `Downloads/livraison-artists-list/` (non versionné — lourd, 322 Ko) | Maquette interactive (15 cards démo, toggles thème/viewport, panneau Tweaks : `pastilleSuivi` visible/hover, `grilleMobile` 2/1 col) |

## Provenance

- **Prompt envoyé** : `docs/refonte-ui/prompts/PROMPT-claude-design-artists-list.md` (+ pièces : `diggy-tokens.css`, fiche `artists-list.md`, `TRANSVERSE.md`, `BRIEF-playlists-list.md` en format-ref, 3 captures actuelles).
- **Livré le** : 2026-07-27. Round unique (pas d'aller-retour signalé).
- **Encodage** : UTF-8 vérifié propre (0 mojibake). Pilote auto-suffisant (zéro ressource externe → CSP-safe).

## Check de conformité Phase 2 — PASS

- **Décisions figées respectées** : card gardée · badge rating retiré · badge in-lib overlay retiré (stat In Lib gardée) · pastille-toggle « Suivi » coin haut-gauche (état + follow/unfollow) · 2 stats + avis (nb_liked NON ajouté, reporté) · SegFilter « Rating »→« Suivis » · toggle « sans Deezer » · FamilyChips gardés · play hover gardé · infinite scroll · clic card → `/artist/:id` · FR, pas d'invité.
- **Aucune donnée inventée hors API** : champs = `id/name/has_artwork/nb_catalog/nb_lib/following/genres[]/top_track_artworks[]/tracks_with_artwork` ; params = `sort(catalog|lib|liked|disliked|alpha)/followed/family/q/no_deezer`. `avg_rating` retiré, `nb_liked` reporté. Le brief liste explicitement ce qui **n'existe pas** au niveau card (bpm/key/durée/%).
- **Aucun token inventé** : le `diggy-tokens.css` livré déclare le même jeu que le repo (diff vide) ; tous les tokens exotiques cités (`--overlay-soft`, `--hero-scrim-l/c/h`, `--genre-tile-ink/border-dark`, `--accent-soft-2`, `--pos-ink`…) existent en prod.

## Évolutions légitimes issues de la latitude DA (pas des anomalies)

- **A1 — pastille « toujours présente », opacité 0,5→1 au survol** (pas hover-only) : tranche la latitude que le prompt laissait ouverte ; un contrôle qui affiche un état ne peut pas être masqué. Cohérent avec la note données (non-suivi discret mais découvrable).
- **A2 — icône cloche** (pas étoile = ex-rating, pas « personne+ » = confusion in-lib) : sémantique veille/nouveautés, disjointe du cœur d'avis.
- **A5 — coin haut-droit laissé vide** après retrait du badge rating.
- **A8 — valeur In Lib en `--pos-ink` quand > 0** : petite addition, porte seule l'info de l'ex-badge overlay retiré.
- **A10 — toggle « sans Deezer » dans la rangée FamilyChips** (pas le head), en interrupteur (pas une chip).
- **A12/A13 — grille jamais 1 colonne (2 min) + container query par card (seuil 190 px)** : diverge du code actuel (qui passait à 1 col < 380 px) ; argument = préserver le mode « scanner beaucoup d'artistes ». `container-type: inline-size` sur la card.
- **A7 — scrim allégé + radial central** : raffinement de l'anatomie gardée (avatar mieux détaché, covers plus lisibles).

## Reliquat assumé

- **nb_liked en 3e stat** : reporté en backlog (données quasi-nulles, 39 artistes). → table Reliquats de `docs/ROADMAP.md`.

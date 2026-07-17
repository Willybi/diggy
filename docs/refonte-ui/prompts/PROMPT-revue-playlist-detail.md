# Prompt — Claude Design · Revue post-implémentation Playlist Detail (round UNIQUE)

> Envoyer au projet Claude Design avec les captures listées en bas.
> Round unique et timeboxé : un seul aller-retour, livrable unique.

---

## Contexte

La refonte **Playlist Detail** (`/playlists/:id`) que tu as spécifiée est **implémentée et déployée en prod** (commit `ef8505f`). Ton rôle : vérifier la conformité de l'implémentation à **TES briefs** — et uniquement à eux :

- `BRIEF-playlist-detail.md` (décisions DA P1-P9, états, responsive)
- `BRIEF-trackcard-extension.md` (extension durée + artistes cliquables)

## Périmètre — ce que tu juges

**Canal visuel (captures jointes)** : fidélité de la mise en forme au brief et à la maquette pilote — hiérarchie, espacements, tokens, états, les deux thèmes, mobile.

**Canal code (fichiers exacts, sur GitHub)** :
- https://github.com/Willybi/diggy/blob/master/server/frontend/src/views/PlaylistDetailView.vue
- https://github.com/Willybi/diggy/blob/master/server/frontend/src/components/TrackCard.vue (uniquement l'extension : colonne durée + artistes cliquables)

Compare aux valeurs de TES briefs : tokens utilisés, tailles, grilles, seuils responsive, libellés français.

## Périmètre — ce que tu NE juges PAS

- **Interdiction de commenter l'architecture JS, les patterns Vue, les tests, le state management** — hors de ton mandat.
- **Les logos plateformes placeholders** (`PlatformLink.vue`) : reliquat assumé et documenté (les SVG officiels arriveront plus tard) — pas un écart.
- **Les composants transverses existants** (`Artwork`, `PlatformLink`, `ScoreRing`, `AdminCard`, `StyleTag`) : leur design est acté par les handoffs précédents — seul leur USAGE sur cette page est jugeable.
- **Convention repo vs pilote** : les breakpoints s'écrivent `@container (max-width: 720px/640px)` (exclusif) — c'est la convention du repo, elle PRIME sur toute variante du pilote. Pas un écart.
- Le bloc AdminCard était explicitement hors périmètre design.

## Livrable — `FIX-playlist-detail.md` (unique)

Un tableau d'écarts, chacun tagué :
- **[visuel]** — constaté sur capture (préciser LAQUELLE)
- **[spec]** — constaté dans le code (préciser fichier + valeur)

Colonnes : `#` · Tag · Où (capture/fichier) · **Constaté** (valeur exacte) · **Attendu** (valeur du brief, avec référence P1-P9 ou section) · Sévérité (bloquant / mineur / cosmétique).

Pas de refonte de tes propres décisions : si tu changerais un choix de TON brief aujourd'hui, note-le en « suggestion hors FIX » séparée, ce n'est pas un écart d'implémentation.

## Captures jointes (référence pour ta lecture)

| # | Capture | Contenu |
|---|---------|---------|
| 1 | desktop-dark-full | Page complète, playlist riche (artwork + description + insights + tracks), dark |
| 2 | desktop-light-full | La même, light |
| 3 | desktop-dark-hero | Zoom hero : cover 216px, stats, PlatformLink + label SOURCE |
| 4 | desktop-dark-insights | Zoom « Dans cette playlist » : avatars/initiales + counts, barres genres + % |
| 5 | desktop-dark-hover | Rangée track survolée (play visible) |
| 6 | desktop-dark-playing | Rangée en lecture (tint accent + pause) |
| 7 | desktop-dark-empty | Playlist jamais crawlée : état vide + stat « jamais » |
| 8 | desktop-dark-noartwork | Hero avec placeholder rayé (pas d'artwork) |
| 9 | mobile-375-dark | Page complète 375px : hero empilé (cover 160), insights 1 col, tracks sans durée |
| 10 | mobile-375-light | La même, light |
| 11 | (si disponible) desktop-dark-crawl | Bannière crawl running (dot pulsant) |

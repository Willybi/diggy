# Prompt — Claude Design · Revue post-implémentation Set Detail (round UNIQUE)

> Envoyer au projet Claude Design avec les captures listées en bas.
> Round unique et timeboxé : un seul aller-retour, livrable unique.

---

## Contexte

La refonte **Set Detail** (`/set/:id`) que tu as spécifiée est **implémentée et déployée en prod** (commit `41e9315`). Ton rôle : vérifier la conformité de l'implémentation à **TES briefs** — et uniquement à eux :

- `BRIEF-set-detail.md` (décisions DA S1-S10, hero, tracklist, similaires, états, responsive)
- `BRIEF-trackcard-extension-set.md` (extension position + timecode + états id/unresolved)
- `SPEC-set-card.md` (carte set réutilisable)

## Périmètre — ce que tu juges

**Canal visuel (captures jointes)** : fidélité de la mise en forme au brief et à la maquette pilote — hero immersif (backdrop flouté aux deux opacités), hiérarchie, espacements, tokens, états de rangée, les deux thèmes, mobile.

**Canal code (fichiers exacts, sur GitHub)** :
- https://github.com/Willybi/diggy/blob/master/server/frontend/src/views/SetDetailView.vue
- https://github.com/Willybi/diggy/blob/master/server/frontend/src/components/TrackCard.vue (UNIQUEMENT l'extension set : position, timecode, states — la base et l'extension durée/artistes sont actées par les handoffs précédents)
- https://github.com/Willybi/diggy/blob/master/server/frontend/src/components/ScoreRing.vue (UNIQUEMENT le mode `pct`)
- https://github.com/Willybi/diggy/blob/master/server/frontend/src/components/SetCard.vue

Compare aux valeurs de TES briefs : tokens utilisés, tailles (216/160 px, colonnes 28/58 px…), grilles (4/3/2), seuils responsive, opacités backdrop (0.22/0.50) et placeholder ID (0.55), libellés français, espace fine insécable des %.

## Périmètre — ce que tu NE juges PAS

- **Interdiction de commenter l'architecture JS, les patterns Vue, les tests, le state management, le backend** — hors de ton mandat.
- **Les logos plateformes placeholders** (`PlatformLink.vue`) : reliquat assumé et documenté — pas un écart.
- **Les composants transverses préexistants** (`Artwork`, `PlatformLink`, `StyleTag`, `AdminCard`, base de `TrackCard`/`ScoreRing`) : design acté par les handoffs précédents — seul leur USAGE sur cette page est jugeable.
- **Convention repo vs pilote** : les breakpoints s'écrivent `@container (max-width: 720px/640px)` **sans nom de container** (exclusif) — convention du repo, elle PRIME sur toute variante du pilote. Pas un écart.
- **La latence de la section « Sets similaires »** (elle peut mettre plusieurs secondes à apparaître) : sujet backend traité séparément — pas un écart design.
- Le bloc AdminCard était explicitement hors périmètre design.
- La grille CSS de `TrackCard` est implémentée en « colonnes composables » (custom properties opt-in) plutôt qu'en classes énumérées : équivalence technique validée, seul le RENDU (largeurs effectives 28/36/42/30/44/58) est jugeable.

## Livrable — `FIX-set-detail.md` (unique)

Un tableau d'écarts, chacun tagué :
- **[visuel]** — constaté sur capture (préciser LAQUELLE)
- **[spec]** — constaté dans le code (préciser fichier + valeur)

Colonnes : `#` · Tag · Où (capture/fichier) · **Constaté** (valeur exacte) · **Attendu** (valeur du brief, avec référence S1-S10 ou section) · Sévérité (bloquant / mineur / cosmétique).

Pas de refonte de tes propres décisions : si tu changerais un choix de TON brief aujourd'hui, note-le en « suggestion hors FIX » séparée, ce n'est pas un écart d'implémentation.

## Captures jointes (référence pour ta lecture)

| # | Capture | Contenu |
|---|---------|---------|
| 1 | desktop-dark-full | Page complète, set bien identifié (ex. `/set/6892`) : hero flouté + genres + ring %, tracklist, similaires — dark |
| 2 | desktop-light-full | La même, light (backdrop à 0.22) |
| 3 | desktop-dark-hero | Zoom hero : cover 216, artistes/b2b si dispo, StyleTags, data-row stats + ring % avec fraction, PlatformLink + label SOURCE |
| 4 | desktop-dark-tracklist | Zoom tracklist : rangée identifiée complète (BPM·KEY·durée·timecode) + rangée « ID / non identifié » en retrait |
| 5 | desktop-dark-hover | Rangée identifiée survolée (play visible) |
| 6 | desktop-dark-playing | Rangée en lecture (tint accent + pause) |
| 7 | desktop-dark-timecode | Un set YouTube/SoundCloud : timecodes en lien (voix `--ink-2`) vs un set TrackID : timecodes texte (`--ink-3`) |
| 8 | desktop-dark-similar | Zoom « Sets similaires » : grille 4 colonnes de SetCard (méta à nulls omis si dispo) |
| 9 | desktop-dark-noartwork | Hero sans artwork : bande `--surface` nue (pas de faux décor), placeholder rayé |
| 10 | desktop-dark-empty | Set 0 identifiée : pas de StyleTags, ring 0 %, pas de section similaires |
| 11 | mobile-375-dark | Page complète 375 px : hero empilé (cover 160), tracklist timecode conservé / BPM+durée masqués, similaires 2 colonnes |
| 12 | mobile-375-light | La même, light |
| 13 | (si disponible) design-system | Vitrines : TrackCard set (5 états), ScoreRing % (0/69/100 sm+md), SetCard (4 variantes) |

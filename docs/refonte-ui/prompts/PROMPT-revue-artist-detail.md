# Prompt — Claude Design · Revue post-implémentation Artist Detail (round UNIQUE)

> Envoyer au projet Claude Design avec les captures listées en bas.
> Round unique et timeboxé : un seul aller-retour, livrable unique.

---

## Contexte

La refonte **Artist Detail** (`/artist/:id`) que tu as spécifiée est **implémentée et déployée en prod** (commits `cb88318` + fix alignement `c81b7e3`). Ton rôle : vérifier la conformité de l'implémentation à **TON brief** — et uniquement à lui :

- `BRIEF-artist-detail.md` (décisions DA A1-A9, hero-bannière, aliases, tracks, sets, artistes proches, états, responsive)

La page ne crée AUCUN composant : elle consomme `<Artwork>`, `<TrackCard>` ligne, `<PlatformLink>`, `<SetCard>`, `<ShelfCard>`, `<ExpandableShelf>`, `<StyleTag>` — tous actés par les handoffs précédents.

## Périmètre — ce que tu juges

**Canal visuel (captures jointes)** : fidélité de la mise en forme au brief et à la maquette pilote — hero-bannière (montage cyclé, scrim, nom sur l'axe du contenu, avatar débordant ring 3 px), stats repliées, hiérarchie, espacements, tokens, grille de SetCard + footer badge %, shelf artistes proches, les deux thèmes, mobile.

**Canal code (fichier exact, sur GitHub)** :
- https://github.com/Willybi/diggy/blob/master/server/frontend/src/views/ArtistDetailView.vue

Compare aux valeurs de TON brief : tokens utilisés, tailles (banner 216/150 px, avatar 120/72 px, ring 3 px `--surface`, débord −60 px, nom `--fs-xl`→`--fs-lg`, axe nom = `calc(--space-6 + 120px + --space-5)`), scrim (0.72 → transparent 62 %), grilles (Sets 4/3/2, proches `minmax(96px, 1fr)`), seuils responsive, libellés français (« Afficher les N autres tracks », « … et N autres tracks au catalog », « identifiées »), espace fine insécable avant %, labels stats mono uppercase.

## Périmètre — ce que tu NE juges PAS

- **Interdiction de commenter l'architecture JS, les patterns Vue, les tests, le state management, le backend** — hors de ton mandat.
- **Les logos plateformes placeholders** (`PlatformLink.vue`) : reliquat assumé et documenté — pas un écart.
- **Les composants transverses préexistants** (`Artwork`, `TrackCard`, `SetCard`, `ShelfCard`, `ExpandableShelf`, `PlatformLink`, `StyleTag`, `AdminCard`) : design acté par les handoffs précédents — seul leur USAGE sur cette page est jugeable. La page les consomme SANS les modifier (contrainte dure du chantier) : un polish local passe par override scopé, c'est le mécanisme prévu.
- **Convention repo vs pilote** : les breakpoints s'écrivent `@container (max-width: 720px/640px)` **sans nom de container** (exclusif) — convention du repo, elle PRIME sur toute variante du pilote. Pas un écart.
- Le bloc **AdminCard** était explicitement hors périmètre design.
- **Arbitrages d'implémentation actés** (documentés au chantier — pas des écarts) :
  1. **Avatar < 640 px** : « en flux sous le banner » implémenté SANS débord (l'avatar descend sous le banner, `margin-top` positif) pour éviter la collision avec le nom calé à gauche — si tu constates un rendu meilleur avec débord conservé, tague-le écart **mineur** avec ta valeur cible, il sera arbitré.
  2. **Logo Deezer masqué** quand `deezer_id` est la sentinelle interne `NOT_FOUND` (un lien cassé n'est pas un « Voir sur Deezer » légitime).
  3. **En-tête « Artistes proches »** : rendu par le composant `ExpandableShelf` préexistant (compteur en pastille), pas par l'en-tête `sec-head` des autres sections — composant inchangeable.
- **La donnée elle-même** (artiste sans avatar, montage pauvre, sets sans artwork, aliases absents) : tu juges le TRAITEMENT du cas, pas la donnée.

## Livrable — `FIX-artist-detail.md` (unique)

Un tableau d'écarts, chacun tagué :
- **[visuel]** — constaté sur capture (préciser LAQUELLE)
- **[spec]** — constaté dans le code (préciser fichier + valeur)

Colonnes : `#` · Tag · Où (capture/fichier) · **Constaté** (valeur exacte) · **Attendu** (valeur du brief, avec référence A1-A9 ou section) · Sévérité (bloquant / mineur / cosmétique).

Pas de refonte de tes propres décisions : si tu changerais un choix de TON brief aujourd'hui, note-le en « suggestion hors FIX » séparée, ce n'est pas un écart d'implémentation.

## Captures jointes (référence pour ta lecture)

| # | Capture | Contenu |
|---|---------|---------|
| 1 | desktop-dark-full | Page complète, artiste riche (ex. `/artist/27` Fred again..) : hero complet, tracks, sets, proches — dark |
| 2 | desktop-light-full | La même, light (lisibilité du nom sur le scrim, ring avatar) |
| 3 | desktop-dark-hero | Zoom hero : montage 6×2, scrim, nom SUR l'axe du contenu, avatar débordant ring 3 px, StyleTags, actions (accent + Suivre + 2 logos), stats CATALOG · IN LIB · SETS (sans Rating) |
| 4 | desktop-dark-tracks | Zoom Tracks : rangées TrackCard (cover+pastille, artistes, BPM·KEY·durée), bouton « Afficher les N autres tracks », note « … et N autres tracks au catalog » |
| 5 | desktop-dark-sets | Zoom Sets : grille 4 colonnes de SetCard, artistes joints « , », méta date · durée · N tracks, footer badge « NN % identifiées » aligné entre cartes |
| 6 | desktop-dark-proches | Zoom Artistes proches : shelf ronds avatar+nom (aperçu 12), rien d'autre |
| 7 | desktop-dark-playing | Rangée track en lecture (tint accent + pause) |
| 8 | desktop-dark-poor | Artiste pauvre : banner placeholder rayé sous scrim (0 cover) OU tuiles cyclées (peu de covers), avatar initiale |
| 9 | desktop-dark-suivi | État « Suivi » du bouton follow (ghost-accent) |
| 10 | mobile-375-dark | Page complète 375 px : banner 150, nom à gauche, avatar 72 en flux, durée masquée dans les tracks, Sets 2 colonnes |
| 11 | mobile-375-light | La même, light |
| 12 | (si dispo) aliases | Un artiste avec aliases : ligne ALIAS · noms joints « · » |

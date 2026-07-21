# Décisions & chantiers transverses — refonte UI

> Sujets qui débordent d'une seule page : DA/brand, système d'icônes, composants
> partagés, navigation, principes UX globaux. On les décide **une fois** ici, on les
> applique partout. Souvent repérés au fil d'une page (le Hub d'abord) mais à **ne pas**
> traiter page par page.

## Brand / DA globale
- **Logo Diggy** — vrai logo, sujet **long terme** de direction artistique (hors périmètre d'une page). À exposer en composant `<BrandLogo>` réutilisé partout : top bar, hero, login, favicon, écrans de chargement, icône PWA. D'ici là, le glyph « D » actuel reste en place. Statut : 🔲 long terme.
- Palette / tokens : déjà centralisés (`diggy-tokens.css`), zéro couleur hardcodée — acquis.

## Système d'icônes
- Set **SVG unifié**, lisible jusqu'à ~13px, couvrant : scopes de recherche, badges de type de résultat, actions récurrentes. Fin des emoji (`⊕ ♫ ● ◎ ☰ ◆`). Sujet design global. Statut : 🔲.

## Composants de découverte mutualisés (reco A — ✅ validé)
- `<TrackCard>` : artwork + titre + artiste + méta compacte `BPM · KEY · âge` (dégradée pour genre/artiste, sans BPM/KEY).
- `<DiscoveryShelf>` (aperçu Hub) + `<DiscoveryList>` (page pleine).
- `<ScoreRing>` : jauge circulaire + note entière /10 (float conservé pour le tri). Issu de Radar (scores Tendance / Pour toi), réutilisable pour tout score affiché. **Unifie et remplace `ScorePill`** (texte %) ; `RingPct` (proportion d'un tout) migrera vers la même géométrie en mode %.
- **Consommés par** : aperçus Hub (Ça sort / Pour toi / Nouveautés) ET les pages destinations (Radar, `/for-you`, `/new-releases`).
- **Objectif** : « une page par étagère » sans dupliquer l'UI ni la maintenance. Statut : 🟡 — spec de `<Artwork>` / `<TrackCard>` ligne / `<ScoreRing>` LIVRÉE (2026-07-17, `docs/refonte-ui/handoff-track-detail/BRIEF-composants-transverses.md`) ; 1re implémentation = chantier Track Detail ; la variante card verticale (`<DiscoveryShelf>`/`<DiscoveryList>`) reste à cadrer.
- **Extension `<TrackCard>` ligne (2026-07-17, chantier Playlist Detail)** : spec ADDITIVE livrée (`docs/refonte-ui/handoff-playlist-detail/BRIEF-trackcard-extension.md`) — `showDuration` (colonne mono m:ss, masquée < 640 px) + `artists[]` structurés cliquables (fallback chaîne plate). Contrainte dure : sans les nouvelles props, rendu bit-à-bit identique (Track Detail en prod dessus).
- **Extension `<TrackCard>` ligne « set » (2026-07-17, chantier Set Detail)** : spec ADDITIVE livrée (`docs/refonte-ui/handoff-set-detail/BRIEF-trackcard-extension-set.md`) — `position` (colonne # en tête), `timecode {ms, href?}` (colonne entre durée et slot fin ; lien si `href`, construit par la page consommatrice), `state 'id'/'unresolved'` (rangées non identifiées/non résolues, non cliquables). Responsive conditionnel : avec `timecode` fourni, < 640 px BPM tombe et le timecode reste (S9) ; sans, comportement actuel strictement inchangé. Même contrainte zéro régression.
- **`<ScoreRing mode="pct">` (2026-07-17, chantier Set Detail)** : spec additive livrée (BRIEF-set-detail.md) — `mode 'score'|'pct'`, défaut `'score'` bit-à-bit identique ; mode % = arc proportion + « N % » au centre (espace fine insécable), md recommandé. **1ʳᵉ migration de la cible « RingPct → géométrie ScoreRing »** posée plus haut ; la migration des autres usages RingPct reste un chantier ultérieur.
- **`<SetCard>` (2026-07-17, chantier Set Detail)** : NOUVEAU composant réutilisable (`docs/refonte-ui/handoff-set-detail/SPEC-set-card.md`) — carte set verticale (Artwork card, titre clamp 2, artistes, méta mono date · durée · N tracks, nulls omis), slot `#footer` d'extension (score, badges — vide par défaut). 1ʳᵉ conso : « Sets similaires » de Set Detail ; réutilisée telle quelle par la future refonte de la liste `/sets`.

## Composant Artwork + indicateur in-lib (issu du Catalog)
- `<Artwork>` (ou `<Cover>`) : gère la cover réelle **et** le placeholder rayé, avec un **indicateur in-lib optionnel** en coin : point vert plein = dans la bib / cercle pointillé vide = pas dans RB. Petit, discret, lisible même sur le placeholder.
- **Réutilisé partout** où une cover apparaît : Catalog, résultats de recherche Hub, `<TrackCard>`, pages détail, sets… → remplace la colonne « In lib » lourde par une info légère et universelle. Statut : ✅ LIVRÉ (chantier Track Detail 2026-07-17 — `Artwork.vue`, prop `inLib` optionnelle point plein/cercle pointillé ; constaté au pré-vol Explorer 2026-07-20).
- **Cards agrégées (artiste / genre / …)** : là l'in-lib est un **count** (pas un booléen) → affiché **en stat dans le body** (pas un badge overlay), cohérent sur **toutes les listes** (décidé sur Artistes + Genres ; à suivre pour Sets / Playlists).

## Système de filtres partagés (issu d'Explorer, D6)
- Mécanique de filtres complète spécifiée comme **famille de composants autonomes** : `<FilterBar>` (conteneur : recherche, bouton + badge compteur, tri, compteur live, chips) + `<FilterChip>` + `<FilterPanel>` (desktop, inline) + `<FilterDrawer>` (mobile, bottom-sheet fixed) + 8 contrôles : `SearchInput`, `RangeSlider`, `CamelotSelect` (grille 12×2), `StyleMultiSelect` (groupé par pilier, couleurs `StyleTag` préservées + ring accent), `ArtistTypeAhead` (recherche serveur), `SegmentedFilter`, `ToggleChip`, `SortSelect`.
- Principes : état = objet plat ↔ query params URL (1:1, défaut = absent) ; chips = représentation canonique toujours visible ; feedback live (compteur, debounce 250 ms) ; sélection = accent plein sauf valeurs à couleur sémantique (ring accent, hue pilier préservée).
- **Spec** : `docs/refonte-ui/handoff-explorer/BRIEF-filtres-partages.md` (contrat consommateur inclus). Consommateurs : Explorer (1re implémentation) puis **Radar** (« filtres façon Explorer », décision figée) et toute liste filtrable.
- ⚠️ Implémentation : le repo a déjà un `SegFilter.vue` (segments de listes existantes) — le `SegmentedFilter` de cette famille est un composant distinct ; nommer sans collision (ex. préfixe famille) et ne PAS modifier `SegFilter`.
- Statut : 🟡 spec livrée (2026-07-21), 1re implémentation = chantier Explorer (lot composants dédié).

## Navigation (WIP — William)
- **Vraie page Radar** dédiée **+ onglet séparé dans Catalog**. Structure encore à travailler.
- Impacte : les destinations « voir plus » (Ça sort → future page Radar), la sidebar, la BottomNav.
- Statut : 🔲 à travailler. → conditionne la cible finale du « voir plus » de « Ça sort en ce moment ».

## Boutons plateformes externes → logos (issu de Set detail)
- Tous les liens vers des plateformes tierces (**SoundCloud, YouTube, Deezer, Beatport, TrackID, 1001Tracklists, Spotify…**) affichent le **logo** de la plateforme, pas son **nom** en texte.
- → composant `<PlatformLink>` (logo + href + `aria-label`), réutilisé sur Set detail (« Voir sur… »), Artist detail (Deezer/SoundCloud/TrackID), Track detail (Beatport/Deezer), etc.
- **Variante `glyph`** (handoff Track Detail, 2026-07-17) : logo seul non cliquable (~13 px, `--ink-2`) pour marquer une **source** dans une liste dense (ex. « Détecté dans ») — remplace les badges texte DEEZER/TIDAL/SPOTIFY (`SourceBadge` à terme).
- **Monochrome `currentColor` partout** (décision D6) : jamais les couleurs de marque — l'accent mauve reste le seul signal coloré.
- Contrainte CSP : logos en **SVG inline / data-URI** (pas de CDN). **Logos temporaires** : tracés simplifiés de la maquette, centralisés dans la map `platform → path` de `PlatformLink.vue` (`TODO logos officiels` — remplacement = un seul fichier). Statut : 🟡 spec livrée (`docs/refonte-ui/handoff-track-detail/BRIEF-composants-transverses.md`), 1re implémentation = chantier Track Detail.

## Rating (étoiles Rekordbox) — à SUPPRIMER du projet
- **Décision** : le rating vient de l'import XML Rekordbox (`rekordbox_xml.py`) = étoiles que l'utilisateur met dans **son** Rekordbox, interprétation 100 % personnelle → **aucune valeur partagée**. Retiré de **tout** le projet (colonne, API, UI, agrégat artiste).
- **Surfaces à nettoyer** (inventaire) :
  - **Front** : `CatalogView` (colonne), `TrackDetailView`, `ArtistsView`, `ArtistDetailView`, `components/ArtistCard.vue` (rating agrégé par artiste) + `__tests__/views/ArtistDetailView.test.js`.
  - **Back** : `models/catalog.py`, `schemas/catalog.py` + `schemas/artist.py` + `schemas/tracks.py`, `routers/catalog.py` + `routers/artists.py`, `services/catalog_service.py` + `services/artist_service.py`, `services/rekordbox_xml.py` (arrêter l'import) + drop colonne (migration, à terme).
- Statut : 🔲 chantier transverse (feature-first, le back suit).

## Principes UX globaux
- **État vide maîtrisé** (reco C — ✅ validé) : hiérarchie verticale claire, pas d'empilement d'accueil. Recherche en priorité, puis découverte. (1re application : retrait du bloc Genres populaires du Hub.)
- **Parcours invité = funnel de conversion voulu** (reco D — ✅ validé) : montrer **librement** le contenu (trends, aperçus), et **gater** le « voir plus » / les actions profondes derrière le login. Quand l'invité est accroché et veut aller plus loin → on l'amène à se connecter (Google). Ce n'est pas un manque, c'est le design.
  - **L'invité est confiné au Hub** (+ `/login`) : toute autre page exige l'auth (`router.beforeEach` redirige vers `/`). → **aucun état invité à concevoir sur les pages internes** (Explorer, Radar, détails…) ; seul le Hub gère le double état invité/connecté.

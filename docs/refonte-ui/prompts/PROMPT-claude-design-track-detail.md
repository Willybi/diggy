# Prompt — Claude Design · Refonte Track Detail (D4, page 1)

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/track-detail.md` (fiche de cadrage figée — décisions produit)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — composants partagés)
> - `docs/completed/design/handoff-detail-pages/BRIEF-detail-pages.md` (référence de FORMAT uniquement — c'est l'ancienne vague, ne pas en reprendre le contenu)
> - (optionnel) screenshot de la page actuelle `/catalog/:id`

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark mode par défaut, tokens centralisés). On lance la **refonte UI page par page** : chaque page a été cadrée produit dans une fiche figée, et tu produis le **handoff purement design** (brief + maquette) qu'un agent d'implémentation appliquera ensuite tel quel.

**Première page : Détail track — `/catalog/:id`** (TrackDetailView). C'est une **refonte, pas une création** : la page existe, sa structure est déjà proche de la cible, toutes les données sont déjà servies par l'API. Ton travail : polir la mise en forme, spécifier les états, et **créer la spec de 4 composants partagés réutilisables** dont cette page est la première consommatrice.

**Périmètre strict : design/UX uniquement.** Aucune demande backend — les données listées plus bas sont exhaustives, ne rien inventer au-delà.

## Décisions produit FIGÉES (fiche jointe — à respecter, pas à rediscuter)

1. **Structure verticale** : Hero → « Où on l'entend » (sobre) → Découverte (« Du même artiste » + « Tracks similaires ») → bloc Admin (réservé `is_admin`, tout en bas).
2. **Rating (étoiles Rekordbox) : SUPPRIMÉ partout** — plus dans la StatStrip, plus d'étoiles dans les mini-lignes. Ne doit apparaître nulle part dans le design.
3. **« Où on l'entend » sobre** : deux listes — sets (timecode ▶ + date) et playlists radar (badge source + date) — avec compteur par bloc. **Pas** de nom de DJ, pas de « 1re/dernière détection », pas de ligne de résumé.
4. **Score des similaires : `<ScoreRing>` note entière /10** (fini le « 87% » texte).
5. **Mini-lignes « même artiste » / « similaires »** : remplacées par le **`<TrackCard>` compact partagé**.
6. **Indicateur in-lib porté par la cover** via `<Artwork>` (point en coin), qui remplace InLibBadge (hero) et LibDot (lignes).
7. **Écarté** : bloc « Souvent joué avec » (redondant avec Similaires). **Pas de bouton « Suivre »** ici (concept artiste).
8. **Conservé** : hero (cover, artist-chips, genres + tags Rekordbox, actions play/like-dislike/collection), liens externes (label, Beatport, Deezer), StatStrip **BPM · Key · Durée · Année · Radar · Radar sets** (sans Rating — les 4 stats musicales peuvent être intégrées au hero ou rester en strip, à toi de trancher).

## Ce que tu dois livrer

### 1. `BRIEF-track-detail.md` — le handoff de la page

Même format que les briefs existants (tableaux de tokens, anatomie, états, décisions DA explicites). Doit couvrir :

- **Hero** (aujourd'hui `PageHero` variant square) : cover via `<Artwork>` (avec in-lib), titre, artist-chips (avatar rond → `/artist/:id`, plusieurs artistes possibles — jamais supposer un seul), genres cliquables (`StyleTag` → `/style/:genre`) + tags Rekordbox, actions (play preview, like/dislike, « Ajouter à une collection » dropdown), liens externes **en logos** via `<PlatformLink>` (Beatport si `beatport_id`, Deezer si `deezer_id`) + label texte. Placement des 4 stats musicales (BPM · Key · Durée · Année) : dans le hero ou juste dessous — décision DA à expliciter.
- **« Où on l'entend »** : les 2 blocs (« Apparaît dans » les sets / « Détecté dans » les playlists) aujourd'hui en 2 colonnes (`rel-cols`, 1 colonne < 720px). Lignes : titre + timecode/source + date + chevron. Sobre, dense, scannable. Spécifier l'état « un seul des deux blocs présent ».
- **Découverte** : « Du même artiste » et « Tracks similaires » en grilles de `<TrackCard>` compact (2 colonnes desktop, 1 < 720px). Variante « même artiste » sans nom d'artiste ; variante « similaires » avec artiste + `<ScoreRing>`.
- **États** : loading page (utilitaire global `.state`), track introuvable, blocs vides (masqués), loading similaires, ligne en cours de lecture (`playing`), hover.
- **Responsive** : container queries (`@container`), pilote sur 375px. Boutons play toujours visibles < 640px (pas de hover mobile). Hero empilé sur mobile.
- **Bloc Admin** : hors design (il reste tel quel, simplement gaté `is_admin` et en bas de page) — juste le mentionner dans l'ordre vertical.
- **Pas d'état invité** : les invités sont confinés au Hub, cette page est toujours authentifiée.

### 2. `BRIEF-composants-transverses.md` — la spec des 4 composants partagés

**Point clé de ce handoff.** Ces composants n'existent pas encore ; Track Detail est leur première consommatrice mais ils seront réutilisés par TOUTES les pages suivantes de la refonte (Explorer, Radar, Hub, listes, autres détails). Les spécifier comme des composants autonomes, pas comme du styling de page :

- **`<Artwork>`** : cover réelle OU placeholder rayé, ratio carré, tailles (hero / ligne 36px / card), et **indicateur in-lib optionnel en coin** : point plein positif = dans la bibliothèque Rekordbox, cercle pointillé = absent. Petit, discret, lisible sur cover ET sur placeholder, dans les deux thèmes.
- **`<TrackCard>` compact (ligne)** : artwork 36px (`<Artwork>` + in-lib) · titre · artiste (optionnel) · BPM · Key (mono) · play au survol · slot de fin (ScoreRing pour similaires, vide sinon). États : hover, playing, sans preview. Prévoir la parenté avec la variante card verticale (Hub/shelves, cadrée dans TRANSVERSE) — ici on spécifie la **variante ligne**.
- **`<ScoreRing>`** : jauge circulaire + note entière **/10** (le float sert au tri, jamais affiché). Tailles ligne (~30px) et card. S'inspirer/unifier avec les précurseurs existants `RingPct` et `ScorePill` si pertinent — c'est TOI qui fixes la forme canonique.
- **`<PlatformLink>`** : logo de plateforme cliquable (Beatport, Deezer ici ; SoundCloud, YouTube, TrackID, Spotify ailleurs) + `aria-label`. **Contrainte CSP : logos en SVG inline / data-URI, aucun CDN.** États hover/focus, taille alignée sur les actions du hero.

### 3. `Track Detail (pilote).html` — maquette interactive

Même approche que les pilotes précédents : maquette HTML autonome consommant les tokens de `diggy-tokens.css` (zéro couleur hardcodée), avec :
- la page complète (hero, où-on-l'entend, découverte) avec des données réalistes,
- les 4 composants transverses visibles dans leurs variantes/états (un « nuancier » de composants en bas de maquette est bienvenu),
- toggle dark/light, toggle viewport desktop / 375px.

## Données disponibles (exhaustif — ne rien inventer au-delà)

`GET /api/catalog/{id}` : `title`, `artists[]` (id, name, has_artwork), `bpm`, `key`, `duration_ms`, `release_date`, `genres[]` (name, pillar, depth), `style`, `tags[]` (tags Rekordbox), `label`, `beatport_id`, `deezer_id`, `isrc`, `in_lib`, `avis` (like/dislike), `has_preview`, `has_artwork`, `nb_radar_playlists`, `nb_radar_sets`, `radar_appearances[]` (playlist_id, playlist_title, playlist_source, detected_at), `set_appearances[]` (set_id, set_title, timecode_ms, played_date), `same_artist_tracks[]` (id, title, bpm, key, has_artwork, has_preview, in_lib).

`GET /api/catalog/{id}/similar?limit=8` : tracks (id, title, artist, bpm, key, has_artwork, has_preview, in_lib) + `similarity.score` (float 0-1 → note /10 entière à l'affichage).

## Design system — contraintes (rappel)

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. Zéro couleur hardcodée.
- **Typo** : `--font-ui` (Space Grotesk) pour le texte, `--font-mono` (JetBrains Mono) pour les données numériques (BPM, key, durées, timecodes, dates).
- **Thèmes** : `[data-theme="dark"]` par défaut + light — la maquette supporte les deux.
- **Responsive** : container queries (`@container`), jamais `@media` sauf éléments `position: fixed`. La page vit dans `.detail-view` (max-width `--detail-max-w`, `container-type: inline-size`).
- **UI en français.**
- Breakpoints actuels de la page : 720px (rel-cols et mini-grid passent en 1 colonne), 640px (padding mobile, play toujours visible).

## Récapitulatif des livrables

| Fichier | Contenu |
|---------|---------|
| `BRIEF-track-detail.md` | Handoff page : hero, où-on-l'entend, découverte, états, responsive, tokens |
| `BRIEF-composants-transverses.md` | Spec réutilisable : `<Artwork>`, `<TrackCard>` ligne, `<ScoreRing>`, `<PlatformLink>` |
| `Track Detail (pilote).html` | Maquette interactive (page + nuancier composants, toggles theme/viewport) |

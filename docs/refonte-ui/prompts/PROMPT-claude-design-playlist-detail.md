# Prompt — Claude Design · Refonte Playlist Detail (D4, page 2)

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `server/frontend/src/styles/diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/playlist-detail.md` (fiche de cadrage figée — décisions produit, incluant les arbitrages pré-vol du 2026-07-17)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — composants partagés)
> - `docs/refonte-ui/handoff-track-detail/BRIEF-composants-transverses.md` (**spec canonique des composants existants** `<Artwork>` / `<TrackCard>` ligne / `<ScoreRing>` / `<PlatformLink>` — cette page les CONSOMME, l'extension TrackCard demandée doit la respecter)
> - `docs/refonte-ui/handoff-track-detail/BRIEF-track-detail.md` (référence de FORMAT uniquement — son contenu est spécifique à Track Detail, ne pas le transposer)
> - (optionnel) screenshot de la page actuelle `/playlists/:id`

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark mode par défaut, tokens centralisés). Refonte UI page par page : chaque page est cadrée produit dans une fiche figée, tu produis le **handoff purement design** (brief + maquette) qu'un agent d'implémentation appliquera tel quel.

**Page 2 : Détail playlist — `/playlists/:id`** (PlaylistDetailView). C'est le détail d'une **playlist surveillée** (watchlist/radar) — un objet de **veille** : on la suit automatiquement, on la crawle périodiquement, on affiche les tracks **détectées**. C'est une **refonte, pas une création** : la page existe et sa structure est proche de la cible. Ton travail : le hero repensé, le bloc « Dans cette playlist » (enfin câblé côté back), les rangées tracks alignées sur le composant partagé, et la **spec de l'extension du `<TrackCard>` ligne**.

**Différence avec Track Detail** : les 4 composants transverses (`<Artwork>`, `<TrackCard>` ligne, `<ScoreRing>`, `<PlatformLink>`) **existent déjà** et sont en prod — tu ne les re-spécifies pas, tu les consommes. La seule création transverse est une **extension additive** du `<TrackCard>` (voir livrables).

**Périmètre strict : design/UX uniquement.** Les données listées plus bas sont exhaustives — ne rien inventer au-delà.

## Décisions produit FIGÉES (fiche jointe — à respecter, pas à rediscuter)

1. **Hero « cover + infos à côté »** : la cover est **un seul carré** (pas une bande) → on l'**agrandit un peu** et les infos vont **à côté** (pas en overlay) : titre + **source en logo** + owner + stats **Tracks · Dernier crawl**. Action : **lien vers la source en logo** via `<PlatformLink>` (plus de bouton texte « Voir sur … ↗ »). Latitude DA : proportions cover/infos, composition exacte, placement des stats.
2. **Pas de bouton « Suivre » / « Ne plus suivre »** : le concept follow-playlist est **masqué de l'UI** (une playlist ajoutée est surveillée par défaut). Ne doit apparaître nulle part.
3. **Stat « Tracks radar » retirée** : on garde **Tracks** (total côté source) **· Dernier crawl** (+ owner dans le hero). Le libellé de la liste doit rester honnête : ce sont les tracks **détectées**.
4. **Bannière crawl live conservée** (états `queued` / `running`, poll temps réel, disparaît à la fin) — sous le hero. Latitude DA : sa forme.
5. **« Dans cette playlist »** : top artistes (avatars ronds → `/artist/:id`) + genres dominants (barres teintées par famille + %, `StyleTag` → `/style/:genre`). Le bloc était mort (données jamais renvoyées) ; le back les livre désormais — c'est le **bloc vivant** de la page, soigne-le.
6. **Tracks (détectées)** : rangées = **`<TrackCard>` ligne étendu** — cover + in-lib (`<Artwork>` point en coin), titre, **artistes cliquables**, BPM, Key (mono), **durée**, play preview. Plus de table bespoke, plus de colonne LibDot.
7. **Description** (si présente) : conservée, sobre.
8. **Bloc Admin** (fetch artwork Deezer) : **tout en bas** — hors design (composant existant déjà gaté `is_admin`), juste le mentionner dans l'ordre vertical.
9. **Écarté** : « Playlists similaires » (trop peu de playlists surveillées).

## Ce que tu dois livrer

### 1. `BRIEF-playlist-detail.md` — le handoff de la page

Même format que les briefs existants (tableaux de tokens, anatomie, états, décisions DA explicites). Doit couvrir :

- **Hero** : cover carrée agrandie via `<Artwork>` (placeholder rayé si `has_artwork=false` — cas fréquent), infos latérales (titre, logo source via `<PlatformLink>` variante adaptée, owner, stats Tracks · Dernier crawl), action lien source. Spécifier le cas titre absent (fallback `external_id`) et owner absent ou redondant avec la source.
- **Bannière crawl** : états `queued` (neutre) et `running` (accent + pulsation), position sous le hero, apparition/disparition.
- **« Dans cette playlist »** : composition top artistes (avatars + noms, combien affichés) / genres dominants (barre % teintée par famille — hues existants `--hue-house`, `--hue-techno`, `--hue-trance`, `--hue-dnb`, `--hue-hardcore`, `--hue-harddance`, fallback `autres`). Spécifier : un seul des deux présents, bloc entier masqué si les deux vides.
- **Tracks (détectées)** : liste de `<TrackCard>` étendus, en-tête de section avec compteur, tri = détection la plus récente d'abord. Ligne → `/catalog/:id`.
- **États** : loading page (utilitaire global `.state`), playlist introuvable, playlist jamais crawlée (0 track + « Dernier crawl : jamais » — état vide engageant, la bannière crawl peut être active), description absente, ligne en lecture (`playing`), hover.
- **Responsive** : container queries (`@container`), pilote sur 375px. Hero empilé sur mobile, play toujours visible < 640px (pas de hover mobile).
- **Pas d'état invité** : les invités sont confinés au Hub, cette page est toujours authentifiée.

### 2. `BRIEF-trackcard-extension.md` — spec de l'extension `<TrackCard>` ligne

**Extension ADDITIVE du composant existant** (spec jointe : BRIEF-composants-transverses.md). Contrainte dure : **zéro changement pour les consommateurs actuels** (Track Detail l'utilise en prod) — tout est optionnel, la forme actuelle reste le défaut. À spécifier comme composant autonome (réutilisé ensuite par Radar, Nouveautés, autres listes) :

- **Durée** (optionnelle) : colonne mono `m:ss`, placement dans la grille de la ligne, comportement responsive (peut-elle disparaître en étroit ?).
- **Artistes cliquables** (optionnel) : `artists[]` structurés → liens vers `/artist/:id` (plusieurs artistes possibles — ne jamais supposer un seul ; séparateur, troncature). Remplace l'artiste-texte quand fourni ; fallback chaîne plate sinon.
- Cohabitation avec l'existant : slot de fin (ScoreRing…), état playing, play au survol — inchangés.

### 3. `Playlist Detail (pilote).html` — maquette interactive

Maquette HTML autonome consommant les tokens de `diggy-tokens.css` (zéro couleur hardcodée), avec :
- la page complète (hero, bannière crawl, dans-cette-playlist, tracks) avec des données réalistes,
- les variantes/états clés visibles : hero sans artwork, bannière queued/running, TrackCard étendu (avec/sans durée, multi-artistes, in-lib +/−, playing),
- toggle dark/light, toggle viewport desktop / 375px.

## Données disponibles (exhaustif — ne rien inventer au-delà)

> ⚠️ Contrat **cible** : les champs marqués ✦ sont livrés par le lot back du même chantier (arbitré le 2026-07-17) — ils seront disponibles avant l'implémentation front. Tout le reste est déjà en prod.

`GET /api/watchlist/{id}` : `id`, `external_id`, `source` (`deezer` | `tidal` | `spotify`), `title` (nullable), `description` (nullable), `owner` (nullable), `has_artwork`, `track_count` (total côté source, nullable), `created_at`, `last_crawled_at` (nullable), `current_task_id`, `followed`, `tracks[]` (tracks détectées : `catalog_id`, `title`, `artist` chaîne fallback, ✦`artists[]` (id, name, has_artwork), `bpm`, `key`, `duration_ms`, `has_artwork`, `has_preview`, ✦`in_lib`, `detected_at`), ✦`top_artists[]` (id, name, has_artwork, count), ✦`top_genres[]` (name, pillar, depth, pct).

`GET /api/watchlist/{id}/crawl-status` (poll) : `status` = `queued` | `running` | `done` | null.

Artwork playlist : `/storage/playlist-artworks/{id}.jpg` si `has_artwork`. Covers tracks : `/storage/catalog-artworks/{catalog_id}.jpg`. URL externe construite de `source` + `external_id` (deezer/tidal/spotify).

## Design system — contraintes (rappel)

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. Zéro couleur hardcodée.
- **Typo** : `--font-ui` (Space Grotesk) pour le texte, `--font-mono` (JetBrains Mono) pour les données numériques (BPM, key, durées, dates, %).
- **Thèmes** : `[data-theme="dark"]` par défaut + light — la maquette supporte les deux.
- **Responsive** : container queries (`@container`), jamais `@media` sauf éléments `position: fixed`. La page vit dans `.detail-view` (max-width `--detail-max-w`, `container-type: inline-size`). **Convention repo : breakpoints 720px / 640px en `max-width` exclusif** — s'y tenir.
- **CSP stricte** : logos/icônes en SVG inline ou data-URI, aucun CDN.
- **Monochrome plateformes** : `<PlatformLink>` en `currentColor`, jamais les couleurs de marque (décision D6).
- **UI en français.**

## Récapitulatif des livrables

| Fichier | Contenu |
|---------|---------|
| `BRIEF-playlist-detail.md` | Handoff page : hero cover+infos, bannière crawl, dans-cette-playlist, tracks, états, responsive, tokens |
| `BRIEF-trackcard-extension.md` | Spec extension additive `<TrackCard>` ligne : durée + artistes cliquables (optionnels, zéro régression) |
| `Playlist Detail (pilote).html` | Maquette interactive (page + variantes/états, toggles theme/viewport) |

**Livraison** : en fin de round, fournis les 3 livrables dans une **archive zip téléchargeable** (un seul lien de téléchargement), en plus de leur affichage dans la conversation.

# Refonte UI — registre des pages

> Refacto **visuel/UX + technique** de toutes les pages du site, page par page.
> Ce dossier est la **source de vérité** : il alimente ensuite les handoffs Claude Design
> (visuel/UX) et les chantiers `/work_manager` (implémentation). On ne reconstruit rien
> à la « next step » : tout ce qui est figé ici s'y déverse.

## Comment on travaille (boucle par page)

1. **Claude** lit la vue réelle → remplit « Ce qu'on a » (high-level, factuel).
2. **William** décrit sa **vision** en quelques lignes.
3. **Claude** fait la **revue de cohérence** high-level : ✅ garder · ➕ ajouter · ➖ retirer (avec le pourquoi) + faisabilité/invariants.
4. On **ré-alloue les points retirés** : page existante, nouvelle page dédiée, ou abandon.
5. **Claude consolide** : décisions figées + sortie next-step. Page suivante.

Chaque page = un fichier court dans ce dossier. Gabarit : voir [`_TEMPLATE.md`](_TEMPLATE.md).

> **Règle de travail — feature & UI/UX first.** On cadre d'abord la feature et l'UX. Un
> besoin backend n'est **pas** un frein à signaler : si le back doit suivre, autant le
> faire maintenant. Mentionner l'impact back en une ligne neutre si utile, puis avancer.

> **Sujets transverses** (brand/logo, système d'icônes, composants partagés, navigation,
> principes UX) → [`TRANSVERSE.md`](TRANSVERSE.md). Décidés une fois, appliqués partout —
> on ne les re-traite pas page par page.

## Légende statut

🔲 à discuter · 🟡 en cours · ✅ figé (prêt pour la next-step)

## Registre

### Pages utilisateur
| Page | Route | Vue | Fichier | Statut |
|------|-------|-----|---------|--------|
| Hub / accueil | `/` | HubView | [hub.md](hub.md) | ✅ |
| **Explorer** (ex-Catalog) | `/explorer` · redirect `/catalog` `/tracks` | CatalogView | [catalog.md](catalog.md) | ✅ |
| Détail track | `/catalog/:id` | TrackDetailView | [track-detail.md](track-detail.md) | ✅ |
| Artistes (liste) | `/artists` | ArtistsView | [artists-list.md](artists-list.md) | ✅ |
| Détail artiste | `/artist/:id` | ArtistDetailView | [artist-detail.md](artist-detail.md) | ✅ |
| **Détail album** (nouvelle, future) | à définir | à créer | [album-detail.md](album-detail.md) | 🔲 |
| Sets (liste) | `/sets` | SetsView | [sets-list.md](sets-list.md) | ✅ |
| Détail set | `/set/:id` | SetDetailView | [set-detail.md](set-detail.md) | ✅ |
| Genres (liste) | `/genres` | GenresView | [genres-list.md](genres-list.md) | ✅ |
| Détail genre/style | `/style/:genre` | GenreDetailView | [genre-detail.md](genre-detail.md) | ✅ |
| Collections (liste) | `/collections` | CollectionsView | [collections.md](collections.md) | 🔲 |
| Détail collection | `/collections/:id` | CollectionDetailView | [collection-detail.md](collection-detail.md) | 🔲 **à la toute fin** (vraie feature complète à designer) |
| Playlists / watchlist | `/playlists` | WatchlistView | [playlists-list.md](playlists-list.md) | ✅ |
| Détail playlist | `/playlists/:id` | PlaylistDetailView | [playlist-detail.md](playlist-detail.md) | ✅ |
| Login | `/login` | LoginView | [login.md](login.md) | ✅ laissée telle quelle |
| Admin | `/admin` | AdminView | [admin.md](admin.md) | ✅ |
| **Nouveautés de tes artistes** (nouvelle, issue du Hub) | `/new-releases` _(proposé)_ | à créer | [new-releases.md](new-releases.md) | 🔲 |
| **Radar** (Tendances + Pour toi ; absorbe `/for-you`) | `/radar` | à créer | [radar.md](radar.md) | ✅ |

_« Pour toi » n'a plus de page dédiée : fusionnée dans Radar (colonne Pour toi)._

### Hors périmètre (référence)
| Page | Route | Vue | Raison |
|------|-------|-----|--------|
| Callback login | `/login/callback` | LoginCallbackView | Flow technique Safari iOS — **ne pas toucher** |
| Design System | `/design-system` | DesignSystemView | Vitrine dev-only = référentiel de tokens, pas une page produit |

## Invariants transverses à respecter (rappel)

- **Zéro couleur hardcodée** : tout via `var(--...)` de `diggy-tokens.css`.
- **Container queries** partout ; `@media` uniquement pour `position: fixed`.
- **Visibilité catalog (C3)** : toute lecture catalog applique `catalog_visible`.
- **Composables** : polling → `useTaskPoll`, listes paginées → `usePaginatedList` (jamais d'ad-hoc).
- **UI en français, code en anglais.**
- Pas de handler multi-statements inline dans les templates (Prettier casse le compilo Vue).

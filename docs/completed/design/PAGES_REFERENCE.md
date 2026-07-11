# Diggy — Reference des pages

> 17 vues (`.vue`) — 16 routes actives + 1 morte (TagsView, redirige vers GenresView).
> 3 redirections legacy : `/tracks` → `/catalog?inlib=true`, `/tags` → `/genres`, `/radar` → `/catalog?view=radar`.

---

## Index des handoffs

| Vue | Route | Dossier handoff | Contenu |
|-----|-------|-----------------|---------|
| HubView | `/` | `handoff-hub/` | Brief + maquette HTML + prompt agent + style-map |
| LoginView | `/login` | — pas de handoff | |
| LoginCallbackView | `/login/callback` | — pas de handoff | Technique pure (cookie OAuth) |
| GenresView | `/genres` | `handoff-genres-couleurs/` | Brief + maquette HTML + style-map |
| GenreDetailView | `/style/:genre` | `handoff-genres-couleurs/` | Meme dossier que GenresView |
| CatalogView | `/catalog` | `handoff-cards-v2/` | Brief + maquette HTML |
| TrackDetailView | `/catalog/:id` | `handoff-detail-pages/` | 2 briefs + maquette HTML + style-map + data + css |
| ArtistDetailView | `/artist/:id` | `handoff-detail-pages/` | Meme dossier que TrackDetailView |
| ArtistsView | `/artists` | — pas de handoff | |
| SetsView | `/sets` | `handoff-sets-fix/` | Brief + maquette HTML |
| SetDetailView | `/set/:id` | `handoff-detail-pages/` | Meme dossier que TrackDetailView |
| AdminView | `/admin` | — pas de handoff | |
| CollectionsView | `/collections` | — pas de handoff | |
| CollectionDetailView | `/collections/:id` | — pas de handoff | |
| WatchlistView | `/playlists` | — pas de handoff | |
| PlaylistDetailView | `/playlists/:id` | — pas de handoff | |
| TagsView | `/tags` | — morte, redirige vers `/genres` | Suppression prevue N1.b |

**Autres handoffs** (transversaux, pas lies a une seule vue) :
- `handoff-refactor/` : audit composants partages (Component Kit) + style-map
- `handoff-mobile/` : brief responsive + prompt agent (s'applique a toutes les vues)

---

## 1. Hub `/`

**Vue** : HubView — **Handoff** : `handoff-hub/`

**Role** : Page d'accueil / point d'entree

**Contenu** :
- Section "Ca sort en ce moment" : grille trend + FamilyChips + badge #N
- Acces rapide aux sections principales

---

## 2. Login `/login`

**Vue** : LoginView — **Handoff** : aucun

**Role** : Authentification via Google OAuth

**Contenu** :
- Logo Diggy + titre
- Bouton "Se connecter avec Google"
- Message d'erreur inline

**Layout** : Carte centree (360px), fond neutre, pas de sidebar

---

## 3. Login Callback `/login/callback`

**Vue** : LoginCallbackView — **Handoff** : aucun

**Role** : Recepteur du callback OAuth Google

**Contenu** : Ecran de chargement, lit le cookie `auth_callback`, redirige vers `/`

---

## 4. Catalog `/catalog`

**Vue** : CatalogView — **Handoff** : `handoff-cards-v2/`

**Role** : Table principale de toutes les tracks connues du systeme. Inclut le mode Radar (`/catalog?view=radar`).

**Header** :
- Titre "Catalog"
- Sous-titre : `{total} tracks . {n} in lib`

**Filtres** :
- Recherche texte (artiste ou titre, debounce 300ms)
- Chip "Pas dans RB" (tracks pas dans Rekordbox)
- Chip "Radar >= 2" (detectees dans 2+ playlists)
- Chip "In lib" (tracks dans la bibliotheque)

**Tableau** (colonnes) :
| Col | Donnee |
|-----|--------|
| Play | Bouton preview (apparait au hover) |
| Track | Artwork mini (38px) + titre (lien vers detail) + artiste |
| Style | Badge genre Beatport (lien vers /style/:genre) |
| BPM | Valeur arrondie |
| Key | Tonalite (accent color) |
| Duree | Format mm:ss |
| Rating | 5 etoiles |
| Radar | ScorePill (nb playlists * 2, max 10) |
| In lib | LibDot (indicateur vert/gris) |

**Interactions** :
- Tri par colonnes (title, style, bpm, key, duration_ms, rating, nb_radar_playlists)
- Pagination (50 items/page)
- Filtre "In lib" persiste en sessionStorage
- Mode Radar : onglets Tous | New | Seen | Added | Ignored avec actions triage

---

## 5. Track Detail `/catalog/:id`

**Vue** : TrackDetailView — **Handoff** : `handoff-detail-pages/`

**Role** : Fiche complete d'une track

**Hero** :
- Artwork grand (variante "square")
- Titre + artiste
- Badges : InLibBadge + StyleTag genre
- Action : HeroPlayer (bouton play)

**StatStrip** : BPM | Key | Duree | Annee | Rating (etoiles) | Radar count

**Meta** : Label + lien Beatport externe

**Blocs relationnels** :
- "Detecte dans" : liste des playlists radar ou la track a ete reperee (titre + date)
- "Apparait dans" : liste des sets DJ contenant cette track (titre + date, lien)
- "Du meme artiste" : autres tracks du meme artiste (titre + badge in lib, lien)

**Admin** (si is_admin) :
- Carte orange : beatport_id affiche
- Bouton "Enrichir via Beatport" : recherche ISRC puis fallback titre+artiste
- Resultat inline (BPM, Key, Label trouves)

---

## 6. Genres `/genres`

**Vue** : GenresView — **Handoff** : `handoff-genres-couleurs/`

**Role** : Grille de navigation par genre musical

**Header** : Titre "Genres" + compteur

**Contenu** : Grille responsive (auto-fill, minmax 220px)
- Chaque carte : StyleTag color + compteur tracks
- Clic → `/style/:genre`

---

## 7. Genre Detail `/style/:genre`

**Vue** : GenreDetailView — **Handoff** : `handoff-genres-couleurs/`

**Role** : Liste des tracks d'un genre specifique

**Header** :
- Lien retour "← Genres"
- StyleTag du genre + total tracks

**Recherche** : Input texte dans le genre

**Liste tracks** : Format compact (pas de table)
- Cover mini (36px) + titre + artiste
- BPM + Key (mono)
- Badge "IN LIB" si applicable

**Pagination** : 50 items/page

---

## 8. Playlists `/playlists`

**Vue** : WatchlistView — **Handoff** : aucun

**Role** : Gestion des playlists surveillees (watchlist)

**Header** :
- Titre "Playlists" + sous-titre "Playlists surveillees par le Radar"
- Toggle "Suivies" / "Toutes"
- Bouton "+ Ajouter"

**Formulaire d'ajout** :
- Input URL (Deezer, Tidal, Spotify)
- Parse auto du type de source
- Bouton "Suivre"

**Tableau** :
| Col | Donnee |
|-----|--------|
| Cover | Thumbnail 40px |
| Playlist | Titre + badge source (deezer/tidal/spotify) + external_id |
| Createur | Nom owner |
| Tracks | Nombre de tracks |
| Dernier crawl | Date relative ("aujourd'hui", "il y a 3j") |
| Action | "Crawl now" + "Ne plus suivre" (ou "Suivre" en mode browse) |

**Interactions** :
- Cooldown crawl : 12h entre deux crawls
- Polling apres ajout/crawl (5s, max 5min)
- Mode "Toutes" affiche les playlists non suivies aussi

---

## 9. Playlist Detail `/playlists/:id`

**Vue** : PlaylistDetailView — **Handoff** : aucun

**Role** : Fiche d'une playlist specifique

**Hero** :
- Artwork (variante "square")
- Titre + sous-titre (owner . source)
- Actions : lien Deezer externe + bouton Suivre/Ne plus suivre

**StatStrip** : Tracks | Tracks radar | Dernier crawl | Ajoutee le

**Description** : Bloc texte si dispo

**Table tracks** :
| Col | Donnee |
|-----|--------|
| Cover | Mini artwork 32px |
| Track | Titre (lien catalog) + artiste |
| BPM | Valeur |
| Key | Tonalite |
| Duree | Format mm:ss |
| Preview | Bouton play/pause |

---

## 10. Artistes `/artists`

**Vue** : ArtistsView — **Handoff** : aucun

**Role** : Repertoire de tous les artistes

**Header** : Titre "Artistes" + compteur + recherche

**Tableau** :
| Col | Donnee |
|-----|--------|
| Cover | Photo ronde 40px (ou lettre fallback) |
| Artiste | Nom + real_name (si dispo, en mono) |
| Genres | Liste de StyleTags |
| Catalog | Nb tracks dans le catalog |
| In lib | Nb tracks dans la lib |
| Rating | Moyenne rating |

**Interactions** :
- Clic sur ligne → page artiste
- Recherche debounce

---

## 11. Artist Detail `/artist/:id`

**Vue** : ArtistDetailView — **Handoff** : `handoff-detail-pages/`

**Role** : Fiche complete d'un artiste

**Hero** :
- Photo ronde (variante "round")
- Nom + sous-titre (real_name . country)
- Badges : StyleTags genres (liens vers /style/)
- Actions : liens externes Deezer, SoundCloud, TrackID

**Admin** (si is_admin) :
- Carte orange : deezer_id affiche
- Recherche Deezer : resultats avec photo, nom, nb fans, lien
- Selection + confirmation liaison
- Bouton "Delier" si deja lie
- Message succes/erreur + gestion fusion si doublon

**StatStrip** : Catalog | In lib | Sets | Rating moy.

**Blocs** :
- **Aliases** : liste texte des noms alternatifs
- **Biographie** : bloc texte
- **Tracks** : mini-table (titre, style, BPM, key, rating)
- **Sets** : liste des sets ou l'artiste joue (titre, date, role B2B, tracks identifiees)

---

## 12. Sets `/sets`

**Vue** : SetsView — **Handoff** : `handoff-sets-fix/`

**Role** : Liste des DJ sets importes

**Header** :
- Titre "Sets" + compteur
- Recherche + toggle "Tous"/"Suivis"
- Bouton "+ Ajouter"

**Formulaire d'ajout** (2 modes) :
- **Rechercher** : recherche TrackID → resultats avec cover, titre, channel, nb tracks, date → bouton "Importer + Suivre"
- **URL** : coller URL TrackID directement

**Tableau** :
| Col | Donnee |
|-----|--------|
| Cover | Thumbnail 40px |
| Set | Titre + artistes (sous-titre) |
| Date | Date played |
| Tracks | identified/total |
| Duree | Format hh:mm |
| Action | Suivre / Ne plus suivre |

---

## 13. Set Detail `/set/:id`

**Vue** : SetDetailView — **Handoff** : `handoff-detail-pages/`

**Role** : Fiche complete d'un DJ set avec tracklist

**Hero** :
- Artwork large (variante "wide")
- Titre + sous-titre (artiste . event . venue)
- Action : lien vers source (YouTube, SoundCloud, TrackID, 1001Tracklists)

**StatStrip** : Duree | Date | Tracks | Identifiees

**Admin** (si is_admin) :
- Carte orange "Artistes du set"
- Liste artistes lies (nom + role + bouton retirer)
- Recherche artiste pour en ajouter

**Blocs** :
- **Artistes** (si > 1) : liste avec liens vers fiches artistes
- **Tracklist** : table complete

**Table tracklist** :
| Col | Donnee |
|-----|--------|
| # | Position |
| Time | Timecode (lien cliquable vers YouTube/SoundCloud au bon timestamp) |
| Cover | Mini artwork 32px |
| Track | Titre + artiste (lien catalog si identifie, "ID" si non identifie) |
| Lib | LibDot ou label "ID" |

**Etats visuels des lignes** :
- Normal : track identifiee et dans le catalog
- `row--unknown` : track non identifiee (italique, grise)
- `row--id` : track "ID" non identifiee (tres attenuee)

---

## 14. Collections `/collections`

**Vue** : CollectionsView — **Handoff** : aucun

**Role** : Liste des collections utilisateur (playlists personnelles)

**Contenu** :
- Grille de cartes collection
- CRUD : creer, renommer, supprimer
- Compteur tracks par collection

---

## 15. Collection Detail `/collections/:id`

**Vue** : CollectionDetailView — **Handoff** : aucun

**Role** : Contenu d'une collection

**Contenu** :
- Header avec nom + compteur
- Table de tracks (similaire a CatalogView)
- Drag & drop reordering
- Actions : ajouter / retirer des tracks

---

## 16. Admin `/admin`

**Vue** : AdminView — **Handoff** : aucun

**Role** : Panel d'administration (reserve is_admin)

**Sections** :

### Sync artistes
- Bouton "Lancer la sync"
- Parse les noms d'artistes du catalog → cree les artistes
- Resultat : crees / flagges / skippes
- Polling status Celery (2s, max 10min)

### Artworks artistes
- Bouton "Fetch artworks"
- Telecharge les photos Deezer de tous les artistes lies
- Resultat : fetched / lies Deezer / skippes

### Artistes des sets
- Bouton "Lier artistes aux sets"
- Parse les titres de sets pour detecter les artistes
- Resultat : lies / deja lies

### Enrichissement Beatport
- Input batch size (0 = tout)
- Bouton "Enrich Beatport"
- Enrichit BPM, key (Camelot), label, genre, artwork
- Resultat : enrichis / non trouves / erreurs / total

### Lier un artiste a Deezer
- Double colonne :
  - Gauche : artistes sans deezer_id (filtrable) + actions "Pas sur Deezer" / "Flagguer"
  - Droite : resultats recherche Deezer (photo, nom, fans, lien)
- Selection croisee + confirmation liaison

### Flags artistes
- Filtre : pending / validated / skipped
- Table flags :
  - String brute (le nom original)
  - Raison (comma_unresolved, ampersand_ambiguous, etc.)
  - Tokens detectes (splits proposes)
  - Deezer (resultat lookup pour chaque token : trouve/manquant)
  - Actions : Splitter / Garder / Ignorer

---

## Composants partages cles

| Composant | Usage |
|-----------|-------|
| `SidebarNav` | Navigation principale (232px, liens + section admin) |
| `BottomNav` | Navigation mobile (<640px, 5 items + admin) |
| `PageHero` | En-tete de page detail (variantes: square, round, wide) |
| `StatStrip` | Bandeau de stats horizontales |
| `RelBlock` | Bloc relationnel avec titre + compteur |
| `AppearRow` | Ligne d'apparition (titre + sous-titre + lien) |
| `StyleTag` | Badge colore par genre |
| `ScorePill` | Indicateur score radar (0-10) |
| `LibDot` | Pastille in lib (vert) ou non (gris) |
| `InLibBadge` | Badge "In lib" pour les heroes |
| `HeroPlayer` | Bouton play dans le hero |
| `PlayerBar` | Lecteur audio (preview Deezer 30s) |

---

## Design tokens

- Tout via CSS custom properties (`var(--...)`)
- Fichier : `src/styles/diggy-tokens.css`
- Zero couleur hardcodee
- Fonts : `--font-ui` (interface), `--font-mono` (donnees)
- Surfaces : `--bg`, `--surface`, `--surface-2`, `--surface-3`
- Encres : `--ink`, `--ink-2`, `--ink-3`
- Lignes : `--line`, `--line-2`
- Accent : `--accent`, `--accent-ink`, `--accent-soft`, `--on-accent`
- Semantique : `--pos-ink`, `--neg-ink`, `--warn-ink`
- Rayons : `--r-xs`, `--r-sm`
- Spacing : `--pad`, `--row-h`

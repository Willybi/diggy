# Prompt — Claude Design · Diggy Mobile Responsive

> Envoyer ce prompt a Claude Design (claude.ai/projects).
> Joindre en fichiers : `diggy-tokens.css`, `BRIEF-catalog.md`, `BRIEF-player.md`

---

## Contexte

Tu es le designer de **Diggy**, une web app DJ (Vue 3, dark mode par defaut, design system "Wildflower"). L'app est actuellement **desktop-only**. On doit la rendre utilisable sur telephone (5-10 amis DJs vont l'utiliser sur mobile).

L'approche : **responsive progressif** (pas de version separee). On ajoute un breakpoint principal a **640px** (telephone vertical). Au-dessus de 640px, rien ne change.

## Ce que tu dois livrer

### 1. `BRIEF-mobile.md`

Un brief complet dans le **meme format** que les briefs existants (voir `BRIEF-catalog.md` et `BRIEF-player.md` fournis en reference). Le brief doit couvrir :

#### a. BottomNav (nouveau composant)

Sur mobile (< 640px), la sidebar desktop disparait. Elle est remplacee par une **barre de navigation fixe en bas** (bottom nav).

Specifier :
- **Items** : Hub (icone maison), Catalog (icone grille), Artistes (icone personnes), Sets (icone disque), Genres (icone tag). Si l'utilisateur est admin : 6e item Admin (icone etoile).
- **Anatomie** : icone SVG 20px + label court en dessous (10px mono), le tout centre
- **Dimensions** : hauteur totale ~56px + safe area iPhone (`env(safe-area-inset-bottom)`)
- **Tokens** : fond, bordure, couleur icones/labels (actif vs inactif), highlight route active
- **Etats** : actif (accent), inactif (ink-3), badge count (optionnel, pour le radar new count)
- **Z-index** : en dessous du PlayerBar

#### b. Layout shell mobile

Ce qui change dans le shell app (la grille sidebar + contenu) sous 640px :
- Sidebar masquee (`display: none`)
- Grille passe a `1fr` (une seule colonne)
- `padding-bottom` du contenu = hauteur BottomNav + espace PlayerBar si visible
- BottomNav affichee

#### c. PlayerBar mobile

Le lecteur audio est un bandeau `position: fixed` en bas. Sur mobile :
- **Repositionner** au-dessus de la BottomNav (bottom = hauteur BottomNav + gap)
- **Marges laterales** reduites (8px au lieu de 24px)
- Les elements deja masques par les container queries internes (BPM/Key sous 720px, elapsed/remain sous 560px, volume sous 440px) restent masques — sur 375px de large, seuls play/pause + identity + scrub + close sont visibles. C'est le bon comportement.
- Specifier les dimensions finales sur 375px

#### d. Tables mobile — colonnes qui tombent

Pour chaque table du projet, specifier l'**ordre de chute des colonnes** par breakpoint (comme dans BRIEF-catalog.md). Etat final sur 375px.

**Table Catalog** (CatalogView) — 12 colonnes desktop :
Play | Track (cover+titre+artiste) | Style | BPM | Key | Source | Detect | Duration | Rating | InLib | Radar | Avis

**Table Sets** (SetsView) — 5 colonnes desktop :
Set | Date | Tracks | Duration | Avis

**Tracklists** (SetDetailView, ArtistDetailView) — colonnes :
# | Play | Time | Cover+Titre | BPM | Key | Style | LibDot

Specifier pour chaque : quelles colonnes survivent a 640px, a 500px, et a 375px.

#### e. Modales mobile

L'import Rekordbox est une modale (`max-width: 480px`). Sur mobile :
- Full-screen sheet (pas de modale flottante)
- Anatomie : header avec titre + bouton close, padding reduit, contenu pleine largeur
- Tokens

#### f. Cibles tactiles

- **Minimum** : 44px de hauteur pour tout element interactif (boutons, chips, rows cliquables)
- **Hover-only → toujours visible** : les boutons play (`.pbtn`) et LikeDislike dans les tables sont `opacity: 0` en desktop (reveles au hover). Sur mobile, pas de hover → les rendre toujours visibles.

#### g. Vue par vue — adaptations mobile

Pour chaque vue principale, decrire ce qui change sous 640px :

| Vue | Changements mobile |
|-----|-------------------|
| **CatalogView** | Table allegee (voir §d), padding lateral 16px, titre h1 reduit, filtres/chips en scroll horizontal |
| **ArtistsView** | Grille `minmax(150px, 1fr)`, padding 16px |
| **ArtistDetailView** | Hero empile (flex-direction: column), mini-rows simplifiees (masquer BPM/Key sous 500px) |
| **SetsView** | Formulaire ajout en column, grille artistes 2 col puis 1 col |
| **SetDetailView** | Tracklist allegee (voir §d), anneau centre |
| **GenresView** | Grille `minmax(150px, 1fr)`, padding 16px |
| **GenreDetailView** | Shelves en scroll horizontal, tracks allegees, padding 16px |
| **HubView** | Search bar pleine largeur, resultats empiles, shelves en scroll horizontal |
| **TrackDetailView** | Hero empile (flex-direction: column), `.rel-cols` 1 colonne |
| **WatchlistView** | Padding reduit, table playlists allegee |
| **LoginView** | Formulaire centre, pas de probleme attendu |
| **AdminView** | Faible priorite (un seul user admin, desktop) — verification minimale |

### 2. `Mobile (pilote).html`

Une **maquette HTML interactive** (meme approche que `Diggy DA.html` et les pilotes existants) montrant :

- **BottomNav** : les 5-6 items avec etats actif/inactif
- **CatalogView mobile** : table allegee sur 375px avec les colonnes restantes
- **PlayerBar mobile** : repositionne au-dessus de la BottomNav
- **Toggle viewport** : boutons pour basculer entre 375px (iPhone SE) / 390px (iPhone 14) / 768px (tablette, sidebar rail visible)
- **Toggle dark/light** : comme les maquettes existantes

La maquette doit utiliser les tokens de `diggy-tokens.css` (fourni). Pas de couleurs hardcodees.

## Design system existant — contraintes

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css` (fourni). Zero couleur hardcodee.
- **Typo** : `--font-ui` (Space Grotesk) pour le texte, `--font-mono` (JetBrains Mono) pour les donnes numeriques
- **Dark mode** : `[data-theme="dark"]` — la maquette doit supporter les deux
- **Container queries** : le code existant utilise `@container` (pas `@media`) pour le responsive. Exception : les elements `position: fixed` (PlayerBar, BottomNav, modales) utilisent `@media` car ils sont hors du flux container.
- **Breakpoints existants** : 900px (sidebar → rail 66px), breakpoints varies par vue (720px, 640px, 560px, 520px, 380px)
- **Nouveau breakpoint** : 640px = mobile. C'est la coupure principale : en dessous, sidebar disparait et BottomNav apparait.

## Layout actuel (ce que tu as)

### Grille App.vue
```css
.app-container { --sidebar-w: 232px; container-type: inline-size; height: 100vh; }
.app-shell { display: grid; grid-template-columns: var(--sidebar-w) 1fr; height: 100%; }
@container (max-width: 900px) { .app-container { --sidebar-w: 66px; } }
```

### Sidebar (SidebarNav.vue)
Items : Hub (/), Catalog, Artistes, Sets, Playlists, Genres + Admin (si admin)
Rail mode a 900px : icones seules, labels masques

### PlayerBar (position: fixed)
```css
.player { position: fixed; bottom: 18px; left: calc(var(--sidebar-w, 232px) + 24px); right: 24px; max-width: 1200px; }
```
Container queries internes masquent progressivement : stats (720px), elapsed/remain (560px), volume (440px)

## Recapitulatif des livrables

| Fichier | Contenu |
|---------|---------|
| `BRIEF-mobile.md` | Brief complet (BottomNav, layout, PlayerBar, tables, modales, cibles tactiles, vue par vue) |
| `Mobile (pilote).html` | Maquette interactive (BottomNav + CatalogView + PlayerBar sur 375px, toggle viewport/theme) |

Format du brief = identique a `BRIEF-catalog.md` : tableaux tokens, colonnes qui tombent par breakpoint, etats a implementer, decisions DA explicites.

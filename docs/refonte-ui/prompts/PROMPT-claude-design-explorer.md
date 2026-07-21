# Prompt — Claude Design · Refonte Explorer (D6, page 1)

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/catalog.md` (fiche de cadrage figée de la page Explorer — décisions produit)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — composants partagés)
> - `docs/refonte-ui/handoff-artist-detail/BRIEF-artist-detail.md` (référence de FORMAT uniquement — son contenu concerne une autre page et peut contredire les décisions ci-dessous)
> - Captures de la page ACTUELLE (dossier `C:\tmp\captures-explorer\`) :
>   - `01-desktop-dark-catalog-full.png` — mode Catalog complet, desktop dark 1440px (table 50 rangées + pagination)
>   - `02-desktop-dark-radar-mode.png` — mode Radar actuel (période « Tout ») : TOUT ce qui est visible en propre ici QUITTE la page (colonnes Source/Détecté/Radar, segment, période)
>   - `03-desktop-light-catalog-full.png` — mode Catalog, desktop light
>   - `04-mobile-375-dark-catalog.png` — mode Catalog, mobile 375px dark (colonnes réduites à Play/Track/Key/InLib, head empilé)

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark mode par défaut, tokens centralisés). La refonte page par page continue : les 4 pages détail (Track, Playlist, Set, Artist) sont livrées, on attaque les **listes**. Chaque page a été cadrée produit dans une fiche figée, et tu produis le **handoff purement design** (briefs + maquette) qu'un agent d'implémentation appliquera tel quel.

**Cette page : Explorer — `/explorer` (ex-Catalog, renommée).** C'est la refonte de l'actuelle page Catalog : le tableau dense de toute la base (117 000+ tracks). Deux mouvements produit majeurs :
1. **Le mode Radar quitte la page** (il devient une page dédiée, conçue au livrable suivant — ne PAS la designer ici).
2. La page devient un **moteur de recherche sur la base brute** : le gros du chantier design est la **barre de filtres riches** et sa déclinaison mobile.

**Périmètre strict : design/UX uniquement.** Le shell de l'app (sidebar, BottomNav) est hors périmètre — tu ne designs que le contenu de la page. Les données listées plus bas sont exhaustives : ne rien inventer au-delà.

**Composants transverses : cette page n'en crée AUCUN.** `<Artwork>` (cover + placeholder rayé + indicateur in-lib en coin : point plein = dans la bibliothèque Rekordbox, cercle pointillé = absent), `<TrackCard>`, `<ScoreRing>`, `<PlatformLink>` existent déjà (spec dans TRANSVERSE.md, implémentés). Tu les CONSOMMES. En revanche la **mécanique de filtres** que tu vas concevoir sera réutilisée telle quelle par la future page Radar (« filtres façon Explorer » — décision figée) : spécifie-la comme un jeu de composants autonomes, pas comme du styling de page.

## Décisions produit FIGÉES (fiche jointe — à respecter, pas à rediscuter)

1. **Nom & rôle** : « Catalog » → **Explorer**, route `/explorer`. Moteur de recherche de la base brute. **Plus aucune info trend affichée**, à une exception près : le **badge `#rank`** (petit, sur le titre, si `trend_rank` ≤ 50) est conservé.
2. **Mode Radar retiré intégralement** : segment Catalog/Radar, colonnes Source + Détecté, colonne Radar (score), chip « Radar ≥ 2 », sub-bar Période. Rien de tout ça dans le design (capture 02 = ce qui part).
3. **Colonnes conservées** : Play · Track (cover **`<Artwork>` avec indicateur in-lib** + titre + artistes cliquables + badge #rank) · Style (`StyleTag` cliquable → `/style/:genre`) · BPM · Key · Durée · Avis (like/dislike). **Colonnes supprimées** : In lib (remplacée par l'indicateur cover), **Rating (étoiles — purge projet, ne doit apparaître nulle part)**, Radar, Source, Détecté. **Aucune nouvelle colonne.**
4. **Filtres retenus** (le cœur de la page) :
   - **BPM** : range (slider).
   - **Key** : multi-select en notation **Camelot** (valeurs réelles en base : `1A`…`12B`) — présentation pensée harmonique (roue/grille Camelot bienvenue).
   - **Style** : multi-select piliers + sous-genres (données : liste plate name/count/pillar/depth — le groupement par pilier est à toi).
   - **Artiste** : type-ahead (recherche serveur).
   - **In lib** : tri-state — tous / dans ma bib / pas dans RB.
   - **Durée** : range ou presets (<3 / 3–5 / 5–8 / >8 min) — à toi de trancher.
   - **Écoutable** : booléen (a un extrait audio).
   - **Avis** : liked / disliked / neutre.
   - **Année** : range sur l'année de sortie (`release_date`).
   - **Label** : recherche/saisie texte (labels non énumérés côté API).
   - Écarté (arbitrage 2026-07-20) : « a une cover ».
5. **Filtres synchronisés dans l'URL** : une recherche est bookmarkable/partageable — l'état des filtres doit donc être entièrement visible et restaurable à l'écran (pense au retour sur une URL filtrée).
6. **Tri** : sélecteur explicite — **Récemment ajoutés (défaut)** · Titre A–Z · Artiste A–Z · BPM · Key (ordre harmonique) · Durée · Date de sortie. Le tri par clic d'en-tête de colonne reste souhaitable là où la colonne existe.
7. **Scroll : infinite scroll virtualisé** (windowing — seules les lignes visibles sont rendues). Contraintes design induites : **hauteur de rangée CONSTANTE** (pas de rangée à hauteur variable), en-tête de table sticky. La pagination `← page/N →` disparaît.
8. **Imports conservés mais rangés** : « Ajouter un track » + « Importer XML » passent dans un **menu « + »** discret — le head est désencombré au profit des filtres.
9. **Conservés** : play inline (extrait), like/dislike avec coloration de ligne (liked = wash positif, disliked = ligne estompée), clic → page détail, ligne en cours de lecture.
10. **Libellés 100 % français** (les « tracks in lib », « In lib », « Catalog » actuels disparaissent).
11. **Pas d'état invité** : page interne toujours authentifiée (l'invité est confiné au Hub).

## Latitude DA (à toi de trancher, décisions à expliciter dans le brief)

- **La barre de filtres** : c'est LE morceau design. Composition (barre compacte + panneau dépliant ? rangée de chips actives ? compteur de résultats live ?), présentation de chaque contrôle (multi-select, range slider, type-ahead, tri-state), état « filtres actifs » + reset, interaction avec la recherche texte existante.
- **Drawer/feuille de filtres mobile** (multi-selects et sliders ne tiennent pas dans un head mobile).
- **Échelle de column-drop responsive** (l'actuelle masque progressivement sur ~8 paliers — à redéfinir pour le nouveau jeu de colonnes ; sous 640px le tactile impose play et avis toujours visibles).
- **Empty states** : aucun résultat (filtres trop stricts — proposer de les assouplir/reset) vs chargement.
- Densité, hover states, transitions — dans l'esprit de la table actuelle (captures 01/03).

## Ce que tu dois livrer

### 1. `BRIEF-explorer.md` — le handoff de la page

Même format que les briefs existants (tableaux de tokens, anatomie, états, décisions DA explicites). Doit couvrir : head de page (titre, compteur, recherche, menu « + »), barre de filtres desktop, table (colonnes, dimensions, hauteur de rangée fixe, sticky header), états de ligne (hover, playing, liked, disliked, sans preview), badge #rank, empty states, responsive complet (échelle de column-drop + drawer mobile), pilote 375px.

### 2. `BRIEF-filtres-partages.md` — spec AUTONOME de la mécanique de filtres

Réutilisée telle quelle par la future page Radar. Spécifier comme des composants indépendants de la page : le conteneur (barre + panneau + drawer mobile), et chaque contrôle — multi-select (Camelot, styles), range slider (BPM, année, durée), type-ahead (artiste), tri-state (in lib), toggles (écoutable, avis), sélecteur de tri, chips d'état actif + reset. États : vide, actif, focus clavier, désactivé, dark/light.

### 3. `Explorer (pilote).html` — maquette interactive

Maquette HTML autonome consommant les tokens de `diggy-tokens.css` (zéro couleur hardcodée), avec :
- la page complète avec données réalistes (~20 rangées, mélange in-lib/hors-lib, avec/sans cover, liked/disliked, badge #rank sur 1-2 titres),
- la barre de filtres dans ses états (fermée, panneau ouvert, plusieurs filtres actifs avec chips, aucun résultat),
- le drawer mobile ouvert,
- toggle dark/light, toggle viewport desktop / 375px.

### 4. ⚠️ **Livraison : une archive ZIP téléchargeable UNIQUE (un seul lien) contenant les 3 livrables.** Sans archive, le transfert des fichiers est manuel et casse le pipeline.

## Données disponibles (exhaustif — ne rien inventer au-delà)

`GET /api/catalog/` → `{ total, items[] }`, champs par item **à la cible** (surface après retrait du rating et des champs radar) :
`id`, `title`, `artist` (chaîne de repli), `artists[]` (id, name — plusieurs artistes possibles, jamais en supposer un seul), `bpm` (float, arrondi à l'affichage), `key` (Camelot `"8A"`, nullable), `duration_ms`, `genres[]` (name, pillar, depth), `style` (repli si `genres` vide), `label` (nullable), `release_date` (nullable), `created_at`, `has_artwork` (cover : `/storage/catalog-artworks/{id}.jpg`), `has_preview`, `in_lib` (bool), `avis` (`liked`/`disliked`/null), `trend_rank` (nullable, badge si ≤ 50), `isrc`, `deezer_id`, `beatport_id`.

Les **paramètres de filtre** correspondants (bpm range, key[], genre[], artiste, durée, écoutable, avis, année, label, in-lib tri-state, recherche texte, tri/ordre) sont ajoutés par le lot back du chantier — leur sémantique est celle de la liste FIGÉE ci-dessus, leurs noms exacts sont fixés à l'implémentation : le design ne doit dépendre que de la sémantique.

Sources des options de filtres :
- Styles : `GET /api/catalog/genres` → liste plate `{ name, count, pillar, depth }`.
- Artiste (type-ahead) : `GET /api/artists/?q=<saisie>&limit=…` → `{ id, name, … }` (avatar dispo si `has_artwork` : `/storage/artist-artworks/{id}.jpg`).
- Keys : les 24 valeurs Camelot `1A`…`12B` (statiques).

## Design system — contraintes (rappel)

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. Zéro couleur hardcodée.
- **Typo** : `--font-ui` (Space Grotesk) pour le texte, `--font-mono` (JetBrains Mono) pour les données numériques (BPM, key, durées, années, compteurs).
- **Thèmes** : `[data-theme="dark"]` par défaut + light — la maquette supporte les deux.
- **Responsive** : container queries (`@container`), jamais `@media` sauf éléments `position: fixed` (le drawer mobile peut en être un). Convention repo : seuils 720/640.
- **CSP stricte** : icônes/logos en SVG inline ou data-URI, aucun CDN, aucune font externe.
- **UI en français.**
- **Monochrome `currentColor`** pour toute iconographie — l'accent mauve reste le seul signal coloré.

## Récapitulatif des livrables

| Fichier | Contenu |
|---------|---------|
| `BRIEF-explorer.md` | Handoff page : head, filtres, table virtualisée, états, responsive, tokens |
| `BRIEF-filtres-partages.md` | Spec réutilisable de la mécanique de filtres (réutilisée par la page Radar) |
| `Explorer (pilote).html` | Maquette interactive (page + états filtres + drawer mobile, toggles theme/viewport) |
| **Archive ZIP unique** | Les 3 livrables téléchargeables en un lien |

# Handoff — Refacto pages détail Diggy (Vague 3)

Maquette pilote validée (2 rounds de retours William) pour les 4 pages détail.

## Contenu

| Fichier | Rôle |
|---|---|
| `Pages détail (pilote).html` | Pilote 4 pages (Track / Artist / Set / Playlist) — ouvrir dans un navigateur |
| `pages-detail.css` | CSS de la maquette (référence visuelle — **pas** à copier tel quel dans Vue) |
| `pages-detail-data.js` | Données de démo + rendu + interactions de la maquette |
| `BRIEF-detail-pages.md` | **LE document à suivre** — changements par page, niveau (✅/🔧/⚙), récap backend |
| `diggy-tokens.css` | Tokens (déjà en prod — pour référence) |
| `diggy-style-map.js` | Palette StyleTag 5 familles (déjà en prod — pour référence) |

## Comment lire la maquette

Ouvrir le `.html`. Barre du haut = **outil de revue** (hors produit) :
- **Page** : bascule Track / Artist / Set / Playlist
- **Thème / Densité / Admin / Largeur** : états à vérifier
- **Annot. backend** : sur `on`, surligne (contour magenta + puce ⚙) tout ce qui **demande un travail API**

## Ordre d'implémentation conseillé

1. Les ✅ (câblage pur, aucune dépendance) sur les 4 pages
2. Les 🔧 (composants existants à replacer : LikeDislike, RingPct, play/preview)
3. Les 3 chantiers ⚙ backend, listés en fin de brief :
   - `DJSetDetailOut.genres[]` (expose `set_genres`)
   - Agrégats playlist **et** set (top artistes + top genres) pour les blocs « Dans cette playlist / Dans ce set »
   - Pagination tracks artiste (au-delà de 50)
   - (+ liste d'IDs covers pour la bannière-mosaïque artiste)

Respecter toutes les conventions de `CLAUDE.md` (tokens uniquement, container queries, mono pour les données, `--pos` pour in-lib, admin role-gated).

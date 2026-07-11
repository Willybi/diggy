# Brief — Sets (pilote réaligné)

> Maquette : `realign/Sets (pilote).html` · Tokens : `realign/diggy-tokens.css` · Cible Vue 3.

## Structure
Table : **Set** (artwork + titre + DJ/artistes) · **Date** (mono) · **Tracks** (anneau %) · **Durée** (mono) · **action Suivre**.
Header : titre « Sets » + compteur, search « Rechercher… », filtre segmenté **Tous / Suivis**, bouton **+ Ajouter** (accent).

## Anneau « tracks identifiées » (remplace `19/19`)
- Donut SVG + **%** mono à côté. `p = round(ident/total*100)`.
- Couleur : **100% → `--pos`** (vert), **≥60% → `--accent`** (mauve), **<60% → ambre** (`oklch(0.74 0.13 60)`).
- `title` = « 13 / 13 tracks identifiées » (le ratio brut reste accessible au survol).
- Idée : pendant l'analyse d'un set fraîchement ajouté, l'anneau se remplit en live (polling).

## Bouton Suivre
- **Non suivi → « Suivre »** (filled `--accent`). **Suivi → « Ne plus suivre »** (ghost, hover `--neg`).
- Pour l'instant : suivre ne fait que **basculer l'état/couleur** (pas d'action en aval — confirmé willi).
- Filtre **Suivis** → n'affiche que les sets suivis.

## Formulaire d'ajout (panneau inline, toggle « Ajouter » ↔ « Annuler »)
2 sous-onglets :
- **Rechercher** — va chercher via l'API (par track id). Champ + bouton « Rechercher » → liste de résultats
  (artwork, titre, source · N tracks · date) avec bouton **« Importer + Suivre »** ; déjà importé → **« Importé »** inerte.
- **URL** — coller une URL déjà connue. Placeholder `URL TrackID (ex : https://trackid.net/audiostream/…)` + bouton « Importer ».

## Responsive (container-queries)
≤1040 Durée tombe · ≤900 sidebar rail · ≤820 Date tombe (search pleine largeur) · ≤600 % de l'anneau masqué (donut seul).
→ Set + Tracks + Suivre survivent toujours.

## À confirmer / fournir (willi)
- Seuils de couleur de l'anneau (60/100 proposés) OK ?
- L'analyse live (anneau qui se remplit) est-elle en place côté back, ou statique pour l'instant ?

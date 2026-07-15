# Genres (liste) — `/genres`

Statut : ✅ figé  |  Vue : `views/GenresView.vue` + `components/GenreCard.vue`

## 1. Ce qu'on a (actuel)

**Données** : `/api/genres` via `usePaginatedList` (pageSize 24 ; sort / family / query). Item : name, pillar, depth, trackCount, artistCount, inLibCount, bpmLo/bpmHi, artworks[], artists[] (top 3 + image).

**Structure** :
- **Header** : titre « Genres » + compteur, SearchBox, SegFilter (Tracks / A–Z / Liked / Disliked).
- **Admin strip** (`is_admin` uniquement ✅) : compteur de tracks sans genre + « Lancer le classement auto ».
- **FamilyChips** (filtre pilier).
- **Grille** `GenreCard` + **infinite scroll** (`usePaginatedList` ✅).

**GenreCard** :
- **Art** : mosaïque 2×2 (4 covers, placeholders teintés) + scrim ; overlays : badge **in-lib « N en bib »** (haut-gauche), **avatars** top-3 artistes (bas-gauche), **like/dislike** (haut-droit, hover), **play** (bas-droit, hover).
- **Body** (teinté pilier) : dot + nom + pilier ; stats **Tracks · Artistes · BPM range**.
- Liké = bordure verte, disliké = estompé.

**Constat** : page **déjà exemplaire** — `usePaginatedList`, admin **gaté** `is_admin`, **aucun rating**, rien de mort. In-lib affiché **une seule fois** (badge, pas de doublon).

## 2. Vision (William)

- Affichage **clean**, aimé. Ne voit pas trop quoi améliorer → **Claude propose** des modifs.

## 3. Proposition (Claude) — polish léger

Honnêtement la page est solide ; voici des retouches **optionnelles** :

1. **Tri « En bib »** dans la SegFilter (la liste Artistes l'a → cohérence entre les deux listes).
2. *(option)* **Signal « tendance »** sur les genres qui montent — via la **velocity des familles du Radar** — une petite flèche ▲ sur la card. Relie **Radar ↔ Genres** et donne du mouvement.
3. **Cohérence in-lib** : ArtistCard = in-lib en **stat** ; GenreCard = in-lib en **badge**. Pas de doublon ni l'un ni l'autre, mais représentation différente → au moins **harmoniser le style visuel** du badge/indicateur (détail, pas structurel).

**Réponses (William)** : tri « En bib » ✅ · signal tendance ❌ · in-lib **harmonisé**.

## 4. Ré-allocation des points retirés
- **Signal « tendance »** → écarté.
- Rien de structurel retiré (page déjà propre).

## 5. Décisions figées
- **Tri « En bib »** ajouté à la SegFilter (cohérence avec la liste Artistes).
- **Signal « tendance »** : écarté.
- **In-lib harmonisé = stat sur les deux cards** (aligné sur la décision liste Artistes) : **GenreCard retire le badge overlay in-lib** et **ajoute « En bib » aux stats** → Tracks · Artistes · BPM · En bib. **Layout exact à valider au design** (si 4 stats serrent la card, le BPM range remonte près du pilier).
- **(recap C2)** : ajouter le **% de couverture bib** (`inLibCount / trackCount`) — le recap le qualifie de **signal de dig le plus actionnable** ; affiché à côté de l'in-lib (petit % ou mini-barre).
- **Gardé** : mosaïque teintée, avatars, like/dislike, play, admin gaté `is_admin`, infinite scroll.

## 6. Sortie next-step
**Handoff Design**
- [ ] GenreCard : in-lib en **stat** (retrait badge, ajout « En bib ») → valider le layout (4 stats vs BPM près du pilier).

**Chantier work_manager**
- **Front** : SegFilter + **tri « En bib »** ; GenreCard : in-lib en stat.
- **Back** : `/api/genres` — supporter le **sort par in-lib** (`sort=lib`) s'il ne l'est pas déjà (l'endpoint artistes l'a).
- **Transverse** : cohérence des cards (in-lib en stat partout).

**Dépend de** : rien de bloquant.

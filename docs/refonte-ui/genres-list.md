# Genres (liste) — `/genres`

Statut : ✅ figé  |  Vue : `views/GenresView.vue` + `components/GenreCard.vue`

> **Précisions pré-vol 2026-07-28 (chantier liste Genres, D6 p.7) — priment sur le reste de la fiche en cas d'écart.**
> Vérifs code réel + prod (SQL read-only, user 2) avant le prompt Design :
> - **`% de couverture bib` (recap C2, §5) → RETIRÉ.** Mesure prod : le ratio `inLibCount / trackCount` vaut **0,1–5,0 %** sur TOUS les genres (max absolu **5 %** = Trance ; 0,3–2,5 % ailleurs) parce que `trackCount` est le compte catalog **global** (~127k, non filtré `catalog_visible`) et `in_lib_count` la sous-partie perso. Une barre/% serait **near-empty sur 100 % des cards** = signal visuel mort (**même piège que l'anneau toujours-100 % de /sets**). William tranche : **on retire le %**. Le **compte in-lib brut reste** (vrai signal : 132 / 79 / 68 … → 0, `max_lib=132`).
> - **In-lib en STAT confirmé** : `inLibCount` déjà renvoyé par le back ; cible = pattern `ArtistCard` (valeur `--pos-ink` si > 0, « — » `--ink-3` sinon). GenreCard **retire le badge overlay `.gc-lib`** et ajoute « En bib » aux stats → **Tracks · Artistes · BPM · En bib** (compte, sans %). Layout 4 stats = latitude Design (fiche §5 : si ça serre, BPM remonte près du pilier).
> - **Tri « En bib » = LOT BACK léger.** `/api/genres` n'accepte que `sort=^(tracks|alpha)$` — **`lib` absent** (l'endpoint **Artistes l'a déjà** : `^(catalog|lib|liked|disliked|alpha)$`). Le tri est fait **en Python sur le `fetchall` complet** (`list_genres`, pas de LIMIT SQL) → ajout trivial : étendre le pattern router + branche `elif sort == "lib"` (tri `-in_lib_count`, tie-break `-track_count`, `name`). `in_lib_count` déjà calculé dans le SQL. **Aucune migration.**
> - **État code réel vs fiche §1** : Admin strip **déjà gaté `is_admin`** ✅ · **aucun rating** (page déjà propre) ✅ · `usePaginatedList` ✅ · mosaïque/avatars/like-dislike/play **présents** ✅. Ce ne sont PAS des dettes.
> - **`GenreCard` est PROPRE à cette page** (seul consommateur = `GenresView`) → redessinable librement. **Aucun composant transverse nouveau** créé par cette page. `<LikeDislike>` consommé tel quel.

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
- **(recap C2)** : ~~ajouter le **% de couverture bib** (`inLibCount / trackCount`)~~ → **RETIRÉ au pré-vol 2026-07-28** (voir bloc en tête) : ratio 0,1–5,0 % constant en prod = signal visuel mort (piège /sets). Seul le **compte in-lib** est conservé (en stat).
- **Gardé** : mosaïque teintée, avatars, like/dislike, play, admin gaté `is_admin`, infinite scroll.

## 6. Sortie next-step
**Handoff Design**
- [ ] GenreCard : in-lib en **stat** (retrait badge, ajout « En bib ») → valider le layout (4 stats vs BPM près du pilier).

**Chantier work_manager**
- **Front** : SegFilter + **tri « En bib »** ; GenreCard : in-lib en stat.
- **Back** : `/api/genres` — supporter le **sort par in-lib** (`sort=lib`) s'il ne l'est pas déjà (l'endpoint artistes l'a).
- **Transverse** : cohérence des cards (in-lib en stat partout).

**Dépend de** : rien de bloquant.

## 7. Handoff Design (livré 2026-07-29) — décisions DA qui raffinent le §5

Handoff versionné : `docs/refonte-ui/handoff-genres-list/` (BRIEF + README de provenance + check conformité PASS). Ces décisions **complètent** le §5 (tel qu'amendé par le bloc pré-vol), elles ne le contredisent pas.

- **G1 — Le BPM sort de la ligne de stats** vers une **ligne de signature** (`HOUSE · 93–136 BPM`) sous le nom ; la ligne de stats reste à **3 comptes homogènes** : **Tracks · Artistes · En bib**. C'est l'option (b) explicitement offerte au pré-vol (« si 4 stats serrent, le BPM remonte près du pilier »). Body en 3 étages : nom / signature pilier+BPM / 3 stats.
- **G3 — « En bib » = 3ᵉ stat, fer à droite, seule couleur du body** : dot 6 px `--pos` + valeur `--pos-ink` quand > 0 ; **« — » `--ink-3` sans dot** quand 0 (34/75 genres à 0). Rappel formel du dot vert de l'ex-badge, déplacé en stat. Pattern identique à `In Lib` d'`ArtistCard`.
- **G8 — Avis : hover-reveal par défaut, bouton actif ÉPINGLÉ** quand un avis est posé (l'autre reste hover). Réalisé en `:deep()` scopé, `<LikeDislike>` non modifié.
- **G13/G14 — Grille jamais 1 colonne** (2 col fixes < 640 ; palier intermédiaire 216 px car card paysage) + **container queries par card** (243/219 ; sous 219, stats en 2 lignes, « En bib » sur sa propre ligne). Reprise de `ArtistCard` A12/A13.
- **G6 — Raffinements art** : scrim allégé en haut / renforcé en bas ; tuiles placeholder **teintées pilier** (genre sans covers reste identifiable, jamais un trou gris).
- **G11 — Admin strip** : traitement neutre (surface + filet, pas d'ambre = pas une alerte, c'est un stock permanent) + **repli mobile corrigé** (texte pleine largeur, bouton dessous).
- **Empty states facettes Liked/Disliked** : pastille colorée + bouton retour + pédagogie de l'avis (modèle empty « Suivis » d'`/artists`).

**Lot back confirmé (léger, aucune migration)** : `/api/genres` pattern `^(tracks|alpha)$` → `^(tracks|alpha|lib)$` + branche `elif sort == "lib"` dans `list_genres` (tri `-in_lib_count`, tie-break `-track_count`, `name`).

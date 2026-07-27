# FIX — Playlists (liste) `/playlists` · Revue post-implémentation

> Revue **unique** du rendu déployé (captures 01/03/04/05/06, 1440 px + 375 px) contre `BRIEF-playlists-list.md`. Mesures relevées sur les captures (± 1 px). Périmètre : conformité au brief + qualité visuelle. Les 5 arbitrages actés (libellé de cadence, sticky top 0, Crawl au survol, glyph non cliquable + son tooltip, 1 chip repliée) ne sont pas comptés comme écarts.
>
> **Verdict : l'implémentation est fidèle sur l'essentiel** (structure de colonnes, retrait de l'`external_id`, glyph source accolé au titre, genre en colonne repliable, nombre brut aligné droite, tri par en-tête + accent sur la colonne active, wash liked, modal, mobile à 3 lignes). **6 écarts**, dont **2 de placement** qui expliquent très probablement le ressenti « mal placé ».

---

## E1 — [visuel] · Le bloc « Dernier crawl » flotte au-dessus de la ligne de base de la rangée ⚠️ **priorité 1**

**Emplacement** : colonne Dernier crawl, toutes les rangées **sans pastille de cadence** (≈ 3/4 des rangées) — capture 01, rangées *Acid Essentials*, *Afterhours*, *Ambient Classics*, *Chicago House*…

**Constaté** : la date relative est rendue **~13 px au-dessus du centre optique de la rangée** (« aujourd'hui » à y ≈ 138 quand le titre, le créateur, le nombre de tracks et les boutons d'avis sont à y ≈ 151). La cellule réserve toujours ses 2 lignes (L1 date 19 px + L2 cadence/bouton 24 px) et centre le **bloc de 43 px** ; comme L2 est vide au repos, seule la ligne haute est visible → la donnée paraît décrochée vers le haut. C'est le seul élément de la rangée qui n'est pas sur la ligne de base commune, et l'œil le lit comme un défaut d'alignement.

**Attendu** (P4) : hauteurs de ligne réservées **pour éviter tout décalage au survol**, mais la donnée visible doit rester sur la ligne de base de la rangée.

**Reco** : réserver L2 **uniquement quand la rangée porte une pastille de cadence**. Rangée sans cadence → cellule sur **une seule ligne centrée** : `date … [Crawl au survol, aligné à droite]` (le bouton occupe l'espace horizontal libre — aucun reflow vertical au survol). Rangée avec cadence → stack 2 lignes actuel (date / cadence + bouton), lui aussi centré. Bénéfice : plus aucune rangée décrochée, et la cadence redevient un signal *distinctif* (la rangée qui en porte une est la seule à 2 lignes).

---

## E2 — [visuel] · Demi-droite de la rangée déséquilibrée : Créateur respire trop, Tracks colle à Dernier crawl ⚠️ **priorité 2**

**Emplacement** : colonnes Créateur · Tracks · Dernier crawl — capture 01.

**Constaté** : `TIDAL` (7 caractères, valeur la plus fréquente) occupe une colonne de ~148 px suivie de ~90 px de vide, tandis que le nombre de tracks (aligné droite, `45` se termine à x ≈ 1120) et la date (alignée gauche, commence à x ≈ 1136) sont séparés par **~16 px** : les deux données mono se lisent comme un seul bloc (« 45 aujourd'hui », « 472 il y a 15 j »). Le vide est du mauvais côté.

**Attendu** : gouttière homogène `--space-3` (12 px) **perçue**, ce qui suppose de compenser le fait que Tracks est fer à droite et Dernier crawl fer à gauche (les deux valeurs se rapprochent optiquement de la gouttière, contrairement aux colonnes fer-à-gauche).

**Reco** : reprendre les largeurs à somme constante — Créateur `148 → 128`, gouttière avant Tracks portée à `--space-4` (16 px) **ou** Dernier crawl `184 → 200` avec un `padding-left: var(--space-2)` sur la cellule Tracks. Objectif : ≥ 24 px de blanc entre le dernier chiffre et le premier caractère de la date.

---

## E3 — [spec] · Segment d'avis actif coloré en positif au lieu de l'accent

**Emplacement** : SegFilter du head, segment **Liked** actif — capture 04 (comparer à *Toutes* actif, capture 01 : mauve).

**Constaté** : `Liked` actif = fond/texte **teinte positive** (vert prairie). `Toutes` actif = `--accent-soft` / `--accent-ink`.

**Attendu** (P9 + grille d'audit) : **tous** les segments actifs en `--accent-soft` / `--accent-ink`. Le vert `--pos` est réservé à la sémantique d'avis dans la rangée (cœur, wash liked) ; l'employer aussi pour l'état « sélectionné » d'un filtre brouille les deux codes et casse la discipline « accent = sélection ».

**Reco** : uniformiser sur `--accent-soft` / `--accent-ink`. Si l'écho couleur filtre↔avis est jugé utile (défendable), le poser explicitement comme décision et l'appliquer **aux 4 segments** (Disliked en `--neg-soft`, À explorer en neutre) plutôt qu'à un seul — l'état actuel est un cas isolé.

---

## E4 — [spec] · Bouton « je n'aime pas » rendu en cœur barré, pas en pouce bas

**Emplacement** : colonne Avis, toutes les rangées — captures 01/04/05/06.

**Constaté** : le 2ᵉ bouton affiche un **cœur barré** ; les deux boutons partagent donc le même glyphe de base.

**Attendu** (tableau « Avis ») : cœur + **pouce bas** — deux glyphes distincts, lisibles à 14 px, différenciables au premier coup d'œil sans s'appuyer sur la barre oblique (fine, peu lisible à cette taille en dark).

**Reco** : si `<LikeDislike>` partagé impose le cœur barré (composant transverse, non modifiable pour cette page), c'est **mon brief qu'il faut corriger** — signalez-le et je le mets à jour. Sinon, revenir au pouce bas.

---

## E5 — [spec] · Chip de genre repliée trop grande en mobile

**Emplacement** : cellule Playlist < 720 px, chip sous le titre — capture 06 (375 px).

**Constaté** : la chip repliée est rendue à la **taille desktop** (hauteur ≈ 21 px, libellé ≈ `--fs-xs`), au point de peser visuellement autant que le titre ; elle prend toute la 2ᵉ ligne et pousse la méta crawl.

**Attendu** (P1/P12) : chip repliée = **`--fs-nano`, hauteur 20 px, dot 5 px** (la version desktop, `--fs-xs` / 22 px / dot 6 px, reste réservée à la colonne).

**Reco** : appliquer la variante nano sous 880 px. Gain : la 2ᵉ ligne redevient secondaire face au titre et la rangée mobile regagne ~4 px.

---

## E6 — [visuel] · Flèche de tri collée au libellé d'en-tête

**Emplacement** : en-tête `PLAYLIST↑` (et toute colonne triée) — captures 01/04/05/06.

**Constaté** : `PLAYLIST↑` sans blanc entre le libellé uppercase (tracking 0,07em) et la flèche ; le tracking rejette l'espace **après** la flèche, ce qui fait lire un caractère collé.

**Attendu** : `gap: var(--space-1)` (4 px) entre libellé et indicateur.

**Reco** : `gap: var(--space-1)` sur le bouton d'en-tête + `letter-spacing: normal` sur la flèche.

---

## Points vérifiés conformes (pour mémoire)

Retrait total de l'`external_id` · glyph source accolé au titre, titre en ellipsis avant le glyph · genre en colonne dédiée avec 1ʳᵉ chip non comprimée, repli à 1 chip sous 720 px · `track_count` brut mono fer à droite, pas d'anneau · date relative mono + pastille de cadence **uniquement quand la donnée existe** · en-tête triable avec colonne active en `--accent-ink` · aucune pagination · wash liked (`--pos-wash`) et sous-compteur « 56 playlists · 9 likées » (ajout utile, cohérent) · modal Ajouter (label mono uppercase, champ URL mono 44 px, aide 2 lignes, `.btn--accent` « Ajouter ») conforme, overlay et centrage OK · light/dark tous deux corrects, aucun mauve parasite · mobile 375 px : 3 lignes max par rangée, avis tactiles conservés, Tracks conservé, pas de scroll horizontal.

---

## Ordre de traitement conseillé

1. **E1** (placement — c'est très probablement le « mal placé » ressenti)
2. **E2** (équilibre de la demi-droite, même sensation)
3. **E6** (2 lignes de CSS, visible sur toutes les captures)
4. **E5**, puis **E3** / **E4** (arbitrages à confirmer)

---

## Triage work-manager (Claude Code, 2026-07-26) — chaque [spec] vérifié contre le code

| Écart | Verdict | Justification (vérifiée dans le code) |
|---|---|---|
| **E1** — bloc crawl décroché vers le haut | ✅ **ACCEPTÉ** (priorité 1) | Réel : `.pl-crawl` réserve L1 19px + L2 24px centrés ; L2 vide au repos → la donnée L1 flotte ~13px au-dessus du centre. C'est très probablement le « mal placé ». Fix = 1 ligne centrée sans cadence, 2 lignes seulement avec cadence. |
| **E2** — demi-droite déséquilibrée | ✅ **ACCEPTÉ** (priorité 2) | Réel : gouttière `--space-3` (12px) entre `track_count` fer-à-droite et date fer-à-gauche → les 2 mono se collent. Fix = grille `190/128/64/196` + paddings pour ≥24px de blanc. |
| **E6** — flèche de tri collée | ✅ **ACCEPTÉ** | Réel : `.pl-arr { margin-left: --space-05 }` (~2px) + tracking 0.07em de l'en-tête → collé. Fix = `gap --space-1` + `letter-spacing: normal` sur la flèche. |
| **E5** — chip genre repliée trop grande (mobile) | ✅ **ACCEPTÉ** | `StyleTag` n'a **pas** de prop taille (fixe `--fs-sm`, dot 7px) → repli mobile à taille desktop. Fix = override `:deep(.style-tag)` scopé (nano) dans `.pl-genre-fold` sous 880px. |
| **E3** — segment Liked actif en vert (≠ accent) | ❌ **REJETÉ** (convention partagée) | Vérifié : `SegFilter.vue` colore **par design** `.liked.on`→`--pos-soft` et `.disliked.on`→`--neg-soft` (écho des couleurs d'avis). Convention **transverse** utilisée par Sets/Artistes/Explorer. La changer = modifier le composant partagé (hors périmètre page) ou désaligner Playlists des autres listes. L'option (b) de Claude Design est **déjà** ce que fait le code. → décision transverse éventuelle sur `SegFilter`, pas un correctif de cette page. |
| **E4** — dislike en cœur barré (≠ pouce bas) | ❌ **REJETÉ** (composant partagé) | Vérifié : `LikeDislike.vue` rend le dislike en **cœur + barre oblique** (path `M4.5 19.5 22 2`), glyphe **app-wide** (Explorer/Sets/Track Detail…). Non modifiable pour une page (règle refonte). → c'est **le brief** à corriger (Claude Design l'a proposé), pas le code. |
| **+ Cadence** (hors FIX) | ✅ **relabel** | Décision produit William : `Quotidien/Hebdo/Mensuel` → **fraîcheur brute** `MAJ ` + `relativeAgeShort(last_changed_at)` (« MAJ 3 j »), tooltip inchangé. Bundlé dans le même lot correctif. |

**Lot correctif = E1 + E2 + E5 + E6 + relabel cadence** (front-only, un déploiement). E3/E4 non touchés (justifiés ci-dessus).

## Statut — corrections appliquées (pilote v4 + brief)

| Écart | Statut | Action |
|---|---|---|
| **E1** | ✅ corrigé | Défaut de ma spec. Bloc crawl à géométrie variable : **1 seule ligne centrée** (`date … [Crawl fer à droite]`) sur les rangées sans cadence, 2 lignes uniquement avec cadence. Brief P4 + section « Bloc Dernier crawl » réécrits, pilote à jour. La rangée à 2 lignes devient un signal distinctif de cadence. |
| **E2** | ✅ corrigé | Défaut de ma spec. Grille `190 / 128 / 64 / 196` + `padding-right: --space-2` sur Tracks et `padding-left: --space-2` sur Dernier crawl → **28 px de blanc perçu** entre le nombre et la date ; les 20 px repris à Créateur suppriment son excès de vide. |
| **E6** | ✅ corrigé | Flèche de tri dans son propre `<span>` en `letter-spacing: normal`, `gap: --space-1` sur le bouton d'en-tête. Explicité dans « En-tête sticky ». |
| **E5** | ⚠️ régression d'implémentation | Le pilote applique déjà la variante nano (20 px, `--fs-nano`, dot 5 px) sous 880 px — rien à changer côté design, à reprendre côté code. |
| **E3** | ⏳ arbitrage | Le pilote a toujours les 4 segments actifs en `--accent-soft` / `--accent-ink`. Deux issues : (a) revenir à l'accent partout — recommandé, discipline « accent = sélection » ; (b) acter l'écho couleur filtre↔avis et l'appliquer aux 4 segments (Liked `--pos-soft`, Disliked `--neg-soft`, Toutes / À explorer neutres). L'état déployé (un seul segment vert) n'est aucune des deux. |
| **E4** | ⏳ arbitrage | Le pilote utilise le **pouce bas**. Si `<LikeDislike>` impose le cœur barré à toutes les pages (composant transverse), confirme-le et je corrige le brief plutôt que le code. |

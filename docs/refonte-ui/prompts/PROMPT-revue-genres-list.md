# Prompt — Claude Design · REVUE post-implémentation · Genres (liste) `/genres` (D6 p.7)

> Round de revue UNIQUE et timeboxé. Objectif : vérifier la fidélité de l'implémentation
> déployée en prod à **TON** brief (`BRIEF-genres-list.md`), rien d'autre.
> Livrable attendu : **`FIX-genres-list.md`** — liste d'écarts, chacun tagué **[visuel]**
> (rendu) ou **[spec]** (non-conformité au brief), avec **valeur constatée** vs **valeur
> attendue** et le token/sélecteur concerné. Si tout est conforme, dis-le explicitement.

## Ce que tu revois

**Canal captures** — jeu produit en prod (headless authentifié, `https://diggy-music.fr/genres`), dossier joint. Chaque fichier :

| Fichier | Contenu |
|---|---|
| `01-desktop-dark-full.png` | Composition desktop dark 1440px : head (titre + « 75 genres », SearchBox, SegFilter **5 segments**), admin strip, FamilyChips, grille de cards (2 rangées). |
| `02-desktop-dark-cards-zoom.png` | Zoom rangée 1 (3 cards) — anatomie : mosaïque 2×2, avatars + « +N », body 3 étages (dot + nom / **signature `PILIER · lo–hi BPM`** / stats **Tracks · Artistes · En bib**), stat « En bib » fer à droite (dot vert + valeur `--pos-ink`, ou « — » si 0). |
| `03-desktop-light-full.png` | Même composition en light. |
| `04-desktop-dark-states.png` | Zoom rangée 1 avec 3 états forcés : card 1 **liked** (halo `--pos` + cœur plein épinglé), card 2 **disliked** (card estompée `opacity 0.45` + cœur barré épinglé), card 3 **hover** (play bas-droit + 2 boutons d'avis révélés). |
| `05-mobile-375-dark.png` | Mobile 375px : head empilé, SegFilter, admin strip replié, FamilyChips en wrap, grille **2 colonnes fixes** (jamais 1). |
| `06-mobile-card-zoom.png` | Zoom d'une card en 2-col mobile (~165px, container `<219px` déclenché) : stats sur **2 lignes** (Tracks + Artistes, puis « En bib » seul fer à droite avec filet), **3ᵉ avatar masqué**. |
| `07-desktop-dark-empty-liked.png` | Empty state facette **Liked** vide (pastille cœur `--pos-soft`, message, pédagogie, bouton « Voir tous les genres »). |

**Canal code** — relis sur GitHub (commit `b6b8a4f`, uniquement ces 2 fichiers) :
- `server/frontend/src/components/GenreCard.vue`
- `server/frontend/src/views/GenresView.vue`

Compare à **`BRIEF-genres-list.md`** (ton handoff, décisions G1–G15). **Interdiction** de commenter l'architecture JS, les patterns Vue, la structure des composants, le nommage, ou le back : périmètre = **fidélité visuelle/DA à ton brief**. Les placeholders assumés ne sont pas des écarts.

## Arbitrages d'implémentation DÉJÀ ACTÉS (ne pas les remonter comme écarts)

1. **`title` par segment de la SegFilter — NON implémenté.** `SegFilter` est un composant **partagé** (hors périmètre, non modifiable) qui n'accepte pas d'attribut `title` ; aucun `:deep()` ne peut injecter un attribut. Les libellés (Tracks/En bib/A–Z/Liked/Disliked) sont explicites.
2. **Cible tactile des boutons d'avis = 30px (pas 44px).** `<LikeDislike>` est **partagé** et fournit des boutons de 30px ; l'agrandir modifierait le composant (interdit). Le disque de 30px respecte le brief ; seul le **play** (construit dans la card) honore 44px cible / 30px disque. Écart app-wide identique à `ArtistCard` — à traiter au niveau du composant partagé, pas ici.
3. **Glyphe « dislike » = cœur barré** (pas un pouce). C'est le glyphe **réel** de `<LikeDislike>` (partagé, consommé tel quel) ; l'empty-state Disliked reprend ce même cœur barré pour cohérence avec le contrôle affiché. Le « pouce » du brief était une hypothèse — le glyphe réel prime.
4. **Scrim en `--hero-scrim-*`** (warm near-black, alpha 0,06→0,34→0,76) : ce sont les tokens que **ton brief G6 nomme explicitement**. La teinte pilier est portée par les **tuiles placeholder**, pas le scrim (qui doit porter fiablement les avatars en bas).
5. **Tuiles placeholder** : léger `filter: brightness` par tuile (±5%) pour éviter 4 carrés identiques quand un genre n'a pas de covers — effet imperceptible sur les vraies covers.

## Point ouvert à TON avis (le seul)

- **Signature tronquée en 2-col mobile** (`06-mobile-card-zoom.png`) : à ~165px de card, la ligne signature affiche « TECHNO · 70–145 B… » (le « BPM » est coupé). Est-ce acceptable à cette largeur extrême, ou proposes-tu un repli (ex. masquer « BPM » sous un seuil, abréger, ou passer la signature sur 2 lignes) ? Donne une reco actionnable si tu juges que ça mérite un fix.

## Format de `FIX-genres-list.md`

Pour chaque écart : `#`, tag **[visuel]**/**[spec]**, élément + sélecteur/token, **constaté** vs **attendu (réf. G# du brief)**, sévérité (bloquant / cosmétique). Ordonne du plus grave au plus léger. Si conforme sur un axe, écris-le. Pas d'archive nécessaire — un seul fichier `.md`.

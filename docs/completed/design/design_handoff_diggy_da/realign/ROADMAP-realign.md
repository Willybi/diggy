# Diggy — Roadmap de réalignement DA

> But : ramener la **prod actuelle** vers la **DA Wildflower v1** (tokens = frontière),
> écran par écran, par effet de levier. Source d'inventaire : `uploads/PAGES_REFERENCE.md`.
> Source visuelle de vérité : `reference/Diggy DA.html` + `diggy-tokens.css`.

---

## La boucle de travail (par lot)

1. **Toi →** tu m'envoies les **screenshots** des écrans du lot (light + dark selon décision #3)
   + une note des **patterns inventés en route** qui ne sont pas dans la DA.
2. **Moi →** je produis une **maquette HTML hi-fi alignée tokens** + un **mini-brief**
   (layout, composants, états hover/empty/loading, copy exacte, comportements)
   + j'ajoute/précise les lignes de checklist ci-dessous.
3. **Claude Code →** recrée en Vue 3 à partir de la maquette + brief, **coche** la case.
4. **Aller-retour** si une question de design surgit en codant.

**Règle d'or :** tout passe par les tokens. Le design ne livre aucune couleur/typo en dur ;
le code n'invente aucune valeur — il lit les `var(--…)`.

---

## La grille d'audit (appliquée à CHAQUE écran — le « ne rien oublier »)

Pour chaque page, on vérifie ces points récurrents de dérive :

- [ ] **Couleurs** : aucune valeur hors-tokens (hex en dur, orange).
- [ ] **Responsive** : large → laptop → tablet → narrow OK (cf. D+).
- [ ] **Admin role-gated** : blocs se détachent (surface utility) ET état "user normal" vérifié (cf. D2).
- [ ] **Accent discipliné** : `--accent` réservé à l'action / rating / key / score.
      Jamais en décor ni en fond de bloc gratuit.
- [ ] **In-lib = `--pos` uniquement**, jamais l'accent.
- [ ] **Boutons** : liens externes = `btn-ghost` ; CTA = `btn-accent`. (cf. FIX-round4)
- [ ] **Type** : UI/titres en `--font-ui` ; **données** (BPM, key, durée, score, dates) en `--font-mono`.
- [ ] **Densité** : hauteur de ligne = `--row-h` ; paddings = `--pad`.
- [ ] **Forme** : rayons (`--r-*`) et ombres (`--shadow-*`) via tokens.
- [ ] **StyleTag** : couleur dérivée de `diggy-style-map.js`, jamais à la main.
- [ ] **États** : hover / empty / loading définis et alignés.
- [ ] **Copy** : pas d'ambiguïté (ex. "ID" → "identifiées"), titres longs gérés (clamp).
- [ ] **Dark mode** : rendu vérifié si concerné.

---

## Vague 0 — Décisions transversales (à trancher maintenant)

- [x] **D1. Cible** : DA Wildflower telle quelle, on aligne. Évolution de la DA → plus tard.
- [x] **D2. Blocs admin** : nouvelle feature **role-gated** — visibles si user=admin, masqués sinon.
      Doivent **se détacher visuellement** comme éléments "utility" (surface + bordure tiretée dédiées,
      tokenisées — pas l'orange hors-DA). Toujours prévoir les 2 états (admin on / off).
- [x] **D3. Scope thème** : light **et** dark en parallèle.
- [x] **D4. Densité par défaut** : **regular**.
- [x] **D+. Responsive** : critère **permanent** sur chaque écran — vérifier l'adaptation
      large → laptop → tablet → narrow (sidebar qui se réduit, colonnes qui tombent, outils qui se replient).

---

## Vague 1 — Le kit (composants partagés)

Re-spec + maquette de référence à jour. Levier maximal.

- [ ] SidebarNav (232px, item actif `--accent-soft`/`--accent-ink`, compteurs mono, section admin)
- [ ] PageHero — variantes `square` / `round` / `wide`
- [ ] StatStrip
- [ ] RelBlock + AppearRow
- [ ] StyleTag
- [ ] ScorePill (0–10, 10 ticks)
- [ ] LibDot + InLibBadge
- [~] HeroPlayer + **player audio inline** (preview Deezer 30s) — **maquette + brief + prompt livrés** (`realign/Lecteur (pilote).html` + `BRIEF-player.md` + `PROMPT-claude-code-player.md`) : bandeau flottant global, equalizer + volume inline (figés), scrub, persiste entre routes. ⏳ à implémenter
- [ ] Système de **table** (header mono uppercase, hover `--surface-2`, tri, pagination)
- [ ] **Filtres / chips** (recherche debounce, chips toggle, persistance sessionStorage)

---

## Vague 2 — Les listes

- [x] **Catalog** `/catalog` — ✅ implémenté (fix round 5)
- [x] Radar `/radar` — ✅ implémenté
- [x] Sets `/sets` — ✅ implémenté
- [x] Artistes `/artists` — ✅ **v2 validée** (carte portrait, avatar teinté, rating étoile, stats Catalog/In Lib/Liked, tri Catalog·In Bib·Liked·Rating·A–Z, photos réelles + fallback initiales, dark mode, scroll infini). ⚠️ Fix API pending : `genres[]` trié par nb tracks desc.
- [x] Playlists `/playlists` — ✅ implémenté
- [~] Genre Detail `/style/:genre` — **maquette + brief livrés** (`realign/Genre Detail (pilote).html` + `BRIEF-genre-detail.md`) : hero mosaïque + blocs typés (Artistes/Sets/Playlists/Tracks) + genres voisins + admin rename/merge. ⏳ à implémenter (⚠️ check backend : agrégats + logique voisins)

---

## Vague 3 — Les pages détail

- [ ] Track Detail `/catalog/:id` (Hero + StatStrip + 3 blocs relationnels + bloc admin)
- [ ] Artist Detail `/artist/:id` (Hero round + aliases + bio + tracks + sets + bloc admin)
- [ ] Set Detail `/set/:id` (Hero wide + tracklist + états row unknown/id + bloc admin)
- [ ] Playlist Detail `/playlists/:id` (Hero square + StatStrip + table tracks)

---

## Vague 4 — Entrées & navigation

- [~] Genres `/tags` — **maquette + brief livrés** (`realign/Genres (pilote).html` + `BRIEF-genres.md`) : cartes riches (pas grille StyleTag simple), chips famille, scroll infini. ⏳ à implémenter
- [ ] Login `/login` (carte centrée 360px, sans sidebar)

---

## Vague 5 — Admin

- [ ] Panel `/admin` (sync artistes, artworks, artistes des sets, enrichissement Beatport,
      liaison Deezer double-colonne, flags artistes)
- [ ] Cartes admin inline (Track / Artist / Set detail) — selon décision **D2**

---

## Journal

| Date | Lot | Livré | Statut |
|---|---|---|---|
| 2026-06-21 | Roadmap | Plan + grille d'audit | ✅ établi |
| 2026-06-21 | Vague 0 | Décisions D1–D4 + D+ tranchées | ✅ |
| 2026-06-21 | Catalog | Maquette pilote `realign/Catalog (pilote).html` + brief | ⏳ en revue |
| 2026-06-23 | Genres `/tags` | Maquette `realign/Genres (pilote).html` + `BRIEF-genres.md` (cartes riches, chips famille, scroll infini) | ⏳ revue → code |
| 2026-06-23 | Genre Detail `/style/:genre` | Maquette `realign/Genre Detail (pilote).html` + `BRIEF-genre-detail.md` (hero mosaïque, blocs Artistes/Sets/Playlists/Tracks, voisins, admin rename/merge) | ⏳ revue → code |
| 2026-06-23 | Lecteur / Player (Vague 1) | Maquette `realign/Lecteur (pilote).html` + `BRIEF-player.md` + `PROMPT-claude-code-player.md` (bandeau flottant global, **equalizer + volume inline** validés, scrub, store audio, persiste entre routes) | ✅ implémenté (PlayerBar.vue + stores/audioPlayer.js) |
| 2026-06-23 | Lecteur — revue code | Implémentation analysée (store 1×`<audio>`, container sur wrapper OK, has_preview, persistance) + `PROMPT-claude-code-player-round2.md` (5 correctifs : icône row pause, seek clavier, échec preview, `--sidebar-w`, finitions) | ⏳ round 2 → code |
| 2026-06-23 | Artistes v2 `/artists` | Refonte DA complète : carte portrait inspirée Genres, `Artistes v2 (pilote).html` + `BRIEF-artists.md`. Implémenté + validé (light/dark, photos réelles, scroll infini, tri In Bib ajouté). Fix API pending : `genres[]` trié par poids. | ✅ clôturé |
| 2026-06-23 | Max-width global | Audit GitHub complet (toutes vues). `PROMPT-claude-code-maxwidth.md` livré : 2 tokens (`--page-max-w: 1400px`, `--detail-max-w: 1080px`), 6 vues liste + 5 vues détail, correctif DA bloc admin ArtistDetailView (D2 : `--line-2` dashed + `--surface-2`, virer `--warn-ink` hors-tokens). | ⏳ → code |

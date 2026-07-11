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
- [ ] HeroPlayer + **player audio inline** (preview Deezer 30s)
- [ ] Système de **table** (header mono uppercase, hover `--surface-2`, tri, pagination)
- [ ] **Filtres / chips** (recherche debounce, chips toggle, persistance sessionStorage)

---

## Vague 2 — Les listes

- [x] **Catalog** `/catalog` — _PILOTE_ ✅ aligné (fix round 5 appliqué : unicode, tags, palette 5 tons)
- [x] Radar `/radar` — ✅ maquette + brief (refonte modèle : tabs Tous/New/Liked/Disliked, reco)
- [x] Sets `/sets` — ✅ maquette + brief (anneau % tracks, form d'ajout 2 modes, suivre)
- [x] Artistes `/artists` — ✅ maquette (avatar circle, genres empilés, palette bornée, mono nums)
- [x] Playlists `/playlists` — ✅ maquette (badge source, Crawl now, form URL simple, Suivies/Toutes)
- [x] Genre Detail `/style/:genre` (liste compacte, pas de table)

---

## Vague 3 — Les pages détail

- [ ] Track Detail `/catalog/:id` (Hero + StatStrip + 3 blocs relationnels + bloc admin)
- [ ] Artist Detail `/artist/:id` (Hero round + aliases + bio + tracks + sets + bloc admin)
- [ ] Set Detail `/set/:id` (Hero wide + tracklist + états row unknown/id + bloc admin)
- [ ] Playlist Detail `/playlists/:id` (Hero square + StatStrip + table tracks)

---

## Vague 4 — Entrées & navigation

- [ ] Genres `/tags` (grille auto-fill, cartes StyleTag + compteur)
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
| 2026-06-22 | Catalog | Fix round 5 (unicode / tags / palette) appliqué par Claude Code | ✅ aligné |
| 2026-06-22 | Radar | Maquette `realign/Radar (pilote).html` + brief (refonte reco) | ⏳ en revue |
| 2026-06-23 | Artistes | Maquette `realign/Artistes (pilote).html` | ✅ |
| 2026-06-23 | Playlists | Maquette `realign/Playlists (pilote).html` | ✅ |

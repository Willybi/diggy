# Brief — Genre Detail `/style/:genre` (pilote réaligné)

> Maquette : `realign/Genre Detail (pilote).html` · Tokens : `realign/diggy-tokens.css` · Mapping : `realign/diggy-style-map.js`
> Cible Vue 3. La barre sombre en haut = **outil de revue** (thème / densité / admin / aperçu famille / largeur), **PAS dans le produit**.
> Page = 1re **vraie page détail**. Elle n'est **pas** une liste plate : c'est un **hero + une série de blocs typés** (Artistes · Sets · Playlists · Tracks) + **genres voisins**.

---

## 🛑 À FAIRE AVANT TOUT — check backend (décision willi)

**N'attaque pas le front avant d'avoir vérifié que la donnée existe.** Cette page agrège plusieurs entités
autour d'un genre. Mets ces points en to-do, vérifie chacun, **signale ce qui manque** avant de planifier l'UI.

- [ ] **Routing** — clé = **nom brut du genre, URL-encodé** (confirmé willi : `/style/Dance%20%2F%20Pop` = "Dance / Pop").
      Décoder côté route, matcher le genre par nom exact. ⚠️ gérer `/`, espaces, accents, casse. Garder ce contrat
      identique partout (StyleTag → lien).
- [ ] **Agrégats du genre** (hero + StatStrip) : `trackCount`, `artistCount` (distinct), `bpmLo/Hi` en **p5–p95** (décidé willi — déjà codé dans `server/api/routers/genres.py` via `PERCENTILE_CONT`),
      `inLibCount` (scopé user), `setCount`, `playlistCount`, `topArtists[]` (≤3 PP pour le hero), `covers[]` (≤6 pour la mosaïque). → existe ? à créer ?
- [ ] **Tracklist du genre** — pagination **serveur** (cursor/offset+limit) + **tri serveur** (`recent` / `bpm` / `key` / `alpha`)
      + **recherche `q`** (titre/artiste) + **filtre `inLib`**, tous appliqués serveur pour que la pagination reste cohérente.
      Param type : `?sort=bpm&q=&inLib=0&cursor=…&limit=50`. Champs/track : `cover`, `title`, `artist(s)`, `bpm`, `key` (Camelot),
      `duration`, `inLib`, `previewUrl`, `id` (→ `/catalog/:id`).
- [ ] **Top Artistes du genre** — artistes distincts ayant ≥1 track du genre, triés par `trackCountInGenre` desc.
      Champs : `id`, `name`, `trackCountInGenre`, `hasInLib` (≥1 track en bib), `photoUrl`. Lien → `/artist/:id`.
- [ ] **Sets liés** — sets contenant ≥1 track du genre. Champs : `id`, `title`, `date`, `trackTotal`, `trackInGenre`
      (→ anneau %), `coverUrl`. Tri par `trackInGenre` desc. Lien → `/set/:id`.
- [ ] **Playlists liées** — playlists (watchlist) contenant ≥1 track du genre. Champs : `id`, `name`, `source`
      (DEEZER/SPOTIFY/TIDAL), `trackInGenre`, `coverUrl`. Lien → `/playlists/:id`.
- [ ] **🔗 Genres voisins — LOGIQUE À CONCEVOIR (décision willi : "à prévoir par Claude Code")**
      Renvoyer les **X genres les plus proches** de celui-ci. Proposer + implémenter la métrique de proximité :
      **artistes en commun** et/ou **tracks co-occurrentes** (artistes/sets/playlists partagés).
      - Définir : pondération (artistes communs vs tracks communs vs co-présence en sets/playlists), `X` (≈ 6),
        seuil mini, et exclusion du genre courant.
      - Renvoyer par voisin : `name`, `family`, et le(s) compteur(s) "en commun" affiché(s) (`commonTracks`, `commonArtists`).
      - Perf : calcul potentiellement lourd → **précalcul / vue matérialisée** rafraîchie à l'ingest, pas live par hit.
      - **Remonte ta proposition de formule à willi avant de coder.**
- [ ] **Médias** (covers tracks/sets/playlists + PP artistes) — synchronisés et servables ? **Fallback** : placeholder
      teinté famille (déjà dans la maquette, classe neutre pour Misc) — acceptable au lancement.
- [ ] **Admin — fusion/rename** : endpoints `PATCH /api/admin/genres/:name` (rename) et
      `POST /api/admin/genres/merge { from, into }` (role-gated). Le **rename** doit re-router (l'URL = le nom) ;
      la **fusion** réaffecte les tracks de `from` vers `into` puis supprime `from`. Existe ? à construire ? Idempotence + confirmation.
- [ ] **Perf agrégats** — `artistCount` distinct, `inLibCount`, `bpm` percentiles, voisins : coûteux et **croissants**.
      Prévoir agrégats cachés (cf. même remarque que le brief Genres).

> Tant que ces points ne sont pas tranchés, ne « devine » pas le contrat d'API : remonte la liste à willi.

---

## Intention (décidé avec willi)

La page est **vierge en prod** (juste un header + liste plate). On repart de zéro : **hero type carte mosaïque**
(cohérent avec la page Genres) **+ blocs par type de données** plutôt qu'un simple dump de tracks.

## Layout — ordre des blocs (proposé)

`← Genres` → **Hero** → *(Admin)* → **Artistes** → **Sets** → **Playlists** → **Tracks** → **Genres voisins**

**Rationale de l'ordre** (willi a demandé une proposition) : les 3 blocs d'**entités** (Artistes / Sets / Playlists)
sont des **shelves horizontaux compacts** (peek + « Voir tout ») qui donnent un aperçu riche du genre en un écran ;
**Tracks** (le cœur, potentiellement 100s d'items) vient ensuite en **liste pleine** searchable/triable, et **Voisins**
clôt par « où aller ensuite ». On garde l'ordre listé par willi (Artistes, Sets, Playlists, Tracks) car les shelves sont
courts et ne repoussent pas trop la tracklist.

---

## Anatomie

### Hero (`.genre-hero`, PageHero "wide" teinté famille)
| Zone | Contenu | Notes |
|---|---|---|
| Mosaïque | collage **3×2** de covers représentatives, teinté famille | fallback placeholder teinté ; neutre (gris) si famille = Misc |
| Avatars | 3 PP rondes empilées + `+N` | bas-gauche, top artistes du genre |
| Play | bouton rond `--accent` | bas-droite, lance un aperçu (preview 30s enchaînées) |
| Titre | nom du genre `--font-ui` 34px, **couleur = famille** + pastille famille | `is-misc` → titre `--ink`, dot/tint neutres |
| Mood | label famille mono `--ink-3` | depuis `diggy-style-map` (FAMILIES[].label) |
| StatStrip | **Tracks · Artistes · BPM · En bib** | valeurs **mono** ; `En bib` en `--pos-ink` ; séparateurs `--line` |
| Actions | `▶ Écouter un aperçu` (`--accent`) + `Tout filtrer dans Catalog` (ghost) | 1 CTA primaire max |

- StatStrip volontairement = **les 4 stats de la carte Genres** (cohérence). Sets/Playlists counts vivent dans leurs block-heads.
- **Famille / couleur** : `--th` = hue famille (House 268 · Techno 312 · Trance 352 · Other 42). **Misc = neutre** (`.is-misc`).
  ✅ **Résolu (code)** : `server/api/routers/genres.py` mappe « Dance / Pop » en **`misc`** (tint **neutre**, bucketé sous la chip « Autre »). La maquette `is-misc` est correcte.
  Le sélecteur « Aperçu famille » de la barre de revue permet de prévisualiser le hero teinté dans les autres familles.

### Bloc Artistes / Sets / Playlists (shelves)
- **block-head** : `h2` + compteur mono + lien `Voir tout →` (vers Catalog/Artistes filtré par ce genre — contrat à définir).
- **shelf** : rangée **scroll horizontal** (`scroll-snap`), cartes `flex:none`.
- **Artist card** : avatar rond 80px (placeholder/PP), nom (ellipsis), `N tracks` mono, **dot `--pos`** en overlay si ≥1 en bib.
- **Set card** : artwork 16:9, **anneau %** (`= trackInGenre/trackTotal`, full≥80 `--pos` / mid≥45 `--accent` / low ambre) en haut-droite,
  badge "Set", titre 2 lignes clampées, méta `date · N de ce genre`. Réutilise l'anneau du pilote **Sets**.
- **Playlist card** : cover carrée, **badge source** (DEEZER `--accent-soft` / SPOTIFY `--pos-soft` / TIDAL `--surface-3`+bordure),
  compteur `N` (tracks de ce genre) en overlay haut-droite, nom 2 lignes. Réutilise le **badge source** du pilote Playlists.

### Bloc Tracks (liste compacte — **pas de table**, décision PAGES_REFERENCE)
- **tracks-head** : `h2` + compteur + outils → **search** (`Rechercher dans ce genre…`, debounce ~250ms),
  **tri segmenté** `Récent · BPM · Key · A–Z`, **toggle `En bib`** (chip `--pos` quand actif).
- **track-row** (hauteur `--row-h`) : play (révélé au hover) · cover 40px · titre + artiste · **BPM** (mono `--ink-2`) ·
  **Key** Camelot (mono `--accent-ink`) · **durée** (mono `--ink-3`) · zone lib droite =
  pastille **`EN BIB`** (`--pos`) si en bib, sinon bouton **`+`** (ajout, pointillé → `--pos` au hover).
- **Pas de StyleTag par ligne** (toutes les tracks = même genre → redondant).
- **Scroll infini** : batch 50 (maquette : 12), IntersectionObserver sur sentinel (spinner `--accent`, off en reduced-motion).
  Reset à chaque changement search/tri/lib. Brancher sur la pagination serveur (cursor).
- Tri **Key** = ordre **Camelot** (1A→12B), pas alpha brut.

### Bloc Genres voisins
- block-head `Genres voisins` + note `le plus en commun`.
- **voisin chip** (carte) : dot famille + nom (couleur famille) + métrique mono `N tracks · N artistes` (séparée par `--line`).
  `is-misc` → neutre. Clic → `/style/:genre`. Data = endpoint voisins (cf. check backend).

---

## Admin (role-gated — décision D2)

- **Bloc** sous le hero : `--surface-2` + bordure **tiretée** `--line-2`, label `ADMIN` mono. **Si `user.role !== 'admin'` → non rendu** (les 2 états sont à vérifier).
- Deux actions inline :
  - **Renommer** : `input` (pré-rempli au nom courant) + bouton → `PATCH …/genres/:name`. ⚠️ le nom = l'URL → **redirige** vers la nouvelle URL après succès.
  - **Fusionner dans** : `select` des autres genres + bouton → `POST …/genres/merge`. Réaffecte les tracks puis supprime le genre source ; **confirmation** + compteur de tracks impactées recommandés.
- Boutons = `btn-admin` neutre (`--surface`/`--line-2`, hover bordure `--accent`). Pas de `--accent` en fond.

## États à implémenter

- **hover** : cartes (élévation/translateY), play révélé sur track-row, `Voir tout` → `--accent-ink`.
- **empty** : tracklist filtrée vide → « Aucune track ne correspond. » mono `--ink-3`. Idem si un shelf est vide → masquer le bloc (ou message court).
- **loading** : skeleton hero (mosaïque + barres) au 1er chargement ; skeleton shelves ; skeleton rows + sentinel pour la tranche suivante.
- **404 genre** : si le nom décodé ne matche aucun genre → page « Genre introuvable » + retour `← Genres`.

## Responsive (container-queries sur `.app`, pas media-queries viewport)

| Largeur conteneur | Adaptation |
|---|---|
| ≤ 900px | sidebar → **rail 66px** |
| ≤ 820px | outils Tracks pleine largeur, search en dernier |
| ≤ 640px | paddings 18px, **durée masquée** dans les rows |
| ≤ 560px | mosaïque hero pleine largeur (stack) |

→ Les shelves scrollent horizontalement à toute taille ; hero, stats et rows ne se cassent jamais.

## Conventions (rappel — voir CLAUDE.md)
- 100% tokens `var(--…)`. Mono = **données** (BPM, key, durée, compteurs, dates), UI = titres/labels/boutons.
- `--accent` réservé action/key/CTA ; **in-lib = `--pos` uniquement** ; StyleTag/voisins via `diggy-style-map.js`.
- Densité via `--row-h`/`--pad` ; formes `--r-*` / `--shadow-*`.

## À trancher par willi
- **Voisins** : valider la **formule de proximité** (artistes communs ? tracks ? sets/playlists partagés ? pondération, X).
- **BPM** : ✅ **p5–p95** (décidé — déjà en place dans `genres.py`).
- **Dance/Pop** : ✅ **misc** / neutre (résolu côté code).
- **`Voir tout`** des shelves : destination exacte (Catalog/Artistes/Sets/Playlists pré-filtrés par genre — contrat d'URL).
- **Aperçu hero** : enchaînement de previews 30s (Deezer) ou lecture de la 1re track ?

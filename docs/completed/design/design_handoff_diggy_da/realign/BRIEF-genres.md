# Brief — Genres `/tags` (pilote réaligné)

> Maquette : `realign/Genres (pilote).html` · Tokens : `realign/diggy-tokens.css` · Mapping : `realign/diggy-style-map.js`
> Cible Vue 3. La barre sombre en haut est un **outil de revue**, PAS dans le produit.
> ⚠️ **Cette page n'est PAS une liste/table** comme Catalog/Radar : c'est une **grille de cartes riches**.

---

## 🛑 À FAIRE AVANT TOUT — check backend (décision willi)

**N'attaque pas le front avant d'avoir vérifié que la donnée existe.** Cette page consomme des
**agrégats par genre** + des **médias** que la prod n'expose probablement pas encore tels quels.
Mets ces points dans ta to-do, vérifie chacun, et **signale ce qui manque** avant de planifier l'UI.

- [ ] **Endpoint agrégat genres** — `GET /api/genres` (ou `/styles`) renvoyant **par genre** :
      `slug/id`, `name`, `family` (ou genre brut à mapper côté front), `trackCount`,
      `artistCount` (artistes distincts), `bpmLo` / `bpmHi`, `inLibCount` (scopé user),
      `artworks[]` (≤4 URLs), `artists[]` (≤3 URLs d'images). → existe ? à créer ? à étendre ?
- [ ] **Pagination serveur (cursor/offset + limit)** pour le **scroll infini**, ET le **tri**
      (`tracks` desc / `alpha`), le **filtre famille** et la **recherche `q`** appliqués **côté serveur**
      pour que la pagination reste cohérente. Param type : `?sort=tracks&family=House&q=&cursor=…&limit=24`.
- [ ] **Compteurs par famille** (badges des chips) — agrégat **indépendant de la pagination**
      (total réel par famille sur l'ensemble filtré). Idéalement renvoyé en `meta` de la réponse.
- [ ] **Mapping genre → famille** — finaliser `diggy-style-map.js` à partir d'un `SELECT DISTINCT`
      des genres réellement en base. Tout genre non mappé tombe en **Misc** (neutre), jamais une couleur au pif.
- [ ] **Slug/identifiant de routing** — clic carte → `/style/:genre`. Les genres sont-ils clés par
      **nom** (à slugifier, URL-safe + accents) ou par **id** ? Verrouille-le maintenant (resservira au lot Genre Detail).
- [ ] **Médias covers + PP artistes** — les artworks Deezer et les **photos d'artistes** sont-ils
      synchronisés et servables ? (cf. Vague 5 « sync artistes / artworks »). **Fallback prévu** : si absents,
      la carte dégrade proprement sur le placeholder teinté famille (déjà dans la maquette) — acceptable au lancement.
- [ ] **Admin — tracks sans genre** : `count` des tracks non classées **+** endpoint/job
      `POST /api/admin/genres/auto-classify` (role-gated). Existe ? à construire ?
- [ ] **Perf** — `bpmLo/Hi`, `artistCount` distinct et `inLibCount` sur tout le catalogue peuvent coûter cher
      et **grossiront avec la base**. Prévoir vue matérialisée / agrégats cachés rafraîchis à l'ingest
      plutôt qu'un calcul live à chaque hit.

> Tant que ces points ne sont pas tranchés, ne « devine » pas le contrat d'API : remonte la liste à willi.

---

## Intention (décidé avec willi)

La page Genres ne doit **pas** ressembler aux autres listes. Format **cartes type « playlist Deezer »** :
un visuel (collage de covers + photos d'artistes du genre) + des **stats lisibles d'un coup d'œil**.
Objectif = donner envie d'explorer un genre, pas dérouler un tableau.

## Anatomie d'une carte (`.genre-card`)

| Zone | Contenu | Notes |
|---|---|---|
| **Artwork** (h 130px) | Collage **2×2** des covers représentatives du genre | teinté famille en fallback ; scrim bas pour lisibilité |
| Badge in-lib | pastille `--pos` + `N en bib`, **haut-droite** | `--surface` + `--line` + `--shadow-sm` ; **masqué si 0** |
| Avatars artistes | 3 PP rondes empilées (overlap) + `+N` | bas-gauche, sur l'artwork (façon Deezer) |
| Play | bouton rond `--accent`, **révélé au hover** | bas-droite ; lance une preview du genre |
| **Titre** | nom du genre `--font-ui` 17px, **couleur = famille** | ellipsis 1 ligne ; pastille famille à gauche |
| Label famille | `House/Techno/Trance/Autre` mono uppercase `--ink-3` | aligné à droite du titre |
| **Stats** | 3 colonnes séparées par `--line` | **Tracks · Artistes · BPM**, valeurs **mono**, `white-space:nowrap` |

- **Tracks / Artistes** : `--font-mono`, séparateur de milliers (`1 180`) — **ne doit jamais wrap** (`nowrap`).
- **BPM** : `Lo–Hi` sur **une seule ligne** (`nowrap`). Voir sémantique ci-dessous.
- Grille : `repeat(auto-fill, minmax(296px, 1fr))`, gap 16px.
- Hover carte : `translateY(-2px)` + `--shadow-md` + bordure `--line-2`.

## Traitement des images — crop (⚠️ à corriger dans l'implé actuelle)

Sur la 1re implé, covers et avatars gardent leur **ratio natif** → tuiles inégales, pochettes déformées ou rognées de travers. Règle : l'image **remplit** sa cellule, recadrée au centre, jamais déformée ni de vide.

- **Tuiles du collage** : grille **2×2 strictement égale** (4 cellules **carrées**, même taille).
  Chaque cover : `width:100%; height:100%; object-fit:cover; object-position:center; display:block`.
  → recadrage *cover* (PAS `contain`, PAS d'étirement). La hauteur des tuiles est imposée par le conteneur, **pas** par le ratio de la pochette.
- **Conteneur artwork** : hauteur fixe (≈130px) → 2 rangées égales (`grid-template-rows:1fr 1fr`), 2 colonnes `1fr 1fr`.
- **Avatars artistes** : carré forcé (même w/h) + `border-radius:50%` + `object-fit:cover` → ronds nets, pas d'ovales.
- **< 4 covers disponibles** : combler les cellules manquantes par le **placeholder teinté famille** (jamais de trou blanc).
- `loading="lazy"` sur les covers hors viewport ; fond `--surface-2` sous l'`<img>` le temps du chargement.

## Sémantique des stats (à confirmer)

- **Tracks** : nombre de tracks rattachées au genre.
- **Artistes** : artistes **distincts** ayant ≥1 track dans le genre. *(dans la maquette c'est un ratio simulé — à remplacer par la vraie valeur.)*
- **BPM range** : ⚠️ **min–max brut sensible aux outliers** (un ambient 70 BPM noyé dans du House fausse tout).
  → recommandation : **p5–p95** (ou borne sur la médiane ±). **Décision willi** : min–max ou percentiles ?
- **In-lib** : nombre de tracks du genre présentes **dans la bib de l'user** (scopé user) ; badge masqué si 0.

## Chips de filtre par famille

- Rang de chips au-dessus de la grille : **`Tous · House · Techno · Trance · Autre`**, chacun avec **compteur mono**.
- Pastille de couleur famille sur chaque chip (sauf `Tous`). Chip actif = `--accent-soft`/`--accent-ink`
  (cohérent avec le segment de tri — l'accent marque la **sélection de contrôle**, pas de la déco).
- Filtre **client-perçu** mais **appliqué serveur** (voir check backend) ; un seul actif à la fois.

## Recherche + tri

- **Search** (debounce ~250ms) sur le nom de genre.
- **Tri** segmenté : **Tracks** (défaut, desc) · **A–Z**. Appliqué serveur (pagination cohérente).
- Sous-titre mono : `52 genres` ; si filtre/recherche actif → `7 / 52 genres`.

## Scroll infini (reveal progressif)

- Pas de pagination numérotée (genres = vocabulaire borné ; numéroter casserait recherche/tri globaux).
- Batch initial **~16–24** cartes, puis **IntersectionObserver** sur un **sentinel** en bas de grille
  qui charge la tranche suivante (`rootMargin` bas ~360px pour préfetch).
- Sentinel = ligne centrée mono `--ink-3` + spinner `--accent` (désactivé en `prefers-reduced-motion`).
  Masqué quand tout est chargé.
- Reset du `shown` à chaque changement de recherche / tri / famille.
- **Côté Vue** : brancher sur la pagination serveur (cursor) — la maquette simule en client sur un set complet.

## Admin (role-gated — décision D2)

- **Bande admin** au-dessus des chips : bloc `--surface-2` + bordure **tiretée** `--line-2`,
  label `ADMIN` mono, texte `<b>342</b> tracks sans genre attribué — à classer` + bouton **Lancer le classement auto**.
- **Si `user.role !== 'admin'` → bloc non rendu** (pas masqué CSS). Les 2 états sont à vérifier.
- Bouton = action → `btn` neutre `--surface`/`--line-2`, hover bordure `--accent`. (CTA réel à câbler sur le job auto-classify.)

## États à implémenter

- **hover** carte (élévation) + play révélé.
- **empty** : « Aucun genre ne correspond. » centré mono `--ink-3` quand recherche/famille ne renvoie rien.
- **loading** : skeleton de cartes (artwork + barres `--surface-2` shimmer) pour le 1er chargement
  et pour la tranche suivante (au-dessus du sentinel).

## Responsive (container-queries sur `.app`, pas media-queries viewport)

| Largeur conteneur | Adaptation |
|---|---|
| ≤ 900px | sidebar → **rail 66px** (icônes seules) |
| ≤ 820px | search pleine largeur, outils repliés |
| ≤ 720px | grille **2 colonnes** |
| ≤ 640px | paddings réduits (18px) |
| ≤ 520px | grille **1 colonne** |

→ La carte reste lisible à toute taille (stats + titre + artwork ne se cassent jamais).

## Route

- Page = **`/tags`** dans la roadmap, mais l'item de nav s'appelle **« Genres »**.
  → **Décision willi** : garder `/tags` ou renommer `/genres` ? (le slug interne genre reste séparé).
- **Clic carte → `/style/:genre`** (lot suivant : Genre Detail).

## À fournir / trancher par willi

- Les **7 points du check backend** ci-dessus (le plus urgent : contrat de l'endpoint agrégat + pagination).
- **BPM** : min–max ou **p5–p95** ?
- **Route** de la page : `/tags` vs `/genres`.
- Liste **exhaustive des genres** (`SELECT DISTINCT`) pour finaliser le mapping famille (commun à toutes les pages StyleTag).
- Disponibilité réelle des **covers** et **PP artistes** (sinon on lance avec le fallback teinté).
